# NEXUS SOC — LAB de démonstration complet

Lab reproductible pour démontrer **en temps réel** les 4 facettes clés du projet
NEXUS SOC lors de la soutenance du 24 août 2026.

> **Hyperviseur cible :** virt-manager / libvirt / KVM sur Ubuntu 22.04+
> **RAM hôte minimale :** 32 Go
> **Disque hôte minimal :** 200 Go SSD
> **Durée de la démo scriptée :** ~45 minutes (couvre les 4 scénarios avec marges)

---

## 1. Ce que le lab démontre

| # | Scénario                                    | Preuve visible                                                | Public visé |
|---|---------------------------------------------|---------------------------------------------------------------|-------------|
| 1 | **Souveraineté** — zéro sortie de données   | `tcpdump` sur `virbr-lab` : aucune requête vers l'extérieur   | Jury + client |
| 2 | **Détection fraude UEBA**                   | Modèle 2 émet une alerte critique → notification DSI + rapport | Jury (technique) |
| 3 | **Ransomware + SOAR avec garde-fous humains** | Isolation host auto + attente validation gel de compte      | Jury (technique) |
| 4 | **PLG SaaS avec OTP Gmail réel**            | Inscription depuis nexussoc.cm → mail reçu → activation      | Jury + client |

---

## 2. Architecture du lab

```
                                     ┌─────────────────────────────────┐
                                     │  MACHINE HÔTE Ubuntu (32 Go+)   │
                                     │                                 │
                                     │  ┌─────────┐  ┌──────────────┐  │
                                     │  │ Firefox │  │ virt-manager │  │
                                     │  └────┬────┘  └──────┬───────┘  │
                                     └───────┼──────────────┼──────────┘
                                             │              │
                                     ┌───────▼──────┐       │
                                     │ Internet     │       │ libvirt
                                     │ Cloudflare   │       │
                                     │ nexussoc.cm  │       │ RÉSEAU ISOLÉ
                                     └──────────────┘       │ 10.42.0.0/24
                                                            │ (pas d'Internet)
                                                            │
                        ┌───────────────┬──────────────────┼─────────────────┬────────────────┐
                        │               │                  │                 │                │
                 ┌──────▼──────┐ ┌──────▼──────┐    ┌──────▼──────┐  ┌──────▼──────┐
                 │  vm-soc     │ │  vm-cible   │    │  vm-kali    │  │  vm-dsi     │
                 │ 10.42.0.10  │ │ 10.42.0.20  │    │ 10.42.0.30  │  │ 10.42.0.40  │
                 │             │ │             │    │             │  │             │
                 │ Ubuntu 22   │ │ Ubuntu 22   │    │ Kali        │  │ Ubuntu 22   │
                 │ Server      │ │ Server      │    │ Rolling     │  │ Desktop     │
                 │             │ │             │    │             │  │             │
                 │ 8 Go / 4 CPU│ │ 4 Go / 2 CPU│    │ 4 Go / 2 CPU│  │ 2 Go / 2 CPU│
                 │             │ │             │    │             │  │             │
                 │ • PostgreSQL│ │ • Agent Go  │    │ • nmap      │  │ • Firefox   │
                 │ • Kafka     │ │ • Wazuh ag. │    │ • hydra     │  │ • terminaux │
                 │ • Wazuh Mgr │ │ • Scripts   │    │ • curl/wget │  │             │
                 │ • uvicorn   │ │   scénarios │    │ • Scripts   │  │             │
                 │ • Cert TLS  │ │             │    │   attaques  │  │             │
                 │   local     │ │             │    │             │  │             │
                 └─────────────┘ └─────────────┘    └─────────────┘  └─────────────┘
                        ▲                                                    │
                        │                                                    │
                        └────── HTTPS soc.minfi.local ──────────────────────┘
                                (certificat self-signed accepté dans le lab)
```

### Rôle de chaque VM

| VM        | IP          | RAM  | Rôle démo                                                                              |
|-----------|-------------|------|----------------------------------------------------------------------------------------|
| `vm-soc`  | 10.42.0.10  | 8 Go | Le SOC souverain déployé chez le client. Reçoit toute la télémétrie et héberge le portail. |
| `vm-cible`| 10.42.0.20  | 4 Go | Un poste de travail comptable (MINFI simulé). Envoie de la télémétrie normale puis anormale. |
| `vm-kali` | 10.42.0.30  | 4 Go | Un attaquant externe qui déclenche le scénario ransomware (C2 depuis IP suspecte).      |
| `vm-dsi`  | 10.42.0.40  | 2 Go | Le poste du DSI qui consulte le portail et valide/rejette les actions SOAR à fort impact. |

