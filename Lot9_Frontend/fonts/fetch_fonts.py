import re, subprocess, os, pathlib, sys

OUT = pathlib.Path("/home/noxtheteenager/Documents/Projets/NEXUS_SOC/Lot9_Frontend/fonts")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

REQ = [
    ("fraunces", "Fraunces:ital,opsz,wght@0,9..144,400..700;1,9..144,400..700"),
    ("manrope",  "Manrope:wght@400..700"),
    ("jetbrains","JetBrains+Mono:wght@400..500"),
]
KEEP = {"latin", "latin-ext"}

def curl(url, binary=False):
    r = subprocess.run(["curl","-sS","-m","40","-A",UA,url], capture_output=True)
    r.check_returncode()
    return r.stdout if binary else r.stdout.decode()

blocks_out = []
for slug, fam in REQ:
    css = curl(f"https://fonts.googleapis.com/css2?family={fam}&display=swap")
    # split into (comment subset name, @font-face block)
    parts = re.findall(r"/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})", css)
    idx = 0
    for subset, block in parts:
        if subset not in KEEP:
            continue
        m = re.search(r"url\((https://[^)]+\.woff2)\)", block)
        if not m:
            continue
        style = "italic" if "font-style: italic" in block else "normal"
        name = f"{slug}-{subset}-{style}.woff2"
        data = curl(m.group(1), binary=True)
        (OUT/name).write_bytes(data)
        newblock = block.replace(m.group(1), f"./{name}")
        newblock = re.sub(r"\n\s*font-display:[^;]*;", "\n  font-display: swap;", newblock)
        blocks_out.append((subset, name, len(data), newblock))
        idx += 1

hdr = """/* NEXUS SOC — Polices auto-hébergées (souveraineté : aucune requête externe)
 * Fraunces, Manrope, JetBrains Mono — sous-ensembles latin + latin-ext, format WOFF2 variable.
 * Sources : Google Fonts, licence SIL Open Font License 1.1 (voir THIRD_PARTY_LICENSES.md).
 * Regénérer : python3 tools/fetch_fonts.py
 * Ne jamais réintroduire fonts.googleapis.com : le déploiement CENADI est coupé d'Internet.
 */
"""
with open(OUT/"fonts.css","w") as f:
    f.write(hdr)
    for subset, name, size, block in blocks_out:
        f.write(f"\n/* {name} — {size//1024} Ko */\n{block}\n")

total = sum(s for _,_,s,_ in blocks_out)
for subset, name, size, _ in blocks_out:
    print(f"{name:44s} {size//1024:4d} Ko")
print(f"TOTAL {total//1024} Ko")
