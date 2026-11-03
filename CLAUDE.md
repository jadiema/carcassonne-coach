# carcassonne-coach — contexte pour Claude

Coach d'IA pour **Carcassonne** (jeu de base, 2 joueurs) sur **Board Game Arena** (BGA).
Auteur : Jérémie (pseudo BGA **Jadiema**, membre de l'équipe de France). Le coach
accompagne son livre « Le jeu Carcassonne autrement » (Éditions Jadiema).
Langue du projet : **français** (code commenté en français, messages et docs en français).

## Architecture

- **Extension Firefox** (Manifest V3, identifiant `jgrisolia@free.fr`, version 3.0.0 signée
  par Mozilla en mode non répertorié) :
  - `content-script.js` : lit la position sur BGA, panneau du coach, bouton DISCLAIMER.
  - `background.js` : utilise le serveur local s'il tourne (port 5555), sinon le moteur
    intégré au navigateur.
  - `engine_worker.js` + `pyodide/` : Python (Pyodide 0.26.4) + NumPy dans un Web Worker.
  - `browser_coach.py` : même analyse que le serveur, réseau calculé en NumPy.
- **Moteur** `carcassonne_engine.py` : règles, décompte, MCTS (`mcts_search`), fin de partie
  exacte (≤ 5 tuiles). Validé : rejoue à l'identique les parties BGA.
- **Réseau** `neural_evaluator.py` (PyTorch) : encodeur 24 canaux, tête policy (case ×
  4 rotations) utilisée par le MCTS ; tête value au palier, **non utilisée** (`use_value=False`).
  `torch_free.py` : même calcul en NumPy (vérifié identique à 3,6e-7 près).
- **Serveur local** `server.py` (Flask, optionnel, plus rapide) : n'accepte que les requêtes
  venant de l'extension.
- **Données** : `replay_bga.py` rejoue exactement une partie exportée (JSON avec `rawLog`) ;
  `selfplay.py` fait jouer le coach contre lui-même → `parties/selfplay/`.

## Règles à respecter

1. **Jamais** de parties de joueurs dans Git (`parties/` est ignoré) : ce sont les données
   personnelles de tiers.
2. L'analyse reste **bloquée pendant une partie en cours** (seulement parties terminées et
   replays, y compris les adresses `/tablereplay`). Ne pas assouplir.
3. Après toute modification du moteur : `python replay_bga.py parties` doit afficher
   « N/N parties rejouées à l'identique ». Une optimisation doit donner **exactement** les
   mêmes coups et visites MCTS qu'avant (comparer avec l'ancienne version, même graine).
4. Après toute modification de l'encodeur ou du réseau : `python verify_torch_free.py parties`.
5. Nouvelle version de l'extension : augmenter `version` dans `manifest.json`, construire
   le `.xpi` avec `python build_xpi.py` (JAMAIS `web-ext build`, qui omet les fichiers .zip,
   donc pyodide/python_stdlib.zip : le moteur du navigateur ne démarre plus) et le faire signer
   sur addons.mozilla.org ; notes pour les vérificateurs : `NOTES-VERIFICATEURS-MOZILLA.txt`.

## Commandes utiles

```powershell
python replay_bga.py parties                       # vérifie toutes les parties exportées
python selfplay.py --workers 4                     # auto-jeu (la nuit ; Ctrl+C pour arrêter)
python neural_evaluator.py train parties 30        # entraînement (humain + auto-jeu)
python evaluate_model.py parties --step 2          # banc de test : top1/top3 vs joueurs forts
python verify_torch_free.py parties                # réseau NumPy = réseau PyTorch
```

## État actuel (v32)

- Réseau v28 entraîné sur 401 parties de joueurs forts.
- v31 : moteur 2 à 6 fois plus rapide (caches par tuile), auto-jeu en place (`selfplay.py`).
- v32 : le MCTS classe les coups par **nombre de visites** (et non par taux de victoire), et
  la valeur d'un meeple en réserve suit le **prix du meeple** du chapitre 8 du livre
  (λ = 0,4 à 2,4 point par tour bloqué selon la réserve). Accord avec les joueurs forts,
  387 positions, 300 simulations, coup complet : 12,7 % → 25,1 % (top1), 27,1 % → 41,1 % (top3).
  Auto-jeu : score moyen 45 → 95 points (joueurs forts : 91).
- Les parties d'auto-jeu générées avec la v31 sont à écarter de l'entraînement
  (`parties/selfplay_v31/`, non lu par `train`).
- `bench_mcts.py` : banc de test du MCTS (top1/top3 contre les coups des joueurs forts).
- Prochaines étapes : auto-jeu v32, entraînement mélangé, version 3.0.1 de l'extension
  (moteur v32 + `update_url`) à faire signer ; dépôt public à la sortie du livre.

PC de développement : Intel i7-7700 (4 cœurs), 32 Go de RAM, NVIDIA Quadro P2000, Windows.
