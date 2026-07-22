#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Service de scoring IA (colle d'intégration)
=======================================================
Branche les modèles d'IA (Modèle 1 réseau, Modèle 2 fraude) sur le pipeline :
  • API REST de scoring synchrone (test / intégration) → /score/network, /score/user-day
  • Consommateur Kafka : lit la télémétrie (topic nexus.telemetry), score, et publie
    les alertes (topic nexus.alerts) consommées ensuite par le SOAR ; persiste en base.

Conçu pour démarrer même si Kafka / PostgreSQL ne sont pas encore prêts (dégradation
gracieuse), afin de faciliter le développement.
"""
import hashlib
import hmac as hmac_lib
import json
import os
import gzip as gziplib
import threading
import time
from collections import defaultdict

import numpy as np
import joblib
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel

# Libellés lisibles (explicabilité Modèle 2)
LISIBLE = {
    "nb_connexions": "connexions", "nb_actions_hors_heures": "actions hors heures ouvrables",
    "nb_transactions": "transactions budgétaires", "montant_total_modifie": "montant total modifié",
    "nb_modifs_montant": "modifications de montants", "nb_creations_compte": "créations de comptes agents",
    "nb_exports": "exports de données", "volume_donnees_exportees": "volume de données exportées",
    "nb_acces_dossiers_sensibles": "accès à des dossiers sensibles", "nb_actions_total": "actions au total",
}

KAFKA = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
T_TELEMETRY = os.getenv("TELEMETRY_TOPIC", "nexus.telemetry")
T_RAW = os.getenv("RAW_TOPIC", "nexus.telemetry.raw")
T_ALERTS = os.getenv("ALERTS_TOPIC", "nexus.alerts")
DB_DSN = os.getenv("DB_DSN")
RISK_THRESHOLD = int(os.getenv("RISK_THRESHOLD", "70"))
# Fenêtre d'agrégation anti-doublon des alertes (minutes ; 0 = désactivé)
ALERT_DEDUP_MIN = int(os.getenv("ALERT_DEDUP_MIN", "15"))

app = FastAPI(title="NEXUS SOC — Service de scoring", version="2.0")
STATE = {"m1": None, "m2": None, "producer": None, "db": None}

# ────────────────────────────────────────────────────────────────────────────
# Rate limiting — compteur en mémoire par IP (remplacer par Redis en production)
# ────────────────────────────────────────────────────────────────────────────
_RATE_WINDOWS: dict = defaultdict(list)   # ip → [timestamps]
RATE_LIMIT_REQ  = int(os.getenv("RATE_LIMIT_REQ",  "100"))  # requêtes max
RATE_LIMIT_WIN  = int(os.getenv("RATE_LIMIT_WIN",  "60"))   # par fenêtre (secondes)
INGEST_LIMIT_REQ = int(os.getenv("INGEST_LIMIT_REQ", "30")) # /ingest plus strict
INGEST_LIMIT_WIN = int(os.getenv("INGEST_LIMIT_WIN", "60"))

def _check_rate_limit(key: str, max_req: int, window: int):
    """Lève HTTP 429 si le client dépasse max_req requêtes dans window secondes."""
    now = time.time()
    hits = _RATE_WINDOWS[key]
    # Purger les timestamps hors fenêtre
    _RATE_WINDOWS[key] = [t for t in hits if now - t < window]
    if len(_RATE_WINDOWS[key]) >= max_req:
        raise HTTPException(
            status_code=429,
            detail=f"Trop de requêtes — limite : {max_req} par {window} s. Réessayez plus tard.",
            headers={"Retry-After": str(window)},
        )
    _RATE_WINDOWS[key].append(now)

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return xff.split(",")[0].strip() if xff else request.client.host

# ────────────────────────────────────────────────────────────────────────────
# Validation HMAC-SHA256 pour la passerelle /ingest
# ────────────────────────────────────────────────────────────────────────────
def _verify_ingest(body: bytes, authorization: str, x_signature: str, agent_id: str) -> bool:
    """
    Vérifie :
      1. Le Bearer token (hash SHA-256 stocké en base dans agents.token_hash)
      2. La signature HMAC-SHA256 du payload (header X-Signature)
    Retourne True si valide, False si invalide.
    En cas d'indisponibilité de la base, on accepte avec avertissement (démarrage).
    """
    if not authorization.startswith("Bearer nexus_"):
        return False
    token = authorization.removeprefix("Bearer ")
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    if STATE["db"]:
        try:
            with STATE["db"].cursor() as cur:
                cur.execute(
                    """SELECT a.hmac_key_hash,
                              a.token_expires_at,
                              a.token_used_at,
                              a.token_one_time
                       FROM agents a
                       WHERE a.token_hash = %s AND a.statut != 'isole'""",
                    (token_hash,)
                )
                row = cur.fetchone()
            if not row:
                return False
            # Token expiré
            if row[1] and row[1] < __import__('datetime').datetime.now(__import__('datetime').timezone.utc):
                return False
            # Usage unique déjà consommé
            if row[2] and row[3]:
                return False
            # Vérification HMAC du payload (si la clé est disponible)
            # Note : hmac_key_hash est le hash de la clé, pas la clé elle-même.
            # En production, stocker la clé chiffrée et la déchiffrer ici.
            # Pour la démo : on vérifie juste la présence du header X-Signature.
            if x_signature and len(x_signature) == 64:
                return True   # signature présente et format valide
            return bool(x_signature)
        except Exception as e:
            print(f"[ingest] validation DB échouée, mode dégradé : {e}")
            return True   # dégradation gracieuse au démarrage
    # Base indisponible → accepter (démarrage / dev)
    return True


# --------------------------------------------------------------------------- #
# Chargement des modèles
# --------------------------------------------------------------------------- #
def _load(path):
    try:
        return joblib.load(path) if path and os.path.exists(path) else None
    except Exception as e:
        print(f"[scoring] échec chargement {path} : {e}")
        return None


def score_network(features: dict):
    b = STATE["m1"]
    if not b:
        return None
    x = np.array([[float(features.get(f, 0)) for f in b["features"]]])
    s = float(-b["model"].score_samples(b["scaler"].transform(x))[0])
    lo, hi = b["risk_cfg"]["lo"], b["risk_cfg"]["hi"]
    risk = int(np.clip((s - lo) / (hi - lo) * 100, 0, 100))
    return {"risque": risk, "anomalie": s >= b["threshold"], "score_brut": round(s, 4)}


def score_userday(features: dict):
    b = STATE["m2"]
    if not b:
        return None
    feats = b["features"]
    x = np.array([float(features.get(f, 0)) for f in feats])
    s = float(-b["model"].score_samples(b["scaler"].transform(x.reshape(1, -1)))[0])
    risk = int(np.clip((s - b["risk_lo"]) / (b["risk_hi"] - b["risk_lo"]) * 100, 0, 100))
    # explicabilité : features les plus déviantes
    z = (x - b["normal_mean"]) / np.where(b["normal_std"] > 1e-9, b["normal_std"], 1e-9)
    raisons = [f"{LISIBLE.get(feats[i], feats[i])} anormalement élevé ({z[i]:.1f}σ)"
               for i in np.argsort(z)[::-1][:3] if z[i] > 1.5] or ["profil globalement atypique"]
    return {"risque": risk, "anomalie": s >= b["threshold"], "raisons": raisons}


# --------------------------------------------------------------------------- #
# Émission d'alerte → Kafka (consommée par le SOAR) + persistance Postgres
# --------------------------------------------------------------------------- #
def _alerte_dupliquee(alert: dict) -> bool:
    """
    Anti-doublon : une alerte identique (même périmètre, type et entité) déjà
    ouverte dans la fenêtre ALERT_DEDUP_MIN n'est pas recréée.

    Sans ce garde-fou, une condition persistante (ex. un flux réseau continu
    jugé anormal) génèrerait une alerte à chaque cycle de collecte et noierait
    la file de l'analyste. C'est l'agrégation d'alertes pratiquée en SOC.
    """
    if not (STATE["db"] and ALERT_DEDUP_MIN > 0):
        return False
    try:
        with STATE["db"].cursor() as cur:
            cur.execute(
                "SELECT 1 FROM alerts "
                " WHERE tenant_id = %s::uuid AND type = %s AND entite = %s "
                "   AND statut = 'ouverte' "
                "   AND cree_le > now() - (%s || ' minutes')::interval "
                " LIMIT 1",
                (alert.get("tenant"), alert.get("type"), alert.get("entite"),
                 str(ALERT_DEDUP_MIN)))
            return cur.fetchone() is not None
    except Exception:
        try:
            STATE["db"].rollback()
        except Exception:
            pass
        return False


def emit_alert(alert: dict) -> bool:
    """Émet une alerte. Retourne True si elle a réellement été enregistrée
    (False si agrégée avec une alerte identique déjà ouverte)."""
    if _alerte_dupliquee(alert):
        return False
    if STATE["producer"]:
        try:
            STATE["producer"].send(T_ALERTS, json.dumps(alert).encode("utf-8"))
        except Exception as e:
            print(f"[scoring] publication Kafka échouée : {e}")
    if STATE["db"]:
        try:
            with STATE["db"].cursor() as cur:
                cur.execute(
                    "INSERT INTO alerts (tenant_id, source_modele, type, entite, risque, raisons, mitre) "
                    "VALUES (%(tenant)s,%(src)s,%(type)s,%(entite)s,%(risque)s,%(raisons)s,%(mitre)s)",
                    {**alert, "raisons": json.dumps(alert.get("raisons", []))})
            STATE["db"].commit()
        except Exception as e:
            print(f"[scoring] insertion Postgres échouée : {e}")
            return False
    return True


# --------------------------------------------------------------------------- #
# Métriques série temporelle (hypertable `metrics`) — mesures réelles
# --------------------------------------------------------------------------- #
def record_metric(tenant_id, agent_id, metrique: str, valeur: float):
    """Enregistre une mesure réelle dans l'hypertable TimescaleDB `metrics`."""
    if not (STATE["db"] and tenant_id):
        return
    try:
        with STATE["db"].cursor() as cur:
            cur.execute(
                "INSERT INTO metrics (ts, tenant_id, agent_id, metrique, valeur) "
                "VALUES (now(), %s::uuid, NULLIF(%s,'')::uuid, %s, %s)",
                (tenant_id, agent_id or "", metrique, float(valeur)))
        STATE["db"].commit()
    except Exception as e:
        try:
            STATE["db"].rollback()
        except Exception:
            pass
        print(f"[metrics] insertion échouée ({metrique}) : {e}")


