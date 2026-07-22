# NEXUS SOC LAB — Topologie de référence (avec GNS3)

Diagramme à projeter pendant l'introduction (bloc 1 du RUNBOOK).

Le HÔTE Ubuntu joue le rôle de vm-soc (économie 8 Go RAM).
GNS3 fournit pfSense + MikroTik pour la crédibilité réseau.

---

## Vue globale

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  MACHINE HÔTE Ubuntu 22.04 (32 Go RAM, SSD 500 Go)                          ║
║  ═════════════════════════════════════════════════                          ║
║                                                                              ║
║  ┌───────────────────────────────┐  ┌────────────────────────────────────┐  ║
║  │  NEXUS SOC (systemd, auto)    │  │  GNS3 Server                       │  ║
║  │                               │  │                                    │  ║
║  │  • PostgreSQL/TimescaleDB     │  │  ┌──────────────────┐              │  ║
║  │  • uvicorn 0.0.0.0:8000       │  │  │  pfSense-Bord    │              │  ║
║  │  • Caddy TLS :8443            │  │  │  ─────────────   │              │  ║
║  │  • cloudflared → nexussoc.cm  │  │  │  • Pare-feu bord │              │  ║
║  │  • Wazuh Manager :514         │  │  │  • Syslog → SOC  │              │  ║
║  │                               │  │  │  • Peut couper   │              │  ║
║  │  ┌─── nexus-mgmt bridge ────┐ │  │  │    Internet      │              │  ║
║  │  │        10.42.0.1/24      │ │  │  └────────┬─────────┘              │  ║
║  │  └──────────┬───────────────┘ │  │           │ trunk 802.1Q            │  ║
║  └─────────────┼─────────────────┘  │  ┌────────▼─────────┐              │  ║
║                │                    │  │  MikroTik CHR    │              │  ║
║                │                    │  │  Router-Core     │              │  ║
║                │                    │  │  ─────────────   │              │  ║
║                │                    │  │  • Inter-VLAN    │              │  ║
║                │                    │  │  • ACL isolation │              │  ║
║                │                    │  │  • NetFlow → SOC │              │  ║
║                │                    │  └──┬────┬────┬─┬──┘              │  ║
║                │                    │     │    │    │ │                  │  ║
║                │                    │  VLAN10 VLAN20 VLAN30 mgmt          │  ║
║                │                    └─────┼────┼────┼────┼────────────────┘  ║
║                │                          │    │    │    │                  ║
║                └──────────────────────────┼────┼────┼────┘                  ║
║                                           │    │    │                        ║
║                                    ┌──────┴┐ ┌─┴──┐ │                       ║
║                                    │virbr- │ │virbr│ ▼                       ║
║                                    │vlan10 │ │vlan20 virbr-vlan30           ║
║                                    │10.42. │ │10.42│ 10.42.30.0/24          ║
║                                    │10.0/24│ │20.0/│                         ║
║                                    │       │ │24   │                         ║
║                                    └─┬───┬─┘ └─────┘   ┌─────┐              ║
║                                      │   │              │     │              ║
║                                   ┌──▼┐ ┌▼──┐        ┌─▼──┐  │              ║
║                                   │cible│ │dsi│       │kali│  │              ║
║                                   │.20  │ │.40│       │.30 │  │              ║
║                                   └─────┘ └───┘       └────┘  │              ║
║                                                                              ║
║                          TENANT Afriland (VLAN 10)          TENANT external     ║
║                          (poste comptable + DSI)         (VLAN 30)           ║
║                                                                              ║
║                          VLAN 20 = UBA (vide, sert la démo        ║
║                                     d'isolation cross-tenant)                ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌──── Réseau externe (Internet) ────┐   ┌──── Firefox hôte ─────┐          ║
║  │  cloudflared → nexussoc.cm         │   │  (démo PLG SaaS)      │          ║
║  │  (accessible depuis Firefox hôte)  │   └───────────────────────┘          ║
║  └────────────────────────────────────┘                                      ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## Adressage réseau

| Segment              | CIDR             | Rôle                                       |
|----------------------|------------------|--------------------------------------------|
| `virbr-mgmt`         | 10.42.0.0/24     | HÔTE SOC ↔ GNS3 (management)               |
| `virbr-vlan10`       | 10.42.10.0/24    | Tenant Afriland (vm-cible, vm-dsi)            |
| `virbr-vlan20`       | 10.42.20.0/24    | Tenant UBA (vm-cibleB Alpine)  |
| `virbr-vlan30`       | 10.42.30.0/24    | Attaquant externe (vm-kali)                |

### IPs statiques

| Composant     | IP              | Segment       |
|---------------|-----------------|---------------|
| HÔTE SOC      | 10.42.0.1       | mgmt          |
| pfSense LAN   | 192.168.100.1   | (interne GNS3)|
| MikroTik ether1 | 192.168.100.2 | (interne GNS3)|
| MikroTik ether2 | 10.42.10.1    | VLAN10        |
| MikroTik ether3 | 10.42.20.1    | VLAN20        |
| MikroTik ether4 | 10.42.30.1    | VLAN30        |
| MikroTik ether5 | 10.42.0.2     | mgmt          |
| vm-cible      | 10.42.10.20     | VLAN10 (Afriland) |
| vm-dsi        | 10.42.10.40     | VLAN10 (Afriland) |
| vm-cibleB     | 10.42.20.20     | VLAN20 (UBA — Alpine 2 Go) |
| vm-kali       | 10.42.30.30     | VLAN30 (external) |

---

## Flux de données par scénario

### Scénario 1 — Souveraineté
```
   vm-cible ─► ping 8.8.8.8 ─► MikroTik ─► pfSense ─► BLOCK
                                                       │
                                                       └─► syslog HÔTE
                                                           « Deny outbound »

   Preuves du jury :
     • pfSense règle : "no Internet"  → visible sur la GUI GNS3
     • Compteur "matches" incrémente en temps réel
     • Log syslog sur /var/log/nexus-lab.log
```

### Scénario 2 — Fraude UEBA
```
   vm-cible (VLAN10) ─► POST /ingest ─► MikroTik ─► HÔTE SOC (10.42.0.1)
                                                     │
                                                     ▼
                                             Kafka → Modèle 2 (UEBA)
                                                     │
                                                     ▼
                                          Alerte "Fraude interne"
                                                     │
                                                     ▼
                                          Notification portail
                                                     │
   vm-dsi (VLAN10) ◄─── poll 30s ◄──────── /portal/notifications
```

### Scénario 3 — Ransomware SOAR
```
   vm-cible (VLAN10) ─► callback ─► MikroTik ─► routage ─► vm-kali (VLAN30)
                                                              │
                                                              ▼
                                                        C2 factice :8443
                                                              │
                                     NetFlow ──► HÔTE SOC ◄───┘
                                                     │
                                     Modèle 1 (réseau) détecte anomalie
                                                     │
                                                     ▼
                                            SOAR Playbook Ransomware
                                            ├─ enrich_ioc (auto)
                                            ├─ snapshot_memory (auto)
                                            ├─ isolate_host (⏸ humain)
                                            ├─ block_ip (auto)
                                            └─ notify_dsi (push)
                                                     │
   vm-dsi (VLAN10) ─► clic VALIDER ─► /analyst/approve-soar
```

### Scénario 4 — PLG (Internet réel, hors lab GNS3)
```
   Firefox hôte ─► Internet ─► Cloudflare ─► cloudflared ─► uvicorn hôte
                                                                │
                                                                ▼
                                                        SMTP Gmail
                                                                │
                                                                ▼
                                                    nguetsajunior@gmail.com
```

### Scénario 5 — Cross-tenant isolation (NOUVEAU grâce à GNS3)
```
   vm-kali (VLAN30) ─► nmap ─► MikroTik ACL ─► DROP
        │                       │
        │                       └─► syslog HÔTE : "Deny inter-VLAN"
        │
        └─► curl HÔTE (10.42.0.1) ─► OK  (télémétrie autorisée)

   Preuve applicative en plus :
     dsi@afriland.cm         → voit N alertes
     dsi@afriland.cm → voit M alertes (M ≠ N)
     Même endpoint, deux vues : RLS PostgreSQL discrimine par JWT.
```

---

## Ports et services par nœud

| Nœud          | Port  | Service            | Sources autorisées       |
|---------------|-------|--------------------|--------------------------|
| **HÔTE SOC**  | 22    | SSH                | Toutes les VMs           |
| HÔTE SOC      | 8000  | uvicorn NEXUS      | Toutes les VMs (via ACL) |
| HÔTE SOC      | 8443  | Caddy TLS          | Toutes les VMs           |
| HÔTE SOC      | 514   | rsyslog (UDP)      | pfSense, MikroTik        |
| HÔTE SOC      | 2055  | NetFlow collector  | MikroTik                 |
| **pfSense**   | 443   | GUI HTTPS          | vm-dsi (mgmt)            |
| **MikroTik**  | 8291  | WinBox/API         | vm-dsi (mgmt)            |
| MikroTik      | 22    | SSH                | vm-dsi (mgmt)            |
| **vm-cible**  | 22    | SSH                | HÔTE                     |
| **vm-kali**   | 22    | SSH                | HÔTE                     |
| vm-kali       | 8443  | C2 factice         | vm-cible (via routeur)   |
| **vm-dsi**    | -     | Firefox local      | Console                  |

---

## Comptes de démo

Tous mots de passe : **`admin`** (à ne pas laisser en production).

| E-mail                      | Rôle              | Tenant                  | VLAN | Utilité démo                     |
|-----------------------------|-------------------|-------------------------|------|----------------------------------|
| `admin@nexussoc.cm`         | admin_plateforme  | (fournisseur NEXUS)     | -    | Console admin                    |
| `soc@nexussoc.cm`           | analyste_soc      | (fournisseur NEXUS)     | -    | Escalades, faux positifs         |
| `dsi@afriland.cm`           | dsi_client        | Afriland First Bank     | 10   | Portail scénarios 2, 3           |
| `dsi@uba.cm`                | dsi_client        | UBA Cameroun            | 20   | Preuve isolation RLS (scénario 5)|

Comptes équipements réseau :
| Équipement | Login | Mot de passe    |
|------------|-------|-----------------|
| pfSense    | admin | pfsense         |
| MikroTik   | admin | (vide au 1er boot, à définir) |
