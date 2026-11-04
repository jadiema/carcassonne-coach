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


def analyze(state_json: str, sims: int = 1000, time_limit: float = 10.0, player_idx: int = 0) -> str:
    """Même entrée et même sortie que le serveur (/analyze puis /result)."""
    data = json.loads(state_json)
    state = E.GameState.from_json(data)
    if not state.current_tile:
        return json.dumps({"status": "error", "error": "Pas de tuile en main détectée"})

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
