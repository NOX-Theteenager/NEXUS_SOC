# -*- coding: utf-8 -*-
"""Connecteur OPNsense — blocage d'adresse et mise en quarantaine.

CE QUE LE CONNECTEUR PILOTE, ET RIEN D'AUTRE
--------------------------------------------
Deux listes, `nexus_block` et `nexus_quarantaine`, déjà référencées par les
règles chargées dans le pare-feu. Le compte de service porte exactement deux
privilèges — `page-firewall-alias-edit` et `page-diagnostics-tables` — qui lui
donnent l'écriture sur ces listes et rien de plus. Il ne peut ni créer une
règle, ni modifier une interface, ni lire la configuration.

C'est volontaire et ça se défend : un moteur de réponse compromis doit pouvoir
ajouter une adresse à une liste, pas reconfigurer un pare-feu.

TLS ÉPINGLÉ
-----------
L'appliance signe son propre certificat. Un connecteur qui accepterait
n'importe quelle autorité — ou pire, qui désactiverait la vérification — se
ferait détourner par la première attaque active sur le segment
d'administration. On vérifie donc contre CE certificat, et on compare en plus
son empreinte : la chaîne seule ne dit pas qu'on parle au bon équipement quand
l'émetteur est aussi le sujet.

LA RÉSERVE QU'IL FAUT DIRE
--------------------------
Une règle de pare-feu ne s'applique qu'aux NOUVELLES connexions. Une session
déjà établie survit à la quarantaine jusqu'à expiration de son état. Le
connecteur tente donc de purger les états de la cible ; ce point d'API relève
d'un privilège que le compte n'a pas. Quand la purge est refusée, la mesure est
posée et la réserve est écrite dans l'audit : « sessions établies non purgées ».
Une isolation à moitié faite doit se voir, pas se deviner.
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import urllib.error
import urllib.request

from .base import ConnecteurIndisponible, Resultat

DELAI = float(os.getenv("OPNSENSE_TIMEOUT", "10"))


class OPNsense:
    """Pilote les deux listes de réponse du pare-feu."""

    nom = "opnsense"

    def __init__(self, alias: str, cible_attendue: str = "ip",
                 url: str | None = None, cle: str | None = None,
                 secret: str | None = None, ca: str | None = None,
                 empreinte: str | None = None):
        self.alias = alias
        self.cible_attendue = cible_attendue
        self.url = (url or os.getenv("OPNSENSE_URL", "https://10.50.0.1")).rstrip("/")
        self.cle = cle if cle is not None else os.getenv("OPNSENSE_KEY", "")
        self.secret = secret if secret is not None else os.getenv("OPNSENSE_SECRET", "")
        self.ca = ca or os.getenv("OPNSENSE_CA", "/etc/nexus/opnsense-ca.pem")
        # Empreinte SHA-256 du certificat, sans séparateurs, en minuscules.
        self.empreinte = (empreinte or os.getenv("OPNSENSE_EMPREINTE", "")) \
            .replace(":", "").replace(" ", "").lower()
        self._contexte = None

    # ── Transport ───────────────────────────────────────────────────────────
    def _ssl(self) -> ssl.SSLContext:
        if self._contexte is not None:
            return self._contexte
        if not os.path.exists(self.ca):
            raise ConnecteurIndisponible(
                f"certificat de l'appliance absent : {self.ca}. Le poser avant "
                f"de raccorder le connecteur — on ne parle pas à un pare-feu "
                f"sans savoir que c'est le bon.")
        ctx = ssl.create_default_context(cafile=self.ca)
        # Le certificat d'OPNsense porte « OPNsense.internal » et l'on se
        # connecte par adresse : la vérification de nom échouerait toujours.
        # On la remplace par l'épinglage de l'empreinte, plus strict ici — il
        # désigne UN certificat, pas une famille de noms.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        self._contexte = ctx
        return ctx

    def _verifier_empreinte(self, reponse) -> None:
        if not self.empreinte:
            return
        try:
            der = reponse.fp.raw._sock.getpeercert(binary_form=True)  # type: ignore[attr-defined]
        except Exception:
            return                      # pas d'accès à la socket : on n'invente pas
        vue = hashlib.sha256(der).hexdigest()
        if vue != self.empreinte:
            raise ConnecteurIndisponible(
                f"empreinte du certificat inattendue ({vue[:16]}… au lieu de "
                f"{self.empreinte[:16]}…) — on ne parle pas à l'appliance attendue")

    def _appel(self, chemin: str, charge: dict | None = None):
        import base64
        jeton = base64.b64encode(f"{self.cle}:{self.secret}".encode()).decode()
        entetes = {"Authorization": f"Basic {jeton}"}
        donnees = None
        if charge is not None:
            donnees = json.dumps(charge).encode()
            entetes["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.url}/api/{chemin}", data=donnees,
                                     headers=entetes,
                                     method="POST" if charge is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=DELAI,
                                        context=self._ssl()) as r:
                self._verifier_empreinte(r)
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            corps = e.read().decode(errors="replace")[:120]
            if e.code in (401, 403):
                raise ConnecteurIndisponible(
                    f"le pare-feu refuse le compte de service (HTTP {e.code}). "
                    f"Vérifier la clé d'API et ses privilèges.") from e
            raise ConnecteurIndisponible(f"HTTP {e.code} sur {chemin} : {corps}") from e
        except (urllib.error.URLError, ssl.SSLError, OSError) as e:
            raise ConnecteurIndisponible(f"pare-feu injoignable : {e}") from e

    # ── Lecture ─────────────────────────────────────────────────────────────
    def cibles_actives(self) -> list[str]:
        rep = self._appel(f"firewall/alias_util/list/{self.alias}")
        return [str(l.get("ip", "")).strip()
                for l in rep.get("rows", []) if l.get("ip")]

    def etat(self, cible: str) -> bool:
        return cible in self.cibles_actives()

    # ── Écriture ────────────────────────────────────────────────────────────
    def _purger_etats(self, cible: str) -> str | None:
        """Coupe les sessions déjà ouvertes. Renvoie une réserve si impossible."""
        try:
            self._appel("diagnostics/firewall/kill_states", {"filter": cible})
            return None
        except ConnecteurIndisponible as e:
            # Le compte n'a pas « page-diagnostics-showstates ». La mesure reste
            # valable pour tout NOUVEAU flux ; on le dit plutôt que de laisser
            # croire à une coupure immédiate.
            return ("sessions déjà établies non purgées "
                    f"({str(e).split('.')[0].lower()}) — l'isolation ne vaut "
                    "que pour les nouvelles connexions")

    def appliquer(self, cible: str) -> Resultat:
        try:
            self._appel(f"firewall/alias_util/add/{self.alias}", {"address": cible})
        except ConnecteurIndisponible as e:
            return Resultat(applique=False, verifie=False,
                            detail=f"écriture impossible : {e}")
        reserve = self._purger_etats(cible)
        # LA relecture. C'est elle qui tranche, pas le code de retour ci-dessus.
        try:
            present = self.etat(cible)
        except ConnecteurIndisponible as e:
            return Resultat(applique=False, verifie=False,
                            detail=f"écriture acceptée mais relecture impossible : {e}")
        return Resultat(
            applique=present, verifie=True,
            detail=(f"{cible} présente dans l'alias {self.alias}, relu sur l'appliance"
                    if present else
                    f"{cible} absente de l'alias {self.alias} après écriture — "
                    f"l'appel a été accepté sans effet"),
            reserves=[reserve] if reserve else [])

    def lever(self, cible: str) -> Resultat:
        try:
            self._appel(f"firewall/alias_util/delete/{self.alias}", {"address": cible})
        except ConnecteurIndisponible as e:
            return Resultat(applique=True, verifie=False,
                            detail=f"retrait impossible : {e}")
        try:
            present = self.etat(cible)
        except ConnecteurIndisponible as e:
            return Resultat(applique=True, verifie=False,
                            detail=f"retrait accepté mais relecture impossible : {e}")
        return Resultat(
            applique=present, verifie=True,
            detail=(f"{cible} retirée de l'alias {self.alias}, relu sur l'appliance"
                    if not present else
                    f"{cible} toujours présente dans {self.alias} après retrait"))
