# CENADI — RUNBOOK de démonstration (déploiement souverain)

Démo ~30 min du déploiement souverain de NEXUS SOC au CENADI. Complémentaire
à un déploiement mutualisé : ici, l'angle est **souveraineté +
sécurisation**, pas produit-led growth.

## Message central à faire passer au jury

> « Le MÊME produit NEXUS SOC sert deux marchés avec deux modèles de
> déploiement souverain on-premise, exploité en interne par le CENADI.
> Pour l'État — le CENADI — : déploiement souverain on-premise, zéro donnée
> sortante, PKI interne, air-gap de la solde. Voici le second. »

---

## Setup avant le jury (T-15 min)

> **Ne PAS recopier `.env.cenadi` par-dessus `.env`.** L'ancienne procédure le
> faisait : `.env` porte désormais les clés d'OPNsense, d'IRIS et du robot
> Mattermost, qui ne sont pas dans le fichier suivi par git. L'écraser couperait
> les trois connecteurs à dix minutes de la soutenance.

```bash
cd ~/Documents/Projets/NEXUS_SOC

# 1. Les six zones, puis le pare-feu qui les route
bash lab-cenadi/01-network-setup.sh --appliquer      # si les réseaux manquent
virsh -c qemu:///system start OPNsense-CENADI
for vm in vm-app-gov vm-antilope vm-rssi KaliPrime; do
    virsh -c qemu:///system start "$vm"
done

# 2. Les outils d'enquête et de coordination
(cd /opt/nexus-iris && docker compose up -d)
docker compose -f Lot0_Socle/docker-compose.reponse.yml up -d

# 3. Le cœur SOC
sudo systemctl restart nexus-soc
```

### Les six vérifications qui décident si on peut y aller

```bash
curl -s  -o /dev/null -w 'SOC       %{http_code}\n' http://10.50.0.2:8000/health
curl -sk -o /dev/null -w 'OPNsense  %{http_code}\n' https://10.50.0.1/
curl -sk -o /dev/null -w 'IRIS      %{http_code}\n' https://10.50.0.2:4443/
curl -s  -o /dev/null -w 'Mattermost %{http_code}\n' http://10.50.0.2:8065/api/v4/system/ping
for h in 10.50.20.20 10.50.30.30 10.50.40.40 10.50.50.50; do
    ping -c1 -W2 "$h" >/dev/null && echo "zone $h OK" || echo "zone $h MUETTE"
done
docker exec nexus-postgres psql -U nexus -d nexus_soc -At -c \
  "SELECT 'alias quarantaine non vide !' FROM soar_audit WHERE execution='automatique' LIMIT 1"
```

**La dernière compte plus que les autres** : une quarantaine oubliée d'une
répétition précédente rend une zone muette le jour J, et on cherche une panne
réseau là où il n'y a qu'une mesure qu'on a omis de lever.

```bash
# Repartir d'un pare-feu propre
set -a; . ./.env; set +a
for a in nexus_quarantaine nexus_block; do
  curl -sk -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" \
       "https://10.50.0.1/api/firewall/alias_util/list/$a"
done
```

Positionner les écrans : terminal HÔTE (cœur SOC), console RSSI dans Firefox sur
vm-rssi, IRIS sur `https://10.50.0.2:4443`, Mattermost sur
`http://10.50.0.2:8065`, et la **vue temps réel du pare-feu** — Firewall → Log
Files → Live View — qui est l'écran le plus parlant de toute la démonstration.

---

## Timeline (~30 min)

| Bloc | Durée | Écran | Scénario |
|------|-------|-------|----------|
| 1. Contexte souverain | 3 min | Slides + `00-architecture-cenadi.md` | — |
| 2. Cloisonnement en six zones | 4 min | Terminal HÔTE | `scenarios/05` |
| 3. Air-gap zone sensible | 4 min | vm-antilope + KaliPrime | `scenarios/02` |
| 4. Détection : la chaîne d'attaque | 5 min | KaliPrime + console RSSI | `scenarios/03` |
| 5. **Réponse pilotée et vérifiée** | 6 min | Console + Live View pare-feu | `scenarios/08` |
| 6. Enquête et coordination | 4 min | IRIS + Mattermost | `scenarios/09`, `10` |
| 7. Questions | 4 min | — | — |

