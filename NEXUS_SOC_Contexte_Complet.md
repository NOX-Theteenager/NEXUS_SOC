CONTEXTE COMPLET DU PROJET NEXUS SOC

Ce document est un prompt de reprise complet. Il contient absolument tout ce dont
tu as besoin pour continuer le développement ou rédiger le rapport de soutenance.
Lis-le en entier avant de répondre à quoi que ce soit.

═══════════════════════════════════════════════════════════════════════════════════
SECTION 1 — IDENTITÉ DU PROJET
═══════════════════════════════════════════════════════════════════════════════════

Nom exact         : NEXUS SOC
Sous-titre        : Plateforme SOC-as-a-Service souveraine pour le Cameroun
Acronyme          : NEXUS = Network Endpoint eXtended Unified Security (rétro-acronyme)
Thème académique  : Cybersécurité — détection d'intrusion, réponse aux incidents, IA appliquée

Problème résolu   :
  Les administrations publiques et PME financières du Cameroun n'ont pas les ressources
  humaines (analystes SOC rares), financières (Splunk > 10 M FCFA/an) ni l'expertise
  pour déployer un SOC interne. Elles restent donc sans supervision de sécurité.

Vision en une phrase :
  « Offrir à chaque organisation camerounaise, quelle que soit sa taille, une capacité
  de détection et de réponse aux incidents de niveau enterprise — mutualisée,
  souveraine, abordable, et expliquée en français. »

Positionnement :
  vs CrowdStrike Falcon : 400–800 $/agent/an, cloud USA, pas souverain, pas de version
    francophone, trop cher pour les microfinances camerounaises.
  vs Splunk SIEM : 10–50 M FCFA/an, nécessite 3 ingénieurs certifiés, zéro adaptation
    au contexte africain.
  vs SentinelOne : idem CrowdStrike, cloud américain, pas accessible au Cameroun.
  vs Wazuh seul : open-source gratuit, mais nécessite compétences internes, pas de
    mutualisation, pas de modèles IA, pas de restitution bilingue, pas de SOAR.
  NEXUS SOC unique car : mutualisé (SOCaaS), hébergement local (souveraineté),
    modèles IA adaptés au contexte SIGIPES/SYDONIA, bilingue FR/EN, prix FCFA.

═══════════════════════════════════════════════════════════════════════════════════
SECTION 2 — CONTEXTE ACADÉMIQUE
═══════════════════════════════════════════════════════════════════════════════════

Nom complet         : NGUETSA Junior Stéphane Céleste
Email               : celestenguetsa@gmail.com
École               : KEYCE Informatique & IA
Ville               : Yaoundé, Cameroun
Filière             : Réseaux et Systèmes Informatiques (RSI)
Niveau              : Bachelor 3 (Bac+3)
Soutenance visée    : 24 août 2026

Stage :
  Institution  : MINFI — Ministère des Finances du Cameroun
  Période      : Mai–Juillet 2026 (3 mois)
  Lieu         : Yaoundé

Ce que l'étudiant peut observer et réaliser pendant le stage MINFI :
  1. Adapter le Modèle 1 (anomalie réseau) aux vraies données réseau du MINFI
     (captures NetFlow ou PCAP sur le LAN ministériel)
  2. Adapter le Modèle 2 (fraude UEBA) aux vraies données d'audit SIGIPES
     (journaux d'activité des agents de la Direction Générale du Budget)
  3. Tester les connecteurs SOAR réels (annuaire LDAP/AD du MINFI, pare-feu périmétrique)
  4. Valider la procédure d'enrôlement des agents sur des postes Windows réels
  5. Initier la démarche de conformité ANTIC (déclaration du système)
  6. Effectuer des simulations d'attaques Atomic Red Team sur un réseau de test
  7. Documenter les incidents réels observés pendant le stage pour alimenter le rapport

═══════════════════════════════════════════════════════════════════════════════════
SECTION 3 — PÉRIMÈTRE ET CIBLES
═══════════════════════════════════════════════════════════════════════════════════

CIBLE PRINCIPALE — Administrations publiques camerounaises :
  Types       : Ministères, Directions Générales, Agences d'État, régies financières
  Exemples    : MINFI, DGI (Direction Générale des Impôts), DGCOOP, DGD (Douanes)
  Taille      : 50 à 500 postes surveillés
  Offre       : Contrat public annuel + hébergement souverain dédié
  Motivation  : Souveraineté numérique, conformité loi 2010/012, détection fraudes
                internes (fonctionnaires fantômes, faux mandatements)

CIBLE SECONDAIRE — Secteur financier non bancaire :
  Microfinances (régulation COBAC — Afrique Centrale)
  Assurances (code CIMA)
  Cabinets comptables (ONECCA — Cameroun)
  Taille      : 5 à 100 postes
  Offres      : Starter / Business / Enterprise (abonnement mensuel en FCFA)

HORS PÉRIMÈTRE (explicitement abandonné) :
  Fraude Mobile Money MTN/Orange : domaine régulé par la BEAC, nécessite accords
  opérateurs, données propriétaires. Décision prise en début de projet et non réversible.
  Banques commerciales (régulation COBAC banques — trop complexe pour le démonstrateur)
  Particuliers / utilisateurs finaux

CADRE JURIDIQUE CAMEROUNAIS APPLICABLE :
  Loi n° 2010/012 du 21 décembre 2010 relative à la cybersécurité et à la
    cybercriminalité au Cameroun (article principal).
  ANTIC — Agence Nationale des TIC : autorité réglementaire, homologation des SIEM.
  COBAC — Commission Bancaire de l'Afrique Centrale : microfinances.
  CIMA — Code des Assurances : assurances zone CIMA.
  ONECCA — Ordre National des Experts Comptables : cabinets comptables.
  ISO/IEC 27001 : cadre international SMSI utilisé comme référence de contrôle.
  RGPD : cité pour comparaison des bonnes pratiques (non applicable directement).

═══════════════════════════════════════════════════════════════════════════════════
SECTION 4 — ARCHITECTURE TECHNIQUE COMPLÈTE
═══════════════════════════════════════════════════════════════════════════════════

COMPOSANT 1 — Agent léger de collecte (Lot 1)
  Nom          : nexus-agent (binaire Go)
  Rôle         : Collecte la télémétrie endpoint sur chaque poste/serveur surveillé
                 et l'envoie vers la passerelle /ingest du serveur NEXUS SOC.
  Technologies : Go 1.21+ — pur stdlib (aucune dépendance externe)
  Fichiers     : nexus-agent.zip contenant main.go, collect.go, buffer.go, sender.go
  Justification: Pur stdlib → binaire unique sans runtime, compilation offline possible,
                 pas de CVE dans les dépendances. Taille mesurée 5.0 Mo Linux / 5.3 Mo Windows.
  Ce que collecte l'agent (toutes les 30 s) :
    - Processus actifs : nom, PID, chemin, empreinte SHA-256 (mise en cache)
    - Connexions réseau : proto, adresse locale/distante, état (depuis /proc/net/tcp)
    - Fichiers modifiés : chemin, taille (scrutation des répertoires surveillés)
    - État système : hostname, OS, arch, uptime, charge
  Mécanismes de sécurité de l'agent :
    - Egress-only HTTPS (aucun port entrant, fonctionne derrière tout pare-feu)
    - Compression gzip du payload (économie ~70 % bande passante)
    - Signature HMAC-SHA256 de chaque lot (intégrité/authenticité)
    - Bearer token d'enrôlement (authentification au serveur)
    - Store-and-forward : file locale persistante bornée (queue_max_mb configurable)
      → les lots sont conservés et rejoués si le serveur est injoignable
    - VirusTotal côté serveur (l'agent calcule les hashes, l'enrichissement est centralisé)
  Configuration (config.json sur le poste) :
    server_url, enroll_token, hmac_key, agent_id, tenant_id, hostname,
    interval_sec (défaut 30), watch_dirs (liste), queue_dir, queue_max_mb (défaut 50)
  Interactions : envoie vers scoring-service:8000/ingest → Kafka → Pipeline

COMPOSANT 2 — Pipeline SIEM : Normalisation + Corrélation (Lot 2)
  Nom          : nexus-pipeline (Python)
  Fichiers     : nexus-pipeline.zip contenant normalizer.py, correlation_engine.py,
                 correlation_engine_v2.py (version corrigée O(N)), telemetry_gen.py
  Rôle         : Normalise la télémétrie brute vers un schéma ECS-like, extrait des
                 features comportementales d'hôte, puis corrèle les événements pour
                 reconstituer des chaînes d'attaque MITRE ATT&CK.
  Technologies : Python 3.10+, bibliothèque standard (collections, datetime, json)
  Règles SIEM actuelles (correlation_engine_v2.py) :
    T1059 — Command and Scripting Interpreter (processus suspects, répertoire /tmp)
    T1071 — Application Layer Protocol (connexion vers ports C2 : 4444, 6667, 1337…)
    T1005 — Data from Local System (accès fichiers sensibles : shadow, passwd, budget…)
    T1204 — User Execution: Malicious File (fichier .exe/.bat dans Downloads)
    T1486 — Data Encrypted for Impact (>20 fichiers modifiés en <5 min — ransomware)
    T1027 — Obfuscated Files or Information (base64 inline, double extension, iex()…)
    T1136 — Create Account (useradd, net user /add, création en masse >5 en 10 min)
    T1083 — File and Directory Discovery (accès /etc/, /proc/, HKLM, SAM…)
  Critère de levée d'incident : ≥ 3 tactiques distinctes OU Execution+C2 OU Impact
                                 OU Defense Evasion+Persistence
  Fenêtre de corrélation : 30 min (configurable via CORR_WINDOW_MIN)
  Bug O(N²) corrigé en v2 : detect_mass_file_change passe de O(N²) à O(N)
    via algorithme à deux pointeurs (chaque événement visité une seule fois).
  Interactions : consomme depuis Kafka → produit incidents → SOAR + base de données

COMPOSANT 3 — Modèles IA (Lot 3)
  Voir Section 5 — Modèles IA entraînés.

COMPOSANT 4 — SOAR : Réponse Automatisée (Lot 4)
  Nom          : soar_engine.py
  Rôle         : Réponse aux incidents via playbooks avec garde-fous (seuils, validation
                 humaine, rollback). Les connecteurs sont SIMULÉS dans le démonstrateur.
  Technologies : Python 3.10+, bibliothèque standard
  9 connecteurs (simulés) :
    freeze_account, isolate_host, block_ip, reset_password, snapshot_memory,
    notify_sms, notify_whatsapp, journal_investigation, preserve_logs
  4 playbooks par type d'incident :
    Fraude interne    : journal_investigation → notify_sms → freeze_account → preserve_logs
    Exfiltration      : journal_investigation → freeze_account → block_ip → notify_sms
    Ransomware        : snapshot_memory → isolate_host → block_ip → notify_sms
    Anomalie réseau/C2: journal_investigation → block_ip → notify_sms
  Niveaux d'impact des actions :
    LOW    : journal_investigation, preserve_logs, notify_sms, notify_whatsapp
    MEDIUM : snapshot_memory, block_ip, reset_password
    HIGH   : freeze_account, isolate_host
  Paramètres du moteur (SOAREngine) :
    dry_run=True          : mode simulation par défaut (aucune action exécutée)
    auto_threshold=70     : seuil de risque pour l'auto-exécution
    auto_exec_max_impact=MEDIUM : impact max exécuté automatiquement
    HIGH toujours en attente de validation humaine
  Méthodes clés :
    engine.handle(alert)         : exécute le playbook
    engine.approve(id, key, who) : valide une action HIGH en attente
    engine.rollback(id, by)      : annule les actions réversibles
  Journal d'audit : audit_log.csv (qui, quoi, quand, statut)
  Interactions : reçoit alertes de scoring-service → produit actions → notifications

COMPOSANT 5 — LLM Analyst + Restitution bilingue (Lot 5)
  Nom          : nexus-portail (portail client DSI) + notifier.py (LLM Analyst)
  Fichiers     : nexus-portail.zip contenant portail/portal/index.html + notifier.py
  Rôle         : Expliquer les incidents en langage clair FR/EN, notifier par SMS
                 et WhatsApp, afficher le portail DSI.
  LLM Analyst — deux modes :
    Mode template (défaut) : explication déterministe sans LLM, sans hallucination,
      3–5 phrases factuelles dans la langue choisie. C'est la voie nominale.
    Mode llm (optionnel) : Mistral 7B ou Llama via API compatible OpenAI (Ollama/vLLM).
      Activé via variable d'env OLLAMA_BASE_URL. Désactivé par défaut.
  Notifications :
    SMS : court, max 160 car. ex. "🚨 NEXUS SOC — Rançongiciel sur POSTE-COMPTA-07
          · risque 100/100. Action : isoler."
    WhatsApp : rapport hebdomadaire structuré (score, incidents, conseils, lien rapport).
               ⚠ hors fenêtre 24h → templates Meta requis (contrainte déploiement).
  Portail DSI (Lot 5) :
    Fichier : portail/portal/index.html — HTML/CSS/JS autonome, aucun serveur requis.
    Design  : mode sombre ops center, Fraunces + Manrope + JetBrains Mono.
    Contenu : score de sécurité, incidents actifs, agents surveillés, kill-chain
              colorée par tactique MITRE, citations LLM Analyst en serif italique.
    Bascule FR/EN instantanée. VUE CLIENT UNIQUEMENT (un tenant).
  Interactions : reçoit incidents du SOAR, génère explications, envoie notifications

COMPOSANT 6 — Console Fournisseur / Command Center (Lot 7)
  Nom          : console_fournisseur.html
  Rôle         : Interface web de l'opérateur NEXUS SOC — supervise TOUS les tenants
                 simultanément. Séparée du portail client.
  Fichier      : Lot7_Console_Fournisseur/console_fournisseur.html (2912 lignes)
  Technologies : HTML/CSS/JS autonome, QRCode.js (CDN), JSZip (CDN)
  Module A — Administration (admin_plateforme) :
    Tableau de bord global : 4 KPIs cross-tenants (tenants actifs, agents en ligne,
      incidents ouverts, disponibilité), résumé tenants, fil d'activité récente.
    Tenants : CRUD complet (créer/modifier/suspendre/réactiver), filtres par type.
    Utilisateurs : liste RBAC cross-tenants, filtres par tenant/rôle, création.
    Agents : liste cross-tenants, provisioning enrichi (voir Section 7).
    Santé système : 6 cartes services avec métriques 24h.
    Facturation : ARR/MRR estimés, détail abonnements FCFA par tenant.
  Module B — Poste Analyste SOC (analyste_soc) :
    File d'alertes : 5 alertes de démo, cartes colorées par niveau de risque (100→rouge,
      60→amber, 40→bleu, <40→teal), kill-chain MITRE inline, filtres multi-critères.
    Modal détail alerte : explication LLM Analyst (Fraunces italique), kill chain
      expandée, raisons σ, actions SOAR disponibles, bouton faux positif.
    Approbation SOAR : file d'actions en attente (isolate_host, freeze_account,
      block_ip), cartes avec contexte, boutons Approuver/Refuser/Rollback.
    Tableau de bord SOC : 3 KPIs SOC, barres CSS MTTD par tenant, résolutions
      récentes, graphique d'activité 7 jours en CSS pur.

