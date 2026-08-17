# Réponse collaborative — dossiers d'enquête et discussion

Déploiement de DFIR-IRIS et de Mattermost dans le cœur SOC.

> **État au 17 août 2026.** Rien de ceci n'est déployé. Phases 3 et 4 du
> [plan](../00_Documents/Decision_Reponse_Collaborative.md).

---

## 1. Ce que chaque outil fait, et ne fait pas

Une seule autorité par question. C'est la règle qui gouverne toute
l'intégration.

| Question | Qui répond |
|---|---|
| Y a-t-il une anomalie ? | NEXUS (M1, M2, corrélation) |
| Quelle réponse proposer ? | NEXUS (`choisir_action_soar`) |
| Qui approuve, qui exécute, avec quel résultat ? | **NEXUS seul** (`soar_audit`) |
| Où en est l'enquête, qui la mène, qu'a-t-on appris ? | **IRIS** |
| Où discute-t-on en direct ? | Mattermost |

IRIS ne décide pas et n'exécute pas. Il porte l'enquête, ce que NEXUS n'a jamais
su faire : ni timeline, ni observables, ni assignation, ni clôture motivée.

---

## 2. Pourquoi IRIS et pas TheHive

TheHive 5 n'a pas de code publié, et son édition gratuite plafonne à
2 utilisateurs et 1 organisation. IRIS est sous **LGPL-3.0**, sans plafond, et
tourne sur PostgreSQL, ce qui évite d'ajouter un Elasticsearch à côté de
l'indexeur Wazuh.

Sa notion de `customer` porte des droits par client. Les périmètres supervisés
(SIGIPES, ANTILOPE, réseau CENADI) s'y projettent directement, donc le
cloisonnement se prolonge dans l'outil d'enquête au lieu de s'arrêter à la
frontière de NEXUS.

L'adaptateur `Lot4_SOAR/dossiers/base.py` reste abstrait : cinq méthodes, un
adaptateur IRIS livré, un adaptateur TheHive possible. L'intégration n'est
captive d'aucun produit.

---

## 3. Déploiement d'IRIS

IRIS se déploie avec sa propre composition, à une version figée. Ne pas
recopier sa composition dans le dépôt : elle utilise `extends` sur un fichier de
base, et une copie partielle diverge silencieusement à la première mise à jour.

```bash
git clone --branch v2.4.20 --depth 1 https://github.com/dfir-iris/iris-web.git \
    /opt/nexus-iris
cd /opt/nexus-iris
cp .env.model .env
```

Dans `/opt/nexus-iris/.env`, renseigner au minimum :

```
POSTGRES_PASSWORD=<aléatoire, 32 caractères>
POSTGRES_ADMIN_PASSWORD=<aléatoire, 32 caractères>
IRIS_SECRET_KEY=<aléatoire, 48 caractères>
IRIS_SECURITY_PASSWORD_SALT=<aléatoire, 32 caractères>
IRIS_ADM_PASSWORD=<mot de passe de l'administrateur IRIS>
IRIS_ADM_API_KEY=<clé d'API que NEXUS utilisera>
SERVER_NAME=iris.soc.cenadi.local
```

```bash
docker compose up -d
```

IRIS embarque sa propre base (`ghcr.io/dfir-iris/iriswebapp_db`). On pourrait la
pointer vers `nexus-postgres` par `POSTGRES_SERVER`, mais l'image officielle
effectue son initialisation : garder la base fournie coûte environ 200 Mio et
supprime une classe entière de pannes le jour de la démonstration.

### Réseau

IRIS écoute sur le cœur SOC uniquement. Aucun port ne doit être publié sur une
interface joignable depuis une autre zone : la matrice de flux autorise
l'administration depuis la zone Admin, et c'est le seul chemin.

### Première configuration

1. Créer un `customer` par périmètre supervisé : `SIGIPES`, `ANTILOPE`,
   `Réseau CENADI`. Relever les identifiants numériques, ils alimentent la
   correspondance `tenant_id` vers `alert_customer_id`.
2. Relever les identifiants de sévérité, la table est propre à l'instance.
3. Créer un utilisateur de service pour NEXUS, avec le droit d'écriture sur les
   alertes et rien de plus.

---

## 4. Déploiement de Mattermost

Mattermost Team Edition réutilise `nexus-postgres`, avec une base et un rôle
dédiés. Voir [docker-compose.reponse.yml](../Lot0_Socle/docker-compose.reponse.yml).

```bash
docker exec -i nexus-postgres psql -U nexus -d postgres <<'SQL'
CREATE ROLE mattermost LOGIN PASSWORD 'à-remplacer';
CREATE DATABASE mattermost OWNER mattermost;
SQL

docker compose -f Lot0_Socle/docker-compose.reponse.yml up -d
```

Créer ensuite une équipe `CENADI-SOC` et un robot `nexus-soc`, puis reporter son
jeton dans le `.env` du cœur SOC.

---

## 5. Le flux

