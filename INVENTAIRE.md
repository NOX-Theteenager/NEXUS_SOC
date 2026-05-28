# NEXUS SOC — Inventaire général du projet

**Auteur** : NGUETSA Junior Stéphane Céleste — Bachelor 3 RSI · KEYCE Informatique & IA · Yaoundé
**Stage** : Mai–Juillet 2026 — MINFI (Ministère des Finances)

---

## État global

| Volet | État |
|---|---|
| Périmètre technique (lots L0 → L7) | **Complet** — toutes les briques livrées et fonctionnelles |
| Documents académiques | Cahier des charges, architecture technique, Gantt et template de rapport **livrés** |
| Rédaction du rapport | **À faire** — le template `.docx` attend la prose des chapitres |
| Support de soutenance (slides) | **À faire** |
| Validation terrain (stage MINFI) | **À venir** — adaptation aux vraies données SIGIPES/SYDONIA |

**Nature du projet** : projet *complet en périmètre* (et non un MVP — démarche assumée dès le
cahier des charges), au niveau *« socle de plateforme + démonstrateur runnable »*. Le passage
au durcissement production (connecteurs SOAR réels, signature de binaires, templates Meta
approuvés, déploiement Kubernetes, audit sécurité) reste l'étape suivante.

---

## Structure du dépôt

```
NEXUS_SOC/
├── INVENTAIRE.md                       (ce fichier)
├── 00_Documents/                       documents académiques
├── Lot0_Socle/                         socle technique docker-compose
├── Lot1_Agent_Go/                      agent endpoint en Go (binaire ~5 Mo)
├── Lot2_Pipeline_SIEM/                 normalisation + corrélation MITRE
├── Lot3_IA/
│   ├── Modele1_Anomalie_reseau/
│   └── Modele2_Fraude_interne/
├── Lot4_SOAR/                          moteur de réponse + playbooks + audit
├── Lot5_Restitution/                   portail DSI FR/EN + LLM Analyst + SMS + WhatsApp
├── Lot6_Tests/                         simulation d'attaques + charge + isolation RLS
└── Lot7_Console_Fournisseur/           console opérateur multi-tenant (admin + analyste SOC)
```

## Détail par lot

### 00_Documents
- `Cahier_des_charges_NEXUS_SOC.pdf` — 9 pages : contexte, ciblage (administrations + secteur
  financier non bancaire), périmètre complet en 7 lots, modèle économique double, contraintes
  légales (loi 2010/012, ANTIC, COBAC, CIMA, ONECCA, ISO 27001).
- `Architecture_technique_NEXUS_SOC.pdf` — 7 pages, 4 diagrammes (global, pipeline, attack
  chain MITRE, multi-tenant).
- `Template_Rapport_Soutenance_NEXUS_SOC.docx` — 18 pages, page de garde bilingue camerounaise,
  squelette des 6 chapitres + intro/conclusion.
- `Planning_Gantt_NEXUS_SOC.png` — calendrier par lots, jalons.

### Lot 0 — Socle technique
Pile `docker-compose` intégrée. Kafka KRaft (sans Zookeeper) + TimescaleDB (PostgreSQL 16) +
indexeur Wazuh (qui sert aussi de stockage chaud compatible Elasticsearch, économie de RAM) +
manager + dashboard + service de scoring FastAPI (charge les Modèles 1 & 2, expose `/score/*`
et la passerelle `/ingest` de l'agent). Schéma SQL multi-tenant **avec Row-Level Security**
(patch `NULLIF` intégré, validé par le Lot 6). Modèles entraînés déjà déposés dans `models/`.

→ Archive : `nexus-soc-socle.zip`

### Lot 1 — Agent Go
Agent universel léger en **pur stdlib Go** (aucune dépendance externe). Collecte processus
(avec SHA-256 caché), connexions réseau (`/proc/net/tcp` + IPv6), modifications de fichiers,
état système. **Egress-only HTTPS + gzip + signature HMAC**, file d'attente locale persistante
(*store-and-forward*) pour résilience aux coupures.
**Mesuré** : 5,0 Mo (Linux) / 5,3 Mo (Windows) — bien sous la cible de 15 Mo.

→ Archive : `nexus-agent.zip` + échantillon `telemetry_sample.json` (59 événements réels)

### Lot 2 — Pipeline (normalisation + corrélation SIEM)
Normalisation vers schéma commun (ECS-like) + features comportementales d'hôte.
Moteur de corrélation à **règles mappées MITRE ATT&CK** qui regroupe les détections par
hôte et reconstitue les chaînes d'attaque. Démo : 155 événements → 1 incident corrélé
« Ransomware » sur `POSTE-COMPTA-07`, chaîne Initial Access → Execution → Collection → C2 →
Impact, risque 100/100, transmis au SOAR. **Zéro faux positif** sur les hôtes normaux.

→ Archive : `nexus-pipeline.zip` + figures `chain_reconstruction.png`, `mitre_coverage.png`

### Lot 3 — Modèles d'IA
- **Modèle 1 (anomalie réseau)** : Isolation Forest sur features CICIDS-like + variante
  **autoencodeur** comparée, **analyse par type d'attaque** (DDoS / PortScan / Bot-C2).
  Résultats démo : ROC-AUC 0,987 (IF) vs 0,991 (AE) — modèles complémentaires.
- **Modèle 2 (fraude interne UEBA)** : Isolation Forest sur profils agent-jour ; trois
  scénarios (faux mandatements, fonctionnaires fantômes, exfiltration). Données réalistes
  avec « zone grise » légitime. ROC-AUC 0,969, 4 % de faux positifs. **Explicabilité**
  intégrée (raisons en σ pour chaque alerte).

### Lot 4 — SOAR (réponse encadrée)
Moteur de playbooks avec garde-fous : seuils de confiance, mode dry-run, **validation
humaine** pour les actions à fort impact (gel de compte, isolation), réversibilité
(rollback), journal d'audit CSV. 9 connecteurs simulés, 4 playbooks (Fraude interne,
Exfiltration, Ransomware, Anomalie réseau / C2).

