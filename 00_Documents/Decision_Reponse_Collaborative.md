# Décision — réponse collaborative aux incidents

Statut : **validée le 17 août 2026.** Soutenance le **14 septembre 2026**.

Ce document fait foi pour tout ce qui touche au pare-feu, à l'exécution des
actions de réponse et à la gestion des dossiers d'enquête. Il complète
[MIGRATION.md](../MIGRATION.md), qui reste la référence de la refonte souveraine.

---

## 1. Ce qui est décidé

| Sujet | Avant | Après |
|---|---|---|
| Pare-feu de périmètre | pfSense, WAN désactivé | **OPNsense**, WAN actif et filtré |
| Routage inter-zone et ACL | MikroTik CHR | **OPNsense** (équipement unique) |
| Sortie Internet | aucune, pour toutes les zones | **par zone**, refus par défaut |
| Exécution des actions SOAR | aucune, commande affichée puis attestée | **connecteurs réels** OPNsense et LDAP |
| Gestion des dossiers d'enquête | inexistante | **DFIR-IRIS** (LGPL-3.0) |
| Orchestrateur d'analyseurs | Cortex envisagé | **retiré** |
| Enrichissement d'indicateurs | VirusTotal | **MISP auto-hébergé**, VirusTotal sous condition |
| Discussion d'incident | aucune | **Mattermost**, canal par dossier |

### Pourquoi OPNsense remplace MikroTik, et pas pfSense

Le §0 de [03-quarantaine-blocage.md](../lab-cenadi/03-quarantaine-blocage.md)
l'établissait déjà : le trafic latéral entre zones ne remonte jamais jusqu'au
pare-feu de périmètre. Bloquer une adresse sur pfSense coupait donc la machine
du cœur SOC sans la couper de ses voisines. Remplacer pfSense en gardant
MikroTik n'aurait rien changé à ce défaut.

OPNsense porte désormais les deux rôles. Un seul équipement route entre les
zones, applique la matrice de flux, tient les listes de réponse et expose
l'API qui les pilote. La licence gratuite de MikroTik CHR plafonnait par
ailleurs chaque interface à 1 Mbit/s, contrainte que la documentation
précédente passait sous silence.

### Pourquoi DFIR-IRIS et pas TheHive

TheHive 5 n'est pas open source : son code n'est pas publié, et l'édition
gratuite se limite à 2 utilisateurs et 1 organisation. Pour une plateforme dont
l'argument est que le CENADI possède, audite et modifie son outil, ce composant
aurait été le seul que le CENADI ne pourrait ni auditer ni modifier.

DFIR-IRIS est publié sous **LGPL-3.0**, activement maintenu (dernier commit du
dépôt `dfir-iris/iris-web` le 13 juillet 2026), sans plafond d'utilisateurs ni
d'organisations. Il tourne sur PostgreSQL, ce qui préserve la décision
d'architecture n° 2 : pas d'Elasticsearch en plus de l'indexeur Wazuh.

Sa notion de `customer` porte des droits par client. Nos périmètres supervisés
(SIGIPES, ANTILOPE, réseau CENADI) s'y projettent directement : le cloisonnement
ne s'arrête plus à la frontière de NEXUS, il se prolonge dans l'outil d'enquête.

L'interface `GestionDossier` reste néanmoins abstraite, avec un adaptateur
TheHive prévu mais non déployé. L'intégration n'est captive d'aucun produit.

### Pourquoi Cortex est retiré

Cortex est un produit StrangeBee conçu pour TheHive. Aucun module Cortex
n'existe pour IRIS : les 19 dépôts de l'organisation `dfir-iris` couvrent MISP,
VirusTotal, IntelOwl, MWDB, EVTX et les webhooks, pas Cortex.

Ses deux fonctions se replacent sans perte :

- les **analyseurs** passent à `iris-misp-module`, sur un MISP auto-hébergé ;
- les **répondeurs** n'ont rien à remplacer, puisque NEXUS est le répondeur.
  `soar_audit`, la file d'approbation et les connecteurs de la phase 2 tiennent
  déjà ce rôle.

