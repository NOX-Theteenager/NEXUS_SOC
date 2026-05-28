#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Modèle 1 : Détection d'anomalies réseau (non supervisée)
====================================================================
Apprend le profil du trafic réseau NORMAL et signale tout écart : volume
sortant anormal, connexions atypiques, scans, communications C2, etc.

Algorithme : Isolation Forest (apprentissage non supervisé).
Données    : CICIDS2017 / CSE-CIC-IDS2018 (features de flux CICFlowMeter).

Le pipeline fonctionne À L'IDENTIQUE sur les vraies données et sur un jeu
synthétique réaliste (option --synthetic), ce qui permet de le tester sans
disposer du dataset, puis de basculer sur CICIDS2017 sans changer le code.

Usage :
    # Données réelles (dossier contenant les CSV CICIDS2017) :
    python model1_anomaly_detection.py --data-dir ./CICIDS2017 --out ./outputs

    # Démonstration sur données synthétiques :
    python model1_anomaly_detection.py --synthetic --out ./outputs

Auteur : NGUETSA Junior Stéphane Céleste — Projet NEXUS SOC
"""

import argparse
import glob
import json
import os
import warnings

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (roc_auc_score, average_precision_score, roc_curve,
                             precision_recall_fscore_support, confusion_matrix)
import joblib

warnings.filterwarnings("ignore")
RNG = 42
np.random.seed(RNG)

# Colonnes à exclure (identifiants / fuites / cible) — noms CICIDS2017 nettoyés
LEAK_COLS = {
    "Flow ID", "Source IP", "Src IP", "Source Port", "Src Port",
    "Destination IP", "Dst IP", "Timestamp", "Label", "Fwd Header Length.1",
}

NAVY, BLUE, TEAL, RED, GREY = "#0B2545", "#1C6DD0", "#1B998B", "#C1432E", "#64748B"


# --------------------------------------------------------------------------- #
# 1. CHARGEMENT DES DONNÉES
# --------------------------------------------------------------------------- #
def load_cicids2017(data_dir):
    """Charge et concatène tous les CSV CICIDS2017 d'un dossier.
    Corrige le défaut connu : espaces en tête de noms de colonnes."""
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    if not files:
        raise FileNotFoundError(f"Aucun CSV trouvé dans {data_dir}")
    frames = []
    for f in files:
        print(f"  · lecture {os.path.basename(f)}")
        df = pd.read_csv(f, low_memory=False, encoding="latin-1")
        df.columns = [c.strip() for c in df.columns]   # <- gotcha CICIDS2017
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    print(f"  → {len(data):,} flux chargés, {data.shape[1]} colonnes")
    return data


def make_synthetic(n=60000, attack_ratio=0.18):
    """Génère un trafic de flux réaliste imitant la structure de CICIDS2017.
    Le trafic normal forme un nuage cohérent ; les attaques s'en écartent."""
    n_att = int(n * attack_ratio)
    n_ben = n - n_att

    def benign(m):
        return pd.DataFrame({
            "Destination Port":        np.random.choice([80, 443, 53, 22, 3389], m, p=[.4, .4, .1, .05, .05]),
            "Flow Duration":           np.random.lognormal(11, 1.1, m),
            "Total Fwd Packets":       np.random.lognormal(2.2, 0.8, m).astype(int) + 1,
            "Total Backward Packets":  np.random.lognormal(2.0, 0.8, m).astype(int) + 1,
            "Flow Bytes/s":            np.random.lognormal(9, 1.0, m),
            "Flow Packets/s":          np.random.lognormal(3, 0.9, m),
            "Fwd Packet Length Mean":  np.random.normal(350, 120, m).clip(20),
            "Bwd Packet Length Mean":  np.random.normal(500, 200, m).clip(20),
            "Flow IAT Mean":           np.random.lognormal(8, 1.0, m),
            "Min Packet Length":       np.random.normal(40, 12, m).clip(0),
            "Max Packet Length":       np.random.normal(1200, 300, m).clip(40),
            "Average Packet Size":     np.random.normal(450, 150, m).clip(20),
        })

    df_ben = benign(n_ben)
    df_ben["Label"] = "BENIGN"

    # --- attaques : trois familles qui s'écartent du normal ---
    a = n_att // 3
    b = n_att // 3
    c = n_att - a - b

    ddos = benign(a)                      # DDoS : débit & paquets très élevés
    ddos["Flow Packets/s"] *= np.random.uniform(15, 40, a)
    ddos["Total Fwd Packets"] = (ddos["Total Fwd Packets"] * np.random.uniform(8, 20, a)).astype(int)
    ddos["Flow Bytes/s"] *= np.random.uniform(10, 30, a)
    ddos["Flow IAT Mean"] *= np.random.uniform(0.01, 0.05, a)
    ddos["Label"] = "DDoS"

    scan = benign(b)                      # PortScan : flux minuscules, ports variés
    scan["Destination Port"] = np.random.randint(1, 65535, b)
    scan["Total Fwd Packets"] = np.random.randint(1, 3, b)
    scan["Total Backward Packets"] = np.random.randint(0, 2, b)
    scan["Flow Bytes/s"] *= np.random.uniform(0.01, 0.08, b)
    scan["Average Packet Size"] = np.random.normal(60, 20, b).clip(0)
    scan["Label"] = "PortScan"

    c2 = benign(c)                        # C2 / exfiltration : ports rares, gros volume sortant
    c2["Destination Port"] = np.random.choice([4444, 8080, 6667, 1337, 9001], c)
    c2["Flow Bytes/s"] *= np.random.uniform(5, 15, c)
    c2["Fwd Packet Length Mean"] = np.random.normal(1400, 80, c).clip(20)
    c2["Flow IAT Mean"] *= np.random.uniform(2, 6, c)
    c2["Label"] = "Bot/C2"

    data = pd.concat([df_ben, ddos, scan, c2], ignore_index=True)
    return data.sample(frac=1, random_state=RNG).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 2. PRÉTRAITEMENT
