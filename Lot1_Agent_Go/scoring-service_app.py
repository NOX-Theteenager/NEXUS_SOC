#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Service de scoring IA (colle d'intégration)
=======================================================
Branche les modèles d'IA (Modèle 1 réseau, Modèle 2 fraude) sur le pipeline :
  • API REST de scoring synchrone (test / intégration) → /score/network, /score/user-day
  • Consommateur Kafka : lit la télémétrie (topic nexus.telemetry), score, et publie
    les alertes (topic nexus.alerts) consommées ensuite par le SOAR ; persiste en base.

Conçu pour démarrer même si Kafka / PostgreSQL ne sont pas encore prêts (dégradation
gracieuse), afin de faciliter le développement.
"""
import hashlib
import hmac as hmac_lib
import json
import os
import re
import sys
import gzip as gziplib
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import numpy as np
import joblib
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel

# Libellés lisibles (explicabilité Modèle 2)
LISIBLE = {
    "nb_connexions": "connexions", "nb_actions_hors_heures": "actions hors heures ouvrables",
    "nb_transactions": "transactions budgétaires", "montant_total_modifie": "montant total modifié",
    "nb_modifs_montant": "modifications de montants", "nb_creations_compte": "créations de comptes agents",
    "nb_exports": "exports de données", "volume_donnees_exportees": "volume de données exportées",
    "nb_acces_dossiers_sensibles": "accès à des dossiers sensibles", "nb_actions_total": "actions au total",
}

KAFKA = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
T_TELEMETRY = os.getenv("TELEMETRY_TOPIC", "nexus.telemetry")
T_RAW = os.getenv("RAW_TOPIC", "nexus.telemetry.raw")
T_ALERTS = os.getenv("ALERTS_TOPIC", "nexus.alerts")
DB_DSN = os.getenv("DB_DSN")
RISK_THRESHOLD = int(os.getenv("RISK_THRESHOLD", "70"))
# Fenêtre d'agrégation anti-doublon des alertes (minutes ; 0 = désactivé)
ALERT_DEDUP_MIN = int(os.getenv("ALERT_DEDUP_MIN", "15"))

app = FastAPI(title="NEXUS SOC — Service de scoring", version="2.0")
STATE = {"m1": None, "m2": None, "producer": None, "db": None}

# ────────────────────────────────────────────────────────────────────────────
# Rate limiting — compteur en mémoire par IP (remplacer par Redis en production)
# ────────────────────────────────────────────────────────────────────────────
_RATE_WINDOWS: dict = defaultdict(list)   # ip → [timestamps]
RATE_LIMIT_REQ  = int(os.getenv("RATE_LIMIT_REQ",  "100"))  # requêtes max
RATE_LIMIT_WIN  = int(os.getenv("RATE_LIMIT_WIN",  "60"))   # par fenêtre (secondes)
INGEST_LIMIT_REQ = int(os.getenv("INGEST_LIMIT_REQ", "30")) # /ingest plus strict
INGEST_LIMIT_WIN = int(os.getenv("INGEST_LIMIT_WIN", "60"))

def _check_rate_limit(key: str, max_req: int, window: int):
    """Lève HTTP 429 si le client dépasse max_req requêtes dans window secondes."""
    now = time.time()
    hits = _RATE_WINDOWS[key]
    # Purger les timestamps hors fenêtre
    _RATE_WINDOWS[key] = [t for t in hits if now - t < window]
    if len(_RATE_WINDOWS[key]) >= max_req:
        raise HTTPException(
            status_code=429,
            detail=f"Trop de requêtes — limite : {max_req} par {window} s. Réessayez plus tard.",
            headers={"Retry-After": str(window)},
        )
    _RATE_WINDOWS[key].append(now)

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return xff.split(",")[0].strip() if xff else request.client.host

# ────────────────────────────────────────────────────────────────────────────
# Clés HMAC des agents — dérivation plutôt que stockage
# ────────────────────────────────────────────────────────────────────────────
# La clé d'un agent était tirée au hasard, transmise une fois, et seule son
# EMPREINTE était conservée. Impossible, dès lors, de recalculer la signature
# attendue : /ingest ne pouvait que constater la présence du header.
#
# La clé est maintenant DÉRIVÉE d'un secret maître et de l'identité de l'agent :
#
#     hmac_key = HMAC-SHA256(NEXUS_HMAC_MASTER, "<agent_id>:<epoch>")
#
# Le serveur la recalcule à la volée, donc rien de réversible ne dort en base.
# L'époque s'incrémente à chaque rotation : la clé change sans que l'identité de
# l'agent bouge, et l'ancienne devient immédiatement inopérante.
#
# Le secret maître retombe sur JWT_SECRET pour qu'un déploiement existant
# continue de fonctionner sans nouvelle variable, mais il est préférable de lui
# en donner une propre : compromettre l'un ne doit pas livrer l'autre.
NEXUS_HMAC_MASTER = os.getenv("NEXUS_HMAC_MASTER") or os.getenv("JWT_SECRET", "")

# Refuse tout lot dont la signature n'est pas vérifiable. À activer une fois le
# parc entièrement migré vers le schéma dérivé (voir v_agents_hmac_a_migrer).
INGEST_STRICT_HMAC = os.getenv("INGEST_STRICT_HMAC", "0").lower() in ("1", "true", "yes")

_legacy_signales: set = set()


def derive_hmac_key(agent_id: str, epoch: int = 0) -> str:
    """Clé HMAC d'un agent, reconstruite à la demande."""
    if not NEXUS_HMAC_MASTER:
        raise RuntimeError(
            "NEXUS_HMAC_MASTER (ou JWT_SECRET) non défini : impossible de dériver "
            "les clés d'agent. Renseignez-le avant d'enrôler."
        )
    return hmac_lib.new(NEXUS_HMAC_MASTER.encode(),
                        f"{agent_id}:{epoch}".encode(),
                        hashlib.sha256).hexdigest()


def _avertir_legacy(agent_id: str) -> None:
    """Signale une fois par agent qu'il circule sans signature vérifiable."""
    if agent_id in _legacy_signales:
        return
    _legacy_signales.add(agent_id)
    print(f"[ingest] ⚠ agent {agent_id[:8]} en schéma HMAC 'legacy' : signature NON vérifiée. "
          f"Faire tourner sa clé (POST /provision/rotate-hmac/{agent_id}) puis activer "
          f"INGEST_STRICT_HMAC=1 une fois le parc migré.")


# ────────────────────────────────────────────────────────────────────────────
# Validation HMAC-SHA256 pour la passerelle /ingest
# ────────────────────────────────────────────────────────────────────────────
def _verify_ingest(body: bytes, authorization: str, x_signature: str, agent_id: str) -> bool:
    """
    Vérifie :
      1. Le Bearer token (hash SHA-256 stocké en base dans agents.token_hash)
      2. La signature HMAC-SHA256 du payload (header X-Signature)
    Retourne True si valide, False si invalide.
    En cas d'indisponibilité de la base, on accepte avec avertissement (démarrage).
    """
    if not authorization.startswith("Bearer nexus_"):
        return False
    token = authorization.removeprefix("Bearer ")
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    if STATE["db"]:
        try:
            with STATE["db"].cursor() as cur:
                cur.execute(
                    """SELECT a.id::text,
                              a.token_expires_at,
                              a.token_used_at,
                              a.token_one_time,
                              a.hmac_scheme,
                              a.hmac_epoch
                       FROM agents a
                       WHERE a.token_hash = %s AND a.statut != 'isole'""",
                    (token_hash,)
                )
                row = cur.fetchone()
            if not row:
                return False
            aid, expires_at, used_at, one_time, scheme, epoch = row
            # Token expiré
            if expires_at and expires_at < datetime.now(timezone.utc):
                return False
            # Usage unique déjà consommé
            if used_at and one_time:
                return False

            if not x_signature:
                return False

            # ── Vérification réelle de la signature ──────────────────────────
            # La clé n'est pas stockée : elle est redérivée du secret maître.
            # On compare en temps constant pour ne pas fuiter d'information par
            # le temps de réponse.
            if scheme == "derived":
                attendue = hmac_lib.new(
                    derive_hmac_key(aid, epoch or 0).encode(), body, hashlib.sha256
                ).hexdigest()
                if hmac_lib.compare_digest(attendue, x_signature):
                    return True
                print(f"[ingest] signature invalide pour l'agent {aid[:8]} — lot rejeté")
                return False

            # ── Agents antérieurs au schéma dérivé ───────────────────────────
            # Leur clé était tirée au hasard et seule son empreinte a été
            # conservée : la signature est mathématiquement invérifiable. On ne
            # prétend pas le contraire.
            if INGEST_STRICT_HMAC:
                print(f"[ingest] agent {aid[:8]} en schéma 'legacy' et mode strict actif — lot rejeté. "
                      f"Faire tourner sa clé (POST /provision/rotate-hmac/{aid}).")
                return False
            _avertir_legacy(aid)
            return len(x_signature) == 64
        except Exception as e:
            print(f"[ingest] validation DB échouée, mode dégradé : {e}")
            return not INGEST_STRICT_HMAC
    # Base indisponible → accepter en dev, refuser si le mode strict est demandé
    return not INGEST_STRICT_HMAC


