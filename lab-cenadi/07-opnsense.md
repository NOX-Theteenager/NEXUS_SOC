# OPNsense — installation et mise en service

Phase 1 du [plan](../00_Documents/Decision_Reponse_Collaborative.md).

> **État au 28 août 2026.** Topologie déployée et recettée : les quatre
> machines sont sur le seul plan 10.50, la matrice de flux passe 12 contrôles
> sur 12, et la quarantaine est démontrée. Reste l'authentification des
> collecteurs (§8), Suricata et la clé d'API.

---

## 1. Ce qui est déjà fait

```bash
bash lab-cenadi/01-network-setup.sh --appliquer      # six zones isolées
bash lab-cenadi/scripts/opnsense-creer-vm.sh --appliquer
```

Les réseaux libvirt sont devenus de purs commutateurs : ni passerelle, ni
service d'adressage. L'hôte ne garde une adresse que sur la zone du cœur SOC,
en **10.50.0.2**, posée par libvirt donc persistante. Les `.1` reviennent au
pare-feu.

La machine porte sept interfaces dans un ordre fixé par leurs adresses MAC :

| Vue OPNsense | Réseau libvirt | Rôle | Adresse |
|---|---|---|---|
| `vtnet0` | `default` | WAN, sortie filtrée | DHCP de l'hyperviseur |
| `vtnet1` | `nexus-cenadi-mgmt` | LAN_MGMT | 10.50.0.1/24 |
| `vtnet2` | `nexus-cenadi-dmz` | LAN_DMZ | 10.50.10.1/24 |
| `vtnet3` | `nexus-cenadi-app` | LAN_APP | 10.50.20.1/24 |
| `vtnet4` | `nexus-cenadi-sens` | LAN_SENS | 10.50.30.1/24 |
| `vtnet5` | `nexus-cenadi-adm` | LAN_ADM | 10.50.40.1/24 |
| `vtnet6` | `nexus-cenadi-men` | LAN_MEN | 10.50.50.1/24 |

---

## 2. Installer sur le disque

L'installateur d'OPNsense est une suite de boîtes de dialogue. L'automatiser
demanderait de détourner `bsddialog`, pour un gain de deux minutes et un risque
de partitionner le mauvais disque. Ces quelques touches se font à la main.

Ouvrir la console :

```bash
virt-viewer --connect qemu:///system OPNsense-CENADI
```

Puis :

1. `login:` **installer** — mot de passe **opnsense**
2. Disposition du clavier : **French** si le clavier est en AZERTY, sinon
   accepter
3. **Install (UFS)**
4. Choisir **vtbd1** (20 Go). *Surtout pas `vtbd0`, qui est l'image
   d'installation elle-même : 2,5 Go, en lecture seule.*
5. Confirmer la destruction du disque
6. Mot de passe root, deux fois, puis **Complete Install**

Au redémarrage, retirer l'image d'installation pour que la machine amorce
seule :

```bash
virsh -c qemu:///system shutdown OPNsense-CENADI
virsh -c qemu:///system detach-disk OPNsense-CENADI vda --config --persistent
virsh -c qemu:///system start OPNsense-CENADI
```

---

## 3. Appliquer la configuration CENADI

Après l'installation, OPNsense repart de sa configuration d'usine : `vtnet0` en
LAN à **192.168.1.1/24**, le reste inutilisé.

> **Ne pas se donner d'adresse dans 192.168.1.0/24 sur l'hôte.** Sur cette
> machine, c'est le réseau Wi-Fi réel, et 192.168.1.1 est la box. Poser
> `192.168.1.2/24` sur `virbr0` crée un sous-réseau en double et peut couper
> l'accès Internet de l'hôte. La version précédente de ce document le
> recommandait : c'était une erreur.

### 3.1 Déplacer l'adresse du LAN depuis la console

La console se pilote sans réseau, avec `virsh send-key`. Se connecter en
**root**, puis :

- option **2** (Set interface IP address) → interface **1** (LAN)
- DHCP : **n** · adresse : **192.168.122.240** · masque : **24** · passerelle :
  Entrée
- IPv6 par suivi WAN : **n** · DHCP6 : **n** · adresse IPv6 : Entrée
- serveur DHCP : **n** · passage en HTTP : **n** · nouveau certificat : **n** ·
  restauration des accès : **n**

