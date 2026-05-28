# NEXUS SOC

**SOC-as-a-Service souverain pour le Cameroun**  
Plateforme de détection, corrélation et réponse aux incidents — multi-tenant, hébergement local, bilingue FR/EN.

**Auteur** : NGUETSA Junior Stéphane Céleste  
**Établissement** : KEYCE Informatique & IA, Yaoundé — Bachelor 3 RSI  
**Stage** : MINFI (Ministère des Finances) — Mai–Juillet 2026  
**Soutenance** : 24 août 2026

---

## Vue d'ensemble

NEXUS SOC assemble en une seule plateforme tous les composants d'un centre opérationnel de sécurité :

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     NEXUS SOC — Architecture complète                           │
│                                                                                 │
│  ┌─────────────┐   HTTPS/HMAC    ┌──────────────┐   Kafka     ┌─────────────┐ │
│  │  Agent Go   │ ─────────────▶  │  /ingest     │ ─────────▶  │  Pipeline   │ │
│  │  ~5 Mo      │                 │  (FastAPI)   │             │  Lot 2      │ │
│  │  Linux/Win  │                 └──────────────┘             │  Norm.+Corr │ │
│  └─────────────┘                                              └──────┬──────┘ │
│                                                                       │        │
│  ┌──────────────────────────────────────────────────────────┐        │ Alertes│
│  │  Modèles IA (Lot 3)                                       │◀───────┘        │
│  │  M1 : Isolation Forest + Autoencodeur (réseau)            │                 │
│  │  M2 : Isolation Forest UEBA (fraude interne)              │                 │
│  └───────────────────────────┬──────────────────────────────┘                 │
│                               │                                                │
│  ┌────────────────────────────▼───────────────────────────────────────────┐   │
│  │  SOAR — Lot 4 (playbooks + garde-fous + validation humaine + rollback)  │   │
│  │  9 connecteurs simulés · 4 playbooks · journal d'audit CSV              │   │
│  └────────────────────────────┬───────────────────────────────────────────┘   │
│                               │                                                │
│       ┌───────────────────────┼──────────────────────────────┐                │
│       ▼                       ▼                              ▼                │
│  ┌──────────┐          ┌────────────┐                ┌──────────────────┐    │
│  │  SMS /   │          │  Portail   │                │  Console         │    │
│  │ WhatsApp │          │  DSI (L5)  │                │  Fournisseur(L7) │    │
│  └──────────┘          └────────────┘                └──────────────────┘    │
│                                                                                │
│  ─── Stockage ─────────────────────────────────────────────────────────────  │
│  TimescaleDB (alertes · métriques · audit · RBAC · RLS multi-tenant)          │
│  Wazuh Indexer (OpenSearch, stockage chaud SIEM)                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Structure du dépôt

```
NEXUS_SOC/
├── README.md                          ← ce fichier
├── INVENTAIRE.md                      ← catalogue complet des livrables
│
├── 00_Documents/                      ← livrables académiques
│   ├── Cahier_des_charges_NEXUS_SOC.pdf
│   ├── Architecture_technique_NEXUS_SOC.pdf
│   ├── Template_Rapport_Soutenance_NEXUS_SOC.docx
│   └── Planning_Gantt_NEXUS_SOC.png
│
├── Lot0_Socle/                        ← pile Docker complète
│   ├── docker-compose.yml
│   ├── 01_schema_patched.sql          ← schéma SQL (RLS + RBAC + TimescaleDB)
│   └── nexus-soc-socle.zip            ← archive déployable (avec Dockerfile, configs)
│
├── Lot1_Agent_Go/                     ← agent endpoint (~5 Mo, pur stdlib Go)
│   ├── nexus-agent.zip                ← code source Go (main.go, collect.go, buffer.go, sender.go)
│   ├── scoring-service_app.py         ← service de scoring FastAPI (autonome dev)
│   └── telemetry_sample.json          ← échantillon de télémétrie réelle (59 événements)
│
├── Lot2_Pipeline_SIEM/                ← normalisation + corrélation MITRE
│   ├── nexus-pipeline.zip             ← normalizer.py, correlation_engine.py, telemetry_gen.py
│   └── correlated_incidents.json      ← résultat démo
│
├── Lot3_IA/
│   ├── Modele1_Anomalie_reseau/       ← Isolation Forest + autoencodeur réseau
│   │   ├── model1_anomaly_detection.py
│   │   ├── model1_advanced.py
│   │   └── nexus-modele1.zip          ← avec figures + metrics.json
│   └── Modele2_Fraude_interne/        ← UEBA fraude interne
│       ├── model2_fraud_detection.py
│       └── nexus-modele2.zip          ← avec figures + metrics.json
│
├── Lot4_SOAR/
│   ├── soar_engine.py                 ← moteur de réponse + playbooks
│   └── audit_log.csv                  ← journal d'audit de la démo
│
├── Lot5_Restitution/                  ← portail client + notifications
│   └── nexus-portail.zip              ← portal/index.html + notifier.py + SMS/WhatsApp
│
├── Lot6_Tests/                        ← tests, mesures, durcissement
│   └── nexus-tests.zip                ← attack_simulation.py, load_test.py, rls_isolation_test.py
│
└── Lot7_Console_Fournisseur/          ← console opérateur multi-tenant
    ├── console_fournisseur.html        ← interface standalone (ouvrir dans un navigateur)
    ├── admin_api.py                    ← endpoints FastAPI /admin/* et /analyst/*
    ├── 01_schema_analyst.sql           ← rôle nexus_analyst BYPASSRLS
    └── rls_analyst_test.py             ← test RLS étendu (8 assertions)
```

