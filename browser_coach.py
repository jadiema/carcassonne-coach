"""
🏰 carcassonne-coach — analyse dans le navigateur
=================================================
Exécuté par Pyodide (Python compilé en WebAssembly) dans l'extension Firefox :
même moteur, même MCTS et même réseau que le serveur local, sans Flask ni PyTorch.

Le réseau est calculé avec NumPy (torch_free.py), à partir du même fichier
carcassonne_model.pt. analyze() renvoie exactement le même résultat que
l'API /analyze → /result du serveur.
"""
import json
import time

import carcassonne_engine as E
import neural_evaluator as N
import torch_free as T


class NumpyNeuralEvaluator(N.NeuralEvaluator):
    """NeuralEvaluator dont la passe avant est faite en NumPy (pas de PyTorch)."""

    def __init__(self, model_path: str = "carcassonne_model.pt", use_value: bool = False):
        self.sd = T.load_state_dict(model_path)
        self.n_rot = int(self.sd["policy_conv2.weight"].shape[0])
        self.use_value = use_value
        self.cache = {}
        print(f"🧠 Réseau chargé (NumPy) : {model_path} — "
              + ("policy + value" if use_value else "policy seule (évaluation heuristique)"))

    def _forward(self, state_dict, player_idx):
        grid = N.encode_board(state_dict, player_idx)
        scalars = N.encode_scalar_features(state_dict, player_idx)
        return grid, T.forward(self.sd, grid, scalars)

    def evaluate(self, state_dict: dict, player_idx: int = 0) -> float:
        key = ("value", N._state_key(state_dict), player_idx)
        if key not in self.cache:
            if len(self.cache) > 50_000:
                self.cache.clear()
            _, (value, _) = self._forward(state_dict, player_idx)
            self.cache[key] = value
        return self.cache[key]

    def _policy_maps(self, state_dict: dict, player_idx: int = 0):
        board = state_dict.get("board", [])
        locs = [(t["location"]["x"], t["location"]["y"]) for t in board if t.get("location")]
        if not locs:
            return None
        cx = sum(x for x, _ in locs) / len(locs)
        cy = sum(y for _, y in locs) / len(locs)
        _, (_, policy) = self._forward(state_dict, player_idx)
        maps = policy.reshape(self.n_rot, N.NUM_CELLS)
        occupied = set(locs)
        free = {(x + dx, y + dy) for x, y in locs
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - occupied
        cells = {}
        for rx, ry in free:
            gx = int(rx - cx + N.GRID_CENTER)
            gy = int(ry - cy + N.GRID_CENTER)
            if 0 <= gx < N.GRID_SIZE and 0 <= gy < N.GRID_SIZE:
                cells[(rx, ry)] = gy * N.GRID_SIZE + gx
        return maps, cells


_evaluator = None

# v3.0.4 : analyse réservée aux parties terminées et aux replays (règle de BGA).
# Le content script inscrit la preuve dans _meta ; sans elle, refus.
FINISHED_PROOFS = ("replay-url", "replay-mode", "game-end")


def is_marked_finished(data) -> bool:
    meta = data.get("_meta") if isinstance(data, dict) else None
    return (isinstance(meta, dict) and meta.get("gameFinished") is True
            and meta.get("finishedProof") in FINISHED_PROOFS)


def load(model_path: str = "carcassonne_model.pt", use_value: bool = True) -> str:
    """Charge le réseau une fois pour toutes. Renvoie le mode utilisé.
    v3.0.3 : la tête value juge les positions (réseau v33, +69 Elo en match contre la v28)."""
    global _evaluator
    try:
        _evaluator = NumpyNeuralEvaluator(model_path, use_value=use_value)
        return "neural"
    except Exception as e:                      # pas de modèle : heuristique seule
        print(f"⚠️ Réseau non chargé ({e}) — heuristique seule")
        _evaluator = None
        return "heuristique"


# ------------------------------------------------------------
# Onglet « Probabilités » — trous réels du plateau (livre, chapitres 1 à 3)
# ------------------------------------------------------------
# Lettres A–X → type de tuile du moteur. Mêmes bords et blasons que
# LETTER_EDGES dans probabilites.js ; la description sert à départager les
# types de mêmes bords (I = ville 2 côtés adjacents séparés, N/M = coin relié).
_LETTER_TILE = {
    "A": ("FFRF", False, "Monastère + route"), "B": ("FFFF", False, "Monastère"),
    "C": ("CCCC", True, "Ville 4 côtés"),      "D": ("CRFR", False, "Ville + route traversante"),
    "E": ("CFFF", False, "Ville 1 côté"),      "F": ("FCFC", True, "Ville 2 côtés opposés"),
    "G": ("FCFC", False, "Ville 2 côtés opposés"), "H": ("CFCF", False, "Ville 2 côtés séparés"),
    "I": ("CFFC", False, "Ville 2 côtés adjacents séparés"),
    "J": ("CRRF", False, "Ville + virage"),    "K": ("CFRR", False, "Ville + virage"),   # convention du livre
    "L": ("CRRR", False, "Ville + carrefour"),
    "M": ("CFFC", True, "Ville angle"),        "N": ("CFFC", False, "Ville angle"),
    "O": ("CRRC", True, "Ville angle + route"), "P": ("CRRC", False, "Ville angle + route"),
    "Q": ("CCFC", True, "Ville 3 côtés"),      "R": ("CCFC", False, "Ville 3 côtés"),
    "S": ("CCRC", True, "Ville 3 côtés + route"), "T": ("CCRC", False, "Ville 3 côtés + route"),
    "U": ("RFRF", False, "Route droite"),      "V": ("FFRR", False, "Virage route"),
    "W": ("FRRR", False, "Carrefour 3 routes"), "X": ("RRRR", False, "Carrefour 4 routes"),
}
_LETTER_TYPE_CACHE = {}


def letter_tile_type(letter: str):
    if letter not in _LETTER_TYPE_CACHE:
        edges, shield, desc = _LETTER_TILE[letter]
        tt = E._find_tile_type(edges, shield, desc)
        if tt is None or tt.edges != edges or tt.shield != shield:
            raise ValueError(f"type de tuile introuvable pour {letter}")
        _LETTER_TYPE_CACHE[letter] = tt
    return _LETTER_TYPE_CACHE[letter]


def _side_half_sides(side: int):
    """Demi-côtés de champ portés par un bord (7,0 → 0 ; 1,2 → 1 ; 3,4 → 2 ; 5,6 → 3)."""
    return ((2 * side - 1) % 8, 2 * side)


def board_holes(data: dict, player_idx: int, bag: dict) -> dict:
    """Cases vides qui touchent une structure ouverte du joueur (ville, route, pré
    où il a un partisan) ou une ville adverse qu'il peut rejoindre. Pour chacune,
    n = nombre de tuiles du sac qui peuvent y être posées légalement (au moins
    une rotation valide, GameState.can_place du moteur). bag = {lettre: effectif}
    calculé par probabilites.js : le même sac que les familles."""
    if not is_marked_finished(data):
        return {"status": "error",
                "code": "not_finished",
                "error": "Analyse refusée : partie non terminée (ni replay ni fin de partie prouvée)."}
    state = E.GameState.from_json(data)
    return holes_for_state(state, int(player_idx), bag)


def _merge_letters(state, x, y, bag, my_cities, opp_cities) -> list:
    """Types du sac qui, posés légalement en (x, y) dans au moins une rotation,
    relient par une même pièce de ville un bord tourné vers une de mes villes
    et un bord tourné vers une ville adverse (distincte)."""
    pairs = [(dm, do) for mk, mds in my_cities.items() for ok, ods in opp_cities.items()
             if mk != ok for dm in mds for do in ods]
    if not pairs:
        return []
    out = []
    for l in bag:
        tt = letter_tile_type(l)
        for r in range(4):
            if not state.can_place(tt, x, y, r):
                continue
            groups = E.rotate_connected_city(tt.connected_city, r)
            if any(dm in g and do in g for g in groups for dm, do in pairs):
                out.append(l)
                break
    return out


def holes_for_state(state, me: int, bag: dict) -> dict:
    """Cœur du calcul de board_holes, sur un GameState déjà chargé (testable)."""
    state.valid_positions = None            # toutes les cases vides, pas seulement celles de la tuile en main
    bag = {l: int(c) for l, c in (bag or {}).items() if l in _LETTER_TILE and int(c) > 0}
    N = sum(bag.values())

    holes = []
    for (x, y) in sorted(state.get_open_positions()):
        kinds = set()
        my_cities, opp_cities = {}, {}        # ville (ensemble de ses côtés) → directions depuis la case
        for d, adj in state.neighbors(x, y).items():
            if adj is None:
                continue
            side = E.OPPOSITE[d]                 # côté de la tuile voisine tourné vers la case
            ax, ay = adj.x, adj.y
            e = adj.edge(side)
            if e == "C":
                res = state._trace_structure(ax, ay, side, "city")
                owners = res["meeples"]
                if owners.get(me):
                    kinds.add("city")
                    my_cities.setdefault(res["sides"], set()).add(d)
                elif owners:                      # occupée par l'adversaire seul
                    opp_cities.setdefault(res["sides"], set()).add(d)
            elif e == "R":
                if state._trace_structure(ax, ay, side, "road")["meeples"].get(me):
                    kinds.add("road")
            for hs in _side_half_sides(side):
                if state._trace_field(ax, ay, hs)["meeples"].get(me):
                    kinds.add("field")
                    break
        # Ville adverse « que je peux rejoindre » (livre) : la case touche une
        # ville adverse ET une de MES villes occupées, deux villes distinctes,
        # et au moins une tuile du sac peut s'y poser en les reliant (fusion).
        # Un partisan en réserve ne suffit pas : on ne peut pas poser de
        # partisan dans une ville déjà occupée.
        merge = _merge_letters(state, x, y, bag, my_cities, opp_cities) if my_cities and opp_cities else []
        if merge:
            kinds.add("opp_city")
        if not kinds:
            continue
        fits = [l for l in bag
                if any(state.can_place(letter_tile_type(l), x, y, r) for r in range(4))]
        if merge:
            # Case de fusion : n = tuiles qui relient réellement les deux villes ;
            # m = autres tuiles légales ici, qui fermeraient cette possibilité.
            others = [l for l in fits if l not in merge]
            holes.append({"x": x, "y": y, "kinds": sorted(kinds), "fusion": True,
                          "fits": sorted(merge), "others": sorted(others),
                          "n": sum(bag[l] for l in merge), "m": sum(bag[l] for l in others), "N": N})
            continue
        holes.append({"x": x, "y": y, "kinds": sorted(kinds), "fits": sorted(fits),
                      "n": sum(bag[l] for l in fits), "N": N})
    holes.sort(key=lambda h: (h["n"], h["y"], h["x"]))
    return {"status": "done", "holes": holes, "N": N}


def holes_json(state_json: str, player_idx: int, bag_json: str) -> str:
    """Point d'entrée du worker (Pyodide)."""
    return json.dumps(board_holes(json.loads(state_json), player_idx, json.loads(bag_json)))


def analyze(state_json: str, sims: int = 1000, time_limit: float = 10.0, player_idx: int = 0) -> str:
    """Même entrée et même sortie que le serveur (/analyze puis /result)."""
    data = json.loads(state_json)
    if not is_marked_finished(data):
        return json.dumps({"status": "error",
                           "code": "not_finished",
                           "error": "Analyse refusée : partie non terminée (ni replay ni fin de partie prouvée)."})
    state = E.GameState.from_json(data)
    if not state.current_tile:
        return json.dumps({"status": "error", "code": "no_tile", "error": "Pas de tuile en main détectée"})

    info = {
        "players": [{"name": state.player_names[i], "score": state.scores[i],
                     "meeples": state.meeples[i]} for i in range(state.num_players)],
        "tilesPlaced": len(state.board),
        "tilesRemaining": len(state.draw_pile),
        "currentTile": state.current_tile.edges,
        "activePlayer": state.player_names[player_idx],
    }
    start = time.time()
    results = E.mcts_search(state, state.current_tile, player_idx,
                            simulations=int(sims), time_limit=0.7 * float(time_limit),
                            neural_eval=_evaluator)
    # v3.0.3 : réponse de l'adversaire (Expectimax sur deux coups) pour les meilleurs coups
    results = E.expectimax_rerank(state, state.current_tile, player_idx, results,
                                  neural_eval=_evaluator, top_n=10,
                                  time_limit=max(1.5, 0.3 * float(time_limit)), leaf="mix")
    elapsed = time.time() - start
    moves = [{"x": r["x"], "y": r["y"], "rotation": r["rotation"], "edges": r["edges"],
              "meeple": r["meeple"], "winRate": r.get("expectimax", r["score"]), "visits": r["visits"],
              "meepleAt": E.meeple_anchor(state.current_tile, r["rotation"], r["meeple"]),
              "desc": r["desc"]} for r in results[:5]]
    return json.dumps({"status": "done", "result": {
        "info": info,
        "moves": moves,
        "stats": {"simulations": sum(r["visits"] for r in results),
                  "elapsed": round(elapsed, 1),
                  "totalMoves": len(results),
                  "engine": "navigateur"},
    }})
