#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — API de Provisioning et d'Enrôlement (Lot 7)
=========================================================
Endpoints dédiés au cycle de vie complet des agents :
  - Génération de tokens avec expiration, usage unique et binding hostname
  - Génération de scripts d'installation Linux (.sh) et Windows (.ps1)
  - Génération de packs offline (.zip)
  - Génération de QR codes d'enrôlement
  - Provisioning en masse par import CSV
  - Statut du token et journal d'enrôlement

À intégrer dans scoring-service_app.py :
    from provisioning_api import router as prov_router
    app.include_router(prov_router)
"""

import csv
import hashlib
import io
import json
import os
import secrets
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

DB_DSN = os.getenv("DB_DSN", "postgresql://nexus_app:nexus_pass@localhost:5432/nexus")
NEXUS_SERVER_URL = os.getenv("NEXUS_SERVER_URL", "https://nexussoc.cm")
NEXUS_AGENT_VERSION = os.getenv("NEXUS_AGENT_VERSION", "1.0.0")
TEMPLATES_DIR = Path(__file__).parent / "install_templates"

router = APIRouter(prefix="/provision", tags=["Provisioning & Enrôlement"])


# ---------------------------------------------------------------------------
# DB + auth helpers
# ---------------------------------------------------------------------------
def get_db():
    conn = psycopg2.connect(DB_DSN, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


# --- Validation JWT unifiée (même schéma HS256 que auth_middleware.py) --------
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
    """Valide le JWT Bearer (admin_plateforme ou analyste_soc)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token manquant")
    payload = _decode_jwt(authorization.removeprefix("Bearer "))
    if payload.get("role") not in ("admin_plateforme", "analyste_soc"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Rôle insuffisant")
    return payload


# ---------------------------------------------------------------------------
# Schémas Pydantic
# ---------------------------------------------------------------------------
class TokenRequest(BaseModel):
    tenant_id:       str
    hostname:        str
    os:              str = "linux"          # linux | windows | auto
    expires_in_hours: int = 24              # 1 | 24 | 168 (7 jours)
    one_time:        bool = True            # invalidé après premier enrôlement
    bind_hostname:   bool = True            # token valide uniquement pour ce hostname


class BulkRow(BaseModel):
    hostname:    str
    os:          str = "linux"
    description: str = ""


# ---------------------------------------------------------------------------
# A. Génération de token avec cycle de vie
# ---------------------------------------------------------------------------
@router.post("/token", status_code=201, summary="Générer un token d'enrôlement avec cycle de vie")
def generate_token(body: TokenRequest, db=Depends(get_db), _=Depends(require_admin)):
    bearer_token = f"nexus_{secrets.token_urlsafe(32)}"
    hmac_key     = secrets.token_hex(32)
    token_hash   = hashlib.sha256(bearer_token.encode()).hexdigest()
    hmac_hash    = hashlib.sha256(hmac_key.encode()).hexdigest()
    expires_at   = datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)
    binding      = body.hostname if body.bind_hostname else None

    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO agents (tenant_id, hostname, os, statut,
                                   token_hash, hmac_key_hash,
                                   token_expires_at, token_one_time, token_binding_host)
               VALUES (%s, %s, %s, 'hors_ligne', %s, %s, %s, %s, %s)
               RETURNING id""",
            (body.tenant_id, body.hostname, body.os,
             token_hash, hmac_hash, expires_at, body.one_time, binding)
        )
        agent_id = str(cur.fetchone()["id"])
        db.commit()

    # Payload QR code : JSON compact pour le scanner
    qr_payload = json.dumps({
        "s": NEXUS_SERVER_URL,
        "t": bearer_token,
        "h": hmac_key,
        "a": agent_id,
        "n": body.tenant_id,
        "e": expires_at.isoformat(),
    }, separators=(',', ':'))

    return {
        "agent_id":      agent_id,
        "bearer_token":  bearer_token,
        "hmac_key":      hmac_key,
        "expires_at":    expires_at.isoformat(),
        "expires_in_h":  body.expires_in_hours,
        "one_time":      body.one_time,
        "bind_hostname": binding,
        "qr_payload":    qr_payload,
        "warning":       "Ces valeurs ne sont affichées qu'une seule fois.",
    }


# ---------------------------------------------------------------------------
# B. Vérification du token à l'enrôlement (appelée par l'agent Go)
# ---------------------------------------------------------------------------
@router.post("/enroll", summary="Valider un token et enregistrer l'enrôlement")
def enroll_agent(
    authorization: str = Header(...),
    x_agent_hostname: Optional[str] = Header(None),
    x_agent_version:  Optional[str] = Header(None),
    x_forwarded_for:  Optional[str] = Header(None),
    db=Depends(get_db),
):
    """
    Appelé par l'agent Go lors de son premier contact.
    Vérifie le token, applique les règles (usage unique, binding, expiration).
    Retourne la config définitive de l'agent.
    """
    if not authorization.startswith("Bearer nexus_"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token invalide")

    token = authorization.removeprefix("Bearer ")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    ip_source  = (x_forwarded_for or "").split(",")[0].strip() or "unknown"

    with db.cursor() as cur:
        cur.execute(
            """SELECT id, tenant_id, hostname, statut, token_used_at,
                      token_expires_at, token_one_time, token_binding_host
               FROM agents WHERE token_hash = %s""",
            (token_hash,)
        )
        agent = cur.fetchone()

    if not agent:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inconnu")

    # Règle 1 : usage unique déjà utilisé
    if agent["token_one_time"] and agent["token_used_at"]:
        _log_enrollment(db, agent["id"], agent["tenant_id"], ip_source,
                        x_agent_version, False, "Token déjà utilisé")
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Token déjà utilisé")

    # Règle 2 : token expiré
    if agent["token_expires_at"] and datetime.now(timezone.utc) > agent["token_expires_at"].replace(tzinfo=timezone.utc):
        _log_enrollment(db, agent["id"], agent["tenant_id"], ip_source,
                        x_agent_version, False, "Token expiré")
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Token expiré")

    # Règle 3 : binding hostname
    if agent["token_binding_host"] and x_agent_hostname:
        if x_agent_hostname.upper() != agent["token_binding_host"].upper():
            _log_enrollment(db, agent["id"], agent["tenant_id"], ip_source,
                            x_agent_version, False,
                            f"Hostname interdit : {x_agent_hostname}")
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail=f"Token lié à {agent['token_binding_host']}")

    # Marquer comme utilisé
    now = datetime.now(timezone.utc)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE agents SET token_used_at=%s, token_used_by_ip=%s, statut='actif', "
            "version_agent=%s, vu_le=%s WHERE id=%s",
            (now, ip_source, x_agent_version, now, agent["id"])
        )
        db.commit()

    _log_enrollment(db, agent["id"], agent["tenant_id"], ip_source,
                    x_agent_version, True, "Enrôlement réussi")

    return {
        "agent_id":    str(agent["id"]),
        "tenant_id":   str(agent["tenant_id"]),
        "hostname":    agent["hostname"],
        "enrolled_at": now.isoformat(),
        "config": {
            "ingest_url":    f"{NEXUS_SERVER_URL}/ingest",
            "interval_sec":  30,
            "queue_max_mb":  50,
        }
    }


def _log_enrollment(db, agent_id, tenant_id, ip, version, succes, detail):
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO enrollment_log (agent_id, tenant_id, ip_source, version, succes, detail) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (agent_id, tenant_id, ip, version, succes, detail)
            )
            db.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# C. Génération de script d'installation
# ---------------------------------------------------------------------------
def _load_template(filename: str) -> str:
    tpl = TEMPLATES_DIR / filename
    if tpl.exists():
        return tpl.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Template introuvable : {tpl}")


def _build_linux_script(agent_id: str, bearer: str, hmac: str,
                         tenant_id: str, hostname: str) -> str:
    tpl = _load_template("install_linux.sh")
    return (tpl
            .replace("{{SERVER_URL}}",    NEXUS_SERVER_URL)
            .replace("{{BEARER_TOKEN}}", bearer)
            .replace("{{HMAC_KEY}}",     hmac)
            .replace("{{TENANT_ID}}",    tenant_id)
            .replace("{{AGENT_ID}}",     agent_id)
            .replace("{{HOSTNAME}}",     hostname)
            .replace("{{VERSION}}",      NEXUS_AGENT_VERSION)
            .replace("{{DATE}}",         datetime.now().strftime("%Y-%m-%d %H:%M")))


def _build_windows_script(agent_id: str, bearer: str, hmac: str,
                            tenant_id: str, hostname: str) -> str:
    tpl = _load_template("install_windows.ps1")
    return (tpl
            .replace("{{SERVER_URL}}",    NEXUS_SERVER_URL)
            .replace("{{BEARER_TOKEN}}", bearer)
            .replace("{{HMAC_KEY}}",     hmac)
            .replace("{{TENANT_ID}}",    tenant_id)
            .replace("{{AGENT_ID}}",     agent_id)
            .replace("{{HOSTNAME}}",     hostname)
            .replace("{{VERSION}}",      NEXUS_AGENT_VERSION)
            .replace("{{DATE}}",         datetime.now().strftime("%Y-%m-%d %H:%M")))


@router.get("/installer/{agent_id}", summary="Télécharger le script d'installation")
def get_installer(
    agent_id: str,
    os: str = "linux",           # linux | windows
    bearer: str = "",
    hmac: str = "",
    db=Depends(get_db),
    _=Depends(require_admin),
):
    """
    Retourne le script d'installation prêt à l'emploi pour cet agent.
    Les paramètres `bearer` et `hmac` sont passés en query string (car secrets
    générés une seule fois — le front les a déjà, il les repasse ici).
    """
    with db.cursor() as cur:
        cur.execute("SELECT tenant_id, hostname, os FROM agents WHERE id = %s", (agent_id,))
        agent = cur.fetchone()
    if not agent:
        raise HTTPException(404, detail="Agent introuvable")

    os_target = os or agent["os"] or "linux"
    tenant_id = str(agent["tenant_id"])
    hostname  = agent["hostname"]

    if os_target == "windows":
        content  = _build_windows_script(agent_id, bearer, hmac, tenant_id, hostname)
        filename = f"Install-NexusAgent_{hostname}.ps1"
        media    = "text/plain"
    else:
        content  = _build_linux_script(agent_id, bearer, hmac, tenant_id, hostname)
        filename = f"install_nexus_{hostname.lower()}.sh"
        media    = "text/x-shellscript"

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# D. Pack offline (.zip)
# ---------------------------------------------------------------------------
@router.get("/offline-pack/{agent_id}", summary="Télécharger le pack offline complet (.zip)")
def get_offline_pack(
    agent_id: str,
    bearer: str = "",
    hmac: str = "",
    os: str = "linux",
    db=Depends(get_db),
    _=Depends(require_admin),
):
    with db.cursor() as cur:
        cur.execute(
            "SELECT a.tenant_id, a.hostname, a.os, t.nom AS tenant_nom "
            "FROM agents a JOIN tenants t ON t.id = a.tenant_id WHERE a.id = %s",
            (agent_id,)
        )
        agent = cur.fetchone()
    if not agent:
        raise HTTPException(404, detail="Agent introuvable")

    tenant_id  = str(agent["tenant_id"])
    hostname   = agent["hostname"]
    os_target  = os or agent["os"] or "linux"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # config.json
        config = {
            "server_url":   f"{NEXUS_SERVER_URL}/ingest",
            "enroll_token": bearer,
            "hmac_key":     hmac,
            "agent_id":     agent_id,
            "tenant_id":    tenant_id,
            "hostname":     hostname,
            "interval_sec": 30,
            "watch_dirs":   ["/home", "/tmp", "/var/log"] if os_target == "linux"
                            else ["%USERPROFILE%", "%TEMP%"],
            "queue_dir":    "./queue",
            "queue_max_mb": 50,
            "tls_verify":   True,
        }
        zf.writestr("config.json", json.dumps(config, indent=2, ensure_ascii=False))

        # Script d'installation
        if os_target == "windows":
            script   = _build_windows_script(agent_id, bearer, hmac, tenant_id, hostname)
            zf.writestr("install.ps1", script)
        else:
            script   = _build_linux_script(agent_id, bearer, hmac, tenant_id, hostname)
            zf.writestr("install.sh", script)

        # Unité systemd (Linux seulement)
        if os_target == "linux":
            svc = _load_template("nexusagent.service")
            zf.writestr("nexusagent.service", svc)

        # README
        readme = f"""NEXUS SOC — Pack d'installation offline
