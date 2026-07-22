#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Recalibration des seuils de risque sur une ligne de base RÉELLE
============================================================================
Problème traité
---------------
Les modèles (Isolation Forest) ont été entraînés sur des données synthétiques.
Sur l'activité réelle d'une machine, leurs scores bruts saturent → le risque
affiché reste bloqué à 100/100. Ce script NE réentraîne PAS les modèles : il
mesure la distribution réelle des scores bruts sur cette machine (activité
normale), puis règle le MAPPING de décision (bornes lo/hi + seuil d'alerte) pour
que « 100 » ne s'affiche que lorsqu'on s'écarte vraiment de la normale locale.

Deux étapes
-----------
  1) COLLECTE  : mesure les features réelles à intervalle régulier et enregistre
                 les scores bruts M1/M2 dans un fichier de base.
      python3 recalibrate_baseline.py --collect --duration 2700 --interval 15

  2) APPLICATION : lit la base, calcule les percentiles, sauvegarde les modèles
                 et écrit les nouveaux lo/hi/threshold dans les .joblib.
      python3 recalibrate_baseline.py --apply --percentile 99

Principe de calibration (par modèle)
------------------------------------
  lo (risque 0)   = médiane (p50) des scores bruts de base
  hi (risque 100) = p<percentile> des scores bruts de base
  threshold       = p<percentile>  (drapeau « anomalie »)
→ l'activité normale (sous la médiane) tombe vers 0 ; seuls les événements
  au-delà du percentile choisi (~1 % de la base au 99e) déclenchent une alerte.
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone

import numpy as np
import joblib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Lot1_Agent_Go"))

M1_PATH = os.getenv("MODEL1_PATH", os.path.join(
    ROOT, "Lot3_IA/Modele1_Anomalie_reseau/outputs/model1_isoforest.joblib"))
M2_PATH = os.getenv("MODEL2_PATH", os.path.join(
    ROOT, "Lot3_IA/Modele2_Fraude_interne/outputs_m2/model2_isoforest.joblib"))
BASE_FILE = os.getenv("BASELINE_FILE",
                      os.path.expanduser("~/nexus-soc-backups/baseline_scores.jsonl"))
BACKUP_DIR = os.path.expanduser("~/nexus-soc-backups")


# --------------------------------------------------------------------------- #
def _load_models():
    m1 = joblib.load(M1_PATH)
    m2 = joblib.load(M2_PATH)
    return m1, m2


def _raw_score(bundle, feats: dict) -> float:
    """Score brut d'anomalie (plus élevé = plus anormal) pour un modèle donné."""
    x = np.array([[float(feats.get(f, 0.0)) for f in bundle["features"]]])
    xs = bundle["scaler"].transform(x)
    return float(-bundle["model"].score_samples(xs)[0])


# --------------------------------------------------------------------------- #
def collecte(duration_s: int, interval_s: int):
    """Mesure les features réelles et journalise les scores bruts M1/M2."""
    import nexus_collector as nc  # réutilise les fonctions de mesure réelle

    m1, m2 = _load_models()
    os.makedirs(os.path.dirname(BASE_FILE), exist_ok=True)
    t_fin = time.time() + duration_s
    n = 0
    print(f"▶ Collecte de base : {duration_s}s (intervalle {interval_s}s) → {BASE_FILE}")
    print("  Utilise ta machine NORMALEMENT pendant ce temps.")

    with open(BASE_FILE, "a") as f:
        while time.time() < t_fin:
            enr = {"ts": datetime.now(timezone.utc).isoformat()}
            try:
                fr, _ = nc.features_reseau()
                if fr:
                    enr["m1"] = _raw_score(m1, fr)
            except Exception as e:
                print(f"  [m1] mesure ignorée : {e}")
            try:
                fc, ctx = nc.features_comportement()
                enr["m2"] = _raw_score(m2, fc)
                enr["hors_heures"] = ctx.get("hors_heures")
            except Exception as e:
                print(f"  [m2] mesure ignorée : {e}")

            if "m1" in enr or "m2" in enr:
                f.write(json.dumps(enr) + "\n"); f.flush()
                n += 1
                reste = int(t_fin - time.time())
                print(f"  [{n:3}] m1={enr.get('m1',float('nan')):.4f}  "
                      f"m2={enr.get('m2',float('nan')):.4f}  (reste ~{reste}s)")
            time.sleep(max(interval_s - 2, 1))  # features_reseau consomme déjà ~2s
    print(f"✓ Collecte terminée : {n} échantillons dans {BASE_FILE}")


