"""
🏰 carcassonne-coach — match entre deux réseaux (arène)
=======================================================
Fait jouer le coach avec le réseau A contre le coach avec le réseau B.
Les parties vont par paires : même ordre de tuiles, puis on échange les places.
Le hasard du tirage s'annule ainsi, et seul le réseau fait la différence.

Usage :
    python arena.py --a carcassonne_model_v33.pt --b carcassonne_model_v28.pt
    python arena.py --a A.pt --b B.pt --pairs 100 --sims 200 --workers 4

Résultat : victoires de A, écart de score moyen, et écart Elo estimé avec sa
marge d'incertitude (95 %). Les parties sont enregistrées dans arena/.
"""
import argparse, contextlib, io, itertools, json, math, os, random, time
from pathlib import Path

_nets = {}


def _net(path):
    """Un réseau NumPy par fichier et par processus (sans PyTorch)."""
    if path not in _nets:
        with contextlib.redirect_stdout(io.StringIO()):
            import browser_coach
            _nets[path] = browser_coach.NumpyNeuralEvaluator(path)
    return _nets[path]


def play_game(args):
    """Une partie. seats[i] = fichier du réseau qui joue le joueur i."""
    seed, swap, sims, model_a, model_b = args
    import carcassonne_engine as E
    seats = [model_b, model_a] if swap else [model_a, model_b]
    nets = [_net(seats[0]), _net(seats[1])]
    random.seed(seed)                          # même tirage pour les deux parties de la paire
    g = E.GameState(2)
    g.init_draw_pile()
    start = next(t for t in g.draw_pile if t.edges == "CRFR" and not t.shield)
    g.draw_pile.remove(start)
    g.place_tile(start, 0, 0, 0)
    random.seed(seed * 2 + swap)               # hasard propre à la recherche
    player, t0 = 0, time.time()
    while g.draw_pile:
        tile = g.draw_pile.pop()
        if not g.get_legal_placements(tile):
            continue
        g.current_tile = tile
        with contextlib.redirect_stdout(io.StringIO()):
            res = E.mcts_search(g, tile, player, simulations=sims, time_limit=600, neural_eval=nets[player])
        r = res[0]
        g.place_tile(tile, r["x"], r["y"], r["rotation"], player if r["meeple"] else None, r["meeple"])
        player = 1 - player
    g.final_scoring()
    a = 1 if swap else 0                       # siège du réseau A
    return {"seed": seed, "swap": swap, "score_a": g.scores[a], "score_b": g.scores[1 - a],
            "seconds": round(time.time() - t0, 1)}


def elo(score):
    score = min(max(score, 1e-3), 1 - 1e-3)
    return -400 * math.log10(1 / score - 1)


def summary(results):
    n = len(results)
    pts = [1.0 if r["score_a"] > r["score_b"] else 0.5 if r["score_a"] == r["score_b"] else 0.0 for r in results]
    s = sum(pts) / n
    sd = math.sqrt(max(sum((p - s) ** 2 for p in pts) / max(n - 1, 1), 1e-9) / n)
    diff = sum(r["score_a"] - r["score_b"] for r in results) / n
    lo, hi = elo(s - 1.96 * sd), elo(s + 1.96 * sd)
    return s, diff, elo(s), lo, hi


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", required=True, help="réseau A (celui qu'on teste)")
    ap.add_argument("--b", required=True, help="réseau B (la référence)")
    ap.add_argument("--pairs", type=int, default=100, help="paires de parties (2 parties chacune)")
    ap.add_argument("--sims", type=int, default=200, help="simulations MCTS par coup")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--out", default="arena")
    a = ap.parse_args()
    from multiprocessing import Pool
    Path(a.out).mkdir(exist_ok=True)
    log = Path(a.out) / f"{Path(a.a).stem}_vs_{Path(a.b).stem}_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    base = 1_000_003
    jobs = [(base + i, swap, a.sims, a.a, a.b) for i in range(a.pairs) for swap in (0, 1)]
    print(f"🏰 Arène : {Path(a.a).name} (A) contre {Path(a.b).name} (B)")
    print(f"   {a.pairs} paires = {2 * a.pairs} parties, {a.sims} simulations par coup, {a.workers} en parallèle")
    print(f"   Résultats enregistrés dans {log}\n")
    results, t0 = [], time.time()
    try:
        with Pool(a.workers) as pool, open(log, "w", encoding="utf-8") as f:
            for r in pool.imap_unordered(play_game, jobs):
                results.append(r); f.write(json.dumps(r) + "\n"); f.flush()
                s, diff, e, lo, hi = summary(results)
                print(f"  {len(results):4d}/{len(jobs)}  A {r['score_a']:3d} - {r['score_b']:<3d} B   |  "
                      f"A marque {s:5.1%} des points, écart moyen {diff:+5.1f}, Elo {e:+4.0f} [{lo:+.0f} ; {hi:+.0f}]",
                      flush=True)
    except KeyboardInterrupt:
        print("\n⏹️ Arrêt demandé.")
    if results:
        s, diff, e, lo, hi = summary(results)
        print(f"\n✅ {len(results)} parties : A marque {s:.1%} des points (victoire = 1, nul = ½), "
              f"écart de score moyen {diff:+.1f}")
        print(f"   Écart Elo estimé : {e:+.0f}, intervalle à 95 % [{lo:+.0f} ; {hi:+.0f}]  "
              f"({(time.time() - t0) / 60:.0f} min)")
        verdict = ("A est plus fort" if lo > 0 else "B est plus fort" if hi < 0
                   else "pas de différence démontrée : jouer plus de paires pour trancher")
        print(f"   → {verdict}")


if __name__ == "__main__":
    main()
