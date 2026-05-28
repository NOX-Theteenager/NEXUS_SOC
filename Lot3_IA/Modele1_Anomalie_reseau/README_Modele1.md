# NEXUS SOC — Modèle 1 : Détection d'anomalies réseau

Détection **non supervisée** d'anomalies dans le trafic réseau : le modèle apprend le profil
du trafic *normal* d'une organisation et signale tout écart (volume sortant anormal, scans de
ports, communications C2, débits anormaux, ports atypiques…). Algorithme : **Isolation Forest**.

---

## 1. Contenu

| Fichier | Rôle |
|---|---|
| `model1_anomaly_detection.py` | Pipeline de base : Isolation Forest (chargement → prétraitement → entraînement → évaluation → sauvegarde) |
| `model1_advanced.py` | Module avancé : autoencodeur vs Isolation Forest + analyse par type d'attaque |
| `metrics.json` | Métriques de l'Isolation Forest (démonstration) |
| `comparison_metrics.json` | Comparaison des deux modèles + détection par type |
| `scores_distribution.png` | Distribution des scores d'anomalie (normal vs attaque) |
| `roc_curve.png` / `confusion_matrix.png` | Courbe ROC et matrice de confusion (Isolation Forest) |
| `model_comparison.png` | Comparaison chiffrée Isolation Forest vs autoencodeur |
| `detection_by_attack_type.png` | Taux de détection par type d'attaque |
| `autoencoder_error_distribution.png` | Erreur de reconstruction de l'autoencodeur (normal vs attaque) |

---

## 2. Installation

```bash
pip install scikit-learn pandas numpy matplotlib joblib
```

## 3. Exécution

**Mode démonstration** (données synthétiques réalistes, fonctionne immédiatement) :
```bash
python model1_anomaly_detection.py --synthetic --out ./outputs
```

**Sur les vraies données CICIDS2017** :
```bash
python model1_anomaly_detection.py --data-dir ./CICIDS2017 --out ./outputs
```

Le même code fonctionne dans les deux cas : il suffit de pointer `--data-dir` vers le dossier
contenant les CSV.

## 4. Obtenir le dataset CICIDS2017

Téléchargeable gratuitement (formulaire) auprès du **Canadian Institute for Cybersecurity (CIC),
University of New Brunswick** : rechercher « CICIDS2017 dataset UNB ». Placer les fichiers
`*.csv` (jour par jour, ex. *Monday-WorkingHours.pcap_ISCX.csv*…) dans un même dossier.

> Le pipeline corrige automatiquement deux pièges connus de CICIDS2017 :
> les espaces en tête de noms de colonnes, et les valeurs infinies de `Flow Bytes/s`.

Datasets complémentaires utiles : **CTU-13** (trafic botnet/C2), **UNSW-NB15**, **NSL-KDD**.

---

## 5. Logique du pipeline

1. **Chargement** — lecture et concaténation des CSV.
2. **Prétraitement** — nettoyage (inf → NaN, suppression des lignes incomplètes), suppression des
   colonnes identifiantes/fuites (IP, ports source, horodatage, label) et des colonnes constantes,
   conservation des seules features numériques.
3. **Découpage** — séparation train/test stratifiée. **L'entraînement ne porte que sur le trafic
   BENIN du train** : c'est ainsi qu'on apprend le « normal » de façon non supervisée.
4. **Normalisation** — `StandardScaler` ajusté sur le trafic normal.
5. **Entraînement** — `IsolationForest` (200 arbres).
6. **Seuil opérationnel** — fixé sur la distribution des scores du trafic normal (quantile lié au
   paramètre `contamination`) : aucune étiquette d'attaque n'est utilisée pour le régler.
7. **Évaluation** — calculée *avec* les étiquettes (CICIDS2017 est labellisé) : ROC-AUC, PR-AUC,
   taux de détection, taux de faux positifs, précision, F1, matrice de confusion.
8. **Sauvegarde** — `model1_isoforest.joblib` (modèle + scaler + seuil + mapping du score de risque).

## 6. Lecture des métriques

- **Taux de détection** (rappel sur les attaques) : proportion d'attaques correctement repérées.
- **Taux de faux positifs** : proportion de trafic normal signalé à tort — métrique critique pour
  un SOC (trop de faux positifs = fatigue d'alerte).
- **ROC-AUC** : qualité globale du classement, indépendante du seuil.

Le seuil est l'arbitrage central : le baisser augmente la détection mais aussi les faux positifs.
La courbe ROC permet de justifier ce compromis dans le rapport.

## 7. Intégration dans NEXUS SOC

Le fichier `.joblib` est consommé par le **service de scoring** de la plateforme : pour chaque
flux reçu via le pipeline Kafka, le modèle produit un **score de risque 0–100** (mapping inclus
dans le `.joblib`). Ce score alimente le moteur de corrélation (SIEM) et le score de sécurité
affiché dans le portail.

> **Démarche assumée** : le modèle est entraîné sur des *benchmarks publics* (CICIDS2017…), puis
> **ré-entraîné sur le trafic réel du client** après déploiement, pour apprendre son « normal »
> propre. Les chiffres de la démonstration synthétique sont **illustratifs** : seules les mesures
> sur CICIDS2017 (puis sur données de terrain) feront foi dans le rapport.

## 8. Module avancé : autoencodeur & analyse par type

```bash
python model1_advanced.py --synthetic --out ./outputs_advanced
python model1_advanced.py --data-dir ./CICIDS2017 --out ./outputs_advanced
```

Ce module ajoute une seconde approche et une analyse plus fine :

- **Autoencodeur** — un réseau de neurones apprend à *reconstruire* le trafic normal ;
  l'**erreur de reconstruction** (MSE par flux) sert de score d'anomalie. Implémenté ici avec
  `MLPRegressor` (encodeur → goulot d'étranglement → décodeur, architecture `16 → 6 → 16`),
  léger et exécutable ; cette architecture se transpose directement en PyTorch/Keras pour la
  version de production.
- **Comparaison chiffrée** des deux modèles sur les mêmes données.
- **Détection par type d'attaque** : on mesure le taux de détection séparément pour chaque
  famille (DDoS, PortScan, Bot/C2…).

**Enseignement clé (exécution de démonstration).** Les deux modèles sont excellents et très
proches globalement (ROC-AUC ≈ 0,99), mais l'analyse par type révèle qu'ils sont
**complémentaires** : l'Isolation Forest est le meilleur sur les attaques volumétriques (DDoS),
tandis que l'autoencodeur capte mieux les attaques discrètes (PortScan, Bot/C2). Cela justifie,
en perspective, une **combinaison des deux modèles (ensemble)** plutôt qu'un choix exclusif —
un argument solide à présenter en soutenance.

## 9. Pistes d'amélioration restantes (chapitre perspectives)

- Combiner Isolation Forest et autoencodeur en **ensemble** (vote ou moyenne des scores).
- Réimplémenter l'autoencodeur en **PyTorch/Keras** pour la version de production.
- Ajouter **CTU-13** pour renforcer la détection des communications C2.
- Cartographier chaque type détecté sur **MITRE ATT&CK**.
