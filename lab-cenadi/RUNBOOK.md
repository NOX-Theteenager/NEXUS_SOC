# CENADI — RUNBOOK de démonstration (déploiement souverain)

Démo ~30 min du déploiement souverain de NEXUS SOC au CENADI. Complémentaire
au RUNBOOK SaaS (`../lab/RUNBOOK.md`) : ici, l'angle est **souveraineté +
sécurisation**, pas produit-led growth.

## Message central à faire passer au jury

> « Le MÊME produit NEXUS SOC sert deux marchés avec deux modèles de
> déploiement. Pour une microfinance : SaaS multi-tenant (démo `../lab/`).
> Pour l'État — le CENADI — : déploiement souverain on-premise, zéro donnée
> sortante, PKI interne, air-gap de la solde. Voici le second. »

---

## Setup avant le jury (T-10 min)

```bash
# 1. Réseaux souverains
cd ~/Documents/Projets/NEXUS_SOC/lab-cenadi
./01-network-setup.sh

# 2. Config souveraine du hôte (PKI interne + .env souverain)
sudo bash scripts/host-cenadi-configure.sh
cp ~/Documents/Projets/NEXUS_SOC/.env.cenadi ~/Documents/Projets/NEXUS_SOC/.env
sudo systemctl restart nexus-soc

# 3. Vérifs
curl -s http://10.50.0.1:8000/health          # {"status":"ok",...}
openssl x509 -in ~/pki-cenadi/soc.cenadi.local.crt -noout -issuer   # CENADI Root CA
```

Positionner : terminal HÔTE (SOC), terminal vm-antilope, terminal vm-menace,
Firefox vm-rssi sur la console.

---

## Timeline (~30 min)

| Bloc | Durée | Écran | Scénario |
|------|-------|-------|----------|
| 1. Contexte souverain | 4 min | Slides + `00-architecture-cenadi.md` | — |
| 2. Sécurisation (7 couches) | 6 min | `SECURISATION.md` | — |
| 3. Souveraineté datacenter | 5 min | Terminal HÔTE | `scenarios/01` |
| 4. Air-gap zone sensible | 6 min | Terminal vm-antilope + vm-menace | `scenarios/02` |
| 5. Exfiltration + SOAR | 7 min | vm-app-gov + console RSSI | `scenarios/03` |
| 6. Questions | 2 min | — | — |

---

## Bloc 1 — Contexte souverain (4 min)

Afficher `00-architecture-cenadi.md`. Dialogue :

> « Le CENADI héberge ANTILOPE — la solde de centaines de milliers d'agents de
> l'État — et PROBMIS, le budget national. Ces données ne peuvent PAS partir
> chez un fournisseur SaaS ni sortir du territoire. NEXUS SOC se déploie donc
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

## Reset entre répétitions

```bash
for vm in vm-app-gov vm-antilope vm-rssi vm-menace; do
    virsh snapshot-revert "$vm" os-installed 2>/dev/null
done
docker exec nexus-postgres psql -U nexus -d nexus_soc -c \
  "DELETE FROM agents WHERE hostname LIKE 'SRV-%';"
```

## En cas de panne
- SOC injoignable depuis une zone → vérifier l'ACL MikroTik zone→mgmt (voir
  `SECURISATION.md` couche 2) et `ufw status`.
- Firefox refuse le certificat → l'AC racine CENADI n'a pas été importée sur
  vm-rssi (relancer `vm-rssi-setup.sh` après scp du `cenadi-root-ca.crt`).
- Pour revenir en mode SaaS : `cp .env` d'origine et `systemctl restart nexus-soc`.
