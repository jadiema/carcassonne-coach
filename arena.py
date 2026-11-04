"""
🏰 carcassonne-coach — match entre deux réseaux (arène)
=======================================================
Fait jouer le coach avec le réseau A contre le coach avec le réseau B.
Les parties vont par paires : même ordre de tuiles, puis on échange les places.
Le hasard du tirage s'annule ainsi, et seul le réseau fait la différence.

Usage :
    python arena.py --a carcassonne_model_v33.pt --b carcassonne_model_v28.pt
    python arena.py --a A.pt --b B.pt --pairs 100 --sims 200 --workers 4
    python arena.py --a M.pt --b M.pt --sims-a 400 --sims-b 200      (que vaut le double de calcul ?)
    python arena.py --a M.pt --b M.pt --value-a                      (la tête value aide-t-elle ?)

Résultat : victoires de A, écart de score moyen, et écart Elo estimé avec sa
marge d'incertitude (95 %). Les parties sont enregistrées dans arena/.
"""
import argparse, contextlib, io, itertools, json, math, os, random, time
from pathlib import Path

_nets = {}


def _net(path, use_value=False):
    """Un réseau NumPy par fichier, par mode et par processus (sans PyTorch).
    use_value=True : la tête value juge les positions à la place des simulations."""
    key = (path, use_value)
    if key not in _nets:
        with contextlib.redirect_stdout(io.StringIO()):
            import browser_coach
            _nets[key] = browser_coach.NumpyNeuralEvaluator(path, use_value=use_value)
    return _nets[key]


def play_game(args):
    """Une partie. Chaque camp = (fichier du réseau, simulations par coup, tête value)."""
    seed, swap, camp_a, camp_b = args
    import carcassonne_engine as E
    seats = [camp_b, camp_a] if swap else [camp_a, camp_b]
    nets = [_net(c[0], c[2]) for c in seats]
    sims = [c[1] for c in seats]
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
            res = E.mcts_search(g, tile, player, simulations=sims[player], time_limit=600, neural_eval=nets[player])
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
    ap.add_argument("--sims", type=int, default=200, help="simulations MCTS par coup (les deux camps)")
    ap.add_argument("--sims-a", type=int, default=0, help="simulations par coup pour A (défaut : --sims)")
    ap.add_argument("--sims-b", type=int, default=0, help="simulations par coup pour B (défaut : --sims)")
    ap.add_argument("--value-a", action="store_true", help="A juge les positions avec la tête value du réseau")
    ap.add_argument("--value-b", action="store_true", help="B juge les positions avec la tête value du réseau")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--out", default="arena")
    a = ap.parse_args()
    from multiprocessing import Pool
    Path(a.out).mkdir(exist_ok=True)
    camp_a = (a.a, a.sims_a or a.sims, a.value_a)
    camp_b = (a.b, a.sims_b or a.sims, a.value_b)
    label = lambda c: f"{Path(c[0]).stem}, {c[1]} sim.{', value' if c[2] else ''}"
    tag = lambda c: f"{Path(c[0]).stem}-{c[1]}{'-value' if c[2] else ''}"
    log = Path(a.out) / f"{tag(camp_a)}_vs_{tag(camp_b)}_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    base = 1_000_003
    jobs = [(base + i, swap, camp_a, camp_b) for i in range(a.pairs) for swap in (0, 1)]
    print(f"🏰 Arène : A = {label(camp_a)}   contre   B = {label(camp_b)}")
    print(f"   {a.pairs} paires = {2 * a.pairs} parties, {a.workers} en parallèle")
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
