// Fenêtre de l'icône : français si le navigateur est en français, anglais sinon.
const lang = (navigator.language || "fr").toLowerCase().startsWith("fr") ? "fr" : "en";
document.documentElement.lang = lang;
for (const el of document.querySelectorAll("[data-fr]")) {
  el.innerHTML = el.dataset[lang];
}

// Couverture du livre (édition de la langue affichée) : masquée si le fichier manque
const cover = document.getElementById("cover");
if (cover) {
  const hide = () => { cover.style.display = "none"; };
  cover.addEventListener("error", hide);
  if (typeof CarcLivre !== "undefined") {
    cover.alt = CarcLivre.titreComplet(lang);
    cover.src = CarcLivre.couverture(lang);
  }
  if (cover.complete && !cover.naturalWidth) hide();
}

// Bouton « Découvrir le livre » (lien défini dans livre.js, ouvert sur clic dans un nouvel onglet)
const slot = document.getElementById("book-button");
if (slot && typeof CarcLivre !== "undefined") {
  const label = lang === "en" ? "Discover the book" : "Découvrir le livre";
  const btn = CarcLivre.creerLien(document, lang, "📖 " + label, "link");
  if (!CarcLivre.lienLivre(lang)) {
    btn.classList.add("disabled");
    btn.title = lang === "en" ? "Link coming soon" : "Lien bientôt disponible";
  }
  slot.append(btn);
}
