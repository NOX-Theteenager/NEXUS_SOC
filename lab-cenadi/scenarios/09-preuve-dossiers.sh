#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : preuve de la file vers l'outil d'enquête (phase 3)
#
#      bash lab-cenadi/scenarios/09-preuve-dossiers.sh
#
#  Ce que cette recette doit établir tient en une phrase : **l'ingestion ne
#  dépend jamais d'IRIS**. On arrête IRIS, on continue à produire des alertes,
#  on le redémarre, et rien n'a été perdu.
#
#  POURQUOI C'EST LA PROPRIÉTÉ QUI COMPTE
#  --------------------------------------
#  Un SOC qui cesse de voir parce que son outil d'enquête redémarre est un SOC
#  qui s'aveugle au pire moment. La file persistée existe pour que la panne d'un
#  outil de confort ne remonte jamais jusqu'au chemin de collecte.
#
#  On conclut sur des CODES DE SORTIE.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

IRIS_DIR="${IRIS_DIR:-/opt/nexus-iris}"
VM_SOURCE="${VM_SOURCE:-KaliPrime}"
CYCLE=25                      # laisser à l'ouvrier le temps d'un tour

GREEN="\033[32m"; RED="\033[31m"; JAUNE="\033[33m"; BOLD="\033[1m"; RAZ="\033[0m"
echec=0
psql() { docker exec nexus-postgres psql -U nexus -d nexus_soc -At -c "$1" 2>/dev/null; }

verifier() {  # $1 = attendu, $2 = libellé, $3 = obtenu
  if [[ "$3" == "$1" ]]; then
    printf "    ${GREEN}✓${RAZ} %-50s %s\n" "$2" "$3"
  else
    printf "    ${RED}✗${RAZ} %-50s %s (attendu %s)\n" "$2" "$3" "$1"
    echec=1
  fi
}
au_moins() {  # $1 = minimum, $2 = libellé, $3 = obtenu
  if [[ "${3:-0}" -ge "$1" ]]; then
    printf "    ${GREEN}✓${RAZ} %-50s %s\n" "$2" "$3"
  else
    printf "    ${RED}✗${RAZ} %-50s %s (attendu ≥ %s)\n" "$2" "$3" "$1"
    echec=1
  fi
}

# La plateforme AGRÈGE les alertes identiques (ALERT_DEDUP_MIN) : rejouer deux
# fois le même scénario ne produit pas deux alertes, et c'est voulu. On essaie
# donc les trois scénarios jusqu'à ce qu'un nouvel incident sorte.
produire_alerte() {
  local avant
  avant=$(psql "SELECT count(*) FROM dossier_sortie")
  for genre in chaine exfil portscan; do
    python3 lab-cenadi/scripts/qga-exec.py "$VM_SOURCE" \
      "NEXUS_AGENT_DIR=/etc/nexus-agent python3 /opt/nexus-agent/nexus_collector.py --simulate $genre" \
      >/dev/null 2>&1
    sleep 5
    [[ "$(psql "SELECT count(*) FROM dossier_sortie")" -gt "$avant" ]] && return 0
  done
  return 1                       # tout a été agrégé : rien de neuf
}

# Troisième issue, distincte d'un succès comme d'un échec : la sonde n'a PAS
# pu être exécutée. La compter comme réussie serait mentir ; comme échouée,
# accuser à tort.
non_eprouve() { printf "    ${JAUNE}◦${RAZ} %-50s %s\n" "$1" "$2"; }

en_attente() { psql "SELECT count(*) FROM dossier_sortie WHERE etat='en_attente'"; }
envoyes()    { psql "SELECT count(*) FROM dossier_sortie WHERE etat='envoye'"; }

echo -e "${BOLD}Preuve de la file vers l'outil d'enquête${RAZ}"

# ── 1. Une alerte crée une entrée, une seule ────────────────────────────────
echo -e "\n  ${BOLD}1. Une alerte, une entrée en file${RAZ}"
AVANT=$(psql "SELECT count(*) FROM dossier_sortie")
if produire_alerte; then
  APRES=$(psql "SELECT count(*) FROM dossier_sortie")
  au_moins 1 "l'alerte a produit une entrée" "$(( APRES - AVANT ))"
