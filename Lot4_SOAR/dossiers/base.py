# -*- coding: utf-8 -*-
"""Contrat commun aux gestionnaires de dossiers d'enquête.

CE QUE NEXUS POUSSE, ET CE QU'IL NE POUSSE PAS
----------------------------------------------
NEXUS pousse des **alertes**, jamais des dossiers. L'escalade d'une alerte en
dossier d'enquête reste un geste d'analyste, dans IRIS. C'est la même ligne que
partout ailleurs dans ce projet : la plateforme mesure et propose, l'humain
qualifie.

Ouvrir automatiquement un dossier sur chaque anomalie produirait, en une
semaine, quelques centaines de dossiers vides que plus personne ne regarde —
la façon la plus sûre de rendre un outil d'enquête inutile.

L'IDEMPOTENCE EST DANS LE CONTRAT
---------------------------------
`ouvrir()` reçoit une `reference` qui identifie l'incident côté NEXUS. Un
gestionnaire DOIT s'en servir pour qu'un second appel sur la même référence ne
crée pas un second dossier, mais retrouve le premier. Un ouvrier qui reprend
après une panne ne sait pas si son dernier envoi est arrivé ; sans cette
garantie, il travaille en double et l'analyste aussi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Depot:
    """Ce qu'on envoie à l'outil d'enquête, figé au moment de la décision.

    Rejouer un envoi trois heures plus tard ne doit pas reconstruire un dossier
    avec des données qui ont bougé depuis : ce qui part est ce qu'on a vu.
    """

    reference: str
    """Identifiant de l'incident côté NEXUS. Clé d'idempotence."""

    titre: str
    description: str
    gravite: str
    """Nom de gravité, pas un identifiant : la table est propre à chaque
    instance de l'outil, et coder un numéro en dur rendrait le connecteur
    inutilisable ailleurs."""

    perimetre: str
    """UUID du périmètre supervisé. Traduit par le gestionnaire."""

    lien_retour: str = ""
    """Retour vers l'explicabilité NEXUS. Un analyste doit pouvoir remonter du
    dossier au calcul qui l'a déclenché, sinon il juge sur une conclusion."""

    contenu: dict[str, Any] = field(default_factory=dict)
    etiquettes: list[str] = field(default_factory=list)
    indicateurs: list[dict] = field(default_factory=list)
    """Indicateurs **observés** uniquement. On ne remonte pas une hypothèse au
    même rang qu'un fait."""
    actifs: list[dict] = field(default_factory=list)
    horodatage: str | None = None


@dataclass(frozen=True)
class Depose:
    """Résultat d'un dépôt. `identifiant` atteste l'envoi, pas un code HTTP."""

    identifiant: str
    deja_present: bool
    detail: str


class DossierIndisponible(Exception):
    """L'outil d'enquête ne répond pas, ou refuse le compte de service.

    Distincte d'un refus de contenu : ici on ne sait pas si le dépôt a eu lieu,
    et l'entrée doit rester dans la file.
    """


class DepotRefuse(Exception):
    """L'outil a répondu, et a refusé. Rejouer à l'identique ne changera rien.

    Ce cas ne doit PAS être retenté indéfiniment : une charge malformée
    resterait dans la file pour toujours, en masquant les envois valides
    derrière son report.
    """


@runtime_checkable
class GestionDossier(Protocol):
    """Ce que tout gestionnaire de dossiers doit savoir faire."""

    nom: str

    def ouvrir(self, depot: Depot) -> Depose:
        """Dépose l'alerte. Idempotent sur `depot.reference`."""

    def ajouter_observable(self, identifiant: str, observable: dict) -> bool:
        """Attache un indicateur à un dépôt existant."""

    def commenter(self, identifiant: str, texte: str) -> bool:
        """Ajoute une note lisible par l'analyste."""

    def cloturer(self, identifiant: str, motif: str) -> bool:
        """Marque le dépôt comme traité côté outil."""

    def etat(self) -> dict:
        """Santé de l'outil : joignable, version, compte de service accepté."""
