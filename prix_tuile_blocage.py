"""prix_tuile_blocage.py — Mesure le « prix d'une tuile » et le coût d'une tuile de blocage.

Usage : python prix_tuile_blocage.py dossier_des_exports/   (exports AVEC rawLog)
Nécessite carcassonne_engine.py dans le même dossier.

1. Rejoue chaque partie coup par coup (ordre du moveLog, positions finales du board,
   meeples d'après le rawLog) et vérifie que le score final colle à celui de BGA.
2. Attribue à chaque tuile sa part des points de chaque structure gagnée
   (points de la structure / nombre de tuiles), pour le joueur qui l'a posée.
3. Repère les coups de blocage : la tuile est posée À CÔTÉ d'une case qui borde une ville
   ou une route occupée par l'adversaire, et réduit le nombre de tuiles du sac capables
   de combler cette case (« condamnation » si ce nombre tombe à zéro).
"""
import json, sys, glob, os, copy
from collections import defaultdict
from statistics import mean
import carcassonne_engine as ce
from carcassonne_engine import GameState, PlacedTile, DX, DY, OPPOSITE

KIND = {'ville': 'city', 'route': 'road', 'pré': 'field', 'abbaye': 'monastery'}

class Replay(GameState):
    """GameState qui enregistre à qui va chaque point, et sur quelles tuiles."""
    def __init__(self, n):
        super().__init__(n); self.ledger = []          # (tiles, {player: pts})
        self.events = []; self.k = -1                  # (k, type, tiles, completed, gain)
    def _score_structure(self, result, struct_type, completed):
        before = list(self.scores)
        super()._score_structure(result, struct_type, completed)
        gain = {p: self.scores[p] - before[p] for p in range(self.num_players) if self.scores[p] != before[p]}
        if gain:
            self.ledger.append((set(result['tiles']), gain))
            self.events.append((self.k, struct_type, set(result['tiles']), completed, gain))
    def _score_fields(self):
        visited, cache = set(), {}
        for (x, y), tile in list(self.board.items()):
            for seg in ce.tile_field_segments(tile):
                hs = min(seg)
                if (x, y, hs) in visited: continue
                fr = self._trace_field(x, y, hs); visited |= fr['visited']
                if not fr['meeples']: continue
                n = self._count_adjacent_complete_cities(fr['tiles_and_sides'], cache)
                if not n: continue
                m = max(fr['meeples'].values()); gain = {}
                for o, c in fr['meeples'].items():
                    if c == m: self.scores[o] += 3 * n; gain[o] = 3 * n
                self.ledger.append((set(fr['tiles']), gain))

def block9(x, y): return {(x + i, y + j) for i in (-1, 0, 1) for j in (-1, 0, 1)}

def tile_type_of(bt):
    tt = ce._find_tile_type(bt['edgesOriginal'], bt.get('shield', False), bt.get('desc', ''))
    if tt is None or ce.rotate_edges(tt.edges, bt['rotation']) != bt['edges']:
        mon = 'monast' in bt.get('desc', '').lower() or 'abbaye' in bt.get('desc', '').lower()
        tt = ce.TileType(bt['edgesOriginal'], 1, shield=bt.get('shield', False), monastery=mon)
    return tt

def parse(d):
    names = [p['name'] for p in d['players']]
    board = {bt['bgId']: bt for bt in d['board'] if bt.get('location')}
    moves = []
    for e in d['rawLog']:
        t = e['text']
        for i, n in enumerate(names):
            if t.startswith(n + ' place une tuile'):
                moves.append({'player': i, 'meeple': None})
            elif t.startswith(n + ' place un partisan sur la tuile '):
                import re as _re
                w = _re.match(r'[a-zàâçéèêëîïôûùüÿ]+', t.split('sur la tuile ')[1]).group(0)
                moves[-1]['meeple'] = KIND.get(w)
    order = [m['bgId'] for m in d['moveLog']]
    assert len(order) == len(moves), 'rawLog et moveLog ne concordent pas'
    for m, b in zip(moves, order): m['bt'] = board[b]
    start = [bt for b, bt in board.items() if b not in set(order)]
    return names, start[0], moves

