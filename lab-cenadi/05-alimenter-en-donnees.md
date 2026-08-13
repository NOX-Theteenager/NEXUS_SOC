# Alimenter NEXUS SOC en données

Ce que faire tourner sur les VM pour que la plateforme ait matière à analyser.

---

## 1. D'abord le vrai problème : la continuité

Mesure du 12/08/2026 :

| Agent | Heures de collecte sur 24 |
|---|---|
| SRV-APP-GOV-01 | 9,7 |
| SRV-ANTILOPE-01 | 7,1 |

Les VM sont éteintes le reste du temps. **Aucun script ne compense ça** — c'est
la cause des jours sans mesure sur le portail et des six interruptions visibles
sur les graphiques de supervision.

Avant tout le reste : laisser les VM allumées, et vérifier que le collecteur
redémarre bien avec elles.

```bash
systemctl is-enabled nexus-collector.service   # doit répondre : enabled
systemctl status  nexus-collector.service
journalctl -u nexus-collector -n 30 --no-pager
```

Si le service n'est pas `enabled`, il ne survit pas au redémarrage de la VM :

```bash
sudo systemctl enable --now nexus-collector.service
```

---

## 2. Rendre observables NoxTheMachine, vm-rssi et KaliPrime

### 2.0 D'abord redémarrer le serveur — sinon l'enrôlement échoue

L'unicité `(périmètre, hôte)` posée sur `agents` fait échouer tout réenrôlement
tant que le serveur n'a pas chargé la clause `ON CONFLICT` correspondante.
**Cette étape n'est pas optionnelle :**

```bash
sudo systemctl restart nexus-soc.service
```

### 2.1 NoxTheMachine — jeton expiré, pas un agent mort

Le collecteur de l'hôte **tourne** et émet toutes les 60 s, mais le serveur
refuse ses lots depuis le 29/07 :

```
✗ HTTP 401 {"detail":"Token ou signature invalide"}
```

Son jeton d'enrôlement a expiré le **29/07 à 21 h 36**, ce qui correspond
exactement à sa dernière émission. Ce n'est ni un défaut de signature, ni un
problème de HMAC : un jeton de 168 h qui arrive à terme.

**L'enrôlement exige un compte `admin_plateforme`.** La base n'en contient qu'un
seul, `admin@nexussoc.cm` ; les comptes `resp.sigipes@` et `resp.antilope@` sont
des responsables de périmètre et seront refusés. Tout autre courriel est inconnu
et provoque un 401 sur `/auth/token` — c'est la connexion qui échoue, pas
l'enrôlement.

Le collecteur tourne sous l'utilisateur `noxtheteenager`, sa configuration vit
dans `~/.nexus-agent` — pas de `sudo` :

```bash
cd ~/Documents/Projets/NEXUS_SOC
.venv/bin/python Lot1_Agent_Go/nexus_collector.py --enroll \
    --hostname NoxTheMachine \
    --perimetre "Réseau/LAN CENADI" \
    --email admin@nexussoc.cm --password <mot-de-passe-admin>

sudo systemctl restart nexus-collector.service     # indispensable :
journalctl -u nexus-collector -n 10 --no-pager     # le jeton est lu au démarrage
```

Le redémarrage n'est pas cosmétique : `charger_conf()` n'est appelée qu'au
lancement. Sans lui, le processus continue d'émettre avec le jeton expiré qu'il
a en mémoire, et les 401 se poursuivent malgré un enrôlement réussi.

Le réenrôlement **renouvelle** la ligne existante, il n'en crée pas une seconde,
et bascule l'agent de `legacy` vers `derived` — sa signature devient réellement
vérifiable.

### 2.2 vm-rssi — SSH fermé, passer par la console

`vm-rssi` (192.168.122.25) répond au ping mais **son port 22 est fermé** : c'est
l'Ubuntu Desktop, où OpenSSH n'est pas installé par défaut. Deux voies.

Ouvrir SSH depuis la fenêtre virt-manager de la VM, puis opérer à distance :

```bash
sudo apt install -y openssh-server && sudo systemctl enable --now ssh
```

