# NEXUS SOC

**SOC-as-a-Service souverain pour le Cameroun**  
Plateforme de détection, corrélation et réponse aux incidents — multi-tenant, hébergement local, bilingue FR/EN.

**Auteur** : NGUETSA Junior Stéphane Céleste  
**École** : KEYCE Informatique & IA, Yaoundé — Bachelor 3 RSI  
**Stage** : MINFI (Ministère des Finances) — Mai–Juillet 2026  
**Soutenance** : 24 août 2026

---

## Navigation rapide

### Frontend connecté (Lot 9 — recommandé)

> Démarrer d'abord le serveur : `uvicorn run:app --host 0.0.0.0 --port 8000 --reload`

| Interface | Rôle | URL |
|---|---|---|
| **Login** | Authentification (tous rôles) | `http://localhost:8000/app/login.html` |
| **Console Opérateur** | Admin + Analyste SOC — données réelles | `http://localhost:8000/app/console.html` |
| **Portail DSI** | Vue client — alertes + agents + trial | `http://localhost:8000/app/portail.html` |
| **Landing page PLG** | Vitrine + inscription SaaS | `http://localhost:8000/app/../Lot8_PLG/landing_page.html` |
| **API REST (Swagger)** | Documentation interactive | `http://localhost:8000/docs` |
| **Wazuh Dashboard** | Interface SIEM | `https://localhost:5601` |

### Interfaces standalone (Lot 5 / Lot 7 — maquettes statiques)

| Interface | Commande |
|---|---|
| Portail DSI (maquette) | `xdg-open Lot5_Restitution/portail/portal/index.html` |
| Console (maquette) | `xdg-open Lot7_Console_Fournisseur/console_fournisseur.html` |

### Déploiement Souverain

```bash
cd Lot8_PLG/terraform-souverain && terraform apply
```

---

## Architecture globale

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     NEXUS SOC — Architecture complète (Lots 0–9)                │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │  Lot 8 — PLG (Product-Led Growth)                                         │  │
│  │  Landing page duale · API inscription · Quotas trial · Terraform souverain │  │
│  └───────────────────────┬───────────────────────────────────────────────────┘  │
│                           │ auto-provisioning                                    │
│  ┌────────────┐  HTTPS    ▼    ┌──────────────┐  Kafka  ┌──────────────────┐   │
│  │ Agent Go   │ ────────────▶  │ /ingest      │ ──────▶ │ Pipeline SIEM    │   │
│  │ ~5 Mo      │  HMAC-SHA256   │ (FastAPI L1) │         │ Normalisation    │   │
│  │ Linux/Win  │  Watermark     │ Quota trial  │         │ Corrélation MITRE│   │
│  └────────────┘                └──────────────┘         └────────┬─────────┘   │
│                                                                   │ Alertes     │
│  ┌────────────────────────────────────────────────────┐          │             │
│  │  Modèles IA (Lot 3)                                 │◀─────────┘             │
│  │  M1 : Isolation Forest + Autoencodeur (réseau)      │                        │
│  │  M2 : Isolation Forest UEBA (fraude interne)        │                        │
│  └─────────────────────────┬──────────────────────────┘                        │
│                             │                                                    │
│  ┌──────────────────────────▼────────────────────────────────────────────────┐  │
│  │  SOAR — Lot 4 (playbooks + garde-fous + validation humaine + rollback)    │  │
│  └──────────────────────────┬────────────────────────────────────────────────┘  │
│                              │                                                   │
│       ┌──────────────────────┼──────────────────────┐                           │
│       ▼                      ▼                       ▼                           │
│  ┌──────────┐        ┌─────────────┐        ┌──────────────────┐               │
│  │ SMS /    │        │ Portail DSI │        │ Console          │               │
│  │ WhatsApp │        │ (Lot 5)     │        │ Fournisseur(Lot7)│               │
│  └──────────┘        └─────────────┘        └──────────────────┘               │
│                                                                                  │
│  ── Stockage ──────────────────────────────────────────────────────────────── │
│  TimescaleDB · Wazuh Indexer (OpenSearch) · RLS multi-tenant · RBAC            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Structure du dépôt

