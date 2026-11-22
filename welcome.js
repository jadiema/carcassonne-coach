// Page de bienvenue (ouverte une seule fois, à l'installation : voir background.js).
// Français si le navigateur est en français, anglais sinon ; bouton pour changer.
let lang = (navigator.language || "fr").toLowerCase().startsWith("fr") ? "fr" : "en";

const cover = document.getElementById("cover");
if (cover) cover.addEventListener("error", () => { cover.style.display = "none"; });

function render() {
  document.documentElement.lang = lang;
  if (cover && typeof CarcLivre !== "undefined") {   // couverture de l'édition affichée
    cover.style.display = "";
    cover.alt = CarcLivre.titreComplet(lang);
    cover.src = CarcLivre.couverture(lang);
  }
  for (const el of document.querySelectorAll("[data-fr]")) el.innerHTML = el.dataset[lang];
  document.getElementById("lang").textContent = lang === "fr" ? "English" : "Français";
  const slot = document.getElementById("book-button");
  slot.textContent = "";
  if (typeof CarcLivre !== "undefined") {
    const btn = CarcLivre.creerLien(document, lang,
      "📖 " + (lang === "en" ? "Discover the book" : "Découvrir le livre"), "btn");
    if (!CarcLivre.lienLivre(lang)) {
      btn.classList.add("disabled");
      btn.title = lang === "en" ? "Link coming soon" : "Lien bientôt disponible";
    }
    slot.append(btn);
  }
}

document.getElementById("lang").addEventListener("click", () => {
  lang = lang === "fr" ? "en" : "fr";
  render();
});
render();