# --------------------------------------------------------------------------- #
def preprocess(df):
    """Nettoyage + sélection des features numériques. Retourne X, y, noms.
    y (0 = BENIGN, 1 = attaque) ne sert QU'À l'évaluation, jamais à l'entraînement."""
    df = df.copy()
    if "Label" not in df.columns:
        raise ValueError("Colonne 'Label' absente.")
    y = (df["Label"].astype(str).str.upper() != "BENIGN").astype(int).values

    # remplacer +/-inf par NaN puis supprimer les lignes incomplètes
    df = df.replace([np.inf, -np.inf], np.nan)

    # garder uniquement les colonnes numériques, hors fuites/identifiants
    feat_cols = [c for c in df.columns
                 if c not in LEAK_COLS and pd.api.types.is_numeric_dtype(df[c])]
    X = df[feat_cols]

    # supprimer les colonnes constantes (variance nulle) et imputer le reste
    keep = [c for c in feat_cols if X[c].nunique(dropna=True) > 1]
    X = X[keep]
    mask = ~X.isna().any(axis=1)
    X, y = X[mask].values, y[mask]
    print(f"  → {X.shape[0]:,} flux retenus · {X.shape[1]} features · "
          f"{y.mean()*100:.1f}% d'attaques")
    return X, y, keep