```
NEXUS_SOC/
├── README.md                            ← ce fichier
├── INVENTAIRE.md
│
├── 00_Documents/                        ← livrables académiques
│
├── Lot0_Socle/                          ← pile Docker complète
│   ├── docker-compose.yml               ← 6 services avec healthchecks
│   ├── 01_schema_patched.sql            ← schéma SQL (RLS + RBAC + TimescaleDB)
│   ├── 01_schema_retention.sql          ← politiques de rétention + compression
│   ├── backup.sh / restore.sh           ← sauvegarde/restauration automatisées
│   └── nexus-soc-socle.zip
│
├── Lot1_Agent_Go/                       ← agent endpoint (~5 Mo, pur stdlib Go)
│   ├── nexus-agent.zip                  ← main.go, collect.go, buffer.go, sender.go
│   ├── scoring-service_app.py           ← API FastAPI v2 (scoring + /ingest + PLG quotas)
│   ├── auth_middleware.py               ← JWT HMAC-SHA256 (access 15 min + refresh 7 j)
│   └── pseudonymizer.py                 ← pseudonymisation HMAC stable des PII
│
├── Lot2_Pipeline_SIEM/                  ← normalisation + corrélation MITRE ATT&CK
│   ├── nexus-pipeline.zip               ← normalizer.py + correlation_engine.py + gen
│   └── correlation_engine_v2.py         ← correctif O(N²)→O(N) + T1027/T1136/T1083
│
├── Lot3_IA/
│   ├── Modele1_Anomalie_reseau/         ← IF + autoencodeur (ROC-AUC 0.991)
│   ├── Modele2_Fraude_interne/          ← UEBA (ROC-AUC 0.969, FPR 4 %)
│   └── model_monitor.py                 ← détection de dérive PSI + σ-drift
│
├── Lot4_SOAR/
│   ├── soar_engine.py                   ← 9 connecteurs · 4 playbooks · rollback
│   └── audit_log.csv
│
├── Lot5_Restitution/
│   └── nexus-portail.zip                ← portal/index.html + notifier.py (LLM Analyst)
│
├── Lot6_Tests/
│   └── nexus-tests.zip                  ← attack_simulation · load_test · rls_test
│
├── Lot7_Console_Fournisseur/
│   ├── console_fournisseur.html         ← interface opérateur standalone (2912 lignes)
│   ├── admin_api.py                     ← FastAPI /admin/* + /analyst/*
│   ├── provisioning_api.py              ← tokens · scripts · QR · bulk · one-liner
│   └── rls_analyst_test.py              ← 8/8 assertions RLS nexus_app + nexus_analyst
│
├── Lot8_PLG/                            ← Product-Led Growth + Déploiement Souverain
│   ├── landing_page.html                ← vitrine duale (SaaS trial + Souverain)
│   ├── plg_api.py                       ← API inscription · filtre email · quotas · suspension
│   ├── 01_schema_plg.sql                ← tables trial_quotas, subscriptions, plg_registrations
│   ├── build_agent.py                   ← compilation garble + watermark HMAC par tenant
│   ├── nexus-agent-plg/                 ← agent "coquille vide" (config dynamique + watermark)
│   │   ├── watermark.go
│   │   ├── config_fetcher.go
│   │   └── main_plg.go
│   └── terraform-souverain/             ← déploiement souverain sur serveur institution
│       ├── providers.tf / variables.tf / main.tf / outputs.tf
│       ├── terraform.tfvars.example
│       └── templates/                   ← env.tpl · docker-compose.tpl · Dockerfile.scoring.tpl
│
├── Lot9_Frontend/                       ← ★ Frontend connecté (PWA, dynamique, responsive)
│   ├── login.html                       ← authentification (JWT, redirect par rôle)
│   ├── console.html                     ← console opérateur connectée (admin + analyste SOC)
│   ├── portail.html                     ← portail DSI connecté (bilingue FR/EN, trial banner)
│   ├── offline.html                     ← page hors ligne (PWA)
│   ├── manifest.json                    ← manifest PWA (shortcuts, icônes, standalone)
│   ├── sw.js                            ← service worker (Cache First + Network First + push)
│   ├── js/api.js                        ← client API universel (JWT auto-refresh, 40+ endpoints)
│   └── icons/                           ← icônes PWA (SVG)
│
└── run.py                               ← ★ Point d'entrée principal (tous routers + frontend statique)
                                            uvicorn run:app --host 0.0.0.0 --port 8000
```

---

## Prérequis

### Obligatoires pour la pile complète

```bash
# Docker Engine + Docker Compose v2
docker --version          # ≥ 24.x
docker compose version    # ≥ 2.x

# Paramètre noyau requis par Wazuh Indexer (OpenSearch)
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Python (scripts standalone + frontend connecté)

```bash
# Dépendances de base (scoring, modèles, pipeline)
pip install scikit-learn joblib numpy pandas matplotlib fastapi uvicorn \
            kafka-python psycopg2-binary asyncpg pydantic httpx

# Dépendances supplémentaires pour run.py (frontend + static files)
pip install "fastapi[standard]" aiofiles python-multipart
```

### Go (compilation de l'agent)

```bash
go version   # ≥ 1.21
# Optionnel : garble pour l'obfuscation (Lot 8 PLG uniquement)
go install mvdan.cc/garble@latest
```

### Terraform (déploiement souverain uniquement)

```bash
# Ubuntu/Debian
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
terraform version  # ≥ 1.6
```

### RAM recommandée

| Mode | RAM minimale | Services actifs |
|---|---|---|
| Pile complète | **8 Go** | Kafka + TimescaleDB + Wazuh (indexer + manager + dashboard) + scoring |
| Sans Wazuh Dashboard | **5 Go** | Commenter le service `wazuh.dashboard` dans docker-compose.yml |
| Standalone (scripts) | **1 Go** | Aucun conteneur requis |

---

## 1 — Démarrage rapide : frontend connecté (recommandé)

Le mode le plus simple pour utiliser toutes les interfaces dynamiques **sans Docker**.

```bash
# 1. Installer les dépendances Python
pip install "fastapi[standard]" uvicorn aiofiles scikit-learn joblib numpy \
            kafka-python psycopg2-binary asyncpg pydantic httpx python-multipart

# 2. Entraîner les modèles IA (si pas encore fait)
python3 Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
python3 Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py

# 3. Lancer le serveur (tous routers + frontend sur /app/)
uvicorn run:app --host 0.0.0.0 --port 8000 --reload

# 4. Ouvrir le navigateur
http://localhost:8000/app/login.html
```

**Comptes de démonstration :**

| E-mail | Mot de passe | Rôle | Redirect |
|---|---|---|---|
| `admin@nexussoc.cm` | `admin` | admin_plateforme | Console (tous modules) |
| `soc@nexussoc.cm` | `admin` | analyste_soc | Console (alertes + SOAR) |
| `dsi@minfi.cm` | `admin` | dsi_client | Portail DSI |

> **Note :** Pour que les données soient réelles, PostgreSQL + Kafka doivent tourner (voir section 2 ci-dessous). Sans eux, l'API répond en mode dégradé avec des erreurs claires.

**PWA — Installer sur mobile ou desktop :**
- Chrome/Edge : icône "Installer" dans la barre d'adresse
- Android : "Ajouter à l'écran d'accueil" → lance en standalone sans barre navigateur

---

## 2 — Démarrage complet : pile Docker (données réelles)

```bash
# Étape 1 — Extraire le socle
cd Lot0_Socle
unzip nexus-soc-socle.zip
cd nexus-soc-socle

