#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — Déploiement du collecteur sur les VM allumées
#
#    bash lab-cenadi/scripts/deployer-collecteur.sh              # aperçu
#    bash lab-cenadi/scripts/deployer-collecteur.sh --appliquer
#
#  À exécuter DEPUIS L'HÔTE, à la racine du dépôt.
#
#  POURQUOI CE SCRIPT EXISTE
#  -------------------------
#  NEXUS ne peut pas mettre ses agents à jour tout seul. Le collecteur est
#  uniquement ÉMETTEUR : il envoie sa télémétrie et n'interroge jamais le
#  serveur. Il n'existe donc aucun canal serveur → agent, et la plateforme n'a
#  aucun moyen de pousser quoi que ce soit sur une machine.
#
#  La version n'apparaîtra dans la console que lorsque le FICHIER du collecteur
#  aura été remplacé sur chaque VM et son service redémarré. C'est ce que fait
#  ce script, en SSH, machine par machine.
#
#  CE QU'IL NE FAIT PAS
#  --------------------
#  Il ne devine pas vos identifiants. Si vos VM demandent un mot de passe SSH,
#  il vous sera demandé à chaque machine. Pour un déploiement sans interruption,
#  installez d'abord une clé :  ssh-copy-id <utilisateur>@<ip>
# =============================================================================
set -uo pipefail

APPLIQUER=0
[[ "${1:-}" == "--appliquer" ]] && APPLIQUER=1

SOURCE="Lot1_Agent_Go/nexus_collector.py"
[[ -f "$SOURCE" ]] || { echo "✗ Lancez le script depuis la racine du dépôt." >&2; exit 1; }
VERSION=$(grep -oP 'VERSION_AGENT\s*=\s*"\K[^"]+' "$SOURCE")

# hôte:utilisateur:URL du SOC — l'URL diffère selon la zone de la machine.
CIBLES=(
  "192.168.122.20:noxtheteenager:http://192.168.122.1:8000"   # vm-app-gov
  "192.168.122.125:antilope:http://192.168.122.1:8000"        # vm-antilope
  "192.168.122.25:rssi:http://192.168.122.1:8000"             # vm-rssi
  "10.50.50.50:kali:http://10.50.50.1:8000"                   # KaliPrime (zone Menace)
)

echo "Collecteur à déployer : version $VERSION"
[[ $APPLIQUER -eq 0 ]] && echo "MODE APERÇU — rien ne sera modifié. Ajoutez --appliquer pour agir."
echo

