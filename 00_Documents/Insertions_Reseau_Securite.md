# Insertions réseau / sécurité — mémoire NEXUS SOC

Contenu prêt à coller dans `NEXUS_SOC_Rapport_CENADI_OpenSource.docx`.
Chaque item indique son emplacement, le texte, et les figures/tableaux à insérer.
Les numéros de figures et de tableaux se renumérotent automatiquement dans Word
(champs de légende) : ne pas les fixer à la main.

Figures : les PNG sont prêts à coller (400 dpi, dans `figures/`). Les `.drawio`
sont les sources éditables (icônes réseau natives) si tu veux retoucher dans draw.io.

- `figures/topologie-reseau-souveraine.png`   (source : `.drawio`)
- `figures/airgap-zone-sensible.png`          (source : `.drawio`)
- `figures/defense-en-profondeur-7-couches.png` (source : `.drawio`)

---

## Item 1 — Concepts : segmentation et défense en profondeur

**Emplacement :** §1.1.1 « Concepts fondamentaux », à ajouter après le paragraphe
sur l'architecture multi-locataire (juste avant §1.1.2).

> La protection d'un système d'information ne repose pas sur une barrière unique
> mais sur leur empilement. Ce principe de défense en profondeur consiste à
> disposer des contrôles de sécurité en couches successives, de la sécurité
> physique jusqu'à la gouvernance, de sorte qu'une compromission doive franchir
> plusieurs obstacles avant d'atteindre une donnée sensible. La couche réseau y
> tient une place particulière. La segmentation découpe l'infrastructure en zones
> aux niveaux de confiance distincts et n'autorise entre elles que les flux
> nécessaires, ce qui limite les déplacements latéraux d'un attaquant. Sa forme la
> plus stricte, l'air-gap, isole une zone au point qu'elle n'initie aucune
> connexion vers l'extérieur : un serveur cloisonné de la sorte peut émettre sa
> télémétrie de supervision, sans jamais servir de point de rebond. Ces deux
> notions, défense en profondeur et segmentation, structurent la sécurisation de
> la plateforme exposée aux chapitres 3 et 4.

*Aucune figure. Référence possible : rattacher au guide NIST déjà cité (Cichonski
et al., 2012).*

---

## Item 2 — Nouvelle sous-section §3.2.1 bis « Architecture réseau du déploiement souverain »

**Emplacement :** dans §3.2, juste après §3.2.1 « Architecture de la plateforme
implémentée » et avant §3.2.2. À numéroter §3.2.2, en décalant les suivantes,
ou à insérer comme fin de §3.2.1.

**Titre (Heading 3) :** `Architecture réseau du déploiement souverain`

> L'architecture logicielle décrite ci-dessus se déploie sur un réseau conçu pour
> refléter les contraintes d'un opérateur informatique de l'État. Le plan
> d'adressage `10.50.0.0/16` découpe l'infrastructure en six zones, séparées selon
> leur niveau de sensibilité (figure X). Le cœur SOC (`10.50.0.0/24`), qui héberge
> NEXUS SOC, la PKI interne et Wazuh, collecte la télémétrie des autres zones. Une
> DMZ interne (`10.50.10.0/24`) porte le relais applicatif et la messagerie ; la
> zone applicative (`10.50.20.0/24`) accueille les serveurs métier ; la zone
> sensible (`10.50.30.0/24`) isole l'application de la solde, image du système
> ANTILOPE ; une zone d'administration (`10.50.40.0/24`) est réservée aux postes du
> RSSI et de la DSI ; une zone menace (`10.50.50.0/24`) simule un poste compromis.
>
> Aucune de ces zones ne dispose d'une route vers Internet. Cette absence de sortie
> est un choix de souveraineté : le pare-feu de périmètre pfSense a son interface
> WAN désactivée, et ne fait donc que du filtrage interne. Le routage entre zones
> et les règles d'accès sont portés par un routeur MikroTik, qui applique la
> matrice de flux du tableau Y. Cette matrice se lit par ligne source vers colonne
> destination : le SOC atteint toutes les zones pour la collecte, mais chaque zone
> supervisée ne parle qu'au SOC.
>
> La zone sensible obéit à une règle plus stricte encore. Le serveur ANTILOPE ne
> peut émettre que sa télémétrie, vers le seul cœur SOC, sur les ports de collecte ;
> toute autre tentative de connexion, vers Internet comme vers une zone voisine,
> est rejetée. Ce cloisonnement en air-gap garantit qu'un poste bureautique
> compromis dans la zone menace ne peut atteindre le système de la solde, quand
> bien même il aurait été piégé. La vérification de cette étanchéité figure en
> §3.2.5.
>
> Les six zones sont créées de façon reproductible par un script libvirt versionné,
> chaque réseau étant défini sans routage sortant. L'ensemble constitue une maquette
> souveraine, montée sous GNS3 avec les images pfSense et MikroTik, qui reproduit
> l'organisation réseau visée au CENADI sans dépendre de son infrastructure de
> production.