def expected_scores(d, names):
    """Score de chaque joueur après chaque coup, d'après les « gagne N points » du rawLog."""
    import re
    exp, cur, started = [], [0] * len(names), False
    for e in d['rawLog']:
        t = e['text']
        if 'Décompte' in t or 'approvisionne' in t or 'Fin de la partie' in t: break
        for i, n in enumerate(names):
            if t.startswith(n + ' place une tuile'):
                if started: exp.append(list(cur))
                started = True
            m = re.match(re.escape(n) + r' gagne (\d+) points', t)
            if m: cur[i] += int(m.group(1))
    exp.append(list(cur))
    return exp

def replay(d, choices=None, record=None, gs_out=None):
    names, start, moves = parse(d)
    expected = expected_scores(d, names)
    gs = Replay(len(names)); gs.player_names = names
    col = {p['color']: i for i, p in enumerate(d['players'])}
    st = start; gs.board[(st['location']['x'], st['location']['y'])] = PlacedTile(tile_type_of(st), st['location']['x'], st['location']['y'], st['rotation'])
    owner, ambiguous = {}, []
    types = [tile_type_of(m['bt']) for m in moves]
    for k, m in enumerate(moves):
        bt, tt, p = m['bt'], types[k], m['player']
        x, y, r = bt['location']['x'], bt['location']['y'], bt['rotation']
        spot = None
        if m['meeple']:
            opts = [s for s in ce._meeple_options(gs, tt, x, y, r) if s.startswith(m['meeple'])]
            fin = bt.get('meeple')
            if fin and col.get(fin['color']) == p:
                g = ce._guess_meeple_spot(tt, r, fin['spot'])
                g2 = [s for s in opts if s == g]
                if g2: opts = g2
            if len(opts) > 1 and expected and k < len(expected):
                good = []
                for s in opts:                    # garde le spot qui redonne le score BGA du coup
                    t = copy.deepcopy(gs); t.place_tile(tt, x, y, r, p, s)
                    if t.scores == expected[k]: good.append(s)
                if good: opts = good
            if len(opts) > 1: ambiguous.append((k, opts))
            if opts: spot = opts[(choices or {}).get(k, 0) % len(opts)]
        if record is not None:
            bag = types[k + 1:]
            record(gs, k, p, tt, x, y, r, bag)
        gs.k = k
        mons = {pos for pos, t in gs.board.items() if t.tile_type.monastery and t.meeple_spot == 'monastery'}
        sc = list(gs.scores)
        gs.place_tile(tt, x, y, r, p if spot else None, spot)
        for pos in mons:
            if gs.board[pos].meeple_spot != 'monastery':
                gain = {o: gs.scores[o] - sc[o] for o in range(len(names)) if gs.scores[o] > sc[o]}
                gs.ledger.append((block9(*pos), {o: 9 for o in gain}))
        owner[(x, y)] = p
    # abbayes inachevées
    for (x, y), t in gs.board.items():
        if t.tile_type.monastery and t.meeple_spot == 'monastery':
            cells = {c for c in block9(x, y) if c in gs.board}
            gs.ledger.append((cells, {t.meeple_player: len(cells)}))
    gs.k = len(moves)
    gs.final_scoring()
    if gs_out is not None: gs_out.append(gs)
    return gs, owner, ambiguous

def replay_ok(d):
    target = [p['score'] for p in d['players']]
    gs, owner, amb = replay(d)
    if gs.scores == target: return {}, gs, owner
    for k, opts in amb:                        # essaie l'autre choix, un coup ambigu à la fois
        for i in range(1, len(opts)):
            gs2, o2, _ = replay(d, {k: i})
            if gs2.scores == target: return {k: i}, gs2, o2
    return None, gs, owner

def fit_count(gs, cx, cy, bag):
    seen, n = {}, 0
    for t in bag:
        if id(t) not in seen:
            seen[id(t)] = any(gs.can_place(t, cx, cy, r) for r in range(4))
        n += seen[id(t)]
    return n

from math import comb

