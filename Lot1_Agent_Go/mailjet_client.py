"""
NEXUS SOC — Client Mailjet (e-mails transactionnels)
=====================================================
Petit wrapper synchrone autour de l'API Mailjet Send v3.1.

Trois modes (variable d'environnement MAILJET_MODE) :
  - "live"    : envoi réel via api.mailjet.com (auth Basic = APIKEY:SECRET)
  - "sandbox" : la requête est validée par Mailjet mais aucun e-mail n'est
                réellement délivré (SandboxMode=true dans le body)
  - "log"     : aucun appel HTTP ; on logge le destinataire et le contenu.
                Pratique en développement local quand on n'a pas de clé.

L'absence de clés API force automatiquement le mode "log" pour éviter de
faire échouer un déploiement par oubli de configuration.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("nexus.mailjet")

MAILJET_API_URL = "https://api.mailjet.com/v3.1/send"


def _config() -> dict:
    """Lit la configuration depuis l'environnement à chaque appel.

    Permet aux tests d'override via monkeypatch.setenv sans redémarrer le proc.
    """
    api_key    = os.getenv("MAILJET_API_KEY", "").strip()
    api_secret = os.getenv("MAILJET_API_SECRET", "").strip()
    mode       = os.getenv("MAILJET_MODE", "log").strip().lower()
    if mode == "live" and not (api_key and api_secret):
        logger.warning("MAILJET_MODE=live mais clés API absentes → fallback en mode 'log'")
        mode = "log"
    return {
        "api_key":    api_key,
        "api_secret": api_secret,
        "mode":       mode,
        "from_email": os.getenv("MAILJET_FROM_EMAIL", "no-reply@nexussoc.cm").strip(),
        "from_name":  os.getenv("MAILJET_FROM_NAME", "NEXUS SOC").strip(),
    }


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    *,
    to_name: str = "",
    reply_to: Optional[str] = None,
    timeout: float = 8.0,
) -> dict:
    """Envoi d'un e-mail. Retourne un dict {ok, mode, message_id?, error?}.

    Ne lève PAS d'exception : un échec d'e-mail ne doit pas casser une route
    métier. C'est l'appelant qui décide ce qu'il fait en cas de retour ok=False.
    """
    cfg = _config()

    message = {
        "From":     {"Email": cfg["from_email"], "Name": cfg["from_name"]},
        "To":       [{"Email": to_email, "Name": to_name or to_email.split("@", 1)[0]}],
        "Subject":  subject,
        "TextPart": text_body,
    }
    if html_body:
        message["HTMLPart"] = html_body
    if reply_to:
        message["ReplyTo"] = {"Email": reply_to}

    payload = {"Messages": [message]}
    if cfg["mode"] == "sandbox":
        payload["SandboxMode"] = True

    if cfg["mode"] == "log":
        logger.info(
            "MAILJET[log] to=%s | subject=%s | preview=%s",
            to_email, subject, text_body[:120].replace("\n", " "),
        )
        return {"ok": True, "mode": "log"}

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                MAILJET_API_URL,
                json=payload,
                auth=(cfg["api_key"], cfg["api_secret"]),
                headers={"Content-Type": "application/json"},
            )
        if resp.status_code >= 400:
            logger.error("MAILJET error %s : %s", resp.status_code, resp.text[:300])
            return {"ok": False, "mode": cfg["mode"], "error": resp.text[:300]}
        data = resp.json()
        msg_id = (
            data.get("Messages", [{}])[0]
                .get("To", [{}])[0]
                .get("MessageID")
        )
        logger.info("MAILJET[%s] envoyé à %s (id=%s)", cfg["mode"], to_email, msg_id)
        return {"ok": True, "mode": cfg["mode"], "message_id": msg_id}
    except httpx.HTTPError as e:
        logger.error("MAILJET réseau : %s", e)
        return {"ok": False, "mode": cfg["mode"], "error": str(e)}


# ─── Helpers métier ──────────────────────────────────────────────────────────

def send_otp_email(to_email: str, otp: str, purpose: str = "vérification") -> dict:
    """Envoie un OTP à 6 chiffres avec un template HTML lisible."""
    ttl_min = max(1, int(os.getenv("OTP_TTL_S", "300")) // 60)
    subject = f"NEXUS SOC — Code de {purpose} : {otp}"
    text = (
        f"Votre code de {purpose} NEXUS SOC est : {otp}\n\n"
        f"Ce code expire dans {ttl_min} minutes. Ne le partagez avec personne."
    )
    html = f"""<!DOCTYPE html><html lang="fr"><body style="font-family:system-ui,sans-serif;background:#0A0F1C;color:#E2E8F0;padding:32px;margin:0">
