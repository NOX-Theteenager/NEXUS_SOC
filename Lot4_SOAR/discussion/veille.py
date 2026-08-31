# -*- coding: utf-8 -*-
"""Veille des escalades : d'une alerte escaladée dans IRIS à un canal ouvert.

POURQUOI UNE VEILLE ET PAS UN MODULE IRIS
------------------------------------------
Le plan prévoyait un module IRIS branché sur l'accroche
`on_postload_alert_update`. IRIS n'expose ses accroches qu'à des modules Python
installés DANS son conteneur : il aurait fallu empaqueter du code au format de
leur cadriciel, le réinstaller à chaque montée de version d'IRIS, et le
déboguer à travers leur système de tâches asynchrones.

On regarde donc du côté de NEXUS, à intervalle. Trois raisons, dans cet ordre :

1. **Le code reste dans notre dépôt**, donc testable sans IRIS — c'est le
   principe qu'on applique partout ailleurs.
2. **Une montée de version d'IRIS ne casse rien.** Un module tiers mal reconnu
   après une mise à jour échouerait en silence, et personne ne s'apercevrait
   que les canaux ne s'ouvrent plus.
3. **Le délai n'a pas d'importance ici.** Une escalade est un geste humain
   délibéré ; que le canal s'ouvre trente secondes plus tard ne change rien à
   la conduite de l'incident. Ce serait différent pour une mesure de blocage.

Le compromis à assumer : la veille interroge IRIS régulièrement, ce qui coûte
un appel toutes les trente secondes. C'est peu cher payé pour ne pas dépendre
du cadriciel d'un tiers.

CE QUI EST GARANTI
------------------
Un incident n'a jamais deux canaux : `incident_canal` porte une contrainte
d'unicité sur la référence, et la veille regarde avant d'ouvrir. Et une panne
de Mattermost n'interrompt rien : l'entrée reste `a_ouvrir`, l'erreur est
consignée, et le tour suivant réessaie.
"""
from __future__ import annotations

import os

from .base import DiscussionIndisponible, Incident

# Statut « Escalated » d'IRIS. Relu sur l'instance plutôt que supposé : cette
# table est propre à chaque déploiement, et un identifiant figé dans le code
# ferait rater toutes les escalades sur une autre installation.
STATUT_ESCALADE = int(os.getenv("IRIS_STATUT_ESCALADE", "8"))

INTERVALLE = float(os.getenv("VEILLE_INTERVALLE_S", "30"))
CONSOLE = os.getenv("NEXUS_SERVER_URL", "https://soc.cenadi.local:8443")


def _lien_console(reference: str) -> str:
    return f"{CONSOLE}/app/console.html#alerte={reference}"


def _lien_dossier(url_iris: str, alerte_iris: str) -> str:
    return f"{url_iris.rstrip('/')}/alerts?alert_id={alerte_iris}"


