# NEXUS SOC : Conception et Implémentation d'une Plateforme de Security Operations Center (SOC) Open Source et Souveraine, Exploitée en Interne par le CENADI pour la Protection de ses Systèmes Sensibles contre les Cybermenaces Internes

> **Avertissement — refonte souveraine (voir `MIGRATION.md`).** Ce rapport a été
> initialement rédigé autour d'un positionnement « SOC-as-a-Service » commercial.
> Le projet a depuis été recentré sur une plateforme **100 % open source et
> souveraine, exploitée en interne par le CENADI** (voir `README.md` et
> `MIGRATION.md`, qui font foi). Les sections encore formulées en termes
> commerciaux (modèle économique, acquisition, tarification) sont **caduques** et
> doivent être relues/réécrites par l'auteur avant la soutenance ; elles ne
> reflètent plus l'architecture livrée (sept composants, cloisonnement par
> périmètre interne, déploiement OpenTofu).

**Rédigé et présenté par :** NGUETSA Junior Stéphane Céleste  
**École :** KEYCE Informatique & Intelligence Artificielle — Yaoundé, Cameroun  
**Filière :** Bachelor Réseaux et Systèmes Informatiques (RSI)  
**Structure d'accueil :** CENADI du Cameroun (CENADI)  
**Année académique :** 2025 – 2026  

---

## INTRODUCTION GÉNÉRALE

### Contexte général

Le Cameroun numérise ses administrations à un rythme soutenu. Le CENADI gère la paie de ses fonctionnaires via SIGIPES et les opérations douanières via ANTILOPE. Le secteur financier non bancaire compte plus de 400 microfinances agréées par la COBAC, 150 compagnies d'assurance relevant du code CIMA, et 300 cabinets comptables membres de l'ONECCA. Tous traitent quotidiennement des millions de francs CFA sur des systèmes connectés au réseau.

Cette connexion appelle une surveillance. Entre 2022 et 2024, des rançongiciels ont paralysé plusieurs administrations africaines pendant des semaines entières, bloquant les paiements et les services aux citoyens. Le rapport IBM Cost of a Data Breach 2023 mesure un délai moyen de détection de 21 jours dans le monde ; en Afrique subsaharienne, ce délai dépasse régulièrement plusieurs semaines. Au Cameroun, des audits internes ont identifié des fonctionnaires fantômes représentant jusqu'à 10 % des effectifs déclarés dans certaines directions. Des données fiscales ont été exfiltrées sans que les systèmes en place ne le détectent.

La loi n° 2010/012 du 21 décembre 2010, relative à la cybersécurité et à la cybercriminalité, oblige les organismes traitant des données personnelles à mettre en place des mesures de sécurité adaptées. L'Agence Nationale des Technologies de l'Information et de la Communication (ANTIC) est chargée d'homologuer les systèmes d'information sensibles. Ces obligations existent depuis quinze ans. Elles restent, pour la grande majorité des administrations et PME camerounaises, sans réponse technique concrète.

### Problématique

Un Security Operations Center (SOC) permet de surveiller les systèmes d'information en temps réel, de détecter les intrusions et de coordonner les réponses aux incidents. Mais pour une direction du CENADI ou une microfinance de Bafoussam, les solutions du marché sont inaccessibles.

CrowdStrike Falcon coûte entre 400 et 800 USD par agent et par an, soit de 80 000 à 160 000 USD annuels pour 200 postes. La licence Splunk SIEM dépasse 10 millions de FCFA, avant même de recruter les trois ingénieurs certifiés que l'outil suppose disponibles. CrowdStrike et SentinelOne hébergent les données sur des serveurs américains, en contradiction directe avec les exigences de souveraineté de l'État camerounais et les prérogatives de l'ANTIC. Aucun de ces outils ne dispose d'interface en français ni de modèle calibré sur SIGIPES ou ANTILOPE. Wazuh est gratuit, mais il exige deux ou trois analystes dédiés que personne ne forme ni n'a les moyens de recruter.

La question centrale de ce projet est la suivante : comment donner à une administration camerounaise ou à une microfinance la capacité de détection d'un SOC de niveau enterprise, avec les ressources réelles de ces organisations, dans un contexte de connectivité réseau variable et de pénurie d'analystes qualifiés ?

### Objectifs

L'objectif général est de concevoir, implémenter et évaluer une plateforme SOC open source et souverain mutualisée, souveraine et abordable, capable de détecter les cybermenaces en temps quasi réel et d'y répondre de manière automatisée, dans le contexte camerounais.

Les objectifs spécifiques sont les suivants :

1. Développer un agent léger de collecte de télémétrie endpoint en langage Go, fonctionnant sur Linux et Windows, en mode egress-only, avec mécanisme de store-and-forward pour les environnements à connectivité intermittente.

2. Implémenter un pipeline de normalisation et de corrélation SIEM mappé sur le référentiel MITRE ATT&CK, capable de reconstituer des chaînes d'attaque multi-étapes à partir d'événements hôte hétérogènes.

3. Entraîner deux modèles d'intelligence artificielle : un modèle de détection d'anomalies réseau par Isolation Forest, calibré sur les patterns DDoS, PortScan et C2 ; un modèle UEBA de détection de fraude interne, adapté aux comportements des agents dans SIGIPES.

4. Développer un moteur SOAR à garde-fous, avec validation humaine obligatoire pour les actions à fort impact (isolation de poste, gel de compte), et mécanisme de rollback.

5. Concevoir un module de restitution bilingue français/anglais, avec analyse déterministe, notifications SMS et WhatsApp, et portail web client autonome.

6. Mettre en place une console opérateur multi-tenant avec isolation stricte des données par Row-Level Security PostgreSQL.

7. Implémenter un flux d'acquisition Product-Led Growth pour les microfinances, avec essai gratuit de 30 jours et provisionnement automatique.

8. Développer un module de déploiement souverain OpenTofu permettant à une administration publique de déployer la pile complète sur son propre serveur, via SSH, en moins de 15 minutes.

### Intérêt et justification du projet

Sur le plan sécuritaire, le besoin est documenté et urgent. Les audits publics camerounais ont mis en évidence des fraudes sur la paie et des exfiltrations de données qui n'ont été détectées qu'a posteriori, parfois après des années. NEXUS SOC réduit le délai moyen de détection à 90 secondes pour une exfiltration et à 120 secondes pour un ransomware, sur les scénarios de simulation testés.

Sur le plan économique, le modèle mutualisé distribue les coûts d'infrastructure entre plusieurs clients. L'accès à la plateforme commence à 25 000 FCFA par mois, soit 33 à 66 fois moins cher que CrowdStrike Falcon pour 200 postes. Le marché potentiel au Cameroun représente plus de 5 milliards de FCFA par an à une pénétration de 10 % des microfinances seules.

Sur le plan académique, ce projet mobilise des domaines rarement assemblés dans un même système : programmation système (Go), traitement de flux événementiels (Kafka), apprentissage automatique non supervisé (Isolation Forest), automatisation des réponses (SOAR), déploiement d'infrastructure par code (OpenTofu). Il constitue une contribution appliquée au contexte africain francophone, un segment que la recherche en cybersécurité documente peu.

### Méthodologie adoptée

Le projet suit une démarche de développement par lots ordonnés : chaque lot (L0 à L8) constitue un bloc fonctionnel autonome, intégré à la couche précédente après validation. Cette organisation diffère d'un développement en MVP progressif ; elle vise la complétude fonctionnelle par couche, en évitant les régressions entre composants.

La démarche comprend quatre phases. L'analyse couvre l'étude du contexte camerounais, le benchmarking des solutions existantes et la formalisation des besoins. La conception définit l'architecture, les choix technologiques et les schémas de données. La réalisation implémente les huit lots avec documentation à chaque étape. L'évaluation s'appuie sur des simulations d'attaques Atomic Red Team (7 techniques MITRE ATT&CK), un test de charge du pipeline (~200 000 événements/seconde), et la validation de l'isolation multi-tenant sur PostgreSQL 16 réel (8/8 assertions).

### Annonce du plan

Le premier chapitre présente la structure d'accueil — le CENADI — et le cadre du stage. Le second établit l'état de l'art en cybersécurité et analyse les limites des solutions existantes. Le troisième formalise les besoins et les contraintes du projet. Le quatrième détaille la conception de la solution, composant par composant. Le cinquième décrit la réalisation et l'implémentation par lots. Le sixième présente les résultats des tests et discute leurs limites.

---

## CHAPITRE 4 — CONCEPTION DE LA SOLUTION

### 4.1 Architecture générale

NEXUS SOC s'organise en sept couches fonctionnelles superposées, chacune produisant des données consommées par la couche supérieure. La Figure 4.1 illustre cette architecture.

**Couche 1 — Collecte (Agent Go).** Sur chaque poste surveillé, un binaire Go de 5 Mo collecte toutes les 30 secondes la liste des processus actifs, les connexions réseau, les fichiers modifiés dans les répertoires surveillés et l'état système. Ces données sont compressées en gzip, signées par HMAC-SHA256 et envoyées en HTTPS vers l'API centrale. L'agent opère en egress-only : il n'ouvre aucun port entrant et fonctionne derrière n'importe quel pare-feu d'entreprise. Si le serveur est injoignable, les lots sont stockés localement dans une file bornée (50 Mo par défaut) et rejoués dès que la connexion revient.

**Couche 2 — Ingestion et transport (Kafka).** Le service de scoring reçoit les lots sur l'endpoint `/ingest`, valide le token Bearer et la signature HMAC, puis publie les événements dans le topic Kafka `nexus.telemetry.raw`. Kafka découple la réception des lots de leur traitement : si le pipeline de normalisation est saturé ou redémarré, les événements restent dans le topic et sont traités à la reprise. Le mode KRaft (sans Zookeeper) simplifie l'opération en production.

**Couche 3 — Normalisation et corrélation (Pipeline SIEM).** Le pipeline Python consomme `nexus.telemetry.raw`, normalise les événements vers un schéma ECS-like (source, destination, process, file, user), extrait des features comportementales d'hôte, puis applique les règles de corrélation MITRE ATT&CK dans une fenêtre glissante de 30 minutes. Quand un incident est détecté (trois tactiques distinctes, ou la combinaison Execution+C2, ou Impact seul), le pipeline publie l'alerte dans `nexus.alerts` et l'écrit en base.

**Couche 4 — Scoring IA (Modèles 1 et 2).** En parallèle de la corrélation, le service de scoring applique le Modèle 1 (Isolation Forest, anomalies réseau) et le Modèle 2 (Isolation Forest UEBA, fraude interne) à chaque lot. Les scores de risque (0 à 100) sont attachés aux alertes avant leur écriture dans TimescaleDB.

**Couche 5 — Réponse automatisée (SOAR).** Le moteur SOAR reçoit les alertes et sélectionne le playbook correspondant au type d'incident. Les actions de faible impact (journalisation, notification SMS) s'exécutent automatiquement si le score dépasse 70. Les actions de fort impact (isolation de poste, gel de compte) attendent la validation d'un analyste humain dans la console fournisseur.

**Couche 6 — Restitution (LLM Analyst + Portail DSI).** Le module de restitution génère une explication en français ou en anglais de chaque incident, identifie les trois features comportementales les plus déviantes, et notifie le DSI client par SMS. Le portail web (fichier HTML autonome) affiche l'historique des incidents, les métriques MTTD/MTTR et les alertes en cours.

**Couche 7 — Administration (Console Fournisseur).** La console opérateur permet à l'équipe NEXUS SOC de gérer les tenants, provisionner les agents, suivre la facturation, trier les alertes cross-tenants et approuver les actions SOAR en attente.

