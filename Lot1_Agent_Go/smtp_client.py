"""
NEXUS SOC — Client SMTP (Gmail, Outlook, tout serveur SMTP standard)
=====================================================================
Alternative à Mailjet basée sur `smtplib` (stdlib Python — aucune dépendance).
Fonctionne avec :
  - Gmail (smtp.gmail.com:587, mot de passe d'application requis)
  - Outlook / Office 365 (smtp.office365.com:587)
  - OVH, Gandi, Zoho, etc.

Variables d'environnement lues :
  SMTP_HOST        (ex. smtp.gmail.com)
  SMTP_PORT        (587 = STARTTLS, 465 = SSL implicite, 25 = plain)
  SMTP_USER        (ex. nguetsajunior@gmail.com)
  SMTP_PASSWORD    (mot de passe d'application, PAS le mdp du compte)
  SMTP_FROM_EMAIL  (défaut = SMTP_USER)
  SMTP_FROM_NAME   (défaut = "NEXUS SOC")
  SMTP_MODE        live | log  (log = pas d'envoi réel, sortie stdout)
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from typing import Optional

logger = logging.getLogger("nexus.smtp")


def _config() -> dict:
    user = os.getenv("SMTP_USER", "").strip()
    return {
        "host":       os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        "port":       int(os.getenv("SMTP_PORT", "587")),
        "user":       user,
        "password":   os.getenv("SMTP_PASSWORD", "").replace(" ", ""),  # accepte "yjzt kjyd..."
        "from_email": os.getenv("SMTP_FROM_EMAIL", user).strip() or user,
        "from_name":  os.getenv("SMTP_FROM_NAME", "NEXUS SOC").strip(),
        "mode":       os.getenv("SMTP_MODE", "live" if user else "log").strip().lower(),
        "timeout":    int(os.getenv("SMTP_TIMEOUT_S", "15")),
    }


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    *,
    to_name: str = "",
    reply_to: Optional[str] = None,
) -> dict:
    """Envoi d'un e-mail via SMTP. Retourne {ok, mode, message_id?, error?}.
    Ne lève JAMAIS d'exception — un échec SMTP ne doit pas casser une route.
    """
    cfg = _config()

    if cfg["mode"] == "log" or not cfg["user"] or not cfg["password"]:
        logger.info(
            "SMTP[log] to=%s | subject=%s | preview=%s",
            to_email, subject, text_body[:120].replace("\n", " "),
        )
        return {"ok": True, "mode": "log"}

    msg = MIMEMultipart("alternative")
    msg["From"]       = formataddr((cfg["from_name"], cfg["from_email"]))
    msg["To"]         = formataddr((to_name or to_email.split("@", 1)[0], to_email))
    msg["Subject"]    = subject
    msg["Message-ID"] = make_msgid(domain=cfg["from_email"].split("@", 1)[-1])
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        if cfg["port"] == 465:
            server_cls = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=cfg["timeout"], context=ctx)
            server_cls.login(cfg["user"], cfg["password"])
            server_cls.send_message(msg)
            server_cls.quit()
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=cfg["timeout"]) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        logger.info("SMTP envoyé à %s via %s:%s", to_email, cfg["host"], cfg["port"])
        return {"ok": True, "mode": "live", "message_id": msg["Message-ID"]}
    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP auth échouée : %s", e)
        return {"ok": False, "mode": "live", "error": f"Auth SMTP refusée : {e.smtp_error.decode('utf-8', 'ignore') if hasattr(e, 'smtp_error') else e}"}
    except Exception as e:
        logger.error("SMTP erreur : %s", e)
        return {"ok": False, "mode": "live", "error": str(e)}


# ─── Helpers métier (mêmes signatures que mailjet_client) ────────────────────

def send_otp_email(to_email: str, otp: str, purpose: str = "vérification") -> dict:
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
