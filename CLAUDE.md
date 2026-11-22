# carcassonne-coach — contexte pour Claude

Coach d'IA pour **Carcassonne** (jeu de base, 2 joueurs) sur **Board Game Arena** (BGA).
Auteur : Jérémie (pseudo BGA **Jadiema**, membre de l'équipe de France). Le coach
accompagne son livre « Carcassonne, le jeu autrement – Du hasard à l'intelligence
artificielle » (Éditions Jadiema).
Langue du projet : **français** (code commenté en français, messages et docs en français).

## Architecture

- **Extension Firefox** (Manifest V3, identifiant `jgrisolia@free.fr`, version 3.1.1 signée
  par Mozilla en mode non répertorié, mise à jour automatique via `updates.json`) :
  - `content-script.js` : lit la position sur BGA, panneau du coach (onglets Probabilités et
    Analyse), bouton DISCLAIMER.
  - `probabilites.js` : calculs de l'onglet Probabilités (chapitres 1 à 3 du livre).
  - `background.js` : utilise le serveur local s'il tourne (port 5555), sinon le moteur
    intégré au navigateur.
  - `engine_worker.js` + `pyodide/` : Python (Pyodide 0.26.4) + NumPy dans un Web Worker.
  - `browser_coach.py` : même analyse que le serveur, réseau calculé en NumPy.
- **Moteur** `carcassonne_engine.py` : règles, décompte, MCTS (`mcts_search`), fin de partie
  exacte (≤ 5 tuiles). Validé : rejoue à l'identique les parties BGA.
- **Réseau** `neural_evaluator.py` (PyTorch) : encodeur 24 canaux, tête policy (case ×
  4 rotations) utilisée par le MCTS ; tête value **utilisée par la recherche depuis la v3.0.3** (réseau v33 entraîné sur l'auto-jeu :
  +74 Elo contre la v33 sans value, +69 Elo contre la v28 de la 3.0.2, matchs de 200 parties).
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
   le `.xpi` avec `python build_xpi.py` (fichiers de l'extension uniquement) et le faire signer
   sur addons.mozilla.org ; notes pour les vérificateurs : `NOTES-VERIFICATEURS-MOZILLA.txt`.

## Commandes utiles

```powershell
python replay_bga.py parties                       # vérifie toutes les parties exportées
python selfplay.py --workers 4                     # auto-jeu (la nuit ; Ctrl+C pour arrêter)
python neural_evaluator.py train parties 30        # entraînement (humain + auto-jeu)
python evaluate_model.py parties --step 2          # banc de test : top1/top3 vs joueurs forts
python verify_torch_free.py parties                # réseau NumPy = réseau PyTorch
```

## État actuel (3.1.1)

- Extension 3.1.1 : réseau **v33** (tête policy + tête value), entraîné sur les parties de
  joueurs forts et l'auto-jeu. Validation (15 parties, 989 positions), case seule :
  top1 41,2 %, top3 71,0 % (heuristique : 35,6 % / 57,0 %).
- Analyse **réservée aux parties terminées et aux replays** (3.0.4) : interdite par défaut,
  autorisée seulement avec une preuve de fin (`finishedProof()`), vérifiée à chaque point
  d'entrée (bouton, export JSON, serveur local, worker).
- Renvois vers le livre (3.1.1) : `livre.js` (liens, titres FR/EN, pastilles « 📖 ch. N »), bouton
  du livre en bas du panneau, section À propos de la fenêtre de l'icône, page de bienvenue
  (`welcome.html`) ouverte seulement à l'installation ; liens vers les sections Le livre / The book
  des README (README.md en anglais, README.fr.md en français). Onglet Probabilités à gauche.
- Onglet **Probabilités** (3.1.0) : sac, familles de tuiles, chances de tirage, entropie,
  trous du plateau ; lit la position uniquement via `extractFinishedState()` et suit le replay.
  En-tête du panneau et onglet lisent la même position.
- v32 : le MCTS classe les coups par **nombre de visites**, et la valeur d'un meeple en
  réserve suit le **prix du meeple** du chapitre 8 du livre (λ = 0,4 à 2,4 point par tour
  bloqué selon la réserve).
- Les parties d'auto-jeu générées avec la v31 sont à écarter de l'entraînement
  (`parties/selfplay_v31/`, non lu par `train`).
- `bench_mcts.py` : banc de test du MCTS (top1/top3 contre les coups des joueurs forts).
- Aucun pseudo de joueur dans le dépôt : `python verifier_pseudos.py` avant chaque publication.
- Publication : créer la release GitHub **avant** de pousser `updates.json`.

PC de développement : Intel i7-7700 (4 cœurs), 32 Go de RAM, NVIDIA Quadro P2000, Windows.