Faire transiter l'exécution par Cortex aurait ajouté une machine virtuelle Java,
un Elasticsearch et un second journal d'exécution susceptible de diverger du
nôtre. La migration `06_schema_soar_cible.sql` avait justement séparé la
décision de l'exécution pour supprimer cette ambiguïté.

---

## 2. Le modèle de sortie Internet

Le WAN d'OPNsense cesse d'être désactivé. Il devient l'objet de la
démonstration : la politique de sortie se prouve, alors qu'une absence de câble
ne prouve rien.

| Zone | Sortie Internet | Portée |
|---|---|---|
| Cœur SOC (mgmt) | **oui**, sortante seule | liste blanche de dépôts et de sources de renseignement, journalisée |
| DMZ interne | non | |
| Applicatif | non | les serveurs métier n'initient rien vers l'extérieur |
| **Sensible (ANTILOPE)** | **jamais** | air-gap inchangé, seule la télémétrie vers le SOC est permise |
| Admin (RSSI) | oui, filtrée | poste de travail réel |
| Menace | non | le canal de commande reste simulé en interne |

La zone Menace garde son isolement pour une raison de sûreté : une machine Kali
volontairement compromise n'a pas à joindre l'Internet réel depuis un poste de
travail personnel.

**Contrepartie assumée.** Dès qu'un enrichissement peut sortir, soumettre un
indicateur à VirusTotal revient à transmettre une empreinte issue d'un système
de l'État à une société étrangère. MISP auto-hébergé devient donc la source
primaire, et `VIRUSTOTAL_ENABLED` reste à `false` par défaut. L'appel externe
est un geste d'analyste, précédé d'un avertissement.

---

## 3. Budget mémoire

Mesuré sur l'hôte le 17 août 2026, machines virtuelles éteintes : 23 841 Mio au
total, 14 409 Mio disponibles, aucune pression mémoire (PSI à 0,00 sur les trois
fenêtres), 4 Go d'échange intacts. La carte mère accepte 64 Go sur 2 emplacements,
ce qui laisse une marge matérielle si le besoin apparaît.

| Poste | Mio | Nature |
|---|---:|---|
| Disponible, VMs éteintes | 14 409 | mesuré |
| OPNsense (Suricata activé) | −4 096 | recommandation éditeur, à créer |
| KaliPrime, sans session graphique | −2 048 | **appliqué le 17 août** |
| vm-rssi (bureau) | −2 048 | inchangé |
| vm-app-gov | −1 536 | **appliqué le 17 août** |
| vm-antilope | −1 024 | **appliqué le 17 août** |
| iris-web + worker + RabbitMQ | −1 250 | estimé |
| Mattermost (base dans nexus-postgres) | −400 | estimé |
| **Marge restante** | **≈ 2 000** | |

La pile TheHive aurait consommé environ 6 000 Mio, soit la totalité de cette
marge plus Suricata. Le choix d'IRIS finance l'inspection réseau du pare-feu.

### Application des allocations

Les trois ajustements sont inscrits dans la configuration persistante des
machines et prennent effet **au prochain démarrage** de chacune :

```bash
virsh -c qemu:///system setmem    KaliPrime   2097152KiB --config
virsh -c qemu:///system setmaxmem KaliPrime   2097152KiB --config
virsh -c qemu:///system setmem    vm-app-gov  1572864KiB --config
virsh -c qemu:///system setmaxmem vm-app-gov  1572864KiB --config
virsh -c qemu:///system setmem    vm-antilope 1048576KiB --config
virsh -c qemu:///system setmaxmem vm-antilope 1048576KiB --config
```

KaliPrime démarre désormais sans session graphique
(`systemctl set-default multi-user.target`, cible relue et constatée). Deux
gigaoctets suffisent aux scripts de scénario ; ils ne suffiraient pas à XFCE
accompagné d'un outil Java. Pour revenir au bureau, `systemctl set-default
graphical.target` et remonter la mémoire à 3 Go.

Contrôle après redémarrage :

```bash
for v in KaliPrime vm-app-gov vm-antilope vm-rssi; do
    virsh -c qemu:///system dominfo "$v" | awk -F: '/Used memory/{print "'"$v"' :"$2}'
