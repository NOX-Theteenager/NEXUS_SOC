# NEXUS SOC LAB — Phase 2 : Création des 4 VMs dans virt-manager

Après avoir créé le réseau `nexus-lab` (Phase 1), il faut créer les 4 VMs.
Le mode graphique de **virt-manager** est le plus simple ; la CLI `virt-install`
est fournie en Annexe A pour ceux qui préfèrent le scripter.

**Temps prévu : ~1h** (15 min de création + attente install OS pour chaque VM).

---

## 1. vm-soc — Serveur NEXUS SOC

Le cœur du lab. Doit accueillir PostgreSQL, Kafka, Wazuh, uvicorn.

### Spécifications

| Paramètre       | Valeur                                            |
|-----------------|---------------------------------------------------|
| Nom             | `vm-soc`                                          |
| ISO             | `ubuntu-22.04.5-live-server-amd64.iso`            |
| RAM             | **8 192 Mo** (8 Go)                               |
| vCPU            | **4**                                             |
| Disque          | **60 Gio** (qcow2, allocation dynamique)          |
| Réseau          | `nexus-lab` (source de type Virtual network)      |
| MAC             | `52:54:00:aa:00:10` (**forcer**, sinon pas d'IP fixe) |
| Firmware        | UEFI (recommandé) ou BIOS SeaBIOS                 |
| Vidéo           | Virtio ou QXL                                     |

### Étapes dans virt-manager

1. **Fichier → Nouvelle machine virtuelle**
2. Type : **Média d'installation local (ISO ou image CD/DVD)** → Suivant
3. Sélectionner l'ISO Ubuntu Server 22.04 → Suivant
4. Mémoire : **8192**, CPU : **4** → Suivant
5. Disque : **60 Gio** → Suivant
6. Nom : `vm-soc`
7. **Cocher « Personnaliser la configuration avant l'installation »** → Terminer
8. Dans la fenêtre de personnalisation :
   - Onglet **NIC** → Réseau source : **`nexus-lab`**
   - **Adresse MAC : `52:54:00:aa:00:10`** (à saisir manuellement)
   - Onglet **Options du processeur** → cocher « Copier la config CPU du hôte »
9. **Commencer l'installation**

### Installation Ubuntu Server 22.04

Choisir tous les défauts, SAUF :

| Écran                        | Choix                                          |
|------------------------------|------------------------------------------------|
| Langue                       | Français ou Anglais (au choix)                 |
| Réseau                       | Doit détecter DHCP → afficher `10.42.0.10/24` |
| Miroir                       | Défaut Ubuntu                                  |
| Stockage                     | Utiliser tout le disque (LVM ou pas, indifférent) |
| Profil                       | Nom : `NGUETSA`, hôte : **`vm-soc`**, user : **`nexus`**, mdp : **`nexus`** |
| SSH                          | **Cocher : Installer OpenSSH server**          |
| Snaps                        | **NE RIEN cocher** (allège la VM)              |

Après reboot, se connecter en console (`nexus`/`nexus`) et vérifier :

```bash
ip a | grep 10.42          # doit afficher 10.42.0.10/24
```

Passer ensuite à `scripts/vm-soc-setup.sh` (voir README).

---

## 2. vm-cible — Poste comptable simulé

Une station de travail qui envoie de la télémétrie normale, puis anormale.

### Spécifications

| Paramètre  | Valeur                                        |
|------------|-----------------------------------------------|
| Nom        | `vm-cible`                                    |
| ISO        | `ubuntu-22.04.5-live-server-amd64.iso`        |
| RAM        | **4 096 Mo** (4 Go)                           |
| vCPU       | **2**                                         |
| Disque     | **40 Gio**                                    |
| Réseau     | `nexus-lab`                                   |
| MAC        | `52:54:00:aa:00:20`                           |

### Installation

Idem vm-soc, sauf :
- Hôte : **`vm-cible`**, user : **`compta`**, mdp : **`compta`**
- Après reboot : `ip a` doit afficher `10.42.0.20`

---

## 3. vm-kali — Poste attaquant externe

Kali Rolling pour lancer les attaques réseau du scénario ransomware.

### Spécifications

| Paramètre  | Valeur                                        |
|------------|-----------------------------------------------|
| Nom        | `vm-kali`                                     |
| ISO        | `kali-linux-2026.2-installer-amd64.iso`       |
| RAM        | **4 096 Mo**                                  |
| vCPU       | **2**                                         |
| Disque     | **40 Gio**                                    |
| Réseau     | `nexus-lab`                                   |
| MAC        | `52:54:00:aa:00:30`                           |

### Installation Kali

Installation classique Kali, choisir :
- Type : Graphical install
- Hôte : **`vm-kali`**
- User : **`kali`**, mdp : **`kali`**
- Environnement bureau : XFCE (léger)
- Sélection outils : **default** (nmap, hydra, etc. inclus)

Après reboot : `ip a` → `10.42.0.30`.

---

## 4. vm-dsi — Poste du DSI

Ubuntu Desktop pour lancer Firefox et consulter le portail.

### Spécifications

| Paramètre  | Valeur                                        |
|------------|-----------------------------------------------|
| Nom        | `vm-dsi`                                      |
| ISO        | `ubuntu-22.04.5-desktop-amd64.iso`            |
| RAM        | **2 048 Mo**                                  |
| vCPU       | **2**                                         |
| Disque     | **40 Gio**                                    |
| Réseau     | `nexus-lab`                                   |
| MAC        | `52:54:00:aa:00:40`                           |

### Installation Ubuntu Desktop

- Type d'installation : **Minimale** (juste Firefox et terminal)
- Hôte : **`vm-dsi`**, user : **`dsi`**, mdp : **`dsi`**
- Après reboot : `ip a` → `10.42.0.40`

---

## 5. Vérification finale de la topologie

Depuis le hôte :

```bash
virsh net-dhcp-leases nexus-lab
```

Sortie attendue (les 4 VMs doivent apparaître) :

```
 Expiry Time           MAC address         Protocol   IP address        Hostname   Client ID
------------------------------------------------------------------------------------------------
 2026-07-02 20:00:00   52:54:00:aa:00:10   ipv4       10.42.0.10/24     vm-soc     -
 2026-07-02 20:00:00   52:54:00:aa:00:20   ipv4       10.42.0.20/24     vm-cible   -
 2026-07-02 20:00:00   52:54:00:aa:00:30   ipv4       10.42.0.30/24     vm-kali    -
 2026-07-02 20:00:00   52:54:00:aa:00:40   ipv4       10.42.0.40/24     vm-dsi     -
```

Tester la connectivité inter-VMs (depuis vm-cible) :

```bash
ping -c 3 10.42.0.10       # vers vm-soc → doit répondre
ping -c 3 10.42.0.30       # vers vm-kali → doit répondre
ping -c 3 8.8.8.8          # vers Internet → doit TIMEOUT (isolation OK)
```

Si le dernier ping RÉUSSIT → le réseau n'est pas isolé, relancer
`01-network-setup.sh --destroy` puis `01-network-setup.sh`.

---

## 6. Snapshots baseline

Une fois les 4 VMs installées et connectivité vérifiée, faire un snapshot
de chacune AVANT d'installer NEXUS SOC :

```bash
for vm in vm-soc vm-cible vm-kali vm-dsi; do
    virsh snapshot-create-as "$vm" "os-installed" \
        "OS installé, avant NEXUS SOC — $(date -I)"
done

virsh snapshot-list vm-soc      # vérification
```

**Ce snapshot est un filet de sécurité** : si une des installations post-OS
casse quelque chose, on peut y revenir en 30 secondes :

```bash
virsh snapshot-revert vm-soc os-installed
```

---

## Annexe A — Créer les VMs en CLI (bonus pour aller vite)

Alternative à virt-manager, si tu es à l'aise avec la ligne de commande.
Une seule commande par VM.

```bash
ISO_DIR=~/nexus-lab-isos
POOL=/var/lib/libvirt/images

virt-install \
    --name vm-soc --memory 8192 --vcpus 4 \
    --disk path=$POOL/vm-soc.qcow2,size=60,format=qcow2 \
    --network network=nexus-lab,mac=52:54:00:aa:00:10 \
    --os-variant ubuntu22.04 \
    --cdrom $ISO_DIR/ubuntu-22.04.5-live-server-amd64.iso \
    --graphics vnc,listen=127.0.0.1 --console pty,target_type=serial \
    --noautoconsole
```

(idem pour les 3 autres VMs en adaptant nom, RAM, vCPU, MAC, ISO).

---

## Étapes suivantes

Une fois les 4 VMs installées et pingables → passer à la phase 3 :
- vm-soc    → `scripts/vm-soc-setup.sh`
- vm-cible  → `scripts/vm-cible-setup.sh`
- vm-kali   → `scripts/vm-kali-setup.sh`
- vm-dsi    → `scripts/vm-dsi-setup.sh`
