# NEXUS SOC — Configuration des services externes

En exploitation souveraine par le CENADI, la plateforme n'a **aucune dépendance
commerciale** (pas de passerelle de paiement, pas d'envoi d'e-mails
transactionnels externes). Le seul service externe optionnel est **VirusTotal**,
utilisé pour enrichir les indicateurs de compromission (IOC) dans le moteur SOAR.
Il peut être désactivé entièrement (`VIRUSTOTAL_ENABLED=false`) pour un
fonctionnement 100 % hors-ligne.

---

## VirusTotal — Enrichissement IOC dans le SOAR

### Création du compte & récupération de la clé

1. Aller sur <https://www.virustotal.com/gui/join-us> → créer un compte
2. Confirmer l'adresse e-mail
3. Aller sur <https://www.virustotal.com/gui/my-apikey>
4. Copier la **Public API Key** affichée (64 caractères hexadécimaux)

```env
# .env
VIRUSTOTAL_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
VIRUSTOTAL_ENABLED=true
VIRUSTOTAL_CACHE_HOURS=24    # cache local pour éviter le rate-limit
```

### Quotas et limites

La clé publique gratuite est limitée à :
- **4 requêtes / minute**
- **500 requêtes / jour**
- **15 500 requêtes / mois**

NEXUS SOC respecte ces limites en :
1. **Cachant** chaque verdict pendant `VIRUSTOTAL_CACHE_HOURS` (24 h par défaut)
   → un IOC vu deux fois dans la journée n'est pas recompté.
2. **Limitant** à 5 IOC max par alerte (les plus pertinents extraits par
   regex de l'entité et des `reasons`).
3. **Désactivation à chaud** possible via `VIRUSTOTAL_ENABLED=false` sans
   redémarrer (lu à chaque appel).

### Intégration dans les playbooks SOAR

Le connecteur `enrich_ioc` est en tête des 4 playbooks
([`Lot4_SOAR/soar_engine.py`](../Lot4_SOAR/soar_engine.py)) :

```python
PLAYBOOKS = {
    "Fraude interne":        ["enrich_ioc", "journal_investigation", "notify_dsi", ...],
    "Exfiltration":          ["enrich_ioc", "journal_investigation", "freeze_account", ...],
    "Ransomware":            ["enrich_ioc", "snapshot_memory", "isolate_host", ...],
    "Anomalie réseau / C2":  ["enrich_ioc", "journal_investigation", "block_ip", ...],
}
```

Pour chaque alerte, NEXUS SOC :
1. Extrait les IP, hashes et domaines présents dans `alert.entity` et `alert.reasons`
2. Interroge VirusTotal pour chacun (4 req/min max)
3. Pour les verdicts `malveillant` ou `suspect`, **ajoute la mention au rapport**
4. Cache le résultat 24 h dans la RAM du process

### Test rapide

```bash
.venv/bin/python -c "
import os; os.environ['VIRUSTOTAL_ENABLED'] = 'true'
import sys; sys.path.insert(0, 'Lot4_SOAR')
from virustotal_client import lookup
print(lookup('8.8.8.8'))            # Google DNS → propre
print(lookup('45.155.205.233'))     # IP connue malveillante
"
```

Attendu :
```json
{"ioc": "8.8.8.8", "verdict": "propre", "malicious": 0, ...}
{"ioc": "45.155.205.233", "verdict": "malveillant", "malicious": 15, ...}
```

### Dimensionnement

Pour l'ensemble des périmètres supervisés du CENADI, avec le cache 24 h
(~quelques dizaines de lookups uniques par jour), la clé publique gratuite
suffit largement. En cas de forte volumétrie, VirusTotal propose des offres
Intelligence / Enterprise à quotas élevés ; l'enrichissement reste toutefois
strictement optionnel et désactivable.

---

## Récapitulatif du fichier `.env`

```env
# ── VirusTotal (optionnel) ──────────────────────────────────────────────────
VIRUSTOTAL_API_KEY=
VIRUSTOTAL_ENABLED=false
VIRUSTOTAL_CACHE_HOURS=24
```