done
```

---

## 4. Les phases

Sept phases, du 17 août au 14 septembre. Le gel fonctionnel est fixé au
**7 septembre** : au-delà, plus aucun code, uniquement le rapport et les
diapositives.

### Phase 0 — Alignement de la documentation et des figures
**17 au 18 août.**

Le dépôt décrit une architecture qui n'est pas celle qui tourne. C'est le
premier risque de la soutenance, avant tout choix de produit.

- réécriture des documents du lab autour d'OPNsense ;
- refonte des figures, avec distinction explicite entre architecture **cible** et
  état **déployé** ;
- `SOAR_COMMANDES` produit de la syntaxe OPNsense au lieu de RouterOS ;
- recensement des licences des nouveaux composants.

*Recette : plus une seule mention de MikroTik ou de pfSense hors historique ;
chaque figure porte sa mention cible/déployé.*

### Phase 1 — Topologie OPNsense
**19 au 23 août.**

- installation d'OPNsense, WAN plus six interfaces internes ;
- plan d'adressage `10.50.0.0/16` réellement appliqué, en remplacement du
  réseau libvirt à plat actuel ;
- matrice de flux du §2 de l'architecture, refus par défaut ;
- politique de sortie par zone du §2 ci-dessus ;
- alias `nexus_block` et `nexus_quarantaine`, compte d'API restreint ;
- Suricata sur les interfaces internes.

*Recette : depuis vm-antilope, `ping 8.8.8.8` et `ping 10.50.20.20` échouent,
`curl 10.50.0.2:8000/health` répond. Depuis le cœur SOC, le miroir de paquets
répond, un domaine hors liste blanche non.*

### Phase 2 — Connecteurs réels
**24 au 27 août.**

```
Lot4_SOAR/connecteurs/
    base.py           Protocol Connecteur : appliquer / lever / etat
    opnsense.py       API REST, clé et secret, empreinte TLS épinglée
    ldap_ppolicy.py   pwdAccountLockedTime via ldap3
    registre.py       action vers connecteur compétent
