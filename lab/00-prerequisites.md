# NEXUS SOC LAB — Phase 0 : Préparation du hôte

Cette phase se fait **une seule fois** sur la machine Ubuntu qui hébergera les VMs.
Durée : ~30 minutes (dont ~20 min de téléchargement des ISOs).

---

## 1. Vérifier que la virtualisation matérielle est activée

```bash
egrep -c '(vmx|svm)' /proc/cpuinfo
```

- Résultat **`>= 1`** → VT-x (Intel) ou AMD-V activé dans le BIOS. OK.
- Résultat **`0`** → Redémarrer, aller dans le BIOS/UEFI, activer **Intel VT-x**
  ou **AMD-V**, sauvegarder, redémarrer.

```bash
# Autre vérification, plus verbeuse
kvm-ok
```

- `INFO: /dev/kvm exists` → parfait
- Sinon → installer `cpu-checker` : `sudo apt install cpu-checker`

---

## 2. Installer libvirt / virt-manager / QEMU

Une seule commande. Ubuntu 22.04 ou 24.04 :

```bash
sudo apt update
sudo apt install -y \
    qemu-kvm \
    libvirt-daemon-system \
    libvirt-clients \
    bridge-utils \
    virt-manager \
    virtinst \
    genisoimage \
    ovmf
```

Ajouter l'utilisateur aux bons groupes puis se reconnecter (indispensable
pour utiliser virt-manager sans sudo) :

```bash
sudo usermod -aG libvirt,kvm $USER
newgrp libvirt   # ou déconnexion/reconnexion complète
```

Vérifier :

```bash
virsh list --all         # doit afficher une table vide (pas d'erreur)
systemctl status libvirtd | head -5
```

---

## 3. Espace disque nécessaire

Le HÔTE est le serveur SOC (pas de VM vm-soc → pas de disque de 60 Go).

| Élément                       | Taille |
|-------------------------------|--------|
| ISO Ubuntu 22.04 Server       | 2.5 Go |
| ISO Ubuntu 22.04 Desktop      | 4.7 Go |
| ISO Kali Rolling              | 4.5 Go |
| ISO Alpine Standard           | 0.05 Go|
| Images GNS3 (pfSense+MikroTik)| 1.0 Go |
| Disque virtuel vm-cible       | 40 Go  |
| Disque virtuel vm-dsi         | 40 Go  |
| Disque virtuel vm-cibleB      | 8 Go   |
| Disque virtuel vm-kali        | 40 Go  |
| Snapshots (x1 par VM)         | ~25 Go |
| **TOTAL sur `/var/lib/libvirt/images`** | **~165 Go** |

Vérifier l'espace disponible :

```bash
df -h /var/lib/libvirt/images
```

Si moins de 180 Go, prévoir de :
- monter un SSD externe et changer le pool de stockage libvirt, OU
- réduire les disques (20 Go min pour vm-cible/vm-dsi/vm-kali)

---

## 4. Télécharger les ISOs

```bash
mkdir -p ~/nexus-lab-isos && cd ~/nexus-lab-isos

# Ubuntu 22.04 Server (pour vm-cible)
wget -c https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso

# Ubuntu 22.04 Desktop (pour vm-dsi)
wget -c https://releases.ubuntu.com/22.04/ubuntu-22.04.5-desktop-amd64.iso

# Kali Linux Rolling (pour vm-kali)
wget -c https://cdimage.kali.org/kali-2026.2/kali-linux-2026.2-installer-amd64.iso

# Alpine Linux 3.19 Standard (pour vm-cibleB — client UBA léger, ~50 Mo)
wget -c https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/x86_64/alpine-standard-3.19.1-x86_64.iso
```

Vérifier les hashs SHA256 (contre les fichiers SHA256SUMS publiés) :

```bash
sha256sum *.iso
```

### Images GNS3 (équipements réseau)

Voir `03-gns3-architecture.md §2.2` pour le détail. À télécharger séparément :

| Image                  | Source                              |
|------------------------|-------------------------------------|
| pfSense CE 2.7 (ISO)   | https://www.pfsense.org/download/   |
| MikroTik RouterOS CHR  | https://mikrotik.com/download#chr   |

---

## 5. Configuration réseau du hôte

Pas de manip particulière — libvirt gère tout. Mais **vérifier qu'aucun autre
pont réseau ne conflit** avec notre futur `10.42.0.0/24` :

```bash
ip addr | grep "10.42"
```

- Aucune sortie → OK, la plage est libre
- Une sortie → il faut changer la plage IP du lab (édite `01-network-setup.sh`)

---

## 6. Fichiers hosts sur le hôte (pour la démo)

Le HÔTE est lui-même le serveur SOC (IP lab `10.42.0.1`). Pour que Firefox
sur le hôte résolve `soc.nexus.local` vers le service local, ajouter cette
ligne à `/etc/hosts` (une seule fois) :

```bash
echo "10.42.0.1  soc.nexus.local  api.soc.nexus.local  portail.soc.nexus.local" \
    | sudo tee -a /etc/hosts
```

Vérifier :

```bash
getent hosts soc.nexus.local
# doit répondre : 10.42.0.1       soc.nexus.local api.soc.nexus.local ...
```

---

## 7. Outils annexes utiles pour la démo

```bash
# Screenshots automatiques
sudo apt install -y flameshot

# Enregistrement vidéo de la démo (pour la remise post-soutenance)
sudo apt install -y obs-studio

# tcpdump côté hôte (pour prouver zéro sortie même côté hyperviseur)
sudo apt install -y tcpdump

# jq pour analyser les JSON API dans le runbook
sudo apt install -y jq
```

---

## 8. Cloudflared côté hôte (déjà installé)

Le tunnel vers `nexussoc.cm` est déjà en place et démarre au boot.
Vérifier avant la soutenance :

```bash
systemctl is-active cloudflared
curl -s https://nexussoc.cm/health | jq
# attendu : {"status": "ok", ...}
```

Si le health échoue, redémarrer le tunnel :

```bash
sudo systemctl restart cloudflared
```

---

## 9. Checklist finale avant de passer à la Phase 1

- [ ] Virtualisation matérielle activée (`egrep -c '(vmx|svm)' /proc/cpuinfo` ≥ 1)
- [ ] `virsh list --all` répond sans erreur
- [ ] `groups | grep libvirt` — l'utilisateur est dans le groupe libvirt
- [ ] 250 Go libres sur `/var/lib/libvirt/images`
- [ ] Les 3 ISOs téléchargées et hashes vérifiés
- [ ] `/etc/hosts` contient l'entrée `soc.nexus.local`
- [ ] `curl https://nexussoc.cm/health` renvoie 200

Une fois tous cochés → passer à **`01-network-setup.sh`**.