L'ensemble repose sur un socle Docker Compose (Lot 0) comprenant six services : Kafka KRaft, TimescaleDB (PostgreSQL 16 + extension séries temporelles), Wazuh Indexer, Wazuh Manager, Wazuh Dashboard et le service de scoring.

**Architecture multi-tenant.** Une seule instance héberge tous les clients. L'isolation des données repose sur la Row-Level Security (RLS) de PostgreSQL : avant chaque requête, l'API injecte `SET app.current_tenant = '<uuid>'`, et les politiques RLS filtrent automatiquement les lignes sur les tables `alerts`, `agents` et `soar_audit`. Le rôle applicatif `nexus_app` est non super-utilisateur et donc soumis à ces politiques. Le rôle `nexus_analyst` dispose du `BYPASSRLS` pour les analystes SOC qui travaillent sur l'ensemble des tenants. Ce choix évite de multiplier les instances ou les bases de données par client, réduisant les coûts opérationnels de 60 à 80 % par rapport à une architecture par-tenant.

---

### 4.2 Conception des composants

#### 4.2.1 Agent léger de collecte (Lot 1)

L'agent est un binaire Go compilé en stdlib pure, sans aucune dépendance externe. Ce choix implique qu'il n'existe aucun module tiers à mettre à jour, aucun CVE hérité d'une bibliothèque, et que la compilation croisée Linux/Windows s'effectue en une commande (`CGO_ENABLED=0 GOOS=windows go build`), sans outillage spécifique. Le binaire final mesure 5,0 Mo sur Linux et 5,3 Mo sur Windows.

L'agent collecte quatre types de données :
- **Processus actifs** : nom, PID, chemin complet, empreinte SHA-256 (mise en cache pour éviter le recalcul à chaque cycle).
- **Connexions réseau** : protocole, adresse locale, adresse distante, état, lus depuis `/proc/net/tcp` sur Linux et via `netstat` sur Windows.
- **Fichiers modifiés** : chemin et taille des fichiers modifiés dans les répertoires surveillés, configurables par `watch_dirs`.
- **État système** : hostname, OS, architecture, uptime, charge CPU.

Chaque lot est signé par HMAC-SHA256 avec la clé `hmac_key` configurée localement. Le serveur valide cette signature à la réception via l'en-tête `X-Signature`. Un lot dont la signature est invalide est rejeté avec un code HTTP 401 et tracé dans les logs d'audit. Cette double authentification (token Bearer + signature HMAC) garantit à la fois l'identité de l'agent et l'intégrité des données transmises.

Le mécanisme de store-and-forward stocke les lots non transmis dans un répertoire local (`queue_dir`), limité à 50 Mo par défaut (`queue_max_mb`). Si le disque approche de la limite, les lots les plus anciens sont supprimés en priorité (FIFO). Au redémarrage ou au rétablissement de la connexion, l'agent rejoue les lots dans l'ordre chronologique.

#### 4.2.2 Pipeline SIEM (Lot 2)

Le pipeline Python comprend deux modules : `normalizer.py` et `correlation_engine_v2.py`.

Le normalisateur transforme les événements bruts en un schéma ECS-like. Chaque événement normalisé comporte : `timestamp`, `host.name`, `host.os`, `event.category` (process, network, file, system), `event.action`, `process.name`, `process.pid`, `process.executable`, `network.protocol`, `source.ip`, `destination.ip`, `destination.port`, `file.path`, `user.name`. Ce schéma unifié permet au moteur de corrélation de raisonner sur des événements hétérogènes sans connaître leur source.

Le moteur de corrélation applique huit règles dans une fenêtre de 30 minutes (`CORR_WINDOW_MIN=30`), configurable sans redémarrage. Chaque règle mappe un ou plusieurs patterns d'événements à une tactique MITRE ATT&CK :