# --------------------------------------------------------------------------- #
# Chargement des modèles
# --------------------------------------------------------------------------- #
def _load(path):
    try:
        return joblib.load(path) if path and os.path.exists(path) else None
    except Exception as e:
        print(f"[scoring] échec chargement {path} : {e}")
        return None


# --------------------------------------------------------------------------- #
# Explicabilité : écarts par feature
# --------------------------------------------------------------------------- #
# Les modèles produisaient déjà les écarts-types par feature, puis les
# formataient en chaîne de caractères — la valeur numérique était jetée. Elle est
# désormais conservée : c'est elle qui permet à la console de tracer la
# décomposition de l'explicabilité au lieu d'aligner des phrases.
#
# Chaque raison porte :
#   feature  identifiant technique de la variable
#   label    libellé lisible (table LISIBLE)
#   sigma    écart à la normale, en écarts-type
#   valeur   valeur observée
#   texte    phrase prête à l'emploi — préserve les consommateurs existants
#            (rapport HTML, notifications SMS) qui attendent une chaîne
SIGMA_MIN = float(os.getenv("EXPLAIN_SIGMA_MIN", "1.5"))
SIGMA_TOP = int(os.getenv("EXPLAIN_TOP_N", "5"))


def _raisons_sigma(feats, x, mean, std) -> list:
    """Features les plus déviantes, triées par écart décroissant."""
    std = np.where(np.abs(std) > 1e-9, std, 1e-9)
    z = (np.asarray(x, dtype=float) - np.asarray(mean, dtype=float)) / np.asarray(std, dtype=float)
    out = []
    for i in np.argsort(z)[::-1][:SIGMA_TOP]:
        if z[i] <= SIGMA_MIN:
            continue
        label = LISIBLE.get(feats[i], str(feats[i]).replace("_", " "))
        out.append({
            "feature": str(feats[i]),
            "label":   label,
            "sigma":   round(float(z[i]), 1),
            "valeur":  round(float(x[i]), 2),
            "texte":   f"{label} anormalement élevé ({z[i]:.1f}σ)",
        })
    return out


def _stats_normales(b):
    """Moyenne et écart-type de référence du modèle.

    Le Modèle 2 les embarque explicitement (`normal_mean` / `normal_std`). Le
    Modèle 1 ne les embarquait pas, mais son StandardScaler les porte : c'est la
    même statistique, apprise sur les mêmes données d'entraînement. On la
    réutilise plutôt que de laisser les alertes réseau sans explicabilité.
    """
    if b.get("normal_mean") is not None and b.get("normal_std") is not None:
        return b["normal_mean"], b["normal_std"]
    sc = b.get("scaler")
    if sc is not None and hasattr(sc, "mean_") and hasattr(sc, "scale_"):
        return sc.mean_, sc.scale_
    return None, None


def score_network(features: dict):
    b = STATE["m1"]
    if not b:
        return None
    feats = b["features"]
    x = np.array([float(features.get(f, 0)) for f in feats])
    s = float(-b["model"].score_samples(b["scaler"].transform(x.reshape(1, -1)))[0])
    lo, hi = b["risk_cfg"]["lo"], b["risk_cfg"]["hi"]
    risk = int(np.clip((s - lo) / (hi - lo) * 100, 0, 100))

    mean, std = _stats_normales(b)
    raisons = _raisons_sigma(feats, x, mean, std) if mean is not None else []
    if not raisons:
        raisons = [{"label": "profil de flux globalement atypique", "sigma": None,
                    "texte": "profil de flux globalement atypique"}]

    return {"risque": risk, "anomalie": s >= b["threshold"],
            "score_brut": round(s, 4), "raisons": raisons}


def score_userday(features: dict):
    b = STATE["m2"]
    if not b:
        return None
    feats = b["features"]
    x = np.array([float(features.get(f, 0)) for f in feats])
    s = float(-b["model"].score_samples(b["scaler"].transform(x.reshape(1, -1)))[0])
    risk = int(np.clip((s - b["risk_lo"]) / (b["risk_hi"] - b["risk_lo"]) * 100, 0, 100))

    mean, std = _stats_normales(b)
    raisons = _raisons_sigma(feats, x, mean, std) if mean is not None else []
    if not raisons:
        raisons = [{"label": "profil globalement atypique", "sigma": None,
                    "texte": "profil globalement atypique"}]

    return {"risque": risk, "anomalie": s >= b["threshold"], "raisons": raisons}


# --------------------------------------------------------------------------- #
# Émission d'alerte → Kafka (consommée par le SOAR) + persistance Postgres
# --------------------------------------------------------------------------- #
def _alerte_dupliquee(alert: dict) -> bool:
    """
    Anti-doublon : une alerte identique (même périmètre, type et entité) déjà
    ouverte dans la fenêtre ALERT_DEDUP_MIN n'est pas recréée.

    Sans ce garde-fou, une condition persistante (ex. un flux réseau continu
    jugé anormal) génèrerait une alerte à chaque cycle de collecte et noierait
    la file de l'analyste. C'est l'agrégation d'alertes pratiquée en SOC.
    """
    if not (STATE["db"] and ALERT_DEDUP_MIN > 0):
        return False
    try:
        with STATE["db"].cursor() as cur:
            cur.execute(
                "SELECT 1 FROM alerts "
                " WHERE tenant_id = %s::uuid AND type = %s AND entite = %s "
                "   AND statut = 'ouverte' "
                "   AND cree_le > now() - (%s || ' minutes')::interval "
                " LIMIT 1",
                (alert.get("tenant"), alert.get("type"), alert.get("entite"),
                 str(ALERT_DEDUP_MIN)))
            return cur.fetchone() is not None
    except Exception:
        try:
            STATE["db"].rollback()
        except Exception:
            pass
        return False


def typer_entite(entite: str) -> tuple:
    """Déduit (type, identifiant) de l'entité portée par une alerte.

    Le collecteur préfixe ce qu'il mesure : `hote_<machine>` pour les features
    comportementales — qui sont des agrégats de MACHINE (sessions `who`, flux,
    /etc/passwd), sans aucune identité d'utilisateur — et `agent_<perimetre>_<n>`
    pour les comptes applicatifs issus des journaux métier.

    Cette distinction n'était pas exploitée : le playbook proposait un gel de
    compte sur des hôtes. On ne gèle pas « hote_SRV-APP-GOV-01 », ce compte
    n'existe pas.
    """
    e = (entite or "").strip()
    if not e or e == "?":
        return ("inconnu", e)
    if e.startswith("hote_"):
        return ("hote", e[5:])
    if e.startswith("agent_"):
        return ("compte", e)
    # Sans préfixe, le collecteur envoie un nom de machine (features réseau).
    return ("hote", e)


