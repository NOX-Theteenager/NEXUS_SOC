# NEXUS SOC — Bilan du projet

**Date :** 2 juillet 2026 — mi-parcours du stage CENADI
**Soutenance :** 24 août 2026 (dans ~7 semaines)

---

## ✅ Terminé (production-ready)

### Cœur technique
- **Lot 0 — Socle** : Docker Compose (Kafka + TimescaleDB + Wazuh), schémas SQL avec RLS par périmètre, retention policies, seed démo
- **Lot 1 — Agent Go & pipeline** : agent d'ingestion, scoring FastAPI, auth JWT HMAC-SHA256, pseudonymisation RGPD-like
- **Lot 2 — Pipeline SIEM** : corrélation Kafka, seuils configurables, dégradation gracieuse si Kafka absent
- **Lot 3 — IA** : Isolation Forest (M1 réseau) + UEBA (M2 fraude), monitoring de dérive (PSI, sigma, taux FP)
- **Lot 4 — SOAR** : 4 playbooks (Fraude, Exfiltration, Ransomware, C2), garde-fous (validation humaine, rollback), enrichissement IOC VirusTotal
- **Lot 5 — Restitution** : notifier push in-app + rapports HTML enrichis (MITRE, indicateurs, recommandations)
- **Lot 6 — Tests** : 14/14 passent, couvre Auth, Admin, Analyste, Portail
- **Lot 7 — Console opérateur CENADI** : Admin (/admin), Analyste (/analyst), Portail périmètre (/portal), Provisioning agents (/provision)
- **Lot 9 — Frontend PWA** : login, console, portail, docs, contact, manifest, service worker, offline

### Déploiement
- **HTTPS interne** : `https://nexussoc.cm` (certificat institutionnel, HSTS actif)
- **Systemd** : `nexus-soc` auto-start au boot, restart en cas de crash
- **Sécurité** : HSTS + X-Frame-Options + Content-Type-Options + Referrer-Policy en réponse
- **Souverain (OpenTofu)** : déploiement de la pile sur serveur interne CENADI (`deploy/opentofu`)

### Intégrations externes
- ✅ **VirusTotal** — enrichissement IOC dans les 4 playbooks (optionnel, désactivé par défaut, activable sans redémarrage)

### Documentation
- `README.md` — vue d'ensemble
- `NEXUS_SOC_Contexte_Complet.md` — contexte projet + décisions
- `MIGRATION.md` — journal de la refonte souveraine CENADI
- `00_Documents/Configuration_Services_Externes.md` — guide config VirusTotal
- `00_Documents/Bilan_Projet.md` — ce document

---

## 🔧 Reste à finaliser (facile)

### 1. Auto-start PostgreSQL au boot (5 min — SUDO REQUIS)
Le service systemd est prêt dans `00_Documents/nexus-postgres.service`. À installer :

```bash
sudo cp 00_Documents/nexus-postgres.service /etc/systemd/system/nexus-postgres.service
sudo cp 00_Documents/nexus-soc.service     /etc/systemd/system/nexus-soc.service   # mise à jour avec dépendance
sudo systemctl daemon-reload
sudo systemctl enable --now nexus-postgres
sudo systemctl restart nexus-soc
```

Ordre de boot final :
```
docker.service  →  nexus-postgres.service  →  nexus-soc.service  →  cloudflared.service
                                                                       ↓
                                                            https://nexussoc.cm
```

### 2. Rôle PostgreSQL `nexus_analyst` (2 min)
Le rôle secondaire (pour les endpoints Analyste) n'est pas créé sur le nouveau volume. À faire une seule fois :

```bash
docker exec nexus-postgres psql -U nexus -d nexus_soc -c "
CREATE ROLE nexus_analyst LOGIN PASSWORD 'change_me_analyst';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nexus_analyst;
GRANT INSERT, UPDATE ON alerts, soar_audit TO nexus_analyst;
"
```

### 3. Cloudflare : HSTS côté edge (optionnel, 1 min)
Dashboard Cloudflare → SSL/TLS → Edge Certificates → activer **HSTS** (12 mois, includeSubDomains). Double couche avec le HSTS déjà envoyé par uvicorn.

---

## 🎯 Perspectives d'amélioration (pas nécessaires pour la soutenance)

### Court terme (semaines suivantes)
- **Wazuh Manager** : brancher l'ingestion de vraies alertes système (SSH, sudo, escalade)
- **Connecteurs SOAR réels** : raccorder gel de compte AD/LDAP et blocage IP au pare-feu du CENADI

### Moyen terme
- **Stack Kafka + Wazuh** au démarrage : quand le serveur a assez de RAM (>8 Go), lancer tout le docker-compose au boot au lieu de juste PostgreSQL
- **LLM Analyst** : brancher Ollama local (Mistral) pour explication des alertes en langage naturel
- **Tests d'intégration** : couvrir l'enrichissement VirusTotal et le pipeline Kafka
- **Monitoring Prometheus + Grafana** : dashboards de santé pour l'exposé technique

### Long terme (post-soutenance)
- **Multi-nœud Kubernetes** : passer de mono-machine à cluster haute disponibilité
- **Bibliothèque de playbooks internes** : partage des SOAR customs entre périmètres
- **Conformité ANTIC** : dossier de déclaration/homologation du système auprès de l'ANTIC

---

## 📊 Métriques clés

| Métrique | Valeur |
|---|---|
| Lignes de code Python | ~7 500 |
| Lignes de code JS/HTML/CSS | ~9 000 |
| Fichiers SQL (schémas + seed) | 8 |
| Endpoints API | ~35 (Auth, Admin, Analyst, Portal, Provision) |
| Playbooks SOAR | 4 |
| Modèles IA | 2 (Isolation Forest + UEBA) |
| Tests automatisés | 14 (100% verts) |
| Intégrations externes | 1, optionnelle (VirusTotal) |
| Documents Markdown | 12 |
| Uptime cible | 99.5% (Cloudflare Tunnel + systemd restart) |

---

## 🏁 Ce qui est déjà démontrable au jury

- **Ouvrir `https://nexussoc.cm`** depuis le réseau interne
- **Docs interactive** (`/app/docs.html`) → sections avec exemples
- **Contact** (`/app/contact.html`) → formulaire de contact de l'équipe SOC
- **Portail périmètre** (login `resp.sigipes@cenadi.cm` / `admin`) → alertes SIGIPES + notifications + rapports téléchargeables
- **Console opérateur** (login `admin@nexussoc.cm` / `admin`) → périmètres, agents, KPIs
- **SOAR en action** : `python Lot4_SOAR/soar_engine.py` → 4 incidents traités avec garde-fous

---

## 🚦 Verdict

**Le projet est fonctionnellement complet** pour la soutenance du 24 août.

Il ne reste **AUCUNE tâche critique**. Les 3 points listés dans "Reste à finaliser" sont des ajustements de confort (persistance, rôle secondaire, HSTS edge) qui prennent 10 minutes cumulées.

Le focus des 7 prochaines semaines peut passer à :
- **Rédaction du mémoire** (~50 pages)
- **Préparation de la soutenance orale** (support Beamer/Keynote + démo scriptée)
- **Répétitions** avec des questions de jury type
- **Corrections finales cosmétiques** si des utilisateurs de test remontent des bugs
