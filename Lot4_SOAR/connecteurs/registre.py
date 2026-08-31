# -*- coding: utf-8 -*-
"""Aiguillage : quelle action va vers quel connecteur, et sous quelles conditions.

Le registre est le seul endroit du code qui sache qu'un `block_ip` finit dans un
alias de pare-feu et qu'un `freeze_account` finit dans un annuaire. Le reste de
la plateforme manipule des actions ; lui seul connaît les équipements.

DEUX REFUS AVANT TOUTE ÉCRITURE
-------------------------------
1. **Action inconnue.** Aucun connecteur n'est déclaré pour elle : on ne
   bricole pas, on renvoie l'opérateur vers la commande manuelle.
2. **Cible du mauvais type.** `block_ip` sur un nom d'hôte, `freeze_account`
   sur un agrégat de machine préfixé `hote_` : ces cas viennent d'une
   qualification ratée en amont. Les laisser passer produirait une entrée
   inerte dans un alias — une mesure qui semble prise et ne protège rien.

Le second refus mérite d'être défendu à l'oral : la réponse automatique est
dangereuse exactement là où elle croit avoir compris. On préfère qu'elle
s'arrête et le dise.
"""
from __future__ import annotations

import os

from .base import Connecteur, Resultat
from .ldap_ppolicy import AnnuairePpolicy
from .opnsense import OPNsense


class ActionNonPilotable(Exception):
    """Cette action ne peut pas être exécutée automatiquement, et voici pourquoi."""


def construire() -> dict[str, Connecteur]:
    """Instancie les connecteurs à partir de l'environnement.

    Rien n'est ouvert ici : les connecteurs se connectent au premier appel. Un
    équipement éteint ne doit pas empêcher le cœur SOC de démarrer.
    """
    bloc = os.getenv("OPNSENSE_ALIAS_BLOCK", "nexus_block")
    quarantaine = os.getenv("OPNSENSE_ALIAS_QUARANTAINE", "nexus_quarantaine")
    return {
        # Une adresse dans la liste de blocage : rejetée en source comme en
        # destination, sur toutes les interfaces.
        "block_ip": OPNsense(alias=bloc, cible_attendue="ip"),
        # La quarantaine coupe les flux de la machine MAIS laisse passer sa
        # télémétrie vers le cœur SOC. Isoler sans aveugler : c'est la
        # propriété centrale du dispositif, portée par l'ordre des règles.
        "isolate_host": OPNsense(alias=quarantaine, cible_attendue="hote"),
        "freeze_account": AnnuairePpolicy(),
    }


CIBLE_ATTENDUE = {"block_ip": "ip", "isolate_host": "hote",
                  "freeze_account": "compte"}


def adresses_protegees() -> set[str]:
    """Les adresses qu'une réponse automatique ne doit jamais viser.

    Le cœur SOC émet sa propre télémétrie et apparaît donc dans l'inventaire
    comme n'importe quel poste : le moteur peut parfaitement proposer de
    l'isoler. Appliquer cette décision couperait la plateforme qui l'exécute,
    et personne ne serait plus là pour la lever — c'est le seul cas où une
    réponse se retourne contre celui qui la déclenche.

    La passerelle est protégée pour une raison voisine : la mettre dans une
    liste de blocage rendrait toutes les zones muettes d'un coup.
    """
    defaut = "10.50.0.2,10.50.0.1"
    brut = os.getenv("SOAR_ADRESSES_PROTEGEES", defaut)
    return {a.strip() for a in brut.split(",") if a.strip()}


def verifier_cible_autorisee(adresse: str) -> None:
    """Lève `ActionNonPilotable` si l'adresse fait partie des intouchables."""
    if adresse in adresses_protegees():
        raise ActionNonPilotable(
            f"{adresse} est une adresse protégée (cœur SOC ou passerelle) : "
            f"l'isoler couperait la plateforme qui exécute la décision. "
            f"Requalifier l'alerte ou intervenir manuellement, en connaissance "
            f"de cause.")


def connecteur_pour(action: str, cible: str, cible_type: str,
                    registre: dict[str, Connecteur] | None = None) -> Connecteur:
    """Renvoie le connecteur compétent, ou explique pourquoi il n'y en a pas."""
    registre = registre if registre is not None else construire()
    if not cible:
        raise ActionNonPilotable(
            "aucune cible n'a été résolue pour cette action")
    c = registre.get(action)
    if c is None:
        raise ActionNonPilotable(
            f"aucun connecteur n'est déclaré pour « {action} » — "
            f"exécution manuelle")
    attendu = CIBLE_ATTENDUE.get(action)
    if attendu and cible_type != attendu:
        raise ActionNonPilotable(
            f"cible de type « {cible_type} » alors que « {action} » attend "
            f"« {attendu} » — requalifier ou refuser l'action plutôt que "
            f"l'exécuter à côté")
    return c


def reconcilier(attendues: dict[str, list[str]],
                registre: dict[str, Connecteur] | None = None) -> list[str]:
    """Repousse les mesures que la plateforme croit en vigueur.

    POURQUOI C'EST INDISPENSABLE
    ----------------------------
    Les listes `alias_util` vivent dans la table pf, en mémoire. OPNsense 26 les
    réécrit après un `configctl filter reload` — vérifié sur l'appliance, et
    c'est une bonne nouvelle — mais rien ne les protège d'une purge (`pfctl -T
    flush`, le bouton « Flush » de l'interface, une réinstallation) ni d'une
    divergence lente entre ce que la plateforme a décidé et ce que l'équipement
    applique réellement.

    Le cas à redouter n'est pas la panne bruyante : c'est la quarantaine tombée
    sans que personne ne l'ait levée, pendant que la console affiche « isolée ».

    On compare donc ce que l'équipement applique à ce que l'audit dit avoir
    décidé, et on repose ce qui manque. Renvoie la liste des écarts constatés.

    L'ÉCART INVERSE COMPTE AUSSI
    ----------------------------
    Une mesure EN VIGUEUR que l'audit n'explique pas est le symétrique du
    problème : une machine isolée sans qu'aucune décision ne le justifie, et
    personne pour dire pourquoi. On la SIGNALE, on ne la retire pas — un
    opérateur a pu la poser à la main, en pleine intervention, et une
    réconciliation qui la lèverait toute seule serait pire que le mal.
    """
    registre = registre if registre is not None else construire()
    corriges: list[str] = []
    # On parcourt TOUS les connecteurs, pas seulement ceux qui ont une mesure
    # attendue. Sinon le cas le plus grave passe inaperçu : aucune décision en
    # base, et pourtant des machines isolées sur l'équipement. C'est
    # exactement ce qui s'est produit le 29 août — KaliPrime en quarantaine
    # sans qu'aucune action ne l'explique, et une réconciliation muette.
    for action in sorted(set(registre) | set(attendues)):
        cibles = attendues.get(action, [])
        c = registre.get(action)
        if c is None:
            continue
        try:
            actives = set(c.cibles_actives())
        except Exception as e:
            corriges.append(f"{action} : état illisible ({e})")
            continue
        for cible in cibles:
            if cible in actives:
                continue
            r: Resultat = c.appliquer(cible)
            corriges.append(
                f"{action} {cible} : {'reposée' if r.applique else 'ÉCHEC'} — {r.resume()}")
        for orpheline in sorted(actives - set(cibles)):
            corriges.append(
                f"{action} {orpheline} : EN VIGUEUR SANS DÉCISION — mesure "
                f"présente sur l'équipement qu'aucune action approuvée "
                f"n'explique. Signalée, pas levée : à arbitrer.")
    return corriges
