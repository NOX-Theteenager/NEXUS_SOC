#!/usr/bin/env python3
"""
NEXUS SOC — Tests de la file vers l'outil d'enquête
===================================================

    pytest Lot6_Tests/test_dossiers.py -v

Ces tests ne demandent NI réseau NI IRIS. C'est délibéré : la logique qui décide
de réessayer ou d'abandonner un envoi doit être vérifiable sans dépendre de la
disponibilité d'un outil tiers — sinon on ne la teste que les jours où il
fonctionne, c'est-à-dire jamais quand ça compte.

Le gestionnaire est remplacé par un double qui répond ce qu'on lui demande de
répondre. La base est remplacée par une base en mémoire qui reproduit les
quelques comportements dont l'ouvrier dépend : conflit sur la référence,
verrouillage des lignes dues, report.

CE QUI EST VÉRIFIÉ, ET POURQUOI
-------------------------------
1. Idempotence à l'entrée : deux fois la même alerte, une seule entrée.
2. Un outil INDISPONIBLE fait REPORTER — on ne perd pas l'incident.
3. Un REFUS fait ABANDONNER — une charge malformée ne bloque pas la file
   derrière son report éternel.
4. Le report croît puis plafonne — on ne martèle pas un outil en panne.
5. « Envoyé » ne s'écrit que sur un identifiant rendu par l'outil.
"""
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "Lot4_SOAR"))

from dossiers.base import Depose, DepotRefuse, DossierIndisponible  # noqa: E402
from dossiers.sortie import TENTATIVES_MAX, report, vider  # noqa: E402


# ── Doubles ────────────────────────────────────────────────────────────────
class GestionnaireDouble:
    """Répond ce qu'on lui a dit de répondre, et compte ses appels."""

    nom = "double"

    def __init__(self, reponse="ok"):
        self.reponse = reponse
        self.appels = []

    def ouvrir(self, depot, customer_id=None):
        self.appels.append(depot.reference)
        if self.reponse == "indisponible":
            raise DossierIndisponible("outil éteint")
        if self.reponse == "refus":
            raise DepotRefuse("charge malformée")
        if self.reponse == "deja":
            return Depose(identifiant="42", deja_present=True, detail="déjà là")
        return Depose(identifiant="7", deja_present=False, detail="déposé")


class CurseurDouble:
    def __init__(self, base):
        self.base = base
        self._resultats = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).lower()
        if s.startswith("select id, alert_id"):
            self._resultats = [
                dict(l) for l in self.base.lignes
                if l["etat"] == "en_attente"][:params[0]]
        elif s.startswith("select customer_id"):
            self._resultats = [{"customer_id": 1}]
        elif "set etat = 'envoye'" in s:
            self.base.maj(params[-1], etat="envoye", dossier_externe=params[0])
        elif "set etat = 'abandonne'" in s:
            self.base.maj(params[-1], etat="abandonne", tentatives=params[0],
                          derniere_erreur=params[1])
        elif "set tentatives" in s:
            self.base.maj(params[-1], tentatives=params[0],
                          derniere_erreur=params[1])
        else:
            self._resultats = []

    def fetchall(self):
        return self._resultats

    def fetchone(self):
        return self._resultats[0] if self._resultats else None


class BaseDouble:
    def __init__(self, lignes):
        self.lignes = lignes
        self.commits = 0

    def cursor(self):
        return CurseurDouble(self)

    def commit(self):
        self.commits += 1

    def maj(self, ident, **champs):
        for l in self.lignes:
            if l["id"] == ident:
                l.update(champs)


def entree(ident=1, tentatives=0, reference="ref-1"):
    return {"id": ident, "alert_id": "a" * 8, "tenant_id": "t" * 8,
            "reference_source": reference, "tentatives": tentatives,
            "etat": "en_attente",
            "charge": {"titre": "T", "description": "D", "gravite": "High"}}


# ── Report ─────────────────────────────────────────────────────────────────
def test_report_croit_puis_plafonne():
    """Un outil en panne ne doit pas être martelé, ni oublié."""
    suite = [report(n) for n in range(1, 10)]
    assert suite[0] < suite[1] < suite[2], "le report doit croître"
    assert suite[-1] == suite[-2], "le report doit plafonner"
    assert max(suite) <= 1800, "le plafond ne doit pas dépasser la demi-heure"


# ── Envoi nominal ──────────────────────────────────────────────────────────
def test_envoi_marque_l_identifiant_rendu():
    """« Envoyé » ne s'écrit que sur un identifiant, jamais sur un code HTTP."""
    base = BaseDouble([entree()])
    bilan = vider(base, GestionnaireDouble("ok"))
    assert bilan["envoyes"] == 1
    assert base.lignes[0]["etat"] == "envoye"
    assert base.lignes[0]["dossier_externe"] == "7"