`192.168.122.0/24` est le réseau `default` de libvirt, où l'hôte tient déjà
`192.168.122.1`. L'appliance devient donc joignable sans rien ajouter sur
l'hôte.

### 3.2 Ouvrir SSH

Le système installé démarre sans SSH. Depuis la console, option **8** (Shell) :

```sh
cp /conf/config.xml /conf/cfg.bak
sed -i "" -e "s|<ssh>|<ssh><enabled>enabled</enabled><interfaces>lan</interfaces><permitrootlogin>1</permitrootlogin><passwordauth>1</passwordauth>|" /conf/config.xml
reboot
```

### 3.3 Générer et pousser la configuration

Partir de la configuration **courante** de l'appliance, pas de celle du support
d'installation : elle porte l'empreinte du mot de passe root choisi pendant
l'installation.

```bash
export OPNSENSE_SSH_HOST=192.168.122.240 OPNSENSE_SSH_PASSWORD='<mot de passe root>'
python3 lab-cenadi/scripts/opnsense-console.py "sh -c 'cat /conf/config.xml'" \
    | sed -n '/<?xml/,/<\/opnsense>/p' > /tmp/config-usine.xml

python3 lab-cenadi/scripts/opnsense-generer-config.py \
    --usine /tmp/config-usine.xml --sortie /tmp/config-cenadi.xml
```

Le générateur affiche **une seule fois** la clé et le secret du compte d'API du
moteur SOAR. Les reporter aussitôt dans le `.env` du cœur SOC.

`opnsense-console.py` ne transmet pas l'entrée standard : le fichier voyage
compressé, dans la commande elle-même, et son empreinte est comparée des deux
côtés.

```bash
B64=$(gzip -9c /tmp/config-cenadi.xml | base64 -w0)
python3 lab-cenadi/scripts/opnsense-console.py \
    "sh -c \"echo $B64 | openssl base64 -d -A | gzip -d > /conf/config.new.xml\""
python3 lab-cenadi/scripts/opnsense-console.py "sh -c 'md5 -q /conf/config.new.xml'"
md5sum /tmp/config-cenadi.xml      # les deux empreintes doivent coïncider

python3 lab-cenadi/scripts/opnsense-console.py \
    "sh -c 'cp /conf/config.xml /conf/config.avant-cenadi.xml;
            cp /conf/config.new.xml /conf/config.xml;
            chown wwwonly:wheel /conf/config.xml'"
python3 lab-cenadi/scripts/opnsense-console.py "sh -c 'reboot'"
```

Au redémarrage, le LAN passe sur `vtnet1` et l'appliance répond sur
**10.50.0.1**, joignable depuis l'hôte qui tient `10.50.0.2`. En cas de
problème, `/conf/config.avant-cenadi.xml` reste sur l'appliance et la console
est toujours accessible.

### 3.4 Le secret d'API se saisit dans l'appliance

OPNsense stocke l'empreinte du secret, pas le secret. Le générateur ne peut donc
pas la calculer de l'extérieur. Dans **Système → Accès → Utilisateurs →
nexus-soar**, créer une clé d'API : OPNsense affiche alors le couple à reporter
dans le `.env`. C'est cette valeur qui fait foi.

---

## 4. Ce que la configuration contient

**Sept interfaces**, adressées comme au §1.

**Trois alias** : `nexus_block` et `nexus_quarantaine`, vides au départ, pilotés
par l'API du moteur SOAR ; `soc_sortie_autorisee`, la liste blanche de sortie
du cœur SOC, en noms d'hôtes plutôt qu'en adresses pour survivre aux
changements de miroir.

**Cinquante-neuf règles**, dans un ordre qui décide du comportement :

1. les cinq règles de réponse SOAR passent en premier sur chaque zone. La
   première autorise une machine en quarantaine à continuer d'émettre sa
   télémétrie vers le SOC. Si elle passait après la règle de rejet, la
   quarantaine couperait aussi l'observation, et la démonstration perdrait tout
   son intérêt ;
2. la matrice de flux, interface par interface ;
3. un refus par défaut, explicite et journalisé, sur chaque interface.

**Un compte d'API** `nexus-soar`, sans accès à l'interface web, limité à deux
privilèges : modifier un alias, et utiliser l'utilitaire d'alias. Rien d'autre.

