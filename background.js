// ============================================================
// 🏰 Carcassonne Coach — Background Script v8
// ============================================================
// Toutes les requêtes sont courtes (< 2s).
// L'analyse longue est gérée par polling côté content script.
// ============================================================

const SERVER_URL = "http://127.0.0.1:5555";

browser.runtime.onMessage.addListener((message, sender, sendResponse) => {

  if (message.type === "health") {
    fetch(SERVER_URL + "/health", { signal: AbortSignal.timeout(3000) })
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (message.type === "open-folder") {
    fetch(SERVER_URL + "/open-folder", { method: "POST", signal: AbortSignal.timeout(5000) })
      .then(r => r.json())
      .then(data => sendResponse(data))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  // Lancer une analyse (retour immédiat avec job_id)
  if (message.type === "start-analysis") {
    fetch(SERVER_URL + "/analyze?sims=" + message.sims + "&time=" + message.time + "&player=" + message.player, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.state),
      signal: AbortSignal.timeout(10000),
    })
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  // Polling du résultat (retour immédiat)
  if (message.type === "poll-result") {
    fetch(SERVER_URL + "/result/" + message.jobId, { signal: AbortSignal.timeout(5000) })
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

});
