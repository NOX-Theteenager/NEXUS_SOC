# NEXUS SOC LAB — Phase 2 : Création des 4 VMs dans virt-manager

Après avoir créé les **4 bridges libvirt** (Phase 1, `01-network-setup.sh`)
et configuré le **HÔTE** comme serveur SOC (via `scripts/host-configure.sh`),
créer **4 VMs** :

- `vm-cible`  → Client Afriland — poste comptable (VLAN 10)
- `vm-dsi`    → Client Afriland — poste du DSI (VLAN 10)
- `vm-cibleB` → Client UBA — Alpine Linux léger (VLAN 20) — isolation
- `vm-kali`   → Attaquant externe (VLAN 30) (Firefox)

Le rôle « vm-soc » du lab original est joué directement par le **HÔTE**
qui a déjà PostgreSQL, uvicorn (nexus-soc.service) et cloudflared en
systemd. C'est un gain de **8 Go de RAM** et de temps de setup.

**Temps prévu : ~45 min** (15 min par VM).

---

## 0. Le HÔTE (rappel — pas une VM à créer)

Le hôte a déjà :

| Composant         | État                                             |
|-------------------|--------------------------------------------------|
| PostgreSQL/Timescale | Container Docker (via nexus-postgres.service)  |
| uvicorn NEXUS SOC | systemd `nexus-soc.service`, écoute `0.0.0.0:8000` |
| cloudflared       | systemd `cloudflared.service` → nexussoc.cm      |
| Caddy TLS lab     | Ajouté par `host-configure.sh`, port 8443       |
| IP sur virbr-lab  | `10.42.0.1` (gateway libvirt)                    |

**Après `01-network-setup.sh` :** exécuter `scripts/host-configure.sh` **avant**
de créer les VMs.

---

## 1. vm-cible — Poste comptable Afriland (VLAN 10)

Une station de travail qui envoie de la télémétrie normale, puis anormale.

### Spécifications

| Paramètre  | Valeur                                        |
|------------|-----------------------------------------------|
| Nom        | `vm-cible`                                    |
| ISO        | `ubuntu-22.04.5-live-server-amd64.iso`        |
| RAM        | **4 096 Mo** (4 Go)                           |
| vCPU       | **2**                                         |
| Disque     | **40 Gio**                                    |
| Réseau     | **`nexus-vlan10`** (VLAN 10 Afriland)         |
| MAC        | `52:54:00:aa:00:20`                           |

### Étapes dans virt-manager

1. **Fichier → Nouvelle machine virtuelle**
2. Type : **Média d'installation local (ISO)** → Suivant
3. Sélectionner l'ISO Ubuntu Server 22.04
4. Mémoire : **4096**, CPU : **2**
5. Disque : **40 Gio**
6. Nom : `vm-cible`
7. **Cocher « Personnaliser avant l'installation »** → Terminer
8. Onglet **NIC** → Réseau **`nexus-vlan10`** + **MAC `52:54:00:aa:00:20`**
9. Commencer l'installation

### Installation Ubuntu Server 22.04

| Écran     | Choix                                                   |
|-----------|---------------------------------------------------------|
| Langue    | Français ou Anglais                                     |
| Réseau    | DHCP → doit afficher `10.42.10.20/24` (VLAN 10)         |
| Profil    | Hôte : **`vm-cible`**, user : **`compta`**, mdp : **`compta`** |
| SSH       | **Cocher : Installer OpenSSH server**                   |
| Snaps     | Ne rien cocher                                          |

Après reboot :

```bash
ip a | grep 10.42    # doit afficher 10.42.10.20/24
```

---

## 2. vm-cibleB — Client UBA (Alpine Linux léger)

VM ultra-légère (2 Go RAM, 8 Go disque) qui représente le **client UBA**
(Cameroun Microfinance). Sert exclusivement à rendre l'isolation VLAN
tangible dans virt-manager et le scénario 5. Alpine est choisi car
l'ISO ne pèse que 50 Mo et l'install prend 5 min.

### Spécifications

