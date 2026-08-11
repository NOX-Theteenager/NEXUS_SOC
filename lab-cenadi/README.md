# NEXUS SOC — LAB de déploiement SOUVERAIN au CENADI

Lab de démonstration du **déploiement souverain** de NEXUS SOC au **CENADI**
(Centre National de Développement de l'Informatique du Cameroun).

> **Contexte du stage :** stage effectué au **CENADI**. Ce lab illustre comment
> le CENADI déploie et exploite NEXUS SOC *sur sa propre infrastructure*, sans
> aucune donnée quittant le territoire ni même le datacenter.

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
| Exposition Internet | **Aucune** (reverse-proxy interne uniquement) |
| Cloisonnement | Par **périmètre supervisé** (RLS interne, un seul opérateur : le CENADI) |
| Systèmes surveillés | **Serveurs applicatifs gouvernementaux internes** |
| Notifications | Canal **in-app** (+ serveur SMTP interne Postfix on-premise si besoin) |
| Enrichissement IOC | **Base de menaces locale** (miroir hors-ligne) ou désactivé |
| Certificats TLS | **PKI interne CENADI** (autorité racine souveraine) |
| Zone sensible | **Air-gap** (VLAN paie/budget sans route Internet) |

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
║                                   │ pare-feu interne (pfSense)             ║
║  ┌────────────────────────────────┼───────────────────────────────────┐   ║
║  │  ZONE 1 — CŒUR SOC (NEXUS SOC souverain)                            │   ║
║  │   • PostgreSQL/TimescaleDB (données SOC, chiffré au repos)          │   ║
║  │   • uvicorn NEXUS SOC (mono-tenant CENADI)                          │   ║
║  │   • Wazuh Manager + Indexer (SIEM)                                  │   ║
║  │   • Moteur IA (M1 réseau, M2 UEBA) + SOAR                           │   ║
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
| Cœur SOC | `vm-soc-cenadi` (ou **HÔTE**) | 10.50.0.1 | NEXUS SOC souverain + PKI + SMTP interne |
| Z2 Applicatif | `vm-app-gov` | 10.50.20.20 | Serveur applicatif métier (annuaire, messagerie) |
| Z3 Sensible **air-gap** | `vm-antilope` | 10.50.30.30 | Simule ANTILOPE/SIGIPES (solde) — **zéro Internet** |
| Z4 Admin | `vm-rssi` | 10.50.40.40 | Poste du RSSI/DSI CENADI (console + validation SOAR) |
| Z5 Menace | `vm-menace` | 10.50.50.50 | Poste bureautique compromis (Kali) |

---

## 4. Ce que le lab démontre

| # | Scénario | Preuve |
|---|----------|--------|
| 1 | **Souveraineté totale** — zéro sortie datacenter | tcpdump + config firewall : aucune route Internet, même pour le SOC |
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
├── 01-network-setup.sh           ← réseaux libvirt (zones/VLANs souverains)
├── 02-vm-specs.md                ← specs des VMs
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
2. Lire **`SECURISATION.md`** (le durcissement — c'est le cœur de la valeur)
3. Exécuter **`01-network-setup.sh`** (réseaux souverains isolés)
4. Créer les VMs selon **`02-vm-specs.md`**
5. Configurer le HÔTE : **`scripts/host-cenadi-configure.sh`**
6. Configurer chaque VM : **`scripts/vm-*-setup.sh`**
7. Répéter la démo avec **`RUNBOOK.md`**

> Ce lab exécute **le même code** NEXUS SOC que le reste du dépôt : seules la
> configuration (`.env` souverain), le réseau (aucune sortie), la PKI (AC
> interne) et, le cas échéant, le SMTP (Postfix local) sont adaptés au contexte
> on-premise du CENADI.
