# NEXUS SOC

**Plateforme SOC open source et souveraine, exploitée en interne par le CENADI**
Détection, corrélation et réponse aux incidents — cloisonnement par périmètre supervisé, hébergement local, restitution bilingue FR/EN.

**Auteur** : NGUETSA Junior Stéphane Céleste
**École** : KEYCE Informatique & IA, Yaoundé — Bachelor 3 RSI
**Stage** : CENADI (Centre National de Développement de l'Informatique)
**Soutenance** : 24 août 2026

> **Contexte.** NEXUS SOC est une plateforme 100 % open source, souveraine et
> exploitée **en interne par le CENADI**, opérateur des systèmes sensibles de
> l'État camerounais (SIGIPES — gestion des personnels et de la solde ;
> ANTILOPE — traitement de la solde). Le CENADI possède, audite, modifie et
> exploite lui-même la plateforme. L'argument n'est pas le prix mais la
> **souveraineté** et la **maîtrise du code**. Le multi-locataire technique est
> réinterprété comme un **cloisonnement de périmètres internes** : chaque
> « périmètre supervisé » est un système ou une zone (SIGIPES, ANTILOPE,
> réseau/LAN interne), pas un client payant.

---

## Navigation rapide

### Frontend connecté (Lot 9)

> Démarrer d'abord le serveur : `uvicorn run:app --host 0.0.0.0 --port 8000 --reload`

| Interface | Rôle | URL |
|---|---|---|
| **Login** | Authentification (tous rôles) | `http://localhost:8000/app/login.html` |
| **Console opérateur CENADI** | Admin + Analyste SOC — données réelles | `http://localhost:8000/app/console.html` |
| **Portail responsable de périmètre** | Vue filtrée — alertes + agents | `http://localhost:8000/app/portail.html` |
| **Documentation** | Guide intégré | `http://localhost:8000/app/docs.html` |
| **API REST (Swagger)** | Documentation interactive | `http://localhost:8000/docs` |
| **Wazuh Dashboard** | Interface SIEM | `https://localhost:5601` |

La racine `/` redirige vers la page de connexion : la plateforme est un outil
interne, sans vitrine publique.

### Maquette statique de référence (Lot 5)

| Interface | Commande |
|---|---|
| Portail (maquette) | `xdg-open Lot5_Restitution/portail/portal/index.html` |

### Tests automatisés

Suite API : `.venv/bin/pytest Lot6_Tests/test_api.py -v` → **14 passed**.
Isolation RLS : `python3 Lot7_Console_Fournisseur/rls_analyst_test.py` → **8/8**.

### Déploiement souverain (OpenTofu)

```bash
cd deploy/opentofu && tofu init && tofu plan && tofu apply
```

---

## Architecture globale

Sept composants intégrés (agent, pipeline SIEM, modèles IA, SOAR, restitution,
console opérateur, socle technique) :

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  NEXUS SOC — Architecture (exploitation CENADI)               │
│                                                                               │
│  ┌────────────┐  HTTPS       ┌──────────────┐  Kafka  ┌──────────────────┐   │
│  │ Agent Go   │ ───────────▶ │ /ingest      │ ──────▶ │ Pipeline SIEM    │   │
│  │ ~5 Mo      │  HMAC-SHA256 │ (FastAPI L1) │         │ Normalisation    │   │
│  │ Linux/Win  │  egress-only │              │         │ Corrélation MITRE│   │
│  └────────────┘              └──────────────┘         └────────┬─────────┘   │
│                                                                │ Alertes      │
│  ┌────────────────────────────────────────────────────┐       │              │
│  │  Modèles IA (Lot 3)                                 │◀──────┘              │
│  │  M1 : Isolation Forest + Autoencodeur (réseau)      │                      │
│  │  M2 : Isolation Forest UEBA (fraude interne)        │                      │
│  └─────────────────────────┬──────────────────────────┘                      │
│                            │                                                  │
│  ┌─────────────────────────▼─────────────────────────────────────────────┐   │
│  │  SOAR — Lot 4 (playbooks + garde-fous + validation humaine + rollback) │   │
│  └─────────────────────────┬─────────────────────────────────────────────┘   │
│                            │                                                  │
│       ┌────────────────────┼─────────────────────┐                           │
│       ▼                    ▼                      ▼                           │
│  ┌──────────┐      ┌────────────────┐    ┌──────────────────────┐            │
│  │ Notif.   │      │ Portail        │    │ Console opérateur     │            │
│  │ in-app   │      │ périmètre (L5) │    │ CENADI (Lot 7 + L9)   │            │
│  └──────────┘      └────────────────┘    └──────────────────────┘            │
│                                                                               │
│  ── Stockage ──────────────────────────────────────────────────────────────  │
│  TimescaleDB · Wazuh Indexer (OpenSearch) · RLS par périmètre · RBAC          │
│                                                                               │
│  ── Déploiement souverain ─────────────────────────────────────────────────  │
│  deploy/opentofu/  (OpenTofu, MPL 2.0) — pile complète sur serveur CENADI     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Structure du dépôt