```

Endpoints `POST /analyst/execute/{id}` et `POST /analyst/revert/{id}`.

Trois garde-fous, repris des exigences déjà écrites dans le dépôt :

1. `execution` ne passe à `automatique` qu'après **relecture vérifiée** de
   l'alias ou de l'attribut LDAP. Un code HTTP 200 ne suffit pas.
2. En cas d'échec, `execution` reste `non_executee`, le motif est écrit dans
   `execution_note`, et la console affiche la commande manuelle comme
   aujourd'hui.
3. Réconciliation au démarrage : NEXUS repousse ses listes, pour qu'un
   redémarrage du pare-feu ne lève pas une quarantaine en silence.

*Recette : approuver un blocage dans la console fait apparaître l'adresse dans
l'alias OPNsense ; la machine cible perd le contact latéral et reste observée.
Couper OPNsense fait échouer l'exécution sans jamais mentir sur son résultat.*

> **Réalisée le 28 août 2026.** `bash lab-cenadi/scenarios/08-preuve-connecteurs.sh`
> — **22 contrôles sur 22**, transcription dans
> `00_Documents/figures/preuves/recette-connecteurs.txt`. Tout passe par
> `/analyst` : la recette n'appelle jamais un équipement directement.
>
> Quatre choses ont dû être ajoutées en chemin, qui ne figuraient pas au plan et
> qui comptent davantage que le code prévu.
>
> **L'audit portait un nom de machine, l'alias attend une adresse.** Personne ne
> stockait l'adresse des agents. La plateforme l'apprend désormais de sa propre
> télémétrie : `/ingest` écrit `agents.derniere_ip` à chaque lot. Une table de
> correspondance figée aurait dérivé au premier changement d'adressage.
>
> **Le cœur SOC est dans son propre inventaire.** `NoxTheMachine` résout en
> 10.50.0.2 : le moteur peut proposer, très logiquement, de l'isoler. Appliquer
> cette décision couperait la plateforme qui l'exécute, et plus personne ne
> serait là pour la lever. Une liste d'adresses protégées refuse désormais ce
> cas, et le refuse *avant* d'écrire sur l'équipement.
>
> **La levée écrivait un état que le schéma interdisait.** `execution = 'levee'`
> violait une contrainte `CHECK` — après que la mesure avait été retirée du
> pare-feu. La base croyait la quarantaine active alors qu'elle ne l'était plus,
> et la réconciliation l'aurait reposée sur une machine qu'un analyste venait de
> libérer. Le schéma disait déjà `annulee` : il fallait lire, pas inventer.
>
> **Une affirmation du plan était fausse.** « Un `configctl filter reload` vide
> les tables » : vérifié sur l'appliance, OPNsense 26 les réécrit. Ce qui les
> perd, c'est une purge (`pfctl -T flush`, le bouton « Flush » de l'interface).
> La réconciliation reste indispensable, pour une autre raison que celle
> annoncée — et la recette éprouve la vraie.
>
> **Une réserve assumée.** Le compte de service n'a pas le privilège
> `page-diagnostics-showstates`, donc le connecteur ne peut pas purger les
> sessions déjà établies : l'isolation ne vaut que pour les nouvelles
> connexions. La réserve est écrite dans `soar_audit.execution_note` à chaque
> exécution plutôt que passée sous silence. Élargir le compte est une décision
> à prendre en connaissance de cause — voir §Arbitrage en attente.

### Phase 3 — Dossiers d'enquête (IRIS)
**28 août au 2 septembre.**

```
Lot4_SOAR/dossiers/
    base.py     Protocol GestionDossier (ouvrir, ajouter_observable,
                commenter, cloturer, etat)
    iris.py     adaptateur DFIR-IRIS
    sortie.py   file persistée et worker de reprise
Lot0_Socle/08_schema_dossiers.sql
```

Accrochage dans `_proposer_soar()` du service de scoring, en transaction
séparée. `_ouvrir_dossier()` écrit dans `dossier_sortie` et rend la main :
`/ingest` n'attend jamais un appel HTTP vers IRIS.

Correspondance des champs :

| Champ IRIS | Contenu | Source |
|---|---|---|
| `alert_title` | `[SIGIPES] Anomalie réseau / C2 — SRV-APP-GOV-01` | type, entité, périmètre |
| `alert_description` | écarts en σ, rédigés | `raisons` |
| `alert_severity_id` | dérivé du risque mesuré | `risque` |
| `alert_customer_id` | le périmètre | `tenant_id` |
| `alert_source_ref` | UUID de l'alerte NEXUS | clé d'idempotence |
| `alert_source_link` | `console.html#alerte={id}` | retour vers l'explicabilité |
| `alert_source_content` | charge brute | `score_parts`, `chaine`, `iocs` |
| `alert_tags` | `T1027,T1059,perimetre:sigipes` | chaîne MITRE |
| `alert_iocs` | indicateurs **observés** uniquement | `alerts.iocs` |
| `alert_assets` | hôte, compte | `cible`, `cible_type` |

NEXUS pousse des alertes, pas des dossiers. L'escalade en dossier
(`POST /alerts/escalate/{id}`) reste un geste d'analyste, cohérent avec la ligne
du projet : la plateforme mesure et propose, l'humain qualifie.

*Recette : arrêter IRIS pendant dix minutes de collecte ne perd aucune alerte ;
la file se vide au redémarrage ; un rejeu ne crée pas de doublon.*

