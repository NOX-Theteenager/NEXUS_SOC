#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Module Administration (Lot 7)
==========================================
Endpoints FastAPI à ajouter au scoring-service pour la console fournisseur.

À intégrer dans scoring-service_app.py :
    from admin_api import router as admin_router
    app.include_router(admin_router)

Points clés :
- Le rôle admin_plateforme et analyste_soc n'injectent PAS app.current_tenant
  → ils voient à travers tous les tenants (pas de filtre RLS par tenant).
- Le rôle client (dsi_client / lecteur) reçoit son tenant_id via son JWT et
  le scoring-service injecte SET app.current_tenant = '<uuid>'.
- Authentification simplifiée (Bearer token + vérification en base) ;
  en production, utiliser un middleware JWT complet (PyJWT + secret rotatif).
"""

import os
import secrets
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, List

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, EmailStr

DB_DSN = os.getenv("DB_DSN", "postgresql://nexus_app:nexus_pass@localhost:5432/nexus")

router = APIRouter(prefix="/admin", tags=["Administration"])

# ---------------------------------------------------------------------------
# Présence des agents — statut dérivé du dernier battement
# ---------------------------------------------------------------------------
# La colonne `agents.statut` n'est écrite que par /ingest, qui la passe à
# 'actif'. Rien ne la repasse jamais à 'hors_ligne' : un poste éteint restait
# affiché actif indéfiniment. Le statut réel est donc CALCULÉ À LA LECTURE à
# partir de `vu_le`, ce qui donne une présence vraie sans tâche de fond, sans
# dérive d'horloge, et correcte même après un arrêt du serveur.
#
# `isole` est une décision humaine ou SOAR : elle prime sur le battement. Un
# poste isolé qui continue d'émettre reste isolé à l'écran.
#
# Seuil : l'agent émet toutes les `interval_sec` (30 s par défaut). On tolère
# trois battements manqués avant de déclarer le poste hors ligne.
AGENT_STALE_SECONDS = max(30, int(os.getenv("AGENT_STALE_SECONDS", "120")))

# Dérivation des clés HMAC — source unique de vérité dans le service de scoring,
# qui est aussi celui qui vérifie les signatures (voir provisioning_api.py).
try:
    from nexus_scoring import derive_hmac_key  # type: ignore
except Exception:  # pragma: no cover
    import hmac as _hmac_mod

    _HMAC_MASTER = os.getenv("NEXUS_HMAC_MASTER") or os.getenv("JWT_SECRET", "")

    def derive_hmac_key(agent_id: str, epoch: int = 0) -> str:
        if not _HMAC_MASTER:
            raise RuntimeError("NEXUS_HMAC_MASTER (ou JWT_SECRET) non défini.")
        return _hmac_mod.new(_HMAC_MASTER.encode(),
                             f"{agent_id}:{epoch}".encode(),
                             hashlib.sha256).hexdigest()


def agent_statut_sql(alias: str = "a") -> str:
    """Expression SQL du statut effectif d'un agent (valeur d'un entier maîtrisé,
    jamais d'une entrée utilisateur : aucune injection possible)."""
    return (
        f"CASE WHEN {alias}.statut = 'isole' THEN 'isole' "
        f"     WHEN {alias}.vu_le IS NOT NULL "
        f"      AND {alias}.vu_le > now() - interval '{AGENT_STALE_SECONDS} seconds' THEN 'actif' "
        f"     ELSE 'hors_ligne' END"
    )


def agent_presence_cols(alias: str = "a") -> str:
    """Colonnes de présence à ajouter à un SELECT sur `agents`.

    `statut`         : statut effectif, celui qu'affiche l'interface
    `statut_declare` : valeur brute en base, conservée pour l'audit
    `vu_il_y_a_s`    : ancienneté du dernier battement, en secondes
    """
    return (
        f"{agent_statut_sql(alias)} AS statut, "
        f"{alias}.statut AS statut_declare, "
        f"EXTRACT(EPOCH FROM (now() - {alias}.vu_le))::int AS vu_il_y_a_s"
    )