# Étape 2 — Configurer les variables d'environnement
cp .env.example .env
# Editer .env : changer les mots de passe POSTGRES_PASSWORD, JWT_SECRET, PSEUDO_SECRET

# Étape 3 — Générer les certificats Wazuh (une seule fois)
docker compose -f generate-certs.yml run --rm generator

# Étape 4 — Entraîner et déposer les modèles IA
python3 ../Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
python3 ../Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py
cp ../Lot3_IA/Modele1_Anomalie_reseau/model1_isoforest.joblib models/
cp ../Lot3_IA/Modele2_Fraude_interne/model2_isoforest.joblib  models/

# Étape 5 — Démarrer la pile (attendre ~90 s que tous les services soient healthy)
docker compose up -d

# Étape 6 — Vérifier
docker compose ps
curl http://localhost:8000/health
# → {"status":"ok","modele1":true,"modele2":true}
```

### Appliquer tous les schémas SQL

```bash
# Les schémas sont exécutés automatiquement si placés dans config/postgres/init/
# Sinon, les appliquer manuellement :
DB="postgresql://nexus:change_me@localhost:5432/nexus_soc"
psql $DB -f ../Lot0_Socle/01_schema_patched.sql
psql $DB -f ../Lot7_Console_Fournisseur/01_schema_analyst.sql
psql $DB -f ../Lot7_Console_Fournisseur/01_schema_provisioning.sql
psql $DB -f ../Lot0_Socle/01_schema_retention.sql
psql $DB -f ../Lot8_PLG/01_schema_plg.sql
```

### Puis lancer le frontend connecté par-dessus la pile Docker

```bash
# Dans un second terminal, depuis la racine du projet :
uvicorn run:app --host 0.0.0.0 --port 8000 --reload
# → http://localhost:8000/app/login.html (frontend connecté à la pile Docker)
```

### Ports exposés

| Service | Port | URL |
|---|---|---|
| **API NEXUS SOC** | `8000` | `http://localhost:8000/docs` |
| Wazuh Dashboard | `5601` | `https://localhost:5601` |
| Wazuh Indexer | `9200` | `https://localhost:9200` |
| Wazuh Manager | `1514` `1515` `55000` | Agents, enrôlement, API |
| Kafka (dev) | `29092` | `localhost:29092` |
| TimescaleDB | `5432` | `localhost:5432` |

---

## 3 — Guide des interfaces

> **Lot 9 (connecté)** → démarrer `uvicorn run:app --port 8000 --reload` puis ouvrir les URLs ci-dessous.
> **Lot 5/7 (statiques)** → `xdg-open` sur les fichiers HTML, aucun serveur requis mais données hardcodées.

---

### Interface 0 — Login (Lot 9 — nouveau)

Point d'entrée unique pour tous les utilisateurs. Détecte le rôle et redirige automatiquement.

```
http://localhost:8000/app/login.html
```

- Saisir e-mail + mot de passe → `POST /auth/token`
- Redirect automatique selon le rôle : `admin_plateforme` / `analyste_soc` → **Console**, `dsi_client` / `lecteur` → **Portail**
- JWT stocké en `localStorage` (access 15 min + refresh 7 j, auto-renouvelé)

---

### Interface 1 — Landing Page PLG (Lot 8)

Vitrine publique avec deux flux : essai SaaS automatisé et contact déploiement souverain.

```bash
# Version connectée (via run.py)
http://localhost:8000/app/../Lot8_PLG/landing_page.html

# Version standalone (aucun serveur requis pour la navigation visuelle)
xdg-open Lot8_PLG/landing_page.html
```

**Ce que vous verrez :**
- Bouton **"Essai gratuit 30 jours"** → ouvre un modal multi-étapes (4 étapes : email → organisation → vérification → pré-auth bancaire)
- Bouton **"Déploiement Souverain"** → formulaire de contact pour administrations publiques
- Section tarification (25 000 / 75 000 / 200 000 FCFA/mois)
- Filtrage live des emails : les adresses jetables et les domaines `.gov.cm` / `.cm` sont bloqués en temps réel

> La landing page est entièrement standalone (HTML/CSS/JS, aucun serveur requis pour la navigation).  
> Les appels API (`/plg/check-email`, `/plg/register`, `/plg/preauth`) nécessitent la pile Docker pour fonctionner.

---

### Interface 2 — Portail DSI Client

**Lot 9 (connecté, recommandé) :**

```
http://localhost:8000/app/portail.html
```

- Score de sécurité calculé dynamiquement depuis les alertes réelles du tenant
- **Trial banner** : si le tenant est en période d'essai, affiche les jours restants + barre de quota (agents / événements)
- Alertes réelles du tenant (polling 60 s) avec kill-chain MITRE cliquable
- Modal détail bilingue FR/EN (explication LLM Analyst depuis la base de données)
- Agents du tenant avec statut temps réel
- Bouton "Passer à un plan" renvoyant vers la landing page PLG
- Bascule FR/EN instantanée

**Lot 5 (maquette statique, standalone) :**

```bash
xdg-open Lot5_Restitution/portail/portal/index.html
```

**Générer les notifications (LLM Analyst) :**

```bash
cd Lot5_Restitution && unzip nexus-portail.zip && cd portail

# Explication déterministe (mode template — défaut, sans LLM)
python notifier.py --mode template --lang fr
python notifier.py --mode template --lang en

# SMS court (160 caractères max)
python notifier.py --mode template --lang fr --format sms

# Rapport WhatsApp hebdomadaire
python notifier.py --mode template --lang fr --format whatsapp

# Mode LLM (requiert un serveur Ollama sur le port 11434)
OLLAMA_BASE_URL=http://localhost:11434/v1 python notifier.py --mode llm --lang fr
```

---

### Interface 3 — Console Opérateur

**Lot 9 (connectée, recommandée) :**