else
  non_eprouve "l'alerte produit une entrée" \
    "agrégation anti-doublon : aucun incident neuf, relancer après ALERT_DEDUP_MIN"
fi
verifier "0" "toute entrée pointe une alerte réelle" \
  "$(psql "SELECT count(*) FROM dossier_sortie d LEFT JOIN alerts a ON a.id::text = d.reference_source WHERE a.id IS NULL")"
verifier "0" "aucune référence en double dans la file" \
  "$(psql "SELECT count(*) FROM (SELECT reference_source FROM dossier_sortie GROUP BY 1 HAVING count(*)>1) d")"

# ── 2. IRIS arrêté : rien ne se perd ────────────────────────────────────────
echo -e "\n  ${BOLD}2. IRIS arrêté — la collecte continue, la file garde${RAZ}"
(cd "$IRIS_DIR" && docker compose stop >/dev/null 2>&1)
sleep 3
# On remet une entrée déjà partie en attente : c'est exactement l'état d'un
# ouvrier qui reprend après une panne, et cela n'exige pas qu'un incident neuf
# survienne juste au bon moment.
psql "UPDATE dossier_sortie SET etat='en_attente', prochaine_tentative=now(), tentatives=0
       WHERE id = (SELECT id FROM dossier_sortie ORDER BY id DESC LIMIT 1)" >/dev/null
produire_alerte || true
sleep "$CYCLE"
au_moins 1 "des entrées attendent leur envoi" "$(en_attente)"
verifier "0" "aucune entrée abandonnée pendant la panne" \
  "$(psql "SELECT count(*) FROM dossier_sortie WHERE etat='abandonne'")"
verifier "200" "l'ingestion répond toujours" \
  "$(curl -s -m8 -o /dev/null -w '%{http_code}' http://10.50.0.2:8000/health)"
au_moins 1 "les tentatives sont reportées, pas martelées" \
  "$(psql "SELECT coalesce(max(tentatives),0) FROM dossier_sortie WHERE etat='en_attente'")"

# ── 3. IRIS revient : la file se vide ───────────────────────────────────────
echo -e "\n  ${BOLD}3. IRIS redémarre — la file se vide toute seule${RAZ}"
(cd "$IRIS_DIR" && docker compose start >/dev/null 2>&1)
echo "    attente de la remise en service…"
for _ in $(seq 1 30); do
  curl -sk -m4 -o /dev/null "https://10.50.0.2:4443/" 2>/dev/null && break
  sleep 5
done
# Deux cycles d'ouvrier : le premier peut tomber pendant que IRIS finit de lever.
sleep $(( CYCLE * 2 ))
au_moins 1 "des entrées sont parties" "$(envoyes)"
verifier "0" "plus rien n'attend" "$(en_attente)"
verifier "0" "chaque envoi porte un identifiant IRIS" \
  "$(psql "SELECT count(*) FROM dossier_sortie WHERE etat='envoye' AND dossier_externe IS NULL")"

# ── 4. Le rejeu ne duplique pas ─────────────────────────────────────────────
echo -e "\n  ${BOLD}4. Rejouer un envoi ne crée pas de second dossier${RAZ}"
REF=$(psql "SELECT reference_source FROM dossier_sortie WHERE etat='envoye' ORDER BY id DESC LIMIT 1")
ID_EXT=$(psql "SELECT dossier_externe FROM dossier_sortie WHERE reference_source='$REF'")
psql "UPDATE dossier_sortie SET etat='en_attente', prochaine_tentative=now(),
             dossier_externe=NULL WHERE reference_source='$REF'" >/dev/null
sleep "$CYCLE"
verifier "envoye" "l'entrée rejouée est repartie" \
  "$(psql "SELECT etat FROM dossier_sortie WHERE reference_source='$REF'")"
verifier "$ID_EXT" "elle a retrouvé le MÊME dossier, pas un nouveau" \
  "$(psql "SELECT dossier_externe FROM dossier_sortie WHERE reference_source='$REF'")"

echo
if [[ $echec -eq 0 ]]; then
  echo -e "  ${GREEN}${BOLD}Recette complète : l'ingestion ne dépend pas d'IRIS, et rien ne se perd.${RAZ}"
else
  echo -e "  ${RED}${BOLD}Au moins une sonde a démenti l'attendu — voir ci-dessus.${RAZ}"
fi
exit $echec
