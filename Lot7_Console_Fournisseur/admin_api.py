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
    type: str          # administration | microfinance | assurance | cabinet_comptable
    offre: str         # starter | business | enterprise | contrat_public
    email_admin: Optional[EmailStr] = None


class TenantUpdate(BaseModel):
    nom: Optional[str] = None
    offre: Optional[str] = None
    statut: Optional[str] = None   # actif | suspendu


class UserCreate(BaseModel):
    email: EmailStr
    role: str          # admin_plateforme | analyste_soc | dsi_client | lecteur
    tenant_id: Optional[str] = None
    mot_de_passe: str


# ---------------------------------------------------------------------------
# A. TENANTS
# ---------------------------------------------------------------------------
@router.get("/tenants", summary="Lister tous les tenants")
def list_tenants(db=Depends(get_db), _=Depends(require_admin)):
    """Retourne la liste des tenants avec métriques d'agents et d'alertes."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT
                t.id, t.nom, t.type, t.offre, t.cree_le,
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


@router.post("/tenants", status_code=201, summary="Créer un tenant")
def create_tenant(body: TenantCreate, db=Depends(get_db), _=Depends(require_admin)):
    TYPES_OK  = {"administration", "microfinance", "assurance", "cabinet_comptable"}
    OFFRES_OK = {"starter", "business", "enterprise", "contrat_public"}
    if body.type not in TYPES_OK:
        raise HTTPException(400, detail=f"type invalide : {body.type}")
    if body.offre not in OFFRES_OK:
        raise HTTPException(400, detail=f"offre invalide : {body.offre}")
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (nom, type, offre) VALUES (%s, %s, %s) RETURNING id",
            (body.nom, body.type, body.offre)
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
    return {"id": str(tenant_id), "message": "Tenant créé"}


@router.patch("/tenants/{tenant_id}", summary="Modifier / suspendre un tenant")
def update_tenant(tenant_id: str, body: TenantUpdate, db=Depends(get_db), _=Depends(require_admin)):
    sets, vals = [], []
    if body.nom:
        sets.append("nom = %s"); vals.append(body.nom)
    if body.offre:
        sets.append("offre = %s"); vals.append(body.offre)
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
    return {"message": "Tenant mis à jour"}


@router.post("/tenants/{tenant_id}/suspend", summary="Suspendre un tenant (coupe l'ingestion)")
def suspend_tenant(tenant_id: str, db=Depends(get_db), _=Depends(require_admin)):
    """Marque le tenant comme suspendu (colonne PLG suspended_at + plan)."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE tenants SET suspended_at = now(), plan = 'suspended' "
            "WHERE id = %s AND suspended_at IS NULL RETURNING id",
            (tenant_id,)
        )
        row = cur.fetchone()
        db.commit()
    if not row:
        raise HTTPException(404, detail="Tenant introuvable ou déjà suspendu")
    return {"message": "Tenant suspendu", "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/activate", summary="Réactiver un tenant suspendu")