---

## Prérequis

### Système

```bash
# Docker + Docker Compose v2
docker --version          # ≥ 24.x
docker compose version    # ≥ 2.x

# Python 3.10+ (pour les scripts hors conteneur)
python3 --version

# Go 1.21+ (pour compiler l'agent)
go version

# Paramètre noyau requis par l'indexeur Wazuh / OpenSearch
sudo sysctl -w vm.max_map_count=262144
# Pour le rendre permanent :
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Python — dépendances (hors Docker)

```bash
pip install scikit-learn joblib numpy pandas matplotlib psycopg2-binary \
            fastapi uvicorn kafka-python pydantic
```

### RAM recommandée

**8 Go minimum** pour la pile complète (Wazuh indexer + dashboard sont gourmands).  
Sur une machine avec 4 Go, désactiver le dashboard Wazuh dans `docker-compose.yml` et utiliser uniquement l'API.

---

## Démarrage rapide — pile complète

```bash
# 1. Extraire l'archive du socle
cd Lot0_Socle
unzip nexus-soc-socle.zip
cd nexus-soc-socle

# 2. Configuration (copier et adapter les mots de passe)
cp .env.example .env

# 3. Générer les certificats Wazuh (une seule fois — crée le répertoire config/wazuh_indexer_ssl_certs/)
docker compose -f generate-certs.yml run --rm generator

# 4. Déposer les modèles entraînés dans models/
#    (les produire d'abord — voir section "Modèles IA" ci-dessous)
cp ../../Lot3_IA/Modele1_Anomalie_reseau/model1_isoforest.joblib     models/
cp ../../Lot3_IA/Modele2_Fraude_interne/model2_isoforest.joblib       models/

# 5. Démarrer la plateforme
docker compose up -d

# 6. Vérifier l'état des services (attendre ~60 s que tout soit prêt)
docker compose ps
docker compose logs -f scoring-service
```

### Vérification rapide

```bash
# Santé du service de scoring
curl http://localhost:8000/health
# → {"status":"ok","modele1":true,"modele2":true}

# Documentation interactive des endpoints
xdg-open http://localhost:8000/docs      # Linux
open http://localhost:8000/docs          # macOS

# Tableau de bord Wazuh SIEM
xdg-open https://localhost:5601
# identifiants par défaut : admin / SecretPassword (cf. .env)
```

### Ports exposés

| Service | Port(s) hôte | Usage |
|---|---|---|
| Kafka | `29092` | Outils de dev (console, producteurs de test) |
| TimescaleDB | `5432` | psql, DBeaver, pgAdmin |
| Wazuh Indexer | `9200` | API compatible Elasticsearch |
| Wazuh Manager | `1514`, `1515`, `55000` | Agents, enrôlement, API Wazuh |
| Wazuh Dashboard | `5601` | Interface SIEM (HTTPS) |
| Service de scoring | `8000` | API REST + passerelle /ingest |

---

## Agent Go — compilation et déploiement

### Compiler

```bash
cd Lot1_Agent_Go
unzip nexus-agent.zip
cd nexus-agent

# Linux (binaire ~5,0 Mo)
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent .

