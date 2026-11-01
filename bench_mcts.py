"""
Banc de test du MCTS : le coach retrouve-t-il le coup des joueurs forts ?
Usage : python bench_mcts.py [simulations] [une position sur N]
        python bench_mcts.py 300 3
Compare le coup joué (case, rotation, meeple) au classement du coach, sur les
parties rejouables de parties/ (hors fin de partie, calculée exactement).
"""
import json, glob, io, contextlib, random, sys
import replay_bga as R, carcassonne_engine as E

try:
    with contextlib.redirect_stdout(io.StringIO()):
        import browser_coach
        net = browser_coach.NumpyNeuralEvaluator("carcassonne_model.pt")
except Exception:
    net = None
sims = int(sys.argv[1]) if len(sys.argv) > 1 else 300
step = int(sys.argv[2]) if len(sys.argv) > 2 else 3
n = top1 = top3 = 0
files = [f for f in sorted(glob.glob("parties/*.json"))
         if json.load(open(f, encoding="utf-8")).get("rawLog")]
for f in files:
    try:
        G, states, _ = R.replay(json.load(open(f, encoding="utf-8")))
    except R.ReplayError:
        continue
    for i, (st, mv, p) in enumerate(states):
        if i % step or len(st.draw_pile) <= 6:
            continue
        random.seed(i)
        with contextlib.redirect_stdout(io.StringIO()):
            r = E.mcts_search(st, st.current_tile, p, simulations=sims, time_limit=600, neural_eval=net)
        order = [(m["x"], m["y"], m["rotation"], m["meeple"]) for m in r]
        n += 1; top1 += order[:1] == [tuple(mv)]; top3 += tuple(mv) in order[:3]
    print(f"  {f}: {n} positions, top1 {top1/max(n,1):.1%}, top3 {top3/max(n,1):.1%}", flush=True)
print(f"\nCoup complet (case, rotation, meeple) : top1 {top1/n:.1%}  top3 {top3/n:.1%}  "
      f"({n} positions, {sims} simulations)")
