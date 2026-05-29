# =============================================================================
# NEXUS SOC — Lot 8 : API PLG (Product-Led Growth)
# Flux automatisé SaaS pour microfinances et cabinets comptables
#
# Montage : inclure ce router dans scoring-service_app.py :
#   from plg_api import router as plg_router
#   app.include_router(plg_router)
# =============================================================================

import os
import re
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from pydantic import BaseModel, validator

logger = logging.getLogger("nexus.plg")

router = APIRouter(prefix="/plg", tags=["PLG"])

# =============================================================================
# Filtrage email
# =============================================================================

DISPOSABLE_DOMAINS: frozenset = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.info", "guerrillamail.biz",
    "guerrillamail.de", "guerrillamail.net", "guerrillamail.org",
    "tempmail.com", "throwaway.email", "yopmail.com", "maildrop.cc",
    "10minutemail.com", "10minutemail.net", "sharklasers.com", "spam4.me",
    "trashmail.at", "trashmail.com", "trashmail.io", "trashmail.me",
    "trashmail.net", "trashmail.org", "trashmail.xyz", "getairmail.com",
    "dispostable.com", "discard.email", "spamgourmet.com", "spamgourmet.net",
    "fakeinbox.com", "mytrashmail.com", "mailnull.com", "tempr.email",
    "cmail.club", "cmail.rocks", "luxusmail.org", "luxusmail.uk",
    "zetmail.com", "sogetthis.com", "spamhereplease.com", "spambob.com",
    "filzmail.com", "bumpymail.com", "mt2009.com", "mt2014.com", "mt2015.com",
    "mailtemp.info", "wegwerfmail.de", "wegwerfmail.net", "wegwerfmail.org",
    "spamfree24.org", "spamfree.eu", "notsharingmy.info",
})

# Patterns de domaines souverains/étatiques → redirection flux Hub & Spoke
_GOV_PATTERNS = [
    re.compile(r"\.gov\.cm$"),
    re.compile(r"\.gouv\.cm$"),
    re.compile(r"\.mil\.cm$"),
    re.compile(r"\.edu\.cm$"),
    re.compile(r"^minfi(\.gov)?\.cm$"),
    re.compile(r"^minfopra\.cm$"),
    re.compile(r"^finances\.cm$"),
    re.compile(r"^dgi\.cm$"),
    re.compile(r"^dgd\.cm$"),
    re.compile(r"^beac\.int$"),
    re.compile(r"^cobac\.org$"),
    re.compile(r"^antic\.cm$"),
    re.compile(r"^camtel\.cm$"),
    re.compile(r"\.cm$"),  # tout domaine .cm → vérification manuelle
]


def _domain(email: str) -> str:
    return email.lower().split("@", 1)[-1]


def is_disposable(email: str) -> bool:
    return _domain(email) in DISPOSABLE_DOMAINS


def is_gov_domain(email: str) -> bool:
    d = _domain(email)
    return any(p.search(d) for p in _GOV_PATTERNS)


# =============================================================================
# Configuration des plans
# =============================================================================

TRIAL_CFG = {
    "max_agents":       5,
    "max_daily_events": 10_000,
    "duration_days":    30,
}

PLAN_CFG = {
    "starter":    {"amount_fcfa": 25_000,  "max_agents": 10,  "max_daily_events": 50_000},
    "business":   {"amount_fcfa": 75_000,  "max_agents": 50,  "max_daily_events": 200_000},
    "enterprise": {"amount_fcfa": 200_000, "max_agents": 200, "max_daily_events": 1_000_000},
}

# =============================================================================
# Schémas Pydantic
# =============================================================================

class RegistrationRequest(BaseModel):
    email: str
    organization_name: str
    sector: str  # microfinance | assurance | cabinet | autre

    @validator("sector")
    def valid_sector(cls, v):
        allowed = {"microfinance", "assurance", "cabinet", "autre"}
        if v not in allowed:
            raise ValueError(f"Secteur invalide : {allowed}")
        return v

    @validator("email")
    def valid_email(cls, v):
        v = v.lower().strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Adresse e-mail invalide")
        return v


class EmailVerifyRequest(BaseModel):
    token: str