Tenant   : {agent['tenant_nom']}
Hostname : {hostname}
OS cible : {os_target}
Généré   : {datetime.now().strftime('%Y-%m-%d %H:%M')}

INSTRUCTIONS
============
1. Copier ce dossier sur le poste cible (clé USB ou partage réseau)
2. Déposer le binaire nexusagent (ou nexusagent.exe) dans ce même dossier
   → Télécharger depuis : {NEXUS_SERVER_URL}/agent/download/{NEXUS_AGENT_VERSION}/{os_target}/amd64/

Linux :
  sudo bash install.sh

Windows (PowerShell Administrateur) :
  Set-ExecutionPolicy Bypass -Scope Process -Force
  .\\install.ps1

⚠ Ce token est à usage unique. Ne pas partager config.json.
"""
        zf.writestr("README_INSTALLATION.txt", readme)

    buf.seek(0)
    zipname = f"nexus-agent-{hostname.lower()}-{os_target}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zipname}"'},
    )


# ---------------------------------------------------------------------------
# E. QR code d'enrôlement
# ---------------------------------------------------------------------------
@router.get("/qr/{agent_id}", summary="Générer le QR code d'enrôlement (PNG base64)")
def get_qr_code(
    agent_id: str,
    bearer: str = "",
    db=Depends(get_db),
    _=Depends(require_admin),
):
    """
    Retourne un QR code PNG encodé en base64.
    Le QR encode le one-liner curl d'installation pour ce poste spécifique.
    """
    with db.cursor() as cur:
        cur.execute("SELECT tenant_id, hostname, os FROM agents WHERE id = %s", (agent_id,))
        agent = cur.fetchone()
    if not agent:
        raise HTTPException(404, detail="Agent introuvable")

    os_target = agent["os"] or "linux"
    hostname  = agent["hostname"]

    if os_target == "windows":
        oneliner = (
            f"irm {NEXUS_SERVER_URL}/install.ps1 | iex "
            f"-Token \"{bearer}\" -Hostname \"{hostname}\""
        )
    else:
        oneliner = (
            f"curl -fsSL {NEXUS_SERVER_URL}/install | "
            f"NEXUS_TOKEN={bearer} NEXUS_HOSTNAME={hostname} bash"
        )

    try:
        import qrcode
        import qrcode.image.pure
        import base64

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=3,
        )
        qr.add_data(oneliner)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_b64 = base64.b64encode(buf.getvalue()).decode()

        return {
            "qr_png_b64":   png_b64,
            "payload_text": oneliner,
            "hostname":     hostname,
            "os":           os_target,
        }
    except ImportError:
        # qrcode non installé : retourner juste le texte
        return {
            "qr_png_b64":   None,
            "payload_text": oneliner,
            "message":      "Installer 'qrcode[pil]' pour obtenir l'image : pip install qrcode[pil]",
        }


# ---------------------------------------------------------------------------
# F. Statut du token
# ---------------------------------------------------------------------------
@router.get("/status/{agent_id}", summary="Statut du token d'enrôlement")
def token_status(agent_id: str, db=Depends(get_db), _=Depends(require_admin)):
    with db.cursor() as cur:
        cur.execute(
            """SELECT token_statut, token_expires_at, token_used_at,
                      token_used_by_ip, token_ttl_seconds, hostname, statut
               FROM v_agent_token_status WHERE id = %s""",
            (agent_id,)
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, detail="Agent introuvable")
    return dict(row)


@router.get("/status/{agent_id}/log", summary="Journal des enrôlements d'un agent")
def enrollment_log(agent_id: str, db=Depends(get_db), _=Depends(require_admin)):
    with db.cursor() as cur:
        cur.execute(
            "SELECT horodatage, ip_source, version, succes, detail "
            "FROM enrollment_log WHERE agent_id = %s ORDER BY horodatage DESC LIMIT 50",
            (agent_id,)
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# G. Provisioning en masse (import CSV)
# ---------------------------------------------------------------------------
@router.post("/bulk", status_code=201, summary="Provisionner plusieurs agents depuis un CSV")
async def bulk_provision(
    tenant_id:        str,
    expires_in_hours: int = 24,
    file: UploadFile = File(...),
    db=Depends(get_db),
    user=Depends(require_admin),
):
    """
    CSV attendu (avec en-tête) :
    hostname,os,description
    POSTE-COMPTA-01,windows,Service comptabilité
    SRV-BUDGET-02,linux,Serveur budgétaire

    Retourne la liste des agents créés avec leurs tokens (une seule fois).
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # gère le BOM des exports Excel
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    required_cols = {"hostname"}
    if not required_cols.issubset({c.strip().lower() for c in (reader.fieldnames or [])}):
        raise HTTPException(400, detail="Le CSV doit contenir au moins la colonne 'hostname'.")

    created  = []
    errors   = []
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

    for i, row in enumerate(reader, start=2):
        hostname = (row.get("hostname") or row.get("Hostname") or "").strip()
        os_val   = (row.get("os") or row.get("OS") or "linux").strip().lower()
        if not hostname:
            errors.append({"ligne": i, "erreur": "hostname vide"})
            continue
        if os_val not in ("linux", "windows", "auto", "unknown"):
            os_val = "linux"

        bearer_token = f"nexus_{secrets.token_urlsafe(32)}"
        hmac_key     = secrets.token_hex(32)
        token_hash   = hashlib.sha256(bearer_token.encode()).hexdigest()
        hmac_hash    = hashlib.sha256(hmac_key.encode()).hexdigest()

        try:
            with db.cursor() as cur:
                cur.execute(
                    """INSERT INTO agents (tenant_id, hostname, os, statut,
                                          token_hash, hmac_key_hash,
                                          token_expires_at, token_one_time, token_binding_host)
                       VALUES (%s, %s, %s, 'hors_ligne', %s, %s, %s, TRUE, %s)
                       RETURNING id""",
                    (tenant_id, hostname, os_val,
                     token_hash, hmac_hash, expires_at, hostname)
                )
                agent_id = str(cur.fetchone()["id"])
                db.commit()

            oneliner_linux = (
                f"curl -fsSL {NEXUS_SERVER_URL}/install | "
                f"NEXUS_TOKEN={bearer_token} NEXUS_HOSTNAME={hostname} bash"
            )
            oneliner_win = (
                f"irm {NEXUS_SERVER_URL}/install.ps1 | iex "
                f"-Token \"{bearer_token}\" -Hostname \"{hostname}\""
            )
            created.append({
                "agent_id":        agent_id,
                "hostname":        hostname,
                "os":              os_val,
                "bearer_token":    bearer_token,
                "hmac_key":        hmac_key,
                "expires_at":      expires_at.isoformat(),
                "oneliner_linux":  oneliner_linux,
                "oneliner_windows": oneliner_win,
            })
        except Exception as e:
            db.rollback()
            errors.append({"ligne": i, "hostname": hostname, "erreur": str(e)})

    # Enregistrement de l'opération de masse
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO bulk_provisioning (tenant_id, initiateur, nb_agents, statut, detail) "
            "VALUES (%s, %s, %s, 'termine', %s)",
            (tenant_id, user.get("email", "admin"),
             len(created), json.dumps({"created": len(created), "errors": len(errors)}))
        )
        db.commit()

    return {
        "created":        created,
        "errors":         errors,
        "total_created":  len(created),
        "total_errors":   len(errors),
        "expires_at":     expires_at.isoformat(),
        "warning":        "Les tokens ne sont affichés qu'une seule fois dans cette réponse.",
    }


