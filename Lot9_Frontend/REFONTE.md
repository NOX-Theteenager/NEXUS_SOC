# Refonte du frontend — note de livraison

Réponse au brief [`designexus.md`](../designexus.md), à partir de la maquette
« NEXUS SOC — Maquette refonte ». Les six pages ont été réécrites, pas retouchées.

Livrable §10 attendu par le brief : cette note couvre le point 5, « les choix qui
s'écartent du brief, avec leur motif ».

---

## 1. Ce qui a été livré

| Fichier | État | Contenu |
|---|---|---|
| `login.html` | réécrit | Sous-titre corrigé, échec réseau distingué de l'échec d'identifiants, bascule d'affichage du mot de passe, sonde de disponibilité de l'API |
| `portail.html` | réécrit | Mobile d'abord, score + tendance 14 jours, Analyse NEXUS, alertes en langage clair, notifications hiérarchisées, rapport en iframe sandboxée, FR/EN en direct |
| `console.html` | réécrit | 8 sections, détail d'alerte avec chaîne MITRE, parcours d'enrôlement complet, supervision SVG, dérive IA, journal d'audit SOAR |
| `docs.html` | réécrit | 9 sections, sommaire collant, recherche locale, coloration et copie sans CDN |
| `contact.html` | réécrit | Formulaire interne branché sur l'API, file locale hors ligne |
| `offline.html` | réécrit | Autonomie totale conservée, reprise explicite |
| `fonts/` | **nouveau** | Fraunces, Manrope, JetBrains Mono auto-hébergés (WOFF2, 380 Ko) |
| `js/api.js` | étendu | Journal SOAR, demande de périmètre, QR, archive, import CSV, téléchargements authentifiés |
| `sw.js` | mis à jour | `nexus-soc-v4`, polices précachées, précache tolérant aux 404 |

### Dettes de design du brief §7

| # | Dette | État |
|---|---|---|
| 1 | Polices chargées depuis un service distant | **corrigée** — auto-hébergées et précachées |
| 2 | Sous-titre `SOCaaS · Cameroun` | **corrigée** — `CENADI · Plateforme souveraine` |
| 3 | Endpoints `/provision/*` sans interface | **corrigée** — parcours en 3 étapes, 4 voies de déploiement |
| 4 | `raisons` et `mitre` jamais affichés | **corrigée** — chaîne colorée par tactique + raisons brutes |
| 5 | `soar_audit` jamais affichée | **corrigée** — journal filtrable (a nécessité un endpoint, voir §3) |
| 6 | `#sup-charts` vide | **corrigée** — graphiques SVG produits sur place |
| 7 | `/monitor/drift` sans écran | **corrigée** — l'endpoint n'existait pas non plus, voir §3 |
| 8 | Manifeste « Portail client DSI » | **corrigée** — « Portail de périmètre » |
| 9 | Modales sans piège de focus ni Échap | **corrigée** — les deux, sur console et portail |
| 10 | Composants dupliqués | **corrigée** — badge, champ, KPI, squelette, table unifiés |

---

## 1 bis. Présence des agents — statut dynamique

`agents.statut` n'était écrit que par `/ingest`, qui le passait à `actif`. **Rien
ne le repassait jamais à `hors_ligne`** : un poste éteint restait affiché actif
indéfiniment. En base, des agents vus pour la dernière fois 20 jours plus tôt
étaient toujours marqués `actif`.

Le statut est désormais **calculé à la lecture** à partir de `vu_le`
(`agent_statut_sql`, `Lot7_Console_Fournisseur/admin_api.py`) :

| Condition | Statut effectif |
|---|---|
| `statut = 'isole'` en base | `isole` — décision SOAR, prime sur le battement |
| dernier battement < `AGENT_STALE_SECONDS` (120 s par défaut) | `actif` |
| sinon, ou jamais vu | `hors_ligne` |