```
http://localhost:8000/app/console.html
```

Toutes les données sont chargées depuis l'API. Polling 30 s sur les alertes et les actions SOAR en attente.

| Section | Données source | Actions connectées |
|---|---|---|
| Tableau de bord | `/admin/tenants`, `/admin/agents`, `/analyst/alerts`, `/health` | Vue globale temps réel |
| Tenants | `GET /admin/tenants` | Créer · Suspendre · Réactiver |
| Agents | `GET /admin/agents` | Générer token → one-liner · Rotation HMAC · Révoquer |
| Alertes | `GET /analyst/alerts` (polling 30s) | Voir détail + kill-chain · Marquer FP |
| Approbation SOAR | `GET /analyst/pending` | Approuver · Refuser · Rollback |
| Santé système | `GET /health/detailed` | Vérification à la demande |
| Facturation PLG | `GET /admin/billing`, `POST /plg/run-expiry-check` | Suspendre · Vérifier essais expirés |

**Badge alertes** dans la sidebar : se met à jour automatiquement toutes les 30 secondes.

**Lot 7 (maquette statique, standalone) :**

```bash
xdg-open Lot7_Console_Fournisseur/console_fournisseur.html
```

**Module B — Analyste SOC (`analyste_soc`)**

Accessible depuis la sidebar gauche → icône bouclier.

| Section | Ce que vous pouvez faire |
|---|---|
| File d'alertes | 5 alertes de démo · cartes colorées par risque · kill-chain MITRE inline · filtre multi-critères |
| Approbation SOAR | Actions en attente (`isolate_host`, `freeze_account`, `block_ip`) · Approuver / Refuser / Rollback |
| Tableau de bord SOC | MTTD par tenant · MTTR · barres CSS · graphique d'activité 7 jours |

**Actions clés à tester :**
1. Section **File d'alertes** → cliquer une alerte rouge → modal détail (kill-chain + explication LLM)
2. Section **Approbation SOAR** → "Approuver" une action HIGH → retire la carte et décrémente le badge
3. Bouton FR/EN en haut à droite → bascule instantanée

**Brancher le backend FastAPI (optionnel) :**

```python
# Dans scoring-service_app.py, ajouter après la création de `app` :
from admin_api        import router as admin_router
from provisioning_api import router as prov_router

app.include_router(admin_router)
app.include_router(prov_router)
```

---

### Interface 4 — API REST / Swagger UI (Lot 1)

Documentation interactive de tous les endpoints. Requiert la pile Docker.

```bash
# Ouvrir la documentation interactive
xdg-open http://localhost:8000/docs

# Ou la version ReDoc
xdg-open http://localhost:8000/redoc
```

**Endpoints principaux :**

```bash
# --- Authentification ---
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@nexussoc.cm","password":"admin"}'
# → {"access_token":"...","refresh_token":"...","expires_in":900}

TOKEN="<access_token>"

# --- Healthcheck ---
curl http://localhost:8000/health
curl http://localhost:8000/health/detailed | python3 -m json.tool

# --- Ingestion de télémétrie ---
curl -X POST http://localhost:8000/ingest \
  -H "Authorization: Bearer nexus_demo" \
  -H "X-Signature: $(sha256sum Lot1_Agent_Go/telemetry_sample.json | cut -d' ' -f1)" \
  -H "Content-Type: application/json" \
  -d @Lot1_Agent_Go/telemetry_sample.json
# → {"recus":59,"publies":59}

# --- Scoring Modèle 1 (anomalie réseau) ---
curl -X POST http://localhost:8000/score/network \
  -H "Content-Type: application/json" \
  -d '{"features":{"src_bytes":3200000,"dst_bytes":512,"duration":0}}'
# → {"risque":87,"anomalie":true,"score_brut":0.2341}

# --- Scoring Modèle 2 (fraude interne UEBA) ---
curl -X POST http://localhost:8000/score/user-day \
  -H "Content-Type: application/json" \
  -d '{"features":{"nb_exports":28,"volume_donnees_exportees":92000,"nb_acces_dossiers_sensibles":40,"nb_transactions":12,"montant_total_modifie":0,"nb_modifs_montant":0,"nb_connexions":3,"nb_actions_hors_heures":2,"nb_creations_compte":0,"nb_actions_total":45}}'
# → {"risque":94,"anomalie":true,"raisons":["volume de données exportées anormalement élevé (13.1σ)",...]}

# --- PLG : vérification email ---
curl -X POST http://localhost:8000/plg/check-email \
  -H "Content-Type: application/json" \
  -d '{"email":"dsi@microfinance-abc.com"}'
# → {"valid":true,"email":"dsi@microfinance-abc.com"}

curl -X POST http://localhost:8000/plg/check-email \
  -H "Content-Type: application/json" \
  -d '{"email":"agent@minfi.gov.cm"}'
# → HTTP 422 : {"code":"GOV_DOMAIN_REDIRECT","redirect_to":"sovereign_contact"}

# --- PLG : plans disponibles ---
curl http://localhost:8000/plg/plans | python3 -m json.tool

# --- Admin tenants ---
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/tenants
```

---

### Interface 5 — Wazuh Dashboard (SIEM)

Interface web du SIEM Wazuh. Requiert la pile Docker complète.

```bash
xdg-open https://localhost:5601
# Identifiants : admin / <WAZUH_ADMIN_PASSWORD dans .env>
# Ignorer l'avertissement certificat auto-signé (normal en dev)
```

**Ce que vous verrez :**
- Tableau de bord **Security Events** : événements ingérés depuis les agents Wazuh
- **Threat Hunting** : requêtes sur les index OpenSearch
- **Vulnerability Detector** : CVE détectées sur les postes
- **MITRE ATT&CK** : tactiques et techniques cartographiées