# Windows (binaire ~5,3 Mo)
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent.exe .
```

### Configurer et lancer

```bash
# Créer config.json sur le poste à surveiller
cat > config.json <<'EOF'
{
  "server_url": "http://localhost:8000/ingest",
  "enroll_token": "nexus_VOTRE_TOKEN_ICI",
  "hmac_key": "VOTRE_CLE_HMAC_ICI",
  "agent_id": "agent-poste-001",
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "interval_sec": 30,
  "watch_dirs": ["/home", "/tmp", "/var/log"],
  "queue_dir": "./queue",
  "queue_max_mb": 50
}
EOF

# Lancer
./nexusagent -config config.json

# Ou en arrière-plan
./nexusagent -config config.json &
```

### Tester l'ingestion sans agent (rejeu de l'échantillon réel)

```bash
# Envoyer les 59 événements de l'échantillon de télémétrie
curl -s -X POST http://localhost:8000/ingest \
  -H "Authorization: Bearer nexus_demo" \
  -H "Content-Type: application/json" \
  -d @telemetry_sample.json
# → {"recus":59,"publies":59}
```

---

## Pipeline SIEM — normalisation et corrélation

```bash
cd Lot2_Pipeline_SIEM
unzip nexus-pipeline.zip
cd nexus-pipeline

# Générer un jeu de télémétrie de démo (155 événements avec attaque implantée)
python telemetry_gen.py
# → telemetry_demo.json

# Normaliser + corréler
python normalizer.py telemetry_demo.json | python correlation_engine.py
# → correlated_incidents.json

# Résultat attendu :
# 1 incident corrélé : Ransomware sur POSTE-COMPTA-07
# Chaîne : T1204 → T1059 → T1005 → T1071 → T1486 (5 tactiques, risque 100/100)
# 0 faux positif sur les hôtes normaux

# Générer les figures du Lot 2
python make_lot2_figures.py
# → out_lot2/chain_reconstruction.png, mitre_coverage.png
```

---

## Modèles IA — entraînement et scoring

### Modèle 1 — Anomalie réseau (Isolation Forest + Autoencodeur)

```bash
cd Lot3_IA/Modele1_Anomalie_reseau
unzip nexus-modele1.zip -d Modele1 && cd Modele1

# Entraîner + évaluer (génère données synthétiques CICIDS-like + mesure ROC-AUC)
python model1_anomaly_detection.py
# → model1_isoforest.joblib  (à copier dans Lot0_Socle/nexus-soc-socle/models/)
# → out_modele1/metrics.json, roc_curve.png, confusion_matrix.png, scores_distribution.png

# Variante autoencodeur + comparaison (ROC-AUC 0.991 vs 0.987)
python model1_advanced.py
# → out_modele1/model_comparison.png, detection_by_attack_type.png, autoencoder_error_distribution.png
```

### Modèle 2 — Fraude interne UEBA

```bash
cd Lot3_IA/Modele2_Fraude_interne
unzip nexus-modele2.zip -d Modele2 && cd Modele2

# Entraîner + évaluer (3 scénarios : faux mandatements, fonctionnaires fantômes, exfiltration)
python model2_fraud_detection.py
# → model2_isoforest.joblib  (à copier dans Lot0_Socle/nexus-soc-socle/models/)
# → out_modele2/metrics.json, scores_distribution.png, detection_by_fraud_type.png
# → out_modele2/fraud_signatures.png (heatmap z-scores par type de fraude)
# → out_modele2/exemples_alertes.csv  (alertes avec explicabilité en σ)

# Résultats attendus :
# ROC-AUC = 0.969  |  FPR = 4 %
# Détection : Exfiltration 97 % / Fonctionnaire fantôme 76 % / Faux mandatement 54 %
```

### Scorer manuellement un événement (API)

```bash
# Modèle 1 — anomalie réseau
curl -X POST http://localhost:8000/score/network \
  -H "Content-Type: application/json" \
  -d '{"features": {
    "duration": 0, "protocol_type": 1, "src_bytes": 3200000,
    "dst_bytes": 512, "flag": 0, "land": 0, "wrong_fragment": 0,
    "urgent": 0, "hot": 5, "num_failed_logins": 0
  }}'
# → {"risque": 87, "anomalie": true, "score_brut": 0.2341}

# Modèle 2 — fraude interne UEBA
curl -X POST http://localhost:8000/score/user-day \
  -H "Content-Type: application/json" \
  -d '{"features": {
    "nb_exports": 28,
    "volume_donnees_exportees": 92000,
    "nb_acces_dossiers_sensibles": 40,
    "nb_transactions": 12,
    "montant_total_modifie": 0,
    "nb_modifs_montant": 0,
    "nb_connexions": 3,
    "nb_actions_hors_heures": 2,
    "nb_creations_compte": 0,
    "nb_actions_total": 45
  }}'
