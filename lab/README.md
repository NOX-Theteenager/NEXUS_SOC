# NEXUS SOC — LAB de démonstration complet

Lab reproductible pour démontrer **en temps réel** les 5 facettes clés du projet
NEXUS SOC lors de la soutenance du 24 août 2026.

> **Hyperviseur cible :** virt-manager / libvirt / KVM + GNS3 sur Ubuntu 22.04+
> **RAM hôte minimale :** 32 Go
> **Disque hôte minimal :** 200 Go SSD
> **Durée de la démo scriptée :** ~50 minutes (5 scénarios + intro GNS3)

**Architecture unique et robuste :**
- Le **HÔTE Ubuntu** joue le rôle du serveur SaaS NEXUS SOC (systemd auto-start)
- **GNS3** apporte pfSense (pare-feu bord) + MikroTik CHR (routeur multi-VLAN)
- **4 VMs libvirt** représentent deux clients + un attaquant :
  - VLAN 10 : Client **Afriland First Bank** (`vm-cible` poste comptable + `vm-dsi` poste DSI)
  - VLAN 20 : Client **UBA Cameroun** (`vm-cibleB` Alpine 2 Go, prouve isolation)
  - VLAN 30 : Attaquant externe (`vm-kali`)
- **Segmentation VLAN + RLS PostgreSQL** = double isolation prouvable

---

## 1. Ce que le lab démontre

| # | Scénario                                    | Preuve visible                                                | Public visé |
|---|---------------------------------------------|---------------------------------------------------------------|-------------|
| 1 | **Souveraineté** — zéro sortie de données   | pfSense : règle "no Internet" + compteur bloqué en temps réel | Jury + client |
| 2 | **Détection fraude UEBA**                   | Modèle 2 émet une alerte critique → notification DSI + rapport | Jury (technique) |
| 3 | **Ransomware + SOAR avec garde-fous humains** | Isolation host auto + attente validation gel de compte      | Jury (technique) |
| 4 | **PLG SaaS avec OTP Gmail réel**            | Inscription depuis nexussoc.cm → mail reçu → activation      | Jury + client |
| 5 | **Isolation cross-tenant (VLAN + RLS)**     | nmap VLAN30→VLAN10 échoue + JWT filtrage RLS PostgreSQL       | Jury (technique) |

---

## 2. Architecture du lab

Le **HÔTE Ubuntu** joue le rôle du serveur NEXUS SOC (services déjà en systemd :
PostgreSQL, uvicorn, cloudflared). GNS3 fournit pfSense + MikroTik pour la
segmentation multi-VLAN. 4 VMs représentent deux clients et un attaquant.

```
        ┌──────────────────────────────────────────────────────────────┐
        │  MACHINE HÔTE Ubuntu (32 Go+) = SERVEUR NEXUS SOC            │
        │  • PostgreSQL/Timescale  • uvicorn 0.0.0.0:8000              │
        │  • Caddy TLS :8443       • cloudflared → nexussoc.cm         │
        │  • IP lab = 10.42.0.1 (gateway virbr-mgmt)                   │
        │  • GNS3 Server (pfSense + MikroTik)                          │
        └───────────────┬──────────────────────────────────────────────┘
                        │ virbr-mgmt (10.42.0.0/24)
                ┌───────▼────────┐
                │  pfSense-Bord  │  pare-feu de bord (WAN désactivable)
                └───────┬────────┘
                ┌───────▼────────┐
                │ MikroTik-Core  │  routage inter-VLAN + ACL isolation
                └──┬────┬────┬───┘
          VLAN10  │    │    │  VLAN30
          ┌───────┘  VLAN20 └────────┐
          │            │             │
   ┌──────▼─────┐ ┌────▼──────┐ ┌────▼──────┐
   │ virbr-     │ │ virbr-    │ │ virbr-    │
   │ vlan10     │ │ vlan20    │ │ vlan30    │
   │ 10.42.10.x │ │ 10.42.20.x│ │ 10.42.30.x│
   └──┬──────┬──┘ └────┬──────┘ └────┬──────┘
      │      │         │             │
 ┌────▼──┐┌──▼───┐ ┌───▼─────┐  ┌────▼────┐
 │vm-cible││vm-dsi│ │vm-cibleB│  │ vm-kali │
 │.10.20 ││.10.40│ │ .20.20  │  │ .30.30  │
 │4Go    ││2Go   │ │Alpine2Go│  │ Kali4Go │
 └───────┘└──────┘ └─────────┘  └─────────┘
  ══ Client Afriland ══  ═ UBA ═   ═ Attaquant ═
     (VLAN 10)          (VLAN 20)    (VLAN 30)
```