Pas de tâche de fond, pas de dérive d'horloge, et un résultat correct même après
un arrêt du serveur. Allumer une VM la fait passer à `actif` au premier lot
ingéré ; l'éteindre la fait basculer `hors_ligne` après le délai de tolérance.
Le seuil se règle par `AGENT_STALE_SECONDS` et est renvoyé aux interfaces
(`stale_after_s`) pour qu'elles annoncent la règle qu'elles appliquent.

Répercuté sur `/admin/agents`, `/portal/agents`, `/analyst/dashboard`
(`agents_online`) et `/portal/summary` (`agents_active`). Les deux écrans
affichent en plus l'ancienneté du battement (« il y a 4 s », « il y a 20 j »).

Deux corrections liées :

- `/ingest` ne repasse plus un agent `isole` à `actif`. La décision d'isolement
  d'un analyste ne peut plus être annulée par l'arrivée d'un lot.
- Un poste isolé ne peut plus ingérer du tout (`_verify_ingest` le refuse déjà) :
  son dernier battement est figé à l'instant de l'isolation. La console le
  signale par « ingestion coupée » pour qu'on ne lise pas une panne.

---

## 2. Écarts de maquette — levés

Les trois écarts initialement assumés ne venaient pas d'une donnée manquante mais
d'une **donnée produite puis perdue en chemin**. Ils sont levés.

### 2.1 Décomposition du score — rétablie

`score_userday()` et `score_network()` calculaient déjà l'écart σ de chaque
feature, puis le formataient dans une phrase et jetaient la valeur numérique.
`raisons` est désormais une liste d'objets :

```json
[{"feature":"volume_donnees_exportees","label":"volume de données exportées",
  "sigma":541.4,"valeur":940000.0,"texte":"volume de données exportées anormalement élevé (541.4σ)"}]
```

Le champ `texte` est conservé : les consommateurs existants (rapport HTML,
notifications) continuent de fonctionner sans modification, et les alertes déjà
en base — simples chaînes — restent lisibles, le frontend normalisant les deux
formes.

Le Modèle 1 n'avait **aucune** explicabilité : ses statistiques de référence
n'étaient pas embarquées dans le bundle. Elles sont récupérées depuis son
`StandardScaler` (`mean_` / `scale_`), qui porte la même statistique apprise sur
les mêmes données. Les alertes réseau ont donc désormais leurs raisons chiffrées.

Une **seconde** décomposition, additive celle-là, accompagne les alertes de
corrélation : `alerts.score_parts` publie les termes réels de la somme
(`socle 45`, `12 × tactiques`, `C2 +10`, `Impact +12`, `hors heures +6`). La
console la trace en barres. Les modèles d'anomalie, dont le score est une
distance normalisée et non une somme, n'en reçoivent pas — on ne fabrique pas de
pondérations pour eux, l'écran s'en tient à l'échelle et aux seuils.

### 2.2 Chaîne d'attaque horodatée — rétablie

`correlation_engine_v2.py` construisait une liste `chaine` complète (heure,
tactique, technique, preuve) mais restait un **script autonome, jamais importé
par `run.py`**. Il est maintenant appelé à chaque lot ingéré.

Une chaîne s'étale sur plusieurs minutes alors qu'un lot ne couvre que
l'intervalle de collecte : le service maintient donc une **fenêtre glissante par
hôte** (`CORR_WINDOW_MIN`, 30 min), bornée en temps et en nombre
(`CORR_MAX_EVENTS_PER_HOST`, 2000) pour que la mémoire reste maîtrisée. Le
résultat est persisté dans `alerts.chaine`.

Le collecteur n'envoyait que des vecteurs de features — de quoi scorer, pas de
quoi corréler. Il émet désormais aussi les **événements bruts** que le moteur sait
lire : processus (`/proc`), connexions TCP établies (`/proc/net/tcp`), fichiers
modifiés dans `NEXUS_WATCH_DIRS`. Le premier passage mémorise l'état sans rien
signaler : sinon le démarrage du collecteur produirait une fausse modification
massive et déclencherait à tort la règle rançongiciel.