---

## 5. Recette

À exécuter une fois les machines rebasculées sur le plan 10.50 :

```bash
bash lab-cenadi/scenarios/05-matrice-de-flux.sh
```

Trois preuves attendues :

- depuis vm-antilope, `ping 8.8.8.8` et `ping 10.50.20.20` échouent, mais
  `curl 10.50.0.2:8000/health` répond ;
- depuis le cœur SOC, un miroir de la liste blanche répond, un domaine absent
  de la liste est rejeté et journalisé ;
- une adresse ajoutée à `nexus_quarantaine` perd le contact latéral et
  **continue** d'émettre sa télémétrie.

---

## 6. Reste à faire dans cette phase

- **Authentification des collecteurs** — voir §8, seul point bloquant.
- **Clé d'API réelle** pour `nexus-soar` (§3.4), puis report dans le `.env`.
- **Suricata** sur les interfaces internes (Services → Détection d'intrusion).

---

## 7. État constaté le 28 août 2026

```
vtnet0  192.168.122.173  WAN, bail DHCP, route par defaut
vtnet1  10.50.0.1  LAN_MGMT      vtnet4  10.50.30.1  LAN_SENS
vtnet2  10.50.10.1 LAN_DMZ       vtnet5  10.50.40.1  LAN_ADM
vtnet3  10.50.20.1 LAN_APP       vtnet6  10.50.50.1  LAN_MEN

alias : nexus_block · nexus_quarantaine · soc_sortie_autorisee · nexus_collecte
69 regles generees, 129 chargees dans pf
```

Les quatre machines ont une adresse fixe dans leur zone, une configuration
persistante, et **plus aucune carte sur le réseau de gestion**. C'est ce dernier
point qui rend les preuves d'étanchéité honnêtes : tant que la carte de gestion
subsistait, le trafic contournait le pare-feu et l'air-gap n'était qu'une
apparence.

L'hôte pose sa route vers les zones au démarrage, par l'unité
`nexus-route-zones.service`. Sans elle, il envoie le trafic 10.50.x vers sa
passerelle par défaut et ne joint aucune zone — c'est arrivé deux fois pendant
la mise en place, au gré des changements de réseau de la machine.

### Recette de la matrice de flux, 12 contrôles sur 12

```
1. Le coeur SOC atteint les quatre zones                        4/4
2. Air-gap : telemetrie OK, lateral bloque, Internet bloque     4/4
3. Cloisonnement des autres zones, resolution de noms           4/4
```

### Quarantaine, la preuve centrale

```
vm-rssi hors quarantaine   Internet PASSE     telemetrie EMISE
vm-rssi en quarantaine     Internet COUPE     telemetrie EMISE
```

La machine est coupée du monde **et reste observée**. C'est exactement ce que
l'isolation locale de l'agent ne sait pas faire, puisqu'elle coupe aussi la
supervision.

---

## 8. Point ouvert : authentification des collecteurs

Le chemin réseau est bon — `POST /ingest` répond en 2 ms depuis n'importe quelle
zone autorisée. Les collecteurs reçoivent en revanche un **HTTP 401 « Token ou
signature invalide »**.

Ce qui a été écarté :

- l'adresse du SOC : `config.json` portait encore `10.50.0.1`, devenue celle du
  pare-feu. Corrigée en `10.50.0.2` sur les quatre machines ;
- le jeton porteur : son empreinte SHA-256 correspond exactement à
  `agents.token_hash` en base ;
- le statut : les quatre agents sont `actif`, pas `isole` ;
- le réseau : `/health` et `/ingest` répondent depuis les zones.

Reste donc la signature HMAC. Deux agents sont en schéma `derived`
(POSTE-RSSI-01, POSTE-MENACE-vrai) et deux en `legacy` (SRV-APP-GOV-01,
SRV-ANTILOPE-01). Le serveur redérive la clé des premiers depuis le secret
maître ; si la clé locale ne correspond plus, le lot est rejeté.

La voie la plus sûre est de refaire l'enrôlement des quatre agents, qui
régénère jeton et clé de façon cohérente des deux côtés.

---

## 9. Ce qui se fait dans l'interface web

Adresse : **https://10.50.0.1** — depuis l'hôte, ou depuis vm-rssi (zone
d'administration). Aucune autre zone n'y a accès.

**Identifiants : `root` / le mot de passe choisi à l'installation.**

Le certificat est auto-signé par l'appliance : le navigateur avertit, il faut
accepter l'exception. C'est le comportement attendu d'une PKI interne.

> L'assistant de configuration initiale a été **désarmé** le 28 août
> (`trigger_initial_wizard` retiré de `config.xml`). Son étape « LAN » aurait
> réécrit l'adressage des sept interfaces. Ne pas le relancer.

### 9.1 Créer la clé d'API du moteur SOAR — bloquant

**System → Access → Users**, éditer **nexus-soar** (le crayon).

Le compte porte déjà une clé de remplissage qui ne fonctionne pas : OPNsense
stocke l'empreinte du secret, et cette empreinte ne peut pas être calculée hors
de l'appliance.

1. Dans **API keys**, supprimer la ligne existante (la corbeille).
2. Cliquer **+** pour en créer une : OPNsense télécharge aussitôt un fichier
   `apikey.txt`. **C'est le seul moment où le secret est lisible.**
3. **Save**.

Reporter le couple dans le `.env` du cœur SOC :

```
OPNSENSE_KEY=<key du fichier>
OPNSENSE_SECRET=<secret du fichier>
```

Ne pas toucher aux privilèges : `page-firewall-alias-edit` et
`page-diagnostics-tables`, rien de plus. Un moteur de réponse compromis doit
pouvoir modifier deux listes, pas reconfigurer un pare-feu.

> **Corrigé le 28 août.** La configuration générée portait
> `page-firewall-alias` et `page-firewall-alias-util` : ces deux noms n'existent
> pas dans OPNsense. L'authentification réussissait, l'autorisation échouait, et
> l'API répondait `403 Forbidden` — un code qu'on impute volontiers à la clé
> alors qu'il ne parle que des droits. Les noms exacts se relisent dans
> `/usr/local/opnsense/mvc/app/models/OPNsense/Core/ACL/ACL.xml` : c'est
> `page-firewall-alias-edit` qui couvre `api/firewall/alias/*` et
> `page-diagnostics-tables` qui couvre `api/firewall/alias_util/*`.
> `opnsense-generer-config.py` a été corrigé.

Vérification depuis l'hôte :

```bash
curl -sk -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" \
  https://10.50.0.1/api/firewall/alias_util/list/nexus_quarantaine
```

Une réponse JSON, même avec une liste vide, vaut confirmation.

### 9.2 Activer Suricata

**Services → Intrusion Detection → Administration**, onglet **Settings** :

- **Enabled** : coché
- **IPS mode** : décoché pour commencer — en détection seule, une règle trop
  large ne coupe pas la démonstration
- **Interfaces** : LAN_APP, LAN_SENS, LAN_ADM, LAN_MEN
- **Apply**

Onglet **Download** : cocher les jeux voulus, puis **Download & Update
Rules**.

> **Fait le 28 août**, en configuration plutôt qu'à la souris, avec trois
> décisions qui méritent d'être défendues à l'oral.
>
> **Trois jeux de règles, pas trente.** `emerging-scan`,
> `emerging-attack_response` et `emerging-exploit` : 2,3 Mio. Le premier essai
> incluait `emerging-malware` — 17,5 Mio à lui seul — et l'appliance a
> **redémarré** pendant l'installation des règles. Elle a 4 Gio ; une sonde qui
> tombe ne détecte rien. Ces règles visent d'ailleurs la commande-et-contrôle
> vers Internet, que les zones internes n'atteignent pas : leur coût n'aurait
> été payé par aucune détection. `emerging-trojan` et `emerging-policy` ont
> disparu d'ET Open 8.0.
>
> **La zone menace est déclarée hors du réseau interne.** `HOME_NET` vaut les
> cinq zones **sauf** 10.50.50.0/24. Les règles ET Open sont orientées « externe
> vers interne » : tant que l'attaquant du lab était déclaré interne, aucune ne
> pouvait se déclencher — Suricata voyait 22 000 paquets et ne disait rien.
> Déclarer la zone menace comme extérieure, c'est décrire ce qu'elle est.
>
> **Écrire `config.xml` ne suffit pas.** Le téléchargeur de règles lit
> `/usr/local/etc/suricata/rule-updater.config`, un fichier généré. Sans
> `configctl template reload OPNsense/IDS`, il reste vide et
> `configctl ids update` répond `OK` sans rien télécharger.

### 9.3 Ce qu'on peut vérifier au passage

- **Firewall → Aliases** : les quatre alias, dont `nexus_block` et
  `nexus_quarantaine` vides tant que le SOAR n'a rien décidé.
- **Firewall → Rules** (`/ui/firewall/filter`, chercher `NEXUS`) : la règle de
  télémétrie doit rester **au-dessus** de la règle de rejet. Si l'ordre
  s'inverse, la quarantaine coupe aussi l'observation. L'ancienne adresse
  `firewall_rules.php?if=…` n'existe plus en 26.7.
- **Firewall → Log Files → Live View** : filtrer sur `10.50.30.0/24` pour voir
  les rejets de la zone sensible en direct. C'est la vue à montrer pendant la
  soutenance.

### 9.4 À ne pas faire

- Ne pas lancer l'assistant de configuration.
- Ne pas modifier les interfaces ni leurs adresses : elles sont générées par
  `opnsense-generer-config.py`, et une retouche manuelle serait écrasée au
  prochain envoi de configuration.
- Ne pas activer le serveur DHCP sur les zones : les machines ont des adresses
  fixes, et un bail pourrait entrer en conflit.

## 10. Séance du 28 août 2026 : le pare-feu est piloté, et c'est prouvé

La clé d'API du compte `nexus-soar` a été créée dans l'interface et reportée
dans `.env` — le fichier ignoré par git, jamais `.env.cenadi` qui est suivi.
Trois défauts ont été trouvés en chemin ; aucun n'était visible sans essayer
réellement de piloter l'appliance.

### 10.1 La zone du cœur SOC échappait à la matrice de flux

C'est le plus sérieux. La première recette de quarantaine a échoué sur une
seule sonde : `10.50.40.40` était bien dans l'alias, les états étaient purgés,
et le cœur SOC continuait pourtant à joindre la machine isolée.

OPNsense 26 tient **deux jeux de règles**. L'ancien, `<filter>`, est celui que
génère `opnsense-generer-config.py`. Le nouveau,
`<OPNsense><Firewall><Filter>`, est posé à l'installation — et il est chargé
**en premier**, avec des règles `quick`. Il contenait les deux règles d'usine
« Default allow LAN to any », portant sur LAN_MGMT :

```
pass in quick on vtnet1 inet from (vtnet1:network) to any    ← avant tout le reste
```

Autrement dit, le cœur SOC pouvait atteindre n'importe quoi : la liste blanche
de sortie, le refus par défaut et les rejets de quarantaine ne s'appliquaient
pas à lui. La démonstration de la matrice de flux aurait été fausse sur la zone
la plus sensible du dispositif.

Les deux règles sont **désactivées** plutôt que supprimées : elles restent
visibles, barrées, dans l'interface, ce qui documente la décision au lieu de
l'effacer. Les règles anti-verrouillage (ssh/http/https vers l'appliance
elle-même) sont d'une autre nature — générées par `filter.inc` — et n'ont pas
été touchées : l'accès à l'interface reste garanti.