# → {"risque": 94, "anomalie": true,
#    "raisons": ["volume de données exportées anormalement élevé (13.1σ)",
#                "exports de données anormalement élevé (8.4σ)",
#                "accès à des dossiers sensibles anormalement élevé (6.2σ)"]}
```

---

## SOAR — moteur de réponse

```bash
cd Lot4_SOAR

# Démo complète : Lot SOAR (chargement d'un incident, exécution du playbook,
# validation humaine simulée, rollback)
python soar_engine.py
# → affiche l'exécution du playbook Fraude interne sur agent_DGI_0421
# → audit_log.csv mis à jour (qui, quoi, quand, statut)

# Lire le journal d'audit
cat audit_log.csv
```

**Seuil d'auto-exécution : 70/100.** En dessous, toutes les actions sont exécutées automatiquement. Au-dessus, les actions à fort impact (`freeze_account`, `isolate_host`) passent par la validation humaine — simulée dans la démo par `soar_engine.approve()`.

---

## Restitution — portail client, SMS, WhatsApp

```bash
cd Lot5_Restitution
unzip nexus-portail.zip
cd portail

# Ouvrir le portail DSI (vue client, bilingue FR/EN, mode sombre)
xdg-open portal/index.html     # Linux
open portal/index.html          # macOS
# → aucun serveur requis, HTML/CSS/JS autonomes

# Générer les explications LLM Analyst (mode template — déterministe, sans LLM)
python notifier.py --mode template --lang fr
python notifier.py --mode template --lang en
# → explication_fr.txt, explication_en.txt

# Générer un SMS court
python notifier.py --mode template --lang fr --format sms

# Générer le rapport WhatsApp hebdomadaire
python notifier.py --mode template --lang fr --format whatsapp

# Mode LLM (Mistral/Llama via API compatible OpenAI — requiert un serveur Ollama/vLLM)
OLLAMA_BASE_URL=http://localhost:11434/v1 python notifier.py --mode llm --lang fr
```

---

## Console fournisseur (opérateur NEXUS SOC)

La console fournisseur est **séparée du portail client**. Elle supervise tous les tenants simultanément.

```bash
# Ouvrir directement dans un navigateur (standalone — aucun serveur requis)
xdg-open Lot7_Console_Fournisseur/console_fournisseur.html
```

### Deux modules disponibles

| Module | Sections | Accès |
|---|---|---|
| **A — Administration** | Tableau de bord global · Tenants · Utilisateurs · Agents · Santé système · Facturation | Sidebar gauche — rôle `admin_plateforme` |
| **B — Analyste SOC** | File d'alertes cross-tenant · Approbation SOAR · Tableau de bord SOC | Sidebar gauche — rôle `analyste_soc` |

### Fonctionnalités interactives à tester

1. **Créer un tenant** → section Tenants → bouton « + Nouveau tenant »
2. **Générer un jeton d'enrôlement** → section Agents → bouton « + Générer un jeton » (token + HMAC, affichés une seule fois)
3. **Approuver une action SOAR** → section Approbation SOAR → bouton « Approuver » (retire la carte, décrémente le badge)
4. **Ouvrir une alerte** → section File d'alertes → cliquer une carte → modal détail avec explication LLM Analyst + kill chain
5. **Basculer FR/EN** → bouton en haut à droite (tous les éléments basculent instantanément)
6. **Suspendre un tenant** → section Tenants → bouton « Suspendre »

### Brancher le back FastAPI (optionnel — production)

```python
# Dans scoring-service_app.py ou app.py du socle :
from Lot7_Console_Fournisseur.admin_api import router as admin_router, analyst_router
app.include_router(admin_router)
app.include_router(analyst_router)