# ---------------------------------------------------------------------------
# H. One-liner dynamique (appelé par le script curl | bash)
# ---------------------------------------------------------------------------
@router.get("/oneliner", summary="Script shell généré dynamiquement depuis les variables d'env")
def dynamic_installer(
    token: str,
    hostname: str,
    os: str = "linux",
):
    """
    Point d'entrée du one-liner :
      curl -fsSL https://nexussoc.cm/provision/oneliner?token=xxx&hostname=yyy | bash
    Génère et retourne le script inline, sans authentification admin
    (le token est validé à l'enrôlement par /provision/enroll).
    """
    # Validation minimale du format du token
    if not token.startswith("nexus_") or len(token) < 20:
        raise HTTPException(400, detail="Format de token invalide")

    if os == "windows":
        content = _build_windows_script(
            agent_id="__dynamic__", bearer=token, hmac="__see_enroll__",
            tenant_id="__dynamic__", hostname=hostname
        )
        media = "text/plain"
    else:
        content = _build_linux_script(
            agent_id="__dynamic__", bearer=token, hmac="__see_enroll__",
            tenant_id="__dynamic__", hostname=hostname
        )
        media = "text/x-shellscript"

    return StreamingResponse(io.BytesIO(content.encode("utf-8")), media_type=media)


