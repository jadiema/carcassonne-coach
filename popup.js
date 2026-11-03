// Fenêtre de l'icône : français si le navigateur est en français, anglais sinon.
const lang = (navigator.language || "fr").toLowerCase().startsWith("fr") ? "fr" : "en";
document.documentElement.lang = lang;
for (const el of document.querySelectorAll("[data-fr]")) {
  el.innerHTML = el.dataset[lang];
}
