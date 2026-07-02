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

| Élément                    | Taille |
|----------------------------|--------|
| ISO Ubuntu 22.04 Server    | 2.5 Go |
| ISO Ubuntu 22.04 Desktop   | 4.7 Go |
| ISO Kali Rolling           | 4.5 Go |
| Disque virtuel vm-soc      | 60 Go  |
| Disque virtuel vm-cible    | 40 Go  |
| Disque virtuel vm-kali     | 40 Go  |
| Disque virtuel vm-dsi      | 40 Go  |
| Snapshots (x2 par VM)      | ~40 Go |
| **TOTAL sur `/var/lib/libvirt/images`** | **~240 Go** |

Vérifier l'espace disponible :

```bash
df -h /var/lib/libvirt/images
```

Si moins de 250 Go, prévoir de :
- monter un SSD externe et changer le pool de stockage libvirt, OU
- réduire les disques (30 Go min pour vm-soc, 20 Go pour les autres)

---

## 4. Télécharger les ISOs

```bash
mkdir -p ~/nexus-lab-isos && cd ~/nexus-lab-isos

# Ubuntu 22.04 Server (pour vm-soc, vm-cible)
wget -c https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso

# Ubuntu 22.04 Desktop (pour vm-dsi)
wget -c https://releases.ubuntu.com/22.04/ubuntu-22.04.5-desktop-amd64.iso

# Kali Linux Rolling (pour vm-kali)
wget -c https://cdimage.kali.org/kali-2026.2/kali-linux-2026.2-installer-amd64.iso
```

Vérifier les hashs SHA256 (contre les fichiers SHA256SUMS publiés) :

```bash
sha256sum *.iso
```

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

Pour que le navigateur du hôte puisse accéder au portail DSI de vm-soc via
le nom `soc.minfi.local` (pas juste par IP), ajouter cette ligne à
`/etc/hosts` (une seule fois) :

```bash
echo "10.42.0.10  soc.minfi.local  api.soc.minfi.local  portail.soc.minfi.local" \
    | sudo tee -a /etc/hosts
```

Vérifier :

```bash
getent hosts soc.minfi.local
# doit répondre : 10.42.0.10       soc.minfi.local api.soc.minfi.local ...
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
- [ ] `/etc/hosts` contient l'entrée `soc.minfi.local`
- [ ] `curl https://nexussoc.cm/health` renvoie 200

Une fois tous cochés → passer à **`01-network-setup.sh`**.
