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

Le collecteur tourne sous l'utilisateur `noxtheteenager`, sa configuration vit
dans `~/.nexus-agent` — pas de `sudo` :

```bash
cd ~/Documents/Projets/NEXUS_SOC
.venv/bin/python Lot1_Agent_Go/nexus_collector.py --enroll \
    --hostname NoxTheMachine \
    --perimetre "Réseau/LAN CENADI" \
    --email <votre-admin> --password <votre-mot-de-passe>

sudo systemctl restart nexus-collector.service
journalctl -u nexus-collector -n 10 --no-pager     # les 401 doivent cesser
```

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
sudo mkdir -p /opt/nexus-agent
sudo mv /tmp/nexus_collector.py /opt/nexus-agent/
export SOC_URL=http://192.168.122.1:8000
sudo -E python3 /opt/nexus-agent/nexus_collector.py --enroll \
     --hostname POSTE-RSSI-01 --perimetre "Réseau/LAN CENADI" \
     --email <votre-admin> --password <votre-mot-de-passe>
```

`SOC_URL` est indispensable : sans lui le collecteur vise `127.0.0.1:8000`,
c'est-à-dire la VM elle-même. C'est la première cause d'échec d'enrôlement.

Puis le service, pour qu'il survive au redémarrage — c'est ce qui manque
aujourd'hui à tout le parc :

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

### 2.3 KaliPrime — pas d'adresse sur le réseau de gestion

`KaliPrime` a deux interfaces (`default` et `nexus-cenadi-men`) mais **n'apparaît
pas dans la table ARP de `virbr0`** : sa patte de gestion n'a pas d'adresse. À
vérifier depuis sa console :

```bash
ip -br a          # la patte sur virbr0 doit porter une 192.168.122.x
sudo dhclient -v <interface>
```

Une fois joignable, même commande qu'en 2.2 avec
`--hostname POSTE-MENACE-01`. C'est la seule machine de la zone Menace : sans
elle, aucune attaque simulée n'est observée à la source.

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