def activate_tenant(tenant_id: str, db=Depends(get_db), _=Depends(require_admin)):
    """Lève la suspension. Remet le plan à 'trial' si aucun abonnement payant."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE tenants SET suspended_at = NULL, "
            "plan = CASE WHEN plan = 'suspended' THEN 'trial' ELSE plan END "
            "WHERE id = %s RETURNING id",
            (tenant_id,)
        )
        row = cur.fetchone()
        db.commit()
    if not row:
        raise HTTPException(404, detail="Tenant introuvable")
    return {"message": "Tenant réactivé", "tenant_id": tenant_id}


@router.delete("/tenants/{tenant_id}", summary="Supprimer un tenant (irréversible)")
def delete_tenant(tenant_id: str, db=Depends(get_db), _=Depends(require_admin)):
    with db.cursor() as cur:
        cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
        db.commit()
    return {"message": "Tenant supprimé"}


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
    with db.cursor() as cur:
        if tenant_id:
            cur.execute(
                "SELECT id, tenant_id, hostname, os, statut, vu_le FROM agents WHERE tenant_id = %s",
                (tenant_id,)
            )
        else:
            cur.execute("SELECT id, tenant_id, hostname, os, statut, vu_le FROM agents ORDER BY tenant_id, hostname")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


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
    hmac_key     = secrets.token_hex(32)           # 256 bits
    token_hash   = hashlib.sha256(bearer_token.encode()).hexdigest()

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO agents (tenant_id, hostname, statut) "
            "VALUES (%s, %s, 'hors_ligne') RETURNING id",
            (tenant_id, hostname)
        )
        agent_id = cur.fetchone()["id"]
        # Stocker uniquement le hash du token (jamais le token en clair)
        # Nécessite une colonne token_hash TEXT dans agents (voir 01_schema_analyst.sql)
        cur.execute(
            "UPDATE agents SET token_hash = %s, hmac_key_hash = %s WHERE id = %s",
            (token_hash, hashlib.sha256(hmac_key.encode()).hexdigest(), str(agent_id))
        )
        db.commit()

    return {
        "agent_id": str(agent_id),
        "bearer_token": bearer_token,
        "hmac_key": hmac_key,
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
# E. FACTURATION (vue simple)
# ---------------------------------------------------------------------------
OFFRE_MONTANT = {"starter": 25000, "business": 75000, "enterprise": 200000, "contrat_public": None}

@router.get("/billing", summary="Vue facturation par tenant")
def list_billing(db=Depends(get_db), _=Depends(require_admin)):
    with db.cursor() as cur:
        cur.execute("SELECT id, nom, offre, cree_le FROM tenants ORDER BY cree_le")
        tenants = cur.fetchall()
    result = []
    for t in tenants:
        montant = OFFRE_MONTANT.get(t["offre"])
        result.append({
            "tenant_id": str(t["id"]),
            "nom": t["nom"],
            "offre": t["offre"],
            "montant_fcfa": montant,
            "devise": "XAF",
            "statut": "actif",
        })
    return result


# ---------------------------------------------------------------------------
# F. ANALYSTE SOC — lecture cross-tenant (pas de filtre RLS)
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
                   a.entite, a.risque, a.raisons, a.mitre, a.statut, a.cree_le
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
                   a.entite, a.risque, a.raisons, a.mitre, a.statut, a.cree_le
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
                   a.entite, a.type, a.risque
            FROM soar_audit s
            JOIN tenants t ON t.id = s.tenant_id
            LEFT JOIN alerts a ON a.id = s.alert_id
            WHERE s.statut = 'EN ATTENTE DE VALIDATION'
            ORDER BY s.horodatage DESC
        """)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


@analyst_router.post("/approve/{action_id}", summary="Approuver une action SOAR par son id")
def approve_action_by_id(action_id: int, body: dict = None,
                         db=Depends(get_analyst_db), _=Depends(require_analyst)):
    """Approuve une action SOAR (clé = soar_audit.id) — appelé par la console."""
    actor = (body or {}).get("approved_by", "analyste_soc")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE soar_audit SET statut = 'EXÉCUTÉE', decision = 'APPROUVÉE', acteur = %s "
            "WHERE id = %s AND statut = 'EN ATTENTE DE VALIDATION' RETURNING id",
            (actor, action_id)
        )
        updated = cur.fetchone()
        db.commit()
    if not updated:
        raise HTTPException(404, detail="Action en attente introuvable")
    return {"message": "Action approuvée et exécutée", "audit_id": str(updated["id"])}


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
    """Variante historique : valide par (alert_id, action). Conservée pour compat."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE soar_audit SET statut = 'EXÉCUTÉE', decision = 'APPROUVÉE', acteur = 'analyste_soc' "
            "WHERE alert_id = %s AND action = %s AND statut = 'EN ATTENTE DE VALIDATION' "
            "RETURNING id",
            (alert_id, action)
        )
        updated = cur.fetchone()
        db.commit()
    if not updated:
        raise HTTPException(404, detail="Action en attente introuvable")
    return {"message": "Action approuvée et exécutée", "audit_id": str(updated["id"])}


@analyst_router.get("/dashboard", summary="Tableau de bord SOC global")
def soc_dashboard(db=Depends(get_analyst_db), _=Depends(require_analyst)):
    """Métriques globales cross-tenants pour le poste analyste."""
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM alerts WHERE statut = 'ouverte'")
        open_alerts = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM alerts WHERE statut = 'ouverte' AND risque >= 80")
        critical = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM agents WHERE statut = 'actif'")
        agents_online = cur.fetchone()["n"]
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
        "tenants_total": tenants_total,
        "top_tenants_by_incidents": top_tenants,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