Les deux qualités de donnée ne sont jamais confondues à l'écran : déroulé
horodaté avec preuves quand la corrélation en a produit un, simple liste ordonnée
par phase ATT&CK sinon — en le disant.

### 2.3 Analyse NEXUS — produite par le serveur

`LLMAnalyst` (Lot 5) était écrit, bilingue, testé, et joignable par aucun
endpoint. `GET /portal/alerts/{id}/explain?lang=fr|en` l'expose. Un seul texte
fait désormais autorité dans le portail, le rapport et les notifications, et le
mode LLM optionnel (`ANALYST_MODE=llm` + `LLM_API_URL`) devient accessible sans
toucher au frontend, avec repli automatique sur le template.

Le portail garde une composition locale en repli : si l'endpoint est
indisponible, mieux vaut une phrase construite sur place qu'un encart vide. La
mention sous le paragraphe distingue les deux (`mode template` / `mode local`).

### 2.4 Tendance du score reconstruite côté client

Toujours d'actualité. `/portal/summary` ne renvoie qu'un instantané ; la courbe
14 jours est calculée depuis `/portal/alerts` (`100 − risque maximum du jour`).
Donnée réelle issue d'une seule source, mais une série historisée dans
l'hypertable `metrics` serait plus juste et plus stable.

### 2.5 Chiffres de la maquette non repris

`p95 42 ms`, `uptime 99,98 %`, `12 400 msg/min` étaient des valeurs
d'illustration. Les cartes de santé affichent ce que `/health/detailed` renvoie
réellement, et rien d'autre.

---

## 2 bis. Intégrité des lots — signature réellement vérifiée

`_verify_ingest` ne vérifiait que la **présence et le format** du header
`X-Signature`, jamais la signature : la base ne conserve que l'empreinte de la
clé HMAC, ce qui interdit tout recalcul. Le contexte projet donnait pourtant R5
pour résolu.

La clé n'est plus stockée du tout, elle est **dérivée** :

```
hmac_key = HMAC-SHA256(NEXUS_HMAC_MASTER, "<agent_id>:<hmac_epoch>")
```

Le serveur la recalcule à chaque lot et compare en temps constant ; rien de
réversible ne dort en base. `hmac_epoch` s'incrémente à chaque rotation, ce qui
invalide l'ancienne clé sans changer l'identité de l'agent.

**Migration sans casse.** `agents.hmac_scheme` vaut `legacy` pour les agents
enrôlés avant ce changement : leur clé était aléatoire et n'est pas
recalculable. Ils continuent d'être acceptés, avec un avertissement journalisé
une fois par agent, et la console les signale par « signature non vérifiée ».
Une rotation de clé les bascule en `derived`. Une fois le parc migré — la vue
`v_agents_hmac_a_migrer` le dit — poser `INGEST_STRICT_HMAC=1` pour refuser tout
lot non vérifiable.

Vérifié : signature valide acceptée (200), signature forgée rejetée (401).

---

## 3. Modifications hors frontend rendues nécessaires

Trois endpoints décrits par le brief comme existants n'existaient pas. Sans eux,
les écrans correspondants n'auraient été que des maquettes.

| Endpoint | Fichier | Motif |
|---|---|---|
| `GET /analyst/soar-audit` | `Lot7_Console_Fournisseur/admin_api.py` | Dette n°5 : `soar_audit` peuplée, aucune lecture exposée. Filtres périmètre / impact / statut + facettes |
| `GET /monitor/drift` | idem, routeur `monitor_router` | Dette n°7 : le calcul vit dans `Lot3_IA/model_monitor.py`, aucun endpoint ne l'appelait |
| `POST /contact/perimetre-request` | idem, routeur `contact_router` | `contact.html` postait vers un endpoint inexistant et retombait sur `localStorage` |