Sauvegarde avant modification : `/conf/config.avant-regles-defaut.xml`.

### 10.2 Les rejets de réponse ne laissaient aucune trace

Les quatre règles de rejet NEXUS — quarantaine sortante, quarantaine entrante,
IOC en source, IOC en destination — étaient chargées sans `log`. Une décision de
réponse qui ne laisse pas de trace n'est pas auditable : impossible de montrer
au RSSI ce que la quarantaine a effectivement empêché, et la vue temps réel
serait restée vide pendant la soutenance.

Les vingt-quatre règles (quatre rejets × six zones) journalisent désormais.
`opnsense-generer-config.py` porte un paramètre `journal=` pour que la
régénération conserve ce comportement. Sauvegarde :
`/conf/config.avant-journal.xml`.

### 10.3 Suricata voyait tout et ne disait rien

Voir le bloc de la section 9.2. Trois causes empilées : les règles n'étaient
pas installées faute de rechargement des gabarits, le jeu retenu était trop
lourd pour l'appliance, et `HOME_NET` englobait la zone menace, ce qui rendait
inerte l'intégralité d'un jeu de règles orienté « externe vers interne ».

### 10.4 Ce qui est prouvé, et par quoi

`bash lab-cenadi/scenarios/06-preuve-quarantaine.sh` — **11 contrôles sur 11**.
Le scénario appelle l'API avec le compte de service, puis observe des deux
côtés de la frontière : de l'intérieur par l'agent invité QEMU, dont le canal
ne traverse pas le pare-feu et reste donc lisible quand la machine est isolée ;
de l'extérieur depuis le cœur SOC. Il conclut sur des **codes de sortie**.