# Playbook SOAR : l'action dépend du type de menace ET de la nature de la cible.
# Une même famille d'anomalie ne se traite pas pareil selon qu'elle porte sur un
# compte ou sur une machine.
SOAR_PLAYBOOK = {
    ("Fraude interne", "compte"): ("freeze_account", "fort",
                                   "Gel du compte suspecté + préservation des journaux. "
                                   "Validation RSSI requise avant exécution."),
    ("Fraude interne", "hote"):   ("isolate_host", "fort",
                                   "Comportement anormal mesuré au niveau de la machine "
                                   "(sessions, flux, comptes locaux) : aucune identité "
                                   "utilisateur n'est impliquée. Mise en quarantaine réseau "
                                   "de l'hôte. Validation requise."),
}
DEFAULT_SOAR = ("isolate_host", "fort",
                "Isolation de l'hôte concerné du réseau. Validation requise.")


def choisir_action_soar(alert: dict) -> tuple:
    """Retourne (action, impact, detail, cible, cible_type) pour une alerte.

    Le blocage d'IP n'est proposé QUE si un indicateur exploitable a été
    observé. Sans IP, l'action n'a pas de cible : la proposer reviendrait à
    demander une validation pour un geste que personne ne peut exécuter.
    """
    ctype, cible = typer_entite(alert.get("entite"))
    iocs = [i for i in (alert.get("iocs") or []) if i]

    if alert.get("type") == "Anomalie réseau / C2":
        if iocs:
            return ("block_ip", "moyen",
                    f"Blocage de la destination {iocs[0]} observée comme canal de "
                    f"commande. Validation analyste requise.",
                    iocs[0], "ip")
        # Canal C2 soupçonné sans destination identifiée : on contient la
        # machine, faute de pouvoir bloquer quoi que ce soit au pare-feu.
        return ("isolate_host", "fort",
                "Canal de commande soupçonné mais aucune destination n'a été "
                "observée dans les événements bruts : rien à bloquer au pare-feu. "
                "Mise en quarantaine réseau de l'hôte. Validation requise.",
                cible, ctype)

    action, impact, detail = SOAR_PLAYBOOK.get(
        (alert.get("type"), ctype), DEFAULT_SOAR)
    return (action, impact, detail, cible, ctype)


def _proposer_soar(alert_id, alert: dict) -> None:
    """Crée une proposition d'action SOAR en attente de validation pour l'alerte.
    Transaction séparée : un échec ici ne doit jamais annuler l'alerte déjà
    persistée."""
    if not STATE["db"]:
        return
    action, impact, detail, cible, cible_type = choisir_action_soar(alert)
    try:
        with STATE["db"].cursor() as cur:
            cur.execute(
                "INSERT INTO soar_audit (alert_id, tenant_id, action, impact, statut, "
                "                        detail, cible, cible_type) "
                "VALUES (%s::uuid, %s::uuid, %s, %s, 'EN ATTENTE DE VALIDATION', %s, %s, %s)",
                (alert_id, alert.get("tenant"), action, impact, detail, cible, cible_type))
        STATE["db"].commit()
    except Exception as e:
        try:
            STATE["db"].rollback()
        except Exception:
            pass
        print(f"[soar] proposition non créée : {e}")


# ---------------------------------------------------------------------------
# Rapport d'incident HTML
# ---------------------------------------------------------------------------
# Ce document SORT du navigateur : il est transféré par e-mail, imprimé,
# archivé. Trois contraintes en découlent, différentes du reste de la
# plateforme (voir designexus.md §5.7) :
#   1. Fond blanc obligatoire — le thème sombre ne s'applique pas ici.
#   2. Aucune ressource externe, aucun script — le portail l'affiche dans une
#      iframe sandboxée qui bloque le JavaScript de toute façon.
#   3. Feuille @media print dédiée : marges 18 mm, pas de coupure au milieu
#      d'un tableau, en-tête répété.
# Polices système uniquement (Georgia / Courier New) : le document doit rester
# lisible sur un poste qui n'a pas les polices de la plateforme.

# Référentiel MITRE réduit aux techniques produites par correlation_engine_v2,
# pour donner une phrase lisible à côté de chaque identifiant.
_MITRE_LIB = {
    "T1566": ("Initial Access",    "Hameçonnage — pièce jointe ou lien externe"),
    "T1078": ("Initial Access",    "Utilisation de comptes valides existants"),
    "T1059": ("Execution",         "Exécution de commandes ou de scripts"),
    "T1204": ("Execution",         "Exécution déclenchée par l'utilisateur"),
    "T1053": ("Persistence",       "Tâche planifiée"),
    "T1136": ("Persistence",       "Création de compte"),
    "T1027": ("Defense Evasion",   "Fichier ou commande obfusqués"),
    "T1070": ("Defense Evasion",   "Effacement de traces"),
    "T1083": ("Discovery",         "Énumération de fichiers et de répertoires"),
    "T1087": ("Discovery",         "Énumération de comptes"),
    "T1005": ("Collection",        "Collecte de données sur le système local"),
    "T1114": ("Collection",        "Collecte de messagerie"),
    "T1071": ("Command & Control", "Canal de commande sur protocole applicatif"),
    "T1571": ("Command & Control", "Port réseau non standard"),
    "T1090": ("Command & Control", "Relais ou proxy"),
    "T1041": ("Exfiltration",      "Exfiltration par le canal de commande"),
    "T1048": ("Exfiltration",      "Exfiltration par protocole alternatif"),
    "T1486": ("Impact",            "Chiffrement de données (rançongiciel)"),
}
_MITRE_ORDRE = ["Initial Access", "Execution", "Persistence", "Defense Evasion",
                "Discovery", "Collection", "Command & Control", "Exfiltration", "Impact"]


