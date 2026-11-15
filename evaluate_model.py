"""
🧪 Le réseau améliore-t-il vraiment les conseils ?
==================================================
Rejoue les parties de VALIDATION (jamais vues à l'entraînement) et compare, sur
chaque position, le coup réellement joué par le joueur fort avec :
  - le hasard parmi les placements légaux (référence) ;
  - l'heuristique du moteur (évaluation après le coup, 1 coup de profondeur) ;
  - la tête VALUE du réseau (même principe) ;
  - la tête POLICY du réseau (case choisie, sans la rotation).
Puis mesure si la tête value prédit le vainqueur mieux que « celui qui mène gagne ».

Usage :
    python evaluate_model.py parties                       # modèle carcassonne_model.pt
    python evaluate_model.py parties --model autre.pt --step 2
    (--step 2 : une position sur deux, deux fois plus rapide)
"""
import argparse, json, random, time
from copy import deepcopy
from pathlib import Path
import carcassonne_engine as E
import replay_bga as R


def validation_games(data_dir: Path, model_path: Path):
    saved = model_path.with_suffix(".validation.json")
    if saved.exists():
        # numéros de table (sans pseudos) → fichiers de parties/
        from neural_evaluator import game_key, load_validation_keys
        keys = load_validation_keys(saved)
        names = {jf.name for jf in data_dir.glob("*.json") if game_key(jf.name) in keys}
        src = f"{saved.name}"
    else:   # même tirage que train() (approximation si le fichier manque)
        names = []
        for jf in data_dir.glob("*.json"):
            d = json.load(open(jf, encoding="utf-8"))
            sc = [p.get("score", 0) for p in d.get("players", [])]
            if len(sc) < 2 or sc[0] == sc[1] or not any(sc):
                continue
            if d.get("rawLog") or len(d.get("board", [])) >= 70:
                names.append(jf.name)
        games = sorted(set(names)); random.Random(0).shuffle(games)
        names = set(games[:max(1, len(games) // 10)])
        src = "tirage recalculé"
    files = [data_dir / n for n in sorted(names) if (data_dir / n).exists()]
    files = [f for f in files if json.load(open(f, encoding="utf-8")).get("rawLog")]
    return files, src


def rank_of(scores: dict, played) -> int:
    """Rang (1 = meilleur) du coup joué ; ex æquo comptés en sa défaveur."""
    s = scores[played]
    return 1 + sum(1 for k, v in scores.items() if k != played and v >= s)


def move_scores(state, tile, player, legal, evaluate):
    """Score de chaque placement (x, y, rot) = meilleur score sur les options de meeple."""
    out = {}
    for (x, y, r) in legal:
        spots = [None] + (E._meeple_options(state, tile, x, y, r) if state.meeples[player] > 0 else [])
        best = -1e9
        for sp in spots:
            s = deepcopy(state)
            s.place_tile(tile, x, y, r, player if sp else None, sp)
            best = max(best, evaluate(s, player))
        out[(x, y, r)] = best
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--model", default="carcassonne_model.pt")
    ap.add_argument("--step", type=int, default=1, help="une position sur N")
    a = ap.parse_args()
    model_path = Path(a.model)

    from neural_evaluator import NeuralEvaluator
    net = NeuralEvaluator(str(model_path))
    files, src = validation_games(Path(a.data_dir), model_path)
    print(f"Parties de validation rejouables : {len(files)} ({src})\n")

    heur = lambda s, p: E._evaluate_position(s, p)
    value = lambda s, p: net.evaluate(E._state_to_dict(s, p), p)
    stats = {k: [0, 0, 0] for k in ("hasard", "heuristique", "réseau value",
                                    "policy → heuristique", "policy coup → heuristique",
                                    "réseau policy (coup)", "—", "heuristique (case)",
                                    "réseau policy (case)")}
    calib = {k: [0, 0, 0] for k in ("début", "milieu", "fin")}   # [n, réseau juste, « qui mène » juste]
    n_pos, t0 = 0, time.time()

    for f in files:
        data = json.load(open(f, encoding="utf-8"))
        G, states, _ = R.replay(data)
        final = G["final_scores"]
        for i, (state, (x, y, rot, spot), mover) in enumerate(states):
            # --- calibration de la tête value (toutes les positions)
            phase = "début" if i < 24 else "milieu" if i < 48 else "fin"
            opp = 1 - mover
            won = final[mover] > final[opp]
            v = value(state, mover)
            lead = state.scores[mover] - state.scores[opp]
            c = calib[phase]; c[0] += 1
            c[1] += (v > 0.5) == won
            c[2] += (lead > 0) == won if lead != 0 else 0.5
            if i % a.step:
                continue
            tile = state.current_tile
            legal = state.get_legal_placements(tile)
            if len(legal) < 2 or (x, y, rot) not in legal:
                continue
            n_pos += 1
            played = (x, y, rot)
            n = len(legal)
            st = stats["hasard"]; st[0] += 1; st[1] += 1 / n; st[2] += min(3, n) / n
            hs = move_scores(state, tile, mover, legal, heur)
            for name, sc in (("heuristique", hs),
                             ("réseau value", move_scores(state, tile, mover, legal, value))):
                r = rank_of(sc, played)
                st = stats[name]; st[0] += 1; st[1] += r == 1; st[2] += r <= 3
            pol = net.get_policy(E._state_to_dict(state, mover), mover)
            # policy → heuristique : case classée par le réseau, puis rotation (et
            # meeple) par l'heuristique — même périmètre que « heuristique »
            combo = {m: (pol.get(m[:2], 0.0), hs[m]) for m in legal}
            r = rank_of(combo, played)
            st = stats["policy → heuristique"]; st[0] += 1; st[1] += r == 1; st[2] += r <= 3
            # v28 : la policy note directement (case, rotation)
            polr = net.get_policy_rot(E._state_to_dict(state, mover), mover)
            sc_rot = {m: polr.get(m, 0.0) for m in legal}
            r = rank_of(sc_rot, played)
            st = stats["réseau policy (coup)"]; st[0] += 1; st[1] += r == 1; st[2] += r <= 3
            # policy (case + rotation) puis heuristique pour départager / le meeple
            combo2 = {m: (sc_rot[m], hs[m]) for m in legal}
            r = rank_of(combo2, played)
            st = stats["policy coup → heuristique"]; st[0] += 1; st[1] += r == 1; st[2] += r <= 3
            cells = {(lx, ly) for lx, ly, _ in legal}
            if len(cells) >= 2:
                hc = {c: max(v for m, v in hs.items() if m[:2] == c) for c in cells}
                r = rank_of(hc, (x, y))
                st = stats["heuristique (case)"]; st[0] += 1; st[1] += r == 1; st[2] += r <= 3
                cs = {c: pol.get(c, 0.0) for c in cells}
                r = rank_of(cs, (x, y))
                st = stats["réseau policy (case)"]; st[0] += 1; st[1] += r == 1; st[2] += r <= 3
        print(f"  {f.name}: {len(states)} coups  ({time.time() - t0:.0f} s)")

    print(f"\n── Le coup du joueur fort est-il dans le top 1 / top 3 ? ({n_pos} positions)")
    print("   coup complet (case + rotation) :")
    for name, (n, t1, t3) in stats.items():
        if name == "—":
            print("   case seule :")
        elif n:
            print(f"     {name:<22} top1 {t1 / n:5.1%}   top3 {t3 / n:5.1%}")

    print(f"\n── La tête value prédit-elle le vainqueur ? (⚠️ {len(files)} parties = "
          f"{len(files)} résultats indépendants seulement)")
    for phase, (n, ok_net, ok_lead) in calib.items():
        if n:
            print(f"   {phase:<7} ({n:4d} pos.)  réseau {ok_net / n:5.1%}   « qui mène gagne » {ok_lead / n:5.1%}")


if __name__ == "__main__":
    main()
