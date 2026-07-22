# NEXUS SOC LAB — Architecture GNS3 fusionnée (Phase 3)

Ce document décrit l'**architecture finale** du lab en fusionnant :

- **Niveau 1 GNS3** — Cage réseau visuelle avec pare-feu de bord (pfSense)
- **Niveau 2 GNS3** — Segmentation multi-tenant réaliste avec VLANs et ACL

Le **HÔTE Ubuntu** est le SOC (comme dans le lab modifié précédemment).
GNS3 s'insère **entre le hôte SOC et les VMs libvirt** pour simuler
l'infrastructure réseau réelle d'un client Afriland multi-agences.

Cette architecture unique est **la** cible finale — elle remplace les
approches "avec/sans GNS3" par une seule topologie robuste, cohérente et
pédagogiquement dense.

---

## 1. Architecture cible

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  MACHINE HÔTE Ubuntu 22.04 (32 Go RAM, SSD)                                 ║
║                                                                             ║
║  ┌──────────────────────┐  ┌───────────────────────────────────────────┐   ║
║  │ NEXUS SOC (systemd)  │  │ GNS3 Server (local)                       │   ║
║  │ • PostgreSQL         │  │                                           │   ║
║  │ • uvicorn 0.0.0.0    │  │  ┌──────────┐                             │   ║
║  │ • cloudflared        │  │  │ pfSense  │ ← pare-feu bord             │   ║
║  │ • Caddy TLS lab      │  │  │  (bord)  │   syslog+netflow → HÔTE SOC │   ║
║  │ • Wazuh Manager      │  │  │          │                             │   ║
║  └──────────┬───────────┘  │  └────┬─────┘                             │   ║
║             │              │       │ trunk 802.1Q                       │   ║
║             │              │       ▼                                    │   ║
║             │              │  ┌──────────┐                              │   ║
║             │              │  │ MikroTik │ ← routeur multi-VLAN         │   ║
║             │              │  │  Core    │   + ACL inter-tenant         │   ║
║             │              │  │  (CHR)   │                              │   ║
║             │              │  └──┬───┬─┬─┘                              │   ║
║             │              │     │   │ │                                │   ║
║             │              │  VLAN10│ VLAN20 VLAN30                     │   ║
║             │              └─────┼───┼──┼────────────────────────────────┘   ║
║             │                    │   │  │                                    ║
║             │                 [Cloud GNS3 → bridge libvirt]                  ║
║             │                    │   │  │                                    ║
║             │        ┌───────────┼─────┼─────┼─────────────────────────────┐  ║
║             │      virbr-mgmt  virbr-vlan10 virbr-vlan20  virbr-vlan30    │  ║
║             │      10.42.0.0/24 10.42.10.x  10.42.20.x    10.42.30.x       │  ║
║             │        │           │    │        │              │           │  ║
║             │     [HÔTE]     ┌────┴┐ ┌─┴──┐ ┌───┴────┐    ┌────┴───┐      │  ║
║             └─►  10.42.0.1   │cible│ │dsi │ │cibleB  │    │ kali   │      │  ║
║                              │.10.20│ │.10.40│ │.20.20 │    │ .30.30 │      │  ║
║                              └─────┘ └────┘ └────────┘    └────────┘      │  ║
║                              ══ Afriland ══   ══ UBA ══     ══ externe ══   │  ║
║                              (VLAN 10)        (VLAN 20)     (VLAN 30)       │  ║
║                              poste + DSI      Alpine 2Go    attaquant       │  ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

### Rôles

| Composant       | Rôle                                                             |
|-----------------|------------------------------------------------------------------|
| **HÔTE (SOC)**  | Le serveur NEXUS SOC. IP `10.42.0.1` sur `virbr-mgmt`, receveur syslog/netflow. |
| **pfSense**     | Pare-feu de bord. Interface WAN (désactivable pour la démo souveraineté). Interface LAN vers routeur core. |
| **MikroTik CHR** | Routeur inter-VLAN. Applique les **ACL strictes** entre tenants + route vers le SOC. |
| **VLAN 10 (Afriland)** | Tenant client principal. Contient `vm-cible` (poste comptable) et `vm-dsi` (poste du DSI). |
| **VLAN 20 (UBA)** | Tenant client secondaire. Contient `vm-cibleB` (Alpine léger), prouve l'isolation cross-tenant. |
| **VLAN 30 (external)** | Segment "hostile" simulant un réseau externe compromis. Contient `vm-kali`. |