# Libellés du rapport. Le rapport sort de la plateforme — courriel, impression,
# archivage, transmission à un partenaire — et c'était le seul écran resté
# monolingue alors que tout le reste bascule FR/EN. Un document destiné à être
# diffusé hors du CENADI doit pouvoir l'être dans les deux langues.
_RAPPORT_L10N = {
    "fr": {
        "html_lang": "fr", "date_fmt": "%d/%m/%Y %H:%M", "tz": "(UTC+1)",
        "titre_doc": "Rapport d'incident {ref} — NEXUS SOC",
        "h1": "NEXUS SOC — Rapport d'incident",
        "org": "CENADI · Centre National de Développement de l'Informatique",
        "ref": "Réf. {ref}",
        "f_incident": "Incident", "f_perimetre": "Périmètre", "f_entite": "Entité",
        "f_type": "Type", "f_score": "Score de risque", "f_detecte": "Détecté par",
        "perim_vide": "périmètre non renseigné",
        "s1": "1. Analyse", "s2": "2. Chaîne d'attaque (MITRE ATT&CK)",
        "s3": "3. Raisons du modèle", "s4": "4. Décomposition du score",
        "s_suite": "{n}. Suite donnée",
        "chaine_correlee": "Déroulé reconstitué par corrélation des événements bruts "
                           "de l'agent, sur une fenêtre glissante.",
        "chaine_isolee": "Alerte issue du scoring d'un événement isolé : techniques "
                         "ordonnées par phase ATT&CK, sans chronologie.",
        "chaine_vide": "Aucune technique ATT&amp;CK corrélée sur cet incident.",
        "raisons_vide": "Aucune raison détaillée n'a été fournie par le modèle.",
        "total": "TOTAL", "borne": " (somme des contributions : {somme}, risque borné à 100)",
        "suite": "Les actions de réponse engagées sur cet incident sont consignées dans le "
                 "journal d'audit SOAR de la plateforme, avec leur auteur, leur horodatage "
                 "et leur statut. Ce journal fait foi en cas de contestation.",
        "foot1": "Document généré automatiquement par NEXUS SOC · GPL-3.0-or-later",
        "foot2": "Diffusion restreinte — personnels habilités du CENADI",
        "a_declenche": "L'entité {entite} du périmètre {perim} a déclenché une alerte de "
                       "type « {type} » le {date}.",
        "a_score": "Le modèle {src} lui attribue un score de risque de {risque} sur 100.",
        "a_sequence": "La séquence corrèle {n} technique(s) ATT&CK ({ids}), de la phase "
                      "{p1} à la phase {p2}.",
        "a_facteur": "Facteur principal retenu par le modèle : {facteur}.",
        "a_validation": "Les actions de réponse d'impact fort restent soumises à la "
                        "validation d'un analyste du SOC ; les actions d'impact faible ou "
                        "moyen sont exécutées automatiquement.",
        "int_titre": "Intégrité du document",
        "int_hash": "Empreinte SHA-256 : {hash}",
        "int_verif": "Vérifier : grep -v NEXUS-INTEGRITY <fichier> | sha256sum",
        "int_sig": "Scellé HMAC-SHA256 : {sig} — vérifiable par le SOC détenteur du secret "
                   "de plateforme.",
        "int_sig_absente": "Aucun scellé : NEXUS_HMAC_MASTER n'est pas configuré sur cette "
                           "instance. L'empreinte reste vérifiable.",
    },
    "en": {
        "html_lang": "en", "date_fmt": "%d %b %Y, %H:%M", "tz": "(UTC+1)",
        "titre_doc": "Incident report {ref} — NEXUS SOC",
        "h1": "NEXUS SOC — Incident report",
        "org": "CENADI · National Centre for IT Development",
        "ref": "Ref. {ref}",
        "f_incident": "Incident", "f_perimetre": "Scope", "f_entite": "Entity",
        "f_type": "Type", "f_score": "Risk score", "f_detecte": "Detected by",
        "perim_vide": "scope not specified",
        "s1": "1. Analysis", "s2": "2. Attack chain (MITRE ATT&CK)",
        "s3": "3. Model reasons", "s4": "4. Score breakdown",
        "s_suite": "{n}. Follow-up",
        "chaine_correlee": "Sequence reconstructed by correlating the agent's raw events "
                           "over a sliding window.",
        "chaine_isolee": "Alert produced by scoring a single event: techniques ordered by "
                         "ATT&CK phase, without a timeline.",
        "chaine_vide": "No ATT&amp;CK technique correlated on this incident.",
        "raisons_vide": "The model provided no detailed reason.",
        "total": "TOTAL", "borne": " (sum of contributions: {somme}, risk capped at 100)",
        "suite": "Response actions taken on this incident are recorded in the platform's "
                 "SOAR audit log, with their author, timestamp and status. That log is "
                 "authoritative in case of dispute.",
        "foot1": "Document automatically generated by NEXUS SOC · GPL-3.0-or-later",
        "foot2": "Restricted circulation — authorised CENADI staff",
        "a_declenche": "Entity {entite} of scope {perim} raised a « {type} » alert on {date}.",
        "a_score": "Model {src} assigns it a risk score of {risque} out of 100.",
        "a_sequence": "The sequence correlates {n} ATT&CK technique(s) ({ids}), from phase "
                      "{p1} to phase {p2}.",
        "a_facteur": "Main factor retained by the model: {facteur}.",
        "a_validation": "High-impact response actions remain subject to validation by a SOC "
                        "analyst; low- and medium-impact actions are executed automatically.",
        "int_titre": "Document integrity",
        "int_hash": "SHA-256 digest: {hash}",
        "int_verif": "Verify: grep -v NEXUS-INTEGRITY <file> | sha256sum",
        "int_sig": "HMAC-SHA256 seal: {sig} — verifiable by the SOC holding the platform "
                   "secret.",
        "int_sig_absente": "No seal: NEXUS_HMAC_MASTER is not configured on this instance. "
                           "The digest remains verifiable.",
    },
}

# Marqueur porté par CHAQUE ligne du bloc d'intégrité. L'empreinte est calculée
# sur le document privé de ces lignes : le lecteur reproduit exactement les
# mêmes octets en les retirant, avec des outils standards et sans réseau.
_MARQUEUR_INTEGRITE = "NEXUS-INTEGRITY"


def _sceller_rapport(document: str, lang: str) -> str:
    """Remplace le jeton d'intégrité par l'empreinte réelle du document.

    L'empreinte ne peut pas porter sur le document qui la contient. On la calcule
    donc sur le document privé du bloc d'intégrité — ce que `grep -v` reproduit
    à l'octet près.
    """
    L = _RAPPORT_L10N.get(lang, _RAPPORT_L10N["fr"])
    canonique = document.replace("@@INTEGRITE@@\n", "")
    empreinte = hashlib.sha256(canonique.encode("utf-8")).hexdigest()

    master = os.getenv("NEXUS_HMAC_MASTER") or os.getenv("JWT_SECRET", "")
    if master:
        sig = hmac_lib.new(master.encode(), canonique.encode("utf-8"),
                           hashlib.sha256).hexdigest()
        ligne_sig = L["int_sig"].format(sig=f"{sig[:16]}…{sig[-8:]}")
    else:
        ligne_sig = L["int_sig_absente"]

    groupes = " ".join(empreinte[i:i + 8] for i in range(0, 32, 8))
    bloc = "\n".join(
        f'    <div class="int">{_MARQUEUR_INTEGRITE} {ligne}</div>'
        for ligne in (
            L["int_titre"],
            L["int_hash"].format(hash=f"{groupes} … {empreinte[-8:]}"),
            L["int_verif"],
            ligne_sig,
        )) + "\n"
    return document.replace("@@INTEGRITE@@\n", bloc)


