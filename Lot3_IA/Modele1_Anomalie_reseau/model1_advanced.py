#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Modèle 1 (avancé) : Autoencodeur vs Isolation Forest
================================================================
Étoffe le Modèle 1 avec :
  1. une variante AUTOENCODEUR (réseau de neurones à goulot d'étranglement),
     dont le score d'anomalie est l'erreur de reconstruction ;
  2. une COMPARAISON chiffrée des deux modèles (ROC-AUC, PR-AUC, détection, FPR, F1) ;
  3. une ANALYSE de la détection PAR TYPE D'ATTAQUE (DDoS, PortScan, Bot/C2…).

L'autoencodeur est ici réalisé avec scikit-learn (MLPRegressor) pour rester léger et
exécutable ; son architecture (encodeur → goulot → décodeur) se transpose directement
en PyTorch/Keras pour la version de production.

Usage :
    python model1_advanced.py --synthetic --out ./outputs_advanced
    python model1_advanced.py --data-dir ./CICIDS2017 --out ./outputs_advanced

Auteur : NGUETSA Junior Stéphane Céleste — Projet NEXUS SOC
"""

import argparse
import json
import os
import warnings

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.ensemble import IsolationForest
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             precision_recall_fscore_support, confusion_matrix)
import joblib

# réutilise le chargement / prétraitement du pipeline de base
from model1_anomaly_detection import make_synthetic, load_cicids2017, preprocess

warnings.filterwarnings("ignore")
RNG = 42
np.random.seed(RNG)
NAVY, BLUE, TEAL, RED, AMBER, GREY = "#0B2545", "#1C6DD0", "#1B998B", "#C1432E", "#B7791F", "#64748B"


# --------------------------------------------------------------------------- #
# Score d'anomalie par modèle
# --------------------------------------------------------------------------- #
def isoforest_scores(X_tr_benign, X_te, contamination):
    m = IsolationForest(n_estimators=200, contamination=contamination,
                        max_samples="auto", random_state=RNG, n_jobs=-1)
    m.fit(X_tr_benign)
    s_tr = -m.score_samples(X_tr_benign)   # plus haut = plus anormal
    s_te = -m.score_samples(X_te)
    return m, s_tr, s_te


def autoencoder_scores(X_tr_benign, X_te):
    """Autoencodeur : on apprend à reconstruire le trafic NORMAL.
    L'erreur de reconstruction (MSE par flux) sert de score d'anomalie."""
    ae = MLPRegressor(hidden_layer_sizes=(16, 6, 16), activation="relu",
                      solver="adam", max_iter=400, early_stopping=True,
                      random_state=RNG)
    ae.fit(X_tr_benign, X_tr_benign)            # X -> X (auto-reconstruction)
    err = lambda Z: np.mean((Z - ae.predict(Z)) ** 2, axis=1)
    return ae, err(X_tr_benign), err(X_te)


# --------------------------------------------------------------------------- #
# Métriques
# --------------------------------------------------------------------------- #
def evaluate(y_te, scores, thr):
    y_pred = (scores >= thr).astype(int)
    prec, _, f1, _ = precision_recall_fscore_support(
        y_te, y_pred, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(y_te, y_pred).ravel()
    return {
        "roc_auc": roc_auc_score(y_te, scores),
        "pr_auc": average_precision_score(y_te, scores),
        "detection_rate": tp / (tp + fn) if (tp + fn) else 0.0,
        "false_positive_rate": fp / (fp + tn) if (fp + tn) else 0.0,
        "precision": prec, "f1": f1,
        "cm": {"TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp)},
    }, y_pred


def detection_by_type(lbl_te, y_pred):
    """Taux de détection par famille d'attaque + FPR sur le trafic normal."""
    out = {}
    for t in sorted(set(lbl_te)):
        idx = (lbl_te == t)
        flagged = y_pred[idx].mean()
        if t.upper() == "BENIGN":
            out[t] = {"flux": int(idx.sum()), "taux_faux_positifs": round(float(flagged), 4)}
        else:
            out[t] = {"flux": int(idx.sum()), "taux_detection": round(float(flagged), 4)}
    return out


# --------------------------------------------------------------------------- #
# Graphiques
# --------------------------------------------------------------------------- #
def plot_comparison(mif, mae, out_dir):
    labels = ["ROC-AUC", "PR-AUC", "Détection", "F1", "Faux positifs"]
    vif = [mif["roc_auc"], mif["pr_auc"], mif["detection_rate"], mif["f1"], mif["false_positive_rate"]]
    vae = [mae["roc_auc"], mae["pr_auc"], mae["detection_rate"], mae["f1"], mae["false_positive_rate"]]
    x = np.arange(len(labels)); w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4.8))
    b1 = ax.bar(x - w/2, vif, w, color=BLUE, label="Isolation Forest")
    b2 = ax.bar(x + w/2, vae, w, color=TEAL, label="Autoencodeur")
    for b in (b1, b2):
        ax.bar_label(b, fmt="%.2f", fontsize=8, padding=2)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.08); ax.set_ylabel("Score")
    ax.set_title("Comparaison Isolation Forest vs Autoencodeur", color=NAVY, weight="bold")
    ax.legend(); ax.spines[["top", "right"]].set_visible(False)
    ax.text(0.5, -0.16, "(pour « Faux positifs », plus bas = mieux)", transform=ax.transAxes,
            ha="center", fontsize=8, color=GREY)
    fig.tight_layout(); fig.savefig(f"{out_dir}/model_comparison.png", dpi=170); plt.close(fig)


