# NEXUS SOC — Pipeline : normalisation + corrélation SIEM (Lot 2)

Le **maillon central** du SOC : il transforme la télémétrie brute hétérogène (issue de l'agent et,
à terme, d'autres sources) en données exploitables, et surtout il **reconstitue les chaînes
d'attaque multi-étapes** mappées sur MITRE ATT&CK — ce qui produit *une seule alerte enrichie*
plutôt que des dizaines d'événements isolés sans contexte.

---

## 1. Deux briques complémentaires

### a. Normalisation (`normalizer.py`)
Transforme la télémétrie brute de l'agent en un **schéma commun** inspiré d'ECS/OCSF
(`@timestamp`, `host`, `category`, `action`, `process.*`, `destination.*`, `file.*`…). À partir
des événements normalisés, elle calcule pour chaque hôte un **vecteur de features
comportementales** par fenêtre temporelle : nombre de processus, hashs inconnus, exécutions
depuis `/tmp`, connexions externes uniques, accès à des dossiers sensibles, activité hors heures…

> **Point d'honnêteté important.** Les features d'hôte produites ici sont **distinctes** des
> features de flux réseau (Modèle 1, issues d'un capteur réseau type CICFlowMeter) et des
> features d'audit applicatif (Modèle 2, issues de SIGIPES/SYDONIA). Chaque source possède son
> extracteur de features. Le pipeline accueille ces différents extracteurs ; il n'en force pas un seul.

### b. Corrélation SIEM (`correlation_engine.py`)
Applique des **règles** qui rattachent chaque événement à une **technique MITRE ATT&CK** :

| Tactique | Technique | Règle |
|---|---|---|
| Initial Access | T1204 | fichier déposé dans `Downloads/` avec extension exécutable |
| Execution | T1059 | interpréteur de commandes (`cmd.exe`, `powershell`…) |
| Execution | T1059 | exécution depuis un répertoire temporaire (`/tmp`) |
| Collection | T1005 | accès à un dossier sensible (`/etc/shadow`, `finance`, `contribuable`…) |
| Command and Control | T1071 | connexion vers un port C2 connu ou une IP de la threat intel |
| Impact | T1486 | modification de **> 20 fichiers en moins de 5 minutes** (rançongiciel) |

Pour chaque hôte, le moteur regroupe les détections dans une fenêtre de **30 minutes** et **lève
un incident corrélé** si l'une des conditions suivantes est remplie :
- au moins **3 tactiques distinctes** observées, ou
- couple **Exécution + Command and Control** détecté, ou
- tactique **Impact** détectée.

L'incident inclut : la chaîne reconstituée (ordonnée chronologiquement), la liste des techniques
MITRE, un score de risque 0–100, un drapeau « activité hors heures » et un **type** mappé au
SOAR (`Ransomware`, `Anomalie réseau / C2` ou `Compromission probable`).

## 2. Démonstration (résultat de l'exécution)

Sur un jeu généré (3 hôtes : bruit normal + une attaque implantée sur `POSTE-COMPTA-07`), le
moteur reconstitue **un seul incident** (zéro faux positif sur les hôtes normaux) :

```
Tactiques : Initial Access → Execution → Collection → Command and Control → Impact
MITRE     : T1005, T1059, T1071, T1204, T1486   (activité hors heures)
Risque    : 100/100  →  transmis au SOAR (type « Ransomware »)
```

La chronologie complète est dans `chain_reconstruction.png` et l'incident JSON dans
`correlated_incidents.json`. La couverture MITRE du moteur est résumée dans `mitre_coverage.png`.

## 3. Contenu

| Fichier | Rôle |
|---|---|
| `telemetry_gen.py` | Générateur de télémétrie brute (bruit normal + chaîne d'attaque implantée) |
| `normalizer.py` | Normalisation vers schéma commun + features comportementales d'hôte |
| `correlation_engine.py` | Détection MITRE + reconstitution des chaînes d'attaque |
| `out_lot2/normalized_sample.json` | Échantillon d'événements normalisés |
| `out_lot2/host_features.json` | Vecteur de features par hôte |
| `out_lot2/correlated_incidents.json` | Incident corrélé produit par le moteur |
| `out_lot2/chain_reconstruction.png` | Chronologie de la chaîne reconstituée |
| `out_lot2/mitre_coverage.png` | Couverture MITRE ATT&CK du moteur |

## 4. Exécution

```bash
python normalizer.py --out ./out_lot2
python correlation_engine.py --out ./out_lot2
```

## 5. Place dans NEXUS SOC

```
Agent (Lot 1) → /ingest → Kafka nexus.telemetry.raw
   → NORMALISATION  → nexus.telemetry (events + features) → scoring (Lot 3)
   → CORRÉLATION SIEM → nexus.alerts (incident corrélé) → SOAR (Lot 4)
```

L'**incident** émis par la corrélation se branche directement sur le SOAR existant : son champ
`type` (`Ransomware`, `Anomalie réseau / C2`…) sélectionne le playbook à exécuter, et la chaîne
reconstituée alimente l'explicabilité (le LLM Analyst pourra la résumer en français pour le DSI).

## 6. Limites et perspectives

- Les détecteurs implémentés ici sont une **base pédagogique solide** mais non exhaustive. En
  production, Wazuh apporte des centaines de règles supplémentaires que le moteur peut compléter,
  pas remplacer.
- La **threat intelligence** des IP/ports malveillants est ici une petite liste statique ; elle
  doit être branchée sur un flux dynamique (TI locale + listes publiques) avec mise à jour régulière.
- L'étape de **reconstitution** est volontairement simple (fenêtre + critères). Des approches
  plus avancées (graphes d'attaque, modèles séquentiels) figurent au chapitre perspectives du rapport.
- L'agrégation pour les features d'hôte se fait ici sur un seul lot ; en production, fenêtre
  glissante par hôte côté pipeline temps réel (Kafka Streams ou consumer dédié).
