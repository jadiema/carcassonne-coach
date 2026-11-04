// ============================================================
// 🏰 Carcassonne Coach — Content Script
// ============================================================
// Injecté automatiquement sur boardgamearena.com
// Ajoute un bouton flottant pour extraire l'état de la partie
// ============================================================

(function () {
  "use strict";

  // ============================================================
  // LANGUE DE L'INTERFACE (français / anglais) — v3.0.1
  // ============================================================
  const LANG_KEY = "carcCoachLang";
  let LANG = (() => {
    try { const s = localStorage.getItem(LANG_KEY); if (s === "fr" || s === "en") return s; } catch {}
    return (navigator.language || "fr").toLowerCase().startsWith("fr") ? "fr" : "en";
  })();
  const I18N = {
    fr: {
      notBga: "Cette page n’est pas une partie de Carcassonne sur BGA.",
      noBoard: "Plateau de jeu non trouvé.",
      unexpected: "Erreur inattendue : {m}",
      blocked: "Le coach analyse les parties <strong>terminées</strong> et les <strong>replays</strong> " +
               "uniquement, conformément aux règles de Board Game Arena.<br>" +
               "Revenez à la fin de la partie, ou ouvrez son replay.",
      startFail: "Impossible de lancer l’analyse",
      noJob: "Pas de job_id reçu",
      analysisError: "Erreur d’analyse",
      timeout: "Délai dépassé : l’analyse n’a pas terminé à temps",
      warnTitle: "⚠ AVERTISSEMENT",
      warnText: "Le carcassonne-coach est un outil d’apprentissage, conçu uniquement pour vous aider " +
                "à progresser. Il ne doit en aucun cas être utilisé pendant une partie classée, ni " +
                "pendant une partie en cours contre d’autres joueurs qui n’en sont pas informés. " +
                "Se faire conseiller par une machine en cours de partie, c’est tricher. C’est " +
                "contraire au fair-play et aux règles des sites de jeu en ligne. Servez-vous-en pour " +
                "relire vos parties terminées et leurs replays, ou analyser une position après coup.",
      levelTitle: "⚠ SON NIVEAU ACTUEL",
      levelText: "Le carcassonne-coach reste un outil d’apprentissage. À ce jour, ses conseils " +
                 "n’atteignent pas le niveau des joueurs Maîtres de Board Game Arena, classés au-dessus " +
                 "de 700 points Elo, ni probablement celui des joueurs classés au-dessus de 600. " +
                 "Je continue cependant de l’améliorer jour après jour : peut-être deviendra-t-il un " +
                 "jour, lui aussi, un maître de Carcassonne.",
      legal: "Projet indépendant, sans lien avec Hans im Glück ni avec Board Game Arena. " +
             "Carcassonne est une marque déposée de Hans im Glück Verlags-GmbH.",
      understood: "J’ai compris",
      placed: "{n} posées",
      remaining: "{n} restantes",
      iAm: "Je suis :",
      engineChecking: "Moteur : vérification…",
      engineServer: "Moteur : serveur local (rapide) ✓",
      engineBrowser: "Moteur : intégré au navigateur ✓",
      engineFirst: "Première analyse : quelques secondes de chargement du moteur.",
      engineDown: "Moteur : indisponible — rechargez la page",
      engineDownMsg: "Moteur indisponible. Rechargez la page (F5), puis relancez l’analyse.",
      timeLabel: "Temps d’analyse :",
      seconds: "{n} secondes",
      minute: "1 minute",
      minutes: "{n} minutes",
      analyze: "🔍 Analyser",
      connecting: "⏳ Connexion…",
      analyzing: "⏳ Analyse… ({s} s)",
      simulating: "⏳ Simulation en cours… ({s} s)",
      rerun: "🔄 Relancer",
      error: "Erreur : {m}",
      tileMissing: "⚠️ Tuile de <strong>{name}</strong> non détectée. " +
                   "L’analyse utilise votre tuile (<strong>{edges}</strong>).",
      tileInfo: "🎯 Tuile : <strong>{tile}</strong> — analyse pour <strong>{player}</strong>",
      tilesSeen: "Tuiles détectées : {me}={mine}, adversaire={theirs}",
      you: "Vous",
      early: "ℹ️ <strong>{n} tuiles restantes</strong> — en début de partie, l’analyse MCTS " +
             "est peu fiable. Fiez-vous à votre intuition. L’outil devient pertinent " +
             "sous 30 tuiles restantes.",
      mid: "ℹ️ <strong>{n} tuiles restantes</strong> — les recommandations sont indicatives. " +
           "La fiabilité augmente à mesure que la partie avance.",
      copied: "✅ Copié",
      saveTitle: "Sauvegarder le JSON",
      disclaimerTitle: "Avertissement : usage et niveau du coach",
      simsIn: "{n} simulations en {s} s",
      noMove: "Aucun placement possible.",
      noMeeple: "sans meeple",
      clickToSee: "{n} sim. · cliquez pour voir sur le plateau",
      langTitle: "Switch to English",
    },
    en: {
      notBga: "This page is not a Carcassonne game on BGA.",
      noBoard: "Game board not found.",
      unexpected: "Unexpected error: {m}",
      blocked: "The coach only analyses <strong>finished</strong> games and <strong>replays</strong>, " +
               "in accordance with Board Game Arena rules.<br>" +
               "Come back at the end of the game, or open its replay.",
      startFail: "Could not start the analysis",
      noJob: "No job_id received",
      analysisError: "Analysis error",
      timeout: "Timed out: the analysis did not finish in time",
      warnTitle: "⚠ WARNING",
      warnText: "The carcassonne-coach is a learning tool, designed only to help you improve. " +
                "It must never be used during a rated game, nor during a game in progress against " +
                "other players who are not aware of it. Getting advice from a machine during a game " +
                "is cheating. It goes against fair play and the rules of online gaming sites. Use it " +
                "to review your finished games and their replays, or to analyse a position afterwards.",
      levelTitle: "⚠ ITS CURRENT LEVEL",
      levelText: "The carcassonne-coach remains a learning tool. Its advice does not yet reach the " +
                 "level of Board Game Arena Master players, rated above 700 Elo, nor probably that of " +
                 "players rated above 600. I keep improving it day after day: perhaps one day it will " +
                 "become a Carcassonne master too.",
      legal: "Independent project, not affiliated with Hans im Glück or Board Game Arena. " +
             "Carcassonne is a registered trademark of Hans im Glück Verlags-GmbH.",
      understood: "Got it",
      placed: "{n} placed",
      remaining: "{n} left",
      iAm: "I am:",
      engineChecking: "Engine: checking…",
      engineServer: "Engine: local server (fast) ✓",
      engineBrowser: "Engine: built into the browser ✓",
      engineFirst: "First analysis: a few seconds to load the engine.",
      engineDown: "Engine: unavailable — reload the page",
      engineDownMsg: "Engine unavailable. Reload the page (F5), then run the analysis again.",
      timeLabel: "Analysis time:",
      seconds: "{n} seconds",
      minute: "1 minute",
      minutes: "{n} minutes",
      analyze: "🔍 Analyse",
      connecting: "⏳ Connecting…",
      analyzing: "⏳ Analysing… ({s} s)",
      simulating: "⏳ Simulating… ({s} s)",
      rerun: "🔄 Run again",
      error: "Error: {m}",
      tileMissing: "⚠️ <strong>{name}</strong>’s tile was not detected. " +
                   "The analysis uses your tile (<strong>{edges}</strong>).",
      tileInfo: "🎯 Tile: <strong>{tile}</strong> — analysis for <strong>{player}</strong>",
      tilesSeen: "Detected tiles: {me}={mine}, opponent={theirs}",
      you: "You",
      early: "ℹ️ <strong>{n} tiles left</strong> — early in the game, the MCTS analysis is not " +
             "very reliable. Trust your intuition. The tool becomes relevant below 30 tiles left.",
      mid: "ℹ️ <strong>{n} tiles left</strong> — the recommendations are indicative. " +
           "Their reliability increases as the game goes on.",
      copied: "✅ Copied",
      saveTitle: "Save the JSON",
      disclaimerTitle: "Warning: use and level of the coach",
      simsIn: "{n} simulations in {s} s",
      noMove: "No legal placement.",
      noMeeple: "no meeple",
      clickToSee: "{n} sim. · click to see it on the board",
      langTitle: "Passer en français",
    },
  };
  function t(key, vars = {}) {
    const s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.fr[key] ?? key;
    return s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] !== undefined ? vars[k] : ""));
  }

  // ============================================================
  // TILE DATABASE — Jeu de base (72 tuiles)
  // ============================================================
  // landscape = bords [Top, Right, Bottom, Left]
  // C=City, F=Field, R=Road
  const TILES_DB = {
    1:{type:"CCRC",shield:false,desc:"Ville 3 côtés + route bas"},
    2:{type:"CCRC",shield:true,desc:"Ville 3 côtés + route bas (blason)"},
    3:{type:"CCRC",shield:true,desc:"Ville 3 côtés + route bas (blason)"},
    4:{type:"CFFC",shield:false,desc:"Ville angle"},
    5:{type:"CFFC",shield:false,desc:"Ville angle"},
    6:{type:"CFFC",shield:false,desc:"Ville angle"},
    7:{type:"CFFC",shield:true,desc:"Ville angle (blason)"},
    8:{type:"CFFC",shield:true,desc:"Ville angle (blason)"},
    9:{type:"CRRC",shield:false,desc:"Ville angle + route"},
    10:{type:"CRRC",shield:false,desc:"Ville angle + route"},
    11:{type:"CRRC",shield:false,desc:"Ville angle + route"},
    12:{type:"CRRC",shield:true,desc:"Ville angle + route (blason)"},
    13:{type:"CRRC",shield:true,desc:"Ville angle + route (blason)"},
    14:{type:"FCFC",shield:false,desc:"Ville 2 côtés opposés"},
    15:{type:"FCFC",shield:true,desc:"Ville 2 côtés opposés (blason)"},
    16:{type:"FCFC",shield:true,desc:"Ville 2 côtés opposés (blason)"},
    17:{type:"CFFC",shield:false,desc:"Ville 2 côtés adjacents séparés"},
    18:{type:"CFFC",shield:false,desc:"Ville 2 côtés adjacents séparés"},
    19:{type:"CFCF",shield:false,desc:"Ville 2 côtés adjacents séparés"},
    20:{type:"CFCF",shield:false,desc:"Ville 2 côtés adjacents séparés"},
    21:{type:"CFCF",shield:false,desc:"Ville 2 côtés adjacents séparés"},
    22:{type:"CFFF",shield:false,desc:"Ville 1 côté"},
    23:{type:"CFFF",shield:false,desc:"Ville 1 côté"},
    24:{type:"CFFF",shield:false,desc:"Ville 1 côté"},
    25:{type:"CFFF",shield:false,desc:"Ville 1 côté"},
    26:{type:"CFFF",shield:false,desc:"Ville 1 côté"},
    27:{type:"CFRR",shield:false,desc:"Ville + virage route droite"},
    28:{type:"CFRR",shield:false,desc:"Ville + virage route droite"},
    29:{type:"CFRR",shield:false,desc:"Ville + virage route droite"},
    30:{type:"CRRF",shield:false,desc:"Ville + virage route gauche"},
    31:{type:"CRRF",shield:false,desc:"Ville + virage route gauche"},
    32:{type:"CRRF",shield:false,desc:"Ville + virage route gauche"},
    33:{type:"CRRR",shield:false,desc:"Ville + carrefour 3 routes"},
    34:{type:"CRRR",shield:false,desc:"Ville + carrefour 3 routes"},
    35:{type:"CRRR",shield:false,desc:"Ville + carrefour 3 routes"},
    36:{type:"CRFR",shield:false,desc:"Ville + route traversante"},
    37:{type:"CRFR",shield:false,desc:"Ville + route traversante"},
    38:{type:"CRFR",shield:false,desc:"Ville + route traversante"},
    39:{type:"CRFR",shield:false,desc:"Ville + route traversante"},
    40:{type:"RFRF",shield:false,desc:"Route droite"},
    41:{type:"RFRF",shield:false,desc:"Route droite"},
    42:{type:"RFRF",shield:false,desc:"Route droite"},
    43:{type:"RFRF",shield:false,desc:"Route droite"},
    44:{type:"RFRF",shield:false,desc:"Route droite"},
    45:{type:"RFRF",shield:false,desc:"Route droite"},
    46:{type:"RFRF",shield:false,desc:"Route droite"},
    47:{type:"RFRF",shield:false,desc:"Route droite"},
    48:{type:"FFRR",shield:false,desc:"Virage route"},
    49:{type:"FFRR",shield:false,desc:"Virage route"},
    50:{type:"FFRR",shield:false,desc:"Virage route"},
    51:{type:"FFRR",shield:false,desc:"Virage route"},
    52:{type:"FFRR",shield:false,desc:"Virage route"},
    53:{type:"FFRR",shield:false,desc:"Virage route"},
    54:{type:"FFRR",shield:false,desc:"Virage route"},
    55:{type:"FFRR",shield:false,desc:"Virage route"},
    56:{type:"FFRR",shield:false,desc:"Virage route"},
    57:{type:"FRRR",shield:false,desc:"Carrefour 3 routes"},
    58:{type:"FRRR",shield:false,desc:"Carrefour 3 routes"},
    59:{type:"FRRR",shield:false,desc:"Carrefour 3 routes"},
    60:{type:"FRRR",shield:false,desc:"Carrefour 3 routes"},
    61:{type:"RRRR",shield:false,desc:"Carrefour 4 routes"},
    62:{type:"FFFF",shield:false,desc:"Monastère"},
    63:{type:"FFFF",shield:false,desc:"Monastère"},
    64:{type:"FFFF",shield:false,desc:"Monastère"},
    65:{type:"FFFF",shield:false,desc:"Monastère"},
    66:{type:"FFRF",shield:false,desc:"Monastère + route"},
    67:{type:"FFRF",shield:false,desc:"Monastère + route"},
    68:{type:"CCCC",shield:true,desc:"Ville 4 côtés (blason)"},
    69:{type:"CCFC",shield:false,desc:"Ville 3 côtés"},
    70:{type:"CCFC",shield:false,desc:"Ville 3 côtés"},
    71:{type:"CCFC",shield:false,desc:"Ville 3 côtés"},
    72:{type:"CCFC",shield:true,desc:"Ville 3 côtés (blason)"},
  };

  const COLOR_NAMES = {
    ff0000:"Rouge","0000ff":"Bleu","008000":"Vert",
    ffa500:"Jaune","000000":"Noir",
  };

  // ============================================================
  // BGA → Tile ID mapping (2nd edition)
  // ============================================================
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

  // ============================================================
  // HELPERS
  // ============================================================
  function getRotation(transform) {
    if (!transform || transform === "rotate(0deg)" || transform === "rotate(360deg)") return 0;
    if (transform === "rotate(90deg)") return 1;
    if (transform === "rotate(180deg)") return 2;
    if (transform === "rotate(-90deg)" || transform === "rotate(270deg)") return 3;
    return -1;
  }

  function rotateEdges(edges, rotation) {
    const arr = edges.split("");
    for (let i = 0; i < rotation; i++) arr.unshift(arr.pop());
    return arr.join("");
  }

  function tileIdToBgId(id) {
    return id.startsWith("tile_") ? Number(id.substring("tile_".length)) : null;
  }

  function parseCoord(placeId) {
    const m = placeId.replace("place_", "").split("x");
    return { x: Number(m[0]), y: Number(m[1]) };
  }

  function rgbToHex(rgb) {
    return rgb.replace("rgb(", "").replace(")", "")
      .split(",").map(c => Number(c.trim()).toString(16).padStart(2, "0")).join("");
  }

  function colorName(rgb) {
    return COLOR_NAMES[rgbToHex(rgb)] || rgbToHex(rgb);
  }

  function hexName(hex) {
    return COLOR_NAMES[hex] || hex;
  }

  function shortenCoord(str) {
    str = str.replace(/%/g, "");
    const dot = str.indexOf(".");
    return dot === -1 ? str : str.substring(0, dot) + "." + str.substring(dot + 1, dot + 3);
  }

  function styleToId(style) {
    if (!style) return null;
    const s = style.split(" ");
    const key = shortenCoord(s[0]) + "% " + shortenCoord(s[1]) + "%";
    return BG_POS_TO_ID[key] || null;
  }

  function getTilesEdition() {
    const els = document.getElementsByClassName("tile_art");
    return els && els.length > 0 && els[0].classList.contains("first_edition") ? 1 : 2;
  }

  // ============================================================
  // EXTRACTION ENGINE
  // ============================================================
  function extractGameState() {
    const wrapper = document.querySelector("#leftright_page_wrapper");
    if (!wrapper || wrapper.className !== "bgagame-carcassonne") {
      return { error: t("notBga") };
    }

    const mapContainer = document.getElementById("map_container");
    if (!mapContainer) {
      return { error: t("noBoard") };
    }

    // Players
    const players = Array.from(document.querySelectorAll(".player-name")).map(el => {
      const id = el.id.substring("player_name_".length);
      const scoreEl = document.getElementById("player_score_" + id);
      const link = el.getElementsByTagName("a")[0];
      if (!link) return null;
      return {
        id, name: link.textContent.trim(),
        color: colorName(link.style.color || ""),
        score: scoreEl ? Number(scoreEl.innerText) : 0,
      };
    }).filter(Boolean);

    // Board tiles
    const boardTiles = Array.from(mapContainer.getElementsByClassName("bdtile"))
      .filter(el => el.id !== "tile_current")
      .map(el => {
        const bgId = tileIdToBgId(el.id);
        const info = TILES_DB[bgId];
        const art = el.getElementsByClassName("tile_art")[0];
        const rotation = getRotation(art?.style?.transform);

        let meeple = null;
        const part = el.getElementsByClassName("partisanboard")[0];
        if (part) {
          const cc = Array.from(part.classList).find(c => c.indexOf("_") !== -1 && c.indexOf("-") === -1);
          const hex = cc ? cc.substring("partisan_".length) : "?";
          const spot = Number(part.id?.substring(String("part_" + bgId + "_").length));
          meeple = { color: hexName(hex), spot };
        }

        const placeEl = Array.from(el.childNodes).find(n => n.id?.startsWith("place"));
        const location = placeEl ? parseCoord(placeEl.id) : null;

        return {
          bgId,
          edges: info ? rotateEdges(info.type, rotation) : "????",
          edgesOriginal: info?.type || "????",
          rotation,
          shield: info?.shield || false,
          desc: info?.desc || "Inconnue",
          location,
          meeple,
        };
      });

    // Current tile — lire depuis TOUTES les sources disponibles
    // handtile0 : la tuile dans MA main (mon prochain coup)
    // title_tile : la tuile que le joueur actif doit placer (affichée dans le bandeau)
    // tile_current : la dernière tuile placée/en cours sur le plateau

    const handEl = document.getElementById("handtile0");
    const titleEl = document.getElementById("title_tile");
    const tileCurrentEl = document.getElementById("tile_current");

    const myTileId = handEl ? styleToId(handEl.style.backgroundPosition) : null;
    const titleTileId = titleEl ? styleToId(titleEl.style.backgroundPosition) : null;

    let activeTileId = null;
    if (tileCurrentEl) {
      const art = tileCurrentEl.querySelector(".tile_art");
      if (art && art.style.backgroundPosition) {
        activeTileId = styleToId(art.style.backgroundPosition);
      }
    }

    // Déterminer les tuiles distinctes disponibles
    const allTileIds = new Set([myTileId, titleTileId, activeTileId].filter(Boolean));

    // La tuile du bandeau (title_tile) est typiquement celle du joueur actif
    // handtile0 est MA tuile (celle du joueur connecté)
    // On stocke les deux pour que le sélecteur "Je suis" choisisse
    const connectedPlayerTileId = myTileId;
    const activePlayerTileId = titleTileId || activeTileId;

    // Par défaut, utiliser la tuile du joueur actif si disponible
    const curId = activePlayerTileId || connectedPlayerTileId;
    const currentTile = curId ? {
      bgId: curId,
      edges: TILES_DB[curId]?.type || "????",
      shield: TILES_DB[curId]?.shield || false,
      desc: TILES_DB[curId]?.desc || "Inconnue",
    } : null;

    // Stocker les deux tuiles pour le choix dans le panneau
    const tileOptions = {};
    if (connectedPlayerTileId && TILES_DB[connectedPlayerTileId]) {
      tileOptions.myTile = {
        bgId: connectedPlayerTileId,
        edges: TILES_DB[connectedPlayerTileId]?.type || "????",
        shield: TILES_DB[connectedPlayerTileId]?.shield || false,
        desc: TILES_DB[connectedPlayerTileId]?.desc || "Inconnue",
      };
    }
    if (activePlayerTileId && TILES_DB[activePlayerTileId] && activePlayerTileId !== connectedPlayerTileId) {
      tileOptions.opponentTile = {
        bgId: activePlayerTileId,
        edges: TILES_DB[activePlayerTileId]?.type || "????",
        shield: TILES_DB[activePlayerTileId]?.shield || false,
        desc: TILES_DB[activePlayerTileId]?.desc || "Inconnue",
      };
    }

    // Free places — toutes les positions .place moins celles occupées par des tuiles
    const occupiedSet = new Set(boardTiles.map(t => t.location ? t.location.x + "," + t.location.y : null).filter(Boolean));
    const freePlaces = Array.from(mapContainer.getElementsByClassName("place"))
      .map(el => parseCoord(el.id))
      .filter(p => !occupiedSet.has(p.x + "," + p.y));
    // Dédupliquer
    const freePlacesUnique = [];
    const freeSet = new Set();
    freePlaces.forEach(p => {
      const key = p.x + "," + p.y;
      if (!freeSet.has(key)) { freeSet.add(key); freePlacesUnique.push(p); }
    });

    console.log("🏰 Coach: " + freePlacesUnique.length + " emplacements libres, " + boardTiles.length + " tuiles posées");

    // Détecter à qui c'est le tour
    let activePlayerId = null;
    // Méthode 1: classe "active" sur le panneau joueur
    const activePanel = document.querySelector(".player-board.active, .player_board_wrap.active, .player-name.active");
    if (activePanel) {
      const idMatch = activePanel.id?.match(/\d+/);
      if (idMatch) activePlayerId = idMatch[0];
    }
    // Méthode 2: élément whoseturnis
    if (!activePlayerId) {
      const whoseTurn = document.getElementById("pagemaintitletext");
      if (whoseTurn) {
        const turnName = whoseTurn.textContent.trim();
        const matchedPlayer = players.find(p => turnName.includes(p.name));
        if (matchedPlayer) activePlayerId = matchedPlayer.id;
      }
    }
    // Méthode 3: animation pulsante sur le nom du joueur
    if (!activePlayerId) {
      const activeEl = document.querySelector(".player_elo_wrap .emblemwrap_active, .player-name .playername_active");
      if (activeEl) {
        const panel = activeEl.closest("[id*='player']");
        if (panel) {
          const idMatch = panel.id?.match(/\d+/);
          if (idMatch) activePlayerId = idMatch[0];
        }
      }
    }

    const activePlayer = players.find(p => p.id === activePlayerId) || null;

    // Détecter le joueur CONNECTÉ (pas le joueur actif)
    // Sur BGA, le joueur connecté est identifiable de plusieurs façons
    let loggedInPlayerId = null;
    // Méthode 1: data attribute sur le body ou un élément global
    const bodyData = document.body.dataset.playerId || document.body.dataset.myId;
    if (bodyData) loggedInPlayerId = bodyData;
    // Méthode 2: le panneau "Vous" / "You" ou indicateur spécial
    if (!loggedInPlayerId) {
      const panels = document.querySelectorAll("[id^='overall_player_board_']");
      for (const panel of panels) {
        // Le joueur connecté a souvent un indicateur spécifique
        const youIndicator = panel.querySelector(".bga-player-panel__is-current-player, .you_indicator, .current-player-indicator");
        if (youIndicator) {
          const idMatch = panel.id.match(/\d+/);
          if (idMatch) { loggedInPlayerId = idMatch[0]; break; }
        }
      }
    }
    // Méthode 3: tenter de lire gameui.player_id via un élément injecté
    if (!loggedInPlayerId) {
      try {
        const tempEl = document.createElement("div");
        tempEl.id = "carc-coach-detect-player";
        tempEl.style.display = "none";
        document.body.appendChild(tempEl);
        const script = document.createElement("script");
        script.textContent = 'document.getElementById("carc-coach-detect-player").dataset.pid = (typeof gameui !== "undefined" && gameui.player_id) || "";';
        document.body.appendChild(script);
        script.remove();
        loggedInPlayerId = tempEl.dataset.pid || null;
        tempEl.remove();
      } catch {}
    }
    // Méthode 4: le premier joueur dans l'ordre d'affichage est souvent le joueur connecté
    // (BGA affiche votre panneau en premier)
    if (!loggedInPlayerId && players.length >= 2) {
      const firstPanel = document.querySelector("[id^='overall_player_board_']");
      if (firstPanel) {
        const idMatch = firstPanel.id.match(/\d+/);
        if (idMatch) loggedInPlayerId = idMatch[0];
      }
    }

    const loggedInPlayer = players.find(p => p.id === loggedInPlayerId) || null;

    // Move log
    const logContainer = document.getElementById("logs");
    const logEntries = Array.from(logContainer.getElementsByClassName("log  log_replayable")).reverse();
    const moveLog = logEntries.map(entry => {
      const art = entry.querySelector(".tile_art");
      if (!art) return null;
      const bgId = styleToId(art.style.backgroundPosition);
      const ps = entry.querySelector("span.playername span.playername");
      return { player: ps?.textContent?.trim() || "?", bgId, text: entry.textContent.replace(/\s+/g, " ").trim() };
    }).filter(Boolean);

    // Remaining tiles
    const usedIds = new Set(boardTiles.map(t => t.bgId));
    moveLog.forEach(m => { if (m.bgId) usedIds.add(m.bgId); });
    const remaining = {};
    for (const [id, info] of Object.entries(TILES_DB)) {
      if (!usedIds.has(Number(id))) {
        const key = info.type + (info.shield ? "★" : "");
        remaining[key] = (remaining[key] || 0) + 1;
      }
    }

    // Meeple count
    const meeplesOnBoard = {};
    boardTiles.forEach(t => {
      if (t.meeple) meeplesOnBoard[t.meeple.color] = (meeplesOnBoard[t.meeple.color] || 0) + 1;
    });

    return {
      _meta: {
        extractedAt: new Date().toISOString(),
        tool: "Carcassonne Coach v1.0",
        note: "Collez ce JSON dans Claude pour analyse tactique",
      },
      players: players.map(p => ({
        ...p,
        meeplesUsed: meeplesOnBoard[p.color] || 0,
        meeplesAvailable: 7 - (meeplesOnBoard[p.color] || 0),
      })),
      currentTile,
      tileOptions,
      board: boardTiles,
      freePlaces: freePlacesUnique,
      activePlayer: activePlayer ? { id: activePlayer.id, name: activePlayer.name, color: activePlayer.color } : null,
      loggedInPlayer: loggedInPlayer ? { id: loggedInPlayer.id, name: loggedInPlayer.name, color: loggedInPlayer.color } : null,
      remainingTiles: remaining,
      remainingCount: Object.values(remaining).reduce((a, b) => a + b, 0),
      moveCount: moveLog.length,
      moveLog,
      // Journal BGA complet (tuiles, partisans, décomptes) pour rejouer la
      // partie coup par coup côté Python.
      rawLog: Array.from(logContainer.getElementsByClassName("log  log_replayable"))
        .reverse()
        .map(entry => {
          // On ne garde que l'image de la tuile (classe + style : planche, position,
          // rotation) : le reste du HTML (noms colorés, ombres…) ne sert à rien
          // et multipliait la taille des exports par 4.
          const art = entry.querySelector(".tile_art");
          return {
            text: entry.textContent.replace(/\s+/g, " ").trim(),
            html: art ? `<div class="${art.className}" style="${art.getAttribute("style") || ""}"></div>` : "",
          };
        }),
    };
  }

  // ============================================================
  // SERVER COMMUNICATION (via background script)
  // ============================================================

  // Moteur disponible : « serveur » (start_server.bat lancé, le plus rapide)
  // ou « navigateur » (intégré à l'extension, rien à installer).
  async function checkEngine() {
    try {
      const response = await browser.runtime.sendMessage({ type: "health" });
      if (!response || !response.ok) return null;
      return (response.data && response.data.engine) || "serveur";
    } catch { return null; }
  }
  async function checkServer() { return (await checkEngine()) !== null; }

  // ============================================================
  // CADRE D'USAGE — analyse réservée aux parties terminées et aux replays
  // ============================================================
  // Conseiller pendant une partie en cours serait contraire aux règles de
  // Board Game Arena. Le coach est un outil d'étude : il n'analyse qu'une
  // partie terminée (« Fin de la partie » dans le journal) ou un replay.
  const REPLAY_URL = /\/tablereplay\b|\/archive\/replay\/|[?&]replay=|\/replay\b/i;

  function isReplay() {
    // 1. adresse de la page, ou de la page parente si le plateau est dans un cadre
    const urls = [location.href];
    try { urls.push(window.top.location.href); } catch (e) {}
    if (urls.some(u => u && REPLAY_URL.test(u))) return true;
    // 2. variable de BGA en mode replay (accessible depuis l'extension sous Firefox)
    try {
      const page = window.wrappedJSObject || window;
      if (page.g_archive_mode) return true;
    } catch (e) {}
    // 3. commandes de replay présentes dans la page (ou la page parente)
    const docs = [document];
    try { if (window.top.document) docs.push(window.top.document); } catch (e) {}
    return docs.some(d => d.querySelector("#archivecontrol"));
  }

  function analysisAllowed() {
    if (isReplay()) return { ok: true };
    const logs = document.getElementById("logs");
    if (logs && /Fin de la partie|End of game/.test(logs.textContent)) {
      return { ok: true };
    }
    let top = "";
    try { top = window.top.location.pathname; } catch (e) { top = "(inaccessible)"; }
    return {
      ok: false,
      reason: t("blocked") +
              `<div style="margin-top:8px;font-size:10px;color:#7f849c">diagnostic : ${location.pathname}` +
              ` · parent ${top}</div>`,
    };
  }

  async function requestAnalysis(state, sims = 1000, timeSec = 10, playerIdx = 0) {
    // 1. Lancer l'analyse (retour immédiat avec job_id)
    const startResp = await browser.runtime.sendMessage({
      type: "start-analysis",
      state: state,
      sims: sims,
      time: timeSec,
      player: playerIdx,
    });

    if (!startResp || !startResp.ok) {
      throw new Error(startResp?.error || t("startFail"));
    }

    const jobId = startResp.data.job_id;
    if (!jobId) {
      // Réponse directe (pas de job — ancienne API ?)
      if (startResp.data.moves) return startResp.data;
      throw new Error(startResp.data.error || t("noJob"));
    }

    // 2. Polling toutes les 2 secondes jusqu'au résultat
    const maxPolls = Math.ceil((timeSec + 60) / 2); // timeout : temps + 1 minute
    for (let i = 0; i < maxPolls; i++) {
      await new Promise(r => setTimeout(r, 2000));

      const pollResp = await browser.runtime.sendMessage({
        type: "poll-result",
        jobId: jobId,
      });

      if (!pollResp || !pollResp.ok) continue; // erreur réseau, on réessaie

      const data = pollResp.data;
      if (data.status === "done") {
        return data.result;
      }
      if (data.status === "error") {
        throw new Error(data.error || t("analysisError"));
      }
      // status === "running" → on continue le polling
    }

    throw new Error(t("timeout"));
  }

  // ============================================================
  // UI — Panneau latéral déplaçable
  // ============================================================
  // ============================================================
  // AVERTISSEMENT (repris du livre « Le jeu Carcassonne autrement », annexe C)
  // ============================================================
  const DISCLAIMER_KEY = "carcCoachDisclaimerSeen";

  function buildDisclaimer(onClose) {
    const box = document.createElement("div");
    box.id = "carc-disclaimer";
    box.style.cssText = `
      margin: 0 0 12px; padding: 12px 14px; border-radius: 10px;
      background: #2a2430; border: 1px solid #f9a85a; font-size: 12.5px; line-height: 1.45;
    `;
    box.innerHTML = `
      <div style="font-weight:700;color:#f9a85a;margin-bottom:6px">${t("warnTitle")}</div>
      <div style="margin-bottom:10px">${t("warnText")}</div>
      <div style="font-weight:700;color:#f9a85a;margin-bottom:6px">${t("levelTitle")}</div>
      <div style="margin-bottom:10px">${t("levelText")}</div>
      <div style="font-size:11px;color:#a6adc8;margin-bottom:10px">${t("legal")}</div>`;
    const ok = document.createElement("button");
    ok.className = "carc-btn carc-btn-secondary";
    ok.textContent = t("understood");
    ok.addEventListener("click", () => {
      try { localStorage.setItem(DISCLAIMER_KEY, "1"); } catch {}
      box.remove();
      if (onClose) onClose();
    });
    box.append(ok);
    return box;
  }

  function toggleDisclaimer(body) {
    const existing = body.querySelector("#carc-disclaimer");
    if (existing) { existing.remove(); return; }
    body.prepend(buildDisclaimer());
  }

  function showModal(state) {
    removeModal();

    // Panneau (pas d'overlay bloquant)
    const panel = document.createElement("div");
    panel.id = "carc-coach-overlay";
    panel.style.cssText = `
      position: fixed; top: 60px; right: 20px; z-index: 999999;
      width: 380px; max-height: 85vh; overflow-y: auto;
      background: #1e1e2e; color: #cdd6f4; border-radius: 16px;
      box-shadow: 0 12px 48px rgba(0,0,0,0.5);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      display: flex; flex-direction: column;
    `;

    // Barre de titre draggable
    const dragBar = document.createElement("div");
    dragBar.style.cssText = `
      padding: 14px 16px 8px; cursor: grab; user-select: none;
      display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid #313244;
    `;
    dragBar.innerHTML = `
      <span style="font-size:16px;font-weight:700">🏰 Carcassonne Coach</span>
    `;

    const closeX = document.createElement("button");
    closeX.textContent = "✕";
    closeX.style.cssText = `
      background: none; border: none; color: #6c7086; font-size: 18px;
      cursor: pointer; padding: 0 4px; line-height: 1;
    `;
    closeX.addEventListener("click", removeModal);

    // Drapeau : change la langue de l'interface (mémorisée pour les prochaines fois)
    const langBtn = document.createElement("button");
    langBtn.id = "carc-lang";
    langBtn.textContent = LANG === "fr" ? "🇬🇧" : "🇫🇷";
    langBtn.title = t("langTitle");
    langBtn.style.cssText = `
      background: none; border: none; font-size: 18px; cursor: pointer;
      padding: 0 6px; line-height: 1; margin-left: auto;
    `;
    langBtn.addEventListener("mousedown", e => e.stopPropagation());
    langBtn.addEventListener("click", () => {
      LANG = LANG === "fr" ? "en" : "fr";
      try { localStorage.setItem(LANG_KEY, LANG); } catch {}
      const pos = { left: panel.style.left, top: panel.style.top, right: panel.style.right };
      showModal(state);
      const p2 = document.getElementById("carc-coach-overlay");
      if (p2 && pos.left) { p2.style.left = pos.left; p2.style.top = pos.top; p2.style.right = pos.right; }
    });
    dragBar.append(langBtn, closeX);

    // Drag logic
    let isDragging = false, offsetX = 0, offsetY = 0;
    dragBar.addEventListener("mousedown", e => {
      isDragging = true;
      offsetX = e.clientX - panel.getBoundingClientRect().left;
      offsetY = e.clientY - panel.getBoundingClientRect().top;
      dragBar.style.cursor = "grabbing";
    });
    document.addEventListener("mousemove", e => {
      if (!isDragging) return;
      panel.style.left = (e.clientX - offsetX) + "px";
      panel.style.top = (e.clientY - offsetY) + "px";
      panel.style.right = "auto";
    });
    document.addEventListener("mouseup", () => {
      isDragging = false;
      dragBar.style.cursor = "grab";
    });

    // Corps
    const body = document.createElement("div");
    body.style.cssText = "padding: 12px 16px; overflow-y: auto; flex: 1;";

    // Stats
    const statsHtml = document.createElement("div");
    statsHtml.className = "carc-stats";
    const statItems = [
      ["🧩", t("placed", { n: state.board.length })],
      ["📦", t("remaining", { n: state.remainingCount })],
    ];
    if (state.currentTile) {
      statItems.push(["🎯", state.currentTile.edges]);
    }
    statItems.forEach(([icon, text]) => {
      const s = document.createElement("div");
      s.className = "carc-stat";
      s.innerHTML = `<span>${icon}</span> ${text}`;
      statsHtml.append(s);
    });
    state.players.forEach(p => {
      const s = document.createElement("div");
      s.className = "carc-stat";
      s.innerHTML = `<span class="carc-stat-value">${p.name}</span> ${p.score}pts · ${p.meeplesAvailable}♟`;
      statsHtml.append(s);
    });

    // Sélecteur de joueur
    const playerRow = document.createElement("div");
    playerRow.style.cssText = "display:flex;align-items:center;gap:8px;margin:12px 0 4px;";
    playerRow.innerHTML = `<span style="font-size:13px;color:#a6adc8">${t("iAm")}</span>`;

    const playerSelect = document.createElement("select");
    playerSelect.id = "carc-player-select";
    playerSelect.style.cssText = `
      background: #313244; color: #cdd6f4; border: 1px solid #45475a;
      border-radius: 6px; padding: 6px 10px; font-size: 13px; cursor: pointer;
      outline: none; flex: 1;
    `;
    state.players.forEach((p, i) => {
      const o = document.createElement("option");
      o.value = i;
      o.textContent = `${p.name} (${p.color})`;
      playerSelect.append(o);
    });
    playerRow.append(playerSelect);

    // Indicateur serveur
    const serverRow = document.createElement("div");
    serverRow.style.cssText = "display:flex;align-items:center;gap:8px;margin:8px 0 4px;flex-wrap:wrap;";
    const serverDot = document.createElement("span");
    serverDot.id = "carc-server-dot";
    serverDot.style.cssText = `
      width: 8px; height: 8px; border-radius: 50%; background: #6c7086;
      display: inline-block; flex-shrink: 0;
    `;
    const serverLabel = document.createElement("span");
    serverLabel.id = "carc-server-label";
    serverLabel.style.cssText = "font-size:12px;color:#6c7086;";
    serverLabel.textContent = t("engineChecking");
    serverRow.append(serverDot, serverLabel);

    // Moteur utilisé : serveur local s'il est lancé, sinon le navigateur
    checkEngine().then(engine => {
      const dot = document.getElementById("carc-server-dot");
      const label = document.getElementById("carc-server-label");
      if (!dot || !label) return;
      if (engine === "serveur") {
        dot.style.background = "#a6e3a1";
        label.style.color = "#a6e3a1";
        label.textContent = t("engineServer");
      } else if (engine === "navigateur") {
        dot.style.background = "#89b4fa";
        label.style.color = "#89b4fa";
        label.textContent = t("engineBrowser");
        const note = document.createElement("div");
        note.style.cssText = "width:100%;margin-top:4px;font-size:11px;color:#a6adc8;line-height:1.5;";
        note.textContent = t("engineFirst");
        serverRow.append(note);
      } else {
        dot.style.background = "#f38ba8";
        label.style.color = "#f38ba8";
        label.textContent = t("engineDown");
      }
    });

    // Sélecteur de temps
    const timeRow = document.createElement("div");
    timeRow.style.cssText = "display:flex;align-items:center;gap:8px;margin:12px 0 8px;";
    timeRow.innerHTML = `<span style="font-size:13px;color:#a6adc8">${t("timeLabel")}</span>`;

    const timeSelect = document.createElement("select");
    timeSelect.style.cssText = `
      background: #313244; color: #cdd6f4; border: 1px solid #45475a;
      border-radius: 6px; padding: 6px 10px; font-size: 13px; cursor: pointer;
      outline: none;
    `;
    [
      { value: "5", label: t("seconds", { n: 5 }) },
      { value: "10", label: t("seconds", { n: 10 }) },
      { value: "15", label: t("seconds", { n: 15 }) },
      { value: "30", label: t("seconds", { n: 30 }) },
      { value: "60", label: t("minute") },
      { value: "120", label: t("minutes", { n: 2 }) },
      { value: "300", label: t("minutes", { n: 5 }) },
      { value: "600", label: t("minutes", { n: 10 }) },
    ].forEach(opt => {
      const o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      if (opt.value === "15") o.selected = true;
      timeSelect.append(o);
    });
    timeRow.append(timeSelect);

    // Zone de résultats
    const resultsDiv = document.createElement("div");
    resultsDiv.id = "carc-coach-results";

    // Textarea caché
    const json = JSON.stringify(state, null, 2);
    const textarea = document.createElement("textarea");
    textarea.className = "carc-json";
    textarea.value = json;
    textarea.readOnly = true;
    textarea.style.display = "none";

    // Boutons
    const buttons = document.createElement("div");
    buttons.style.cssText = "padding: 12px 16px; border-top: 1px solid #313244; display: flex; gap: 8px; flex-wrap: wrap;";

    const analyzeBtn = document.createElement("button");
    analyzeBtn.className = "carc-btn carc-btn-primary";
    analyzeBtn.style.cssText += "flex:1;";
    analyzeBtn.textContent = t("analyze");
    analyzeBtn.addEventListener("click", async () => {
      const policy = analysisAllowed();
      if (!policy.ok) {
        resultsDiv.innerHTML = `<div class="carc-error" style="font-size:13px">⏸️ ${policy.reason}</div>`;
        return;
      }
      analyzeBtn.disabled = true;
      analyzeBtn.textContent = t("connecting");

      // Ré-extraire l'état frais à chaque analyse
      const freshState = extractGameState();
      if (freshState.error) {
        resultsDiv.innerHTML = `<div class="carc-error">${freshState.error}</div>`;
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = t("analyze");
        return;
      }

      const serverUp = await checkServer();
      if (!serverUp) {
        resultsDiv.innerHTML = `<div class="carc-error" style="font-size:13px">
          ${t("engineDownMsg")}
        </div>`;
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = t("analyze");
        return;
      }

      const timeSec = Number(timeSelect.value);
      const playerIdx = Number(playerSelect.value);
      const selectedPlayer = freshState.players[playerIdx];

      // Sélectionner la tuile en fonction du joueur choisi
      let turnWarning = "";
      const loggedIn = freshState.loggedInPlayer;
      const opts = freshState.tileOptions || {};
      const isSelectingSelf = loggedIn && selectedPlayer && loggedIn.id === selectedPlayer.id;

      // Si on sélectionne l'adversaire et qu'on a sa tuile, l'utiliser
      if (!isSelectingSelf && opts.opponentTile) {
        freshState.currentTile = opts.opponentTile;
      } else if (isSelectingSelf && opts.myTile) {
        freshState.currentTile = opts.myTile;
      } else if (!isSelectingSelf && opts.myTile && !opts.opponentTile) {
        // Pas de tuile adverse détectée, on utilise la nôtre avec avertissement
        turnWarning = `<div style="background:#45283c;color:#f9e2af;border-radius:8px;padding:10px;margin-bottom:8px;font-size:12px;line-height:1.5">
          ${t("tileMissing", { name: selectedPlayer.name, edges: opts.myTile.edges })}
        </div>`;
      }

      // Info sur la tuile analysée
      const tileName = freshState.currentTile?.edges || '?';
      const tileShield = freshState.currentTile?.shield ? ' ★' : '';
      let tileInfo = `<div style="background:#1e3a5f;color:#89b4fa;border-radius:8px;padding:8px 10px;margin-bottom:8px;font-size:12px">
        ${t("tileInfo", { tile: tileName + tileShield, player: selectedPlayer?.name || "?" })}`;
      // Montrer les deux tuiles si elles sont différentes
      if (opts.myTile && opts.opponentTile) {
        const myE = opts.myTile.edges;
        const oppE = opts.opponentTile.edges;
        tileInfo += `<br><span style="color:#a6adc8;font-size:11px">${t("tilesSeen", { me: loggedIn?.name || t("you"), mine: myE, theirs: oppE })}</span>`;
      }
      tileInfo += `</div>`;

      // Avertissement si trop de tuiles restantes
      let earlyWarning = "";
      const remaining = freshState.remainingCount || 0;
      if (remaining > 40) {
        earlyWarning = `<div style="background:#1e3a5f;color:#89b4fa;border-radius:8px;padding:10px;margin-bottom:8px;font-size:12px;line-height:1.5">
          ${t("early", { n: remaining })}
        </div>`;
      } else if (remaining > 25) {
        earlyWarning = `<div style="background:#1e3a5f;color:#89b4fa;border-radius:8px;padding:10px;margin-bottom:8px;font-size:12px;line-height:1.5">
          ${t("mid", { n: remaining })}
        </div>`;
      }

      analyzeBtn.textContent = t("analyzing", { s: timeSec });

      // Vider immédiatement et afficher le chargement
      const warnings = turnWarning + tileInfo + earlyWarning;
      resultsDiv.innerHTML = warnings + `<div style="font-size:12px;color:#a6adc8;text-align:center;padding:16px">
        ${t("simulating", { s: timeSec })}
      </div>`;

      try {
        const result = await requestAnalysis(freshState, 999999, timeSec, playerIdx);
        console.log("🏰 Coach: résultats reçus —", result.stats.simulations, "sim en", result.stats.elapsed + "s");
        resultsDiv.innerHTML = warnings;
        analysisTile = freshState.currentTile || null;
        showResults(resultsDiv, result);
      } catch (e) {
        console.error("🏰 Coach: erreur", e);
        resultsDiv.innerHTML = `<div class="carc-error">${t("error", { m: e.message })}</div>`;
      }
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = t("rerun");
    });

    const copyBtn = document.createElement("button");
    copyBtn.className = "carc-btn carc-btn-secondary";
    copyBtn.textContent = "📋 JSON";
    copyBtn.addEventListener("click", () => {
      textarea.style.display = textarea.style.display === "none" ? "block" : "none";
      if (textarea.style.display === "block") {
        textarea.select();
        document.execCommand("copy");
        copyBtn.textContent = t("copied");
        setTimeout(() => { copyBtn.textContent = "📋 JSON"; }, 2000);
      }
    });

    const saveBtn = document.createElement("button");
    saveBtn.className = "carc-btn carc-btn-secondary";
    saveBtn.textContent = "💾";
    saveBtn.title = t("saveTitle");
    saveBtn.addEventListener("click", () => {
      if (saveGameJSON()) {
        saveBtn.textContent = "✅";
        setTimeout(() => { saveBtn.textContent = "💾"; }, 2000);
      }
    });

    const disclaimerBtn = document.createElement("button");
    disclaimerBtn.className = "carc-btn carc-btn-secondary";
    disclaimerBtn.textContent = "⚠️ DISCLAIMER";
    disclaimerBtn.title = t("disclaimerTitle");
    disclaimerBtn.style.cssText += "border-color:#f9a85a;color:#f9a85a;";
    disclaimerBtn.addEventListener("click", () => toggleDisclaimer(body));

    buttons.append(analyzeBtn, copyBtn, saveBtn, disclaimerBtn);

    body.append(statsHtml, playerRow, serverRow, timeRow, resultsDiv, textarea);
    // Affiché d'office à la première ouverture du coach
    let seen = false;
    try { seen = localStorage.getItem(DISCLAIMER_KEY) === "1"; } catch {}
    if (!seen) body.prepend(buildDisclaimer());
    panel.append(dragBar, body, buttons);
    document.body.append(panel);
  }


  // ============================================================
  // DESSIN DE LA TUILE ORIENTÉE (v3.0.3)
  // ============================================================
  // edges = bords APRÈS rotation, dans l'ordre [haut, droite, bas, gauche] ;
  // tile = tuile en main (description : villes séparées, monastère, blason).
  let analysisTile = null;

  function tileSvg(edges, tile, size) {
    if (!edges || edges.length !== 4) return "";
    const F = "#8db36a", C = "#c9924a", R = "#f3ede1", INK = "#1e2b2f";
    const desc = (tile && tile.desc) || "";
    const separate = /séparés/.test(desc), monastery = /Monast/.test(desc);
    const mid = [[50, 0], [100, 50], [50, 100], [0, 50]];
    const corner = [[0, 0], [100, 0], [100, 100], [0, 100]];      // coin d'avant chaque côté
    const pts = a => a.map(p => p.join(",")).join(" ");
    const city = [0, 1, 2, 3].filter(i => edges[i] === "C");
    const road = [0, 1, 2, 3].filter(i => edges[i] === "R");
    let g = `<rect width="100" height="100" fill="${F}"/>`;

    // Villes
    const cap = i => {
      const [cx, cy] = mid[i];
      const horiz = i % 2 === 0;
      return `<ellipse cx="${cx}" cy="${cy}" rx="${horiz ? 52 : 30}" ry="${horiz ? 30 : 52}" fill="${C}"/>`;
    };
    if (city.length === 4) {
      g += `<rect width="100" height="100" fill="${C}"/>`;
    } else if (city.length === 3) {
      const k = [0, 1, 2, 3].find(i => edges[i] !== "C");
      const a = corner[k], b = corner[(k + 1) % 4];
      const inward = [50 + (mid[k][0] - 50) * 0.05, 50 + (mid[k][1] - 50) * 0.05];
      g += `<rect width="100" height="100" fill="${C}"/><polygon points="${pts([a, b, inward])}" fill="${F}"/>`;
    } else if (city.length === 2 && !separate) {
      const [i, j] = city;
      if ((j - i) % 2 === 1) {                                    // deux côtés voisins : demi-tuile en diagonale
        const shared = j - i === 1 ? corner[j] : corner[0];
        const others = [corner[i], corner[(i + 1) % 4], corner[j], corner[(j + 1) % 4]]
          .filter((c, n, arr) => arr.findIndex(d => d[0] === c[0] && d[1] === c[1]) === n);
        g += `<polygon points="${pts(others)}" fill="${C}"/>`;
      } else {                                                    // deux côtés opposés : bande
        g += i === 0
          ? `<polygon points="0,0 100,0 72,50 100,100 0,100 28,50" fill="${C}"/>`
          : `<polygon points="0,0 50,28 100,0 100,100 50,72 0,100" fill="${C}"/>`;
      }
    } else {
      city.forEach(i => { g += cap(i); });
    }

    // Routes
    const line = (a, b) => `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${R}" stroke-width="9" stroke-linecap="butt"/>`;
    if (road.length === 2 && (road[1] - road[0]) % 2 === 0) {
      g += line(mid[road[0]], mid[road[1]]);
    } else if (road.length === 2) {
      const [a, b] = [mid[road[0]], mid[road[1]]];
      g += `<path d="M${a[0]},${a[1]} Q50,50 ${b[0]},${b[1]}" fill="none" stroke="${R}" stroke-width="9"/>`;
    } else if (road.length > 0) {
      road.forEach(i => { g += line(mid[i], [50, 50]); });
      if (road.length >= 3) g += `<rect x="42" y="42" width="16" height="16" fill="#7a6650"/>`;
    }

    // Monastère
    if (monastery) {
      g += `<rect x="36" y="44" width="28" height="22" fill="#ece4d4"/><polygon points="32,46 50,30 68,46" fill="#b5442e"/>`;
    }

    // Blason, au cœur de la ville
    if (tile && tile.shield && city.length) {
      const cx = city.reduce((s, i) => s + mid[i][0], 0) / city.length;
      const cy = city.reduce((s, i) => s + mid[i][1], 0) / city.length;
      const x = 50 + (cx - 50) * 0.55, y = 50 + (cy - 50) * 0.55;
      g += `<polygon points="${x - 8},${y - 9} ${x + 8},${y - 9} ${x + 8},${y + 2} ${x},${y + 10} ${x - 8},${y + 2}" fill="#2f5d8a"/>`;
    }
    g += `<rect width="100" height="100" fill="none" stroke="${INK}" stroke-width="3"/>`;
    return `<svg viewBox="0 0 100 100" width="${size}" height="${size}" style="display:block;flex:none">${g}</svg>`;
  }

  function showResults(container, result) {
    const { info, moves, stats } = result;

    // Nettoyer les highlights précédents
    clearHighlights();

    let html = `<div style="margin:8px 0">`;
    html += `<div style="font-size:11px;color:#6c7086;margin-bottom:10px">
      ${t("simsIn", { n: stats.simulations, s: stats.elapsed })}
    </div>`;

    if (!moves || moves.length === 0) {
      html += `<div class="carc-error">${t("noMove")}</div>`;
    } else {
      moves.forEach((m, i) => {
        const medal = i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `#${i+1}`;
        const barWidth = Math.round(m.winRate);
        const barColor = m.winRate > 60 ? "#a6e3a1" : m.winRate > 40 ? "#f9e2af" : "#f38ba8";

        const meepleText = m.meeple
          ? `<span style="color:#f9e2af">♟ ${m.meeple}</span>`
          : `<span style="color:#6c7086">${t("noMeeple")}</span>`;

        const rotNames = ["0°", "90°↻", "180°", "270°↺"];

        html += `<div class="carc-move-card" data-x="${m.x}" data-y="${m.y}" data-rank="${i+1}" data-edges="${m.edges}"
                    style="background:#313244;border-radius:8px;padding:10px;margin-bottom:6px;
                    cursor:pointer; transition: background 0.15s;
                    ${i === 0 ? "border:1px solid #a6e3a1;" : "border:1px solid transparent;"}">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <span style="font-size:14px;font-weight:600;display:flex;align-items:center;gap:8px">${tileSvg(m.edges, analysisTile, 30)}${medal} (${m.x}, ${m.y}) ${rotNames[m.rotation]}</span>
            <span style="font-size:16px;font-weight:700;color:${barColor}">${m.winRate}%</span>
          </div>
          <div style="font-size:12px;color:#cdd6f4;margin-bottom:3px">
            <code style="background:#11111b;padding:1px 5px;border-radius:3px;font-size:11px">${m.edges}</code>
            ${meepleText}
          </div>
          <div style="background:#11111b;height:5px;border-radius:3px;overflow:hidden">
            <div style="width:${barWidth}%;height:100%;background:${barColor};border-radius:3px"></div>
          </div>
          <div style="font-size:10px;color:#585b70;margin-top:3px">${t("clickToSee", { n: m.visits })}</div>
        </div>`;
      });
    }

    html += `</div>`;
    container.innerHTML = html;

    // Ajouter les événements au clic sur chaque carte
    container.querySelectorAll(".carc-move-card").forEach(card => {
      card.addEventListener("click", () => {
        const x = Number(card.dataset.x);
        const y = Number(card.dataset.y);
        const rank = Number(card.dataset.rank);
        highlightPosition(x, y, rank, card.dataset.edges);

        // Style actif sur la carte cliquée
        container.querySelectorAll(".carc-move-card").forEach(c => {
          c.style.outline = "none";
        });
        card.style.outline = "2px solid #89b4fa";
      });

      card.addEventListener("mouseenter", () => {
        card.style.background = "#45475a";
      });
      card.addEventListener("mouseleave", () => {
        card.style.background = "#313244";
      });
    });

    // Auto-highlight du meilleur coup
    if (moves && moves.length > 0) {
      highlightPosition(moves[0].x, moves[0].y, 1, moves[0].edges);
    }
  }

  // ============================================================
  // HIGHLIGHT — Mettre en évidence un emplacement sur le plateau
  // ============================================================
  function clearHighlights() {
    document.querySelectorAll(".carc-coach-highlight").forEach(el => el.remove());
  }

  function highlightPosition(x, y, rank, edges) {
    clearHighlights();

    // Sur BGA, les emplacements libres sont des éléments indépendants place_XxY
    // directement dans map_container (pas enfants de bdtile)
    const placeId = "place_" + x + "x" + y;
    const placeEl = document.getElementById(placeId);

    if (placeEl) {
      const marker = document.createElement("div");
      marker.className = "carc-coach-highlight";
      marker.style.cssText = `
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        border: 4px solid #89b4fa;
        border-radius: 4px;
        background: rgba(137, 180, 250, 0.25);
        z-index: 9999;
        pointer-events: none;
        animation: carc-pulse 1.5s ease-in-out infinite;
        box-sizing: border-box;
      `;

      const badge = document.createElement("div");
      badge.className = "carc-coach-highlight";
      badge.style.cssText = `
        position: absolute; top: -12px; left: -12px;
        width: 28px; height: 28px;
        background: #89b4fa; color: #1e1e2e;
        border-radius: 50%; font-size: 14px; font-weight: 700;
        display: flex; align-items: center; justify-content: center;
        z-index: 10000; pointer-events: none;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4);
      `;
      badge.textContent = rank;

      // Tuile fantôme dans la bonne orientation, sous le cadre
      if (edges) {
        const ghost = document.createElement("div");
        ghost.className = "carc-coach-highlight";
        ghost.style.cssText = `
          position: absolute; inset: 4px; z-index: 9998; pointer-events: none; opacity: 0.85;
        `;
        ghost.innerHTML = tileSvg(edges, analysisTile, "100%").replace('style="display:block;flex:none"', 'style="display:block;width:100%;height:100%"');
        placeEl.appendChild(ghost);
      }
      // Les place_ de BGA sont déjà en position absolute
      placeEl.appendChild(marker);
      placeEl.appendChild(badge);

      placeEl.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    } else {
      console.warn("🏰 Coach: place_" + x + "x" + y + " non trouvé dans le DOM");
    }
  }

  function showError(message) {
    removeModal();
    const panel = document.createElement("div");
    panel.id = "carc-coach-overlay";
    panel.style.cssText = `
      position: fixed; top: 60px; right: 20px; z-index: 999999;
      width: 360px; background: #1e1e2e; color: #cdd6f4;
      border-radius: 16px; padding: 20px;
      box-shadow: 0 12px 48px rgba(0,0,0,0.5);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    `;
    panel.innerHTML = `
      <div class="carc-error" style="margin-bottom:12px">❌ ${message}</div>
      <button class="carc-btn carc-btn-secondary" style="width:100%">Fermer</button>
    `;
    panel.querySelector("button").addEventListener("click", removeModal);
    document.body.append(panel);
  }

  function removeModal() {
    const el = document.getElementById("carc-coach-overlay");
    if (el) el.remove();
  }

  // ============================================================
  // UI — Floating Action Button
  // ============================================================
  function injectFAB() {
    if (document.getElementById("carc-coach-fab")) return;

    const fab = document.createElement("button");
    fab.id = "carc-coach-fab";
    fab.textContent = "🏰";
    fab.addEventListener("click", () => {
      try {
        const state = extractGameState();
        if (state.error) {
          showError(state.error);
        } else {
          showModal(state);
        }
      } catch (e) {
        showError(t("unexpected", { m: e.message }));
        console.error("Carcassonne Coach error:", e);
      }
    });

    document.body.append(fab);
  }


  // ============================================================
  // SAUVEGARDE JSON (bouton 💾 et export automatique en fin de partie)
  // ============================================================
  function currentTableId() {
    const m = location.href.match(/[?&]table=(\d+)/);
    return m ? m[1] : null;
  }

  function saveGameJSON() {
    const state = extractGameState();
    if (state.error) return false;
    const table = currentTableId();
    if (table) state._meta.tableId = table;
    const json = JSON.stringify(state, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const names = state.players.map(p => p.name).join("_vs_");
    const date = new Date().toISOString().slice(0, 10);
    const filename = `carcassonne_${names}_t${state.board.length}_${table || date}.json`;
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    return true;
  }

  // Export automatique : dès que le journal contient « Fin de la partie »,
  // le JSON complet est téléchargé une seule fois par table.
  function watchGameEnd() {
    if (window.__carcCoachWatching) return;
    window.__carcCoachWatching = true;
    const KEY = "carcCoachExportedTables";
    const timer = setInterval(() => {
      const logs = document.getElementById("logs");
      if (!logs || !/Fin de la partie|End of game/.test(logs.textContent)) return;
      clearInterval(timer);
      const table = currentTableId() || "?";
      let done = [];
      try { done = JSON.parse(localStorage.getItem(KEY) || "[]"); } catch {}
      if (done.includes(table)) return;
      setTimeout(() => {          // laisser BGA finir d'afficher le décompte
        if (saveGameJSON()) {
          done.push(table);
          try { localStorage.setItem(KEY, JSON.stringify(done.slice(-2000))); } catch {}
          console.log("🏰 Carcassonne Coach : partie exportée automatiquement (table " + table + ")");
        }
      }, 3000);
    }, 2000);
  }

  // ============================================================
  // INIT — Detect Carcassonne game page
  // ============================================================
  function init() {
    // Check if we're on a Carcassonne game page
    const wrapper = document.querySelector("#leftright_page_wrapper");
    if (wrapper && wrapper.className === "bgagame-carcassonne") {
      injectFAB();
      watchGameEnd();
      return;
    }

    // If not immediately available, observe for SPA navigation
    const observer = new MutationObserver(() => {
      const w = document.querySelector("#leftright_page_wrapper");
      if (w && w.className === "bgagame-carcassonne" && !document.getElementById("carc-coach-fab")) {
        injectFAB();
        watchGameEnd();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