> **Livrée le 29 août 2026.** IRIS tourne, le compte de service est cloisonné,
> les alertes NEXUS y arrivent de bout en bout. Journal ci-dessous.
>
> **(28 août — écrite et branchée, IRIS pas encore levé.)** Le schéma est
> appliqué, les trois modules sont en place, l'ouvrier tourne dans le cœur SOC.
> Deux alertes réelles, produites par le pipeline signé depuis KaliPrime, sont
> entrées en file et y attendent avec un report exponentiel : **la propriété
> visée est donc déjà démontrée**, l'ingestion ne dépend pas d'IRIS.
>
> Ce qui manque est matériel : l'image `iriswebapp_app` pèse près d'un
> gigaoctet et la liaison de la machine n'a pas tenu le téléchargement. Le code
> n'attend qu'elle. Reprendre par `cd /opt/nexus-iris && docker compose pull`
> sur une meilleure liaison, puis suivre `lab-cenadi/06-reponse-collaborative.md`
> §11.3.
>
> **Deux défauts corrigés en chemin.** Une correspondance de périmètre absente
> était traitée comme un refus définitif : l'incident était jeté alors qu'il
> suffisait d'attendre une minute de configuration. Et le titre de chaque dépôt
> affichait `[CENADI]` pour tous les périmètres, le nom ne circulant pas dans
> l'objet alerte — il est désormais lu en base.
>
> **Une version figée.** `.env.model` d'IRIS livre `APP_IMAGE_TAG=latest`, qui
> écrase la version épinglée de sa propre composition. Ramené à `v2.4.20` :
> une image qui change sous les pieds est ce qui casse une démonstration le
> matin où elle doit avoir lieu.
>
> **Tests de phase 6 pris d'avance.** `Lot6_Tests/test_dossiers.py` (7) et
> `test_connecteurs.py` (14) s'exécutent sans réseau ni équipement. Une logique
> vérifiable seulement les jours où l'outil tiers fonctionne n'est jamais
> vérifiée le jour où ça compte. **35 tests au total, tous au vert.**

### Phase 4 — Discussion d'incident
**3 au 4 septembre.**

- `iris-webhooks-module` sur l'escalade d'alerte ;
- canal `#incident-AAAAMMJJ-<id court>`, message initial avec le résumé, le
  risque, l'entité, le lien vers le dossier et le lien vers la console ;
- module `iris-nexus-module`, dérivé d'`iris-skeleton-module`, qui renvoie à
  NEXUS le passage en investigation.

*Recette : un échec Mattermost ne bloque ni l'escalade ni l'alerte.*

> **Livrée le 29 août 2026.** Mattermost tourne, le robot publie, la veille
> ouvre les canaux. Deux écarts au plan, assumés et documentés en
> [06-reponse-collaborative.md §13](../lab-cenadi/06-reponse-collaborative.md) :
>
> **Une veille plutôt qu'un module IRIS.** IRIS n'expose ses accroches qu'à des
> modules Python installés dans son conteneur. Faire dépendre l'ouverture d'un
> canal du cadriciel d'un tiers, c'est accepter qu'elle cesse un jour sans que
> personne ne s'en aperçoive. NEXUS interroge donc IRIS toutes les trente
> secondes — une escalade est un geste humain délibéré, le délai est sans
> conséquence.
>
> **Deux défauts trouvés dans la composition déjà écrite.** Mattermost était
> publié sur `127.0.0.1`, inatteignable depuis vm-rssi où travaille le RSSI,
> sous un commentaire annonçant le contraire. Et la composition référençait un
> réseau `nexus` inexistant : le conteneur n'aurait jamais trouvé la base.
>
> **Un piège de mon propre script.** Le contrôle de création de compte cherchait
> un champ `id` dans la réponse — or une réponse d'ERREUR de Mattermost en
> contient un aussi. L'échec s'affichait comme un succès. On demande désormais
> au serveur si le compte existe : la seule question qui tranche.

### Phase 5 — Enrichissement souverain (optionnel)
**5 au 6 septembre.** À faire seulement si les phases 1 à 4 sont recettées.

MISP auto-hébergé, `iris-misp-module`, flux hors ligne. VirusTotal reste
désactivé par défaut.

### Phase 6 — Tests et répétition
**7 au 10 septembre.**

- `test_connecteurs.py` : OPNsense et LDAP bouchonnés, cas d'échec,
  non-régression sur le statut d'exécution ;
- `test_dossiers.py` : file de sortie, reprise après panne, idempotence ;
- les 14 tests existants restent au vert ;
- réécriture du `RUNBOOK.md` et deux répétitions chronométrées.

