# -*- coding: utf-8 -*-
"""File de sortie vers l'outil d'enquête, et ouvrier qui la vide.

POURQUOI CETTE INDIRECTION
--------------------------
`/ingest` est le chemin le plus chaud de la plateforme. Y placer un appel HTTP
vers IRIS ferait dépendre l'INGESTION de la disponibilité d'un outil d'enquête :
IRIS redémarre, et le SOC cesse de voir. C'est exactement l'inverse de ce qu'on
construit.

L'ingestion écrit donc une ligne dans `dossier_sortie`, **en transaction
séparée**, et rend la main. Si l'écriture échoue, l'alerte reste enregistrée :
perdre un dépôt vers IRIS est regrettable, perdre une alerte est inacceptable.

CE QUE L'OUVRIER GARANTIT
-------------------------
· Un IRIS arrêté dix minutes ne perd rien : la file grossit, elle se vide après.
· Un rejeu ne crée pas de doublon : `reference_source` est unique ici, et part
  dans `alert_source_ref` côté IRIS, qui refuse le second dépôt.
· Un refus définitif n'immobilise pas la file : après plusieurs tentatives, ou
  sur un refus explicite, l'entrée passe en `abandonne` avec son motif. Une
  charge malformée retentée pour l'éternité masquerait tous les envois valides
  derrière son report.
· « Envoyé » ne s'écrit que sur un identifiant rendu par IRIS, jamais sur un
  code HTTP.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from .base import Depose, Depot, DepotRefuse, DossierIndisponible

TENTATIVES_MAX = int(os.getenv("DOSSIER_TENTATIVES_MAX", "8"))
REPORT_BASE_S = int(os.getenv("DOSSIER_REPORT_BASE_S", "30"))
REPORT_MAX_S = int(os.getenv("DOSSIER_REPORT_MAX_S", "1800"))


def report(tentatives: int) -> int:
    """Report exponentiel plafonné : un outil en panne ne doit pas être martelé."""
    return min(REPORT_BASE_S * (2 ** max(0, tentatives - 1)), REPORT_MAX_S)


# ── Écriture (côté ingestion) ───────────────────────────────────────────────
def enfiler(db, alert_id: str, tenant_id: str, reference: str,
            charge: dict[str, Any]) -> bool:
    """Dépose une alerte dans la file. Idempotent, silencieux sur doublon.

    Renvoie True si une nouvelle entrée a été créée. Ne lève jamais : appelée
    depuis le chemin d'ingestion, elle ne doit pas pouvoir le faire échouer.
    """
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO dossier_sortie "
                "  (alert_id, tenant_id, reference_source, charge) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (reference_source) DO NOTHING "
                "RETURNING id",
                (alert_id, tenant_id, reference, json.dumps(charge)))
            cree = cur.fetchone() is not None
        db.commit()
        return cree
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[dossiers] mise en file impossible pour {reference[:8]} : {e}")
        return False


# ── Lecture (côté ouvrier) ──────────────────────────────────────────────────
def _a_traiter(db, limite: int) -> list[dict]:
    with db.cursor() as cur:
        # `SKIP LOCKED` : deux ouvriers peuvent tourner sans se marcher dessus
        # ni traiter deux fois la même entrée.
        cur.execute(
            "SELECT id, alert_id::text, tenant_id::text, reference_source, "
            "       charge, tentatives "
            "  FROM dossier_sortie "
            " WHERE etat = 'en_attente' AND prochaine_tentative <= now() "
            " ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED", (limite,))
        return [dict(l) for l in cur.fetchall()]


def _customer_de(db, tenant_id: str) -> int | None:
    with db.cursor() as cur:
        cur.execute("SELECT customer_id FROM perimetre_iris WHERE tenant_id = %s",
                    (tenant_id,))
        ligne = cur.fetchone()
    return int(ligne["customer_id"]) if ligne else None


def _marquer_envoye(db, ident: int, depose: Depose) -> None:
    with db.cursor() as cur:
        cur.execute(
            "UPDATE dossier_sortie SET etat = 'envoye', envoye_le = now(), "
            "       dossier_externe = %s, derniere_erreur = NULL "
            " WHERE id = %s", (depose.identifiant, ident))


def _reporter(db, ident: int, tentatives: int, motif: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "UPDATE dossier_sortie "
            "   SET tentatives = %s, derniere_erreur = %s, "
            "       prochaine_tentative = now() + (%s || ' seconds')::interval "
            " WHERE id = %s",
            (tentatives, motif[:500], report(tentatives), ident))


def _abandonner(db, ident: int, tentatives: int, motif: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "UPDATE dossier_sortie SET etat = 'abandonne', tentatives = %s, "
            "       derniere_erreur = %s WHERE id = %s",
            (tentatives, motif[:500], ident))


def vider(db, gestionnaire, limite: int = 50) -> dict:
    """Traite un lot d'entrées dues. Renvoie un bilan chiffré.

    Chaque entrée est validée séparément : une erreur sur l'une ne doit pas
    faire perdre le travail fait sur les précédentes.
    """
    bilan = {"envoyes": 0, "deja": 0, "reportes": 0, "abandonnes": 0}
    lignes = _a_traiter(db, limite)
    for l in lignes:
        ident, tentatives = l["id"], l["tentatives"] + 1
        charge = l["charge"] if isinstance(l["charge"], dict) else json.loads(l["charge"])
        customer = _customer_de(db, l["tenant_id"])
        depot = Depot(reference=l["reference_source"],
                      perimetre=l["tenant_id"], **{
                          k: v for k, v in charge.items()
                          if k in ("titre", "description", "gravite",
                                   "lien_retour", "contenu", "etiquettes",
                                   "indicateurs", "actifs", "horodatage")})
        try:
            depose = gestionnaire.ouvrir(depot, customer_id=customer)
        except DepotRefuse as e:
            # L'outil a répondu et refusé : rejouer à l'identique est vain.
            _abandonner(db, ident, tentatives, f"refus définitif : {e}")
            bilan["abandonnes"] += 1
        except DossierIndisponible as e:
            if tentatives >= TENTATIVES_MAX:
                _abandonner(db, ident, tentatives,
                            f"abandon après {tentatives} tentatives : {e}")
                bilan["abandonnes"] += 1
            else:
                _reporter(db, ident, tentatives, str(e))
                bilan["reportes"] += 1
        else:
            _marquer_envoye(db, ident, depose)
            bilan["deja" if depose.deja_present else "envoyes"] += 1
        db.commit()
    return bilan


def boucler(db_fabrique, gestionnaire, intervalle: int = 20) -> None:
    """Ouvrier de fond. Ne meurt pas sur une erreur : il reporte et continue."""
    print(f"[dossiers] ouvrier démarré, cycle {intervalle} s")
    while True:
        db = None
        try:
            db = db_fabrique()
            bilan = vider(db, gestionnaire)
            if any(bilan.values()):
                print(f"[dossiers] {bilan}")
        except Exception as e:
            print(f"[dossiers] cycle en échec, on continue : {e}")
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
        time.sleep(intervalle)