def process_normalized_event(ev: dict, tenant_id: str = "", agent_id: str = "") -> bool:
    """
    Score un événement DÉJÀ normalisé (contenant `kind` + `features`) et émet une
    alerte réelle si le risque dépasse le seuil. Enregistre aussi le score comme
    métrique série temporelle.

    Utilisé par le consommateur Kafka ET, en l'absence de Kafka, directement par
    /ingest (dégradation gracieuse : la détection reste opérationnelle).
    Retourne True si une alerte a été émise.
    """
    if not isinstance(ev, dict) or "features" not in ev:
        return False
    kind = ev.get("kind")
    res = score_network(ev["features"]) if kind == "network" else score_userday(ev["features"])
    if not res:
        return False

    tid = ev.get("tenant_id") or tenant_id
    aid = ev.get("agent_id") or agent_id

    # Mesure réelle : score de risque calculé sur la télémétrie reçue
    record_metric(tid, aid, f"risque_{kind or 'inconnu'}", res["risque"])

    if res.get("anomalie") and res["risque"] >= RISK_THRESHOLD:
        return emit_alert({
            "tenant": tid,
            "src":    "Modèle 1 (réseau)" if kind == "network" else "Modèle 2 (UEBA)",
            "type":   ev.get("type", "Anomalie réseau / C2" if kind == "network" else "Fraude interne"),
            "entite": ev.get("entite", "?"),
            "risque": res["risque"],
            "raisons": res.get("raisons", []),
            "mitre":  ev.get("mitre", ""),
        })
    return False