> Dans NEXUS SOC, Wazuh est utilisé comme **stockage chaud** (index des événements bruts). La corrélation avancée (kill-chain MITRE) se fait dans le Pipeline Lot 2, pas dans Wazuh.

---

## 4 — Démarrage standalone (sans Docker)

Pour les démonstrations rapides sans infrastructure Docker.

```bash
# 1. Pipeline SIEM complet (Lot 2)
cd Lot2_Pipeline_SIEM && unzip nexus-pipeline.zip && cd nexus-pipeline
python telemetry_gen.py
python normalizer.py telemetry_demo.json | python ../../correlation_engine_v2.py
# → 1 incident corrélé : Ransomware, chaîne T1204→T1059→T1005→T1071→T1486, risque 100/100

# Benchmark O(N²) → O(N)
python ../../correlation_engine_v2.py --benchmark

# 2. Modèles IA (Lot 3)
python3 Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
python3 Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py

# 3. SOAR (Lot 4)
python3 Lot4_SOAR/soar_engine.py

# 4. Monitoring dérive modèles (Lot 3)
python3 Lot3_IA/model_monitor.py --demo

# 5. Interfaces web (HTML/CSS/JS, aucun serveur requis)
xdg-open Lot8_PLG/landing_page.html                          # vitrine PLG
xdg-open Lot5_Restitution/portail/portal/index.html          # portail DSI client
xdg-open Lot7_Console_Fournisseur/console_fournisseur.html   # console fournisseur

# 6. Tests (hors RLS qui requiert PostgreSQL)
cd Lot6_Tests && unzip nexus-tests.zip && cd nexus-tests
python attack_simulation.py
python load_test.py
```

---

## 5 — Agent Go : compilation et déploiement

### Compiler l'agent standard (Lot 1)

```bash
cd Lot1_Agent_Go && unzip nexus-agent.zip && cd nexus-agent

# Linux amd64 (~5.0 Mo)
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent .

# Windows amd64 (~5.3 Mo)
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent.exe .
```

### Configurer et lancer

```bash
cat > config.json << 'EOF'
{
  "server_url":   "http://localhost:8000/ingest",
  "enroll_token": "nexus_demo",
  "hmac_key":     "VOTRE_CLE_HMAC",
  "agent_id":     "agent-poste-001",
  "tenant_id":    "11111111-1111-1111-1111-111111111111",
  "interval_sec": 30,
  "watch_dirs":   ["/home", "/tmp", "/var/log"],
  "queue_dir":    "./queue",
  "queue_max_mb": 50
}
EOF

./nexusagent -config config.json
```

### Déploiement automatisé depuis la console (Lot 7)

```bash
# One-liner Linux (généré par la console fournisseur)
curl -fsSL "https://nexussoc.cm/provision/oneliner?token=nexus_xxx&hostname=POSTE-01" | bash

# One-liner Windows (PowerShell en tant qu'Administrateur)
Set-ExecutionPolicy Bypass -Scope Process -Force
irm "https://nexussoc.cm/provision/oneliner?token=nexus_xxx&hostname=POSTE-01&os=windows" | iex

# Déploiement de masse Ansible
ansible-playbook -i inventaire.ini \
  Lot7_Console_Fournisseur/install_templates/ansible_nexus_agent.yml \
  -e "nexus_server=https://nexussoc.cm" \
  -e "nexus_token=nexus_xxx" \
  -e "nexus_tenant_id=11111111-1111-1111-1111-111111111111"
```

### Compiler l'agent PLG (Lot 8) — obfusqué + watermark

```bash
# Prérequis : garble installé (go install mvdan.cc/garble@latest)
cd Lot8_PLG

# Compilation CLI directe
python3 build_agent.py \
  --tenant-id "11111111-1111-1111-1111-111111111111" \
  --os linux --arch amd64

# Sans garble (debug)
python3 build_agent.py \
  --tenant-id "11111111-1111-1111-1111-111111111111" \
  --os linux --no-garble
```

---

## 6 — Module PLG (Product-Led Growth) — Lot 8

Flux d'acquisition automatisé pour les microfinances et cabinets comptables.

### Démarrer l'API PLG (avec la pile Docker)

Le module PLG est inclus automatiquement dans `scoring-service_app.py`. Pour le monter manuellement :

```python
# Dans scoring-service_app.py :
from Lot8_PLG.plg_api import router as plg_router
app.include_router(plg_router)
```

### Appliquer le schéma PLG

```bash
psql postgresql://nexus:change_me@localhost:5432/nexus_soc \
  -f Lot8_PLG/01_schema_plg.sql
```

### Tester le parcours d'inscription complet

```bash
# 1. Vérification email (email professionnel → OK)
curl -X POST http://localhost:8000/plg/check-email \
  -H "Content-Type: application/json" \
  -d '{"email":"directeur@caisse-abc.cm"}'

# 2. Inscription
curl -X POST http://localhost:8000/plg/register \
  -H "Content-Type: application/json" \
  -d '{"email":"directeur@caisse-abc.cm","organization_name":"Caisse ABC","sector":"microfinance"}'

# 3. Vérifier le statut d'un tenant trial
curl http://localhost:8000/plg/trial-status/<TENANT_ID>
# → {"plan":"trial","remaining_days":30,"quota":{"agents_active":0,"max_agents":5,...}}

# 4. Lancer la suspension des essais expirés (admin)
curl -X POST http://localhost:8000/plg/run-expiry-check
# → {"suspended_count":0}

# 5. Plans disponibles
curl http://localhost:8000/plg/plans | python3 -m json.tool
```

---

## 7 — Déploiement Souverain (Terraform) — Lot 8

Déploie la pile complète NEXUS SOC directement sur les serveurs de l'institution souveraine.

### Configuration

```bash
cd Lot8_PLG/terraform-souverain/

# Copier et adapter le fichier de configuration
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars
```

Valeurs minimales à renseigner dans `terraform.tfvars` :