```
NEXUS_SOC/
├── README.md                            ← ce fichier
├── LICENSE                              ← GPL-3.0-or-later
├── THIRD_PARTY_LICENSES.md              ← licences des composants tiers
├── MIGRATION.md                         ← journal de la refonte souveraine CENADI
├── INVENTAIRE.md
│
├── 00_Documents/                        ← livrables académiques
│
├── Lot0_Socle/                          ← pile Docker complète
│   ├── docker-compose.yml               ← 6 services avec healthchecks
│   ├── 01_schema_patched.sql            ← schéma SQL (RLS par périmètre + RBAC + TimescaleDB)
│   ├── 01_schema_retention.sql          ← politiques de rétention + compression
│   ├── 02_seed_demo.sql                 ← périmètres + comptes + alertes de démo
│   ├── 03_schema_notifications.sql      ← notifications push in-app
│   └── backup.sh / restore.sh           ← sauvegarde/restauration automatisées
│
├── Lot1_Agent_Go/                       ← agent endpoint (~5 Mo, pur stdlib Go)
│   ├── nexus-agent.zip                  ← main.go, collect.go, buffer.go, sender.go
│   ├── scoring-service_app.py           ← API FastAPI v2 (scoring + /ingest)
│   ├── auth_middleware.py               ← JWT HMAC-SHA256 (access 15 min + refresh 7 j)
│   └── pseudonymizer.py                 ← pseudonymisation HMAC stable des PII
│
├── Lot2_Pipeline_SIEM/                  ← normalisation + corrélation MITRE ATT&CK
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
│   ├── test_api.py                      ← suite API (14 tests httpx/pytest)
│   └── nexus-tests.zip                  ← attack_simulation · load_test · rls_test
│
├── Lot7_Console_Fournisseur/            ← API console opérateur CENADI + provisioning
│   ├── admin_api.py                     ← FastAPI /admin/* + /analyst/* + /portal/*
│   ├── provisioning_api.py              ← tokens · scripts · QR · bulk · one-liner
│   ├── 01_schema_analyst.sql            ← rôle nexus_analyst (BYPASSRLS) + colonnes token
│   ├── 01_schema_provisioning.sql       ← cycle de vie des tokens
│   └── rls_analyst_test.py              ← 8/8 assertions RLS nexus_app + nexus_analyst
│
├── Lot9_Frontend/                       ← ★ Frontend connecté (PWA, dynamique, responsive)
│   ├── login.html                       ← authentification (JWT, redirect par rôle)
│   ├── console.html                     ← console opérateur CENADI connectée
│   ├── portail.html                     ← portail responsable de périmètre (bilingue FR/EN)
│   ├── docs.html / contact.html         ← documentation + contact équipe SOC
│   ├── manifest.json / sw.js            ← PWA (shortcuts, icônes, service worker)
│   ├── js/api.js                        ← client API universel (JWT auto-refresh)
│   └── icons/                           ← icônes PWA
│
├── deploy/opentofu/                     ← ★ Déploiement souverain (OpenTofu, MPL 2.0)
│   ├── providers.tf / variables.tf / main.tf / outputs.tf
│   ├── terraform.tfvars.example         ← institution_name=CENADI, nexus_domain=soc.cenadi.gov.cm
│   ├── README.md                        ← workflow tofu init/plan/apply
│   └── templates/                       ← env.tpl · docker-compose.tpl · Dockerfile.scoring.tpl
│
└── run.py                               ← ★ Point d'entrée principal (tous routers + frontend)
                                            uvicorn run:app --host 0.0.0.0 --port 8000
```

---

## Prérequis

### Obligatoires pour la pile complète

```bash
# Docker Engine + Docker Compose v2
docker --version && docker compose version

# Paramètre noyau requis par Wazuh Indexer (OpenSearch)
sudo sysctl -w vm.max_map_count=262144
```

### Python (scripts standalone + frontend connecté)

```bash
# Dépendances (scoring, modèles, pipeline, API, frontend)
pip install -r requirements.txt
```

### Go (compilation de l'agent)

```bash
# Go 1.21+ — agent pur stdlib, aucune dépendance externe
go version
```

### OpenTofu (déploiement souverain uniquement)