### Ressources totales

| Élément            | RAM    | Notes                                    |
|--------------------|--------|------------------------------------------|
| pfSense (GNS3)     | 1 Go   | Image ISO CE, minimal                    |
| MikroTik CHR (GNS3)| 512 Mo | Image gratuite jusqu'à 1 Mbps            |
| vm-cible           | 4 Go   | Ubuntu Server (Afriland)                 |
| vm-dsi             | 2 Go   | Ubuntu Desktop (Afriland DSI)            |
| vm-cibleB          | 2 Go   | Alpine Linux (UBA)                       |
| vm-kali            | 4 Go   | Kali Rolling (attaquant)                 |
| Hôte OS + GNS3 GUI | ~10 Go | Firefox, terminaux, OBS                  |
| **TOTAL**          | **~23 Go** | reste ~9 Go de marge sur 32 Go        |

---

## 2. Prérequis

### 2.1 Installer GNS3

```bash
sudo add-apt-repository -y ppa:gns3/ppa
sudo apt update
sudo apt install -y gns3-gui gns3-server ubridge dynamips
sudo usermod -aG ubridge,libvirt,kvm $USER
# Reconnexion requise pour les groupes
```

### 2.2 Télécharger les images d'équipements

| Image                     | Source                                           | Taille |
|---------------------------|--------------------------------------------------|--------|
| pfSense CE 2.7            | https://www.pfsense.org/download/                | 800 Mo |
| MikroTik RouterOS CHR     | https://mikrotik.com/download                     | 100 Mo |

Copier dans `~/GNS3/images/QEMU/`.

### 2.3 Créer les bridges libvirt supplémentaires

L'ancien script `01-network-setup.sh` créait un seul réseau `nexus-lab`.
La nouvelle architecture en demande **4** :

- `nexus-mgmt` — 10.42.0.0/24 (hôte SOC ↔ GNS3)
- `nexus-vlan10` — 10.42.10.0/24 (VLAN Afriland)
- `nexus-vlan20` — 10.42.20.0/24 (VLAN UBA)
- `nexus-vlan30` — 10.42.30.0/24 (VLAN attaquant externe)

Le script **`01-network-setup.sh`** (déjà à jour) crée ces 4 réseaux :

```bash
./01-network-setup.sh            # crée les 4 bridges
./01-network-setup.sh --status   # vérifie
```

---

## 3. Construction de la topologie GNS3 (étape par étape)

### 3.1 Démarrer GNS3 et créer le projet

```bash
gns3 &
```

- Fichier → Nouveau projet → **`NEXUS-SOC-Lab`**
- Emplacement : `~/GNS3/projects/nexus-soc-lab/`

### 3.2 Ajouter pfSense

- Panneau gauche → **Firewall** → glisser **pfSense CE** dans la scène
- Nom : `pfSense-Bord`
- Interfaces : 2 (WAN + LAN)
- Console : Telnet

### 3.3 Ajouter MikroTik CHR

- Panneau gauche → **Router** → glisser **MikroTik CHR** dans la scène
- Nom : `Router-Core`
- Interfaces : 5
  - `ether1` : trunk vers pfSense
  - `ether2` : VLAN 10 (Afriland)
  - `ether3` : VLAN 20 (UBA)
  - `ether4` : VLAN 30 (external)
  - `ether5` : mgmt vers HÔTE SOC

### 3.4 Ajouter les nodes Cloud (pont vers libvirt)

**C'est la partie clé.** Chaque VLAN a son propre bridge libvirt.

Pour chaque bridge (`nexus-mgmt`, `nexus-vlan10`, `nexus-vlan20`, `nexus-vlan30`) :

1. Panneau gauche → **End Devices** → glisser **Cloud** dans la scène
2. Renommer selon le bridge (ex: `Cloud-MGMT`, `Cloud-VLAN10`, …)
3. Clic-droit → **Configure**
4. Onglet **Ethernet interfaces** → cocher le bridge libvirt correspondant
5. OK

### 3.5 Câbler

Utiliser l'outil **Add a link** de GNS3 :

