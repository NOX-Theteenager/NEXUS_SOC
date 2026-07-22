# MIGRATION — Refonte souveraine CENADI

Ce document journalise la refonte qui recentre NEXUS SOC : de « SOC-as-a-Service »
commercial mutualisé vers une **plateforme 100 % open source, souveraine et
exclusive au CENADI**. Le multi-locataire technique est réinterprété comme un
**cloisonnement de périmètres internes** (SIGIPES, ANTILOPE, réseau/LAN CENADI).

Branche : `refonte/cenadi-open-source` (créée depuis `nexus_test`).
Chaque tâche A→G correspond à un commit atomique.

---

## Points nécessitant votre validation

1. **Licence (Tâche F).** Choix par défaut appliqué : **GPL-3.0-or-later**
   (fichier `LICENSE` = texte canonique GNU GPL v3). Motif : copyleft compatible
   avec Wazuh (GPL v2) et garantie d'auditabilité/redistribution. → **À confirmer.**
2. **Domaine par défaut.** `soc.cenadi.gov.cm` appliqué dans `.env.example`,
   `deploy/opentofu` et la doc. → **À confirmer** (ajuster si le FQDN réel diffère).
3. **Maquette Lot 7 supprimée.** `Lot7_Console_Fournisseur/console_fournisseur.html`
   (maquette statique, 148 Ko) a été **supprimée** plutôt que renommée : elle
   portait un module de facturation ARR/MRR/FCFA incompatible avec la vision, et
   est intégralement remplacée par la console connectée `Lot9_Frontend/console.html`
   (propre). → Si vous en avez besoin pour des captures du rapport, je peux la
   restaurer depuis git et la purger à la place.
4. **Documents académiques `Rapport_NEXUS_SOC.md` et `NEXUS_SOC_Contexte_Complet.md`.**
   Conformément à la décision « purge lexicale ciblée, pas de réécriture », ils
   ont reçu les swaps mécaniques (MINFI→CENADI, Terraform→OpenTofu,
   SOC-as-a-Service→SOC souverain, SYDONIA→ANTILOPE) + un **bandeau
   d'avertissement** en tête. Ils **conservent des sections commerciales caduques**
   (modèle économique, tarification, parcours PLG, marché des microfinances) qui
   relèvent de votre rédaction académique et **doivent être relues/réécrites par
   vous** avant la soutenance. Résiduel indicatif : ~34 occurrences (Rapport),
   ~192 (Contexte). Ces deux fichiers sont **exclus** de l'objectif « zéro
   occurrence » de la Tâche G.

---

## Tâche A — Suppression de la couche commerciale (PLG / SaaS)

**Fichiers supprimés**
- `Lot8_PLG/plg_api.py`, `Lot8_PLG/landing_page.html`, `Lot8_PLG/01_schema_plg.sql`,
  `Lot8_PLG/02_schema_otp.sql`, `Lot8_PLG/build_agent.py`, `Lot8_PLG/cinetpay_client.py`
- `Lot8_PLG/nexus-agent-plg/` (agent « coquille vide » obfusqué garble + watermark)
- `Lot1_Agent_Go/mailjet_client.py`, `Lot1_Agent_Go/smtp_client.py`
  (envoi d'e-mails OTP d'inscription self-service — décision : suppression avec PLG)

**Fichiers modifiés**
- `run.py` : retrait du montage du routeur PLG, du hook `@app.on_event("startup")`
  créant le pool asyncpg (`app.state.db`, utilisé uniquement par PLG) et de
  `Lot8_PLG` du `sys.path`.
