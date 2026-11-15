// Tests du module probabilites.js — valeurs du livre « Carcassonne, le jeu autrement »
// (chapitres 1 à 3).    Lancer :  node --test tests/probabilites.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const P = require("../probabilites.js");

const pct = p => Math.round(p * 100);
const bits2 = h => Math.round(h * 100) / 100;

// ---------------------------------------------------------------
// Boîte, correspondance BGA → A–X
// ---------------------------------------------------------------
test("boîte de base : 72 tuiles, 24 types", () => {
  assert.equal(P.LETTERS.length, 24);
  assert.equal(Object.values(P.BOX).reduce((a, b) => a + b, 0), 72);
});

test("correspondance BGA → lettre : 72 identifiants, effectifs de la boîte", () => {
  const ids = Object.keys(P.BGA_TO_LETTER).map(Number).sort((a, b) => a - b);
  assert.deepEqual(ids, Array.from({ length: 72 }, (_, i) => i + 1));
  const counts = {};
  for (const l of Object.values(P.BGA_TO_LETTER)) counts[l] = (counts[l] || 0) + 1;
  assert.deepEqual(counts, P.BOX);
});

test("correspondance cohérente avec TILES_DB de content-script.js (bords + blason)", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "content-script.js"), "utf8");
  const re = /(\d+):\{type:"([CRF]{4})",shield:(true|false),desc:"([^"]*)"\}/g;
  let m, n = 0;
  while ((m = re.exec(src))) {
    const [, id, type, shield, desc] = m;
    const l = P.letterOfBgaId(id);
    const [edges, sh] = P.LETTER_EDGES[l];
    assert.equal(type, edges, `tuile BGA ${id} (${desc}) → ${l}`);
    assert.equal(shield === "true", sh, `blason tuile BGA ${id} → ${l}`);
    // I (séparés) et N/M (coin relié) ont les mêmes bords : la description les distingue
    if (l === "I") assert.match(desc, /séparés/);
    if (l === "N" || l === "M") assert.doesNotMatch(desc, /séparés/);
    n++;
  }
  assert.equal(n, 72, "72 tuiles lues dans TILES_DB");
});

function rotations(e) {
  return [0, 1, 2, 3].map(r => e.slice(4 - r) + e.slice(0, 4 - r));
}

test("J et K selon le livre : J = CRRF, K = CFRR (à la rotation près), BGA 30-32 et 27-29", () => {
  assert.ok(rotations(P.LETTER_EDGES.J[0]).includes("CRRF"));
  assert.ok(rotations(P.LETTER_EDGES.K[0]).includes("CFRR"));
  assert.ok(!rotations("CFRR").includes("CRRF"), "J et K sont symétriques, pas des rotations");
  for (const id of [30, 31, 32]) assert.equal(P.letterOfBgaId(id), "J");
  for (const id of [27, 28, 29]) assert.equal(P.letterOfBgaId(id), "K");
});

// ---------------------------------------------------------------
// Familles : boîte et sac au premier tour
// ---------------------------------------------------------------
const BOX_TOTALS = { arrets: 13, lignes: 16, coins: 18, virages: 20, capuchons: 23, courbes: 28 };
const BAG1_TOTALS = { arrets: 13, lignes: 15, coins: 18, virages: 20, capuchons: 22, courbes: 28 };

test("familles comptées sur la boîte entière", () => {
  for (const f of P.FAMILIES) assert.equal(P.familyCount(P.BOX, f), BOX_TOTALS[f.id], f.id);
});

test("sac au premier tour : 71 tuiles, 15 lignes, 22 capuchons", () => {
  const { counts, N } = P.initialBag();
  assert.equal(N, 71);
  assert.equal(counts.D, 3);
  for (const f of P.FAMILIES) assert.equal(P.familyCount(counts, f), BAG1_TOTALS[f.id], f.id);
});

test("sac : la tuile de départ posée (BGA 36-39) ne compte qu'une fois", () => {
  for (const startId of [36, 37, 38, 39]) {
    const { counts, N } = P.bagCounts([startId]);
    assert.equal(N, 71);
    assert.equal(counts.D, 3);
  }
});

test("sac : la tuile en main n'en fait pas partie", () => {
  const { counts, N } = P.bagCounts([36], [48]);    // départ + un virage V en main
  assert.equal(N, 70);
  assert.equal(counts.V, 8);
  const again = P.bagCounts([36, 48], [48]);         // tuile en main déjà dessinée sur le plateau
  assert.equal(again.N, 70);
});

test("sac : dernière tuile, puis sac vide", () => {
  const all = Array.from({ length: 72 }, (_, i) => i + 1);
  assert.equal(P.bagCounts(all.slice(0, 71)).N, 1);
  assert.equal(P.bagCounts(all).N, 0);
});

// ---------------------------------------------------------------
// Valeurs du livre au premier tour (sac de 71, k = 3)
// ---------------------------------------------------------------
const BOOK = {
  arrets:    [18, 46, 0.69],
  lignes:    [21, 52, 0.74],
  coins:     [25, 59, 0.82],
  virages:   [28, 64, 0.86],
  capuchons: [31, 68, 0.89],
  courbes:   [39, 78, 0.97],
};

