// ============================================================
// 🏰 Carcassonne Coach — calculs de probabilités (livre, chapitres 1 à 3)
// ============================================================
// Module de calcul PUR : aucune lecture de la page, aucune interface.
// Il reçoit des listes de tuiles déjà lues (via extractFinishedState() dans
// le content script) et renvoie des nombres. Il ne lit jamais l'état de la
// partie lui-même : la règle d'accès (finishedProof) reste dans content-script.js.
//
// Chargé comme script de contenu avant content-script.js (objet global
// CarcProba) et par Node pour les tests (module.exports).
// ============================================================

(function (root) {
  "use strict";

  // ------------------------------------------------------------
  // 1. Composition de la boîte de base (72 tuiles), nomenclature A–X
  // ------------------------------------------------------------
  const BOX = {
    A: 2, B: 4, C: 1, D: 4, E: 5, F: 2, G: 1, H: 3, I: 2, J: 3, K: 3, L: 3,
    M: 2, N: 3, O: 2, P: 3, Q: 1, R: 3, S: 2, T: 1, U: 8, V: 9, W: 4, X: 1,
  };
  const LETTERS = Object.keys(BOX);
  const START_TILE = "D";

  // Bords (haut, droite, bas, gauche, orientation de BGA) et blason de chaque
  // lettre, tels que dans TILES_DB de content-script.js. Sert à vérifier la
  // table de correspondance ci-dessous contre la base de l'extension.
  //   I : deux côtés de ville adjacents SÉPARÉS ; N : coin de ville relié.
  //   J et K, convention du livre (bords N E S O, ville en haut) :
  //   J = C R R F (virage entre est et sud), K = C F R R (virage entre sud et
  //   ouest). L'un est le symétrique de l'autre, pas une rotation.
  const LETTER_EDGES = {
    A: ["FFRF", false], B: ["FFFF", false], C: ["CCCC", true],  D: ["CRFR", false],
    E: ["CFFF", false], F: ["FCFC", true],  G: ["FCFC", false], H: ["CFCF", false],
    I: ["CFFC", false], J: ["CRRF", false], K: ["CFRR", false], L: ["CRRR", false],
    M: ["CFFC", true],  N: ["CFFC", false], O: ["CRRC", true],  P: ["CRRC", false],
    Q: ["CCFC", true],  R: ["CCFC", false], S: ["CCRC", true],  T: ["CCRC", false],
    U: ["RFRF", false], V: ["FFRR", false], W: ["FRRR", false], X: ["RRRR", false],
  };

  // Identifiant de tuile BGA (1 à 72, TILES_DB) → lettre.
  const BGA_RANGES = [
    [1, 1, "T"], [2, 3, "S"], [4, 6, "N"], [7, 8, "M"], [9, 11, "P"], [12, 13, "O"],
    [14, 14, "G"], [15, 16, "F"], [17, 18, "I"], [19, 21, "H"], [22, 26, "E"],
    [27, 29, "K"], [30, 32, "J"], [33, 35, "L"], [36, 39, "D"], [40, 47, "U"],
    [48, 56, "V"], [57, 60, "W"], [61, 61, "X"], [62, 65, "B"], [66, 67, "A"],
    [68, 68, "C"], [69, 71, "R"], [72, 72, "Q"],
  ];
  const BGA_TO_LETTER = {};
  for (const [a, b, l] of BGA_RANGES) for (let i = a; i <= b; i++) BGA_TO_LETTER[i] = l;

  function letterOfBgaId(bgId) {
    return BGA_TO_LETTER[Number(bgId)] || null;
  }

  // ------------------------------------------------------------
  // 2. Familles (comptées sur la boîte entière)
  // ------------------------------------------------------------
  const FAMILIES = [
    { id: "arrets",   types: ["A", "L", "S", "T", "W", "X"],
      fr: { name: "Arrêts de route", one: "arrêt de route", q: "Puis-je terminer ma route à ce bout ?" },
      en: { name: "Road ends", one: "road end",       q: "Can I finish my road at this end?" } },
    { id: "lignes",   types: ["U", "D", "W"],
      fr: { name: "Lignes", one: "ligne",          q: "Puis-je prolonger ma route tout droit ?" },
      en: { name: "Straights", one: "straight",       q: "Can I extend my road straight on?" } },
    { id: "coins",    types: ["M", "N", "O", "P", "Q", "R", "S", "T", "C"],
      fr: { name: "Villes en coin", one: "ville en coin",  q: "Puis-je rejoindre la ville de l'adversaire ?" },
      en: { name: "Corner cities", one: "corner city",   q: "Can I join my opponent's city?" } },
    { id: "virages",  types: ["V", "J", "K", "O", "P"],
      fr: { name: "Vrais virages", one: "vrai virage",   q: "Puis-je faire entrer mon paysan dans ce pré ?" },
      en: { name: "True curves", one: "true curve",     q: "Can I bring my farmer into this field?" } },
    { id: "capuchons", types: ["D", "E", "H", "I", "J", "K", "L"],
      fr: { name: "Capuchons", one: "capuchon",       q: "Puis-je fermer ma ville ?" },
      en: { name: "City caps", one: "city cap",       q: "Can I close my city?" } },
    { id: "courbes",  types: ["V", "J", "K", "O", "P", "L", "W", "X"],
      fr: { name: "Courbes", one: "courbe",         q: "Puis-je faire tourner ma route ?" },
      en: { name: "Bends", one: "bend",           q: "Can I turn my road?" } },
  ];

  // ------------------------------------------------------------
  // 3. État du sac
  // ------------------------------------------------------------
  // placedBgIds : tuiles posées (tuile de départ comprise).
  // revealedBgIds : tuiles révélées mais pas encore posées (tuile en main).
  // Le sac = boîte − posées − révélées. Si la tuile de départ n'apparaît pas
  // dans les tuiles posées (plateau vide), elle est retirée quand même.
  function bagCounts(placedBgIds = [], revealedBgIds = []) {
    const counts = { ...BOX };
    const unknown = [];
    const seen = new Set();
    let startSeen = false;
    for (const id of [...placedBgIds, ...revealedBgIds]) {
      if (id == null || seen.has(Number(id))) continue;   // doublon (ex. tuile en main déjà dessinée)
      seen.add(Number(id));
      const l = letterOfBgaId(id);
      if (!l) { unknown.push(id); continue; }
      if (l === START_TILE) startSeen = true;
      counts[l]--;
    }
    if (!startSeen) counts[START_TILE]--;
    const negative = LETTERS.filter(l => counts[l] < 0);
    if (negative.length) throw new Error("Sac incohérent : trop de tuiles " + negative.join(", "));
    const N = LETTERS.reduce((s, l) => s + counts[l], 0);
    return { counts, N, unknown };
  }

  // Sac complet au premier tour, avant tout tirage : 71 tuiles.
  function initialBag() {
    return bagCounts([], []);
  }

  function familyCount(counts, family) {
    return family.types.reduce((s, l) => s + (counts[l] || 0), 0);
  }

  // ------------------------------------------------------------
  // 4. Probabilités
  // ------------------------------------------------------------
  function pNext(n, N) {
    return N > 0 ? n / N : null;
  }

  // P(au moins une tuile de la famille sur k tirages sans remise)
  //   = 1 − C(N − n, k) / C(N, k) = 1 − Π_{i<k} (N − n − i) / (N − i).
  // Le produit s'annule dès que k ≥ N − n + 1 : 100 %.
  function pAtLeastOne(n, N, k) {
    if (!(N > 0)) return null;
    k = Math.max(0, Math.min(Math.floor(k), N));
    if (k === 0) return 0;
    let q = 1;
    for (let i = 0; i < k; i++) {
      const f = (N - n - i) / (N - i);
      if (f <= 0) return 1;
      q *= f;
    }
    return 1 - q;
  }

  // Nombre de tirages qu'il me reste dans un sac de N tuiles, à deux joueurs
  // qui tirent à tour de rôle. iDrawNext : le prochain tirage du sac est-il le mien ?
  function myRemainingDraws(N, iDrawNext) {
    return iDrawNext ? Math.ceil(N / 2) : Math.floor(N / 2);
  }

  // k réglable (3 par défaut), plafonné au nombre de tirages qu'il me reste.
  function effectiveK(k, N, iDrawNext) {
    return Math.max(0, Math.min(k, myRemainingDraws(N, iDrawNext)));
  }

  // ------------------------------------------------------------
  // 5. Entropie (bits), avec 0·log₂(1/0) = 0
  // ------------------------------------------------------------
  function term(p) {
    return p > 0 ? p * Math.log2(1 / p) : 0;
  }

  function binaryEntropy(p) {
    if (p == null) return null;
    return term(p) + term(1 - p);
  }

  // Entropie du prochain tirage : type exact (A–X).
  function typeEntropy(counts) {
    const N = LETTERS.reduce((s, l) => s + (counts[l] || 0), 0);
    if (N === 0) return 0;
    return LETTERS.reduce((s, l) => s + term((counts[l] || 0) / N), 0);
  }

  // ------------------------------------------------------------
  // 6. Tableau complet pour un sac donné
  // ------------------------------------------------------------
  function familyTable(counts, k) {
    const N = LETTERS.reduce((s, l) => s + (counts[l] || 0), 0);
    return FAMILIES.map(f => {
      const n = familyCount(counts, f);
      const p = pNext(n, N);
      return { id: f.id, n, N, p, pK: pAtLeastOne(n, N, k), k, H: binaryEntropy(p) };
    });
  }

  // ------------------------------------------------------------
  // 7. Mise en forme (français / anglais)
  // ------------------------------------------------------------
  const NBSP = " ";

  // 100 % et 0 % sont réservés aux certitudes (k ≥ N − n + 1, ou n = 0) :
  // 99,6 % s'affiche « > 99 % », 0,3 % « < 1 % ».
  function fmtPct(p, lang = "fr") {
    if (p == null) return "—";
    let v = String(Math.round(p * 100));
    if (p < 1 && v === "100") v = ">" + NBSP + "99";
    else if (p > 0 && v === "0") v = "<" + NBSP + "1";
    return lang === "fr" ? `${v}${NBSP}%` : `${v}%`;
  }

  function fmtFraction(n, N, lang = "fr") {
    if (!(N > 0)) return "—";
    return `${n}/${N} ≈ ${fmtPct(n / N, lang)}`;
  }

  function fmtBits(h, lang = "fr", digits = 2) {
    if (h == null) return "—";
    const s = h.toFixed(digits);
    return (lang === "fr" ? s.replace(".", ",") : s) + `${NBSP}bit${h >= 2 ? "s" : ""}`;
  }

  // Rapport d'incertitude entre le type exact et une question oui/non.
  function entropyRatio(hType, hFamily) {
    return hFamily > 0 ? hType / hFamily : null;
  }

  // Phrase du livre : « type exact 4,32 bits, capuchon 0,89 bit, soit cinq
  // fois moins d'incertitude ». family = entrée de FAMILIES (famille de référence).
  const TIMES = {
    fr: ["", "", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix"],
    en: ["", "", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"],
  };

  function ratioPhrase(hType, hFamily, family, lang = "fr") {
    const L = lang === "en" ? "en" : "fr";
    const one = family[L].one;
    const head = (L === "fr" ? "type exact " : "exact type ") + fmtBits(hType, L) +
                 ", " + one + " " + fmtBits(hFamily, L);
    if (!(hType > 0)) {
      return L === "fr" ? "Plus aucune incertitude : le sac est vide ou ne contient plus qu'un type de tuile."
                        : "No uncertainty left: the bag is empty or holds a single tile type.";
    }
    if (!(hFamily > 0)) {
      return head + (L === "fr" ? " : la réponse à cette question est déjà connue."
                                : ": the answer to this question is already known.");
    }
    const r = Math.round(entropyRatio(hType, hFamily));
    if (r < 2) {
      return head + (L === "fr" ? ", soit à peu près autant d'incertitude." : ", about the same uncertainty.");
    }
    const times = TIMES[L][r] || String(r);
    return head + (L === "fr" ? `, soit ${times} fois moins d'incertitude.`
                              : `, ${times} times less uncertainty.`);
  }

  const API = {
    BOX, LETTERS, START_TILE, LETTER_EDGES, BGA_TO_LETTER, FAMILIES,
    letterOfBgaId, bagCounts, initialBag, familyCount,
    pNext, pAtLeastOne, myRemainingDraws, effectiveK,
    binaryEntropy, typeEntropy, familyTable, entropyRatio, ratioPhrase,
    fmtPct, fmtFraction, fmtBits,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.CarcProba = API;
})(typeof globalThis !== "undefined" ? globalThis : this);