def _rapport_html(alert: dict, risque: int, reference: str = "", perimetre: str = "",
                  lang: str = "fr") -> str:
    """Rapport d'incident HTML autonome : imprimable, diffusable, archivable."""
    import html
    from datetime import datetime as _dt
    esc = html.escape

    L = _RAPPORT_L10N.get(lang, _RAPPORT_L10N["fr"])
    horodatage = _dt.now().strftime(L["date_fmt"])
    ref = reference or "—"
    perim = perimetre or L["perim_vide"]
    couleur = "#B91C1C" if risque >= 80 else "#B45309" if risque >= 60 else "#1D4ED8"

    # ── Identification ────────────────────────────────────────────────────
    champs = [
        (L["f_incident"],  ref,                                        True),
        (L["f_perimetre"], perim,                                      False),
        (L["f_entite"],    str(alert.get("entite", "—")),              False),
        (L["f_type"],      str(alert.get("type", "—")),                False),
        (L["f_score"],     f"{risque} / 100",                          True),
        (L["f_detecte"],   str(alert.get("src", "—") or "—"),          False),
    ]
    id_html = "".join(
        '<div class="f"><span class="k">{k}</span><span class="v"{s}>{v}</span></div>'.format(
            k=esc(k), v=esc(v),
            s=f' style="font-weight:700;color:{couleur}"' if fort and k == L["f_score"]
              else ' style="font-weight:700"' if fort else "")
        for k, v, fort in champs)

    # ── Chaîne d'attaque ──────────────────────────────────────────────────
    # Si le moteur de corrélation a produit un déroulé horodaté avec preuves, on
    # le publie tel quel : c'est la pièce la plus utile du rapport. Sinon, on se
    # rabat sur la liste des techniques ordonnée par phase, en le disant — un
    # rapport diffusé ne doit pas laisser croire à une chronologie inexistante.
    deroule = alert.get("chaine") or []
    if isinstance(deroule, list) and deroule and isinstance(deroule[0], dict):
        chaine_html = "".join(
            f'<tr><td class="mono">{esc(str(e.get("heure", "")))}</td>'
            f'<td class="mono b">{esc(str(e.get("technique_id") or e.get("technique") or ""))}</td>'
            f'<td>{esc(str(e.get("tactique", "")))}'
            + (f'<br><span style="color:#555">{esc(str(e.get("detail")))}</span>'
               if e.get("detail") else "")
            + '</td></tr>'
            for e in deroule if isinstance(e, dict))
        chaine_note = L["chaine_correlee"]
        etapes = []
    else:
        # Deux formats en base : « T1005, T1059 » et « T1071 · C2 ». On extrait
        # les identifiants par motif plutôt que de découper sur la virgule, qui
        # laisserait le second format non résolu.
        bruts = list(dict.fromkeys(
            re.findall(r"T\d{4}(?:\.\d{3})?", str(alert.get("mitre", "") or ""))))
        etapes = []
        for tid in bruts:
            base = tid.split(".")[0]
            tac, lib = _MITRE_LIB.get(base, ("Technique", "Technique non répertoriée"))
            etapes.append((_MITRE_ORDRE.index(tac) if tac in _MITRE_ORDRE else 99, tid, tac, lib))
        etapes.sort(key=lambda e: e[0])
        chaine_html = "".join(
            f'<tr><td class="mono b">{esc(tid)}</td><td class="mono">{esc(tac)}</td><td>{esc(lib)}</td></tr>'
            for _, tid, tac, lib in etapes
        ) or f'<tr><td colspan="3" class="vide">{L["chaine_vide"]}</td></tr>'
        chaine_note = L["chaine_isolee"] if etapes else ""

    # ── Raisons du modèle, telles que renvoyées ───────────────────────────
    # Deux formes possibles : chaînes déjà rédigées, ou objets porteurs de
    # l'écart σ. Dans le second cas on publie le chiffre : c'est l'explicabilité
    # du modèle, et un rapport d'incident qui sort de la plateforme doit pouvoir
    # être contesté sur pièces.
    raisons = alert.get("raisons", []) or []
    if isinstance(raisons, str):
        raisons = [raisons]
    lignes = []
    for r in raisons:
        if isinstance(r, dict):
            libelle = esc(str(r.get("texte") or r.get("label") or ""))
            sigma = r.get("sigma")
            if sigma is not None and not str(r.get("texte") or "").strip().endswith("σ)"):
                libelle += f' <span style="font-family:\'Courier New\',monospace;color:#555">({sigma}σ)</span>'
            lignes.append(f"<li>{libelle}</li>")
        else:
            lignes.append(f"<li>{esc(str(r))}</li>")
    raisons_html = "".join(lignes) or f'<li>{L["raisons_vide"]}</li>'

    # ── Décomposition du score, quand le score est une somme ──────────────
    parts = alert.get("score_parts") or []
    parts_html = ""
    if isinstance(parts, list) and parts:
        lignes_p = "".join(
            f'<tr><td>{esc(str(p.get("label", "—")))}</td>'
            f'<td class="mono" style="text-align:right">+{esc(str(p.get("valeur", "")))}</td></tr>'
            for p in parts if isinstance(p, dict))
        somme = sum(int(p.get("valeur", 0)) for p in parts if isinstance(p, dict))
        note = L["borne"].format(somme=somme) if somme > risque else ""
        parts_html = (
            f'<section><h2>{L["s4"]}</h2><table>'
            f'{lignes_p}'
            f'<tr><td class="b">{L["total"]}{esc(note)}</td>'
            f'<td class="mono b" style="text-align:right">{risque}</td></tr>'
            '</table></section>'
        )

    # La section « Suite donnée » ferme le document : son numéro dépend de la
    # présence de la décomposition, qui n'existe pas pour toutes les alertes.
    n_suite = 5 if parts_html else 4

    # ── Analyse en clair (déterministe, aucune phrase inventée) ───────────
    phrases = [
        L["a_declenche"].format(entite=alert.get("entite", "—"), perim=perim,
                                type=alert.get("type", "—"), date=horodatage),
        L["a_score"].format(src=alert.get("src", "—") or "—", risque=risque),
    ]
    if etapes:
        phrases.append(L["a_sequence"].format(
            n=len(etapes), ids=", ".join(e[1] for e in etapes),
            p1=etapes[0][2], p2=etapes[-1][2]))
    if raisons:
        # Les raisons peuvent être des objets porteurs de l'écart σ : on reprend
        # le texte, jamais la représentation du dictionnaire.
        premier = raisons[0]
        facteur = (premier.get("texte") or premier.get("label") or "") \
            if isinstance(premier, dict) else str(premier)
        if facteur.strip():
            phrases.append(L["a_facteur"].format(facteur=facteur.rstrip(".")))
    phrases.append(L["a_validation"])
    analyse = " ".join(phrases)

    document = f"""<!DOCTYPE html>
<html lang="{L['html_lang']}"><head><meta charset="utf-8">
<title>{esc(L['titre_doc'].format(ref=ref))}</title>
<style>
  @page {{ margin: 18mm; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#fff; color:#1a1a1a;
         font-family:Georgia,"Times New Roman",serif; font-size:13.5px; line-height:1.6; }}
  .page {{ max-width:680px; margin:0 auto; padding:44px 46px; }}
  .mono {{ font-family:"Courier New",monospace; }}
  .b {{ font-weight:700; }}

  header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px;
            border-bottom:2px solid #1a1a1a; padding-bottom:14px; margin-bottom:22px; flex-wrap:wrap; }}
  h1 {{ font-size:22px; font-weight:700; letter-spacing:-.01em; margin:0; }}
  .org {{ font-family:"Courier New",monospace; font-size:11px; color:#555; margin-top:4px; }}
  .meta {{ font-family:"Courier New",monospace; font-size:11px; color:#555; text-align:right; line-height:1.7; }}

  .ident {{ display:grid; grid-template-columns:1fr 1fr; gap:0 26px; margin-bottom:24px; }}
  .f {{ display:flex; justify-content:space-between; gap:12px;
        border-bottom:1px solid #ddd; padding:7px 0; }}
  .k {{ font-family:"Courier New",monospace; font-size:10.5px; text-transform:uppercase;
        letter-spacing:.06em; color:#666; }}
  .v {{ text-align:right; }}

  h2 {{ font-size:15px; font-weight:700; border-bottom:1px solid #1a1a1a;
        padding-bottom:4px; margin:0 0 12px; page-break-after:avoid; }}
  section {{ margin-bottom:22px; page-break-inside:avoid; }}
  p {{ margin:0 0 10px; }}
  .analyse {{ font-style:italic; color:#333; }}

  table {{ width:100%; border-collapse:collapse; }}
  td {{ padding:6px 8px 6px 0; border-bottom:1px solid #eee; vertical-align:top; font-size:12.5px; }}
  td.mono {{ white-space:nowrap; }}
  .vide {{ color:#666; font-style:italic; }}
  ul {{ margin:0; padding-left:20px; }}
  li {{ font-size:13px; margin-bottom:5px; }}

  footer {{ border-top:1px solid #ccc; padding-top:12px; margin-top:26px;
            font-family:"Courier New",monospace; font-size:10.5px; color:#666; line-height:1.7; }}
  .int {{ font-family:"Courier New",monospace; font-size:10px; color:#333;
          line-height:1.6; word-break:break-all; }}
  .intbox {{ margin-top:12px; padding:9px 12px; background:#f4f4f4;
             border:1px solid #ddd; border-radius:4px; }}

  @media print {{
    .page {{ max-width:none; padding:0; }}
    section, table, tr {{ page-break-inside:avoid; }}
    h2 {{ page-break-after:avoid; }}
  }}
</style></head>
<body><div class="page">

  <header>
    <div>
      <h1>{esc(L['h1'])}</h1>
      <div class="org">{esc(L['org'])}</div>
    </div>
    <div class="meta">{esc(L['ref'].format(ref=ref))}<br>{esc(horodatage)} {L['tz']}</div>
  </header>

  <div class="ident">{id_html}</div>

  <section>
    <h2>{esc(L['s1'])}</h2>
    <p class="analyse">{esc(analyse)}</p>
  </section>

  <section>
    <h2>{esc(L['s2'])}</h2>
    <table>{chaine_html}</table>
    {f'<p style="font-size:11.5px;color:#666;margin-top:8px">{esc(chaine_note)}</p>' if chaine_note else ''}
  </section>

  <section>
    <h2>{esc(L['s3'])}</h2>
    <ul>{raisons_html}</ul>
  </section>

  {parts_html}

  <section>
    <h2>{esc(L['s_suite'].format(n=n_suite))}</h2>
    <p>{esc(L['suite'])}</p>
  </section>

  <footer>
    {esc(L['foot1'])}<br>
    {esc(L['foot2'])}
    <div class="intbox">
@@INTEGRITE@@
    </div>
  </footer>

</div></body></html>
"""
    return _sceller_rapport(document, lang)