class PreAuthRequest(BaseModel):
    registration_id: str
    card_token: str  # token opaque fourni par CinetPay / PayDunya


class UpgradeRequest(BaseModel):
    tenant_id: str
    plan: str
    payment_reference: str


class AgentConfigRequest(BaseModel):
    agent_id: str


# =============================================================================
# Dépendance DB (réutilise le pool asyncpg de l'app principale)
# =============================================================================

async def _db(request: Request) -> asyncpg.Pool:
    return request.app.state.db


# =============================================================================
# Endpoints PLG
# =============================================================================

@router.post("/check-email")
async def check_email(body: dict, db: asyncpg.Pool = Depends(_db)):
    """
    Validation live (appelé en debounce pendant la saisie).
    Retourne 422 si email jetable ou domaine souverain.
    """
    email = body.get("email", "").lower().strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Adresse e-mail invalide")

    if is_disposable(email):
        raise HTTPException(422, detail={
            "code":    "DISPOSABLE_EMAIL",
            "message": (
                "Les adresses e-mail temporaires ne sont pas acceptées. "
                "Utilisez l'adresse professionnelle de votre organisation."
            ),
        })

    if is_gov_domain(email):
        raise HTTPException(422, detail={
            "code":        "GOV_DOMAIN_REDIRECT",
            "message": (
                "Votre domaine correspond à une organisation publique ou réglementée. "
                "Le flux SaaS automatisé n'est pas disponible pour ce type d'entité. "
                "Utilisez le formulaire Déploiement Souverain pour être mis en contact "
                "avec un architecte NEXUS SOC."
            ),
            "redirect_to": "sovereign_contact",
        })

    return {"valid": True, "email": email}


@router.post("/register")
async def register(
    body: RegistrationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: asyncpg.Pool = Depends(_db),
):
    """
    Étape 1 — Crée l'entrée d'inscription et envoie un e-mail de vérification.
    Bloque les emails jetables et les domaines souverains.
    """
    email = body.email

    if is_disposable(email):
        raise HTTPException(422, "Adresse e-mail jetable non acceptée")
    if is_gov_domain(email):
        raise HTTPException(422, detail={
            "code": "GOV_DOMAIN_REDIRECT",
            "redirect_to": "sovereign_contact",
        })

    existing = await db.fetchrow(
        "SELECT id, email_verified, tenant_id, verification_token FROM plg_registrations WHERE email = $1",
        email,
    )
    if existing:
        if existing["tenant_id"]:
            raise HTTPException(409, "Un compte existe déjà pour cette adresse e-mail.")
        # Renvoi du lien si pas encore vérifié
        background_tasks.add_task(
            _send_verification_email, email, existing["verification_token"], body.organization_name
        )
        return {"status": "resent", "message": "Lien de vérification renvoyé."}

    token = secrets.token_urlsafe(32)
    ip    = request.client.host if request.client else None

    await db.execute(
        """
        INSERT INTO plg_registrations
            (email, organization_name, sector, verification_token, verification_sent_at, ip_address)
        VALUES ($1, $2, $3, $4, NOW(), $5)
        """,
        email, body.organization_name, body.sector, token, ip,
    )

    background_tasks.add_task(_send_verification_email, email, token, body.organization_name)
    return {"status": "pending_verification", "message": "E-mail de vérification envoyé."}


@router.post("/verify-email")
async def verify_email(body: EmailVerifyRequest, db: asyncpg.Pool = Depends(_db)):
    """
    Étape 2 — Confirme l'adresse e-mail via le token reçu.
    Débloque la pré-autorisation bancaire.
    """
    reg = await db.fetchrow(
        "SELECT id, email, email_verified FROM plg_registrations WHERE verification_token = $1",
        body.token,
    )
    if not reg:
        raise HTTPException(404, "Token de vérification invalide ou expiré.")

    if reg["email_verified"]:
        return {"status": "already_verified", "registration_id": str(reg["id"])}

    await db.execute(
        "UPDATE plg_registrations SET email_verified = TRUE, verification_token = NULL WHERE id = $1",
        reg["id"],
    )
    return {
        "status":          "verified",
        "registration_id": str(reg["id"]),
        "next_step":       "preauth",
        "message":         "Adresse confirmée. Procédez à la validation d'identité.",
    }


