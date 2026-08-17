# NEXUS SOC au CENADI — Sécurisation (défense en profondeur)

Guide de durcissement du déploiement souverain. Organisé selon les **7 couches
de défense en profondeur**, de la sécurité physique jusqu'à la gouvernance.
Chaque couche liste : la **menace**, la **mesure**, et la **commande / preuve**.

> Ce document est la pièce maîtresse du lab CENADI : il montre non seulement
> *que* NEXUS SOC fonctionne, mais *comment il est protégé* dans un contexte
> gouvernemental à très haute sensibilité (solde de l'État, budget national).

---

## Vue d'ensemble — les 7 couches

```
┌─────────────────────────────────────────────────────────────┐
│ 7. GOUVERNANCE   — politiques, audits, conformité CEMAC       │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 6. DÉTECTION    — le SOC lui-même surveille le SOC        │ │
│ │ ┌─────────────────────────────────────────────────────┐ │ │
│ │ │ 5. DONNÉES    — chiffrement repos + transit + backup  │ │ │
│ │ │ ┌─────────────────────────────────────────────────┐ │ │ │
│ │ │ │ 4. APPLICATION — RBAC, JWT, RLS, secrets          │ │ │ │
│ │ │ │ ┌─────────────────────────────────────────────┐ │ │ │ │
│ │ │ │ │ 3. HÔTE/OS  — durcissement systemd, SELinux   │ │ │ │ │
│ │ │ │ │ ┌─────────────────────────────────────────┐ │ │ │ │ │
│ │ │ │ │ │ 2. RÉSEAU — segmentation VLAN, air-gap    │ │ │ │ │ │
│ │ │ │ │ │ ┌─────────────────────────────────────┐ │ │ │ │ │ │
│ │ │ │ │ │ │ 1. PHYSIQUE — datacenter, accès       │ │ │ │ │ │ │
│ │ │ │ │ │ └─────────────────────────────────────┘ │ │ │ │ │ │
│ │ │ │ │ └─────────────────────────────────────────┘ │ │ │ │ │
│ │ │ │ └─────────────────────────────────────────────┘ │ │ │ │
│ │ │ └─────────────────────────────────────────────────┘ │ │ │
│ │ └─────────────────────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Couche 1 — Sécurité physique

| Menace | Mesure |
|--------|--------|
| Accès physique non autorisé aux serveurs | Datacenter CENADI en zone contrôlée, badge + biométrie, journal d'entrée |
| Vol de disque | Chiffrement complet du disque (LUKS) sur les serveurs SOC et sensibles |
| Extraction de données par port USB | Ports USB désactivés au BIOS sur les serveurs de la zone sensible |

**Chiffrement du disque (LUKS) — à la création du serveur :**
```bash
# Vérifier qu'un volume est chiffré
lsblk -o NAME,FSTYPE,MOUNTPOINT | grep crypto_LUKS
cryptsetup status /dev/mapper/nexus-data   # doit indiquer "active"
```

Dans le lab (VMs), on **simule** LUKS sur le volume de données PostgreSQL.

---

## Couche 2 — Réseau (segmentation + air-gap)

C'est la couche la plus visible du lab. Six zones, routées et filtrées par un
seul équipement : **OPNsense**, en refus par défaut.

La version précédente répartissait les rôles entre pfSense en périmètre et
MikroTik en routage inter-zone. Le trafic latéral ne remontait jamais jusqu'au
pare-feu de périmètre, donc une adresse bloquée là-haut restait joignable par
ses voisines. Un seul équipement supprime ce défaut.

| Zone | Réseau | Internet | Peut joindre |
|------|--------|----------|--------------|
| DMZ interne | 10.50.10.0/24 | Non | SOC uniquement |
| Cœur SOC | 10.50.0.0/24 | **Sortie sur liste blanche, journalisée** | Toutes zones (collecte) |
| Applicatif | 10.50.20.0/24 | Non | SOC (télémétrie) |
| **Sensible (ANTILOPE)** | 10.50.30.0/24 | **AIR-GAP total** | **SOC uniquement, rien d'autre** |
| Admin RSSI | 10.50.40.0/24 | Sortie filtrée | SOC + DMZ |
| Menace | 10.50.50.0/24 | Non | doit être bloquée partout sauf SOC |

Le WAN d'OPNsense est actif. Il ne l'était pas dans la version précédente, où
l'absence de câble tenait lieu de politique. Une politique de sortie se
démontre, une absence de câble ne démontre rien : depuis le cœur SOC, une
destination sur liste blanche répond et une autre est rejetée puis journalisée.

**Règle d'or de l'air-gap (zone 30) :** un serveur ANTILOPE peut *émettre* sa
télémétrie vers le SOC (flux sortant unidirectionnel vers 10.50.0.1), mais **ne
peut initier aucune autre connexion** — ni Internet, ni latéralement vers une
autre zone.

**Règles OPNsense sur l'interface LAN_SENS (dans l'ordre) :**

| # | Action | Source | Destination | Port | Commentaire |
|---|--------|--------|-------------|------|-------------|
| 1 | Autoriser | LAN_SENS net | 10.50.0.2 | 8000, 443 | ANTILOPE vers SOC : télémétrie |
| 2 | Rejeter | LAN_SENS net | any | any | air-gap, tout le reste |

Et sur les autres interfaces, une règle de rejet vers `LAN_SENS net`, pour que
personne n'entre dans la zone sensible. Les réponses aux connexions établies
sont gérées par le suivi d'état d'OPNsense, sans règle explicite.

**Preuve (scénario 02) :** depuis vm-antilope, `ping 8.8.8.8` échoue,
`ping 10.50.20.20` (autre zone) échoue, mais `curl 10.50.0.2:8000/health`
réussit.

---

## Couche 3 — Hôte / système d'exploitation

| Menace | Mesure | Vérification |
|--------|--------|--------------|
| Élévation de privilèges du service SOC | Durcissement systemd (`NoNewPrivileges`, `ProtectSystem`, `ProtectHome`) | `systemd-analyze security nexus-soc` |
| Surface d'attaque OS | Paquets minimaux, pas de GUI sur les serveurs, SSH par clé uniquement | `systemctl list-units --type=service --state=running` |
| Compte root exposé | `PermitRootLogin no`, sudo journalisé | `grep PermitRootLogin /etc/ssh/sshd_config` |
| Mises à jour manquantes | `unattended-upgrades` pour les correctifs de sécurité | `apt list --upgradable` |

**Le service systemd `nexus-soc.service` est déjà durci** (voir
`../00_Documents/nexus-soc.service`) :
```ini
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=/home/.../NEXUS_SOC
LimitNOFILE=65536
```

Score de durcissement systemd :
```bash
systemd-analyze security nexus-soc | tail -3
# Objectif : score < 5.0 (OK / bon)
```

> **Note de configuration importante** (leçon du déploiement) : les variables
> numériques du `.env` (`ACCESS_TOKEN_TTL_S`, etc.) **ne doivent pas** contenir
> de commentaire en fin de ligne. `systemd EnvironmentFile` ne les strippe pas
> comme `python-dotenv` et casse le `int()` au chargement. Garder le `.env`
> propre : `CLE=valeur` sans `# commentaire` sur la même ligne.

---

## Couche 4 — Application (RBAC / JWT / RLS / secrets)

C'est la couche du code NEXUS SOC lui-même.

### 4.1 Contrôle d'accès basé sur les rôles (RBAC)
4 rôles, séparation stricte :
- `admin_plateforme` — administration (au CENADI : l'équipe SOC)
- `analyste_soc` — supervision, escalade, validation SOAR
- `dsi_client` — lecture du portail (au CENADI : le RSSI / DSI)
- `lecteur` — lecture seule

**Preuve :** un `dsi_client` reçoit **403** sur `/admin/*`.
```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $DSI" \
  http://10.50.0.1:8000/admin/tenants     # → 403
```

### 4.2 JWT signés HMAC-SHA256
- Secret 32 octets, **jamais** la valeur par défaut en production.
- TTL court (15 min access, 7 j refresh).
```bash
# Générer un secret fort et l'injecter dans .env (une seule fois)
openssl rand -base64 32
```

### 4.3 Row-Level Security PostgreSQL
Même en mono-tenant CENADI, la RLS garantit qu'une requête ne peut jamais
lire les données d'un autre périmètre. En souverain, on l'utilise pour
**cloisonner par direction** (DGI vs DGTCFM vs paie).

### 4.4 Gestion des secrets
| Secret | Où | Durcissement souverain |
|--------|-----|------------------------|
| `JWT_SECRET`, `PSEUDO_SECRET` | `.env` (0600, hors git) | En prod : coffre-fort (HashiCorp Vault interne ou `systemd-creds`) |
| Mot de passe PostgreSQL | `.env` | Rotation trimestrielle |
| Clé privée PKI | `~/pki-cenadi/` (0600) | HSM ou clé hors-ligne pour l'AC racine |

```bash
# Vérifier les permissions du .env (doit être 600, propriétaire uniquement)
stat -c '%a %U' /home/.../NEXUS_SOC/.env    # → 600 <user>
```

---

## Couche 5 — Données (chiffrement repos + transit + sauvegarde)

| État de la donnée | Protection |
|-------------------|------------|
| **Au repos** | Volume PostgreSQL sur disque LUKS ; pseudonymisation des identifiants (HMAC) via `PSEUDO_ENABLED=true` |
| **En transit** | TLS partout via la **PKI interne CENADI** (pas Let's Encrypt) ; l'agent signe sa télémétrie en HMAC-SHA256 |
| **Sauvegarde** | Backups chiffrés (GPG) stockés dans le datacenter, jamais dans un cloud |

**Pseudonymisation active :** les identifiants d'agents/utilisateurs surveillés
sont hachés (HMAC) avant stockage — conformité protection des données.
```bash
grep PSEUDO_ENABLED /home/.../NEXUS_SOC/.env    # → PSEUDO_ENABLED=true
```

**Sauvegarde chiffrée (exemple) :**
```bash
docker exec nexus-postgres pg_dump -U nexus nexus_soc \
  | gpg --encrypt --recipient soc@cenadi.local \
  > /backup/nexus_soc_$(date +%F).sql.gpg
# Restauration : gpg --decrypt ... | psql
```

---

## Couche 6 — Détection (le SOC se surveille lui-même)

NEXUS SOC applique sa propre doctrine à sa propre infrastructure :

- **Wazuh Manager** collecte les logs des serveurs SOC eux-mêmes (auth, sudo,
  modifications de fichiers sensibles).
- **Le Modèle 1** surveille les flux réseau anormaux **depuis/vers** le SOC.
- **Le SOAR** peut isoler un serveur SOC compromis (avec validation humaine).
- **Journal d'audit immuable** : chaque action admin/SOAR est tracée
  (`soar_audit`, `enrollment_log`), horodatée, non modifiable.

```bash
# Voir le journal d'audit SOAR (qui a validé quoi, quand)
docker exec nexus-postgres psql -U nexus -d nexus_soc -c \
  "SELECT horodatage, action, decision, acteur FROM soar_audit ORDER BY horodatage DESC LIMIT 10;"

# Journal d'enrôlement des agents (traçabilité de chaque poste ajouté)
docker exec nexus-postgres psql -U nexus -d nexus_soc -c \
  "SELECT * FROM enrollment_log ORDER BY created_at DESC LIMIT 10;"
```

---

## Couche 7 — Gouvernance & conformité

| Exigence | Mise en œuvre NEXUS SOC |
|----------|-------------------------|
| **Souveraineté des données** (CEMAC 2020) | Aucune donnée ne quitte le datacenter CENADI — prouvé par tcpdump (scénario 1) |
| **Traçabilité / auditabilité** | `soar_audit`, `enrollment_log`, logs Wazuh, rétention configurable |
| **Séparation des devoirs** | RBAC : celui qui détecte (analyste) n'est pas celui qui valide l'isolation (RSSI) |
| **Réversibilité** | Toute action SOAR à fort impact est validée par un humain et annulable (rollback) |
| **Continuité** | Services en systemd `Restart=on-failure` + auto-start au boot ; backups chiffrés |
| **Moindre privilège** | Chaque agent a un token *lié à son hostname*, à usage unique, expirable |

---

## Checklist de durcissement (avant mise en production souveraine)

- [ ] `.env` : secrets régénérés (`openssl rand -base64 32`), aucune valeur `CHANGE_ME`
- [ ] `.env` : permissions `600`, hors git, aucun commentaire inline sur variables numériques
- [ ] Disque de données PostgreSQL sur volume **LUKS** chiffré
- [ ] `NEXUS_CORS_ORIGINS` = uniquement les origines internes (pas de `*`)
- [ ] TLS via **PKI interne CENADI** (AC racine hors-ligne), pas Let's Encrypt
- [ ] `EMAIL_BACKEND=smtp` pointant vers le **Postfix interne** (pas Gmail)
- [ ] `VIRUSTOTAL_ENABLED=false` (pas d'appel Internet) — base de menaces locale
- [ ] SSH : clés uniquement, `PermitRootLogin no`, fail2ban
- [ ] Pare-feu : zone sensible (VLAN 30) en **air-gap** vérifié par tcpdump
- [ ] `systemd-analyze security nexus-soc` : score OK
- [ ] Sauvegardes chiffrées GPG testées (dump + restore)
- [ ] Journal d'audit `soar_audit` activé et consultable par le RSSI
- [ ] Comptes de démo (`admin@nexussoc.cm` / `admin`) **supprimés ou mots de passe changés**

---

## Le `.env` souverain type (CENADI)

Points clés du `.env` souverain :
```env
# Pas d'Internet — tout est interne
NEXUS_SERVER_URL=https://soc.cenadi.local
NEXUS_CORS_ORIGINS=https://soc.cenadi.local,https://portail.soc.cenadi.local

# E-mail via Postfix interne (pas Gmail)
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.cenadi.local
SMTP_PORT=25
SMTP_MODE=live

# Pas d'enrichissement Internet
VIRUSTOTAL_ENABLED=false

# Pas de paiement (outil interne souverain)
CINETPAY_MODE=stub

# Secrets RÉGÉNÉRÉS (jamais les valeurs par défaut)
JWT_SECRET=<openssl rand -base64 32>
PSEUDO_SECRET=<openssl rand -base64 32>
PSEUDO_ENABLED=true
```

Voir `scripts/host-cenadi-configure.sh` qui génère ce `.env` et la PKI interne
automatiquement.
