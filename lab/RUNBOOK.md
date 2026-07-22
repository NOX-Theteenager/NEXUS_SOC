# NEXUS SOC — RUNBOOK de démonstration

Script **minute-par-minute** pour la soutenance du 24 août 2026.

**Durée totale : 50 minutes** (35 min de démo + 15 min de questions/marge)

Ce runbook suppose que :
- Le HÔTE est configuré (via `scripts/host-configure.sh`) et fait tourner
  NEXUS SOC en systemd
- La topologie GNS3 est active (pfSense + MikroTik + 4 clouds VLANs)
- Les 3 VMs libvirt sont installées et connectées aux bons VLANs
- Les scripts setup ont été exécutés
- Les snapshots baseline existent

---

## Setup avant l'entrée du jury (T-10 min)

### Sur le hôte

Ouvrir dans cet ordre exact, **écrans/onglets déjà positionnés** :

- **Écran/moniteur principal** (projeté au jury) :
  - Terminal 1 (grand) : sur le HÔTE (le SOC — logs, tcpdump, SQL)
  - Terminal 2 (moyen) : SSH `compta@10.42.10.20` (vm-cible Afriland)
  - Terminal 3 (petit) : SSH `kali@10.42.30.30` (vm-kali, pour le C2)
  - Fenêtre GNS3 (topologie ouverte)
  - Firefox onglet 1 : `https://nexussoc.cm` (masqué en fond)
  - Firefox onglet 2 : Gmail `nguetsajunior@gmail.com` (masqué en fond)

- **Écran secondaire** (pour toi seulement) :
  - Ce runbook ouvert
  - Chronomètre visible (téléphone en mode DND, écran retourné vers toi)
  - Notes/slides de secours

### Dans les VMs (Snapshots)

**Réinitialiser** chaque VM à son snapshot baseline (si démo répétée).
Le HÔTE n'est PAS une VM — il tourne en continu (systemd).

```bash
for vm in vm-cible vm-dsi vm-cibleB vm-kali; do
    virsh snapshot-revert "$vm" "os-installed"
    virsh start "$vm"
done

# Attente boot complet (~ 90 s)
sleep 90

# Vérifier (chaque VM dans son VLAN)
for ip in 10.42.10.20 10.42.10.40 10.42.20.20 10.42.30.30; do
    ping -c 1 -W 2 "$ip" >/dev/null && echo "$ip UP" || echo "$ip ✗"
done
# + le HÔTE SOC
curl -s http://10.42.0.1:8000/health && echo " ← HÔTE SOC UP"
```

### Vérifications finales

- [ ] `curl https://nexussoc.cm/health` répond 200
- [ ] `curl -k https://soc.nexus.local:8443/health` (dans le lab) répond 200
- [ ] Portail DSI accessible depuis vm-dsi (Firefox déjà lancé)
- [ ] Console admin accessible : `curl -u admin@nexussoc.cm:admin ...`
- [ ] Test SMTP Gmail : `.venv/bin/python -c "from smtp_client import send_otp_email; ..."`
- [ ] OBS Studio prêt à enregistrer

---

## Timeline complète

| Bloc                          | Début  | Fin    | Écran principal                       |
|-------------------------------|--------|--------|---------------------------------------|
| 1. Introduction (contexte)    | T+0    | T+4    | Slides / topology.md                  |
| 2. **Tour d'écran GNS3**      | T+4    | T+6    | GNS3 GUI (pfSense + MikroTik + VLANs) |
| 3. **Scénario 4 — PLG SaaS**  | T+6    | T+12   | Firefox `nexussoc.cm` + Gmail         |
| 4. **Scénario 1 — Souveraineté** | T+12 | T+17 | Terminal HÔTE + pfSense GUI           |
| 5. **Scénario 2 — Fraude UEBA** | T+17 | T+27  | Terminal vm-cible + Firefox portail DSI |
| 6. **Scénario 3 — Ransomware SOAR** | T+27 | T+39 | Terminal vm-cible + vm-dsi + vm-kali |
| 7. **Scénario 5 — Cross-tenant** | T+39 | T+43 | Terminal vm-kali + comptes 2 DSI      |
| 8. Synthèse & questions       | T+43   | T+50   | Console admin + audit_log.csv         |

---

## Bloc 1 — Introduction (4 min)

### Slides à projeter

1. **NEXUS SOC** — Plateforme SOC-as-a-Service souveraine pour le Cameroun
2. Problématique : pas de SOC accessible aux microfinances camerounaises
3. Approche : 2 canaux — SaaS PLG + Déploiement souverain
4. Topologie du lab (`lab/topology.md`)