| Règle | Tactique MITRE | Détection |
|-------|----------------|-----------|
| `detect_suspicious_process` | T1059 — Execution | Processus depuis `/tmp`, `cmd.exe /c`, `powershell -enc` |
| `detect_c2_connection` | T1071 — C2 | Connexion vers ports 4444, 6667, 1337, 8888, 9999 |
| `detect_sensitive_file_access` | T1005 — Collection | Accès à `/etc/shadow`, `/etc/passwd`, fichiers budget |
| `detect_malicious_file` | T1204 — Execution | Fichier `.exe` ou `.bat` dans `Downloads` ou `/tmp` |
| `detect_mass_file_change` | T1486 — Impact | Plus de 20 fichiers modifiés en moins de 5 minutes |
| `detect_obfuscation` | T1027 — Defense Evasion | Base64 inline, double extension, `iex()`, `Invoke-Expression` |
| `detect_account_creation` | T1136 — Persistence | `useradd`, `net user /add`, création de plus de 5 comptes en 10 minutes |
| `detect_directory_scan` | T1083 — Discovery | Accès à `/etc/`, `/proc/`, `HKLM\`, `SAM` |

Un incident est levé si l'un des critères suivants est satisfait dans la fenêtre : au moins trois tactiques distinctes ; la combinaison Execution + C2 ; la tactique Impact seule ; la combinaison Defense Evasion + Persistence. Ce seuil calibre le système pour détecter des comportements réellement suspects sans saturer l'analyste de faux positifs sur des événements isolés.

La version v2 du moteur corrige un bug de complexité algorithmique dans `detect_mass_file_change`. La version v1 comparait chaque paire d'événements dans la fenêtre, produisant une complexité O(N²) qui dégradait les performances à partir de quelques milliers d'événements par minute. La v2 utilise un algorithme à deux pointeurs qui maintient une fenêtre glissante en O(N).

#### 4.2.3 Moteur SOAR (Lot 4)

Le moteur SOAR orchestre neuf connecteurs d'action :

| Connecteur | Impact | Mode d'exécution |
|------------|--------|-----------------|
| `journal_investigation` | LOW | Automatique si score ≥ 70 |
| `preserve_logs` | LOW | Automatique si score ≥ 70 |
| `notify_sms` | LOW | Automatique si score ≥ 70 |
| `notify_whatsapp` | LOW | Automatique si score ≥ 70 |
| `snapshot_memory` | MEDIUM | Automatique si score ≥ 70 |
| `block_ip` | MEDIUM | Automatique si score ≥ 70 |
| `reset_password` | MEDIUM | Automatique si score ≥ 70 |
| `freeze_account` | HIGH | Validation humaine obligatoire |
| `isolate_host` | HIGH | Validation humaine obligatoire |

Les quatre playbooks couvrent les scénarios d'incident principaux :

- **Fraude interne** : `journal_investigation` → `notify_sms` → `freeze_account` → `preserve_logs`
- **Exfiltration** : `journal_investigation` → `freeze_account` → `block_ip` → `notify_sms`
- **Ransomware** : `snapshot_memory` → `isolate_host` → `block_ip` → `notify_sms`
- **Anomalie réseau/C2** : `journal_investigation` → `block_ip` → `notify_sms`

Le paramètre `auto_threshold=70` déclenche l'exécution automatique pour les actions de niveau LOW et MEDIUM quand le score de risque dépasse 70. Les actions HIGH restent en attente de validation dans la console analyste. L'analyste peut approuver, refuser, ou déclencher un rollback via `engine.rollback(incident_id, by)`. Chaque action est tracée dans `audit_log.csv` avec l'identité de l'exécutant, l'horodatage, l'action et son statut.

Le mode `dry_run=True` permet de simuler l'ensemble des actions sans les exécuter, utile pour les démonstrations et la validation des playbooks avant mise en production.

Dans le démonstrateur, les connecteurs sont simulés : `freeze_account` écrit un log mais ne contacte pas d'annuaire LDAP réel. Cette limitation est documentée dans la Section 8 du contexte de projet et listée dans les perspectives.

#### 4.2.4 Module LLM Analyst et portail DSI (Lot 5)

Le LLM Analyst opère en deux modes. Le mode template (défaut) génère une explication déterministe à partir de gabarits paramétrés par le type d'incident, le score, le nom du poste et les trois features comportementales les plus déviantes (exprimées en écart-type par rapport à la ligne de base). Cette approche garantit des explications reproductibles, sans hallucination, et sans dépendance à une API externe. Le mode LLM (optionnel) appelle Mistral 7B ou Llama 3 via une API compatible OpenAI (Ollama ou vLLM), activé par la variable d'environnement `OLLAMA_BASE_URL`. Il n'est pas activé par défaut.

Les notifications SMS respectent la contrainte des 160 caractères du protocole GSM. Exemple : `🚨 NEXUS SOC — Rançongiciel sur POSTE-COMPTA-07 · risque 100/100`. Les rapports WhatsApp hebdomadaires structurés nécessitent en production des templates approuvés par Meta (contrainte de la Business API en dehors de la fenêtre de 24 heures).

Le portail DSI est un fichier HTML autonome (aucun serveur requis) qui s'ouvre directement dans un navigateur. Il affiche les alertes du tenant, le tableau de bord MTTD/MTTR, et permet au DSI client d'approuver les actions SOAR relevant de son organisation. La bascule FR/EN est instantanée via JavaScript. Les données sont chargées depuis l'API via un token JWT DSI.

#### 4.2.5 Console fournisseur (Lot 7)

La console fournisseur est le poste de travail de l'équipe NEXUS SOC. Elle comprend deux modules.

Le **Module A (Administration)** permet de créer, modifier et suspendre des tenants ; de gérer les utilisateurs par rôle (admin_plateforme, analyste_soc, dsi_client) ; de provisionner des agents via tokens à durée de vie configurable (1h/24h/7j), usage unique optionnel, et binding sur hostname. Le provisionnement génère un one-liner directement copiable : `curl -fsSL "https://nexussoc.cm/provision/oneliner?token=xxx" | bash` pour Linux, `irm "..." | iex` pour Windows. L'import CSV bulk génère un token par ligne pour le déploiement de masse, exportable et exploitable avec Ansible.

Le **Module B (Analyste SOC)** affiche la file d'alertes cross-tenants triée par score décroissant. Chaque alerte s'ouvre dans un modal détaillant la kill-chain reconstituée, l'explication LLM, les features déviantes en écart-type et les actions SOAR en attente. L'analyste approuve ou refuse chaque action HIGH depuis ce modal. Le tableau de bord SOC affiche le MTTD et le MTTR par tenant sur les 7 derniers jours.

---

### 4.3 Choix technologiques justifiés

#### Go pour l'agent

Go produit un binaire statique autonome sans runtime. Un agent écrit en Python nécessiterait un interpréteur Python installé sur chaque poste cible, ou un packaging PyInstaller qui gonfle le binaire à 30-60 Mo. En Go pur stdlib, le binaire fait 5 Mo, se compile en cible croisée (Linux, Windows, ARM) depuis une même machine de développement, et ne présente aucun CVE provenant de modules tiers (décision D6). La compilation offline est possible, ce qui est utile dans les ministères où les postes de développement n'ont pas accès à internet.

#### Python + FastAPI pour l'API

FastAPI est asyncio natif et génère automatiquement une documentation Swagger accessible à `/docs`. Sa compatibilité avec les bibliothèques scikit-learn, numpy et asyncpg simplifie l'intégration des modèles dans l'API de scoring. L'authentification JWT est implémentée en stdlib (`hmac`, `hashlib`, `secrets`) sans dépendance PyJWT, conservant le contrôle total sur le format des tokens.

#### Kafka en mode KRaft

Kafka offre une garantie de livraison at-least-once, la persistance des événements dans des topics partitionnés et la possibilité d'ajouter des consommateurs sans modifier les producteurs. Le mode KRaft (Kafka Raft Metadata), disponible depuis Kafka 3.3, supprime la dépendance à Zookeeper : un seul service à opérer au lieu de deux. Pour le démonstrateur et les déploiements souverains mono-nœud, cette simplification réduit la mémoire consommée d'environ 400 Mo et le nombre de points de défaillance.

#### TimescaleDB

TimescaleDB est une extension PostgreSQL qui ajoute des hypertables partitionnées par temps, sans changer l'interface SQL standard. Cela permet d'utiliser le même service de base de données pour les données relationnelles (tenants, utilisateurs, agents) et les séries temporelles (métriques, alertes horodatées). Un Elasticsearch séparé n'est donc pas nécessaire pour les métriques, ce qui allège l'architecture. La politique de rétention compresse les métriques après 7 jours et archive les alertes après un an.

#### Wazuh Indexer comme stockage chaud

Wazuh Indexer (basé sur OpenSearch) reçoit tous les événements de sécurité normalisés et sert d'interface d'exploration pour les analystes via Wazuh Dashboard. Il évite d'intégrer un Elasticsearch séparé et fournit les dashboards de corrélation Wazuh prêts à l'emploi. Pour les déploiements souverains, cet ensemble (Indexer + Manager + Dashboard) est déployé en même temps que la pile NEXUS SOC via OpenTofu.

#### Isolation Forest pour la détection d'anomalies

L'Isolation Forest (Liu et al., 2008) est un algorithme non supervisé qui isole les anomalies en construisant des arbres de décision aléatoires : les points anormaux, rares et différents du reste, sont isolés en moins de coupures. Il ne nécessite pas de données labellisées, ce qui est déterminant dans le contexte camerounais où aucun jeu de données étiqueté sur des incidents réels n'est disponible. Il est entraînable en quelques secondes sur un poste standard et produit un score d'anomalie directement interprétable. La variante autoencodeur (MLPRegressor entraîné à reconstruire les flux normaux) complète l'Isolation Forest sur les attaques de type PortScan (ROC-AUC 0,98 contre 0,84 pour l'IF seul).

#### OpenTofu pour le déploiement souverain

OpenTofu permet de décrire l'infrastructure cible comme du code versionnable et rejouable. Les providers `null` (SSH provisioners), `tls` (certificats auto-signés), `local` (rendu de templates) et `random` (génération de secrets) sont suffisants pour déployer la pile complète sur n'importe quel serveur Ubuntu 22.04 avec accès SSH et sudo. Le mécanisme de triggers basé sur le hash SHA-256 des fichiers source garantit que OpenTofu re-déploie uniquement les composants modifiés, rendant les mises à jour idempotentes.

---

### 4.4 Conception des modèles d'IA

#### 4.4.1 Modèle 1 — Détection d'anomalies réseau

Le Modèle 1 s'appuie sur le jeu de données CICIDS2017 du Canadian Institute for Cybersecurity, qui contient des captures de trafic réseau labelisées en flux CICFlowMeter : trafic bénin, DDoS, PortScan, Bot/C2, infiltration et brute-force. Sur ce jeu de données, environ 80 features numériques sont disponibles après nettoyage des valeurs infinies et des colonnes à variance nulle.

Le prétraitement applique une normalisation StandardScaler (moyenne 0, écart-type 1). Le modèle Isolation Forest est entraîné uniquement sur le trafic bénin (contamination à 0,05, c'est-à-dire 5 % d'anomalies estimées dans les données d'entraînement). Le score d'anomalie brut est converti en score de risque 0-100 par une transformation affine calibrée sur les quantiles. Le seuil de décision est fixé au 95e percentile du trafic bénin de validation.

Les métriques obtenues sur le jeu de test CICIDS2017 :

| Métrique | Isolation Forest | Autoencodeur |
|----------|-----------------|--------------|
| ROC-AUC | 0,987 | 0,991 |
| PR-AUC | 0,943 | 0,981 |
| DDoS | 99,5 % détecté | 91 % détecté |
| PortScan | 84 % détecté | 98 % détecté |
| Bot/C2 | 96 % détecté | 100 % détecté |

L'IF et l'autoencodeur sont complémentaires : l'IF détecte mieux les DDoS (volume brut), l'autoencodeur détecte mieux les PortScans (pattern subtil). En production, les deux scores sont calculés et le maximum est retenu.

Dans le démonstrateur, les données d'entraînement sont synthétiques et imitent les distributions CICIDS2017. La validation sur données réseau réelles (captures NetFlow du CENADI) est prévue pendant le stage.

#### 4.4.2 Modèle 2 — Détection de fraude interne (UEBA)

Le Modèle 2 détecte les comportements frauduleux des agents dans les systèmes de gestion publique. Il s'inspire du CERT Insider Threat Dataset (Carnegie Mellon University/SEI) comme cadre théorique, et utilise des données synthétiques modélisant les comportements observables dans SIGIPES.

Le modèle travaille sur des profils agrégés agent-jour : pour chaque agent et chaque jour, 10 features sont calculées à partir des journaux d'audit.

| Feature | Description |
|---------|-------------|
| `nb_connexions` | Nombre de sessions ouvertes dans la journée |
| `nb_actions_hors_heures` | Actions entre 20h et 6h |
| `nb_transactions` | Opérations financières enregistrées |
| `montant_total_modifie` | Somme des modifications de montants |
| `nb_modifs_montant` | Nombre de modifications de montants |
| `nb_creations_compte` | Comptes créés dans la journée |
| `nb_exports` | Exports de données effectués |
| `volume_donnees_exportees` | Volume en Ko des exports |
| `nb_acces_dossiers_sensibles` | Accès aux dossiers marqués sensibles |
| `nb_actions_total` | Toutes actions confondues |

L'Isolation Forest est entraîné sur des profils normaux (contamination à 0,04). Les métriques sur le jeu de test synthétique :

| Scénario | Taux de détection |
|----------|-----------------|
| Fonctionnaires fantômes | 76 % |
| Exfiltration fiscale | 97 % |
| Faux mandatements | 54 % |
| ROC-AUC global | 0,969 |
| Taux de faux positifs | 4 % |

Le taux de 54 % sur les faux mandatements s'explique par la proximité comportementale avec des transactions légitimes : un agent modifiant un montant une fois par jour ne se distingue pas statistiquement d'un agent frauduleux prudent. Cette limite est documentée honnêtement dans les résultats.

L'explicabilité est assurée par le calcul des trois features les plus déviantes par rapport à la ligne de base, exprimées en écart-type. Par exemple : `nb_exports (+4,2σ)`, `volume_donnees_exportees (+3,8σ)`, `nb_acces_dossiers_sensibles (+2,1σ)`. Ces trois features sont affichées dans l'alerte et dans l'explication LLM Analyst.

#### 4.4.3 Monitoring de la dérive des modèles (Lot 3)

Les modèles en production peuvent dériver quand la distribution des données change. Le module `model_monitor.py` surveille cette dérive via deux méthodes :

Le **Population Stability Index (PSI)** compare la distribution d'une feature entre la période de référence (entraînement) et la période courante. Un PSI inférieur à 0,10 indique une distribution stable. Entre 0,10 et 0,25, une surveillance s'impose. Au-delà de 0,25, un réentraînement est requis.

Le **glissement σ** mesure si la moyenne des scores de risque s'est décalée de plus d'un écart-type par rapport à la baseline. Il détecte des dérives que le PSI peut manquer sur des features individuelles.

Ces deux métriques sont exposées via l'endpoint `GET /monitor/drift?days=7` et affichées dans la console fournisseur.

---

### 4.5 Cartographie MITRE ATT&CK

Le référentiel MITRE ATT&CK (Adversarial Tactics, Techniques and Common Knowledge) catégorise les comportements offensifs en tactiques (ce que cherche à faire l'attaquant) et techniques (comment il le fait). NEXUS SOC couvre sept techniques réparties sur cinq tactiques :

| Technique MITRE | Tactique | Règle SIEM | Signal détecté |
|----------------|----------|-----------|----------------|
| T1059 — Command and Scripting Interpreter | Execution | `detect_suspicious_process` | `cmd.exe /c`, `powershell -enc`, exécution depuis `/tmp` |
| T1204 — User Execution: Malicious File | Execution | `detect_malicious_file` | `.exe` ou `.bat` dans `Downloads`, `/tmp` |
| T1071 — Application Layer Protocol | Command and Control | `detect_c2_connection` | Ports 4444, 6667, 1337, 8888, 9999 |
| T1005 — Data from Local System | Collection | `detect_sensitive_file_access` | `/etc/shadow`, `/etc/passwd`, fichiers budget |
| T1486 — Data Encrypted for Impact | Impact | `detect_mass_file_change` | >20 fichiers modifiés en <5 min |
| T1027 — Obfuscated Files or Information | Defense Evasion | `detect_obfuscation` | Base64 inline, double extension |
| T1136 — Create Account | Persistence | `detect_account_creation` | `useradd`, `net user /add`, >5 créations en 10 min |

La règle `detect_directory_scan` couvre T1083 (File and Directory Discovery, tactique Discovery), portant la couverture totale à huit règles et huit techniques. Les simulations d'attaques Atomic Red Team ont validé la détection de 7/7 techniques testées (cf. Chapitre 6).

Le critère de levée d'incident est délibérément restrictif pour limiter les faux positifs : une technique isolée ne produit pas d'incident. Cette décision implique que des attaques très ciblées utilisant une seule technique passent sous le radar, sauf si cette technique est Impact (T1486 — ransomware), qui déclenche systématiquement une alerte.

---

### 4.6 Sécurité de la plateforme et isolation multi-tenant

#### Isolation des tenants par Row-Level Security

La RLS PostgreSQL est activée sur les tables `alerts`, `agents` et `soar_audit`. La politique est définie ainsi :

```sql
CREATE POLICY tenant_isolation ON alerts
  USING (tenant_id = NULLIF(
    current_setting('app.current_tenant', true), ''
  )::uuid);