Deux ajustements complémentaires :

- **`GET /auth/me`** renvoie désormais `tenant_nom`, `tenant_type` et
  `tenant_criticite`. Le JWT ne porte que `tenant_id` : le portail ne pouvait pas
  titrer ses écrans du nom du périmètre sans appeler `/admin/*`, réservé aux rôles
  plateforme. Lecture en échec ⇒ libellé neutre, jamais un blocage.
- **`_rapport_html()`** (`Lot1_Agent_Go/scoring-service_app.py`) produit maintenant
  un document autonome complet — `<!DOCTYPE>`, fond blanc, `@page` 18 mm, `@media
  print`, polices système, chaîne MITRE ordonnée, aucune ressource externe, aucun
  script. L'ancienne version était un fragment `<article>` de 738 caractères.
  Les rapports déjà en base gardent leur ancien format ; les nouveaux incidents
  utilisent le nouveau.

**Migration à appliquer** :

```bash
psql -U nexus -d nexus_soc -f Lot7_Console_Fournisseur/02_schema_contact.sql
```

Sans elle, `POST /contact/perimetre-request` répond 503 avec le message
d'instruction, et le formulaire l'affiche tel quel.

**Dépendance activée** : `qrcode[pil]` passe de commentaire à dépendance réelle
dans `requirements.txt`, la console exposant désormais l'onglet QR. Sans elle
l'endpoint répond quand même, sans image, et la console affiche la commande en
clair à recopier.

---

## 4. Écart assumé par rapport au brief §2.1

Le brief impose « CSS et JavaScript en ligne, seule exception `js/api.js` ».
S'y ajoute **`fonts/fonts.css`**, chargé par les cinq pages applicatives.

Motif : la dette n°1 impose d'auto-héberger trois familles en WOFF2. Dupliquer
huit déclarations `@font-face` dans chaque page interdirait toute correction
groupée et gonflerait chaque fichier. Un fichier de polices est un actif statique,
pas une chaîne d'outils : il ne réintroduit ni build, ni bundler, ni
`node_modules`. `offline.html` ne le charge pas et conserve son autonomie totale.

---

## 5. Vérifications effectuées

Pile réelle (TimescaleDB, Kafka, Wazuh, uvicorn) et données de démonstration.

- **14 états de page** pilotés dans Chrome : aucune erreur console, aucune requête
  échouée, aucun débordement horizontal, les trois polices chargées partout.
- **Aucune ressource distante** : plus une seule référence à un service de polices
  ou à un CDN dans les pages livrées.
- **Parcours d'enrôlement** de bout en bout : périmètre → jeton
  (`POST /provision/token`) → commande shell, QR code PNG rendu, archive hors
  ligne, import CSV avec rejet des doublons, hôtes vides et OS non pris en charge.
- **Accessibilité des modales** : focus piégé après 12 tabulations, Échap ferme,
  focus rendu à l'élément d'origine.
- **Bascule FR/EN** du portail en direct, contenus produits en JS compris.
- **Rapport HTML** : `<!DOCTYPE>`, `@media print`, zéro script, zéro URL externe,
  chaîne MITRE réordonnée par phase.
- **Poids** : login 16 Ko · contact 18 Ko · docs 55 Ko · portail 59 Ko ·
  console 116 Ko — tous sous les 150 Ko hors polices (380 Ko, précachées).
- **Suite existante** : `pytest Lot6_Tests/` — 14 tests, 14 passés.

### Limite connue

Le jeu de démonstration contient des alertes de type « Fraude interne » dont
l'entité est un hôte (`hote_SRV-APP-GOV-01`). La mise en langage clair parle donc
d'« un compte » à propos d'une machine. C'est une incohérence du jeu de données,
pas du rendu : les gabarits sont indexés sur `alerts.type`.

---

## 5 bis. Connexion PostgreSQL laissée « idle in transaction »