COMPOSANT 7 — Service de Scoring IA + API (Lot 1 + Lot 7)
  Fichier principal : Lot1_Agent_Go/scoring-service_app.py (374 lignes, version v2)
  FastAPI — endpoints :
    POST /ingest         : passerelle sécurisée (Bearer + HMAC validés, rate limit 30/min)
    POST /score/network  : scorer un flux réseau via Modèle 1
    POST /score/user-day : scorer un profil agent-jour via Modèle 2
    GET  /health         : healthcheck rapide (Docker-friendly)
    GET  /health/detailed: vérifie Kafka, TimescaleDB, Wazuh Indexer en temps réel
  Modules complémentaires (Lot 7) :
    admin_api.py         : /admin/* (tenants, users, agents, billing) + /analyst/*
    provisioning_api.py  : /provision/* (token lifecycle, scripts, offline pack, QR, bulk)
    auth_middleware.py   : JWT HMAC-SHA256 (access 15min + refresh 7j)

COMPOSANT 8 — Système de déploiement automatisé des agents (Lot 7)
  Voir Section 7 — Fonctionnalités détaillées.

COMPOSANT 9 — Socle technique (Lot 0)
  Voir Section 6 — Stack technique complète.

COMPOSANT 10 — Monitoring des modèles (correctif session 28 mai)
  Fichier : Lot3_IA/model_monitor.py (324 lignes)
  Rôle    : Détecte la dérive silencieuse des modèles en production.
  Méthodes: PSI (Population Stability Index), glissement σ de la moyenne, taux de FP,
            taux d'alertes global.
  Seuils  : PSI > 0.10 = surveillance ; PSI > 0.25 = retraining requis.
  Endpoint: GET /monitor/drift?days=7
  CLI     : python model_monitor.py --demo (ou --db postgresql://...)

═══════════════════════════════════════════════════════════════════════════════════
SECTION 5 — MODÈLES IA ENTRAÎNÉS
═══════════════════════════════════════════════════════════════════════════════════

MODÈLE 1 — Détection d'anomalies réseau
  Nom        : model1_isoforest.joblib (Isolation Forest) + variante autoencodeur
  Fichiers   : model1_anomaly_detection.py, model1_advanced.py
  Rôle       : Détecter les flux réseau anormaux (DDoS, PortScan, Bot/C2, infiltration)
  Type       : Isolation Forest (non supervisé) + MLPRegressor comme autoencodeur
  Dataset    : CICIDS2017 / CSE-CIC-IDS2018 (Canadian Institute for Cybersecurity)
    Lien     : https://www.unb.ca/cic/datasets/ids-2017.html
    Features : features de flux CICFlowMeter (durée, protocole, octets src/dst, flags…)
               ~80 features numériques après nettoyage (exclusion fuites / identifiants)
  Mode actuel: données synthétiques imitant CICIDS2017 (validation réelle au MINFI)
  Métriques mesurées (jeu synthétique) :
    Isolation Forest : ROC-AUC 0.987 | PR-AUC 0.943
    Autoencodeur     : ROC-AUC 0.991 | PR-AUC 0.981
  Détection par type d'attaque (complémentarité justifiant l'ensemble) :
    IF  : DDoS 99.5% | PortScan 84% | Bot/C2 96%
    AE  : DDoS 91%   | PortScan 98% | Bot/C2 100%
  Contamination : 0.05 (5 % d'anomalies estimées dans le trafic de prod)
  Output scoré : risque 0–100 + flag anomalie + score brut
  Fichier de sortie : model1_isoforest.joblib (dict : model, scaler, features,
                      threshold, risk_cfg{lo, hi})
  Entraînement : python model1_anomaly_detection.py [--data-dir ./CICIDS2017]
  Entraînement avancé + comparaison : python model1_advanced.py

MODÈLE 2 — Fraude interne UEBA (User and Entity Behavior Analytics)
  Nom        : model2_isoforest.joblib
  Fichier    : model2_fraud_detection.py
  Rôle       : Détecter les comportements frauduleux des agents internes dans les
               systèmes SIGIPES (gestion RH/paie) et SYDONIA (gestion douanière).
  Type       : Isolation Forest sur profils agrégés agent-jour
  Dataset    : CERT Insider Threat Dataset (CMU/SEI) comme référence théorique.
    Lien     : https://kilthub.cmu.edu/articles/dataset/
               Synthétique pour la démo — adaptation à SIGIPES au stage MINFI.
  Features (10) — profil agent-jour :
    nb_connexions, nb_actions_hors_heures, nb_transactions,
    montant_total_modifie, nb_modifs_montant, nb_creations_compte,
    nb_exports, volume_donnees_exportees, nb_acces_dossiers_sensibles,
    nb_actions_total
  3 scénarios de fraude simulés :
    Faux mandatements     : montant_total_modifie élevé, nb_modifs_montant élevé,
                            activité hors heures → 54 % détecté (zone grise légitime)
    Fonctionnaires fantômes: nb_creations_compte très élevé → 76 % détecté
    Exfiltration fiscale  : volume_donnees_exportees + nb_exports très élevés → 97 %
  Contamination : 0.04 (4 % d'anomalies)
  Métriques    : ROC-AUC 0.969 | FPR 4 %
  Explicabilité : top-3 features déviantes en σ pour chaque alerte
    ex : "volume de données exportées anormalement élevé (13.1σ)"
  Output      : risque 0–100 + flag anomalie + liste de raisons
  Entraînement: python model2_fraud_detection.py [--data-file ./profils_agents.csv]

MODÈLE 3 — Détection de dérive (monitoring en production)
  Fichier     : model_monitor.py
  Méthodes    : PSI, glissement σ, taux FP, taux d'alertes
  Pas de fichier .joblib — calcul à la volée sur les données de production

MODÈLES PROSPECTIFS (non implémentés, listés en perspectives) :
  LSTM temporel : séquences d'audit longues pour détecter APT lentes (T1+)
  UEBA personnalisé : ligne de base par agent × rôle (nécessite 90j de données)
  Ensemble M1+AE : combinaison IF + autoencodeur déjà justifiée par les métriques

═══════════════════════════════════════════════════════════════════════════════════
SECTION 6 — STACK TECHNIQUE COMPLÈTE
═══════════════════════════════════════════════════════════════════════════════════

LANGAGE DE L'AGENT :
  Go 1.21+ — pur stdlib, aucune dépendance externe.
  Justification : binaire unique sans runtime, compilation croisée Linux/Windows offline,
  surface d'attaque minimale (pas de CVE dans les dépendances), ~5 Mo.

BACKEND API :
  Python 3.10+ + FastAPI
  Justification : prototypage rapide, compatibilité avec l'écosystème ML (scikit-learn,
  joblib), documentation OpenAPI automatique (/docs).
  Authentification : JWT HMAC-SHA256 maison (auth_middleware.py) — access 15 min,
  refresh 7 jours, sans dépendance PyJWT.

BASE DE DONNÉES :
  TimescaleDB (extension PostgreSQL 16) — port 5432
    Rôle : stockage relationnel (tenants, users, agents, alerts, soar_audit)
           + stockage séries temporelles (table metrics, hypertable TimescaleDB)
    Justification : une seule instance pour le relationnel ET les métriques temporelles.
    Extension pgcrypto pour les mots de passe (crypt + gen_salt).
  Isolation multi-tenant : Row-Level Security (RLS) PostgreSQL
    Rôle client : nexus_app (non super-utilisateur — soumis à la RLS)
    Rôle analyste : nexus_analyst (BYPASSRLS — voit tous les tenants)
    Patch NULLIF : tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid

PIPELINE DE DONNÉES :
  Apache Kafka 3.7.1 — mode KRaft (sans Zookeeper)
    Port interne : 9092 | Port hôte dev : 29092
    Topics : nexus.telemetry.raw → nexus.telemetry → nexus.alerts
    Justification : découplage ingestion/traitement, résilience, scalabilité horizontale.

STOCKAGE CHAUD SIEM :
  Wazuh Indexer 4.9.0 (basé sur OpenSearch — port 9200, API compatible Elasticsearch)
    Justification : Wazuh embarque son propre indexeur — pas besoin d'Elasticsearch
    séparé (doublon mémoire sur matériel limité). Port API compatible → migration facile.
  Wazuh Manager 4.9.0 — ports 1514, 1515, 55000
  Wazuh Dashboard 4.9.0 — port 5601 (HTTPS)

ORCHESTRATION :
  Docker Compose v2 (développement/démo)
    Fichier : Lot0_Socle/docker-compose.yml (188 lignes)
    Healthchecks sur tous les services (Kafka, TimescaleDB, Wazuh Indexer,
    Wazuh Manager, Wazuh Dashboard, scoring-service)
  Kubernetes : NON implémenté — Docker Compose est la cible démo.
    Kubernetes est listé en perspectives pour la production (Helm chart à créer).

CI/CD : NON implémenté dans le projet actuel.
  Perspective : GitHub Actions avec job de build du binaire Go + tests Python.

MONITORING :
  model_monitor.py : dérive des modèles IA (PSI, σ-drift, taux FP)
  /health/detailed : healthcheck API multi-service (Kafka, DB, Wazuh)
  Docker healthchecks sur chaque conteneur

LLM LOCAL (optionnel) :
  Mistral 7B ou Llama 3 via Ollama ou vLLM
  API compatible OpenAI (OLLAMA_BASE_URL)
  Mode désactivé par défaut — mode template est la voie nominale

FRONTEND :
  Portail client DSI : portail/portal/index.html — HTML/CSS/JS autonome (Lot 5)
  Console fournisseur : console_fournisseur.html — HTML/CSS/JS (2912 lignes) (Lot 7)
  Polices : Fraunces + Manrope + JetBrains Mono (Google Fonts via CDN)
  Bibliothèques : QRCode.js 1.5.3 + JSZip 3.10.1 (via CDN jsDelivr)
  Design : mode sombre ops center, palette NAVY #0B2545 / BLUE #1C6DD0 /
           TEAL #1B998B / RED #C1432E / AMBER #B7791F

VARIABLES D'ENVIRONNEMENT CRITIQUES :
  POSTGRES_USER=nexus (défaut)
  POSTGRES_PASSWORD=change_me (À CHANGER en production)
  POSTGRES_DB=nexus_soc
  DB_DSN=postgresql://nexus:change_me@postgres:5432/nexus_soc
  KAFKA_BOOTSTRAP=kafka:9092
  TELEMETRY_TOPIC=nexus.telemetry
  ALERTS_TOPIC=nexus.alerts
  MODEL1_PATH=/models/model1_isoforest.joblib
  MODEL2_PATH=/models/model2_isoforest.joblib
  RISK_THRESHOLD=70 (seuil de risque pour publication alerte)
  JWT_SECRET=CHANGE_ME_IN_PRODUCTION (32 octets aléatoires)
  PSEUDO_SECRET=CHANGE_ME_PSEUDO_SECRET
  RATE_LIMIT_REQ=100 / RATE_LIMIT_WIN=60 (req/min global)
  INGEST_LIMIT_REQ=30 / INGEST_LIMIT_WIN=60 (req/min /ingest)
  ACCESS_TOKEN_TTL_S=900 (15 min)
  REFRESH_TOKEN_TTL_S=604800 (7 jours)
  CORR_WINDOW_MIN=30 (fenêtre de corrélation SIEM)
  MASS_FILE_THRESHOLD=20 (nb fichiers pour détecter ransomware)
  ACCOUNT_CREATE_THRESHOLD=5 (créations comptes pour T1136)
  WAZUH_API_URL=https://localhost:9200
  OLLAMA_BASE_URL=http://localhost:11434/v1 (optionnel, LLM mode)
  NEXUS_SERVER_URL=https://nexussoc.cm
  NEXUS_AGENT_VERSION=1.0.0
  BACKUP_DEST=/opt/nexus-backups
  KEEP_DAYS=14

═══════════════════════════════════════════════════════════════════════════════════
SECTION 7 — FONCTIONNALITÉS DÉTAILLÉES
═══════════════════════════════════════════════════════════════════════════════════

MULTI-TENANT :
  Architecture : une seule instance de la plateforme héberge TOUS les tenants.
  Isolation   : Row-Level Security PostgreSQL — chaque requête API injecte
                SET app.current_tenant = '<uuid>' avant les requêtes.
  Rôle client : nexus_app (non super-user) — filtré par RLS, voit son tenant uniquement.
  Rôle analyste: nexus_analyst (BYPASSRLS) — voit tous les tenants pour le SOC mutualisé.
  Patch critique: NULLIF(current_setting('app.current_tenant', true), '')::uuid
    → gère proprement le cas d'une variable vide (sinon ''::uuid lève une exception).
  Validé par : 8/8 assertions sur PostgreSQL 16 réel (rls_analyst_test.py).
  Tables avec RLS : alerts, agents, soar_audit.
  Tables sans RLS : tenants, users (filtrées au niveau applicatif).

DÉPLOIEMENT AUTOMATISÉ DES AGENTS (provisioning — Lot 7) :
  Console → modal "Provisionnement d'agent" :
    1. Saisir hostname + choisir OS + expiration (1h/24h/7j) + options sécurité
    2. Cliquer "Générer" → token Bearer + clé HMAC générés côté serveur
    3. One-liner immédiatement copiable :
       Linux  : curl -fsSL "https://nexussoc.cm/provision/oneliner?token=xxx&hostname=yyy" | bash
       Windows: irm "https://nexussoc.cm/provision/oneliner?token=xxx&hostname=yyy&os=windows" | iex
    4. Téléchargements : Script Linux (.sh), Script Windows (.ps1), Pack offline (.zip),
       QR Code (via QRCode.js — scanner le QR → commande curl sur terminal)
  Options de sécurité des tokens :
    Usage unique (token_one_time) : invalidé après premier enrôlement réussi.
    Binding hostname : token ne fonctionne que si le hostname de l'agent correspond.
    Expiration configurable : 1h / 24h / 7 jours.
    Statut visible en console : actif / utilisé / expiré.
  Import CSV (bulk) :
    CSV format : hostname,os,description
    → console génère un token par ligne, résultat affichable + téléchargeable (.csv).
  Script Linux (install_linux.sh) : détection arch, téléchargement ou fallback offline,
    création user système nexusagent, config.json (chmod 600), unité systemd avec
    hardening (NoNewPrivileges, ProtectSystem, PrivateTmp, PrivateDevices…), healthcheck.
  Script Windows (install_windows.ps1) : téléchargement ou fallback offline, config.json
    avec ACL restrictive (SYSTEM + Admins), Windows Service via sc.exe, retry auto.
  Ansible (ansible_nexus_agent.yml) : playbook complet pour déploiement de masse Linux.
  Rotation HMAC : POST /provision/rotate-hmac/{agent_id} → nouvelle clé HMAC.
  Révocation urgence : POST /provision/revoke-tenant/{tenant_id} → coupe tous les agents.

LLM ANALYST MULTILINGUE :
  Deux modes :
    Mode template (DÉFAUT) : explication déterministe 3–5 phrases, aucune hallucination.
    Mode LLM (OPTIONNEL) : Mistral/Llama via API OpenAI-compatible.
  Bilingue : --lang fr (français) ou --lang en (anglais).
  Exemple FR : "Le système a détecté un incident de type rançongiciel sur POSTE-COMPTA-07.
    L'incident reconstitue une chaîne d'attaque en 6 étapes (accès initial, exécution,
    collecte, commande et contrôle, impact), cartographiée sur MITRE ATT&CK (T1005, T1059,
    T1071, T1204, T1486). Le score de risque atteint 100/100. Le poste a été isolé."
  Exemple SMS FR : "🚨 NEXUS SOC — Rançongiciel sur POSTE-COMPTA-07 · risque 100/100.
    Action : isoler. Détails : nexussoc.cm/i/abc123"
  Rapport WhatsApp hebdo : score de sécurité, incidents, conseils, lien rapport.

IRP AUTOMATISÉE (Incident Response Plan) — 6 phases :
  Phase 1 — Détection    : agent Go → Kafka → Pipeline → modèles IA → alerte.
  Phase 2 — Analyse      : LLM Analyst génère l'explication + explicabilité des features.
  Phase 3 — Confinement  : SOAR exécute isolate_host / freeze_account / block_ip.
  Phase 4 — Éradication  : snapshot_memory / reset_password / preserve_logs.
  Phase 5 — Récupération : rollback des actions réversibles si nécessaire.
  Phase 6 — Leçons       : journal_investigation + rapport WhatsApp hebdomadaire.

NIVEAUX D'AUTOMATISATION :
  Mode Observe (dry_run=True) : toutes les actions sont proposées, aucune exécutée.
    Chaque action affiche ce qui se passerait → pour les tenants peu matures.
  Mode Semi-auto (défaut prod) : actions LOW/MEDIUM exécutées automatiquement dès que
    risque ≥ 70/100. Actions HIGH (freeze_account, isolate_host) → validation humaine.
  Mode Auto complet : toutes les actions automatiques quel que soit l'impact.
    NON recommandé par défaut — risque d'actions irréversibles erronées.

3 TYPES D'UTILISATEURS ET LEURS DROITS :
  admin_plateforme (Super Admin — côté fournisseur) :
    → Gestion de tous les tenants (CRUD, suspension, réactivation)
    → Gestion de tous les utilisateurs et leurs rôles
    → Provisioning agents (génération tokens, scripts, QR)
    → Vue santé système + facturation
    → Accès BYPASSRLS sur toutes les tables
  analyste_soc (Analyste SOC — côté fournisseur) :
    → File d'alertes cross-tenants (voit toutes les alertes de tous les tenants)
    → Approbation / refus des actions SOAR en attente de validation humaine
    → Tableau de bord SOC global (MTTD, MTTR, charge par tenant)
    → SELECT sur toutes les tables sensibles (BYPASSRLS), UPDATE limité sur soar_audit
  dsi_client (DSI Client — côté tenant) :
    → Portail Lot 5 : voit UNIQUEMENT les données de son organisation
    → Actions SOAR de sa propre organisation
    → Filtré par RLS (app.current_tenant positionné par l'API à la connexion)
  lecteur (Lecteur — côté tenant) :
    → Lecture seule sur son tenant
    → Filtré par RLS

═══════════════════════════════════════════════════════════════════════════════════
SECTION 8 — RISQUES ET LIMITES
═══════════════════════════════════════════════════════════════════════════════════

RISQUES TECHNIQUES AVEC MESURES D'ATTÉNUATION :

  R1. Données synthétiques — validation terrain absente [criticité ÉLEVÉE]
    Statut : risque documenté. Chiffres valides comme ordre de grandeur, pas preuve terrain.
    Atténuation : adaptation aux données SIGIPES/SYDONIA pendant le stage MINFI.

  R2. Dérive des modèles dans le temps [criticité ÉLEVÉE]
    Statut : risque documenté. model_monitor.py implémenté (PSI + σ-drift).
    Atténuation prévue : pipeline de ré-entraînement + DVC/MLflow (post-stage).

  R3. Faux mandatement — 54 % de détection [criticité MOYENNE]
    Statut : limite documentée honnêtement dans le rapport.
    Justification : fraude cachée dans la zone grise des grosses opérations légitimes.
    Atténuation prévue : UEBA personnalisé par agent×rôle + LSTM temporel.

  R4. Bug O(N²) dans detect_mass_file_change [RÉSOLU]
    Statut : corrigé dans correlation_engine_v2.py (deux pointeurs O(N)).

  R5. Validation HMAC absente sur /ingest [RÉSOLU]
    Statut : corrigé dans scoring-service_app.py v2.

  R6. Authentification JWT incomplète [RÉSOLU]
    Statut : auth_middleware.py implémenté (access 15min + refresh 7j).

  R7. Rate limiting absent [RÉSOLU]
    Statut : 100 req/min global, 30 req/min /ingest, HTTP 429 avec Retry-After.

  R8. Single point of failure [criticité ÉLEVÉE en production]
    Statut : Docker Compose mono-nœud pour la démo.
    Atténuation prévue : Kubernetes + Kafka multi-broker + PostgreSQL réplication streaming.

  R9. Pas de chiffrement au repos [criticité MOYENNE]
    Statut : non traité — nécessite infrastructure (LUKS, pgcrypto sur volumes).

  R10. Secrets en clair dans config.json sur les postes [criticité ÉLEVÉE]
    Statut : chmod 600 + ACL Windows implémentés. Clé HMAC en clair reste un risque.
    Atténuation prévue : DPAPI Windows / Linux Keyring (nécessite code Go dans l'agent).

  R11. T1027 par effet de bord (pas de règle dédiée) [PARTIELLEMENT RÉSOLU]
    Statut : règle T1027 dédiée ajoutée dans correlation_engine_v2.py.
    Limite restante : pas de règles YARA (analyse de contenu).

  R12. T1083 et T1136 non couverts [PARTIELLEMENT RÉSOLU]
    Statut : règles T1083 et T1136 ajoutées dans correlation_engine_v2.py.

RISQUES HUMAINS :
  Analystes SOC rares au Cameroun → la plateforme automatise pour compenser.
  Validation humaine : si l'analyste est absent, les actions HIGH s'accumulent.
  Formation des clients non incluse dans le produit.

RISQUES LIÉS AUX MODÈLES IA :
  Absence de MLOps — pas de versioning, pas de déploiement automatique.
  Pas de feedback loop (FP marqués par analystes ne mettent pas à jour le modèle).
  Biais des données synthétiques — le générateur peut créer des patterns artificiels.

RISQUES JURIDIQUES :
  Données personnelles (emails, IDs agents, IPs) dans les alertes.
    Atténuation : pseudonymizer.py implémenté (HMAC stable, mapping admin seulement).
  Conformité ANTIC non validée → démarche administrative requise.
  WhatsApp templates Meta non soumis → bloquant en production pour les rapports.
  Responsabilité contractuelle non définie.

LIMITES INTRINSÈQUES PERMANENTES :
  Données synthétiques → les métriques sont des ordres de grandeur, pas des preuves terrain.
  Connecteurs SOAR simulés → gel de compte et isolation ne s'exécutent pas réellement.
  Fenêtre de corrélation 30 min → APT lentes (>30 min entre étapes) non détectées.
  Pas de détection basée sur le contenu (YARA, sandbox).
  macOS non supporté par l'agent Go.

CE QUE NEXUS SOC NE REMPLACE PAS :
  Un pare-feu (NEXUS SOC détecte, ne bloque pas nativement).
  Un antivirus/EDR (NEXUS SOC enrichit la télémétrie, ne scanne pas les fichiers).
  Un RSSI humain (NEXUS SOC assiste, n'assume pas la responsabilité légale).
  Les audits de conformité (ANTIC, ISO 27001) qui nécessitent des organismes agréés.

═══════════════════════════════════════════════════════════════════════════════════
SECTION 9 — MODÈLE ÉCONOMIQUE
═══════════════════════════════════════════════════════════════════════════════════

NIVEAUX D'ABONNEMENT :

  Starter — 25 000 FCFA/mois (~41 USD/mois)
    Cible : cabinets comptables ONECCA, petites microfinances
    Agents : jusqu'à 10 postes
    Fonctionnalités : portail DSI, alertes email, LLM Analyst mode template
    Support : tickets email

  Business — 75 000 FCFA/mois (~124 USD/mois)
    Cible : microfinances COBAC moyennes, assurances CIMA
    Agents : jusqu'à 50 postes
    Fonctionnalités : + Modèle 2 UEBA, notifications SMS + WhatsApp, SOAR semi-auto
    Support : tickets + 1 session de formation/mois

  Enterprise — 200 000 FCFA/mois (~330 USD/mois)
    Cible : grandes microfinances, assurances nationales
    Agents : jusqu'à 200 postes
    Fonctionnalités : + Modèle 1 réseau, SOAR complet, tableau de bord SOC, API
    Support : SLA 4h, accès analyste SOC dédié

  Contrat public — tarif annuel négocié
    Cible : administrations publiques camerounaises
    Agents : illimités
    Hébergement : souverain (instance dédiée sur serveur du ministère)
    Fonctionnalités : toutes + intégration SIGIPES/SYDONIA + conformité ANTIC
    Support : SLA 1h, analyste SOC dédié, formation des équipes DSI

COMPARAISON AVEC L'EXISTANT :
  CrowdStrike Falcon : ~400-800 USD/agent/an → 200 postes = 80 000–160 000 USD/an
                       vs NEXUS Enterprise = 2 400 USD/an (33 à 66x moins cher)
  Splunk SIEM       : 10 000–50 000 USD/an + ingénieurs certifiés
  Wazuh seul        : gratuit mais nécessite 2–3 ingénieurs internes (salaires)
  NEXUS SOC         : SOCaaS mutualisé — l'analyste SOC est inclus dans l'abonnement

MARCHÉ CIBLE AU CAMEROUN :
  ~400 microfinances agréées COBAC au Cameroun (source COBAC 2023)
  ~150 compagnies d'assurance zone CIMA
  ~300 cabinets comptables ONECCA
  ~150 administrations publiques avec SI (ministères, agences, régies)
  Taille de marché estimée : ~5 Md FCFA/an si pénétration 10 % des microfinances

═══════════════════════════════════════════════════════════════════════════════════
SECTION 10 — AMÉLIORATIONS PRÉVUES
═══════════════════════════════════════════════════════════════════════════════════

Toutes ces améliorations sont PROSPECTIVES (non implémentées) et constituent
le chapitre "Perspectives" du rapport de soutenance.

  1. UEBA personnalisé par agent×rôle
     Ligne de base individuelle plutôt que populationnelle. Nécessite 90+ jours de données.
     Impact : améliorer les 54 % de détection des faux mandatements.

  2. LSTM temporel pour la détection d'APT
     Analyser les séquences d'actions dans le temps (pas juste un profil agrégé par jour).
     Nécessite des séquences d'audit réelles longues (SIGIPES 6+ mois).

  3. LLM Analyst — Mistral local en remplacement du mode template
     Activer le mode LLM avec Mistral 7B hébergé localement (Ollama) pour des explications
     adaptatives. Réduire les hallucinations via RAG sur la base de connaissances NEXUS SOC.

  4. Ensemble M1 + Autoencodeur
     Combiner Isolation Forest et autoencodeur pour la détection réseau (déjà justifié par
     les métriques : IF excelle DDoS 99.5%, AE excelle PortScan 97.9% et Bot/C2 99.9%).

  5. Connecteurs SOAR réels
     Brancher les vrais systèmes : AD/LDAP (freeze_account réel), pare-feu périmétrique
     (block_ip réel), EDR (isolate_host réel), passerelle SMS Orange/MTN Business.

  6. Optimisation O(N) du détecteur de modification massive
     FAIT dans correlation_engine_v2.py — à intégrer dans la version de production.

  7. Templates WhatsApp Business approuvés par Meta
     Soumettre les templates de rapports hebdomadaires à Meta avant le déploiement.
     Délai estimé : 1–2 semaines, acceptation non garantie.

  8. Détection d'arnaques spécifiques au Cameroun
     Détection de scams téléphoniques (SIM swapping), faux appels d'offres, fraude
     administrative (faux arrêtés, faux ordres de virement). Règles SIEM spécifiques.

  9. IA prédictive
     Prédire les postes à risque avant incident (score de vulnérabilité comportementale).
     Basé sur l'évolution des profils UEBA dans le temps.

  10. Protection Wi-Fi
      Détection de points d'accès Wi-Fi non autorisés et d'attaques Man-in-the-Middle.
      Nécessite une sonde Wi-Fi dédiée (Raspberry Pi + hostapd en mode monitor).

  11. Email Security Gateway (intégrée)
      Analyse des pièces jointes et liens dans les emails entrants.
      Intégration avec les serveurs SMTP du client.

  12. Rapport WhatsApp hebdomadaire automatique
      DÉJÀ IMPLÉMENTÉ en mode template (notifier.py). Templates Meta requis en prod.

  13. Conformité réglementaire automatique
      Dashboard de conformité ANTIC / ISO 27001 avec checklist des contrôles.
      Génération automatique du rapport de conformité annuel.

  14. Mode dégradé connexion lente
      L'agent réduit la fréquence de collecte et compresse davantage sur connexions <1 Mbps.
      Prioritisation des événements critiques (processus, connexions) sur les fichiers.

  15. Application mobile DSI
      Application Android/iOS pour le DSI client : alertes push, approbation SOAR depuis
      le smartphone. Technologie : React Native ou Flutter.

  16. Intégration MTN/Orange
      HORS PÉRIMÈTRE — domaine régulé par la BEAC. Nécessite accords opérateurs.
      Décision prise en début de projet et non réversible.

  17. Architecture HA — Kubernetes
      Kafka multi-broker, PostgreSQL avec réplication streaming, scoring-service derrière
      load balancer. Helm chart à créer pour déploiement Kubernetes.

  18. MLOps — pipeline de ré-entraînement automatique
      DVC (Data Version Control) pour versionner les modèles.
      MLflow pour suivre les expériences et comparer les versions.
      Déclenchement automatique si PSI > 0.25.

═══════════════════════════════════════════════════════════════════════════════════
SECTION 11 — ÉLÉMENTS POUR LE RAPPORT
═══════════════════════════════════════════════════════════════════════════════════

TITRE OFFICIEL DU RAPPORT :
  « NEXUS SOC : Conception et Implémentation d'une Plateforme SOC-as-a-Service
  Souveraine pour les Organisations Camerounaises — Détection Intelligente des
  Menaces par l'Intelligence Artificielle et Réponse Automatisée aux Incidents »

RÉSUMÉ EN FRANÇAIS (200 mots) :
  La cybersécurité des organisations camerounaises souffre d'un déficit structurel : les
  administrations publiques et PME financières manquent de moyens humains et financiers
  pour déployer un Security Operations Center (SOC) interne. Ce travail présente NEXUS SOC,
  une plateforme SOC-as-a-Service mutualisée, souveraine et abordable, conçue pour le
  contexte camerounais.

  L'architecture repose sur sept composants intégrés : un agent de collecte léger écrit en
  Go (~5 Mo, egress-only), un pipeline de normalisation et de corrélation SIEM mappé sur
  MITRE ATT&CK, deux modèles d'intelligence artificielle (Isolation Forest pour les anomalies
  réseau et UEBA pour la fraude interne), un moteur SOAR à garde-fous, un module de
  restitution bilingue français/anglais, et une console opérateur multi-tenant.

  La plateforme adopte un modèle économique double : abonnement mensuel (25 000 à
  200 000 FCFA) pour le secteur financier non bancaire, et contrat souverain pour les
  administrations publiques. Les résultats mesurés sur jeux de données synthétiques réalistes
  démontrent une couverture MITRE de 7/7 techniques attendues, un MTTD de 90 secondes pour
  l'exfiltration et 120 secondes pour le ransomware, une isolation multi-tenant vérifiée en
  8/8 assertions sur PostgreSQL réel, et des ROC-AUC de 0,987 et 0,969 pour les modèles
  réseau et fraude interne respectivement.

ABSTRACT IN ENGLISH (200 words) :
  Cybersecurity in Cameroonian organizations faces a structural deficit: public administrations
  and financial SMEs lack the human and financial resources to deploy an internal Security
  Operations Center (SOC). This work presents NEXUS SOC, a mutualized, sovereign, and
  affordable SOC-as-a-Service platform designed for the Cameroonian context.

  The architecture relies on seven integrated components: a lightweight Go collection agent
  (~5 MB, egress-only), a SIEM normalization and correlation pipeline mapped to MITRE ATT&CK,
  two artificial intelligence models (Isolation Forest for network anomalies and UEBA for
  internal fraud), a SOAR engine with guardrails, a bilingual French/English reporting module,
  and a multi-tenant operator console.

  The platform adopts a dual business model: monthly subscription (25,000 to 200,000 XAF) for
  the non-banking financial sector, and a sovereign contract for public administrations.
  Results measured on realistic synthetic datasets demonstrate MITRE coverage of 7/7 expected
  techniques, MTTD of 90 seconds for exfiltration and 120 seconds for ransomware, multi-tenant
  isolation verified in 8/8 assertions on real PostgreSQL, and ROC-AUC scores of 0.987 and
  0.969 for the network anomaly and internal fraud models respectively.

MOTS-CLÉS FR :
  SOC-as-a-Service, cybersécurité souveraine, détection d'intrusion, MITRE ATT&CK,
  Isolation Forest, UEBA, SOAR, multi-tenant, Cameroun, ANTIC, fraude interne,
  agent léger, corrélation SIEM, intelligence artificielle, réponse aux incidents

KEYWORDS EN :
  SOC-as-a-Service, sovereign cybersecurity, intrusion detection, MITRE ATT&CK,
  Isolation Forest, UEBA, SOAR, multi-tenant, Cameroon, ANTIC, insider threat,
  lightweight agent, SIEM correlation, artificial intelligence, incident response

PROBLÉMATIQUE PRÉCISE :
  « Comment concevoir et implémenter une plateforme de Security Operations Center
  accessible aux organisations camerounaises de taille moyenne — administrations publiques,
  microfinances et cabinets comptables — en conjuguant souveraineté numérique (hébergement
  local), abordabilité économique (modèle de mutualisation), automatisation intelligente
  (IA + SOAR) et restitution en langue française, dans un contexte marqué par des ressources
  humaines en cybersécurité rares et une connectivité réseau variable ? »

JUSTIFICATION DU PROJET :
  1. Menaces réelles documentées : ransomware sur administrations africaines (données 2022–2024),
     fraudes sur paie publique (fonctionnaires fantômes — contexte Cameroun), exfiltrations
     fiscales, phishing ciblant les microfinances.
  2. Absence de solutions adaptées : CrowdStrike/Splunk hors budget et hors souveraineté.
     Wazuh seul sans expertise interne est inutile. Pas de SOCaaS francophone souverain.
  3. Cadre légal : loi 2010/012 impose des mesures de sécurité aux SI traitant des données
     personnelles. Les organisations sont juridiquement exposées sans supervision de sécurité.
  4. Impact mesurable : MTTD de 90–120 secondes (vs plusieurs semaines dans les incidents
     non monitorés en Afrique subsaharienne selon le rapport IBM Cost of a Data Breach 2023).

POSITIONNEMENT PAR RAPPORT À L'EXISTANT :
  CrowdStrike Falcon EDR : 400–800 USD/agent/an, cloud américain, pas souverain, pas de
    version française, trop cher. NEXUS SOC : 2x–66x moins cher, cloud local, français.
  Splunk SIEM : $10K–50K/an, nécessite ingénieurs certifiés. NEXUS SOC : clé en main,
    aucune expertise interne requise côté client.
  SentinelOne : même problème que CrowdStrike. Pas d'offre africaine.
  Wazuh (open source) : gratuit mais nécessite 2–3 ingénieurs, pas de mutualisation,
    pas de modèles IA contextualisés, pas de restitution bilingue, pas de SOAR.
  Solutions africaines existantes : très peu documentées, pas de SOCaaS certifié
    en Afrique centrale francophone. NEXUS SOC est pionnier dans ce segment.

PHRASE DE CONCLUSION POUR LA SOUTENANCE :
  « NEXUS SOC démontre qu'il est possible de concevoir une plateforme de sécurité
  de niveau enterprise, adaptée au contexte camerounais, avec des ressources académiques
  et des technologies open-source — prouvant que la souveraineté numérique et
  la cybersécurité abordable ne sont pas des contradictions, mais un impératif
  stratégique pour le développement numérique de l'Afrique centrale. »

═══════════════════════════════════════════════════════════════════════════════════
SECTION 12 — CE QUI A ÉTÉ CODÉ
═══════════════════════════════════════════════════════════════════════════════════

RÉPERTOIRE RACINE : /home/noxtheteenager/Documents/Projets/NEXUS_SOC/

├── README.md (781 lignes) — documentation complète avec correctifs du 28 mai
├── INVENTAIRE.md — catalogue général des livrables
├── NEXUS_SOC_Contexte_Complet.md — ce fichier

LOT 0 — Socle technique
├── Lot0_Socle/docker-compose.yml (188 lignes)
│   6 services : Kafka KRaft + TimescaleDB + Wazuh Indexer + Wazuh Manager +
│   Wazuh Dashboard + scoring-service. Healthchecks sur tous les services.
│   start_period adapté : 90s indexeur, 60s manager, 120s dashboard, 30s scoring.
├── Lot0_Socle/01_schema_patched.sql (123 lignes)
│   Tables : tenants, users (RBAC), agents, alerts, soar_audit, metrics (hypertable).
│   RLS sur alerts, agents, soar_audit avec patch NULLIF.
│   Données demo : 2 tenants, 1 user admin, 2 agents.
├── Lot0_Socle/01_schema_retention.sql (NOUVEAU — correctif du 28 mai)
│   Compression TimescaleDB metrics après 7j, archivage alertes après 1an,
│   purge tokens expirés, table retention_policy par offre.
├── Lot0_Socle/backup.sh (NOUVEAU)
│   Sauvegarde PostgreSQL dump + Wazuh snapshot + modèles + config.
│   Rotation automatique sur KEEP_DAYS jours (défaut 14).
├── Lot0_Socle/restore.sh (NOUVEAU)
│   Restauration PostgreSQL + modèles + Wazuh snapshot.
└── Archive nexus-soc-socle.zip

LOT 1 — Agent Go + Service de scoring
├── Lot1_Agent_Go/nexus-agent.zip
│   Contient : main.go, collect.go (collecteurs Linux+Windows), buffer.go
│   (store-and-forward), sender.go (HMAC + gzip + Bearer token)
│   Taille binaire mesurée : 5.0 Mo Linux, 5.3 Mo Windows.
│   Collecte : processus (SHA-256 caché), connexions /proc/net/tcp + IPv6,
│   modifications de fichiers, état système. Envoi toutes les 30s.
├── Lot1_Agent_Go/scoring-service_app.py (374 lignes — VERSION v2)
│   FastAPI v2 : validation HMAC + Bearer token sur /ingest, rate limiting
│   (100/min global, 30/min /ingest), /health/detailed (Kafka + TimescaleDB + Wazuh),
│   consommateur Kafka en tâche de fond, score M1 + M2, emit alert.
├── Lot1_Agent_Go/auth_middleware.py (181 lignes — NOUVEAU)
│   JWT HMAC-SHA256 maison : create_token, decode_token, require_role(*roles).
│   Endpoints : POST /auth/token, POST /auth/refresh, GET /auth/me.
│   Access token TTL : 15 min. Refresh token TTL : 7 jours.
├── Lot1_Agent_Go/pseudonymizer.py (196 lignes — NOUVEAU)
│   Pseudonymisation HMAC-SHA256 stable : emails, IPs publiques, agent_ids, DOMAIN\user.
│   AlertPseudonymizer.process(alert) → remplace les PII par des pseudonymes.
│   Mapping pseudonyme→original stocké en base (réservé admin pour enquête légale).
└── Lot1_Agent_Go/telemetry_sample.json (59 événements réels)

LOT 2 — Pipeline SIEM
├── Lot2_Pipeline_SIEM/nexus-pipeline.zip
│   Contient : normalizer.py, correlation_engine.py (v1 originale),
│   telemetry_gen.py (générateur avec attaque implantée), make_lot2_figures.py
├── Lot2_Pipeline_SIEM/correlation_engine_v2.py (335 lignes — NOUVEAU — correctif)
│   Correctifs : O(N²) → O(N) sur detect_mass_file_change (deux pointeurs).
│   Nouvelles règles : T1027 dédié (base64, double ext., iex), T1136 (useradd,
│   net user /add, création en masse), T1083 (/etc/, /proc/, HKLM, SAM).
│   Fenêtre configurable CORR_WINDOW_MIN. Mode --benchmark inclus.
│   Critères de levée d'incident étendus : Execution+C2 OU Impact OU
│   Defense Evasion + Persistence (couvre T1027 + T1136 ensemble).
└── Lot2_Pipeline_SIEM/correlated_incidents.json (résultat démo)

LOT 3 — Modèles IA
├── Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
│   Isolation Forest sur features CICIDS-like. Génère model1_isoforest.joblib.
│   Résultats : ROC-AUC 0.987, PR-AUC 0.943.
├── Lot3_IA/Modele1_Anomalie_reseau/model1_advanced.py
│   Autoencodeur (MLPRegressor) + comparaison IF vs AE + analyse par type d'attaque.
│   Résultats AE : ROC-AUC 0.991, PR-AUC 0.981.
│   Figures : model_comparison.png, detection_by_attack_type.png, roc_curve.png,
│   confusion_matrix.png, scores_distribution.png, autoencoder_error_distribution.png.
├── Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py
│   Isolation Forest UEBA, 10 features, 3 scénarios, explicabilité σ.
│   Génère model2_isoforest.joblib.
│   Résultats : ROC-AUC 0.969, FPR 4%.
│   Détection : Exfiltration 97%, Fonctionnaire fantôme 76%, Faux mandatement 54%.
│   Figures : fraud_signatures.png (heatmap), detection_by_fraud_type.png, metrics.json.
└── Lot3_IA/model_monitor.py (324 lignes — NOUVEAU)
    PSI, σ-drift, taux FP, taux d'alertes. Seuils : PSI>0.10 warning, >0.25 alarm.
    GET /monitor/drift?days=7. CLI --demo pour test sans base de données.

LOT 4 — SOAR
├── Lot4_SOAR/soar_engine.py (285 lignes)
│   9 connecteurs, 4 playbooks, seuil auto_threshold=70, validation HIGH,
│   rollback réversible, journal CSV. Modes dry_run / semi-auto / auto complet.
└── Lot4_SOAR/audit_log.csv (journal de la démo)

LOT 5 — Restitution bilingue
├── Lot5_Restitution/nexus-portail.zip
│   portail/portal/index.html : portail DSI HTML autonome, bilingue FR/EN.
│   portail/notifier.py : LLM Analyst (mode template défaut + mode llm optionnel).
│   Sortie : explanation_fr/en.txt, sms_fr/en.txt, whatsapp_fr/en.txt
└── Lot5_Restitution/preview_fr.png + preview_en.png

LOT 6 — Tests et mesures
└── Lot6_Tests/nexus-tests.zip
    attack_simulation.py : 7/7 techniques détectées, 3/3 scénarios, MTTD mesuré.
    load_test.py : ~200 000 ev/s normalisation, p99 ≤ 12 μs.
    rls_isolation_test.py : 5/5 assertions PostgreSQL (test original).
    make_lot6_figures.py : génère mttd_by_scenario.png, load_test_perf.png,
                           rls_isolation_result.png, mitre_coverage_tested.png.

LOT 7 — Console Fournisseur + Provisioning
├── Lot7_Console_Fournisseur/console_fournisseur.html (2912 lignes)
│   Module A (admin) : tableau de bord, tenants CRUD, utilisateurs, agents,
│   santé système, facturation. Provisioning enrichi avec QR code + downloads.
│   Module B (analyste SOC) : file d'alertes, approbation SOAR, tableau de bord SOC.
│   Design : mode sombre, Fraunces + Manrope + JetBrains Mono, bilingue FR/EN.
├── Lot7_Console_Fournisseur/admin_api.py (409 lignes)
│   /admin/* : tenants, users, agents, health, billing.
│   /analyst/* : alerts cross-tenant, approve, dashboard.
├── Lot7_Console_Fournisseur/provisioning_api.py (701 lignes)
│   /provision/token : génération avec lifecycle (expiration, one-time, binding).
│   /provision/enroll : validation à l'enrôlement (règles token).
│   /provision/installer/{id} : script Linux ou Windows prêt à l'emploi.
│   /provision/offline-pack/{id} : ZIP complet (binaire + config + scripts + README).
│   /provision/qr/{id} : QR code PNG base64 (via lib qrcode).
│   /provision/status/{id} : statut token (actif/utilisé/expiré).
│   /provision/bulk : provisioning en masse CSV.
│   /provision/oneliner : one-liner dynamique curl|bash.
│   /provision/rotate-hmac/{id} : rotation clé HMAC.
│   /provision/revoke-tenant/{id} : révocation urgence tous agents d'un tenant.
├── Lot7_Console_Fournisseur/rls_analyst_test.py (277 lignes)
│   8/8 assertions : 5 nexus_app (RLS filtré) + 3 nexus_analyst (BYPASSRLS).
│   Génère rls_analyst_result.png.
├── Lot7_Console_Fournisseur/01_schema_analyst.sql
│   Rôle nexus_analyst BYPASSRLS, colonnes token_hash + hmac_key_hash sur agents.
├── Lot7_Console_Fournisseur/01_schema_provisioning.sql
│   Colonnes lifecycle tokens sur agents (expires_at, used_at, binding_host, one_time).
│   Vue v_agent_token_status, table enrollment_log, table bulk_provisioning.
└── Lot7_Console_Fournisseur/install_templates/
    install_linux.sh   : script bash complet avec systemd hardened.
    install_windows.ps1: script PowerShell avec Windows Service sc.exe.
    nexusagent.service : unité systemd production-grade.
    ansible_nexus_agent.yml : playbook Ansible complet.
    config.json.j2     : template Jinja2 pour Ansible.

TESTS EFFECTUÉS ET RÉSULTATS :

  Simulation Atomic Red Team (attack_simulation.py) :
    7/7 techniques détectées (T1059, T1071, T1005, T1204, T1486, T1027*, T1136)
    *T1027 par effet de bord en v1, règle dédiée en v2.
    3/3 scénarios reconstitués. MTTD ransomware : 120 s. MTTD exfiltration : 90 s.
    Scénario négatif : 0 alerte (aucun faux positif).

  Test de charge (load_test.py) :
    Normalisation : ~200 000 ev/s stable, p99 ≤ 12 μs (mono-cœur).
    Corrélation v1 : 714k ev/s à 1k, chute à 22k ev/s à 100k (O(N²) identifié).
    Corrélation v2 : stable à toutes tailles (O(N) vérifié par benchmark).

  Isolation RLS (rls_isolation_test.py + rls_analyst_test.py) :
    5/5 assertions nexus_app (Lot 6). 8/8 assertions totales (Lot 7).
    Découverte et correction du bug NULLIF propagée au schéma Lot 0.

BUGS RÉSOLUS ET COMMENT :
  B1. O(N²) detect_mass_file_change : remplacé par algorithme deux pointeurs (O(N)).
      Fichier : correlation_engine_v2.py.
  B2. /ingest sans authentification : ajout validation Bearer token (hash SHA-256)
      + header X-Signature. Fichier : scoring-service_app.py.
  B3. Pas de rate limiting : compteur en mémoire par IP, 429 avec Retry-After.
      Fichier : scoring-service_app.py.
  B4. JWT incomplet : auth_middleware.py avec access+refresh tokens HMAC-SHA256.
  B5. RLS contournement NULLIF : NULLIF(current_setting('app.current_tenant', true), '')
      propagé au schéma Lot 0 depuis les tests Lot 6.
  B6. Règles SIEM incomplètes : T1027 (dédié), T1136, T1083 ajoutées en v2.

DÉCISIONS TECHNIQUES IMPORTANTES ET VERROUILLÉES :
  D1. Pas de MVP — projet complet en lots ordonnés L0→L7.
  D2. Wazuh indexeur intégré = stockage chaud (pas d'Elasticsearch séparé).
  D3. TimescaleDB = relationnel + séries temporelles en un seul service.
  D4. Multi-tenant via RLS PostgreSQL (nexus_app non super-user).
  D5. Agent egress-only HTTPS (pas de port entrant, agit derrière tout pare-feu).
  D6. Pur stdlib Go pour l'agent (pas de dépendances externes).
  D7. Télémétrie endpoint ≠ entrée directe M1 et M2 (M1 attend features CICIDS,
      M2 attend features audit applicatif — la télémétrie alimente le corrélateur SIEM).
  D8. VirusTotal côté serveur (clé API centralisée, pas de secret sur les postes).
  D9. LLM Analyst mode template par défaut (déterministe, sans hallucination).
  D10. WhatsApp Business API : templates Meta requis hors fenêtre 24h (déploiement).
  D11. Connecteurs SOAR simulés dans le démonstrateur (interface prête, corps à brancher).

═══════════════════════════════════════════════════════════════════════════════════
SECTION 13 — PROCHAINES ÉTAPES
═══════════════════════════════════════════════════════════════════════════════════

CE QUI RESTE À FAIRE (par priorité décroissante) :

  PRIORITÉ 1 — Académique (bloquant pour la soutenance du 24 août 2026)

  P1. Rédiger le rapport écrit (ordre recommandé) :
    Chapitre 3 (Conception) en premier — le plus important, tout le code existe déjà.
    Chapitre 2 (État de l'art) — citer MITRE ATT&CK, CICIDS2017, CERT Insider Threat,
      Wazuh, Isolation Forest (Liu 2008), autoencodeur (Hinton 2006), LSTM (Hochreiter 1997).
    Chapitre 4 (Réalisation) — un sous-chapitre par lot avec code + figures.
    Chapitre 5 (Tests) — tableau de chiffres mesurés, figures déjà produites.
    Chapitre 6 (Conclusion + perspectives) — les 18 améliorations prévues.
    Chapitre 1 (Contexte) — loi 2010/012, ANTIC, panorama des menaces.
    Conclusion générale + Abstract + Bibliographie (≥ 20 entrées).
    Introduction.

  P2. Préparer le support de soutenance (~20 slides) :
    S'appuyer sur : chain_reconstruction.png, mitre_coverage.png, mttd_by_scenario.png,
    load_test_perf.png, rls_isolation_result.png, fraud_signatures.png,
    model_comparison.png, detection_by_attack_type.png.

  PRIORITÉ 2 — Technique léger (2–4h, pendant la rédaction)

  P3. Captures d'écran de la console fournisseur (preview_fr.png + preview_en.png).
      → ouvrir console_fournisseur.html dans un navigateur, faire F11.

  P4. Vérifier que correlation_engine_v2.py remplace bien v1 dans la démo complète.
      → python telemetry_gen.py | python normalizer.py | python correlation_engine_v2.py

  P5. Appliquer les schémas SQL complémentaires sur une instance de dev :
      psql -U postgres -d nexus_soc -f Lot7_Console_Fournisseur/01_schema_analyst.sql
      psql -U postgres -d nexus_soc -f Lot7_Console_Fournisseur/01_schema_provisioning.sql
      psql -U postgres -d nexus_soc -f Lot0_Socle/01_schema_retention.sql

  PRIORITÉ 3 — Stage MINFI (mai–juillet 2026)

  P6. Adapter M1 aux données réseau réelles (CICIDS2017 ou captures MINFI).
  P7. Adapter M2 aux données d'audit SIGIPES (journaux agents DGI/DGB).
  P8. Brancher les connecteurs SOAR réels (LDAP + pare-feu périmétrique).
  P9. Tester Atomic Red Team sur réseau MINFI de test (avec autorisation).
  P10. Initier la démarche conformité ANTIC.

DÉPENDANCES ENTRE LES TÂCHES :
  P3 dépend de : navigateur avec accès internet (CDN fonts)
  P4 dépend de : nexus-pipeline.zip extrait
  P5 dépend de : PostgreSQL accessible localement
  P6 dépend de : autorisation MINFI pour les données réseau
  P7 dépend de : accès aux journaux SIGIPES (données protégées)
  P8 dépend de : accès à l'annuaire LDAP et pare-feu du MINFI
  P1 (rapport) ne dépend de rien — peut commencer immédiatement

RISQUES SUR LES PROCHAINES ÉTAPES :
  Rapport : risque de sous-documentation des limites honnêtes (atténuation : Section 6
    du prompt de reprise d'origine documente tout explicitement à assumer).
  Stage : accès aux données réelles soumis à autorisation administrative (délais).
  Soutenance : questions attendues du jury sur la détection à 54% des faux mandatements
    et les données synthétiques → réponses préparées dans la Section 11.

═══════════════════════════════════════════════════════════════════════════════════
SECTION 14 — COMMANDES ET CONFIGURATIONS CLÉS
═══════════════════════════════════════════════════════════════════════════════════

DÉMARRAGE DE LA PILE COMPLÈTE :

  # Prérequis noyau
  sudo sysctl -w vm.max_map_count=262144

  # Extraire et configurer le socle
  cd Lot0_Socle && unzip nexus-soc-socle.zip && cd nexus-soc-socle
  cp .env.example .env  # adapter les mots de passe

  # Générer les certificats Wazuh (une seule fois)
  docker compose -f generate-certs.yml run --rm generator

  # Déposer les modèles
  python3 Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
  cp model1_isoforest.joblib nexus-soc-socle/models/
  python3 Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py
  cp model2_isoforest.joblib nexus-soc-socle/models/

  # Lancer toute la pile
  docker compose up -d

  # Vérifier l'état
  docker compose ps
  curl http://localhost:8000/health
  curl http://localhost:8000/health/detailed | python3 -m json.tool

DÉMO PIPELINE SANS DOCKER :

  cd Lot2_Pipeline_SIEM && unzip nexus-pipeline.zip
  cd nexus-pipeline
  python telemetry_gen.py
  python normalizer.py telemetry_demo.json | python ../../correlation_engine_v2.py

  # Benchmark O(N²) → O(N)
  python ../../correlation_engine_v2.py --benchmark

ENTRAÎNER LES MODÈLES :

  # Modèle 1 (données synthétiques)
  python Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
  python Lot3_IA/Modele1_Anomalie_reseau/model1_advanced.py

  # Modèle 1 (données réelles CICIDS2017)
  python Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py --data-dir ./CICIDS2017

  # Modèle 2 (données synthétiques)
  python Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py

  # Modèle 2 (données réelles SIGIPES)
  python Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py --data-file ./profils_sigipes.csv

SCORING API :

  # Healthcheck
  curl http://localhost:8000/health
  curl http://localhost:8000/health/detailed

  # Scorer un flux réseau (M1)
  curl -X POST http://localhost:8000/score/network \
    -H "Content-Type: application/json" \
    -d '{"features": {"src_bytes": 3200000, "dst_bytes": 512, "duration": 0}}'

  # Scorer un profil agent-jour (M2)
  curl -X POST http://localhost:8000/score/user-day \
    -H "Content-Type: application/json" \
    -d '{"features": {"nb_exports": 28, "volume_donnees_exportees": 92000,
                       "nb_acces_dossiers_sensibles": 40, "nb_transactions": 12,
                       "montant_total_modifie": 0, "nb_modifs_montant": 0,
                       "nb_connexions": 3, "nb_actions_hors_heures": 2,
                       "nb_creations_compte": 0, "nb_actions_total": 45}}'

  # Ingest telemetry (avec auth)
  curl -X POST http://localhost:8000/ingest \
    -H "Authorization: Bearer nexus_demo" \
    -H "X-Signature: $(sha256sum telemetry_sample.json | cut -d' ' -f1)" \
    -H "Content-Type: application/json" \
    -d @Lot1_Agent_Go/telemetry_sample.json

AUTHENTIFICATION JWT :

  # Login
  curl -X POST http://localhost:8000/auth/token \
    -H "Content-Type: application/json" \
    -d '{"email": "admin@nexussoc.cm", "password": "admin"}'
  # → {"access_token": "...", "refresh_token": "...", "expires_in": 900}

  # Utiliser le token
  curl -H "Authorization: Bearer <access_token>" http://localhost:8000/admin/tenants

COMPILATION DE L'AGENT GO :

  cd Lot1_Agent_Go && unzip nexus-agent.zip && cd nexus-agent

  # Linux amd64
  CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent .

  # Windows amd64
  CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent.exe .

DÉPLOIEMENT D'UN AGENT :

  # One-liner Linux
  curl -fsSL "https://nexussoc.cm/provision/oneliner?token=nexus_xxx&hostname=POSTE-01" | bash

  # One-liner Windows (PowerShell Admin)
  Set-ExecutionPolicy Bypass -Scope Process -Force
  irm "https://nexussoc.cm/provision/oneliner?token=nexus_xxx&hostname=POSTE-01&os=windows" | iex

  # Ansible (parc Linux)
  ansible-playbook -i inventaire.ini Lot7_Console_Fournisseur/install_templates/ansible_nexus_agent.yml \
    -e "nexus_server=https://nexussoc.cm" \
    -e "nexus_token=nexus_xxx" \
    -e "nexus_tenant_id=11111111-1111-1111-1111-111111111111"

TESTS :

  # Simulation d'attaques
  cd Lot6_Tests && unzip nexus-tests.zip
  python attack_simulation.py

  # Test de charge
  python load_test.py

  # Test isolation RLS Lot 6 (5 assertions nexus_app)
  python rls_isolation_test.py

  # Test isolation RLS étendu Lot 7 (8 assertions : nexus_app + nexus_analyst)
  python3 Lot7_Console_Fournisseur/rls_analyst_test.py

  # Monitoring dérive modèles (mode démo)
  python3 Lot3_IA/model_monitor.py --demo

  # Pseudonymisation (test)
  python3 Lot1_Agent_Go/pseudonymizer.py

  # Figures synthèse Lot 6
  python make_lot6_figures.py

SAUVEGARDE :

  sudo bash Lot0_Socle/backup.sh --dest /opt/nexus-backups --compress

INTERFACES WEB (aucun serveur requis) :

  # Portail client DSI (Lot 5)
  xdg-open Lot5_Restitution/portail/portal/index.html

  # Console fournisseur (Lot 7 — Modules A + B)
  xdg-open Lot7_Console_Fournisseur/console_fournisseur.html

APPLIQUER LES SCHÉMAS SQL COMPLÉMENTAIRES :

  psql -U postgres -d nexus_soc -f Lot0_Socle/01_schema_patched.sql
  psql -U postgres -d nexus_soc -f Lot7_Console_Fournisseur/01_schema_analyst.sql
  psql -U postgres -d nexus_soc -f Lot7_Console_Fournisseur/01_schema_provisioning.sql
  psql -U postgres -d nexus_soc -f Lot0_Socle/01_schema_retention.sql