| État | Résolution de noms | Télémétrie vers le SOC | Joignable depuis le SOC |
|---|---|---|---|
| Avant | passe | passe | oui |
| **En quarantaine** | **coupée** | **passe** | **non** |
| Après levée | passe | passe | oui |

C'est la propriété centrale du dispositif : la quarantaine isole sans aveugler.

Suricata, lui, a été mis à l'épreuve par une reconnaissance réelle lancée
depuis KaliPrime vers trois zones — **onze alertes** : `ET SCAN Potential SSH
Scan`, `ET SCAN Suspicious inbound to mySQL port 3306`, `ET SCAN Suspicious
inbound to PostgreSQL port 5432`. Interface LAN_MEN, source 10.50.50.50.

Les captures sont dans `00_Documents/figures/preuves/` :

| Fichier | Ce qu'il établit |
|---|---|
| `00-tableau-de-bord.png` | Sept interfaces, adressage des six zones |
| `01-avant-alias-quarantaine.png` | Table `nexus_quarantaine` vide |
| `02-pendant-alias-quarantaine.png` | Les deux adresses posées **par l'API** |
| `02-pendant-journal-pare-feu.png` | Rejets en rouge, télémétrie en vert, simultanément |
| `03-apres-alias-quarantaine.png` | Table vidée après la levée |
| `04-compte-service-nexus-soar.png` | Le compte de service et son périmètre |
| `05-aliases-nexus.png` | Les quatre alias de réponse |
| `06-regles-reponse-nexus.png` | Les 34 règles NEXUS chargées |
| `08-suricata-parametres.png` | Détection seule, quatre zones internes |
| `09-suricata-alertes.png` | Les onze détections, horodatées |

