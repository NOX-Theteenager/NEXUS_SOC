# CENADI — Architecture souveraine détaillée

Adressage, zones, flux autorisés et topologie du déploiement souverain.

> **État au 17 août 2026.** Ce document décrit l'architecture **cible**. Ce qui
> tourne aujourd'hui est un réseau libvirt à plat (`192.168.122.0/24`), sans
> pare-feu ni segmentation. La phase 1 du
> [plan de réponse collaborative](../00_Documents/Decision_Reponse_Collaborative.md)
> déploie ce qui suit. Toute figure tirée de ce document porte la mention
> « architecture cible ».

---

## 1. Plan d'adressage (10.50.0.0/16)

| Zone | Réseau libvirt | CIDR | Passerelle (OPNsense) | Rôle |
|------|----------------|------|-----------------------|------|
| Cœur SOC | `nexus-cenadi-mgmt` | 10.50.0.0/24 | 10.50.0.1 | NEXUS SOC + PKI + collecte + IRIS |
| DMZ interne | `nexus-cenadi-dmz` | 10.50.10.0/24 | 10.50.10.1 | Relais applicatif, SMTP interne |
| Applicatif | `nexus-cenadi-app` | 10.50.20.0/24 | 10.50.20.1 | Serveurs métier, annuaire LDAP |
| **Sensible** | `nexus-cenadi-sens` | 10.50.30.0/24 | 10.50.30.1 | **ANTILOPE (air-gap)** |
| Admin | `nexus-cenadi-adm` | 10.50.40.0/24 | 10.50.40.1 | Poste RSSI/DSI |
| Menace | `nexus-cenadi-men` | 10.50.50.0/24 | 10.50.50.1 | Poste compromis (simulation) |

L'hôte conserve `10.50.0.2` sur la zone mgmt. Les adresses `.1` appartiennent
toutes à OPNsense, qui est la passerelle de chaque zone.

### Adresses fixes

| Machine | IP | Zone |
|---|-----|------|
| OPNsense | .1 de chaque zone | toutes |
| HÔTE (cœur SOC) | 10.50.0.2 | mgmt |
| vm-app-gov | 10.50.20.20 | app |
| vm-antilope | 10.50.30.30 | **sensible (air-gap)** |
| vm-rssi | 10.50.40.40 | admin |
| KaliPrime | 10.50.50.50 | menace |

---

## 2. Matrice des flux inter-zone

Ligne = source, colonne = destination. `✓` autorisé, `✗` bloqué par OPNsense.
Le refus est la règle par défaut : tout ce qui n'est pas listé est rejeté.

| De \ Vers | SOC (mgmt) | DMZ | App | Sensible | Admin | Menace | Internet |
|-----------|-----------|-----|-----|----------|-------|--------|----------|
| **SOC** | — | ✓ | ✓ | ✓ (collecte) | ✓ | ✓ | **✓ (liste blanche)** |
| **DMZ** | ✓ | — | ✗ | ✗ | ✗ | ✗ | ✗ |
| **App** | ✓ (télémétrie) | ✗ | — | ✗ | ✗ | ✗ | ✗ |
| **Sensible** | ✓ (télémétrie seule) | ✗ | ✗ | — | ✗ | ✗ | **✗** |
| **Admin** | ✓ | ✓ | ✗ | ✗ | — | ✗ | ✓ (filtrée) |
| **Menace** | ✓ (télémétrie) | ✗ | ✗ | **✗** | ✗ | — | **✗** |

**Points-clés :**

- La zone **Sensible** ne parle qu'au SOC. Une seule case `✓` sur sa ligne, et
  jamais vers Internet. C'est l'air-gap, et il est inchangé.
- La zone **Menace** n'atteint pas la zone Sensible. Un poste bureautique
  compromis ne touche pas la solde.
- La zone **Menace** ne sort pas non plus sur Internet : le canal de commande de
  la démonstration est simulé en interne, une machine volontairement compromise
  n'a pas à joindre l'Internet réel.
- Le **cœur SOC** sort, mais vers une liste blanche journalisée.

### Politique de sortie du cœur SOC

