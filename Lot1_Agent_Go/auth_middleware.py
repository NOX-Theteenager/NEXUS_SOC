#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Middleware d'authentification JWT
=============================================
Remplace la vérification simplifiée par mot de passe en base.
Fournit :
  - Génération de tokens JWT (access + refresh)
  - Validation avec expiration, type de token, rôle
  - Dépendances FastAPI : require_role("admin_plateforme") etc.
  - Endpoint /auth/token (login) et /auth/refresh

Intégration dans scoring-service_app.py :
    from auth_middleware import auth_router, require_role
    app.include_router(auth_router)
"""
import hashlib
import hmac
import json
import os
import time
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel

# ────────────────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────────────────
DB_DSN              = os.getenv("DB_DSN", "postgresql://nexus_app:nexus_pass@localhost:5432/nexus")
JWT_SECRET          = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_USE_32_RANDOM_BYTES")
ACCESS_TOKEN_TTL    = int(os.getenv("ACCESS_TOKEN_TTL_S",   str(15 * 60)))    # 15 min
REFRESH_TOKEN_TTL   = int(os.getenv("REFRESH_TOKEN_TTL_S",  str(7 * 86400)))  # 7 jours

# ────────────────────────────────────────────────────────────────────────────
# JWT maison (pas de dépendance PyJWT — HMAC-SHA256 + base64url)
# ────────────────────────────────────────────────────────────────────────────
import base64

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))

def _sign(header_b64: str, payload_b64: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(JWT_SECRET.encode(), msg, hashlib.sha256).digest()
    return _b64url_encode(sig)

def create_token(user_id: str, email: str, role: str, tenant_id: Optional[str], kind: str) -> str:
    """kind = 'access' | 'refresh'"""
    ttl = ACCESS_TOKEN_TTL if kind == "access" else REFRESH_TOKEN_TTL
    now = int(time.time())
    header  = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub":       user_id,
        "email":     email,
        "role":      role,
        "tenant_id": tenant_id,
        "kind":      kind,
        "iat":       now,
        "exp":       now + ttl,
    }).encode())
    sig = _sign(header, payload)
    return f"{header}.{payload}.{sig}"

def decode_token(token: str) -> dict:
    """Retourne le payload ou lève HTTPException."""
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token malformé")
    header_b64, payload_b64, sig_received = parts
    sig_expected = _sign(header_b64, payload_b64)
    if not hmac.compare_digest(sig_expected, sig_received):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Signature invalide")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Payload illisible")
    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expiré")
    return payload

# ────────────────────────────────────────────────────────────────────────────
# Dépendances FastAPI
# ────────────────────────────────────────────────────────────────────────────
def get_current_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token Bearer manquant")
    return decode_token(authorization.removeprefix("Bearer "))

def require_role(*roles: str):
    """Dépendance FastAPI qui vérifie que l'utilisateur a l'un des rôles donnés."""
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Rôle requis : {' ou '.join(roles)}. Rôle actuel : {user.get('role')}"
            )
        return user
    return _check

require_admin   = require_role("admin_plateforme", "analyste_soc")
require_analyst = require_role("admin_plateforme", "analyste_soc")
require_client  = require_role("admin_plateforme", "analyste_soc", "dsi_client", "lecteur")

# ────────────────────────────────────────────────────────────────────────────
# Endpoints d'authentification
# ────────────────────────────────────────────────────────────────────────────
auth_router = APIRouter(prefix="/auth", tags=["Authentification"])

class LoginRequest(BaseModel):
    email:    str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

def get_db():
    conn = psycopg2.connect(DB_DSN, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

@auth_router.post("/token", summary="Connexion — obtenir un access token + refresh token")
def login(body: LoginRequest, db=Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id::text, email, role, tenant_id::text "
            "FROM users WHERE email = %s AND mot_de_passe = crypt(%s, mot_de_passe) AND actif = TRUE",
            (body.email, body.password)
        )
        user = cur.fetchone()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Email ou mot de passe incorrect")

    uid = str(user["id"]); email = user["email"]
    role = user["role"]; tid = user["tenant_id"]

    access  = create_token(uid, email, role, tid, "access")
    refresh = create_token(uid, email, role, tid, "refresh")

    # Journaliser la connexion
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO enrollment_log (agent_id, tenant_id, succes, detail) "
                "SELECT id, %s, TRUE, %s FROM agents WHERE tenant_id = %s LIMIT 1",
                (tid, f"login:{email}", tid)
            )
            db.commit()
    except Exception:
        pass

    return {
        "access_token":  access,
        "refresh_token": refresh,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_TTL,
        "role":          role,
        "tenant_id":     tid,
    }

@auth_router.post("/refresh", summary="Renouveler l'access token via le refresh token")
def refresh_token(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload.get("kind") != "refresh":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ce n'est pas un refresh token")
    access = create_token(
        payload["sub"], payload["email"], payload["role"], payload.get("tenant_id"), "access"
    )
    return {"access_token": access, "token_type": "bearer", "expires_in": ACCESS_TOKEN_TTL}

@auth_router.get("/me", summary="Informations sur l'utilisateur connecté")
def me(user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Claims du JWT, enrichies du périmètre supervisé rattaché à l'utilisateur.

    Le JWT ne porte que `tenant_id` : le portail a besoin du nom lisible et de
    la criticité pour titrer ses écrans sans faire un appel /admin réservé aux
    rôles plateforme.
    """
    out = {k: v for k, v in user.items() if k not in ("iat", "exp", "kind")}
    tid = user.get("tenant_id")
    if tid:
        try:
            with db.cursor() as cur:
                cur.execute("SELECT nom, type, criticite FROM tenants WHERE id = %s::uuid", (tid,))
                row = cur.fetchone()
            if row:
                out["tenant_nom"]       = row["nom"]
                out["tenant_type"]      = row["type"]
                out["tenant_criticite"] = row["criticite"]
        except Exception:
            pass  # dégradé : le portail retombe sur un libellé neutre
    return out