for cible in "${CIBLES[@]}"; do
  IFS=: read -r ip user soc <<< "$cible"

  # Une machine éteinte n'est pas une erreur : on la saute et on le dit.
  if ! ping -c1 -W1 "$ip" >/dev/null 2>&1; then
    printf '  %-16s éteinte ou injoignable — ignorée\n' "$ip"
    continue
  fi
  if ! timeout 3 bash -c "</dev/tcp/$ip/22" 2>/dev/null; then
    printf '  %-16s allumée, SSH fermé — installer openssh-server\n' "$ip"
    continue
  fi

  if [[ $APPLIQUER -eq 0 ]]; then
    # Trois situations à ne pas confondre : pas d'accès, pas de collecteur,
    # collecteur présent mais trop ancien pour porter une version. Le message
    # précédent les résumait toutes par « inconnue ou clé SSH absente », ce qui
    # laissait croire à un problème d'accès alors que la clé fonctionnait.
    etat=$(timeout 8 ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$user@$ip" '
        if [ ! -f /opt/nexus-agent/nexus_collector.py ]; then echo "AUCUN"; else
          v=$(grep -oP "VERSION_AGENT\s*=\s*\"\K[^\"]+" /opt/nexus-agent/nexus_collector.py 2>/dev/null)
          [ -n "$v" ] && echo "V:$v" || echo "ANCIEN"
        fi' 2>/dev/null) || etat=""
    case "$etat" in
      V:*)    msg="version ${etat#V:}" ;;
      ANCIEN) msg="collecteur antérieur à 1.4.0 (ne transmet pas sa version)" ;;
      AUCUN)  msg="aucun collecteur installé" ;;
      *)      msg="accès SSH refusé — lancez ssh-copy-id $user@$ip" ;;
    esac
    printf '  %-16s prête · %s\n' "$ip" "$msg"
    continue
  fi

  # Voie préférée : l'agent invité QEMU. Il ne demande aucun identifiant — le
  # canal virtio-serial passe par l'hyperviseur, que vous contrôlez déjà. Si le
  # paquet qemu-guest-agent n'est pas installé sur la VM, on retombe sur SSH.
  dom=$(virsh -c qemu:///system list --name 2>/dev/null | while read -r d; do
          [ -n "$d" ] && virsh -c qemu:///system domifaddr "$d" 2>/dev/null | grep -q "$ip" && echo "$d"
        done | head -1)
  if [[ -n "$dom" ]] && timeout 6 virsh -c qemu:///system qemu-agent-command "$dom" \
        '{"execute":"guest-ping"}' >/dev/null 2>&1; then
    printf '  %-16s via agent invité (%s)… ' "$ip" "$dom"
    if python3 "$(dirname "$0")/deployer-via-qga.py" "$dom" "$SOURCE" >/dev/null 2>&1; then
      echo "✓ déployé, empreinte vérifiée"
    else
      echo "✗ échec — voir deployer-via-qga.py pour le détail"
    fi
    continue
  fi

  printf '  %-16s déploiement… ' "$ip"

  # Le succès est CONSTATÉ, jamais supposé : on relit la version installée sur
  # la machine après coup. La version précédente de ce script masquait les
  # erreurs (2>/dev/null, « || true ») et annonçait « déployé » alors que
  # `sudo install` avait échoué faute de mot de passe. Un déploiement qui ment
  # sur son résultat est pire que pas de déploiement du tout.
  if ! scp -q -o StrictHostKeyChecking=accept-new "$SOURCE" "$user@$ip:/tmp/nexus_collector.py" 2>/dev/null; then
    echo "✗ copie refusée — vérifiez l'accès SSH"
    continue
  fi

  sortie=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$user@$ip" '
      set -e
      if sudo -n true 2>/dev/null; then S="sudo -n"; else S=""; fi
      if [ -z "$S" ] && [ ! -w /opt/nexus-agent/nexus_collector.py ]; then
        echo "BESOIN_SUDO"; exit 0
      fi
      $S install -m 0755 /tmp/nexus_collector.py /opt/nexus-agent/nexus_collector.py
      rm -f /tmp/nexus_collector.py
      $S systemctl restart nexus-collector.service 2>/dev/null || echo "SERVICE_KO"
      grep -oP "VERSION_AGENT\s*=\s*\"\K[^\"]+" /opt/nexus-agent/nexus_collector.py
  ' 2>&1 | tail -2 | tr '\n' ' ')

  case "$sortie" in
    *BESOIN_SUDO*) echo "✗ sudo exige un mot de passe — voir les deux solutions en fin de script" ;;
    *"$VERSION"*)
      case "$sortie" in
        *SERVICE_KO*) echo "⚠ fichier installé en $VERSION mais service non relancé" ;;
        *)            echo "✓ déployé et vérifié en $VERSION" ;;
      esac ;;
    *) echo "✗ échec — version sur la machine : ${sortie:-inconnue}" ;;
  esac
done

cat <<'EOF'

L'hôte (NoxTheMachine) exécute le collecteur directement depuis le dépôt :
un simple redémarrage suffit, sans copie.

    sudo systemctl restart nexus-collector.service

Les versions apparaissent dans la console au premier lot suivant le
redémarrage, soit au maximum une minute après.

── Si une machine répond « sudo exige un mot de passe » ────────────────────
Le fichier est bien copié dans /tmp, seule l'installation échoue. Deux voies,
à faire une fois par machine :

  A. Agent invité QEMU — le plus utile : plus aucun identifiant ensuite, ni
     pour ce script ni pour les suivants. Le canal virtio-serial est déjà
     câblé sur les quatre VM du lab.
         sudo apt install -y qemu-guest-agent
         sudo systemctl enable --now qemu-guest-agent

  B. Règle sudo restreinte à ce déploiement, rien de plus :
         echo "$USER ALL=(root) NOPASSWD: /usr/bin/install -m 0755 /tmp/nexus_collector.py /opt/nexus-agent/nexus_collector.py, /usr/bin/systemctl restart nexus-collector.service" \
           | sudo tee /etc/sudoers.d/nexus-deploiement
         sudo chmod 0440 /etc/sudoers.d/nexus-deploiement
EOF