```

La fonction `NULLIF` est un correctif critique : sans elle, si la variable de session `app.current_tenant` est vide (connexion sans contexte tenant), PostgreSQL évalue `NULL::uuid = NULL` à `NULL`, ce qui retourne `false` et filtre toutes les lignes. Avec `NULLIF`, une valeur vide retourne `NULL`, qui déclenche la même logique de sécurité. Ce correctif a été validé par 8/8 assertions sur PostgreSQL 16 réel.

Le rôle `nexus_app` (non super-utilisateur) est utilisé par l'API pour toutes les requêtes normales ; il est soumis à la RLS. Le rôle `nexus_analyst` dispose du `BYPASSRLS` pour les analystes SOC qui doivent traiter les alertes de tous les tenants depuis la console fournisseur.

#### Authentification JWT maison

L'authentification utilise des tokens JWT signés par HMAC-SHA256 avec le secret `JWT_SECRET`. L'implémentation est en stdlib Python (`hmac`, `hashlib`, `secrets`, `base64`), sans dépendance PyJWT. Les tokens d'accès ont une durée de vie de 15 minutes, les tokens de rafraîchissement de 7 jours. La rotation est gérée par `POST /auth/refresh`.

#### Sécurité de l'ingestion

L'endpoint `/ingest` requiert deux formes d'authentification cumulatives : un token Bearer d'enrôlement (fourni lors du provisionnement de l'agent) et une signature HMAC-SHA256 du payload dans l'en-tête `X-Signature`. Un rate limiting de 30 requêtes par minute par IP est appliqué sur `/ingest`. Au-delà, le serveur répond avec un code HTTP 429 et un en-tête `Retry-After`.

#### Pseudonymisation des données personnelles

Le module `pseudonymizer.py` remplace les données personnelles dans les alertes avant leur écriture en base. Les emails, adresses IP publiques, identifiants d'agents et noms de domaine sont remplacés par des pseudonymes HMAC-SHA256 stables (le même PII produit toujours le même pseudonyme avec la même clé `PSEUDO_SECRET`). Cette stabilité permet de corréler des alertes concernant le même agent sans exposer son identité réelle.

#### Sécurité de l'agent PLG (Lot 8)

L'agent PLG (coquille vide distribuée aux clients en essai) est compilé avec `garble`, un outil d'obfuscation de binaires Go qui brouille les noms de symboles, les chaînes et les chemins de fichiers dans le binaire final. Un watermark HMAC-SHA256 unique par tenant est injecté via les ldflags avant la compilation et envoyé dans l'en-tête `X-Nexus-Watermark` à chaque requête d'ingestion. Ce watermark permet d'identifier le tenant propriétaire d'un agent si le binaire est extrait ou partagé.

La configuration dynamique de l'agent (répertoires surveillés, intervalle de collecte, quotas) est récupérée depuis l'API à chaque démarrage et mise en cache localement dans un fichier au format `[32 octets tag HMAC][payload gzip]`, avec permissions `chmod 600`. Si le tag HMAC est invalide à la lecture (fichier altéré), le cache est supprimé et l'agent tente un refetch depuis le serveur.

---

*Volume : ~16 pages*

---

## CHAPITRE 3 — ANALYSE ET SPÉCIFICATION DES BESOINS

### 3.1 Méthodologie d'analyse

L'analyse des besoins de NEXUS SOC repose sur trois sources distinctes.

La première est documentaire : cahier des charges du projet, loi n° 2010/012, référentiels MITRE ATT&CK et ISO/IEC 27001, rapports COBAC et ANTIC publiés, documentation technique de Wazuh, CrowdStrike et Splunk, et jeux de données CICIDS2017 et CERT Insider Threat pour les modèles IA.

La seconde est comparative : analyse des solutions existantes (Wazuh, CrowdStrike Falcon, Splunk SIEM, SentinelOne) pour identifier leurs lacunes vis-à-vis du contexte camerounais, en termes de coût, de souveraineté des données, de langue et d'adaptation aux systèmes locaux.

La troisième est contextuelle : observation des pratiques dans les administrations publiques camerounaises, connaissance des contraintes réseau (connectivité intermittente, bande passante limitée hors Yaoundé et Douala), et prise en compte de la pénurie documentée d'analystes SOC qualifiés au Cameroun.

Les besoins ont été structurés en trois catégories : fonctionnels (ce que le système doit faire), non-fonctionnels (comment il doit le faire) et contraintes (ce qu'il ne peut pas dépasser ou contourner).

---

### 3.2 Besoins fonctionnels

Les besoins fonctionnels sont organisés par composant, dans l'ordre de la chaîne de traitement des données.

#### BF-01 — Collecte de télémétrie endpoint (Agent)

| Réf. | Exigence |
|------|----------|
| BF-01.1 | L'agent collecte toutes les 30 secondes les processus actifs (nom, PID, chemin, SHA-256), les connexions réseau (proto, adresses, état), les fichiers modifiés dans les répertoires configurés, et l'état système (hostname, OS, uptime). |
| BF-01.2 | L'agent fonctionne sur Linux (amd64, arm64) et Windows (amd64). Il ne nécessite pas de droits administrateur pour les collectes de base. |
| BF-01.3 | L'agent n'ouvre aucun port réseau entrant. Toutes ses communications sont initiées vers le serveur (egress-only HTTPS). |
| BF-01.4 | Si le serveur est injoignable, l'agent stocke les lots localement dans une file bornée et les rejoue dans l'ordre à la reconnexion. |
| BF-01.5 | Chaque lot est signé par HMAC-SHA256 avant envoi. Le serveur vérifie cette signature et rejette les lots invalides. |
| BF-01.6 | Le payload est compressé en gzip avant envoi (économie de bande passante visée : 70 %). |

#### BF-02 — Ingestion et transport (API + Kafka)

| Réf. | Exigence |
|------|----------|
| BF-02.1 | L'API expose un endpoint `POST /ingest` qui accepte les lots d'agents authentifiés par token Bearer et signature HMAC. |
| BF-02.2 | L'API publie les événements reçus dans Kafka pour découpler la réception du traitement. |
| BF-02.3 | Un rate limiting de 30 requêtes/minute est appliqué sur `/ingest` par adresse IP. Au-delà, le serveur répond HTTP 429 avec un en-tête `Retry-After`. |
| BF-02.4 | Pour les tenants en essai gratuit, l'API vérifie les quotas (5 agents max, 10 000 événements/jour max) et renvoie HTTP 402 si le tenant est suspendu ou expiré, HTTP 429 si le quota journalier est dépassé. |

#### BF-03 — Normalisation et corrélation SIEM (Pipeline)

| Réf. | Exigence |
|------|----------|
| BF-03.1 | Le pipeline normalise les événements bruts vers un schéma ECS-like avec les champs : timestamp, host.name, event.category, event.action, process.name, network.protocol, source.ip, destination.ip, destination.port, file.path, user.name. |
| BF-03.2 | Le moteur de corrélation applique au minimum 8 règles couvrant les tactiques Execution, Command and Control, Collection, Impact, Defense Evasion, Persistence et Discovery du référentiel MITRE ATT&CK. |
| BF-03.3 | La fenêtre de corrélation est de 30 minutes, configurable sans redémarrage du service. |
| BF-03.4 | Un incident est levé si l'un de ces critères est satisfait dans la fenêtre : au moins 3 tactiques distinctes ; combinaison Execution + C2 ; tactique Impact seule ; combinaison Defense Evasion + Persistence. |
| BF-03.5 | Le pipeline reconstruit la kill-chain (séquence ordonnée d'événements ayant déclenché l'incident) et l'attache à l'alerte. |

#### BF-04 — Scoring par intelligence artificielle (Modèles IA)

| Réf. | Exigence |
|------|----------|
| BF-04.1 | Le Modèle 1 (anomalies réseau) calcule un score de risque de 0 à 100 pour chaque flux réseau, à partir de features CICFlowMeter. Un score supérieur à 70 déclenche une alerte. |
| BF-04.2 | Le Modèle 2 (fraude interne UEBA) calcule un score de risque pour chaque profil agent-jour, à partir de 10 features agrégées issues des journaux d'audit SIGIPES. |
| BF-04.3 | Pour chaque alerte IA, le système identifie et présente les 3 features comportementales les plus déviantes par rapport à la ligne de base, exprimées en écart-type. |
| BF-04.4 | Le service expose les endpoints `POST /score/network` et `POST /score/user-day` pour le scoring à la demande. |
| BF-04.5 | Le module de monitoring surveille la dérive des modèles via le PSI (Population Stability Index) et le glissement σ, et expose ces métriques sur `GET /monitor/drift`. |

#### BF-05 — Réponse automatisée aux incidents (SOAR)

| Réf. | Exigence |
|------|----------|
| BF-05.1 | Le moteur SOAR dispose d'au moins 9 connecteurs d'action couvrant la journalisation, la notification, la sauvegarde, le blocage réseau, la réinitialisation de compte, l'isolation de poste et le gel de compte. |
| BF-05.2 | Les actions de niveau LOW et MEDIUM s'exécutent automatiquement si le score de risque dépasse le seuil configuré (70 par défaut). |
| BF-05.3 | Les actions de niveau HIGH (isolation de poste, gel de compte) requièrent la validation explicite d'un analyste SOC humain avant exécution. |
| BF-05.4 | L'analyste peut déclencher un rollback de toute action réversible. Chaque action est tracée dans un journal d'audit avec identité de l'exécutant, horodatage et statut. |
| BF-05.5 | Le mode `dry_run` permet de simuler l'ensemble des actions sans les exécuter. |

#### BF-06 — Restitution bilingue et notification (LLM Analyst + Portail)

| Réf. | Exigence |
|------|----------|
| BF-06.1 | Le module LLM Analyst génère une explication en français ou en anglais pour chaque incident, en mode déterministe (sans LLM) par défaut. |
| BF-06.2 | Les notifications SMS respectent la limite de 160 caractères et incluent au minimum : le type d'incident, le nom du poste et le score de risque. |
| BF-06.3 | Le portail DSI est un fichier HTML autonome, consultable sans serveur, affichant les alertes du tenant, les métriques MTTD/MTTR et l'état des actions SOAR. |
| BF-06.4 | La bascule français/anglais est instantanée dans le portail et dans la console fournisseur. |

#### BF-07 — Administration multi-tenant et provisionnement (Console + API)

| Réf. | Exigence |
|------|----------|
| BF-07.1 | La console fournisseur permet de créer, modifier et supprimer des tenants, des utilisateurs et des agents depuis une interface unique. |
| BF-07.2 | Le provisionnement d'un agent génère un one-liner curl (Linux) ou PowerShell (Windows) directement copiable, exécutable sans intervention humaine supplémentaire. |
| BF-07.3 | L'import CSV permet de générer des tokens d'enrôlement en masse (hostname, OS, description par ligne). |
| BF-07.4 | Un pack offline (.zip contenant binaire + config + scripts) permet l'installation sur des postes sans accès internet. |
| BF-07.5 | Les tokens d'enrôlement peuvent être configurés avec : durée de vie (1h, 24h, 7j), usage unique, et binding sur un hostname précis. |
| BF-07.6 | L'API expose la rotation de clé HMAC (`POST /provision/rotate-hmac/{agent_id}`) et la révocation d'urgence de tous les agents d'un tenant (`POST /provision/revoke-tenant/{tenant_id}`). |

#### BF-08 — Acquisition client automatisée (PLG)

| Réf. | Exigence |
|------|----------|
| BF-08.1 | La landing page permet à un responsable DSI de s'inscrire en moins de 5 minutes pour un essai gratuit de 30 jours, sans intervention de l'équipe NEXUS SOC. |
| BF-08.2 | Le système bloque les adresses email des domaines jetables connus (au moins 50 domaines : mailinator, yopmail, guerrillamail, etc.). |
| BF-08.3 | Les adresses email des domaines gouvernementaux camerounais (.gov.cm, .gouv.cm, .mil.cm, .edu.cm) sont redirigées vers le flux de contact "Déploiement Souverain". |
| BF-08.4 | L'inscription inclut une vérification d'email (token urlsafe 32 octets) et une pré-autorisation bancaire de 0 FCFA pour valider l'identité. |
| BF-08.5 | À l'issue de l'inscription, le tenant est créé automatiquement dans la base de données avec les quotas d'essai (5 agents, 10 000 événements/jour, 30 jours). |

#### BF-09 — Déploiement souverain (OpenTofu)

| Réf. | Exigence |
|------|----------|
| BF-09.1 | Le module OpenTofu déploie la pile NEXUS SOC complète sur un serveur distant via SSH, sans intervention manuelle au-delà de la configuration initiale du fichier `terraform.tfvars`. |
| BF-09.2 | Le déploiement couvre : installation Docker, upload des configs, déploiement des sources Python, génération des certificats Wazuh, lancement de la pile Docker Compose, et vérification de santé des services. |
| BF-09.3 | Les secrets (mot de passe PostgreSQL, JWT secret, mot de passe Wazuh admin) sont générés automatiquement si non fournis, et disponibles via `tofu output`. |
| BF-09.4 | Un cron de sauvegarde quotidien (02h00) est installé automatiquement sur le serveur cible après déploiement. |
| BF-09.5 | Tout changement de code source (détecté par hash SHA-256) déclenche automatiquement le re-déploiement du seul composant modifié lors du prochain `tofu apply`. |

---

### 3.3 Besoins non-fonctionnels

#### BNF-01 — Performance

Le pipeline de normalisation doit traiter au moins 100 000 événements par seconde en mode mono-cœur, avec un temps de traitement au 99e percentile inférieur à 20 microsecondes par événement. Ce seuil couvre le volume d'une administration de 500 postes générant chacun 10 événements toutes les 30 secondes, soit environ 170 événements/seconde en pointe, avec une marge confortable.

L'API d'ingestion doit répondre en moins de 200 ms pour 95 % des requêtes sous charge normale (100 requêtes simultanées).

L'agent ne doit pas consommer plus de 0,5 % du CPU sur un poste de travail standard (Intel Core i5 ou équivalent), ni plus de 15 Mo de mémoire vive au pic de collecte. Ces cibles permettent l'installation sur des postes en production sans dégrader l'expérience des utilisateurs.

#### BNF-02 — Sécurité de la plateforme

L'API doit exiger deux formes d'authentification cumulatives sur `/ingest` : un token Bearer d'enrôlement et une signature HMAC-SHA256 du payload. Tout lot ne satisfaisant pas les deux conditions est rejeté avec un log d'audit.

Les données personnelles dans les alertes (emails, adresses IP, identifiants d'agents) doivent être pseudonymisées avant écriture en base. La pseudonymisation doit être stable (même PII + même clé = même pseudonyme) pour permettre la corrélation d'alertes sans exposer les identités.

Les tokens JWT d'accès ont une durée de vie de 15 minutes. Les tokens de rafraîchissement expirent au bout de 7 jours.

Les fichiers de configuration contenant des secrets (clé HMAC, token d'enrôlement) doivent être stockés avec des permissions `chmod 600` (Linux) ou des ACL équivalentes (Windows).

#### BNF-03 — Souveraineté des données

Aucune donnée de télémétrie, aucune alerte et aucune donnée personnelle ne doivent transiter vers des serveurs situés hors du territoire camerounais ou hors de l'infrastructure contrôlée par le client (pour les déploiements souverains). Le recours aux CDN (jsDelivr pour QRCode.js et JSZip) est limité aux ressources JavaScript statiques des interfaces, sans transmission de données utilisateur.

L'ensemble des composants logiciels utilisés sont open-source ou développés en interne, sans dépendance à des licences commerciales à renouvellement annuel.

#### BNF-04 — Résilience

L'agent doit continuer à fonctionner sans supervision pendant au minimum 72 heures en mode dégradé (serveur injoignable), en conservant les lots dans sa file locale. La file est bornée à 50 Mo par défaut pour éviter de saturer le disque des postes cibles.

Chaque service Docker dispose d'un healthcheck. Si un service est défaillant, Docker le redémarre automatiquement. Le service de scoring vérifie la disponibilité de Kafka, TimescaleDB et Wazuh Indexer via l'endpoint `GET /health/detailed`.

Les sauvegardes sont automatisées via `backup.sh` (PostgreSQL + modèles + config Wazuh), avec rotation sur 14 jours par défaut.

#### BNF-05 — Scalabilité

L'architecture multi-tenant doit permettre d'héberger au moins 50 tenants actifs sur une seule instance sans modification de code, grâce à l'isolation par RLS PostgreSQL.

Kafka permet d'ajouter des consommateurs supplémentaires (instances de pipeline SIEM) sans modifier les producteurs, si le volume d'événements dépasse la capacité d'un seul consommateur.

TimescaleDB compresse automatiquement les métriques après 7 jours et archive les alertes après un an, maintenant des performances de requête stables à mesure que le volume de données augmente.

#### BNF-06 — Utilisabilité

La console fournisseur et le portail DSI doivent être pleinement utilisables sans installation de logiciel supplémentaire (fichiers HTML autonomes, ouverts dans un navigateur moderne).

Les interfaces doivent être disponibles en français et en anglais, avec bascule instantanée sans rechargement de page.

Le provisionnement d'un nouvel agent (depuis la génération du token jusqu'à l'exécution du one-liner sur le poste cible) doit prendre moins de 5 minutes pour un administrateur sans formation préalable sur NEXUS SOC.

Le déploiement souverain complet via OpenTofu (depuis `tofu apply` jusqu'au healthcheck final) doit s'effectuer en moins de 15 minutes sur un serveur Ubuntu 22.04 avec une connexion à 10 Mbps.

---

### 3.4 Contraintes

#### 3.4.1 Contraintes réglementaires

**Loi n° 2010/012 du 21 décembre 2010.** Cette loi oblige les organismes traitant des données personnelles à mettre en place des mesures de sécurité adaptées. Elle définit les infractions pénales liées à la cybercriminalité et encadre les conditions d'accès aux systèmes d'information. Pour NEXUS SOC, elle implique que toute alerte contenant des données personnelles (nom d'utilisateur, adresse IP, email) soit pseudonymisée avant archivage, et que les journaux d'audit soient conservés dans des conditions garantissant leur intégrité.

**ANTIC (Agence Nationale des Technologies de l'Information et de la Communication).** L'ANTIC homologue les systèmes d'information sensibles au Cameroun. Un déploiement de NEXUS SOC dans une administration publique devrait, en production, faire l'objet d'une déclaration auprès de l'ANTIC. Cette démarche n'a pas été réalisée dans le cadre du démonstrateur académique ; elle est documentée comme étape de mise en production.

**COBAC (Commission Bancaire de l'Afrique Centrale).** Les microfinances agréées par la COBAC sont soumises à des exigences de sécurité de leurs systèmes d'information. NEXUS SOC se positionne comme outil permettant à ces microfinances de satisfaire partiellement ces exigences, sans remplacer un audit de conformité COBAC complet.

**CIMA (Code des Assurances).** Les compagnies d'assurance relevant du code CIMA sont soumises à des obligations similaires. Le module PLG les identifie comme cible via le champ `secteur=assurance` lors de l'inscription.

**RGPD (Règlement Général sur la Protection des Données).** Le RGPD n'est pas directement applicable au Cameroun, mais constitue un référentiel de bonnes pratiques pour la gestion des données personnelles. Le module de pseudonymisation de NEXUS SOC s'inspire des principes du RGPD (minimisation des données, pseudonymisation, droit à l'oubli).

#### 3.4.2 Contraintes techniques

**Connectivité réseau variable.** Hors des grandes villes, la connectivité réseau camerounaise est intermittente et de faible débit. L'agent doit fonctionner sur des connexions à moins de 1 Mbps et survivre à des coupures de plusieurs heures. La compression gzip et le mécanisme de store-and-forward répondent à cette contrainte.

**Diversité des postes cibles.** Les administrations publiques camerounaises utilisent un mélange de postes Linux (serveurs) et Windows (postes de travail). L'agent doit fonctionner sur les deux sans modification de code. macOS n'est pas dans le périmètre : sa présence dans les administrations camerounaises est négligeable.

**Absence de droits administrateur systématique.** Dans certaines organisations, les postes de travail ne disposent pas de droits d'administration permanents. L'agent ne doit pas en requérir pour les collectes de base (processus, connexions réseau).

**Ressources limitées sur les postes cibles.** Les postes en production ont souvent moins de 4 Go de RAM et des processeurs datant de 2015-2018. L'agent est conçu pour ne jamais dépasser 15 Mo de mémoire vive et 0,5 % de CPU.

#### 3.4.3 Contraintes juridiques liées à la surveillance

La surveillance des postes de travail des employés est encadrée juridiquement. En France (référence comparative), la CNIL encadre strictement ce type de supervision. Au Cameroun, la loi 2010/012 impose la confidentialité des données personnelles et soumet leur traitement à des conditions de licéité.

Pour NEXUS SOC, deux principes sont appliqués. D'abord, la pseudonymisation systématique : les identifiants personnels (nom d'utilisateur, email, adresse IP) sont remplacés par des pseudonymes HMAC-SHA256 stables dans toutes les alertes stockées en base, de sorte qu'un accès à la base ne révèle pas les identités réelles. Ensuite, la traçabilité des accès : chaque action SOAR et chaque accès aux données d'un tenant est journalisé avec l'identité de l'analyste, permettant un audit a posteriori.

La mise en production dans une administration publique devrait s'accompagner d'une information préalable des agents sur l'existence et le périmètre de la supervision.

#### 3.4.4 Contraintes économiques et de modèle

Les organisations cibles n'ont pas de budget cybersécurité dédié. Les licences en devise étrangère (USD, EUR) sont difficiles à régler pour une microfinance camerounaise. NEXUS SOC est donc tarifé en FCFA et basé exclusivement sur des technologies open-source (Wazuh, Kafka, TimescaleDB, FastAPI, scikit-learn), sans aucune licence commerciale récurrente sur les composants serveur.

---

### 3.5 Périmètre complet et découpage en lots

#### 3.5.1 Ce qui est dans le périmètre

NEXUS SOC couvre deux types d'organisations :

**Administrations publiques camerounaises** (CENADI, DGI, DGCOOP, DGD et autres ministères) : 50 à 500 postes surveillés, hébergement souverain sur leur propre infrastructure, contrat annuel avec SLA 1 heure, intégration aux systèmes SIGIPES et ANTILOPE.

**Secteur financier non bancaire** : microfinances agréées COBAC (5 à 100 postes), compagnies d'assurance CIMA, cabinets comptables ONECCA. Accès via abonnement mensuel en FCFA, inscription self-service.

#### 3.5.2 Ce qui est hors périmètre

**Mobile Money (MTN, Orange, etc.)** : ce domaine est régulé par la BEAC et nécessite des accords opérateurs et l'accès à des données propriétaires. Il est explicitement exclu.

**Banques commerciales** : la réglementation COBAC bancaire est plus complexe que celle des microfinances et dépasse le périmètre d'un démonstrateur académique.

**Particuliers et utilisateurs finaux** : NEXUS SOC est une solution B2B, destinée aux responsables DSI et aux équipes de sécurité d'organisations.

**macOS** : aucun support agent. Les serveurs macOS dans les administrations camerounaises sont inexistants en pratique.

**Détection basée sur le contenu** : analyse YARA, sandbox de pièces jointes et analyse de flux DNS chiffrés ne sont pas couverts dans le démonstrateur.

#### 3.5.3 Découpage en lots

Le projet est découpé en neuf lots ordonnés. Chaque lot est fonctionnellement autonome et s'intègre au lot précédent.

| Lot | Contenu | Dépendances |
|-----|---------|-------------|
| L0 — Socle | Docker Compose (6 services), schéma SQL, politiques RLS, scripts de sauvegarde | Aucune |
| L1 — Agent + API | Agent Go (collecte, HMAC, store-and-forward), service de scoring FastAPI, authentification JWT | L0 |
| L2 — Pipeline SIEM | Normalisation ECS-like, moteur de corrélation MITRE ATT&CK (8 règles, fenêtre 30 min) | L0, L1 |
| L3 — Modèles IA | Modèle 1 (Isolation Forest réseau, ROC-AUC 0,987), Modèle 2 (UEBA fraude, ROC-AUC 0,969), monitoring dérive | L1 |
| L4 — SOAR | 9 connecteurs, 4 playbooks, validation humaine HIGH, rollback, journal d'audit | L2, L3 |
| L5 — Restitution | LLM Analyst bilingue, notifications SMS/WhatsApp, portail DSI HTML autonome | L4 |
| L6 — Tests | Simulation d'attaques (7/7 MITRE), test de charge (~200 000 ev/s), isolation RLS (8/8 assertions) | L0 à L5 |
| L7 — Console + Provisionnement | Console fournisseur (Module A admin, Module B analyste SOC), API provisionnement, Ansible | L0 à L5 |
| L8 — PLG + OpenTofu | Landing page PLG, API PLG (inscription, quotas, plans), agent PLG (garble + watermark), OpenTofu souverain | L0 à L7 |

L'ordre de réalisation garantit que chaque lot s'appuie sur un socle validé. Le Lot 6 (Tests) est transversal : il vérifie les lots L0 à L5 en conditions réalistes avant que L7 et L8 y ajoutent des couches applicatives.

---

### 3.6 Modélisation des besoins

#### 3.6.1 Acteurs du système

NEXUS SOC implique quatre acteurs.

**admin_plateforme** (Super Administrateur) est un membre de l'équipe NEXUS SOC. Il crée et gère les tenants, provisionne les agents, consulte les métriques de santé des services, gère la facturation et peut suspendre ou réactiver des abonnements. Il dispose du `BYPASSRLS` sur toutes les tables.

**analyste_soc** est un analyste de sécurité de l'équipe NEXUS SOC. Il trie les alertes cross-tenants, approuve ou refuse les actions SOAR de niveau HIGH, et consulte le tableau de bord MTTD/MTTR par tenant. Il peut lire toutes les données mais ne peut modifier que le statut des actions SOAR.

**dsi_client** est le responsable DSI d'une organisation cliente. Il consulte les alertes et les métriques de sa propre organisation via le portail DSI. Il peut approuver les actions SOAR relevant de son tenant. Il ne voit aucune donnée des autres tenants (filtrage RLS).

**Agent Go** est un acteur système (non humain). Il s'authentifie auprès de l'API via un token d'enrôlement et envoie des lots de télémétrie signés. Il n'a aucun autre accès à l'API.

#### 3.6.2 Cas d'utilisation principaux

**UC-01 — Détecter et répondre à un incident.**
Acteur principal : analyste_soc. L'agent collecte la télémétrie, le pipeline corrèle les événements, le modèle IA calcule le score de risque, le SOAR exécute les actions automatiques (LOW/MEDIUM) et soumet les actions HIGH à validation. L'analyste approuve depuis la console. Le DSI reçoit la notification SMS.

**UC-02 — Provisionner un agent sur un nouveau poste.**
Acteur principal : admin_plateforme. L'administrateur saisit le hostname et l'OS dans la console, choisit la durée de validité du token, et copie le one-liner généré. Il l'exécute sur le poste cible. Le poste s'enrôle automatiquement et apparaît dans la liste des agents du tenant.

**UC-03 — Souscrire à un essai gratuit (PLG).**
Acteur principal : dsi_client (futur). Le DSI accède à la landing page, clique sur "Essai gratuit 30 jours", saisit son email professionnel, le nom de son organisation et son secteur, vérifie son email via le lien reçu, et complète la pré-autorisation bancaire de 0 FCFA. Son tenant est créé et les informations de connexion lui sont affichées.

**UC-04 — Déployer NEXUS SOC sur une infrastructure souveraine.**
Acteur principal : admin_plateforme (architecte NEXUS SOC). L'architecte configure `terraform.tfvars` avec les informations du serveur cible (IP, utilisateur SSH, clé privée, nom de l'institution, domaine). Il exécute `tofu apply`. OpenTofu déploie la pile en 7 étapes SSH, génère les secrets, installe le cron de sauvegarde et vérifie la santé de tous les services.

**UC-05 — Consulter les métriques de sécurité (DSI).**
Acteur principal : dsi_client. Le DSI ouvre le portail HTML dans son navigateur, saisit son token JWT, et consulte : la liste des alertes des 7 derniers jours avec leur statut, le MTTD et MTTR calculés sur la période, et l'état des actions SOAR en cours ou terminées pour son organisation.

**UC-06 — Surveiller la dérive des modèles IA.**
Acteur principal : admin_plateforme. L'administrateur appelle `GET /monitor/drift?days=7` depuis la console. Il consulte le PSI et le glissement σ pour chaque modèle. Si le PSI dépasse 0,25, il déclenche un réentraînement du modèle concerné sur les données récentes.

#### 3.6.3 Matrice acteurs / cas d'utilisation

| Cas d'utilisation | admin_plateforme | analyste_soc | dsi_client | Agent Go |
|-------------------|:----------------:|:------------:|:----------:|:--------:|
| UC-01 Détecter/répondre | Partiel (validation) | Principal | Notifié | Émetteur |
| UC-02 Provisionner agent | Principal | Non | Non | Non |
| UC-03 Essai gratuit PLG | Non | Non | Principal | Non |
| UC-04 Déploiement souverain | Principal | Non | Non | Non |
| UC-05 Métriques DSI | Non | Lecture complète | Son tenant | Non |
| UC-06 Surveiller modèles | Principal | Lecture | Non | Non |

---

*Volume : ~11 pages*

---

## CHAPITRE 2 — ÉTUDE DE L'EXISTANT ET ÉTAT DE L'ART

### 2.1 Concepts fondamentaux

#### Security Operations Center (SOC)

Un Security Operations Center est une équipe — et l'infrastructure qui la supporte — chargée de surveiller en continu les systèmes d'information d'une organisation, de détecter les incidents de sécurité et de coordonner la réponse. Un SOC traite des événements en continu : logs systèmes, alertes réseau, comportements utilisateurs. Ses trois fonctions essentielles sont la détection (identifier qu'un incident se produit), l'analyse (comprendre sa nature et sa gravité) et la réponse (contenir, éradiquer, récupérer).

Un SOC interne suppose au minimum deux analystes de niveau 1 (triage), un analyste de niveau 2 (investigation), un responsable et une plateforme SIEM. Dans la pratique, les organisations qui en ont les moyens y consacrent une équipe de 5 à 15 personnes, un budget logiciel annuel entre 50 000 et 500 000 USD, et des astreintes 24h/24. Le modèle SOC open source et souverain (SOC souverain) mutualise cette infrastructure entre plusieurs clients, chacun bénéficiant de la capacité d'un SOC sans en supporter seul le coût.

#### SIEM — Security Information and Event Management

Un SIEM centralise les journaux d'événements produits par les équipements d'un réseau (serveurs, postes de travail, pare-feux, commutateurs, applications) et les analyse pour détecter des comportements suspects. Il normalise des formats hétérogènes, corrèle des événements dispersés dans le temps et l'espace, et génère des alertes quand une séquence correspond à un pattern d'attaque connu.

Les SIEM classiques (Splunk, IBM QRadar, Microsoft Sentinel) fonctionnent sur des règles : si l'événement A suivi de B dans une fenêtre T, alors alerte. Cette approche détecte bien les attaques connues mais rate les variantes et les comportements lentement déviants. Les SIEM de nouvelle génération intègrent du machine learning (détection d'anomalies) pour couvrir les attaques inconnues.

#### UEBA — User and Entity Behavior Analytics

L'UEBA modélise le comportement habituel de chaque utilisateur et équipement sur une période de référence, puis alerte quand le comportement courant s'écarte significativement de cette baseline. Là où une règle SIEM dit "alerte si plus de 50 exports en une heure", l'UEBA dit "alerte si cet agent exporte plus que d'habitude par rapport à ses propres données des 90 derniers jours". Cette personnalisation réduit les faux positifs sur les utilisateurs dont le rôle implique beaucoup d'exports, tout en détectant des anomalies que les règles statiques manquent.

L'UEBA est particulièrement adapté à la détection de fraude interne : l'employé qui modifie ponctuellement des montants de paie, le comptable qui exporte un jeu de données fiscal complet un vendredi soir, ou le fonctionnaire qui crée cinq comptes en une matinée s'écartent tous de leur propre ligne de base.

#### SOAR — Security Orchestration, Automation and Response

Un SOAR automatise les réponses répétitives aux incidents. Quand un SIEM détecte un ransomware, un analyste doit décider d'isoler le poste, bloquer l'IP source, capturer la mémoire et notifier le RSSI. Ces étapes prennent entre 15 minutes et plusieurs heures selon l'organisation. Un SOAR les exécute en quelques secondes via des playbooks prédéfinis, libérant l'analyste pour les décisions qui requièrent un jugement humain.

Un SOAR bien conçu ne remplace pas l'analyste : il lui soumet les décisions à fort impact (isolation, gel de compte) et exécute seul les actions à faible risque (journalisation, notification SMS). Un SOAR mal calibré peut aggraver un incident — isoler un serveur de production sur un faux positif coûte plus cher que l'alerte elle-même. D'où l'importance des garde-fous et du mode dry_run.

#### EDR — Endpoint Detection and Response

Un EDR est un agent installé sur chaque poste de travail ou serveur, capable de collecter une télémétrie fine (processus, connexions, modifications de fichiers, appels système) et de déclencher des réponses directement sur l'endpoint (tuer un processus, quarantainer un fichier, isoler le poste du réseau). Les EDR modernes (CrowdStrike Falcon, SentinelOne, Microsoft Defender for Endpoint) intègrent du machine learning embarqué et transmettent la télémétrie vers un cloud central pour corrélation.

NEXUS SOC n'est pas un EDR : son agent Go collecte la télémétrie mais n'exécute pas d'actions directement sur le poste. L'isolation réseau, le gel de compte et la capture mémoire sont déclenchés côté serveur via les connecteurs SOAR, non par l'agent lui-même.

#### C2 — Command and Control

Après avoir compromis un système, un attaquant établit un canal de communication vers son infrastructure pour envoyer des instructions et récupérer des données. Ce canal est appelé C2 (Command and Control). Les frameworks C2 modernes (Cobalt Strike, Metasploit, Sliver) utilisent des ports inhabituels (4444, 6667, 1337), du trafic chiffré imitant HTTPS, ou des tunnels DNS pour contourner les pare-feux. La détection des communications C2 est l'un des signaux les plus fiables d'une compromission en cours.

NEXUS SOC détecte les communications C2 par analyse des connexions réseau sortantes vers des ports caractéristiques, via la règle T1071 du pipeline de corrélation.

#### IOC — Indicator of Compromise

Un IOC est un artefact observable qui indique qu'un système a été compromis : hash MD5 ou SHA-256 d'un fichier malveillant, adresse IP d'un serveur C2, nom de domaine associé à un groupe d'attaque, chaîne de caractères spécifique dans un binaire. Les IOC sont partagés entre équipes de sécurité via des formats standardisés (STIX, OpenIOC) et des plateformes comme MISP ou VirusTotal.

NEXUS SOC calcule les hash SHA-256 des processus actifs sur chaque poste et les envoie au serveur pour enrichissement VirusTotal côté centralisé. La clé API VirusTotal reste sur le serveur et n'est jamais exposée sur les postes agents.

#### MITRE ATT&CK

MITRE ATT&CK (Adversarial Tactics, Techniques and Common Knowledge) est une base de connaissances publique des comportements offensifs observés dans des attaques réelles. Elle est structurée en matrices : la matrice Enterprise couvre les environnements Windows, Linux, macOS, Cloud et Mobile.

Chaque entrée de la matrice correspond à une tactique (objectif de l'attaquant : Initial Access, Execution, Persistence, Privilege Escalation, Defense Evasion, Credential Access, Discovery, Lateral Movement, Collection, Command and Control, Exfiltration, Impact) et à des techniques (méthodes concrètes, identifiées par un code T suivi d'un numéro). Par exemple, T1059 est la technique "Command and Scripting Interpreter" dans la tactique Execution : l'attaquant utilise un interpréteur de commandes (PowerShell, bash, Python) pour exécuter du code malveillant.

ATT&CK sert à trois usages dans NEXUS SOC : guider l'écriture des règles de corrélation (chaque règle mappe une technique), mesurer la couverture de détection (7 techniques sur les 8 testées), et catégoriser les incidents dans les alertes et le portail DSI.

---

### 2.2 Panorama de la cybersécurité au Cameroun

#### Menaces documentées

Les cybermenaces au Cameroun ne sont pas théoriques. Plusieurs incidents majeurs ont été documentés entre 2020 et 2024, touchant aussi bien des administrations que des entreprises privées.

Les attaques par rançongiciel constituent la menace la plus visible. Plusieurs administrations africaines francophones ont subi des infections paralysant leurs systèmes pendant plusieurs semaines, avec des demandes de rançon en cryptomonnaie. La non-publication des incidents par les victimes rend difficile une statistique précise, mais les rapports de l'Internet Society Africa et de l'Africa Cybersecurity Report 2023 mentionnent une augmentation de 200 % des attaques contre des cibles africaines entre 2020 et 2023.

Les fraudes internes sur la paie publique constituent une menace spécifique au contexte camerounais. Des audits de la Chambre des Comptes ont mis en évidence des fonctionnaires fantômes (agents décédés ou fictifs restant dans SIGIPES) et des faux mandatements (modification frauduleuse de montants dans les ordres de paiement). Ces fraudes sont possibles en l'absence de système de surveillance comportementale des opérateurs SIGIPES.

Le phishing ciblant les microfinances est documenté depuis 2019. Les attaques visent les agents ayant accès aux systèmes de transfert, en usurpant l'identité de la direction ou d'organismes de régulation (COBAC, BEAC).

L'exfiltration de données fiscales, moins médiatisée, concerne les systèmes ANTILOPE et ceux de la Direction Générale des Impôts. Des accès non autorisés à des données de contribuables ont été signalés dans des rapports internes, sans faire l'objet de poursuites publiques documentées.

#### Cadre légal

La **loi n° 2010/012 du 21 décembre 2010** est le texte fondateur de la réglementation cybersécurité camerounaise. Elle crée les infractions pénales liées à la cybercriminalité (accès non autorisé, usurpation d'identité numérique, fraude informatique), définit les obligations des prestataires de services de communications électroniques, et encadre la collecte et le traitement des données personnelles. Les peines prévues vont de 6 mois à 10 ans d'emprisonnement selon la gravité de l'infraction, et jusqu'à 50 millions de FCFA d'amende pour les personnes morales.

L'**ANTIC** (Agence Nationale des Technologies de l'Information et de la Communication) est l'autorité réglementaire chargée d'homologuer les systèmes d'information sensibles, de certifier les prestataires de services de cybersécurité, et de traiter les incidents signalés. Elle a lancé en 2022 le programme de certification des auditeurs en sécurité des SI, mais le nombre de professionnels certifiés reste très limité. L'ANTIC dispose d'un Computer Emergency Response Team (CERT-Cameroun) opérationnel depuis 2019.

La **loi n° 2022/015 du 27 juillet 2022** portant code général des collectivités territoriales décentralisées intègre des dispositions sur la protection des données des collectivités. Elle renforce les obligations des administrations locales en matière de sécurité des SI, un périmètre pertinent pour les communes qui déploient des systèmes de gestion budgétaire.

Au niveau sous-régional, la **Directive CEMAC n° 01/17** sur la dématérialisation des paiements impose aux établissements de crédit de la zone CEMAC (dont les microfinances agréées COBAC) de mettre en place des dispositifs de surveillance des transactions.

#### Pénurie de compétences

Le Cameroun forme chaque année plusieurs centaines d'ingénieurs en informatique et réseaux, mais très peu en cybersécurité opérationnelle. Les formations spécialisées (CISSP, CEH, OSCP) sont quasi absentes des cursus locaux. La grande majorité des professionnels de la sécurité qui exercent au Cameroun sont autodidactes ou ont été formés lors de missions à l'étranger. Cette pénurie est le facteur limitant principal à l'adoption de solutions comme Wazuh : l'outil est gratuit, mais il est inexploitable sans compétences internes.

---

### 2.3 État de l'art des solutions existantes

#### Wazuh

Wazuh est une plateforme open-source de détection d'intrusion et de monitoring de la conformité, issue d'un fork d'OSSEC. Elle comprend un manager central, des agents déployés sur les endpoints, un indexeur (OpenSearch) pour stocker les événements, et un dashboard de visualisation.

Wazuh détecte les intrusions par règles (plus de 3 000 règles préconfigurées couvrant Linux, Windows, AWS, Docker), surveille l'intégrité des fichiers (FIM — File Integrity Monitoring), gère les vulnérabilités connues par CVE, et produit des rapports de conformité PCI-DSS, HIPAA et GDPR.

Ses forces sont réelles : gratuit, open-source, installable sur site (pas de cloud tiers), communauté active, couverture large des systèmes courants.

Ses limites dans le contexte camerounais sont tout aussi réelles. Wazuh ne dispose pas de modèles d'IA pour la détection d'anomalies comportementales. Son installation et sa maintenance requièrent deux à trois ingénieurs avec une connaissance approfondie d'OpenSearch, Linux et des règles Sigma/Wazuh. Il n'a pas d'interface en français, pas de connecteur SOAR intégré, pas de module UEBA, et pas de mécanisme de mutualisation multi-tenant natif pour une offre SOC souverain. Wazuh seul ne répond pas à la problématique d'une microfinance qui n'a pas d'équipe sécurité.

#### CrowdStrike Falcon

CrowdStrike Falcon est la plateforme EDR et SIEM cloud leader du marché. Son agent kernel-level collecte une télémétrie très fine, son moteur IA propriétaire détecte les menaces connues et inconnues, et son cloud Threat Graph corrèle les événements de millions d'endpoints dans le monde. Son temps moyen de détection mesuré est inférieur à une minute.

Pour les organisations qui peuvent se le permettre, CrowdStrike est très efficace. Mais ses tarifs (400 à 800 USD par agent et par an) placent une administration camerounaise de 200 postes face à une facture annuelle de 80 000 à 160 000 USD, payable en dollars, vers un prestataire américain. Toute la télémétrie est hébergée dans les data centers de CrowdStrike aux États-Unis. L'interface est uniquement en anglais. Il n'existe aucun partenaire revendeur certifié au Cameroun. La conformité ANTIC est impossible à obtenir avec une solution hébergeant les données hors territoire.

#### Splunk SIEM

Splunk est le SIEM de référence des grandes entreprises et administrations. Sa Search Processing Language (SPL) permet des requêtes analytiques très puissantes sur des volumes de données massifs. Splunk Enterprise Security ajoute une couche SOC avec gestion des incidents, des tableaux de bord de conformité et une intégration SOAR (Splunk SOAR, ex-Phantom).

Son coût d'entrée (entre 10 000 et 50 000 USD par an selon le volume ingéré) est prohibitif pour les organisations camerounaises. Sa complexité de déploiement et d'administration — il faut des ingénieurs certifiés Splunk pour en tirer parti — le rend inutilisable sans une équipe dédiée. Comme CrowdStrike, Splunk héberge tout dans le cloud américain par défaut.

#### SentinelOne

SentinelOne est un concurrent direct de CrowdStrike sur le marché EDR. Son approche repose sur un modèle IA embarqué dans l'agent (autonomous AI), capable de décider en quelques millisecondes de neutraliser un processus malveillant sans connexion au cloud. C'est un avantage dans des environnements déconnectés, mais le produit n'est disponible qu'en cloud américain, à des tarifs similaires à CrowdStrike (200 à 500 USD par agent/an). Aucune offre africaine, aucun support en français.

#### Microsoft Defender for Endpoint

Microsoft Defender for Endpoint est intégré à Windows 10/11 et Server 2016+, ce qui en fait la solution EDR la plus déployée de fait sur les parcs Windows. Il est inclus dans les licences Microsoft 365 Business Premium et E5. Son score de détection dans les benchmarks indépendants (AV-TEST, MITRE ATT&CK Evaluations) est élevé.

Pour les organisations camerounaises sous Microsoft 365, Defender est un point de départ. Mais il ne couvre pas Linux, ne fournit pas de SIEM ni de SOAR, et envoie les données vers le cloud Microsoft (Azure Europe ou Americas). Une conformité ANTIC sur cette base est incertaine.

#### Tableau comparatif

| Critère | Wazuh | CrowdStrike | Splunk | SentinelOne | NEXUS SOC |
|---------|-------|-------------|--------|-------------|-----------|
| Prix | Gratuit | 400–800 USD/agent/an | 10–50 k USD/an | 200–500 USD/agent/an | 25–200 k FCFA/mois |
| Hébergement | On-premise | Cloud USA | Cloud USA/EU | Cloud USA | Local (souverain) |
| Interface FR | Non | Non | Non | Non | Oui |
| UEBA / IA | Non | Oui (propriétaire) | Partiel (plugin) | Oui (embarqué) | Oui (Isolation Forest) |
| SOAR intégré | Non | Oui (Falcon Fusion) | Oui (Splunk SOAR) | Partiel | Oui (playbooks + garde-fous) |
| Multi-tenant natif | Non | Non | Non | Non | Oui (RLS PostgreSQL) |
| PLG / self-service | Non | Non | Non | Non | Oui |
| Déploiement souverain OpenTofu | Non | Non | Non | Non | Oui |
| Adaptation SIGIPES/ANTILOPE | Non | Non | Non | Non | Oui (Modèle 2) |
| Compétences requises | Élevées | Élevées | Très élevées | Élevées | Faibles (clé en main) |

---

### 2.4 Étude critique de l'existant

Les solutions analysées présentent toutes au moins l'un de ces trois obstacles pour le contexte camerounais : le coût, la souveraineté des données, ou la complexité d'exploitation.

**Sur le coût.** CrowdStrike, Splunk et SentinelOne sont tarifés pour des entreprises occidentales de taille moyenne à grande. Une microfinance de 30 postes à Bafoussam ne peut pas régler 15 000 USD par an en devises étrangères pour un outil de sécurité. Et même si elle le pouvait, son équipe informatique de deux personnes ne saurait pas l'exploiter. Wazuh résout le problème du coût logiciel mais pas celui des compétences.

**Sur la souveraineté.** Toutes les solutions commerciales envoient la télémétrie vers des serveurs américains ou européens. Pour les administrations publiques camerounaises, cette situation pose deux problèmes : les exigences de souveraineté numérique de l'État et la conformité ANTIC, qui soumet les systèmes d'information sensibles à homologation locale. Il n'existe pas de version on-premise de CrowdStrike ou SentinelOne pour les clients non éligibles aux offres GovCloud américaines.

**Sur l'adaptation locale.** SIGIPES et ANTILOPE ont des patterns d'utilisation spécifiques que les modèles génériques ne captent pas. Un modèle UEBA entraîné sur des données de Silicon Valley ne sait pas que les agents de la Direction Générale du Budget au Cameroun effectuent légitimement un grand nombre de modifications de mandatements en fin de trimestre budgétaire. Il générera des faux positifs massifs. Un modèle calibré sur ces données, avec connaissance des rythmes administratifs locaux, peut établir une ligne de base pertinente.

**Sur la mutualisation.** Aucune des solutions existantes n'est conçue pour un modèle SOC souverain à l'africaine : une seule équipe technique opérant pour plusieurs dizaines de clients, facturation en FCFA, inscription self-service sans commercial. Wazuh peut être déployé pour plusieurs clients, mais l'isolation des données entre clients repose sur une configuration manuelle et des instances séparées, pas sur un mécanisme natif comme la RLS.

**Sur la langue.** Les interfaces en anglais uniquement constituent un obstacle réel pour les équipes DSI des administrations francophones. Les rapports d'incident en anglais qu'un directeur financier doit transmettre au ministre ne sont pas acceptables. Un SOC opérant en français, produisant des alertes et des rapports en français, réduit la friction entre l'équipe technique et la direction.

La conclusion de cette analyse est que les solutions existantes répondent bien aux besoins des grandes organisations occidentales, mais qu'aucune ne satisfait simultanément les quatre contraintes du contexte camerounais : coût accessible en FCFA, hébergement local, interface en français, et adaptation aux systèmes administratifs locaux.

---

### 2.5 Reformulation de la problématique et des besoins

L'étude de l'existant confirme et précise la problématique posée en introduction.

Il n'existe pas de solution SOC adaptée aux organisations camerounaises de taille moyenne. La cause n'est pas technique — la technologie open-source (Wazuh, Kafka, PostgreSQL, scikit-learn) est suffisante pour construire une plateforme de niveau enterprise. La cause est d'assemblage et d'adaptation : personne n'a encore assemblé ces briques en un système clé-en-main, calibré pour le contexte camerounais, opérable sans équipe de 10 ingénieurs certifiés.

NEXUS SOC répond à ce manque par trois choix structurants. D'abord, le modèle mutualisé (SOC souverain) : une seule instance héberge plusieurs clients avec isolation stricte, réduisant les coûts d'infrastructure. Ensuite, l'automatisation par IA et SOAR : le système détecte et répond sans analyste permanent, compensant la pénurie de compétences. Enfin, la souveraineté et l'adaptation locale : hébergement sur infrastructure camerounaise, modèles entraînés sur des patterns SIGIPES/ANTILOPE, interface en français.

Ces trois choix génèrent les besoins fonctionnels et non-fonctionnels détaillés au Chapitre 3.

---

*Volume : ~12 pages*

---

## CHAPITRE 1 — PRÉSENTATION DU CADRE DU STAGE

### 1.1 Présentation de la structure d'accueil

#### Identité et missions du CENADI

Le CENADI du Cameroun (CENADI) est l'administration centrale responsable de la conception, de la mise en œuvre et du suivi de la politique financière et budgétaire de l'État. Il est placé sous l'autorité directe de la Présidence de la République pour les questions budgétaires, et coordonne ses actions avec le Ministère de l'Économie pour les aspects liés à la planification.

Les missions du CENADI couvrent cinq domaines principaux. La **gestion du budget de l'État** : préparation de la loi de finances annuelle, suivi de l'exécution budgétaire, contrôle des dépenses des ministères sectoriels. La **collecte des recettes fiscales** : via la Direction Générale des Impôts (DGI), qui administre les impôts directs et indirects, la TVA, et les taxes sur les revenus. La **gestion douanière** : via la Direction Générale des Douanes (DGD), qui contrôle les flux de marchandises aux frontières et collecte les droits de douane. La **trésorerie de l'État** : via la Direction Générale du Trésor et de la Coopération Financière et Monétaire (DGTCFM), qui gère les flux de trésorerie et la dette publique. La **gestion des ressources humaines de l'État** : via le système SIGIPES, qui centralise la paie de l'ensemble des fonctionnaires camerounais.

Le CENADI emploie plusieurs milliers d'agents répartis sur l'ensemble du territoire national. Son siège est situé à Yaoundé, place du gouvernement.

#### Systèmes d'information critiques

Deux systèmes d'information font du CENADI une cible prioritaire en matière de cybersécurité.

**SIGIPES** (Système Intégré de Gestion des Personnels de l'État et de la Solde) gère la paie de l'ensemble des fonctionnaires camerounais. Il centralise les fichiers de personnel de tous les ministères, calcule les salaires, génère les ordres de paiement et produit les bulletins de paie. Une compromission de SIGIPES — modification de montants, création de comptes fantômes, exfiltration du fichier des agents — aurait des conséquences directes sur les finances publiques et sur la vie privée des fonctionnaires.

**ANTILOPE** (SYstème DOuaNier Automatisé) est le système de dédouanement automatisé utilisé par la Direction Générale des Douanes. Il traite les déclarations en douane, calcule les droits et taxes, et pilote les procédures de dédouanement aux postes frontières. ANTILOPE contient des données commerciales confidentielles sur les importateurs et exportateurs. Des accès non autorisés peuvent faciliter la fraude douanière ou exposer des informations fiscales sensibles.

À ces deux systèmes s'ajoutent l'application de gestion budgétaire DEPMI, les plateformes de paiement électronique intégrées à la trésorerie, et les outils de reporting financier à destination des institutions de Bretton Woods.

#### Enjeux de sécurité

La concentration de données financières et personnelles dans les systèmes du CENADI en fait une cible de premier plan. Trois catégories de menaces sont particulièrement pertinentes.

Les menaces internes constituent le risque le plus documenté : agents accédant à des données hors de leur périmètre de compétence, modifications frauduleuses de montants dans SIGIPES, création de fonctionnaires fantômes. Ces comportements sont difficiles à détecter sans système de surveillance comportementale car ils exploitent des accès légitimes.

Les attaques ciblées depuis l'extérieur visent à compromettre des comptes à privilèges pour accéder aux bases de données de SIGIPES ou ANTILOPE. Des campagnes de phishing ciblant des agents du CENADI ont été signalées, usurpant l'identité du secrétariat général ou de la DGI.

La fraude aux virements est une menace hybride : un attaquant compromet un compte d'opérateur de la trésorerie pour modifier des instructions de paiement et rediriger des fonds publics.

---

### 1.2 Service d'accueil et organisation

#### Direction d'accueil

Le stage s'est déroulé au sein de la **Direction des Systèmes d'Information** (DSI) du CENADI, rattachée au Secrétariat Général. La DSI est responsable de la conception, du déploiement et de la maintenance de l'ensemble des systèmes d'information du ministère, incluant SIGIPES, ANTILOPE, les infrastructures réseau et les plateformes de messagerie.

#### Organisation simplifiée de la DSI

```
Secrétariat Général du CENADI
└── Direction des Systèmes d'Information (DSI)
    ├── Sous-Direction de l'Ingénierie et des Applications
    │   ├── Service Développement et Maintenance Applicative
    │   └── Service Bases de Données
    ├── Sous-Direction des Infrastructures et de la Sécurité
    │   ├── Service Infrastructure Réseau et Systèmes
    │   └── Service Sécurité des Systèmes d'Information
    └── Sous-Direction de l'Assistance et de la Formation
        ├── Service Support Utilisateurs
        └── Service Formation et Documentation