@router.post("/preauth")
async def bank_preauth(
    body: PreAuthRequest,
    db: asyncpg.Pool = Depends(_db),
):
    """
    Étape 3 — Pré-autorisation bancaire à 0 FCFA.
    Protège le cluster Kafka contre les inscriptions frauduleuses en masse.

    Intégration production :
      - CinetPay : https://developer.cinetpay.com/
      - PayDunya  : https://paydunya.com/api-docs
    La fonction _run_preauth() est le seul point à remplacer.
    """
    try:
        reg_uuid = body.registration_id
    except Exception:
        raise HTTPException(400, "registration_id invalide")

    reg = await db.fetchrow(
        """
        SELECT id, email, organization_name, sector, email_verified, preauth_completed
        FROM plg_registrations WHERE id = $1
        """,
        reg_uuid,
    )
    if not reg:
        raise HTTPException(404, "Inscription introuvable.")
    if not reg["email_verified"]:
        raise HTTPException(400, "L'e-mail doit être vérifié avant la pré-autorisation.")
    if reg["preauth_completed"]:
        tenant_id = await db.fetchval(
            "SELECT tenant_id FROM plg_registrations WHERE id = $1", reg_uuid
        )
        return {"status": "already_completed", "tenant_id": str(tenant_id) if tenant_id else None}

    result = await _run_preauth(body.card_token)
    if not result["success"]:
        raise HTTPException(402, detail={
            "code":    "PREAUTH_FAILED",
            "message": result.get("message", "La validation d'identité a échoué."),
        })

    await db.execute(
        """
        UPDATE plg_registrations
        SET preauth_completed = TRUE, preauth_reference = $2, preauth_completed_at = NOW()
        WHERE id = $1
        """,
        reg_uuid, result["reference"],
    )

    tenant_id = await _provision_tenant(db, reg)

    logger.info("PLG tenant provisioned | tenant=%s | email=%s", tenant_id, reg["email"])
    return {
        "status":      "activated",
        "tenant_id":   str(tenant_id),
        "trial_days":  TRIAL_CFG["duration_days"],
        "max_agents":  TRIAL_CFG["max_agents"],
        "message":     f"Compte activé. Essai gratuit de {TRIAL_CFG['duration_days']} jours démarré.",
    }


@router.get("/trial-status/{tenant_id}")
async def trial_status(tenant_id: str, db: asyncpg.Pool = Depends(_db)):
    """Retourne l'état de l'essai : jours restants, quota agents, quota événements."""
    row = await db.fetchrow(
        """
        SELECT
            t.plan,
            t.trial_ends_at,
            t.suspended_at,
            t.max_agents,
            t.max_daily_events,
            COALESCE(q.agent_count, 0) AS agents_today,
            COALESCE(q.event_count, 0) AS events_today
        FROM tenants t
        LEFT JOIN trial_quotas q ON q.tenant_id = t.id AND q.date = CURRENT_DATE
        WHERE t.id = $1::uuid
        """,
        tenant_id,
    )
    if not row:
        raise HTTPException(404, "Tenant introuvable.")

    remaining_days = None
    if row["trial_ends_at"]:
        delta = row["trial_ends_at"] - datetime.now(timezone.utc)
        remaining_days = max(0, delta.days)

    return {
        "plan":           row["plan"],
        "trial_ends_at":  row["trial_ends_at"].isoformat() if row["trial_ends_at"] else None,
        "remaining_days": remaining_days,
        "suspended":      row["suspended_at"] is not None,
        "quota": {
            "max_agents":       row["max_agents"],
            "agents_active":    row["agents_today"],
            "agents_pct":       _pct(row["agents_today"], row["max_agents"]),
            "max_daily_events": row["max_daily_events"],
            "events_today":     row["events_today"],
            "events_pct":       _pct(row["events_today"], row["max_daily_events"]),
        },
    }


