#!/usr/bin/env python3
"""
NEXUS SOC — Tests des connecteurs de réponse
============================================

    pytest Lot6_Tests/test_connecteurs.py -v

Ni réseau, ni pare-feu, ni annuaire : le transport de chaque connecteur est
remplacé par un double. Ce qu'on teste ici n'est pas la capacité à parler à
OPNsense — la recette `08-preuve-connecteurs.sh` s'en charge contre le vrai
matériel — mais la RÈGLE DE DÉCISION, qui doit rester vérifiable un jour où
l'appliance est éteinte.

LA RÈGLE, RAPPELÉE
------------------
Un connecteur ne dit jamais « fait » parce qu'il a reçu un 200. Il relit
l'équipement, et c'est la relecture qui tranche. D'où trois issues et non deux :

    applique=True,  verifie=True   la mesure est en vigueur, constaté
    applique=False, verifie=True   elle ne l'est pas, constaté
    verifie=False                  on NE SAIT PAS

Le dernier cas est celui qui compte : ne pas savoir n'est pas savoir que oui.
Les tests ci-dessous existent surtout pour qu'une refonte future ne les
confonde pas.
"""
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "Lot4_SOAR"))

from connecteurs import (ActionNonPilotable, ConnecteurIndisponible,  # noqa: E402
                         OPNsense, connecteur_pour, reconcilier,
                         verifier_cible_autorisee)


# ── Doubles ────────────────────────────────────────────────────────────────
def pare_feu(ecriture="ok", contenu_apres=("10.50.20.20",), relecture="ok"):
    """Un OPNsense dont on pilote l'écriture et la relecture séparément.

    Les deux se contrôlent indépendamment parce que la panne intéressante est
    précisément celle où l'écriture passe et la relecture non.
    """
    c = OPNsense(alias="nexus_quarantaine", cible_attendue="hote",
                 cle="k", secret="s")

    def _appel(chemin, charge=None):
        if "alias_util/list" in chemin:
            if relecture != "ok":
                raise ConnecteurIndisponible("relecture impossible")
            return {"rows": [{"ip": ip} for ip in contenu_apres]}
        if "kill_states" in chemin:
            raise ConnecteurIndisponible("HTTP 403")
        if ecriture != "ok":
            raise ConnecteurIndisponible("écriture impossible")
        return {"status": "done"}

    c._appel = _appel
    return c


# ── Le cas nominal ─────────────────────────────────────────────────────────
def test_mesure_confirmee_par_relecture():
    r = pare_feu().appliquer("10.50.20.20")
    assert r.applique is True and r.verifie is True
    assert "relu" in r.detail


def test_la_reserve_sur_les_sessions_est_dite_et_non_tue():
    """Une isolation à moitié faite doit se voir, pas se deviner."""
    r = pare_feu().appliquer("10.50.20.20")
    assert r.reserves, "la purge des états a échoué : il faut le dire"
    assert "nouvelles connexions" in " ".join(r.reserves)
    assert "réserves" in r.resume()


# ── Les trois façons d'échouer, qui ne se valent pas ───────────────────────
def test_ecriture_acceptee_mais_sans_effet():
    """OPNsense accepte une adresse dans un alias qui ne sert pas."""
    r = pare_feu(contenu_apres=()).appliquer("10.50.20.20")
    assert r.applique is False and r.verifie is True, \
        "on a pu constater : la mesure n'est pas en vigueur"
    assert "sans effet" in r.resume()


def test_ecriture_impossible_ne_pretend_rien():
    r = pare_feu(ecriture="ko").appliquer("10.50.20.20")
    assert r.verifie is False, "on ne sait pas, et on ne doit pas dire autre chose"
    assert "NON VÉRIFIÉ" in r.resume()


def test_relecture_impossible_ne_vaut_pas_succes():
    """Le piège : l'écriture passe, la relecture non. Ce n'est PAS un succès."""
    r = pare_feu(relecture="ko").appliquer("10.50.20.20")
    assert r.verifie is False
    assert r.applique is False