---

## 3. Séquence d'installation (une fois pour toutes)

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 0 : Préparation du hôte (~30 min)                        │
│  → Suivre 00-prerequisites.md                                    │
│  → Installer libvirt/virt-manager                                │
│  → Télécharger les ISOs Ubuntu 22.04 Server/Desktop + Kali       │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1 : Réseau libvirt isolé (~2 min)                        │
│  → Exécuter 01-network-setup.sh                                  │
│  → Vérifier que 'nexus-lab' apparaît dans virsh net-list         │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2 : Création des 4 VMs (~1h — 15 min chacune)            │
│  → Suivre 02-vm-specs.md                                         │
│  → Créer manuellement dans virt-manager avec les specs exactes   │
│  → Installer l'OS de base (defaults acceptables)                 │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3 : Post-installation par VM (~2h au total)              │
│  → vm-soc    : scripts/vm-soc-setup.sh                           │
│  → vm-cible  : scripts/vm-cible-setup.sh                         │
│  → vm-kali   : scripts/vm-kali-setup.sh                          │
│  → vm-dsi    : scripts/vm-dsi-setup.sh                           │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 4 : Snapshots libvirt (~5 min)                           │
│  → virsh snapshot-create-as <vm> baseline "État post-install"    │
│  → Permet de rejouer la démo autant que voulu (reset < 30s)      │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 5 : Répétition & jour J                                  │
│  → Suivre RUNBOOK.md (minute par minute)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Structure des fichiers du lab

```
lab/
├── README.md                            ← ce fichier
├── 00-prerequisites.md                  ← installation host + ISOs
├── 01-network-setup.sh                  ← création réseau libvirt isolé
├── 02-vm-specs.md                       ← specs pour virt-manager
├── RUNBOOK.md                           ← script de la démo minute-par-minute
├── topology.md                          ← diagramme ASCII de référence
├── troubleshooting.md                   ← erreurs fréquentes + fix
│
├── scripts/
│   ├── vm-soc-setup.sh                  ← installation NEXUS SOC serveur
│   ├── vm-cible-setup.sh                ← installation agent + Wazuh
│   ├── vm-kali-setup.sh                 ← outils d'attaque + scripts
│   └── vm-dsi-setup.sh                  ← Firefox + certificats + raccourcis
│
└── scenarios/
    ├── 01-souverainete-check.sh         ← tcpdump + preuve zéro sortie
    ├── 02-fraude-ueba.sh                ← transactions frauduleuses
    ├── 03-ransomware-soar.sh            ← chiffrement + attente SOAR
    └── 04-plg-otp-guide.md              ← démo PLG depuis le hôte
```

---

## 5. Timing de la démo (résumé)

| Bloc                          | Durée | Preuve produite                                    |
|-------------------------------|-------|----------------------------------------------------|
| Introduction (contexte, arch) | 5 min | Slide + topology.md affiché                        |
| **Scénario 4 — PLG SaaS**     | 6 min | Mail Gmail arrivé sur écran + tenant créé          |
| **Scénario 1 — Souveraineté** | 5 min | tcpdump vide de trafic sortant + arp table         |
| **Scénario 2 — Fraude UEBA**  | 10 min| Alerte critique + notification portail DSI + PDF   |
| **Scénario 3 — Ransomware**   | 12 min| Playbook SOAR animé + validation humaine + rollback|
| Questions & synthèse          | 7 min | audit_log.csv + KPIs console admin                 |
| **Total**                     | ~45 min |                                                  |

Le runbook complet (dialogues, commandes, points de bascule) est dans
**`RUNBOOK.md`**.

---

## 6. Étapes suivantes après lecture

1. Lire **`00-prerequisites.md`** et installer libvirt + télécharger les ISOs
2. Exécuter **`01-network-setup.sh`** pour créer le réseau isolé
3. Suivre **`02-vm-specs.md`** pour créer les 4 VMs dans virt-manager
4. Sur chaque VM, exécuter le script correspondant dans **`scripts/`**
5. Faire un snapshot de chaque VM en état "baseline"
6. Lire et répéter **`RUNBOOK.md`** au moins deux fois avant la soutenance

---

## 7. En cas de blocage

Consulter **`troubleshooting.md`** — les 15 pannes les plus fréquentes (VM qui
ne boote pas, réseau isolé qui laisse fuiter, agent qui ne se connecte pas,
certificat TLS refusé, etc.) avec commande de diagnostic + fix.
