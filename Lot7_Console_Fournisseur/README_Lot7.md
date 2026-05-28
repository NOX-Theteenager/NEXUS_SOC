# NEXUS SOC — Lot 7 : Console Fournisseur

**Auteur** : NGUETSA Junior Stéphane Céleste — Bachelor 3 RSI · KEYCE Informatique & IA · Yaoundé  
**Statut** : Module A (Administration) réalisé · Module B (Analyste SOC) à venir

---

## Objectif

Interface web réservée à l'opérateur NEXUS SOC, séparée du portail client DSI (Lot 5).  
Contrairement au portail client qui voit uniquement les données d'un tenant, la console fournisseur supervise **tous les tenants simultanément**.

---

## Contenu du lot

| Fichier | Rôle |
|---|---|
| `console_fournisseur.html` | Interface standalone (HTML/CSS/JS embarqués, mode sombre, bilingue FR/EN) |
| `admin_api.py` | Endpoints FastAPI à intégrer dans le scoring-service (`/admin/*` et `/analyst/*`) |
| `01_schema_analyst.sql` | Patch SQL : colonne `statut` sur `tenants`, colonnes de provisioning agent, rôle `nexus_analyst` BYPASSRLS |
| `rls_analyst_test.py` | Test d'isolation RLS étendu : **8/8 assertions** (5 nexus_app + 3 nexus_analyst) |

---

## Modules de la console

### Module A — Administration (`admin_plateforme`) — **Réalisé**

- **Tableau de bord** : KPIs cross-tenants (tenants actifs, agents en ligne, incidents ouverts, disponibilité), résumé des tenants, fil d'activité récente.
- **Tenants** : liste, création, modification (nom, type, offre), suspension / réactivation.
- **Utilisateurs** : liste cross-tenants avec filtre par tenant et par rôle RBAC, création d'utilisateurs.
- **Agents** : liste cross-tenants, filtre par tenant et statut, génération de jetons d'enrôlement (Bearer token + clé HMAC-SHA256, affichés une seule fois).
- **Santé système** : état des 6 services (Kafka, TimescaleDB, Wazuh Manager, Wazuh Dashboard, scoring service, passerelle /ingest) + métriques 24 h.
- **Facturation** : ARR / MRR estimés, détail des abonnements par tenant (offre, montant, échéance).

### Module B — Poste Analyste SOC (`analyste_soc`) — **À venir**

- File d'alertes agrégée tous tenants (endpoints `/analyst/alerts` déjà implémentés dans `admin_api.py`)
- Approbation des actions SOAR en attente de validation humaine
- Tableau de bord SOC global (MTTD / MTTR, charge par tenant)

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
| GET | `/admin/tenants` | Lister tous les tenants avec métriques |
| POST | `/admin/tenants` | Créer un tenant + compte DSI initial |
| PATCH | `/admin/tenants/{id}` | Modifier nom / offre / statut |
| DELETE | `/admin/tenants/{id}` | Supprimer un tenant (irréversible) |
| GET | `/admin/users` | Lister les utilisateurs (tous tenants) |
| POST | `/admin/users` | Créer un utilisateur |
| GET | `/admin/agents` | Lister les agents (tous tenants) |
| POST | `/admin/agents/token` | Générer un jeton d'enrôlement d'agent |
| GET | `/admin/health` | État des services du socle |
| GET | `/admin/billing` | Vue facturation par tenant |

### `/analyst/*` (rôle analyste_soc)

| Méthode | Route | Description |
|---|---|---|
| GET | `/analyst/alerts` | File d'alertes agrégée tous tenants |
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

---

## Esthétique

Identique au portail client (Lot 5) :
- Mode sombre (fond `#0A0F1C`)
- Typographie : **Fraunces** (display) · **Manrope** (corps) · **JetBrains Mono** (technique)
- Palette : AMBER `#F5A524` (admin) · TEAL `#3DDC97` · BLUE `#5EAAFF` · RED `#EF4444`
- Bascule FR / EN instantanée sur tous les éléments
