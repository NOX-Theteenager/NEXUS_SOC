# NEXUS SOC — Modèle 2 : Détection de fraude interne (UEBA)

Détection de **comportements frauduleux** dans un système d'information administratif
(type SIGIPES / SYDONIA) par **analyse d'anomalies comportementales sur logs structurés**.

> ⚠ **Ce n'est pas du NLP.** On n'analyse pas du texte : on agrège l'activité de chaque agent
> par jour en un profil chiffré, on apprend le comportement normal, et on signale les journées
> anormales. C'est l'approche **UEBA** (User and Entity Behavior Analytics).

---

## 1. Scénarios de fraude détectés

| Fraude | Mécanisme | Signature comportementale |
|---|---|---|
| **Faux mandatement** | Modification de montants de paiement élevés | montant modifié + nb. de modifications + activité hors heures |
| **Fonctionnaire fantôme** | Création de comptes d'agents fictifs pour percevoir des salaires | créations de comptes massives |
| **Exfiltration** | Export massif de données contribuables / fiscales | volume exporté + nb. d'exports + accès à des dossiers sensibles |

> Le problème des **fonctionnaires fantômes** est un enjeu réel et documenté des finances
> publiques camerounaises (d'où les opérations de comptage physique/biométrique des agents).

---

## 2. Contenu

| Fichier | Rôle |
|---|---|
| `model2_fraud_detection.py` | Pipeline complet : génération/chargement → prétraitement → Isolation Forest → évaluation → **explicabilité** |
| `metrics.json` | Métriques + détection par type de fraude |
| `exemples_alertes.csv` | Exemples d'alertes **expliquées** (type, score de risque, raisons) |
| `scores_distribution.png` | Distribution des scores d'anomalie (normal vs fraude) |
| `detection_by_fraud_type.png` | Taux de détection par type de fraude |
| `fraud_signatures.png` | Signature comportementale de chaque fraude (écart au profil normal) |

## 3. Exécution

```bash
pip install scikit-learn pandas numpy matplotlib joblib

# Démonstration (profils agent-jour synthétiques réalistes) :
python model2_fraud_detection.py --synthetic --out ./outputs_m2

# Sur un fichier réel de features agrégées par agent-jour :
python model2_fraud_detection.py --data-file agent_jour.csv --out ./outputs_m2
```

## 4. Le profil « agent-jour »

Pour chaque agent et chaque jour, on calcule 10 features comportementales :
`nb_connexions`, `nb_actions_hors_heures`, `nb_transactions`, `montant_total_modifie`,
`nb_modifs_montant`, `nb_creations_compte`, `nb_exports`, `volume_donnees_exportees`,
`nb_acces_dossiers_sensibles`, `nb_actions_total`.

C'est ce tableau (une ligne = un agent un jour) qui alimente le modèle.

## 5. Données réelles : où les trouver, comment les construire

Aucune donnée de fraude réelle et **étiquetée** n'est publiquement disponible — c'est une
**contrainte de disponibilité**, pas un choix de périmètre. Deux voies :

- **CERT Insider Threat (CMU/SEI)** — *la* référence mondiale de la menace interne (synthétique
  mais standard). On l'**agrège par utilisateur-jour** : `logon.csv` → connexions et activité hors
  heures ; `device.csv` / `file.csv` → exports et volumes ; `http.csv` → accès ; etc. Le tableau
  obtenu a le même schéma que ci-dessus.
- **Journaux d'audit réels (SIGIPES / SYDONIA)** — mêmes agrégations à partir des logs d'audit
  applicatifs, après accord de l'administration. À défaut, on assume des **données synthétiques**.

> **Démarche assumée** : modèle entraîné sur référence + synthétique, puis **ré-entraîné sur les
> journaux réels** après déploiement. Les chiffres de la démonstration sont **illustratifs**.

## 6. Explicabilité (point clé pour ce cas d'usage)

Pour chaque alerte, le modèle indique les features qui s'écartent le plus du profil normal
(en σ), traduites en **raisons lisibles** — par exemple :

> *[risque 87/100] Exfiltration — volume de données exportées anormalement élevé (13 σ) ;
> exports de données (20 σ) ; accès à des dossiers sensibles (12 σ).*

C'est exactement ce dont un DSI a besoin pour agir, et c'est la matière que le **LLM Analyst**
de NEXUS transforme en explication en français. Voir `exemples_alertes.csv`.

## 7. Lecture des résultats (démonstration)

La détection varie fortement selon le type de fraude, et **c'est un enseignement majeur** :

- **Exfiltration** : très bien détectée (signal de volume « bruyant »).
- **Fonctionnaire fantôme** : bien détectée (les créations de comptes massives sont distinctives).
- **Faux mandatement** : la plus difficile — elle se cache dans la « zone grise » des grosses
  opérations légitimes (pics de fin de mois).

**Conséquence pour la conception** : une détection d'anomalies *globale* atteint vite ses limites
sur la fraude financière. La parade, déjà prévue dans l'architecture, est le **profilage par
agent / par rôle** (vrai UEBA personnalisé) et le modèle **LSTM** pour les motifs temporels —
complétés par une **validation humaine** (human-in-the-loop) sur les cas ambigus.

## 8. Intégration dans NEXUS SOC

Le `.joblib` (modèle + scaler + profil normal + mapping de risque 0–100) est consommé par le
service UEBA : chaque profil agent-jour reçoit un **score de risque 0–100** et, s'il dépasse le
seuil, génère une alerte **accompagnée de ses raisons**, transmise au moteur de corrélation et au
portail.

## 9. Pistes d'amélioration (chapitre perspectives)

- **UEBA personnalisé** : une ligne de base par agent / par rôle plutôt qu'un modèle global.
- Ajouter une dimension **temporelle** (LSTM) pour les fraudes qui se construisent sur plusieurs jours.
- Cartographier les fraudes sur **MITRE ATT&CK** (tactique *Exfiltration*, etc.).
- Boucler avec le **SOAR** (playbook : gel du compte, notification, journalisation pour enquête).