### Rôle de chaque nœud

| Nœud        | IP           | RAM  | Rôle démo                                                            |
|-------------|--------------|------|---------------------------------------------------------------------|
| **HÔTE**    | 10.42.0.1    | —    | Serveur NEXUS SOC (systemd). Reçoit la télémétrie, héberge le portail. |
| `vm-cible`  | 10.42.10.20  | 4 Go | Poste comptable **Afriland** (VLAN 10). Télémétrie normale → fraude → ransomware. |
| `vm-dsi`    | 10.42.10.40  | 2 Go | Poste DSI **Afriland** (VLAN 10). Consulte le portail, valide/rejette le SOAR. |
| `vm-cibleB` | 10.42.20.20  | 2 Go | Client **UBA** (VLAN 20, Alpine léger). Prouve l'isolation cross-tenant. |
| `vm-kali`   | 10.42.30.30  | 4 Go | Attaquant externe (VLAN 30). C2 ransomware + scan cross-tenant échoué. |

pfSense (1 Go) + MikroTik CHR (512 Mo) dans GNS3. **Total ≈ 22 Go** sur 32.

---

## 3. Séquence d'installation (une fois pour toutes)

**Documents à lire en séquence :**

| # | Fichier                        | Rôle                                       |
|---|--------------------------------|--------------------------------------------|
| 1 | `00-prerequisites.md`          | Installer libvirt + GNS3, télécharger ISOs |
| 2 | `01-network-setup.sh`          | Créer les 4 bridges libvirt multi-VLAN     |
| 3 | `03-gns3-architecture.md`      | Construire la topologie GNS3 (pfSense + MikroTik) |
| 4 | `scripts/host-configure.sh`    | Configurer le HÔTE comme serveur SOC       |
| 5 | `02-vm-specs.md`               | Créer les 4 VMs libvirt                    |
| 6 | `scripts/vm-*-setup.sh`        | Configurer chaque VM (agent, outils)       |
| 7 | `RUNBOOK.md`                   | Répéter la démo jusqu'à maîtrise           |

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 0 : Préparation du hôte (~40 min)                        │
│  → 00-prerequisites.md : libvirt + GNS3 + ISOs (dont Alpine)     │
│  → Images GNS3 : pfSense CE + MikroTik CHR                       │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1 : Réseaux libvirt multi-VLAN (~2 min)                  │
│  → ./01-network-setup.sh                                         │
│  → Vérifier : virsh net-list → nexus-mgmt/vlan10/vlan20/vlan30   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2 : Topologie GNS3 (~45 min)                             │
│  → 03-gns3-architecture.md : pfSense + MikroTik + 4 Cloud nodes  │
│  → Configurer ACL inter-VLAN + routage vers 10.42.0.1           │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3 : Configurer le HÔTE comme SOC (~10 min)               │
│  → scripts/host-configure.sh                                     │
│  → uvicorn 0.0.0.0, ufw virbr-mgmt, Caddy TLS, mkcert            │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 4 : Création des 4 VMs (~1h)                             │
│  → 02-vm-specs.md (vm-cible, vm-dsi, vm-cibleB, vm-kali)         │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 5 : Post-install par VM (~1h30)                          │
│  → vm-cible  : scripts/vm-cible-setup.sh                         │
│  → vm-cibleB : scripts/vm-cibleB-setup.sh                        │
│  → vm-kali   : scripts/vm-kali-setup.sh                          │
│  → vm-dsi    : scripts/vm-dsi-setup.sh                           │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 6 : Snapshots + répétition (~5 min + répét.)             │
│  → virsh snapshot-create-as <vm> os-installed "..."             │
│  → Suivre RUNBOOK.md (minute par minute)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Structure des fichiers du lab

