// Tests de tuiles.js : reconnaissance des tuiles en graphisme 1re et 2e édition.
// Lancer :  node --test tests/tuiles.test.js
//
// Contrôle principal : sur une partie complète (anonymisée, tests/fixtures), la
// position lue en 1re édition est identique à celle lue en 2e édition à chaque
// coup : même plateau, même tuile en main, même sac, posées + sac + main = 72.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const P = require("../probabilites.js");
const TU = require("../tuiles.js");

const partie = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "partie_1re_edition_anonyme.json"), "utf8"));
const poses = partie.poses;

// Image 2e édition d'un identifiant, comme BGA l'écrit (pleine précision)
function ed2Style(id) {
  const c = (id - 1) % 16, r = Math.floor((id - 1) / 16);
  return `${c * 100 / 15}% ${r * 100 / 9}%`;
}
const classes = (...cls) => c => cls.includes(c);

// Lecture d'une position comme le fait content-script.js : plateau par
// l'identifiant d'élément « tile_N » et la transformation CSS, tuile en main
// par son image, sac par probabilites.js.
function lirePosition(plateau, imageMain, classesImage) {
  const board = plateau.map(p => ({
    bgId: TU.tileIdToBgId("tile_" + p.bgId),
    rotation: TU.getRotation(p.transform),
    x: p.x, y: p.y,
  }));
  const art = imageMain ? { style: imageMain, edition: TU.editionFromClasses(classesImage) } : null;
  const ids = TU.identifyTiles(board.map(b => b.bgId), { title: art, current: null, hand: art });
  const main = ids.titleTileId || ids.activeTileId || ids.myTileId || null;
  const bag = P.bagCounts(board.map(b => b.bgId), main ? [main] : []);
  return { board, main: main ? P.letterOfBgaId(main) : null, bag: bag.counts, N: bag.N,
           tileIssue: ids.tileIssue };
}

test("données de test anonymes : 72 tuiles distinctes, aucun pseudo", () => {
  assert.equal(poses.length, 72);
  assert.equal(new Set(poses.map(p => p.bgId)).size, 72);
  assert.deepEqual(partie.joueurs, ["Joueur 1", "Joueur 2"]);
  for (const p of poses) assert.deepEqual(Object.keys(p).sort(), ["bgId", "image1re", "joueur", "transform", "x", "y"]);
});

test("planche 2e édition : 72 images, une par identifiant", () => {
  assert.equal(Object.keys(TU.BG_POS_TO_ID).length, 72);
  for (let id = 1; id <= 72; id++) assert.equal(TU.styleToId(ed2Style(id), 2), id);
});

test("planche 1re édition : les 24 types, dans l'ordre des identifiants BGA", () => {
  const letters = Object.values(TU.ED1_POS_TO_LETTER);
  assert.equal(new Set(letters).size, 24);
  const ordreBga = [];
  for (let id = 1; id <= 72; id++) {
    const l = P.letterOfBgaId(id);
    if (ordreBga[ordreBga.length - 1] !== l) ordreBga.push(l);
  }
  const ordreTable = letters.filter((l, i) => l !== letters[i - 1]);
  assert.deepEqual(ordreTable, ordreBga);
});

test("planche 1re édition : copie conforme de ed1_art_table.json (replay_bga.py)", () => {
  const table = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "ed1_art_table.json"), "utf8"));
  const lettre = (edges, shield, desc) => {
    const cands = Object.entries(P.LETTER_EDGES).filter(([, [e, s]]) => e === edges && s === shield).map(([l]) => l);
    if (cands.length === 1) return cands[0];
    return /sépar/i.test(desc) ? "I" : "N";        // CFFC sans blason : séparées (I) ou reliées (N)
  };
  const attendu = {};
  for (const [k, [e, s, d]] of Object.entries(table)) {
    const [x, y] = k.split(" ");
    attendu[TU.artKey(`${x}% ${y}%`)] = lettre(e, s, d);
  }
  assert.deepEqual(TU.ED1_POS_TO_LETTER, attendu,
    "ed1_art_table.json a changé : recopier la table dans tuiles.js (ED1_POS_TO_LETTER)");
});

