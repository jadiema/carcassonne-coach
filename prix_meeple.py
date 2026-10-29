"""
💰 Le prix d'un meeple (λ) mesuré sur des parties réelles
=========================================================
Rejoue chaque partie (replay_bga) et suit chaque meeple de sa pose à son retour :
  - quand il est posé (tour de la partie, tuiles restantes, meeples encore libres) ;
  - sur quoi (ville, route, abbaye, pré) ;
  - combien de temps il reste bloqué (en tours de son propriétaire) ;
  - combien de points il rapporte.

Le prix d'un meeple λ est estimé comme son RENDEMENT : points rapportés par
tour passé sur le plateau. C'est la méthode « données » de la séance 2.

Points d'un meeple :
  - structure fermée en cours de partie : les points gagnés par son propriétaire
    à ce coup-là (partagés à parts égales s'il récupère plusieurs meeples) ;
  - meeple encore posé à la fin : sa part du décompte final de son propriétaire
    (valeur de Shapley : ses meeples d'un même pré ou d'une même ville se
    partagent les points qu'ils obtiennent ensemble).

Usage :
    python prix_meeple.py parties
    python prix_meeple.py parties --csv meeples.csv --png prix_meeple.png
"""
import argparse, csv, json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import replay_bga as R

KIND = {"city": "ville", "road": "route", "field": "pré", "monastery": "abbaye"}
TOTAL_TILES = 72


def kind_of(spot: str) -> str:
    return KIND.get(spot.split("_")[0], spot)


def meeples_on(state):
    """{(x, y): (joueur, emplacement)} des meeples présents sur le plateau."""
    return {(x, y): (t.meeple_player, t.meeple_spot)
            for (x, y), t in state.board.items() if t.meeple_player is not None and t.meeple_spot}


def after_last_move(states):
    snap, (x, y, rot, spot), mover = states[-1]
    s = deepcopy(snap)
    s.place_tile(s.current_tile, x, y, rot, mover if spot else None, spot)
    return s


def end_values(s_end, player, positions):
    """Part de chaque meeple du joueur dans son décompte final (valeur de Shapley).
    Deux paysans du même joueur dans le même pré se partagent ses points, au lieu
    de valoir 0 chacun (en retirer un seul ne changerait rien)."""
    from itertools import combinations
    from math import factorial
    positions = list(positions)
    n = len(positions)
    cache = {}

    def v(keep):
        if keep in cache:
            return cache[keep]
        s2 = deepcopy(s_end)
        for i, pos in enumerate(positions):
            if i not in keep:
                t = s2.board[pos]; t.meeple_player = None; t.meeple_spot = None
                s2.meeples[player] += 1
        before = s2.scores[player]
        s2.final_scoring()
        cache[keep] = s2.scores[player] - before
        return cache[keep]

    phi = [0.0] * n
    for i in range(n):
        others = [j for j in range(n) if j != i]
        for k in range(n):
            w = factorial(k) * factorial(n - k - 1) / factorial(n)
            for S in combinations(others, k):
                S = frozenset(S)
                phi[i] += w * (v(S | {i}) - v(S))
    return dict(zip(positions, phi))


def analyse_game(data):
    G, states, _ = R.replay(data)
    n = len(states)
    n_players = states[0][0].num_players
    episodes = []          # un dict par meeple posé
    open_ep = {}           # (x, y) -> épisode en cours
    for i, (snap, (x, y, rot, spot), mover) in enumerate(states):
        nxt = states[i + 1][0] if i + 1 < n else after_last_move(states)
        if spot:
            ep = {"player": mover, "kind": kind_of(spot), "t0": i,
                  "tiles_left": TOTAL_TILES - 1 - len(snap.board),
                  "free_before": snap.meeples[mover], "points": 0.0, "t1": None}
            open_ep[(x, y)] = ep
            episodes.append(ep)
        # meeples rendus pendant ce coup
        on_after = meeples_on(nxt)
        returned = defaultdict(list)
        for pos, ep in list(open_ep.items()):
            if pos not in on_after or on_after[pos][0] != ep["player"]:
                returned[ep["player"]].append(ep)
                ep["t1"] = i
                del open_ep[pos]
        for p, eps in returned.items():
            gain = nxt.scores[p] - snap.scores[p]
            for ep in eps:
                ep["points"] = gain / len(eps)
    # fin de partie : contribution au décompte final
    s_end = after_last_move(states)
    final_check = None
    for p in range(n_players):
        mine = [pos for pos, ep in open_ep.items() if ep["player"] == p]
        if not mine:
            continue
        for pos, val in end_values(s_end, p, mine).items():
            ep = open_ep[pos]
            ep["points"] = float(val)
            ep["t1"] = n
            ep["end"] = True
    for ep in episodes:
        own_turns = (ep["t1"] - ep["t0"]) / n_players
        ep["turns"] = max(1.0, own_turns)
        ep.setdefault("end", False)
    return episodes, G["final_scores"], final_check