- `Cloud-MGMT` ─── `pfSense-Bord.WAN`
- `pfSense-Bord.LAN` ─── `Router-Core.ether1` (trunk)
- `Router-Core.ether2` ─── `Cloud-VLAN10`
- `Router-Core.ether3` ─── `Cloud-VLAN20`
- `Router-Core.ether4` ─── `Cloud-VLAN30`
- `Router-Core.ether5` ─── `Cloud-MGMT` (route directe SOC)

### 3.6 Démarrer les équipements

Clic-droit sur chaque appliance → **Start**.

Attendre le boot pfSense (~2 min) puis MikroTik (~30 s).

---

## 4. Configuration pfSense (~10 min)

Console GNS3 sur pfSense (clic-droit → Console).

### 4.1 Interfaces

- **WAN (em0)** : DHCP client (récupère IP sur `nexus-mgmt` → 10.42.0.100+)
- **LAN (em1)** : static `192.168.100.1/24` (côté routeur core)

### 4.2 Règles firewall

Firewall → Rules → LAN :

| Source                  | Destination        | Port    | Action | Description                       |
|-------------------------|-------------------|---------|--------|-----------------------------------|
| LAN net                 | HÔTE (10.42.0.1)  | 8000, 8443, 514 | PASS | SOC traffic |
| any VLAN                | any other VLAN    | any     | BLOCK | Isolation inter-tenant |
| LAN net                 | !LAN net + !10.42.0.0/24 | any | BLOCK | No Internet |
| any                     | any               | any     | DEFAULT DENY | |

### 4.3 Syslog → HÔTE

System → Advanced → Logging :
- ✓ Enable Remote Syslog
- Remote Syslog Server : `10.42.0.1:514`
- Log everything : ✓

Le HÔTE reçoit désormais tous les logs de pfSense (dans Wazuh Manager).

---

## 5. Configuration MikroTik Router-Core (~15 min)

Console GNS3 sur MikroTik, login `admin` / (pas de mdp au premier boot).

### 5.1 VLANs et sous-réseaux

```
/interface bridge add name=bridge-vlan10
/interface bridge add name=bridge-vlan20
/interface bridge add name=bridge-vlan30

/ip address add address=192.168.100.2/24 interface=ether1 comment="uplink pfSense"
/ip address add address=10.42.10.1/24 interface=ether2 comment="VLAN10 Afriland"
/ip address add address=10.42.20.1/24 interface=ether3 comment="VLAN20 Afriland"
/ip address add address=10.42.30.1/24 interface=ether4 comment="VLAN30 external"
/ip address add address=10.42.0.2/24 interface=ether5 comment="mgmt vers SOC"

/ip route add dst-address=0.0.0.0/0 gateway=192.168.100.1
```

### 5.2 ACL — isolation inter-tenant (LA règle-clé)

```
/ip firewall filter add chain=forward src-address=10.42.10.0/24 dst-address=10.42.20.0/24 action=drop \
    comment="Bloque Afriland -> Afriland"
/ip firewall filter add chain=forward src-address=10.42.20.0/24 dst-address=10.42.10.0/24 action=drop
/ip firewall filter add chain=forward src-address=10.42.30.0/24 dst-address=10.42.10.0/24 action=drop \
    comment="Bloque attaquant externe -> Afriland"
/ip firewall filter add chain=forward src-address=10.42.30.0/24 dst-address=10.42.20.0/24 action=drop

# Autoriser tous les tenants à joindre le HÔTE SOC pour envoyer leur télémétrie
/ip firewall filter add chain=forward dst-address=10.42.0.1 action=accept

# Netflow export vers le SOC
/ip traffic-flow set enabled=yes
/ip traffic-flow target add address=10.42.0.1 port=2055 version=9
```

### 5.3 Log SSH tentative

Ajoute une règle de logging pour que Wazuh remonte les tentatives d'accès.

```
/system logging action set 3 remote=10.42.0.1
/system logging add topics=info,firewall action=remote
```

---

## 6. Configuration côté HÔTE (Wazuh)

Sur le hôte, activer la réception syslog + Netflow :

```bash
# Écoute syslog sur port 514 UDP
sudo sed -i 's/#module(load="imudp")/module(load="imudp")/' /etc/rsyslog.conf
sudo sed -i 's/#input(type="imudp" port="514")/input(type="imudp" port="514")/' /etc/rsyslog.conf

# Redirection des logs pfSense/MikroTik vers un fichier dédié
sudo tee /etc/rsyslog.d/10-nexus-lab.conf <<'RSYS'
if $fromhost-ip startswith '10.42.' then /var/log/nexus-lab.log
& stop
RSYS

sudo systemctl restart rsyslog

# Vérifier
sudo tail -f /var/log/nexus-lab.log    # doit afficher les événements pfSense
```