test("partie complète : position identique en 1re et en 2e édition à chaque coup", () => {
  for (let k = 1; k < 72; k++) {
    const plateau = poses.slice(0, k), tuile = poses[k];
    const ed1 = lirePosition(plateau, tuile.image1re, classes("tile_art", "first_edition"));
    const ed2 = lirePosition(plateau, ed2Style(tuile.bgId), classes("tile_art", "second_edition"));
    const vraie = P.letterOfBgaId(tuile.bgId);
    assert.deepEqual(ed1.board, ed2.board, `coup ${k} : plateau`);
    assert.equal(ed2.main, vraie, `coup ${k} : tuile en main (2e édition)`);
    assert.equal(ed1.main, vraie, `coup ${k} : tuile en main (1re édition, image ${tuile.image1re})`);
    assert.deepEqual(ed1.bag, ed2.bag, `coup ${k} : sac`);
    assert.equal(ed1.board.length + ed1.N + 1, 72, `coup ${k} : posées + sac + main`);
    assert.ok(ed1.board.every(b => b.rotation >= 0), `coup ${k} : rotations lues`);
  }
});

test("fin de partie : 72 tuiles posées, plus de tuile en main (les deux éditions)", () => {
  const last = poses[71];
  const ed1 = lirePosition(poses, last.image1re, classes("first_edition"));
  const ed2 = lirePosition(poses, ed2Style(last.bgId), classes("second_edition"));
  for (const r of [ed1, ed2]) {
    assert.equal(r.main, null);
    assert.equal(r.N, 0);
    assert.deepEqual(r.tileIssue, { kind: "end" });
  }
});

test("entre deux coups : l'image d'une tuile déjà posée n'est pas une tuile à jouer", () => {
  const plateau = poses.slice(0, 30), posee = poses[29];
  const r = lirePosition(plateau, ed2Style(posee.bgId), classes("second_edition"));
  assert.equal(r.main, null);
  assert.deepEqual(r.tileIssue, { kind: "replay" });
  assert.deepEqual(lirePosition(plateau, null, classes()).tileIssue, { kind: "replay" });
});

test("images communes aux deux planches : lues selon l'édition", () => {
  const vide = new Set();
  // « 100% 0% » : carrefour 3 routes (W) en 1re édition, tuile 16 (F) en 2e
  assert.equal(TU.readTileArt({ style: "100% 0%", edition: 1 }, vide).letter, "W");
  assert.equal(TU.readTileArt({ style: "100% 0%", edition: 2 }, vide).bgId, 16);
  assert.equal(TU.readTileArt({ style: "0% 33.333333333333336%", edition: 1 }, vide).letter, "X");
  assert.equal(TU.styleToId("100% 0%", 1), null);
});

test("graphisme non reconnu : cause signalée", () => {
  const plateau = poses.slice(0, 10);
  const inconnue1 = lirePosition(plateau, "50% 33.333333333333336%", classes("first_edition"));
  assert.deepEqual(inconnue1.tileIssue, { kind: "graphics", pos: "50% 33.33%" });
  const sansClasse = lirePosition(plateau, "12.5% 50%", classes());
  assert.equal(sansClasse.tileIssue.kind, "graphics");
  const inconnue2 = lirePosition(plateau, "12.5% 50%", classes("second_edition"));
  assert.equal(inconnue2.tileIssue.kind, "art");
});

// Deux tuiles tirées (règle de BGA : chaque joueur garde sa prochaine tuile) :
// celle du joueur actif dans le bandeau, celle de l'autre joueur dans son panneau.
function lireDeuxTuiles(plateau, active, autre, edition, handSeparate = true) {
  const img = p => edition === 1 ? p.image1re : ed2Style(p.bgId);
  const art = p => ({ style: img(p), edition });
  const board = plateau.map(p => p.bgId);
  const ids = TU.identifyTiles(board, { title: art(active), current: null, hand: art(autre) }, { handSeparate });
  const bag = P.bagCounts(board, ids.drawnIds);
  return { drawn: ids.drawnIds.map(id => P.letterOfBgaId(id)).sort(), bag: bag.counts, N: bag.N };
}