Le WAN d'OPNsense est actif. Il ne l'était pas dans la version précédente de
cette architecture, où l'absence de câble tenait lieu de politique. Une
politique se prouve, une absence de câble ne prouve rien.

Destinations autorisées depuis `10.50.0.0/24`, en sortie seule :

| Destination | Usage |
|---|---|
| Miroir de paquets de la distribution | correctifs de sécurité |
| Registre de conteneurs | images de la pile |
| Sources de renseignement sur les menaces | alimentation MISP |
| Dépôt de règles Wazuh | mises à jour de détection |

Tout le reste est rejeté et journalisé. L'enrichissement d'indicateurs passe par
MISP auto-hébergé ; VirusTotal reste désactivé par défaut, car soumettre une
empreinte issue d'un système de l'État à un service étranger sort du périmètre
de souveraineté que la plateforme défend.

---

## 3. Topologie

```
                          ┌────────────────────────────┐
                          │  Internet (sortie filtrée) │
                          └──────────────┬─────────────┘
                                         │ WAN
                          ┌──────────────▼─────────────┐
                          │      OPNsense-CENADI       │
                          │  routage inter-zone + ACL  │
                          │  Suricata + API de réponse │
                          └──┬───┬───┬───┬───┬───┬─────┘
                             │   │   │   │   │   │
              ┌──────────────┘   │   │   │   │   └──────────────┐
              │ mgmt         dmz │   │   │   │ adm         men  │
              │                  │   │   │   │                  │
      ┌───────▼────────┐    ┌────▼┐  │   │  ┌▼──────┐   ┌───────▼──────┐
      │ HÔTE 10.50.0.2 │    │ DMZ │  │   │  │vm-rssi│   │  KaliPrime   │
      │ NEXUS SOC      │    └─────┘  │   │  └───────┘   │  10.50.50.50 │
      │ PostgreSQL     │             │   │              └──────────────┘
      │ Wazuh          │       ┌─────▼┐  └──────┐
      │ IRIS           │       │ app  │      sens│
      │ Mattermost     │  ┌────▼──────▼┐  ┌──────▼──────┐
      └────────────────┘  │ vm-app-gov │  │ vm-antilope │
                          │ 10.50.20.20│  │ 10.50.30.30 │
                          │ LDAP       │  │  AIR-GAP    │
                          └────────────┘  └─────────────┘
```

**Un seul équipement.** La version précédente empilait pfSense en périmètre et
MikroTik en routage inter-zone. Le trafic latéral, menace vers app ou app vers
sensible, transitait par MikroTik et ne remontait jamais jusqu'à pfSense :
bloquer une adresse sur le pare-feu de périmètre coupait la machine du cœur SOC
sans la couper de ses voisines. OPNsense porte les deux rôles, ce qui supprime
le défaut et l'équipement.

---

## 4. Prérequis

- libvirt, virt-manager, KVM
- image OPNsense (BSD 2-Clause), 4 Go de RAM avec Suricata
- ISOs : Ubuntu Server (app, antilope), Ubuntu Desktop (rssi), Kali (menace)
- NEXUS SOC installé sur l'hôte (PostgreSQL et uvicorn sous systemd)

GNS3 n'est plus nécessaire. Avec un seul pare-feu et des réseaux libvirt, la
topologie se monte directement sous libvirt, ce qui retire une couche
d'émulation et son coût mémoire.

---

## 5. Séquence de mise en place

1. `./01-network-setup.sh` crée les six zones libvirt
2. Installer OPNsense, une interface par zone plus le WAN
3. Appliquer la matrice du §2 et la politique de sortie
4. Créer les alias `nexus_block` et `nexus_quarantaine`, puis le compte d'API
   restreint (voir [03-quarantaine-blocage.md](03-quarantaine-blocage.md))
5. `scripts/host-cenadi-configure.sh` pour la PKI interne et le `.env` souverain
6. `cp .env.cenadi .env && sudo systemctl restart nexus-soc`
7. Créer les machines virtuelles ([02-vm-specs.md](02-vm-specs.md))
8. Déployer la pile de réponse ([06-reponse-collaborative.md](06-reponse-collaborative.md))
9. Démonstration : [RUNBOOK.md](RUNBOOK.md)