# ── Levée ──────────────────────────────────────────────────────────────────
def test_levee_confirmee():
    r = pare_feu(contenu_apres=()).lever("10.50.20.20")
    assert r.applique is False and r.verifie is True


def test_levee_qui_n_a_pas_pris():
    r = pare_feu(contenu_apres=("10.50.20.20",)).lever("10.50.20.20")
    assert r.applique is True, "la mesure est encore là : ne pas dire « levée »"


# ── Ce que le registre refuse AVANT d'écrire ───────────────────────────────
@pytest.mark.parametrize("action,cible,typ", [
    ("block_ip", "SRV-APP-GOV-01", "hote"),      # une IP attendue, un nom reçu
    ("freeze_account", "hote_SRV-01", "hote"),   # un compte attendu
    ("action_inventee", "10.0.0.1", "ip"),       # aucun connecteur
    ("block_ip", "", "ip"),                      # aucune cible résolue
])
def test_le_registre_refuse_plutot_que_d_executer_a_cote(action, cible, typ):
    with pytest.raises(ActionNonPilotable):
        connecteur_pour(action, cible, typ)


def test_le_coeur_soc_ne_peut_pas_s_isoler_lui_meme():
    """Le seul cas où une réponse se retourne contre celui qui la déclenche."""
    with pytest.raises(ActionNonPilotable):
        verifier_cible_autorisee("10.50.0.2")
    with pytest.raises(ActionNonPilotable):
        verifier_cible_autorisee("10.50.0.1")
    verifier_cible_autorisee("10.50.20.20")      # ne doit pas lever


# ── Réconciliation ─────────────────────────────────────────────────────────
def test_la_reconciliation_repose_ce_qui_manque_et_pas_le_reste():
    deja = pare_feu(contenu_apres=("10.50.20.20",))
    ecarts = reconcilier({"isolate_host": ["10.50.20.20"]},
                         registre={"isolate_host": deja})
    assert ecarts == [], "ce qui est déjà en vigueur ne doit pas être réécrit"

    manquant = pare_feu(contenu_apres=("10.50.20.20",))
    ecarts = reconcilier({"isolate_host": ["10.50.20.20", "10.50.40.40"]},
                         registre={"isolate_host": manquant})
    assert len(ecarts) == 1 and "10.50.40.40" in ecarts[0]


def test_un_equipement_muet_est_signale_pas_ignore():
    muet = pare_feu(relecture="ko")
    ecarts = reconcilier({"isolate_host": ["10.50.20.20"]},
                         registre={"isolate_host": muet})
    assert len(ecarts) == 1 and "illisible" in ecarts[0]

def test_une_mesure_sans_decision_est_signalee_pas_levee():
    """Le 29 août, 10.50.20.20 était en quarantaine sans qu'aucune action ne
    l'explique. Une réconciliation qui la lèverait toute seule défferait le
    geste d'un opérateur en pleine intervention : on signale, on n'agit pas."""
    equipement = pare_feu(contenu_apres=("10.50.20.20", "10.50.99.99"))
    ecarts = reconcilier({"isolate_host": ["10.50.20.20"]},
                         registre={"isolate_host": equipement})
    assert len(ecarts) == 1
    assert "10.50.99.99" in ecarts[0]
    assert "SANS DÉCISION" in ecarts[0]

def test_une_mesure_orpheline_est_vue_meme_sans_aucune_decision():
    """Le cas le plus grave : la base ne porte AUCUNE mesure pour cette action,
    et l'équipement en applique pourtant une. La première version ne regardait
    l'équipement que si une mesure était attendue — elle restait donc muette
    précisément quand il fallait parler."""
    equipement = pare_feu(contenu_apres=("10.50.50.50",))
    ecarts = reconcilier({}, registre={"isolate_host": equipement})
    assert len(ecarts) == 1
    assert "10.50.50.50" in ecarts[0] and "SANS DÉCISION" in ecarts[0]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
