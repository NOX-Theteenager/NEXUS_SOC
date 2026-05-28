# NEXUS SOC — Socle technique (Lot 0)

Plateforme de développement intégrée qui assemble les briques du projet en un seul
`docker compose` : **SIEM (Wazuh)**, **pipeline temps réel (Kafka)**, **stockage chaud
(indexeur Wazuh, compatible Elasticsearch)**, **base relationnelle + séries temporelles
(PostgreSQL/TimescaleDB)** et un **service de scoring** qui branche les modèles d'IA et le SOAR
sur le pipeline. On passe ainsi des briques isolées à une plateforme cohérente.

> **« Où est Elasticsearch ? »** — Wazuh 4.x embarque son propre **indexeur** (basé sur
> OpenSearch, exposant l'API Elasticsearch sur le port 9200). Il joue le rôle de stockage chaud.
> Déployer un Elasticsearch *séparé* serait redondant et doublerait la charge mémoire — coûteux
> sur du matériel limité. Le socle réutilise donc l'indexeur Wazuh comme moteur de recherche.

---

## 1. Arborescence

```
nexus-soc-socle/
├── docker-compose.yml            # la pile complète
├── generate-certs.yml            # génération unique des certificats Wazuh
├── .env.example                  # variables (copier en .env)
├── config/
│   ├── certs.yml                 # description des nœuds pour les certificats
│   ├── wazuh_indexer/opensearch.yml
│   └── postgres/init/01_schema.sql   # schéma multi-tenant (RLS + RBAC + alertes + métriques)
├── models/                       # y déposer model1_isoforest.joblib et model2_isoforest.joblib
└── scoring-service/              # service d'intégration IA → SOAR
    ├── Dockerfile
    ├── requirements.txt
    └── app.py
```

## 2. Prérequis

- Docker + Docker Compose v2.
- **~8 Go de RAM** recommandés (l'indexeur et le tableau de bord sont gourmands).
- Augmenter `vm.max_map_count` (requis par l'indexeur) :
  ```bash
  sudo sysctl -w vm.max_map_count=262144
  ```
- Déposer les deux modèles entraînés dans `models/` :
  `model1_isoforest.joblib` et `model2_isoforest.joblib` (produits par les pipelines des Modèles 1 et 2).

## 3. Démarrage

```bash
# 1. Configuration
cp .env.example .env          # adapter les mots de passe

# 2. Générer les certificats Wazuh (une seule fois)
docker compose -f generate-certs.yml run --rm generator

# 3. Lancer la plateforme
docker compose up -d

# 4. Suivre le démarrage
docker compose ps
docker compose logs -f scoring-service
```

## 4. Services et ports

| Service | Rôle | Accès |
|---|---|---|
| `kafka` | Pipeline temps réel | `localhost:29092` (hôte), `kafka:9092` (interne) |
| `postgres` | Config, tenants, alertes, métriques | `localhost:5432` |
| `wazuh.indexer` | Stockage chaud (compatible Elasticsearch) | `https://localhost:9200` |
| `wazuh.manager` | SIEM / corrélation | API `localhost:55000`, agents `1514/1515` |
| `wazuh.dashboard` | Interface SIEM | `https://localhost:5601` |
| `scoring-service` | Scoring IA + alimentation du SOAR | `http://localhost:8000/docs` |

## 5. Vérifier l'intégration IA

Le service de scoring expose une API (documentation interactive sur `/docs`) :

```bash
# Santé + modèles chargés
curl http://localhost:8000/health

# Scorer une journée d'activité (Modèle 2 — fraude)
curl -X POST http://localhost:8000/score/user-day -H "Content-Type: application/json" \
  -d '{"features": {"nb_exports": 28, "volume_donnees_exportees": 90000, "nb_acces_dossiers_sensibles": 40}}'
# → { "risque": 9x, "anomalie": true, "raisons": ["volume de données exportées anormalement élevé (..σ)", ...] }
```

En fonctionnement, le service **consomme la télémétrie** sur le topic `nexus.telemetry`, score
chaque événement, et **publie les alertes** sur `nexus.alerts` (consommé par le SOAR) tout en les
**persistant dans PostgreSQL** (table `alerts`).

## 6. Le schéma multi-tenant (PostgreSQL)

`config/postgres/init/01_schema.sql` crée les tables `tenants`, `users` (RBAC), `agents`,
`alerts`, `soar_audit` et `metrics` (hypertable TimescaleDB). L'**isolation entre clients** est
appliquée au niveau base par **Row-Level Security** : une session ne voit que les données de son
tenant (variable `app.current_tenant` positionnée par l'API après authentification). C'est la
traduction concrète de l'exigence « isolation des tenants + RBAC strict » du cahier des charges.

## 7. Flux de données

```
Agents (Go) → Kafka (nexus.telemetry) → scoring-service (Modèles 1 & 2)
   → nexus.alerts → SOAR (playbooks + garde-fous) → connecteurs / portail / notifications
Wazuh Manager → Wazuh Indexer (stockage chaud) → Wazuh Dashboard
scoring-service → PostgreSQL/TimescaleDB (alertes, audit, métriques)
```

## 8. Avertissements honnêtes

- La partie **Wazuh** suit le modèle de déploiement *single-node* officiel de Wazuh. Les
  **tags d'images** (`4.9.0`) et la procédure de certificats peuvent évoluer : à confirmer avec la
  documentation Wazuh en vigueur.
- Les **connecteurs du SOAR** (pare-feu, Active Directory, EDR, SMS) restent **simulés** tant
  qu'ils ne sont pas branchés sur des systèmes réels.
- Ce socle est un **environnement de développement**. Le déploiement de production (Kubernetes,
  Helm, Terraform, secrets managés, TLS partout) est le lot suivant de l'architecture cible.

## 9. Arrêt

```bash
docker compose down            # arrêt
docker compose down -v         # arrêt + suppression des volumes (remise à zéro)
```