- `Lot1_Agent_Go/scoring-service_app.py` : suppression de `_enforce_trial_quota_sync`
  et de son appel dans `/ingest` (l'ingestion ne dépend plus d'un quota d'abonnement).
- `requirements.txt` : retrait de `asyncpg` (plus utilisé hors PLG).

**Endpoints retirés** : `/plg/check-email`, `/plg/register`, `/plg/verify-email`,
`/plg/verify-otp`, `/plg/preauth`, `/plg/cinetpay/notify`, `/plg/trial-status/*`,
`/plg/plans`, `/plg/upgrade`, `/plg/suspend/*`, `/plg/resume/*`,
`/plg/run-expiry-check`, `/plg/agent/config/*`, et `/provision/agent-binary`.

**Objets SQL supprimés** (via suppression de `01_schema_plg.sql`) : tables
`plg_registrations`, `trial_quotas`, `subscriptions`, `plan_config` ; vues
`v_trial_expiry`, `v_active_subscriptions` ; fonction `suspend_expired_trials()` ;
colonnes commerciales ajoutées à `tenants` (`plan`, `trial_ends_at`,
`suspended_at`, `max_agents`, `max_daily_events`).

---

## Tâche B — Infra : extraction + migration OpenTofu

- **Déplacement** `Lot8_PLG/terraform-souverain/` → `deploy/opentofu/` (module de
  premier niveau, indépendant de PLG). Le dossier `Lot8_PLG/` (vide) est supprimé.
- **Migration Terraform → OpenTofu** : commandes `terraform apply/init/plan/output`
  → `tofu …` ; mentions « Terraform » → « OpenTofu » dans commentaires, templates
  et doc. Conservés pour compatibilité OpenTofu : le bloc HCL `terraform {}`, les
  noms de fichiers `terraform.tfstate` et `terraform.tfvars`.
- **Valeurs par défaut CENADI** : `institution_name = "CENADI"`,
  `nexus_domain = "soc.cenadi.gov.cm"` (`variables.tf` + `terraform.tfvars.example`).
- Ajout de `deploy/opentofu/README.md` (workflow `tofu`).
- **Correctif (Tâche G)** : `main.tf` uploadait encore `Lot8_PLG/01_schema_plg.sql`
  et `Lot8_PLG/plg_api.py` (supprimés) → remplacés par `03_schema_notifications.sql`,
  suppression de l'upload `plg_api.py`, retrait de `asyncpg` des requirements
  générés, suppression de la variable `enable_plg_module` et de la sortie
  `plg_enabled`, retrait de `COPY plg_api.py` du `Dockerfile.scoring.tpl`.

---

## Tâche C — Réinterprétation en périmètres internes

**Identifiants techniques conservés (inchangés)** : colonne `tenant_id`, rôles
`nexus_app` / `nexus_analyst`, patch `NULLIF(current_setting('app.current_tenant',
true), '')::uuid`, politiques RLS. Seules la sémantique, les libellés et les
données de démo changent.

- `Lot0_Socle/01_schema_patched.sql` : table `tenants` recommentée « périmètres
  supervisés » ; colonne `type` → catégories `application_metier`/`reseau`/
  `infrastructure`/`poste_utilisateur` ; colonne `offre` (abonnement) **renommée
  `criticite`** (`standard`/`sensible`/`critique`). Données de démo → SIGIPES,
  Réseau/LAN CENADI.
- `Lot0_Socle/02_seed_demo.sql` : périmètres **SIGIPES**, **ANTILOPE**,
  **Réseau/LAN CENADI** ; responsables `resp.sigipes@cenadi.cm` /
  `resp.antilope@cenadi.cm` ; suppression du bloc PLG plan/quota et des anciens
  comptes commerciaux (afriland/uba/minfi).
- `Lot7_Console_Fournisseur/admin_api.py` : validation `type`/`criticite` ;
  `suspend`/`activate` basés sur la colonne `statut` (au lieu des colonnes PLG
  supprimées) ; **endpoint `/admin/billing` (barème FCFA) supprimé**, remplacé par
  `/admin/perimetres` (inventaire non commercial) ; libellés tenant → périmètre.
- `Lot7_Console_Fournisseur/01_schema_analyst.sql` : docstrings du rôle
  `nexus_analyst` = analyste SOC du CENADI supervisant tous les périmètres.
- `Lot6_Tests/test_api.py` : retrait des 4 tests `/plg` (routeur supprimé) ;
  cycle de vie de périmètre adapté (`type`/`criticite`) ; compte DSI de test →
  `resp.sigipes@cenadi.cm`.
- `Lot7_Console_Fournisseur/rls_analyst_test.py` : libellés de démo en périmètres
  CENADI (logique 8/8 inchangée).

---

## Tâche D — Frontend

- `Lot9_Frontend/console.html` : « Tenants » → « Périmètres supervisés » ;
  création par `type` + `criticite` (au lieu de plan/offre FCFA) ; **suppression
  de la section Facturation & PLG** (nav + section + `loadBilling` +
  `runExpiryCheck`) ; badge de criticité ; brand « Opérateur CENADI ».
- `Lot9_Frontend/portail.html` : **suppression complète de la bannière d'essai**
  (HTML + CSS + `loadTrialStatus` + `openUpgrade`).
- `Lot9_Frontend/js/api.js` : suppression des méthodes commerciales (`getBilling`,
  `getTrialStatus`, `getPlgPlans`, `upgradePlan`, `suspendPlg`, `resumePlg`,
  `runExpiryCheck`, `formatFCFA`, `planBadge`) ; ajout `getPerimetres` +
  `criticiteBadge`.
- **Landing** : suppression de `Lot9_Frontend/landing.html` (vitrine SaaS) ;
  `run.py` redirige `/` vers `login.html` ; liens nav (contact/docs/login) et
  précache `sw.js` repointés ; `manifest.json` redécrit.
- `Lot9_Frontend/contact.html` : « Déploiement souverain Hub & Spoke » → page de
  contact interne « Équipe SOC CENADI » ; endpoint `/plg/sovereign-contact` →
  `/contact/perimetre-request`.
- `Lot9_Frontend/docs.html` : purge SOC-as-a-Service/PLG/asyncpg ;
  Terraform→OpenTofu ; tenant→périmètre.
- `Lot7_Console_Fournisseur/console_fournisseur.html` **supprimée** (voir point 3
  « validation » ci-dessus).
- `Lot5_Restitution/portail/portal/index.html` : entité de démo
  `POSTE-COMPTA-07` → `POSTE-RH-07`.

---

## Tâche E — Docs, README, environnement

- `README.md` : réécriture complète (positionnement souverain CENADI,
  architecture **8 → 7 composants**, schéma ASCII sans bloc PLG, déploiement
  OpenTofu, 18 → 14 tests, comptes et périmètres de démo).
- `.env.example` : suppression des sections e-mail/OTP (SMTP/Mailjet) et CinetPay
  (mortes) ; `NEXUS_SERVER_URL` → `soc.cenadi.gov.cm` ; VirusTotal conservé.
- `00_Documents/Configuration_Services_Externes.md` : réécrit autour du seul
  service externe restant (VirusTotal).
- `Lot9_Frontend/docs.html`, `INVENTAIRE.md`, `00_Documents/Bilan_Projet.md`,
  `Lot7_Console_Fournisseur/README_Lot7.md`, `Lot0_Socle/README_Lot0.md`,
  `00_Documents/Deploiement_HTTPS_nexussoc.md` : purge lexicale.
- `00_Documents/Architecture_NEXUS_SOC.drawio` : diagramme mis à jour (retrait des
  blocs Agent PLG et Landing PLG, du « quota trial » sur /ingest ; Terraform →
  OpenTofu ; multi-tenant → cloisonnement par périmètre ; console → opérateur CENADI).
- `Rapport_NEXUS_SOC.md`, `NEXUS_SOC_Contexte_Complet.md` : voir point 4 « validation ».

---

## Tâche F — Caractère open source

- `LICENSE` : GNU GPL v3 (texte canonique). Déclaration **GPL-3.0-or-later**.
- `THIRD_PARTY_LICENSES.md` : recensement des composants et licences
  (Agent Go BSD-3 · Kafka Apache-2.0 · FastAPI/scikit-learn MIT/BSD-3 · Wazuh
  GPL v2 · PostgreSQL License · TimescaleDB Apache-2.0 · SOAR interne ·
  Docker Apache-2.0 · OpenTofu MPL-2.0).

---

## Lab (hors A→G, décidé en cours de refonte)

- Suppression du dossier `lab/` (ancien lab orienté déploiement mutualisé +
  scénario PLG-OTP, avec Afriland/UBA/microfinance/CinetPay).
- `lab-cenadi/` : retrait du cadrage dual « SaaS vs Souverain » et des références
  au lab supprimé (`../lab/`). Présenté comme l'unique lab souverain du CENADI.

---

## Tâche G — Vérification finale

- **Grep termes interdits** (PLG, Product-Led, SaaS, SOC-as-a-Service, trial,
  abonnement, FCFA, microfinance, COBAC, CIMA, ONECCA, « Hub & Spoke », Terraform)
  hors `MIGRATION.md` et hors les 2 narratifs académiques flaggés :
  **zéro occurrence** (les seuls restes sont des faux positifs : « indus**trial** »
  dans le texte GPL, « terraform.tfvars » nom de fichier conservé pour OpenTofu,
  et sous-chaînes comme « dé**cima**ux »/« né**cessai**re »).
- **Démarrage** : `uvicorn run:app` démarre sans erreur d'import liée à `plg_api`
  (routeurs montés : Auth, Admin+Analyste+Portail, Provisioning ; frontend `/app`).
- **Tests API** : `pytest Lot6_Tests/test_api.py` → **14/14 PASS**
  (contre PostgreSQL/TimescaleDB réel, schémas + seed appliqués sur base vierge).
- **Isolation RLS** : `rls_analyst_test.py` n'a pas pu être exécuté dans cet
  environnement (il exige un PostgreSQL local en socket Unix avec les rôles
  `postgres`/`nexus_app`/`nexus_analyst` ; seul un conteneur TCP était disponible).
  Sa **logique est inchangée** (politique NULLIF + BYPASSRLS non touchées, seuls
  les libellés de démo ont changé) → attendu **8/8** dans un environnement
  socket. Vérification équivalente réalisée **manuellement** contre la base réelle
  reformulée : `nexus_app` filtré ne voit que son périmètre (2 alertes SIGIPES),
  fuite cross-périmètre = 0, session sans périmètre = 0 ; `nexus_analyst`
  (BYPASSRLS) voit les 4 alertes sur 3 périmètres.
- **`attack_simulation.py` / `load_test.py`** : livrés dans `Lot6_Tests/nexus-tests.zip`,
  non ré-exécutés ici (indépendants de la refonte : ils ne touchent ni au vocabulaire
  commercial ni au schéma modifié). À relancer si besoin après extraction du zip.

---

## Décisions techniques verrouillées — statut

Conservées : agent egress-only, Wazuh stockage chaud, TimescaleDB unique, RLS via
`nexus_app`, JWT HS256 maison, `run.py` point d'entrée unique.
Annulées (commerciales) : D12 (pré-auth bancaire PLG/CinetPay), tout le module PLG
(agent coquille vide, quotas trial, abonnements). Migrée : D13 Terraform → OpenTofu.
