# Carcassonne Coach

Un coach d’intelligence artificielle pour Carcassonne (jeu de base, 2 joueurs) sur Board Game Arena (BGA). L’extension Firefox lit une partie terminée ou un replay (l’analyse est désactivée pendant une partie en cours, conformément aux règles de Board Game Arena), cherche les meilleurs coups avec une recherche arborescente de Monte-Carlo (MCTS) guidée par un réseau de neurones, et les affiche sur le plateau. Tout le calcul se fait dans le navigateur ; aucune donnée n’est envoyée ailleurs.

> Projet indépendant, sans lien avec Hans im Glück ni avec Board Game Arena. Carcassonne est une marque déposée de Hans im Glück Verlags-GmbH. Le coach ne reproduit aucune image du jeu : il lit la page de Board Game Arena dans votre navigateur.

Ce dépôt accompagne le livre *Carcassonne, le jeu autrement – Du hasard à l’intelligence artificielle* (Éditions Jadiema).

## Sommaire

- [Installation](#installation)
- [Utilisation sur Board Game Arena](#utilisation-sur-board-game-arena)
- [Fonctionnement](#fonctionnement)
- [Serveur local (facultatif)](#serveur-local-facultatif)
- [Constituer les données d’entraînement](#constituer-les-données-dentraînement)
- [Entraîner et évaluer le réseau](#entraîner-et-évaluer-le-réseau)
- [Scripts d’analyse](#scripts-danalyse)
- [Fabriquer le paquet de l’extension](#fabriquer-le-paquet-de-lextension)
- [Organisation des fichiers](#organisation-des-fichiers)
- [Historique et état actuel](#historique-et-état-actuel)
- [Limites connues](#limites-connues)
- [Licence](#licence)

## Installation

1. Dans Firefox (version 140 ou plus récente), ouvrir la [dernière version](https://github.com/jadiema/carcassonne-coach/releases/latest).
2. Cliquer sur `carcassonne-coach.xpi`, puis sur **Ajouter**.

C’est tout : rien d’autre à installer. L’extension est signée par Mozilla, elle reste en place après le redémarrage de Firefox et les versions suivantes s’installent automatiquement.

## Utilisation sur Board Game Arena

1. Ouvrir une partie terminée ou un replay de Carcassonne sur BGA.
2. Cliquer sur le bouton 🏰 ajouté par l’extension, choisir son joueur et le temps d’analyse.
3. Lancer l’analyse : les meilleurs coups apparaissent sur le plateau. La tuile conseillée est dessinée dans sa bonne orientation, avec le meeple à sa place.

L’onglet **Probabilités** reprend les calculs des chapitres 1 à 3 du livre : état du sac, familles de tuiles (arrêts de route, lignes, villes en coin, vrais virages, capuchons, courbes) avec la chance au prochain tirage et sur vos prochains tirages, entropie en bits, et trous du plateau autour de vos structures, y compris la fusion avec une ville adverse. Il suit la position affichée du replay, en avant comme en arrière.

L’interface existe en français et en anglais : cliquer sur le drapeau du panneau pour changer de langue (le choix est mémorisé).

## Fonctionnement

```
 Firefox (boardgamearena.com)
┌───────────────────────────────┐         ┌──────────────────────────────────────┐
│ content-script.js             │         │ engine_worker.js (Pyodide + NumPy)   │
│  · lit plateau, tuile en      │ ──────▶ │   └─ browser_coach.py                │
│    main, cases libres, sac    │         │        · carcassonne_engine.py       │
│  · affiche les coups          │ ◀────── │          règles, décompte, MCTS      │
│    recommandés                │         │        · réseau en NumPy             │
└───────────────────────────────┘         │          (torch_free.py)             │
                                          └──────────────────────────────────────┘
                    (si lancé : server.py sur le port 5555, environ deux fois plus rapide)
```

- **L’extension** lit la position sur BGA : plateau, tuile en main, cases libres, tuiles restantes, scores et meeples.
- **Le moteur Python** (`carcassonne_engine.py`) tourne dans le navigateur grâce à Pyodide 0.26.4. Il génère les coups légaux, puis lance le MCTS pendant le temps choisi. Les coups sont classés par nombre de visites, et le prix d’un meeple immobilisé est pris en compte.
- **Le réseau** (`carcassonne_model.pt`, lu sans PyTorch par `torch_free.py`) fournit :
  - une **politique** : une probabilité pour chaque (case, rotation), qui oriente l’exploration ;
  - une **valeur** : la chance de victoire, qui juge les positions dans la recherche.
- **La réponse de l’adversaire** (`expectimax_rerank`) départage les meilleurs coups en regardant aussi le coup suivant de l’adversaire (Expectimax sur deux coups), avec une chance de fermer les villes calculée sur le sac et les fusions de villes.

## Serveur local (facultatif)

L’extension n’a besoin de rien d’autre. Pour aller environ deux fois plus vite, on peut lancer le serveur Python du dépôt : l’extension l’utilise alors automatiquement.

```
pip install -r requirements.txt
python server.py
```

Sous Windows, `start_server.bat` fait la même chose. Le serveur écoute sur `http://127.0.0.1:5555`.

## Constituer les données d’entraînement

1. Sur BGA, ouvrir une partie terminée (de préférence entre joueurs forts) et cliquer sur le bouton JSON de l’extension.
2. Ranger les fichiers dans le dossier `parties/`.
3. Vérifier que chaque partie se rejoue exactement :

```
python replay_bga.py parties
```

Chaque partie doit afficher `✅ … rejouée à l’identique` : le rejeu refait tous les coups et compare les scores finaux à ceux de BGA. Les parties en échec sont écartées de l’entraînement.

**Parties en tuiles « 1re édition ».** Dans les replays, BGA affiche l’édition choisie par les joueurs ; l’extension ne reconnaît pas ces images. `replay_bga.py` retrouve alors les tuiles par déduction et apprend la correspondance image → type dans `ed1_art_table.json`. Relancer le contrôle une seconde fois permet souvent de rejouer les parties qui avaient échoué.

> Le contenu de `parties/` n’est pas versionné : ce sont les parties d’autres joueurs, avec leurs pseudos. Seul `carcassonne_model.validation.json` (liste des parties de validation) est suivi.

## Entraîner et évaluer le réseau

L’entraînement demande PyTorch ; une carte graphique (CUDA) l’accélère nettement.

### Auto-jeu

```
python selfplay.py --value
```

Le moteur joue contre lui-même avec le réseau courant ; les parties sont rangées dans `parties/`.

### Entraîner

```
python neural_evaluator.py train parties 30 --selfplay-keep=0.04
```

- 30 époques au maximum, arrêt automatique après 4 époques sans progrès en validation ;
- la validation est figée (`carcassonne_model.validation.json`) ; `--new-split` en tire une nouvelle ;
- chaque plateau est présenté sous ses 4 rotations ;
- `--selfplay-keep` règle la part des positions d’auto-jeu conservées ;
- les parties sont lues en parallèle.

Au début de l’entraînement, vérifier la ligne « Contrôle des rotations » : aucune rotation ne doit rester « sans équivalent ».

### Évaluer

```
python arena.py --a carcassonne_model_v33.pt --b carcassonne_model_v28.pt
```

Fait jouer deux configurations l’une contre l’autre et donne l’écart en Elo. Options : `--sims-a/b` (nombre de simulations), `--value-a/b` (tête valeur), `--reply-a/b` (réponse de l’adversaire).

```
python evaluate_model.py parties
```

Rejoue les parties de validation et mesure, sur chaque position, si le coup réellement joué par le joueur fort figure dans le top 1 / top 3 de chaque méthode. Résultats du réseau v33 (989 positions des 15 parties de validation) :

| Méthode | Top 1 | Top 3 |
|---|---|---|
| Hasard parmi les coups légaux | 6,4 % | 19,0 % |
| Heuristique du moteur | 31,2 % | 48,6 % |
| Réseau, tête valeur | 20,3 % | 37,8 % |
| Réseau, politique | 36,4 % | 62,5 % |

La liste de validation (`carcassonne_model.validation.json`) ne contient que des numéros de table ; ces parties ne doivent jamais servir à l’entraînement.

`bench_mcts.py` mesure si la recherche MCTS retrouve le coup des joueurs forts (top 1 / top 3, coup complet).

## Scripts d’analyse

| Script | Rôle | Commande |
|---|---|---|
| `replay_bga.py` | Rejoue les parties et vérifie les scores finaux ; apprend les images de la 1re édition | `python replay_bga.py parties` |
| `evaluate_model.py` | Compare réseau, heuristique et hasard sur les parties de validation | `python evaluate_model.py parties` |
| `prix_meeple.py` | Suit chaque meeple de sa pose à son retour : rendement (points par tour bloqué) selon la phase, la structure et le stock de meeples | `python prix_meeple.py parties` |
| `prix_tuile_blocage.py` | Prix de la tuile de blocage | `python prix_tuile_blocage.py parties` |
| `stats_tuiles.py` | Statistiques des tuiles | `python stats_tuiles.py parties` |
| `virage_premier_tour.py` | Premier tour avec un virage simple : durée de blocage d’un meeple posé sur la route, ou fréquence du virage posé sans meeple (le « coup de Nazario ») | `python virage_premier_tour.py parties` |
| `bayes_paysans.py` | Cherche deux styles de joueurs (agressif / prudent) dans les prés par un mélange de lois binomiales (algorithme EM) | `python bayes_paysans.py parties` |
| `diag_rotation.py` | Diagnostic de la convention de rotation de l’augmentation des données | `python diag_rotation.py parties` |
| `check_spots.py` | Vérifie la table des emplacements de meeples BGA | `python check_spots.py parties` |
| `calibrate_spots.py` | Recherche l’affectation des paysans ambigus quand seul le décompte final diffère de BGA | `python calibrate_spots.py parties` |

Les fichiers produits (CSV, PNG) ne sont pas versionnés.

## Fabriquer le paquet de l’extension

```
python build_xpi.py
```

Produit `carcassonne-coach-<version>.xpi`, à faire signer par Mozilla. **Ne pas utiliser `web-ext build`**, qui omet les fichiers `.zip` (dont `pyodide/python_stdlib.zip`, indispensable).

Avant toute publication, `python verifier_pseudos.py` vérifie qu’aucun pseudo de joueur ne figure dans les fichiers suivis ni dans l’historique. Il lit les pseudos dans `parties/` au moment où il tourne et n’en contient aucun.

Garde-fou avant chaque push : `python verifier_pseudos.py --installer-hook` installe un hook git `pre-push` local (non versionné, à refaire après chaque clone) qui bloque le push si un pseudo se trouve dans ce qui part (fichiers, noms de fichiers, messages de commits et d’étiquettes), ou si `parties/` est absent.

Tests : `node --test tests/probabilites.test.js` (calculs de l’onglet Probabilités) et `python tests/test_holes.py` (trous du plateau).

## Organisation des fichiers

```
carcassonne-coach/
├── manifest.json               Extension Firefox (Manifest V3)
├── content-script.js           Lecture de la partie sur BGA, affichage des coups
├── content-style.css
├── background.js
├── engine_worker.js            Moteur dans le navigateur (Pyodide)
├── probabilites.js            Calculs de l’onglet Probabilités
├── popup.html, popup.js
├── images/                     Icônes de l’extension
├── pyodide/                    Pyodide 0.26.4 et NumPy
├── browser_coach.py            Point d’entrée du coach dans le navigateur
├── torch_free.py               Lecture du réseau sans PyTorch
├── verify_torch_free.py        Vérifie que torch_free.py donne le même résultat que PyTorch
├── carcassonne_engine.py       Règles, décompte, génération des coups, MCTS
├── neural_evaluator.py         Encodage du plateau, réseau, entraînement
├── server.py, start_server.bat Serveur local facultatif (port 5555)
├── selfplay.py, arena.py, bench_mcts.py   Auto-jeu, matchs, banc du MCTS
├── replay_bga.py, evaluate_model.py       Rejeu et évaluation
├── prix_meeple.py, prix_tuile_blocage.py, stats_tuiles.py,
│   virage_premier_tour.py, bayes_paysans.py                Analyses
├── diag_rotation.py, check_spots.py, calibrate_spots.py   Diagnostics
├── build_xpi.py                Fabrication du paquet de l’extension
├── verifier_pseudos.py         Contrôle des pseudos avant publication
├── tests/                      Tests de l’onglet Probabilités et des trous du plateau
├── updates.json                Mises à jour automatiques de l’extension
├── ed1_art_table.json          Table apprise : images 1re édition → types de tuiles
├── carcassonne_model.pt        Réseau courant (politique + valeur)
├── carcassonne_model.validation.json   Les parties de validation figées
├── parties/                    Parties exportées (non versionnées)
├── NOTES-VERIFICATEURS-MOZILLA.txt   Notes et procédure de test pour les vérificateurs Mozilla
├── CLAUDE.md                   Consignes pour l’assistant de développement (Claude Code)
├── requirements.txt
├── LICENSE
└── README.md
```

## Historique et état actuel

- **3.1.0** : onglet Probabilités (chapitres 1 à 3 du livre : familles, entropie, trous du plateau), en-tête synchronisé avec le replay.
- **3.0.4** : analyse strictement réservée aux parties terminées et aux replays, contrôlée aussi par le moteur ; réseau v33 avec tête valeur, entraîné sur 10 000 parties d’auto-jeu (**+69 Elo** contre le réseau v28 de la 3.0.2, 200 parties) ; réponse de l’adversaire ; tuile dessinée dans la bonne orientation.
- **3.0.2** : première version signée, tout le calcul dans le navigateur, interface français / anglais (retirée au profit de la 3.0.4).
- **v32** : MCTS classé par visites et prix du meeple ; l’accord avec les joueurs forts passe d’environ 13 % à 25 % en top 1.
- **v28** : politique à 4 rotations, contrôle de cohérence des rotations.

Mesures en arène : doubler le calcul ne rapporte qu’environ +23 Elo (non significatif), le facteur limitant est l’évaluation. Un second cycle d’auto-jeu (réseau v34) n’a pas fait mieux que la v33, qui reste le réseau de référence.

Données : 401 parties humaines rejouées à l’identique, dont des parties en tuiles 1re édition, et plusieurs milliers de parties d’auto-jeu.

## Limites connues

- **Début de partie** : avec beaucoup de tuiles restantes, les coups raisonnables sont proches et leur ordre tient en partie au hasard des simulations.
- **Plans à plusieurs coups** : partages, jonctions futures et blocages restent difficiles à voir au-delà de la réponse de l’adversaire.
- **Vitesse** : moteur en Python pur, plus lent encore dans le navigateur ; le serveur local va environ deux fois plus vite.
- **Variantes** : seul le jeu de base à 2 joueurs est pris en charge.

## Licence

Copyright © 2026 Jérémie (Jadiema) — Éditions Jadiema

Ce programme est un logiciel libre : vous pouvez le redistribuer et le modifier selon les termes de la GNU General Public License version 3, telle que publiée par la Free Software Foundation. Toute version modifiée que vous distribuez doit rester sous la même licence, avec son code source.

Ce programme est distribué dans l’espoir qu’il sera utile, mais sans aucune garantie, pas même la garantie implicite de qualité marchande ou d’adéquation à un usage particulier. Le texte complet de la licence figure dans le fichier `LICENSE`.