Découvert en appliquant la migration : `ALTER TABLE agents` restait bloqué
indéfiniment, et comme un `ALTER` en attente fait la queue, **toute requête
suivante sur `agents` se bloquait derrière lui** — `/ingest` compris.

Cause : `STATE["db"]` est une connexion persistante ouverte sans autocommit.
psycopg2 démarre alors une transaction au premier `SELECT` et ne la referme
jamais. Or trois chemins sont en lecture seule et ne committent pas :
`_verify_ingest`, `_alerte_dupliquee`, `/health/detailed`. Le service restait
donc en permanence `idle in transaction`, ce qui :

- conserve un verrou `ACCESS SHARE` sur les tables lues, bloquant tout DDL ;
- retient un snapshot et prive l'autovacuum de son travail sur les tables chaudes.

Correctif : `STATE["db"].autocommit = True` à l'ouverture. Chaque écriture du
service étant une instruction unique suivie d'un `commit()`, la sémantique est
strictement identique ; les `commit()` et `rollback()` existants deviennent des
non-opérations inoffensives.

Vérifié : après le même appel `/ingest`, la session corrigée ne détient plus
aucun verrou sur `agents`, là où l'ancienne conservait un `AccessShareLock`.

**Conséquence d'exploitation** : appliquer une migration DDL pendant que le
service tourne échouait silencieusement par blocage. Redémarrer `uvicorn` avant
toute migration reste de bonne pratique, mais ce n'est plus une obligation.

---

## 5 ter. Reprise sur les alertes existantes

Trois corrections rendent les écrans exploitables sur les 45 alertes antérieures
à la refonte.

### Identifiants ATT&CK non résolus — corrigé

Deux formats coexistent en base : `« T1005, T1059, T1071 »` (corrélation) et
`« T1071 · C2 »` (scoring, identifiant suivi de sa tactique). Le parseur
découpait sur la virgule : **toutes les alertes existantes** tombaient donc en
« technique non répertoriée ». Les identifiants sont maintenant extraits par
motif (`T\d{4}(\.\d{3})?`), ce qui couvre les deux formes et les
sous-techniques. Corrigé dans la console, le portail et le rapport HTML.

### Écarts σ récupérés — `05_backfill_explicabilite.sql`

Les modèles calculaient l'écart σ de chaque variable puis le formataient dans
une phrase : `« volume de données exportées anormalement élevé (13.1σ) »`. La
valeur numérique était donc déjà là, sérialisée dans le texte. La migration la
récupère : chaque raison devient `{label, sigma, texte}`, où `texte` est la
chaîne d'origine **inchangée** — rien n'est perdu et les consommateurs qui
attendent une phrase continuent de fonctionner.

Résultat : 29 alertes reprises, 86 raisons structurées dont 80 portent un σ. Les
6 restantes sont des raisons rédigées à la main dans le jeu de démonstration,
sans écart chiffré. Migration idempotente, vérifiée par une seconde exécution.

Un écart aberrant (variance quasi nulle sur une variable → σ à cinq chiffres)
écraserait les autres barres en échelle linéaire : au-delà d'un rapport de 100,
l'affichage bascule en logarithmique et l'annonce sous le bloc.

### Chaîne d'attaque — non reconstituable, et c'est assumé

Les événements bruts qui produiraient une chronologie n'ont jamais été stockés :
seule la liste des techniques a survécu. Inventer des horodatages et des preuves
sur l'écran qui porte l'argument d'explicabilité du projet serait exactement ce
que ce travail s'interdit. `alerts.chaine` et `alerts.score_parts` restent donc
NULL sur l'existant, et l'interface l'énonce : *« alerte issue du scoring d'un
événement isolé : pas de déroulé horodaté, la liste est ordonnée par phase
ATT&CK »*.

Pour disposer d'une chaîne réelle en démonstration, le collecteur sait en
produire une à la demande :

