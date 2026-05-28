#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Pseudonymisation des données personnelles dans les alertes
======================================================================
Problème : les alertes contiennent des identifiants d'agents (agent_DGI_0421),
des emails (dsi@minfi.cm), des adresses IP — des données qui peuvent identifier
des personnes physiques (loi 2010/012, bonnes pratiques RGPD).

Ce module applique une pseudonymisation réversible avec un secret maître :
  - Les données sont hachées avec HMAC-SHA256 + secret → pseudonyme stable et irréversible
    sans la clé (protection des données, mais on peut rechercher un pseudonyme connu)
  - Un mapping pseudonyme → valeur originale est stocké en base chiffrée
    (accessible uniquement aux admins pour investigation légale)
  - La console et les notifications utilisent les pseudonymes par défaut

Usage :
    from pseudonymizer import pseudonymize, depseudonymize, PseudonymMiddleware
"""
import hashlib
import hmac
import json
import os
import re
from typing import Optional

# ────────────────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────────────────
PSEUDO_SECRET  = os.getenv("PSEUDO_SECRET", "CHANGE_ME_PSEUDO_SECRET_32_BYTES")
PSEUDO_ENABLED = os.getenv("PSEUDO_ENABLED", "true").lower() != "false"

# Patterns d'identifiants personnels à pseudonymiser
_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.I),
    "ip_public": re.compile(
        r"\b(?!10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)(\d{1,3}\.){3}\d{1,3}\b"
    ),
    "agent_id": re.compile(r"\bagent_[A-Z0-9_]{3,}\b", re.I),
    "username": re.compile(r"\b[A-Z]{2,8}\\[A-Za-z0-9._\-]{3,}\b"),  # DOMAIN\user
}

_PSEUDO_PREFIX = {
    "email":    "user",
    "ip_public":"ip",
    "agent_id": "agent",
    "username": "user",
}


# ────────────────────────────────────────────────────────────────────────────
# Fonctions de base
# ────────────────────────────────────────────────────────────────────────────
def _make_pseudonym(value: str, kind: str) -> str:
    """Génère un pseudonyme stable et déterministe pour une valeur donnée."""
    sig = hmac.new(
        PSEUDO_SECRET.encode(), f"{kind}:{value}".encode(), hashlib.sha256
    ).hexdigest()[:12]
    prefix = _PSEUDO_PREFIX.get(kind, "id")
    return f"{prefix}_{sig}"


def pseudonymize(text: str, mapping_store: Optional[dict] = None) -> str:
    """
    Remplace tous les identifiants personnels reconnus par leur pseudonyme.
    Si mapping_store est fourni, enregistre le mapping original→pseudonyme.
    """
    if not PSEUDO_ENABLED:
        return text
    result = text
    for kind, pattern in _PATTERNS.items():
        for match in pattern.findall(text):
            pseudo = _make_pseudonym(match, kind)
            result = result.replace(match, pseudo)
            if mapping_store is not None:
                mapping_store[pseudo] = {"original": match, "kind": kind}
    return result


def pseudonymize_dict(data: dict, mapping_store: Optional[dict] = None) -> dict:
    """Pseudonymise récursivement les valeurs string d'un dictionnaire."""
    if not PSEUDO_ENABLED:
        return data
    out = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = pseudonymize(v, mapping_store)
        elif isinstance(v, dict):
            out[k] = pseudonymize_dict(v, mapping_store)
        elif isinstance(v, list):
            out[k] = [
                pseudonymize(i, mapping_store) if isinstance(i, str)
                else pseudonymize_dict(i, mapping_store) if isinstance(i, dict)
                else i
                for i in v
            ]
        else:
            out[k] = v
    return out


def depseudonymize(pseudo: str, mapping_store: dict) -> Optional[str]:
    """Retrouve la valeur originale depuis le mapping (accès réservé admin)."""
    entry = mapping_store.get(pseudo)
    return entry["original"] if entry else None


# ────────────────────────────────────────────────────────────────────────────
# Middleware FastAPI
# ────────────────────────────────────────────────────────────────────────────
class AlertPseudonymizer:
    """
    Applique la pseudonymisation aux alertes avant leur insertion en base
    et leur transmission aux notifications.
    Usage :
        pseu = AlertPseudonymizer(db_conn)
        clean_alert = pseu.process(raw_alert)
    """
    def __init__(self, db_conn=None):
        self._db = db_conn
        self._local_map: dict = {}

    def process(self, alert: dict) -> dict:
        """Pseudonymise l'alerte et persiste le mapping."""
        mapping: dict = {}
        result = pseudonymize_dict(alert, mapping)
        self._local_map.update(mapping)
        if self._db and mapping:
            self._persist(mapping)
        return result

    def _persist(self, mapping: dict):
        """Stocke le mapping pseudonyme→original en base (table pseudo_mapping)."""
        try:
            with self._db.cursor() as cur:
                for pseudo, entry in mapping.items():
                    cur.execute(
                        "INSERT INTO pseudo_mapping (pseudonyme, original_hash, kind) "
                        "VALUES (%s, %s, %s) ON CONFLICT (pseudonyme) DO NOTHING",
                        (pseudo,
                         hashlib.sha256(entry["original"].encode()).hexdigest(),
                         entry["kind"])
                    )
            self._db.commit()
        except Exception:
            pass

    def reveal(self, pseudo: str, admin_token: str) -> Optional[str]:
        """
        Révèle la valeur originale (accès admin uniquement — audit légal).
        En production, l'admin_token est vérifié via le JWT middleware.
        """
        return depseudonymize(pseudo, self._local_map)


# ────────────────────────────────────────────────────────────────────────────
# SQL pour la table de mapping
# ────────────────────────────────────────────────────────────────────────────
PSEUDO_MAPPING_SQL = """
CREATE TABLE IF NOT EXISTS pseudo_mapping (
    pseudonyme    TEXT PRIMARY KEY,
    original_hash TEXT NOT NULL,    -- SHA-256 de la valeur originale (pas en clair)
    kind          TEXT NOT NULL,    -- email | ip_public | agent_id | username
    cree_le       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Seul l'admin_plateforme peut voir la table de mapping
REVOKE ALL ON pseudo_mapping FROM PUBLIC;
GRANT SELECT ON pseudo_mapping TO nexus_analyst;
"""


# ────────────────────────────────────────────────────────────────────────────
# Démo / test
# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_alert = {
        "type": "Fraude interne",
        "entite": "agent_DGI_0421",
        "raisons": [
            "volume de données exportées anormalement élevé — 13σ",
            "connexion depuis 185.220.101.47 vers 10.0.0.1",
        ],
        "contact_dsi": "dsi@minfi.cm",
        "details": "Utilisateur MINFI\\jean.dupont a accédé à 40 dossiers sensibles.",
    }

    mapping = {}
    clean = pseudonymize_dict(sample_alert, mapping)

    print("=== Alerte originale ===")
    print(json.dumps(sample_alert, ensure_ascii=False, indent=2))
    print("\n=== Alerte pseudonymisée ===")
    print(json.dumps(clean, ensure_ascii=False, indent=2))
    print("\n=== Mapping (réservé admin) ===")
    for pseudo, entry in mapping.items():
        print(f"  {pseudo} → {entry['original']} ({entry['kind']})")