`02-pendant-journal-pare-feu.png` est la capture à projeter : on y lit dans la
même fenêtre les paquets rejetés des deux machines en quarantaine **et** leur
télémétrie qui continue d'atteindre 10.50.0.2:8000.

### 10.5 Outillage écrit pour cette séance

- `lab-cenadi/scripts/qga-exec.py` — exécute une commande dans une machine par
  l'agent invité QEMU. Aucun identifiant, aucun port réseau : la seule voie qui
  reste quand la machine est en quarantaine.
- `lab-cenadi/scripts/opnsense-captures.py` — pilote l'interface web par le
  protocole CDP de Chrome, en bibliothèque standard seulement. Ni Playwright ni
  Selenium : le projet ne prend pas de dépendance externe. Une centaine de
  lignes de WebSocket contre un paquet à installer.
- `lab-cenadi/scenarios/06-preuve-quarantaine.sh` — la recette ci-dessus.

Deux pièges rencontrés, à ne pas réapprendre :

- `document.querySelector('form').submit()` n'envoie **pas** le couple
  nom/valeur du bouton. `index.php` n'entre dans la vérification que si `login`
  est présent : sans lui, la page revient avec « Wrong username or password »
  alors qu'aucune authentification n'a été tentée, et le journal d'audit reste
  muet. Il faut **cliquer** le bouton.
- La page des tables de pare-feu s'ouvre sur `bogons`. Une capture prise sans
  sélectionner l'alias prouve l'état d'une table qui ne concerne personne.

### 10.6 Les deux points ouverts, réglés le 28 août au soir

**Le 401 n'était pas un problème de signature.** Le message
« Token ou signature invalide » désignait la signature ; la cause était la date.
Les quatre jetons, émis pour 168 heures les 16 et 19 août, avaient **expiré**.
`_verify_ingest` teste l'échéance bien avant d'examiner la moindre signature —
un message trompeur nous a fait chercher pendant des heures du côté du HMAC.

