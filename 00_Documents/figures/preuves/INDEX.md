# Dossier de preuves — captures d'écran

Toutes les images de ce dossier sont des **photographies d'interfaces réelles**,
prises session ouverte par `lab-cenadi/scripts/captures-preuves.py`. Aucune
n'est une maquette, un montage ou une reconstitution.

Deux réserves sont à lire avant de les insérer dans le mémoire — elles sont au
bas de ce fichier, et l'une d'elles est **impérative**.

---

## 1. Pare-feu et réponse réseau — phase 1

| Fichier | Ce qu'il établit |
|---|---|
| `00-tableau-de-bord.png` | Sept interfaces OPNsense, adressage des six zones |
| `01-avant-alias-quarantaine.png` | Table `nexus_quarantaine` vide, avant décision |
| `02-pendant-alias-quarantaine.png` | Les adresses posées **par l'API**, relues sur l'appliance |
| `02-pendant-journal-pare-feu.png` | Rejets en rouge **et** télémétrie en vert, simultanément |
| `03-apres-alias-quarantaine.png` | Table vidée après la levée |
| `04-compte-service-nexus-soar.png` | Le compte de service et son périmètre |
| `05-aliases-nexus.png` | Les quatre alias de réponse |
| `06-regles-reponse-nexus.png` | Les 34 règles NEXUS chargées |
| `08-suricata-parametres.png` | Détection seule, quatre zones internes |
| `09-suricata-alertes.png` | Onze détections réelles, horodatées |

`02-pendant-journal-pare-feu.png` est la capture à projeter : on y lit dans la
même fenêtre les paquets rejetés des machines en quarantaine **et** leur
télémétrie qui continue d'atteindre le cœur SOC. Une seule image, toute la
thèse : *isoler sans aveugler*.

---

## 2. Dossier d'enquête DFIR-IRIS — phase 3

Dossier **#2 — Incident NEXUS : commande-et-contrôle sur POSTE-MENACE-vrai**,
escaladé depuis l'alerte NEXUS n°17.

| Fichier | Ce qu'il montre |
|---|---|
| `20-iris-alerte.png` | L'alerte telle que NEXUS l'a déposée : titre, périmètre, gravité, source |
| `21-iris-dossier-resume.png` | Résumé, **périmètre** (Réseau/LAN CENADI), identifiant SOC, **état de l'enquête** (Containment), sévérité, étiquettes |
| `22-iris-observables.png` | **Sept observables**, chacun typé et rattaché à sa technique MITRE, en TLP:AMBER |
| `23-iris-chronologie.png` | La **chronologie** : l'alerte importée puis les étapes de la chaîne reconstituée, avec leurs techniques |
| `24-iris-actifs.png` | L'actif concerné |

**Provenance des observables et de la chronologie.** Ils ne sont pas saisis à la
main : ils viennent de la colonne `alerts.chaine`, c'est-à-dire de ce que la
plateforme a corrélé. Le dépôt des observables se fait automatiquement à
l'ingestion ; le versement de la chronologie dans le dossier est un geste
d'analyste, effectué avec le compte administrateur — le compte de service de
NEXUS n'a **pas** le droit d'écrire dans un dossier, et c'est délibéré.

---

## 3. Canal d'incident Mattermost — phase 4

| Fichier | Ce qu'il montre |
|---|---|
| `30-mattermost-canal-incident.png` | Le canal `incident-20260829-e8caaf15`, son message d'ouverture automatique et la coordination |

Le canal est ouvert **automatiquement** par la veille NEXUS dès l'escalade de
l'alerte dans IRIS. Le message d'ouverture — titre, périmètre, entité, risque,
motifs mesurés, techniques MITRE, lien vers le dossier et lien vers
l'explicabilité — est produit par la plateforme.

> ### ⚠ Réserve impérative sur cette figure
>
> **L'échange entre `rssi-cenadi`, `operateur-cenadi` et `dsi-cenadi` est une
> mise en scène.** Ces comptes portent des noms de RÔLES du laboratoire, jamais
> de personnes, et les messages ont été écrits d'avance par
> `lab-cenadi/scripts/mattermost-scenario-coordination.sh`.
>
> Cette figure doit être légendée comme une **simulation de coordination**, au
> même titre que les attaques rejouées depuis KaliPrime. La présenter comme la
> trace d'une intervention réelle serait présenter une conversation fabriquée
> comme une preuve.
>
> Ce qui est **dit** dans ces messages correspond en revanche à ce que la
> plateforme a réellement fait : la quarantaine a bien été appliquée et relue,
> la télémétrie a bien continué de parvenir, et la réserve sur les sessions
> déjà établies est bien celle que l'audit consigne.
>
> Ce qui est **automatique** dans cette capture — l'ouverture du canal et le
> message initial — est authentique et se rejoue avec
> `lab-cenadi/scenarios/10-preuve-discussion.sh`.

---

## 4. Journal `soar_audit` — phases 1 et 2

| Fichier | Ce qu'il montre |
|---|---|
| `40-soar-journal-audit.png` | Le journal complet : horodatage, action, cible, acteur, impact, statut, exécution |

Deux lignes portent le cycle entier :

| Horodatage | Action | Cible | Acteur | Statut | Exécution |
|---|---|---|---|---|---|
| 30/08 08:34 | `isolate_host` | SRV-APP-GOV-01 | operateur-cenadi | **LEVÉE** | **annulée** |
| 29/08 16:54 | `isolate_host` | POSTE-MENACE-vrai | rssi-cenadi | **EXÉCUTÉE (automatique)** | connecteur |

La première est le **retour arrière** demandé : une mesure appliquée puis levée,
avec son acteur et son horodatage. La seconde est une mesure **en vigueur**,
appliquée par le connecteur et confirmée par relecture de l'équipement.

Les lignes « non exécutée » ne sont pas des échecs : ce sont des propositions du
moteur qui attendent une décision humaine. C'est l'état normal d'une file
d'approbation, et il vaut mieux le montrer que le masquer.

**Cadrage.** La section affiche d'abord les quatre-vingt-treize actions en
attente, puis le journal. La capture masque les cartes en attente pour que le
journal soit lisible — aucune ligne du journal n'est retirée.

---

## Reproduire ces captures

```bash
set -a; . ./.env; set +a
export IRIS_GUI_PASSWORD=…   MM_GUI_USER=rssi-cenadi MM_GUI_PASSWORD=…
export NEXUS_ADMIN_PASSWORD=…
export ALERTE_IRIS=17 DOSSIER_IRIS=2 CANAL_INCIDENT=incident-20260829-e8caaf15
python3 lab-cenadi/scripts/captures-preuves.py --sortie 00_Documents/figures/preuves
```

Les mots de passe viennent de l'environnement, jamais d'un argument : la table
des processus est lisible par tous les utilisateurs de la machine.

---

## Seconde réserve : les blocs-notes de la console

`40-soar-journal-audit.png` affiche « 93 actions en attente ». Ce nombre vient
de mois de simulations accumulées dans le laboratoire, pas d'un parc réel qui
serait laissé sans arbitrage. Si la figure est commentée à l'oral, mieux vaut le
dire — un jury peut légitimement s'en étonner.
