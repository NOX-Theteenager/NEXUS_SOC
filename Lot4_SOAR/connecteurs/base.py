# -*- coding: utf-8 -*-
"""Contrat commun aux connecteurs de réponse.

UN CONNECTEUR NE DIT JAMAIS « FAIT » PARCE QU'IL A REÇU UN 200
--------------------------------------------------------------
C'est la règle qui structure tout ce module. Un appel d'API peut réussir sans
que la mesure soit en vigueur : OPNsense accepte une adresse dans un alias que
la règle n'utilise pas ; OpenLDAP accepte `nsAccountLock` puis l'ignore
silencieusement, parce que cet attribut appartient à 389-DS. Dans les deux cas
la console afficherait « exécutée » sur une machine qui communique encore.

Chaque connecteur doit donc RELIRE l'état après avoir écrit, et c'est cette
relecture — pas le code de retour — qui décide de `Resultat.applique`.

TROIS ÉTATS, PAS DEUX
---------------------
    applique=True,  verifie=True   la mesure est en vigueur, on l'a constaté
    applique=False, verifie=True   elle ne l'est pas, on l'a constaté
    applique=?,     verifie=False  on n'a pas pu constater — l'équipement n'a
                                   pas répondu, ou a refusé la relecture

Le troisième cas est le plus important. Il ne doit jamais être confondu avec le
premier : ne pas savoir n'est pas la même chose que savoir que oui. La
plateforme laisse alors l'action en `non_executee` et affiche la commande
manuelle, comme si aucun connecteur n'existait.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Resultat:
    """Ce qu'un connecteur a réellement constaté."""

    applique: bool
    """La mesure est-elle en vigueur ? N'a de sens que si `verifie` est vrai."""

    verifie: bool
    """La relecture a-t-elle pu être faite ? Faux = on ne sait pas."""

    detail: str
    """Phrase destinée à `soar_audit.execution_note`, lue par un humain."""

    reserves: list[str] = field(default_factory=list)
    """Ce que la mesure ne couvre PAS, alors qu'on pourrait le croire.

    Exemple : l'alias est bien posé, mais les sessions déjà établies n'ont pas
    été purgées faute de privilège. La mesure est réelle et incomplète ; taire
    la seconde moitié serait mentir.
    """

    def resume(self) -> str:
        if not self.verifie:
            return f"NON VÉRIFIÉ — {self.detail}"
        etat = "en vigueur" if self.applique else "sans effet"
        texte = f"{etat} — {self.detail}"
        if self.reserves:
            texte += " · réserves : " + " ; ".join(self.reserves)
        return texte


class ConnecteurIndisponible(Exception):
    """L'équipement n'est pas joignable, ou refuse le compte de service.

    Distincte d'un échec d'application : ici on ne sait rien de l'état de la
    cible, et c'est exactement ce qu'il faut remonter.
    """


@runtime_checkable
class Connecteur(Protocol):
    """Ce que tout connecteur de réponse doit savoir faire."""

    nom: str
    """Identifiant court, écrit dans l'audit : « opnsense », « ldap »."""

    cible_attendue: str
    """Type de cible accepté : « ip », « compte », « hote »."""

    def appliquer(self, cible: str) -> Resultat:
        """Pose la mesure, PUIS relit pour confirmer."""

    def lever(self, cible: str) -> Resultat:
        """Retire la mesure, PUIS relit pour confirmer.

        `applique` vaut alors False quand la levée a réussi : la mesure n'est
        plus en vigueur.
        """

    def etat(self, cible: str) -> bool:
        """La mesure est-elle en vigueur sur cette cible ?

        Lève `ConnecteurIndisponible` si la question ne peut pas être posée.
        """

    def cibles_actives(self) -> list[str]:
        """Toutes les cibles sur lesquelles la mesure est en vigueur.

        Sert à la réconciliation au démarrage : comparer ce que l'équipement
        applique à ce que la plateforme croit avoir décidé.
        """
