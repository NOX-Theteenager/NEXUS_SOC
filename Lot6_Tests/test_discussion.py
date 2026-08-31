#!/usr/bin/env python3
"""
NEXUS SOC — Tests de la discussion d'incident
=============================================

    pytest Lot6_Tests/test_discussion.py -v

Ni Mattermost ni IRIS : les deux sont remplacés par des doubles. Ce qui est
vérifié n'est pas la capacité à parler à Mattermost — la recette
`10-preuve-discussion.sh` s'en charge contre le vrai service — mais la RÈGLE :

    **une panne de la messagerie ne doit RIEN interrompre.**

C'est la propriété la plus facile à casser sans s'en apercevoir : il suffit
qu'un jour quelqu'un remplace un `return False` par un `raise`, et la détection
s'arrête parce que le canal de discussion est indisponible.
"""
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "Lot4_SOAR"))

from discussion.base import Canal, DiscussionIndisponible, Incident  # noqa: E402
from discussion.mattermost import Mattermost  # noqa: E402
from discussion.veille import ouvrir_canaux, reperer_escalades  # noqa: E402


# ── Doubles ────────────────────────────────────────────────────────────────
class MessagerieDouble:
    nom = "double"

    def __init__(self, ouverture="ok", publication="ok"):
        self.ouverture = ouverture
        self.publication = publication
        self.canaux = []
        self.messages = []

    def ouvrir_canal(self, incident):
        if self.ouverture == "panne":
            raise DiscussionIndisponible("messagerie éteinte")
        deja = incident.reference in self.canaux
        self.canaux.append(incident.reference)
        return Canal(identifiant=f"c-{incident.reference[:6]}",
                     nom=f"incident-20260829-{incident.reference[:8]}",
                     deja_present=deja, lien="http://exemple/canal")

    def publier(self, canal, texte):
        if self.publication == "panne":
            return False
        self.messages.append((canal, texte))
        return True

    @staticmethod
    def message_initial(incident):
        return Mattermost.message_initial(incident)


class IrisDouble:
    def __init__(self, alertes=(), panne=False):
        self.alertes = list(alertes)
        self.panne = panne

    def alertes_par_statut(self, statut, limite=100):
        if self.panne:
            raise RuntimeError("IRIS éteint")
        return self.alertes


class Curseur:
    def __init__(self, base):
        self.base = base
        self._res = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).lower()
        if s.startswith("insert into incident_canal"):
            ref = params[0]
            if ref in {l["reference_source"] for l in self.base.lignes} \
               or ref not in self.base.alertes_connues:
                self.rowcount = 0
            else:
                self.base.lignes.append(
                    {"id": len(self.base.lignes) + 1, "reference_source": ref,
                     "alerte_iris": params[1], "tentatives": 0, "etat": "a_ouvrir",
                     "type": "Anomalie réseau / C2", "risque": 0.91,
                     "entite": "SRV-APP-GOV-01", "raisons": "T1071 écart 4,2 σ",
                     "mitre": "T1071", "perimetre": "SIGIPES"})
                self.rowcount = 1
        elif s.startswith("select c.id"):
            self._res = [l for l in self.base.lignes if l["etat"] == "a_ouvrir"]
        elif "set etat = 'ouvert'" in s:
            self.base.maj(params[-1], etat="ouvert", canal_id=params[0])
        elif "set tentatives = tentatives + 1" in s:
            for l in self.base.lignes:
                if l["id"] == params[-1]:
                    l["tentatives"] += 1
                    l["derniere_erreur"] = params[0]
                    l["etat"] = "echec" if l["tentatives"] >= 5 else "a_ouvrir"

    def fetchall(self):
        return self._res


class BaseDouble:
    def __init__(self, alertes_connues=()):
        self.lignes = []
        self.alertes_connues = set(alertes_connues)

    def cursor(self):
        return Curseur(self)

    def commit(self):
        pass

    def maj(self, ident, **champs):
        for l in self.lignes:
            if l["id"] == ident:
                l.update(champs)


REF = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _escalade(ref=REF):
    return {"alert_id": 42, "alert_source_ref": ref}


# ── Repérage des escalades ─────────────────────────────────────────────────
def test_une_escalade_est_notee_une_seule_fois():
    """La veille tourne en boucle : sans mémoire, elle rouvrirait sans fin."""
    base = BaseDouble([REF])
    iris = IrisDouble([_escalade()])
    assert reperer_escalades(base, iris) == 1
    assert reperer_escalades(base, iris) == 0, "le second tour ne doit rien créer"
    assert len(base.lignes) == 1


def test_une_alerte_inconnue_de_nexus_est_ignoree():
    """IRIS peut contenir des alertes venues d'ailleurs : ce ne sont pas les
    nôtres, et leur ouvrir un canal serait s'attribuer le travail d'un autre."""
    base = BaseDouble([REF])
    assert reperer_escalades(base, IrisDouble([_escalade("ref-etrangere")])) == 0


def test_iris_en_panne_ne_fait_pas_tomber_la_veille():
    base = BaseDouble([REF])
    assert reperer_escalades(base, IrisDouble(panne=True)) == 0


