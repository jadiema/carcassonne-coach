"""Calibration des spots de paysans : pour une partie dont seul le décompte final
diffère de BGA, essaie toutes les affectations de champ des paysans ambigus et
indique celles qui reproduisent BGA.   Usage : python calibrate_spots.py parties"""
import json, sys, itertools, copy
from pathlib import Path
import replay_bga as R, carcassonne_engine as E
for f in sorted(Path(sys.argv[1]).glob("*.json")):
    d = json.load(open(f, encoding="utf-8"))
    try:
        R.replay(d); continue
    except R.ReplayError as e:
        rep = getattr(e, "rep", {})
    if "final_state" not in rep:
        continue
    g, hist = rep["final_state"]
    G = R.parse_game(d)
    want = G["final"]
    before = list(g.scores)
    farmers = [(p, t) for p, t in g.board.items()
               if t.meeple_spot and t.meeple_spot.startswith("field") and len(E.tile_field_segments(t)) > 1]
    print(f"\n{f.name}: BGA {want}, {len(farmers)} paysans ambigus")
    sols = []
    for combo in itertools.product(*[E.tile_field_segments(t) for _, t in farmers]):
        g2 = copy.deepcopy(g)
        for (p, _), seg in zip(farmers, combo):
            g2.board[p].meeple_spot = f"field_{min(seg)}"
        b = list(g2.scores); g2.final_scoring()
        if [g2.scores[i] - b[i] for i in range(2)] == want:
            sols.append(combo)
    print("  solutions:", len(sols))
    if sols:
        for (p, t), seg in zip(farmers, sols[0]):
            spot = R.parse_game(d)["board"]
            bid = next(b for b, v in spot.items() if (v["x"], v["y"]) == p)
            n = spot[bid]["meeple"][1]
            cur = E._farmer_segment(t)
            orig = sorted((h - 2 * t.rotation) % 8 for h in seg)
            same = all(s[[q for q, _ in farmers].index(p)] == seg for s in sols)
            if cur != seg or True:
                print(f"   {t.tile_type.edges:<5} conn={t.tile_type.connected_city} rot={t.rotation} spot BGA {n}: "
                      f"table→{sorted((h - 2*t.rotation) % 8 for h in cur)}  correct→{orig} {'(sûr)' if same else '(ambigu)'}"
                      + ("  ❗" if cur != seg else ""))
