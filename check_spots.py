"""
Vérifie la table des spots BGA (_bga_zones) sur toutes les parties d'un dossier.
Usage : python check_spots.py parties
Pour chaque type de tuile : numéros de spot observés vs nombre de zones du moteur,
et quelques exemples (fichier, position, rotation) pour aller vérifier sur BGA.
"""
import json, sys
from collections import defaultdict
from pathlib import Path
import carcassonne_engine as E

seen = defaultdict(lambda: defaultdict(int))
examples = defaultdict(list)
for f in sorted(Path(sys.argv[1]).glob("*.json")):
    try:
        data = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    for t in data.get("board", []):
        m = t.get("meeple")
        if not m or not t.get("location"):
            continue
        tt = E._find_tile_type(t["edgesOriginal"], t.get("shield", False), t.get("desc", ""))
        if tt is None:
            continue
        key = (t["edgesOriginal"], t.get("desc", ""))
        seen[key][m["spot"]] += 1
        n = len(E._bga_zones(tt))
        if m["spot"] > n and len(examples[key]) < 3:
            examples[key].append(f'{f.name}  ({t["location"]["x"]},{t["location"]["y"]}) '
                                 f'rot={t["rotation"]} bgId={t["bgId"]}')

print(f"{'type':<6} {'description':<40} zones  spots observés (nombre)")
for key in sorted(seen):
    edges, desc = key
    tt = E._find_tile_type(edges, "blason" in desc, desc)
    n = len(E._bga_zones(tt))
    spots = dict(sorted(seen[key].items()))
    flag = "  ⚠️" if max(spots) > n else ""
    print(f"{edges:<6} {desc[:40]:<40} {n:>5}  {spots}{flag}")
    for ex in examples[key]:
        print(f"         ↳ {ex}")