# ── Ouverture des canaux ───────────────────────────────────────────────────
def test_le_canal_s_ouvre_et_le_message_part():
    base = BaseDouble([REF])
    reperer_escalades(base, IrisDouble([_escalade()]))
    mess = MessagerieDouble()
    bilan = ouvrir_canaux(base, mess, "https://iris")
    assert bilan["ouverts"] == 1 and bilan["echecs"] == 0
    assert base.lignes[0]["etat"] == "ouvert"
    assert len(mess.messages) == 1


def test_messagerie_en_panne_laisse_l_entree_a_reprendre():
    """Une panne ne perd pas l'incident : on réessaiera au tour suivant."""
    base = BaseDouble([REF])
    reperer_escalades(base, IrisDouble([_escalade()]))
    bilan = ouvrir_canaux(base, MessagerieDouble(ouverture="panne"), "https://iris")
    assert bilan["echecs"] == 1
    assert base.lignes[0]["etat"] == "a_ouvrir", "l'entrée doit rester à reprendre"
    assert base.lignes[0]["tentatives"] == 1


def test_l_echec_repete_finit_par_se_voir():
    """Un canal qu'on ne sait pas ouvrir doit cesser d'être silencieux : la
    cellule attendrait sinon une notification qui ne viendra jamais."""
    base = BaseDouble([REF])
    reperer_escalades(base, IrisDouble([_escalade()]))
    panne = MessagerieDouble(ouverture="panne")
    for _ in range(5):
        ouvrir_canaux(base, panne, "https://iris")
    assert base.lignes[0]["etat"] == "echec"
    assert base.lignes[0]["derniere_erreur"]


def test_un_message_perdu_n_annule_pas_le_canal():
    """Mieux vaut un canal vide qu'aucun canal : on pourra y écrire ensuite."""
    base = BaseDouble([REF])
    reperer_escalades(base, IrisDouble([_escalade()]))
    bilan = ouvrir_canaux(base, MessagerieDouble(publication="panne"), "https://iris")
    assert bilan["ouverts"] == 1
    assert base.lignes[0]["etat"] == "ouvert"


# ── Le message lui-même ────────────────────────────────────────────────────
def _incident():
    return Incident(reference=REF, titre="Anomalie réseau / C2 — SRV-APP-GOV-01",
                    resume="- T1071 : écart 4,2 σ", risque="critique (91 %)",
                    entite="SRV-APP-GOV-01", perimetre="SIGIPES",
                    lien_dossier="https://iris/alerts?alert_id=42",
                    lien_console="https://soc/app/console.html#alerte=" + REF,
                    etiquettes=["T1071"])


def test_le_message_porte_les_deux_liens():
    """Sans le lien vers l'explicabilité, on subit la conclusion au lieu de
    pouvoir la contester."""
    m = Mattermost.message_initial(_incident())
    assert "iris/alerts?alert_id=42" in m
    assert "console.html#alerte=" in m


def test_le_message_dit_le_perimetre_l_entite_et_le_risque():
    m = Mattermost.message_initial(_incident())
    for attendu in ("SIGIPES", "SRV-APP-GOV-01", "critique"):
        assert attendu in m, f"« {attendu} » manque au message d'ouverture"


def test_le_nom_du_canal_est_datable_et_unique():
    from datetime import datetime, timezone
    quand = datetime(2026, 8, 29, tzinfo=timezone.utc)
    nom = Mattermost.nom_canal(_incident(), quand)
    assert nom.startswith("incident-20260829-")
    assert len(nom.split("-")[-1]) == 8, "un fragment de référence, pas la totale"

# ── L'échelle du risque : le défaut du 29 août ─────────────────────────────
@pytest.mark.parametrize("valeur,attendu", [
    (100, "critique (100 %)"),      # échelle 0–100, celle de `alerts.risque`
    (91, "critique (91 %)"),
    (70, "élevé (70 %)"),
    (45, "moyen (45 %)"),
    (12, "faible (12 %)"),
    (0.91, "critique (91 %)"),      # une fraction reste acceptée
    (None, "non mesuré"),
])
def test_le_risque_ne_depasse_jamais_cent_pour_cent(valeur, attendu):
    """Le titre du canal affichait « critique (10000 %) » : `alerts.risque` est
    sur 0–100 et le libellé le prenait pour une fraction. Une erreur visible de
    tous, du genre à faire douter du reste."""
    from discussion.veille import _libelle_risque
    assert _libelle_risque(valeur) == attendu

def test_les_motifs_ne_sont_jamais_publies_en_dictionnaire_brut():
    """Le canal affichait « {'label': 'Collection · T1005…', 'sigma': None } ».
    C'est la première chose que lit un intervenant qui arrive sur l'incident."""
    from discussion.veille import _resume
    texte = _resume({"raisons": [
        {"label": "Collection · T1005", "texte": "Collection — /etc/shadow",
         "sigma": 4.23},
        {"label": "C2 · T1071", "texte": "connexion vers 185.220.101.45:4444",
         "sigma": None}]})
    assert "{" not in texte and "'label'" not in texte
    assert "/etc/shadow" in texte and "4.2 σ" in texte
    assert "185.220.101.45:4444" in texte


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