# ---------------------------------------------------------------------------
# Connexion PostgreSQL helper
# ---------------------------------------------------------------------------
def get_db():
    conn = psycopg2.connect(DB_DSN, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Vérification du rôle (guard simple — remplacer par JWT en production)
# ---------------------------------------------------------------------------
# --- Validation JWT unifiée (même schéma HS256 que auth_middleware.py) --------
# On réutilise auth_middleware.decode_token si disponible (source unique de
# vérité), sinon on retombe sur une implémentation locale identique. Cela permet
# au frontend (qui envoie un JWT) d'authentifier les appels /admin et /analyst.
try:
    from auth_middleware import decode_token as _decode_jwt  # type: ignore
except Exception:  # pragma: no cover - fallback autonome
    import hmac as _hmac, hashlib as _hashlib, json as _json, base64 as _b64, time as _time

    _JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_USE_32_RANDOM_BYTES")

    def _decode_jwt(token: str) -> dict:
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token malformé")
        h, p, sig = parts
        expected = _b64.urlsafe_b64encode(
            _hmac.new(_JWT_SECRET.encode(), f"{h}.{p}".encode(), _hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        if not _hmac.compare_digest(expected, sig):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Signature invalide")
        payload = _json.loads(_b64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
        if payload.get("exp", 0) < int(_time.time()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expiré")
        return payload


def require_admin(authorization: str = Header(...)):
    """Vérifie que le JWT Bearer appartient à un admin_plateforme ou analyste_soc."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token manquant")
    payload = _decode_jwt(authorization.removeprefix("Bearer "))
    if payload.get("role") not in ("admin_plateforme", "analyste_soc"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rôle insuffisant")
    return payload


def require_analyst(authorization: str = Header(...)):
    """Accepte admin_plateforme et analyste_soc (cross-tenant read)."""
    return require_admin(authorization)


# ---------------------------------------------------------------------------
# Schémas Pydantic
# ---------------------------------------------------------------------------
class TenantCreate(BaseModel):
    nom: str
    type: str          # application_metier | reseau | infrastructure | poste_utilisateur
    criticite: str     # standard | sensible | critique
    email_admin: Optional[EmailStr] = None


class TenantUpdate(BaseModel):
    nom: Optional[str] = None
    criticite: Optional[str] = None
    statut: Optional[str] = None   # actif | suspendu


class UserCreate(BaseModel):
    email: EmailStr
    role: str          # admin_plateforme | analyste_soc | dsi_client | lecteur
    tenant_id: Optional[str] = None
    mot_de_passe: str


# ---------------------------------------------------------------------------
# A. TENANTS
# ---------------------------------------------------------------------------
@router.get("/tenants", summary="Lister tous les périmètres supervisés")
def list_tenants(db=Depends(get_db), _=Depends(require_admin)):
    """Retourne la liste des périmètres supervisés avec métriques d'agents et d'alertes."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT
                t.id, t.nom, t.type, t.criticite, t.cree_le,
                COUNT(DISTINCT a.id) FILTER (WHERE a.statut = 'actif')     AS agents_actifs,
                COUNT(DISTINCT a.id)                                        AS agents_total,
                COUNT(DISTINCT al.id) FILTER (WHERE al.statut = 'ouverte') AS incidents_ouverts
            FROM tenants t
            LEFT JOIN agents a  ON a.tenant_id = t.id
            LEFT JOIN alerts al ON al.tenant_id = t.id
            GROUP BY t.id
            ORDER BY t.cree_le
        """)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/tenants", status_code=201, summary="Créer un périmètre supervisé")
def create_tenant(body: TenantCreate, db=Depends(get_db), _=Depends(require_admin)):
    TYPES_OK      = {"application_metier", "reseau", "infrastructure", "poste_utilisateur"}
    CRITICITES_OK = {"standard", "sensible", "critique"}
    if body.type not in TYPES_OK:
        raise HTTPException(400, detail=f"type invalide : {body.type}")
    if body.criticite not in CRITICITES_OK:
        raise HTTPException(400, detail=f"criticité invalide : {body.criticite}")
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (nom, type, criticite) VALUES (%s, %s, %s) RETURNING id",
            (body.nom, body.type, body.criticite)
        )
        tenant_id = cur.fetchone()["id"]
        if body.email_admin:
            tmp_pw = secrets.token_urlsafe(12)
            cur.execute(
                "INSERT INTO users (tenant_id, email, mot_de_passe, role) "
                "VALUES (%s, %s, crypt(%s, gen_salt('bf')), 'dsi_client')",
                (str(tenant_id), body.email_admin, tmp_pw)
            )
        db.commit()
    return {"id": str(tenant_id), "message": "Périmètre créé"}


@router.patch("/tenants/{tenant_id}", summary="Modifier / suspendre un périmètre")
def update_tenant(tenant_id: str, body: TenantUpdate, db=Depends(get_db), _=Depends(require_admin)):
    sets, vals = [], []
    if body.nom:
        sets.append("nom = %s"); vals.append(body.nom)
    if body.criticite:
        sets.append("criticite = %s"); vals.append(body.criticite)
    if body.statut:
        # On stocke le statut dans une colonne optionnelle ; si elle n'existe pas encore,
        # cet endpoint sert de point d'entrée pour le Lot 7 — voir 01_schema_analyst.sql
        sets.append("statut = %s"); vals.append(body.statut)
    if not sets:
        raise HTTPException(400, detail="Aucun champ à modifier")
    vals.append(tenant_id)
    with db.cursor() as cur:
        cur.execute(f"UPDATE tenants SET {', '.join(sets)} WHERE id = %s", vals)
        db.commit()
    return {"message": "Périmètre mis à jour"}


@router.post("/tenants/{tenant_id}/suspend", summary="Suspendre un périmètre (coupe la supervision)")
def suspend_tenant(tenant_id: str, db=Depends(get_db), _=Depends(require_admin)):
    """Met le périmètre en pause de supervision (colonne statut = 'suspendu')."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE tenants SET statut = 'suspendu' "
            "WHERE id = %s AND statut <> 'suspendu' RETURNING id",
            (tenant_id,)
        )
        row = cur.fetchone()
        db.commit()
    if not row:
        raise HTTPException(404, detail="Périmètre introuvable ou déjà suspendu")
    return {"message": "Périmètre suspendu", "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/activate", summary="Réactiver un périmètre suspendu")
def activate_tenant(tenant_id: str, db=Depends(get_db), _=Depends(require_admin)):
    """Lève la suspension et remet le périmètre sous supervision active."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE tenants SET statut = 'actif' WHERE id = %s RETURNING id",
            (tenant_id,)
        )
        row = cur.fetchone()
        db.commit()
    if not row:
        raise HTTPException(404, detail="Périmètre introuvable")
    return {"message": "Périmètre réactivé", "tenant_id": tenant_id}


@router.delete("/tenants/{tenant_id}", summary="Supprimer un périmètre (irréversible)")
def delete_tenant(tenant_id: str, db=Depends(get_db), _=Depends(require_admin)):
    with db.cursor() as cur:
        cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
        db.commit()
    return {"message": "Périmètre supprimé"}


# ---------------------------------------------------------------------------
# B. UTILISATEURS
# ---------------------------------------------------------------------------
@router.get("/users", summary="Lister les utilisateurs (tous tenants)")
def list_users(tenant_id: Optional[str] = None, db=Depends(get_db), _=Depends(require_admin)):
    with db.cursor() as cur:
        if tenant_id:
            cur.execute(
                "SELECT id, tenant_id, email, role, actif, cree_le FROM users WHERE tenant_id = %s ORDER BY cree_le",
                (tenant_id,)
            )
        else:
            cur.execute("SELECT id, tenant_id, email, role, actif, cree_le FROM users ORDER BY cree_le")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/users", status_code=201, summary="Créer un utilisateur")
def create_user(body: UserCreate, db=Depends(get_db), _=Depends(require_admin)):
    ROLES_OK = {"admin_plateforme", "analyste_soc", "dsi_client", "lecteur"}
    if body.role not in ROLES_OK:
        raise HTTPException(400, detail=f"rôle invalide : {body.role}")
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users (tenant_id, email, mot_de_passe, role) "
            "VALUES (%s, %s, crypt(%s, gen_salt('bf')), %s) RETURNING id",
            (body.tenant_id, body.email, body.mot_de_passe, body.role)
        )
        uid = cur.fetchone()["id"]
        db.commit()
    return {"id": str(uid), "message": "Utilisateur créé"}


# ---------------------------------------------------------------------------
# C. AGENTS — provisioning (génération de jetons d'enrôlement)
# ---------------------------------------------------------------------------
@router.get("/agents", summary="Lister les agents (tous tenants)")
def list_agents(tenant_id: Optional[str] = None, db=Depends(get_db), _=Depends(require_admin)):
    """Le statut renvoyé est le statut EFFECTIF, dérivé du dernier battement
    (voir agent_statut_sql). Allumer une VM la fait passer à `actif` au premier
    lot ingéré ; l'éteindre la fait passer à `hors_ligne` après le délai de
    tolérance, sans intervention."""
    cols = (f"a.id, a.tenant_id, a.hostname, a.os, a.vu_le, a.hmac_scheme, "
            f"a.version_agent, {agent_presence_cols('a')}")
    with db.cursor() as cur:
        if tenant_id:
            cur.execute(f"SELECT {cols} FROM agents a WHERE a.tenant_id = %s ORDER BY a.hostname",
                        (tenant_id,))
        else:
            cur.execute(f"SELECT {cols} FROM agents a ORDER BY a.tenant_id, a.hostname")
        rows = [dict(r) for r in cur.fetchall()]

        # Télémétrie récente, 12 créneaux de 2 h : de quoi tracer une silhouette
        # d'activité par agent. C'est un COMPTE de mesures reçues, pas une
        # valeur métier — un creux signale un agent qui s'est tu, ce qui est
        # précisément ce qu'on veut voir d'un coup d'œil.
        cur.execute("""
            SELECT agent_id,
                   floor(EXTRACT(EPOCH FROM (now() - ts)) / 7200)::int AS creneau,
                   count(*) AS n
              FROM metrics
             WHERE ts > now() - interval '24 hours' AND agent_id IS NOT NULL
             GROUP BY 1, 2
        """)
        series = {}
        for r in cur.fetchall():
            if r["creneau"] is None or not (0 <= r["creneau"] < 12):
                continue
            series.setdefault(str(r["agent_id"]), [0] * 12)[11 - r["creneau"]] = int(r["n"])

    for a in rows:
        a["telemetrie_24h"] = series.get(str(a["id"]), [0] * 12)
    return rows


class BulkAgentAction(BaseModel):
    agent_ids: List[str]
    isoler:    bool
    motif:     Optional[str] = None


@router.post("/agents/isolation", summary="Isoler ou reconnecter plusieurs agents")
def bulk_agent_isolation(body: BulkAgentAction, db=Depends(get_db),
                         user: dict = Depends(require_admin)):
    """Isole — ou reconnecte — un lot d'agents.

    L'isolement est réel : `_verify_ingest` refuse tout lot d'un agent dont le
    statut vaut `isole`, sa télémétrie est donc coupée à la source.

    Ce n'est PAS un confinement réseau. La machine garde son réseau et continue
    de fonctionner ; c'est la plateforme qui cesse de l'écouter. Le confinement
    demande une règle sur la passerelle (voir lab-cenadi/03-quarantaine-blocage.md).
    L'action est journalisée pour que l'écart entre les deux reste traçable.
    """
    ids = [i for i in (body.agent_ids or []) if i]
    if not ids:
        raise HTTPException(422, detail="Aucun agent désigné.")
    if len(ids) > 200:
        raise HTTPException(422, detail="Lot trop grand : 200 agents au maximum.")

    cible = 'isole' if body.isoler else 'hors_ligne'
    acteur = user.get("email", "admin")
    with db.cursor() as cur:
        # Le statut effectif est dérivé du battement : repasser un agent à
        # « hors_ligne » suffit à le reconnecter, son prochain lot le rendra
        # actif de lui-même.
        cur.execute(
            "UPDATE agents SET statut = %s WHERE id = ANY(%s::uuid[]) "
            "RETURNING id::text, hostname, tenant_id::text",
            (cible, ids))
        touches = [dict(r) for r in cur.fetchall()]

        for a in touches:
            cur.execute(
                "INSERT INTO soar_audit (alert_id, tenant_id, action, impact, decision, "
                "                        statut, acteur, detail, cible, cible_type, execution) "
                "VALUES (NULL, %s::uuid, %s, 'fort', 'APPROUVÉE', %s, %s, %s, %s, 'hote', %s)",
                (a["tenant_id"],
                 'isolate_host' if body.isoler else 'reconnect_host',
                 'EXÉCUTÉE (manuelle)',
                 acteur,
                 (body.motif or ('Isolement décidé depuis la console.' if body.isoler
                                 else 'Reconnexion décidée depuis la console.'))
                 + ' Ingestion coupée à la source ; aucun confinement réseau.',
                 a["hostname"],
                 'automatique'))
        db.commit()

    return {"traites": len(touches), "statut": cible,
            "agents": [a["hostname"] for a in touches],
            "avertissement": "L'ingestion est coupée. La machine reste sur le réseau : "
                             "le confinement demande une règle sur la passerelle."}


@router.post("/agents/token", status_code=201, summary="Générer un jeton d'enrôlement d'agent")
def generate_agent_token(
    tenant_id: str,
    hostname: str,
    db=Depends(get_db),
    _=Depends(require_admin)
):
    """
    Crée un enregistrement agent + retourne le Bearer token et la clé HMAC-SHA256.
    Ces valeurs ne sont JAMAIS re-affichées après cette réponse.
    L'agent Go les reçoit lors de son premier déploiement (variable d'env ou fichier de config).
    """
    bearer_token = f"nexus_{secrets.token_urlsafe(32)}"
    token_hash   = hashlib.sha256(bearer_token.encode()).hexdigest()

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO agents (tenant_id, hostname, statut, hmac_scheme, hmac_epoch) "
            "VALUES (%s, %s, 'hors_ligne', 'derived', 0) RETURNING id",
            (tenant_id, hostname)
        )
        agent_id = str(cur.fetchone()["id"])
        # La clé HMAC dérive de l'identité de l'agent : le serveur la recalcule à
        # chaque lot, rien de réversible n'est conservé. On ne stocke que son
        # empreinte, à titre d'audit.
        hmac_key = derive_hmac_key(agent_id, 0)
        cur.execute(
            "UPDATE agents SET token_hash = %s, hmac_key_hash = %s WHERE id = %s",
            (token_hash, hashlib.sha256(hmac_key.encode()).hexdigest(), agent_id)
        )
        db.commit()

    return {
        "agent_id": agent_id,
        "bearer_token": bearer_token,
        "hmac_key": hmac_key,
        "hmac_scheme": "derived",
        "warning": "Ces valeurs ne sont affichées qu'une seule fois. Configurez l'agent maintenant.",
    }


# ---------------------------------------------------------------------------
# D. SANTÉ SYSTÈME
# ---------------------------------------------------------------------------
@router.get("/health", summary="État des services du socle")
def system_health(db=Depends(get_db), _=Depends(require_admin)):
    """Vérifie la connectivité aux composants critiques."""
    checks = {}
    # PostgreSQL / TimescaleDB
    try:
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM tenants")
            n = cur.fetchone()["n"]
        checks["timescaledb"] = {"status": "ok", "tenants": n}
    except Exception as e:
        checks["timescaledb"] = {"status": "error", "detail": str(e)}

    # Wazuh indexeur (API compatible Elasticsearch)
    wazuh_url = os.getenv("WAZUH_API_URL", "https://localhost:9200")
    try:
        import urllib.request, ssl
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(f"{wazuh_url}/_cluster/health", headers={"Authorization": "Basic " + __import__('base64').b64encode(b"admin:admin").decode()})
        with urllib.request.urlopen(req, context=ctx, timeout=3) as r:
            data = json.loads(r.read())
        checks["wazuh_indexer"] = {"status": "ok", "cluster_status": data.get("status")}
    except Exception as e:
        checks["wazuh_indexer"] = {"status": "unavailable", "detail": str(e)}

    return {"timestamp": datetime.now(timezone.utc).isoformat(), "services": checks}


# ---------------------------------------------------------------------------
# E. INVENTAIRE DES PÉRIMÈTRES (vue synthétique, sans notion commerciale)
# ---------------------------------------------------------------------------
@router.get("/perimetres", summary="Vue synthétique des périmètres supervisés")
def list_perimetres(db=Depends(get_db), _=Depends(require_admin)):
    """Inventaire des périmètres avec leur criticité et leur statut de supervision."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, nom, type, criticite, statut, cree_le FROM tenants ORDER BY cree_le"
        )
        rows = cur.fetchall()
    return [
        {
            "tenant_id": str(t["id"]),
            "nom":       t["nom"],
            "type":      t["type"],
            "criticite": t["criticite"],
            "statut":    t.get("statut", "actif"),
        }
        for t in rows
    ]


# ---------------------------------------------------------------------------
# E-bis. SUPERVISION — séries temporelles réelles (hypertable metrics)
# ---------------------------------------------------------------------------
@router.get("/metrics", summary="Séries temporelles de supervision (metrics)")
def get_metrics(hours: int = 24, tenant_id: Optional[str] = None,
                db=Depends(get_db), _=Depends(require_admin)):
    """
    Retourne les séries temporelles mesurées (table `metrics`) agrégées par
    minute, pour alimenter les graphiques de supervision de la console.
    Réponse : { metriques: [...], series: { <metrique>: [{t, v}, ...] }, resume: {...} }
    """
    hours = max(1, min(int(hours), 168))
    params = [f"{hours} hours"]
    filtre_tenant = ""
    if tenant_id:
        filtre_tenant = "AND tenant_id = %s::uuid"
        params.append(tenant_id)

    with db.cursor() as cur:
        # Points agrégés par minute et par métrique
        cur.execute(
            f"""
            SELECT date_trunc('minute', ts) AS t, metrique, avg(valeur) AS v
              FROM metrics
             WHERE ts > now() - %s::interval {filtre_tenant}
             GROUP BY 1, 2
             ORDER BY 1
            """,
            params,
        )
        rows = cur.fetchall()

        # Résumé par métrique (dernier point, moyenne, max)
        cur.execute(
            f"""
            SELECT metrique, count(*) AS points,
                   round(avg(valeur)::numeric, 1) AS moyenne,
                   max(valeur) AS maxi,
                   (array_agg(valeur ORDER BY ts DESC))[1] AS dernier
              FROM metrics
             WHERE ts > now() - %s::interval {filtre_tenant}
             GROUP BY metrique
             ORDER BY metrique
            """,
            params,
        )
        resume_rows = cur.fetchall()

    series: dict = {}
    metriques: list = []
    for r in rows:
        m = r["metrique"]
        if m not in series:
            series[m] = []
            metriques.append(m)
        series[m].append({"t": r["t"].isoformat(), "v": round(float(r["v"]), 2)})

    resume = {
        r["metrique"]: {
            "points":  int(r["points"]),
            "moyenne": float(r["moyenne"]) if r["moyenne"] is not None else 0.0,
            "maxi":    float(r["maxi"]) if r["maxi"] is not None else 0.0,
            "dernier": float(r["dernier"]) if r["dernier"] is not None else 0.0,
        }
        for r in resume_rows
    }
    return {"hours": hours, "metriques": metriques, "series": series, "resume": resume}


# ---------------------------------------------------------------------------
# F. ANALYSTE SOC — lecture cross-périmètre (pas de filtre RLS)
#    Note : ces endpoints utilisent le rôle nexus_analyst (BYPASSRLS)
#    défini dans 01_schema_analyst.sql. La connexion doit utiliser ce rôle,
#    pas nexus_app.
# ---------------------------------------------------------------------------
analyst_router = APIRouter(prefix="/analyst", tags=["Analyste SOC"])

DB_DSN_ANALYST = os.getenv("DB_DSN_ANALYST", DB_DSN.replace("nexus_app", "nexus_analyst"))


def get_analyst_db():
    conn = psycopg2.connect(DB_DSN_ANALYST, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


@analyst_router.get("/alerts", summary="File d'alertes agrégée tous tenants")
def list_all_alerts(
    tenant_id: Optional[str] = None,
    statut: Optional[str] = None,
    limit: int = 50,
    db=Depends(get_analyst_db),
    _=Depends(require_analyst),
):
    """L'analyste voit toutes les alertes sans filtre RLS tenant (rôle nexus_analyst)."""
    conditions, vals = ["TRUE"], []
    if tenant_id:
        conditions.append("a.tenant_id = %s"); vals.append(tenant_id)
    if statut:
        conditions.append("a.statut = %s"); vals.append(statut)
    vals.append(limit)
    with db.cursor() as cur:
        cur.execute(f"""
            SELECT a.id, a.tenant_id, t.nom AS tenant_nom, a.source_modele, a.type,
                   a.entite, a.risque, a.raisons, a.mitre, a.statut, a.cree_le,
                   a.chaine, a.score_parts
            FROM alerts a
            JOIN tenants t ON t.id = a.tenant_id
            WHERE {' AND '.join(conditions)}
            ORDER BY a.cree_le DESC
            LIMIT %s
        """, vals)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


@analyst_router.get("/alerts/{alert_id}", summary="Détail d'une alerte")
def get_alert(alert_id: str, db=Depends(get_analyst_db), _=Depends(require_analyst)):
    with db.cursor() as cur:
        cur.execute("""
            SELECT a.id, a.tenant_id, t.nom AS tenant_nom, a.source_modele, a.type,
                   a.entite, a.risque, a.raisons, a.mitre, a.statut, a.cree_le,
                   a.chaine, a.score_parts
            FROM alerts a JOIN tenants t ON t.id = a.tenant_id
            WHERE a.id = %s
        """, (alert_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, detail="Alerte introuvable")
    return dict(row)


@analyst_router.get("/pending", summary="Actions SOAR en attente de validation humaine")
def list_pending_soar(db=Depends(get_analyst_db), _=Depends(require_analyst)):
    """File des actions à fort impact (isolate_host, freeze_account…) en attente."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT s.id, s.alert_id, s.tenant_id, t.nom AS tenant_nom,
                   s.action, s.impact, s.detail, s.horodatage,
                   s.cible, s.cible_type,
                   a.entite, a.type, a.risque
            FROM soar_audit s
            JOIN tenants t ON t.id = s.tenant_id
            LEFT JOIN alerts a ON a.id = s.alert_id
            WHERE s.statut = 'EN ATTENTE DE VALIDATION'
            ORDER BY s.horodatage DESC
        """)
        rows = cur.fetchall()

    # La console doit pouvoir dire, AVANT l'approbation, ce que l'opérateur
    # devra faire — et signaler les propositions dont la cible ne correspond
    # pas au connecteur compétent.
    out = []
    for r in rows:
        d = dict(r)
        d.update(_commande_manuelle(d["action"], d["cible"], d["cible_type"], d["id"]))
        out.append(d)
    return out


# Aucun connecteur n'est raccordé : ni pare-feu, ni annuaire, ni canal d'ordres
# vers les agents. Approuver une action est donc une DÉCISION tracée, pas une
# exécution. Tant que les connecteurs n'existent pas, la plateforme fournit la
# commande exacte à passer et enregistre qui déclare l'avoir passée.
#
# Les commandes visent l'architecture cible documentée dans
# lab-cenadi/00-architecture-cenadi.md : MikroTik porte le routage inter-zone et
# les ACL, pfSense filtre le périmètre interne.
LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "dc=cenadi,dc=local")
LDAP_SOAR_DN = os.getenv("LDAP_SOAR_DN", f"cn=nexus-soar,ou=services,{LDAP_BASE_DN}")

SOAR_COMMANDES = {
    "block_ip": (
        "/ip firewall address-list add list=NEXUS_BLOCK address={cible} "
        "comment=\"NEXUS {audit_id}\""),
    "isolate_host": (
        "/ip firewall address-list add list=NEXUS_QUARANTAINE address={cible} "
        "comment=\"NEXUS {audit_id}\""),
    # OpenLDAP + surcouche ppolicy (lab-cenadi/scripts/vm-app-gov-annuaire.sh).
    # 000001010000Z est la valeur conventionnelle d'un verrouillage sans date de
    # levée. Le compte reste présent et lisible : on suspend un accès, on ne
    # détruit pas une trace d'enquête.
    "freeze_account": (
        "ldapmodify -x -D \"" + LDAP_SOAR_DN + "\" -W <<'EOF'\n"
        "dn: uid={cible},ou=agents," + LDAP_BASE_DN + "\n"
        "changetype: modify\n"
        "replace: pwdAccountLockedTime\n"
        "pwdAccountLockedTime: 000001010000Z\n"
        "EOF"),
}
SOAR_CIBLE_ATTENDUE = {"block_ip": "ip", "freeze_account": "compte",
                       "isolate_host": "hote"}


def _commande_manuelle(action: str, cible: str, cible_type: str, audit_id) -> dict:
    """Construit la commande d'exécution manuelle, ou dit pourquoi c'est impossible."""
    modele = SOAR_COMMANDES.get(action)
    attendu = SOAR_CIBLE_ATTENDUE.get(action)
    if not cible:
        return {"commande": None,
                "blocage": "Aucune cible n'a été résolue pour cette action."}
    if attendu and cible_type != attendu:
        return {"commande": None,
                "blocage": f"Cible de type « {cible_type} » alors que « {action} » "
                           f"attend « {attendu} ». Requalifier ou refuser l'action."}
    if not modele:
        return {"commande": None,
                "blocage": f"Aucune commande n'est documentée pour « {action} »."}
    return {"commande": modele.format(cible=cible, audit_id=audit_id), "blocage": None}


@analyst_router.post("/approve/{action_id}", summary="Approuver une action SOAR par son id")
def approve_action_by_id(action_id: int, body: dict = None,
                         db=Depends(get_analyst_db), _=Depends(require_analyst)):
    """Approuve une action SOAR (clé = soar_audit.id) — appelé par la console.

    N'exécute rien : aucun connecteur n'est raccordé. Enregistre la décision et
    renvoie la commande à passer pour la réaliser.
    """
    actor = (body or {}).get("approved_by", "analyste_soc")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE soar_audit SET statut = 'APPROUVÉE — EXÉCUTION REQUISE', "
            "       decision = 'APPROUVÉE', acteur = %s "
            "WHERE id = %s AND statut = 'EN ATTENTE DE VALIDATION' "
            "RETURNING id, action, cible, cible_type",
            (actor, action_id)
        )
        updated = cur.fetchone()
        db.commit()
    if not updated:
        raise HTTPException(404, detail="Action en attente introuvable")

    cmd = _commande_manuelle(updated["action"], updated["cible"],
                             updated["cible_type"], updated["id"])
    return {
        "message": "Décision enregistrée. L'action n'est pas exécutée : "
                   "aucun connecteur n'est raccordé.",
        "audit_id": str(updated["id"]),
        "action": updated["action"],
        "cible": updated["cible"],
        "cible_type": updated["cible_type"],
        **cmd,
    }


@analyst_router.post("/executed/{action_id}", summary="Déclarer une action réellement exécutée")
def mark_action_executed(action_id: int, body: dict = None,
                         db=Depends(get_analyst_db), _=Depends(require_analyst)):
    """Un opérateur déclare avoir passé la commande à la main.

    C'est le seul moyen honnête de marquer une exécution tant qu'aucun
    connecteur n'est raccordé : la plateforme n'a rien fait, un humain l'a fait,
    et c'est lui qui l'atteste — horodaté et nominatif.
    """
    payload = body or {}
    actor = payload.get("executed_by", "operateur")
    note = payload.get("note")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE soar_audit SET execution = 'manuelle', execute_le = now(), "
            "       execute_par = %s, execution_note = %s, statut = 'EXÉCUTÉE (manuelle)' "
            "WHERE id = %s AND decision = 'APPROUVÉE' AND execution = 'non_executee' "
            "RETURNING id, action, cible",
            (actor, note, action_id)
        )
        updated = cur.fetchone()
        db.commit()
    if not updated:
        raise HTTPException(
            404, detail="Action approuvée non exécutée introuvable (déjà déclarée ?)")
    return {"message": "Exécution manuelle enregistrée",
            "audit_id": str(updated["id"]), "action": updated["action"],
            "cible": updated["cible"], "execute_par": actor}


