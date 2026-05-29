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
    modèles IA adaptés au contexte SIGIPES/SYDONIA, bilingue FR/EN, prix FCFA,
    flux PLG automatisé pour les microfinances + déploiement Terraform souverain
    pour les administrations publiques.

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
  8. Tester le déploiement Terraform souverain sur l'infrastructure MINFI (si autorisé)

═══════════════════════════════════════════════════════════════════════════════════
SECTION 3 — PÉRIMÈTRE ET CIBLES
═══════════════════════════════════════════════════════════════════════════════════

CIBLE PRINCIPALE — Administrations publiques camerounaises :
  Types       : Ministères, Directions Générales, Agences d'État, régies financières
  Exemples    : MINFI, DGI (Direction Générale des Impôts), DGCOOP, DGD (Douanes)
  Taille      : 50 à 500 postes surveillés
  Offre       : Contrat public annuel + hébergement souverain dédié (Hub & Spoke)
  Déploiement : Module Terraform souverain (Lot 8) — déploie la pile complète via SSH
  Motivation  : Souveraineté numérique, conformité loi 2010/012, détection fraudes
                internes (fonctionnaires fantômes, faux mandatements)
  Flux        : Formulaire "Déploiement Souverain" sur la landing page → contact
                architecte NEXUS SOC → déploiement Terraform sur site

CIBLE SECONDAIRE — Secteur financier non bancaire :
  Microfinances (régulation COBAC — Afrique Centrale)
  Assurances (code CIMA)
  Cabinets comptables (ONECCA — Cameroun)
  Taille      : 5 à 100 postes
  Offres      : Starter / Business / Enterprise (abonnement mensuel en FCFA)
  Flux        : Product-Led Growth automatisé (Lot 8) — inscription self-service
                via landing_page.html → API PLG → provisioning automatique tenant

HORS PÉRIMÈTRE (explicitement abandonné) :
  Fraude Mobile Money MTN/Orange : domaine régulé par la BEAC, nécessite accords
  opérateurs, données propriétaires. Décision prise en début de projet et non réversible.
  IMPORTANT : la pré-autorisation bancaire à 0 FCFA du flux PLG est une vérification
  d'IDENTITÉ (carte Visa/Mastercard/CinetPay), pas une collecte Mobile Money — c'est
  légalement distinct et hors du domaine BEAC.
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

COMPOSANT 1-PLG — Agent "coquille vide" (Lot 8)
  Nom          : nexus-agent-plg (binaire Go obfusqué + watermarqué)
  Rôle         : Version PLG de l'agent, compilée dynamiquement par tenant.
                 Ne contient AUCUNE règle de surveillance en dur.
                 Config (watch_dirs, interval_sec, quotas) récupérée dynamiquement
                 depuis /plg/agent/config/{agent_id} au démarrage, puis mise en cache
                 locale chiffrée par HMAC (fichier .nexus_cfg_cache).
  Fichiers     : Lot8_PLG/nexus-agent-plg/ (watermark.go 28L, config_fetcher.go 249L,
                 main_plg.go 114L)
  Obfuscation  : garble -tiny -seed <salt> → symboles/chaînes obfusqués dans le binaire
  Watermark    : HMAC-SHA256(JWT_SECRET, tenant_id + ":" + salt) injecté via ldflags
                 avant garble. Vérifiable côté serveur via la table build_log.
  Cache local  : Format [32 bytes HMAC tag][gzip payload] — chmod 600.
                 HMAC vérifié à la lecture pour détecter toute altération.
                 Fallback sur cache si serveur injoignable (mode dégradé).
  Compilation  : python3 Lot8_PLG/build_agent.py --tenant-id <uuid> --os linux --arch amd64
  Headers HTTP : X-Nexus-Watermark (16 premiers hex du watermark), X-Nexus-Tenant, X-Nexus-Version
  Interactions : récupère config depuis /plg/agent/config/{agent_id} (Bearer auth)
                 envoie télémétrie vers /ingest avec headers watermark supplémentaires

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
    via algorithme à deux pointeurs.
  Interactions : consomme depuis Kafka → produit incidents → SOAR + base de données

COMPOSANT 3 — Modèles IA (Lot 3) — voir Section 5

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
  Niveaux d'impact :
    LOW    : journal_investigation, preserve_logs, notify_sms, notify_whatsapp
    MEDIUM : snapshot_memory, block_ip, reset_password
    HIGH   : freeze_account, isolate_host
  Paramètres :
    dry_run=True, auto_threshold=70, auto_exec_max_impact=MEDIUM
    HIGH toujours en attente de validation humaine
  Méthodes clés : engine.handle(alert) / engine.approve(id,key,who) / engine.rollback(id,by)
  Journal d'audit : audit_log.csv (qui, quoi, quand, statut)

COMPOSANT 5 — LLM Analyst + Restitution bilingue (Lot 5)
  Nom          : nexus-portail (portail client DSI) + notifier.py (LLM Analyst)
  Fichiers     : nexus-portail.zip contenant portail/portal/index.html + notifier.py
  Rôle         : Expliquer les incidents en langage clair FR/EN, notifier par SMS
                 et WhatsApp, afficher le portail DSI.
  LLM Analyst — deux modes :
    Mode template (défaut) : explication déterministe sans LLM, sans hallucination.
    Mode llm (optionnel) : Mistral 7B ou Llama via API compatible OpenAI (Ollama/vLLM).
      Activé via variable d'env OLLAMA_BASE_URL. Désactivé par défaut.
  Notifications :
    SMS : max 160 car. ex. "🚨 NEXUS SOC — Rançongiciel sur POSTE-COMPTA-07 · risque 100/100."
    WhatsApp : rapport hebdomadaire structuré.
               ⚠ hors fenêtre 24h → templates Meta requis (contrainte déploiement).
  Portail DSI (Lot 5) :
    Fichier : portail/portal/index.html — HTML/CSS/JS autonome, aucun serveur requis.
    Design  : mode sombre ops center, Fraunces + Manrope + JetBrains Mono.
    Bascule FR/EN instantanée. VUE CLIENT UNIQUEMENT (un tenant).

COMPOSANT 6 — Console Fournisseur / Command Center (Lot 7)
  Fichier      : Lot7_Console_Fournisseur/console_fournisseur.html (2912 lignes)
  Technologies : HTML/CSS/JS autonome, QRCode.js (CDN), JSZip (CDN)
  Module A — Administration :
    Tableau de bord global, tenants CRUD, utilisateurs RBAC, agents, santé système, facturation ARR/MRR.
  Module B — Poste Analyste SOC :
    File d'alertes cross-tenants, approbation SOAR, tableau de bord SOC (MTTD/MTTR).

