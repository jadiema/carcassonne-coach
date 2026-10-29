# 🏰 Carcassonne Coach

Un coach d’intelligence artificielle pour **Carcassonne** (jeu de base, 2 joueurs) sur **Board Game Arena** (BGA).
Une extension Firefox lit la partie en cours ; un serveur local cherche les meilleurs coups avec une **recherche arborescente de Monte-Carlo (MCTS)** guidée par un **réseau de neurones** entraîné sur des parties de joueurs forts ; les meilleurs coups s’affichent sur le plateau.

> Projet personnel, dépôt privé. Voir [LICENSE](LICENSE).

---

## Sommaire

1. [Fonctionnement](#fonctionnement)
2. [Installation](#installation)
3. [Utilisation sur Board Game Arena](#utilisation-sur-board-game-arena)
4. [Constituer les données d’entraînement](#constituer-les-données-dentraînement)
5. [Entraîner et évaluer le réseau](#entraîner-et-évaluer-le-réseau)
6. [Scripts d’analyse](#scripts-danalyse)
7. [Réglages](#réglages)
8. [Organisation des fichiers](#organisation-des-fichiers)
9. [Historique et état actuel](#historique-et-état-actuel)
10. [Limites connues](#limites-connues)

---

## Fonctionnement

```
 Firefox (boardgamearena.com)                     Ordinateur local
┌──────────────────────────────┐   HTTP    ┌────────────────────────────────────┐
│ content-script.js            │ ───────▶  │ server.py  (Flask, port 5555)       │
│  · lit plateau, tuile en     │  /analyze │   └─ carcassonne_engine.py          │
│    main, cases libres, sac   │           │        · règles, décompte           │
│  · affiche les coups         │ ◀───────  │        · MCTS (UCB1 / PUCT)         │
│    recommandés               │  /result  │   └─ neural_evaluator.py            │
└──────────────────────────────┘           │        · réseau valeur + politique  │
                                           └────────────────────────────────────┘
```

1. **L’extension** (`manifest.json`, `content-script.js`, `background.js`, `popup.html`) lit la position sur BGA : plateau, tuile en main, cases libres, tuiles restantes, scores et meeples.
2. **Le serveur** (`server.py`) reçoit la position, lance l’analyse dans un fil séparé et renvoie un identifiant ; l’extension interroge ensuite le résultat (mode asynchrone).
3. **Le moteur** (`carcassonne_engine.py`) génère les coups légaux, les filtre avec une heuristique, puis lance le MCTS pendant le temps choisi (≈ 2 600 parties d’essai en 15 s).
4. **Le réseau** (`neural_evaluator.py`) fournit :
   - une **politique** : une probabilité pour chaque (case, rotation), qui oriente l’exploration et peut repêcher des coups écartés par l’heuristique ;
   - une **valeur** : la chance de victoire (désactivée par défaut, voir [Limites](#limites-connues)).

---

## Installation

### Prérequis

- **Python 3.12** (testé sous Windows 10/11)
- **Firefox 109 ou plus récent**
- Git (pour cloner le dépôt)

### Dépendances Python

```bash
pip install -r requirements.txt
```

PyTorch en version CPU suffit. Si l’installation de `torch` échoue, suivre les instructions de [pytorch.org](https://pytorch.org/get-started/locally/).
Sans PyTorch, le serveur fonctionne quand même, avec l’heuristique seule.

### Lancer le serveur

Sous Windows : double-cliquer sur **`start_server.bat`** (installe Flask si besoin puis lance le serveur).
Ou en ligne de commande :

```bash
python server.py
```

Le serveur écoute sur `http://localhost:5555`. Au démarrage, il doit afficher `Réseau de neurones chargé avec succès` si `carcassonne_model.pt` est présent.

### Installer l’extension Firefox

L’extension n’est pas signée : elle s’installe en mode temporaire.

1. Ouvrir `about:debugging#/runtime/this-firefox`
2. **Charger un module complémentaire temporaire…**
3. Choisir le fichier `manifest.json` du dépôt

L’extension est à recharger après chaque redémarrage de Firefox (bouton **Actualiser** dans `about:debugging` après une modification des fichiers).

---

## Utilisation sur Board Game Arena

1. Lancer le serveur, ouvrir une partie de Carcassonne sur BGA.
2. Cliquer sur le bouton **🏰** ajouté par l’extension, choisir son joueur et le temps d’analyse (de 5 secondes à 10 minutes).
3. Lancer l’analyse : les meilleurs coups apparaissent en surbrillance sur le plateau, avec leur taux de victoire estimé.

Le panneau signale qu’en début de partie (plus de 30 tuiles restantes) les écarts entre coups sont souvent dans le bruit de la simulation.

---

## Constituer les données d’entraînement

1. Sur BGA, ouvrir une partie **terminée** (de préférence entre joueurs forts) et cliquer sur le bouton **JSON** de l’extension.
2. Ranger les fichiers dans le dossier **`parties/`**.
3. Vérifier que chaque partie se rejoue exactement :

```bash
python replay_bga.py parties
```

Chaque partie doit afficher `✅ … rejouée à l’identique` : le rejeu refait tous les coups et compare les scores finaux à ceux de BGA. Les parties en échec sont écartées de l’entraînement.

**Parties en tuiles « 1re édition ».** Dans les replays, BGA affiche l’édition choisie par les joueurs ; l’extension ne reconnaît pas ces images. `replay_bga.py` retrouve alors les tuiles par déduction et **apprend** la correspondance image → type dans `ed1_art_table.json`. Relancer le contrôle une seconde fois permet souvent de rejouer les parties qui avaient échoué.

> Le contenu de `parties/` n’est **pas versionné** (voir `.gitignore`) : ce sont les parties d’autres joueurs, et le dossier pèse plusieurs dizaines de Mo. Seul `carcassonne_model.validation.json` (liste des 15 parties de validation) est suivi.

---

## Entraîner et évaluer le réseau

### Entraîner

```bash
python neural_evaluator.py train parties 30
```

- 30 époques au maximum, arrêt automatique après 4 époques sans progrès en validation ;
- la **validation est figée** : les mêmes 15 parties (`carcassonne_model.validation.json`) servent d’examen d’un entraînement à l’autre ; `--new-split` en tire de nouvelles ;
- chaque plateau est présenté sous ses **4 rotations** (augmentation des données) ;
- le meilleur modèle (politique) est enregistré dans `carcassonne_model.pt`, la meilleure tête valeur dans `carcassonne_model.value.pt`.

Options : `--new-split` (nouveau tirage de validation), `--value-joint` (la valeur influence aussi le tronc commun), `--legacy` (ancien format).

Au début de l’entraînement, vérifier la ligne **« Contrôle des rotations »** : aucune rotation ne doit rester « sans équivalent ».

Mémoire : environ 7 Go pour 400 parties. Fermer les autres applications pendant l’entraînement.

### Évaluer

```bash
python evaluate_model.py parties
```

Rejoue les parties de validation et mesure, sur chaque position, si le coup réellement joué par le joueur fort figure dans le top 1 / top 3 de chaque méthode (hasard, heuristique, réseau), puis si la valeur prédit le vainqueur mieux que « celui qui mène gagne ».

### Résultats actuels (401 parties, modèle v28)

| Méthode (coup complet : case + rotation) | Top 1 | Top 3 |
| --- | --- | --- |
| Hasard parmi les coups légaux | 6,4 % | 19,0 % |
| Heuristique du moteur | 25,8 % | 42,7 % |
| **Réseau, politique (case + rotation)** | **35,1 %** | **61,9 %** |
| Réseau, case seule | 41,9 % | 71,4 % |

---

## Scripts d’analyse

| Script | Rôle | Commande |
| --- | --- | --- |
| `replay_bga.py` | Rejoue les parties et vérifie les scores finaux ; apprend les images de la 1re édition | `python replay_bga.py parties` |
| `evaluate_model.py` | Compare réseau, heuristique et hasard sur les parties de validation | `python evaluate_model.py parties` |
| `prix_meeple.py` | Suit chaque meeple de sa pose à son retour : rendement λ (points par tour bloqué) selon la phase, la structure et le stock de meeples | `python prix_meeple.py parties` |
| `bayes_paysans.py` | Cherche deux styles de joueurs (agressif / prudent) dans les prés par un mélange de lois binomiales (algorithme EM) | `python bayes_paysans.py parties` |
| `diag_rotation.py` | Diagnostic de la convention de rotation de l’augmentation des données | `python diag_rotation.py parties` |
| `check_spots.py` | Vérifie la table des emplacements de meeples BGA | `python check_spots.py parties` |
| `calibrate_spots.py` | Recherche l’affectation des paysans ambigus quand seul le décompte final diffère de BGA | `python calibrate_spots.py parties` |

Les fichiers produits (`prix_meeple.csv`, `prix_meeple.png`, `bayes_paysans.csv`) ne sont pas versionnés.

---

## Réglages

| Réglage | Valeurs | Effet |
| --- | --- | --- |
| Variable d’environnement `CARCASSONNE_POLICY` | `rotation` (défaut) / `case` | Politique du réseau par (case, rotation), ou par case seule comme avant la v28 |
| Temps d’analyse | 5 s à 10 min (panneau de l’extension) | ≈ 2 600 parties d’essai en 15 s, ≈ 11 000 en 1 min |

Exemple sous PowerShell, pour comparer avec l’ancien mode :

```powershell
$env:CARCASSONNE_POLICY="case"; python server.py
```

---

## Organisation des fichiers

```
carcassonne-coach/
├── manifest.json               Extension Firefox (Manifest V3)
├── content-script.js           Lecture de la partie sur BGA, affichage des coups
├── content-style.css
├── background.js
├── popup.html
├── images/                     Icônes de l’extension
├── server.py                   Serveur Flask local (port 5555, mode asynchrone)
├── start_server.bat            Lanceur Windows du serveur
├── carcassonne_engine.py       Règles, décompte, génération des coups, MCTS
├── neural_evaluator.py         Encodage du plateau (24 calques 25×25), réseau, entraînement
├── replay_bga.py               Rejeu exact des parties BGA
├── evaluate_model.py           Évaluation du réseau
├── prix_meeple.py              Analyse du prix d’un meeple
├── bayes_paysans.py            Analyse bayésienne des styles de joueurs
├── diag_rotation.py, check_spots.py, calibrate_spots.py   Outils de diagnostic
├── ed1_art_table.json          Table apprise : images 1re édition → types de tuiles
├── carcassonne_model.pt        Modèle courant (meilleure politique en validation)
├── carcassonne_model.value.pt  Meilleure tête valeur
├── carcassonne_model.validation.json   Les 15 parties de validation figées
├── parties/                    Parties exportées (non versionnées)
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Historique et état actuel

- **Réseau** : tronc commun de 4 couches convolutives (loupes 3×3) sur 24 calques de 25×25 cases + 9 nombres, environ 530 000 poids.
  - **v27** : tête valeur compacte (≈ 3 000 poids, dropout), gradient de la valeur arrêté avant le tronc, exemples pondérés par l’avancement de la partie, validation figée.
  - **v28** : politique à **4 rotations** (une carte par rotation, 2 500 notes par position), cibles compactes, contrôle de cohérence des rotations, rotations équivalentes des tuiles symétriques ramenées à celle du moteur.
- **Moteur** : politique par (case, rotation) dans le MCTS, prior partagé entre les options de meeple d’un même placement, **repêchage** par le réseau des coups écartés par l’heuristique, exclusion « catastrophique » fondée sur le bilan (ce que le coup donne moins ce qu’il rapporte).
- **Données** : 401 parties rejouées à l’identique, dont des parties en tuiles 1re édition.
- **Serveur** : v8, mode asynchrone (`/analyze` puis `/result/<job_id>`), `/health`.

---

## Limites connues

- **Valeur** : la tête valeur ne prédit pas le vainqueur mieux que « celui qui mène gagne » ; elle est désactivée (`use_value=False`) et le MCTS garde l’évaluation heuristique.
- **Début de partie** : avec plus de 30 tuiles restantes, les coups raisonnables obtiennent tous environ 53 % et l’ordre tient au hasard des simulations.
- **Plans à plusieurs coups** : partages, jonctions futures et blocages sont mal vus par des parties d’essai jouées au hasard.
- **Vitesse** : moteur en Python pur, environ cent fois plus lent qu’un moteur compilé.
- **Données** : le réseau progresse d’environ un point par lot de parties ajouté ; un vrai saut demanderait des milliers de parties ou de l’auto-apprentissage.
- **Extension** : identifiant temporaire (`carcassonne-coach@votre-email.com`), à remplacer avant toute publication.
