"""
Vérifie que la passe avant NumPy (torch_free.py) donne exactement les mêmes
résultats que PyTorch sur des positions réelles.
Usage (dans le dossier du coach, PyTorch installé) :  python verify_torch_free.py parties
"""
import sys, json, random
from pathlib import Path
import numpy as np
import torch
import carcassonne_engine as E, neural_evaluator as N, replay_bga as R, torch_free as T

sd = T.load_state_dict("carcassonne_model.pt")
net = N.NeuralEvaluator("carcassonne_model.pt")
files = sorted(Path(sys.argv[1]).glob("*.json"))
random.seed(0); random.shuffle(files)
worst_v = worst_p = 0.0; n = 0
for f in files[:5]:
    data = json.load(open(f, encoding="utf-8"))
    if not data.get("rawLog"):
        continue
    _, states, _ = R.replay(data)
    for state, _, mover in states[::7]:
        d = E._state_to_dict(state, mover)
        grid, sc = N.encode_board(d, mover), N.encode_scalar_features(d, mover)
        v_np, p_np = T.forward(sd, grid, sc)
        with torch.no_grad():
            v_t, p_t = net.model(torch.from_numpy(grid[None]).float(), torch.from_numpy(sc[None]).float())
        worst_v = max(worst_v, abs(v_np - float(v_t[0, 0])))
        worst_p = max(worst_p, float(np.abs(p_np - p_t[0].numpy()).max()))
        n += 1
print(f"{n} positions comparées — écart max value {worst_v:.2e}, policy {worst_p:.2e}")
print("✅ identique (aux arrondis près)" if worst_v < 1e-4 and worst_p < 1e-4 else "❌ écart anormal")
