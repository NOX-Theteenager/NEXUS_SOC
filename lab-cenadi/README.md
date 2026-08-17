# NEXUS SOC — LAB de déploiement SOUVERAIN au CENADI

Lab de démonstration du **déploiement souverain** de NEXUS SOC au **CENADI**
(Centre National de Développement de l'Informatique du Cameroun).

> **Contexte du stage :** stage effectué au **CENADI**. Ce lab illustre comment
> le CENADI déploie et exploite NEXUS SOC *sur sa propre infrastructure*, sans
> aucune donnée quittant le territoire ni même le datacenter.

> **État au 17 août 2026.** Les sections 3 et 6 décrivent l'architecture
> **cible**. Ce qui tourne est un réseau libvirt à plat, sans pare-feu ni
> segmentation. La phase 1 du
> [plan de réponse collaborative](../00_Documents/Decision_Reponse_Collaborative.md)
> déploie la topologie décrite ici.

---

## 1. Pourquoi un déploiement souverain pour le CENADI ?

Le CENADI héberge et exploite les systèmes d'information critiques de l'État
camerounais :

| Système | Rôle | Sensibilité |
|---------|------|-------------|
| **ANTILOPE / SIGIPES** | Gestion de la solde et du personnel de l'État | Très élevée (paie de centaines de milliers d'agents) |
| **PROBMIS** | Préparation et exécution du budget de l'État | Très élevée |
| **Systèmes DGI / DGTCFM** | Recettes fiscales, trésor | Très élevée |
| **Annuaire / messagerie gouvernementale** | Identités, communications | Élevée |

Pour ces systèmes, l'hébergement des données de sécurité chez un tiers ou hors
du territoire est **inacceptable** :

- Les données de paie et de budget de l'État **ne peuvent pas** transiter par
  un tiers, ni sortir du territoire (règlement CEMAC 2020, souveraineté
  numérique nationale).
- Le CENADI dispose de sa **propre infrastructure** (datacenter, personnel IT)
  et **exploite lui-même** la plateforme, dont il possède et audite le code.
- Exigence d'**air-gap partiel** : la zone la plus sensible n'a aucune route
  vers Internet.

C'est exactement ce que NEXUS SOC est conçu pour faire : une plateforme
100 % open source, déployée **on-premise** et cloisonnée par **périmètre
supervisé** (SIGIPES, ANTILOPE, réseau/LAN interne).

---

## 2. Principes du lab souverain

| Critère | Choix du lab souverain CENADI |
|---------|-------------------------------|
| Hébergement du SOC | **Dans le datacenter CENADI** |
| Exposition Internet | **Aucune en entrée.** Sortie maîtrisée par zone : cœur SOC sur liste blanche journalisée, zone sensible jamais |
| Cloisonnement | Par **périmètre supervisé** (RLS interne, un seul opérateur : le CENADI) |
| Systèmes surveillés | **Serveurs applicatifs gouvernementaux internes** |
| Notifications | Canal **in-app** (+ serveur SMTP interne Postfix on-premise si besoin) |
| Enrichissement IOC | **MISP auto-hébergé** ; VirusTotal désactivé par défaut |
| Certificats TLS | **PKI interne CENADI** (autorité racine souveraine) |
| Zone sensible | **Air-gap** (paie/budget, aucune route Internet, télémétrie vers le SOC seule) |
| Dossiers d'enquête | **DFIR-IRIS** (LGPL-3.0), cloisonné par périmètre |
| Pare-feu | **OPNsense**, routage inter-zone + ACL + API de réponse |

---