```
lab/
├── README.md                            ← ce fichier
├── 00-prerequisites.md                  ← installation host + GNS3 + ISOs
├── 01-network-setup.sh                  ← 4 bridges libvirt multi-VLAN
├── 02-vm-specs.md                       ← specs des 4 VMs pour virt-manager
├── 03-gns3-architecture.md              ← topologie GNS3 (pfSense + MikroTik)
├── RUNBOOK.md                           ← script de la démo minute-par-minute
├── topology.md                          ← diagramme ASCII de référence
├── troubleshooting.md                   ← erreurs fréquentes + fix
│
├── scripts/
│   ├── host-configure.sh                ← configure le HÔTE comme serveur SOC
│   ├── vm-cible-setup.sh                ← poste comptable Afriland (VLAN 10)
│   ├── vm-cibleB-setup.sh               ← client UBA Alpine (VLAN 20)
│   ├── vm-kali-setup.sh                 ← attaquant + C2 factice (VLAN 30)
│   └── vm-dsi-setup.sh                  ← Firefox DSI Afriland + certificats
│
└── scenarios/
    ├── 01-souverainete-check.sh         ← data residency Cameroun + tcpdump
    ├── 02-fraude-ueba.sh                ← transactions frauduleuses UEBA
    ├── 03-ransomware-soar.sh            ← chiffrement + SOAR + validation
    ├── 04-plg-otp-guide.md              ← démo PLG SaaS depuis le hôte
    └── 05-cross-tenant-isolation.sh     ← isolation VLAN + RLS (Afriland/UBA)
```

---

## 5. Timing de la démo (résumé)

| Bloc                          | Durée | Preuve produite                                    |
|-------------------------------|-------|----------------------------------------------------|
| Introduction (contexte, arch) | 4 min | Slide + topology.md (avec GNS3) affiché            |
| **Tour d'écran GNS3**         | 2 min | pfSense + MikroTik + VLANs visibles à la GUI       |
| **Scénario 4 — PLG SaaS**     | 6 min | Mail Gmail arrivé sur écran + tenant créé          |
| **Scénario 1 — Souveraineté** | 5 min | pfSense compteur "deny" incrémente en temps réel   |
| **Scénario 2 — Fraude UEBA**  | 10 min| Alerte critique + notification portail DSI + PDF   |
| **Scénario 3 — Ransomware**   | 12 min| Playbook SOAR animé + validation humaine + rollback|
| **Scénario 5 — Cross-tenant** | 4 min | nmap échoue + JWT RLS discrimine 2 tenants         |
| Questions & synthèse          | 7 min | audit_log.csv + KPIs console admin                 |
| **Total**                     | ~50 min |                                                  |

Le runbook complet (dialogues, commandes, points de bascule) est dans
**`RUNBOOK.md`**.

---

## 6. Étapes suivantes après lecture

1. Lire **`00-prerequisites.md`** : installer libvirt + GNS3, télécharger ISOs + images GNS3
2. Exécuter **`01-network-setup.sh`** : créer les 4 bridges multi-VLAN
3. Suivre **`03-gns3-architecture.md`** : monter pfSense + MikroTik dans GNS3
4. Exécuter **`scripts/host-configure.sh`** : configurer le hôte en serveur SOC
5. Suivre **`02-vm-specs.md`** : créer les 4 VMs dans virt-manager
6. Sur chaque VM, exécuter le script correspondant dans **`scripts/`**
7. Faire un snapshot `os-installed` de chaque VM
8. Lire et répéter **`RUNBOOK.md`** au moins deux fois avant la soutenance

---

## 7. En cas de blocage

Consulter **`troubleshooting.md`** — les 15 pannes les plus fréquentes (VM qui
ne boote pas, réseau isolé qui laisse fuiter, agent qui ne se connecte pas,
certificat TLS refusé, etc.) avec commande de diagnostic + fix.
