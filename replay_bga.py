"""
🔁 Rejeu exact d'une partie BGA à partir du JSON de l'extension (v24+, champ rawLog)
==================================================================================
- reconstruit chaque position intermédiaire avec les VRAIS scores et meeples ;
- vérifie, coup par coup, que le moteur marque exactement les points annoncés par
  BGA, puis le décompte final : c'est un test de non-régression automatique ;
- lève les ambiguïtés (quelle ville / quel champ ?) par recherche sous contraintes ;
- déduit les meeples des premiers coups absents du journal (début tronqué).

Usage :
    python replay_bga.py partie.json            # vérifie une partie
    python replay_bga.py dossier_parties/       # vérifie tout un dossier
"""
import json, re, sys
from copy import deepcopy
from pathlib import Path
import carcassonne_engine as E

KIND = {"ville": "city", "route": "road", "pré": "field", "pre": "field",
        "abbaye": "monastery", "monastère": "monastery"}
RE_ROT = re.compile(r"rotate\((\d+)deg\)")
RE_BGPOS = re.compile(r"background-position:\s*([\d.]+)%\s+([\d.]+)%")


def bgid_from_html(html: str):
    """Numéro de tuile d'après la position dans la planche de sprites BGA
    (16 colonnes à 100/15 %, lignes à 100/9 %) — même table que l'extension."""
    m = RE_BGPOS.search(html or "")
    if not m:
        return None
    col = round(float(m.group(1)) / (100 / 15))
    row = round(float(m.group(2)) / (100 / 9))
    return row * 16 + col + 1
RE_PTS = re.compile(r"^(.*) gagne (\d+) points?")
# lettres seulement : BGA colle parfois l'heure au texte (« …tuile route07:08 »)
RE_MEEPLE = re.compile(r"^(.*) place un partisan sur la tuile ([^\W\d_]+)")


class ReplayError(Exception):
    pass


# ------------------------------------------------------------------ parsing
def parse_game(data: dict) -> dict:
    players = [p["name"] for p in data["players"]]
    colors = [p["color"] for p in data["players"]]
    raw = data.get("rawLog")
    if not raw:
        raise ReplayError("pas de rawLog (export antérieur à la v24)")
    board = {}
    for t in data["board"]:
        if t.get("location") is None:
            continue
        m = t.get("meeple")
        board[t["bgId"]] = dict(edges=t["edgesOriginal"], rot=t["rotation"], shield=t["shield"],
                                desc=t["desc"], x=t["location"]["x"], y=t["location"]["y"],
                                meeple=(colors.index(m["color"]), m["spot"]) if m else None)
    tile_ids = [m["bgId"] for m in data["moveLog"]]

    def who(text):
        for i, n in enumerate(sorted(players, key=len, reverse=True)):
            if text.startswith(n):
                return players.index(n)
        return None

    moves, final = [], [0] * len(players)
    in_final, k, conceded = False, 0, False
    pre = [0] * len(players)
    for e in raw:
        text, html = e["text"], e.get("html", "")
        if "tile_art" in html:                        # pose de tuile
            r = RE_ROT.search(html)
            pos = RE_BGPOS.search(html)
            art = pos.groups() if pos else None
            if "first_edition" in html:
                # planche de la 1re édition : la table de l'extension (2e édition)
                # donne des numéros FAUX → tuile identifiée plus tard par contraintes
                bid = None
            else:
                bid = tile_ids[k] if k < len(tile_ids) else None
                if bid is None:                        # image non reconnue par l'extension
                    bid = bgid_from_html(html)
            moves.append(dict(player=who(text), bgId=bid, art=art,
                              rot=int(r.group(1)) // 90 if r else None, meeple=None,
                              points=[0] * len(players)))
            k += 1
            continue
        if "concède" in text or "abandonne" in text:
            conceded = True
        if text.startswith("Décompte") or text.startswith("Ce pré"):
            in_final = True
        m = RE_MEEPLE.match(text)
        if m and not moves and not in_final:
            continue          # partisan d'un coup absent du journal : retrouvé par la recherche
        if m and moves and not in_final:
            kind = KIND.get(m.group(2).lower())
            if kind is None:
                raise ReplayError(f"type de partisan inconnu dans le journal : {text!r}")
            moves[-1]["meeple"] = kind
            continue
        m = RE_PTS.match(text)
        if m:
            p = who(text)
            if p is None:
                continue
            if in_final:
                final[p] += int(m.group(2))
            elif moves:
                moves[-1]["points"][p] += int(m.group(2))
            else:
                pre[p] += int(m.group(2))   # points d'un coup absent du journal
    if k != len(tile_ids):
        raise ReplayError(f"{k} poses dans rawLog, {len(tile_ids)} dans moveLog")
    return dict(players=players, colors=colors, board=board, moves=moves, final=final,
                conceded=conceded, pre_points=pre,
                final_scores=[p["score"] for p in data["players"]])