Le mauvais réflexe aurait été de repousser la date en base. Le réenrôlement est
fait proprement par `lab-cenadi/scripts/reenroler-agents.py` :

- jetons réémis pour un an, non à usage unique — un collecteur continu émet en
  boucle, un jeton à usage unique s'invaliderait au premier lot ;
- les cinq agents passent en schéma **`derived`** : SRV-APP-GOV-01 et
  SRV-ANTILOPE-01 étaient encore en `legacy`, c'est-à-dire avec une signature
  mathématiquement invérifiable ;
- **cinq**, et non quatre : le collecteur du cœur SOC lui-même
  (`NoxTheMachine`) avait expiré comme les autres et se taisait depuis neuf
  jours sans que rien ne le signale. Un SOC qui ne se supervise pas lui-même a
  un angle mort à l'endroit exact où il ne peut pas se le permettre ;
- l'enrôlement se fait **depuis l'hôte**. Le mot de passe administrateur du SOC
  ne descend jamais dans une machine supervisée : seul le couple jeton/clé
  produit pour elle y est déposé. Un collecteur compromis ne doit pas livrer de
  quoi en enrôler d'autres.

Le parc réel étant migré, **`INGEST_STRICT_HMAC=1`** a été activé : tout lot
dont la signature n'est pas vérifiable est désormais refusé. C'est ce que le
code attendait depuis sa conception. Les quatre agents encore marqués `legacy`
par `v_agents_hmac_a_migrer` sont des jeux de démonstration vus pour la dernière
fois le 22 juillet — aucune machine derrière eux.

**L'annuaire est déployé et pilotable.** OpenLDAP tourne sur vm-app-gov, écoute
sur 10.50.20.20:389, et `bash lab-cenadi/scenarios/07-preuve-gel-annuaire.sh`
passe **7 contrôles sur 7**. Voir `lab-cenadi/04-annuaire-vm-app-gov.md`.

Un obstacle méritait mieux qu'un contournement : la zone applicative n'a pas
d'Internet, et `apt-get install slapd` ne pouvait donc pas aboutir. Ouvrir une
sortie pour la commodité d'un installateur aurait défait l'architecture qu'on
prétend démontrer. Le cœur SOC sert désormais de point de distribution
logicielle — `lab-cenadi/scripts/paquets-hors-ligne.sh` résout les dépendances
contre l'état dpkg réel de la machine cible, dans sa version de distribution à
elle, et livre le strict nécessaire. C'est ainsi que fonctionne un système
d'information cloisonné.

**`update.opnsense.org` reste injoignable** depuis ce réseau — l'hôte lui-même
n'y accède pas. Sans conséquence : ET Open, lui, répond.

### 10.7 État vérifiable en une commande

**Soixante-douze contrôles joués, tous conformes**, plus une sonde signalée
« non éprouvée » quand l'agrégation anti-doublon empêche de la jouer — ni
réussie, ni échouée, parce qu'elle n'a pas pu être exécutée. Transcriptions dans
`00_Documents/figures/preuves/` — `recettes.txt` pour les trois premières,
`recette-connecteurs.txt` pour la phase 2 :

| Recette | Contrôles | Ce qu'elle établit |
|---|---|---|
| `05-matrice-de-flux.sh` | 12 | Le cloisonnement des six zones |
| `06-preuve-quarantaine.sh` | 11 | Le pare-feu obéit au SOAR, la télémétrie survit |
| `07-preuve-gel-annuaire.sh` | 7 | L'identité se suspend, se rend, et rien d'autre |
| `08-preuve-connecteurs.sh` | 22 | La plateforme applique, vérifie, lève — et refuse |
| `09-preuve-dossiers.sh` | 9 | L'ingestion ne dépend pas d'IRIS, et rien ne se perd |
| `10-preuve-discussion.sh` | 11 | Le canal s'ouvre, et la messagerie ne bloque rien |

`08` est la recette de la phase 2 : elle ne touche jamais un équipement
directement, tout passe par `/analyst`. Elle éprouve aussi ce que la plateforme
**refuse** — isoler le cœur SOC lui-même, exécuter `block_ip` sur un nom d'hôte —
parce qu'une réponse automatique se juge d'abord à ses refus.