```bash
# OpenTofu >= 1.6 (outil IaC libre, licence MPL 2.0)
tofu version
```

### RAM recommandée

- Pile Docker complète (Kafka + TimescaleDB + Wazuh ×3 + scoring) : **8 Go** minimum.
- Frontend connecté + PostgreSQL seul (mode dégradé, sans Kafka/Wazuh) : **2 Go**.

---

## 1 — Démarrage rapide : frontend connecté

```bash
# 1. Installer les dépendances Python
pip install -r requirements.txt

# 2. Entraîner les modèles IA (si pas encore fait)
python3 Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
python3 Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py

# 3. Lancer le serveur (tous routers + frontend sur /app/)
export DB_DSN="postgresql://nexus:change_me@localhost:5432/nexus_soc"
export JWT_SECRET="CHANGE_ME_IN_PRODUCTION_USE_32_RANDOM_BYTES"
uvicorn run:app --host 0.0.0.0 --port 8000 --reload

# 4. Ouvrir le navigateur
#    http://localhost:8000/  → redirige vers /app/login.html
```

Le serveur fonctionne en **mode dégradé gracieux** si Kafka/Wazuh sont absents :
seuls PostgreSQL et l'API sont requis pour la console et le portail.

---

## 2 — Démarrage complet : pile Docker (données réelles)

```bash
# Étape 1 — Extraire le socle
cd Lot0_Socle && unzip -o nexus-soc-socle.zip

# Étape 2 — Configurer les variables d'environnement
cp .env.example .env
# Editer .env : changer POSTGRES_PASSWORD, JWT_SECRET, PSEUDO_SECRET

# Étape 3 — Générer les certificats Wazuh (une seule fois)
docker compose -f generate-certs.yml run --rm generator

# Étape 4 — Entraîner et déposer les modèles IA
cp model1_isoforest.joblib model2_isoforest.joblib models/

# Étape 5 — Démarrer la pile (attendre ~90 s que tous les services soient healthy)
docker compose up -d

# Étape 6 — Vérifier
curl http://localhost:8000/health
# → {"status":"ok","modele1":true,"modele2":true}
```

### Appliquer tous les schémas SQL

> **IMPORTANT — ordre des schémas.** Les fichiers ci-dessous doivent être
> appliqués **dans cet ordre exact**. `01_schema_analyst.sql` ajoute les colonnes
> `token_hash`/`hmac_key_hash` à la table `agents` et la colonne `statut` à
> `tenants` ; `01_schema_provisioning.sql` ajoute le cycle de vie des tokens.
> Le seed doit être appliqué **en dernier**.

```bash
DB="postgresql://nexus:change_me@localhost:5432/nexus_soc"

psql $DB -f Lot0_Socle/01_schema_patched.sql            # 1. base (périmètres, users, agents, alerts…)
psql $DB -f Lot0_Socle/01_schema_retention.sql          # 2. rétention / purge
psql $DB -f Lot7_Console_Fournisseur/01_schema_analyst.sql        # 3. rôle analyste + token_hash + statut
psql $DB -f Lot7_Console_Fournisseur/01_schema_provisioning.sql   # 4. cycle de vie des tokens
psql $DB -f Lot0_Socle/03_schema_notifications.sql      # 5. notifications push in-app
psql $DB -f Lot0_Socle/02_seed_demo.sql                 # 6. périmètres + comptes + alertes (EN DERNIER)
```

