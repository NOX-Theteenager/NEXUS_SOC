# NEXUS SOC — Lot 7 : Console opérateur CENADI (API)

**Auteur** : NGUETSA Junior Stéphane Céleste — Bachelor 3 RSI · KEYCE Informatique & IA · Yaoundé  
**Statut** : API d'administration + provisioning · console web connectée dans le Lot 9

---

## Objectif

API réservée à l'opérateur du CENADI, séparée du portail de périmètre (Lot 5).  
Contrairement au portail de périmètre qui voit uniquement les données d'un seul
périmètre, la console opérateur supervise **tous les périmètres simultanément**.
L'interface web connectée correspondante vit dans le Lot 9 (`console.html`).

---

## Contenu du lot

| Fichier | Rôle |
|---|---|
| `admin_api.py` | Endpoints FastAPI montés par `run.py` (`/admin/*`, `/analyst/*`, `/portal/*`) |
| `provisioning_api.py` | Cycle de vie des jetons d'enrôlement d'agents (`/provision/*`) |
| `01_schema_analyst.sql` | Patch SQL : colonne `statut` sur `tenants`, colonnes de provisioning agent, rôle `nexus_analyst` BYPASSRLS |
| `rls_analyst_test.py` | Test d'isolation RLS étendu : **8/8 assertions** (5 nexus_app + 3 nexus_analyst) |

---

## Modules de la console

### Module A — Administration (`admin_plateforme`) — **Réalisé**

- **Tableau de bord** : KPIs cross-périmètre (périmètres actifs, agents en ligne, incidents ouverts, disponibilité), résumé des périmètres, fil d'activité récente.
- **Périmètres supervisés** : liste, création, modification (nom, type, criticité), suspension / réactivation.
- **Utilisateurs** : liste cross-périmètre avec filtre par périmètre et par rôle RBAC, création d'utilisateurs.
- **Agents** : liste cross-périmètre, filtre par périmètre et statut, génération de jetons d'enrôlement (Bearer token + clé HMAC-SHA256, affichés une seule fois).
- **Santé système** : état des 6 services (Kafka, TimescaleDB, Wazuh Manager, Wazuh Dashboard, scoring service, passerelle /ingest) + métriques 24 h.

### Module B — Poste Analyste SOC (`analyste_soc`) — **À venir**

- File d'alertes agrégée tous les périmètres (endpoints `/analyst/alerts` déjà implémentés dans `admin_api.py`)
- Approbation des actions SOAR en attente de validation humaine
- Tableau de bord SOC global (MTTD / MTTR, charge par périmètre)

---

## Point clé RLS : nexus_analyst vs nexus_app

| Rôle | BYPASSRLS | Comportement |
|---|---|---|
| `nexus_app` | Non | Voit uniquement le tenant défini par `SET app.current_tenant = '<uuid>'` |
| `nexus_analyst` | **Oui** | Voit **toutes** les lignes de toutes les tables, sans filtre tenant |

Le rôle `nexus_analyst` n'est jamais super-utilisateur (NOSUPERUSER). Il dispose uniquement de SELECT sur les tables pertinentes et UPDATE limité sur `soar_audit` (approbation).

---

## Intégration dans le scoring-service

Ajouter dans `scoring-service_app.py` :

```python
from admin_api import router as admin_router, analyst_router
app.include_router(admin_router)
app.include_router(analyst_router)
```

Définir les variables d'environnement :

```env
DB_DSN=postgresql://nexus_app:nexus_pass@timescaledb:5432/nexus
DB_DSN_ANALYST=postgresql://nexus_analyst:CHANGE_ME@timescaledb:5432/nexus
```

---

## Endpoints disponibles

### `/admin/*` (rôle admin_plateforme)

| Méthode | Route | Description |
|---|---|---|
| GET | `/admin/tenants` | Lister tous les périmètres avec métriques |
| POST | `/admin/tenants` | Créer un périmètre + compte responsable initial |
| PATCH | `/admin/tenants/{id}` | Modifier nom / criticité / statut |
| DELETE | `/admin/tenants/{id}` | Supprimer un périmètre (irréversible) |
| GET | `/admin/users` | Lister les utilisateurs (tous les périmètres) |
| POST | `/admin/users` | Créer un utilisateur |
| GET | `/admin/agents` | Lister les agents (tous les périmètres) |
| POST | `/admin/agents/token` | Générer un jeton d'enrôlement d'agent |
| GET | `/admin/health` | État des services du socle |
| GET | `/admin/perimetres` | Inventaire synthétique des périmètres |

### `/analyst/*` (rôle analyste_soc)

| Méthode | Route | Description |
|---|---|---|
| GET | `/analyst/alerts` | File d'alertes agrégée tous les périmètres |
| POST | `/analyst/alerts/{id}/approve` | Approuver une action SOAR en attente |
| GET | `/analyst/dashboard` | Métriques SOC globales |

---

## Test RLS étendu

```bash
python3 rls_analyst_test.py
```

Résultat attendu : **8/8 assertions vérifiées**

```
  ▸ nexus_app (RLS — filtré par tenant)
  ✓ #1 Tenant A voit 3 alertes
  ✓ #2 Tenant B voit 2 alertes
  ✓ #3 Fuite A→B bloquée (→ 0)
  ✓ #4 Sans tenant : 0 alerte
  ✓ #5 Tenant A voit UNIQUEMENT tenant_id=A

  ▸ nexus_analyst (BYPASSRLS — cross-tenant)
  ✓ #6 COUNT(alerts) global = 5
  ✓ #7 Filtre sur tenant A → 3 alertes
  ✓ #8 2 tenant_id distincts visibles
```

