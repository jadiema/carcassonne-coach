"""
🧑‍🌾 Bayes avec de vraies parties : y a-t-il des joueurs « agressifs » dans les prés ?
=====================================================================================
Pour chaque joueur et chaque partie, on compte :
  - ses OCCASIONS de poser un paysan : les tours où il lui reste au moins un meeple
    et où sa tuile permet de poser un paysan quelque part (pose légale avec un pré libre) ;
  - ses POSES de paysan : les tours où il a effectivement posé un paysan.

On suppose ensuite qu'il existe deux styles cachés, comme dans le cours :
  A « agressif »  : pose un paysan avec une probabilité pA à chaque occasion ;
  B « prudent »   : pose un paysan avec une probabilité pB (plus faible).
Un algorithme classique (EM, « espérance-maximisation ») retrouve à partir des
données la proportion π de joueurs A (l'a priori) et les deux probabilités pA, pB
(les vraisemblances). On peut alors refaire les calculs de Bayes du cours avec
des chiffres réels.

Usage :
    python bayes_paysans.py parties
    python bayes_paysans.py parties --csv paysans.csv
"""
import argparse, csv, json, math
from pathlib import Path
import replay_bga as R
import carcassonne_engine as E


def farmer_possible(state, tile, player) -> bool:
    if state.meeples[player] <= 0:
        return False
    for (x, y, r) in state.get_legal_placements(tile):
        if any(sp.startswith("field") for sp in E._meeple_options(state, tile, x, y, r)):
            return True
    return False


def analyse_game(data):
    G, states, _ = R.replay(data)
    n_players = states[0][0].num_players
    occ = [0] * n_players
    put = [0] * n_players
    for snap, (x, y, rot, spot), mover in states:
        if farmer_possible(snap, snap.current_tile, mover):
            occ[mover] += 1
            if spot and spot.startswith("field"):
                put[mover] += 1
    final = G["final_scores"]
    rows = []
    for p in range(n_players):
        won = final[p] > max(final[q] for q in range(n_players) if q != p)
        rows.append({"player": p, "occasions": occ[p], "paysans": put[p],
                     "score": final[p], "gagne": int(won)})
    return rows


def log_binom(k, n, p):
    p = min(max(p, 1e-9), 1 - 1e-9)
    return k * math.log(p) + (n - k) * math.log(1 - p)


def em(data, iters=500):
    """Mélange de deux lois binomiales : renvoie π, pA, pB et l'appartenance de chacun."""
    pi, pa, pb = 0.5, 0.15, 0.04
    for _ in range(iters):
        resp = []
        for k, n in data:
            la = math.log(pi) + log_binom(k, n, pa)
            lb = math.log(1 - pi) + log_binom(k, n, pb)
            m = max(la, lb)
            ra = math.exp(la - m) / (math.exp(la - m) + math.exp(lb - m))
            resp.append(ra)
        sa = sum(resp); sb = len(resp) - sa
        pi = min(max(sa / len(resp), 1e-3), 1 - 1e-3)
        pa = sum(r * k for r, (k, n) in zip(resp, data)) / max(sum(r * n for r, (k, n) in zip(resp, data)), 1e-9)
        pb = sum((1 - r) * k for r, (k, n) in zip(resp, data)) / max(sum((1 - r) * n for r, (k, n) in zip(resp, data)), 1e-9)
        if pa < pb:  # A = le style qui pose le plus de paysans
            pa, pb, pi = pb, pa, 1 - pi
    return pi, pa, pb, resp


def posterior(prior, pa, pb, obs):
    """Probabilité d'être A après une suite d'observations (True = pose un paysan)."""
    p = prior
    for o in obs:
        la = pa if o else 1 - pa
        lb = pb if o else 1 - pb
        p = la * p / (la * p + lb * (1 - p))
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--csv", default="bayes_paysans.csv")
    a = ap.parse_args()
    rows, ok = [], 0
    for f in sorted(Path(a.data_dir).glob("*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
            if not data.get("rawLog"):
                continue
            names = [pl.get("name", f"J{i}") for i, pl in enumerate(data.get("players", []))]
            for r in analyse_game(data):
                r["partie"] = f.name
                r["nom"] = names[r["player"]] if r["player"] < len(names) else ""
                rows.append(r)
            ok += 1
            if ok % 25 == 0:
                print(f"   … {ok} parties analysées")
        except Exception as e:
            print(f"   ⚠️ {f.name} ignorée : {e}")
    rows = [r for r in rows if r["occasions"] > 0]
    print(f"\n{ok} parties, {len(rows)} joueurs-parties")
    if len(rows) < 10:
        print("Pas assez de données pour estimer les deux styles.")
        return

    tot_k = sum(r["paysans"] for r in rows); tot_n = sum(r["occasions"] for r in rows)
    print(f"Occasions de poser un paysan : {tot_n / len(rows):.1f} par joueur et par partie ; "
          f"paysans posés : {tot_k / len(rows):.1f} ; soit {tot_k / tot_n:.1%} des occasions")

    pi, pa, pb, resp = em([(r["paysans"], r["occasions"]) for r in rows])
    for r, ra in zip(rows, resp):
        r["prob_A"] = ra
    print("\n── Les deux styles retrouvés dans les données")
    print(f"   A priori        : π = {pi:.0%} de joueurs-parties « agressifs » (A), {1 - pi:.0%} « prudents » (B)")
    print(f"   Vraisemblances  : P(paysan | A) = {pa:.1%}   P(paysan | B) = {pb:.1%}   (par occasion)")
    print(f"   Rapport         : un A pose un paysan {pa / pb:.1f} fois plus souvent qu'un B")

    print("\n── Bayes en partie, avec ces chiffres réels")
    steps = [("au départ", []), ("après un paysan", [True]), ("après deux paysans", [True, True]),
             ("puis une abstention", [True, True, False]), ("après une abstention seule", [False]),
             ("après trois abstentions", [False, False, False])]
    for lab, obs in steps:
        print(f"   {lab:<28} P(A) = {posterior(pi, pa, pb, obs):.0%}")

    A = [r for r in rows if r["prob_A"] > 0.5]; Bp = [r for r in rows if r["prob_A"] <= 0.5]
    if A and Bp:
        print("\n── Les agressifs gagnent-ils plus ?")
        for lab, grp in (("A agressifs", A), ("B prudents", Bp)):
            print(f"   {lab:<12} {len(grp):>4} joueurs-parties   "
                  f"paysans {sum(r['paysans'] for r in grp) / len(grp):.1f}/partie   "
                  f"victoires {sum(r['gagne'] for r in grp) / len(grp):.0%}   "
                  f"score moyen {sum(r['score'] for r in grp) / len(grp):.0f}")

    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["partie", "joueur", "nom", "occasions", "paysans", "taux", "prob_agressif", "score", "gagne"])
        for r in rows:
            w.writerow([r["partie"], r["player"], r["nom"], r["occasions"], r["paysans"],
                        f"{r['paysans'] / r['occasions']:.3f}", f"{r['prob_A']:.3f}", r["score"], r["gagne"]])
    print(f"\n💾 Détail par joueur et par partie : {a.csv}")


if __name__ == "__main__":
    main()
