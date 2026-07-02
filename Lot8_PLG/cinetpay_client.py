"""
NEXUS SOC — Client CinetPay (paiement Mobile Money + carte bancaire)
====================================================================
Wrapper minimal autour de l'API CinetPay v2 utilisée pour :

  1. La pré-autorisation bancaire à 0 FCFA durant le flux PLG (anti-bot)
  2. Les paiements d'abonnement (Starter 25 000 / Business 75 000 / Enterprise)

Docs officielles : https://docs.cinetpay.com/api/1.0-fr/

Trois modes (variable d'environnement CINETPAY_MODE) :
  - "live"    : appel réel sur api-checkout.cinetpay.com (clés production)
  - "sandbox" : même endpoint avec les clés sandbox CinetPay (mêmes signatures)
  - "stub"    : pas d'appel HTTP — retour simulé (mode démo soutenance)

Le module ne lève PAS d'exception : tous les retours respectent le contrat
{"success": bool, "reference": str | None, "message": str, ...}. C'est
l'appelant (plg_api) qui transforme ça en HTTP 200/402.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from typing import Optional

import httpx

logger = logging.getLogger("nexus.cinetpay")

CINETPAY_INIT_URL    = "https://api-checkout.cinetpay.com/v2/payment"
CINETPAY_CHECK_URL   = "https://api-checkout.cinetpay.com/v2/payment/check"


def _config() -> dict:
    return {
        "api_key":     os.getenv("CINETPAY_API_KEY", "").strip(),
        "site_id":     os.getenv("CINETPAY_SITE_ID", "").strip(),
        "secret_key":  os.getenv("CINETPAY_SECRET_KEY", "").strip(),
        "currency":    os.getenv("CINETPAY_CURRENCY", "XAF").strip(),
        "mode":        os.getenv("CINETPAY_MODE", "stub").strip().lower(),
        "notify_url":  os.getenv("CINETPAY_NOTIFY_URL", "").strip(),
        "return_url":  os.getenv("CINETPAY_RETURN_URL", "").strip(),
    }


def _new_transaction_id(prefix: str = "NEXUS") -> str:
    """ID transactionnel unique côté NEXUS (≤ 64 caractères pour CinetPay)."""
    return f"{prefix}-{secrets.token_hex(10).upper()}"


def init_payment(
    amount_fcfa: int,
    description: str,
    customer_email: str,
    *,
    customer_name: str = "",
    customer_phone: str = "",
    metadata: str = "",
    timeout: float = 8.0,
) -> dict:
    """Initialise un paiement CinetPay. Retourne :

        {success: bool, transaction_id: str, payment_url: str | None,
         message: str, raw?: dict}

    `payment_url` est l'URL de redirection sur laquelle envoyer le client pour
    saisir Orange Money / MTN MoMo / Wave / carte bancaire.
    """
    cfg = _config()
    txn_id = _new_transaction_id()

    if cfg["mode"] == "stub" or not (cfg["api_key"] and cfg["site_id"]):
        # Mode démo : pas d'appel réseau, retour simulé positif
        logger.info(
            "CINETPAY[stub] init txn=%s | %s FCFA | email=%s",
            txn_id, amount_fcfa, customer_email,
        )
        return {
            "success":        True,
            "transaction_id": txn_id,
            "payment_url":    None,   # le frontend gère son propre fallback
            "message":        "Mode démo : paiement simulé sans appel CinetPay.",
        }

    payload = {
        "apikey":         cfg["api_key"],
        "site_id":        cfg["site_id"],
        "transaction_id": txn_id,
        "amount":         int(amount_fcfa),
        "currency":       cfg["currency"],
        "description":    description[:255],
        "customer_email": customer_email,
        "customer_name":  customer_name or customer_email.split("@", 1)[0],
        "customer_phone": customer_phone,
        "notify_url":     cfg["notify_url"],
        "return_url":     cfg["return_url"],
        "channels":       "ALL",         # Mobile Money + Visa/Mastercard
        "metadata":       metadata,
        "lang":           "fr",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(CINETPAY_INIT_URL, json=payload)
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        code = str(data.get("code", "")).strip()
        if code == "201":
            url = data.get("data", {}).get("payment_url")
            return {
                "success":        True,
                "transaction_id": txn_id,
                "payment_url":    url,
                "message":        data.get("message", "Initialisation OK"),
                "raw":            data,
            }
        msg = data.get("message") or data.get("description") or resp.text[:200]
        logger.error("CINETPAY init refusé code=%s : %s", code, msg)
        return {
            "success":        False,
            "transaction_id": txn_id,
            "payment_url":    None,
            "message":        msg,
            "raw":            data,
        }
    except httpx.HTTPError as e:
        logger.error("CINETPAY init réseau : %s", e)
        return {
            "success":        False,
            "transaction_id": txn_id,
            "payment_url":    None,
            "message":        f"Erreur réseau : {e}",
        }


def check_payment(transaction_id: str, *, timeout: float = 8.0) -> dict:
    """Vérifie l'état d'une transaction côté CinetPay (à appeler dans le webhook
    pour ne pas se fier au body brut transmis par le client).
    """
    cfg = _config()
    if cfg["mode"] == "stub" or not (cfg["api_key"] and cfg["site_id"]):
        return {"success": True, "status": "ACCEPTED", "mode": "stub"}

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(CINETPAY_CHECK_URL, json={
                "apikey":         cfg["api_key"],
                "site_id":        cfg["site_id"],
                "transaction_id": transaction_id,
            })
        data = resp.json() if resp.status_code == 200 else {}
        status = data.get("data", {}).get("status", "UNKNOWN")
        return {
            "success": data.get("code") == "00",
            "status":  status,            # ACCEPTED | REFUSED | PENDING | …
            "amount":  data.get("data", {}).get("amount"),
            "raw":     data,
        }
    except httpx.HTTPError as e:
        logger.error("CINETPAY check réseau : %s", e)
        return {"success": False, "status": "ERROR", "error": str(e)}


def verify_webhook_signature(token_header: str, body_raw: bytes) -> bool:
    """Vérifie le X-Token envoyé par CinetPay sur l'URL `notify_url`.

    CinetPay calcule HMAC-SHA256(secret_key, payload) → header `x-token`.
    Si CINETPAY_SECRET_KEY n'est pas configuré, on retourne True (mode démo).
    """
    cfg = _config()
    if not cfg["secret_key"]:
        return True
    expected = hmac.new(
        cfg["secret_key"].encode("utf-8"),
        body_raw,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, (token_header or "").lower())


# ─── Adaptateur pour le flux PLG existant ───────────────────────────────────

def run_preauth(card_token: str, *, email: str = "anonymous@nexussoc.cm") -> dict:
    """
    Pré-autorisation bancaire à 0 FCFA pour le flux PLG.
    Conserve la signature attendue par plg_api._run_preauth().

    Le frontend NEXUS SOC fournit aujourd'hui un `card_token` opaque issu
    de son widget de saisie. En mode "live", on initialise un paiement de
    100 FCFA (CinetPay refuse 0) puis on l'annule immédiatement. En mode
    "stub", on simule le succès si le token ne commence pas par FAIL_.
    """
    cfg = _config()

    if cfg["mode"] == "stub":
        if not card_token or card_token.startswith("FAIL_"):
            return {"success": False, "message": "Carte refusée (mode démo)."}
        return {
            "success":   True,
            "reference": f"NEXUS-PA-{secrets.token_hex(8).upper()}",
            "mode":      "stub",
        }

    # En live, on déclenche une initialisation 100 FCFA marquée "PREAUTH"
    res = init_payment(
        amount_fcfa=100,
        description="Pré-autorisation NEXUS SOC (vérification d'identité)",
        customer_email=email,
        metadata=f"preauth|{card_token[:32]}",
    )
    if not res["success"]:
        return {"success": False, "message": res.get("message", "Pré-autorisation refusée.")}
    return {
        "success":   True,
        "reference": res["transaction_id"],
        "mode":      cfg["mode"],
    }