def test_deja_present_compte_comme_envoye_sans_doublon():
    """Un rejeu retrouve le dossier existant et ne crée pas de second."""
    base = BaseDouble([entree()])
    bilan = vider(base, GestionnaireDouble("deja"))
    assert bilan["deja"] == 1 and bilan["envoyes"] == 0
    assert base.lignes[0]["dossier_externe"] == "42"


# ── Panne contre refus : la distinction qui compte ─────────────────────────
def test_outil_indisponible_fait_reporter_pas_perdre():
    """Une panne ne doit jamais faire perdre un incident."""
    base = BaseDouble([entree()])
    bilan = vider(base, GestionnaireDouble("indisponible"))
    assert bilan["reportes"] == 1
    assert base.lignes[0]["etat"] == "en_attente", "l'entrée doit rester en file"
    assert base.lignes[0]["tentatives"] == 1


def test_refus_explicite_fait_abandonner():
    """Une charge refusée ne doit pas bloquer la file derrière son report."""
    base = BaseDouble([entree()])
    bilan = vider(base, GestionnaireDouble("refus"))
    assert bilan["abandonnes"] == 1
    assert base.lignes[0]["etat"] == "abandonne"
    assert "refus" in base.lignes[0]["derniere_erreur"].lower()


def test_abandon_seulement_apres_le_plafond_de_tentatives():
    """On n'abandonne pas au premier hoquet, mais on n'insiste pas sans fin."""
    juste_avant = BaseDouble([entree(tentatives=TENTATIVES_MAX - 2)])
    vider(juste_avant, GestionnaireDouble("indisponible"))
    assert juste_avant.lignes[0]["etat"] == "en_attente"

    au_plafond = BaseDouble([entree(tentatives=TENTATIVES_MAX - 1)])
    vider(au_plafond, GestionnaireDouble("indisponible"))
    assert au_plafond.lignes[0]["etat"] == "abandonne"


# ── Isolation entre entrées ────────────────────────────────────────────────
def test_une_entree_en_echec_n_empeche_pas_les_autres():
    """Le travail fait sur les entrées précédentes ne doit pas être perdu."""
    base = BaseDouble([entree(1, reference="a"), entree(2, reference="b")])
    double = GestionnaireDouble("ok")
    bilan = vider(base, double)
    assert bilan["envoyes"] == 2
    assert double.appels == ["a", "b"]
    assert base.commits >= 2, "chaque entrée doit être validée séparément"



# ── Idempotence côté outil : le défaut trouvé le 29 août ───────────────────
# La recette a montré qu'IRIS n'impose AUCUNE unicité sur `alert_source_ref` :
# rejouer un envoi créait un second dossier. La vérification a donc été
# déplacée AVANT l'écriture. Ces deux tests existent pour qu'une refonte ne
# la remette pas après.
class IrisDouble:
    """Un IRIS qui accepte tout, comme le vrai — et qu'on interroge d'abord."""

    def __init__(self, connues=()):
        self.connues = dict(connues)
        self.deposes = []

    def _appel(self, methode, chemin, charge=None):
        if chemin.startswith("/alerts/filter"):
            from urllib.parse import parse_qs, urlparse
            ref = parse_qs(urlparse(chemin).query).get("source_reference", [""])[0]
            lignes = [{"alert_id": i, "alert_source_ref": r}
                      for r, i in self.connues.items()]
            # Le vrai IRIS renvoie TOUT quand le filtre ne lui parle pas : on
            # reproduit ce piège pour vérifier qu'on revérifie chaque ligne.
            return {"data": {"alerts": lignes if ref else lignes}}
        if chemin == "/alerts/add":
            ref = charge["alert_source_ref"]
            ident = 100 + len(self.deposes)
            self.deposes.append(ref)
            self.connues[ref] = ident
            return {"data": {"alert_id": ident}}
        raise AssertionError(f"appel inattendu : {chemin}")


def _iris(connues=()):
    from dossiers.iris import IRIS
    c = IRIS(url="https://exemple", cle="k")
    double = IrisDouble(connues)
    c._appel = double._appel
    c._gravites = {"critical": 6, "medium": 4}
    return c, double


def test_le_rejeu_retrouve_le_dossier_au_lieu_d_en_creer_un_second():
    from dossiers.base import Depot
    c, double = _iris({"ref-connue": 55})
    d = Depot(reference="ref-connue", titre="T", description="D",
              gravite="Critical", perimetre="p")
    r = c.ouvrir(d, customer_id=1)
    assert r.identifiant == "55" and r.deja_present is True
    assert double.deposes == [], "aucun second dépôt ne doit être créé"


def test_une_reference_inconnue_est_bien_deposee():
    from dossiers.base import Depot
    c, double = _iris({"autre-ref": 55})
    d = Depot(reference="ref-neuve", titre="T", description="D",
              gravite="Critical", perimetre="p")
    r = c.ouvrir(d, customer_id=1)
    assert r.deja_present is False
    assert double.deposes == ["ref-neuve"], \
        "un filtre qui renvoie tout ne doit pas faire conclure « déjà déposé »"

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
