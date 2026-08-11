# CENADI — Architecture souveraine détaillée

Adressage, zones, flux autorisés et topologie GNS3 du déploiement souverain.

---

## 1. Plan d'adressage (10.50.0.0/16)

| Zone | Réseau libvirt | CIDR | Gateway (MikroTik) | Rôle |
|------|----------------|------|--------------------|------|
| Cœur SOC | `nexus-cenadi-mgmt` | 10.50.0.0/24 | 10.50.0.1 = **HÔTE** | NEXUS SOC + PKI + collecte |
| DMZ interne | `nexus-cenadi-dmz` | 10.50.10.0/24 | 10.50.10.1 | Reverse-proxy, SMTP interne |
| Applicatif | `nexus-cenadi-app` | 10.50.20.0/24 | 10.50.20.1 | Serveurs métier gouvernementaux |
| **Sensible** | `nexus-cenadi-sens` | 10.50.30.0/24 | 10.50.30.1 | **ANTILOPE (air-gap)** |
| Admin | `nexus-cenadi-adm` | 10.50.40.0/24 | 10.50.40.1 | Poste RSSI/DSI |
| Menace | `nexus-cenadi-men` | 10.50.50.0/24 | 10.50.50.1 | Poste compromis (simulation) |

### IP fixes des VMs
| VM | IP | Zone |
|----|-----|------|
| HÔTE (SOC) | 10.50.0.1 | mgmt |
| vm-app-gov | 10.50.20.20 | app |
| vm-antilope | 10.50.30.30 | **sensible (air-gap)** |
| vm-rssi | 10.50.40.40 | admin |
| vm-menace | 10.50.50.50 | menace |

---

## 2. Matrice des flux autorisés

Ligne = source, colonne = destination. `✓` autorisé, `✗` bloqué (ACL MikroTik).

| De \ Vers | SOC (mgmt) | DMZ | App | Sensible | Admin | Menace | Internet |
|-----------|-----------|-----|-----|----------|-------|--------|----------|
| **SOC** | — | ✓ | ✓ | ✓ (collecte) | ✓ | ✓ | ✗ |
| **DMZ** | ✓ | — | ✗ | ✗ | ✗ | ✗ | ✗ |
| **App** | ✓ (télémétrie) | ✗ | — | ✗ | ✗ | ✗ | ✗ |
| **Sensible** | ✓ (télémétrie only) | ✗ | ✗ | — | ✗ | ✗ | ✗ |
| **Admin** | ✓ | ✓ | ✗ | ✗ | — | ✗ | ✗ |
| **Menace** | ✓ (télémétrie) | ✗ | ✗ | **✗** | ✗ | — | ✗ |

**Points-clés :**
- **Aucune** zone n'atteint Internet (colonne Internet = ✗ partout).
- La zone **Sensible** ne peut QUE parler au SOC (une seule case ✓ sur sa ligne).
- La zone **Menace** ne peut PAS atteindre la zone Sensible (case en gras `✗`)
  → même compromis, un poste bureautique ne touche pas la solde.
- Le SOC peut joindre toutes les zones (collecte) mais **pas** Internet.

---

## 3. Topologie GNS3

```
                    ┌──────────────────────────────┐
                    │  HÔTE = CŒUR SOC (10.50.0.1)  │
                    │  NEXUS SOC + PKI + Wazuh       │
                    └───────────────┬──────────────┘
                                    │ virbr-cen-mgmt
                          ┌─────────▼──────────┐
                          │  pfSense-CENADI    │  pare-feu périmètre interne
                          │  (WAN DÉSACTIVÉ)   │  ← aucune patte Internet
                          └─────────┬──────────┘
                          ┌─────────▼──────────┐
                          │  MikroTik-CENADI   │  routage inter-zone + ACL
                          │  (matrice §2)      │
                          └──┬───┬───┬───┬───┬─┘
                   VLAN10 ───┘   │   │   │   └─── VLAN50 (menace)
                     DMZ    VLAN20 VLAN30 VLAN40
                            app   sensible admin
                             │      │       │
                        vm-app-gov  vm-      vm-rssi
                                   antilope
                                   (AIR-GAP)
```

**Particularité souveraine :** l'interface WAN de pfSense est
**désactivée** (ou non câblée). Il n'y a physiquement aucun lien vers un cloud
« Internet ». Le pare-feu ne fait que du filtrage inter-zone interne.

---

## 4. Prérequis (sans les images cloud)

- libvirt / virt-manager / KVM
- GNS3 + images pfSense CE + MikroTik CHR
- ISOs : Ubuntu Server (app, antilope), Ubuntu Desktop (rssi), Kali (menace)
- Le projet NEXUS SOC déjà installé sur le hôte (PostgreSQL + uvicorn en systemd)

---

## 5. Séquence de mise en place

1. `./01-network-setup.sh` — crée les 6 zones libvirt
2. GNS3 — pfSense (WAN OFF) + MikroTik avec la matrice ACL du §2
3. `scripts/host-cenadi-configure.sh` — PKI interne + .env souverain
4. `cp .env.cenadi .env && sudo systemctl restart nexus-soc` — active la config souveraine
5. Créer les VMs (`02-vm-specs.md`) + scripts de setup
6. Démo : `RUNBOOK.md`
nox&é"