// ============================================================
// 🏰 carcassonne-coach — Background Script v9
// ============================================================
// Deux moteurs, même interface pour le content script :
//   • serveur local (start_server.bat) s'il est lancé : le plus rapide ;
//   • sinon, le moteur intégré au navigateur (engine_worker.js), sans rien installer.
// L'analyse longue est suivie par polling côté content script (toutes les 2 s),
// ce qui garde aussi le script d'arrière-plan actif pendant le calcul.
// ============================================================

const SERVER_URL = "http://127.0.0.1:5555";

// v3.0.4 : position acceptée seulement si le content script a prouvé que la
// partie est terminée (replay ou état gameEnd de BGA). Interdit par défaut.
const FINISHED_PROOFS = ["replay-url", "replay-mode", "game-end"];
function isMarkedFinished(state) {
  const m = state && state._meta;
  return !!m && m.gameFinished === true && FINISHED_PROOFS.includes(m.finishedProof);
}
const NOT_FINISHED = "Analyse refusée : la position n’est pas marquée comme issue d’une partie terminée ou d’un replay.";
// Les erreurs portent un « code » que le content script traduit (FR/EN) ; le texte
// français reste en repli.
const engineError = (detail) => ({ error: "Moteur du navigateur : " + detail, code: "engine_failed", detail });

// Page de bienvenue locale : une seule fois, à la première installation.
// Jamais lors d'une mise à jour (reason "update") ni d'une mise à jour du navigateur.
// tabs.create ne demande aucune permission ; welcome.html est un fichier de l'extension.
browser.runtime.onInstalled.addListener(details => {
  if (details && details.reason === "install") {
    browser.tabs.create({ url: browser.runtime.getURL("welcome.html") });
  }
});

let worker = null;
const browserJobs = {};
const holeRequests = {};      // onglet « Probabilités » : réponse directe, sans polling

function ensureWorker() {
  if (worker) return worker;
  worker = new Worker(browser.runtime.getURL("engine_worker.js"));
  worker.onmessage = (e) => {
    const { id, ...rest } = e.data;
    if (holeRequests[id]) {
      holeRequests[id](rest.status === "done" ? { ok: true, data: rest }
                                              : { ok: false, error: rest.error, code: rest.code, detail: rest.detail });
      delete holeRequests[id];
      return;
    }
    browserJobs[id] = rest;
  };
  worker.onerror = (e) => {
    for (const id of Object.keys(browserJobs)) {
      if (browserJobs[id].status === "running") {
        browserJobs[id] = { status: "error", ...engineError(e.message || "?") };
      }
    }
    for (const id of Object.keys(holeRequests)) {
      holeRequests[id]({ ok: false, ...engineError(e.message || "?") });
      delete holeRequests[id];
    }
    worker = null;
  };
  return worker;
}

async function serverHealth() {
  try {
    const r = await fetch(SERVER_URL + "/health", { signal: AbortSignal.timeout(1500) });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

browser.runtime.onMessage.addListener((message, sender, sendResponse) => {

  if (message.type === "health") {
    serverHealth().then(data => {
      if (data) sendResponse({ ok: true, data: { ...data, engine: "serveur" } });
      else sendResponse({ ok: true, data: { status: "ok", engine: "navigateur" } });
    });
    return true;
  }

  if (message.type === "open-folder") {
    fetch(SERVER_URL + "/open-folder", { method: "POST", signal: AbortSignal.timeout(5000) })
      .then(r => r.json())
      .then(data => sendResponse(data))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  // Onglet « Probabilités » : trous réels du plateau (légalité du moteur, sans MCTS)
  if (message.type === "board-holes") {
    if (!isMarkedFinished(message.state)) {
      sendResponse({ ok: false, error: NOT_FINISHED, code: "not_finished" });
      return;
    }
    serverHealth().then(up => {
      if (up) {
        fetch(SERVER_URL + "/holes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: message.state, player: message.player, bag: message.bag }),
          signal: AbortSignal.timeout(15000),
        })
          .then(r => r.json())
          .then(data => sendResponse(data.status === "done" ? { ok: true, data }
                                                     : { ok: false, error: data.error, code: data.code, detail: data.detail }))
          .catch(err => sendResponse({ ok: false, error: err.message }));
        return;
      }
      const id = "h" + Math.random().toString(36).slice(2, 10);
      holeRequests[id] = sendResponse;
      ensureWorker().postMessage({ id, kind: "holes", state: message.state,
                                   player: message.player, bag: message.bag });
    });
    return true;
  }

  // Lancer une analyse (retour immédiat avec job_id)
  if (message.type === "start-analysis") {
    if (!isMarkedFinished(message.state)) {
      sendResponse({ ok: false, error: NOT_FINISHED, code: "not_finished" });
      return;
    }
    serverHealth().then(up => {
      if (up) {
        fetch(SERVER_URL + "/analyze?sims=" + message.sims + "&time=" + message.time + "&player=" + message.player, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(message.state),
          signal: AbortSignal.timeout(10000),
        })
          .then(r => r.json())
          .then(data => sendResponse({ ok: true, data }))
          .catch(err => sendResponse({ ok: false, error: err.message }));
        return;
      }
      const id = Math.random().toString(36).slice(2, 10);
      browserJobs[id] = { status: "running", started: Date.now(), time_limit: message.time };
      ensureWorker().postMessage({ id, state: message.state, sims: message.sims,
                                   time: message.time, player: message.player });
      sendResponse({ ok: true, data: { job_id: "nav-" + id, status: "running" } });
    });
    return true;
  }

  // Polling du résultat (retour immédiat)
  if (message.type === "poll-result") {
    if (message.jobId && message.jobId.startsWith("nav-")) {
      const job = browserJobs[message.jobId.slice(4)];
      if (!job) { sendResponse({ ok: true, data: { status: "not_found" } }); return; }
      if (job.status === "running") {
        sendResponse({ ok: true, data: { status: "running",
                                         elapsed: Math.round((Date.now() - job.started) / 100) / 10,
                                         time_limit: job.time_limit } });
      } else {
        sendResponse({ ok: true, data: job });
        if (job.status !== "running") delete browserJobs[message.jobId.slice(4)];
      }
      return;
    }
    fetch(SERVER_URL + "/result/" + message.jobId, { signal: AbortSignal.timeout(5000) })
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

});
