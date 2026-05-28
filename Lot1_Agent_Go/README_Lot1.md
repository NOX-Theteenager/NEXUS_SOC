# NEXUS SOC — Agent universel léger (Lot 1)

Source de télémétrie du SOC. Un petit programme installé sur chaque poste/serveur qui collecte
l'activité locale et l'envoie, en **egress-only**, vers la passerelle d'ingestion de NEXUS SOC,
laquelle la produit dans Kafka.

---

## 1. Caractéristiques de conception

- **Pur stdlib Go** — aucune dépendance externe : binaire compact, surface d'attaque minimale,
  compilation hors-ligne. **Taille mesurée : ≈ 5,0 Mo (Linux), 5,3 Mo (Windows)** — bien sous la
  cible de 15 Mo du cahier des charges.
- **Multiplateforme** — Linux et Windows à partir du même code.
- **Egress-only** — l'agent n'ouvre **aucun port entrant** ; il ne fait que des connexions
  **sortantes** (HTTPS). Il fonctionne donc derrière n'importe quel pare-feu, sans configuration
  réseau côté client.
- **Store-and-forward** — chaque lot est d'abord écrit dans une **file d'attente locale
  persistante** (un fichier par lot, écriture atomique). Si le serveur est injoignable (coupure
  réseau ou électrique), les lots sont **conservés et rejoués** à la reconnexion : aucune perte.
  La file est **bornée** (les plus anciens sont supprimés au-delà du seuil) pour ne pas remplir le disque.
- **Sobriété & authenticité** — envoi **compressé (gzip)** pour économiser la bande passante
  (contexte de connectivité limitée), **signé en HMAC-SHA256** pour garantir l'intégrité et
  l'authenticité du lot.

## 2. Ce que l'agent collecte (toutes les 30 s)

| Type | Détail |
|---|---|
| `process` | Processus actifs : nom, PID, chemin de l'exécutable, **empreinte SHA-256** (mise en cache) |
| `connection` | Connexions réseau : protocole, adresse locale/distante, état (depuis `/proc/net/tcp`) |
| `file_change` | Fichiers modifiés dans les répertoires surveillés (chemin, taille) |
| `system` | Hôte, OS, architecture, uptime, charge système |

> L'empreinte SHA-256 des exécutables est calculée par l'agent ; **l'enrichissement VirusTotal se
> fait côté serveur** (clé d'API centralisée, pas de secret sur chaque poste, pas de limite de débit
> dupliquée). C'est plus sûr et plus simple à exploiter.

## 3. Compilation

```bash
# Linux
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent .

# Windows
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o nexusagent.exe .
```

L'option `-ldflags="-s -w"` retire les symboles de débogage pour minimiser la taille.

## 4. Configuration (`config.json`)

```json
{
  "server_url": "https://ingest.nexussoc.cm/ingest",
  "enroll_token": "JETON_D_ENROLEMENT_A_USAGE_UNIQUE",
  "hmac_key": "CLE_HMAC_PROVISIONNEE_A_L_ENROLEMENT",
  "agent_id": "agent-poste-001",
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "interval_sec": 30,
  "watch_paths": ["/etc", "/home"],
  "spool_dir": "./spool",
  "max_spool_files": 500
}
```

> **Enrôlement** : l'agent s'authentifie avec un **jeton d'enrôlement** (en-tête `Authorization`)
> et une **clé HMAC** provisionnés au déploiement — et non un code court devinable.

## 5. Exécution

```bash
# Collecte un seul lot, l'affiche (JSON) puis quitte — idéal pour tester :
./nexusagent --once --config config.json

# Fonctionnement en continu (boucle toutes les interval_sec) :
./nexusagent --config config.json
```

`telemetry_sample.json` contient un exemple réel de lot produit par l'agent.

## 6. Intégration dans NEXUS SOC

```
Agent → (HTTPS egress) → Passerelle /ingest → Kafka (nexus.telemetry.raw)
      → normalisation / agrégation (pipeline, lot suivant) → features
      → service de scoring (Modèles 1 & 2) → alertes → SOAR
```

La passerelle `/ingest` est exposée par le **service de scoring** du socle (Lot 0) : elle
décompresse le lot et publie chaque événement brut sur le topic `nexus.telemetry.raw`. La
transformation de la télémétrie brute en *features* exploitables par les modèles (normalisation,
agrégation agent-jour, calcul des features de flux) est l'objet du **lot suivant** (pipeline/SIEM).

## 7. Limites mesurées et garanties

- Empreinte binaire validée (~5 Mo) ; le coût CPU est borné (calcul de hash mis en cache et
  plafonné par cycle).
- L'agent **ne parle jamais directement à Kafka** : Kafka reste interne, jamais exposé aux postes.
- La résilience hors-ligne est démontrable : couper le serveur fait s'accumuler les lots en file,
  qui repartent dès la reconnexion.

## 8. Pistes (chapitre perspectives)

- **Chiffrement applicatif (E2EE)** du corps en complément du TLS (AES-256-GCM avec clé d'enrôlement).
- **Signature des binaires** et **canal de mise à jour sécurisé** (anti supply-chain).
- Watcher de fichiers événementiel (inotify/ETW) à la place de la scrutation, pour les très grands volumes.