def phase_label(tiles_left):
    lo = (tiles_left // 10) * 10
    return f"{lo:2d}–{min(lo + 9, 71):2d}"


def table(title, groups, order, horizon=False):
    print(f"\n── {title}")
    print(f"   {'':<14}{'meeples':>8}{'points moy.':>13}{'tours bloqués':>15}{'λ = pts/tour':>14}"
          + (f"{'λ × tours restants':>20}" if horizon else ""))
    rows = []
    for k in order:
        eps = groups.get(k, [])
        if not eps:
            continue
        pts = sum(e["points"] for e in eps); tr = sum(e["turns"] for e in eps)
        lam = pts / tr
        left = sum(e["tiles_left"] for e in eps) / len(eps) / 2   # tours restants du joueur (2 joueurs)
        rows.append((k, len(eps), pts / len(eps), tr / len(eps), lam, lam * left))
        print(f"   {str(k):<14}{len(eps):>8}{pts / len(eps):>13.1f}{tr / len(eps):>15.1f}{lam:>14.2f}"
              + (f"{lam * left:>20.1f}" if horizon else ""))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--csv", default="prix_meeple.csv")
    ap.add_argument("--png", default="prix_meeple.png")
    a = ap.parse_args()
    all_eps, ok, ko = [], 0, 0
    for f in sorted(Path(a.data_dir).glob("*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
            if not data.get("rawLog"):
                continue
            eps, final, check = analyse_game(data)
            for e in eps:
                e["game"] = f.name
            all_eps += eps
            ok += 1
            if ok % 25 == 0:
                print(f"   … {ok} parties analysées")
        except Exception as e:
            ko += 1
            print(f"   ⚠️ {f.name} ignorée : {e}")
    print(f"\n{ok} parties analysées ({ko} ignorées), {len(all_eps)} meeples suivis")
    if not all_eps:
        return

    by_phase = defaultdict(list)
    for e in all_eps:
        by_phase[phase_label(e["tiles_left"])].append(e)
    phases = sorted(by_phase, key=lambda k: -int(k.split("–")[0]))
    rows = table("Prix d'un meeple selon le moment de la pose (tuiles restantes)", by_phase, phases, horizon=True)
    print("   λ × tours restants : ce qu'un meeple libre pourrait encore rapporter d'ici la fin, au même rendement.")

    by_kind = defaultdict(list)
    for e in all_eps:
        by_kind[e["kind"]].append(e)
    table("Selon la structure", by_kind, ["ville", "route", "abbaye", "pré"])

    by_free = defaultdict(list)
    for e in all_eps:
        by_free[f"{e['free_before']} libres"].append(e)
    table("Selon le nombre de meeples libres avant la pose", by_free,
          [f"{k} libres" for k in range(7, 0, -1)])

    # par phase et par structure (λ seulement)
    print("\n── λ par phase et par structure (points par tour bloqué)")
    print(f"   {'':<10}" + "".join(f"{k:>9}" for k in ["ville", "route", "abbaye", "pré"]))
    for ph in phases:
        line = f"   {ph:<10}"
        for k in ["ville", "route", "abbaye", "pré"]:
            eps = [e for e in by_phase[ph] if e["kind"] == k]
            line += f"{(sum(e['points'] for e in eps) / sum(e['turns'] for e in eps)):>9.2f}" if len(eps) >= 20 else f"{'—':>9}"
        print(line)
    print("   (— : moins de 20 meeples dans la case)")

    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["partie", "joueur", "structure", "coup", "tuiles_restantes",
                    "meeples_libres_avant", "tours_bloque", "points", "fin_de_partie"])
        for e in all_eps:
            w.writerow([e["game"], e["player"], e["kind"], e["t0"], e["tiles_left"],
                        e["free_before"], f"{e['turns']:.1f}", f"{e['points']:.2f}", int(e["end"])])
    print(f"\n💾 Détail par meeple : {a.csv}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        mids = []
        for r in rows:
            lo = int(r[0].split("–")[0]); hi = min(lo + 9, 71)
            mids.append((lo + hi) / 2)
        lam = [r[4] for r in rows]
        val = [r[5] for r in rows]
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(mids, lam, "o-", color="#B5442E", lw=2.5, label="rendement d'un meeple posé (λ, pts/tour)")
        ax.set_xlabel("tuiles restantes au moment de la pose")
        ax.set_ylabel("λ : points par tour bloqué", color="#B5442E")
        ax2 = ax.twinx()
        ax2.plot(mids, val, "s--", color="#1F3B2D", lw=2, label="valeur d'un meeple libre (λ × tours restants)")
        ax2.set_ylabel("points qu'un meeple libre peut encore rapporter", color="#1F3B2D")
        ax2.set_ylim(bottom=0)
        ax.set_title("Le prix d'un meeple au fil de la partie")
        ax.invert_xaxis(); ax.grid(alpha=0.3)
        h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper center", fontsize=9)
        fig.tight_layout(); fig.savefig(a.png, dpi=150)
        print(f"📈 Courbe : {a.png}")
    except ImportError:
        print("(matplotlib absent : pas de courbe)")


if __name__ == "__main__":
    main()