# --------------------------------------------------------------------------- #
# 3. ENTRAÎNEMENT + ÉVALUATION
# --------------------------------------------------------------------------- #
def train_eval(X, y, feat_names, out_dir, contamination=0.05):
    os.makedirs(out_dir, exist_ok=True)

    # Split stratifié. On ENTRAÎNE uniquement sur le trafic BENIN du train
    # (apprentissage du "normal"), conformément à la logique non supervisée.
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.30, stratify=y, random_state=RNG)
    X_tr_benign = X_tr[y_tr == 0]

    scaler = StandardScaler().fit(X_tr_benign)
    Xtr_s = scaler.transform(X_tr_benign)
    Xte_s = scaler.transform(X_te)

    model = IsolationForest(
        n_estimators=200, contamination=contamination,
        max_samples="auto", random_state=RNG, n_jobs=-1)
    model.fit(Xtr_s)

    # score_samples : plus c'est BAS, plus c'est anormal -> score d'anomalie = -score
    anomaly_te = -model.score_samples(Xte_s)
    anomaly_tr = -model.score_samples(scaler.transform(X_tr_benign))

    # Seuil OPÉRATIONNEL fixé sur le trafic normal du train (non supervisé) :
    # on tolère ~contamination de faux positifs sur le normal.
    threshold = np.quantile(anomaly_tr, 1 - contamination)
    y_pred = (anomaly_te >= threshold).astype(int)

    # --- métriques ---
    roc = roc_auc_score(y_te, anomaly_te)
    pr_auc = average_precision_score(y_te, anomaly_te)
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_te, y_pred, average="binary", zero_division=0)
    cm = confusion_matrix(y_te, y_pred)
    tn, fp, fn, tp = cm.ravel()
    detection_rate = tp / (tp + fn) if (tp + fn) else 0      # recall sur attaques
    fpr = fp / (fp + tn) if (fp + tn) else 0                 # taux de faux positifs

    metrics = {
        "roc_auc": round(roc, 4), "pr_auc": round(pr_auc, 4),
        "precision": round(prec, 4), "recall_detection_rate": round(detection_rate, 4),
        "f1": round(f1, 4), "false_positive_rate": round(fpr, 4),
        "threshold": round(float(threshold), 6),
        "confusion_matrix": {"TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp)},
        "n_test": int(len(y_te)), "n_features": int(X.shape[1]),
        "contamination": contamination,
    }

    print("\n  ===== RÉSULTATS (jeu de test) =====")
    print(f"  ROC-AUC ................. {roc:.3f}")
    print(f"  PR-AUC .................. {pr_auc:.3f}")
    print(f"  Taux de détection ....... {detection_rate*100:.1f}%")
    print(f"  Taux de faux positifs ... {fpr*100:.1f}%")
    print(f"  Précision / F1 .......... {prec:.3f} / {f1:.3f}")
    print(f"  Matrice : TN={tn} FP={fp} FN={fn} TP={tp}")

    # --- score de risque NEXUS 0-100 (réutilisable par la plateforme) ---
    lo, hi = np.quantile(anomaly_tr, 0.01), np.quantile(anomaly_te, 0.999)
    risk_cfg = {"lo": float(lo), "hi": float(hi)}

    _plots(y_te, anomaly_te, threshold, cm, model, feat_names, out_dir)

    # --- sauvegarde du modèle pour intégration plateforme ---
    joblib.dump({"model": model, "scaler": scaler, "features": feat_names,
                 "threshold": float(threshold), "risk_cfg": risk_cfg},
                os.path.join(out_dir, "model1_isoforest.joblib"))
    with open(os.path.join(out_dir, "metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2, ensure_ascii=False)
    print(f"\n  Modèle + métriques sauvegardés dans {out_dir}/")
    return metrics


def _plots(y_te, scores, thr, cm, model, feat_names, out_dir):
    # (a) distribution des scores benin vs attaque
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(scores[y_te == 0], bins=60, alpha=.7, color=TEAL, label="Normal (BENIGN)", density=True)
    ax.hist(scores[y_te == 1], bins=60, alpha=.7, color=RED, label="Attaque", density=True)
    ax.axvline(thr, color=NAVY, ls="--", lw=1.5, label=f"Seuil = {thr:.3f}")
    ax.set_xlabel("Score d'anomalie"); ax.set_ylabel("Densité")
    ax.set_title("Distribution des scores d'anomalie", color=NAVY, weight="bold")
    ax.legend(); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(f"{out_dir}/scores_distribution.png", dpi=170); plt.close(fig)

    # (b) courbe ROC
    fpr_c, tpr_c, _ = roc_curve(y_te, scores)
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot(fpr_c, tpr_c, color=BLUE, lw=2, label=f"AUC = {roc_auc_score(y_te, scores):.3f}")
    ax.plot([0, 1], [0, 1], color=GREY, ls=":")
    ax.set_xlabel("Taux de faux positifs"); ax.set_ylabel("Taux de détection")
    ax.set_title("Courbe ROC", color=NAVY, weight="bold")
    ax.legend(loc="lower right"); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(f"{out_dir}/roc_curve.png", dpi=170); plt.close(fig)

    # (c) matrice de confusion
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    im = ax.imshow(cm, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        ax.text(j, i, f"{v:,}", ha="center", va="center",
                color="white" if v > cm.max()/2 else NAVY, fontsize=12, weight="bold")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Normal", "Attaque"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["Normal", "Attaque"])
    ax.set_xlabel("Prédiction"); ax.set_ylabel("Réalité")
    ax.set_title("Matrice de confusion", color=NAVY, weight="bold")
    fig.tight_layout(); fig.savefig(f"{out_dir}/confusion_matrix.png", dpi=170); plt.close(fig)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="NEXUS SOC — Modèle 1 (anomalies réseau)")
    ap.add_argument("--data-dir", help="dossier des CSV CICIDS2017")
    ap.add_argument("--synthetic", action="store_true", help="utiliser des données synthétiques")
    ap.add_argument("--out", default="./outputs", help="dossier de sortie")
    ap.add_argument("--contamination", type=float, default=0.05)
    args = ap.parse_args()

    print("NEXUS SOC — Modèle 1 : détection d'anomalies réseau\n" + "=" * 52)
    if args.data_dir and not args.synthetic:
        print(f"[1/3] Chargement CICIDS2017 depuis {args.data_dir}")
        df = load_cicids2017(args.data_dir)
    else:
        print("[1/3] Génération d'un jeu synthétique réaliste (mode démonstration)")
        df = make_synthetic()
        print(f"  → {len(df):,} flux générés")

    print("[2/3] Prétraitement")
    X, y, feats = preprocess(df)

    print("[3/3] Entraînement Isolation Forest + évaluation")
    train_eval(X, y, feats, args.out, contamination=args.contamination)


if __name__ == "__main__":
    main()