def p_fill(f, R, d):
    """Probabilité de piocher au moins une des f tuiles utiles en d tirages parmi R (loi hypergéométrique)."""
    if f <= 0 or d <= 0: return 0.0
    if R - f < d: return 1.0
    return 1 - comb(R - f, d) / comb(R, d)

def opp_structures(gs, opp):
    """Villes et routes incomplètes où l'adversaire est majoritaire : liste de (type, résultat, cases du bord)."""
    out, done = [], set()
    for (x, y), t in gs.board.items():
        for s in range(4):
            e = t.edges[s]
            if e not in 'CR' or (x, y, s) in done: continue
            typ = 'city' if e == 'C' else 'road'
            res = gs._trace_structure(x, y, s, typ)
            done |= res['sides']
            mp = res['meeples']
            if res['complete'] or not mp or mp.get(opp, 0) <= max([c for q, c in mp.items() if q != opp] or [0]):
                continue
            cells = {(sx + DX[ss], sy + DY[ss]) for (sx, sy, ss) in res['sides']} - set(gs.board)
            if cells: out.append((typ, res, cells))
    return out

def meeple_value(R):
    """Prix d'un meeple libre (chapitre 8) : environ 13 points en début de partie, décroissant avec les tuiles restantes."""
    return 13.0 * R / 70

def analyse(d):
    choices, gs, owner = replay_ok(d)
    if choices is None: return None
    blocks, targets, controls = {}, [], []
    def rec(state, k, p, tt, x, y, r, bag):
        opp = 1 - p
        structs = opp_structures(state, opp)
        R = len(bag); dd = (R + 1) // 2
        near = [st for st in structs if any(abs(c[0] - x) + abs(c[1] - y) == 1 for c in st[2])]
        hit = False
        if near:
            state.board[(x, y)] = PlacedTile(tt, x, y, r)
            for typ, res, cells in near:
                cells_after = cells - {(x, y)}
                fb = {c: fit_count_off(state, c, bag, (x, y)) for c in cells}
                fa = {c: fit_count(state, *c, bag) for c in cells_after}
                if (x, y) in cells or not any(fa[c] < fb[c] for c in cells_after if c in fb): continue
                hit = True
                kill = any(fa[c] == 0 < fb[c] for c in cells_after)
                pb = 1.0
                for c in cells: pb *= p_fill(fb[c], R, dd)
                pa = 1.0
                for c in cells_after: pa *= p_fill(fa[c], R, dd)
                n = len(res['tiles']); sh = len({(a, b) for (a, b, _) in res['sides'] if state.board[(a, b)].tile_type.shield}) if typ == 'city' else 0
                gain_pts = (n + sh) if typ == 'city' else 0
                nm = res['meeples'].get(opp, 0)
                targets.append({'opp': opp, 'k': k, 'typ': typ, 'n': n, 'R': R, 'rep': next(iter(res['tiles'])),
                                'dp': pb - pa, 'pts': (pb - pa) * gain_pts, 'mee': (pb - pa) * nm * meeple_value(R), 'kill': kill})
            del state.board[(x, y)]
            if hit: blocks[(x, y)] = 'condamne' if any(t['kill'] for t in targets if t['k'] == k) else 'contraint'
        for typ, res, cells in structs:
            if any(abs(c[0] - x) + abs(c[1] - y) == 1 for c in cells): continue
            controls.append({'opp': opp, 'k': k, 'typ': typ, 'n': len(res['tiles']), 'R': R, 'rep': next(iter(res['tiles']))})
    gs_out = []
    replay(d, choices, rec, gs_out)
    gsr = gs_out[0]
    def outcome(o):
        closed, pts = False, 0
        for (kk, typ, tiles, comp, gain) in gsr.events:
            if kk >= o['k'] and typ == o['typ'] and o['rep'] in tiles:
                pts += gain.get(o['opp'], 0)
                closed = closed or comp
                break
        return closed, pts
    for o in targets + controls: o['closed'], o['opp_pts'] = outcome(o)
    val = defaultdict(float)
    for tiles, gain in gs.ledger:
        for pos in tiles:
            if pos in owner and owner[pos] in gain:
                val[pos] += gain[owner[pos]] / len(tiles)
    rows = [{'v': val[pos], 'bloc': blocks.get(pos)} for pos in owner]
    return rows, targets, controls