**Gel fonctionnel le 7 septembre au soir.**

### Phase 7 — Rapport et diapositives
**11 au 14 septembre.** Aucun code.

---

## 5. Ce que la décision ne règle pas

**Les connecteurs restent à écrire.** Tant que la phase 2 n'est pas livrée,
`execution` vaut `non_executee` et la plateforme continue d'annoncer qu'elle n'a
rien exécuté. C'est honnête, mais c'est la faiblesse la plus visible.

**La topologie reste à déployer.** Les figures décrivent six zones ; quatre
machines virtuelles tournent aujourd'hui sur le réseau libvirt par défaut, à
plat. La phase 1 existe pour cela.

---

## 6. Journal des décisions d'architecture

À reporter dans le suivi des décisions verrouillées.

| N° | Décision | Effet |
|---|---|---|
| D14 | OPNsense unique, MikroTik et pfSense retirés | remplace la topologie à deux équipements |
| D15 | Sortie Internet par zone, refus par défaut | lève « aucune zone n'atteint Internet » |
| D16 | DFIR-IRIS pour les dossiers, derrière une interface abstraite | la décision n° 2 est préservée, pas d'Elasticsearch |
| D17 | Cortex retiré | NEXUS reste le seul exécutant |
| D18 | MISP primaire, VirusTotal sous condition explicite | applique la souveraineté à l'enrichissement |
| D19 | Un seul point d'exécution, deux points d'entrée | IRIS renvoie vers la console pour valider |

---

## 7. Journal du 29 août 2026 — IRIS en service

DFIR-IRIS v2.4.20 tourne sur le cœur SOC, écoute sur `10.50.0.2:4443` et rien
d'autre. Cinq alertes réelles y sont déposées, chacune avec sa gravité résolue
par nom, son périmètre et ses étiquettes MITRE.

**Un compte de service qui ne peut faire qu'une chose.** Groupe dédié, trois
droits : `standard_user`, `alerts_read`, `alerts_write`. Il ne peut ni
administrer IRIS, ni supprimer une alerte, ni toucher aux dossiers. L'escalade
d'une alerte en dossier d'enquête reste un geste d'analyste — garanti ici par
une permission absente, pas par une convention.

IRIS cloisonne d'ailleurs à deux niveaux : les droits d'un côté, l'habilitation
par périmètre de l'autre. Le compte est habilité aux trois périmètres
supervisés, et à eux seuls.

**Le défaut qui comptait.** La recette a montré qu'IRIS n'impose **aucune**
unicité sur `alert_source_ref` : rejouer un envoi créait un second dossier. Le
cas réel n'est pas théorique — on poste, IRIS crée l'alerte, l'ouvrier tombe
avant d'enregistrer l'identifiant, et à la reprise l'analyste trouve deux
dossiers pour un incident. La vérification a été déplacée **avant** l'écriture,
au prix d'un appel supplémentaire par dépôt. C'est le prix d'une garantie qui,
autrement, n'existe pas.

Le filtre de recherche portait d'ailleurs deux erreurs qui se compensaient en
silence : la méthode (GET, pas POST) et le nom du paramètre (`source_reference`,
pas `alert_source_ref`). Un filtre inconnu ne provoque aucune erreur côté IRIS —
il renvoie simplement tout le catalogue. Le code revérifie donc la référence sur
chaque ligne reçue, plutôt que de faire confiance au serveur.

**Deux tests de non-régression** couvrent désormais ce point précis.

**Ce que la recette a aussi appris.** La plateforme agrège les alertes
identiques (`ALERT_DEDUP_MIN`) : rejouer le même scénario ne produit pas une
seconde alerte. C'était ma recette qui postulait le contraire, pas la plateforme
qui se trompait. La recette essaie maintenant les trois scénarios, et lorsque
tout est agrégé elle le signale comme **non éprouvé** — ni réussi, ni échoué.
Compter une sonde non exécutée comme réussie serait le pire des mensonges dans
un dossier de soutenance.
