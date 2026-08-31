# -*- coding: utf-8 -*-
"""Connecteur annuaire — gel et dégel de compte par la surcouche ppolicy.

POURQUOI `pwdAccountLockedTime` ET PAS AUTRE CHOSE
--------------------------------------------------
`nsAccountLock` appartient à 389-DS et FreeIPA. Sur OpenLDAP, l'attribut est
accepté puis **ignoré** : le compte paraîtrait gelé sans l'être, et la console
afficherait « exécutée » sur une identité toujours utilisable. C'est le type
d'erreur qu'aucun code de retour ne signale — d'où la relecture systématique.

`pwdAccountLockedTime` est l'attribut de la surcouche ppolicy, standard
OpenLDAP, déployée par `lab-cenadi/scripts/vm-app-gov-annuaire.sh`. La valeur
`000001010000Z` est la convention d'un verrouillage sans date de levée.

ON SUSPEND, ON NE SUPPRIME PAS
------------------------------
Le compte gelé reste présent et lisible pendant toute l'enquête. Les ACL de
l'annuaire limitent d'ailleurs le compte de service à ce seul attribut : il ne
peut ni supprimer un compte ni changer un mot de passe, et l'annuaire le lui
refuse avec un code 50. Le périmètre n'est pas une intention écrite dans un
document, c'est une ACL qui dit non.

CE QUE LA VÉRIFICATION COUVRE, ET CE QU'ELLE NE COUVRE PAS
----------------------------------------------------------
Le connecteur relit l'attribut sur l'entrée. Il ne rejoue PAS d'authentification
avec le mot de passe de l'utilisateur — il ne le connaît pas, et il serait
malsain qu'il le connaisse. La preuve par le refus d'authentification appartient
à la recette `07-preuve-gel-annuaire.sh`, qui dispose du mot de passe de
démonstration. C'est une limite du connecteur, pas un oubli.
"""
from __future__ import annotations

import os

from .base import ConnecteurIndisponible, Resultat

VERROU = "000001010000Z"


class AnnuairePpolicy:
    """Gèle et dégèle une identité dans l'annuaire souverain."""

    nom = "ldap"
    cible_attendue = "compte"

    def __init__(self, uri: str | None = None, base_dn: str | None = None,
                 soar_dn: str | None = None, mot_de_passe: str | None = None,
                 ou_agents: str = "ou=agents"):
        self.uri = uri or os.getenv("LDAP_URI", "ldap://10.50.20.20:389")
        self.base_dn = base_dn or os.getenv("LDAP_BASE_DN", "dc=cenadi,dc=local")
        self.soar_dn = soar_dn or os.getenv(
            "LDAP_SOAR_DN", f"cn=nexus-soar,ou=services,{self.base_dn}")
        self.mot_de_passe = (mot_de_passe if mot_de_passe is not None
                             else os.getenv("LDAP_SOAR_PASSWORD", ""))
        self.ou_agents = ou_agents

    def dn_de(self, uid: str) -> str:
        return f"uid={uid},{self.ou_agents},{self.base_dn}"

    # ── Connexion ───────────────────────────────────────────────────────────
    def _ouvrir(self):
        try:
            from ldap3 import ALL, Connection, Server
            from ldap3.core.exceptions import LDAPException
        except ImportError as e:      # pragma: no cover
            raise ConnecteurIndisponible(
                "ldap3 n'est pas installé dans l'environnement du cœur SOC") from e
        if not self.mot_de_passe:
            raise ConnecteurIndisponible(
                "LDAP_SOAR_PASSWORD absent : le compte de service ne peut pas "
                "s'authentifier auprès de l'annuaire")
        try:
            serveur = Server(self.uri, get_info=ALL, connect_timeout=6)
            c = Connection(serveur, user=self.soar_dn, password=self.mot_de_passe,
                           auto_bind=True, raise_exceptions=False)
            if not c.bound:
                raise ConnecteurIndisponible(
                    f"l'annuaire refuse le compte de service : {c.result}")
            return c
        except LDAPException as e:
            raise ConnecteurIndisponible(f"annuaire injoignable : {e}") from e

    # ── Lecture ─────────────────────────────────────────────────────────────
    def etat(self, uid: str) -> bool:
        c = self._ouvrir()
        try:
            trouve = c.search(self.dn_de(uid), "(objectClass=*)",
                              attributes=["pwdAccountLockedTime"])
            if not trouve or not c.entries:
                raise ConnecteurIndisponible(
                    f"compte « {uid} » introuvable dans l'annuaire")
            valeurs = c.entries[0].pwdAccountLockedTime.values
            return bool(valeurs)
        finally:
            c.unbind()

    def cibles_actives(self) -> list[str]:
        c = self._ouvrir()
        try:
            c.search(f"{self.ou_agents},{self.base_dn}",
                     "(pwdAccountLockedTime=*)", attributes=["uid"])
            return [str(e.uid.value) for e in c.entries]
        finally:
            c.unbind()

    # ── Écriture ────────────────────────────────────────────────────────────
    def _modifier(self, uid: str, operation, valeur):
        from ldap3 import MODIFY_DELETE, MODIFY_REPLACE  # noqa: F401
        c = self._ouvrir()
        try:
            ok = c.modify(self.dn_de(uid),
                          {"pwdAccountLockedTime": [(operation, valeur)]})
            return ok, dict(c.result or {})
        finally:
            c.unbind()

    def appliquer(self, uid: str) -> Resultat:
        from ldap3 import MODIFY_REPLACE
        try:
            ok, resultat = self._modifier(uid, MODIFY_REPLACE, [VERROU])
        except ConnecteurIndisponible as e:
            return Resultat(applique=False, verifie=False,
                            detail=f"gel impossible : {e}")
        if not ok:
            # Un refus d'ACL arrive ici : c'est un échec net, pas une incertitude.
            return Resultat(
                applique=False, verifie=True,
                detail=f"l'annuaire a refusé le gel : "
                       f"{resultat.get('description')} ({resultat.get('result')})")
        try:
            gele = self.etat(uid)
        except ConnecteurIndisponible as e:
            return Resultat(applique=False, verifie=False,
                            detail=f"modification acceptée mais relecture impossible : {e}")
        return Resultat(
            applique=gele, verifie=True,
            detail=(f"pwdAccountLockedTime posé sur {uid}, relu dans l'annuaire"
                    if gele else
                    f"pwdAccountLockedTime absent de {uid} après écriture — "
                    f"attribut accepté sans effet"),
            reserves=[] if gele else [
                "vérifier que la surcouche ppolicy est bien active sur la base"])

    def lever(self, uid: str) -> Resultat:
        from ldap3 import MODIFY_DELETE
        try:
            ok, resultat = self._modifier(uid, MODIFY_DELETE, [])
        except ConnecteurIndisponible as e:
            return Resultat(applique=True, verifie=False,
                            detail=f"dégel impossible : {e}")
        if not ok and resultat.get("result") != 16:   # 16 = attribut déjà absent
            return Resultat(
                applique=True, verifie=True,
                detail=f"l'annuaire a refusé le dégel : "
                       f"{resultat.get('description')} ({resultat.get('result')})")
        try:
            gele = self.etat(uid)
        except ConnecteurIndisponible as e:
            return Resultat(applique=True, verifie=False,
                            detail=f"modification acceptée mais relecture impossible : {e}")
        return Resultat(
            applique=gele, verifie=True,
            detail=(f"pwdAccountLockedTime retiré de {uid}, relu dans l'annuaire"
                    if not gele else
                    f"{uid} toujours verrouillé après le dégel"))