@router.get("/plans")
async def list_plans():
    """Plans disponibles avec tarification en FCFA."""
    return {
        "trial": {
            "label":       "Essai gratuit",
            "price_fcfa":  0,
            "duration_days": TRIAL_CFG["duration_days"],
            "max_agents":  TRIAL_CFG["max_agents"],
            "features":    ["Portail DSI", "5 agents max", "Alertes e-mail", "LLM Analyst (mode template)"],
        },
        "starter": {
            "label":      "Starter",
            "price_fcfa": PLAN_CFG["starter"]["amount_fcfa"],
            "max_agents": PLAN_CFG["starter"]["max_agents"],
            "features":   ["Portail DSI", "10 agents", "Alertes e-mail", "LLM Analyst"],
        },
        "business": {
            "label":      "Business",
            "price_fcfa": PLAN_CFG["business"]["amount_fcfa"],
            "max_agents": PLAN_CFG["business"]["max_agents"],
            "features":   [
                "Portail DSI", "50 agents", "SMS + WhatsApp", "SOAR semi-auto",
                "Modèle UEBA fraude interne", "1 session formation/mois",
            ],
        },
        "enterprise": {
            "label":      "Enterprise",
            "price_fcfa": PLAN_CFG["enterprise"]["amount_fcfa"],
            "max_agents": PLAN_CFG["enterprise"]["max_agents"],
            "features":   [
                "Portail DSI", "200 agents", "SMS + WhatsApp", "SOAR complet",
                "Modèle réseau + UEBA", "Tableau de bord SOC", "API", "SLA 4h",
            ],
        },
    }


@router.post("/upgrade")
async def upgrade_plan(body: UpgradeRequest, db: asyncpg.Pool = Depends(_db)):
    """Souscrit un plan payant. Appeler après confirmation du paiement."""
    if body.plan not in PLAN_CFG:
        raise HTTPException(400, f"Plan invalide. Valeurs : {list(PLAN_CFG)}")

    cfg = PLAN_CFG[body.plan]

    async with db.acquire() as conn:
        async with conn.transaction():
            rows = await conn.execute(
                """
                UPDATE tenants SET
                    plan             = $2,
                    max_agents       = $3,
                    max_daily_events = $4,
                    trial_ends_at    = NULL,
                    suspended_at     = NULL
                WHERE id = $1::uuid
                """,
                body.tenant_id, body.plan, cfg["max_agents"], cfg["max_daily_events"],
            )
            if rows == "UPDATE 0":
                raise HTTPException(404, "Tenant introuvable.")

            await conn.execute(
                """
                INSERT INTO subscriptions (tenant_id, plan, amount_fcfa, payment_reference)
                VALUES ($1::uuid, $2, $3, $4)
                """,
                body.tenant_id, body.plan, cfg["amount_fcfa"], body.payment_reference,
            )

    return {"status": "upgraded", "plan": body.plan, "max_agents": cfg["max_agents"]}


@router.post("/suspend/{tenant_id}")
async def suspend_tenant(tenant_id: str, db: asyncpg.Pool = Depends(_db)):
    """Admin — suspend un tenant (non-paiement ou fin d'essai)."""
    r = await db.execute(
        "UPDATE tenants SET suspended_at = NOW(), plan = 'suspended' WHERE id = $1::uuid AND suspended_at IS NULL",
        tenant_id,
    )
    if r == "UPDATE 0":
        raise HTTPException(404, "Tenant introuvable ou déjà suspendu.")
    return {"status": "suspended", "tenant_id": tenant_id}


@router.post("/resume/{tenant_id}")
async def resume_tenant(tenant_id: str, db: asyncpg.Pool = Depends(_db)):
    """Admin — réactive un tenant suspendu après paiement."""
    await db.execute(
        "UPDATE tenants SET suspended_at = NULL WHERE id = $1::uuid",
        tenant_id,
    )
    return {"status": "active", "tenant_id": tenant_id}


@router.post("/run-expiry-check")
async def run_expiry_check(db: asyncpg.Pool = Depends(_db)):
    """Admin — déclenche la suspension des essais expirés (appelable par cron)."""
    n = await db.fetchval("SELECT suspend_expired_trials()")
    return {"suspended_count": n}


# =============================================================================
# Distribution dynamique de configuration pour l'agent "coquille vide"
# =============================================================================

