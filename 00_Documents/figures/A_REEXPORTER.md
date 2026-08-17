# PNG à réexporter avant de coller dans le mémoire

Les sources `.drawio` ont été refaites le **17 août 2026** (OPNsense à la place
de pfSense et MikroTik, politique de sortie par zone, couche investigation).
Les PNG datent du **11 août** et montrent encore l'ancienne architecture.

**Un PNG périmé collé dans le rapport montrerait un pare-feu qui n'existe plus
dans le projet.** C'est exactement l'écart que la phase 0 vise à supprimer.

| Fichier | État | Action |
|---|---|---|
| `topologie-reseau-souveraine.png` | **périmé** (pfSense + MikroTik) | réexporter |
| `defense-en-profondeur-7-couches.png` | **périmé** (couche 2) | réexporter |
| `airgap-zone-sensible.png` | **périmé** (10.50.0.1, MikroTik) | réexporter |
| `chaine-reponse-collaborative.png` | **absent** | exporter |
| `Architecture_NEXUS_SOC.png` | à produire si utilisé | exporter |

## Comment réexporter

Dans l'application draw.io de bureau, ouvrir chaque `.drawio` puis
**Fichier → Exporter → PNG**, avec :

- Zoom 400 % (équivalent 400 dpi, cohérent avec les PNG existants)
- Bordure 10 px
- Fond transparent décoché, fond blanc

En ligne de commande, si le paquet est installé :

```bash
cd 00_Documents/figures
for f in *.drawio; do
    drawio -x -f png -s 4 --border 10 -o "${f%.drawio}.png" "$f"
done
drawio -x -f png -s 4 --border 10 \
    -o Architecture_NEXUS_SOC.png ../Architecture_NEXUS_SOC.drawio
```

Supprimer ce fichier une fois les cinq exports faits.
