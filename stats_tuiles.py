"""stats_tuiles.py — Vérifie le « prix d'une tuile » sur des exports JSON du Carcassonne Coach.

Usage :  python stats_tuiles.py dossier_des_exports/
         python stats_tuiles.py partie1.json partie2.json ...

Pour chaque partie terminée (moveCount == 71), on lit le score final de chaque joueur
et on compte ses tuiles posées dans le moveLog (la tuile de départ n'appartient à personne).
"""
import json, sys, glob, os
from collections import defaultdict
from statistics import mean, pstdev

def charger(paths):
    fichiers = []
    for p in paths:
        fichiers += sorted(glob.glob(os.path.join(p, '*.json'))) if os.path.isdir(p) else [p]
    return fichiers

def analyser(path):
    d = json.load(open(path, encoding='utf-8'))
    if d.get('moveCount') != 71 or d.get('remainingCount', 1) != 0:
        return None, 'partie non terminée'
    joueurs = d['players']
    if len(joueurs) != 2:
        return None, 'pas 2 joueurs'
    tuiles = defaultdict(int)
    for m in d['moveLog']:
        tuiles[m.get('player')] += 1
    lignes = []
    for j in joueurs:
        n = tuiles.get(j['name'], 0)
        if n == 0:
            return None, f"aucune tuile trouvée pour {j['name']}"
        lignes.append({'nom': j['name'], 'score': j['score'], 'tuiles': n})
    gagnant = max(lignes, key=lambda l: l['score'])
    for l in lignes:
        l['gagnant'] = (l is gagnant)
    return lignes, None

def main():
    fichiers = charger(sys.argv[1:] or ['.'])
    tous, rejets = [], defaultdict(int)
    for f in fichiers:
        try:
            r, err = analyser(f)
        except Exception as e:
            r, err = None, f'illisible ({e.__class__.__name__})'
        if r: tous += r
        else: rejets[err] += 1
    if not tous:
        print('Aucune partie exploitable.'); return
    def bilan(titre, L):
        sc = [l['score'] for l in L]; tu = [l['tuiles'] for l in L]
        print(f"\n{titre} ({len(L)} joueurs)")
        print(f"  score moyen          : {mean(sc):6.1f}  (écart-type {pstdev(sc):.1f})")
        print(f"  tuiles posées        : {mean(tu):6.1f}")
        print(f"  points par tuile     : {sum(sc)/sum(tu):6.2f}")
    print(f"Parties analysées : {len(tous)//2}   (rejetées : {sum(rejets.values())})")
    for k, v in rejets.items(): print(f"  - {v} × {k}")
    bilan('Tous les joueurs', tous)
    bilan('Gagnants', [l for l in tous if l['gagnant']])
    bilan('Perdants', [l for l in tous if not l['gagnant']])

if __name__ == '__main__':
    main()