test("premier tour : prochain tirage / 3 tirages / entropie (valeurs du livre)", () => {
  const { counts } = P.initialBag();
  for (const row of P.familyTable(counts, 3)) {
    const [p1, p3, h] = BOOK[row.id];
    assert.equal(pct(row.p), p1, `${row.id} prochain tirage`);
    assert.equal(pct(row.pK), p3, `${row.id} sur 3 tirages`);
    assert.equal(bits2(row.H), h, `${row.id} entropie`);
  }
});

test("100 % et 0 % réservés aux certitudes", () => {
  assert.equal(P.fmtPct(P.pAtLeastOne(26, 32, 3), "fr"), "> 99 %");   // 99,6 %
  assert.equal(P.fmtPct(P.pAtLeastOne(30, 32, 3), "fr"), "100 %");          // k ≥ N − n + 1
  assert.equal(P.fmtPct(0.003, "en"), "< 1%");
  assert.equal(P.fmtPct(0, "fr"), "0 %");
});

test("affichage « 18/71 ≈ 25 % » (villes en coin)", () => {
  assert.equal(P.fmtFraction(18, 71, "fr"), "18/71 ≈ 25 %");
  assert.equal(P.fmtFraction(18, 71, "en"), "18/71 ≈ 25%");
  assert.equal(P.fmtBits(0.8184, "fr"), "0,82 bit");
  assert.equal(P.fmtBits(4.3249, "fr"), "4,32 bits");
});

// ---------------------------------------------------------------
// Loi hypergéométrique
// ---------------------------------------------------------------
test("contrôle : sac de 40 dont 13 utiles, k = 3 ≈ 70,4 %", () => {
  const expected = 1 - (27 / 40) * (26 / 39) * (25 / 38);
  assert.ok(Math.abs(P.pAtLeastOne(13, 40, 3) - expected) < 1e-12);
  assert.equal(Math.round(P.pAtLeastOne(13, 40, 3) * 1000) / 10, 70.4);
});

function comb(a, b) {
  if (b < 0 || b > a) return 0;
  let r = 1;
  for (let i = 0; i < b; i++) r = r * (a - i) / (i + 1);
  return r;
}

test("1 − C(N−n,k)/C(N,k) : formule par produit = formule par combinaisons", () => {
  for (let N = 1; N <= 40; N++)
    for (let n = 0; n <= N; n++)
      for (let k = 1; k <= N; k++) {
        const ref = 1 - comb(N - n, k) / comb(N, k);
        assert.ok(Math.abs(P.pAtLeastOne(n, N, k) - ref) < 1e-12, `N=${N} n=${n} k=${k}`);
      }
});

test("k ≥ N − n + 1 → 100 %", () => {
  assert.equal(P.pAtLeastOne(13, 40, 28), 1);
  assert.equal(P.pAtLeastOne(5, 5, 1), 1);
  assert.ok(P.pAtLeastOne(13, 40, 27) < 1);
  assert.equal(P.pAtLeastOne(0, 40, 3), 0);
});

test("k plafonné au nombre de tirages qu'il me reste", () => {
  assert.equal(P.myRemainingDraws(71, false), 35);   // l'adversaire tire le premier
  assert.equal(P.myRemainingDraws(71, true), 36);
  assert.equal(P.effectiveK(3, 71, false), 3);
  assert.equal(P.effectiveK(3, 4, false), 2);
  assert.equal(P.effectiveK(3, 1, false), 0);
  assert.equal(P.effectiveK(3, 1, true), 1);
});

// ---------------------------------------------------------------
// Entropie
// ---------------------------------------------------------------
test("entropie binaire : bornes et 0·log₂(1/0) = 0", () => {
  assert.equal(P.binaryEntropy(0), 0);
  assert.equal(P.binaryEntropy(1), 0);
  assert.equal(P.binaryEntropy(0.5), 1);
  assert.equal(P.binaryEntropy(null), null);
});

test("entropie du type exact : 4,32 bits au premier tour, 0 bit à la dernière tuile", () => {
  assert.equal(bits2(P.typeEntropy(P.initialBag().counts)), 4.32);
  const all = Array.from({ length: 72 }, (_, i) => i + 1);
  assert.equal(P.typeEntropy(P.bagCounts(all.slice(0, 71)).counts), 0);
  assert.equal(P.typeEntropy(P.bagCounts(all).counts), 0);
});

test("phrase du livre : capuchon par défaut au premier tour", () => {
  const { counts } = P.initialBag();
  const capFam = P.FAMILIES.find(f => f.id === "capuchons");
  const cap = P.familyTable(counts, 3).find(r => r.id === "capuchons");
  const nb = s => s.replace(/ /g, " ");
  assert.equal(nb(P.ratioPhrase(P.typeEntropy(counts), cap.H, capFam, "fr")),
               "type exact 4,32 bits, capuchon 0,89 bit, soit cinq fois moins d'incertitude.");
  assert.equal(nb(P.ratioPhrase(P.typeEntropy(counts), cap.H, capFam, "en")),
               "exact type 4.32 bits, city cap 0.89 bit, five times less uncertainty.");
  assert.match(P.ratioPhrase(0, 0, capFam, "fr"), /Plus aucune incertitude/);
  assert.match(P.ratioPhrase(2, 0, capFam, "fr"), /déjà connue/);
});

test("rapport type exact / capuchon ≈ 5 au premier tour", () => {
  const { counts } = P.initialBag();
  const cap = P.familyTable(counts, 3).find(r => r.id === "capuchons");
  assert.equal(Math.round(P.entropyRatio(P.typeEntropy(counts), cap.H)), 5);
});
