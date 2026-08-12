# DESIGNEXUS — Brief de design des interfaces NEXUS SOC

> Document de passation destiné à un agent de design. Il décrit ce qu'est NEXUS SOC,
> ce qui existe déjà, les contraintes à respecter et ce qu'il reste à concevoir,
> interface par interface.
>
> **Auteur du projet** : NGUETSA Junior Stéphane Céleste — KEYCE Informatique & IA, Yaoundé (B3 RSI)
> **Commanditaire** : CENADI (Centre National de Développement de l'Informatique), Cameroun
> **Branche courante** : `refonte/cenadi-open-source`
> **Licence** : GPL-3.0-or-later

---

## 0. Comment utiliser ce document

Chaque interface a sa fiche en [section 5](#5-fiches-interface). Une fiche donne l'utilisateur,
l'objectif, les données réellement disponibles côté API, la structure attendue et les états à couvrir.

Les sections 1 à 4 sont le cadre commun : ne pas les contourner. Le design system de la
[section 3](#3-design-system-existant) est déjà implémenté sur 5 pages en production ; toute
nouvelle interface doit s'y raccorder plutôt que d'inventer sa propre palette.

La [section 7](#7-dettes-de-design-identifiées) liste les incohérences repérées dans l'existant.
Elles sont à corriger dans le cadre de la refonte.

---

## 1. Le produit en bref

NEXUS SOC est une plateforme de détection et de réponse aux incidents de sécurité, open source,
déployée et exploitée **en interne par le CENADI**. Le CENADI opère les systèmes sensibles de
l'État camerounais : SIGIPES (gestion des personnels et de la solde) et ANTILOPE (traitement de
la solde).

Ce n'est pas un produit commercial. Il n'y a ni client payant, ni facturation, ni essai gratuit.
L'argument du projet est la souveraineté : le CENADI possède le code, l'audite, le modifie et
l'héberge sur son infrastructure.

**Vocabulaire imposé.** Le multi-locataire technique existe toujours dans la base (`tenant_id`,
RLS PostgreSQL) mais se lit désormais comme un **cloisonnement de périmètres internes**.

| À écrire | À ne jamais écrire |
|---|---|
| Périmètre supervisé | Tenant, client, locataire |
| Responsable de périmètre | DSI client, client final |
| Opérateur CENADI | Fournisseur, prestataire |
| Criticité (standard / sensible / critique) | Offre, plan, abonnement |
| Plateforme souveraine | SOC-as-a-Service, SaaS, SOCaaS |
| OpenTofu | Terraform |

Aucune mention de prix, FCFA, MRR, ARR, essai, upgrade ou facturation ne doit apparaître.

**Chaîne technique** (utile pour comprendre ce que les écrans affichent) :

```
Agent Go (~5 Mo, egress-only, HMAC-SHA256)
    → POST /ingest (FastAPI)
        → Kafka KRaft (nexus.telemetry)
            → Normalisation + corrélation MITRE ATT&CK (8 règles)
            → Modèles IA : M1 Isolation Forest réseau · M2 UEBA fraude interne
                → nexus.alerts
                    → SOAR (4 playbooks, validation humaine sur impact fort)
                        → Portail + notifications + rapport HTML
```

Wazuh 4.9.0 assure le stockage chaud et le SIEM. TimescaleDB (PostgreSQL 16) porte la
configuration, les alertes et les séries temporelles.

---

## 2. Contraintes techniques non négociables

Ces contraintes viennent du contexte de déploiement, pas d'une préférence esthétique.

### 2.1 Pas de build, pas de framework

Chaque page est un **fichier HTML autonome** avec son CSS et son JavaScript en ligne. Pas de
React, pas de Vue, pas de bundler, pas de `node_modules`. Motif : le CENADI doit pouvoir ouvrir
le fichier, le lire, le modifier et le redéployer sans chaîne d'outils.

Seule exception : [`js/api.js`](Lot9_Frontend/js/api.js), le client HTTP partagé, chargé via
`<script src="js/api.js">` avant tout autre script.

### 2.2 Aucune dépendance réseau externe à l'exécution

Le déploiement cible est souverain et potentiellement coupé d'Internet. Toute ressource chargée
depuis un CDN casse la plateforme en production.

> **⚠️ Dette active.** Les 5 pages chargent aujourd'hui les polices depuis
> `fonts.googleapis.com`. Le service worker ne les met pas en cache. En réseau fermé, les pages
> retombent sur les polices système et perdent leur identité visuelle.
> **À corriger** : auto-héberger les 3 familles en WOFF2 sous `Lot9_Frontend/fonts/`,
> les déclarer en `@font-face`, les ajouter au `PRECACHE_URLS` de [`sw.js`](Lot9_Frontend/sw.js).

Même règle pour les icônes : SVG en ligne uniquement, pas de Font Awesome ni de Lucide via CDN.
L'existant utilise déjà un système d'attributs `data-ic="nom"` résolu en SVG par un script local.

### 2.3 Service par FastAPI

Les fichiers sont servis en statique sous `/app` par [`run.py`](run.py) :
`app.mount("/app", StaticFiles(directory=frontend_dir, html=True))`.
La racine `/` redirige vers `login.html`. Il n'y a pas de vitrine publique : la plateforme est
un outil interne.

Les chemins internes doivent rester **relatifs** (`js/api.js`, `console.html`) pour que les
pages fonctionnent aussi en ouverture directe `file://` pendant le développement. Le client
`api.js` détecte ce cas et bascule automatiquement sur `http://localhost:8000`.

### 2.4 PWA installable et utilisable hors ligne

[`manifest.json`](Lot9_Frontend/manifest.json) et [`sw.js`](Lot9_Frontend/sw.js) sont en place :
cache-first sur les assets, network-first sur l'API, `offline.html` en repli, notifications push,
3 raccourcis (Console, Portail, Documentation).

Toute nouvelle page doit être ajoutée à `PRECACHE_URLS` et le `CACHE_NAME` incrémenté
(`nexus-soc-v3` → `v4`).

### 2.5 Réseau contraint

Les postes du CENADI ne sont pas des machines de développeur. Viser moins de 150 Ko par page
hors polices, un premier rendu utile sans attendre l'API, et des squelettes de chargement plutôt
que des spinners plein écran.

### 2.6 Bilinguisme FR / EN

Le portail bascule en direct sans rechargement. Le mécanisme existant :

```html
<span data-i18n="cleDuDictionnaire">Texte par défaut</span>
<span data-fr="Bonjour" data-en="Hello"></span>
```

`setLang(lang)` parcourt les deux familles d'attributs. La console opérateur reste en français
seul : ses utilisateurs sont les analystes internes du CENADI.

---

## 3. Design system existant

Établi et déployé sur `login.html`, `console.html`, `portail.html`, `docs.html`, `contact.html`.
**Le respecter, ne pas le réinventer.** Il est autorisé de l'étendre (nouveaux tokens, nouveaux
composants) tant que la base reste intacte.

### 3.1 Direction artistique

Centre d'opérations de nuit. Sombre, dense, technique, sans être froid ni générique. La
signature vient du contraste entre une serif d'affichage en italique (inhabituelle sur un outil
de sécurité) et une monospace pour tout ce qui est machine.

### 3.2 Palette

```css
:root {
  /* Fonds, du plus profond au plus élevé */
  --bg:        #0A0F1C;   /* fond de page */
  --bg-2:      #0D1424;   /* champs de saisie, zones creusées */
  --surface:   #0F1729;   /* cartes, panneaux */
  --surface-2: #131D33;   /* survol, lignes de tableau actives */

  /* Bordures */
  --border:    #1E293B;   /* séparateurs discrets */
  --border-2:  #334155;   /* contours de carte, de champ */

  /* Texte, du plus fort au plus faible */
  --text:      #E2E8F0;   /* titres, valeurs */
  --text-2:    #94A3B8;   /* libellés, corps secondaire */
  --text-3:    #64748B;   /* métadonnées, placeholders */

  /* Accents fonctionnels */
  --accent:    #5EAAFF;   /* bleu — action principale, liens, risque 40–59 */
  --teal:      #3DDC97;   /* vert — sain, actif, risque < 40 */
  --amber:     #F5A524;   /* ambre — attention, criticité sensible, risque 60–79 */
  --red:       #EF4444;   /* rouge — critique, risque ≥ 80 */
  --purple:    #B98BFF;   /* violet — console seulement : IA, modèles */
  --cyan:      #38E1D6;   /* cyan — console seulement : réseau, flux */
}
```

**La couleur porte du sens, jamais de la décoration.** Le rouge signifie « risque ≥ 80 » et rien
d'autre. Un bouton secondaire n'a pas le droit d'être rouge parce que ça rend bien.

Échelle de risque, implémentée dans `NexusAPI.riskColor(score)` :

| Score | Token | Lecture |
|---|---|---|
| ≥ 80 | `--red` | Critique, action immédiate |
| 60–79 | `--amber` | Élevé, à traiter dans la journée |
| 40–59 | `--accent` | Moyen, à qualifier |
| < 40 | `--teal` | Faible, surveillance |

Badges de criticité de périmètre (`NexusAPI.criticiteBadge`) : `critique` → rouge,
`sensible` → ambre, `standard` → bleu.

### 3.3 Typographie

```css
--display: "Fraunces", Georgia, serif;        /* titres, logo, citations de l'Analyst */
--body:    "Manrope", sans-serif;             /* corps, boutons, libellés */
--mono:    "JetBrains Mono", monospace;       /* toute donnée machine */
```

Règles d'emploi :

- **Fraunces** en italique 600 pour le logo et les grands titres. Interlettrage serré
  (`letter-spacing: -.03em`). C'est la signature ; ne pas la remplacer par une grotesque.
- **Manrope** 400/500/600/700 pour le corps et l'interface.
- **JetBrains Mono** pour tout ce qui vient de la machine : horodatages, identifiants MITRE,
  noms d'hôtes, adresses IP, hachages, scores, libellés de champs en petites capitales.

Les libellés de formulaire suivent un motif constant : mono, 11 px, `letter-spacing: .08em`,
`text-transform: uppercase`, couleur `--text-2`.

### 3.4 Formes, ombres, mouvement

| Élément | Valeur |
|---|---|
| Rayon carte | 20 px (login), 12 px (cartes internes) |
| Rayon champ / bouton | 9–10 px |
| Rayon badge | 999 px |
| Ombre carte flottante | `0 24px 80px rgba(0,0,0,.55)` |
| Halo de focus | `0 0 0 3px rgba(94,170,255,.15)` |
| Largeur barre latérale | 220 px |
| Hauteur en-tête | 58 px |

Trois motifs d'ambiance sont déjà en place et réutilisables :

- `.bg-grid` : grille de 36 px à `rgba(94,170,255,.018)`, quasi invisible, donne de la texture.
- `.bg-glow` : halo radial bleu centré, `rgba(94,170,255,.07)`.
- `.scan-line` : ligne de balayage qui descend en 6 s. Présente sur le login uniquement.
  Ne pas la généraliser aux écrans de travail : elle distrait sur une session de 8 heures.

Le mouvement reste sobre. Entrée de carte en `cubic-bezier(.22,1,.36,1)` sur 600 ms, pulsation
2,2 s sur les points d'état en direct, transitions de 200 ms sur les états interactifs. Pas
d'animation d'entrée sur les lignes de tableau : un analyste rafraîchit sa file d'alertes
plusieurs fois par minute.

---

## 4. Rôles, routage, données

### 4.1 Les quatre rôles

Contrainte SQL : `role IN ('admin_plateforme','analyste_soc','dsi_client','lecteur')`.

| Rôle | Interface | Portée | Ce qu'il fait |
|---|---|---|---|
| `admin_plateforme` | `console.html` | Tous périmètres | Crée les périmètres, enrôle les agents, surveille le socle |
| `analyste_soc` | `console.html` | Tous périmètres (BYPASSRLS) | Traite les alertes, approuve ou refuse les actions SOAR |
| `dsi_client` | `portail.html` | Son périmètre (RLS) | Consulte les alertes de son périmètre, reçoit les rapports |
| `lecteur` | `portail.html` | Son périmètre (RLS) | Lecture seule |

> Le nom `dsi_client` est un identifiant technique figé en base. À l'écran il s'affiche
> **« Responsable de périmètre »**.

Le routage après connexion, dans [`login.html`](Lot9_Frontend/login.html#L335) :

```js
admin_plateforme → console.html
analyste_soc     → console.html
dsi_client       → portail.html
lecteur          → portail.html
```

`NexusAPI.guard(roles)` protège chaque page et renvoie vers `login.html` si le rôle ne
correspond pas. Dans la console, les sections réservées à l'admin portent la classe
`.admin-only` et sont masquées pour un analyste.

L'isolation réelle est appliquée en base par Row-Level Security PostgreSQL, pas par le frontend.
Masquer un bouton est du confort, pas de la sécurité.

### 4.2 Modèle de données

Les valeurs ci-dessous sont contraintes par `CHECK` en base. Un badge ou un filtre ne doit
jamais proposer une valeur hors de ces listes.

**`tenants`** (périmètres supervisés)

| Champ | Valeurs |
|---|---|
| `nom` | libre — en démo : SIGIPES, ANTILOPE, Réseau/LAN CENADI |
| `type` | `application_metier` · `reseau` · `infrastructure` · `poste_utilisateur` |
| `criticite` | `standard` · `sensible` · `critique` |

**`alerts`**

| Champ | Détail |
|---|---|
| `source_modele` | `Modèle 1 (réseau)` ou `Modèle 2 (UEBA)` |
| `type` | `Ransomware`, `Fraude interne`, `Exfiltration`, `Anomalie réseau / C2` |
| `entite` | hôte ou compte concerné |
| `risque` | entier 0–100 |
| `raisons` | JSONB, liste de chaînes — c'est l'explicabilité, à afficher telle quelle |
| `mitre` | identifiants séparés par virgule, ex. `T1005, T1059, T1071` |
| `statut` | `ouverte` · `en_cours` · `resolue` · `faux_positif` |

**`agents`** — `statut` ∈ `actif` · `isole` · `hors_ligne` ; `os` ∈ `windows` · `linux`.

**`soar_audit`** — `impact` ∈ `info` · `faible` · `moyen` · `fort` ;
`statut` ∈ `EXÉCUTÉE` · `EN ATTENTE DE VALIDATION` · `ANNULÉE` · `IGNORÉE`.
Seul l'impact `fort` déclenche une demande de validation humaine.

**`notifications`** — `type` ∈ `alert` · `soar_action` · `system` · `report` ;
`severity` ∈ `info` · `warning` · `critical` ; `report_html` porte le rapport téléchargeable.

**`metrics`** — hypertable TimescaleDB : `ts`, `tenant_id`, `agent_id`, `metrique`, `valeur`.
Métriques connues : `cpu`, `score_risque`, `octets_sortants`.

### 4.3 Endpoints disponibles

Tous exposés par `window.NexusAPI` (voir [`js/api.js`](Lot9_Frontend/js/api.js)). Le client gère
le JWT, le rafraîchissement automatique sur 401 et les erreurs réseau.

**Authentification**

```
POST /auth/token      {email, password} → {access_token, refresh_token}
POST /auth/refresh    {refresh_token}   → {access_token}
GET  /auth/me                           → {email, role, tenant_id, ...}
```

**Administration** (`admin_plateforme`)

```
GET    /admin/tenants                      POST   /admin/tenants
PATCH  /admin/tenants/{id}                 DELETE /admin/tenants/{id}
POST   /admin/tenants/{id}/suspend         POST   /admin/tenants/{id}/activate
GET    /admin/users                        POST   /admin/users
GET    /admin/agents                       POST   /admin/agents/token
GET    /admin/health                       GET    /admin/perimetres
GET    /admin/metrics?hours=24
```

**Provisionnement d'agents**

```
POST /provision/token                  génère un jeton d'enrôlement
POST /provision/enroll                 valide le jeton côté agent
GET  /provision/installer/{agent_id}   script d'installation
GET  /provision/offline-pack/{id}      archive .zip complète (réseau fermé)
GET  /provision/qr/{agent_id}          QR code d'enrôlement, PNG base64
GET  /provision/status/{agent_id}      état du jeton
GET  /provision/status/{id}/log        journal des tentatives
POST /provision/bulk                   provisionnement CSV en masse
GET  /provision/oneliner               commande shell générée
POST /provision/rotate-hmac/{id}       rotation de clé
POST /provision/revoke/{agent_id}      révocation ciblée
POST /provision/revoke-tenant/{id}     révocation de tout un périmètre
```

**Analyste SOC**

```
GET  /analyst/alerts              file agrégée, tous périmètres
GET  /analyst/alerts/{id}         détail
GET  /analyst/pending             actions SOAR en attente de validation
POST /analyst/approve/{action_id} {approved_by}
POST /analyst/reject/{action_id}  {reason}
POST /analyst/false-positive/{alert_id}
GET  /analyst/dashboard
```

Réponse de `/analyst/dashboard` :

```json
{
  "open_alerts": 12,
  "critical_alerts": 3,
  "agents_online": 47,
  "tenants_total": 3,
  "top_tenants_by_incidents": [{"nom": "SIGIPES", "incidents": 8}],
  "generated_at": "2026-08-11T14:32:00Z"
}
```

**Portail** (`dsi_client`, `lecteur` — filtré par RLS sur le `tenant_id` du JWT)

```
GET  /portal/alerts?limit=50
GET  /portal/agents
GET  /portal/summary
GET  /portal/notifications?unread_only=false&limit=50
POST /portal/notifications/{id}/mark-read
POST /portal/notifications/mark-all-read
GET  /portal/notifications/{id}/report      rapport HTML pour affichage in-app
GET  /portal/notifications/{id}/download    même rapport en pièce jointe
```

Réponse de `/portal/summary` :

```json
{
  "open_alerts": 4,
  "max_risk": 87,
  "agents_active": 12,
  "agents_total": 14,
  "unread_notifications": 2
}
```

**Socle et modèles**

```
GET  /health              sonde simple
GET  /health/detailed     état par service
GET  /monitor/drift?days=7   dérive des modèles IA
POST /score/network       {features} → score M1
POST /score/user-day      {features} → score M2
```

---

## 5. Fiches interface

### 5.1 `login.html` — Connexion

| | |
|---|---|
| **Fichier** | [Lot9_Frontend/login.html](Lot9_Frontend/login.html) (11 Ko) |
| **Utilisateurs** | Les 4 rôles |
| **Priorité de refonte** | Faible — corriger la dette, garder la composition |

**Objectif.** Authentifier et router vers la bonne interface. C'est la première impression de la
plateforme et la seule page vue par tous les rôles.

**État actuel.** Carte de 420 px centrée sur fond animé (grille, halo, ligne de balayage). Logo
Fraunces italique avec « SOC » en ambre, sous-titre mono, badge vert pulsé. Formulaire à deux
champs, bouton pleine largeur avec spinner intégré, zone d'erreur. Redirection automatique si
un jeton valide est déjà en session.

**À corriger.** Le sous-titre affiche encore `SOCaaS · Cameroun`
([login.html:246](Lot9_Frontend/login.html#L246)). Vestige de l'ancien positionnement commercial,
en contradiction directe avec la refonte souveraine. Remplacer par
`CENADI · Plateforme souveraine` ou équivalent.

**Améliorations utiles.**
- Distinguer visuellement l'échec d'authentification (identifiants) de l'échec réseau (serveur
  injoignable). `api.js` renvoie déjà `_network: true` sur le second cas.
- Rendre visible que la plateforme est hors ligne quand le service worker sert la page depuis
  le cache sans API joignable.
- Le champ mot de passe n'a pas de bouton d'affichage. Sur un poste sécurisé avec mot de passe
  long, c'est une gêne réelle.

**États à couvrir.** Repos · saisie · chargement · identifiants refusés · serveur injoignable ·
session déjà ouverte.

---

### 5.2 `console.html` — Console opérateur CENADI

| | |
|---|---|
| **Fichier** | [Lot9_Frontend/console.html](Lot9_Frontend/console.html) (81 Ko) |
| **Utilisateurs** | `admin_plateforme`, `analyste_soc` |
| **Priorité de refonte** | **Haute** — c'est le poste de travail principal |

**Objectif.** Poste de travail de l'équipe SOC du CENADI. Un analyste y passe sa journée. La
densité d'information prime sur l'aération.

**Architecture actuelle.** Barre latérale de 220 px, en-tête de 58 px, zone principale à
sections commutées par `goto(section)`. Sept sections en deux groupes :

*Administration* (classe `.admin-only`, masquée pour l'analyste)

| Section | Contenu | Endpoint |
|---|---|---|
| Tableau de bord | Grille de KPI | `/analyst/dashboard` |
| Périmètres | Table CRUD, badge de criticité, suspendre/réactiver | `/admin/tenants` |
| Agents | Table, statut, OS, dernière vue | `/admin/agents` |
| Santé système | Grille d'état par service | `/health/detailed` |
| Supervision | KPI + graphiques, sélecteur 1 h / 6 h / 24 h / 7 j | `/admin/metrics?hours=` |

*SOC Analyst* (visible pour les deux rôles)

| Section | Contenu | Endpoint |
|---|---|---|
| Alertes | File filtrable par risque et statut, pastille de compteur | `/analyst/alerts` |
| Approbation SOAR | Actions en attente de validation humaine, pastille | `/analyst/pending` |

Pied de barre latérale : carte utilisateur (initiales, e-mail, rôle, déconnexion).
Sur mobile, la barre latérale passe en tiroir avec voile.

**Ce qui manque et qu'il faut concevoir.**

1. **Parcours d'enrôlement d'agent.** Douze endpoints `/provision/*` existent et ne sont
   exposés nulle part dans l'interface. Il manque un assistant : choisir le périmètre, générer
   le jeton, puis proposer trois voies de déploiement selon le contexte réseau du poste cible.

   | Voie | Endpoint | Quand |
   |---|---|---|
   | Commande shell à copier | `GET /provision/oneliner` | Poste avec accès au serveur |
   | QR code | `GET /provision/qr/{id}` | Enrôlement mobile ou poste isolé |
   | Archive `.zip` | `GET /provision/offline-pack/{id}` | Réseau fermé, clé USB |

   Prévoir aussi l'import CSV (`POST /provision/bulk`) pour enrôler un parc entier, avec
   prévisualisation avant envoi et rapport ligne par ligne après.

2. **Détail d'alerte.** L'écran actuel liste les alertes mais n'exploite pas `raisons` (JSONB)
   ni `mitre`. C'est pourtant le cœur de l'explicabilité du projet. Concevoir un panneau ou une
   vue de détail montrant :
   - la chaîne d'attaque reconstituée, ordonnée, colorée par tactique MITRE
     (Initial Access → Execution → Collection → C2 → Impact) ;
   - les raisons du modèle, en clair, telles que renvoyées par l'API ;
   - le score et sa décomposition ;
   - les actions : approuver le SOAR, refuser, marquer en faux positif.

3. **Journal d'audit SOAR.** La table `soar_audit` est peuplée et jamais affichée. Un analyste
   doit pouvoir répondre à « qui a gelé ce compte, quand, sur quelle décision ». Vue
   chronologique filtrable par périmètre, acteur et impact.

4. **Dérive des modèles.** `GET /monitor/drift?days=7` existe, aucun écran ne le consomme.
   À rattacher à la section Supervision.

5. **Graphiques de supervision.** Le conteneur `#sup-charts` est vide. Séries à tracer depuis
   `/admin/metrics` : `cpu`, `score_risque`, `octets_sortants`. Contrainte : pas de
   bibliothèque externe, donc SVG généré à la main. Viser lisible avant spectaculaire.

**États à couvrir.** Squelettes de chargement (déjà implémentés, `.skeleton .sk-row`) · vide
(« aucune alerte ouverte » n'est pas une erreur, c'est une bonne nouvelle : le dire) · erreur
API · hors ligne · rôle analyste sans les sections admin.

**Points de vigilance.**
- Un analyste garde cette page ouverte des heures. Éviter les animations en boucle hors des
  points d'état en direct.
- Les pastilles de compteur (`#badge-alerts`, `#badge-soar`) doivent rester justes après chaque
  scrutation. Une pastille fausse détruit la confiance dans l'outil.
- 81 Ko en un fichier : la structure interne compte. Garder les blocs CSS commentés et séparés
  par section comme aujourd'hui.

---

### 5.3 `portail.html` — Portail responsable de périmètre

| | |
|---|---|
| **Fichier** | [Lot9_Frontend/portail.html](Lot9_Frontend/portail.html) (34 Ko) |
| **Utilisateurs** | `dsi_client`, `lecteur` |
| **Priorité de refonte** | **Haute** — c'est l'écran montré en soutenance |

**Objectif.** Rendre lisible, pour un responsable non technicien, l'état de sécurité de son
périmètre. Il ne connaît pas MITRE ATT&CK. Il veut savoir si son système va bien, ce qui se
passe s'il ne va pas bien, et quoi faire.

**État actuel.** Page unique, sans barre latérale. En-tête avec nom du périmètre, bascule FR/EN,
cloche de notifications. Panneau de notifications déroulant. Score de sécurité en grand,
rangée de KPI, liste d'alertes, grille d'agents. Deux modales : détail d'alerte et rapport HTML
en `<iframe sandbox>`. Système de toasts.

**Données disponibles.** `/portal/summary` donne `open_alerts`, `max_risk`, `agents_active`,
`agents_total`, `unread_notifications`. `/portal/alerts` et `/portal/agents` complètent.
Tout est filtré en base par RLS sur le `tenant_id` du jeton.

**Ce qu'il faut concevoir.**

1. **Le score de sécurité.** C'est l'élément le plus regardé de la plateforme. Aujourd'hui il
   dérive de `max_risk`. Il doit se lire en une seconde et se comprendre en cinq : que signifie
   un score de 87 ? Est-ce que ça monte ou ça descend ? Depuis quand ? Prévoir une tendance,
   pas seulement une valeur instantanée.

2. **Les alertes sans jargon.** Le responsable doit lire « une tentative d'exfiltration de
   données a été détectée sur le poste POSTE-RH-07 » avant de voir `T1041`. Le vocabulaire
   technique reste accessible, en second plan.

3. **Le LLM Analyst.** Le module produit un paragraphe de 3 à 5 phrases en français ou en
   anglais qui explique l'incident. La maquette du Lot 5 le traite en citation serif italique,
   comme une analyse éditoriale plutôt qu'un log. **Conserver ce traitement** : c'est la
   signature du portail et l'argument d'accessibilité du projet.

4. **Les notifications.** Le panneau existe. Affiner la hiérarchie par `severity`
   (`info` / `warning` / `critical`) et par `type` (`alert` / `soar_action` / `system` /
   `report`). Une notification de type `report` mène au rapport HTML, deux voies : affichage
   in-app en iframe ou téléchargement.

5. **Usage mobile.** Un responsable consulte souvent depuis son téléphone. Le `manifest.json`
   déclare d'ailleurs une capture `390×844`. Concevoir mobile d'abord sur cette page,
   contrairement à la console.

**États à couvrir.** Chargement · aucune alerte (état sain, à valoriser) · alerte critique en
cours · agents hors ligne · aucune notification · hors ligne (service worker) · les deux langues.

---

### 5.4 `docs.html` — Documentation intégrée

| | |
|---|---|
| **Fichier** | [Lot9_Frontend/docs.html](Lot9_Frontend/docs.html) (42 Ko) |
| **Utilisateurs** | Tous |
| **Priorité de refonte** | Moyenne |

**Objectif.** Guide d'exploitation embarqué dans la plateforme. Le CENADI doit pouvoir opérer
sans document externe. C'est aussi la démonstration concrète du caractère open source :
l'exploitant a la doc, le code et la licence.

**À traiter.** Navigation dans un document long (sommaire latéral collant, ancres, recherche
locale sans dépendance externe), coloration syntaxique des blocs de commande sans bibliothèque
CDN, bouton de copie sur chaque bloc, lisibilité en lecture prolongée (longueur de ligne,
interlignage).

---

### 5.5 `contact.html` — Contact équipe SOC

| | |
|---|---|
| **Fichier** | [Lot9_Frontend/contact.html](Lot9_Frontend/contact.html) (25 Ko) |
| **Utilisateurs** | Tous |
| **Priorité de refonte** | Faible |

**Objectif.** Formulaire interne de demande auprès de l'équipe SOC du CENADI, notamment pour
demander la mise sous supervision d'un nouveau périmètre.
Endpoint : `POST /contact/perimetre-request`.

Ce n'est pas une page de contact commercial. Ni carte, ni horaires d'ouverture, ni bouton
d'appel. Un formulaire interne, court, avec confirmation claire.

---

### 5.6 `offline.html` — Repli hors ligne

| | |
|---|---|
| **Fichier** | [Lot9_Frontend/offline.html](Lot9_Frontend/offline.html) (2,4 Ko) |
| **Priorité de refonte** | Faible, mais à ne pas négliger |

Servi par le service worker quand la navigation échoue. C'est la seule page **sans** dépendance
Google Fonts, et c'est le bon modèle : elle doit fonctionner quand tout le reste est coupé.

Elle doit dire ce qui est cassé, ce qui reste consultable depuis le cache, et proposer une
reprise. Garder son autonomie totale : pas de police externe, pas de `js/api.js`.

---

### 5.7 Rapport HTML d'incident

| | |
|---|---|
| **Généré par** | `GET /portal/notifications/{id}/report` et `/download` |
| **Stocké dans** | `notifications.report_html` |
| **Priorité de refonte** | Moyenne |

Document HTML autonome, produit côté serveur, affiché en `<iframe sandbox="allow-same-origin">`
ou téléchargé. Il sort du navigateur : il est transféré par e-mail, imprimé, archivé.

Contraintes propres :

- Aucune ressource externe, aucun script. Le sandbox de l'iframe bloque le JavaScript.
- **Doit rester lisible sur fond blanc à l'impression.** Le thème sombre du reste de la
  plateforme ne s'applique pas ici. Prévoir une feuille de style d'impression dédiée.
- Nommage du fichier : `rapport-nexussoc-{id8}.html`.
- Contenu attendu : identification de l'incident, périmètre, entité, score, chaîne MITRE,
  raisons du modèle, actions SOAR menées et leur statut, horodatages.

---

### 5.8 Maquette de référence — Lot 5

| | |
|---|---|
| **Fichier** | [Lot5_Restitution/portail/portal/index.html](Lot5_Restitution/portail/portal/index.html) |
| **Statut** | Maquette statique, non connectée |

Antérieure au portail connecté, elle porte deux motifs à reprendre plutôt qu'à abandonner :

- **La timeline kill-chain** colorée par tactique MITRE, qui rend une chaîne d'attaque lisible
  d'un coup d'œil.
- **La citation de l'Analyst** en Fraunces italique, traitée comme une analyse et non comme
  un log.

Entité de démonstration : `POSTE-RH-07`.

---

## 6. Composants transverses

À normaliser une fois et à réutiliser partout. Plusieurs existent déjà en plusieurs variantes
selon les pages : les unifier fait partie du travail.

| Composant | État | Note |
|---|---|---|
| Boutons | `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-sm` | Cohérents, à conserver |
| Champs | `.form-field`, `.form-input`, `.form-label` | Deux variantes divergentes login / console |
| Badges | Risque, criticité, statut, OS | À unifier en un seul composant paramétré |
| Squelettes | `.skeleton`, `.sk-row` | Bon motif, à généraliser |
| Modales | `.overlay` + `.modal` | Manque le piège de focus et la fermeture par Échap |
| Toasts | `.toasts` (portail seul) | À porter sur la console |
| Tables | `.tbl`, `.tbl-select` | Manque le tri, la pagination, l'état vide |
| Point d'état en direct | `.live-dot` | Pulsation 2,2 s |
| Icônes | `data-ic="nom"` → SVG en ligne | Système local, à étendre sans CDN |
| Grille de KPI | `.kpi-grid`, `.kpi-card` | Deux implémentations à fusionner |

---

## 7. Dettes de design identifiées

Relevées lors de l'analyse du code. À corriger dans la refonte.

| # | Problème | Fichier | Gravité |
|---|---|---|---|
| 1 | Polices chargées depuis `fonts.googleapis.com` sur 5 pages, non mises en cache par le service worker. Casse l'identité visuelle en réseau fermé et contredit le positionnement souverain | toutes sauf `offline.html` | **Haute** |
| 2 | Sous-titre `SOCaaS · Cameroun`, vocabulaire commercial supprimé partout ailleurs | [login.html:246](Lot9_Frontend/login.html#L246) | **Haute** |
| 3 | Douze endpoints `/provision/*` sans aucune interface (QR, pack hors ligne, CSV, rotation HMAC, révocation) | `console.html` | **Haute** |
| 4 | `raisons` (JSONB) et `mitre` jamais affichés alors qu'ils portent l'explicabilité, argument central du projet | `console.html` | **Haute** |
| 5 | Table `soar_audit` peuplée, jamais affichée | `console.html` | Moyenne |
| 6 | `#sup-charts` vide, aucun graphique implémenté | [console.html:1008](Lot9_Frontend/console.html#L1008) | Moyenne |
| 7 | `/monitor/drift` sans écran consommateur | `console.html` | Moyenne |
| 8 | Raccourci de manifeste libellé « Portail client DSI » | [manifest.json](Lot9_Frontend/manifest.json) | Faible |
| 9 | Modales sans piège de focus ni fermeture clavier | `console.html`, `portail.html` | Moyenne |
| 10 | Composants dupliqués entre console et portail (KPI, champs, badges) | les deux | Faible |

---

## 8. Règles de design

### À faire

- Traiter l'incertitude comme une donnée. Un score, une heure de dernière mise à jour et une
  source valent mieux qu'un chiffre nu.
- Donner un état vide qui informe. « Aucune alerte ouverte sur SIGIPES depuis 14 jours » est
  une information ; « Aucune donnée » n'en est pas une.
- Rendre l'action réversible visible. Le SOAR distingue les actions annulables (gel, isolation,
  blocage IP) des définitives. L'interface doit le montrer avant de demander confirmation.
- Afficher les horodatages en `fr-CM` via `NexusAPI.formatDate()`. Le fuseau du CENADI est
  UTC+1 ; les données arrivent en UTC.
- Rester dense sur la console, aéré sur le portail. Deux publics, deux rythmes de lecture.
- Concevoir les squelettes en même temps que les états chargés, pas après.

### À ne pas faire

- Introduire une bibliothèque JavaScript ou CSS chargée depuis un CDN.
- Employer la couleur hors de sa signification fonctionnelle (section 3.2).
- Réintroduire du vocabulaire commercial, même dans un commentaire de code.
- Utiliser Inter, Roboto ou une police système comme famille principale. Fraunces + Manrope +
  JetBrains Mono est la signature du projet.
- Passer les écrans de travail en thème clair. Un SOC s'exploite en salle sombre.
- Animer les lignes de tableau à chaque rafraîchissement.
- Masquer une donnée derrière un survol : sur mobile, il n'y a pas de survol.

---

## 9. Accessibilité, responsive, performance

**Accessibilité.** Contraste minimum AA sur les textes (`--text-3` sur `--bg` est à 4,7:1, à ne
pas descendre en dessous). Navigation clavier complète, halo de focus visible en permanence.
`role` et `aria-label` sur les éléments interactifs sans libellé textuel. Aucune information
portée par la couleur seule : un statut critique porte aussi une forme ou un mot.

**Responsive.** Points de rupture observés dans l'existant : 480 px (carte de connexion),
768 px (bascule de la barre latérale en tiroir), 1024 px (grilles). La console vise le poste
fixe et dégrade proprement ; le portail vise le mobile d'abord.

**Performance.** Moins de 150 Ko par page hors polices. Premier rendu utile avant la réponse de
l'API grâce aux squelettes. Le scrutation par défaut est de 30 s
(`NexusAPI.poll(fn, 30_000)`) : ne pas la réduire sans raison, chaque appel touche la base.

---

## 10. Livrables attendus

Par interface traitée :

1. Le fichier HTML complet, autonome, CSS et JS en ligne, prêt à déposer dans
   `Lot9_Frontend/`.
2. Les états couverts et démontrables : chargement, vide, erreur, hors ligne, et pour le portail
   les deux langues.
3. Les nouveaux tokens CSS ajoutés à `:root`, documentés en commentaire.
4. La mise à jour de `PRECACHE_URLS` et l'incrément de `CACHE_NAME` dans
   [`sw.js`](Lot9_Frontend/sw.js) si une page est ajoutée.
5. Une note courte sur les choix qui s'écartent de ce brief, avec leur motif.

**Ordre de traitement recommandé**, par valeur pour la soutenance du 24 août 2026 :

1. `portail.html` — c'est l'écran de démonstration, celui que le jury verra.
2. `console.html`, section Alertes et détail d'alerte — porte l'explicabilité, argument central.
3. `console.html`, parcours d'enrôlement d'agent — la plus grosse fonctionnalité non exposée.
4. Auto-hébergement des polices — débloque la démonstration hors ligne.
5. `login.html` — correction du vestige `SOCaaS`.
6. `docs.html` et le rapport HTML.

---

## Annexe — Repères de lancement

```bash
# Socle complet (~8 Go de RAM)
cd Lot0_Socle && docker compose up -d

# Serveur applicatif
uvicorn run:app --host 0.0.0.0 --port 8000 --reload
```

| Interface | URL |
|---|---|
| Connexion | `http://localhost:8000/app/login.html` |
| Console opérateur | `http://localhost:8000/app/console.html` |
| Portail périmètre | `http://localhost:8000/app/portail.html` |
| Documentation | `http://localhost:8000/app/docs.html` |
| API (Swagger) | `http://localhost:8000/docs` |
| Wazuh Dashboard | `https://localhost:5601` — `admin` / `admin` |

Périmètres de démonstration : SIGIPES (`application_metier`, `critique`),
ANTILOPE (`application_metier`, `critique`), Réseau/LAN CENADI (`reseau`, `sensible`).
Comptes : `resp.sigipes@cenadi.cm`, `resp.antilope@cenadi.cm`.