def reperer_escalades(db, gestionnaire) -> int:
    """Note dans `incident_canal` les alertes passées à « Escalated ».

    On ne crée rien dans Mattermost ici : repérer et ouvrir sont deux gestes
    séparés, pour qu'une panne de la messagerie n'empêche pas de constater
    l'escalade. Renvoie le nombre de nouvelles escalades vues.
    """
    try:
        escaladees = gestionnaire.alertes_par_statut(STATUT_ESCALADE)
    except Exception as e:
        print(f"[veille] IRIS illisible, on réessaiera : {e}")
        return 0

    vues = 0
    for alerte in escaladees:
        reference = str(alerte.get("alert_source_ref") or "").strip()
        if not reference:
            continue                  # pas une alerte déposée par NEXUS
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO incident_canal
                       (reference_source, alert_id, tenant_id, alerte_iris)
                   SELECT %s, a.id, a.tenant_id, %s FROM alerts a
                    WHERE a.id::text = %s
                   ON CONFLICT (reference_source) DO NOTHING""",
                (reference, str(alerte.get("alert_id")), reference))
            vues += cur.rowcount
        db.commit()
    return vues


def ouvrir_canaux(db, discussion, url_iris: str) -> dict:
    """Ouvre les canaux des escalades repérées et publie le message initial."""
    bilan = {"ouverts": 0, "deja": 0, "echecs": 0}
    with db.cursor() as cur:
        cur.execute(
            # `alerts` n'a pas de colonne « titre » : le libellé se compose du
            # TYPE d'anomalie et de l'ENTITÉ concernée, comme le fait déjà le
            # dépôt vers IRIS. Une colonne inventée aurait fait échouer la
            # requête au premier tour, en pleine escalade.
            """SELECT c.id, c.reference_source, c.alerte_iris, c.tentatives,
                      a.type, a.risque, a.entite, a.raisons, a.mitre,
                      t.nom AS perimetre
                 FROM incident_canal c
                 LEFT JOIN alerts a  ON a.id = c.alert_id
                 LEFT JOIN tenants t ON t.id = c.tenant_id
                WHERE c.etat = 'a_ouvrir'
                ORDER BY c.cree_le
                LIMIT 20""")
        lignes = cur.fetchall()

    for l in lignes:
        incident = Incident(
            reference=l["reference_source"],
            titre=f'{l["type"] or "Anomalie"} — {l["entite"] or "entité inconnue"}',
            resume=_resume(l),
            risque=_libelle_risque(l["risque"]),
            entite=l["entite"] or "entité inconnue",
            perimetre=l["perimetre"] or "périmètre inconnu",
            lien_dossier=_lien_dossier(url_iris, l["alerte_iris"] or ""),
            lien_console=_lien_console(l["reference_source"]),
            etiquettes=_etiquettes(l["mitre"] or l["raisons"]),
        )
        try:
            canal = discussion.ouvrir_canal(incident)
        except DiscussionIndisponible as e:
            # L'échec DOIT se voir : sans cela la cellule attend une
            # notification qui ne viendra jamais, en prenant le silence pour
            # une absence d'incident.
            with db.cursor() as cur:
                cur.execute(
                    """UPDATE incident_canal
                          SET tentatives = tentatives + 1, derniere_erreur = %s,
                              etat = CASE WHEN tentatives + 1 >= 5 THEN 'echec'
                                          ELSE 'a_ouvrir' END
                        WHERE id = %s""", (str(e)[:400], l["id"]))
                db.commit()
            bilan["echecs"] += 1
            continue

        # Le message part APRÈS la création, et son échec n'annule pas le
        # canal : mieux vaut un canal vide qu'aucun canal.
        discussion.publier(canal.identifiant, discussion.message_initial(incident))

        with db.cursor() as cur:
            cur.execute(
                """UPDATE incident_canal
                      SET etat = 'ouvert', canal_id = %s, canal_nom = %s,
                          canal_lien = %s, ouvert_le = now(), derniere_erreur = NULL
                    WHERE id = %s""",
                (canal.identifiant, canal.nom, canal.lien, l["id"]))
            db.commit()
        bilan["deja" if canal.deja_present else "ouverts"] += 1
    return bilan


# ── Mise en forme ───────────────────────────────────────────────────────────
def _libelle_risque(risque) -> str:
    """Libellé lisible du risque mesuré.

    `alerts.risque` est exprimé sur 0–100, pas sur 0–1. La première version
    supposait une fraction et affichait « critique (10000 %) » dans le titre du
    canal — une erreur visible de tous, et exactement le genre de détail qui
    fait douter du reste. On normalise, et on accepte les deux échelles : une
    valeur ≤ 1 est une fraction, au-delà c'est déjà un pourcentage.
    """
    try:
        r = float(risque)
    except (TypeError, ValueError):
        return "non mesuré"
    pct = r * 100 if r <= 1 else r
    pct = max(0.0, min(100.0, pct))
    if pct >= 85:
        return f"critique ({pct:.0f} %)"
    if pct >= 65:
        return f"élevé ({pct:.0f} %)"
    if pct >= 40:
        return f"moyen ({pct:.0f} %)"
    return f"faible ({pct:.0f} %)"


def _phrase(raison) -> str:
    """Rend un motif lisible, quelle que soit sa forme en base.

    `alerts.raisons` contient des objets `{label, texte, sigma}`. Les passer à
    `str()` publiait le dictionnaire Python tel quel dans le canal — illisible,
    et la première chose qu'un lecteur voit. On extrait le texte, et l'écart en
    sigma quand il est mesuré.
    """
    if isinstance(raison, dict):
        texte = (raison.get("texte") or raison.get("label")
                 or raison.get("description") or "")
        sigma = raison.get("sigma")
        if sigma not in (None, "", "None"):
            try:
                return f"{texte} (écart {float(sigma):.1f} σ)".strip()
            except (TypeError, ValueError):
                pass
        return str(texte).strip()
    return str(raison).strip()


def _resume(ligne) -> str:
    """Les écarts mesurés, rédigés. Jamais une conclusion sans son motif."""
    raisons = ligne.get("raisons")
    if isinstance(raisons, str):
        return raisons[:900]
    if isinstance(raisons, (list, tuple)):
        lignes = [_phrase(r) for r in raisons[:8]]
        return "\n".join(f"- {l}" for l in lignes if l)[:900] \
            or "_Aucun motif exploitable enregistré._"
    if isinstance(raisons, dict):
        return "\n".join(f"- **{k}** : {v}"
                         for k, v in list(raisons.items())[:8])[:900]
    return "_Aucun motif enregistré pour cette alerte._"


def _etiquettes(raisons) -> list[str]:
    """Techniques MITRE citées dans les motifs, sans en inventer aucune."""
    import re
    texte = str(raisons or "")
    return sorted(set(re.findall(r"\bT\d{4}(?:\.\d{3})?\b", texte)))[:8]


def boucler(fabrique_db, gestionnaire, discussion, url_iris: str,
            intervalle: float = INTERVALLE) -> None:
    """Tour de veille sans fin : repérer, puis ouvrir.

    Aucune exception ne sort d'ici. Ce fil accompagne le cœur SOC ; le faire
    tomber pour une messagerie en panne reviendrait à arrêter la détection
    parce que le téléphone ne marche plus.
    """
    import time
    print(f"[veille] démarrée, cycle {intervalle} s")
    while True:
        db = None
        try:
            db = fabrique_db()
            vues = reperer_escalades(db, gestionnaire)
            bilan = ouvrir_canaux(db, discussion, url_iris)
            if vues or bilan["ouverts"] or bilan["echecs"]:
                print(f"[veille] {vues} escalade(s) vue(s), "
                      f"{bilan['ouverts']} canal/canaux ouvert(s), "
                      f"{bilan['echecs']} échec(s)")
        except Exception as e:
            print(f"[veille] tour ignoré : {e}")
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
        time.sleep(intervalle)