## 3. Architecture cible (vue d'ensemble)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║           DATACENTER CENADI (souverain, territoire camerounais)             ║
║                                                                             ║
║  ┌────────────────────────────────────────────────────────────────────┐   ║
║  │  ZONE 0 — DMZ INTERNE (accès restreint, pas d'Internet entrant)     │   ║
║  │   • Reverse-proxy interne (portail SOC) : soc.cenadi.local          │   ║
║  │   • Serveur SMTP interne (Postfix) pour les OTP/notifications       │   ║
║  └───────────────────────────────┬────────────────────────────────────┘   ║
║                                   │ OPNsense (routage + ACL + API)         ║
║  ┌────────────────────────────────┼───────────────────────────────────┐   ║
║  │  ZONE 1 — CŒUR SOC (NEXUS SOC souverain)                            │   ║
║  │   • PostgreSQL/TimescaleDB (données SOC, chiffré au repos)          │   ║
║  │   • uvicorn NEXUS SOC                                               │   ║
║  │   • Wazuh Manager + Indexer (SIEM)                                  │   ║
║  │   • Moteur IA (M1 réseau, M2 UEBA) + SOAR                           │   ║
║  │   • DFIR-IRIS (dossiers) + Mattermost (discussion)                  │   ║
║  │   • PKI interne (autorité de certification racine CENADI)          │   ║
║  └──────┬───────────────────────┬───────────────────────┬─────────────┘   ║
║         │ collecte              │ collecte              │ admin           ║
║  ┌──────▼─────────┐  ┌──────────▼────────┐  ┌───────────▼──────────┐      ║
║  │ ZONE 2 —       │  │ ZONE 3 —          │  │ ZONE 4 —             │      ║
║  │ SERVEURS       │  │ SERVEURS          │  │ POSTES               │      ║
║  │ APPLICATIFS    │  │ SENSIBLES         │  │ ADMINISTRATION       │      ║
║  │ (VLAN 20)      │  │ (VLAN 30 AIR-GAP) │  │ (VLAN 40)            │      ║
║  │                │  │                   │  │                      │      ║
║  │ • App métier   │  │ • ANTILOPE/SIGIPES│  │ • Poste RSSI/DSI     │      ║
║  │ • Annuaire     │  │   (solde État)    │  │ • Console SOC        │      ║
║  │ • Messagerie   │  │ • PROBMIS (budget)│  │ • Validation SOAR    │      ║
║  │                │  │ ZÉRO Internet     │  │                      │      ║
║  │ Agent NEXUS    │  │ Agent NEXUS       │  │ Firefox → portail    │      ║
║  └────────────────┘  └───────────────────┘  └──────────────────────┘      ║
║                                                                             ║
║  ┌────────────────────────────────────────────────────────────────────┐   ║
║  │  ZONE 5 — MENACE (simulation d'un poste compromis interne)          │   ║
║  │   • vm-menace (Kali) — attaquant depuis le réseau bureautique       │   ║
║  └────────────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════════════╝

        AUCUNE flèche ne sort de ce cadre → souveraineté totale des données
```

### Rôle de chaque zone / VM

| Zone | VM | IP | Rôle |
|------|-----|-----|------|
| Cœur SOC | **HÔTE** | 10.50.0.2 | NEXUS SOC + PKI + SMTP interne + IRIS + Mattermost |
| Pare-feu | `OPNsense-CENADI` | `.1` de chaque zone | Routage inter-zone, ACL, alias de réponse |
| Z2 Applicatif | `vm-app-gov` | 10.50.20.20 | Serveur applicatif métier (annuaire, messagerie) |
| Z3 Sensible **air-gap** | `vm-antilope` | 10.50.30.30 | Simule ANTILOPE/SIGIPES (solde) — **zéro Internet** |
| Z4 Admin | `vm-rssi` | 10.50.40.40 | Poste du RSSI/DSI CENADI (console + validation SOAR) |
| Z5 Menace | `vm-menace` | 10.50.50.50 | Poste bureautique compromis (Kali) |

---

## 4. Ce que le lab démontre

| # | Scénario | Preuve |
|---|----------|--------|
| 1 | **Sortie maîtrisée** — rien ne part sans règle | Depuis le SOC, une destination sur liste blanche répond, une autre est rejetée et journalisée |
| 2 | **Air-gap de la zone sensible** | vm-antilope (VLAN 30) ne peut joindre NI Internet NI les autres zones, seulement envoyer sa télémétrie au SOC |
| 3 | **Détection d'exfiltration de données de paie** | Un poste compromis tente d'aspirer ANTILOPE → Modèle 1/2 + SOAR |
| 4 | **PKI souveraine** — certificats émis par l'AC CENADI | Le portail SOC est en HTTPS via une autorité racine **interne**, pas Let's Encrypt |
| 5 | **Notifications sans Internet** | Alertes délivrées en in-app (et Postfix on-premise si e-mail requis), sans dépendance externe |

---

## 5. Documents du lab

```
lab-cenadi/
├── README.md                     ← ce fichier
├── 00-architecture-cenadi.md     ← architecture détaillée + adressage
├── 01-network-setup.sh           ← réseaux libvirt (zones souveraines)
├── 02-vm-specs.md                ← specs des VMs + budget mémoire
├── 03-quarantaine-blocage.md     ← OPNsense : alias, API, connecteur
├── 04-annuaire-vm-app-gov.md     ← annuaire LDAP, gel de compte
├── 05-alimenter-en-donnees.md    ← faire produire de la télémétrie au lab
├── 06-reponse-collaborative.md   ← DFIR-IRIS + Mattermost
├── SECURISATION.md               ← ★ durcissement défense-en-profondeur (pièce maîtresse)
├── RUNBOOK.md                    ← démo minute-par-minute
├── scripts/
│   ├── host-cenadi-configure.sh  ← configure le HÔTE en SOC souverain (PKI + SMTP interne)
│   ├── vm-app-gov-setup.sh       ← agent NEXUS sur serveur applicatif
│   ├── vm-antilope-setup.sh      ← agent NEXUS sur zone sensible air-gap
│   ├── vm-rssi-setup.sh          ← poste RSSI + certificat AC interne
│   └── vm-menace-setup.sh        ← poste attaquant
└── scenarios/
    ├── 01-souverainete-datacenter.sh   ← preuve zéro sortie
    ├── 02-airgap-zone-sensible.sh      ← preuve isolation ANTILOPE
    └── 03-exfiltration-solde.sh        ← attaque + détection + SOAR
```

---

## 6. Ordre de mise en place

1. Lire **`00-architecture-cenadi.md`** (comprendre les 6 zones)
2. Lire **`SECURISATION.md`** (le durcissement)
3. Exécuter **`01-network-setup.sh`** (réseaux isolés)
4. Créer les VMs selon **`02-vm-specs.md`**, à commencer par OPNsense
5. Appliquer la matrice de flux et les alias : **`03-quarantaine-blocage.md`**
6. Configurer le HÔTE : **`scripts/host-cenadi-configure.sh`**
7. Configurer chaque VM : **`scripts/vm-*-setup.sh`**
8. Déployer l'annuaire (**`04-…`**) puis la pile de réponse (**`06-…`**)
9. Répéter la démo avec **`RUNBOOK.md`**

> Ce lab exécute **le même code** NEXUS SOC que le reste du dépôt : seules la
> configuration (`.env` souverain), le réseau (aucune sortie), la PKI (AC
> interne) et, le cas échéant, le SMTP (Postfix local) sont adaptés au contexte
> on-premise du CENADI.