### Dialogue

> « Le projet NEXUS SOC répond à une question précise : comment permettre à
> une microfinance camerounaise, avec un budget d'assurance à 5 000 000 FCFA
> par an, d'avoir un centre opérationnel de sécurité de niveau bancaire ?
>
> Deux réponses sont apportées par le projet — c'est ce que je vais vous
> montrer en live sur cette architecture de lab. Trois VMs isolées, une VM
> DSI, aucune connexion Internet interne. Nous partons d'un état vide. »

**Actions :** afficher `lab/topology.md`, cliquer sur les composants un par un.

---

## Bloc 2 — Tour d'écran GNS3 (2 min) 🆕

### Objectif
Prouver au jury que la topologie n'est pas un dessin PowerPoint : c'est un
vrai lab réseau opérationnel.

### Actions

```
[T+4:00] Basculer sur la fenêtre GNS3 (déjà ouverte)
[T+4:20] Zoomer sur le projet "NEXUS-SOC-Lab"
[T+4:40] Clic-droit pfSense → Console → montrer les règles firewall (`show rules`)
[T+5:20] Clic-droit MikroTik → Console → montrer `/ip firewall filter print`
[T+5:50] Retour vue globale : les VLANs sont visibles par couleur
[T+6:00] Fin
```

### Dialogue

> « Ce que vous voyez ici est la topologie réseau réelle du client :
> un pare-feu pfSense de bord, un routeur MikroTik qui applique la
> segmentation en 3 VLANs, chacun représentant un tenant client.
> Ce n'est pas une simulation en JSON — c'est du vrai routage inter-VLAN,
> avec des ACLs qui bloquent les paquets au niveau 3. »

---

## Bloc 3 — Scénario 4 : PLG SaaS avec OTP Gmail (6 min)

Suivre le guide détaillé : **`scenarios/04-plg-otp-guide.md`**

### Points saillants pour le jury

- Le mail arrive **en direct**, projeté sur écran (Gmail projeté)
- Insister sur la **détection des domaines .gov.cm** qui bascule automatiquement
  vers le canal souverain — c'est un signal-clé de crédibilité

### Actions techniques

```
[T+5:00] Onglet Firefox 1 → https://nexussoc.cm
[T+5:30] Formulaire d'inscription (5 s pour remplir)
[T+6:00] Basculer sur onglet Gmail
[T+6:10] Mail arrive → montrer OTP en gros à l'écran
[T+6:30] Revenir à NEXUS SOC → saisir OTP → validation
[T+7:00] Formulaire CinetPay (token de démo `sandbox_ok`)
[T+8:00] Écran final : dashboard tenant + trial 30 jours
[T+11:00] Fin du bloc
```

### Bascule vers le bloc suivant

> « Ça, c'est le canal SaaS pour les microfinances. Mais que se passe-t-il
> pour un client qui n'accepte AUCUNE fuite de donnée, comme la Direction
> Générale du Trésor ? Ma réponse tient dans le mot **souveraineté** :
> déploiement sur son infrastructure, tout local, zéro sortie. Regardez. »

---

## Bloc 4 — Scénario 1 : Souveraineté (5 min)

Suivre : **`scenarios/01-souverainete-check.sh`** (à exécuter DEPUIS LE HÔTE).

### Actions

```
[T+11:00] Basculer sur Terminal 1 (le HÔTE = SOC)
[T+11:30] sudo lab/scenarios/01-souverainete-check.sh
[T+12:00] PREUVE 1 : whois/DNS → domaine .cm hébergé au Cameroun
[T+13:00] PREUVE 2 : dépendances tierces (Cloudflare/Gmail/CinetPay) géo-localisées
[T+14:30] PREUVE 3 : tcpdump 30 s → aucune exfiltration vers AWS/GCP/Azure US/EU
[T+16:00] Fin
```

> Complément GNS3 : montrer aussi sur la GUI pfSense la règle "no Internet"
> pour les clients qui exigent le mode strict (canal souverain type MINFI).

### Dialogue clé

> « Regardez cette commande `virsh net-dumpxml`. Le fait qu'il n'y ait
> AUCUNE balise `<forward>` signifie que même par erreur, une donnée ne
> peut pas quitter ce réseau. C'est physiquement bloqué au niveau de
> l'hyperviseur.
>
> Aucun concurrent SaaS américain ou européen ne peut prouver ça. C'est
> notre différenciateur numéro un pour vendre à l'administration
> camerounaise. »

---

## Bloc 5 — Scénario 2 : Fraude interne UEBA (10 min)