def _notifier_portail(alert_id, alert: dict) -> None:
    """Crée une notification pour le responsable du périmètre concerné (avec
    rapport téléchargeable). Transaction séparée : ne doit jamais annuler l'alerte."""
    if not STATE["db"]:
        return
    risque = int(alert.get("risque", 0) or 0)
    severity = "critical" if risque >= 80 else "warning" if risque >= 50 else "info"
    titre = f"{alert.get('type', 'Incident')} — {alert.get('entite', '?')}"
    corps = f"Risque {risque}/100 détecté par {alert.get('src', 'le moteur de détection')}."
    if alert.get("mitre"):
        corps += f" Technique {alert['mitre']}."
    # Nom lisible du périmètre : le rapport sort de la plateforme, un UUID n'y
    # est d'aucune utilité pour le lecteur. Échec de la lecture = libellé neutre,
    # jamais un blocage de la notification.
    perimetre = ""
    try:
        with STATE["db"].cursor() as cur:
            cur.execute("SELECT nom FROM tenants WHERE id = %s::uuid", (alert.get("tenant"),))
            row = cur.fetchone()
        if row:
            perimetre = row[0]
    except Exception:
        try:
            STATE["db"].rollback()
        except Exception:
            pass

    reference = str(alert_id)[:8]
    try:
        with STATE["db"].cursor() as cur:
            cur.execute(
                "INSERT INTO notifications (tenant_id, alert_id, type, severity, title, body, report_html) "
                "VALUES (%s::uuid, %s::uuid, 'alert', %s, %s, %s, %s)",
                (alert.get("tenant"), alert_id, severity, titre, corps,
                 _rapport_html({**alert,
                                "chaine":      alert.get("chaine"),
                                "score_parts": alert.get("score_parts")},
                               risque, reference, perimetre)))
        STATE["db"].commit()
    except Exception as e:
        try:
            STATE["db"].rollback()
        except Exception:
            pass
        print(f"[notif] notification non créée : {e}")


def emit_alert(alert: dict) -> bool:
    """Émet une alerte. Retourne True si elle a réellement été enregistrée
    (False si agrégée avec une alerte identique déjà ouverte)."""
    if _alerte_dupliquee(alert):
        return False
    if STATE["producer"]:
        try:
            STATE["producer"].send(T_ALERTS, json.dumps(alert).encode("utf-8"))
        except Exception as e:
            print(f"[scoring] publication Kafka échouée : {e}")
    if STATE["db"]:
        try:
            with STATE["db"].cursor() as cur:
                # chaine et score_parts sont facultatives : NULL quand l'alerte
                # ne vient pas d'une corrélation. Une alerte de scoring isolé n'a
                # ni déroulé ni score additif, et il ne faut pas en fabriquer.
                cur.execute(
                    "INSERT INTO alerts (tenant_id, source_modele, type, entite, risque, "
                    "                    raisons, mitre, chaine, score_parts) "
                    "VALUES (%(tenant)s,%(src)s,%(type)s,%(entite)s,%(risque)s,"
                    "        %(raisons)s,%(mitre)s,%(chaine)s,%(score_parts)s) "
                    "RETURNING id",
                    {**alert,
                     "raisons":     json.dumps(alert.get("raisons", []), ensure_ascii=False),
                     "chaine":      json.dumps(alert["chaine"], ensure_ascii=False)
                                    if alert.get("chaine") else None,
                     "score_parts": json.dumps(alert["score_parts"], ensure_ascii=False)
                                    if alert.get("score_parts") else None})
                alert_id = cur.fetchone()[0]
            STATE["db"].commit()
        except Exception as e:
            print(f"[scoring] insertion Postgres échouée : {e}")
            return False
        # Chaînon réponse : proposer l'action SOAR correspondante (non bloquant).
        _proposer_soar(alert_id, alert)
        # Chaînon information : notifier le responsable du périmètre (non bloquant).
        _notifier_portail(alert_id, alert)
    return True


# --------------------------------------------------------------------------- #
# Métriques série temporelle (hypertable `metrics`) — mesures réelles
# --------------------------------------------------------------------------- #
def record_metric(tenant_id, agent_id, metrique: str, valeur: float):
    """Enregistre une mesure réelle dans l'hypertable TimescaleDB `metrics`."""
    if not (STATE["db"] and tenant_id):
        return
    try:
        with STATE["db"].cursor() as cur:
            cur.execute(
                "INSERT INTO metrics (ts, tenant_id, agent_id, metrique, valeur) "
                "VALUES (now(), %s::uuid, NULLIF(%s,'')::uuid, %s, %s)",
                (tenant_id, agent_id or "", metrique, float(valeur)))
        STATE["db"].commit()
    except Exception as e:
        try:
            STATE["db"].rollback()
        except Exception:
            pass
        print(f"[metrics] insertion échouée ({metrique}) : {e}")


# --------------------------------------------------------------------------- #
# Corrélation SIEM en flux — chaînes d'attaque MITRE
# --------------------------------------------------------------------------- #
# Le moteur du Lot 2 reconstitue des chaînes d'attaque complètes (heure,
# tactique, technique, preuve) et calcule un risque par SOMME de contributions
# explicites. Il n'était jusqu'ici qu'un script autonome, jamais branché sur le
# flux : seule la liste plate des techniques parvenait à la table `alerts`.
#
# Il est désormais appelé à chaque lot ingéré. Une chaîne s'étale sur plusieurs
# minutes alors qu'un lot ne couvre que l'intervalle de collecte (30 s) : on
# conserve donc une fenêtre glissante d'événements bruts par hôte, bornée en
# temps ET en nombre pour que la mémoire reste maîtrisée.
try:
    _lot2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "Lot2_Pipeline_SIEM")
    if _lot2 not in sys.path:
        sys.path.insert(0, _lot2)
    from correlation_engine_v2 import correlate as _correlate  # type: ignore
    CORRELATION_DISPONIBLE = True
except Exception as _e:                                        # pragma: no cover
    _correlate = None
    CORRELATION_DISPONIBLE = False
    print(f"[correlation] moteur indisponible, chaînes désactivées : {_e}")

CORR_WINDOW_MIN   = int(os.getenv("CORR_WINDOW_MIN", "30"))
CORR_MAX_EVENTS   = int(os.getenv("CORR_MAX_EVENTS_PER_HOST", "2000"))
# Types d'événements bruts que le moteur sait lire. Les vecteurs de features
# destinés aux modèles (kind = network / user-day) ne le concernent pas.
CORR_KINDS = {"process", "connection", "file_change"}

_corr_buffer: dict = defaultdict(deque)   # (tenant, host) -> deque d'événements