def plot_by_type(dt_if, dt_ae, out_dir):
    types = [t for t in dt_if if "taux_detection" in dt_if[t]]
    vif = [dt_if[t]["taux_detection"] for t in types]
    vae = [dt_ae[t]["taux_detection"] for t in types]
    x = np.arange(len(types)); w = 0.38
    fig, ax = plt.subplots(figsize=(8, 4.6))
    b1 = ax.bar(x - w/2, vif, w, color=BLUE, label="Isolation Forest")
    b2 = ax.bar(x + w/2, vae, w, color=TEAL, label="Autoencodeur")
    for b in (b1, b2):
        ax.bar_label(b, fmt="%.0f%%", labels=[f"{v*100:.0f}%" for v in b.datavalues],
                     fontsize=8, padding=2)
    ax.set_xticks(x); ax.set_xticklabels(types)
    ax.set_ylim(0, 1.12); ax.set_ylabel("Taux de détection")
    ax.set_title("Taux de détection par type d'attaque", color=NAVY, weight="bold")
    ax.legend(); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(f"{out_dir}/detection_by_attack_type.png", dpi=170); plt.close(fig)


def plot_ae_error(y_te, err, thr, out_dir):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    hi = np.quantile(err, 0.995)
    ax.hist(np.clip(err[y_te == 0], 0, hi), bins=60, alpha=.7, color=TEAL, label="Normal", density=True)
    ax.hist(np.clip(err[y_te == 1], 0, hi), bins=60, alpha=.7, color=RED, label="Attaque", density=True)
    ax.axvline(thr, color=NAVY, ls="--", lw=1.5, label="Seuil")
    ax.set_xlabel("Erreur de reconstruction (MSE)"); ax.set_ylabel("Densité")
    ax.set_title("Autoencodeur — erreur de reconstruction", color=NAVY, weight="bold")
    ax.legend(); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(f"{out_dir}/autoencoder_error_distribution.png", dpi=170); plt.close(fig)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="NEXUS SOC — Modèle 1 avancé")
    ap.add_argument("--data-dir"); ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out", default="./outputs_advanced")
    ap.add_argument("--contamination", type=float, default=0.05)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    print("NEXUS SOC — Modèle 1 avancé (Autoencodeur vs Isolation Forest)\n" + "=" * 62)
    if args.data_dir and not args.synthetic:
        df = load_cicids2017(args.data_dir)
    else:
        print("Génération d'un jeu synthétique réaliste (mode démonstration)")
        df = make_synthetic()
    X, y, labels, feats = preprocess(df)

    # Split commun ; on conserve les types d'attaque pour le test
    X_tr, X_te, y_tr, y_te, _, lbl_te = train_test_split(
        X, y, labels, test_size=0.30, stratify=y, random_state=RNG)
    scaler = StandardScaler().fit(X_tr[y_tr == 0])
    Xtr_b = scaler.transform(X_tr[y_tr == 0])
    Xte = scaler.transform(X_te)

    print("Entraînement Isolation Forest…")
    m_if, sif_tr, sif_te = isoforest_scores(Xtr_b, Xte, args.contamination)
    print("Entraînement Autoencodeur…")
    m_ae, sae_tr, sae_te = autoencoder_scores(Xtr_b, Xte)

    # Seuils opérationnels fixés sur le trafic normal du train (non supervisé)
    thr_if = np.quantile(sif_tr, 1 - args.contamination)
    thr_ae = np.quantile(sae_tr, 1 - args.contamination)

    mif, pred_if = evaluate(y_te, sif_te, thr_if)
    mae, pred_ae = evaluate(y_te, sae_te, thr_ae)
    dt_if = detection_by_type(lbl_te, pred_if)
    dt_ae = detection_by_type(lbl_te, pred_ae)

    # Affichage comparatif
    print("\n  ===== COMPARAISON (jeu de test) =====")
    print(f"  {'Métrique':<22}{'Iso. Forest':>14}{'Autoencodeur':>16}")
    for k, lab in [("roc_auc", "ROC-AUC"), ("pr_auc", "PR-AUC"),
                   ("detection_rate", "Taux de détection"), ("false_positive_rate", "Faux positifs"),
                   ("precision", "Précision"), ("f1", "F1")]:
        print(f"  {lab:<22}{mif[k]:>14.3f}{mae[k]:>16.3f}")
    print("\n  --- Détection par type d'attaque ---")
    for t in dt_if:
        if "taux_detection" in dt_if[t]:
            print(f"  {t:<12} IF={dt_if[t]['taux_detection']*100:5.1f}%   "
                  f"AE={dt_ae[t]['taux_detection']*100:5.1f}%   (n={dt_if[t]['flux']})")

    # Graphiques + sauvegardes
    plot_comparison(mif, mae, args.out)
    plot_by_type(dt_if, dt_ae, args.out)
    plot_ae_error(y_te, sae_te, thr_ae, args.out)

    payload = {
        "isolation_forest": {**{k: round(float(v), 4) for k, v in mif.items() if k != "cm"},
                             "cm": mif["cm"], "detection_par_type": dt_if},
        "autoencodeur": {**{k: round(float(v), 4) for k, v in mae.items() if k != "cm"},
                         "cm": mae["cm"], "detection_par_type": dt_ae},
        "n_test": int(len(y_te)), "n_features": int(X.shape[1]),
    }
    with open(f"{args.out}/comparison_metrics.json", "w") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    joblib.dump({"isoforest": m_if, "autoencoder": m_ae, "scaler": scaler,
                 "features": feats, "thr_if": float(thr_if), "thr_ae": float(thr_ae)},
                f"{args.out}/model1_both.joblib")
    print(f"\n  Comparaison, graphiques et modèles sauvegardés dans {args.out}/")


if __name__ == "__main__":
    main()