def fit_count_off(gs, cell, bag, off):
    """Nombre de tuiles du sac qui comblent la case, en ignorant la tuile posée en `off`."""
    t = gs.board.pop(off)
    try: return fit_count(gs, *cell, bag)
    finally: gs.board[off] = t

def main():
    paths = sys.argv[1:] or ['.']
    files = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, '*.json'))) if os.path.isdir(p) else [p]
    allrows, T, C, ok, ko = [], [], [], 0, []
    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        if 'rawLog' not in d or d.get('moveCount') != 71: ko.append((f, 'pas de rawLog ou partie incomplète')); continue
        try:
            r = analyse(d)
        except Exception as e:
            ko.append((f, f'erreur {e.__class__.__name__}: {e}')); continue
        if r is None: ko.append((f, 'score rejoué ≠ score BGA')); continue
        allrows += r[0]; T += r[1]; C += r[2]; ok += 1
    print(f'Parties rejouées exactement : {ok}   écartées : {len(ko)}')
    for f, why in ko: print(f'  - {os.path.basename(f)} : {why}')
    if not allrows: return
    v = lambda L: mean(r['v'] for r in L) if L else float('nan')
    b = [r for r in allrows if r['bloc']]; c = [r for r in allrows if r['bloc'] == 'condamne']
    nb = [r for r in allrows if not r['bloc']]
    print(f"\n=== COÛT pour celui qui bloque ===")
    print(f"Tuiles posées              : {len(allrows)}")
    print(f"Tuiles hors blocage        : {v(nb):.2f} pt  ({len(nb)})")
    print(f"Tuiles de blocage          : {v(b):.2f} pt  ({len(b)}, dont {len(c)} condamnent une case)")
    print(f"  dont condamnations       : {v(c):.2f} pt")
    print(f"Coût moyen d'un blocage    : {v(nb) - v(b):.2f} pt")
    if not T: return
    M = lambda L, k: mean(o[k] for o in L) if L else float('nan')
    kill = [t for t in T if t['kill']]
    print(f"\n=== DOMMAGE pour l'adversaire, méthode 1 (probabilités) ===")
    print(f"Structures adverses visées : {len(T)}  (villes {sum(t['typ']=='city' for t in T)}, routes {sum(t['typ']=='road' for t in T)})")
    print(f"Baisse moyenne de la chance de fermer : {100*M(T,'dp'):.0f} points de %")
    print(f"Points de ville perdus     : {M(T,'pts'):.2f} pt")
    print(f"Meeple immobilisé (ch. 8)  : {M(T,'mee'):.2f} pt")
    print(f"Dommage total estimé       : {M(T,'pts')+M(T,'mee'):.2f} pt par structure visée")
    if kill: print(f"  dont condamnations ({len(kill)}) : {M(kill,'pts')+M(kill,'mee'):.2f} pt")
    # méthode 2 : comparaison appariée (type, taille, moment de la partie)
    key = lambda o: (o['typ'], min(o['n'], 5), o['R'] // 10)
    grp = defaultdict(list)
    for o in C: grp[key(o)].append(o)
    dc, dp_, w = 0.0, 0.0, 0
    for t in T:
        g = grp.get(key(t))
        if not g: continue
        dc += mean(o['closed'] for o in g) - t['closed']
        dp_ += mean(o['opp_pts'] for o in g) - t['opp_pts']; w += 1
    if w:
        print(f"\n=== DOMMAGE pour l'adversaire, méthode 2 (parties réelles) ===")
        print(f"Structures visées comparées : {w}")
        print(f"Fermées ensuite : visées {100*M(T,'closed'):.0f} %   (écart avec les structures comparables : −{100*dc/w:.0f} points de %)")
        print(f"Points finalement marqués par l'adversaire : −{dp_/w:.2f} pt par rapport aux structures comparables")

if __name__ == '__main__':
    main()