```hcl
server_host          = "192.168.1.100"       # IP du serveur institution
server_user          = "ubuntu"
ssh_private_key_path = "~/.ssh/nexus_deploy"
institution_name     = "MINFI"
nexus_domain         = "soc.minfi.gov.cm"
```

### Clé SSH de déploiement

```bash
# Générer une clé dédiée (si absente)
ssh-keygen -t ed25519 -f ~/.ssh/nexus_deploy -C "nexus-soc-deploy"

# Copier la clé publique sur le serveur
ssh-copy-id -i ~/.ssh/nexus_deploy.pub ubuntu@192.168.1.100
```

### Déployer

```bash
terraform init      # télécharge les providers (null, tls, local, random)
terraform plan      # prévisualise les 10 ressources (lecture seule)
terraform apply     # déploie (durée : 5–15 min selon la connexion)
# → Taper "yes" pour confirmer
```

**Séquence de déploiement :**
```
Étape 1/7  Prérequis  → installe Docker, crée /opt/nexus-soc/
Étape 2/7  Configs    → upload .env, docker-compose.yml, 5 schémas SQL
Étape 3/7  Sources    → upload scoring-service + 5 modules Python
Étape 4/7  Modèles    → upload model1/model2 .joblib (si chemin fourni)
Étape 5/7  Certs      → génère les certificats SSL Wazuh
Étape 6/7  Compose up → docker compose up -d --wait (attend healthchecks)
Étape 7/7  Santé      → vérifie API, Kafka, PostgreSQL, Wazuh Indexer
```

### Récupérer les informations post-déploiement

```bash
terraform output nexus_api_url         # http://192.168.1.100:8000
terraform output wazuh_dashboard_url   # https://192.168.1.100:5601
terraform output -raw postgres_password
terraform output -raw wazuh_admin_password
terraform output next_steps            # guide post-déploiement complet
```

### Uploader les modèles IA (après déploiement)

```bash
# Entraîner localement
python3 Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
python3 Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py

# Copier sur le serveur
scp model1_isoforest.joblib ubuntu@192.168.1.100:/opt/nexus-soc/models/
scp model2_isoforest.joblib ubuntu@192.168.1.100:/opt/nexus-soc/models/

# Recharger le service
ssh ubuntu@192.168.1.100 'cd /opt/nexus-soc && docker compose restart scoring-service'
curl http://192.168.1.100:8000/health
# → {"status":"ok","modele1":true,"modele2":true}
```

### Mettre à jour après modification du code

```bash
# Terraform détecte automatiquement les changements (hash des fichiers)
terraform apply
# → Ne re-déploie que ce qui a changé
```

---

## 8 — Tests complets

### Vue d'ensemble

| Test | Fichier | Résultat attendu | Prérequis |
|---|---|---|---|
| Simulation MITRE (Atomic-style) | `Lot6_Tests/attack_simulation.py` | 7/7 techniques · 3/3 scénarios · MTTD 90–120 s | Python, Lot2 extrait |
| Charge pipeline | `Lot6_Tests/load_test.py` | ~200 000 ev/s · p99 ≤ 12 μs | Python, Lot2 extrait |
| Isolation RLS (Lot 6) | `Lot6_Tests/rls_isolation_test.py` | **5/5** assertions nexus_app | PostgreSQL local |
| Isolation RLS étendue (Lot 7) | `Lot7_Console_Fournisseur/rls_analyst_test.py` | **8/8** assertions | PostgreSQL local |
| Dérive modèles | `Lot3_IA/model_monitor.py --demo` | PSI + σ-drift calculés | Python, joblib |
| Pseudonymisation | `Lot1_Agent_Go/pseudonymizer.py` | IPs + emails pseudonymisés | Python |
| **API de fumée (Lot 9)** | `Lot6_Tests/test_api.py` | **16 tests** : auth multi-rôles, RBAC, analyste, PLG, cycle tenant | Serveur lancé + PostgreSQL + seed |

### Tests API de fumée (frontend connecté)

Valident le parcours REST de bout en bout. Skip propre si le serveur est injoignable.

```bash
# Terminal 1 — serveur (depuis la racine)
uvicorn run:app --port 8000

# Terminal 2 — tests
pip install pytest httpx
pytest Lot6_Tests/test_api.py -v
```

Couverture : login des 3 rôles, rejet d'un JWT invalide, cloisonnement RBAC
(un `dsi_client` reçoit 403 sur `/admin/*`), routes `/analyst/*`, filtres PLG
(email jetable bloqué, domaine `.gov.cm` redirigé), cycle de vie tenant
(créer → suspendre → réactiver → supprimer).

### Simulation d'attaques

```bash
cd Lot6_Tests && unzip nexus-tests.zip && cd nexus-tests
python attack_simulation.py
```

Résultats attendus :
```
✓ T1059 (PowerShell/cmd.exe)         ✓ T1071 (C2 port 4444)
✓ T1059 (exécution depuis /tmp)      ✓ T1486 (ransomware — >20 fichiers/5 min)
✓ T1105 (fichier .exe dans Downloads)✓ T1027 (obfuscation base64/iex)
✓ T1005 (accès /etc/shadow)

Scénarios : 3/3  |  Ransomware MTTD : 120 s  |  Exfiltration MTTD : 90 s
Négatif    : 0 faux positif
```

### Test de charge

```bash
python load_test.py
python make_lot6_figures.py   # génère les figures PNG
```

Résultats attendus :
```
Volume     Normalisation    Corrélation v1   Corrélation v2
1 000 ev   ~229 k ev/s      ~714 k ev/s      ~714 k ev/s
100 000 ev ~189 k ev/s      ~22 k ev/s       ~680 k ev/s  ← gain O(N²)→O(N)
```

### Tests RLS (requiert PostgreSQL)