COMPOSANT 7 — Service de Scoring IA + API (Lot 1 + Lot 7)
  Fichier principal : Lot1_Agent_Go/scoring-service_app.py (466 lignes, version v2 + patch PLG)
  FastAPI — endpoints :
    POST /ingest         : passerelle sécurisée (Bearer + HMAC validés, rate limit 30/min,
                           quota trial vérifié via _enforce_trial_quota_sync)
    POST /score/network  : scorer un flux réseau via Modèle 1
    POST /score/user-day : scorer un profil agent-jour via Modèle 2
    GET  /health         : healthcheck rapide (Docker-friendly)
    GET  /health/detailed: vérifie Kafka, TimescaleDB, Wazuh Indexer en temps réel
    GET  /monitor/drift  : dérive des modèles (PSI + σ-drift)
  Modules complémentaires (Lot 7) :
    admin_api.py (409L)        : /admin/* (tenants, users, agents, billing) + /analyst/*
    provisioning_api.py (701L) : /provision/* (token lifecycle, scripts, offline pack, QR, bulk)
    auth_middleware.py (181L)  : JWT HMAC-SHA256 (access 15min + refresh 7j)
  Module PLG (Lot 8) :
    plg_api.py (712L)          : /plg/* (check-email, register, verify, preauth, trial-status,
                                          plans, upgrade, suspend, resume, run-expiry-check,
                                          agent/config/{agent_id})

COMPOSANT 8 — Système de déploiement automatisé des agents (Lot 7)
  Console → modal "Provisionnement d'agent" :
    1. Saisir hostname + choisir OS + expiration (1h/24h/7j) + options sécurité
    2. Cliquer "Générer" → token Bearer + clé HMAC générés côté serveur
    3. One-liner immédiatement copiable :
       Linux  : curl -fsSL "https://nexussoc.cm/provision/oneliner?token=xxx&hostname=yyy" | bash
       Windows: irm "https://nexussoc.cm/provision/oneliner?token=xxx&hostname=yyy&os=windows" | iex
    4. Téléchargements : Script Linux (.sh), Script Windows (.ps1), Pack offline (.zip), QR Code
  Options de sécurité :
    Usage unique (token_one_time), binding hostname, expiration configurable.
  Import CSV (bulk) : hostname,os,description → token par ligne → CSV téléchargeable.
  Ansible : ansible_nexus_agent.yml — déploiement de masse Linux.
  Rotation HMAC : POST /provision/rotate-hmac/{agent_id}
  Révocation urgence : POST /provision/revoke-tenant/{tenant_id}

COMPOSANT 9 — Socle technique (Lot 0)
  Fichiers : Lot0_Socle/docker-compose.yml (188L), 01_schema_patched.sql (123L),
             01_schema_retention.sql, backup.sh, restore.sh
  6 services Docker : Kafka KRaft + TimescaleDB + Wazuh Indexer + Wazuh Manager +
                      Wazuh Dashboard + scoring-service. Healthchecks sur tous.

COMPOSANT 10 — Monitoring des modèles (Lot 3)
  Fichier : Lot3_IA/model_monitor.py (324 lignes)
  Méthodes: PSI (Population Stability Index), glissement σ, taux de FP, taux d'alertes.
  Seuils  : PSI > 0.10 = surveillance ; PSI > 0.25 = retraining requis.
  Endpoint: GET /monitor/drift?days=7
  CLI     : python model_monitor.py --demo

COMPOSANT 11 — Module PLG Product-Led Growth (Lot 8)
  Fichier         : Lot8_PLG/plg_api.py (712 lignes)
  Landing page    : Lot8_PLG/landing_page.html (1016 lignes, HTML/CSS/JS standalone)
  Schéma DB       : Lot8_PLG/01_schema_plg.sql (169 lignes)
  Build service   : Lot8_PLG/build_agent.py (242 lignes)
  Fonctionnement du parcours PLG :
    1. Utilisateur visite landing_page.html → clique "Essai gratuit 30 jours"
    2. Modal multi-étapes s'ouvre :
       Étape 1 : Email → /plg/check-email (live debounce)
                 → Bloque les emails jetables (liste statique de 50+ domaines)
                 → Redirige les domaines .gov.cm/.cm vers le flux souverain
       Étape 2 : Nom organisation + secteur (microfinance/assurance/cabinet/autre)
                 → /plg/register → envoie email de vérification
       Étape 3 : Vérification email (token urlsafe 32 bytes, /plg/verify-email)
       Étape 4 : Pré-autorisation bancaire 0 FCFA (/plg/preauth)
                 → Stub CinetPay (à remplacer par vraie API en prod)
                 → Fonction _run_preauth() = seul point à swapper pour CinetPay/PayDunya
    3. Succès : tenant auto-créé dans PostgreSQL + utilisateur DSI créé
                plan='trial', trial_ends_at=NOW()+30j, max_agents=5, max_daily_events=10000
    4. tenant_id + URL portail affichés à l'écran
  Flux Souverain : formulaire de contact dans la section #souverain de la landing page
                   → déclenche notification architecte NEXUS SOC (stub email)

COMPOSANT 12 — Terraform Déploiement Souverain (Lot 8)
  Répertoire : Lot8_PLG/terraform-souverain/ (10 fichiers, 1205 lignes total)
  Providers  : hashicorp/null (~3.2), tls (~4.0), local (~2.4), random (~3.6)
  Prérequis  : Terraform >= 1.6, serveur SSH avec sudo, Ubuntu 22.04+ recommandé
  Séquence (7 étapes, null_resource SSH provisioners) :
    1. server_prerequisites : Docker, vm.max_map_count=262144, structure /opt/nexus-soc/
    2. upload_configs        : .env, docker-compose.yml, 5 schémas SQL
    3. upload_scoring_service: scoring-service_app.py + 5 modules Python + requirements.txt
    4. upload_models         : model1/model2 .joblib (optionnel, si path fourni)
    5. wazuh_certs           : génération via wazuh/wazuh-certs-generator + fallback openssl
    6. stack_deploy          : docker compose up -d --wait --timeout 300
    7. health_check          : vérifie API, Kafka, PostgreSQL, Wazuh Indexer
  + backup_cron              : installe cron quotidien 02h00 après déploiement
  Secrets auto-générés : postgres_password (24 chars), jwt_secret (48), pseudo_secret (48),
                          wazuh_admin_password (20) — via random_password resources
  Certificat TLS : tls_self_signed_cert auto-signé, validité 1 an, pour nexus_domain + server_host
  Outputs sensibles : postgres_password, jwt_secret, wazuh_admin_password (sensitive=true)
  Output next_steps : guide post-déploiement complet inclus dans terraform output
  Templates : env.tpl, docker-compose.tpl (avec $${VAR} pour variables Docker Compose),
              Dockerfile.scoring.tpl (Python 3.11-slim, uvicorn, 2 workers)
  Idempotence : triggers = sha256(fichier) sur chaque null_resource → re-déploie seulement si changé

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
               ~80 features numériques après nettoyage
  Mode actuel: données synthétiques imitant CICIDS2017 (validation réelle au MINFI)
  Métriques :
    Isolation Forest : ROC-AUC 0.987 | PR-AUC 0.943
    Autoencodeur     : ROC-AUC 0.991 | PR-AUC 0.981
  Détection par type d'attaque :
    IF  : DDoS 99.5% | PortScan 84% | Bot/C2 96%
    AE  : DDoS 91%   | PortScan 98% | Bot/C2 100%
  Contamination : 0.05 (5 % d'anomalies estimées)
  Output : risque 0–100 + flag anomalie + score brut
  Fichier de sortie : model1_isoforest.joblib (dict : model, scaler, features, threshold, risk_cfg)
  Entraînement : python model1_anomaly_detection.py [--data-dir ./CICIDS2017]

MODÈLE 2 — Fraude interne UEBA
  Nom        : model2_isoforest.joblib
  Fichier    : model2_fraud_detection.py
  Rôle       : Détecter les comportements frauduleux dans SIGIPES (paie) et SYDONIA (douanes)
  Type       : Isolation Forest sur profils agrégés agent-jour
  Dataset    : CERT Insider Threat Dataset (CMU/SEI) comme référence théorique
    Lien     : https://kilthub.cmu.edu/articles/dataset/
    Synthétique pour la démo — adaptation à SIGIPES au stage MINFI.
  Features (10) — profil agent-jour :
    nb_connexions, nb_actions_hors_heures, nb_transactions,
    montant_total_modifie, nb_modifs_montant, nb_creations_compte,
    nb_exports, volume_donnees_exportees, nb_acces_dossiers_sensibles,
    nb_actions_total
  3 scénarios de fraude simulés :
    Faux mandatements     : 54 % détecté (zone grise légitime)
    Fonctionnaires fantômes: 76 % détecté
    Exfiltration fiscale  : 97 % détecté
  Contamination : 0.04 (4 % d'anomalies)
  Métriques    : ROC-AUC 0.969 | FPR 4 %
  Explicabilité : top-3 features déviantes en σ pour chaque alerte
  Output      : risque 0–100 + flag anomalie + liste de raisons
  Entraînement: python model2_fraud_detection.py [--data-file ./profils_agents.csv]

MODÈLE 3 — Détection de dérive (Lot 3)
  Fichier  : model_monitor.py (324 lignes)
  Méthodes : PSI, glissement σ, taux FP, taux d'alertes
  Seuils   : PSI>0.10 warning, >0.25 alarm → retraining requis

MODÈLES PROSPECTIFS (non implémentés, perspectives rapport) :
  LSTM temporel : séquences d'audit longues pour détecter APT lentes
  UEBA personnalisé : ligne de base par agent × rôle (nécessite 90j de données)
  Ensemble M1+AE : combinaison IF + autoencodeur (déjà justifiée par les métriques)

═══════════════════════════════════════════════════════════════════════════════════
SECTION 6 — STACK TECHNIQUE COMPLÈTE
═══════════════════════════════════════════════════════════════════════════════════

LANGAGE DE L'AGENT :
  Go 1.21+ — pur stdlib, aucune dépendance externe.
  Justification : binaire unique sans runtime, compilation croisée Linux/Windows offline,
  surface d'attaque minimale (~5 Mo, décision D6 verrouillée).
  garble (build-time uniquement, Lot 8 PLG) : obfuscation symboles/chaînes du binaire.
  Outil externe mais non-runtime → décision D6 non violée.

BACKEND API :
  Python 3.10+ + FastAPI
  Authentification : JWT HMAC-SHA256 maison (auth_middleware.py) — access 15 min,
  refresh 7 jours, sans dépendance PyJWT.
  Modules principaux :
    scoring-service_app.py (466L) — v2 + patch PLG
    auth_middleware.py (181L)
    pseudonymizer.py (196L)
    admin_api.py (409L)
    provisioning_api.py (701L)
    plg_api.py (712L) — NOUVEAU Lot 8

BASE DE DONNÉES :
  TimescaleDB (extension PostgreSQL 16) — port 5432
    Isolation multi-tenant : Row-Level Security (RLS) PostgreSQL
    Rôle client : nexus_app (non super-utilisateur — soumis à la RLS)
    Rôle analyste : nexus_analyst (BYPASSRLS — voit tous les tenants)
    Patch NULLIF : tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  Tables PLG (Lot 8) :
    plg_registrations (email, token vérif, preauth, tenant_id, IP, user_agent, secteur)
    trial_quotas (tenant_id, date, agent_count, event_count) — clé primaire composite
    subscriptions (tenant_id, plan, status, amount_fcfa, payment_reference)
    plan_config (plan, label_fr, amount_fcfa, max_agents, max_daily_events) — table de référence
    Colonnes ajoutées sur tenants : plan, trial_ends_at, suspended_at, max_agents, max_daily_events
  Vues PLG :
    v_trial_expiry : tenants en essai proches de l'expiration (pour alertes admin)
    v_active_subscriptions : abonnements actifs avec facturation
  Fonction PLG :
    suspend_expired_trials() → UPDATE tenants SET plan='expired' WHERE trial_ends_at < NOW()

PIPELINE DE DONNÉES :
  Apache Kafka 3.7.1 — mode KRaft (sans Zookeeper)
    Topics : nexus.telemetry.raw → nexus.telemetry → nexus.alerts
    Port interne : 9092 | Port hôte dev : 29092

STOCKAGE CHAUD SIEM :
  Wazuh Indexer 4.9.0 (basé sur OpenSearch — port 9200)
  Wazuh Manager 4.9.0 — ports 1514, 1515, 55000
  Wazuh Dashboard 4.9.0 — port 5601 (HTTPS)

DÉPLOIEMENT SOUVERAIN :
  Terraform >= 1.6
    Providers : hashicorp/null (SSH provisioners), hashicorp/tls (certs auto-signés),
                hashicorp/local (rendu templates), hashicorp/random (secrets auto-générés)
  Docker Compose v2 (pile sur serveur cible)
  Garble (obfuscation agent PLG) : go install mvdan.cc/garble@latest

ORCHESTRATION :
  Docker Compose v2 (développement/démo + déploiement souverain via Terraform)
  Kubernetes : NON implémenté — Docker Compose est la cible démo.
    Kubernetes listé en perspectives (Helm chart à créer).

CI/CD : NON implémenté dans le projet actuel.
  Perspective : GitHub Actions avec job build Go + tests Python.

MONITORING :
  model_monitor.py : dérive des modèles IA (PSI, σ-drift, taux FP)
  /health/detailed : healthcheck API multi-service (Kafka, DB, Wazuh)
  Docker healthchecks sur chaque conteneur

LLM LOCAL (optionnel) :
  Mistral 7B ou Llama 3 via Ollama ou vLLM (API compatible OpenAI, OLLAMA_BASE_URL)
  Mode désactivé par défaut — mode template est la voie nominale

FRONTEND :
  Landing page PLG  : Lot8_PLG/landing_page.html (1016L) — HTML/CSS/JS autonome (Lot 8)
  Portail client DSI: portail/portal/index.html — HTML/CSS/JS autonome (Lot 5)
  Console fournisseur: console_fournisseur.html (2912L) — HTML/CSS/JS (Lot 7)
  Design système : mode sombre ops center
    --bg: #0A0F1C | --surface: #0F1729 | --accent: #5EAAFF | --teal: #3DDC97
    --amber: #F5A524 | --red: #EF4444 | --text: #E2E8F0
    Polices : Fraunces (display/serif) + Manrope (body) + JetBrains Mono (mono)
    Bibliothèques : QRCode.js 1.5.3 + JSZip 3.10.1 (via CDN jsDelivr)

VARIABLES D'ENVIRONNEMENT CRITIQUES :
  POSTGRES_USER=nexus | POSTGRES_PASSWORD=change_me | POSTGRES_DB=nexus_soc
  DB_DSN=postgresql://nexus:change_me@postgres:5432/nexus_soc
  KAFKA_BOOTSTRAP=kafka:9092 | TELEMETRY_TOPIC=nexus.telemetry | ALERTS_TOPIC=nexus.alerts
  MODEL1_PATH=/models/model1_isoforest.joblib | MODEL2_PATH=/models/model2_isoforest.joblib
  RISK_THRESHOLD=70
  JWT_SECRET=CHANGE_ME_IN_PRODUCTION (32 octets aléatoires)
  PSEUDO_SECRET=CHANGE_ME_PSEUDO_SECRET
  RATE_LIMIT_REQ=100 / RATE_LIMIT_WIN=60 (req/min global)
  INGEST_LIMIT_REQ=30 / INGEST_LIMIT_WIN=60 (req/min /ingest)
  ACCESS_TOKEN_TTL_S=900 | REFRESH_TOKEN_TTL_S=604800
  CORR_WINDOW_MIN=30 | MASS_FILE_THRESHOLD=20 | ACCOUNT_CREATE_THRESHOLD=5
  WAZUH_API_URL=https://localhost:9200
  OLLAMA_BASE_URL=http://localhost:11434/v1 (optionnel)
  NEXUS_SERVER_URL=https://nexussoc.cm | NEXUS_AGENT_VERSION=1.0.0
  BACKUP_DEST=/opt/nexus-backups | KEEP_DAYS=14

═══════════════════════════════════════════════════════════════════════════════════
SECTION 7 — FONCTIONNALITÉS DÉTAILLÉES
═══════════════════════════════════════════════════════════════════════════════════

MULTI-TENANT :
  Architecture : une seule instance héberge TOUS les tenants.
  Isolation   : Row-Level Security PostgreSQL — chaque requête API injecte
                SET app.current_tenant = '<uuid>' avant les requêtes.
  Rôle client : nexus_app (non super-user) — filtré par RLS.
  Rôle analyste: nexus_analyst (BYPASSRLS) — voit tous les tenants.
  Patch critique: NULLIF(current_setting('app.current_tenant', true), '')::uuid
  Validé par : 8/8 assertions sur PostgreSQL 16 réel (rls_analyst_test.py).
  Tables avec RLS : alerts, agents, soar_audit.

DÉPLOIEMENT AUTOMATISÉ DES AGENTS (Lot 7 + Lot 8) :
  Méthode 1 — Console fournisseur (Lot 7) :
    Générer token → copier one-liner curl|bash (Linux) ou irm|iex (Windows)
    Expiration configurable, usage unique, binding hostname
  Méthode 2 — Bulk CSV :
    Importer hostname,os,description → token généré par ligne → CSV exportable
  Méthode 3 — Pack offline (.zip) :
    Binaire + config.json + scripts d'installation — pour postes sans internet
  Méthode 4 — QR Code :
    QR scannable → commande curl sur terminal (via QRCode.js)
  Méthode 5 — Ansible :
    ansible_nexus_agent.yml — déploiement de masse Linux
  Méthode 6 — Agent PLG (coquille vide, Lot 8) :
    Compilé dynamiquement par tenant via build_agent.py (garble + watermark)
    Téléchargeable via GET /provision/agent-binary?tenant_id=xxx&os=linux&arch=amd64

FLUX PLG COMPLET (Lot 8) :
  1. landing_page.html → bouton "Essai gratuit 30 jours" → modal multi-étapes
  2. Étape 1 : /plg/check-email (debounce 300ms)
     → Bloque emails jetables (50+ domaines : mailinator, yopmail, guerrillamail…)
     → Redirige domaines .gov.cm, .gouv.cm, .mil.cm, .edu.cm, .cm → souverain
  3. Étape 2 : /plg/register → crée plg_registrations + envoie email vérification
  4. Étape 3 : /plg/verify-email (token urlsafe 32 bytes)
  5. Étape 4 : /plg/preauth (stub CinetPay — swap pour prod)
  6. Auto-provisioning : tenant créé dans PostgreSQL + user DSI + trial activé
  7. tenant_id affiché + lien portail DSI
  Gestion des quotas trial :
    Max 5 agents | Max 10 000 events/jour | Durée 30 jours
    Enforcement synchrone dans _enforce_trial_quota_sync() appelé par /ingest
    Réponses HTTP : 402 (suspendu/expiré) ou 429 (quota dépassé)

DÉPLOIEMENT SOUVERAIN (Lot 8 Terraform) :
  1. Formulaire "Contacter un architecte" → email → qualification
  2. terraform.tfvars configuré (server_host, institution_name, nexus_domain, ssh_key)
  3. terraform apply → 7 étapes SSH (prérequis, configs, sources, modèles, certs, compose, santé)
  4. Cron sauvegarde 02h00 installé automatiquement
  5. Secrets récupérés via : terraform output -raw <secret>
  6. Modèles IA uploadés via scp + docker compose restart scoring-service

LLM ANALYST MULTILINGUE (Lot 5) :
  Mode template (DÉFAUT) : explication déterministe 3–5 phrases, aucune hallucination.
  Mode LLM (OPTIONNEL) : Mistral/Llama via API OpenAI-compatible.
  Bilingue : --lang fr (français) ou --lang en (anglais)
  SMS FR : max 160 car. ex. "🚨 NEXUS SOC — Rançongiciel sur POSTE-COMPTA-07 · risque 100/100."
  WhatsApp hebdo : score, incidents, conseils, lien rapport.

IRP AUTOMATISÉE — 6 phases (Lot 4) :
  Phase 1 — Détection    : agent Go → Kafka → Pipeline → modèles IA → alerte.
  Phase 2 — Analyse      : LLM Analyst génère l'explication + explicabilité des features.
  Phase 3 — Confinement  : SOAR exécute isolate_host / freeze_account / block_ip.
  Phase 4 — Éradication  : snapshot_memory / reset_password / preserve_logs.
  Phase 5 — Récupération : rollback des actions réversibles si nécessaire.
  Phase 6 — Leçons       : journal_investigation + rapport WhatsApp hebdomadaire.

NIVEAUX D'AUTOMATISATION :
  Mode Observe (dry_run=True)    : toutes les actions proposées, aucune exécutée.
  Mode Semi-auto (défaut prod)   : LOW/MEDIUM auto si risque ≥ 70. HIGH → validation humaine.
  Mode Auto complet              : toutes actions automatiques. NON recommandé par défaut.

3 TYPES D'UTILISATEURS ET LEURS DROITS :
  admin_plateforme (Super Admin — côté fournisseur) :
    → CRUD tenants (+ PLG : suspendre/réactiver abonnements)
    → Gestion utilisateurs, provisioning agents, santé système, facturation
    → BYPASSRLS sur toutes les tables
  analyste_soc (Analyste SOC — côté fournisseur) :
    → File d'alertes cross-tenants, approbation SOAR, dashboard SOC
    → SELECT toutes tables (BYPASSRLS), UPDATE limité sur soar_audit
  dsi_client (DSI Client — côté tenant) :
    → Portail Lot 5 : données de SON organisation uniquement (RLS)
    → Actions SOAR de sa propre organisation

WORKFLOWS COMPLETS :

  Workflow Déploiement Souverain :
    [Formulaire "Contacter un architecte" sur landing_page.html]
    → email équipe NEXUS SOC → qualification 48h (cartographie SI, contraintes souveraineté)
    → Proposition Hub & Spoke → Déploiement Terraform SSH (terraform apply ~15 min)
    → Provisioning masse Ansible → Formation DSI + SIEM
    → Contrat annuel + SLA 1h activé + démarche ANTIC initiée

  Workflow Admin Plateforme (Console Fournisseur Module A) :
    Matin → /admin/health → tenants trial expirant <5j → agents offline
    Provisioning → modal console → one-liner curl|bash → scp modèles IA
    Facturation → POST /plg/suspend (non-paiement) → POST /plg/resume (paiement reçu)
    Sécurité → /provision/revoke-tenant (urgence) → /provision/rotate-hmac

  Workflow Analyste SOC (Console Fournisseur Module B) :
    File alertes → triage → modal détail (kill-chain + LLM + raisons σ)
    Approbation SOAR (actions HIGH) → Approuver/Refuser/Rollback
    Métriques → MTTD par tenant → taux FP → signalement retraining si >10% FP
    Rapport hebdo → notifier.py → WhatsApp (templates Meta requis en prod)

═══════════════════════════════════════════════════════════════════════════════════
SECTION 8 — RISQUES ET LIMITES
═══════════════════════════════════════════════════════════════════════════════════

RISQUES TECHNIQUES AVEC MESURES D'ATTÉNUATION :

  R1. Données synthétiques — validation terrain absente [criticité ÉLEVÉE]
    Statut : risque documenté. Chiffres valides comme ordre de grandeur, pas preuve terrain.
    Atténuation : adaptation aux données SIGIPES/SYDONIA pendant le stage MINFI.

  R2. Dérive des modèles dans le temps [criticité ÉLEVÉE]
    Statut : model_monitor.py implémenté (PSI + σ-drift). Seuils documentés.
    Atténuation prévue : DVC/MLflow (post-stage).

  R3. Faux mandatement — 54 % de détection [criticité MOYENNE]
    Statut : limite documentée honnêtement.
    Atténuation prévue : UEBA personnalisé par agent×rôle + LSTM temporel.

  R4. Bug O(N²) dans detect_mass_file_change [RÉSOLU]
    Fichier : correlation_engine_v2.py.

  R5. Validation HMAC absente sur /ingest [RÉSOLU]
    Fichier : scoring-service_app.py v2.

  R6. Authentification JWT incomplète [RÉSOLU]
    Fichier : auth_middleware.py.

  R7. Rate limiting absent [RÉSOLU]
    100 req/min global, 30 req/min /ingest, HTTP 429 avec Retry-After.

  R8. Single point of failure [criticité ÉLEVÉE en production]
    Statut : Docker Compose mono-nœud pour la démo.
    Atténuation prévue : Kubernetes + Kafka multi-broker + PostgreSQL réplication.

  R9. Pas de chiffrement au repos [criticité MOYENNE]
    Atténuation prévue : LUKS, pgcrypto sur volumes.

  R10. Secrets en clair dans config.json [criticité ÉLEVÉE]
    chmod 600 + ACL Windows implémentés. Clé HMAC en clair reste un risque.
    Atténuation prévue : DPAPI Windows / Linux Keyring.

  R11. Cache agent PLG : fichier .nexus_cfg_cache altérable [MITIGÉ]
    HMAC tag [32 bytes] préfixé au payload gzip — toute altération détectée.
    Si HMAC invalide : suppression du cache + tentative de re-fetch serveur.

  R12. Pré-autorisation bancaire PLG = stub [BLOQUANT en prod]
    La fonction _run_preauth() dans plg_api.py accepte tout token non vide.
    À remplacer par l'intégration CinetPay ou PayDunya avant déploiement réel.

RISQUES HUMAINS :
  Analystes SOC rares au Cameroun → la plateforme automatise pour compenser.
  Validation humaine : si l'analyste est absent, les actions HIGH s'accumulent.
  Formation des clients non incluse dans le produit.

RISQUES LIÉS AUX MODÈLES IA :
  Absence de MLOps — pas de versioning, pas de déploiement automatique.
  Pas de feedback loop (FP marqués par analystes ne mettent pas à jour le modèle).
  Biais des données synthétiques.

RISQUES JURIDIQUES :
  Données personnelles dans les alertes → pseudonymizer.py implémenté.
  Conformité ANTIC non validée → démarche administrative requise.
  WhatsApp templates Meta non soumis → bloquant en production.
  Responsabilité contractuelle non définie.

LIMITES INTRINSÈQUES PERMANENTES :
  Données synthétiques → métriques sont des ordres de grandeur.
  Connecteurs SOAR simulés → gel de compte et isolation ne s'exécutent pas réellement.
  Fenêtre corrélation 30 min → APT lentes non détectées.
  Pas de détection basée sur le contenu (YARA, sandbox).
  macOS non supporté par l'agent Go.

CE QUE NEXUS SOC NE REMPLACE PAS :
  Un pare-feu, un antivirus/EDR, un RSSI humain, les audits de conformité ANTIC.

═══════════════════════════════════════════════════════════════════════════════════
SECTION 9 — MODÈLE ÉCONOMIQUE
═══════════════════════════════════════════════════════════════════════════════════

NIVEAUX D'ABONNEMENT :

  Essai gratuit (PLG) — 0 FCFA / 30 jours
    Cible : auto-service via landing_page.html
    Agents : 5 postes maximum
    Events : 10 000 événements/jour maximum
    Fonctionnalités : portail DSI, alertes email, LLM Analyst mode template
    Identité validée par pré-autorisation bancaire 0 FCFA

  Starter — 25 000 FCFA/mois (~41 USD/mois)
    Cible : cabinets comptables ONECCA, petites microfinances
    Agents : jusqu'à 10 postes | 50 000 events/jour
    Fonctionnalités : portail DSI, alertes email, LLM Analyst mode template
    Support : tickets email

  Business — 75 000 FCFA/mois (~124 USD/mois)
    Cible : microfinances COBAC moyennes, assurances CIMA
    Agents : jusqu'à 50 postes | 200 000 events/jour
    Fonctionnalités : + Modèle 2 UEBA, notifications SMS + WhatsApp, SOAR semi-auto
    Support : tickets + 1 session de formation/mois

  Enterprise — 200 000 FCFA/mois (~330 USD/mois)
    Cible : grandes microfinances, assurances nationales
    Agents : jusqu'à 200 postes | 1 000 000 events/jour
    Fonctionnalités : + Modèle 1 réseau, SOAR complet, tableau de bord SOC, API
    Support : SLA 4h, accès analyste SOC dédié

  Contrat public — tarif annuel négocié
    Cible : administrations publiques camerounaises
    Agents : illimités | Hébergement : souverain (Terraform souverain Lot 8)
    Fonctionnalités : toutes + intégration SIGIPES/SYDONIA + conformité ANTIC
    Support : SLA 1h, analyste SOC dédié, formation des équipes DSI

COMPARAISON :
  CrowdStrike Falcon : ~400-800 USD/agent/an → 200 postes = 80 000–160 000 USD/an
                       vs NEXUS Enterprise = 2 400 USD/an (33 à 66x moins cher)
  Splunk SIEM       : 10 000–50 000 USD/an + ingénieurs certifiés
  Wazuh seul        : gratuit mais nécessite 2–3 ingénieurs internes

MARCHÉ CIBLE AU CAMEROUN :
  ~400 microfinances agréées COBAC (source COBAC 2023)
  ~150 compagnies d'assurance zone CIMA
  ~300 cabinets comptables ONECCA
  ~150 administrations publiques avec SI
  Taille estimée : ~5 Md FCFA/an si pénétration 10 % des microfinances

═══════════════════════════════════════════════════════════════════════════════════
SECTION 10 — AMÉLIORATIONS PRÉVUES
═══════════════════════════════════════════════════════════════════════════════════

Toutes ces améliorations sont PROSPECTIVES (non implémentées) — chapitre "Perspectives".

  1. UEBA personnalisé par agent×rôle
     Ligne de base individuelle. Nécessite 90+ jours de données réelles.
     Impact : améliorer les 54 % de détection des faux mandatements.

  2. LSTM temporel pour la détection d'APT
     Analyser les séquences d'actions dans le temps.
     Nécessite séquences d'audit réelles longues (SIGIPES 6+ mois).

  3. LLM Analyst — Mistral local en remplacement du mode template
     Mistral 7B hébergé localement (Ollama) + RAG sur base de connaissances NEXUS.

  4. Ensemble M1 + Autoencodeur
     Combiner IF et autoencodeur pour la détection réseau.

  5. Connecteurs SOAR réels
     AD/LDAP (freeze_account réel), pare-feu périmétrique (block_ip réel),
     EDR (isolate_host réel), passerelle SMS Orange/MTN Business.

  6. Intégration CinetPay / PayDunya (PLG)
     Remplacer _run_preauth() dans plg_api.py par l'API CinetPay (Cameroun)
     ou PayDunya. Un seul point de swap, API conçue pour ça.

  7. Templates WhatsApp Business approuvés par Meta
     Soumettre les templates de rapports hebdomadaires.

  8. Détection d'arnaques spécifiques au Cameroun
     SIM swapping, faux appels d'offres, fraude administrative.
     Règles SIEM spécifiques dans correlation_engine_v2.py.

  9. IA prédictive
     Prédire les postes à risque avant incident (score de vulnérabilité comportementale).

  10. Protection Wi-Fi
      Détection points d'accès non autorisés et attaques Man-in-the-Middle.
      Sonde Raspberry Pi + hostapd en mode monitor.

  11. Email Security Gateway intégrée
      Analyse pièces jointes et liens dans les emails entrants.

  12. Mode dégradé connexion lente
      L'agent réduit fréquence de collecte et compresse davantage sur <1 Mbps.

  13. Rapport WhatsApp hebdomadaire automatique
      DÉJÀ IMPLÉMENTÉ en mode template (notifier.py). Templates Meta requis en prod.

  14. Application mobile DSI
      Android/iOS pour le DSI client : alertes push, approbation SOAR smartphone.
      Technologie : React Native ou Flutter.

  15. Conformité réglementaire automatique
      Dashboard de conformité ANTIC / ISO 27001 avec checklist des contrôles.

  16. Architecture HA — Kubernetes
      Kafka multi-broker, PostgreSQL réplication streaming.
      Helm chart à créer pour déploiement Kubernetes.

  17. MLOps — pipeline de ré-entraînement automatique
      DVC (versioning modèles) + MLflow (tracking expériences).
      Déclenchement automatique si PSI > 0.25.

  18. CI/CD — GitHub Actions
      Job build Go + tests Python + push image Docker.

  19. mTLS / PKI interne
      Certificats machine signés par PKI interne (CFSSL, Vault, Smallstep).
      Pour déploiements souverains nécessitant une chaîne de confiance complète.

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

  L'architecture repose sur huit composants intégrés : un agent de collecte léger écrit en
  Go (~5 Mo, egress-only), un pipeline de normalisation et de corrélation SIEM mappé sur
  MITRE ATT&CK, deux modèles d'intelligence artificielle (Isolation Forest pour les anomalies
  réseau et UEBA pour la fraude interne), un moteur SOAR à garde-fous, un module de
  restitution bilingue français/anglais, une console opérateur multi-tenant, un module
  Product-Led Growth automatisé pour les microfinances, et un module de déploiement
  souverain Terraform pour les administrations publiques.

  La plateforme adopte un modèle économique double : abonnement mensuel (25 000 à
  200 000 FCFA) pour le secteur financier non bancaire, et contrat souverain pour les
  administrations publiques. Les résultats mesurés sur jeux synthétiques réalistes
  démontrent une couverture MITRE de 7/7 techniques, un MTTD de 90 secondes pour
  l'exfiltration et 120 secondes pour le ransomware, une isolation multi-tenant vérifiée en
  8/8 assertions, et des ROC-AUC de 0,987 et 0,969 pour les modèles réseau et fraude interne.

ABSTRACT IN ENGLISH (200 words) :
  Cybersecurity in Cameroonian organizations faces a structural deficit: public administrations
  and financial SMEs lack the human and financial resources to deploy an internal Security
  Operations Center (SOC). This work presents NEXUS SOC, a mutualized, sovereign, and
  affordable SOC-as-a-Service platform designed for the Cameroonian context.

  The architecture relies on eight integrated components: a lightweight Go collection agent
  (~5 MB, egress-only), a SIEM normalization and correlation pipeline mapped to MITRE ATT&CK,
  two artificial intelligence models (Isolation Forest for network anomalies and UEBA for
  internal fraud), a SOAR engine with guardrails, a bilingual French/English reporting module,
  a multi-tenant operator console, a Product-Led Growth automated module for microfinances,
  and a Terraform sovereign deployment module for public administrations.

  The platform adopts a dual business model: monthly subscription (25,000 to 200,000 XAF) for
  the non-banking financial sector, and a sovereign contract for public administrations.
  Results measured on realistic synthetic datasets demonstrate MITRE coverage of 7/7 techniques,
  MTTD of 90 seconds for exfiltration and 120 seconds for ransomware, multi-tenant isolation
  verified in 8/8 assertions on real PostgreSQL, and ROC-AUC scores of 0.987 and 0.969 for the
  network anomaly and internal fraud models respectively.

MOTS-CLÉS FR :
  SOC-as-a-Service, cybersécurité souveraine, détection d'intrusion, MITRE ATT&CK,
  Isolation Forest, UEBA, SOAR, multi-tenant, Product-Led Growth, Terraform,
  Cameroun, ANTIC, fraude interne, agent léger, corrélation SIEM, intelligence artificielle

KEYWORDS EN :
  SOC-as-a-Service, sovereign cybersecurity, intrusion detection, MITRE ATT&CK,
  Isolation Forest, UEBA, SOAR, multi-tenant, Product-Led Growth, Terraform,
  Cameroon, ANTIC, insider threat, lightweight agent, SIEM correlation, artificial intelligence

PROBLÉMATIQUE PRÉCISE :
  « Comment concevoir et implémenter une plateforme de Security Operations Center
  accessible aux organisations camerounaises de taille moyenne — administrations publiques,
  microfinances et cabinets comptables — en conjuguant souveraineté numérique (hébergement
  local), abordabilité économique (modèle de mutualisation), automatisation intelligente
  (IA + SOAR), acquisition clients automatisée (PLG) et restitution en langue française,
  dans un contexte marqué par des ressources humaines en cybersécurité rares et une
  connectivité réseau variable ? »

JUSTIFICATION DU PROJET :
  1. Menaces réelles documentées : ransomware sur administrations africaines (2022–2024),
     fraudes sur paie publique (fonctionnaires fantômes), exfiltrations fiscales, phishing
     ciblant les microfinances.
  2. Absence de solutions adaptées : CrowdStrike/Splunk hors budget et hors souveraineté.
     Wazuh seul sans expertise interne est inutile. Pas de SOCaaS francophone souverain.
  3. Cadre légal : loi 2010/012 impose des mesures de sécurité aux SI traitant des données
     personnelles.
  4. Impact mesurable : MTTD de 90–120 s (vs plusieurs semaines dans les incidents non
     monitorés en Afrique subsaharienne — IBM Cost of a Data Breach 2023).
  5. Modèle PLG innovant : premier SOCaaS africain avec flux d'acquisition self-service
     et déploiement souverain automatisé (Terraform).

POSITIONNEMENT PAR RAPPORT À L'EXISTANT :
  CrowdStrike Falcon EDR : 400–800 USD/agent/an, cloud américain, pas souverain, pas de
    version française, trop cher. NEXUS SOC : 2x–66x moins cher, cloud local, français.
  Splunk SIEM : $10K–50K/an, nécessite ingénieurs certifiés. NEXUS SOC : clé en main.
  SentinelOne : même problème que CrowdStrike. Pas d'offre africaine.
  Wazuh (open source) : gratuit mais nécessite 2–3 ingénieurs, pas de mutualisation,
    pas de modèles IA contextualisés, pas de restitution bilingue, pas de SOAR.
  Solutions africaines : très peu documentées, pas de SOCaaS certifié en Afrique centrale
    francophone. NEXUS SOC est pionnier dans ce segment.

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

├── README.md (893 lignes) — guide complet : interfaces, Docker, standalone, PLG, Terraform
├── INVENTAIRE.md — catalogue général des livrables
├── NEXUS_SOC_Contexte_Complet.md — ce fichier (prompt de reprise)

LOT 0 — Socle technique
├── Lot0_Socle/docker-compose.yml (188 lignes)
│   6 services : Kafka KRaft + TimescaleDB + Wazuh Indexer + Manager + Dashboard + scoring.
│   Healthchecks sur tous les services, start_period adapté.
├── Lot0_Socle/01_schema_patched.sql (123 lignes)
│   Tables : tenants, users, agents, alerts, soar_audit, metrics (hypertable TimescaleDB).
│   RLS sur alerts, agents, soar_audit. Patch NULLIF. 2 tenants démo.
├── Lot0_Socle/01_schema_retention.sql
│   Compression TimescaleDB métriques après 7j, archivage alertes après 1an,
│   purge tokens expirés, table retention_policy par offre.
├── Lot0_Socle/backup.sh — Sauvegarde PostgreSQL + Wazuh snapshot + modèles + config.
│   Rotation automatique sur KEEP_DAYS jours (défaut 14).
└── Lot0_Socle/restore.sh — Restauration PostgreSQL + modèles + Wazuh snapshot.

LOT 1 — Agent Go + Service de scoring
├── Lot1_Agent_Go/nexus-agent.zip
│   main.go, collect.go (Linux+Windows), buffer.go (store-and-forward), sender.go (HMAC+gzip)
│   Taille binaire : 5.0 Mo Linux, 5.3 Mo Windows.
├── Lot1_Agent_Go/scoring-service_app.py (466 lignes — VERSION v2 + PATCH PLG)
│   FastAPI v2 + validation HMAC + Bearer token + rate limiting (100/min global, 30/min /ingest)
│   + /health/detailed + consommateur Kafka + score M1+M2 + emit alert
│   PATCH PLG : _enforce_trial_quota_sync() (+75 lignes) appelée dans /ingest
│   → vérifie plan, suspended_at, trial_ends_at, agents_today, events_today
│   → HTTP 402 si suspendu/expiré, HTTP 429 si quota dépassé, incrémente trial_quotas
├── Lot1_Agent_Go/auth_middleware.py (181 lignes)
│   JWT HMAC-SHA256 : create_token, decode_token, require_role(*roles).
│   Endpoints : POST /auth/token, POST /auth/refresh, GET /auth/me.
│   Access TTL 15 min, Refresh TTL 7 jours.
├── Lot1_Agent_Go/pseudonymizer.py (196 lignes)
│   Pseudonymisation HMAC-SHA256 stable : emails, IPs publiques, agent_ids, DOMAIN\user.
│   AlertPseudonymizer.process(alert) → remplace les PII par pseudonymes.
└── Lot1_Agent_Go/telemetry_sample.json (59 événements réels)

LOT 2 — Pipeline SIEM
├── Lot2_Pipeline_SIEM/nexus-pipeline.zip
│   normalizer.py, correlation_engine.py (v1), telemetry_gen.py, make_lot2_figures.py
└── Lot2_Pipeline_SIEM/correlation_engine_v2.py (335 lignes — correctif)
    O(N²) → O(N) sur detect_mass_file_change (deux pointeurs).
    Nouvelles règles T1027, T1136, T1083. Fenêtre configurable CORR_WINDOW_MIN.
    Mode --benchmark inclus.

LOT 3 — Modèles IA
├── Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py → model1_isoforest.joblib
│   ROC-AUC 0.987, PR-AUC 0.943
├── Lot3_IA/Modele1_Anomalie_reseau/model1_advanced.py (autoencodeur)
│   ROC-AUC 0.991, PR-AUC 0.981
├── Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py → model2_isoforest.joblib
│   ROC-AUC 0.969, FPR 4%
└── Lot3_IA/model_monitor.py (324 lignes)
    PSI, σ-drift, taux FP, taux alertes. Endpoint GET /monitor/drift. CLI --demo.

LOT 4 — SOAR
├── Lot4_SOAR/soar_engine.py (285 lignes)
│   9 connecteurs, 4 playbooks, auto_threshold=70, validation HIGH, rollback, CSV.
└── Lot4_SOAR/audit_log.csv

LOT 5 — Restitution bilingue
└── Lot5_Restitution/nexus-portail.zip
    portail/portal/index.html : portail DSI HTML autonome, bilingue FR/EN, mode sombre.
    portail/notifier.py : LLM Analyst (mode template + mode llm optionnel).

LOT 6 — Tests et mesures
└── Lot6_Tests/nexus-tests.zip
    attack_simulation.py : 7/7 techniques, 3/3 scénarios, MTTD mesuré.
    load_test.py : ~200 000 ev/s normalisation, p99 ≤ 12 μs.
    rls_isolation_test.py : 5/5 assertions nexus_app.
    make_lot6_figures.py : génère figures PNG pour le rapport.

LOT 7 — Console Fournisseur + Provisioning
├── Lot7_Console_Fournisseur/console_fournisseur.html (2912 lignes)
│   Module A (admin) + Module B (analyste SOC). Design mode sombre. Bilingue FR/EN.
├── Lot7_Console_Fournisseur/admin_api.py (409 lignes)
│   /admin/* : tenants, users, agents, health, billing. /analyst/* : alerts, approve, dashboard.
├── Lot7_Console_Fournisseur/provisioning_api.py (701 lignes)
│   /provision/token (lifecycle), /provision/enroll, /provision/installer/{id},
│   /provision/offline-pack/{id}, /provision/qr/{id}, /provision/status/{id},
│   /provision/bulk, /provision/oneliner, /provision/rotate-hmac/{id},
│   /provision/revoke-tenant/{id}
├── Lot7_Console_Fournisseur/rls_analyst_test.py (277 lignes)
│   8/8 assertions : 5 nexus_app (RLS filtré) + 3 nexus_analyst (BYPASSRLS).
├── Lot7_Console_Fournisseur/01_schema_analyst.sql (rôle nexus_analyst BYPASSRLS)
├── Lot7_Console_Fournisseur/01_schema_provisioning.sql
│   Colonnes lifecycle tokens (expires_at, used_at, binding_host, one_time).
│   Vue v_agent_token_status, tables enrollment_log, bulk_provisioning.
└── Lot7_Console_Fournisseur/install_templates/
    install_linux.sh, install_windows.ps1, nexusagent.service, ansible_nexus_agent.yml, config.json.j2

LOT 8 — PLG + Déploiement Souverain (NOUVEAU — session 29 mai 2026)
├── Lot8_PLG/landing_page.html (1016 lignes)
│   Vitrine duale SaaS / Souverain. Design système complet (Fraunces/Manrope/JetBrains Mono).
│   Modal multi-étapes 4 étapes (email → org → verify → preauth → success).
│   Section #souverain avec formulaire de contact.
│   Stats hero (400 microfinances, 90s MTTD, 7/7 MITRE, 0.987 AUC).
│   JS : check-email live debounce, registration flow complet, auto-vérification token URL.
│
├── Lot8_PLG/plg_api.py (712 lignes)
│   Endpoints : /plg/check-email, /plg/register, /plg/verify-email, /plg/preauth,
│               /plg/trial-status/{tenant_id}, /plg/plans, /plg/upgrade,
│               /plg/suspend/{tenant_id}, /plg/resume/{tenant_id},
│               /plg/run-expiry-check, /plg/agent/config/{agent_id}
│   DISPOSABLE_DOMAINS : frozenset de 50+ domaines jetables connus
│   GOV_DOMAIN_PATTERNS : 14 patterns regex pour domaines souverains camerounais
│   _enforce_trial_quota_sync() : version asyncpg (utilisée dans Kafka consumer)
│   _run_preauth() : stub CinetPay — seul point à remplacer pour prod
│   _provision_tenant() : crée tenant + user DSI en transaction PostgreSQL
│   _send_verification_email() : stub SMTP — logger + URL pour démo
│
├── Lot8_PLG/01_schema_plg.sql (169 lignes)
│   ALTER TABLE tenants : plan, trial_ends_at, suspended_at, max_agents, max_daily_events, type
│   CREATE TABLE plg_registrations : id, email UNIQUE, organization_name, sector,
│     email_verified, verification_token UNIQUE, preauth_completed, preauth_reference,
│     tenant_id FK, ip_address INET, user_agent
│   CREATE TABLE trial_quotas : (tenant_id, date) PK, agent_count, event_count
│   CREATE TABLE subscriptions : plan, status, started_at, ends_at, amount_fcfa
│   CREATE TABLE plan_config : données de référence (trial/starter/business/enterprise)
│   VIEW v_trial_expiry : tenants trial avec days_remaining et quotas du jour
│   VIEW v_active_subscriptions : abonnements actifs avec tenant_name
│   FUNCTION suspend_expired_trials() : UPDATE + GET DIAGNOSTICS, retourne le count
│   INDEX idx_tenants_plan, idx_tenants_trial_ends (WHERE plan='trial'),
│         idx_tenants_suspended, idx_trial_quotas_tenant_date,
│         idx_subscriptions_tenant, idx_plg_reg_token (WHERE NOT email_verified)
│
├── Lot8_PLG/build_agent.py (242 lignes)
│   compute_watermark(tenant_id, salt) : HMAC-SHA256(JWT_SECRET, tenant_id:salt) → hex
│   build_agent_binary(tenant_id, target_os, target_arch, server_url, use_garble) : async
│     → génère salt aléatoire, injecte TenantID/WatermarkKey/WatermarkSalt/ServerURL via ldflags
│     → compile avec garble -tiny -seed <salt> ou go build en fallback
│     → retourne Path du binaire dans BUILD_OUT_DIR
│   cleanup_old_binaries() : purge binaires > BINARY_TTL_S (300s)
│   register_build_route(app) : monte GET /provision/agent-binary sur FastAPI
│   CLI : --tenant-id, --os, --arch, --server-url, --no-garble
│
├── Lot8_PLG/nexus-agent-plg/watermark.go (28 lignes)
│   Variables injectées via ldflags : TenantID, WatermarkKey, WatermarkSalt, ServerURL, AgentVersion
│   WatermarkHeader() : retourne les 16 premiers hex du watermark
│
├── Lot8_PLG/nexus-agent-plg/config_fetcher.go (249 lignes)
│   RemoteConfig struct : AgentID, TenantIDServer, IntervalSec, WatchDirs, MaxQueueMB,
│     TrialActive, MaxAgents, MaxDailyEvents, ConfigVersion, IssuedAt, Signature
│   ConfigCache struct : RWMutex, current *RemoteConfig, cacheFile, hmacKey
│   InitConfigFetcher(cfg) : essaie remote → fallback cache
│   StartConfigRefreshLoop(cfg) : goroutine refresh toutes les 5 minutes
│   CurrentConfig() : accès thread-safe
│   fetchRemoteConfig(cfg) : GET /plg/agent/config/{id} + vérification HMAC signature
│   verifyServerSignature(rc) : HMAC-SHA256(WatermarkKey, json.Marshal(rc sans sig))
│   persistCache / loadCache : format [32 bytes HMAC tag][gzip payload], chmod 600
│     → HMAC vérifié à la lecture, suppression + erreur si altéré
│
├── Lot8_PLG/nexus-agent-plg/main_plg.go (114 lignes)
│   InitPLG(cfg) : InitConfigFetcher + applyRemoteConfig + StartConfigRefreshLoop + SIGHUP watch
│   ShutdownPLG() : ferme stopCh
│   applyRemoteConfig(cfg, rc) : surcharge WatchDirs, IntervalSec, MaxQueueMB (PAS les secrets)
│   watchSignals(cfg) : goroutine SIGHUP → re-fetch config
│   InjectWatermarkHeader(headers) : ajoute X-Nexus-Watermark, X-Nexus-Tenant, X-Nexus-Version
│
├── Lot8_PLG/terraform-souverain/providers.tf (47 lignes)
│   required_version >= 1.6, providers null/tls/local/random
│   Commentaires backend S3 + MinIO (backend souverain optionnel)
│
├── Lot8_PLG/terraform-souverain/variables.tf (179 lignes)
│   20 variables avec descriptions, types, validations, defaults
│   Sensibles : postgres_password, jwt_secret, pseudo_secret, wazuh_admin_password
│   Versioning : wazuh_version(4.9.0), kafka_version(3.7.1), timescale_version(2.15.3-pg16)
│   Tuning : wazuh_jvm_heap_mb (min 512), risk_threshold (70), ingest_rate_limit (30)
│
├── Lot8_PLG/terraform-souverain/main.tf (580 lignes)
│   10 ressources Terraform :
│   random_password.{postgres,jwt,pseudo,wazuh_admin} (secrets auto-générés)
│   tls_private_key.nexus + tls_self_signed_cert.nexus (RSA4096, 1 an, dns+ip)
│   local_sensitive_file.env (chmod 600) + local_file.{compose,dockerfile_scoring}
│   null_resource.server_prerequisites (Docker, vm.max_map_count, dirs)
│   null_resource.upload_configs (env, compose, 5 schémas SQL, certs TLS)
│   null_resource.upload_scoring_service (triggers=sha256 des 6 sources Python + Dockerfile)
│   null_resource.upload_models (count = var.models_local_path != "" ? 1 : 0)
│   null_resource.wazuh_certs (idempotent + fallback openssl)
│   null_resource.stack_deploy (triggers=hash compose+env+scoring)
│   null_resource.health_check (vérifie API+Kafka+PostgreSQL+Wazuh)
│   null_resource.backup_cron (cron 02h00 quotidien)
│
├── Lot8_PLG/terraform-souverain/outputs.tf (127 lignes)
│   nexus_api_url, nexus_api_docs, wazuh_dashboard_url, wazuh_api_url
│   tls_certificate_pem (public, non sensible), tls_cert_expiry
│   postgres_password, jwt_secret, wazuh_admin_password (sensitive=true)
│   deployment_summary (objet complet : institution, domain, server, versions, tls_expiry)
│   next_steps : guide post-déploiement complet avec commandes exactes
│
├── Lot8_PLG/terraform-souverain/terraform.tfvars.example
│   Template commenté pour MINFI : server_host, server_user, ssh_private_key_path,
│   institution_name, nexus_domain, install_dir, versions, tuning, options
│
├── Lot8_PLG/terraform-souverain/.gitignore
│   *.tfstate, .terraform/, terraform.tfvars, .generated/, *.pem, *.key
│
└── Lot8_PLG/terraform-souverain/templates/
    env.tpl (55L) : variables d'environnement avec ${...} Terraform (= substitués)
    docker-compose.tpl (183L) : compose complet avec $${VAR} pour les vars Docker Compose
      → $${POSTGRES_USER:-nexus} devient ${POSTGRES_USER:-nexus} dans le fichier généré
      → Directive %{ if expose_dashboard } pour port conditionnel Wazuh Dashboard
    Dockerfile.scoring.tpl (34L) : Python 3.11-slim, OCI labels, uvicorn --workers 2

LOT 9 — Frontend connecté (PWA, dynamique, responsive) — session 29 mai 2026
├── run.py (racine) — point d'entrée FastAPI unifié
│   Charge l'app scoring (Lot 1) via importlib, monte les routeurs :
│     auth_router (auth_middleware), router + analyst_router (admin_api),
│     router (provisioning_api), router (plg_api). Sert Lot9_Frontend sur /app/.
│   CORS configurable via NEXUS_CORS_ORIGINS (défaut localhost, pas de wildcard+creds).
│   sys.path inclut Lot1/Lot7/Lot8 pour les imports croisés (JWT).
├── Lot9_Frontend/js/api.js (315L) — client API universel
│   JWT auto-refresh sur 401, 40+ méthodes, poll(), formatDate(), riskColor(), planBadge().
│   guard(roles) : redirige vers login.html si non autorisé. BASE auto (file:// → :8000).
├── Lot9_Frontend/login.html (362L) — auth JWT + redirect par rôle.
├── Lot9_Frontend/console.html (1715L) — console opérateur connectée.
│   7 sections, polling 30s (badges alertes/SOAR), toast, modals. Données 100% API.
├── Lot9_Frontend/portail.html (697L) — portail DSI connecté.
│   Bilingue FR/EN, trial banner dynamique, score calculé depuis alertes réelles.
├── Lot9_Frontend/sw.js (132L) — service worker (Cache First assets / Network First API + push).
├── Lot9_Frontend/manifest.json — PWA (shortcuts, standalone).
├── Lot9_Frontend/offline.html — page hors ligne.
└── Lot9_Frontend/icons/ — icon.svg + PNG générés (icon-192, icon-512, badge-72,
    screenshot-console, screenshot-portail) via Pillow, fidèles à la charte.

INTÉGRATION END-TO-END + DURCISSEMENT (session 29 mai 2026) :
  Bugs d'intégration corrigés (le frontend connecté ne fonctionnait pas avant) :
    I1. run.py ne montait que `router` → /auth/* (auth_router) et /analyst/* (analyst_router)
        absents. Corrigé : _try_include accepte une liste d'attrs + noms corrects.
    I2. admin_api.py et provisioning_api.py authentifiaient « mot de passe = token » alors
        que le frontend envoie un JWT. Corrigé : require_admin/require_analyst valident le
        JWT HS256 (import auth_middleware.decode_token + fallback autonome identique).
    I3. Endpoints manquants ajoutés (appelés par api.js) :
        GET /analyst/pending, POST /analyst/approve/{id}, /analyst/reject/{id},
        POST /analyst/false-positive/{id}, GET /analyst/alerts/{id},
        POST /admin/tenants/{id}/suspend, /activate, POST /provision/revoke/{agent_id}.
    I4. Payloads frontend alignés : generateToken → expires_in_hours (int + bind_hostname) ;
        createTenant → offre/email_admin (mapping trial→starter pour la contrainte CHECK).
  Sécurité :
    CORS durci (NEXUS_CORS_ORIGINS, wildcard+credentials neutralisé).

FICHIERS AJOUTÉS / MODIFIÉS (session 29 mai 2026) :
  Lot1_Agent_Go/scoring-service_app.py :
    +75 lignes : _enforce_trial_quota_sync(tenant_id, db) inséré avant emit_alert()
    Appel dans /ingest : après _verify_ingest, si tenant_id et STATE["db"] présents
    Gère : suspended_at (HTTP 402), trial expiré (HTTP 402), agents/events quota (HTTP 429).
  Lot7_Console_Fournisseur/admin_api.py : auth JWT + 5 endpoints analyste + suspend/activate.
  Lot7_Console_Fournisseur/provisioning_api.py : auth JWT + /provision/revoke/{agent_id}.
  Lot0_Socle/02_seed_demo.sql (NOUVEAU) : seed idempotent — comptes démo
    (admin@nexussoc.cm / soc@nexussoc.cm / dsi@minfi.cm, mot de passe « admin »),
    3 tenants, 5 agents, 4 alertes, 3 actions SOAR en attente.
  Lot6_Tests/test_api.py (NOUVEAU, 16 tests httpx/pytest) : auth multi-rôles, rejet JWT
    invalide, RBAC (dsi → 403 sur /admin), /analyst/*, filtres PLG, cycle de vie tenant.
    Lancement : uvicorn run:app --port 8000 (T1) puis pytest Lot6_Tests/test_api.py -v (T2).
    Skip propre si serveur injoignable.
  00_Documents/Architecture_NEXUS_SOC.drawio (NOUVEAU) : diagramme d'architecture logique
    complet (XML validé) — flux Agent→/ingest→Kafka→SIEM→IA→SOAR→notif, stockage RLS,
    4 frontends, déploiement Terraform. Exploitable au chapitre Conception.
  README.md : guide des interfaces Lot 9 + section tests API + changelog.
  NEXUS_SOC_Contexte_Complet.md : ce fichier (mise à jour).

  COMPTES DE DÉMONSTRATION (après 02_seed_demo.sql) :
    admin@nexussoc.cm / admin  → admin_plateforme → console.html
    soc@nexussoc.cm   / admin  → analyste_soc     → console.html
    dsi@minfi.cm      / admin  → dsi_client        → portail.html

  LANCEMENT DU FRONTEND CONNECTÉ :
    pip install "fastapi[standard]" uvicorn psycopg2-binary scikit-learn joblib numpy kafka-python
    uvicorn run:app --host 0.0.0.0 --port 8000 --reload
    → http://localhost:8000/app/login.html

  VÉRIFICATION NON FAITE : fastapi/psycopg2 absents de l'environnement de dev au moment
    de l'écriture → py_compile OK + XML validé, mais PAS de test d'exécution en direct.
    À lancer dans un environnement avec PostgreSQL + schémas + seed appliqués.

TESTS EFFECTUÉS ET RÉSULTATS :
  Simulation Atomic Red Team (attack_simulation.py) :
    7/7 techniques détectées. 3/3 scénarios. MTTD ransomware 120s, exfiltration 90s.
    0 faux positif sur scénario négatif.
  Test de charge (load_test.py) :
    ~200 000 ev/s stable, p99 ≤ 12 μs (mono-cœur). Bug O(N²) corrigé vérifié.
  Isolation RLS : 5/5 (Lot 6) + 8/8 (Lot 7). Bug NULLIF corrigé.

BUGS RÉSOLUS :
  B1. O(N²) detect_mass_file_change → deux pointeurs O(N). correlation_engine_v2.py.
  B2. /ingest sans authentification → Bearer + X-Signature. scoring-service_app.py.
  B3. Pas de rate limiting → compteur mémoire par IP, 429 Retry-After.
  B4. JWT incomplet → auth_middleware.py access+refresh.
  B5. RLS NULLIF contournement → NULLIF patch propagé schéma Lot 0.
  B6. Règles SIEM incomplètes → T1027, T1136, T1083 ajoutées v2.

DÉCISIONS TECHNIQUES VERROUILLÉES (ne pas rediscuter sans raison nouvelle) :
  D1. Pas de MVP — projet complet en lots ordonnés L0→L9.
  D2. Wazuh indexeur intégré = stockage chaud (pas d'Elasticsearch séparé).
  D3. TimescaleDB = relationnel + séries temporelles en un seul service.
  D4. Multi-tenant via RLS PostgreSQL (nexus_app non super-user).
  D5. Agent egress-only HTTPS (pas de port entrant).
  D6. Pur stdlib Go pour l'agent standard (pas de dépendances externes).
      EXCEPTION : garble est un BUILD-TIME tool uniquement pour l'agent PLG → D6 non violée.
  D7. Télémétrie endpoint ≠ entrée directe M1 et M2.
  D8. VirusTotal côté serveur (clé API centralisée, pas de secret sur les postes).
  D9. LLM Analyst mode template par défaut (déterministe, sans hallucination).
  D10. WhatsApp Business API : templates Meta requis hors fenêtre 24h.
  D11. Connecteurs SOAR simulés dans le démonstrateur.
  D12. Pré-auth bancaire PLG = stub → CinetPay/PayDunya à intégrer en prod.
  D13. Terraform provisioners SSH pour le déploiement souverain (null_resource + file/remote-exec).
  D14. Secrets Terraform auto-générés (random_password) si non fournis → idempotents.
  D15. Cache config agent PLG : HMAC [32B tag] + gzip, chmod 600, supprimé si altéré.
  D16. Auth API unifiée sur JWT HS256 (auth_middleware) — abandon du « mot de passe = token ».
       Frontend stocke access+refresh en localStorage ; api.js auto-refresh sur 401.
  D17. run.py = point d'entrée unique (uvicorn run:app) montant tous les routeurs + /app.
       Le frontend Lot 9 est servi par FastAPI (même origine → pas de souci CORS en prod).
  D18. Frontends Lot 5 / Lot 7 conservés comme MAQUETTES statiques de référence ;
       les versions connectées vivent dans Lot 9. Ne pas confondre les deux.

═══════════════════════════════════════════════════════════════════════════════════
SECTION 13 — PROCHAINES ÉTAPES
═══════════════════════════════════════════════════════════════════════════════════

CE QUI RESTE À FAIRE (par priorité décroissante) :

  PRIORITÉ 1 — Académique (bloquant pour la soutenance du 24 août 2026)

  P1. Rédiger le rapport écrit (ordre recommandé) :
    Chapitre 3 (Conception) en premier — le plus important, tout le code existe déjà.
      Décrire les 9 lots, justifier les décisions D1-D18,
      utiliser 00_Documents/Architecture_NEXUS_SOC.drawio comme schéma principal.
    Chapitre 2 (État de l'art) — citer MITRE ATT&CK, CICIDS2017, CERT Insider Threat,
      Wazuh, Isolation Forest (Liu 2008), autoencodeur (Hinton 2006), LSTM (Hochreiter 1997).
    Chapitre 4 (Réalisation) — un sous-chapitre par lot avec code + figures.
      Inclure Lot 8 (PLG + Terraform) et Lot 9 (frontend connecté + PWA).
    Chapitre 5 (Tests) — chiffres mesurés + 16 tests API (test_api.py) + figures.
    Chapitre 6 (Conclusion + perspectives) — les 19 améliorations prévues.
    Chapitre 1 (Contexte) — loi 2010/012, ANTIC, panorama des menaces.
    Conclusion générale + Abstract + Bibliographie (≥ 20 entrées).
    Introduction.

  P2. Préparer le support de soutenance (~20 slides) :
    Figures disponibles : chain_reconstruction.png, mitre_coverage.png, mttd_by_scenario.png,
    load_test_perf.png, rls_isolation_result.png, fraud_signatures.png,
    model_comparison.png, detection_by_attack_type.png.
    Ajouter : diagramme Architecture_NEXUS_SOC.drawio, captures du frontend connecté
              (login, console, portail), diagramme workflow PLG.

  PRIORITÉ 2 — Technique léger (2–4h, pendant la rédaction)

  P3. Captures d'écran des interfaces CONNECTÉES (serveur lancé) :
      uvicorn run:app --port 8000 puis F11 sur :
      http://localhost:8000/app/login.html
      http://localhost:8000/app/console.html
      http://localhost:8000/app/portail.html

  P4. Vérifier que correlation_engine_v2.py est bien utilisé dans la démo pipeline :
      python telemetry_gen.py | python normalizer.py | python correlation_engine_v2.py

  P5. Appliquer les schémas SQL + le seed sur une instance dev, puis lancer les tests API :
      psql $DB -f Lot7_Console_Fournisseur/01_schema_analyst.sql
      psql $DB -f Lot7_Console_Fournisseur/01_schema_provisioning.sql
      psql $DB -f Lot0_Socle/01_schema_retention.sql
      psql $DB -f Lot8_PLG/01_schema_plg.sql
      psql $DB -f Lot0_Socle/02_seed_demo.sql        # comptes démo + données
      pytest Lot6_Tests/test_api.py -v               # valider l'intégration end-to-end

  P5-bis. FAIT cette session (ne plus chercher à refaire) :
      ✓ Icônes PWA générées (Lot9_Frontend/icons/)
      ✓ Endpoints analyste manquants ajoutés (/analyst/pending, approve, reject, false-positive)
      ✓ Auth API unifiée sur JWT
      ✓ Comptes de démo créés (02_seed_demo.sql)
      ✓ CORS durci
      ✓ Diagramme d'architecture draw.io

  P6. Tester terraform apply sur un serveur de test avant le stage MINFI :
      cd Lot8_PLG/terraform-souverain
      cp terraform.tfvars.example terraform.tfvars
      terraform init && terraform plan && terraform apply

  PRIORITÉ 3 — Stage MINFI (mai–juillet 2026)

  P7. Adapter M1 aux données réseau réelles (captures NetFlow MINFI).
  P8. Adapter M2 aux données d'audit SIGIPES (journaux agents DGI/DGB).
  P9. Brancher les connecteurs SOAR réels (LDAP + pare-feu périmétrique).
  P10. Tester Atomic Red Team sur réseau MINFI de test (avec autorisation).
  P11. Initier la démarche conformité ANTIC.
  P12. Tester déploiement Terraform souverain sur serveur MINFI (si autorisé).

DÉPENDANCES ENTRE LES TÂCHES :
  P3 dépend de : navigateur avec accès internet (CDN fonts Google)
  P4 dépend de : nexus-pipeline.zip extrait
  P5 dépend de : PostgreSQL accessible localement
  P6 dépend de : Terraform installé, serveur SSH cible disponible, clé SSH prête
  P7–P12 dépendent de : autorisation MINFI pour accès aux données et systèmes
  P1 (rapport) ne dépend de rien — peut commencer immédiatement

RISQUES SUR LES PROCHAINES ÉTAPES :
  Rapport : risque de sous-documentation des limites honnêtes → les assumer franchement.
  Stage : accès données réelles soumis à autorisation administrative (délais).
  Terraform : dépend de la disponibilité d'un serveur SSH avec sudo au MINFI.
  Soutenance : questions jury attendues sur 54% faux mandatements, données synthétiques,
               stub pré-auth bancaire, connecteurs SOAR simulés → réponses dans Section 11.

═══════════════════════════════════════════════════════════════════════════════════
SECTION 14 — COMMANDES ET CONFIGURATIONS CLÉS
═══════════════════════════════════════════════════════════════════════════════════

DÉMARRAGE DE LA PILE COMPLÈTE (Docker) :

  # Prérequis noyau
  sudo sysctl -w vm.max_map_count=262144

  # Extraire et configurer le socle
  cd Lot0_Socle && unzip nexus-soc-socle.zip && cd nexus-soc-socle
  cp .env.example .env  # adapter les mots de passe

  # Générer les certificats Wazuh (une seule fois)
  docker compose -f generate-certs.yml run --rm generator

  # Entraîner et déposer les modèles
  python3 Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
  python3 Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py
  cp model1_isoforest.joblib nexus-soc-socle/models/
  cp model2_isoforest.joblib nexus-soc-socle/models/

  # Lancer la pile
  docker compose up -d

  # Vérifier
  docker compose ps
  curl http://localhost:8000/health
  curl http://localhost:8000/health/detailed | python3 -m json.tool

OUVERTURE DES INTERFACES :

  # Interface 1 — Landing page PLG (Lot 8)
  xdg-open Lot8_PLG/landing_page.html

  # Interface 2 — Portail DSI client (Lot 5)
  xdg-open Lot5_Restitution/portail/portal/index.html

  # Interface 3 — Console Fournisseur (Lot 7)
  xdg-open Lot7_Console_Fournisseur/console_fournisseur.html

  # Interface 4 — API Swagger (pile Docker requise)
  xdg-open http://localhost:8000/docs

  # Interface 5 — Wazuh Dashboard (pile Docker requise)
  xdg-open https://localhost:5601  # ignorer avertissement cert auto-signé

DÉMO PIPELINE SANS DOCKER :

  cd Lot2_Pipeline_SIEM && unzip nexus-pipeline.zip && cd nexus-pipeline
  python telemetry_gen.py
  python normalizer.py telemetry_demo.json | python ../../correlation_engine_v2.py
  python ../../correlation_engine_v2.py --benchmark  # gain O(N²) → O(N)

ENTRAÎNER LES MODÈLES :

  python3 Lot3_IA/Modele1_Anomalie_reseau/model1_anomaly_detection.py
  python3 Lot3_IA/Modele1_Anomalie_reseau/model1_advanced.py
  python3 Lot3_IA/Modele2_Fraude_interne/model2_fraud_detection.py

AUTHENTIFICATION ET SCORING API :

  # Login
  curl -X POST http://localhost:8000/auth/token \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}'
  # → {"access_token":"...","expires_in":900}

  # Ingestion télémétrie (59 événements de démo)
  curl -X POST http://localhost:8000/ingest \
    -H "Authorization: Bearer nexus_demo" \
    -H "X-Signature: $(sha256sum Lot1_Agent_Go/telemetry_sample.json | cut -d' ' -f1)" \
    -H "Content-Type: application/json" \
    -d @Lot1_Agent_Go/telemetry_sample.json

  # Score M1 (anomalie réseau DDoS)
  curl -X POST http://localhost:8000/score/network \
    -H "Content-Type: application/json" \
    -d '{"features":{"src_bytes":3200000,"dst_bytes":512,"duration":0}}'

  # Score M2 (exfiltration fiscale)
  curl -X POST http://localhost:8000/score/user-day \
    -H "Content-Type: application/json" \
    -d '{"features":{"nb_exports":28,"volume_donnees_exportees":92000,"nb_acces_dossiers_sensibles":40,"nb_transactions":12,"montant_total_modifie":0,"nb_modifs_montant":0,"nb_connexions":3,"nb_actions_hors_heures":2,"nb_creations_compte":0,"nb_actions_total":45}}'

PLG API :

  # Vérifier un email professionnel
  curl -X POST http://localhost:8000/plg/check-email \
    -H "Content-Type: application/json" -d '{"email":"dsi@caisse-abc.com"}'

  # Vérifier un email gouvernemental (doit retourner GOV_DOMAIN_REDIRECT)
  curl -X POST http://localhost:8000/plg/check-email \
    -H "Content-Type: application/json" -d '{"email":"agent@minfi.gov.cm"}'

  # Inscription
  curl -X POST http://localhost:8000/plg/register \
    -H "Content-Type: application/json" \
    -d '{"email":"dsi@caisse-abc.com","organization_name":"Caisse ABC","sector":"microfinance"}'

  # Plans disponibles
  curl http://localhost:8000/plg/plans | python3 -m json.tool

  # Statut trial d'un tenant
  curl http://localhost:8000/plg/trial-status/<TENANT_ID>

  # Suspension + réactivation (admin)
  curl -X POST http://localhost:8000/plg/suspend/<TENANT_ID> -H "Authorization: Bearer $TOKEN"
  curl -X POST http://localhost:8000/plg/resume/<TENANT_ID> -H "Authorization: Bearer $TOKEN"

  # Lancer la vérification des essais expirés
  curl -X POST http://localhost:8000/plg/run-expiry-check -H "Authorization: Bearer $TOKEN"

COMPILATION DE L'AGENT :

  # Agent standard (Lot 1)
  cd Lot1_Agent_Go && unzip nexus-agent.zip && cd nexus-agent
  CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent .
  CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent.exe .

  # Agent PLG (Lot 8) — obfusqué + watermark
  go install mvdan.cc/garble@latest  # une seule fois
  python3 Lot8_PLG/build_agent.py --tenant-id <uuid> --os linux --arch amd64
  python3 Lot8_PLG/build_agent.py --tenant-id <uuid> --os windows --arch amd64 --no-garble

DÉPLOIEMENT TERRAFORM SOUVERAIN :

  cd Lot8_PLG/terraform-souverain/
  cp terraform.tfvars.example terraform.tfvars
  nano terraform.tfvars  # server_host, institution_name, nexus_domain, ssh_key_path

  # Clé SSH dédiée
  ssh-keygen -t ed25519 -f ~/.ssh/nexus_deploy -C "nexus-soc-deploy"
  ssh-copy-id -i ~/.ssh/nexus_deploy.pub ubuntu@<IP_SERVEUR>

  terraform init                    # télécharge providers
  terraform plan                    # prévisualise
  terraform apply                   # déploie (~5–15 min, taper "yes")

  # Post-déploiement
  terraform output nexus_api_url
  terraform output -raw postgres_password
  terraform output -raw wazuh_admin_password

  # Upload modèles IA
  scp model1_isoforest.joblib ubuntu@<IP>:/opt/nexus-soc/models/
  scp model2_isoforest.joblib ubuntu@<IP>:/opt/nexus-soc/models/
  ssh ubuntu@<IP> 'cd /opt/nexus-soc && docker compose restart scoring-service'
  curl http://<IP>:8000/health  # → {"status":"ok","modele1":true,"modele2":true}

  # Mise à jour code → Terraform détecte le changement de hash
  terraform apply  # re-déploie uniquement ce qui a changé

TESTS :

  # Simulation d'attaques (7/7 techniques, MTTD 90–120s)
  cd Lot6_Tests && unzip nexus-tests.zip && cd nexus-tests
  python attack_simulation.py

  # Test de charge (~200 000 ev/s, p99 ≤ 12 μs)
  python load_test.py

  # Test isolation RLS Lot 6 (5 assertions nexus_app)
  python rls_isolation_test.py

  # Test isolation RLS étendu Lot 7 (8 assertions)
  python3 Lot7_Console_Fournisseur/rls_analyst_test.py

  # Monitoring dérive modèles (mode démo)
  python3 Lot3_IA/model_monitor.py --demo

  # Pseudonymisation (test)
  python3 Lot1_Agent_Go/pseudonymizer.py

SAUVEGARDE :

  sudo bash Lot0_Socle/backup.sh --dest /opt/nexus-backups --compress
  sudo bash Lot0_Socle/restore.sh --backup /opt/nexus-backups/nexus_20260529_020000

DÉPLOIEMENT AGENTS (depuis API) :

  # Générer un token
  curl -X POST http://localhost:8000/provision/token \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"hostname":"POSTE-01","os":"linux","expires_in":"24h","one_time":true}'

  # One-liner Linux (généré par console ou API)
  curl -fsSL "https://nexussoc.cm/provision/oneliner?token=nexus_xxx&hostname=POSTE-01" | bash

  # One-liner Windows
  irm "https://nexussoc.cm/provision/oneliner?token=nexus_xxx&hostname=POSTE-01&os=windows" | iex

  # Ansible (déploiement de masse)
  ansible-playbook -i inventaire.ini \
    Lot7_Console_Fournisseur/install_templates/ansible_nexus_agent.yml \
    -e "nexus_server=https://nexussoc.cm nexus_token=nexus_xxx nexus_tenant_id=<UUID>"

  # Révoquer tous les agents d'un tenant (urgence)
  curl -X POST http://localhost:8000/provision/revoke-tenant/<TENANT_ID> \
    -H "Authorization: Bearer $TOKEN"

APPLIQUER TOUS LES SCHÉMAS SQL :

  DB="postgresql://nexus:change_me@localhost:5432/nexus_soc"
  psql $DB -f Lot0_Socle/01_schema_patched.sql
  psql $DB -f Lot7_Console_Fournisseur/01_schema_analyst.sql
  psql $DB -f Lot7_Console_Fournisseur/01_schema_provisioning.sql
  psql $DB -f Lot0_Socle/01_schema_retention.sql
  psql $DB -f Lot8_PLG/01_schema_plg.sql

FIN DU CONTEXTE