@analyst_router.post("/reject/{action_id}", summary="Refuser une action SOAR")
def reject_action_by_id(action_id: int, body: dict = None,
                        db=Depends(get_analyst_db), _=Depends(require_analyst)):
    reason = (body or {}).get("reason", "Refusé par analyste")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE soar_audit SET statut = 'IGNORÉE', decision = 'REFUSÉE', "
            "acteur = 'analyste_soc', detail = %s "
            "WHERE id = %s AND statut = 'EN ATTENTE DE VALIDATION' RETURNING id",
            (reason, action_id)
        )
        updated = cur.fetchone()
        db.commit()
    if not updated:
        raise HTTPException(404, detail="Action en attente introuvable")
    return {"message": "Action refusée", "audit_id": str(updated["id"])}


@analyst_router.post("/false-positive/{alert_id}", summary="Marquer une alerte comme faux positif")
def mark_false_positive(alert_id: str, db=Depends(get_analyst_db), _=Depends(require_analyst)):
    with db.cursor() as cur:
        cur.execute(
            "UPDATE alerts SET statut = 'faux_positif' WHERE id = %s RETURNING id",
            (alert_id,)
        )
        updated = cur.fetchone()
        db.commit()
    if not updated:
        raise HTTPException(404, detail="Alerte introuvable")
    return {"message": "Alerte marquée comme faux positif", "alert_id": alert_id}


