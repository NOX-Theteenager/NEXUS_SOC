# NEXUS SOC — RUNBOOK de démonstration

Script **minute-par-minute** pour la soutenance du 24 août 2026.

**Durée totale : 45 minutes** (30 min de démo + 15 min de questions/marge)

Ce runbook suppose que les 4 VMs sont installées, les scripts setup ont
été exécutés, et les snapshots baseline existent.

---

## Setup avant l'entrée du jury (T-10 min)

### Sur le hôte

Ouvrir dans cet ordre exact, **écrans/onglets déjà positionnés** :

- **Écran/moniteur principal** (projeté au jury) :
  - Terminal 1 (grand) : SSH `nexus@10.42.0.10` (vm-soc)
  - Terminal 2 (moyen) : SSH `compta@10.42.0.20` (vm-cible)
  - Firefox onglet 1 : `https://nexussoc.cm` (masqué en fond)
  - Firefox onglet 2 : Gmail `nguetsajunior@gmail.com` (masqué en fond)

- **Écran secondaire** (pour toi seulement) :
  - Ce runbook ouvert
  - Chronomètre visible (téléphone en mode DND, écran retourné vers toi)
  - Notes/slides de secours

### Dans les VMs (Snapshots)

**Réinitialiser** chaque VM à son snapshot baseline (si démo répétée) :

```bash
for vm in vm-soc vm-cible vm-kali vm-dsi; do
    virsh snapshot-revert "$vm" "os-installed"
    virsh start "$vm"
done

# Attente boot complet (~ 90 s)
sleep 90

# Vérifier
for ip in 10.42.0.10 10.42.0.20 10.42.0.30 10.42.0.40; do
    ping -c 1 -W 2 "$ip" && echo "$ip UP" || echo "$ip ✗"
done
```

### Vérifications finales

- [ ] `curl https://nexussoc.cm/health` répond 200
- [ ] `curl https://soc.minfi.local/health` (dans le lab) répond 200
- [ ] Portail DSI accessible depuis vm-dsi (Firefox déjà lancé)
- [ ] Console admin accessible : `curl -u admin@nexussoc.cm:admin ...`
- [ ] Test SMTP Gmail : `.venv/bin/python -c "from smtp_client import send_otp_email; ..."`
- [ ] OBS Studio prêt à enregistrer

---

## Timeline complète

| Bloc                          | Début  | Fin    | Écran principal                  |
|-------------------------------|--------|--------|----------------------------------|
| 1. Introduction (contexte)    | T+0    | T+5    | Slides / topology.md             |
| 2. **Scénario 4 — PLG SaaS**  | T+5    | T+11   | Firefox `nexussoc.cm` + Gmail    |
| 3. **Scénario 1 — Souveraineté** | T+11 | T+16 | Terminal 1 (vm-soc + tcpdump)    |
| 4. **Scénario 2 — Fraude UEBA** | T+16 | T+26  | Terminal 2 (vm-cible) + Firefox portail DSI |
| 5. **Scénario 3 — Ransomware SOAR** | T+26 | T+38 | Terminal 2 + vm-dsi + vm-kali |
| 6. Synthèse & questions       | T+38   | T+45   | Console admin + audit_log.csv    |

---

## Bloc 1 — Introduction (5 min)

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

## Bloc 2 — Scénario 4 : PLG SaaS avec OTP Gmail (6 min)

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

## Bloc 3 — Scénario 1 : Souveraineté (5 min)

Suivre : **`scenarios/01-souverainete-check.sh`** (à exécuter DEPUIS LE HÔTE).

### Actions

```
[T+11:00] Basculer sur Terminal 1 (SSH vm-soc)
[T+11:30] Sur le hôte : sudo lab/scenarios/01-souverainete-check.sh
[T+12:00] PREUVE 1 : virsh net-dumpxml → aucune balise <forward>
[T+13:00] PREUVE 2 : tcpdump 30 secondes, sortie vide
[T+15:00] PREUVE 3 : ping 8.8.8.8 depuis vm-soc → TIMEOUT
[T+16:00] Fin
```

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

## Bloc 4 — Scénario 2 : Fraude interne UEBA (10 min)

Suivre : **`scenarios/02-fraude-ueba.sh`** (à exécuter DEPUIS vm-cible).

### Actions

```
[T+16:00] Basculer sur Terminal 2 (SSH vm-cible)
[T+16:30] compta@vm-cible:~$ sudo /path/to/lab/scenarios/02-fraude-ueba.sh
[T+17:00] Phase 1 : baseline normale (10 événements)
[T+19:00] Phase 2 : dérive (5σ)
[T+21:00] Phase 3 : fraude critique (9σ)
[T+22:00] Basculer sur Firefox vm-dsi → portail
[T+22:30] Login dsi@minfi.cm / admin
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

## Bloc 5 — Scénario 3 : Ransomware + SOAR (12 min)

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
[T+33:00] Revenir sur vm-cible → montrer que ping vers 10.42.0.10 échoue maintenant (isolation effective simulée)
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

## Bloc 6 — Synthèse et questions (7 min)

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
# 1. Revert des snapshots
for vm in vm-soc vm-cible vm-kali vm-dsi; do
    virsh snapshot-revert "$vm" "os-installed"
done

# 2. Nettoyage DB (nouveau tenant PLG créé pendant démo précédente)
ssh nexus@10.42.0.10 'docker exec nexus-postgres psql -U nexus -d nexus_soc -c "
    DELETE FROM plg_registrations WHERE email LIKE %demo%;
    DELETE FROM tenants WHERE nom LIKE %Démo%;
"'

# 3. Nettoyage fichiers .locked sur vm-cible
ssh compta@10.42.0.20 'sudo find /home/compta_agent -name "*.locked" -delete'

# 4. Vider audit_log
ssh nexus@10.42.0.10 'rm -f ~/NEXUS_SOC/audit_log.csv'
```

---

## En cas de panne pendant la démo

Voir **`troubleshooting.md`** — 15 pannes fréquentes avec fix en < 30 s.

### Les 3 pannes les plus probables

1. **Mail Gmail bloqué** (spam ou 2FA) → utiliser lien magique dans logs uvicorn
2. **Portail DSI 500** → `sudo systemctl restart nexus-soc` sur vm-soc
3. **Réseau lab qui laisse fuiter** → `virsh net-destroy nexus-lab && virsh net-start nexus-lab`

Chacune se résout en < 30 secondes. Prévoir un plan B texte à lire si l'une
d'elles arrive.