Ou tout faire depuis la console de la VM, sans SSH :

Le serveur **ne distribue pas** le collecteur : `/install`, `/agent/…` et
`/app/nexus_collector.py` répondent tous 404. Le fichier doit être copié depuis
l'hôte. Une fois SSH ouvert :

```bash
# depuis l'HÔTE
scp Lot1_Agent_Go/nexus_collector.py <utilisateur>@192.168.122.25:/tmp/

# sur la VM
sudo mkdir -p /opt/nexus-agent /etc/nexus-agent
sudo mv /tmp/nexus_collector.py /opt/nexus-agent/
export SOC_URL=http://192.168.122.1:8000
export NEXUS_AGENT_DIR=/etc/nexus-agent
sudo -E python3 /opt/nexus-agent/nexus_collector.py --enroll \
     --hostname POSTE-RSSI-01 --perimetre "Réseau/LAN CENADI" \
     --email admin@nexussoc.cm --password <mot-de-passe-admin>
```

Deux variables, et les deux comptent.

`SOC_URL` : sans lui le collecteur vise `127.0.0.1:8000`, c'est-à-dire la VM
elle-même.

`NEXUS_AGENT_DIR` : **à définir dès l'enrôlement**. Avec `sudo -E`, `HOME` est
conservé, donc la configuration atterrit dans `~/.nexus-agent` de l'utilisateur
qui a lancé la commande — par exemple `/home/rssi/.nexus-agent/config.json`. Le
service systemd ci-dessous lit `/etc/nexus-agent` et échouerait sur
« Agent non enrôlé ». Si l'enrôlement a déjà eu lieu sans cette variable :

```bash
sudo mkdir -p /etc/nexus-agent
sudo cp ~/.nexus-agent/config.json /etc/nexus-agent/
```

### Enrôler ne suffit pas : il faut collecter

L'enrôlement crée la ligne d'agent, rien de plus. Tant qu'aucune collecte n'a été
envoyée, `vu_le` reste NULL et la console affiche **hors ligne** — à juste titre.

```bash
# vérification immédiate
sudo -E python3 /opt/nexus-agent/nexus_collector.py --once
```

La machine doit passer « actif » dans la console dans les deux minutes
(`AGENT_STALE_SECONDS`). Puis le service, pour qu'il survive au redémarrage —
c'est ce qui manque aujourd'hui à tout le parc :

```bash
sudo tee /etc/systemd/system/nexus-collector.service >/dev/null <<'EOF'
[Unit]
Description=NEXUS SOC — collecteur de télémétrie
After=network-online.target

[Service]
Type=simple
Environment=SOC_URL=http://192.168.122.1:8000
Environment=NEXUS_AGENT_DIR=/etc/nexus-agent
ExecStart=/usr/bin/python3 /opt/nexus-agent/nexus_collector.py --loop --interval 30
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now nexus-collector.service
```

### 2.3 KaliPrime — le poste compromis

C'est la machine de la zone Menace, décrite par l'architecture comme le « poste
compromis (simulation) ». L'enrôler paraît contre-intuitif — on ne met pas
d'agent chez l'attaquant. Mais dans le scénario que porte ce projet, la menace
est **interne** : un poste bureautique du CENADI compromis, pas un adversaire
extérieur. Sans capteur dessus, l'attaque n'est observée qu'à l'arrivée, jamais à
la source, et la chaîne ATT&CK perd ses premières étapes — celles qui font toute
la démonstration.

#### a. La route existe déjà — passer par la zone Menace

`eth0` (patte de gestion sur `virbr0`) est UP mais sans adresse : aucun bail
DHCP, aucune entrée ARP. Inutile d'insister, **`eth1` suffit** :

```
eth1   UP   10.50.50.50/24
```

C'est l'adresse fixe de la zone Menace prévue par l'architecture, et l'hôte tient
`10.50.50.1` sur ce même bridge. Vérifié : l'hôte joint 10.50.50.50 en 0,17 ms,
et le SOC écoute sur `0.0.0.0:8000` — donc sur toutes ses interfaces, y compris
celle-là.

