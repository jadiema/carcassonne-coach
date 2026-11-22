// ============================================================
// 📖 carcassonne-coach — renvois au livre (seul endroit où les définir)
// ============================================================
// « Carcassonne, le jeu autrement – Du hasard à l'intelligence artificielle »
// (Éditions Jadiema) ; édition anglaise « Rethinking Carcassonne ». Chargé par le panneau sur BGA (content script), la fenêtre
// de l'icône (popup.html) et la page de bienvenue (welcome.html).
//
// Les liens s'ouvrent dans un nouvel onglet, uniquement sur clic, sans pistage
// (rel="noopener noreferrer" : la page du livre ne reçoit pas l'adresse BGA).
// Tant qu'un lien n'est pas une adresse https://, il n'est pas affiché comme lien.
// ============================================================

(function (root) {
  "use strict";

  // Page du livre en français / en anglais (section du README français ou anglais du
  // dépôt, en attendant le lien d'achat)
  const LIEN_LIVRE_FR = "https://github.com/jadiema/carcassonne-coach/blob/main/README.fr.md#le-livre";
  const LIEN_LIVRE_EN = "https://github.com/jadiema/carcassonne-coach#the-book";

  // Titres et couvertures (fichiers locaux, environ 200 px affichés) de chaque édition
  const TITRES = {
    fr: { court: "Carcassonne, le jeu autrement",
          complet: "Carcassonne, le jeu autrement – Du hasard à l'intelligence artificielle" },
    en: { court: "Rethinking Carcassonne",
          complet: "Rethinking Carcassonne – From Chance to Artificial Intelligence" },
  };
  const COUVERTURES = { fr: "images/livre.jpg", en: "images/livre_en.jpg" };
  const ed = lang => (lang === "en" ? "en" : "fr");
  const titreCourt = lang => TITRES[ed(lang)].court;
  const titreComplet = lang => TITRES[ed(lang)].complet;
  const couverture = lang => COUVERTURES[ed(lang)];

  // Table unique des renvois : sujet → chapitre (numéro, titre FR, titre EN).
  // Un titre EN manquant ou à "TODO" : l'infobulle anglaise reprend le titre français.
  const CHAPITRES = {
    sac:      { n: 1,  fr: "Le sac",                                    en: "The Bag" },
    entropie: { n: 2,  fr: "Mesurer l'incertitude : l'entropie",       en: "Measuring Uncertainty: Entropy" },
    tirages:  { n: 3,  fr: "Les chances de fermer",                     en: "The Chances of Completing" },
    trous:    { n: 4,  fr: "Les cases contraintes et l'art de bloquer", en: "Constrained Spaces and the Art of Blocking" },
    meeple:   { n: 8,  fr: "Le prix d'un meeple",                       en: "The Price of a Meeple" },
    mcts:     { n: 12, fr: "Le MCTS : explorer l'arbre de jeu",         en: "MCTS: Exploring the Game Tree" },
    reseau:   { n: 13, fr: "Le réseau de neurones",                     en: "The Neural Network" },
  };

  function lienLivre(lang) {
    const u = lang === "en" ? LIEN_LIVRE_EN : LIEN_LIVRE_FR;
    return /^https:\/\//.test(u || "") ? u : null;
  }

  function titreChapitre(sujet, lang) {
    const c = CHAPITRES[sujet];
    if (!c) return "";
    return lang === "en" && c.en && c.en !== "TODO" ? c.en : c.fr;
  }

  function infobulle(sujet, lang) {
    const c = CHAPITRES[sujet];
    if (!c) return "";
    return lang === "en"
      ? `Explained in chapter ${c.n} of the book “${titreCourt(lang)}”: ${titreChapitre(sujet, lang)}`
      : `Expliqué au chapitre ${c.n} du livre « ${titreCourt(lang)} » : ${titreChapitre(sujet, lang)}`;
  }

  // Lien (ou simple texte si l'URL n'est pas encore fournie), créé par le DOM :
  // aucun HTML injecté, rien n'est chargé tant qu'on ne clique pas.
  function creerLien(doc, lang, texte, classe) {
    const url = lienLivre(lang);
    const el = doc.createElement(url ? "a" : "span");
    if (url) {
      el.href = url;
      el.target = "_blank";
      el.rel = "noopener noreferrer";
    }
    if (classe) el.className = classe;
    el.textContent = texte;
    return el;
  }

  // Pastille « 📖 ch. N » avec son infobulle
  function pastille(doc, sujet, lang) {
    const c = CHAPITRES[sujet];
    if (!c) return doc.createTextNode("");
    const el = creerLien(doc, lang, `📖 ch. ${c.n}`, "carc-ch");
    el.title = infobulle(sujet, lang);
    el.dataset.chapitre = String(c.n);
    return el;
  }

  const api = { LIEN_LIVRE_FR, LIEN_LIVRE_EN, TITRES, COUVERTURES, CHAPITRES,
                lienLivre, titreCourt, titreComplet, couverture, titreChapitre, infobulle,
                creerLien, pastille };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CarcLivre = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
