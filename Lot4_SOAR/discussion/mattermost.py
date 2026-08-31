# -*- coding: utf-8 -*-
"""Adaptateur Mattermost — ouverture et animation des canaux d'incident.

POURQUOI UN COMPTE DE ROBOT ET PAS UN COMPTE D'UTILISATEUR
-----------------------------------------------------------
Un robot ne peut pas lire les messages privés, ne compte pas dans les licences,
et surtout : ses publications sont visiblement signées « BOT ». Personne ne
confond un résumé automatique avec l'avis d'un collègue — ce qui compte quand
la conversation servira à justifier une décision.

CE QUE CE MODULE NE FAIT PAS
----------------------------
Il ne lit rien. NEXUS publie dans le canal, il ne s'abonne pas à ce qui s'y
dit : la discussion appartient aux humains, et une plateforme qui interpréterait
les échanges d'une cellule de crise sortirait de son rôle.

TOUTES LES ERREURS SONT AVALÉES, SAUF À L'OUVERTURE
---------------------------------------------------
`publier()` renvoie False au lieu de lever : un message perdu ne doit jamais
remonter jusqu'à un chemin de détection. `ouvrir_canal()` lève en revanche, car
l'appelant doit pouvoir distinguer « canal ouvert » de « je n'ai pas pu » pour
décider s'il réessaiera.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request

from .base import Canal, Discussion, DiscussionIndisponible, Incident  # noqa: F401

DELAI = float(os.getenv("MATTERMOST_TIMEOUT", "8"))


class Mattermost:
    """Publie les incidents dans une équipe Mattermost auto-hébergée."""

    nom = "mattermost"

    def __init__(self, url: str | None = None, jeton: str | None = None,
                 equipe: str | None = None):
        self.url = (url or os.getenv("MATTERMOST_URL",
                                     "http://10.50.0.2:8065")).rstrip("/")
        self.jeton = jeton if jeton is not None else os.getenv("MATTERMOST_TOKEN", "")
        self.equipe = equipe or os.getenv("MATTERMOST_EQUIPE", "cenadi-soc")
        self._equipe_id: str | None = None

    # ── Transport ───────────────────────────────────────────────────────────
    def _appel(self, methode: str, chemin: str, charge: dict | None = None):
        donnees = json.dumps(charge).encode() if charge is not None else None
        entetes = {"Authorization": f"Bearer {self.jeton}"}
        if donnees:
            entetes["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.url}/api/v4{chemin}", data=donnees,
                                     headers=entetes, method=methode)
        contexte = None
        if self.url.startswith("https"):
            contexte = ssl.create_default_context()
            if os.getenv("MATTERMOST_VERIFIER_TLS", "1") not in ("1", "true", "yes"):
                contexte.check_hostname = False
                contexte.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=DELAI, context=contexte) as r:
                corps = r.read().decode()
                return json.loads(corps) if corps else {}
        except urllib.error.HTTPError as e:
            corps = e.read().decode(errors="replace")[:200]
            raise DiscussionIndisponible(f"HTTP {e.code} sur {chemin} : {corps}") from e
        except (urllib.error.URLError, OSError) as e:
            raise DiscussionIndisponible(f"Mattermost injoignable : {e}") from e

    def _id_equipe(self) -> str:
        if self._equipe_id:
            return self._equipe_id
        rep = self._appel("GET", f"/teams/name/{self.equipe}")
        self._equipe_id = rep.get("id", "")
        if not self._equipe_id:
            raise DiscussionIndisponible(
                f"équipe « {self.equipe} » introuvable dans Mattermost")
        return self._equipe_id

    # ── Canaux ──────────────────────────────────────────────────────────────
    @staticmethod
    def nom_canal(incident: Incident, horodatage) -> str:
        """`incident-AAAAMMJJ-<8 caractères>` : datable et unique.

        La date en clair permet de retrouver un canal des mois plus tard sans
        recherche ; le fragment de référence garantit qu'aucun incident n'en
        écrase un autre le même jour.
        """
        court = (incident.reference or "").replace("-", "")[:8] or "anonyme"
        return f"incident-{horodatage:%Y%m%d}-{court}"

    def ouvrir_canal(self, incident: Incident) -> Canal:
        from datetime import datetime, timezone
        nom = self.nom_canal(incident, datetime.now(timezone.utc))
        equipe = self._id_equipe()

        # On regarde AVANT de créer : rouvrir un canal pour un incident déjà
        # suivi disperserait la conversation entre deux endroits, ce qui est
        # exactement le contraire du but.
        try:
            existant = self._appel("GET", f"/teams/{equipe}/channels/name/{nom}")
            if existant.get("id"):
                return Canal(identifiant=existant["id"], nom=nom, deja_present=True,
                             lien=f"{self.url}/{self.equipe}/channels/{nom}")
        except DiscussionIndisponible:
            pass                      # 404 attendu quand le canal n'existe pas

        cree = self._appel("POST", "/channels", {
            "team_id": equipe,
            "name": nom,
            "display_name": f"Incident {incident.entite} — {incident.risque}",
            "purpose": incident.titre[:250],
            # « P » = privé. Un incident n'a pas à être lisible par toute
            # l'administration avant même d'être qualifié.
            "type": "P",
        })
        return Canal(identifiant=cree.get("id", ""), nom=nom, deja_present=False,
                     lien=f"{self.url}/{self.equipe}/channels/{nom}")

    # ── Messages ────────────────────────────────────────────────────────────
    def publier(self, canal: str, texte: str) -> bool:
        try:
            self._appel("POST", "/posts", {"channel_id": canal, "message": texte})
            return True
        except DiscussionIndisponible:
            # Volontairement avalé. Un message perdu ne doit jamais remonter
            # jusqu'à un chemin dont dépend la détection.
            return False

    @staticmethod
    def message_initial(incident: Incident) -> str:
        """Le message d'ouverture, lisible en dix secondes.

        Qui arrive doit comprendre de quoi il s'agit et savoir où aller. D'où
        les deux liens : l'enquête, et le calcul qui a déclenché l'alerte —
        pour qu'on puisse contester la conclusion plutôt que la subir.
        """
        lignes = [
            f"#### {incident.titre}",
            "",
            f"**Périmètre** {incident.perimetre}  ·  **Entité** `{incident.entite}`  "
            f"·  **Risque** {incident.risque}",
            "",
            incident.resume or "_Aucun résumé fourni._",
        ]
        if incident.etiquettes:
            lignes += ["", "**Techniques** " + " ".join(f"`{e}`"
                                                        for e in incident.etiquettes)]
        liens = []
        if incident.lien_dossier:
            liens.append(f"[Dossier d'enquête]({incident.lien_dossier})")
        if incident.lien_console:
            liens.append(f"[Explicabilité dans NEXUS]({incident.lien_console})")
        if liens:
            lignes += ["", " · ".join(liens)]
        lignes += ["", "_Publié par NEXUS SOC. Ce canal sert à la coordination ; "
                       "la trace de l'enquête reste dans le dossier._"]
        return "\n".join(lignes)

    # ── Santé ───────────────────────────────────────────────────────────────
    def etat(self) -> dict:
        try:
            self._appel("GET", "/system/ping")
            moi = self._appel("GET", "/users/me")
            return {"joignable": True, "compte": moi.get("username"),
                    "robot": bool(moi.get("is_bot"))}
        except DiscussionIndisponible as e:
            return {"joignable": False, "detail": str(e)[:160]}