Le réseau `nexus-cenadi-men` est déclaré **sans `<forward>`** : il est isolé du
reste, mais l'hôte étant sur le bridge, le dialogue machine ↔ hôte reste possible.
C'est exactement la propriété recherchée — le poste compromis parle au SOC et à
personne d'autre.

Depuis la console de KaliPrime, confirmer avant d'aller plus loin :

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://10.50.50.1:8000/health   # attendu : 200
```

Si cette commande échoue alors que le ping passe, c'est le pare-feu de l'hôte
qu'il faut regarder, pas le réseau de la VM.

#### b. Copier le collecteur

Depuis l'**hôte**, par la zone Menace :

```bash
scp Lot1_Agent_Go/nexus_collector.py kali@10.50.50.50:/tmp/
```

Si SSH n'écoute pas sur Kali : `sudo systemctl enable --now ssh`.

#### c. Enrôler

Il n'existe pas de périmètre « Menace » : la base n'en contient que trois
(`ANTILOPE`, `SIGIPES`, `Réseau/LAN CENADI`). Un poste bureautique compromis
appartient au LAN — c'est `Réseau/LAN CENADI`. Créer un quatrième périmètre
dédié est possible, mais brouillerait la démonstration : la matrice de flux
oppose des zones réseau, pas des périmètres supervisés.

```bash
sudo mkdir -p /opt/nexus-agent /etc/nexus-agent
sudo mv /tmp/nexus_collector.py /opt/nexus-agent/
export SOC_URL=http://10.50.50.1:8000        # zone Menace, pas 192.168.122.1
export NEXUS_AGENT_DIR=/etc/nexus-agent
sudo -E python3 /opt/nexus-agent/nexus_collector.py --enroll \
     --hostname POSTE-MENACE-01 --perimetre "Réseau/LAN CENADI" \
     --email admin@nexussoc.cm --password <mot-de-passe-admin>

sudo -E python3 /opt/nexus-agent/nexus_collector.py --once
```

Puis le service systemd du §2.2, en remplaçant l'adresse du SOC par
`http://10.50.50.1:8000`.

#### d. Ce que ça change pour la démonstration

Avec un capteur sur le poste compromis, les techniques d'**Initial Access**,
d'**Execution** et de **Defense Evasion** deviennent observables là où elles se
produisent. C'est la condition pour que le moteur reconstitue une chaîne
complète : il exige trois tactiques distinctes en trente minutes, et les
premières ne sont visibles que depuis la machine attaquante.

Attention toutefois : `--simulate chaine` lancé **depuis KaliPrime** produira une
chaîne attribuée à `POSTE-MENACE-01`. Pour une démonstration racontant une
exfiltration depuis un serveur métier, le lancer plutôt depuis `vm-app-gov`.

### 2.4 Les cinq lignes de démonstration

`POSTE-RH-01`, `POSTE-RH-07`, `POSTE-SOLDE-01`, `SRV-LAN-01` et
`SRV-SIGIPES-01` n'ont aucune machine derrière : elles n'émettront jamais. Les
garder gonfle artificiellement le parc et le ratio « agents en ligne ». À
supprimer quand vous jugerez la démonstration prête.

---

## 3. Le bruit de fond — ce qui manquait

Les scénarios 1 à 3 produisent des **incidents**. Il manquait le quotidien d'un
serveur qui travaille. Sans lui, les modèles n'apprennent le normal que sur une
VM au repos, et le tableau de bord montre des lignes plates coupées de pics.

```bash
# sur vm-app-gov, vm-antilope ou vm-rssi
sudo bash lab-cenadi/scenarios/04-activite-de-fond.sh --duree 240
sudo bash lab-cenadi/scenarios/04-activite-de-fond.sh --install   # en permanence
sudo bash lab-cenadi/scenarios/04-activite-de-fond.sh --purge     # tout retirer
```