Suivre : **`scenarios/02-fraude-ueba.sh`** (à exécuter DEPUIS vm-cible).

### Actions

```
[T+16:00] Basculer sur Terminal 2 (SSH vm-cible)
[T+16:30] compta@vm-cible:~$ sudo /path/to/lab/scenarios/02-fraude-ueba.sh
[T+17:00] Phase 1 : baseline normale (10 événements)
[T+19:00] Phase 2 : dérive (5σ)
[T+21:00] Phase 3 : fraude critique (9σ)
[T+22:00] Basculer sur Firefox vm-dsi → portail
[T+22:30] Login dsi@afriland.cm / admin
[T+23:00] Cloche 🔔 → notification arrivée en direct
[T+23:30] Clic sur la notification → rapport HTML enrichi
[T+24:00] Bouton "Télécharger le rapport" → HTML sauvegardé
[T+25:00] Retour terminal : montrer audit_log.csv
[T+26:00] Fin
```

### Dialogue clé

> « Le Modèle 2, un Isolation Forest entraîné sur 10 000 sessions
> historiques d'agents comptables, a détecté l'anomalie en moins de 3
> secondes après le dernier événement. Il a émis :
>
> - Un score de risque 91/100 → catégorie CRITIQUE
> - Une explication humaine dans le rapport : "9.2σ hors du baseline
>   personnel de compta_agent"
> - Une notification push arrivée sur le portail DSI
>
> Aucune règle statique n'a été écrite. C'est de la détection
> comportementale non supervisée. Elle marche pour un profil d'agent DGI
> comme pour un profil de guichetier microfinance, sans reconfiguration. »

---

## Bloc 6 — Scénario 3 : Ransomware + SOAR (12 min)

Suivre : **`scenarios/03-ransomware-soar.sh`** (à exécuter DEPUIS vm-cible).

### Setup préalable (T-1 min avant le bloc)

Sur **vm-kali**, dans un onglet SSH séparé :

```bash
sudo systemctl start c2-listener
journalctl -u c2-listener -f
```

Cette fenêtre reste visible → montre les callbacks arriver en direct.

### Actions

```
[T+26:00] Confirmer C2 actif sur vm-kali (Terminal 3)
[T+26:30] Terminal 2 (vm-cible) : sudo lab/scenarios/03-ransomware-soar.sh
[T+27:00] Phase 1 : callback C2 (visible sur Terminal 3 vm-kali)
[T+28:00] Phase 2 : chiffrement de 60 fichiers → .locked
[T+29:00] Phase 3 : SOAR interrogé → playbook Ransomware actif
[T+30:00] Basculer vm-dsi : notification "Ransomware sur POSTE-COMPTA-01"
[T+31:00] Onglet "Actions en attente" → "Isoler le poste" ⏸
[T+32:00] Cliquer VALIDER → confirmation + audit
[T+33:00] Revenir sur vm-cible → ping vers 10.42.0.1 (SOC) échoue (isolation effective)
[T+34:00] Retour vm-dsi → cliquer ROLLBACK (démo faux positif)
[T+35:00] Poste réintégré au réseau
[T+37:00] Montrer audit_log.csv complet
[T+38:00] Fin
```

### Dialogue clé

> « Trois garde-fous concrets viennent d'être exercés :
>
> 1. **Validation humaine** : l'isolation n'est pas automatique — un
>    humain doit consentir. C'est ce qui a manqué à SolarWinds en 2020.
>
> 2. **Rollback en 1 clic** : si le DSI se rend compte que c'était un
>    faux positif, il annule sans redémarrage manuel de la machine.
>
> 3. **Audit complet** : chaque décision (auto ou humaine) est loggée
>    avec horodatage. Traçabilité totale pour un audit interne ou COBAC. »

---

## Bloc 7 — Scénario 5 : Isolation cross-tenant (4 min) 🆕

Suivre : **`scenarios/05-cross-tenant-isolation.sh`** (à exécuter DEPUIS vm-kali).

### Actions

```
[T+39:00] Terminal vm-kali : sudo lab/scenarios/05-cross-tenant-isolation.sh
[T+39:30] Preuve 1 : nmap VLAN30 → VLAN10 → tous ports filtered
[T+40:30] Preuve 2 : ping VLAN30 → VLAN10 → timeout
[T+41:00] Preuve 3 : ping HÔTE SOC → OK (télémétrie autorisée)
[T+41:30] Preuve 4 : deux DSI → deux vues d'alertes distinctes (RLS)
[T+43:00] Fin
```

### Dialogue clé