### Lot 5 — Restitution bilingue (FR / EN)
- **Portail web** mode sombre, fichier HTML autonome (Fraunces + Manrope + JetBrains Mono).
  Timeline kill-chain colorée par tactique MITRE, citation **Analyst IA** en serif italique.
  Bascule FR / EN instantanée. Captures `preview_fr.png` et `preview_en.png` incluses.
- **LLM Analyst** : modes `template` (déterministe, par défaut) et `llm` (Mistral/Llama via
  API compatible OpenAI). Explications en français ou en anglais.
- **SMS** et **rapport WhatsApp hebdomadaire** bilingues.

→ Archive : `nexus-portail.zip`

### Lot 6 — Tests, durcissement, mesures
- **Simulation d'attaques** style Atomic Red Team : 7/7 techniques attendues détectées, 2/3
  vrais négatifs, 3/3 scénarios. **MTTD** mesuré (90 s exfiltration, 120 s ransomware).
- **Test de charge** : normalisation **~200 000 ev/s** stable (latence p99 ≤ 12 μs).
  Découverte d'un goulot O(N²) dans le détecteur de modification massive — correctif en
  O(N) identifié.
- **Test d'isolation RLS** sur PostgreSQL 16 réel : **5/5 assertions vérifiées**. A fait
  émerger un bug réel (`NULLIF` manquant) — patch propagé au schéma du Lot 0.

→ Archive : `nexus-tests.zip` + figures `mttd_by_scenario.png`, `load_test_perf.png`,
`rls_isolation_result.png`, `mitre_coverage_tested.png`

### Lot 7 — Console Fournisseur (admin multi-tenant + poste analyste SOC)
Interface web de l'opérateur NEXUS SOC, séparée du portail client. Voir **deux côtés** :
à gauche le fournisseur qui supervise tous les tenants, à droite chaque client qui ne voit
que ses données (RLS). **Module A (Administration) réalisé** ; module B (Analyste SOC) à venir.

- **`console_fournisseur.html`** — interface standalone mode sombre, bilingue FR/EN, même
  esthétique que le portail Lot 5 (Fraunces + Manrope + JetBrains Mono, palette amber/teal).
  6 sections : tableau de bord global, tenants (CRUD + suspension), utilisateurs (RBAC),
  agents (provisioning + génération de jetons d'enrôlement), santé système (6 services),
  facturation (ARR / MRR / détail abonnements). Navigation sidebar. Toutes actions interactives
  (création tenant, génération token, isolation agent) avec toasts de confirmation.
- **`admin_api.py`** — endpoints FastAPI `/admin/*` (tenants, users, agents, health, billing)
  et `/analyst/*` (alerts cross-tenant, approbation SOAR, dashboard SOC) à inclure dans le
  scoring-service existant.
- **`01_schema_analyst.sql`** — colonne `statut` sur `tenants`, colonnes `token_hash` /
  `hmac_key_hash` sur `agents`, rôle PostgreSQL `nexus_analyst` avec attribut **BYPASSRLS**
  (non super-utilisateur — uniquement SELECT + UPDATE limité sur soar_audit).
- **`rls_analyst_test.py`** — test RLS étendu : **8/8 assertions** (5 héritées du Lot 6 pour
  `nexus_app`, + 3 nouvelles pour `nexus_analyst` : COUNT global = 5, filtre tenant = 3,
  2 tenant_id distincts visibles).

**Distinction architecturale clé** :
- `nexus_app` → soumis à la politique RLS (chaque requête voit son tenant uniquement)
- `nexus_analyst` → BYPASSRLS (voit tous les tenants, jamais super-utilisateur)

---

## Ce qui reste à faire

1. **Console fournisseur — Module B** (Poste Analyste SOC) : front-end de la file d'alertes
   cross-tenants + approbation SOAR (les endpoints back `/analyst/*` sont déjà dans `admin_api.py`).
2. **Rédiger le rapport** (chapitres 1 à 6 + intro + conclusion) — toutes les figures et
   métriques sont là, prêtes à être insérées.
3. **Préparer la soutenance** (support visuel à partir des figures déjà produites).
4. Pendant le stage MINFI :
   - Adapter les modèles 1 et 2 aux **vraies données** (CICIDS / CTU-13 pour le réseau,
     audits SIGIPES/SYDONIA pour la fraude) ; re-mesurer.
   - Brancher les **connecteurs réels** du SOAR (AD/LDAP, pare-feu, EDR, passerelle SMS).
   - Valider la **conformité** ANTIC et la procédure d'enrôlement des agents.

---

## Bouton de démarrage rapide

```bash
# Sur un poste de dev avec Docker installé :
unzip Lot0_Socle/nexus-soc-socle.zip && cd nexus-soc-socle
docker compose -f generate-certs.yml run --rm generator     # certificats Wazuh (une fois)
docker compose up -d                                         # toute la pile
# Portail (Lot 5) à ouvrir séparément dans un navigateur :
unzip Lot5_Restitution/nexus-portail.zip && xdg-open portail/portal/index.html
# Console fournisseur (Lot 7) — ouvrir directement dans un navigateur :
xdg-open Lot7_Console_Fournisseur/console_fournisseur.html
```