# ------------------------------------------------------------------ table 1re édition
# Dans les replays, BGA affiche les tuiles dans l'édition choisie par les JOUEURS :
# l'extension ne reconnaît pas les images de la 1re édition (bgId = None) et le
# rejeu doit deviner chaque tuile par déduction. Chaque partie 1re édition rejouée
# avec succès (scores vérifiés) enrichit une table « image → type de tuile »,
# qui sert ensuite à toutes les autres : la déduction devient de plus en plus sûre.
ED1_TABLE_PATH = Path(__file__).with_name("ed1_art_table.json")


def _art_key(art):
    return f"{art[0]} {art[1]}" if art else None


def load_ed1_table() -> dict:
    try:
        return json.load(open(ED1_TABLE_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _learn_ed1(moves, board, table: dict) -> int:
    """Ajoute à la table les images de la partie ; renvoie le nombre d'ajouts."""
    added = 0
    for m in moves:
        k = _art_key(m.get("art"))
        if not k or m.get("bgId") not in board:
            continue
        d = board[m["bgId"]]
        typ = [d["edges"], d["shield"], d["desc"]]
        if k not in table:
            table[k] = typ
            added += 1
    if added:
        with open(ED1_TABLE_PATH, "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=0)
    return added


# ------------------------------------------------------------------ replay
def replay(data: dict, max_branches: int = 20000):
    G = parse_game(data)
    board, moves, n = G["board"], G["moves"], len(G["players"])
    tt = {b: E._find_tile_type(d["edges"], d["shield"], d["desc"]) for b, d in board.items()}
    first_ed = any(m["bgId"] is None for m in moves)
    if first_ed and len(moves) != len(board) - 1:
        raise ReplayError("journal 1re édition incomplet : impossible d'identifier les tuiles "
                          "(passez BGA en tuiles 2e édition et réexportez)")
    unknown = [m for m in moves if m["bgId"] is not None and m["bgId"] not in board]
    if unknown:
        if any(m["meeple"] or any(m["points"]) for m in unknown):
            raise ReplayError(f"tuile(s) du journal absente(s) du plateau : "
                              f"{[m['bgId'] for m in unknown]}")
        moves = [m for m in moves if m["bgId"] is None or m["bgId"] in board]   # défaussées
    if first_ed:
        start_b = [b for b, d in board.items() if (d["x"], d["y"]) == (0, 0)]
        logged = set(board) - set(start_b)
    else:
        logged = {m["bgId"] for m in moves}
    missing = [b for b in board if b not in logged]
    rep = {"missing": missing, "ambiguous": 0, "branches": 0,
           "discarded": [m["bgId"] for m in unknown]}

    def place(g, b, spot, who):
        d = board[b]
        g.place_tile(tt[b], d["x"], d["y"], d["rot"], who if spot else None, spot)

    g = E.GameState(n)
    g.player_names = G["players"]
    start = [b for b in missing if (board[b]["x"], board[b]["y"]) == (0, 0)]
    if len(start) != 1:
        raise ReplayError("tuile de départ introuvable en (0,0)")
    place(g, start[0], None, None)
    others = [b for b in missing if b not in start]
    order, tmp = [], deepcopy(g)
    while others:
        for b in others:
            d = board[b]
            if tmp.can_place(tt[b], d["x"], d["y"], d["rot"]):
                place(tmp, b, None, None); order.append(b); others.remove(b); break
        else:
            raise ReplayError(f"tuiles absentes du journal non connectables : {others}")

    # Points marqués pendant les coups absents du journal : ceux du journal
    # (journal coupé en plein coup) + l'écart entre le score final BGA et le
    # total du journal (journal coupé avant un coup qui a marqué).
    logged_total = [sum(m["points"][j] for m in moves) + G["final"][j] + G["pre_points"][j]
                    for j in range(n)]
    pre_target = [G["pre_points"][j] + G["final_scores"][j] - logged_total[j] for j in range(n)]
    if any(v < 0 for v in pre_target) or (any(pre_target) and not order):
        raise ReplayError(f"le journal totalise {logged_total} mais BGA affiche {G['final_scores']}")

    def prefix(g, i):
        if i == len(order):
            if g.scores == pre_target:
                yield g
            return
        b, d = order[i], board[order[i]]
        if d["meeple"]:
            choices = [(E._guess_meeple_spot(tt[b], d["rot"], d["meeple"][1]), d["meeple"][0])]
        else:
            choices = [(None, None)] + [(s, p) for s in E._meeple_options(g, tt[b], d["x"], d["y"], d["rot"])
                                        for p in range(n)]
        for spot, who in choices:
            g2 = deepcopy(g); place(g2, b, spot, who)
            if all(g2.scores[j] <= pre_target[j] for j in range(n)):
                yield from prefix(g2, i + 1)

    def dfs(g, k, hist, art_map=None):
        art_map = art_map or {}
        if rep["branches"] > max_branches:
            return None
        if k < len(moves) and moves[k]["bgId"] is None:
            mv = moves[k]
            placed = {(t.x, t.y) for t in g.board.values()}
            used = {h[0] for h in hist}
            cands = []
            for b, d in board.items():
                if b in used or (d["x"], d["y"]) in placed:
                    continue
                if mv["rot"] is not None and mv["rot"] != d["rot"]:
                    continue
                if mv["art"] in art_map and art_map[mv["art"]] is not tt[b]:
                    continue
                if any(a is tt[b] and im != mv["art"] for im, a in art_map.items()) and False:
                    continue
                if g.can_place(tt[b], d["x"], d["y"], d["rot"]):
                    cands.append(b)
            # tuiles identiques au même endroit : une seule branche par type
            seen_t = {}
            for b in cands:
                seen_t.setdefault((id(tt[b]), board[b]["x"], board[b]["y"]), b)
            for b in seen_t.values():
                m2 = dict(mv, bgId=b)
                r = dfs_move(g, k, hist, {**art_map, mv["art"]: tt[b]}, m2)
                if r is not None:
                    return r
            return None
        if k < len(moves):
            return dfs_move(g, k, hist, art_map, moves[k])
        return dfs_end(g, hist)

    def dfs_end(g, hist):
        if G["conceded"]:   # abandon : pas de décompte final chez BGA
            return hist if g.scores == G["final_scores"] else None
        g2 = deepcopy(g); before = list(g2.scores); g2.final_scoring()
        got = [g2.scores[i] - before[i] for i in range(n)]
        if got != G["final"]:
            rep["deepest"] = ("décompte final", "moteur", got, "BGA", G["final"])
            rep["final_state"] = (deepcopy(g), list(hist))
            return None
        return hist

    def dfs_move(g, k, hist, art_map, mv):
        if rep["branches"] > max_branches:
            return None
        b = mv["bgId"]; d = board[b]
        if mv["rot"] is not None and mv["rot"] != d["rot"]:
            raise ReplayError(f"rotation incohérente tuile {b}")
        if mv["meeple"]:
            pinned = E._guess_meeple_spot(tt[b], d["rot"], d["meeple"][1]) if d["meeple"] else None
            if pinned and pinned.split("_")[0] != mv["meeple"] and not first_ed:
                # le journal dit « route » mais la table des spots dit « champ » (etc.) :
                # la table _bga_zones est fausse pour ce type → on le signale
                rep.setdefault("table_conflicts", set()).add(
                    (d["edges"], d["desc"], d["meeple"][1], mv["meeple"], pinned.split("_")[0]))
                pinned = None
            if pinned:
                opts = [pinned]
            else:
                opts = [s for s in E._meeple_options(g, tt[b], d["x"], d["y"], d["rot"])
                        if s.split("_")[0] == mv["meeple"]]
            rep["ambiguous"] += len(opts) > 1
        else:
            opts = [None]
        for spot in opts:
            rep["branches"] += 1
            g2 = deepcopy(g); before = list(g2.scores)
            place(g2, b, spot, mv["player"])
            got = [g2.scores[i] - before[i] for i in range(n)]
            if got != mv["points"]:
                prev = rep.get("deepest", (-1,))[0]
                if isinstance(prev, int) and k >= prev:     # un échec au décompte final prime
                    rep["deepest"] = (k, b, spot, "moteur", got, "BGA", mv["points"])
                    rep["deepest_state"] = (g, hist, b, spot)
                continue
            r = dfs(g2, k + 1, hist + [(b, spot)], art_map)
            if r is not None:
                return r
        return None

    seed = {}
    ed1_table = load_ed1_table() if first_ed else {}
    for k_, (e_, s_, d_) in ed1_table.items():
        try:
            seed[tuple(k_.split())] = E._find_tile_type(e_, s_, d_)
        except Exception:
            pass
    rep["ed1_known"] = sum(1 for m in moves if m["bgId"] is None and tuple(m["art"] or ()) in seed)

    for g0 in prefix(g, 0):
        found = dfs(g0, 0, [], dict(seed))
        if found is not None:
            moves = [dict(m, bgId=b) for m, (b, _) in zip(moves, found)]
            spots = [sp for _, sp in found]
            rep["hidden_meeples"] = [(b, g0.board[(board[b]["x"], board[b]["y"])].meeple_spot)
                                     for b in order if g0.board[(board[b]["x"], board[b]["y"])].meeple_spot]
            # rejeu linéaire : positions AVANT chaque coup
            states, s = [], deepcopy(g0)
            for mv, spot in zip(moves, spots):
                d = board[mv["bgId"]]
                remaining = [tt[m["bgId"]] for m in moves[len(states):]]
                snap = deepcopy(s); snap.draw_pile = remaining[1:]; snap.current_tile = tt[mv["bgId"]]
                snap.current_player = mv["player"]
                states.append((snap, (d["x"], d["y"], d["rot"], spot), mv["player"]))
                place(s, mv["bgId"], spot, mv["player"])
            if not G["conceded"]:
                s.final_scoring()
            if s.scores != G["final_scores"]:
                raise ReplayError(f"scores finaux {s.scores} ≠ BGA {G['final_scores']}")
            if first_ed:
                rep["ed1_learned"] = _learn_ed1(moves, board, ed1_table)
            return G, states, rep
    msg = f"incohérence moteur/BGA : {rep.get('deepest')}"
    if first_ed:
        msg = ("partie en tuiles 1re édition : identification des tuiles du journal "
               f"trop incertaine ({rep['ed1_known']} images déjà connues). Rejouez d'autres "
               "parties 1re édition (la table s'enrichit), puis relancez")
    err = ReplayError(msg)
    err.rep = rep
    raise err


# ------------------------------------------------------------------ CLI
def main():
    paths = []
    for a in sys.argv[1:]:
        p = Path(a)
        paths += sorted(p.glob("*.json")) if p.is_dir() else [p]
    ok, skipped, conflicts = 0, 0, set()
    for p in paths:
        rep = {}
        try:
            data = json.load(open(p, encoding="utf-8"))
            if not data.get("rawLog"):
                skipped += 1          # ancien export : rien à rejouer, on n'encombre pas la sortie
                continue
            G, states, rep = replay(data)
            ok += 1
            extra = (f", 1re édition (+{rep['ed1_learned']} images apprises)"
                     if rep.get("ed1_learned") else "")
            print(f"✅ {p.name}: {len(states)} coups, scores {G['final_scores']}, "
                  f"meeples déduits {rep['hidden_meeples']}{extra}")
        except ReplayError as e:
            print(f"❌ {p.name}: {e}")
            rep = getattr(e, "rep", {})
        except Exception as e:
            print(f"💥 {p.name}: {type(e).__name__}: {e}")
        conflicts |= set(rep.get("table_conflicts", ()))
    print(f"\n{ok}/{len(paths) - skipped} parties rejouées à l'identique"
          + (f" ({skipped} anciens exports sans rawLog ignorés)" if skipped else ""))
    if conflicts:
        print("\n⚠️ Table des spots BGA à corriger (journal ≠ table) :")
        for edges, desc, spot, logged, table in sorted(conflicts):
            print(f"   {edges} {desc:<35} spot {spot} : journal = {logged}, table = {table}")


if __name__ == "__main__":
    main()


# ------------------------------------------------------------------ données d'entraînement
def rotate_state(state, k: int = 1):
    """Tourne tout le plateau de k quarts de tour horaires (position équivalente)."""
    k %= 4
    if k == 0:
        return deepcopy(state)
    s = deepcopy(state)
    new = {}
    for (x, y), t in s.board.items():
        for _ in range(k):
            x, y = -y, x
        t.x, t.y = x, y
        t.rotation = (t.rotation + k) % 4
        sp = t.meeple_spot
        if sp and sp.startswith(("city_", "road_")):
            kind, v = sp.split("_"); t.meeple_spot = f"{kind}_{(int(v) + k) % 4}"
        elif sp and sp.startswith("field_"):
            t.meeple_spot = f"field_{(int(sp.split('_')[1]) + 2 * k) % 8}"
        new[(x, y)] = t
    s.board = new
    s.valid_positions = None
    return s


def training_positions(data: dict, augment: bool = True):
    """
    Positions exactes avant chaque coup, avec :
      state      : GameState (vrais scores, meeples, pioche restante)
      mover      : joueur qui doit jouer
      move       : (x, y, rotation, spot) réellement joué
      final      : scores finaux BGA
    Avec augment=True, chaque position est fournie sous ses 4 rotations.
    """
    G, states, _ = replay(data)
    for state, (x, y, rot, spot), mover in states:
        for k in (range(4) if augment else [0]):
            s = rotate_state(state, k)
            mx, my = x, y
            for _ in range(k):
                mx, my = -my, mx
            mspot = spot
            if spot and spot.startswith(("city_", "road_")):
                kind, v = spot.split("_"); mspot = f"{kind}_{(int(v) + k) % 4}"
            elif spot and spot.startswith("field_"):
                mspot = f"field_{(int(spot.split('_')[1]) + 2 * k) % 8}"
            yield dict(state=s, mover=mover, move=(mx, my, (rot + k) % 4, mspot),
                       final=G["final_scores"])