# ---------------------------------------------------------------------------
# I. Rotation de la clé HMAC d'un agent (invalidation + nouvelle clé)
# ---------------------------------------------------------------------------
@router.post("/rotate-hmac/{agent_id}", status_code=201,
             summary="Rotation de la clé HMAC-SHA256 d'un agent")
def rotate_hmac(agent_id: str, db=Depends(get_db), _=Depends(require_admin)):
    """
    Génère une nouvelle clé HMAC pour l'agent et invalide l'ancienne.
    L'agent doit être mis à jour manuellement (re-déploiement du config.json)
    ou via un endpoint de re-configuration si le canal sécurisé est disponible.
    Retourne la nouvelle clé une seule fois.
    """
    new_hmac_key  = secrets.token_hex(32)
    new_hmac_hash = hashlib.sha256(new_hmac_key.encode()).hexdigest()

    with db.cursor() as cur:
        cur.execute(
            "UPDATE agents SET hmac_key_hash = %s WHERE id = %s RETURNING hostname, tenant_id",
            (new_hmac_hash, agent_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, detail="Agent introuvable")
        db.commit()

    return {
        "agent_id":     agent_id,
        "hostname":     row["hostname"],
        "new_hmac_key": new_hmac_key,
        "warning":      "Nouvelle clé HMAC affichée une seule fois. Mettre à jour config.json sur le poste.",
        "next_step":    f"Redéployer la configuration : POST /provision/installer/{agent_id}?os=linux",
    }


# ---------------------------------------------------------------------------
# I-bis. Révoquer un seul agent (par son id)
# ---------------------------------------------------------------------------
@router.post("/revoke/{agent_id}", summary="Révoquer le token d'un agent précis")
def revoke_agent_token(agent_id: str, db=Depends(get_db), _=Depends(require_admin)):
    """Coupe l'authentification d'un agent : token marqué utilisé + statut hors ligne."""
    now = datetime.now(timezone.utc)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE agents SET token_used_at = %s, statut = 'hors_ligne' "
            "WHERE id = %s RETURNING id",
            (now, agent_id)
        )
        row = cur.fetchone()
        db.commit()
    if not row:
        raise HTTPException(404, detail="Agent introuvable")
    return {"agent_id": agent_id, "revoked_at": now.isoformat(), "message": "Agent révoqué."}


# J. Révoquer tous les tokens d'un tenant (urgence — incident en cours)
# ---------------------------------------------------------------------------
@router.post("/revoke-tenant/{tenant_id}",
             summary="Révoquer tous les tokens actifs d'un tenant (urgence)")
def revoke_tenant_tokens(tenant_id: str, db=Depends(get_db), _=Depends(require_admin)):
    """
    Marque tous les tokens du tenant comme utilisés (expirés de fait).
    Utilisé en cas d'incident de sécurité : couper immédiatement tous les agents.
    Les agents continueront à fonctionner localement mais ne pourront plus s'authentifier.
    """
    now = datetime.now(timezone.utc)
    with db.cursor() as cur:
        cur.execute(
            """UPDATE agents
               SET token_used_at = %s, statut = 'hors_ligne'
               WHERE tenant_id = %s AND token_used_at IS NULL""",
            (now, tenant_id)
        )
        revoked = cur.rowcount
        db.commit()
    return {
        "tenant_id":     tenant_id,
        "agents_revoked": revoked,
        "revoked_at":    now.isoformat(),
        "message":       f"{revoked} agents révoqués. Ils nécessitent un re-enrôlement.",
    }