```bash
# Si la pile Docker tourne :
docker exec -it nexus-postgres psql -U nexus -d nexus_soc

# Tests Lot 6 (5 assertions nexus_app)
python3 Lot6_Tests/rls_isolation_test.py

# Tests Lot 7 (8 assertions : nexus_app + nexus_analyst BYPASSRLS)
python3 Lot7_Console_Fournisseur/rls_analyst_test.py
```

---

## 9 — Commandes d'exploitation

### Sauvegarde et restauration

```bash
# Sauvegarde complète (PostgreSQL + Wazuh + modèles + config)
sudo bash Lot0_Socle/backup.sh --dest /opt/nexus-backups --compress
# → /opt/nexus-backups/nexus_20260529_020000.tar.gz

# Restauration
sudo bash Lot0_Socle/restore.sh --backup /opt/nexus-backups/nexus_20260529_020000
```

### Provisioning agents depuis l'API

```bash
TOKEN="<access_token admin>"

# Générer un token d'enrôlement (expire dans 24h, usage unique)
curl -X POST http://localhost:8000/provision/token \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"hostname":"POSTE-COMPTA-01","os":"linux","expires_in":"24h","one_time":true}'

# Révoquer tous les agents d'un tenant (urgence)
curl -X POST http://localhost:8000/provision/revoke-tenant/<TENANT_ID> \
  -H "Authorization: Bearer $TOKEN"

# Rotation de la clé HMAC d'un agent
curl -X POST http://localhost:8000/provision/rotate-hmac/<AGENT_ID> \
  -H "Authorization: Bearer $TOKEN"
```

### Monitoring des modèles IA

```bash
# Mode démo (sans base de données)
python3 Lot3_IA/model_monitor.py --demo

# Mode production (via l'API)
curl "http://localhost:8000/monitor/drift?days=7" | python3 -m json.tool
# Seuils : PSI > 0.10 = surveillance  |  PSI > 0.25 = ré-entraînement requis
```

### PLG : gestion des abonnements (admin)

```bash
TOKEN="<access_token admin>"

# Suspendre un tenant (non-paiement)
curl -X POST http://localhost:8000/plg/suspend/<TENANT_ID> \
  -H "Authorization: Bearer $TOKEN"

# Réactiver après paiement
curl -X POST http://localhost:8000/plg/resume/<TENANT_ID> \
  -H "Authorization: Bearer $TOKEN"

# Passer en plan Business
curl -X POST http://localhost:8000/plg/upgrade \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"<UUID>","plan":"business","payment_reference":"PAY-XYZ-2026"}'

# Lancer la suspension des essais expirés
curl -X POST http://localhost:8000/plg/run-expiry-check \
  -H "Authorization: Bearer $TOKEN"
```

---

## 10 — Résultats mesurés

| Dimension | Chiffre mesuré | Source |
|---|---|---|
| Taille binaire agent | **5,0 Mo Linux · 5,3 Mo Windows** | Lot 1, `go build` |
| Couverture MITRE | **7/7 techniques — 100 %** | Lot 6, simulation |
| Scénarios reconstitués | **3/3** | Lot 6 |
| MTTD Ransomware | **120 s** | Lot 6 |
| MTTD Exfiltration | **90 s** | Lot 6 |
| Débit normalisation | **~200 000 ev/s · p99 ≤ 12 μs** | Lot 6 |
| Isolation RLS | **5/5 (L6) · 8/8 (L7)** | Lots 6 & 7 |
| ROC-AUC M1 (Isolation Forest) | **0,987** | Lot 3 |
| ROC-AUC M1 (Autoencodeur) | **0,991** | Lot 3 |
| ROC-AUC M2 (UEBA fraude) | **0,969 · FPR 4 %** | Lot 3 |
| Détection exfiltration | **97 %** | Lot 3 |
| Détection fonctionnaires fantômes | **76 %** | Lot 3 |
| Détection faux mandatements | **54 %** | Lot 3 |

> Tous ces chiffres sont issus de jeux **synthétiques réalistes**. Validation sur données terrain prévue au MINFI (stage mai–juillet 2026).

---

## 11 — Limites documentées

| Limite | Impact | Perspective |
|---|---|---|
| Données synthétiques | Ordre de grandeur, pas preuve terrain | Données SIGIPES/SYDONIA au MINFI |
| Faux mandatements : 54 % | Zone grise légitimes/fraudes | UEBA personnalisé + LSTM temporel |
| Connecteurs SOAR simulés | freeze_account/isolate_host non exécutés | AD/LDAP/pare-feu à brancher au MINFI |
| WhatsApp hors fenêtre 24h | Nécessite templates Meta approuvés | Soumettre avant mise en production |
| Pré-auth bancaire = stub | CinetPay/PayDunya non intégré | Remplacer `_run_preauth()` dans plg_api.py |
| Single point of failure | Docker Compose mono-nœud | Kubernetes + Kafka multi-broker (HA) |
| Secrets en clair (config.json) | chmod 600 implémenté, clé HMAC reste un risque | DPAPI Windows / Linux Keyring dans l'agent |
| Chiffrement au repos absent | LUKS/pgcrypto volumes non configurés | Infrastructure production |
| Conformité ANTIC non validée | Démarche administrative requise | Stage MINFI |

---

## Cadre réglementaire

- **Loi n° 2010/012** — cybersécurité et cybercriminalité au Cameroun
- **ANTIC** — Agence Nationale des TIC (homologation des SIEM)
- **COBAC** — microfinances Afrique Centrale
- **CIMA** — code des assurances
- **ONECCA** — cabinets comptables Cameroun
- **ISO/IEC 27001** — référence SMSI (alignement des contrôles)

---

## Changelog

### Session du 29 mai 2026 — Intégration end-to-end + durcissement

Correction des décalages frontend↔backend et améliorations transverses.