| Paramètre  | Valeur                                        |
|------------|-----------------------------------------------|
| Nom        | `vm-cibleB`                                   |
| ISO        | `alpine-standard-3.19.1-x86_64.iso` (~50 Mo)  |
| RAM        | **2 048 Mo** (2 Go)                           |
| vCPU       | **1** (suffisant pour Alpine)                 |
| Disque     | **8 Gio**                                     |
| Réseau     | **`nexus-vlan20`** (VLAN 20 UBA)              |
| MAC        | `52:54:00:aa:00:50`                           |

### Installation Alpine (~5 min)

1. Booter sur l'ISO → login `root` (pas de mdp)
2. `setup-alpine` → suivre le wizard :
   - Keymap : `fr fr` (ou `us us`)
   - Hostname : **`vm-cibleB`**
   - Interface : `eth0` → DHCP (doit afficher `10.42.20.20`)
   - Root password : `alpine`
   - Timezone : `Africa/Douala`
   - Proxy : `none`
   - Mirror : `1` (premier disponible)
   - User : `uba` / password : `uba`
   - SSH : `openssh` (activer)
   - NTP : `chrony`
   - Disk : `sda`, mode `sys`, format ext4
3. `reboot` → retirer l'ISO
4. Depuis le hôte : `scp lab/scripts/vm-cibleB-setup.sh root@10.42.20.20:/tmp/`
5. Sur vm-cibleB : `sh /tmp/vm-cibleB-setup.sh`

Après reboot : `ip a | grep 10.42` → `10.42.20.20/24`

---

## 3. vm-kali — Poste attaquant externe

Kali Rolling pour lancer les attaques réseau du scénario ransomware et
le scénario 5 (isolation cross-tenant).

### Spécifications

| Paramètre  | Valeur                                        |
|------------|-----------------------------------------------|
| Nom        | `vm-kali`                                     |
| ISO        | `kali-linux-2026.2-installer-amd64.iso`       |
| RAM        | **4 096 Mo**                                  |
| vCPU       | **2**                                         |
| Disque     | **40 Gio**                                    |
| Réseau     | **`nexus-vlan30`** (VLAN 30 external)         |
| MAC        | `52:54:00:aa:00:30`                           |

### Installation Kali

Installation classique Kali, choisir :
- Type : Graphical install
- Hôte : **`vm-kali`**
- User : **`kali`**, mdp : **`kali`**
- Environnement bureau : XFCE (léger)
- Sélection outils : **default** (nmap, hydra, etc. inclus)

Après reboot : `ip a` → `10.42.30.30`.

---

## 4. vm-dsi — Poste du DSI Afriland

Ubuntu Desktop pour lancer Firefox et consulter le portail (côté Afriland).

### Spécifications

| Paramètre  | Valeur                                        |
|------------|-----------------------------------------------|
| Nom        | `vm-dsi`                                      |
| ISO        | `ubuntu-22.04.5-desktop-amd64.iso`            |
| RAM        | **2 048 Mo**                                  |
| vCPU       | **2**                                         |
| Disque     | **40 Gio**                                    |
| Réseau     | **`nexus-vlan10`** (VLAN 10 Afriland)         |
| MAC        | `52:54:00:aa:00:40`                           |

### Installation Ubuntu Desktop

- Type d'installation : **Minimale** (juste Firefox et terminal)
- Hôte : **`vm-dsi`**, user : **`dsi`**, mdp : **`dsi`**
- Après reboot : `ip a` → `10.42.10.40`

---

## 4. Vérification finale de la topologie

Depuis le hôte, chaque VM apparaît dans les baux de SON réseau VLAN :

```bash
virsh net-dhcp-leases nexus-vlan10    # vm-cible + vm-dsi
virsh net-dhcp-leases nexus-vlan20    # vm-cibleB
virsh net-dhcp-leases nexus-vlan30    # vm-kali
```

Sortie attendue (agrégée) :

```
 MAC address         IP address        Hostname     Réseau
--------------------------------------------------------------
 52:54:00:aa:00:20   10.42.10.20/24    vm-cible     nexus-vlan10
 52:54:00:aa:00:40   10.42.10.40/24    vm-dsi       nexus-vlan10
 52:54:00:aa:00:50   10.42.20.20/24    vm-cibleB    nexus-vlan20
 52:54:00:aa:00:30   10.42.30.30/24    vm-kali      nexus-vlan30

Note : le HÔTE est à 10.42.0.1 (gateway virbr-mgmt) et ne passe pas
par DHCP, donc n'apparaît pas dans les baux.
```

