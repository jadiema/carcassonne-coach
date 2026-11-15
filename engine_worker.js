// ============================================================
// 🏰 carcassonne-coach — calcul dans le navigateur (Web Worker)
// ============================================================
// Héberge Python (Pyodide, WebAssembly) et le moteur du coach : même moteur,
// même MCTS et même réseau que le serveur local, sans rien installer.
// Le premier lancement charge Python, NumPy et le réseau (quelques secondes).
// ============================================================

importScripts("pyodide/pyodide.js");

const PY_FILES = ["carcassonne_engine.py", "neural_evaluator.py", "torch_free.py", "browser_coach.py"];
let ready = null;
let coach = null;

async function init() {
  const t0 = Date.now();
  const py = await loadPyodide({ indexURL: new URL("pyodide/", self.location.href).href });
  await py.loadPackage("numpy");
  for (const f of PY_FILES) {
    py.FS.writeFile(f, await (await fetch(f)).text());
  }
  const model = await (await fetch("carcassonne_model.pt")).arrayBuffer();
  py.FS.writeFile("carcassonne_model.pt", new Uint8Array(model));
  py.runPython("import sys; sys.path.insert(0, '.')");
  coach = py.pyimport("browser_coach");
  const mode = coach.load("carcassonne_model.pt");
  console.log(`🏰 Moteur prêt dans le navigateur (${mode}) en ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  return mode;
}

self.onmessage = async (event) => {
  const { id, kind, state, sims, time, player, bag } = event.data;
  // v3.0.4 : refus d'une position non marquée comme terminée (avant même de charger Python)
  const m = state && state._meta;
  if (!m || m.gameFinished !== true || !["replay-url", "replay-mode", "game-end"].includes(m.finishedProof)) {
    self.postMessage({ id, status: "error", error: "Analyse refusée : partie non terminée (ni replay ni fin de partie prouvée)." });
    return;
  }
  try {
    if (!ready) ready = init();
    const mode = await ready;
    if (kind === "holes") {
      // Onglet « Probabilités » : trous du plateau (légalité du moteur, sans MCTS)
      const out = JSON.parse(coach.holes_json(JSON.stringify(state), player, JSON.stringify(bag || {})));
      self.postMessage({ id, kind, ...out });
      return;
    }
    const out = JSON.parse(coach.analyze(JSON.stringify(state), sims, time, player));
    self.postMessage({ id, mode, ...out });
  } catch (err) {
    self.postMessage({ id, kind, status: "error", error: "Moteur du navigateur : " + (err && err.message ? err.message : String(err)) });
  }
};