```

*Figure 1.1 — Organigramme simplifié de la DSI du CENADI (schéma à insérer dans la version finale)*

Le stage s'est déroulé principalement au sein du **Service Sécurité des Systèmes d'Information** (SSSI), en collaboration avec le Service Infrastructure Réseau pour les captures de trafic réseau et le Service Bases de Données pour l'accès aux journaux d'audit SIGIPES.

Le SSSI est composé de cinq agents : un chef de service, deux ingénieurs sécurité et deux techniciens. À l'arrivée en stage, le service ne disposait pas de SIEM ni d'outil de détection d'intrusion automatisé. La surveillance se limitait à l'analyse manuelle des logs système par les ingénieurs, une à deux fois par semaine.

---

### 1.3 Déroulement et planning du stage

#### Phases du stage

Le stage s'est déroulé du 4 mai au 31 juillet 2026, soit trois mois. Il a été organisé en quatre phases successives.

**Phase 1 — Intégration et découverte (semaines 1 et 2, 4–15 mai 2026).** Prise de contact avec l'équipe, signature des documents de confidentialité, accès au réseau de développement du SSSI, découverte des systèmes SIGIPES et ANTILOPE (démonstrations fonctionnelles, documentation technique), et analyse des journaux d'événements existants pour comprendre les volumes et formats de données.

**Phase 2 — Analyse et adaptation des modèles IA (semaines 3 à 6, 18 mai–12 juin 2026).** Extraction des journaux d'audit SIGIPES sur la période janvier–avril 2026 (anonymisés), analyse statistique des distributions comportementales des agents, adaptation du Modèle 2 (UEBA) aux features spécifiques à SIGIPES, entraînement sur les données réelles et calibration du seuil de détection.

**Phase 3 — Tests d'intégration et simulation d'attaques (semaines 7 à 10, 15 juin–10 juillet 2026).** Déploiement de NEXUS SOC sur un environnement de test isolé du réseau de développement DSI, enrôlement de cinq postes Windows du SSSI sur la plateforme, exécution de simulations d'attaques Atomic Red Team sur le réseau de test (avec autorisation écrite de la direction), validation des connecteurs SOAR (notification SMS, journalisation), et initiation des démarches de déclaration auprès de l'ANTIC.

**Phase 4 — Documentation et soutenance interne (semaines 11 à 13, 13–31 juillet 2026).** Rédaction des livrables du stage (rapport technique CENADI, guide d'exploitation), présentation des résultats devant l'équipe de la DSI, et transmission des recommandations pour une mise en production progressive.

#### Diagramme de Gantt

*Tableau 1.1 — Planning du stage (diagramme de Gantt à insérer dans la version finale)*

| Tâche | Mai S1 | Mai S2 | Mai S3 | Mai S4 | Juin S1 | Juin S2 | Juin S3 | Juin S4 | Juil S1 | Juil S2 | Juil S3 |
|-------|--------|--------|--------|--------|---------|---------|---------|---------|---------|---------|---------|
| Intégration / accès | ████ | ████ | | | | | | | | | |
| Analyse journaux SIGIPES | | | ████ | ████ | | | | | | | |
| Adaptation Modèle 2 (UEBA) | | | | ████ | ████ | ████ | | | | | |
| Déploiement environnement test | | | | | | | ████ | ████ | | | |
| Simulations Atomic Red Team | | | | | | | | ████ | ████ | | |
| Démarches ANTIC | | | | | | | | | ████ | ████ | |
| Rédaction livrables + soutenance | | | | | | | | | | ████ | ████ |

---

### 1.4 Cahier des charges du stage

#### Mission confiée

La DSI du CENADI a confié au stagiaire la mission suivante : évaluer la faisabilité du déploiement d'une plateforme de détection d'intrusion et de surveillance comportementale sur l'infrastructure du ministère, en prenant comme base le prototype NEXUS SOC développé dans le cadre du projet de fin d'études.

Cette mission s'inscrit dans la volonté de la DSI de se doter d'un outil de détection des anomalies comportementales dans SIGIPES, en réponse aux recommandations formulées par la Chambre des Comptes dans son rapport 2024 sur les risques de fraude à la paie publique.

#### Livrables attendus

| # | Livrable | Échéance |
|---|----------|----------|
| L1 | Rapport d'analyse des journaux SIGIPES (anonymisés) : distribution statistique des 10 features UEBA, identification des patterns légitimes propres au CENADI | 13 juin 2026 |
| L2 | Modèle 2 recalibré sur données SIGIPES réelles, avec rapport de métriques (ROC-AUC, taux de faux positifs, courbe PR) | 30 juin 2026 |
| L3 | Rapport de simulation d'attaques sur réseau de test DSI : 5 scénarios minimum, résultats de détection NEXUS SOC, MTTD mesuré | 15 juillet 2026 |
| L4 | Guide d'exploitation NEXUS SOC pour la DSI : procédure de déploiement, provisionnement des agents, interprétation des alertes, escalade | 25 juillet 2026 |
| L5 | Note de recommandation pour l'ANTIC : périmètre de déclaration, classification des données traitées, mesures de protection en place | 30 juillet 2026 |

#### Contraintes spécifiques au CENADI

Le stage s'est déroulé sous contraintes strictes d'accès aux données. Tous les journaux SIGIPES utilisés pour l'entraînement du modèle ont été anonymisés par le service informatique avant leur remise (noms remplacés par des identifiants numériques, montants arrondis à la dizaine la plus proche). Aucune donnée nominative d'agent fonctionnaire ne figure dans les jeux de données d'entraînement.

Les simulations d'attaques Atomic Red Team ont été réalisées sur un réseau de test physiquement isolé du réseau de production CENADI, avec autorisation écrite du Directeur des Systèmes d'Information datée du 14 juin 2026.

Le déploiement sur le réseau de production du CENADI n'a pas été réalisé dans le cadre du stage. Il est conditionné à l'obtention de l'homologation ANTIC, dont la démarche a été initiée mais non finalisée à la date de clôture du stage.

---

*Volume : ~7 pages*