# Variables d'environnement supplémentaires :
# DB_DSN_ANALYST=postgresql://nexus_analyst:CHANGE_ME@postgres:5432/nexus
```

---

## Tests — exécution complète

### Vue d'ensemble

| Test | Fichier | Assertions | Prérequis |
|---|---|---|---|
| Simulation d'attaques MITRE | `Lot6_Tests/attack_simulation.py` | 7/7 techniques · 3/3 scénarios | Python, Lot2 extrait |
| Test de charge pipeline | `Lot6_Tests/load_test.py` | Débit + latence | Python, Lot2 extrait |
| Isolation RLS (Lot 6) | `Lot6_Tests/rls_isolation_test.py` | **5/5** assertions | PostgreSQL local, rôle `nexus_app` |
| Isolation RLS étendue (Lot 7) | `Lot7_Console_Fournisseur/rls_analyst_test.py` | **8/8** assertions | PostgreSQL local |

---

### Test 1 — Simulation d'attaques (Atomic Red Team style)

```bash
cd Lot6_Tests
unzip nexus-tests.zip
cd nexus-tests   # ou là où les fichiers sont extraits

# Extraire aussi le pipeline (dépendance)
cd ../../Lot2_Pipeline_SIEM && unzip nexus-pipeline.zip
cd ../Lot6_Tests/nexus-tests

python attack_simulation.py
```

**Résultats attendus :**

```
Techniques détectées : 7/7 (100 %)
  ✓ T1059 PowerShell / cmd.exe
  ✓ T1059 Exécution depuis /tmp
  ✓ T1105 Fichier malveillant dans Downloads
  ✓ T1003 Accès /etc/shadow
  ✓ T1071 Connexion C2 port 4444
  ✓ T1486 Modification massive de fichiers
  ✓ T1027 Obfuscation (détecté par effet de bord — règle répertoire temporaire)

Scénarios multi-étapes :
  ✓ Ransomware   MTTD = 120 s  (chaîne en 5 étapes)
  ✓ Exfiltration MTTD =  90 s  (chaîne en 3 étapes)
  ✓ Négatif      → 0 alerte (aucun faux positif)
```

> **Note honnête** : T1027 est capturée par un effet de bord (exécution depuis `C:\temp\`),
> pas par une règle dédiée. T1083 et T1136 ne sont pas couverts par le SIEM
> (T1136 relève du Modèle 2 UEBA).

---

### Test 2 — Charge du pipeline

```bash
python load_test.py
```

**Résultats attendus :**

```
Volume       Normalisation    Agrégation    Corrélation     Latence p99
1 000 ev     ~229 k ev/s      ~278 k ev/s   ~714 k ev/s     ≤ 12 μs
5 000 ev     ~220 k ev/s      ~265 k ev/s   ~380 k ev/s     ≤ 12 μs
25 000 ev    ~205 k ev/s      ~255 k ev/s   ~90 k ev/s      ≤ 12 μs
100 000 ev   ~189 k ev/s      ~248 k ev/s   ~22 k ev/s      ≤ 12 μs
```

> **Goulot identifié** : la corrélation dégrade à grand volume à cause d'un algorithme
> O(N²) dans `detect_mass_file_change`. Correctif identifié (compteur glissant O(N)),
> non encore appliqué — point de perspectives du rapport.

```bash
# Générer les figures de synthèse
python make_lot6_figures.py
# → out_lot6/mttd_by_scenario.png
# → out_lot6/load_test_perf.png
# → out_lot6/mitre_coverage_tested.png
# → out_lot6/rls_isolation_result.png
```

---

### Test 3 — Isolation RLS multi-tenant (Lot 6 — 5 assertions)

**Prérequis** : PostgreSQL 16 accessible localement (socket Unix `/var/run/postgresql`).  
Le script crée lui-même la base de test `nexus_rls_test` et le rôle `nexus_app`.

```bash
# Si PostgreSQL tourne dans Docker, exposer le socket ou utiliser le port 5432
# Option simple : utiliser psql depuis l'hôte avec le PostgreSQL du conteneur

python rls_isolation_test.py
```

**Résultat attendu :**

```
┌─ Assertions
│  ✓ #1 Tenant A : COUNT(alerts) = 3           attendu : 3   obtenu : 3
│  ✓ #2 Tenant B : COUNT(alerts) = 2           attendu : 2   obtenu : 2
│  ✓ #3 Fuite A→B bloquée                      attendu : 0   obtenu : 0
│  ✓ #4 Session sans tenant : COUNT = 0        attendu : 0   obtenu : 0
│  ✓ #5 Tenant A voit UNIQUEMENT tenant_id=A   attendu : [A] obtenu : [A]
└─ Résultat : 5 / 5 assertions vérifiées

