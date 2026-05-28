# NEXUS SOC — Moteur SOAR (réponse automatisée encadrée)

Le SOAR (*Security Orchestration, Automation and Response*) **boucle la couche IA** : il consomme
les alertes produites par les modèles (Modèle 1 réseau, Modèle 2 fraude) et déclenche une
**réponse automatisée** via des **playbooks**, sous le contrôle de **garde-fous**.

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

## 6. Connecteurs (intégration réelle)

Dans cette démonstration, les actions sont **simulées** (pas de vrai pare-feu ni d'annuaire).
En production, chaque fonction `_freeze_account`, `_isolate_host`, `_block_ip`, etc. appelle le
connecteur correspondant (Active Directory/LDAP pour le gel de compte, API du pare-feu pour le
blocage, EDR/agent pour l'isolation, passerelle SMS/WhatsApp pour les notifications). L'interface
ne change pas : seul le corps des connecteurs est branché sur les systèmes réels.

## 7. Place dans NEXUS SOC

`Modèles d'IA (scoring + explicabilité)` → `Moteur de corrélation (SIEM)` → **`SOAR (playbooks + garde-fous)`** → `Connecteurs + Portail + Notifications`.

Le SOAR est le dernier maillon de la chaîne de détection : il transforme une alerte en action,
tout en gardant l'humain dans la boucle pour les décisions lourdes.

## 8. Pistes d'amélioration (chapitre perspectives)

- Brancher les connecteurs réels (AD/LDAP, pare-feu, EDR, passerelle SMS).
- Ajouter une file d'approbation visible dans le portail (workflow de validation).
- Cartographier chaque action sur la phase de réponse MITRE D3FEND.
- Mesurer le **MTTR** (temps moyen de réponse) réel apporté par l'automatisation.