@analyst_router.post("/alerts/{alert_id}/approve", summary="Approuver une action SOAR (par alerte + action)")
def approve_soar_action(alert_id: str, action: str, db=Depends(get_analyst_db), _=Depends(require_analyst)):
    """Variante historique : valide par (alert_id, action). Conservée pour compat.

    Même règle que /approve/{id} : la décision est enregistrée, rien n'est exécuté.
    """
    with db.cursor() as cur:
        cur.execute(
            "UPDATE soar_audit SET statut = 'APPROUVÉE — EXÉCUTION REQUISE', "
            "       decision = 'APPROUVÉE', acteur = 'analyste_soc' "
            "WHERE alert_id = %s AND action = %s AND statut = 'EN ATTENTE DE VALIDATION' "
            "RETURNING id, action, cible, cible_type",
            (alert_id, action)
        )
        updated = cur.fetchone()
        db.commit()
    if not updated:
        raise HTTPException(404, detail="Action en attente introuvable")
    cmd = _commande_manuelle(updated["action"], updated["cible"],
                             updated["cible_type"], updated["id"])
    return {"message": "Décision enregistrée. L'action n'est pas exécutée : "
                       "aucun connecteur n'est raccordé.",
            "audit_id": str(updated["id"]), **cmd}


@analyst_router.get("/dashboard", summary="Tableau de bord SOC global")
def soc_dashboard(db=Depends(get_analyst_db), _=Depends(require_analyst)):
    """Métriques globales cross-tenants pour le poste analyste."""
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM alerts WHERE statut = 'ouverte'")
        open_alerts = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM alerts WHERE statut = 'ouverte' AND risque >= 80")
        critical = cur.fetchone()["n"]
        # Présence réelle, pas la valeur figée de la colonne
        cur.execute(f"SELECT COUNT(*) AS n FROM agents a WHERE {agent_statut_sql('a')} = 'actif'")
        agents_online = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM agents")
        agents_total = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM tenants")
        tenants_total = cur.fetchone()["n"]
        cur.execute("""
            SELECT t.nom, COUNT(a.id) AS incidents
            FROM tenants t LEFT JOIN alerts a ON a.tenant_id = t.id AND a.statut = 'ouverte'
            GROUP BY t.nom ORDER BY incidents DESC LIMIT 5
        """)
        top_tenants = [dict(r) for r in cur.fetchall()]
    return {
        "open_alerts": open_alerts,
        "critical_alerts": critical,
        "agents_online": agents_online,
        "agents_total": agents_total,
        "tenants_total": tenants_total,
        "top_tenants_by_incidents": top_tenants,
        "stale_after_s": AGENT_STALE_SECONDS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@analyst_router.get("/soar-audit", summary="Journal d'audit SOAR (qui a fait quoi, quand)")
def soar_audit_journal(
    tenant_id: Optional[str] = None,
    impact: Optional[str] = None,
    statut: Optional[str] = None,
    limit: int = 100,
    db=Depends(get_analyst_db),
    _=Depends(require_analyst),
):
    """Vue chronologique de la table `soar_audit`, filtrable par périmètre,
    impact et statut.

    Répond à la question « qui a gelé ce compte, quand, sur quelle décision ».
    La table était peuplée par le moteur SOAR mais n'était exposée nulle part
    (dette de design n°5).
    """
    conditions, vals = ["TRUE"], []
    if tenant_id:
        conditions.append("s.tenant_id = %s::uuid"); vals.append(tenant_id)
    if impact:
        conditions.append("s.impact = %s"); vals.append(impact)
    if statut:
        conditions.append("s.statut = %s"); vals.append(statut)
    vals.append(max(1, min(int(limit), 500)))

    with db.cursor() as cur:
        cur.execute(f"""
            SELECT s.id, s.alert_id, s.tenant_id, t.nom AS tenant_nom,
                   s.action, s.impact, s.decision, s.statut, s.acteur,
                   s.detail, s.horodatage,
                   s.cible, s.cible_type,
                   s.execution, s.execute_le, s.execute_par,
                   a.entite, a.type AS alerte_type, a.risque
              FROM soar_audit s
              JOIN tenants t ON t.id = s.tenant_id
              LEFT JOIN alerts a ON a.id = s.alert_id
             WHERE {' AND '.join(conditions)}
             ORDER BY s.horodatage DESC
             LIMIT %s
        """, vals)
        rows = [dict(r) for r in cur.fetchall()]

        # Facettes de filtrage : ne jamais proposer une valeur absente du journal
        cur.execute("SELECT DISTINCT impact FROM soar_audit WHERE impact IS NOT NULL ORDER BY 1")
        impacts = [r["impact"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT acteur FROM soar_audit WHERE acteur IS NOT NULL ORDER BY 1")
        acteurs = [r["acteur"] for r in cur.fetchall()]

    return {"items": rows, "facets": {"impacts": impacts, "acteurs": acteurs}}


# ---------------------------------------------------------------------------
# F-bis. MONITORING DES MODÈLES IA — dérive (PSI + glissement σ)
#     Consommé par la section Supervision de la console.
# ---------------------------------------------------------------------------
monitor_router = APIRouter(prefix="/monitor", tags=["Monitoring modèles"])


@monitor_router.get("/drift", summary="Dérive des modèles IA sur N jours (PSI, σ, taux FP)")
def model_drift(days: int = 7, db=Depends(get_analyst_db), _=Depends(require_analyst)):
    """Calcule la dérive des modèles M1 (réseau) et M2 (UEBA).

    La logique de calcul vit dans Lot3_IA/model_monitor.py (source unique de
    vérité, testable hors API). Si le module n'est pas importable — déploiement
    partiel, dépendances manquantes — on renvoie un rapport explicite plutôt
    qu'une erreur opaque : la console affiche alors « indisponible » sans
    laisser croire que les modèles sont sains.
    """
    days = max(1, min(int(days), 90))
    try:
        import sys as _sys
        _lot3 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Lot3_IA")
        if _lot3 not in _sys.path:
            _sys.path.insert(0, _lot3)
        from model_monitor import build_drift_report  # type: ignore
    except Exception as e:
        return {
            "days": days, "available": False,
            "detail": f"Module de monitoring indisponible : {e}",
            "models": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    models = [
        ("Modèle 1 (réseau)", "Modèle 1"),
        ("Modèle 2 (UEBA)",   "Modèle 2"),
    ]
    out = []
    for label, needle in models:
        try:
            with db.cursor() as cur:
                # Période de référence : la fenêtre précédente, de même durée.
                cur.execute(
                    "SELECT risque FROM alerts WHERE source_modele LIKE %s "
                    "AND cree_le <  now() - %s::interval AND cree_le >= now() - %s::interval",
                    (f"%{needle}%", f"{days} days", f"{days * 2} days"),
                )
                reference = [float(r["risque"]) for r in cur.fetchall()]

                cur.execute(
                    "SELECT risque FROM alerts WHERE source_modele LIKE %s "
                    "AND cree_le >= now() - %s::interval",
                    (f"%{needle}%", f"{days} days"),
                )
                current = [float(r["risque"]) for r in cur.fetchall()]

                cur.execute(
                    "SELECT COUNT(*) AS n FROM alerts WHERE source_modele LIKE %s "
                    "AND statut = 'faux_positif' AND cree_le >= now() - %s::interval",
                    (f"%{needle}%", f"{days} days"),
                )
                fp = int(cur.fetchone()["n"])

                cur.execute(
                    "SELECT COUNT(*) AS n FROM metrics WHERE ts >= now() - %s::interval",
                    (f"{days} days",),
                )
                events = int(cur.fetchone()["n"])

            report = build_drift_report(
                reference_scores=reference, current_scores=current,
                fp_count=fp, total_alerts=len(current),
                events_total=max(events, len(current)),
                model_name=label, period_days=days,
            )
            # Tailles d'échantillon : sans elles, un PSI absent est illisible.
            # L'écran doit pouvoir distinguer « pas de dérive » de « pas assez
            # de données pour se prononcer ».
            report["samples"] = {
                "reference_n": len(reference),
                "current_n":   len(current),
                "comparable":  bool(reference and current),
            }
            out.append(report)
        except Exception as e:
            out.append({
                "model": label, "period_days": days, "severity": "unknown",
                "summary": {}, "alerts": [],
                "recommendation": f"Calcul impossible : {e}",
            })

    return {
        "days": days, "available": True, "models": out,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# F-ter. DEMANDE DE MISE SOUS SUPERVISION (formulaire interne contact.html)
# ---------------------------------------------------------------------------
contact_router = APIRouter(prefix="/contact", tags=["Demandes internes"])


class PerimetreRequest(BaseModel):
    systeme:     str
    type:        str
    criticite:   str
    parc:        Optional[str] = None
    contexte:    Optional[str] = None
    responsable: EmailStr


TYPES_VALIDES     = {"application_metier", "reseau", "infrastructure", "poste_utilisateur"}
CRITICITES_VALIDES = {"standard", "sensible", "critique"}


@contact_router.post("/perimetre-request", status_code=201,
                     summary="Demander la mise sous supervision d'un périmètre")
def perimetre_request(body: PerimetreRequest, db=Depends(get_db)):
    """Demande interne entre services du CENADI.

    Ce n'est pas un formulaire de contact commercial : la demande est
    enregistrée, référencée et traitée par l'équipe SOC. Nécessite la table
    `perimetre_requests` (Lot7_Console_Fournisseur/02_schema_contact.sql).
    """
    if body.type not in TYPES_VALIDES:
        raise HTTPException(422, detail=f"type invalide — attendu : {', '.join(sorted(TYPES_VALIDES))}")
    if body.criticite not in CRITICITES_VALIDES:
        raise HTTPException(422, detail=f"criticite invalide — attendu : {', '.join(sorted(CRITICITES_VALIDES))}")

    try:
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO perimetre_requests
                       (systeme, type, criticite, parc, contexte, responsable)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING reference, cree_le""",
                (body.systeme, body.type, body.criticite,
                 body.parc, body.contexte, str(body.responsable)),
            )
            row = cur.fetchone()
            db.commit()
    except psycopg2.errors.UndefinedTable:
        db.rollback()
        raise HTTPException(
            503,
            detail="Table perimetre_requests absente — appliquer "
                   "Lot7_Console_Fournisseur/02_schema_contact.sql sur la base.",
        )

    return {
        "reference": row["reference"],
        "cree_le":   row["cree_le"].isoformat(),
        "message":   "Demande enregistrée. L'équipe SOC la traite sous 2 jours ouvrés.",
    }


# ---------------------------------------------------------------------------
# G. PORTAIL DSI — vue restreinte au tenant du JWT
#    Accessible aux rôles dsi_client, lecteur (et admin_plateforme/analyste_soc).
#    Sert le flux des notifications push in-app + le téléchargement des rapports.
# ---------------------------------------------------------------------------
portail_router = APIRouter(prefix="/portal", tags=["Portail DSI"])


def require_client(authorization: str = Header(...)):
    """JWT obligatoire ; tous les rôles d'un tenant client sont acceptés."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token manquant")
    payload = _decode_jwt(authorization.removeprefix("Bearer "))
    allowed = {"dsi_client", "lecteur", "admin_plateforme", "analyste_soc"}
    if payload.get("role") not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Rôle insuffisant")
    return payload


def _tenant_id_or_403(user: dict) -> str:
    """Renvoie le tenant_id du JWT ; 403 si l'utilisateur n'est pas lié à un tenant."""
    tid = user.get("tenant_id")
    if not tid:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Aucun tenant associé à cet utilisateur (compte plateforme).")
    return tid


@portail_router.get("/alerts", summary="Alertes du tenant courant (filtré par JWT)")
def portal_alerts(limit: int = 50, db=Depends(get_db), user: dict = Depends(require_client)):
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, tenant_id, source_modele, type, entite, risque, raisons,
                   mitre, statut, cree_le, chaine, score_parts
            FROM alerts WHERE tenant_id = %s::uuid
            ORDER BY cree_le DESC LIMIT %s
        """, (tid, limit))
        return [dict(r) for r in cur.fetchall()]


@portail_router.get("/score-history", summary="Score de sécurité jour par jour, avec les jours non mesurés")
def portal_score_history(days: int = 14, db=Depends(get_db),
                         user: dict = Depends(require_client)):
    """Historique du score de sécurité, calculé côté serveur.

    Le portail reconstruisait cette série dans le navigateur avec la règle
    « score du jour = 100 − pire risque du jour ». Un jour SANS alerte y valait
    donc 100 — y compris les jours où la plateforme ne collectait rien. Sur un
    parc réellement mesuré 4 jours sur 14, l'écran affichait dix jours de santé
    parfaite qui n'avaient jamais été observés.

    Un jour sans télémétrie n'est pas un jour sans incident : c'est un jour sans
    information. Le score y vaut NULL, et la courbe s'interrompt.
    """
    days = max(1, min(int(days), 90))
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute(
            """
            WITH bornes AS (
                SELECT (now()::date - (%(d)s - 1) * interval '1 day')::date AS debut
            ),
            jours AS (
                SELECT generate_series((SELECT debut FROM bornes), now()::date,
                                       interval '1 day')::date AS jour
            ),
            mes AS (
                SELECT ts::date AS jour, count(*) AS n
                  FROM metrics
                 WHERE tenant_id = %(t)s::uuid
                   AND ts >= (SELECT debut FROM bornes)
                 GROUP BY 1
            ),
            alt AS (
                SELECT cree_le::date AS jour, max(risque) AS pire, count(*) AS n
                  FROM alerts
                 WHERE tenant_id = %(t)s::uuid
                   AND cree_le >= (SELECT debut FROM bornes)
                 GROUP BY 1
            )
            SELECT j.jour,
                   COALESCE(m.n, 0)  AS mesures,
                   COALESCE(a.n, 0)  AS alertes,
                   a.pire            AS pire_risque
              FROM jours j
              LEFT JOIN mes m ON m.jour = j.jour
              LEFT JOIN alt a ON a.jour = j.jour
             ORDER BY j.jour
            """,
            {"d": days, "t": tid})
        lignes = cur.fetchall()

    serie = []
    for r in lignes:
        mesure = int(r["mesures"] or 0)
        # Une alerte est elle aussi une observation : un jour qui en porte une a
        # forcément été observé, même si la métrique correspondante manque.
        observe = mesure > 0 or int(r["alertes"] or 0) > 0
        serie.append({
            "jour":    r["jour"].isoformat(),
            "mesures": mesure,
            "alertes": int(r["alertes"] or 0),
            "score":   (100 - int(r["pire_risque"] or 0)) if observe else None,
        })

    mesures_jours = sum(1 for d in serie if d["score"] is not None)
    return {
        "days": days,
        "serie": serie,
        "jours_mesures": mesures_jours,
        "jours_aveugles": len(serie) - mesures_jours,
        "source": "alerts + metrics, agrégés par jour côté serveur",
    }


@portail_router.post("/alerts/{alert_id}/request-isolation", status_code=201,
                     summary="Demander l'isolation de l'entité d'une alerte")
def portal_request_isolation(alert_id: str, body: dict = None, db=Depends(get_db),
                             user: dict = Depends(require_client)):
    """Le responsable de périmètre demande une isolation ; il ne l'exécute pas.

    La demande entre dans la file SOAR comme n'importe quelle proposition, en
    attente de validation d'un analyste. C'est le point important : le portail
    donne un moyen d'agir sans transférer au responsable métier un pouvoir
    d'exécution sur le parc.

    Refusée si une demande est déjà en attente sur la même alerte — un bouton
    cliqué trois fois ne doit pas produire trois décisions à arbitrer.
    """
    tid = _tenant_id_or_403(user)
    motif = (body or {}).get("motif") or ""
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, entite, type, risque FROM alerts "
            " WHERE id = %s::uuid AND tenant_id = %s::uuid",
            (alert_id, tid))
        alerte = cur.fetchone()
        if not alerte:
            raise HTTPException(404, detail="Alerte introuvable sur ce périmètre.")

        cur.execute(
            "SELECT id FROM soar_audit "
            " WHERE alert_id = %s::uuid AND action = 'isolate_host' "
            "   AND statut = 'EN ATTENTE DE VALIDATION' LIMIT 1",
            (alert_id,))
        if cur.fetchone():
            raise HTTPException(
                409, detail="Une demande d'isolation est déjà en attente sur cette alerte.")

        entite = alerte["entite"] or ""
        cible = entite[5:] if entite.startswith("hote_") else entite
        cur.execute(
            "INSERT INTO soar_audit (alert_id, tenant_id, action, impact, statut, detail, "
            "                        cible, cible_type, acteur) "
            "VALUES (%s::uuid, %s::uuid, 'isolate_host', 'fort', "
            "        'EN ATTENTE DE VALIDATION', %s, %s, 'hote', %s) "
            "RETURNING id",
            (alert_id, tid,
             f"Isolation demandée par le responsable de périmètre sur l'alerte "
             f"« {alerte['type']} » (risque {alerte['risque']})."
             + (f" Motif : {motif}" if motif else ""),
             cible, user.get("email", "responsable")))
        ref = cur.fetchone()["id"]
        db.commit()

    return {"message": "Demande transmise au SOC. Un analyste doit la valider "
                       "avant toute exécution.",
            "audit_id": str(ref), "cible": cible}


@portail_router.get("/reports", summary="Historique des rapports d'incident du périmètre")
def portal_reports(limit: int = 50, db=Depends(get_db),
                   user: dict = Depends(require_client)):
    """Tous les rapports produits sur le périmètre, pas seulement le dernier.

    Un responsable doit pouvoir retrouver un incident d'il y a trois semaines
    pour l'annexer à un compte rendu ; le portail n'exposait que la dernière
    notification lue.
    """
    limit = max(1, min(int(limit), 200))
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute("""
            SELECT n.id, n.title, n.severity, n.created_at, n.read_at,
                   a.entite, a.type AS type_alerte, a.risque, a.statut AS statut_alerte
              FROM notifications n
              LEFT JOIN alerts a ON a.id = n.alert_id
             WHERE n.tenant_id = %s::uuid AND n.report_html IS NOT NULL
             ORDER BY n.created_at DESC
             LIMIT %s
        """, (tid, limit))
        return {"items": [dict(r) for r in cur.fetchall()]}


@portail_router.get("/agents", summary="Agents du tenant courant")
def portal_agents(db=Depends(get_db), user: dict = Depends(require_client)):
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute(f"""
            SELECT a.id, a.tenant_id, a.hostname, a.os, a.vu_le,
                   {agent_presence_cols('a')}
              FROM agents a WHERE a.tenant_id = %s::uuid
             ORDER BY a.hostname
        """, (tid,))
        return [dict(r) for r in cur.fetchall()]


@portail_router.get("/notifications", summary="Notifications push in-app du tenant")
def portal_notifications(
    unread_only: bool = False,
    limit: int = 50,
    db=Depends(get_db),
    user: dict = Depends(require_client),
):
    tid = _tenant_id_or_403(user)
    conditions = ["tenant_id = %s::uuid"]
    vals = [tid]
    if unread_only:
        conditions.append("read_at IS NULL")
    vals.append(limit)
    with db.cursor() as cur:
        cur.execute(f"""
            SELECT id, tenant_id, alert_id, type, severity, title, body,
                   (report_html IS NOT NULL) AS has_report,
                   created_at, read_at
            FROM notifications
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC LIMIT %s
        """, vals)
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT COUNT(*) AS n FROM notifications "
            "WHERE tenant_id = %s::uuid AND read_at IS NULL",
            (tid,),
        )
        unread = cur.fetchone()["n"]
    return {"items": rows, "unread_count": unread}


@portail_router.post("/notifications/{notif_id}/mark-read",
                     summary="Marquer une notification comme lue")
def portal_notif_mark_read(notif_id: str, db=Depends(get_db),
                           user: dict = Depends(require_client)):
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE notifications SET read_at = now() "
            "WHERE id = %s::uuid AND tenant_id = %s::uuid AND read_at IS NULL "
            "RETURNING id",
            (notif_id, tid),
        )
        row = cur.fetchone()
        db.commit()
    if not row:
        # idempotent : déjà lue ou inexistante → 200 quand même
        return {"status": "noop"}
    return {"status": "marked_read"}


@portail_router.post("/notifications/mark-all-read",
                     summary="Marquer toutes les notifications comme lues")
def portal_notif_mark_all_read(db=Depends(get_db), user: dict = Depends(require_client)):
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE notifications SET read_at = now() "
            "WHERE tenant_id = %s::uuid AND read_at IS NULL RETURNING id",
            (tid,),
        )
        n = cur.rowcount
        db.commit()
    return {"status": "ok", "marked": n}


@portail_router.get("/notifications/{notif_id}/report",
                    summary="Rapport HTML enrichi (affichage in-app)")
def portal_notif_report(notif_id: str, lang: str = "fr", db=Depends(get_db),
                        user: dict = Depends(require_client)):
    """Renvoie le rapport HTML en JSON pour affichage dans le modal du portail."""
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, title, severity, report_html, created_at "
            "FROM notifications WHERE id = %s::uuid AND tenant_id = %s::uuid",
            (notif_id, tid),
        )
        row = cur.fetchone()
    if not row or not row.get("report_html"):
        raise HTTPException(404, detail="Rapport introuvable")
    out = dict(row)
    if lang != "fr":
        rendu = _rapport_traduit(db, notif_id, tid, lang)
        if rendu:
            out["report_html"] = rendu
            out["lang"] = lang
        else:
            # Le rapport français reste servi : mieux vaut un document lisible
            # dans la mauvaise langue qu'une erreur devant un lecteur pressé.
            out["lang"] = "fr"
            out["lang_note"] = "Traduction indisponible : alerte source introuvable."
    return out


def _rapport_traduit(db, notif_id: str, tenant_id: str, lang: str):
    """Re-produit le rapport dans une autre langue à partir de l'alerte source.

    Le rapport français est figé en base au moment de l'incident : c'est lui qui
    fait foi. La version anglaise est rendue à la demande depuis les mêmes
    données — jamais traduite depuis le HTML, ce qui produirait deux documents
    dont les empreintes ne diraient rien l'une de l'autre.
    """
    try:
        from nexus_scoring import _rapport_html  # type: ignore
    except Exception:
        return None
    with db.cursor() as cur:
        cur.execute(
            """SELECT a.entite, a.type, a.risque, a.source_modele, a.mitre,
                      a.raisons, a.chaine, a.score_parts, a.id::text AS aid,
                      t.nom AS perimetre
                 FROM notifications n
                 JOIN alerts a  ON a.id = n.alert_id
                 JOIN tenants t ON t.id = n.tenant_id
                WHERE n.id = %s::uuid AND n.tenant_id = %s::uuid""",
            (notif_id, tenant_id))
        row = cur.fetchone()
    if not row:
        return None
    return _rapport_html(
        {"entite": row["entite"], "type": row["type"], "src": row["source_modele"],
         "mitre": row["mitre"], "raisons": row["raisons"],
         "chaine": row["chaine"], "score_parts": row["score_parts"]},
        int(row["risque"] or 0), row["aid"][:8], row["perimetre"], lang=lang)


@portail_router.get("/notifications/{notif_id}/download",
                    summary="Téléchargement du rapport HTML (attachment)")
def portal_notif_download(notif_id: str, lang: str = "fr", db=Depends(get_db),
                          user: dict = Depends(require_client)):
    """Renvoie le rapport HTML brut avec Content-Disposition: attachment."""
    from fastapi.responses import Response
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute(
            "SELECT report_html FROM notifications "
            "WHERE id = %s::uuid AND tenant_id = %s::uuid",
            (notif_id, tid),
        )
        row = cur.fetchone()
    if not row or not row.get("report_html"):
        raise HTTPException(404, detail="Rapport introuvable")

    contenu, suffixe = row["report_html"], ""
    if lang != "fr":
        rendu = _rapport_traduit(db, notif_id, tid, lang)
        if rendu:
            contenu, suffixe = rendu, f"-{lang}"

    filename = f"rapport-nexussoc-{notif_id[:8]}{suffixe}.html"
    return Response(
        content=contenu,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# G-bis. ANALYSE EN LANGAGE CLAIR — module Analyst (Lot 5)
# ---------------------------------------------------------------------------
# `LLMAnalyst` était écrit, testé, bilingue… et joignable par aucun endpoint :
# le portail devait recomposer l'explication côté navigateur. Elle est désormais
# produite par le serveur, ce qui la rend identique dans le portail, le rapport
# HTML et les notifications, et débloque au passage le mode LLM optionnel.
try:
    import sys as _sys
    _lot5 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "Lot5_Restitution", "portail")
    if _lot5 not in _sys.path:
        _sys.path.insert(0, _lot5)
    from notifier import LLMAnalyst  # type: ignore
    _ANALYST = LLMAnalyst(mode=os.getenv("ANALYST_MODE", "template"))
except Exception as _e:  # pragma: no cover
    _ANALYST = None
    print(f"[analyst] module de restitution indisponible : {_e}")


def _alerte_vers_incident(row: dict) -> dict:
    """Traduit une ligne `alerts` vers la structure attendue par LLMAnalyst."""
    chaine = row.get("chaine") or []
    return {
        "type":     row.get("type") or "Compromission probable",
        "entity":   row.get("entite") or "?",
        "risque":   int(row.get("risque") or 0),
        "mitre":    [t.strip() for t in str(row.get("mitre") or "").split(",") if t.strip()],
        "chaine":   chaine,
        "tactiques": list(dict.fromkeys(
            e.get("tactique") for e in chaine if isinstance(e, dict) and e.get("tactique"))),
        # Le moteur de corrélation marque l'activité nocturne ; à défaut de
        # chaîne, on la déduit de l'heure de levée de l'alerte.
        "activite_hors_heures": bool(
            row.get("cree_le") and (row["cree_le"].hour >= 19 or row["cree_le"].hour < 6)),
    }


@portail_router.get("/alerts/{alert_id}/explain",
                    summary="Explication d'un incident en langage clair (FR/EN)")
def portal_explain(alert_id: str, lang: str = "fr", db=Depends(get_db),
                   user: dict = Depends(require_client)):
    """Paragraphe de 3 à 5 phrases destiné à un responsable non technicien.

    Mode `template` par défaut : explication déterministe, sans risque
    d'hallucination. Mode `llm` si ANALYST_MODE=llm et LLM_API_URL sont fournis,
    avec repli automatique sur le template en cas d'échec.
    """
    tid = _tenant_id_or_403(user)
    lang = "en" if str(lang).lower().startswith("en") else "fr"

    with db.cursor() as cur:
        cur.execute("""
            SELECT id, type, entite, risque, mitre, raisons, chaine, cree_le, source_modele
              FROM alerts WHERE id = %s::uuid AND tenant_id = %s::uuid
        """, (alert_id, tid))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, detail="Alerte introuvable sur ce périmètre")

    if _ANALYST is None:
        raise HTTPException(
            503, detail="Module de restitution indisponible sur ce déploiement.")

    incident = _alerte_vers_incident(dict(row))
    try:
        texte = _ANALYST.explain(incident, lang=lang)
    except Exception as e:
        raise HTTPException(500, detail=f"Explication non produite : {e}")

    return {
        "alert_id":    str(row["id"]),
        "lang":        lang,
        "mode":        getattr(_ANALYST, "mode", "template"),
        "texte":       texte,
        "genere_le":   datetime.now(timezone.utc).isoformat(),
        "source":      row.get("source_modele"),
    }


@portail_router.get("/summary", summary="Synthèse temps-réel du tenant (KPIs portail)")
def portal_summary(db=Depends(get_db), user: dict = Depends(require_client)):
    tid = _tenant_id_or_403(user)
    with db.cursor() as cur:
        cur.execute(f"""
            SELECT
              -- « non résolue » n'est pas « ouverte » : un faux positif écarté
              -- par un analyste et une alerte agrégée à une plus récente ne
              -- pèsent ni sur le compteur ni sur le score. Le filtre les
              -- comptait, gonflant SIGIPES à 17 incidents ouverts pour 3 réels.
              (SELECT COUNT(*) FROM alerts WHERE tenant_id=%s::uuid
                AND statut NOT IN ('resolue','faux_positif','agregee')) AS open_alerts,
              (SELECT COALESCE(MAX(risque),0) FROM alerts WHERE tenant_id=%s::uuid
                AND statut NOT IN ('resolue','faux_positif','agregee')) AS max_risk,
              (SELECT COUNT(*) FROM agents a
                WHERE a.tenant_id=%s::uuid AND {agent_statut_sql('a')}='actif') AS agents_active,
              (SELECT COUNT(*) FROM agents WHERE tenant_id=%s::uuid) AS agents_total,
              (SELECT COUNT(*) FROM notifications WHERE tenant_id=%s::uuid AND read_at IS NULL) AS unread_notifications
        """, (tid, tid, tid, tid, tid))
        row = cur.fetchone()
    out = dict(row) if row else {}
    out["stale_after_s"] = AGENT_STALE_SECONDS
    return out