def _purger_fenetre(buf: deque) -> None:
    """Retire les événements sortis de la fenêtre de corrélation."""
    limite = datetime.now(timezone.utc) - timedelta(minutes=CORR_WINDOW_MIN)
    while buf:
        try:
            t = datetime.fromisoformat(str(buf[0].get("time", "")).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except Exception:
            buf.popleft()          # horodatage illisible : on ne le garde pas
            continue
        if t < limite:
            buf.popleft()
        else:
            break
    while len(buf) > CORR_MAX_EVENTS:
        buf.popleft()


def correler_lot(events: list, tenant_id: str, host: str, agent_id: str = "") -> int:
    """Alimente la fenêtre glissante de l'hôte et émet les incidents corrélés.

    Retourne le nombre d'alertes réellement enregistrées.
    """
    if not CORRELATION_DISPONIBLE or not host:
        return 0

    bruts = [e for e in events if isinstance(e, dict) and e.get("kind") in CORR_KINDS]
    if not bruts:
        return 0

    cle = (tenant_id, host)
    buf = _corr_buffer[cle]
    for e in bruts:
        # correlate() regroupe par ev["host"] : on le renseigne depuis le lot.
        buf.append({**e, "host": host})
    _purger_fenetre(buf)

    try:
        incidents = _correlate(list(buf))
    except Exception as e:
        print(f"[correlation] échec sur {host} : {e}")
        return 0

    emises = 0
    for inc in incidents:
        # Le risque du moteur est une SOMME de contributions connues : on la
        # publie telle quelle, c'est la décomposition réelle du score.
        tactiques = inc.get("tactiques", [])
        parts = [{"label": f"{len(tactiques)} tactiques distinctes corrélées", "valeur": 12 * len(tactiques)},
                 {"label": "socle de corrélation", "valeur": 45}]
        if "Command and Control" in tactiques:
            parts.append({"label": "canal de commande observé", "valeur": 10})
        if "Impact" in tactiques:
            parts.append({"label": "impact sur les données", "valeur": 12})
        if "Defense Evasion" in tactiques:
            parts.append({"label": "contournement de défense", "valeur": 8})
        if inc.get("activite_hors_heures"):
            parts.append({"label": "activité hors heures ouvrables", "valeur": 6})
        parts.sort(key=lambda p: -p["valeur"])

        chaine = [{
            "heure":        e.get("heure"),
            "tactique":     e.get("tactique"),
            "technique_id": (e.get("technique") or "").split(" ")[0],
            "technique":    e.get("technique"),
            "detail":       e.get("detail"),
        } for e in inc.get("chaine", [])]

        if emit_alert({
            "tenant":      tenant_id,
            "src":         "Corrélation SIEM",
            "type":        inc.get("type", "Compromission probable"),
            "entite":      inc.get("entity", host),
            "risque":      int(inc.get("risque", 0)),
            "raisons":     [{"label": f"{c['tactique']} · {c['technique']}",
                             "sigma": None,
                             "texte": f"{c['tactique']} — {c['detail']}"}
                            for c in inc.get("chaine", [])],
            "mitre":       ", ".join(inc.get("mitre", [])),
            "chaine":      chaine,
            "score_parts": parts,
            # Indicateurs réellement observés : ils donnent sa cible à l'action
            # de réponse. Sans eux, aucun blocage n'est proposé.
            "iocs":        inc.get("iocs", []),
        }):
            emises += 1
    return emises


def process_normalized_event(ev: dict, tenant_id: str = "", agent_id: str = "") -> bool:
    """
    Score un événement DÉJÀ normalisé (contenant `kind` + `features`) et émet une
    alerte réelle si le risque dépasse le seuil. Enregistre aussi le score comme
    métrique série temporelle.

    Utilisé par le consommateur Kafka ET, en l'absence de Kafka, directement par
    /ingest (dégradation gracieuse : la détection reste opérationnelle).
    Retourne True si une alerte a été émise.
    """
    if not isinstance(ev, dict) or "features" not in ev:
        return False
    kind = ev.get("kind")
    res = score_network(ev["features"]) if kind == "network" else score_userday(ev["features"])
    if not res:
        return False

    tid = ev.get("tenant_id") or tenant_id
    aid = ev.get("agent_id") or agent_id

    # Mesure réelle : score de risque calculé sur la télémétrie reçue
    record_metric(tid, aid, f"risque_{kind or 'inconnu'}", res["risque"])

    if res.get("anomalie") and res["risque"] >= RISK_THRESHOLD:
        return emit_alert({
            "tenant": tid,
            "src":    "Modèle 1 (réseau)" if kind == "network" else "Modèle 2 (UEBA)",
            "type":   ev.get("type", "Anomalie réseau / C2" if kind == "network" else "Fraude interne"),
            "entite": ev.get("entite", "?"),
            "risque": res["risque"],
            "raisons": res.get("raisons", []),
            "mitre":  ev.get("mitre", ""),
        })
    return False


# --------------------------------------------------------------------------- #
# Consommateur Kafka (tâche de fond)
# --------------------------------------------------------------------------- #
def _producer_connected() -> bool:
    """Vrai seulement si le producteur est RÉELLEMENT connecté à un broker.
    Piège évité : KafkaProducer() ne lève pas quand le broker est injoignable
    (connexion paresseuse) ; c'est .send() qui échoue ensuite en silence. On
    teste donc la connexion effective avant de router vers Kafka."""
    p = STATE["producer"]
    if p is None:
        return False
    try:
        return bool(p.bootstrap_connected())
    except Exception:
        return False


def _producer_watchdog():
    """Rétablit le chemin asynchrone après une coupure de Kafka : recrée le
    producteur dès que le broker redevient joignable. Sans ce watchdog, après un
    arrêt/redémarrage du broker le service resterait bloqué en scoring inline
    jusqu'au prochain redémarrage manuel."""
    from kafka import KafkaProducer
    while True:
        time.sleep(30)
        if _producer_connected():
            continue
        try:
            neuf = KafkaProducer(
                bootstrap_servers=KAFKA, acks=1, retries=1,
                max_block_ms=5000, request_timeout_ms=5000)
            if neuf.bootstrap_connected():
                ancien = STATE["producer"]
                STATE["producer"] = neuf
                print("[scoring] producteur Kafka reconnecté — chemin asynchrone rétabli")
                if ancien is not None:
                    try:
                        ancien.close(timeout=1)
                    except Exception:
                        pass
            else:
                neuf.close(timeout=1)
        except Exception:
            pass  # broker toujours indisponible → on reste en inline (sûr), on retentera


def consume_loop():
    """Consommateur Kafka de scoring, résilient : se reconnecte indéfiniment au
    lieu de mourir au premier échec (sinon la télémétrie publiée n'est plus
    jamais scorée — panne silencieuse). Le scoring inline de /ingest reste le
    filet de sécurité si Kafka est totalement indisponible."""
    while True:
        try:
            from kafka import KafkaConsumer
            consumer = KafkaConsumer(
                T_TELEMETRY, bootstrap_servers=KAFKA, group_id="scoring",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest")
            print(f"[scoring] consommateur connecté — écoute du topic {T_TELEMETRY}")
            for msg in consumer:
                try:
                    process_normalized_event(msg.value)
                except Exception as e:
                    print(f"[scoring] événement ignoré : {e}")
        except Exception as e:
            print(f"[scoring] consommateur Kafka interrompu ({e}) — reconnexion dans 15 s")
            time.sleep(15)


# --------------------------------------------------------------------------- #
# Cycle de vie + endpoints
# --------------------------------------------------------------------------- #
@app.on_event("startup")
def startup():
    STATE["m1"] = _load(os.getenv("MODEL1_PATH"))
    STATE["m2"] = _load(os.getenv("MODEL2_PATH"))
    print(f"[scoring] modèles chargés : M1={bool(STATE['m1'])} M2={bool(STATE['m2'])}")
    try:
        from kafka import KafkaProducer
        # max_block_ms borné : .send() lève vite si le broker est injoignable
        # (au lieu de bufferiser en silence) → repli inline immédiat.
        STATE["producer"] = KafkaProducer(
            bootstrap_servers=KAFKA, acks=1, retries=1,
            max_block_ms=5000, request_timeout_ms=5000)
        connecte = _producer_connected()
        print(f"[scoring] producteur Kafka (broker={KAFKA}, connecté={connecte})")
        if not connecte:
            print(f"[scoring] ⚠ broker {KAFKA} injoignable → scoring INLINE automatique")
    except Exception as e:
        STATE["producer"] = None
        print(f"[scoring] producteur Kafka indisponible ({e}) → scoring INLINE actif")
    if DB_DSN:
        try:
            import psycopg2
            STATE["db"] = psycopg2.connect(DB_DSN)
            # Connexion PERSISTANTE : sans autocommit, psycopg2 ouvre une
            # transaction au premier SELECT et ne la referme jamais. Les chemins
            # de lecture (_verify_ingest, _alerte_dupliquee, /health/detailed)
            # laissaient donc le service en « idle in transaction » en
            # permanence, ce qui :
            #   — conserve un verrou ACCESS SHARE sur les tables lues, bloquant
            #     indéfiniment tout ALTER TABLE (une migration reste en attente,
            #     et fait alors la queue devant TOUTES les requêtes suivantes) ;
            #   — retient un snapshot et empêche l'autovacuum de faire son
            #     travail sur les tables chaudes.
            # Ici chaque écriture est une instruction unique suivie d'un
            # commit() : l'autocommit donne exactement la même sémantique, et
            # les commit()/rollback() existants deviennent des non-opérations
            # inoffensives.
            STATE["db"].autocommit = True
        except Exception as e:
            print(f"[scoring] connexion Postgres indisponible : {e}")
    threading.Thread(target=consume_loop, daemon=True).start()
    threading.Thread(target=_producer_watchdog, daemon=True).start()


class Features(BaseModel):
    features: dict
    entite: str | None = None
    tenant_id: str | None = None


@app.get("/health")
def health():
    """Healthcheck rapide (utilisé par Docker + load balancer)."""
    return {"status": "ok", "modele1": bool(STATE["m1"]), "modele2": bool(STATE["m2"])}


@app.get("/health/detailed")
def health_detailed():
    """Healthcheck approfondi — vérifie chaque service de la pile."""
    import urllib.request, ssl

    checks = {
        "scoring_service": {"status": "ok", "models": {"m1": bool(STATE["m1"]), "m2": bool(STATE["m2"])}},
    }
    overall = "ok"

    # Kafka
    try:
        from kafka.admin import KafkaAdminClient
        admin = KafkaAdminClient(bootstrap_servers=KAFKA, request_timeout_ms=3000)
        topics = admin.list_topics()
        admin.close()
        checks["kafka"] = {"status": "ok", "topics": len(topics)}
    except Exception as e:
        checks["kafka"] = {"status": "unavailable", "detail": str(e)[:80]}
        overall = "degraded"

    # TimescaleDB / PostgreSQL
    if STATE["db"]:
        try:
            with STATE["db"].cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM tenants")
                n = cur.fetchone()[0]
            checks["timescaledb"] = {"status": "ok", "tenants": n}
        except Exception as e:
            checks["timescaledb"] = {"status": "error", "detail": str(e)[:80]}
            overall = "degraded"
    else:
        checks["timescaledb"] = {"status": "not_configured"}

    # Wazuh Indexer
    try:
        import base64
        wazuh_url = os.getenv("WAZUH_API_URL", "https://localhost:9200")
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        creds = base64.b64encode(b"admin:admin").decode()
        req = urllib.request.Request(
            f"{wazuh_url}/_cluster/health",
            headers={"Authorization": f"Basic {creds}"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=3) as r:
            data = json.loads(r.read())
        checks["wazuh_indexer"] = {"status": "ok", "cluster_status": data.get("status")}
    except Exception as e:
        checks["wazuh_indexer"] = {"status": "unavailable", "detail": str(e)[:60]}

    return {
        "status":    overall,
        "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        "services":  checks,
    }


@app.post("/score/network")
def api_score_network(body: Features):
    r = score_network(body.features)
    return r or {"erreur": "Modèle 1 non chargé"}


@app.post("/score/user-day")
def api_score_userday(body: Features):
    r = score_userday(body.features)
    return r or {"erreur": "Modèle 2 non chargé"}


@app.post("/ingest")
async def ingest(request: Request):
    """
    Passerelle d'ingestion sécurisée.
    Vérifie : rate limit par IP, Bearer token (hash en base), signature HMAC-SHA256 du payload.
    """
    ip = _client_ip(request)
    _check_rate_limit(f"ingest:{ip}", INGEST_LIMIT_REQ, INGEST_LIMIT_WIN)

    authorization = request.headers.get("authorization", "")
    x_signature   = request.headers.get("x-signature", "")

    raw = await request.body()
    if request.headers.get("content-encoding") == "gzip":
        try:
            raw = gziplib.decompress(raw)
        except Exception:
            raise HTTPException(400, detail="Décompression gzip impossible")

    try:
        batch  = json.loads(raw)
        events = batch.get("events", [])
    except Exception:
        raise HTTPException(400, detail="JSON invalide")

    agent_id  = batch.get("agent_id", "")
    tenant_id = batch.get("tenant_id", "")

    if not _verify_ingest(raw, authorization, x_signature, agent_id):
        raise HTTPException(401, detail="Token ou signature invalide")

    # ── Routage robuste : Kafka si RÉELLEMENT connecté, sinon scoring inline ──
    # On ne route vers Kafka que si le producteur est connecté (bootstrap). Tout
    # événement NON confié à Kafka (broker injoignable, ou échec de publication)
    # est scoré inline juste après : la détection ne peut plus s'arrêter en
    # silence, quelle que soit la santé de Kafka/du consommateur.
    n = 0
    publies = set()
    if _producer_connected():
        meta = {
            "agent_id":  agent_id,
            "tenant_id": batch.get("tenant_id"),
            "host":      batch.get("host"),
        }
        for i, ev in enumerate(events):
            try:
                # Événement normalisé (kind + features) → topic de télémétrie
                # (consommé par le scoring). Événement brut → topic brut (SIEM).
                topic = T_TELEMETRY if isinstance(ev, dict) and "features" in ev else T_RAW
                STATE["producer"].send(topic, json.dumps({**meta, **ev}).encode("utf-8"))
                publies.add(i)
                n += 1
            except Exception as e:
                print(f"[ingestion] publication Kafka échouée (évt {i}) → repli scoring inline : {e}")

    # Scoring inline de tout ce qui n'a PAS été confié à Kafka (évite le double
    # traitement : les événements publiés seront scorés par le consommateur).
    alertes = 0
    for i, ev in enumerate(events):
        if i in publies:
            continue
        try:
            if process_normalized_event(ev, tenant_id, agent_id):
                alertes += 1
        except Exception as e:
            print(f"[ingestion] scoring inline échoué : {e}")

    # ── Corrélation SIEM : chaînes d'attaque MITRE ──────────────────────────
    # Indépendante du scoring par modèle : elle travaille sur les événements
    # BRUTS (processus, connexions, fichiers) et non sur les vecteurs de
    # features. Un lot peut donc alimenter les deux, l'un, ou aucun.
    try:
        alertes += correler_lot(events, tenant_id, batch.get("host", ""), agent_id)
    except Exception as e:
        print(f"[correlation] lot ignoré : {e}")

    # ── Métriques réelles de volumétrie ─────────────────────────────────────
    if tenant_id:
        record_metric(tenant_id, agent_id, "evenements_recus", len(events))
        if alertes:
            record_metric(tenant_id, agent_id, "alertes_emises", alertes)

    # Mettre à jour vu_le de l'agent en base
    if STATE["db"] and agent_id:
        try:
            token_hash = hashlib.sha256(authorization.removeprefix("Bearer ").encode()).hexdigest()
            with STATE["db"].cursor() as cur:
                # Battement de présence. `vu_le` est la source de vérité : les
                # lectures en dérivent le statut effectif (actif / hors_ligne),
                # ce qui fait redescendre un poste éteint tout seul.
                # `isole` est une décision humaine ou SOAR : un poste isolé qui
                # continue d'émettre doit RESTER isolé, sinon l'ingestion
                # annulerait silencieusement la décision de l'analyste.
                cur.execute(
                    "UPDATE agents SET vu_le = now(), "
                    "       statut = CASE WHEN statut = 'isole' THEN 'isole' ELSE 'actif' END "
                    " WHERE token_hash = %s",
                    (token_hash,)
                )
            STATE["db"].commit()
        except Exception:
            pass

    print(f"[ingestion] {agent_id} : {len(events)} événements, {n} publiés")
    return {"recus": len(events), "publies": n, "alertes": alertes}