Le script **n'écrit rien en base et n'envoie aucune télémétrie**. Il fait
réellement travailler la machine — documents écrits et relus, archives
compressées, rotation, requêtes vers le SOC — et c'est l'agent qui mesure, comme
pour n'importe quelle charge. L'activité se réduit hors 8 h–18 h, parce que le
Modèle 2 utilise cette bande horaire et qu'une charge plate 24 h/24 lui
apprendrait un normal qui n'existe dans aucune administration.

Il reste volontairement **sous les seuils** : transferts sous 1 Mo, aucun compte
créé, aucun port C2, aucune lecture de fichier sensible. S'il déclenche une
alerte, c'est un faux positif — et c'est une mesure utile de la qualité du
modèle, pas un défaut du script.

---

## 4. Déclencher une détection précise

Chaque ligne ci-dessous est une **action réelle** sur la machine. L'agent la
mesure, il ne la reçoit pas toute faite.

### Modèle 2 — UEBA (features de machine)

| Pour faire monter | Action réelle sur la VM |
|---|---|
| `nb_exports`, `volume_donnees_exportees` | transférer un fichier de plus de 1 Mo vers une autre machine |
| `nb_creations_compte` | `sudo useradd -m agent-test` |
| `nb_acces_dossiers_sensibles` | `sudo cat /etc/shadow /etc/sudoers /etc/gshadow` |
| `nb_connexions` | ouvrir plusieurs connexions TCP simultanées |
| `nb_actions_hors_heures` | exécuter n'importe laquelle de ces actions avant 8 h ou après 18 h |

### Moteur de corrélation — chaîne d'attaque

Le moteur exige **3 tactiques distinctes** dans une fenêtre de 30 minutes, ou
`Execution` + `Command and Control`, ou `Impact`, ou `Defense Evasion` +
`Persistence`. Une seule technique ne lève pas d'incident.

| Technique | Action réelle |
|---|---|
| T1204 · Initial Access | créer `~/Téléchargements/facture.pdf.exe` |
| T1059 · Execution | lancer un processus nommé `nc`, `ncat` ou `powershell` |
| T1027 · Defense Evasion | exécutable dans `/tmp`, ou argument base64 de 40+ caractères |
| T1136 · Persistence | `sudo useradd` |
| T1005 · Collection | toucher un fichier dont le chemin contient `finance`, `budget`, `sigipes`, `sydonia` ou `contribuable` |
| T1083 · Discovery | toucher des fichiers dans `/etc`, `/proc` ou `/var/log` |
| T1071 · Command and Control | connexion TCP **établie** vers un port 4444, 6667, 1337, 9001, 31337 ou 5555 |

Deux pièges de terrain :

- La connexion C2 doit être **établie au moment du relevé** (toutes les 30 s).
  Un `nc` qui se referme aussitôt passe inaperçu. Garder la session ouverte :
  `nc -l 4444` d'un côté, `nc <ip> 4444` de l'autre, pendant plus d'une minute.
- Le collecteur ne surveille que `/etc,/home,/tmp,/var/log,/srv` — réglable par
  `NEXUS_WATCH_DIRS`. Un fichier créé ailleurs ne produit aucun événement.

### La chaîne complète, en une commande

```bash
sudo -E python3 /opt/nexus-agent/nexus_collector.py --simulate chaine
```

Six événements bruts traversent `/ingest` signés, et c'est le moteur qui
reconstitue l'incident horodaté. Rien n'est écrit directement en base : c'est la
détection réelle qui travaille. Idéal en soutenance — vous la déclenchez devant
le jury plutôt que de montrer une donnée figée.

---

## 5. Ordre conseillé pour une soutenance

1. La veille : `--install` du bruit de fond sur les trois VM, et les laisser
   allumées. Le tableau de bord aura 24 h d'historique dense et continu.
2. Le jour même : `01-souverainete-datacenter.sh`, puis
   `03-exfiltration-solde.sh` pour montrer la détection UEBA.
3. Bouquet final : `--simulate chaine`, qui produit la chaîne ATT&CK horodatée
   et la proposition SOAR associée.
4. Ne pas oublier `04-activite-de-fond.sh --purge` après coup.
