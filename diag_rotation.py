"""
Diagnostic du sens de rotation de l'augmentation (replay_bga.rotate_state).

Pour chaque coup de quelques parties, on tourne le plateau de k quarts de tour
(k = 1, 2, 3) de deux façons et on vérifie que le coup joué reste LÉGAL :
  A : convention actuelle   — tuiles et coup : rotation + k
  B : convention inverse    — tuiles et coup : rotation - k
La bonne convention doit donner 100 % pour k = 1, 2 et 3.

Usage :  python diag_rotation.py parties          (10 premières parties)
         python diag_rotation.py parties 30       (30 parties)
"""
import json, sys
from copy import deepcopy
from pathlib import Path
import replay_bga as R


def rotate(state, k, sign):
    k %= 4
    s = deepcopy(state)
    if k == 0:
        return s
    new = {}
    for (x, y), t in s.board.items():
        for _ in range(k):
            x, y = -y, x
        t.x, t.y = x, y
        t.rotation = (t.rotation + sign * k) % 4
        new[(x, y)] = t
    s.board = new
    s.valid_positions = None
    return s


def main():
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "parties")
    n_games = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    files = []
    for f in sorted(folder.glob("*.json")):
        if json.load(open(f, encoding="utf-8")).get("rawLog"):
            files.append(f)
        if len(files) >= n_games:
            break
    stats = {(conv, k): [0, 0] for conv in "AB" for k in range(4)}
    for f in files:
        _, states, _ = R.replay(json.load(open(f, encoding="utf-8")))
        for state, (x, y, rot, _), _ in states:
            for k in range(4):
                mx, my = x, y
                for _ in range(k):
                    mx, my = -my, mx
                for conv, sign in (("A", +1), ("B", -1)):
                    s = rotate(state, k, sign)
                    try:
                        ok = (mx, my, (rot + sign * k) % 4) in s.get_legal_placements(s.current_tile)
                    except Exception:
                        ok = False
                    st = stats[(conv, k)]; st[0] += 1; st[1] += ok
        print(f"  {f.name}")
    print("\n  Coups restés légaux après rotation du plateau :")
    print("            k=0      k=1      k=2      k=3")
    for conv, label in (("A", "A (+k, actuel)"), ("B", "B (-k)        ")):
        row = "  ".join(f"{stats[(conv, k)][1] / max(stats[(conv, k)][0], 1):6.1%}" for k in range(4))
        print(f"  {label}  {row}")


if __name__ == "__main__":
    main()