> « Voici la double isolation qui fait la crédibilité d'un SOC multi-tenant :
>
> - Au **niveau réseau**, le routeur MikroTik bloque physiquement les
>   paquets entre VLANs. Un attaquant qui pénétrerait un tenant ne peut pas
>   pivot vers un autre — c'est bloqué à L3, avant même le hôte du voisin.
>
> - Au **niveau applicatif**, même quelqu'un qui aurait un JWT volé ne
>   voit que son tenant. Le Row-Level Security PostgreSQL filtre côté
>   serveur, pas côté client.
>
> Pour compromettre les données d'un tenant client, il faut donc briser
> simultanément 3 barrières indépendantes. C'est ce que l'ANSSI appelle
> "défense en profondeur", et c'est ce qui est attendu d'un vrai SOC. »

---

## Bloc 8 — Synthèse et questions (7 min)

### Console admin

Ouvrir un nouvel onglet Firefox → `https://nexussoc.cm/app/console.html`,
login `admin@nexussoc.cm` / `admin`.

Montrer :
- Nombre total de tenants (avec le nouveau ajouté au scénario 4)
- Nombre d'alertes générées aujourd'hui
- Nombre d'agents actifs
- KPIs de performance : latence médiane P95, taux d'ingestion

### Synthèse orale

> « Ce que je viens de démontrer en 33 minutes :
>
> - **Canal SaaS** avec inscription self-service, OTP Gmail réel, tenant
>   isolé (row-level security PostgreSQL)
> - **Souveraineté prouvée** au niveau hyperviseur — pas juste un
>   marketing claim
> - **Détection ML** non supervisée d'une fraude comportementale
> - **SOAR avec humain-dans-la-boucle**, garde-fous, rollback, audit
>
> L'ensemble fait 7 500 lignes de Python + 9 000 lignes de frontend,
> 18 tests automatisés qui passent à 100%, déployable en 30 minutes
> chez un nouveau client, exposé en HTTPS via Cloudflare Tunnel avec
> HSTS et certificat Google Trust Services.
>
> Le projet est prêt pour les 3 premiers clients pilotes que je
> vais démarcher pendant l'année de fin d'études. »

### Questions attendues (préparer les réponses)

1. **« Comment gérez-vous la scalabilité ? »**
   → Kafka en KRaft mode, RLS PostgreSQL, horizontal scaling par tenant

2. **« Que se passe-t-il si le modèle IA se trompe ? »**
   → Monitoring de dérive (PSI, FP rate), rollback, réentraînement mensuel

3. **« Combien coûte l'infra pour 100 tenants ? »**
   → ~150 000 FCFA/mois VPS + Cloudflare Free (voir Bilan_Projet.md)

4. **« Comment garantissez-vous la confidentialité inter-tenant ? »**
   → RLS PostgreSQL, JWT tenant_id, tests unitaires de fuite

5. **« Pourquoi pas Wazuh directement ? »**
   → Wazuh manque UEBA, SOAR humain-dans-la-boucle, pricing multi-tenant

---

## Procédure de reset entre deux répétitions

Si tu répètes la démo en boucle (pour t'entraîner) :

```bash
# 1. Revert des snapshots (le HÔTE n'est pas une VM, il reste up)
for vm in vm-cible vm-dsi vm-cibleB vm-kali; do
    virsh snapshot-revert "$vm" "os-installed"
done

# 2. Nettoyage DB — directement sur le HÔTE (qui est le SOC)
docker exec nexus-postgres psql -U nexus -d nexus_soc -c "
    DELETE FROM plg_registrations WHERE email LIKE '%demo%';
    DELETE FROM tenants WHERE nom LIKE '%Démo%';
"

# 3. Nettoyage fichiers .locked sur vm-cible
ssh compta@10.42.10.20 'sudo find /home/compta_agent -name "*.locked" -delete'

# 4. Vider audit_log (sur le HÔTE)
rm -f /home/noxtheteenager/Documents/Projets/NEXUS_SOC/audit_log.csv
```

---

## En cas de panne pendant la démo

Voir **`troubleshooting.md`** — 15 pannes fréquentes avec fix en < 30 s.

### Les 3 pannes les plus probables

1. **Mail Gmail bloqué** (spam ou 2FA) → récupérer l'OTP en DB (troubleshooting #7)
2. **Portail DSI 500** → `sudo systemctl restart nexus-soc` sur le HÔTE
3. **VM ne joint pas le SOC** → vérifier routage MikroTik + `host-configure.sh` (troubleshooting #3)

Chacune se résout en < 30 secondes. Prévoir un plan B texte à lire si l'une
d'elles arrive.
