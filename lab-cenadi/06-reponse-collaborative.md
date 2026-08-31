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

---

## 11. Phase 3 — journal de réalisation (28-29 août 2026)

Le **chaînon d'enquête est écrit, branché et éprouvé**. Ce qui manque au
28 août au soir, c'est l'image applicative d'IRIS : `iriswebapp_app` pèse
environ un gigaoctet et la liaison de la machine hôte n'a pas tenu le
téléchargement. Ce n'est pas un obstacle de conception — le code n'attend
qu'elle — mais il faut le dire plutôt que d'annoncer une phase terminée.

### 11.1 Ce qui tourne déjà

`Lot0_Socle/08_schema_dossiers.sql` est appliqué : la table `dossier_sortie` et
sa vue de santé existent, ainsi que `perimetre_iris`, la correspondance entre
un périmètre supervisé et un `customer` IRIS.

L'ouvrier tourne dans le cœur SOC, en fil d'exécution démarré avec l'API. Il a
été observé en fonctionnement : deux alertes réelles, produites par le pipeline
signé depuis KaliPrime, sont entrées en file et y attendent, avec un report
exponentiel, faute d'IRIS pour les recevoir. **C'est exactement le comportement
recherché**, et il est déjà prouvé.

### 11.2 Deux défauts trouvés en écrivant, et corrigés

**Une correspondance manquante n'est pas un refus.** La première version
traitait l'absence de `customer` IRIS comme un refus définitif : l'entrée
passait en `abandonne` et l'incident était perdu pour toujours. Or on n'avait
même pas contacté IRIS — c'est un défaut de configuration qui se corrige en une
minute. Le cas est désormais « indisponible », donc réessayable. La distinction
entre *l'outil a refusé ce contenu* et *on n'a pas pu essayer* est le cœur de
ce module ; s'y tromper coûte cher dans les deux sens.

**Le titre affichait le mauvais périmètre.** Le nom du périmètre ne circule pas
dans l'objet alerte : tous les dépôts sortaient marqués `[CENADI]`. Il est
maintenant lu en base. Un analyste qui ouvre sa file le matin cherche d'abord le
périmètre ; un titre qui les confond tous rend la file inutilisable.

### 11.3 Ce qu'il reste à faire quand l'image sera là

```bash
cd /opt/nexus-iris && docker compose up -d
```

Puis, dans IRIS : créer un `customer` par périmètre supervisé, relever leurs
identifiants numériques, et les inscrire dans la correspondance —

```sql
INSERT INTO perimetre_iris (tenant_id, customer_id, customer_nom)
VALUES ('11111111-…', 1, 'SIGIPES')
ON CONFLICT (tenant_id) DO UPDATE
   SET customer_id = EXCLUDED.customer_id, mis_a_jour_le = now();
```

Créer enfin un utilisateur de service NEXUS avec le droit d'écriture sur les
alertes et rien de plus, relever sa clé d'API, et la porter dans `.env` :

```
IRIS_URL=https://10.50.0.2:4443
IRIS_API_KEY=<clé du compte de service>
```

Les deux alertes en attente partiront d'elles-mêmes au cycle suivant : c'est
précisément ce que la file existe pour garantir.

### 11.4 Vérification

`bash lab-cenadi/scenarios/09-preuve-dossiers.sh` — arrête IRIS, produit des
alertes, le redémarre, et contrôle que rien n'a été perdu ni dupliqué.

Sans IRIS et sans réseau, `pytest Lot6_Tests/test_dossiers.py` couvre déjà la
règle de décision : report sur panne, abandon sur refus, plafond de tentatives,
idempotence. Sept contrôles. C'est délibéré — une logique qu'on ne peut vérifier
que les jours où l'outil tiers fonctionne n'est jamais vérifiée le jour où ça
compte.

### 11.5 Une version figée, pas « latest »

`.env.model` livré par IRIS positionne `APP_IMAGE_TAG=latest`, ce qui écrase la
version épinglée dans sa propre composition. Les trois étiquettes ont été
ramenées à `v2.4.20`. Une image `latest` change sous les pieds : c'est ce qui
casse une démonstration le matin où elle doit avoir lieu.

L'écoute a par ailleurs été restreinte au cœur SOC par
`docker-compose.override.yml` — la composition officielle publie son port sur
toutes les interfaces de l'hôte. Une extension, pas une copie : à la prochaine
version elle reste valable ou échoue bruyamment, elle ne peut pas diverger en
silence.

---

## 12. IRIS levé le 29 août 2026 — quatre obstacles, et ce qu'ils apprennent

