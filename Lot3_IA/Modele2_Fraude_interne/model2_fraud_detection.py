#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Modèle 2 : Détection de fraude interne (UEBA sur logs structurés)
============================================================================
Détecte les comportements frauduleux dans un système d'information administratif
(type SIGIPES / SYDONIA) en analysant l'activité AGRÉGÉE PAR AGENT ET PAR JOUR.

⚠ Ce n'est PAS du NLP : c'est de la détection d'anomalies comportementales sur
  données structurées (logs d'audit), conformément à l'approche UEBA.

Scénarios de fraude modélisés :
  • Faux mandatement      → modification de montants de paiement élevés, hors heures
  • Fonctionnaire fantôme → création massive de comptes d'agents fictifs
  • Exfiltration          → export massif de données fiscales / contribuables

Particularité : EXPLICABILITÉ — pour chaque alerte, le modèle indique les features
qui s'écartent le plus du profil normal (« raisons » exploitables par un DSI / le LLM Analyst).

Le pipeline tourne sur données synthétiques réalistes (--synthetic) OU sur un fichier de
features agrégées par agent-jour (--data-file), même schéma → transposable à CERT Insider
Threat (CMU/SEI) ou aux journaux d'audit réels.

Usage :
    python model2_fraud_detection.py --synthetic --out ./outputs_m2
    python model2_fraud_detection.py --data-file agent_jour.csv --out ./outputs_m2

Auteur : NGUETSA Junior Stéphane Céleste — Projet NEXUS SOC
"""

import argparse, json, os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             precision_recall_fscore_support, confusion_matrix)
import joblib

warnings.filterwarnings("ignore")
RNG = 42
np.random.seed(RNG)
NAVY, BLUE, TEAL, RED, AMBER, GREY = "#0B2545", "#1C6DD0", "#1B998B", "#C1432E", "#B7791F", "#64748B"

# Features comportementales (profil agent-jour). Noms = colonnes attendues sur données réelles.
FEATURES = [
    "nb_connexions", "nb_actions_hors_heures", "nb_transactions",
    "montant_total_modifie", "nb_modifs_montant", "nb_creations_compte",
    "nb_exports", "volume_donnees_exportees", "nb_acces_dossiers_sensibles",
    "nb_actions_total",
]
# Libellé lisible de chaque feature (pour les "raisons" d'alerte)
LISIBLE = {
    "nb_connexions": "connexions", "nb_actions_hors_heures": "actions hors heures ouvrables",
    "nb_transactions": "transactions budgétaires", "montant_total_modifie": "montant total modifié (FCFA)",
    "nb_modifs_montant": "modifications de montants", "nb_creations_compte": "créations de comptes agents",
    "nb_exports": "exports de données", "volume_donnees_exportees": "volume de données exportées",
    "nb_acces_dossiers_sensibles": "accès à des dossiers sensibles", "nb_actions_total": "actions au total",
}


# --------------------------------------------------------------------------- #
# 1. GÉNÉRATION DE DONNÉES SYNTHÉTIQUES (profils agent-jour)
# --------------------------------------------------------------------------- #
def make_synthetic(n=40000, fraud_ratio=0.10):
    """Génère des profils d'activité agent-jour RÉALISTES. Le trafic normal inclut
    une « zone grise » (pics de fin de mois, RH, exports légitimes) qui chevauche les
    fraudes — la séparation n'est donc pas triviale, comme dans la réalité."""
    n_fraud = int(n * fraud_ratio)
    n_norm = n - n_fraud

    def normal(m):
        return pd.DataFrame({
            "nb_connexions":               np.random.poisson(2, m) + 1,
            "nb_actions_hors_heures":      np.random.poisson(0.3, m),
            "nb_transactions":             np.random.poisson(12, m),
            "montant_total_modifie":       np.random.lognormal(10, 1.2, m) * (np.random.random(m) < 0.5),
            "nb_modifs_montant":           np.random.poisson(1.2, m),
            "nb_creations_compte":         np.random.poisson(0.06, m),
            "nb_exports":                  np.random.poisson(0.5, m),
            "volume_donnees_exportees":    np.random.poisson(0.5, m) * np.random.lognormal(4, 1, m),
            "nb_acces_dossiers_sensibles": np.random.poisson(3, m),
            "nb_actions_total":            np.random.poisson(40, m) + 5,
        })

    df = normal(n_norm)
    # --- zone grise : activité légitime mais élevée (rend la détection non triviale) ---
    pu = np.random.random(n_norm) < 0.08                      # pics de fin de mois
    df.loc[pu, "nb_transactions"]       = np.random.poisson(35, pu.sum()) + 10
    df.loc[pu, "montant_total_modifie"] = np.random.lognormal(13, 0.8, pu.sum())
    df.loc[pu, "nb_modifs_montant"]     = np.random.poisson(4, pu.sum()) + 1
    df.loc[pu, "nb_actions_total"]      = np.random.poisson(85, pu.sum()) + 20
    hr = np.random.random(n_norm) < 0.03                      # RH : onboarding légitime
    df.loc[hr, "nb_creations_compte"]   = np.random.randint(1, 7, hr.sum())
    be = np.random.random(n_norm) < 0.05                      # exports légitimes en masse
    df.loc[be, "nb_exports"]            = np.random.randint(2, 9, be.sum())
    df.loc[be, "volume_donnees_exportees"]   = np.random.lognormal(8, 1.0, be.sum())
    df.loc[be, "nb_acces_dossiers_sensibles"] = np.random.poisson(12, be.sum()) + 3
    ot = np.random.random(n_norm) < 0.06                      # heures supplémentaires légitimes
    df.loc[ot, "nb_actions_hors_heures"] = np.random.poisson(3, ot.sum()) + 1
    df["type"] = "Normal"

    a = n_fraud // 3; b = n_fraud // 3; c = n_fraud - a - b

    f1 = normal(a)                                  # Faux mandatement (chevauche les pics légitimes)
    f1["montant_total_modifie"]  = np.random.lognormal(13.8, 0.7, a)
    f1["nb_modifs_montant"]      = np.random.randint(3, 12, a)
    f1["nb_actions_hors_heures"] = np.random.poisson(3, a) + 1
    f1["type"] = "Faux mandatement"

    f2 = normal(b)                                  # Fonctionnaire fantôme (chevauche les RH)
    f2["nb_creations_compte"] = np.random.randint(5, 18, b)
    f2["nb_transactions"]     = np.random.poisson(25, b) + 5
    f2["nb_actions_total"]    = np.random.poisson(70, b) + 20
    f2["type"] = "Fonctionnaire fantôme"

    f3 = normal(c)                                  # Exfiltration (chevauche les exports légitimes)
    f3["nb_exports"]                  = np.random.randint(6, 30, c)
    f3["volume_donnees_exportees"]    = np.random.lognormal(9, 0.9, c)
    f3["nb_acces_dossiers_sensibles"] = np.random.poisson(25, c) + 8
    f3["nb_actions_hors_heures"]      = np.random.poisson(2, c)
    f3["type"] = "Exfiltration"

    data = pd.concat([df, f1, f2, f3], ignore_index=True)
    return data.sample(frac=1, random_state=RNG).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 2. PRÉTRAITEMENT
# --------------------------------------------------------------------------- #
def preprocess(df):
    df = df.copy()
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes : {missing}")
    types = df["type"].astype(str).values if "type" in df.columns else np.array(["?"] * len(df))
    y = np.array([0 if str(t).upper() == "NORMAL" else 1 for t in types], dtype=int)
    X = df[FEATURES].replace([np.inf, -np.inf], np.nan)
    mask = (~X.isna().any(axis=1)).values
    X, y, types = X[mask].values, y[mask], types[mask]
    print(f"  → {X.shape[0]:,} profils agent-jour · {len(FEATURES)} features · "
          f"{y.mean()*100:.1f}% de fraudes")
    return X, y, types


# --------------------------------------------------------------------------- #
# 3. EXPLICABILITÉ — raisons d'une alerte
# --------------------------------------------------------------------------- #
def reasons(x_row, mean, std, k=3):
    """Retourne les k features qui s'écartent le plus (vers le haut) du profil normal."""
    z = (x_row - mean) / np.where(std > 1e-9, std, 1e-9)
    order = np.argsort(z)[::-1]
    out = []
    for i in order[:k]:
        if z[i] > 1.5:    # écart significatif uniquement
            out.append(f"{LISIBLE[FEATURES[i]]} anormalement élevé ({z[i]:.1f}σ)")
    return out or ["profil globalement atypique"]


# --------------------------------------------------------------------------- #
# 4. ENTRAÎNEMENT + ÉVALUATION
# --------------------------------------------------------------------------- #
def train_eval(X, y, types, out_dir, contamination=0.04):
    os.makedirs(out_dir, exist_ok=True)
    X_tr, X_te, y_tr, y_te, _, t_te = train_test_split(
        X, y, types, test_size=0.30, stratify=y, random_state=RNG)
    X_tr_norm = X_tr[y_tr == 0]                       # entraînement sur le NORMAL uniquement

    scaler = StandardScaler().fit(X_tr_norm)
    model = IsolationForest(n_estimators=200, contamination=contamination,
                            random_state=RNG, n_jobs=-1).fit(scaler.transform(X_tr_norm))

    s_tr = -model.score_samples(scaler.transform(X_tr_norm))
    s_te = -model.score_samples(scaler.transform(X_te))
    thr = np.quantile(s_tr, 1 - contamination)
    y_pred = (s_te >= thr).astype(int)

    prec, _, f1, _ = precision_recall_fscore_support(y_te, y_pred, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(y_te, y_pred).ravel()
    metrics = {
        "roc_auc": round(roc_auc_score(y_te, s_te), 4),
        "pr_auc": round(average_precision_score(y_te, s_te), 4),
        "taux_detection": round(tp / (tp + fn), 4) if (tp + fn) else 0,
        "taux_faux_positifs": round(fp / (fp + tn), 4) if (fp + tn) else 0,
        "precision": round(prec, 4), "f1": round(f1, 4),
        "matrice": {"VN": int(tn), "FP": int(fp), "FN": int(fn), "VP": int(tp)},
        "detection_par_type": {}, "n_test": int(len(y_te)),
    }
    for t in sorted(set(t_te)):
        if t.upper() != "NORMAL":
            idx = (t_te == t)
            metrics["detection_par_type"][t] = {
                "profils": int(idx.sum()),
                "taux_detection": round(float(y_pred[idx].mean()), 4)}

    print("\n  ===== RÉSULTATS (jeu de test) =====")
    print(f"  ROC-AUC ............. {metrics['roc_auc']:.3f}   PR-AUC : {metrics['pr_auc']:.3f}")
    print(f"  Taux de détection ... {metrics['taux_detection']*100:.1f}%")
    print(f"  Faux positifs ....... {metrics['taux_faux_positifs']*100:.1f}%   F1 : {metrics['f1']:.3f}")
    print("  Détection par type de fraude :")
    for t, v in metrics["detection_par_type"].items():
        print(f"     {t:<22} {v['taux_detection']*100:5.1f}%   (n={v['profils']})")

    # --- explicabilité : exemples d'alertes avec raisons ---
    mean, std = X_tr_norm.mean(0), X_tr_norm.std(0)
    lo, hi = np.quantile(s_tr, 0.5), np.quantile(s_te, 0.999)
    flagged = np.where((y_pred == 1) & (y_te == 1))[0]
    examples = []
    for i in flagged[:12]:
        risk = int(np.clip((s_te[i] - lo) / (hi - lo) * 100, 0, 100))
        examples.append({"type_reel": t_te[i], "score_risque": risk,
                         "raisons": "; ".join(reasons(X_te[i], mean, std))})
    pd.DataFrame(examples).to_csv(f"{out_dir}/exemples_alertes.csv", index=False)
    print("\n  Exemples d'alertes expliquées :")
    for e in examples[:4]:
        print(f"     [risque {e['score_risque']}/100] {e['type_reel']} — {e['raisons']}")

    _plots(y_te, s_te, thr, t_te, X_te, X_tr_norm, metrics, out_dir)
    joblib.dump({"model": model, "scaler": scaler, "features": FEATURES,
                 "threshold": float(thr), "normal_mean": mean, "normal_std": std,
                 "risk_lo": float(lo), "risk_hi": float(hi)},
                f"{out_dir}/model2_isoforest.joblib")
    with open(f"{out_dir}/metrics.json", "w") as fh:
        json.dump(metrics, fh, indent=2, ensure_ascii=False)
    print(f"\n  Modèle, métriques et exemples sauvegardés dans {out_dir}/")
    return metrics


def _plots(y_te, s_te, thr, t_te, X_te, X_norm, metrics, out_dir):
    # (a) distribution des scores
    fig, ax = plt.subplots(figsize=(8, 4.5))
    hi = np.quantile(s_te, 0.999)
    ax.hist(np.clip(s_te[y_te == 0], None, hi), bins=60, alpha=.7, color=TEAL, label="Normal", density=True)
    ax.hist(np.clip(s_te[y_te == 1], None, hi), bins=60, alpha=.7, color=RED, label="Fraude", density=True)
    ax.axvline(thr, color=NAVY, ls="--", lw=1.5, label="Seuil")
    ax.set_xlabel("Score d'anomalie"); ax.set_ylabel("Densité")
    ax.set_title("Modèle 2 — distribution des scores (agent-jour)", color=NAVY, weight="bold")
    ax.legend(); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(f"{out_dir}/scores_distribution.png", dpi=170); plt.close(fig)

    # (b) détection par type de fraude
    types = list(metrics["detection_par_type"])
    vals = [metrics["detection_par_type"][t]["taux_detection"] for t in types]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    bars = ax.bar(types, vals, color=[RED, AMBER, BLUE][:len(types)], width=0.55)
    ax.bar_label(bars, labels=[f"{v*100:.0f}%" for v in vals], padding=3, fontsize=9, weight="bold")
    ax.set_ylim(0, 1.12); ax.set_ylabel("Taux de détection")
    ax.set_title("Détection par type de fraude interne", color=NAVY, weight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(f"{out_dir}/detection_by_fraud_type.png", dpi=170); plt.close(fig)

    # (c) signatures : écart (z-score) moyen de chaque type de fraude par feature
    mean, std = X_norm.mean(0), np.where(X_norm.std(0) > 1e-9, X_norm.std(0), 1e-9)
    sig = []
    for t in types:
        idx = (t_te == t)
        sig.append(np.clip(((X_te[idx] - mean) / std).mean(0), 0, 6))
    sig = np.array(sig)
    fig, ax = plt.subplots(figsize=(11, 3.6))
    im = ax.imshow(sig, cmap="Reds", aspect="auto", vmin=0, vmax=6)
    ax.set_xticks(range(len(FEATURES)))
    ax.set_xticklabels([LISIBLE[f] for f in FEATURES], rotation=35, ha="right", fontsize=7.5)
    ax.set_yticks(range(len(types))); ax.set_yticklabels(types, fontsize=9)
    for i in range(len(types)):
        for j in range(len(FEATURES)):
            if sig[i, j] > 1.2:
                ax.text(j, i, f"{sig[i,j]:.0f}σ", ha="center", va="center",
                        fontsize=7, color="white" if sig[i, j] > 3 else NAVY)
    ax.set_title("Signature comportementale de chaque fraude (écart au profil normal)",
                 color=NAVY, weight="bold", fontsize=11)
    fig.colorbar(im, ax=ax, shrink=0.8, label="écart (σ)")
    fig.tight_layout(); fig.savefig(f"{out_dir}/fraud_signatures.png", dpi=170); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="NEXUS SOC — Modèle 2 (fraude interne)")
    ap.add_argument("--data-file", help="CSV de features agrégées par agent-jour")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out", default="./outputs_m2")
    ap.add_argument("--contamination", type=float, default=0.04)
    args = ap.parse_args()

    print("NEXUS SOC — Modèle 2 : détection de fraude interne (UEBA)\n" + "=" * 57)
    if args.data_file and not args.synthetic:
        print(f"[1/3] Chargement {args.data_file}")
        df = pd.read_csv(args.data_file)
    else:
        print("[1/3] Génération de profils agent-jour synthétiques (démonstration)")
        df = make_synthetic()
        print(f"  → {len(df):,} profils générés")
    print("[2/3] Prétraitement")
    X, y, types = preprocess(df)
    print("[3/3] Entraînement Isolation Forest + évaluation + explicabilité")
    train_eval(X, y, types, args.out, contamination=args.contamination)


if __name__ == "__main__":
    main()