test("deux tuiles tirées : même sac en 1re et en 2e édition, posées + sac + tirées = 72", () => {
  for (let k = 1; k < 71; k++) {
    const plateau = poses.slice(0, k);
    const ed1 = lireDeuxTuiles(plateau, poses[k], poses[k + 1], 1);
    const ed2 = lireDeuxTuiles(plateau, poses[k], poses[k + 1], 2);
    const vraies = [poses[k], poses[k + 1]].map(p => P.letterOfBgaId(p.bgId)).sort();
    assert.deepEqual(ed2.drawn, vraies, `coup ${k} : tuiles tirées (2e édition)`);
    assert.deepEqual(ed1.drawn, vraies, `coup ${k} : tuiles tirées (1re édition)`);
    assert.deepEqual(ed1.bag, ed2.bag, `coup ${k} : sac`);
    assert.equal(k + ed1.N + 2, 72, `coup ${k} : posées + sac + tirées`);
  }
});

test("1re édition, deux exemplaires du même type : deux tuiles si la main est à l'autre joueur", () => {
  // Deux routes droites (U) : 8 exemplaires dans la boîte
  const u = poses.filter(p => P.letterOfBgaId(p.bgId) === "U");
  const plateau = poses.filter(p => P.letterOfBgaId(p.bgId) !== "U").slice(0, 20);
  const separees = lireDeuxTuiles(plateau, u[0], u[1], 1, true);
  assert.deepEqual(separees.drawn, ["U", "U"]);
  assert.equal(separees.bag.U, 6);
  // Main du joueur actif : même tuile vue deux fois
  const memeTuile = lireDeuxTuiles(plateau, u[0], u[0], 1, false);
  assert.deepEqual(memeTuile.drawn, ["U"]);
  assert.equal(memeTuile.bag.U, 7);
  // 2e édition : même image = même tuile, quel que soit le joueur
  assert.deepEqual(lireDeuxTuiles(plateau, u[0], u[0], 2, true).drawn, ["U"]);
});

test("tuile cachée : point de vue du joueur actif, compteur égal à celui de BGA", () => {
  // Coup 1 (capture du replay) : 1 posée, le joueur actif voit sa tuile (bandeau
  // et panneau = la même), la prochaine tuile de l'adversaire est cachée.
  const plateau = poses.slice(0, 1), active = poses[1];
  const art = { style: active.image1re, edition: 1 };
  const ids = TU.identifyTiles(plateau.map(p => p.bgId), { title: art, current: null, hand: art },
                               { handSeparate: false });
  assert.equal(ids.drawnIds.length, 1);
  const hidden = TU.hiddenDrawn({ handMode: true, nPlayers: 2, placed: 1, visible: ids.drawnIds.length });
  assert.equal(hidden, 1);
  const bag = P.bagCounts(plateau.map(p => p.bgId), ids.drawnIds);
  assert.equal(bag.N, 70);                         // tuiles non vues (composition connue)
  assert.equal(bag.N - hidden, 69);                // pioche = compteur « tuiles restantes » de BGA
  // Point de vue de l'autre joueur : deux tuiles visibles, aucune cachée
  assert.equal(TU.hiddenDrawn({ handMode: true, nPlayers: 2, placed: 1, visible: 2 }), 0);
  // Sans tuile en main sur BGA, ou entre deux coups (rien de visible) : rien de supposé
  assert.equal(TU.hiddenDrawn({ handMode: false, nPlayers: 2, placed: 1, visible: 1 }), 0);
  assert.equal(TU.hiddenDrawn({ handMode: true, nPlayers: 2, placed: 30, visible: 0 }), 0);
  // Dernière tuile : une seule tuile à tirer, rien de caché
  assert.equal(TU.hiddenDrawn({ handMode: true, nPlayers: 2, placed: 71, visible: 1 }), 0);
});

test("1re édition sans classe sur l'élément : reconnue si l'image n'existe qu'en 1re édition", () => {
  const r = TU.readTileArt({ style: "68.18181818181819% 0%", edition: 0 }, new Set([36]));
  assert.equal(r.status, "ok");
  assert.equal(r.letter, "D");
  assert.equal(r.bgId, 37);            // premier exemplaire de D pas encore posé
});