**FIGURE X** → `figures/topologie-reseau-souveraine.png`
Légende : `Topologie réseau souveraine : six zones du plan 10.50.0.0/16 isolées d'Internet, filtrées par pfSense (WAN désactivé) et MikroTik.`

**TABLEAU Y** — Matrice des flux inter-zone autorisés (à créer comme tableau Word)
Légende : `Matrice des flux inter-zone (✓ autorisé, ✗ bloqué par ACL MikroTik).`

| De \ Vers | SOC (mgmt) | DMZ | App | Sensible | Admin | Menace | Internet |
|-----------|:---------:|:---:|:---:|:--------:|:-----:|:------:|:--------:|
| **SOC** | — | ✓ | ✓ | ✓ (collecte) | ✓ | ✓ | ✗ |
| **DMZ** | ✓ | — | ✗ | ✗ | ✗ | ✗ | ✗ |
| **App** | ✓ (télémétrie) | ✗ | — | ✗ | ✗ | ✗ | ✗ |
| **Sensible** | ✓ (télémétrie seule) | ✗ | ✗ | — | ✗ | ✗ | ✗ |
| **Admin** | ✓ | ✓ | ✗ | ✗ | — | ✗ | ✗ |
| **Menace** | ✓ (télémétrie) | ✗ | ✗ | ✗ | ✗ | — | ✗ |

---

## Item 3 — Extension de §3.2.5 « Étanchéité »

**Emplacement :** §3.2.5. Renommer le titre et ajouter un paragraphe + une figure
avant le paragraphe RLS existant.

**Nouveau titre (Heading 3) :** `Étanchéité : cloisonnement réseau et cloisonnement des données`

> L'étanchéité de la plateforme se vérifie à deux niveaux, réseau puis base de
> données. Au niveau réseau, la règle d'air-gap de la zone sensible a été éprouvée
> par un scénario dédié. Depuis le serveur ANTILOPE, une tentative de connexion
> vers Internet (`ping 8.8.8.8`) échoue, de même qu'une tentative vers la zone
> applicative voisine (`ping 10.50.20.20`) ; seul l'appel de collecte vers le cœur
> SOC (`curl 10.50.0.1:8000/health`) aboutit (figure Z). Le poste sensible n'a donc
> aucun chemin latéral ni aucune sortie : il n'émet que sa télémétrie, exactement
> comme le prescrit la matrice de flux.

*(Le paragraphe RLS existant enchaîne ensuite : « Au niveau de la base, la
plateforme prévient la fuite d'un périmètre vers un autre par une isolation au
niveau des lignes… », inchangé, avec ses 8 assertions sur 8.)*

**FIGURE Z** → `figures/airgap-zone-sensible.png`
Légende : `Vérification de l'air-gap de la zone sensible : flux de télémétrie autorisé vers le SOC, tous les autres flux rejetés.`

---

## Item 4 — Nouvelle sous-section §4.2.x « Sécurisation de la plateforme (défense en profondeur) »

**Emplacement :** dans §4.2, après §4.2.2 « Les modalités de déploiement et
d'exploitation », avant §4.2.3. À numéroter §4.2.3, en décalant l'actuelle 4.2.3.

**Titre (Heading 3) :** `Sécurisation de la plateforme (défense en profondeur)`

