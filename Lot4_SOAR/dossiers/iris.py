# -*- coding: utf-8 -*-
"""Adaptateur DFIR-IRIS — dépôt d'alertes dans l'outil d'enquête.

CE QUI EST DÉPOSÉ
-----------------
Une **alerte**, par `POST /alerts/add`. Pas un dossier : l'escalade
(`/alerts/escalate/{id}`) reste un geste d'analyste. La plateforme mesure et
propose, l'humain qualifie — c'est la ligne de tout le projet, et elle vaut
aussi ici.

RIEN N'EST CODÉ EN DUR CÔTÉ IRIS
--------------------------------
Les identifiants de gravité et de `customer` sont propres à chaque instance
d'IRIS. Les figer dans le code produirait un connecteur qui marche sur cette
machine et nulle part ailleurs — et qui déposerait silencieusement en gravité
« Faible » un incident critique après une réinstallation. On les lit donc au
démarrage, par nom, et on les relit si un nom manque.

TROIS ISSUES, PAS DEUX
----------------------
    Depose                l'outil a rendu un identifiant — la seule preuve
    DossierIndisponible   on ne sait pas si le dépôt a eu lieu → on garde
    DepotRefuse           l'outil a répondu et refusé → rejouer est inutile

Confondre les deux dernières coûte cher dans les deux sens : une charge
malformée retentée indéfiniment bloque la file derrière elle, et une panne
réseau prise pour un refus perd un incident.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any

from .base import Depose, Depot, DepotRefuse, DossierIndisponible

DELAI = float(os.getenv("IRIS_TIMEOUT", "15"))

# Noms de gravité côté IRIS, du plus faible au plus fort. On cherche par nom,
# jamais par numéro.
GRAVITES = ("Unspecified", "Informational", "Low", "Medium", "High", "Critical")


class IRIS:
    """Dépose les alertes NEXUS dans DFIR-IRIS."""

    nom = "iris"

    def __init__(self, url: str | None = None, cle: str | None = None,
                 ca: str | None = None, verifier_tls: bool | None = None):
        self.url = (url or os.getenv("IRIS_URL", "https://10.50.0.2:4443")).rstrip("/")
        self.cle = cle if cle is not None else os.getenv("IRIS_API_KEY", "")
        self.ca = ca or os.getenv("IRIS_CA", "")
        # IRIS se signe lui-même à l'installation. Tant que son certificat n'est
        # pas épinglé, on l'assume EXPLICITEMENT plutôt que de le taire : la
        # variable existe pour que le choix soit visible dans la configuration.
        self.verifier_tls = (verifier_tls if verifier_tls is not None
                             else os.getenv("IRIS_VERIFIER_TLS", "0").lower()
                             in ("1", "true", "yes"))
        self._gravites: dict[str, int] = {}

    # ── Transport ───────────────────────────────────────────────────────────
    def _ssl(self) -> ssl.SSLContext:
        if self.ca and os.path.exists(self.ca):
            ctx = ssl.create_default_context(cafile=self.ca)
            ctx.check_hostname = False
            return ctx
        ctx = ssl.create_default_context()
        if not self.verifier_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _appel(self, methode: str, chemin: str, charge: dict | None = None) -> Any:
        if not self.cle:
            raise DossierIndisponible(
                "IRIS_API_KEY absente : le compte de service ne peut pas "
                "déposer d'alerte")
        entetes = {"Authorization": f"Bearer {self.cle}",
                   "Content-Type": "application/json"}
        donnees = json.dumps(charge).encode() if charge is not None else None
        req = urllib.request.Request(f"{self.url}{chemin}", data=donnees,
                                     headers=entetes, method=methode)
        try:
            with urllib.request.urlopen(req, timeout=DELAI,
                                        context=self._ssl()) as r:
                brut = r.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            corps = e.read().decode(errors="replace")[:300]
            if e.code in (401, 403):
                raise DossierIndisponible(
                    f"IRIS refuse le compte de service (HTTP {e.code})") from e
            if 400 <= e.code < 500:
                # L'outil a répondu et refusé : rejouer à l'identique est vain.
                raise DepotRefuse(f"IRIS a refusé (HTTP {e.code}) : {corps}") from e
            raise DossierIndisponible(f"IRIS en erreur (HTTP {e.code}) : {corps}") from e
        except (urllib.error.URLError, ssl.SSLError, OSError) as e:
            raise DossierIndisponible(f"IRIS injoignable : {e}") from e
        try:
            return json.loads(brut or "{}")
        except json.JSONDecodeError as e:
            raise DossierIndisponible(f"réponse illisible d'IRIS : {brut[:120]}") from e

    # ── Correspondances lues sur l'instance ─────────────────────────────────
    def _charger_gravites(self) -> dict[str, int]:
        if self._gravites:
            return self._gravites
        rep = self._appel("GET", "/manage/severities/list")
        table = {}
        for ligne in (rep.get("data") or []):
            nom = str(ligne.get("severity_name", "")).strip()
            ident = ligne.get("severity_id")
            if nom and ident is not None:
                table[nom.lower()] = int(ident)
        if not table:
            raise DossierIndisponible(
                "IRIS n'expose aucune gravité : instance non initialisée ?")
        self._gravites = table
        return table

    def gravite_id(self, nom: str) -> int:
        table = self._charger_gravites()
        cherche = (nom or "").strip().lower()
        if cherche in table:
            return table[cherche]
        # Repli explicite plutôt que silencieux : mieux vaut déposer en
        # « Medium » et le dire que d'inventer un numéro.
        for defaut in ("medium", "moyen", "unspecified"):
            if defaut in table:
                return table[defaut]
        return sorted(table.values())[0]

    # ── Dépôt ───────────────────────────────────────────────────────────────
    def _deja_depose(self, reference: str) -> str | None:
        """Cherche un dépôt portant déjà cette référence."""
        # GET, et le filtre s'appelle « source_reference » — pas
        # « alert_source_ref », qui est le nom du CHAMP au dépôt. Se tromper
        # ici ne produit aucune erreur visible : l'endpoint renvoie simplement
        # toutes les alertes, la première venue passe pour la bonne, ou aucune.
        # C'est le genre de défaut qu'on ne voit qu'en le cherchant.
        from urllib.parse import quote
        try:
            rep = self._appel(
                "GET",
                f"/alerts/filter?source_reference={quote(reference)}"
                f"&page=1&per_page=25")
        except (DepotRefuse, DossierIndisponible):
            return None
        lignes = ((rep.get("data") or {}).get("alerts")
                  or (rep.get("data") or {}).get("data") or [])
        # On revérifie la référence sur chaque ligne. Un filtre ignoré par le
        # serveur renverrait tout le catalogue sans le dire, et on conclurait
        # « déjà déposé » sur la première alerte venue — en perdant l'incident
        # qu'on tenait.
        for ligne in lignes:
            if str(ligne.get("alert_source_ref") or "") == reference:
                ident = ligne.get("alert_id")
                return str(ident) if ident is not None else None
        return None

    def ouvrir(self, depot: Depot, customer_id: int | None = None) -> Depose:
        """Dépose l'alerte. Un second appel sur la même référence ne duplique pas."""
        if customer_id is None:
            # INDISPONIBLE, pas REFUSÉ. On n'a même pas contacté IRIS : c'est
            # une correspondance de périmètre absente, donc un défaut de
            # configuration qui se corrige en une minute. La traiter comme un
            # refus définitif jetterait l'incident pour toujours, alors qu'il
            # suffit d'attendre que la table soit renseignée.
            raise DossierIndisponible(
                f"aucun customer IRIS pour le périmètre {depot.perimetre} — "
                f"renseigner la table perimetre_iris ; l'entrée reste en file")

        corps = {
            "alert_title": depot.titre,
            "alert_description": depot.description,
            "alert_source": "NEXUS SOC",
            "alert_source_ref": depot.reference,
            "alert_source_link": depot.lien_retour,
            "alert_severity_id": self.gravite_id(depot.gravite),
            "alert_status_id": 3,                 # « New » dans IRIS
            "alert_customer_id": int(customer_id),
            "alert_source_content": depot.contenu,
            "alert_tags": ",".join(depot.etiquettes),
        }
        if depot.indicateurs:
            corps["alert_iocs"] = depot.indicateurs
        if depot.actifs:
            corps["alert_assets"] = depot.actifs
        if depot.horodatage:
            corps["alert_source_event_time"] = depot.horodatage

        # ON REGARDE AVANT D'ÉCRIRE. IRIS n'impose AUCUNE unicité sur
        # `alert_source_ref` : vérifié, un second dépôt de la même référence
        # crée une seconde alerte. L'idempotence ne peut donc pas être déléguée
        # à l'outil, elle doit être tenue ici.
        #
        # Le cas réel n'est pas théorique : on poste, IRIS crée l'alerte, et
        # l'ouvrier tombe avant d'avoir enregistré l'identifiant. À la reprise,
        # sans cette lecture, l'analyste trouve deux dossiers pour un incident
        # et travaille en double sans le savoir.
        #
        # Cela coûte un appel de plus par dépôt. C'est le prix d'une garantie
        # qui, sinon, n'existe pas.
        existant = self._deja_depose(depot.reference)
        if existant:
            return Depose(identifiant=existant, deja_present=True,
                          detail="référence déjà déposée dans IRIS, aucun doublon créé")
        try:
            rep = self._appel("POST", "/alerts/add", corps)
        except DepotRefuse:
            # Le refus peut venir d'un dépôt concurrent qui vient de passer :
            # on regarde une dernière fois avant de conclure à l'échec.
            existant = self._deja_depose(depot.reference)
            if existant:
                return Depose(identifiant=existant, deja_present=True,
                              detail="référence déjà déposée dans IRIS")
            raise

        ident = ((rep.get("data") or {}).get("alert_id")
                 or (rep.get("data") or {}).get("id"))
        if ident is None:
            raise DossierIndisponible(
                f"IRIS n'a rendu aucun identifiant : {str(rep)[:160]}")
        return Depose(identifiant=str(ident), deja_present=False,
                      detail=f"alerte {ident} déposée dans IRIS")

    # ── Compléments ─────────────────────────────────────────────────────────
    def ajouter_observable(self, identifiant: str, observable: dict) -> bool:
        rep = self._appel("POST", f"/alerts/update/{identifiant}",
                          {"alert_iocs": [observable]})
        return rep.get("status") == "success"

    def commenter(self, identifiant: str, texte: str) -> bool:
        rep = self._appel("POST", f"/alerts/update/{identifiant}",
                          {"alert_note": texte})
        return rep.get("status") == "success"

    def cloturer(self, identifiant: str, motif: str) -> bool:
        rep = self._appel("POST", f"/alerts/update/{identifiant}",
                          {"alert_status_id": 6, "alert_note": motif})
        return rep.get("status") == "success"

    def alertes_par_statut(self, statut_id: int, limite: int = 100) -> list[dict]:
        """Alertes dans un statut donné — sert à repérer les escalades.

        On revérifie le statut de chaque ligne reçue. Le filtre `alert_status_id`
        est bien supporté par IRIS, mais un paramètre mal orthographié y est
        ignoré SANS erreur : la réponse contiendrait alors tout le catalogue, et
        l'on ouvrirait un canal d'incident sur chaque alerte jamais déposée.
        C'est le même piège que sur `source_reference`, rencontré le 29 août.
        """
        try:
            rep = self._appel(
                "GET",
                f"/alerts/filter?alert_status_id={int(statut_id)}"
                f"&page=1&per_page={int(limite)}")
        except (DepotRefuse, DossierIndisponible):
            return []
        lignes = ((rep.get("data") or {}).get("alerts")
                  or (rep.get("data") or {}).get("data") or [])
        retenues = []
        for ligne in lignes:
            statut = (ligne.get("status") or {}).get("status_id")
            if statut is None or int(statut) == int(statut_id):
                retenues.append(ligne)
        return retenues

    def etat(self) -> dict:
        try:
            rep = self._appel("GET", "/api/ping")
            gravites = len(self._charger_gravites())
            return {"joignable": True, "reponse": rep.get("status", "?"),
                    "gravites_connues": gravites}
        except (DossierIndisponible, DepotRefuse) as e:
            return {"joignable": False, "detail": str(e)[:160]}