L'image applicative est arrivée, IRIS tourne, et **les alertes NEXUS y sont
déposées de bout en bout**. Quatre obstacles ont dû être levés ; aucun n'était
dans la documentation d'IRIS, et trois auraient produit une panne silencieuse.

### 12.1 « latest » écrasait la version épinglée

`.env.model` livré par IRIS positionne `APP_IMAGE_TAG=latest`, ce qui prend le
pas sur la version figée de sa propre composition. Les trois étiquettes sont
ramenées à `v2.4.20`. Une image qui change sous les pieds est ce qui casse une
démonstration le matin où elle doit avoir lieu.

### 12.2 Compose fusionne les ports, il ne les remplace pas

L'override qui restreint l'écoute au cœur SOC **s'ajoutait** à la publication
d'origine au lieu de la remplacer : le port restait ouvert sur toutes les
interfaces, et les deux entrées se disputaient le même port. Le conteneur
bouclait sur « address already in use » pendant qu'on croyait avoir restreint
l'accès — le pire des cas, une protection qui n'en est pas une et une panne qui
ne dit pas pourquoi.

La correction tient en une étiquette : `ports: !override`. Vérifier ensuite avec
`docker compose config`, qui montre la définition réellement appliquée.

### 12.3 Un `umask` hérité rendait le certificat illisible

Le dépôt avait été cloné depuis un shell où un `umask 077` traînait : le
répertoire des certificats sortait en 700, et nginx, qui tourne en `www-data`
dans le conteneur, ne pouvait pas le lire. Le certificat est passé en 644 ; la
clé privée reste en 640, propriété `root:www-data`, donc lisible par le
conteneur seul et non par tout le monde.

### 12.4 Écrire des alertes ne suffit pas : il faut être habilité au périmètre

Le compte de service avait bien `alerts_write`, et IRIS répondait pourtant
`User not entitled to create alerts for the client`. IRIS cloisonne à **deux**
niveaux : les droits fonctionnels d'un côté, l'habilitation par `customer` de
l'autre. Il faut les deux.

C'est une bonne nouvelle pour l'architecture qu'on défend : un compte peut être
autorisé à déposer des alertes sans pouvoir en déposer pour n'importe quel
périmètre.

### 12.5 Le compte de service, et son périmètre exact

Groupe « NEXUS SOC - depot alertes », trois droits et rien d'autre :

| Droit | Valeur | Ce qu'il permet |
|---|---|---|
| `standard_user` | 1 | ouvrir une session d'API |
| `alerts_read` | 4 | relire ses propres dépôts (idempotence) |
| `alerts_write` | 8 | déposer une alerte |

Il ne peut ni administrer IRIS, ni supprimer une alerte, ni toucher aux
dossiers. **L'escalade d'une alerte en dossier reste un geste d'analyste** —
c'est la ligne du projet, et elle est ici garantie par une permission absente,
pas par une convention.

Habilitations : les trois périmètres supervisés, et eux seuls.

### 12.6 Correspondance des périmètres, lue et non devinée

| Périmètre NEXUS | `customer` IRIS |
|---|---|
| SIGIPES | 4 |
| ANTILOPE | 2 |
| Réseau/LAN CENADI | 3 |

Ces identifiants sont propres à cette instance. Ils vivent dans la table
`perimetre_iris`, jamais dans le code : une réinstallation d'IRIS les
renumérote, et un connecteur qui les aurait figés déposerait les incidents d'un
périmètre sous le nom d'un autre.

### 12.7 Ce que les premiers dépôts montrent

Cinq alertes réelles sont dans IRIS, chacune avec son identifiant, sa gravité
résolue **par nom**, son périmètre et ses étiquettes MITRE.

Les deux plus anciennes portent encore le titre `[CENADI]` au lieu du périmètre :
elles ont été mises en file avant le correctif du §11.2, et leur charge était
déjà figée. C'est exactement le comportement voulu — **rejouer un envoi ne
reconstruit pas un dossier avec des données qui ont bougé depuis** — et on le
constate ici sans l'avoir cherché.

---

## 13. Phase 4 — discussion d'incident (29 août 2026)

### 13.1 Une veille plutôt qu'un module IRIS — et pourquoi

Le plan prévoyait un module IRIS branché sur `on_postload_alert_update`. IRIS
n'expose ses accroches qu'à des modules Python installés **dans son
conteneur** : il aurait fallu empaqueter du code au format de leur cadriciel, le
réinstaller à chaque montée de version, et le déboguer à travers leur système de
tâches asynchrones.

La veille interroge donc IRIS depuis NEXUS, toutes les trente secondes. Trois
raisons, dans cet ordre :

1. **Le code reste dans notre dépôt**, donc testable sans IRIS — c'est le
   principe appliqué partout ailleurs dans ce projet.
