# -*- coding: utf-8 -*-
"""Contrat commun aux espaces de discussion d'incident.

CE QUE LA DISCUSSION APPORTE, ET CE QU'ELLE NE REMPLACE PAS
-----------------------------------------------------------
Un dossier d'enquête garde la trace ; un canal de discussion porte la
coordination. Les deux ne se remplacent pas : personne ne coordonne une
intervention à trois en s'écrivant des commentaires dans un formulaire, et
personne ne reconstitue un incident six mois plus tard en relisant un fil de
messages.

Le canal n'est donc PAS la source de vérité. Il contient un résumé et des
liens ; le fait reste dans NEXUS, l'enquête dans IRIS.

UNE PANNE ICI NE DOIT RIEN BLOQUER
----------------------------------
C'est la règle qui structure ce module. Mattermost est un outil de confort :
s'il tombe, l'alerte doit continuer d'être détectée, le dossier d'être ouvert,
et la réponse d'être exécutée. Aucun appel de ce module n'est jamais placé sur
un chemin dont dépend la détection.

Concrètement, `publier()` ne lève pas quand l'outil est absent : il renvoie
False, et l'appelant consigne. Un SOC qui s'arrête parce que sa messagerie est
en panne est un SOC qui a confondu l'accessoire et l'essentiel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Canal:
    """Un canal d'incident, une fois ouvert."""

    identifiant: str
    nom: str
    """Nom technique, `incident-AAAAMMJJ-<id court>`. Il porte la date pour
    qu'un canal se retrouve des mois plus tard sans passer par une recherche."""
    deja_present: bool
    lien: str = ""


@dataclass(frozen=True)
class Incident:
    """Ce qu'on annonce dans le canal à son ouverture.

    Le message initial doit permettre à quelqu'un qui arrive de comprendre en
    dix secondes de quoi il s'agit, et de savoir où aller pour en savoir plus.
    D'où les deux liens : l'enquête, et le calcul qui a déclenché l'alerte.
    """

    reference: str
    titre: str
    resume: str
    risque: str
    entite: str
    perimetre: str
    lien_dossier: str = ""
    lien_console: str = ""
    etiquettes: list[str] = field(default_factory=list)


class DiscussionIndisponible(Exception):
    """L'outil de discussion ne répond pas.

    Distincte des autres erreurs du projet : celle-ci n'est JAMAIS fatale. Elle
    existe pour être attrapée et consignée, pas pour remonter jusqu'à un chemin
    de détection.
    """


@runtime_checkable
class Discussion(Protocol):
    """Ce que tout espace de discussion doit savoir faire."""

    nom: str

    def ouvrir_canal(self, incident: Incident) -> Canal:
        """Ouvre le canal de l'incident. Idempotent sur `incident.reference`.

        Rouvrir un canal existant pour un incident déjà connu disperserait la
        conversation entre deux endroits — le contraire du but recherché.
        """

    def publier(self, canal: str, texte: str) -> bool:
        """Publie un message. Renvoie False plutôt que de lever."""

    def etat(self) -> dict:
        """Santé de l'outil : joignable, compte de service accepté."""
