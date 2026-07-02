"""
NEXUS SOC — Client VirusTotal (enrichissement IOC)
===================================================
Wrapper léger autour de l'API VirusTotal v3 pour récupérer le verdict
multi-antivirus d'un indicateur de compromission (IOC) :

  - IP publique          → /api/v3/ip_addresses/{ip}
  - Domaine              → /api/v3/domains/{domain}
  - Hash SHA-256/MD5     → /api/v3/files/{hash}
  - URL                  → /api/v3/urls/{base64(url)}

L'API publique gratuite est limitée à 4 requêtes/min et 500/jour. Le client
applique un **cache mémoire** (TTL configurable via VIRUSTOTAL_CACHE_HOURS)
pour éviter d'interroger plusieurs fois le même IOC dans la même journée.

Activation : VIRUSTOTAL_ENABLED=true + VIRUSTOTAL_API_KEY=<clé>
Sans clé, toutes les fonctions retournent un verdict "skipped" silencieusement,
afin que les playbooks SOAR fonctionnent en mode dégradé sans aucune erreur.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import time
from typing import Optional

import httpx

logger = logging.getLogger("nexus.virustotal")

VT_BASE = "https://www.virustotal.com/api/v3"

# Cache en mémoire { ioc_key: (verdict_dict, expires_at_epoch) }
_CACHE: dict = {}


# ─── Détection automatique du type d'IOC ────────────────────────────────────

_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_HASH = re.compile(r"^[a-fA-F0-9]+$")
_DOMAIN = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+$")


def _detect_type(ioc: str) -> str:
    ioc = ioc.strip()
    if _IPV4.match(ioc):
        return "ip"
    if ioc.startswith(("http://", "https://")):
        return "url"
    if _HASH.match(ioc) and len(ioc) in (32, 40, 64):
        return "hash"
    if _DOMAIN.match(ioc):
        return "domain"
    return "unknown"


def _config() -> dict:
    return {
        "api_key": os.getenv("VIRUSTOTAL_API_KEY", "").strip(),
        "enabled": os.getenv("VIRUSTOTAL_ENABLED", "false").lower() == "true",
        "cache_s": int(os.getenv("VIRUSTOTAL_CACHE_HOURS", "24")) * 3600,
    }


def _build_url(ioc: str, kind: str) -> Optional[str]:
    if kind == "ip":
        return f"{VT_BASE}/ip_addresses/{ioc}"
    if kind == "domain":
        return f"{VT_BASE}/domains/{ioc}"
    if kind == "hash":
        return f"{VT_BASE}/files/{ioc}"
    if kind == "url":
        # VirusTotal demande un id base64-url sans padding
        encoded = base64.urlsafe_b64encode(ioc.encode()).decode().rstrip("=")
        return f"{VT_BASE}/urls/{encoded}"
    return None


def _verdict_from_stats(stats: dict) -> tuple[str, int]:
    """Calcule un verdict synthétique à partir des compteurs VT."""
    malicious  = int(stats.get("malicious", 0))
    suspicious = int(stats.get("suspicious", 0))
    total      = sum(int(v) for v in stats.values() if isinstance(v, (int, float)))
    score      = malicious * 2 + suspicious  # pondération simple
    if malicious >= 5:
        return "malveillant", score
    if malicious >= 1:
        return "suspect", score
    if suspicious >= 2:
        return "suspect", score
    if total > 0:
        return "propre", 0
    return "inconnu", 0


def lookup(ioc: str, *, timeout: float = 8.0) -> dict:
    """Interroge VirusTotal pour un IOC. Retourne :

        {
          "ioc": str, "kind": str,
          "verdict": "malveillant" | "suspect" | "propre" | "inconnu" | "skipped",
          "malicious": int, "suspicious": int, "harmless": int,
          "report_url": str | None,
          "cached": bool,
          "error": str | None,
        }

    Ne lève PAS d'exception : un échec VT ne doit pas bloquer le SOAR.
    """
    cfg = _config()
    kind = _detect_type(ioc)
    base_result = {"ioc": ioc, "kind": kind, "verdict": "skipped",
                   "malicious": 0, "suspicious": 0, "harmless": 0,
                   "report_url": None, "cached": False, "error": None}

    if not cfg["enabled"]:
        base_result["error"] = "VIRUSTOTAL_ENABLED=false"
        return base_result
    if not cfg["api_key"]:
        base_result["error"] = "VIRUSTOTAL_API_KEY manquante"
        return base_result
    if kind == "unknown":
        base_result["error"] = "Type d'IOC non reconnu"
        return base_result

    # Cache
    now = time.time()
    cache_key = f"{kind}:{ioc}"
    if cache_key in _CACHE:
        cached, exp = _CACHE[cache_key]
        if now < exp:
            cached = dict(cached); cached["cached"] = True
            return cached

    url = _build_url(ioc, kind)
    if not url:
        base_result["error"] = "URL VT non construite"
        return base_result

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers={"x-apikey": cfg["api_key"]})
        if resp.status_code == 404:
            base_result["verdict"] = "inconnu"
            _CACHE[cache_key] = (base_result, now + cfg["cache_s"])
            return base_result
        if resp.status_code >= 400:
            base_result["error"] = f"HTTP {resp.status_code}"
            return base_result
        data = resp.json().get("data", {})
        stats = data.get("attributes", {}).get("last_analysis_stats", {}) or {}
        verdict, _score = _verdict_from_stats(stats)
        # URL publique du rapport (utile pour le DSI)
        if kind == "ip":
            report_url = f"https://www.virustotal.com/gui/ip-address/{ioc}"
        elif kind == "domain":
            report_url = f"https://www.virustotal.com/gui/domain/{ioc}"
        elif kind == "hash":
            report_url = f"https://www.virustotal.com/gui/file/{ioc}"
        else:
            encoded = base64.urlsafe_b64encode(ioc.encode()).decode().rstrip("=")
            report_url = f"https://www.virustotal.com/gui/url/{encoded}"

        result = {
            "ioc":        ioc,
            "kind":       kind,
            "verdict":    verdict,
            "malicious":  int(stats.get("malicious", 0)),
            "suspicious": int(stats.get("suspicious", 0)),
            "harmless":   int(stats.get("harmless", 0)),
            "report_url": report_url,
            "cached":     False,
            "error":      None,
        }
        _CACHE[cache_key] = (result, now + cfg["cache_s"])
        logger.info(
            "VT lookup | %s=%s | verdict=%s | mal=%d susp=%d",
            kind, ioc, verdict, result["malicious"], result["suspicious"],
        )
        return result

    except httpx.HTTPError as e:
        base_result["error"] = f"réseau : {e}"
        logger.error("VT erreur réseau pour %s : %s", ioc, e)
        return base_result


def lookup_alert_iocs(alert) -> list[dict]:
    """Extrait les IOC pertinents d'une alerte (entity + raisons) et les
    interroge tous. Retourne la liste des verdicts non-skipped.

    Heuristique simple : on regarde si l'entité ressemble à une IP ou un hash,
    et on cherche dans les raisons des chaînes du type "IP=1.2.3.4" ou des
    hash SHA-256.
    """
    candidates = set()
    if hasattr(alert, "entity") and alert.entity:
        if _detect_type(alert.entity) != "unknown":
            candidates.add(alert.entity)
    for r in getattr(alert, "reasons", []) or []:
        # Cherche des IP et hashes dans les raisons
        for m in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", str(r)):
            candidates.add(m)
        for m in re.findall(r"\b[a-fA-F0-9]{32,64}\b", str(r)):
            candidates.add(m)

    results = []
    for ioc in list(candidates)[:5]:  # limite à 5 IOC par alerte (rate-limit)
        v = lookup(ioc)
        if v["verdict"] != "skipped":
            results.append(v)
    return results