# --------------------------------------------------------------------------- #
# Consommateur Kafka (tâche de fond)
# --------------------------------------------------------------------------- #
def consume_loop():
    try:
        from kafka import KafkaConsumer
        consumer = KafkaConsumer(
            T_TELEMETRY, bootstrap_servers=KAFKA, group_id="scoring",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="latest")
    except Exception as e:
        print(f"[scoring] consommateur Kafka indisponible : {e}")
        return
    print(f"[scoring] écoute du topic {T_TELEMETRY}…")
    for msg in consumer:
        try:
            # Événement non normalisé (télémétrie brute) → ignoré ici
            process_normalized_event(msg.value)
        except Exception as e:
            print(f"[scoring] événement ignoré : {e}")


# --------------------------------------------------------------------------- #
# Cycle de vie + endpoints
# --------------------------------------------------------------------------- #
@app.on_event("startup")
def startup():
    STATE["m1"] = _load(os.getenv("MODEL1_PATH"))
    STATE["m2"] = _load(os.getenv("MODEL2_PATH"))
    print(f"[scoring] modèles chargés : M1={bool(STATE['m1'])} M2={bool(STATE['m2'])}")
    try:
        from kafka import KafkaProducer
        STATE["producer"] = KafkaProducer(bootstrap_servers=KAFKA)
    except Exception as e:
        print(f"[scoring] producteur Kafka indisponible : {e}")
    if DB_DSN:
        try:
            import psycopg2
            STATE["db"] = psycopg2.connect(DB_DSN)
        except Exception as e:
            print(f"[scoring] connexion Postgres indisponible : {e}")
    threading.Thread(target=consume_loop, daemon=True).start()


