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
import json
import os
import gzip as gziplib
import threading

import numpy as np
import joblib
from fastapi import FastAPI, Request
from pydantic import BaseModel

# Libellés lisibles (explicabilité Modèle 2)
LISIBLE = {
    "nb_connexions": "connexions", "nb_actions_hors_heures": "actions hors heures ouvrables",
    "nb_transactions": "transactions budgétaires", "montant_total_modifie": "montant total modifié (FCFA)",
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

app = FastAPI(title="NEXUS SOC — Service de scoring", version="1.0")
STATE = {"m1": None, "m2": None, "producer": None, "db": None}


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
def emit_alert(alert: dict):
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
            ev = msg.value
            if not isinstance(ev, dict) or "features" not in ev:
                continue   # événement non normalisé (télémétrie brute) → ignoré ici
            kind = ev.get("kind")            # "network" | "user-day"
            res = score_network(ev["features"]) if kind == "network" else score_userday(ev["features"])
            if res and res.get("anomalie") and res["risque"] >= RISK_THRESHOLD:
                emit_alert({
                    "tenant": ev.get("tenant_id"), "src": "Modèle 1 (réseau)" if kind == "network" else "Modèle 2 (UEBA)",
                    "type": ev.get("type", "Anomalie réseau / C2" if kind == "network" else "Fraude interne"),
                    "entite": ev.get("entite", "?"), "risque": res["risque"],
                    "raisons": res.get("raisons", []), "mitre": ev.get("mitre", "")})
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
    return {"status": "ok", "modele1": bool(STATE["m1"]), "modele2": bool(STATE["m2"])}


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
    """Passerelle d'ingestion : reçoit un lot de télémétrie de l'agent (egress HTTPS),
    décompresse, et produit chaque événement brut dans Kafka (topic nexus.telemetry.raw).
    La normalisation/agrégation en features pour les modèles est l'étape suivante (pipeline)."""
    raw = await request.body()
    if request.headers.get("content-encoding") == "gzip":
        try:
            raw = gziplib.decompress(raw)
        except Exception:
            return {"erreur": "décompression gzip impossible"}
    try:
        batch = json.loads(raw)
        events = batch.get("events", [])
    except Exception:
        return {"erreur": "JSON invalide"}
    # NB : en production, vérifier ici le jeton Authorization et la signature X-Signature.
    n = 0
    if STATE["producer"]:
        meta = {"agent_id": batch.get("agent_id"), "tenant_id": batch.get("tenant_id"), "host": batch.get("host")}
        for ev in events:
            try:
                STATE["producer"].send(T_RAW, json.dumps({**meta, **ev}).encode("utf-8"))
                n += 1
            except Exception:
                pass
    print(f"[ingestion] lot reçu de {batch.get('agent_id')} : {len(events)} événements, {n} publiés sur {T_RAW}")
    return {"recus": len(events), "publies": n}