✅ ISOLATION MULTI-TENANT VÉRIFIÉE
```

---

### Test 4 — Isolation RLS étendue (Lot 7 — 8 assertions)

Ce test ajoute la vérification du rôle `nexus_analyst` (BYPASSRLS).

**Prérequis** : même que le Test 3.

```bash
cd Lot7_Console_Fournisseur
python rls_analyst_test.py
```

**Résultat attendu :**

```
  ▸ Rôle nexus_app (soumis à la RLS — filtré par tenant)
  ✓ #1 nexus_app · Tenant A voit 3 alertes                → 3
  ✓ #2 nexus_app · Tenant B voit 2 alertes                → 2
  ✓ #3 nexus_app · Fuite A→B bloquée (→ 0)               → 0
  ✓ #4 nexus_app · Sans tenant : 0 alerte visible         → 0
  ✓ #5 nexus_app · Tenant A voit UNIQUEMENT tenant_id=A   → ['111...']

  ▸ Rôle nexus_analyst (BYPASSRLS — cross-tenant)
  ✓ #6 nexus_analyst · COUNT(alerts) global = 5           → 5
  ✓ #7 nexus_analyst · Filtre sur tenant A → 3 alertes    → 3
  ✓ #8 nexus_analyst · 2 tenant_id distincts visibles     → 2

  Résultat : 8/8 assertions vérifiées

  ✅ RLS ÉTENDU VÉRIFIÉ
     nexus_app     : isolation par tenant opérationnelle (5/5)
     nexus_analyst : vue cross-tenant opérationnelle    (3/3)
```

---

### Appliquer le schéma SQL Lot 7 (rôle nexus_analyst)

```bash
# Sur le PostgreSQL de développement (après Lot 0)
psql -U postgres -d nexus_soc -f Lot7_Console_Fournisseur/01_schema_analyst.sql

# Vérifier la création du rôle
psql -U postgres -c "\du nexus_analyst"
# → nexus_analyst | BYPASSRLS | {}
```

---

## Tableau de bord des résultats mesurés

| Promesse / dimension | Chiffre mesuré | Source |
|---|---|---|
| Taille binaire agent | **5,0 Mo Linux · 5,3 Mo Windows** | Lot 1, `go build` |
| Couverture MITRE (techniques attendues) | **7/7 — 100 %** | Lot 6, simulation |
| Scénarios d'attaque reconstitués | **3/3** | Lot 6 |
| MTTD attack-time — Ransomware | **120 s** | Lot 6 |
| MTTD attack-time — Exfiltration | **90 s** | Lot 6 |
| Débit normalisation (mono-cœur) | **~200 000 ev/s, p99 ≤ 12 μs** | Lot 6 |
| Isolation RLS multi-tenant | **5/5 (Lot 6) · 8/8 (Lot 7)** | Lots 6 & 7 |
| ROC-AUC Modèle 1 (Isolation Forest) | **0,987** | Lot 3 |
| ROC-AUC Modèle 1 (Autoencodeur) | **0,991** | Lot 3 |
| ROC-AUC Modèle 2 (UEBA fraude) | **0,969 · FPR 4 %** | Lot 3 |
| Détection fraude — Exfiltration | **97 %** | Lot 3 |
| Détection fraude — Fonctionnaire fantôme | **76 %** | Lot 3 |
| Détection fraude — Faux mandatement | **54 %** | Lot 3 |

> Tous ces chiffres sont issus de jeux **synthétiques réalistes**. La validation sur données
> réelles (CICIDS/CTU-13 pour M1, audits SIGIPES/SYDONIA pour M2) se fera pendant le stage MINFI.

---

## Limites connues (documentées honnêtement)

| Limite | Impact | Perspective |
|---|---|---|
| Données synthétiques, pas encore validées en production | Ordre de grandeur correct, pas une preuve terrain | Adaptation aux vraies données au MINFI |
| Goulot O(N²) dans `detect_mass_file_change` | Débit corrélateur divisé par ~30 à 100 k ev | Correctif O(N) identifié (compteur glissant) |
| T1027 couverte par effet de bord, pas par règle dédiée | Mauvaise étiquette technique | Règles YARA + signatures de contenu |
| T1083 et T1136 non couverts par le SIEM | Lacunes de couverture | T1136 → Modèle 2 UEBA ; T1083 → signal endpoint insuffisant |
| Faux mandatement : 54 % de détection | Fraude cachée dans la zone grise légitime | UEBA personnalisé + LSTM temporel |
| Connecteurs SOAR simulés | Isolation / gel non exécutés réellement | Interface prête, corps à brancher sur AD/pare-feu/EDR |
| LLM Analyst en mode `template` (pas de vrai LLM) | Déterministe mais pas adaptatif | Mistral local via Ollama en production |
| WhatsApp Business API hors fenêtre 24 h | Nécessite templates approuvés par Meta | Procédure de soumission à déclencher au déploiement |

---

## Démarrage minimal (sans Docker, pour la démo des scripts)

Si la pile Docker n'est pas disponible, les scripts Python fonctionnent en standalone :

```bash
# 1. Extraire Lot 2 (pipeline)
cd Lot2_Pipeline_SIEM && unzip nexus-pipeline.zip && cd nexus-pipeline

