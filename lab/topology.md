# NEXUS SOC LAB — Topologie de référence

Diagramme à afficher/projeter pendant l'introduction (bloc 1 du RUNBOOK).

---

## Vue globale

```
╔════════════════════════════════════════════════════════════════════════════╗
║  MACHINE HÔTE Ubuntu 22.04 (RAM 32 Go, SSD 500 Go)                        ║
║                                                                            ║
║  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────────┐    ║
║  │  Firefox        │  │  virt-manager    │  │  cloudflared (systemd)│    ║
║  │  (démo PLG)     │  │  (gestion VMs)   │  │  → tunnel nexussoc.cm │    ║
║  └────────┬────────┘  └──────────────────┘  └───────────┬───────────┘    ║
║           │                                              │                 ║
║           │                                              ▼                 ║
║           │                                       ┌─────────────┐         ║
║           │                                       │ Cloudflare  │         ║
║           │                                       │ Edge Global │         ║
║           │                                       └──────┬──────┘         ║
║           │                                              │                 ║
║           └──────────► https://nexussoc.cm ◄─────────────┘                 ║
║                                                                            ║
╚═══════════════════════════════════╤════════════════════════════════════════╝
                                    │
                     ┌──────────────┴──────────────┐
                     │ libvirt bridge virbr-lab    │
                     │ Réseau ISOLÉ 10.42.0.0/24   │
                     │ (aucune route vers Internet)│
                     └──────────────┬──────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────────┐
    │                               │                                   │
    │                               │                                   │
    ▼                               ▼                                   ▼
┌────────────────┐          ┌────────────────┐                  ┌──────────────┐
│   vm-soc       │          │   vm-cible     │                  │  vm-kali     │
│   10.42.0.10   │          │   10.42.0.20   │                  │  10.42.0.30  │
│                │          │                │                  │              │
│ Ubuntu 22.04   │          │ Ubuntu 22.04   │                  │ Kali Rolling │
│ Server         │          │ Server         │                  │              │
│                │          │                │                  │              │
│ 8 Go / 4 CPU   │          │ 4 Go / 2 CPU   │                  │ 4 Go / 2 CPU │
│                │          │                │                  │              │
│┌─────────────┐ │          │┌─────────────┐ │                  │┌────────────┐│
││ PostgreSQL  │ │◄─────────┤│ Agent NEXUS │ │────► Callback ───►││ C2 factice ││
││ TimescaleDB │ │          ││ (Bearer)    │ │      HTTP:8443   ││ :8443      ││
│└─────────────┘ │          │└─────────────┘ │                  │└────────────┘│
│┌─────────────┐ │          │┌─────────────┐ │                  │              │
││ Kafka KRaft │ │          ││ Scénarios : │ │                  │              │
│└─────────────┘ │          ││  fraude.sh  │ │                  │              │
│┌─────────────┐ │          ││  ransom.sh  │ │                  │              │
││ Wazuh mgr   │ │          │└─────────────┘ │                  │              │
│└─────────────┘ │          │                │                  │              │
│┌─────────────┐ │          │┌─────────────┐ │                  │              │
││ uvicorn     │ │          ││ compta_agent│ │                  │              │
││ NEXUS SOC   │ │          ││ /Documents/ │ │                  │              │
│└─────────────┘ │          │└─────────────┘ │                  │              │
│┌─────────────┐ │          │                │                  │              │
││ Caddy TLS   │ │          │                │                  │              │
││ mkcert cert │ │          │                │                  │              │
│└─────────────┘ │          │                │                  │              │
└────────┬───────┘          └────────────────┘                  └──────────────┘
         │
         │ HTTPS soc.minfi.local
         │
         ▼
┌────────────────┐
│   vm-dsi       │
│   10.42.0.40   │
│                │
│ Ubuntu 22.04   │
│ Desktop        │
│                │
│ 2 Go / 2 CPU   │
│                │
│┌─────────────┐ │
││ Firefox     │ │
│└─────────────┘ │
│                │
│ Compte :       │
│ dsi@minfi.cm   │
│ / admin        │
└────────────────┘
```