> **Important** : tant que la topologie GNS3 (pfSense + MikroTik) n'est pas
> montée et configurée (voir `03-gns3-architecture.md`), les VLANs ne sont
> PAS routés entre eux ni vers le hôte. Les tests ci-dessous supposent GNS3
> actif.

Tester la connectivité depuis vm-cible (VLAN 10) :

```bash
ping -c 3 10.42.0.1        # vers le HÔTE SOC (via MikroTik) → doit répondre
ping -c 3 10.42.30.30      # vers vm-kali (VLAN 30) → doit ÉCHOUER (ACL isolation)
ping -c 3 8.8.8.8          # vers Internet → doit TIMEOUT (pfSense bloque)

# Test HTTP direct vers le SOC hôte
curl -s http://10.42.0.1:8000/health
# doit renvoyer : {"status":"ok",...}

# Test HTTPS via Caddy sur le hôte
curl -sk https://10.42.0.1:8443/health
# doit renvoyer aussi : {"status":"ok",...}
```

Si le curl 10.42.0.1:8000 échoue → soit le routage MikroTik VLAN10→mgmt
n'est pas configuré, soit ufw bloque virbr-mgmt.
Fix : relancer `scripts/host-configure.sh` + vérifier l'ACL MikroTik.

---

## 5. Snapshots baseline

Une fois les **4 VMs** installées et connectivité vérifiée, faire un snapshot
de chacune AVANT d'appliquer les scripts NEXUS SOC :

```bash
for vm in vm-cible vm-dsi vm-cibleB vm-kali; do
    virsh snapshot-create-as "$vm" "os-installed" \
        "OS installé, avant NEXUS SOC — $(date -I)"
done

virsh snapshot-list vm-cible    # vérification
```

**Ce snapshot est un filet de sécurité** : si une des installations post-OS
casse quelque chose, on peut y revenir en 30 secondes :

```bash
virsh snapshot-revert vm-cible os-installed
```

---

## Annexe A — Créer les VMs en CLI (bonus pour aller vite)

Alternative à virt-manager, si tu es à l'aise avec la ligne de commande.
Adapter `--network` au bon VLAN et la `mac` à la réservation.

```bash
ISO_DIR=~/nexus-lab-isos
POOL=/var/lib/libvirt/images

# vm-cible (Afriland, VLAN 10)
virt-install \
    --name vm-cible --memory 4096 --vcpus 2 \
    --disk path=$POOL/vm-cible.qcow2,size=40,format=qcow2 \
    --network network=nexus-vlan10,mac=52:54:00:aa:00:20 \
    --os-variant ubuntu22.04 \
    --cdrom $ISO_DIR/ubuntu-22.04.5-live-server-amd64.iso \
    --graphics vnc,listen=127.0.0.1 --console pty,target_type=serial \
    --noautoconsole
```

Pour les autres :
| VM        | réseau         | mac                 | RAM  | vCPU | disque | ISO           |
|-----------|----------------|---------------------|------|------|--------|---------------|
| vm-dsi    | nexus-vlan10   | 52:54:00:aa:00:40   | 2048 | 2    | 40     | ubuntu desktop|
| vm-cibleB | nexus-vlan20   | 52:54:00:aa:00:50   | 2048 | 1    | 8      | alpine        |
| vm-kali   | nexus-vlan30   | 52:54:00:aa:00:30   | 4096 | 2    | 40     | kali          |

---

## Étapes suivantes

Une fois les 4 VMs installées et pingables → appliquer les scripts de setup.
Transférer chaque script sur sa VM (ex. `scp lab/scripts/vm-cible-setup.sh
compta@10.42.10.20:/tmp/`) puis l'exécuter :

- vm-cible  → `scripts/vm-cible-setup.sh`   (Afriland, VLAN 10)
- vm-dsi    → `scripts/vm-dsi-setup.sh`     (Afriland DSI, VLAN 10)
- vm-cibleB → `scripts/vm-cibleB-setup.sh`  (UBA, VLAN 20 — Alpine)
- vm-kali   → `scripts/vm-kali-setup.sh`    (attaquant, VLAN 30)

Le HÔTE, lui, a déjà été configuré à la phase 3 via `scripts/host-configure.sh`.