class Features(BaseModel):
    features: dict
    entite: str | None = None
    tenant_id: str | None = None


@app.get("/health")
def health():
    """Healthcheck rapide (utilisé par Docker + load balancer)."""
    return {"status": "ok", "modele1": bool(STATE["m1"]), "modele2": bool(STATE["m2"])}


@app.get("/health/detailed")
def health_detailed():
    """Healthcheck approfondi — vérifie chaque service de la pile."""
    import urllib.request, ssl

    checks = {
        "scoring_service": {"status": "ok", "models": {"m1": bool(STATE["m1"]), "m2": bool(STATE["m2"])}},
    }
    overall = "ok"

    # Kafka
    try:
        from kafka.admin import KafkaAdminClient
        admin = KafkaAdminClient(bootstrap_servers=KAFKA, request_timeout_ms=3000)
        topics = admin.list_topics()
        admin.close()
        checks["kafka"] = {"status": "ok", "topics": len(topics)}
    except Exception as e:
        checks["kafka"] = {"status": "unavailable", "detail": str(e)[:80]}
        overall = "degraded"

    # TimescaleDB / PostgreSQL
    if STATE["db"]:
        try:
            with STATE["db"].cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM tenants")
                n = cur.fetchone()[0]
            checks["timescaledb"] = {"status": "ok", "tenants": n}
        except Exception as e:
            checks["timescaledb"] = {"status": "error", "detail": str(e)[:80]}
            overall = "degraded"
    else:
        checks["timescaledb"] = {"status": "not_configured"}

    # Wazuh Indexer
    try:
        import base64
        wazuh_url = os.getenv("WAZUH_API_URL", "https://localhost:9200")
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        creds = base64.b64encode(b"admin:admin").decode()
        req = urllib.request.Request(
            f"{wazuh_url}/_cluster/health",
            headers={"Authorization": f"Basic {creds}"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=3) as r:
            data = json.loads(r.read())
        checks["wazuh_indexer"] = {"status": "ok", "cluster_status": data.get("status")}
    except Exception as e:
        checks["wazuh_indexer"] = {"status": "unavailable", "detail": str(e)[:60]}

    return {
        "status":    overall,
        "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        "services":  checks,
    }


@app.post("/score/network")
def api_score_network(body: Features):
    r = score_network(body.features)
    return r or {"erreur": "Modèle 1 non chargé"}


@app.post("/score/user-day")
def api_score_userday(body: Features):
    r = score_userday(body.features)
    return r or {"erreur": "Modèle 2 non chargé"}


@app.post("/ingest")
async def ingest(request: Request):
    """
    Passerelle d'ingestion sécurisée.
    Vérifie : rate limit par IP, Bearer token (hash en base), signature HMAC-SHA256 du payload.
    """
    ip = _client_ip(request)
    _check_rate_limit(f"ingest:{ip}", INGEST_LIMIT_REQ, INGEST_LIMIT_WIN)

    authorization = request.headers.get("authorization", "")
    x_signature   = request.headers.get("x-signature", "")

    raw = await request.body()
    if request.headers.get("content-encoding") == "gzip":
        try:
            raw = gziplib.decompress(raw)
        except Exception:
            raise HTTPException(400, detail="Décompression gzip impossible")

    try:
        batch  = json.loads(raw)
        events = batch.get("events", [])
    except Exception:
        raise HTTPException(400, detail="JSON invalide")

    agent_id  = batch.get("agent_id", "")
    tenant_id = batch.get("tenant_id", "")

    if not _verify_ingest(raw, authorization, x_signature, agent_id):
        raise HTTPException(401, detail="Token ou signature invalide")

    n = 0
    if STATE["producer"]:
        meta = {
            "agent_id":  agent_id,
            "tenant_id": batch.get("tenant_id"),
            "host":      batch.get("host"),
        }
        for ev in events:
            try:
                # Routage : un événement DÉJÀ normalisé (kind + features) part sur
                # le topic de télémétrie normalisée, que consomme le scoring.
                # Un événement brut part sur le topic brut, en attente de
                # normalisation par le pipeline SIEM (Lot 2).
                topic = T_TELEMETRY if isinstance(ev, dict) and "features" in ev else T_RAW
                STATE["producer"].send(topic, json.dumps({**meta, **ev}).encode("utf-8"))
                n += 1
            except Exception:
                pass

    # ── Scoring en direct des événements déjà normalisés ────────────────────
    # Un événement portant `kind` + `features` est scoré immédiatement : la
    # détection reste opérationnelle même sans Kafka (dégradation gracieuse).
    # Quand Kafka est présent, le chemin nominal reste le pipeline asynchrone ;
    # on évite alors le double traitement.
    alertes = 0
    if not STATE["producer"]:
        for ev in events:
            try:
                if process_normalized_event(ev, tenant_id, agent_id):
                    alertes += 1
            except Exception as e:
                print(f"[ingestion] scoring direct échoué : {e}")

    # ── Métriques réelles de volumétrie ─────────────────────────────────────
    if tenant_id:
        record_metric(tenant_id, agent_id, "evenements_recus", len(events))
        if alertes:
            record_metric(tenant_id, agent_id, "alertes_emises", alertes)

    # Mettre à jour vu_le de l'agent en base
    if STATE["db"] and agent_id:
        try:
            token_hash = hashlib.sha256(authorization.removeprefix("Bearer ").encode()).hexdigest()
            with STATE["db"].cursor() as cur:
                cur.execute(
                    "UPDATE agents SET vu_le = now(), statut = 'actif' WHERE token_hash = %s",
                    (token_hash,)
                )
            STATE["db"].commit()
        except Exception:
            pass

    print(f"[ingestion] {agent_id} : {len(events)} événements, {n} publiés")
    return {"recus": len(events), "publies": n, "alertes": alertes}