---

## Flux des données pendant les scénarios

### Scénario 1 — Souveraineté
```
   vm-soc ─┐
           ├── ping 8.8.8.8 ──► ✗ DROP (pas de route sortante)
   vm-cible┘
```

### Scénario 2 — Fraude UEBA
```
   vm-cible ────► POST /ingest ────► vm-soc:8000
   (télémétrie                       │
    frauduleuse)                     ▼
                                Kafka → M2 Isolation Forest
                                                │
                                                ▼
                                     Alert créée (risque 91/100)
                                                │
                                                ▼
                                     emit_notification_from_alert()
                                                │
                                                ▼
                                     PostgreSQL notifications
                                                │
                                                ▼
   vm-dsi ◄──── polling 30 s ◄──── /portal/notifications
```

### Scénario 3 — Ransomware SOAR
```
   vm-cible ────► callback ────► vm-kali:8443
                    │
                    └─► POST /ingest ────► vm-soc
                        (débit anormal +
                         .locked pattern)         │
                                                  ▼
                                          Modèle 1 (réseau)
                                                  │
                                                  ▼
                                          Alert Ransomware
                                                  │
                                                  ▼
                                          SOAR Playbook
                                          ├── enrich_ioc      (auto)
                                          ├── snapshot_memory (auto)
                                          ├── isolate_host    (⏸ humain)
                                          ├── block_ip        (auto)
                                          └── notify_dsi      (auto)
                                                  │
                                                  ▼
   vm-dsi ────► clic VALIDER ────► /analyst/approve-soar
                                                  │
                                                  ▼
                                          Poste isolé
                                          (audit_log.csv)
```

### Scénario 4 — PLG (hors lab)
```
                     Internet
                       │
                       ▼
   Hôte (Firefox) ── nexussoc.cm ──► cloudflared ──► uvicorn hôte
                                                        │
                                                        ▼
                                                 SMTP Gmail
                                                        │
                                                        ▼
                                               nguetsajunior@gmail.com
                                                        │
                                                        ▼
                                                 OTP 6 chiffres
```

---

## Comptes de démo disponibles

Tous mots de passe : **`admin`** (à ne pas laisser en production).

| E-mail                      | Rôle              | Tenant           | Utilité démo |
|-----------------------------|-------------------|------------------|--------------|
| `admin@nexussoc.cm`         | admin_plateforme  | (fournisseur)    | Console admin |
| `analyste@nexussoc.cm`      | analyste_soc      | (fournisseur)    | Escalades, faux positifs |
| `dsi@minfi.cm`              | dsi_client        | MINFI            | Portail scénarios 2 & 3 |
| `dsi@microfinance-a.cm`     | dsi_client        | Microfinance A   | Prouver isolation tenant |
| `dsi@microfinance-b.cm`     | dsi_client        | Microfinance B   | Prouver isolation tenant |

---

## Ports et services par VM

| VM       | Port | Service                       | Accessible depuis            |
|----------|------|-------------------------------|------------------------------|
| vm-soc   | 22   | SSH                           | Hôte + toutes les VMs        |
| vm-soc   | 443  | Caddy (TLS terminaison)       | Toutes les VMs               |
| vm-soc   | 8000 | uvicorn (loopback seulement)  | vm-soc seule (via Caddy)     |
| vm-soc   | 5432 | PostgreSQL (loopback)         | vm-soc seule                 |
| vm-soc   | 9092 | Kafka (interne)               | vm-soc seule                 |
| vm-cible | 22   | SSH                           | Hôte                         |
| vm-kali  | 22   | SSH                           | Hôte                         |
| vm-kali  | 8443 | C2 factice (démo ransomware)  | vm-cible                     |
| vm-dsi   | -    | Desktop (Firefox local)       | Console physique             |
