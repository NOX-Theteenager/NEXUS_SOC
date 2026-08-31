# -*- coding: utf-8 -*-
"""Connecteurs de réponse — ce qui transforme une décision en effet réel.

Jusqu'ici la console affichait une commande et enregistrait qui déclarait
l'avoir passée. Ces modules l'exécutent, et surtout : ils RELISENT l'équipement
pour savoir si elle a produit un effet. Voir base.py, qui porte la règle.
"""
from .base import Connecteur, ConnecteurIndisponible, Resultat
from .ldap_ppolicy import AnnuairePpolicy
from .opnsense import OPNsense
from .registre import (ActionNonPilotable, connecteur_pour, construire,
                       reconcilier, verifier_cible_autorisee)

__all__ = ["Connecteur", "ConnecteurIndisponible", "Resultat", "OPNsense",
           "AnnuairePpolicy", "construire", "connecteur_pour", "reconcilier",
           "ActionNonPilotable", "verifier_cible_autorisee"]