@router.get("/agent/config/{agent_id}")
async def get_agent_config(agent_id: str, request: Request, db: asyncpg.Pool = Depends(_db)):
    """
    Retourne la configuration de surveillance pour un agent donné.
    L'agent authentifie la requête avec son Bearer token.
    Signé par HMAC-SHA256 pour que l'agent vérifie l'intégrité.
    """
    import hmac as _hmac
    import hashlib
    import json

    # Récupération + vérification Bearer
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Bearer token manquant")
    token = auth.split(" ", 1)[1]

    row = await db.fetchrow(
        """
        SELECT
            a.id, a.tenant_id, a.hostname,
            a.hmac_key_hash,
            t.plan, t.suspended_at, t.max_agents, t.max_daily_events,
            t.trial_ends_at
        FROM agents a
        JOIN tenants t ON t.id = a.tenant_id
        WHERE a.id = $1 AND a.enroll_token_hash = encode(sha256($2::bytea), 'hex')
        """,
        agent_id, token,
    )
    if not row:
        raise HTTPException(401, "Agent ou token inconnu.")

    if row["suspended_at"]:
        raise HTTPException(402, detail={
            "code":    "TENANT_SUSPENDED",
            "message": "Abonnement suspendu. Contactez support@nexussoc.cm.",
        })

    # Config de surveillance : les watch_dirs sont récupérés depuis la table
    # des règles de surveillance (à enrichir selon les besoins du tenant)
    watch_dirs = await db.fetch(
        "SELECT path FROM agent_watch_dirs WHERE tenant_id = $1",
        row["tenant_id"],
    )
    if not watch_dirs:
        # Règles par défaut si le tenant n'a rien configuré
        default_dirs = (
            ["/etc", "/tmp", "/var/log", "/home"]
            if "linux" in (await db.fetchval(
                "SELECT os FROM agents WHERE id = $1", agent_id
            ) or "linux")
            else [r"C:\Windows\System32", r"C:\Users"]
        )
    else:
        default_dirs = [r["path"] for r in watch_dirs]

    cfg = {
        "agent_id":       agent_id,
        "tenant_id":      str(row["tenant_id"]),
        "interval_sec":   30,
        "watch_dirs":     default_dirs,
        "max_queue_mb":   50,
        "trial_active":   row["plan"] == "trial",
        "max_agents":     row["max_agents"],
        "max_daily_events": row["max_daily_events"],
        "config_version": "1",
        "issued_at":      datetime.now(timezone.utc).isoformat(),
    }

    # Signature HMAC de la config (l'agent vérifie avant d'appliquer)
    master = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION").encode()
    sig = _hmac.new(master, json.dumps(cfg, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    cfg["signature"] = sig

    return cfg


# =============================================================================
# Middleware de quota trial — importé et appelé par /ingest dans scoring-service
# =============================================================================

async def enforce_trial_quota(tenant_id: str, db: asyncpg.Pool) -> None:
    """
    Vérifie les quotas trial et incrémente le compteur d'événements.
    Lève HTTPException si le tenant est suspendu, expiré ou a dépassé ses quotas.
    À appeler au début du handler POST /ingest.
    """
    row = await db.fetchrow(
        """
        SELECT
            t.plan, t.suspended_at, t.trial_ends_at,
            t.max_agents, t.max_daily_events,
            COALESCE(q.agent_count, 0) AS agents_today,
            COALESCE(q.event_count, 0) AS events_today
        FROM tenants t
        LEFT JOIN trial_quotas q ON q.tenant_id = t.id AND q.date = CURRENT_DATE
        WHERE t.id = $1::uuid
        """,
        tenant_id,
    )
    if not row:
        return  # tenant inconnu : le handler principal gère l'erreur

    if row["suspended_at"] is not None:
        raise HTTPException(402, detail={
            "code":        "TENANT_SUSPENDED",
            "message":     "Ingestion suspendue. Renouvelez votre abonnement sur le portail.",
            "upgrade_url": "https://nexussoc.cm/upgrade",
        })

    if row["plan"] == "trial":
        if row["trial_ends_at"] and row["trial_ends_at"] < datetime.now(timezone.utc):
            raise HTTPException(402, detail={
                "code":        "TRIAL_EXPIRED",
                "message":     "Période d'essai terminée. Souscrivez un abonnement pour continuer.",
                "upgrade_url": "https://nexussoc.cm/upgrade",
            })

        if row["agents_today"] >= row["max_agents"]:
            raise HTTPException(429, detail={
                "code":        "AGENT_QUOTA_EXCEEDED",
                "message": (
                    f"Quota d'agents atteint ({row['max_agents']} max en essai). "
                    "Passez à un abonnement payant."
                ),
                "max_agents":  row["max_agents"],
                "upgrade_url": "https://nexussoc.cm/upgrade",
            })

        if row["events_today"] >= row["max_daily_events"]:
            raise HTTPException(429, detail={
                "code":        "DAILY_VOLUME_EXCEEDED",
                "message": (
                    f"Volume quotidien atteint ({row['max_daily_events']:,} événements/jour en essai). "
                    "Reprise demain ou souscrivez un abonnement."
                ),
                "limit":       row["max_daily_events"],
                "retry_after": "tomorrow",
                "upgrade_url": "https://nexussoc.cm/upgrade",
            })

        # Incrémenter le compteur d'événements
        await db.execute(
            """
            INSERT INTO trial_quotas (tenant_id, date, event_count)
            VALUES ($1::uuid, CURRENT_DATE, 1)
            ON CONFLICT (tenant_id, date)
            DO UPDATE SET event_count = trial_quotas.event_count + 1
            """,
            tenant_id,
        )


# =============================================================================
# Fonctions internes
# =============================================================================

async def _provision_tenant(db: asyncpg.Pool, reg) -> str:
    """Crée le tenant + l'utilisateur DSI initial et lie la registration."""
    trial_ends = datetime.now(timezone.utc) + timedelta(days=TRIAL_CFG["duration_days"])

    async with db.acquire() as conn:
        async with conn.transaction():
            tenant_id = await conn.fetchval(
                """
                INSERT INTO tenants
                    (name, type, plan, trial_ends_at, max_agents, max_daily_events)
                VALUES ($1, 'client', 'trial', $2, $3, $4)
                RETURNING id
                """,
                reg["organization_name"],
                trial_ends,
                TRIAL_CFG["max_agents"],
                TRIAL_CFG["max_daily_events"],
            )

            # Utilisateur DSI — mot de passe temporaire, changement forcé à la 1ère connexion
            temp_pwd = secrets.token_urlsafe(16)
            await conn.execute(
                """
                INSERT INTO users (tenant_id, email, role, password_hash)
                VALUES ($1, $2, 'dsi_client', encode(sha256($3::bytea), 'hex'))
                """,
                tenant_id, reg["email"], temp_pwd,
            )

            await conn.execute(
                "UPDATE plg_registrations SET tenant_id = $1 WHERE id = $2",
                tenant_id, reg["id"],
            )

    return tenant_id


async def _run_preauth(card_token: str) -> dict:
    """
    Pré-autorisation bancaire à 0 FCFA.

    Remplacer ce stub par l'intégration réelle :
    -------------------------------------------
    CinetPay (recommandé Cameroun) :
        POST https://api-checkout.cinetpay.com/v2/payment
        Headers: { "Content-Type": "application/json" }
        Body: { "apikey": CINETPAY_API_KEY, "site_id": ...,
                "transaction_id": unique_id, "amount": 0,
                "currency": "XAF", "card_token": card_token }

    PayDunya (alternative) :
        POST https://app.paydunya.com/api/v1/checkout-invoice/create
    -------------------------------------------
    """
    if not card_token or card_token.startswith("FAIL_"):
        return {"success": False, "message": "Carte refusée par la banque émettrice."}

    reference = f"NEXUS-PA-{secrets.token_hex(8).upper()}"
    return {"success": True, "reference": reference}


async def _send_verification_email(email: str, token: str, org_name: str = "") -> None:
    """
    Envoi de l'e-mail de vérification.
    Remplacer par SMTP (smtplib) ou API transactionnelle (SendGrid, MailerSend…).
    """
    verify_url = f"https://nexussoc.cm/verify?token={token}"
    logger.info(
        "PLG verify email | to=%s | org=%s | url=%s", email, org_name, verify_url
    )
    # Production : smtplib.SMTP(...).sendmail(...)


# =============================================================================
# Utilitaires
# =============================================================================

def _pct(value: int, total: int) -> int:
    if not total:
        return 0
    return round(min(value / total * 100, 100))