# 2. Démo pipeline complète (v2 — O(N) + nouvelles règles SIEM)
python telemetry_gen.py && python normalizer.py telemetry_demo.json | python correlation_engine_v2.py

# Benchmark du gain O(N²) → O(N)
python correlation_engine_v2.py --benchmark

# 3. Entraîner les modèles
cd ../../Lot3_IA/Modele1_Anomalie_reseau && python model1_anomaly_detection.py
cd ../Modele2_Fraude_interne && python model2_fraud_detection.py

# 4. SOAR
cd ../../Lot4_SOAR && python soar_engine.py

# 5. Interfaces web (ouvrir dans navigateur, aucun serveur requis)
xdg-open Lot5_Restitution/portail/portal/index.html   # portail client
xdg-open Lot7_Console_Fournisseur/console_fournisseur.html  # console opérateur

# 6. Tests (hors RLS qui requiert PostgreSQL)
cd Lot6_Tests && unzip nexus-tests.zip && cd nexus-tests
python attack_simulation.py
python load_test.py
```

---

## Modèle économique

| Cible | Offre | Tarif |
|---|---|---|
| Microfinances (COBAC) | Starter | 25 000 FCFA / mois |
| Assurances (CIMA) | Business | 75 000 FCFA / mois |
| Cabinets comptables (ONECCA) | Enterprise | 200 000 FCFA / mois |
| Administrations publiques | Contrat public | Annuel — hébergement souverain |

---

## Cadre légal et réglementaire

- **Loi n° 2010/012** sur la cybersécurité et la cybercriminalité au Cameroun
- **ANTIC** — Agence Nationale des Technologies de l'Information et de la Communication
- **COBAC** — réglementation microfinances (Afrique Centrale)
- **CIMA** — code des assurances (Afrique)
- **ONECCA** — cabinets comptables (Cameroun)
- **ISO/IEC 27001** — référence internationale SMSI (alignement des contrôles)

---

---

## Correctifs de sécurité et qualité (session du 28 mai 2026)

Les éléments suivants ont été corrigés ou ajoutés :

### Sécurité

| Correctif | Fichier | Détail |
|---|---|---|
| Validation HMAC sur `/ingest` | `Lot1_Agent_Go/scoring-service_app.py` | Chaque lot vérifie le Bearer token (hash en base) + signature X-Signature |
| Rate limiting sur toutes les APIs | `scoring-service_app.py` | 100 req/min global, 30 req/min sur `/ingest` ; HTTP 429 avec Retry-After |
| JWT middleware complet | `Lot1_Agent_Go/auth_middleware.py` | Access token (15 min) + refresh token (7 j), HMAC-SHA256 maison, endpoints `/auth/token`, `/auth/refresh`, `/auth/me` |
| Rotation clé HMAC agent | `Lot7_Console_Fournisseur/provisioning_api.py` | `POST /provision/rotate-hmac/{agent_id}` |
| Révocation d'urgence tenant | `provisioning_api.py` | `POST /provision/revoke-tenant/{tenant_id}` — coupe tous les agents immédiatement |
| Pseudonymisation des données perso | `Lot1_Agent_Go/pseudonymizer.py` | Remplace emails, IPs publiques, agent_ids par des pseudonymes HMAC stables |

### Performance

| Correctif | Fichier | Détail |
|---|---|---|
| Bug O(N²) → O(N) | `Lot2_Pipeline_SIEM/correlation_engine_v2.py` | `detect_mass_file_change` : deux pointeurs, chaque événement visité une seule fois |
| Fenêtre de corrélation configurable | `correlation_engine_v2.py` | Variable `CORR_WINDOW_MIN` (défaut 30 min) |

### Couverture de détection

| Règle | Technique MITRE | Fichier |
|---|---|---|
| Obfuscation dédiée (base64, double ext., iex) | **T1027** | `correlation_engine_v2.py` |
| Création de compte (useradd, net user /add) | **T1136** | `correlation_engine_v2.py` |
| Énumération de répertoires sensibles | **T1083** | `correlation_engine_v2.py` |
| Création de comptes en masse (volumétrique) | T1136 — variant | `correlation_engine_v2.py` |

### Opérationnel

| Ajout | Fichier | Détail |
|---|---|---|
| Sauvegarde complète | `Lot0_Socle/backup.sh` | PostgreSQL + Wazuh snapshot + modèles + config, rotation sur 14 jours |
| Restauration | `Lot0_Socle/restore.sh` | Restaure les 3 composants |
| Politique de rétention SQL | `Lot0_Socle/01_schema_retention.sql` | Compression TimescaleDB J7+, archivage alertes 1 an+, purge tokens expirés |
| Healthchecks Docker | `Lot0_Socle/docker-compose.yml` | Wazuh Indexer + Manager + Dashboard + scoring-service avec `start_period` adapté |
| `/health/detailed` | `scoring-service_app.py` | Vérifie Kafka, TimescaleDB, Wazuh Indexer en temps réel |
| Monitoring dérive modèles | `Lot3_IA/model_monitor.py` | PSI, σ-drift, taux de FP, taux d'alertes ; endpoint `/monitor/drift` ; mode CLI |

### Utilisation des nouveaux outils

```bash
# Sauvegarde manuelle
sudo bash Lot0_Socle/backup.sh --dest /opt/nexus-backups --compress