# --------------------------------------------------------------------------- #
def _percentiles(vals, p):
    a = np.array([v for v in vals if v is not None and not np.isnan(v)])
    if len(a) < 10:
        return None
    return {
        "n":    int(len(a)),
        "p05":  float(np.percentile(a, 5)),
        "p50":  float(np.percentile(a, 50)),
        "p90":  float(np.percentile(a, 90)),
        "p99":  float(np.percentile(a, p)),
        "min":  float(a.min()),
        "max":  float(a.max()),
        "std":  float(a.std()),
    }


def _nouvelle_config(stats):
    """Dérive (lo, hi, threshold) robustes depuis les percentiles de base."""
    lo = stats["p50"]
    hi = stats["p99"]
    # Garde-fou : éviter hi<=lo (distribution trop plate) → largeur minimale
    largeur_min = max(stats["std"], 1e-3)
    if hi - lo < largeur_min:
        hi = lo + largeur_min
    threshold = stats["p99"]
    return round(lo, 6), round(hi, 6), round(threshold, 6)


def application(percentile: float):
    if not os.path.exists(BASE_FILE):
        sys.exit(f"✗ Aucune base trouvée : {BASE_FILE}. Lance d'abord --collect.")
    lignes = [json.loads(l) for l in open(BASE_FILE) if l.strip()]
    s1 = _percentiles([r.get("m1") for r in lignes], percentile)
    s2 = _percentiles([r.get("m2") for r in lignes], percentile)
    if not s1 or not s2:
        sys.exit(f"✗ Pas assez d'échantillons (m1={s1 and s1['n']}, m2={s2 and s2['n']}).")

    print(f"\n=== Distribution des scores bruts (base réelle) ===")
    for nom, s in (("M1 réseau", s1), ("M2 UEBA", s2)):
        print(f"  {nom:10} n={s['n']:4}  p05={s['p05']:.4f}  p50={s['p50']:.4f}  "
              f"p90={s['p90']:.4f}  p{int(percentile)}={s['p99']:.4f}  max={s['max']:.4f}")

    lo1, hi1, th1 = _nouvelle_config(s1)
    lo2, hi2, th2 = _nouvelle_config(s2)

    # Sauvegarde des modèles avant modification
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    m1, m2 = _load_models()
    shutil.copy2(M1_PATH, os.path.join(BACKUP_DIR, f"model1_precalib_{ts}.joblib"))
    shutil.copy2(M2_PATH, os.path.join(BACKUP_DIR, f"model2_precalib_{ts}.joblib"))

    print(f"\n=== Nouvelle configuration ===")
    print(f"  M1  ancien : lo={m1['risk_cfg']['lo']:.4f} hi={m1['risk_cfg']['hi']:.4f} "
          f"threshold={m1['threshold']:.4f}")
    print(f"  M1  nouveau: lo={lo1:.4f} hi={hi1:.4f} threshold={th1:.4f}")
    print(f"  M2  ancien : lo={m2['risk_lo']:.4f} hi={m2['risk_hi']:.4f} "
          f"threshold={m2['threshold']:.4f}")
    print(f"  M2  nouveau: lo={lo2:.4f} hi={hi2:.4f} threshold={th2:.4f}")

    m1["risk_cfg"] = {"lo": lo1, "hi": hi1}
    m1["threshold"] = th1
    m1.setdefault("calibration", {}).update(
        {"source": "baseline_reelle", "percentile": percentile, "date": ts, "stats": s1})
    m2["risk_lo"], m2["risk_hi"] = lo2, hi2
    m2["threshold"] = th2
    m2.setdefault("calibration", {}).update(
        {"source": "baseline_reelle", "percentile": percentile, "date": ts, "stats": s2})

    joblib.dump(m1, M1_PATH)
    joblib.dump(m2, M2_PATH)
    print(f"\n✓ Modèles recalibrés (sauvegardes : {BACKUP_DIR}/model{{1,2}}_precalib_{ts}.joblib)")
    print("  → Redémarre le service : systemctl restart nexus-soc")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Recalibration des seuils sur base réelle")
    ap.add_argument("--collect", action="store_true", help="collecter la ligne de base")
    ap.add_argument("--apply",   action="store_true", help="appliquer la recalibration")
    ap.add_argument("--duration", type=int, default=2700, help="durée de collecte (s)")
    ap.add_argument("--interval", type=int, default=15, help="intervalle entre mesures (s)")
    ap.add_argument("--percentile", type=float, default=99.0, help="percentile du seuil")
    a = ap.parse_args()
    if a.collect:
        collecte(a.duration, a.interval)
    elif a.apply:
        application(a.percentile)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