> Un centre opérationnel de sécurité concentre les journaux et les alertes des
> systèmes les plus sensibles de l'État ; sa propre compromission serait donc
> critique. NEXUS SOC applique à lui-même la doctrine qu'il met en œuvre, selon sept
> couches de défense en profondeur (figure W).
>
> La couche physique repose sur le datacenter contrôlé du CENADI et sur le
> chiffrement de disque (LUKS) des serveurs. La couche réseau est la segmentation en
> six zones et l'air-gap décrits au chapitre 3. Au niveau du système, le service de
> la plateforme est durci sous systemd : il s'exécute sans élévation de privilèges
> (`NoNewPrivileges`), avec un système de fichiers protégé (`ProtectSystem=full`,
> `ProtectHome=read-only`) et un espace temporaire isolé, l'accès distant étant
> restreint à l'authentification par clé. La couche applicative est celle du code de
> NEXUS SOC : un contrôle d'accès à quatre rôles sépare l'administrateur de la
> plateforme, l'analyste, le responsable de périmètre et le lecteur ; les jetons
> d'accès sont signés en HMAC-SHA256 avec une durée de vie courte ; l'isolation au
> niveau des lignes cloisonne les données. La couche données ajoute le chiffrement
> en transit par la PKI interne du CENADI plutôt que par une autorité externe, la
> pseudonymisation des identifiants surveillés avant stockage, et des sauvegardes
> chiffrées conservées dans le datacenter.
>
> Deux couches méritent une attention particulière dans un contexte gouvernemental.
> La couche détection retourne les capteurs de la plateforme vers la plateforme
> elle-même : Wazuh collecte les journaux d'authentification et les modifications de
> fichiers des serveurs SOC, et chaque action d'administration ou de réponse est
> inscrite dans un journal d'audit horodaté et non modifiable. La couche
> gouvernance, enfin, traduit ces mesures en garanties vérifiables : souveraineté
> des données prouvée par capture réseau, séparation des devoirs entre celui qui
> détecte et celui qui valide une action, réversibilité des actions à fort impact,
> et jetons d'enrôlement liés au nom d'hôte et à usage unique. Le tableau V
> récapitule, pour chaque couche, la menace visée, la mesure et sa preuve.
>
> Cette sécurisation aligne la plateforme sur les contrôles de la norme ISO/IEC
> 27001 et sert la démarche d'homologation portée par l'ANTIC. Dans le lab, le
> chiffrement de disque est simulé sur le volume de données ; les autres mesures
> (durcissement systemd, isolation, journal d'audit, PKI) sont effectives sur le
> déploiement.

**FIGURE W** → `figures/defense-en-profondeur-7-couches.png`
Légende : `Sécurisation de NEXUS SOC en défense en profondeur : sept couches, de la sécurité physique à la gouvernance.`

**TABLEAU V** — Synthèse de la sécurisation par couche (à créer comme tableau Word)
Légende : `Défense en profondeur : menace, mesure et preuve par couche.`

| Couche | Menace | Mesure | Preuve |
|--------|--------|--------|--------|
| 1. Physique | Accès physique, vol de disque | Datacenter contrôlé, LUKS, USB désactivés | Statut LUKS `cryptsetup` |
| 2. Réseau | Déplacement latéral, exfiltration | Segmentation 6 zones, air-gap, ACL MikroTik | Scénario air-gap (figure Z) |
| 3. Hôte/OS | Élévation de privilèges | Durcissement systemd, SSH par clé | `systemd-analyze security` |
| 4. Application | Accès non autorisé | RBAC 4 rôles, JWT signés, RLS | Un responsable reçoit 403 sur `/admin/*` |
| 5. Données | Lecture au repos / en transit | LUKS, TLS via PKI interne, pseudonymisation HMAC | Config `PSEUDO_ENABLED`, certificats internes |
| 6. Détection | Compromission du SOC | Wazuh sur les serveurs SOC, journal d'audit immuable | Table `soar_audit` consultable |
| 7. Gouvernance | Perte de souveraineté, non-conformité | Traçabilité, séparation des devoirs, réversibilité | Capture réseau (scénario souveraineté) |

---

## Item 5 — Ajustement du verdict H2 (et, en option, du Tableau 1)

**Emplacement :** §4.1, paragraphe de la deuxième hypothèse. Remplacer la phrase
médiane pour y intégrer segmentation, air-gap et durcissement.

Texte proposé (remplace le paragraphe H2 existant) :

> La deuxième hypothèse portait sur la souveraineté et la maîtrise interne. La
> plateforme s'appuie exclusivement sur des logiciels libres, hébergeables
> localement, et se déploie de façon automatisée par infrastructure-as-code ; aucun
> composant propriétaire ni aucune licence commerciale n'entre dans sa composition.
> La maîtrise interne ne tient pas qu'au code : le déploiement est cloisonné en six
> zones réseau sans route vers Internet, la zone sensible est isolée en air-gap, et
> le service lui-même est durci au niveau du système. L'État conserve ainsi le plein
> contrôle de l'outil, de son code jusqu'à son réseau. L'hypothèse est confirmée au
> plan de la conception, la validation en exploitation réelle restant à établir.

**Option (Tableau 1, §2.1.2)** — deux lignes à ajouter sous H2 :

| Hypothèse | Variable évaluée | Indicateur | Instrument de mesure |
|-----------|------------------|------------|----------------------|
| H2 | Cloisonnement réseau du déploiement | Nombre de zones isolées ; flux inter-zone bloqués conformes à la matrice | Scénarios d'air-gap et de souveraineté |
| H2 | Durcissement du service | Score `systemd-analyze security` ; directives de durcissement actives | Inspection de l'unité systemd |

---

## Item 6 — Résumé, Abstract, Conclusion générale (visibilité)

**Résumé** — après « … une architecture cloisonnant les différents périmètres
supervisés. », ajouter :

> Le déploiement est en outre segmenté en zones réseau isolées, la zone la plus
> sensible étant maintenue en air-gap, et la plateforme elle-même est durcie selon
> une défense en profondeur.

**Abstract** — après « … an architecture that compartmentalises the supervised
perimeters. », ajouter :

> The deployment is further segmented into isolated network zones, with the most
> sensitive one kept air-gapped, and the platform itself is hardened following a
> defence-in-depth approach.

**Conclusion générale** — dans le bilan des apports, ajouter une phrase du type :

> Au-delà de la détection, le travail a porté sur l'ingénierie réseau du déploiement
> souverain (segmentation en six zones, air-gap de la zone sensible) et sur la
> sécurisation de la plateforme elle-même en défense en profondeur, deux dimensions
> attendues d'un opérateur de l'État.

---

## Item 7 — Limites et sigles

**§6.2 « Délimitation thématique »** — ajouter aux limites déjà listées :

> Enfin, l'architecture réseau est éprouvée sous la forme d'une maquette souveraine
> reproductible (réseaux libvirt et routage pfSense/MikroTik sous GNS3), et le
> chiffrement de disque y est simulé. La transposition sur l'infrastructure de
> production du CENADI prolonge le présent travail, au même titre que la validation
> des modèles sur les données réelles.

**Liste des sigles et abréviations** — ajouter :

| Sigle | Signification |
|-------|---------------|
| ACL | Access Control List (liste de contrôle d'accès) |
| DMZ | Demilitarized Zone (zone démilitarisée) |
| GNS3 | Graphical Network Simulator 3 |
| JWT | JSON Web Token |
| LUKS | Linux Unified Key Setup (chiffrement de disque) |
| PKI | Public Key Infrastructure (infrastructure à clés publiques) |
| RBAC | Role-Based Access Control (contrôle d'accès par rôles) |
| TLS | Transport Layer Security |
| VLAN | Virtual Local Area Network |

---

## Récapitulatif de l'impact

- Figures nouvelles : 3 (topologie, air-gap, défense en profondeur) — côté réseau/sécurité.
- Tableaux nouveaux : 2 (matrice de flux, synthèse défense en profondeur) + 2 lignes optionnelles au Tableau 1.
- Sous-sections nouvelles : 2 (§3.2 réseau souverain, §4.2 défense en profondeur) + 3 extensions.
- Volume estimé : +5 à 7 pages.