Ajouter le fichier dans la config Wazuh Manager (si installé) :

```yaml
<localfile>
    <log_format>syslog</log_format>
    <location>/var/log/nexus-lab.log</location>
</localfile>
```

---

## 7. Vérifier que les VMs sont sur les bons VLANs

Les VMs sont créées **directement** sur leur bridge VLAN (voir `02-vm-specs.md`),
donc normalement rien à rebrancher. Cette section sert à **vérifier** ou à
**corriger** si une VM a été créée sur le mauvais réseau.

Vérification :

```bash
for vm in vm-cible vm-dsi vm-cibleB vm-kali; do
    echo -n "$vm → "
    virsh dumpxml "$vm" | grep -oP "source network='\K[^']+"
done
# attendu :
#   vm-cible  → nexus-vlan10
#   vm-dsi    → nexus-vlan10
#   vm-cibleB → nexus-vlan20
#   vm-kali   → nexus-vlan30
```

Correction (uniquement si une VM est sur le mauvais réseau) — exemple vm-cible :

```bash
virsh detach-interface vm-cible network --mac 52:54:00:aa:00:20 --config --live
virsh attach-interface vm-cible network nexus-vlan10 \
    --mac 52:54:00:aa:00:20 --model virtio --config --live
virsh reboot vm-cible
```

IP attendue par VM après boot :
- `vm-cible`  : `10.42.10.20`   (VLAN 10 Afriland)
- `vm-dsi`    : `10.42.10.40`   (VLAN 10 Afriland)
- `vm-cibleB` : `10.42.20.20`   (VLAN 20 UBA)
- `vm-kali`   : `10.42.30.30`   (VLAN 30 external)

---

## 8. Ce que ça permet de démontrer en plus

### Bloc GNS3 dans la démo (2 min de plus dans le RUNBOOK)

Avant le scénario 1, projeter GNS3 pendant 90 secondes :
- Ouvrir la topologie
- Montrer les VLANs colorés
- Montrer les règles firewall pfSense
- Montrer l'ACL MikroTik

**Effet jury :** on passe d'un lab "amateur" à une topologie réseau
digne d'un Bachelor RSI. C'est **le** signal que tu maîtrises l'infra.

### Nouveaux scénarios possibles

1. **Cross-tenant isolation** (nouveau scénario 5) : depuis vm-kali (VLAN30),
   tenter de scanner vm-cible (VLAN10) → nmap échoue à cause de l'ACL MikroTik.

2. **Réception syslog en direct** : pendant le scénario 3 (ransomware),
   afficher `tail -f /var/log/nexus-lab.log` sur le hôte. Les paquets
   bloqués par pfSense apparaissent en temps réel.

3. **NetFlow → Modèle 1** : les flux export depuis MikroTik nourrissent
   directement le Modèle 1 (anomalie réseau) — plus besoin d'inventer
   des JSON de flow.

---

## 9. Récapitulatif des changements par rapport au lab initial

| Élément                     | Avant                          | Après                             |
|----------------------------|--------------------------------|-----------------------------------|
| vm-soc                     | VM Ubuntu 8 Go                 | **HÔTE** (déjà en systemd)        |
| Réseau                     | 1 bridge libvirt plat          | **4 bridges** + pfSense + MikroTik|
| Isolation                  | Applicative (RLS PostgreSQL)   | **Applicative + réseau (VLAN+ACL)**|
| Logs équipements réseau    | Aucun                          | **Syslog pfSense + MikroTik**     |
| Flux réseau réels          | Simulés en JSON                | **NetFlow v9 exporté**            |
| Scénarios démontrables     | 4                              | **5** (ajout cross-tenant)        |
| Temps de setup total       | ~2h30                          | ~3h30 (+ 1h pour GNS3)            |
| Effet jury                 | Bon                            | **Très bon** (crédibilité infra)  |

---

## 10. Suite

- Lire **`topology.md`** pour le nouveau schéma de référence (à projeter au jury)
- Lire **`scenarios/05-cross-tenant-isolation.sh`** pour le nouveau scénario
- Lire **`RUNBOOK.md`** section « Bloc GNS3 » pour l'intégration dans la démo