Variante **conteneur** (le `psql` local n'est pas requis) :

```bash
for f in \
  Lot0_Socle/01_schema_patched.sql \
  Lot0_Socle/01_schema_retention.sql \
  Lot7_Console_Fournisseur/01_schema_analyst.sql \
  Lot7_Console_Fournisseur/01_schema_provisioning.sql \
  Lot0_Socle/03_schema_notifications.sql \
  Lot0_Socle/02_seed_demo.sql \
; do
  echo "── $f"
  docker exec -i nexus-postgres psql -U nexus -d nexus_soc -q < "$f"
done
```

### Ports exposés

| Service | Port | Usage |
|---|---|---|
| scoring-service (API) | 8000 | `/ingest`, `/score/*`, `/admin/*`, `/analyst/*`, frontend `/app` |
| TimescaleDB | 5432 | PostgreSQL 16 + séries temporelles |
| Kafka (KRaft) | 9092 / 29092 | pipeline temps réel |
| Wazuh Indexer | 9200 | stockage chaud (OpenSearch) |
| Wazuh Dashboard | 5601 | interface SIEM (HTTPS) |

---

## 3 — Comptes de démonstration

Après `02_seed_demo.sql` (mot de passe `admin` pour tous) :

| Compte | Rôle | Interface |
|---|---|---|
| `admin@nexussoc.cm` | admin_plateforme (opérateur CENADI) | console.html |
| `soc@nexussoc.cm` | analyste_soc (SOC CENADI, tous périmètres) | console.html |
| `resp.sigipes@cenadi.cm` | dsi_client (responsable périmètre SIGIPES) | portail.html |
| `resp.antilope@cenadi.cm` | dsi_client (responsable périmètre ANTILOPE) | portail.html |

Périmètres supervisés de démo : **SIGIPES** (application métier, critique),
**ANTILOPE** (application métier, critique), **Réseau/LAN CENADI** (réseau, sensible).

---

## 4 — API REST (exemples)

```bash
# --- Authentification ---
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@nexussoc.cm","password":"admin"}'
# → {"access_token":"...","refresh_token":"...","expires_in":900}

# --- Healthcheck ---
curl http://localhost:8000/health

# --- Scoring Modèle 1 (anomalie réseau) ---
curl -X POST http://localhost:8000/score/network \
  -H "Content-Type: application/json" \
  -d '{"features":{"src_bytes":3200000,"dst_bytes":512,"duration":0}}'

# --- Scoring Modèle 2 (fraude interne UEBA) ---
curl -X POST http://localhost:8000/score/user-day \
  -H "Content-Type: application/json" \
  -d '{"features":{"nb_exports":28,"volume_donnees_exportees":92000,"nb_acces_dossiers_sensibles":40,"nb_transactions":12,"montant_total_modifie":0,"nb_modifs_montant":0,"nb_connexions":3,"nb_actions_hors_heures":2,"nb_creations_compte":0,"nb_actions_total":45}}'

# --- Admin : lister les périmètres supervisés (JWT admin requis) ---
curl http://localhost:8000/admin/perimetres -H "Authorization: Bearer $TOKEN"
```

---

## 5 — Isolation par périmètre (RLS)

Une seule instance héberge tous les périmètres. L'isolation repose sur la
**Row-Level Security** de PostgreSQL : chaque requête applicative positionne
`SET app.current_tenant = '<uuid>'` avant les requêtes.

- **`nexus_app`** — rôle applicatif, soumis à la RLS (un seul périmètre visible).
- **`nexus_analyst`** — analyste SOC du CENADI, `BYPASSRLS`, supervise l'ensemble
  des périmètres.
- Patch clé : `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid`.

> La colonne technique `tenant_id` et les rôles `nexus_app`/`nexus_analyst` sont
> conservés tels quels : ce sont les identifiants de cloisonnement portés par la
> RLS. Seule la **sémantique** change (un « tenant » est un périmètre supervisé).

Validation : `python3 Lot7_Console_Fournisseur/rls_analyst_test.py` → **8/8**.

---

## 6 — Déploiement souverain (OpenTofu)

La pile complète se déploie sur un serveur du CENADI via SSH, avec
[OpenTofu](https://opentofu.org/) (outil IaC libre, licence MPL 2.0)
pour garantir une chaîne d'outils 100 % open source.

```bash
cd deploy/opentofu
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars          # server_host, ssh_private_key_path…
                               # institution_name=CENADI, nexus_domain=soc.cenadi.gov.cm par défaut

tofu init
tofu plan
tofu apply                     # déploie la pile (~5–15 min)

tofu output -raw postgres_password
tofu output -raw wazuh_admin_password
```

Détails : voir [`deploy/opentofu/README.md`](deploy/opentofu/README.md).

---

## 7 — Tests

```bash
# Suite API (14 tests) — serveur lancé requis
uvicorn run:app --port 8000            # terminal 1
pytest Lot6_Tests/test_api.py -v       # terminal 2 → 14 passed

# Isolation RLS étendue (8 assertions) — PostgreSQL local requis
python3 Lot7_Console_Fournisseur/rls_analyst_test.py   # → 8/8

# Simulation d'attaques + charge (dans nexus-tests.zip)
python attack_simulation.py            # 7/7 techniques, MTTD 90–120 s
python load_test.py                    # ~200 000 ev/s
```

---

## 8 — Sauvegarde / restauration

```bash
sudo bash Lot0_Socle/backup.sh  --dest /opt/nexus-backups --compress
sudo bash Lot0_Socle/restore.sh --backup /opt/nexus-backups/nexus_<date>
```

---

## Licence

NEXUS SOC est distribué sous **GPL-3.0-or-later** (voir [LICENSE](LICENSE)),
licence copyleft compatible avec Wazuh (GPL v2). Les licences des composants
tiers sont listées dans [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