<div style="max-width:520px;margin:auto;background:#0F1729;border:1px solid #1E293B;border-radius:12px;padding:32px">
  <h2 style="color:#5EAAFF;margin:0 0 8px 0">NEXUS SOC</h2>
  <p style="color:#94A3B8;font-size:13px;margin:0 0 24px 0">Code de {purpose}</p>
  <div style="font-family:monospace;font-size:42px;letter-spacing:8px;font-weight:700;color:#5EAAFF;background:rgba(94,170,255,.08);padding:18px;text-align:center;border-radius:8px;border:1px solid rgba(94,170,255,.3)">{otp}</div>
  <p style="color:#94A3B8;font-size:14px;line-height:1.6;margin:24px 0 0 0">Ce code est valable <strong style="color:#E2E8F0">{ttl_min} minutes</strong>. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.</p>
  <p style="color:#64748B;font-size:11px;margin:32px 0 0 0;border-top:1px solid #1E293B;padding-top:16px">NEXUS SOC — Plateforme SOC souveraine pour le Cameroun</p>
</div></body></html>"""
    return send_email(to_email, subject, text, html_body=html)


def send_verification_email(to_email: str, verify_url: str, otp: str, org_name: str = "") -> dict:
    """E-mail combinant lien magique + code OTP pour la vérification PLG."""
    subject = "NEXUS SOC — Confirmez votre adresse pour activer l'essai gratuit"
    ttl_min = max(1, int(os.getenv("OTP_TTL_S", "300")) // 60)
    greeting = f"Bonjour {org_name}," if org_name else "Bonjour,"
    text = (
        f"{greeting}\n\n"
        f"Cliquez sur ce lien pour activer votre compte d'essai NEXUS SOC :\n"
        f"  {verify_url}\n\n"
        f"Ou saisissez ce code dans l'application : {otp}\n"
        f"(valable {ttl_min} minutes)\n\n"
        f"— L'équipe NEXUS SOC"
    )
    html = f"""<!DOCTYPE html><html lang="fr"><body style="font-family:system-ui,sans-serif;background:#0A0F1C;color:#E2E8F0;padding:32px;margin:0">
<div style="max-width:560px;margin:auto;background:#0F1729;border:1px solid #1E293B;border-radius:12px;padding:32px">
  <h2 style="color:#5EAAFF;margin:0 0 4px 0;font-family:Georgia,serif;font-style:italic">NEXUS SOC</h2>
  <p style="color:#94A3B8;font-size:13px;margin:0 0 24px 0">Activation de votre essai gratuit</p>
  <p style="color:#E2E8F0;line-height:1.6">{greeting} confirmez votre adresse pour finaliser l'inscription.</p>
  <p style="text-align:center;margin:28px 0">
    <a href="{verify_url}" style="background:#5EAAFF;color:#0A0F1C;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:700;display:inline-block">Activer mon compte</a>
  </p>
  <p style="color:#94A3B8;font-size:13px;text-align:center;margin:16px 0">— ou —</p>
  <p style="color:#94A3B8;font-size:13px;text-align:center;margin:0">Saisissez ce code dans l'application :</p>
  <div style="font-family:monospace;font-size:36px;letter-spacing:6px;font-weight:700;color:#5EAAFF;background:rgba(94,170,255,.08);padding:16px;text-align:center;border-radius:8px;border:1px solid rgba(94,170,255,.3);margin-top:8px">{otp}</div>
  <p style="color:#64748B;font-size:12px;line-height:1.6;margin:24px 0 0 0">Lien et code expirent dans {ttl_min} minutes. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.</p>
</div></body></html>"""
    return send_email(to_email, subject, text, html_body=html)
