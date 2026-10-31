"""
🏰 carcassonne-coach — le coach joue contre lui-même (auto-jeu)
================================================================
Chaque coup est choisi par la recherche MCTS guidée par le réseau actuel ; la
partie est enregistrée dans parties/selfplay/. L'entraînement
(python neural_evaluator.py train parties 30) apprend alors au réseau à
reproduire les choix de sa propre recherche, et à la tête value à prédire le
vrai résultat de ces parties.

Usage (laisser tourner la nuit, Ctrl+C pour arrêter proprement) :
    python selfplay.py                         # 4 parties en parallèle, sans fin
    python selfplay.py --games 2000 --workers 4 --sims 200

Options :
    --games N     nombre de parties à jouer (défaut : sans fin)
    --workers N   parties jouées en parallèle (défaut : nombre de cœurs)
    --sims N      simulations MCTS par coup (défaut : 200)
    --explore N   coups d'ouverture tirés au sort selon les visites (défaut : 10)
    --model F     réseau utilisé (défaut : carcassonne_model.pt)
    --out D       dossier de sortie (défaut : parties/selfplay)
"""
import argparse, contextlib, io, itertools, json, os, random, sys, time
from pathlib import Path

_net = None


def _load_net(model):
    """Réseau calculé en NumPy (sans PyTorch) : léger, un par processus."""
    global _net
    if _net is None:
        with contextlib.redirect_stdout(io.StringIO()):
            import browser_coach
            _net = browser_coach.NumpyNeuralEvaluator(model) if Path(model).exists() else False
    return _net or None


def play_one(args):
    seed, sims, explore, model, out_dir = args
    import carcassonne_engine as E
    random.seed(seed)
    net = _load_net(model)
    T = E.TILE_TYPES
    g = E.GameState(2)
    g.init_draw_pile()
    start = next(t for t in g.draw_pile if t.edges == "CRFR" and not t.shield)
    g.draw_pile.remove(start)
    g.place_tile(start, 0, 0, 0)
    player = seed % 2              # alterne le premier joueur d'une partie à l'autre
    moves, t0 = [], time.time()
    while g.draw_pile:
        tile = g.draw_pile.pop()
        if not g.get_legal_placements(tile):          # tuile impossible : défaussée
            moves.append({"t": T.index(tile), "discard": True})
            continue
        g.current_tile = tile
        with contextlib.redirect_stdout(io.StringIO()):
            res = E.mcts_search(g, tile, player, simulations=sims, time_limit=600, neural_eval=net)
        cand = [(r["x"], r["y"], r["rotation"], r["meeple"], int(r.get("visits", 0))) for r in res]
        n_played = sum(1 for m in moves if not m.get("discard"))
        if n_played < explore and sum(c[4] for c in cand) > 0:
            x, y, rot, meeple, _ = random.choices(cand, weights=[c[4] for c in cand])[0]
        else:
            x, y, rot, meeple, _ = cand[0]
        g.place_tile(tile, x, y, rot, player if meeple else None, meeple)
        moves.append({"p": player, "t": T.index(tile), "x": x, "y": y, "r": rot, "m": meeple,
                      "v": [list(c) for c in sorted(cand, key=lambda c: -c[4])[:8]]})
        player = 1 - player
    g.final_scoring()
    name = f"sp_{time.strftime('%Y%m%d-%H%M%S')}_{seed}.json"
    data = {"selfplay": True, "version": 1, "seed": seed, "sims": sims,
            "model": Path(model).name if net else None, "start": T.index(start), "moves": moves,
            "final_scores": list(g.scores),
            "players": [{"name": "coach A", "score": g.scores[0]}, {"name": "coach B", "score": g.scores[1]}],
            "seconds": round(time.time() - t0, 1)}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    with open(Path(out_dir) / name, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    return name, g.scores, data["seconds"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--games", type=int, default=0)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--sims", type=int, default=200)
    ap.add_argument("--explore", type=int, default=10)
    ap.add_argument("--model", default="carcassonne_model.pt")
    ap.add_argument("--out", default="parties/selfplay")
    a = ap.parse_args()
    from multiprocessing import Pool
    base = int(time.time())
    jobs = ((base + i, a.sims, a.explore, a.model, a.out)
            for i in (range(a.games) if a.games else itertools.count()))
    print(f"🏰 Auto-jeu : {a.workers} parties en parallèle, {a.sims} simulations par coup, "
          f"réseau {'oui' if Path(a.model).exists() else 'non (heuristique seule)'} → {a.out}")
    print("   Ctrl+C pour arrêter (les parties terminées sont déjà enregistrées).\n")
    done, t0 = 0, time.time()
    try:
        with Pool(a.workers) as pool:
            for name, scores, sec in pool.imap_unordered(play_one, jobs):
                done += 1
                rate = done / (time.time() - t0) * 3600
                print(f"  {done:5d}  {name}  {scores[0]:3d}-{scores[1]:<3d}  {sec:5.0f} s   "
                      f"(≈ {rate:.0f} parties/heure)", flush=True)
    except KeyboardInterrupt:
        print(f"\n⏹️ Arrêt demandé — {done} parties enregistrées dans {a.out}")


if __name__ == "__main__":
    main()
