// ============================================================
// 🏰 carcassonne-coach — reconnaissance des tuiles de BGA
// ============================================================
// Module sans DOM, partagé par content-script.js et les tests (node --test).
// Le content script lit le DOM de BGA et passe ici des valeurs simples :
// identifiant d'élément, transformation CSS, position de l'image, édition.
//
//   • Plateau : l'élément de chaque tuile posée s'appelle « tile_N », N étant
//     l'identifiant BGA (1 à 72, TILES_DB) : le type ne dépend PAS du graphisme.
//     La rotation vient de la transformation CSS de son image (.tile_art).
//   • Tuile en main (#handtile0, #title_tile, #tile_current) : pas d'identifiant,
//     seulement une image découpée dans une planche (background-position).
//     2e édition : 72 cases, une par identifiant (BG_POS_TO_ID).
//     1re édition : autre planche, 29 images pour les 24 types (ED1_POS_TO_LETTER) ;
//     l'image donne le type, pas l'exemplaire.
//   Les deux planches dessinent les tuiles dans la même orientation : la même
//   transformation CSS donne la même rotation (46 parties 1re édition rejouées
//   à l'identique par replay_bga.py).
// ============================================================
(function (root) {
  "use strict";

  const CP = root.CarcProba ||
    (typeof require !== "undefined" ? require("./probabilites.js") : null);

  // Planche 2e édition : 16 colonnes (pas de 6,66 %), rangées de 11,11 %.
  const BG_POS_TO_ID = {
    "0% 0%":1,"6.66% 0%":2,"13.33% 0%":3,"20% 0%":4,
    "26.66% 0%":5,"33.33% 0%":6,"40% 0%":7,"46.66% 0%":8,
    "53.33% 0%":9,"60% 0%":10,"66.66% 0%":11,"73.33% 0%":12,
    "80% 0%":13,"86.66% 0%":14,"93.33% 0%":15,"100% 0%":16,
    "0% 11.11%":17,"6.66% 11.11%":18,"13.33% 11.11%":19,
    "20% 11.11%":20,"26.66% 11.11%":21,"33.33% 11.11%":22,
    "40% 11.11%":23,"46.66% 11.11%":24,"53.33% 11.11%":25,
    "60% 11.11%":26,"66.66% 11.11%":27,"73.33% 11.11%":28,
    "80% 11.11%":29,"86.66% 11.11%":30,"93.33% 11.11%":31,
    "100% 11.11%":32,"0% 22.22%":33,"6.66% 22.22%":34,
    "13.33% 22.22%":35,"20% 22.22%":36,"26.66% 22.22%":37,
    "33.33% 22.22%":38,"40% 22.22%":39,"46.66% 22.22%":40,
    "53.33% 22.22%":41,"60% 22.22%":42,"66.66% 22.22%":43,
    "73.33% 22.22%":44,"80% 22.22%":45,"86.66% 22.22%":46,
    "93.33% 22.22%":47,"100% 22.22%":48,"0% 33.33%":49,
    "6.66% 33.33%":50,"13.33% 33.33%":51,"20% 33.33%":52,
    "26.66% 33.33%":53,"33.33% 33.33%":54,"40% 33.33%":55,
    "46.66% 33.33%":56,"53.33% 33.33%":57,"60% 33.33%":58,
    "66.66% 33.33%":59,"73.33% 33.33%":60,"80% 33.33%":61,
    "86.66% 33.33%":62,"93.33% 33.33%":63,"100% 33.33%":64,
    "0% 44.44%":65,"6.66% 44.44%":66,"13.33% 44.44%":67,
    "20% 44.44%":68,"26.66% 44.44%":69,"33.33% 44.44%":70,
    "40% 44.44%":71,"46.66% 44.44%":72,
  };

  // Planche 1re édition : 23 colonnes (pas de 4,54 %), rangées de 33,33 %.
  // Position de l'image → type de tuile (lettre du livre). Copie figée de
  // ed1_art_table.json (appris par replay_bga.py) : 29 images, les 24 types.
  // Les images sont rangées dans l'ordre des identifiants BGA (T, S, N, M…).
  // Toutes les tuiles de 46 parties complètes y figurent (3 266 images) :
  // aucune autre image n'existe dans la planche.
  const ED1_POS_TO_LETTER = {
    "0% 0%": "T", "4.54% 0%": "S", "9.09% 0%": "N", "13.63% 0%": "M", "18.18% 0%": "P",
    "22.72% 0%": "O", "27.27% 0%": "G", "31.81% 0%": "F", "36.36% 0%": "I", "40.90% 0%": "H",
    "45.45% 0%": "E", "50% 0%": "E", "54.54% 0%": "K", "59.09% 0%": "J", "63.63% 0%": "L",
    "68.18% 0%": "D", "72.72% 0%": "U", "77.27% 0%": "U", "81.81% 0%": "V", "86.36% 0%": "V",
    "90.90% 0%": "V", "95.45% 0%": "W", "100% 0%": "W",
    "0% 33.33%": "X", "4.54% 33.33%": "B", "9.09% 33.33%": "A", "13.63% 33.33%": "C",
    "18.18% 33.33%": "R", "22.72% 33.33%": "Q",
  };

  function shortenCoord(str) {
    str = String(str).replace(/%/g, "");
    const dot = str.indexOf(".");
    return dot === -1 ? str : str.substring(0, dot) + "." + str.substring(dot + 1, dot + 3);
  }

  // « 68.18181818181819% 0% » → « 68.18% 0% » (clé des deux tables)
  function artKey(style) {
    if (!style) return null;
    const s = String(style).trim().split(/\s+/);
    if (s.length < 2) return null;
    return shortenCoord(s[0]) + "% " + shortenCoord(s[1]) + "%";
  }

  // Classes d'une image de tuile → 1, 2, ou 0 (édition non indiquée)
  function editionFromClasses(has) {
    if (has("first_edition")) return 1;
    if (has("second_edition")) return 2;
    return 0;
  }

  // Identifiant BGA d'une image 2e édition. Une image 1re édition ne donne
  // JAMAIS d'identifiant : quatre de ses positions existent aussi dans la
  // planche 2e édition et y désignent d'autres tuiles.
  function styleToId(style, edition = 2) {
    if (edition === 1) return null;
    const key = artKey(style);
    return (key && BG_POS_TO_ID[key]) || null;
  }

  function getRotation(transform) {
    if (!transform || transform === "rotate(0deg)" || transform === "rotate(360deg)") return 0;
    if (transform === "rotate(90deg)") return 1;
    if (transform === "rotate(180deg)") return 2;
    if (transform === "rotate(-90deg)" || transform === "rotate(270deg)") return 3;
    return -1;
  }

  function tileIdToBgId(id) {
    return id && id.startsWith("tile_") ? Number(id.substring("tile_".length)) : null;
  }

  // Lit l'image d'une tuile hors plateau.
  //   art   : { style: background-position, edition: 1 | 2 | 0 } ou null
  //   taken : identifiants des tuiles déjà sur le plateau
  // Renvoie null (pas d'image) ou { status, edition, pos, bgId, letter } :
  //   "ok"      : tuile reconnue, pas encore posée ;
  //   "stale"   : tuile déjà posée (BGA laisse son image entre deux coups et en
  //               fin de partie) : ce n'est pas une tuile à jouer ;
  //   "unknown" : image non reconnue.
  // Édition 0 (non indiquée) : planche 2e édition d'abord, puis 1re édition.
  function readTileArt(art, taken) {
    if (!art || !art.style) return null;
    const pos = artKey(art.style) || String(art.style);
    const ed = art.edition;
    if (ed !== 1) {
      const id = BG_POS_TO_ID[pos] || null;
      if (id) {
        return { status: taken.has(id) ? "stale" : "ok", edition: 2, pos, bgId: id,
                 letter: CP ? CP.letterOfBgaId(id) : null };
      }
      if (ed === 2) return { status: "unknown", edition: 2, pos, bgId: null, letter: null };
    }
    const letter = ED1_POS_TO_LETTER[pos];
    if (!letter || !CP) return { status: "unknown", edition: ed, pos, bgId: null, letter: null };
    // L'image ne distingue pas les exemplaires : premier exemplaire de ce type
    // pas encore posé (le sac et le moteur ne regardent que le type).
    for (let id = 1; id <= 72; id++) {
      if (CP.BGA_TO_LETTER[id] === letter && !taken.has(id)) {
        return { status: "ok", edition: 1, pos, bgId: id, letter };
      }
    }
    return { status: "stale", edition: 1, pos, bgId: null, letter };
  }

  // Tuiles hors plateau d'une position.
  //   boardIds : identifiants des tuiles posées
  //   arts     : { title, current, hand } (images de #title_tile, #tile_current
  //              .tile_art, #handtile0 ; null si absentes)
  //   opts.handSeparate : true si la tuile de #handtile0 appartient à un autre
  //              joueur que le joueur actif. Sur BGA, chaque joueur garde sa
  //              prochaine tuile en main : le bandeau montre celle du joueur
  //              actif, le panneau celle de l'autre joueur, soit DEUX tuiles
  //              tirées hors du sac. Sert seulement en 1re édition, où deux
  //              images identiques peuvent être deux exemplaires du même type.
  // Renvoie { titleTileId, activeTileId, myTileId, drawnIds, tileIssue, readings } ;
  // drawnIds : tuiles tirées, distinctes, hors du sac.
  // tileIssue (si aucune tuile reconnue) donne la cause la plus probable :
  //   "end" : 72 tuiles posées ; "graphics" : image d'un graphisme non reconnu ;
  //   "art" : image 2e édition inconnue ; "replay" : pas d'image, ou tuile déjà posée.
  function identifyTiles(boardIds, arts, opts = {}) {
    const taken = new Set(boardIds.filter(id => id != null));
    const allPlaced = boardIds.length >= 72;
    const readings = [];
    const read = (art, used = taken) => {
      if (allPlaced) return null;
      const r = readTileArt(art, used);
      if (!r) return null;
      readings.push(r);
      // Bandeau et main montrent souvent la même tuile : même image → même identifiant.
      return r.status === "ok" ? r.bgId : null;
    };
    const titleTileId = read(arts.title);
    const activeTileId = read(arts.current);
    let myTileId = read(arts.hand);
    // 1re édition : même image dans le bandeau et dans la main d'un AUTRE joueur
    // → deux exemplaires du même type : la main reçoit l'exemplaire suivant.
    const last = readings[readings.length - 1];
    if (opts.handSeparate === true && myTileId && last && last.edition === 1 &&
        (myTileId === titleTileId || myTileId === activeTileId)) {
      readings.pop();
      const other = read(arts.hand, new Set([...taken, titleTileId, activeTileId].filter(Boolean)));
      if (other) myTileId = other;
    }
    const drawnIds = [...new Set([titleTileId, activeTileId, myTileId].filter(Boolean))];
    let tileIssue = null;
    if (!titleTileId && !activeTileId && !myTileId) {
      const g = readings.find(r => r.status === "unknown" && r.edition !== 2);
      const a = readings.find(r => r.status === "unknown" && r.edition === 2);
      tileIssue = allPlaced ? { kind: "end" }
                : g ? { kind: "graphics", pos: g.pos }
                : a ? { kind: "art", pos: a.pos }
                : { kind: "replay" };
    }
    return { titleTileId, activeTileId, myTileId, drawnIds, tileIssue, readings };
  }

  // Tuiles tirées mais cachées. Sur BGA (#handtile0 présent), chaque joueur garde
  // sa prochaine tuile en main ; un point de vue ne montre que la sienne et celle
  // du joueur actif. Du point de vue du joueur actif, la tuile de l'adversaire
  // est donc tirée (hors de la pioche, compteur de BGA) mais invisible.
  //   handMode : #handtile0 présent ; nPlayers ; placed : tuiles posées ;
  //   visible  : tuiles tirées reconnues (drawnIds.length).
  // Sans tuile visible (entre deux coups), on ne suppose rien.
  function hiddenDrawn({ handMode, nPlayers, placed, visible }) {
    if (!handMode || !(visible > 0)) return 0;
    return Math.max(0, Math.min(nPlayers, 72 - placed) - visible);
  }

  const API = {
    BG_POS_TO_ID, ED1_POS_TO_LETTER,
    shortenCoord, artKey, editionFromClasses, styleToId, getRotation, tileIdToBgId,
    readTileArt, identifyTiles, hiddenDrawn,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.CarcTuiles = API;
})(typeof globalThis !== "undefined" ? globalThis : this);
