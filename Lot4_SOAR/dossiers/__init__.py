# -*- coding: utf-8 -*-
"""Dossiers d'enquête — ce qui relie une alerte mesurée à un travail d'analyste.

NEXUS pousse des ALERTES vers l'outil d'enquête, jamais des dossiers : l'escalade
reste un geste humain. Voir base.py, qui porte le contrat, et sortie.py, qui
explique pourquoi tout passe par une file plutôt que par un appel direct.
"""
from .base import (Depose, Depot, DepotRefuse, DossierIndisponible,
                   GestionDossier)
from .iris import IRIS
from .sortie import boucler, enfiler, vider

__all__ = ["Depot", "Depose", "GestionDossier", "DossierIndisponible",
           "DepotRefuse", "IRIS", "enfiler", "vider", "boucler"]