```
  collecteur → /ingest → scoring-service_app.py
                          ├─ alerte persistée (alerts)
                          ├─ _proposer_soar()  → soar_audit
                          └─ _ouvrir_dossier() → dossier_sortie
                                                      │
                             worker de reprise ───────┘
                                       │ POST /alerts/add
                                       ▼
                                     IRIS        alerte reçue, non escaladée
                                       │         GET /alerts/similarities/{id}
                        l'analyste juge : bruit, ou incident ?
                                       │
                    escalate/{id}  ────┴──── merge/{id}
                                       │
                          hook on_postload_alert_escalate
                            ┌──────────┴──────────┐
                            ▼                     ▼
                    iris-webhooks-module     iris-nexus-module
                            │                     │ statut renvoyé à NEXUS
                            ▼                     ▼
                       Mattermost           la console reflète l'état réel
                  #incident-20260817-a3f
```

Deux points méritent d'être soulignés.

**IRIS rapproche les alertes voisines** par `GET /alerts/similarities/{id}`.
La déduplication grossière de NEXUS, réglée à 60 minutes après la crue de
juillet, cesse d'être la seule défense : l'analyste voit le groupe et fusionne.

**L'escalade est un geste humain.** NEXUS pousse des alertes, pas des dossiers.
Ouvrir une enquête reste une décision d'analyste, cohérente avec toute la ligne
du projet.

---

## 6. Correspondance des champs

| Champ IRIS | Contenu | Source NEXUS |
|---|---|---|
| `alert_title` | `[SIGIPES] Anomalie réseau / C2 — SRV-APP-GOV-01` | type, entité, périmètre |
| `alert_description` | écarts en σ, rédigés | `raisons` |
| `alert_severity_id` | dérivé du risque mesuré | `risque` |
| `alert_customer_id` | le périmètre | `tenant_id` |
| `alert_source` | `NEXUS SOC` | constante |
| `alert_source_ref` | UUID de l'alerte | clé d'idempotence |
| `alert_source_link` | `console.html#alerte={id}` | retour vers l'explicabilité |
| `alert_source_content` | charge brute | `score_parts`, `chaine`, `iocs` |
| `alert_context` | périmètre, criticité, agent | `tenants`, `agents` |
| `alert_tags` | `T1027,T1059,perimetre:sigipes` | chaîne MITRE |
| `alert_iocs` | indicateurs **observés** | `alerts.iocs` |
| `alert_assets` | hôte, compte | `cible`, `cible_type` |

`alert_source_ref` porte l'idempotence : un rejeu ne duplique rien.
`alert_source_link` évite de réimplémenter l'explicabilité dans IRIS. Le panneau
des écarts en σ, la chaîne d'attaque et la fiche MITRE locale restent dans la
console, et IRIS y renvoie.

---

## 7. Valider une action depuis IRIS

Un seul point d'exécution, deux points d'entrée.

```
console NEXUS ────────────────────────► POST /analyst/execute/{id}
     ▲                                          │
     │ alert_source_link                        ▼
   IRIS ── l'analyste clique et revient ──► connecteurs ──► OPNsense / LDAP
```

Depuis IRIS, l'analyste suit le lien et arrive sur le détail de l'alerte, avec
les écarts en σ, la chaîne d'attaque, la commande exacte et le bouton
d'approbation. Il valide là où se trouve la justification.

Un bouton dans IRIS déclenchant un module reste possible techniquement. Il place
une action à fort impact, couper une machine ou suspendre une identité, derrière
un changement d'étiquette, loin de l'écran qui explique pourquoi. Pour une
plateforme dont l'argument est l'explicabilité, c'est le mauvais compromis.

---

## 8. Quand IRIS tombe

`_ouvrir_dossier()` n'appelle jamais IRIS depuis le chemin d'ingestion. Il écrit
dans `dossier_sortie` et rend la main. Un worker dépile.

C'est la discipline déjà appliquée à `_proposer_soar()` : un échec ne doit jamais
annuler l'alerte persistée. IRIS peut donc être arrêté pendant une mise à jour
sans qu'une alerte se perde, `/ingest` ne ralentit pas, et la console affiche
l'état réel de la synchronisation : en attente, poussée, ou en échec avec son
motif. Jamais un dossier supposé ouvert qui ne l'est pas.

---

## 9. Sauvegarde

Trois volumes à sauvegarder, en plus de la base NEXUS :

```bash
docker compose -f /opt/nexus-iris/docker-compose.yml exec db \
    pg_dump -U postgres iris_db | gzip > iris-$(date -I).sql.gz
docker exec nexus-postgres pg_dump -U nexus mattermost | gzip > mm-$(date -I).sql.gz
```

Les pièces jointes d'IRIS vivent dans le volume `server_data`.

---

## 10. Déploiement sans Internet

Sur un site coupé d'Internet, pré-charger les images depuis un poste raccordé :

```bash
for i in ghcr.io/dfir-iris/iriswebapp_app:v2.4.20 \
         ghcr.io/dfir-iris/iriswebapp_db:v2.4.20 \
         ghcr.io/dfir-iris/iriswebapp_nginx:v2.4.20 \
         rabbitmq:3-management-alpine \
         mattermost/mattermost-team-edition:9.11; do
    docker pull "$i"
done
docker save $(...) | gzip > pile-reponse.tar.gz
```

Puis `docker load < pile-reponse.tar.gz` sur l'hôte du SOC. La liste blanche de
sortie du cœur SOC, décrite au §2 de
[00-architecture-cenadi.md](00-architecture-cenadi.md), autorise ce
téléchargement quand le site est raccordé.