```bash
sudo -E python3 /opt/nexus-agent/nexus_collector.py --simulate chaine
```

Six événements bruts — pièce jointe ouverte, script obfusqué, création de compte,
collecte dans les dossiers de solde, énumération système, canal C2 — traversent
`/ingest` signés, et c'est le moteur de corrélation qui reconstitue l'incident.
Vérifié contre le serveur en production : 6 étapes horodatées, 3 termes de score.
Rien n'est écrit directement en base.

---

## 5 quater. Dérive des modèles — fenêtre réglable

Le PSI compare **deux fenêtres consécutives de même durée** : la période
courante et celle qui la précède. Si l'une des deux est vide, il n'est pas
calculable — ce n'est pas une panne, c'est la définition de l'indicateur.

L'historique du parc étant irrégulier (campagne de démonstration du 22 au 29
juillet, puis activité réelle à partir du 9 août), la fenêtre de 7 jours tombait
pile dans le creux : M1 n'avait plus rien en courant, M2 n'avait rien en
référence. Les deux modèles s'affichaient donc « non mesurable », correctement
mais sans recours puisque `days=7` était figé dans le code.

Le panneau porte maintenant un sélecteur **7 j / 14 j / 30 j**, présent aussi sur
les branches dégradées (erreur d'appel, module absent, chargement). Sur les
données actuelles :

| Fenêtre | M1 réf / cour. | M2 réf / cour. | PSI |
|---|---|---|---|
| 7 j | 2 / 0 | 0 / 11 | non calculable |
| **14 j** | **15 / 2** | **17 / 11** | **0,745 · 0,650** |
| 30 j | 0 / 17 | 0 / 28 | non calculable |

**Garde-fou ajouté.** Un PSI sur 2 alertes est arithmétiquement juste et
statistiquement muet : le découpage en déciles n'a plus de sens. En dessous de
30 observations du côté le moins fourni, la valeur reste affichée mais l'étiquette
passe à « indicatif » (ambre) au lieu de « ré-entraînement requis » (rouge), avec
la taille d'échantillon en clair. Sans ce garde-fou, l'écran recommandait un
ré-entraînement sur la foi de deux alertes.

---

## 5 quinquies. Reprise de la maquette — repli hors ligne et rapport

Deux écarts restants avec la maquette de refonte, tous deux sur des écrans qui
fonctionnent précisément quand le reste ne fonctionne plus.

### Repli hors ligne — liste réellement ouvrable

La liste « consultable depuis le cache » était écrite en dur. Elle annonçait
« documentation · disponible » même lorsque `docs.html` n'avait jamais été mis
en cache, et aucune entrée n'était cliquable : on nommait des pages sans pouvoir
les ouvrir.

`offline.html` interroge maintenant l'API Cache et ne rend en lien que ce qui
s'ouvrira vraiment ; le reste passe en « pas en cache ». L'API Cache est locale,
l'autonomie de la page est intacte — aucune requête réseau, conformément à sa
raison d'être. Sans API Cache (navigateur ancien, contexte non sécurisé), la
liste reste affichée mais non cliquable, plutôt que de proposer des liens morts.

Le service worker passe en **v5** : cette page n'étant jamais servie depuis le
réseau, l'ancienne copie précachée serait restée affichée indéfiniment.

### Rapport d'incident — bilingue et scellé

Le rapport était le seul écran resté monolingue alors que tout le portail bascule
FR/EN. C'est pourtant celui qui sort de la plateforme : courriel, impression,
archivage, transmission à un partenaire.

`_rapport_html(..., lang=)` produit les deux versions. **La version française
reste figée en base au moment de l'incident** — c'est elle qui fait foi ; la
version anglaise est rendue à la demande depuis les mêmes données, jamais
traduite depuis le HTML, ce qui produirait deux documents dont les empreintes ne
diraient rien l'une de l'autre.

**Sceau d'intégrité.** Une empreinte ne peut pas porter sur le document qui la
contient. Elle est donc calculée sur le document privé de son bloc d'intégrité,
chaque ligne de ce bloc portant le marqueur `NEXUS-INTEGRITY` — ce qu'un lecteur
reproduit à l'octet près avec des outils standards et sans réseau :

```bash
grep -v NEXUS-INTEGRITY rapport-nexussoc-a7f3c91d.html | sha256sum
```

Vérifié : empreinte reproduite en FR et en EN, et divergente dès qu'un seul
caractère du corps est modifié.

S'y ajoute un scellé HMAC-SHA256 sur les mêmes octets. Il est présenté pour ce
qu'il est — **vérifiable par le SOC détenteur du secret de plateforme**, pas par
un tiers. Une signature Ed25519 serait publiquement vérifiable, mais aucune clé
asymétrique n'existe dans le projet et `cryptography` n'est pas une dépendance :
l'annoncer serait promettre une garantie inexistante. Si `NEXUS_HMAC_MASTER`
n'est pas configuré, le rapport le dit et l'empreinte reste vérifiable.

### Deux défauts trouvés en chemin

**`etapes` n'était jamais défini dans la branche corrélée.** Toute alerte
porteuse d'une chaîne horodatée levait un `NameError` à la génération du rapport
— silencieusement, l'appelant se contentant d'imprimer « notification non
créée ». Le cas ne s'était encore jamais produit en base : aucune alerte
existante ne porte de `chaine`. Il se serait déclenché à la première corrélation
réelle, c'est-à-dire à la première démonstration.

**Le facteur principal affichait un dictionnaire Python.** Depuis la reprise des
raisons en objets `{label, sigma, texte}`, `str(raisons[0])` produisait
`{'label': …, 'sigma': …}` en toutes lettres dans le rapport diffusé. Le texte
est désormais extrait explicitement.

---

## 5 sexies. Données affichées sans avoir été mesurées

Signalé par l'opérateur sur le portail : « j'ai l'impression d'avoir des données
factices ». L'impression était juste, et le défaut se répétait à trois endroits.

### La règle, désormais explicite

> **Une absence de mesure ne se dessine jamais comme une mesure.**
> Pas de zéro par défaut sur une grandeur observée, pas de segment qui franchit
> une interruption, pas d'axe qui présente comme régulier un échantillonnage qui
> ne l'est pas. Quand la donnée manque, l'écran le dit et la courbe s'arrête.

Toute nouvelle série ajoutée à la plateforme doit passer ces trois questions :
que vaut un intervalle sans donnée ? le tracé le distingue-t-il d'une valeur
stable ? l'axe est-il proportionnel au temps ou à l'index ?

### 1. Score de sécurité du portail — jours inventés

`dailyScores()` appliquait « score du jour = 100 − pire risque du jour ». Un jour
sans alerte valait donc **100**, y compris les jours où la plateforme ne
collectait rien. Sur le périmètre SIGIPES, mesuré **3 jours sur 14**, l'écran
affichait quatorze jours dont onze n'avaient jamais été observés — et une
tendance calculée par rapport à l'un d'eux.

Le calcul passe côté serveur (`GET /portal/score-history`), qui croise `alerts`
et `metrics`. Un jour sans télémétrie revient avec `score: null`, la courbe s'y
interrompt, les jours aveugles sont grisés et dénombrés en légende. La tendance
se compare au dernier jour réellement mesuré, ou annonce « pas de comparaison ».

Ceci clôt la dette §2.4 (« historiser le score plutôt que le recalculer côté
client »).

### 2. `/portal/summary` — « non résolue » n'est pas « ouverte »

Le compteur d'incidents et le score du jour filtraient sur `statut != 'resolue'`,
englobant donc les faux positifs écartés par un analyste **et** les alertes
agrégées. Après l'arbitrage du §7, SIGIPES annonçait **17 incidents ouverts pour
3 réels**. Le filtre exclut désormais explicitement `resolue`, `faux_positif` et
`agregee`.

### 3. Graphiques de supervision — abscisse par index

`svgChart()` positionnait les points sur leur **index**, pas sur leur
horodatage. Une coupure de collecte occupait la même largeur qu'un pas d'une
minute, et la ligne la traversait sans rupture, sous un axe annonçant « il y a
24 h → maintenant ».

Mesure sur les dernières 24 h : **423 minutes de données sur 1440**, six
interruptions, la plus longue de 5 h 38. L'écran montrait une série continue.

L'axe est maintenant temporel, les interruptions rompent le tracé, sont grisées
proportionnellement à leur durée et annoncées sous le graphique. Vérifié : une
coupure de 338 minutes sur 853 occupe 40 % de la largeur.

---

## 6. Points ouverts pour la suite

1. **Historiser le score de sécurité** dans l'hypertable `metrics` plutôt que de
   le recalculer côté client à chaque chargement (§2.4).
2. **Raccorder les connecteurs SOAR réels** — gel de compte AD/LDAP, isolation
   d'hôte, blocage IP périmétrique. L'interface annonce déjà impact et
   réversibilité avant confirmation : elle est prête à piloter de vraies actions.
3. **Achever la migration HMAC** : faire tourner la clé des agents encore en
   schéma `legacy` (`SELECT * FROM v_agents_hmac_a_migrer`), puis poser
   `INGEST_STRICT_HMAC=1` pour refuser tout lot non vérifiable.
4. **Poser l'unicité du parc** une fois les doublons arbitrés (§7).
5. **Séparer `NEXUS_HMAC_MASTER` de `JWT_SECRET`** : la dérivation retombe
   aujourd'hui sur le second par compatibilité, mais compromettre l'un ne devrait
   pas livrer l'autre.

---

## 7. Doublons du parc — arbitrage requis

`SRV-ANTILOPE-01` et `SRV-SIGIPES-01` existent chacun en deux exemplaires : une
ligne du jeu de démonstration et une ligne réellement enrôlée. Rien n'empêchait
d'enrôler deux fois le même hôte.

La contrainte `UNIQUE (tenant_id, hostname)` est écrite dans
`Lot0_Socle/04_schema_explicabilite.sql` mais **volontairement non posée** tant
que des doublons subsistent : chaque ligne porte un jeton et un historique, le
choix de celle à conserver est une décision d'exploitation, pas quelque chose
qu'une migration doit trancher seule.

```sql
-- Voir les doublons et laquelle garder a priori (plus_recent = TRUE)
SELECT * FROM v_agents_doublons;

-- Après arbitrage, supprimer la ligne obsolète puis relancer la migration
DELETE FROM agents WHERE id = '<uuid de la ligne à retirer>';
\i Lot0_Socle/04_schema_explicabilite.sql
```

---

## 8. Appliquer les migrations

Le poste de développement n'a pas de client `psql` local ; la base tourne dans
Docker. Toutes les migrations passent donc par le conteneur :

```bash
docker exec -i nexus-postgres psql -U nexus -d nexus_soc -v ON_ERROR_STOP=1 \
  < Lot0_Socle/04_schema_explicabilite.sql
```

Ordre complet, sur une base neuve :

```
Lot0_Socle/01_schema_patched.sql
Lot7_Console_Fournisseur/01_schema_analyst.sql
Lot7_Console_Fournisseur/01_schema_provisioning.sql
Lot7_Console_Fournisseur/02_schema_contact.sql        (demandes de supervision)
Lot0_Socle/03_schema_notifications.sql
Lot0_Socle/04_schema_explicabilite.sql                (chaîne, score, HMAC, unicité)
Lot0_Socle/02_seed_demo.sql
Lot0_Socle/05_backfill_explicabilite.sql              (reprise σ sur l'existant)
```