| Fichier | Ajout / Correctif |
|---|---|
| `run.py` | **Fix montage routeurs** : `auth_router` (login) et `analyst_router` (`/analyst/*`) n'étaient pas montés ; `sys.path` des Lots ajouté pour les imports croisés. **CORS durci** : origines via `NEXUS_CORS_ORIGINS`, plus de wildcard+credentials |
| `Lot7_Console_Fournisseur/admin_api.py` | **Auth unifiée JWT** (remplace « mot de passe = token ») ; endpoints ajoutés : `/analyst/pending`, `/analyst/approve/{id}`, `/analyst/reject/{id}`, `/analyst/false-positive/{id}`, `/analyst/alerts/{id}`, `/admin/tenants/{id}/suspend`, `/activate` |
| `Lot7_Console_Fournisseur/provisioning_api.py` | Auth unifiée JWT + `/provision/revoke/{agent_id}` (révocation d'un agent unique) |
| `Lot9_Frontend/console.html` | Alignement des payloads `generateToken` (`expires_in_hours`) et `createTenant` (`offre`/`email_admin`) |
| `Lot0_Socle/02_seed_demo.sql` | Seed idempotent : comptes démo (admin/soc/dsi, mdp « admin »), 3 tenants, 5 agents, 4 alertes, 3 actions SOAR en attente |
| `Lot9_Frontend/icons/` | Icônes PWA générées (192, 512, badge-72, 2 screenshots) — plus de 404 à l'installation |
| `Lot6_Tests/test_api.py` | 16 tests de fumée httpx/pytest (auth, RBAC, analyste, PLG, cycle tenant) |
| `00_Documents/Architecture_NEXUS_SOC.drawio` | Diagramme d'architecture logique complet pour le rapport |

### Session du 29 mai 2026 — Lot 9 Frontend connecté (PWA, dynamique, responsive)

| Fichier | Ajout |
|---|---|
| `run.py` | Point d'entrée FastAPI unifié : charge tous les routers (auth, admin, provisioning, PLG) + sert `Lot9_Frontend/` sur `/app/` via StaticFiles |
| `Lot9_Frontend/js/api.js` | Client API universel 315L : JWT auto-refresh sur 401, 40+ méthodes (tenants, agents, alertes, SOAR, PLG, scoring), poll(), formatDate(), riskColor() |
| `Lot9_Frontend/login.html` | Page d'auth 362L : formulaire JWT + redirect automatique par rôle (admin/analyste → console, dsi_client → portail) |
| `Lot9_Frontend/console.html` | Console opérateur connectée 1715L : 7 sections (dashboard, tenants CRUD, agents + provisioning, alertes + SOAR approval, santé, facturation PLG) — polling 30s, toast, modals, responsive |
| `Lot9_Frontend/portail.html` | Portail DSI connecté 697L : bilingue FR/EN, trial banner dynamique, score calculé depuis alertes réelles, agents temps réel, modal détail |
| `Lot9_Frontend/sw.js` | Service worker PWA 132L : Cache First (assets), Network First (API), push notifications, offline fallback |
| `Lot9_Frontend/manifest.json` | Manifest PWA : shortcuts console + portail, standalone, icônes SVG |
| `Lot9_Frontend/offline.html` | Page hors ligne (affiché par le SW quand réseau indisponible) |

**Passage de statique → dynamique :**
Les frontends Lot 5 et Lot 7 restent disponibles comme maquettes de référence. Les nouvelles versions Lot 9 remplacent toutes les données hardcodées par des appels API réels.

---

### Session du 29 mai 2026 — Lot 8 PLG + Déploiement Souverain

| Fichier | Ajout / Correctif |
|---|---|
| `Lot8_PLG/landing_page.html` | Vitrine duale SaaS / Souverain — modal multi-étapes, filtre email live |
| `Lot8_PLG/plg_api.py` | API PLG : filtrage emails jetables, blocage domaines gov, pré-auth, quotas, suspension |
| `Lot8_PLG/01_schema_plg.sql` | Tables `plg_registrations`, `trial_quotas`, `subscriptions`, colonnes PLG sur `tenants` |
| `Lot8_PLG/build_agent.py` | Compilation garble + watermark HMAC injecté par ldflags par tenant |
| `Lot8_PLG/nexus-agent-plg/` | Agent coquille vide : `config_fetcher.go` (config dynamique + cache HMAC), `watermark.go`, `main_plg.go` |
| `Lot8_PLG/terraform-souverain/` | Module Terraform complet : `providers.tf`, `variables.tf`, `main.tf` (7 étapes), `outputs.tf`, 3 templates |
| `Lot1_Agent_Go/scoring-service_app.py` | `_enforce_trial_quota_sync()` sur `/ingest` : détecte suspendu/expiré/quota agents/quota events |

### Session du 28 mai 2026 — Correctifs sécurité + qualité

| Fichier | Ajout / Correctif |
|---|---|
| `scoring-service_app.py` v2 | Validation HMAC + Bearer sur `/ingest`, rate limiting 100/30 req/min, HTTP 429 |
| `auth_middleware.py` | JWT HMAC-SHA256 maison (access 15 min + refresh 7 j) |
| `pseudonymizer.py` | Pseudonymisation stable des PII (emails, IPs, agent_ids) |
| `correlation_engine_v2.py` | Bug O(N²)→O(N), règles T1027/T1136/T1083 ajoutées |
| `model_monitor.py` | Détection dérive PSI + σ-drift + endpoint `/monitor/drift` |
| `01_schema_retention.sql` | Compression TimescaleDB J7+, archivage alertes 1 an, purge tokens |
| `backup.sh` / `restore.sh` | Sauvegarde/restauration PostgreSQL + Wazuh + modèles |
| `console_fournisseur.html` | Lot 7 complet : admin multi-tenant + poste analyste SOC cross-tenant |

---

*NEXUS SOC — Plateforme SOC-as-a-Service souveraine — KEYCE Informatique & IA, Yaoundé, 2026*