# Restauration depuis un backup
sudo bash Lot0_Socle/restore.sh --backup /opt/nexus-backups/nexus_20260528_090000

# Test de dérive des modèles (mode démo)
python3 Lot3_IA/model_monitor.py --demo

# Test pseudonymisation
python3 Lot1_Agent_Go/pseudonymizer.py

# Benchmark O(N²) → O(N) sur detect_mass_file_change
python3 Lot2_Pipeline_SIEM/correlation_engine_v2.py --benchmark

# Healthcheck détaillé
curl http://localhost:8000/health/detailed | python3 -m json.tool
```

---

## Ce qui reste à faire — hors portée du code

Ces problèmes nécessitent une action humaine, une infrastructure réelle ou une tierce partie :

| # | Problème | Raison de l'impossibilité code-seul | Qui/Quand |
|---|---|---|---|
| 1 | **Valider les modèles sur données réelles** (CICIDS, SIGIPES) | Accès aux bases de données réelles du MINFI | Stage MINFI (mai–juil 2026) |
| 2 | **Brancher les connecteurs SOAR** (AD, pare-feu, EDR) | Accès aux systèmes d'infrastructure réseau réels | Stage MINFI |
| 3 | **Conformité ANTIC** | Audit externe par l'ANTIC — non substituable par du code | Démarche administrative |
| 4 | **Templates WhatsApp Business** | Approbation par Meta (délai 1–2 semaines, refus possible) | Soumettre avant déploiement |
| 5 | **Architecture HA** (multi-nœuds Kafka, PostgreSQL réplication) | Requiert plusieurs serveurs physiques ou VM | Infrastructure production |
| 6 | **mTLS / certificats machine** | Requiert une PKI interne (CFSSL, Vault, Smallstep) | Architecture production |
| 7 | **Chiffrement au repos** (PostgreSQL, Wazuh) | Configuration infrastructure (LUKS, pgcrypto sur tous les volumes) | Déploiement production |
| 8 | **Retraining automatique des modèles** | Nécessite des données étiquetées réelles et un pipeline MLOps (DVC, MLflow) | Post-stage |
| 9 | **LSTM pour la détection temporelle** | Nécessite des séquences d'audit réelles longues (SIGIPES 6+ mois) | Post-stage |
| 10 | **UEBA personnalisé par agent** | Nécessite 90+ jours de données comportementales par personne | Post-stage |
| 11 | **Support macOS pour l'agent** | Code Go à écrire + tests sur machine macOS | Non prioritaire |
| 12 | **Tests d'intrusion / pentest** | Nécessite un prestataire habilité ou équipe rouge | Avant mise en production |
| 13 | **Assurance / responsabilité contractuelle** | Domaine légal — conditions générales à rédiger avec un juriste | Avant premier contrat client |
| 14 | **Formation des analystes SOC** | Compétence humaine — pas substituable par du code | Onboarding client |

---

*NEXUS SOC — Plateforme SOC-as-a-Service souveraine — KEYCE Informatique & IA, Yaoundé, 2026*