Le bloc 5 est le cœur de la soutenance : c'est le seul où la plateforme **agit**
au lieu de constater. Si le temps manque, retrancher sur les blocs 1 et 3, jamais
sur celui-là.

---

## Bloc 1 — Contexte souverain (4 min)

Afficher `00-architecture-cenadi.md`. Dialogue :

> « Le CENADI héberge ANTILOPE — la solde de centaines de milliers d'agents de
> l'État — et PROBMIS, le budget national. Ces données ne peuvent PAS partir
> chez un tiers ni sortir du territoire. NEXUS SOC se déploie donc
> DANS le datacenter, en 6 zones, dont une en air-gap total. »

## Bloc 2 — Sécurisation (6 min)

Parcourir les 7 couches de `SECURISATION.md`. Insister sur :
- Couche 2 : l'air-gap de la zone solde (matrice de flux)
- Couche 5 : chiffrement + PKI interne (pas Let's Encrypt)
- Couche 7 : conformité CEMAC + auditabilité

## Bloc 3 — Souveraineté datacenter (5 min)

```bash
sudo bash scenarios/01-souverainete-datacenter.sh
```
3 preuves : .env sans clés Internet, TLS via AC CENADI, tcpdump vide.

## Bloc 4 — Air-gap zone sensible (6 min)

Sur **vm-antilope** :
```bash
sudo bash scenarios/02-airgap-zone-sensible.sh
```
Puis sur **vm-menace** (montrer que l'attaquant ne touche pas la solde) :
```bash
nmap -Pn --host-timeout 5s 10.50.30.30   # tous ports filtered
ping -c 3 10.50.30.30                     # timeout
```

Dialogue-clé :
> « Voici un poste bureautique compromis. Il essaie d'atteindre le serveur de
> la solde. Le routeur droppe chaque paquet au niveau 3. Même compromis de
> l'intérieur, l'attaquant est piégé dans sa zone. »

## Bloc 5 — Exfiltration + SOAR (7 min)

Sur **vm-app-gov** :
```bash
sudo bash scenarios/03-exfiltration-solde.sh
```
Puis sur **vm-rssi**, Firefox → `https://soc.cenadi.local:8443/app/console.html`
(cadenas vert car AC CENADI importée), login `soc@nexussoc.cm` / `admin`,
montrer l'alerte + la file SOAR + la validation humaine.

Dialogue de clôture :
> « Détection, analyse, réponse : tout s'est passé dans le datacenter CENADI.
> Aucune donnée de solde n'a transité par un tiers. C'est la souveraineté
> numérique concrète — le même produit NEXUS SOC, configuré pour l'État. »

---

## Bloc 5 — Réponse pilotée et vérifiée (6 min) — LE bloc

Deux écrans : la console RSSI, et la vue temps réel du pare-feu.

1. **Montrer l'action proposée**, avec sa cible et son impact. Insister : la
   plateforme n'a rien exécuté. `execution` vaut `non_executee`, et elle le dit.

2. **Approuver.** Rien ne se passe encore — approuver et appliquer sont deux
   gestes. Souligner que la fenêtre entre les deux est délibérée.

3. **Exécuter.** Sur la vue temps réel, les rejets apparaissent en rouge pendant
   que la télémétrie de la machine isolée continue de passer en vert vers
   `10.50.0.2:8000`.

   > « La quarantaine coupe les flux de la machine et laisse passer sa
   > télémétrie vers le SOC. Isoler sans aveugler : au moment précis où l'on a
   > le plus besoin de voir, on continue de voir. »

4. **Le refus.** Demander à la plateforme d'isoler le cœur SOC lui-même. Elle
   refuse, explique pourquoi, et rend la commande manuelle.

   > « Une réponse automatique se juge d'abord à ses refus. Celle-ci sait
   > qu'isoler le SOC couperait la plateforme qui exécute la décision — et que
   > plus personne ne serait là pour lever la mesure. »

5. **La relecture.** Montrer `execution_note` : la mesure a été relue sur
   l'appliance. Un code HTTP 200 n'aurait pas suffi — OPNsense accepte une
   adresse dans un alias inutilisé, OpenLDAP accepte un attribut qu'il ignore.

6. **Lever**, et constater le retour à la normale.

**Si un jury demande ce qui n'est pas couvert** : les sessions déjà établies ne
sont pas purgées, faute d'un privilège que le compte de service n'a pas. La
réserve est écrite dans l'audit à chaque exécution. Le dire avant qu'on ne le
demande vaut mieux que de l'admettre après.

---

## Bloc 6 — Enquête et coordination (4 min)

Escalader l'alerte dans IRIS. Trente secondes plus tard, le canal
`incident-AAAAMMJJ-…` s'ouvre dans Mattermost avec le résumé, le risque,
l'entité et les deux liens.

> « L'escalade reste un geste d'analyste. La plateforme mesure et propose ;
> l'humain qualifie. Ce n'est pas une limite technique : le compte de service
> n'a pas la permission d'escalader. »

Montrer aussi la file : arrêter IRIS pendant la démonstration ne perd aucune
alerte, elles partent au redémarrage.

---

## Reset entre répétitions

```bash
cd ~/Documents/Projets/NEXUS_SOC
set -a; . ./.env; set +a

# 1. Lever TOUTE mesure restée en vigueur — le point le plus important.
#    Une quarantaine oubliée rend une zone muette à la répétition suivante,
#    et on cherche une panne réseau là où il n'y a qu'une mesure non levée.
for a in nexus_quarantaine nexus_block; do
  for ip in $(curl -sk -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" \
        "https://10.50.0.1/api/firewall/alias_util/list/$a" \
        | python3 -c "import sys,json;[print(r['ip']) for r in (json.load(sys.stdin).get('rows') or [])]"); do
    curl -sk -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" -X POST \
         -H 'Content-Type: application/json' -d "{\"address\":\"$ip\"}" \
         "https://10.50.0.1/api/firewall/alias_util/delete/$a" >/dev/null
  done
done

# 2. Dégeler les comptes suspendus
.venv/bin/python -c "
import sys; sys.path.insert(0,'Lot4_SOAR')
from connecteurs import construire
c = construire()['freeze_account']
for uid in c.cibles_actives():
    print(uid, c.lever(uid).resume())"

# 3. Remettre l'audit et les files à zéro
docker exec nexus-postgres psql -U nexus -d nexus_soc -c \
  "UPDATE soar_audit SET execution='non_executee', decision=NULL,
          statut='EN ATTENTE DE VALIDATION', execution_note=NULL
     WHERE execute_par LIKE 'recette%';
   DELETE FROM incident_canal WHERE canal_nom LIKE 'incident-%';"
```

**Vérifier après reset** : les quatre zones répondent au ping, et les deux alias
sont vides. Si une zone reste muette, c'est une mesure non levée — pas le
réseau.

## En cas de panne — par ordre de probabilité

**Une zone est muette.** Regarder l'alias de quarantaine AVANT le réseau : neuf
fois sur dix c'est une mesure d'une répétition précédente qu'on n'a pas levée.
La commande de reset ci-dessus les retire toutes.

**Une machine a perdu son adresse après un redémarrage.** Son interface a
changé de nom (`eth1` → `eth0`) et le profil NetworkManager était lié au nom.
C'est arrivé sur KaliPrime le 28 août. Correction :

```bash
python3 lab-cenadi/scripts/qga-exec.py <VM> \
  'nmcli con mod cenadi-zone connection.interface-name "" \
   802-3-ethernet.mac-address <MAC de la zone> && nmcli con up cenadi-zone'
```

**L'API du pare-feu répond 403.** C'est l'autorisation, pas la clé : vérifier
que le compte `nexus-soar` porte bien `page-firewall-alias-edit` et
`page-diagnostics-tables`. Un 401 en revanche désigne la clé.

**IRIS ne reçoit plus rien.** Regarder la file, pas IRIS :
`SELECT etat, count(*) FROM dossier_sortie GROUP BY etat`. Si tout est en
attente avec des tentatives qui montent, IRIS est en panne et **rien n'est
perdu** — c'est la propriété qu'on démontre, autant le dire au jury.

**Le canal d'incident ne s'ouvre pas.** Sans conséquence sur le reste : la
détection, le dossier et la réponse continuent. Vérifier
`SELECT etat, derniere_erreur FROM incident_canal WHERE etat <> 'ouvert'`.

**Firefox refuse le certificat** → l'AC racine CENADI n'a pas été importée sur
vm-rssi (relancer `vm-rssi-setup.sh` après scp du `cenadi-root-ca.crt`).

**Ne jamais** recopier `.env.cenadi` sur `.env` pendant la démonstration : les
clés des trois connecteurs n'y sont pas.
