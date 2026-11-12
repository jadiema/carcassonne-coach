"""virage_premier_tour.py — Combien de temps reste bloqué le meeple posé sur un virage au premier tour ?

Usage : python virage_premier_tour.py parties
Nécessite carcassonne_engine.py et prix_tuile_blocage.py dans le même dossier.

Pour chaque partie rejouée exactement, on regarde le premier coup de chaque joueur.
Si la tuile est un virage simple (deux routes sur des côtés voisins, sans ville ni abbaye) :
  - avec un meeple sur la route : on mesure le nombre de tours de ce joueur avant que la route
    ne se ferme, ou on note qu'elle ne s'est jamais fermée (meeple bloqué jusqu'à la fin) ;
  - sans meeple : on compte simplement le cas (le « coup de Nazario »).
"""
import json, sys, glob, os
from statistics import mean, median
import prix_tuile_blocage as P

def is_curve(bt):
    e = bt['edges']
    if 'C' in e or 'monast' in bt.get('desc', '').lower() or 'abbaye' in bt.get('desc', '').lower(): return False
    idx = [i for i, c in enumerate(e) if c == 'R']
    return len(idx) == 2 and (idx[1] - idx[0]) in (1, 3)

def analyse(d):
    choices, gs, owner = P.replay_ok(d)
    if choices is None: return None
    names, start, moves = P.parse(d)
    out_ = []
    seen = set()
    for k, m in enumerate(moves):
        if m['player'] in seen: continue
        seen.add(m['player'])
        bt = m['bt']
        if not is_curve(bt): continue
        if m['meeple'] != 'road':
            out_.append({'meeple': False}); continue
        pos = (bt['location']['x'], bt['location']['y'])
        closed_at = None
        for (kk, typ, tiles, comp, gain) in gs.events:
            if typ == 'road' and comp and pos in tiles and kk >= k and m['player'] in gain:
                closed_at = kk; break
        n_moves = len(moves)
        if closed_at is None:
            out_.append({'meeple': True, 'closed': False, 'tours': (n_moves - k) / 2})
        else:
            out_.append({'meeple': True, 'closed': True, 'tours': (closed_at - k) / 2})
        if len(seen) == 2: break
    return out_

def main():
    paths = sys.argv[1:] or ['.']
    files = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, '*.json'))) if os.path.isdir(p) else [p]
    rows, ok, ko = [], 0, 0
    for f in files:
        try:
            d = json.load(open(f, encoding='utf-8'))
            if 'rawLog' not in d or d.get('moveCount') != 71: ko += 1; continue
            r = analyse(d)
        except Exception:
            ko += 1; continue
        if r is None: ko += 1; continue
        rows += r; ok += 1
    print(f'Parties rejouées exactement : {ok}   écartées : {ko}')
    sans = [r for r in rows if not r['meeple']]
    avec = [r for r in rows if r['meeple']]
    print(f'\nPremiers coups avec un virage : {len(rows)}')
    print(f'  sans meeple (coup de Joueur) : {len(sans)}')
    print(f'  avec un meeple sur la route     : {len(avec)}')
    if not avec: return
    fermees = [r for r in avec if r['closed']]
    jamais = [r for r in avec if not r['closed']]
    t = [r['tours'] for r in fermees]
    print(f'\nRoute fermée avant la fin : {len(fermees)} ({100*len(fermees)/len(avec):.0f} %)')
    if t:
        print(f'  tours bloqués : moyenne {mean(t):.1f}, médiane {median(t):.1f}')
        for a, b in [(0, 4), (4.5, 10), (10.5, 20), (20.5, 99)]:
            n = sum(1 for x in t if a <= x <= b)
            print(f'  {a:>4}–{b:<3} tours : {n} ({100*n/len(avec):.0f} % des meeples)')
    print(f'Route jamais fermée (meeple bloqué jusqu’à la fin) : {len(jamais)} ({100*len(jamais)/len(avec):.0f} %)')
    enlise = sum(1 for r in avec if (not r['closed']) or r['tours'] > 20)
    print(f'\n« Enlisée » (jamais fermée, ou bloquée plus de 20 tours) : {enlise} ({100*enlise/len(avec):.0f} %)')

if __name__ == '__main__':
    main()
