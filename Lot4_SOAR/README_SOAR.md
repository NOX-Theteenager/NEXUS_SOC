# NEXUS SOC — Moteur SOAR (réponse automatisée encadrée)

Le SOAR (*Security Orchestration, Automation and Response*) **boucle la couche IA** : il consomme
les alertes produites par les modèles (Modèle 1 réseau, Modèle 2 fraude) et déclenche une
**réponse automatisée** via des **playbooks**, sous le contrôle de **garde-fous**.

> **`soar_engine.py` est un démonstrateur autonome, pas le chemin d'exécution.**
> En production, la proposition d'action est faite par `choisir_action_soar()` et
> `_proposer_soar()` dans `Lot1_Agent_Go/scoring-service_app.py`, écrite dans la
> table `soar_audit`, puis arbitrée par les routes `/analyst/*` de
> `Lot7_Console_Fournisseur/admin_api.py`. Ce fichier sert à exposer la logique de
> décision et les garde-fous sur un jeu d'alertes reproductible. Un correctif
> appliqué ici ne change rien au comportement de la plateforme, et réciproquement.
> La consolidation des deux implémentations est à l'ordre du jour (phase 6 du
> [plan](../00_Documents/Decision_Reponse_Collaborative.md)).

---

## 1. Contenu

| Fichier | Rôle |
|---|---|
| `soar_engine.py` | Moteur SOAR : alertes, playbooks, règle de décision, validation, rollback, audit |
| `playbook_fraude.png` | Schéma du playbook de fraude interne avec garde-fous |
| `audit_log.csv` | Journal d'audit produit par une exécution de démonstration |

## 2. Exécution

```bash
python soar_engine.py            # mode SIMULATION (dry-run) : montre ce qui SERAIT fait
python soar_engine.py --execute  # exécution réelle + démo validation humaine et rollback
```

Le moteur charge automatiquement le **Modèle 2** (s'il est disponible), score un échantillon et
convertit les fraudes détectées en alertes — démontrant la **connexion réelle IA → SOAR**.

## 3. Les garde-fous (le cœur du dispositif)

C'est ce qui distingue une automatisation *responsable* d'une automatisation dangereuse :

- **Seuil de confiance** — une action ne s'exécute automatiquement que si le score de risque
  dépasse un seuil (par défaut 70/100).
- **Niveau d'impact** — chaque action est classée *faible / moyen / fort*. Les actions sûres
  (journaliser, notifier) s'exécutent toujours ; les actions à **fort impact** (geler un compte,
  isoler un poste) exigent une **validation humaine** (*human-in-the-loop*).
- **Mode simulation (dry-run)** — par défaut, rien n'est exécuté : on visualise les décisions
  avant d'activer l'exécution réelle.
- **Réversibilité (rollback)** — toute action réversible (gel, isolation, blocage IP) peut être
  annulée en cas de faux positif ; les actions non réversibles (notification, journalisation) ne
  le sont pas.
- **Journal d'audit** — chaque décision et action est tracée (incident, entité, risque, action,
  impact, décision, statut, acteur) → `audit_log.csv`.

## 4. Playbooks

| Type d'incident | Actions (dans l'ordre) |
|---|---|
| **Fraude interne** | journaliser pour enquête → notifier (SMS) → geler le compte *(validation)* → archiver les journaux |
| **Exfiltration** | journaliser → geler le compte *(validation)* → bloquer l'IP → notifier |
| **Ransomware** | capturer la mémoire → isoler le poste *(validation)* → bloquer l'IP → notifier |
| **Anomalie réseau / C2** | journaliser → bloquer l'IP → notifier |

> Demande explicite du projet (fraude) : **gel de compte + notification + journalisation pour
> enquête** — c'est exactement le playbook « Fraude interne », avec le gel soumis à validation.

## 5. Format d'alerte (interface IA → SOAR)

Chaque modèle émet une alerte standard que le SOAR sait traiter :

```python
Alert(type="Fraude interne", entity="agent_DGI_0421", entity_kind="compte",
      risk=86, reasons=["montant total modifié anormalement élevé (9.2σ)"],
      source="Modèle 2 (UEBA)", mitre="T1565 (Manipulation de données)")
```

Le champ `reasons` provient directement de l'**explicabilité** du Modèle 2 : c'est ce qui permet
au DSI (et au LLM Analyst) de comprendre *pourquoi* une action est proposée.

## 6. Connecteurs

Dans ce démonstrateur, les actions restent **simulées**. Les connecteurs réels vivent dans
`Lot4_SOAR/connecteurs/` et sont appelés par `POST /analyst/execute/{id}` :

| Action | Connecteur | Cible réelle |
|---|---|---|
| `block_ip` | `opnsense.py` | alias `nexus_block` du pare-feu |
| `isolate_host` | `opnsense.py` | alias `nexus_quarantaine` |
| `freeze_account` | `ldap_ppolicy.py` | attribut `pwdAccountLockedTime` de l'annuaire |

Trois règles s'appliquent à tout nouveau connecteur :

1. `execution` ne passe à `automatique` **qu'après relecture vérifiée** de l'état visé. Un code
   HTTP 200 ne prouve pas que l'adresse figure dans l'alias.
2. En cas d'échec, `execution` reste `non_executee`, le motif part dans `execution_note`, et la
   console affiche la commande manuelle.
3. Au démarrage, NEXUS relit les listes du pare-feu et repousse ce qui manque : un redémarrage
   d'équipement ne doit pas lever une quarantaine en silence.

La quarantaine réseau laisse volontairement passer la télémétrie vers le SOC. C'est ce qui la
distingue de l'isolation locale de l'agent, laquelle coupe la machine du réseau et donc aussi de
la supervision.

## 7. Place dans NEXUS SOC

`Modèles d'IA (scoring + explicabilité)` → `Moteur de corrélation (SIEM)` → **`SOAR (playbooks + garde-fous)`** → `Connecteurs + Portail + Notifications`.

Le SOAR est le dernier maillon de la chaîne de détection : il transforme une alerte en action,
tout en gardant l'humain dans la boucle pour les décisions lourdes.

## 8. Pistes d'amélioration (chapitre perspectives)

- Consolider `soar_engine.py` et le chemin d'exécution réel en une seule implémentation.
- Cartographier chaque action sur la phase de réponse MITRE D3FEND.
- Mesurer le **MTTR** réel, une fois les connecteurs branchés et la topologie déployée.
- Étendre l'isolation aux voisines de zone (isolation de port sur le commutateur), que la
  quarantaine par pare-feu ne couvre pas.
