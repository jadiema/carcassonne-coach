"""
🏰 Carcassonne Coach — Serveur local v8
=========================================
Mode asynchrone : /analyze lance un thread et retourne un job_id,
/result/<job_id> permet de récupérer le résultat par polling.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from carcassonne_engine import GameState, mcts_search, _evaluate_position
import carcassonne_engine as E
import time
import threading
import uuid
import os

app = Flask(__name__)
# Seule l'extension peut appeler le serveur local : une page web quelconque
# ouverte dans le navigateur ne doit pas pouvoir lancer d'analyse ni ouvrir
# le dossier du coach (CORS seul n'empêche pas l'exécution d'une requête).
_EXT_ORIGINS = ("moz-extension://", "chrome-extension://")
CORS(app, origins=[r"moz-extension://.*", r"chrome-extension://.*"])


@app.before_request
def _only_extension():
    origin = request.headers.get("Origin")
    if origin and not origin.startswith(_EXT_ORIGINS):
        return jsonify({"error": "origine non autorisée"}), 403

# v3.0.4 : analyse réservée aux parties terminées et aux replays (règle de BGA).
# Le content script inscrit la preuve dans _meta ; sans elle, refus (interdit par défaut).
FINISHED_PROOFS = ("replay-url", "replay-mode", "game-end")


def is_marked_finished(data) -> bool:
    meta = data.get("_meta") if isinstance(data, dict) else None
    return (isinstance(meta, dict) and meta.get("gameFinished") is True
            and meta.get("finishedProof") in FINISHED_PROOFS)


# Stockage des jobs en mémoire
jobs = {}

# Chargement optionnel du réseau de neurones
neural_evaluator = None
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "carcassonne_model.pt")
if os.path.exists(MODEL_PATH):
    try:
        from neural_evaluator import NeuralEvaluator
        neural_evaluator = NeuralEvaluator(MODEL_PATH, use_value=True)   # v3.0.3 : tête value (réseau v33)
        print("🧠 Réseau de neurones chargé avec succès")
    except Exception as e:
        print(f"⚠️ Réseau non chargé: {e}")
        print("   Le serveur utilisera l'heuristique classique")
else:
    print("ℹ️ Pas de modèle neuronal trouvé (carcassonne_model.pt)")
    print("   Utilisez: python neural_evaluator.py train <dossier_parties>")


@app.route("/health", methods=["GET"])
def health():
    mode = "neural" if neural_evaluator else "heuristic"
    return jsonify({"status": "ok", "service": "Carcassonne Coach v10", "mode": mode})


@app.route("/open-folder", methods=["POST"])
def open_folder():
    import subprocess, os
    folder = os.path.dirname(os.path.abspath(__file__))
    print(f"📂 Ouverture du dossier: {folder}")
    try:
        if os.name == 'nt':
            subprocess.Popen(["explorer", os.path.normpath(folder)])
        elif os.name == 'posix':
            subprocess.Popen(["xdg-open", folder])
        return jsonify({"ok": True, "folder": folder})
    except Exception as e:
        print(f"❌ Erreur ouverture dossier: {e}")
        return jsonify({"ok": False, "error": str(e)})


@app.route("/holes", methods=["POST"])
def holes():
    """Onglet « Probabilités » : trous réels du plateau (calcul rapide, sans MCTS)."""
    from browser_coach import board_holes
    payload = request.get_json(silent=True) or {}
    data = payload.get("state")
    if not isinstance(data, dict) or not is_marked_finished(data):
        return jsonify({"error": "Analyse refusée : partie non terminée (ni replay ni fin de partie prouvée)."}), 403
    try:
        return jsonify(board_holes(data, int(payload.get("player", 0)), payload.get("bag") or {}))
    except Exception as e:
        return jsonify({"status": "error", "error": f"Erreur de calcul : {e}"}), 400


@app.route("/analyze", methods=["POST"])
def analyze():
    """Lance l'analyse dans un thread et retourne immédiatement un job_id."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON invalide"}), 400
    if not is_marked_finished(data):
        return jsonify({"error": "Analyse refusée : partie non terminée (ni replay ni fin de partie prouvée)."}), 403

    sims = request.args.get("sims", 1000, type=int)
    time_limit = request.args.get("time", 10, type=float)
    player_idx = request.args.get("player", 0, type=int)

    try:
        state = GameState.from_json(data)
    except Exception as e:
        return jsonify({"error": f"Erreur de chargement: {str(e)}"}), 400

    if not state.current_tile:
        return jsonify({"error": "Pas de tuile en main détectée"}), 400

    # Log diagnostic
    print(f"\n📊 Position chargée: {len(state.board)} tuiles, {len(state.draw_pile)} en pioche")
    print(f"   Tuile en main: {state.current_tile.edges} (connected_city={state.current_tile.connected_city})")
    print(f"   Joueur analysé: {state.player_names[player_idx]} (index {player_idx})")
    # Meeples sur le plateau
    for (x,y), t in state.board.items():
        if t.meeple_player is not None:
            print(f"   🏠 ({x},{y}) {t.edges} — {state.player_names[t.meeple_player]} meeple={t.meeple_spot}")
    free_places = data.get("freePlaces", None)
    if isinstance(free_places, list) and len(free_places) > 0 and isinstance(free_places[0], dict):
        print(f"   freePlaces reçues: {len(free_places)} positions")
    if state.valid_positions:
        print(f"   valid_positions chargées: {len(state.valid_positions)}")
    legal = state.get_legal_placements(state.current_tile)
    print(f"   Placements légaux: {len(legal)}")

    # Créer le job
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "running", "started": time.time(), "time_limit": time_limit}

    # Infos de base
    info = {
        "players": [
            {"name": state.player_names[i], "score": state.scores[i], "meeples": state.meeples[i]}
            for i in range(state.num_players)
        ],
        "tilesPlaced": len(state.board),
        "tilesRemaining": len(state.draw_pile),
        "currentTile": state.current_tile.edges,
        "activePlayer": state.player_names[player_idx],
    }

    # Lancer dans un thread
    def run_analysis():
        try:
            start = time.time()
            results = mcts_search(state, state.current_tile, player_idx,
                                  simulations=sims, time_limit=0.7 * time_limit,
                                  neural_eval=neural_evaluator)
            # v3.0.3 : réponse de l'adversaire (Expectimax sur deux coups)
            results = E.expectimax_rerank(state, state.current_tile, player_idx, results,
                                          neural_eval=neural_evaluator, top_n=10,
                                          time_limit=max(1.5, 0.3 * float(time_limit)), leaf="mix")
            elapsed = time.time() - start

            top_moves = []
            for r in results[:5]:
                top_moves.append({
                    "x": r["x"], "y": r["y"], "rotation": r["rotation"],
                    "edges": r["edges"], "meeple": r["meeple"],
                    "meepleAt": E.meeple_anchor(state.current_tile, r["rotation"], r["meeple"]),
                    "winRate": r.get("expectimax", r["score"]), "visits": r["visits"], "desc": r["desc"],
                })

            jobs[job_id] = {
                "status": "done",
                "result": {
                    "info": info,
                    "moves": top_moves,
                    "stats": {
                        "simulations": sum(r["visits"] for r in results),
                        "elapsed": round(elapsed, 1),
                        "totalMoves": len(results),
                    },
                }
            }
            print(f"   ✅ Job {job_id} terminé en {elapsed:.1f}s")
        except Exception as e:
            jobs[job_id] = {"status": "error", "error": str(e)}
            print(f"   ❌ Job {job_id} erreur: {e}")

    thread = threading.Thread(target=run_analysis, daemon=True)
    thread.start()

    print(f"   🚀 Job {job_id} lancé ({time_limit}s)")
    return jsonify({"job_id": job_id, "status": "running"})


@app.route("/result/<job_id>", methods=["GET"])
def get_result(job_id):
    """Récupère le résultat d'un job. Polling par le client."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404

    if job["status"] == "running":
        elapsed = time.time() - job.get("started", 0)
        return jsonify({"status": "running", "elapsed": round(elapsed, 1),
                        "time_limit": job.get("time_limit", 0)})

    if job["status"] == "error":
        result = jsonify({"status": "error", "error": job["error"]})
        del jobs[job_id]  # Nettoyer
        return result

    if job["status"] == "done":
        result = jsonify({"status": "done", "result": job["result"]})
        del jobs[job_id]  # Nettoyer
        return result

    return jsonify({"status": "unknown"}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("🏰 Carcassonne Coach — Serveur local v8")
    print("=" * 50)
    print("  Adresse: http://localhost:5555")
    print("  Mode: asynchrone (polling)")
    print("=" * 50)

    try:
        from waitress import serve
        print("  Serveur: waitress")
        serve(app, host="127.0.0.1", port=5555, threads=4)
    except ImportError:
        print("  Serveur: Flask (threaded)")
        app.run(host="127.0.0.1", port=5555, debug=False, threaded=True)
