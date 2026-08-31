# -*- coding: utf-8 -*-
"""Discussion d'incident — la coordination, à côté de la trace.

Le dossier d'enquête garde la trace ; le canal porte la coordination. Une panne
ici ne doit jamais remonter jusqu'à un chemin de détection : voir base.py.
"""
from .base import Canal, Discussion, DiscussionIndisponible, Incident
from .mattermost import Mattermost
from .veille import boucler, ouvrir_canaux, reperer_escalades

__all__ = ["Canal", "Discussion", "DiscussionIndisponible", "Incident",
           "Mattermost", "reperer_escalades", "ouvrir_canaux", "boucler"]