2. **Une montée de version d'IRIS ne casse rien.** Un module tiers mal reconnu
   après une mise à jour échouerait en silence, et personne ne s'apercevrait que
   les canaux ne s'ouvrent plus.
3. **Le délai est sans conséquence ici.** Une escalade est un geste humain
   délibéré ; que le canal s'ouvre trente secondes plus tard ne change rien à la
   conduite de l'incident. Ce serait différent pour une mesure de blocage.

Le compromis assumé : un appel toutes les trente secondes. Peu cher payé pour ne
pas dépendre du cadriciel d'un tiers.

### 13.2 La règle qui structure tout le module

**Une panne de Mattermost ne bloque rien.** Ni l'escalade, ni le dossier, ni la
détection, ni la réponse. `publier()` renvoie `False` au lieu de lever ; aucun
appel de ce module ne se trouve sur un chemin dont dépend la détection.

Un SOC qui s'arrête parce que sa messagerie est en panne a confondu
l'accessoire et l'essentiel.

Mais l'échec doit **se voir** : une entrée qu'on n'a pas su ouvrir passe à
`echec` après cinq tentatives, avec son motif. Sans cela, la cellule attendrait
une notification qui ne viendra jamais, en prenant le silence pour une absence
d'incident.

### 13.3 Ce que le canal contient

Nom : `incident-AAAAMMJJ-<8 caractères de la référence>`. La date en clair pour
retrouver un canal des mois plus tard sans recherche ; le fragment de référence
pour qu'aucun incident n'en écrase un autre le même jour. Canal **privé** : un
incident n'a pas à être lisible par toute l'administration avant d'être
qualifié.

Le message d'ouverture porte le périmètre, l'entité, le risque mesuré, les
écarts rédigés, les techniques MITRE **citées dans les motifs** — jamais
inventées — et **deux liens** : le dossier d'enquête, et l'explicabilité dans
NEXUS. Le second est celui qui compte : sans lui, on subit une conclusion au
lieu de pouvoir la contester.

### 13.4 Une correction au passage

`docker-compose.reponse.yml` publiait Mattermost sur `127.0.0.1:8065` sous un
commentaire annonçant que « la zone Admin y accède par la matrice de flux ». La
boucle locale n'est joignable que depuis l'hôte : le RSSI, qui travaille depuis
vm-rssi, n'y aurait jamais accédé. Liaison corrigée en `10.50.0.2:8065`. Ce
n'est pas une ouverture — le pare-feu reste le seul chemin, et il ne l'ouvre
qu'à la zone d'administration.

La composition référençait par ailleurs un réseau `nexus` qui n'existait pas :
Mattermost n'aurait pas trouvé `nexus-postgres`. Réseau créé, base rattachée.

### 13.5 Le robot, et son périmètre

Compte de type **robot**, pas compte ordinaire : ses publications sont
visiblement signées « BOT ». Personne ne confond un résumé automatique avec
l'avis d'un collègue — ce qui compte le jour où la conversation servira à
justifier une décision.

Il publie et crée des canaux. **Il ne lit rien.** La discussion appartient aux
humains ; une plateforme qui interpréterait les échanges d'une cellule de crise
sortirait de son rôle.

### 13.6 Le champ `id` d'une réponse d'erreur — deux fois le même piège

Mattermost répond à ses erreurs avec un objet qui porte, lui aussi, un champ
`id` — par exemple `app.team.get_by_name.missing.app_error`. Lire ce champ sans
précaution fait conclure « l'objet existe » sur un 404.

Le piège s'est refermé deux fois dans le même script :

1. sur la création du compte administrateur, où l'échec s'est affiché comme un
   succès pendant que l'inscription par courriel était désactivée ;
2. sur la recherche de l'équipe, où un 404 a été pris pour « équipe déjà
   présente » — l'équipe n'a donc jamais été créée, et la veille a échoué
   ensuite avec un message qui ne désignait pas la cause.

Deux règles en sont tirées, applicables à tout appel d'API de ce projet :

- **Ne jamais conclure au succès sur la PRÉSENCE d'un champ.** Demander au
  serveur l'état qui nous intéresse — « ce compte existe-t-il ? » — plutôt que
  d'interpréter la forme d'une réponse.
- **Valider la forme des identifiants.** Un identifiant Mattermost fait
  26 caractères alphanumériques ; un identifiant d'erreur contient toujours des
  points. Le script exige désormais la première forme.

C'est le même défaut que sur le filtre `source_reference` d'IRIS (§12), et que
sur la relecture des alias OPNsense : **un service qui ne comprend pas la
question ne répond pas toujours par une erreur.** Il répond autre chose, et
c'est à l'appelant de s'en apercevoir.
