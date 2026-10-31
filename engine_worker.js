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
  const { id, state, sims, time, player } = event.data;
  try {
    if (!ready) ready = init();
    const mode = await ready;
    const out = JSON.parse(coach.analyze(JSON.stringify(state), sims, time, player));
    self.postMessage({ id, mode, ...out });
  } catch (err) {
    self.postMessage({ id, status: "error", error: "Moteur du navigateur : " + (err && err.message ? err.message : String(err)) });
  }
};
