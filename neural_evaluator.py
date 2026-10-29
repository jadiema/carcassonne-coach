"""
🏰 Carcassonne Neural Evaluator
================================
Réseau de neurones léger entraîné sur des parties réelles
pour évaluer les positions de Carcassonne.

Architecture:
- Entrée: plateau encodé en grille 25x25 avec 12 canaux
- Réseau: quelques couches convolutionnelles + fully connected
- Sortie: probabilité de victoire (0 à 1)

Usage:
    # Entraîner sur des parties
    python neural_evaluator.py train parties/*.json

    # Évaluer une position
    python neural_evaluator.py eval position.json
"""

import json
import numpy as np
import os
import sys
from pathlib import Path

# ============================================================
# ENCODAGE DU PLATEAU
# ============================================================
# Grille 25x25 centrée (supporte des plateaux de -12 à +12)
# 24 canaux:
#   --- Tuile de base ---
#   0-3: Bords de la tuile (top/right/bottom/left) — C=1, R=0.5, F=0
#   4:   Blason (1 si présent)
#   5:   Monastère (1 si présent)
#   6:   Meeple joueur (1 si meeple du joueur évalué)
#   7:   Meeple adversaire (1 si meeple adverse)
#   8:   Case occupée (1 si tuile posée)
#   9:   Case libre jouable (1 si emplacement libre adjacent)
#   10:  Nombre de voisins (0.25 par voisin, max 1.0)
#   --- Structures (villes) ---
#   11:  Ville du joueur (1 si cette tuile fait partie d'une ville avec meeple joueur)
#   12:  Ville adverse (1 si ville avec meeple adverse)
#   13:  Ville sans propriétaire (1 si ville sans meeple)
#   14:  Taille de la ville normalisée (nombre de tuiles / 15)
#   15:  Ouvertures de la ville normalisées (nombre d'ouvertures / 8, 0 = fermée)
#   --- Structures (routes) ---
#   16:  Route du joueur (1 si route avec meeple joueur)
#   17:  Route adverse (1 si route avec meeple adverse)
#   --- Champs ---
#   18:  Champ du joueur (1 si champ avec paysan joueur)
#   19:  Champ adverse (1 si champ avec paysan adverse)
#   20:  Villes complètes adjacentes au champ (normalisé / 5)
#   --- Monastères ---
#   21:  Monastère joueur — progression (tuiles autour / 8)
#   22:  Monastère adverse — progression (tuiles autour / 8)
#   --- Tuile courante ---
#   23:  Tuile courante compatible (simplifié)

GRID_SIZE = 25
GRID_CENTER = GRID_SIZE // 2  # 12
NUM_CHANNELS = 24
# v28 : la policy note chaque (case, rotation) : 4 cartes de 25 × 25.
POLICY_ROTATIONS = 4
NUM_CELLS = GRID_SIZE * GRID_SIZE

EDGE_VALUES = {"C": 1.0, "R": 0.5, "F": 0.0}


def encode_board(state_dict: dict, player_idx: int = 0) -> np.ndarray:
    """
    Encode l'état d'une partie en un tenseur (CHANNELS, GRID_SIZE, GRID_SIZE).
    Version enrichie avec structures, champs, et monastères.
    """
    grid = np.zeros((NUM_CHANNELS, GRID_SIZE, GRID_SIZE), dtype=np.float32)

    players = state_dict.get("players", [])
    board = state_dict.get("board", [])
    opponent_idx = 1 - player_idx

    # Mapper les couleurs aux indices joueur
    color_to_idx = {}
    for i, p in enumerate(players):
        color_to_idx[p.get("color", "")] = i

    # Calculer le centre du plateau pour le recentrer
    locs = [(t["location"]["x"], t["location"]["y"])
            for t in board if t.get("location")]
    if not locs:
        return grid

    cx = sum(x for x, y in locs) / len(locs)
    cy = sum(y for x, y in locs) / len(locs)

    occupied = set()
    # Mapping position réelle → position grille
    pos_to_grid = {}
    grid_to_pos = {}

    # === PASS 1: Encoder les tuiles de base (canaux 0-10) ===
    for tile in board:
        loc = tile.get("location")
        if not loc:
            continue

        rx, ry = loc["x"], loc["y"]
        gx = int(rx - cx + GRID_CENTER)
        gy = int(ry - cy + GRID_CENTER)

        if not (0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE):
            continue

        occupied.add((gx, gy))
        pos_to_grid[(rx, ry)] = (gx, gy)
        grid_to_pos[(gx, gy)] = (rx, ry)
        edges = tile.get("edges", "FFFF")

        # Canaux 0-3: bords
        for i, edge in enumerate(edges[:4]):
            grid[i, gy, gx] = EDGE_VALUES.get(edge, 0.0)

        # Canal 4: blason
        if tile.get("shield", False):
            grid[4, gy, gx] = 1.0

        # Canal 5: monastère
        desc = tile.get("desc", "").lower()
        if "monastère" in desc or "monast" in desc:
            grid[5, gy, gx] = 1.0

        # Canaux 6-7: meeples
        meeple = tile.get("meeple")
        if meeple:
            meeple_color = meeple.get("color", "")
            meeple_idx = color_to_idx.get(meeple_color, -1)
            if meeple_idx == player_idx:
                grid[6, gy, gx] = 1.0
            elif meeple_idx >= 0:
                grid[7, gy, gx] = 1.0

        # Canal 8: case occupée
        grid[8, gy, gx] = 1.0

    # Canal 9: cases libres jouables + Canal 10: nombre de voisins
    for gy_check in range(GRID_SIZE):
        for gx_check in range(GRID_SIZE):
            if (gx_check, gy_check) in occupied:
                continue
            n_neighbors = 0
            for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
                if (gx_check + dx, gy_check + dy) in occupied:
                    n_neighbors += 1
            if n_neighbors > 0:
                grid[9, gy_check, gx_check] = 1.0
                grid[10, gy_check, gx_check] = min(1.0, n_neighbors * 0.25)

    # === PASS 2-4 (v24) : structures calculées par le MOTEUR de jeu ===
    # (v10 : propriétaire de ville = n'importe quel meeple de la tuile, villes
    #  séparées fusionnées, paysans mal détectés, canal 20 jamais rempli)
    _encode_with_engine(grid, state_dict, pos_to_grid, player_idx)

    return grid


def _state_from_dict(state_dict: dict):
    """GameState correspondant au dict (directement si fourni par le moteur)."""
    import carcassonne_engine as E
    st = state_dict.get("_state")
    if st is not None:
        return st
    return E.GameState.from_json({**state_dict,
                                  "players": [{"name": p.get("name", ""), "color": p.get("color", ""),
                                               "score": p.get("score", 0),
                                               "meeplesAvailable": p.get("meeplesAvailable", 7)}
                                              for p in state_dict.get("players", [])]})


def _encode_with_engine(grid, state_dict, pos_to_grid, player_idx):
    """Canaux 11-23 calculés avec le moteur (même logique que le décompte)."""
    import carcassonne_engine as E
    st = _state_from_dict(state_dict)
    opp = 1 - player_idx

    def mark(ch, tiles, value=1.0, use_max=False):
        for t in tiles:
            if t in pos_to_grid:
                gx, gy = pos_to_grid[t]
                grid[ch, gy, gx] = max(grid[ch, gy, gx], value) if use_max else value

    def owners(meeples):
        if not meeples:
            return set()
        m = max(meeples.values())
        return {p for p, c in meeples.items() if c == m}

    # Villes et routes
    seen = set()
    for (x, y), t in st.board.items():
        for side in range(4):
            e = t.edges[side]
            if e not in "CR" or (x, y, side) in seen:
                continue
            kind = "city" if e == "C" else "road"
            r = st._trace_structure(x, y, side, kind)
            seen |= r["sides"]
            own = owners(r["meeples"])
            if kind == "city":
                openings = sum(1 for (sx, sy, ss) in r["sides"]
                               if (sx + E.DX[ss], sy + E.DY[ss]) not in st.board)
                if player_idx in own: mark(11, r["tiles"])
                if opp in own: mark(12, r["tiles"])
                if not own: mark(13, r["tiles"])
                mark(14, r["tiles"], min(1.0, len(r["tiles"]) / 15.0), True)
                mark(15, r["tiles"], min(1.0, openings / 8.0), True)
            else:
                if player_idx in own: mark(16, r["tiles"])
                if opp in own: mark(17, r["tiles"])

    # Champs (paysans sur le bon segment, villes complètes adjacentes)
    seen_hs, cache = set(), {}
    for (x, y), t in st.board.items():
        for seg in E.tile_field_segments(t):
            if (x, y, min(seg)) in seen_hs:
                continue
            fr = st._trace_field(x, y, min(seg))
            seen_hs |= fr["visited"]
            own = owners(fr["meeples"])
            if not own:
                continue
            n = st._count_adjacent_complete_cities(fr["tiles_and_sides"], cache)
            if player_idx in own: mark(18, fr["tiles"])
            if opp in own: mark(19, fr["tiles"])
            mark(20, fr["tiles"], min(1.0, n / 5.0), True)

    # Monastères occupés : progression
    for (x, y), t in st.board.items():
        if t.meeple_spot == "monastery" and t.meeple_player is not None:
            n = sum(1 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    if (dx or dy) and (x + dx, y + dy) in st.board)
            mark(21 if t.meeple_player == player_idx else 22, [(x, y)], n / 8.0)

    # Canal 23 : cases où la tuile en main peut être posée
    ct = state_dict.get("currentTile")
    tile = st.current_tile
    if tile is None and ct:
        tile = E._find_tile_type(ct["edges"], ct.get("shield", False), ct.get("desc", ""))
    if tile is not None:
        saved = st.valid_positions
        st.valid_positions = None
        try:
            locs = list(pos_to_grid.keys())
            cx = sum(x for x, _ in locs) / len(locs)
            cy = sum(y for _, y in locs) / len(locs)
            for (x, y, _) in st.get_legal_placements(tile):
                gx, gy = int(x - cx + GRID_CENTER), int(y - cy + GRID_CENTER)
                if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
                    grid[23, gy, gx] = 1.0
        finally:
            st.valid_positions = saved


def _encode_structures(grid, board, pos_to_grid, color_to_idx, player_idx):
    """Encode les villes et routes avec leur propriétaire et taille."""
    opponent_idx = 1 - player_idx

    # Construire une map des tuiles par position réelle
    tiles_by_pos = {}
    for tile in board:
        loc = tile.get("location")
        if loc:
            tiles_by_pos[(loc["x"], loc["y"])] = tile

    # Tracer les villes
    visited_city = set()
    for tile in board:
        loc = tile.get("location")
        if not loc:
            continue
        rx, ry = loc["x"], loc["y"]
        edges = tile.get("edges", "FFFF")

        for side in range(4):
            if edges[side] == "C" and (rx, ry, side) not in visited_city:
                # Tracer cette ville avec un BFS simplifié
                city_tiles, owner, n_openings, n_shields = _trace_city_simple(
                    tiles_by_pos, rx, ry, side, color_to_idx, player_idx)

                for (tx, ty) in city_tiles:
                    for s in range(4):
                        visited_city.add((tx, ty, s))

                # Encoder dans la grille
                for (tx, ty) in city_tiles:
                    if (tx, ty) in pos_to_grid:
                        gx, gy = pos_to_grid[(tx, ty)]
                        size_norm = min(1.0, len(city_tiles) / 15.0)
                        open_norm = min(1.0, n_openings / 8.0)

                        if owner == "player":
                            grid[11, gy, gx] = 1.0
                        elif owner == "opponent":
                            grid[12, gy, gx] = 1.0
                        else:
                            grid[13, gy, gx] = 1.0

                        grid[14, gy, gx] = max(grid[14, gy, gx], size_norm)
                        grid[15, gy, gx] = max(grid[15, gy, gx], open_norm)

    # Tracer les routes
    visited_road = set()
    for tile in board:
        loc = tile.get("location")
        if not loc:
            continue
        rx, ry = loc["x"], loc["y"]
        edges = tile.get("edges", "FFFF")

        for side in range(4):
            if edges[side] == "R" and (rx, ry, side) not in visited_road:
                road_tiles, owner = _trace_road_simple(
                    tiles_by_pos, rx, ry, side, color_to_idx, player_idx)

                for (tx, ty) in road_tiles:
                    for s in range(4):
                        visited_road.add((tx, ty, s))

                for (tx, ty) in road_tiles:
                    if (tx, ty) in pos_to_grid:
                        gx, gy = pos_to_grid[(tx, ty)]
                        if owner == "player":
                            grid[16, gy, gx] = 1.0
                        elif owner == "opponent":
                            grid[17, gy, gx] = 1.0


def _trace_city_simple(tiles_by_pos, start_x, start_y, start_side,
                        color_to_idx, player_idx):
    """Trace une ville et retourne (tiles, owner, openings, shields)."""
    DX_MAP = {0: 0, 1: 1, 2: 0, 3: -1}
    DY_MAP = {0: -1, 1: 0, 2: 1, 3: 0}
    OPP_SIDE = {0: 2, 1: 3, 2: 0, 3: 1}

    visited = set()
    to_visit = [(start_x, start_y, start_side)]
    city_tiles = set()
    meeple_counts = {player_idx: 0, 1 - player_idx: 0}
    openings = 0
    shields = 0

    while to_visit:
        x, y, side = to_visit.pop()
        if (x, y, side) in visited:
            continue
        visited.add((x, y, side))

        tile = tiles_by_pos.get((x, y))
        if tile is None:
            openings += 1
            continue

        city_tiles.add((x, y))
        edges = tile.get("edges", "FFFF")

        if tile.get("shield", False):
            shields += 1

        # Meeple
        meeple = tile.get("meeple")
        if meeple:
            spot = meeple.get("spot", 0)
            color = meeple.get("color", "")
            midx = color_to_idx.get(color, -1)
            if midx in meeple_counts:
                # Vérifier que le meeple est sur cette ville (approximation)
                meeple_counts[midx] += 1

        # Traverser vers la tuile adjacente
        nx, ny = x + DX_MAP[side], y + DY_MAP[side]
        opp = OPP_SIDE[side]
        if (nx, ny, opp) not in visited:
            to_visit.append((nx, ny, opp))

        # Connecter les côtés ville de la même tuile
        # (simplifié : on connecte tous les côtés C de la tuile)
        for other_side in range(4):
            if other_side != side and edges[other_side] == "C":
                if (x, y, other_side) not in visited:
                    to_visit.append((x, y, other_side))

    # Déterminer le propriétaire
    p_count = meeple_counts[player_idx]
    o_count = meeple_counts[1 - player_idx]
    if p_count > o_count:
        owner = "player"
    elif o_count > p_count:
        owner = "opponent"
    elif p_count > 0:
        owner = "shared"
    else:
        owner = "none"

    return city_tiles, owner, openings, shields


def _trace_road_simple(tiles_by_pos, start_x, start_y, start_side,
                        color_to_idx, player_idx):
    """Trace une route et retourne (tiles, owner)."""
    DX_MAP = {0: 0, 1: 1, 2: 0, 3: -1}
    DY_MAP = {0: -1, 1: 0, 2: 1, 3: 0}
    OPP_SIDE = {0: 2, 1: 3, 2: 0, 3: 1}

    visited = set()
    to_visit = [(start_x, start_y, start_side)]
    road_tiles = set()
    meeple_counts = {player_idx: 0, 1 - player_idx: 0}

    while to_visit:
        x, y, side = to_visit.pop()
        if (x, y, side) in visited:
            continue
        visited.add((x, y, side))

        tile = tiles_by_pos.get((x, y))
        if tile is None:
            continue

        road_tiles.add((x, y))
        edges = tile.get("edges", "FFFF")

        meeple = tile.get("meeple")
        if meeple:
            color = meeple.get("color", "")
            midx = color_to_idx.get(color, -1)
            if midx in meeple_counts:
                meeple_counts[midx] += 1

        # Traverser vers l'adjacent
        nx, ny = x + DX_MAP[side], y + DY_MAP[side]
        opp = OPP_SIDE[side]
        if (nx, ny, opp) not in visited:
            to_visit.append((nx, ny, opp))

        # Connecter les côtés route (seulement si 2 côtés route = pas un carrefour)
        road_sides = [s for s in range(4) if edges[s] == "R"]
        if len(road_sides) <= 2:
            for other_side in road_sides:
                if other_side != side and (x, y, other_side) not in visited:
                    to_visit.append((x, y, other_side))

    p_count = meeple_counts[player_idx]
    o_count = meeple_counts[1 - player_idx]
    if p_count > o_count:
        owner = "player"
    elif o_count > p_count:
        owner = "opponent"
    else:
        owner = "none"

    return road_tiles, owner


def _encode_fields(grid, board, pos_to_grid, color_to_idx, player_idx):
    """Encode les champs avec propriétaire et villes complètes adjacentes."""
    # Simplification : on ne trace pas les champs complets (trop complexe pour l'encodeur)
    # On marque les tuiles qui ont un paysan (meeple sur champ)
    for tile in board:
        loc = tile.get("location")
        if not loc:
            continue

        meeple = tile.get("meeple")
        if not meeple:
            continue

        spot = meeple.get("spot", 0)
        color = meeple.get("color", "")
        midx = color_to_idx.get(color, -1)

        # Spot pour un paysan : dans TileTracker, le spot "field" est différent
        # Approximation : si le meeple n'est pas sur ville/route/monastère, c'est un paysan
        edges = tile.get("edges", "FFFF")
        desc = tile.get("desc", "").lower()
        is_monastery = "monastère" in desc or "monast" in desc

        # Deviner si c'est un paysan
        is_farmer = False
        if not is_monastery:
            # Si le spot ne correspond à aucun côté ville/route, c'est un paysan
            city_sides = [s for s in range(4) if edges[s] == "C"]
            road_sides = [s for s in range(4) if edges[s] == "R"]
            # Heuristique : spot élevé ou spot sur un champ
            if spot > len(city_sides) + len(road_sides):
                is_farmer = True

        if is_farmer and (loc["x"], loc["y"]) in pos_to_grid:
            gx, gy = pos_to_grid[(loc["x"], loc["y"])]
            if midx == player_idx:
                grid[18, gy, gx] = 1.0
            elif midx >= 0:
                grid[19, gy, gx] = 1.0


def _encode_monasteries(grid, board, pos_to_grid, occupied, color_to_idx, player_idx):
    """Encode les monastères avec leur progression."""
    for tile in board:
        loc = tile.get("location")
        if not loc:
            continue

        desc = tile.get("desc", "").lower()
        if "monastère" not in desc and "monast" not in desc:
            continue

        rx, ry = loc["x"], loc["y"]
        if (rx, ry) not in pos_to_grid:
            continue
        gx, gy = pos_to_grid[(rx, ry)]

        meeple = tile.get("meeple")
        if not meeple:
            continue

        color = meeple.get("color", "")
        midx = color_to_idx.get(color, -1)

        # Compter les tuiles autour
        surrounding = 0
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if (dx, dy) == (0, 0):
                    continue
                check_gx, check_gy = gx + dx, gy + dy
                if (check_gx, check_gy) in occupied:
                    surrounding += 1

        progress = surrounding / 8.0

        if midx == player_idx:
            grid[21, gy, gx] = progress
        elif midx >= 0:
            grid[22, gy, gx] = progress


def encode_scalar_features(state_dict: dict, player_idx: int = 0) -> np.ndarray:
    """
    Encode les features scalaires (non spatiales).
    
    Returns:
        np.ndarray de shape (NUM_SCALAR_FEATURES,)
    """
    players = state_dict.get("players", [])
    opponent_idx = 1 - player_idx

    p = players[player_idx] if player_idx < len(players) else {}
    o = players[opponent_idx] if opponent_idx < len(players) else {}

    features = [
        p.get("score", 0) / 100.0,                           # score normalisé
        o.get("score", 0) / 100.0,                           # score adverse normalisé
        (p.get("score", 0) - o.get("score", 0)) / 50.0,     # différence de score
        p.get("meeplesAvailable", 7) / 7.0,                  # meeples disponibles
        o.get("meeplesAvailable", 7) / 7.0,                  # meeples adverses
        p.get("meeplesUsed", 0) / 7.0,                       # meeples posés
        o.get("meeplesUsed", 0) / 7.0,                       # meeples adverses posés
        len(state_dict.get("board", [])) / 72.0,             # progression de la partie
        state_dict.get("remainingCount", 72) / 72.0,         # tuiles restantes
    ]

    return np.array(features, dtype=np.float32)


NUM_SCALAR_FEATURES = 9


# ============================================================
# GÉNÉRATION DES DONNÉES D'ENTRAÎNEMENT
# ============================================================

def generate_training_data(json_path: str) -> list:
    """
    Génère les données d'entraînement à partir d'une partie terminée.
    
    Crée des positions intermédiaires en retirant progressivement les
    dernières tuiles jouées (via le moveLog). Chaque position est un exemple
    avec le label victoire/défaite final.
    
    Returns:
        liste de (grid, scalars, value_label, policy_target, player_idx)
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    players = data.get("players", [])
    if len(players) < 2:
        return []

    board = data.get("board", [])
    move_log = data.get("moveLog", [])

    # Déterminer le gagnant (scores finaux)
    scores = [p.get("score", 0) for p in players]
    max_score = max(scores)
    winners = [i for i, s in enumerate(scores) if s == max_score]

    # Mapper couleur → joueur
    color_to_idx = {}
    for i, p in enumerate(players):
        color_to_idx[p.get("color", "")] = i

    # Créer un index des tuiles par bgId
    board_by_bgid = {}
    for tile in board:
        board_by_bgid[tile.get("bgId")] = tile

    examples = []

    # Calculer le centre du plateau (pour convertir les positions en grille)
    locs = [(t["location"]["x"], t["location"]["y"])
            for t in board if t.get("location")]
    if not locs:
        return []
    cx = sum(x for x, y in locs) / len(locs)
    cy = sum(y for x, y in locs) / len(locs)

    # Position finale (pas de policy target — c'est la fin)
    empty_policy = np.zeros(GRID_SIZE * GRID_SIZE, dtype=np.float32)
    for player_idx in range(len(players)):
        grid = encode_board(data, player_idx)
        scalars = encode_scalar_features(data, player_idx)
        label = _get_label(player_idx, winners)
        examples.append((grid, scalars, label, empty_policy, player_idx))

    # Positions intermédiaires
    removed_bgids = set()
    n_moves = len(move_log)

    for step in range(n_moves):
        move = move_log[n_moves - 1 - step]
        bgid = move.get("bgId")
        if bgid is not None:
            removed_bgids.add(bgid)

        if len(removed_bgids) < 4:
            continue
        if step % 2 != 1:
            continue

        # Le prochain coup à jouer (celui qu'on vient de retirer)
        # C'est la tuile bgid, et sa position dans le plateau final
        # Construire le plateau intermédiaire
        intermediate_board = [t for t in board if t.get("bgId") not in removed_bgids]

        # Case du prochain coup, dans le MÊME repère que encode_board(), qui
        # recentre sur le plateau intermédiaire (v10 utilisait le centre du
        # plateau final → cible policy décalée d'une ou plusieurs cases).
        next_move_tile = board_by_bgid.get(bgid)
        next_move_pos = None
        inter_locs = [(t["location"]["x"], t["location"]["y"])
                      for t in intermediate_board if t.get("location")]
        if next_move_tile and next_move_tile.get("location") and inter_locs:
            icx = sum(x for x, _ in inter_locs) / len(inter_locs)
            icy = sum(y for _, y in inter_locs) / len(inter_locs)
            loc = next_move_tile["location"]
            gx = int(loc["x"] - icx + GRID_CENTER)
            gy = int(loc["y"] - icy + GRID_CENTER)
            if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
                next_move_pos = (gx, gy)

        meeples_used = [0] * len(players)
        for tile in intermediate_board:
            meeple = tile.get("meeple")
            if meeple:
                color = meeple.get("color", "")
                idx = color_to_idx.get(color, -1)
                if 0 <= idx < len(players):
                    meeples_used[idx] += 1

        intermediate_players = []
        for i, p in enumerate(players):
            progress = len(intermediate_board) / max(len(board), 1)
            approx_score = int(p.get("score", 0) * progress * 0.7)
            intermediate_players.append({
                "name": p.get("name", ""),
                "color": p.get("color", ""),
                "score": approx_score,
                "meeplesUsed": meeples_used[i],
                "meeplesAvailable": 7 - meeples_used[i],
            })

        intermediate_data = {
            "players": intermediate_players,
            "board": intermediate_board,
            "remainingCount": 72 - len(intermediate_board),
        }

        for player_idx in range(len(players)):
            grid = encode_board(intermediate_data, player_idx)
            scalars = encode_scalar_features(intermediate_data, player_idx)

            distance_from_end = len(removed_bgids) / max(n_moves, 1)
            raw_label = _get_label(player_idx, winners)
            discounted_label = 0.5 + (raw_label - 0.5) * (1.0 - distance_from_end * 0.5)

            # Policy target : heatmap avec 1.0 sur la case du prochain coup
            policy = np.zeros(GRID_SIZE * GRID_SIZE, dtype=np.float32)
            if next_move_pos:
                gx, gy = next_move_pos
                policy[gy * GRID_SIZE + gx] = 1.0

            examples.append((grid, scalars, discounted_label, policy, player_idx))

    return examples


def value_target(scores: list, player_idx: int, scale: float = 20.0) -> float:
    """Cible value « douce » : 0.5 + 0.5·tanh(écart final / 20).
    Garde la sortie sigmoïde (0-1) mais distingue +2 de +40."""
    diff = scores[player_idx] - max(s for i, s in enumerate(scores) if i != player_idx)
    return float(0.5 + 0.5 * np.tanh(diff / scale))


def generate_training_data_v2(json_path: str, augment: bool = True) -> list:
    """
    Exemples EXACTS par rejeu de la partie dans le moteur (nécessite rawLog, v24+).
    - positions avant chaque coup, vrais scores et vrais meeples ;
    - cible value = écart de score final (adoucie), pour chaque point de vue ;
    - cible policy = case du coup joué, uniquement du point de vue de celui qui joue ;
    - augmentation ×4 par rotation du plateau.
    """
    import carcassonne_engine as E
    import replay_bga
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    examples = []
    for pos in replay_bga.training_positions(data, augment=augment):
        st, mover, (mx, my, mrot, _) = pos["state"], pos["mover"], pos["move"]
        # v28 : contrôle de cohérence de la rotation cible. Le coup (x, y, rot)
        # doit être une pose légale de la tuile courante DANS l'état fourni
        # (y compris pour les plateaux tournés de l'augmentation). Sinon la
        # rotation est marquée « inconnue » (-1) et seule la case sert de cible.
        rot = int(mrot) % 4 if mrot is not None else -1
        try:
            legal = st.get_legal_placements(st.current_tile)
            if (mx, my, rot) in legal:
                ROT_CHECK["ok"] += 1
            else:
                # Tuile symétrique : le moteur ne liste qu'UNE des rotations
                # équivalentes (route droite : 0 ou 2, pas les deux). On prend
                # la rotation légale qui donne exactement les mêmes bords.
                rot = _canonical_rotation(E, st, mx, my, rot, legal)
                ROT_CHECK["eq" if rot >= 0 else "ko"] += 1
        except Exception:
            rot = -1
            ROT_CHECK["ko"] += 1
        for pidx in range(st.num_players):
            d = E._state_to_dict(st, pidx)
            grid = encode_board(d, pidx)
            scalars = encode_scalar_features(d, pidx)
            target = (-1, -1)
            if pidx == mover:
                locs = [(t["location"]["x"], t["location"]["y"]) for t in d["board"]]
                cx = sum(x for x, _ in locs) / len(locs)
                cy = sum(y for _, y in locs) / len(locs)
                gx, gy = int(mx - cx + GRID_CENTER), int(my - cy + GRID_CENTER)
                if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
                    target = (gy * GRID_SIZE + gx, rot)
            examples.append((grid, scalars, value_target(pos["final"], pidx), target, pidx))
    return examples


# Compteur du contrôle de cohérence des rotations (affiché par train())
ROT_CHECK = {"ok": 0, "eq": 0, "ko": 0}


def _canonical_rotation(E, st, mx, my, rot, legal) -> int:
    """Rotation listée par le moteur équivalente à `rot` (mêmes bords orientés),
    ou -1 si aucune. Sert aux tuiles symétriques, dont le moteur ne garde
    qu'une rotation parmi les rotations équivalentes."""
    from copy import deepcopy
    cands = [r for (x, y, r) in legal if (x, y) == (mx, my)]
    if not cands:
        return -1

    def edges_with(r):
        s = deepcopy(st)
        s.place_tile(st.current_tile, mx, my, r, None, None)
        for t in E._state_to_dict(s, 0)["board"]:
            loc = t.get("location") or {}
            if (loc.get("x"), loc.get("y")) == (mx, my):
                return t.get("edges")
        return None

    try:
        ref = edges_with(rot)
        if ref is None:
            return -1
        for r in cands:
            if edges_with(r) == ref:
                return r
    except Exception:
        pass
    return -1


def _to_target(policy) -> tuple:
    """Convertit une ancienne cible policy (vecteur 625) en (case, rotation inconnue)."""
    if isinstance(policy, tuple):
        return policy
    arr = np.asarray(policy)
    return (int(arr.argmax()), -1) if arr.max() > 0 else (-1, -1)


def generate_policy_only_legacy(json_path: str, augment: bool = True, min_tiles: int = 70) -> list:
    """
    Anciens exports (sans rawLog) : la pose de chaque tuile est exacte (ordre du
    moveLog + emplacement/rotation du plateau final) mais les scores et les meeples
    rendus en cours de partie sont inconnus. On n'en tire donc QUE des cibles
    policy (où le joueur a posé sa tuile) ; la cible value vaut -1 = « ignorée ».
    Les meeples encore présents en fin de partie sont posés au coup où leur tuile
    a été jouée.
    """
    import carcassonne_engine as E
    import replay_bga
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    board = {t["bgId"]: t for t in data["board"] if t.get("location")}
    if len(board) < min_tiles:
        return []      # partie abandonnée / exportée en cours de route
    colors = [p["color"] for p in data["players"]]
    order = [m["bgId"] for m in data.get("moveLog", []) if m.get("bgId") in board]
    first = [b for b in board if b not in set(order)]
    tt = {b: E._find_tile_type(t["edgesOriginal"], t.get("shield", False), t.get("desc", ""))
          for b, t in board.items()}
    g = E.GameState(len(data["players"]))
    g.player_names = [p["name"] for p in data["players"]]

    def put(state, b, with_meeple):
        t = board[b]; m = t.get("meeple") if with_meeple else None
        who = colors.index(m["color"]) if m and m["color"] in colors else None
        spot = E._guess_meeple_spot(tt[b], t["rotation"], m["spot"]) if who is not None else None
        state.place_tile(tt[b], t["location"]["x"], t["location"]["y"], t["rotation"], who, spot)

    # tuile de départ puis tuiles absentes du journal
    pending = sorted(first, key=lambda b: (board[b]["location"]["x"], board[b]["location"]["y"]) != (0, 0))
    while pending:
        for b in pending:
            t = board[b]
            if not g.board or g.can_place(tt[b], t["location"]["x"], t["location"]["y"], t["rotation"]):
                put(g, b, True); pending.remove(b); break
        else:
            return []
    examples = []
    for i, b in enumerate(order):
        t = board[b]
        g.current_tile = tt[b]
        g.draw_pile = [tt[o] for o in order[i + 1:]]
        mover = next((k for k, p in enumerate(data["players"]) if p["name"] ==
                      data["moveLog"][[m.get("bgId") for m in data["moveLog"]].index(b)]["player"]), 0)
        for k in (range(4) if augment else [0]):
            st = replay_bga.rotate_state(g, k)
            mx, my = t["location"]["x"], t["location"]["y"]
            for _ in range(k):
                mx, my = -my, mx
            d = E._state_to_dict(st, mover)
            grid = encode_board(d, mover)
            locs = [(q["location"]["x"], q["location"]["y"]) for q in d["board"]]
            cx = sum(x for x, _ in locs) / len(locs); cy = sum(y for _, y in locs) / len(locs)
            gx, gy = int(mx - cx + GRID_CENTER), int(my - cy + GRID_CENTER)
            policy = np.zeros(GRID_SIZE * GRID_SIZE, dtype=np.float32)
            if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
                policy[gy * GRID_SIZE + gx] = 1.0
            examples.append((grid, np.zeros(NUM_SCALAR_FEATURES, dtype=np.float32), -1.0, policy, mover))
        put(g, b, True)
    return examples


def _get_label(player_idx: int, winners: list) -> float:
    """Retourne le label pour un joueur donné."""
    if len(winners) > 1 and player_idx in winners:
        return 0.5  # égalité
    elif player_idx in winners:
        return 1.0
    else:
        return 0.0


def generate_from_replay(json_path: str) -> list:
    """
    Génère des données depuis un replay complet avec moveLog.
    Reconstruit le plateau étape par étape.
    
    Pour l'instant, génère un seul exemple depuis la position finale.
    TODO: reconstruire chaque étape intermédiaire.
    """
    return generate_training_data(json_path)


# ============================================================
# RÉSEAU DE NEURONES
# ============================================================

def build_model(n_rot: int = POLICY_ROTATIONS):
    """
    Construit le modèle PyTorch avec deux têtes :
    - Value head : probabilité de victoire (scalaire 0-1)
    - Policy head : probabilité de jouer sur chaque case (grille 25x25)
    """
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError:
        print("❌ PyTorch requis. Installez-le avec:")
        print("   pip install torch")
        sys.exit(1)

    class CarcassonneNet(nn.Module):
        def __init__(self):
            super().__init__()

            # === Tronc commun (shared backbone) ===
            self.conv1 = nn.Conv2d(NUM_CHANNELS, 48, kernel_size=3, padding=1)
            self.conv2 = nn.Conv2d(48, 96, kernel_size=3, padding=1)
            self.conv3 = nn.Conv2d(96, 96, kernel_size=3, padding=1)
            self.conv4 = nn.Conv2d(96, 64, kernel_size=3, padding=1)
            self.bn1 = nn.BatchNorm2d(48)
            self.bn2 = nn.BatchNorm2d(96)
            self.bn3 = nn.BatchNorm2d(96)
            self.bn4 = nn.BatchNorm2d(64)

            # Branche scalaire
            self.scalar_fc = nn.Linear(NUM_SCALAR_FEATURES, 48)

            # === Value head (qui va gagner ?) — v27 : tête compacte ===
            # Avant (v26) : 625 cases aplaties + 48 → 128 → 1, soit ~86 000 poids,
            # assez pour apprendre par cœur ~150 parties (validation ≥ 0.693).
            # Maintenant : 16 « détecteurs » résumés par moyenne et maximum sur le
            # plateau (32 nombres) + 48 scalaires → 32 → 1, soit ~3 000 poids.
            self.value_conv = nn.Conv2d(64, 16, kernel_size=1)
            self.value_bn = nn.BatchNorm2d(16)
            self.value_fc1 = nn.Linear(16 * 2 + 48, 32)
            self.value_fc2 = nn.Linear(32, 1)
            self.value_dropout = nn.Dropout(0.5)
            # Si True, la value n'entraîne pas le tronc commun (gradient arrêté) :
            # le tronc est façonné par la policy, qui généralise ; la value
            # apprend à lire ces mêmes caractéristiques sans pouvoir les déformer.
            self.value_detach = False

            # === Policy head (où jouer ?) ===
            self.policy_conv1 = nn.Conv2d(64, 32, kernel_size=3, padding=1)
            self.policy_bn = nn.BatchNorm2d(32)
            # v28 : n_rot cartes (une par rotation de la tuile) au lieu d'une seule
            self.n_rot = n_rot
            self.policy_conv2 = nn.Conv2d(32, n_rot, kernel_size=1)

            self.relu = nn.ReLU()
            self.dropout = nn.Dropout(0.3)

        def forward(self, grid, scalars):
            # Tronc commun
            x = self.relu(self.bn1(self.conv1(grid)))
            x = self.relu(self.bn2(self.conv2(x)))
            x = self.relu(self.bn3(self.conv3(x)))
            x = self.relu(self.bn4(self.conv4(x)))
            # x shape: (batch, 64, 25, 25)

            # Branche scalaire
            s = self.relu(self.scalar_fc(scalars))
            # s shape: (batch, 48)

            # === Value head ===
            xv = x.detach() if self.value_detach else x
            v = self.relu(self.value_bn(self.value_conv(xv)))   # (batch, 16, 25, 25)
            v_mean = v.mean(dim=(2, 3))                          # (batch, 16)
            v_max = v.amax(dim=(2, 3))                           # (batch, 16)
            v = torch.cat([v_mean, v_max, s], dim=1)             # (batch, 80)
            v = self.value_dropout(self.relu(self.value_fc1(v)))
            value = torch.sigmoid(self.value_fc2(v))
            # value shape: (batch, 1)

            # === Policy head ===
            p = self.relu(self.policy_bn(self.policy_conv1(x)))
            p = self.policy_conv2(p)  # (batch, n_rot, 25, 25)
            p = p.view(p.size(0), -1)  # (batch, n_rot × 625), indice = rot × 625 + case
            # Masquer les cases non jouables (occupées) avec le canal 9 (libres),
            # pour chacune des rotations
            mask = grid[:, 9, :, :].reshape(grid.size(0), -1).repeat(1, self.n_rot)
            p = p.masked_fill(mask == 0, float('-inf'))
            policy = torch.softmax(p, dim=1)
            # policy shape: (batch, n_rot × 625) — probabilité de chaque (rotation, case)

            return value, policy

    return CarcassonneNet()


# ============================================================
# ENTRAÎNEMENT
# ============================================================

def train(data_dir: str, model_path: str = "carcassonne_model.pt",
          epochs: int = 100, lr: float = 0.001, legacy: bool = False,
          value_detach: bool = True, keep_split: bool = True):
    """Entraîne le modèle sur des parties JSON."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    print("=" * 50)
    print("🏰 Entraînement du réseau de neurones")
    print("=" * 50)

    # Collecter les données
    all_grids = []
    all_scalars = []
    all_labels = []
    all_policies = []

    json_files = list(Path(data_dir).glob("*.json"))
    print(f"  Fichiers trouvés: {len(json_files)}")

    skipped_equal = 0
    skipped_zero = 0
    skipped_error = 0
    skipped_legacy = 0
    n_v2 = 0
    n_legacy = 0
    all_games = []

    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                check_data = json.load(f)
            players = check_data.get("players", [])
            if len(players) < 2:
                skipped_error += 1
                continue
            scores = [p.get("score", 0) for p in players]

            # Filtrer les parties avec scores identiques (vrais égalités ou erreurs)
            if scores[0] == scores[1]:
                skipped_equal += 1
                continue
            # Filtrer les parties avec tous les scores à 0
            if all(s == 0 for s in scores):
                skipped_zero += 1
                continue

            if check_data.get("rawLog"):
                examples = generate_training_data_v2(str(jf))
                n_v2 += 1
            elif legacy:
                examples = generate_policy_only_legacy(str(jf))
                n_legacy += 1 if examples else 0
            else:
                skipped_legacy += 1
                continue
            for grid, scalars, label, policy, _ in examples:
                all_games.append(jf.name)
                all_grids.append(grid.astype(np.float16))   # v28 : float16 dès la collecte
                all_scalars.append(scalars)
                all_labels.append(label)
                all_policies.append(_to_target(policy))
        except Exception as e:
            print(f"  ⚠️ {jf.name}: {type(e).__name__}: {e}")
            skipped_error += 1

    print(f"  Parties rejouées exactement (rawLog): {n_v2}")
    if legacy:
        print(f"  Anciens exports utilisés pour la policy seule: {n_legacy}")
    elif skipped_legacy:
        print(f"  Anciens exports sans rawLog ignorés: {skipped_legacy} "
              f"(--legacy pour les utiliser en policy seule)")
    if skipped_equal or skipped_zero or skipped_error:
        print(f"  Parties ignorées: {skipped_equal} scores égaux, {skipped_zero} scores à 0, {skipped_error} erreurs")

    if not all_grids:
        print("❌ Aucune donnée d'entraînement trouvée.")
        return

    print(f"  Exemples d'entraînement: {len(all_grids)}")
    print(f"  Avec cible value: {sum(1 for l in all_labels if l >= 0)}")
    print(f"  Positions gagnantes (cible > 0.5): {sum(1 for l in all_labels if l > 0.5)}")
    print(f"  Positions perdantes (cible < 0.5): {sum(1 for l in all_labels if 0 <= l < 0.5)}")
    n_with_policy = sum(1 for c, _ in all_policies if c >= 0)
    n_with_rot = sum(1 for c, r in all_policies if c >= 0 and r >= 0)
    print(f"  Avec policy target: {n_with_policy} (dont rotation connue : {n_with_rot})")
    tot = ROT_CHECK["ok"] + ROT_CHECK["eq"] + ROT_CHECK["ko"]
    if tot:
        print(f"  Contrôle des rotations : {ROT_CHECK['ok']}/{tot} légales telles quelles, "
              f"{ROT_CHECK['eq']} ramenées à une rotation équivalente (tuile symétrique)"
              + ("" if ROT_CHECK["ko"] == 0 else
                 f"  ⚠️ {ROT_CHECK['ko']} sans équivalent (traitées comme inconnues)"))

    # Convertir en tenseurs (grilles stockées en float16 : ~4x moins de RAM ;
    # 200 parties ≈ 110 000 exemples ≈ 3 Go en float16 au lieu de 6,5 Go)
    # v28 : remplissage d'un tenseur réservé d'avance, en libérant la liste au
    # fur et à mesure → pas de double copie au moment de la conversion.
    n_ex = len(all_grids)
    grids_tensor = torch.empty((n_ex, NUM_CHANNELS, GRID_SIZE, GRID_SIZE), dtype=torch.float16)
    for i in range(n_ex):
        grids_tensor[i] = torch.from_numpy(all_grids[i])
        all_grids[i] = None
    del all_grids
    print(f"  Mémoire des plateaux : {grids_tensor.numel() * 2 / 1e9:.1f} Go")
    scalars_tensor = torch.FloatTensor(np.array(all_scalars))
    labels_tensor = torch.FloatTensor(all_labels).unsqueeze(1)
    # v28 : cibles policy compactes (case, rotation) au lieu de vecteurs de 625
    policies_tensor = torch.tensor(all_policies, dtype=torch.long)

    # Validation : 10 % des PARTIES mises de côté (jamais vues à l'entraînement)
    import random as _r
    games = sorted(set(all_games)); _r.Random(0).shuffle(games)
    val_games = set(games[:max(1, len(games) // 10)]) if len(games) >= 5 else set()
    # v27 : validation FIGÉE. Si une liste de validation existe déjà (fichier
    # <modèle>.validation.json), on reprend exactement ces parties : ajouter des
    # parties au dossier ne change pas l'« examen », et les résultats restent
    # comparables d'un entraînement à l'autre. --new-split pour refaire un tirage.
    val_file = Path(model_path).with_suffix(".validation.json")
    if keep_split and val_file.exists():
        try:
            kept = set(json.load(open(val_file, encoding="utf-8"))) & set(games)
            if len(kept) >= 5:
                val_games = kept
                print(f"  Validation figée : {len(kept)} parties reprises de {val_file.name}")
        except (OSError, ValueError):
            pass
    is_val = torch.tensor([g in val_games for g in all_games])
    tr = ~is_val
    # v28 : Subset au lieu de grids_tensor[tr], qui COPIAIT tous les plateaux
    # d'entraînement (une seconde fois toute la mémoire).
    from torch.utils.data import Subset
    tr_idx = torch.nonzero(tr, as_tuple=False).squeeze(1).tolist()
    dataset = Subset(TensorDataset(grids_tensor, scalars_tensor, labels_tensor, policies_tensor), tr_idx)
    loader = DataLoader(dataset, batch_size=128, shuffle=True)
    val = (grids_tensor[is_val], scalars_tensor[is_val], labels_tensor[is_val], policies_tensor[is_val])
    print(f"  Validation: {len(val_games)} parties, {int(is_val.sum())} exemples")
    # liste des parties de validation, pour evaluate_model.py
    try:
        with open(Path(model_path).with_suffix(".validation.json"), "w", encoding="utf-8") as f:
            json.dump(sorted(val_games), f, ensure_ascii=False, indent=1)
    except OSError:
        pass
    # Choix du meilleur modèle : tant qu'il y a moins de 5 parties rejouées en
    # validation, la perte value est trop bruitée → on choisit sur la policy seule.
    val_value_games = {g for g, l in zip(all_games, all_labels) if g in val_games and l >= 0}
    # La value ne généralise pas encore (perte de validation ≥ 0.693, le niveau
    # d'une réponse constante « 50 % ») : le meilleur modèle est choisi sur la
    # policy. La value est affichée pour suivi, avec ce repère.
    select_on_policy = True
    print(f"  Parties de validation avec cible value: {len(val_value_games)} "
          f"(repère value : 0.693 = réponse constante 50 %)")
    print(f"  Meilleur modèle choisi sur la policy")

    def policy_loss_sum(policy_pred, pol):
        """Somme des pertes policy et compteurs top-1 / top-3.
        pol : (batch, 2) = (case, rotation), -1 si inconnue.
        - rotation connue : -log p(rotation, case) ;
        - rotation inconnue : -log p(case), toutes rotations additionnées.
        Compteurs : « case » (rotations additionnées, comparable aux versions
        précédentes) et « coup complet » (case + rotation, si la rotation est connue)."""
        nr = policy_pred.size(1) // NUM_CELLS
        cell, rot = pol[:, 0], pol[:, 1]
        has = cell >= 0
        stats = {"n": 0, "c1": 0.0, "c3": 0.0, "f1": 0.0, "f3": 0.0, "fn": 0}
        if not has.any():
            return torch.tensor(0.0), stats
        pp, c, r = policy_pred[has], cell[has], rot[has]
        pcell = pp.view(-1, nr, NUM_CELLS).sum(dim=1)               # (n, 625)
        known = r >= 0
        full_idx = (r.clamp(min=0) * NUM_CELLS + c)
        p_full = pp.gather(1, full_idx.unsqueeze(1)).squeeze(1)
        p_cell = pcell.gather(1, c.unsqueeze(1)).squeeze(1)
        prob = torch.where(known, p_full, p_cell)
        loss = -torch.log(prob + 1e-8).sum()
        topc = pcell.topk(3, dim=1).indices
        stats["n"] = int(has.sum())
        stats["c1"] = float((topc[:, 0] == c).sum())
        stats["c3"] = float((topc == c.unsqueeze(1)).any(dim=1).sum())
        if known.any() and nr > 1:
            topf = pp[known].topk(3, dim=1).indices
            fi = full_idx[known]
            stats["f1"] = float((topf[:, 0] == fi).sum())
            stats["f3"] = float((topf == fi.unsqueeze(1)).any(dim=1).sum())
            stats["fn"] = int(known.sum())
        return loss, stats

    def losses(model, g, sc, lab, pol):
        """(value_loss, policy_loss, top-1, top-3) — value ignorée si cible < 0.
        v27 : à l'entraînement, chaque position pèse 0.25 + 0.75 × avancement
        (scalaire 7 = tuiles posées / 72) : en début de partie l'issue est presque
        imprévisible, ces positions poussent surtout à apprendre par cœur."""
        value_pred, policy_pred = model(g.float(), sc)
        w = (lab >= 0).float() * (0.25 + 0.75 * sc[:, 7:8].clamp(0, 1))
        bce = nn.functional.binary_cross_entropy(value_pred, lab.clamp(min=0), reduction="none")
        v = (bce * w).sum() / w.sum().clamp(min=1)
        pl, _ = policy_loss_sum(policy_pred, pol)
        n = int((pol[:, 0] >= 0).sum())
        return v, (pl / max(n, 1)) if n else torch.tensor(0.0), 0.0, 0.0

    def evaluate_val(model):
        """Pertes de validation pondérées correctement : la value n'est moyennée
        que sur les exemples qui ont une cible value, la policy sur ceux qui ont
        une cible policy (v25 : moyenne par paquet → value sous-estimée)."""
        model.eval()
        sv = sw = sp = sn = s1 = s3 = f1 = f3 = fn = 0.0
        with torch.no_grad():
            for i in range(0, len(val[0]), 256):
                g, sc, lab, pol = [t[i:i + 256] for t in val]
                value_pred, policy_pred = model(g.float(), sc)
                w = (lab >= 0).float()
                bce = nn.functional.binary_cross_entropy(value_pred, lab.clamp(min=0), reduction="none")
                sv += float((bce * w).sum()); sw += float(w.sum())
                pl, st_ = policy_loss_sum(policy_pred, pol)
                sp += float(pl); sn += st_["n"]
                s1 += st_["c1"]; s3 += st_["c3"]; f1 += st_["f1"]; f3 += st_["f3"]; fn += st_["fn"]
        model.train()
        return (sv / max(sw, 1), sp / max(sn, 1), s1 / max(sn, 1), s3 / max(sn, 1),
                f1 / max(fn, 1), f3 / max(fn, 1))

    # Modèle
    model = build_model()
    model.value_detach = value_detach
    print(f"  Tête value : compacte (~3 000 poids)"
          + (", sans influence sur le tronc commun (gradient arrêté)" if value_detach
             else ", entraînée avec le tronc commun (--value-joint)"))
    best_value, best_value_epoch = float("inf"), 0
    value_path = str(Path(model_path).with_suffix(".value.pt"))
    # AdamW (pénalité sur les poids) + taux d'apprentissage décroissant (cosinus) :
    # retarde l'apprentissage par cœur observé dès l'époque 10.
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    patience, since_best = 4, 0

    print(f"\n  Entraînement: {epochs} époques max, lr={lr} (décroissant), arrêt après "
          f"{patience} époques sans progrès en validation")
    print(f"  Loss = value_loss + 0.5 * policy_loss")

    best = float("inf")
    for epoch in range(epochs):
        total_vloss = 0
        total_ploss = 0
        n_batches = 0

        for batch_grids, batch_scalars, batch_labels, batch_policies in loader:
            optimizer.zero_grad()
            v_loss, p_loss, _, _ = losses(model, batch_grids, batch_scalars,
                                          batch_labels, batch_policies)
            loss = v_loss + 0.5 * p_loss
            loss.backward()
            optimizer.step()
            total_vloss += v_loss.item()
            total_ploss += p_loss.item()
            n_batches += 1
        scheduler.step()

        avg_vloss = total_vloss / max(n_batches, 1)
        avg_ploss = total_ploss / max(n_batches, 1)
        msg = f"  Époque {epoch+1:4d}/{epochs}: value_loss={avg_vloss:.4f}  policy_loss={avg_ploss:.4f}"
        if len(val[0]):
            vv, vp, t1, t3, ft1, ft3 = evaluate_val(model)
            msg += (f"  | VALIDATION value={vv:.4f} policy={vp:.4f} case top1={t1:.0%} top3={t3:.0%}"
                    f"  coup top1={ft1:.0%} top3={ft3:.0%}")
            if vv < best_value:
                best_value, best_value_epoch = vv, epoch + 1
                torch.save(model.state_dict(), value_path)
                msg += "  ★value"
            score = vp if select_on_policy else vv + 0.5 * vp
            if score < best:
                best, since_best = score, 0
                torch.save(model.state_dict(), model_path)
                msg += "  💾"
            else:
                since_best += 1
            print(msg, flush=True)
            if since_best >= patience:
                print(f"  ⏹️ Arrêt : pas de progrès en validation depuis {patience} époques")
                break
        else:
            print(msg, flush=True)

    # Sauvegarder : le meilleur modèle en validation (💾) a déjà été écrit ;
    # sans parties de validation, on garde le dernier.
    if not len(val[0]):
        torch.save(model.state_dict(), model_path)
    print(f"\n✅ Modèle sauvegardé: {model_path}"
          + (f" (meilleure validation, loss={best:.4f})" if len(val[0]) else ""))
    print(f"   Taille: {os.path.getsize(model_path) / 1024:.1f} KB")
    if len(val[0]) and best_value_epoch:
        verdict = ("meilleure qu'une réponse constante 50 %" if best_value < 0.693
                   else "pas mieux qu'une réponse constante 50 % : garder use_value=False")
        print(f"   Meilleure value en validation : {best_value:.4f} (époque {best_value_epoch}) — {verdict}")
        print(f"   Modèle de cette époque : {value_path}")


# ============================================================
# ÉVALUATION AVEC LE RÉSEAU
# ============================================================

def evaluate_position(state_dict: dict, player_idx: int = 0,
                      model_path: str = "carcassonne_model.pt") -> float:
    """
    Évalue une position avec le réseau de neurones.
    
    Returns:
        float entre 0 et 1 (probabilité de victoire)
    """
    import torch

    state = torch.load(model_path, weights_only=True)
    model = build_model(int(state["policy_conv2.weight"].shape[0]))
    model.load_state_dict(state)
    model.eval()

    grid = encode_board(state_dict, player_idx)
    scalars = encode_scalar_features(state_dict, player_idx)

    with torch.no_grad():
        grid_tensor = torch.FloatTensor(grid).unsqueeze(0)
        scalars_tensor = torch.FloatTensor(scalars).unsqueeze(0)
        value, policy = model(grid_tensor, scalars_tensor)

    return value.item()


# ============================================================
# INTÉGRATION AVEC LE MCTS
# ============================================================


def _state_key(state_dict: dict) -> tuple:
    """Clé de cache qui identifie VRAIMENT la position.
    (v10 : clé = scores + meeples dispo + nb de tuiles → presque tous les coups
     candidats d'une même analyse recevaient la même valeur, et le cache
     renvoyait des valeurs issues d'autres parties.)"""
    tiles = []
    for t in state_dict.get("board", []):
        loc = t.get("location") or {}
        m = t.get("meeple") or {}
        tiles.append((loc.get("x"), loc.get("y"), t.get("edges"), t.get("shield", False),
                      m.get("color"), m.get("spot")))
    players = tuple((p.get("score", 0), p.get("meeplesAvailable", 0))
                    for p in state_dict.get("players", []))
    return (players, tuple(sorted(tiles, key=str)), state_dict.get("remainingCount"))


class NeuralEvaluator:
    """
    Remplace l'heuristique dans le MCTS par le réseau de neurones.
    Fournit à la fois l'évaluation de position (value) et la suggestion
    de coup (policy) pour guider l'exploration du MCTS.
    """
    def __init__(self, model_path: str = "carcassonne_model.pt", use_value: bool = False):
        import torch
        self.torch = torch
        # use_value=False : le MCTS n'utilise que la POLICY du réseau (pour choisir
        # quels coups explorer) et garde l'heuristique + rollouts pour évaluer.
        # À passer à True quand evaluate_model.py montrera une value fiable.
        self.use_value = use_value
        state = torch.load(model_path, weights_only=True)
        # v28 : modèle à 4 rotations ou ancien modèle à une seule carte ?
        self.n_rot = int(state["policy_conv2.weight"].shape[0]) if "policy_conv2.weight" in state else POLICY_ROTATIONS
        self.model = build_model(self.n_rot)
        own = self.model.state_dict()
        skipped = [k for k, v in state.items() if k in own and own[k].shape != v.shape]
        state = {k: v for k, v in state.items() if k not in skipped}
        self.model.load_state_dict(state, strict=False)
        if skipped:
            # Modèle d'avant la v27 : tronc et policy chargés, tête value à réentraîner.
            print(f"⚠️ Ancien modèle : tête value ignorée ({len(skipped)} tenseurs), "
                  f"policy conservée. Réentraînez pour une value v27.")
            self.use_value = False
        self.model.eval()
        self.cache = {}
        print(f"🧠 Réseau chargé : {model_path} — "
              + ("policy + value" if use_value else "policy seule (évaluation heuristique)"))

    def evaluate(self, state_dict: dict, player_idx: int = 0) -> float:
        """Évalue la position (value head). Retourne probabilité de victoire."""
        cache_key = ("value", _state_key(state_dict), player_idx)

        if cache_key in self.cache:
            return self.cache[cache_key]

        grid = encode_board(state_dict, player_idx)
        scalars = encode_scalar_features(state_dict, player_idx)

        with self.torch.no_grad():
            grid_tensor = self.torch.FloatTensor(grid).unsqueeze(0)
            scalars_tensor = self.torch.FloatTensor(scalars).unsqueeze(0)
            value, _ = self.model(grid_tensor, scalars_tensor)

        result = value.item()
        if len(self.cache) > 200_000:
            self.cache.clear()
        self.cache[cache_key] = result
        return result

    def _policy_maps(self, state_dict: dict, player_idx: int = 0):
        """Sortie brute de la policy : (tableau (n_rot, 625), cx, cy, cases libres)."""
        grid = encode_board(state_dict, player_idx)
        scalars = encode_scalar_features(state_dict, player_idx)
        board = state_dict.get("board", [])
        locs = [(t["location"]["x"], t["location"]["y"])
                for t in board if t.get("location")]
        if not locs:
            return None
        cx = sum(x for x, y in locs) / len(locs)
        cy = sum(y for x, y in locs) / len(locs)
        with self.torch.no_grad():
            grid_tensor = self.torch.FloatTensor(grid).unsqueeze(0)
            scalars_tensor = self.torch.FloatTensor(scalars).unsqueeze(0)
            _, policy = self.model(grid_tensor, scalars_tensor)
        maps = policy.squeeze(0).numpy().reshape(self.n_rot, NUM_CELLS)
        # Cases réelles libres, converties EXACTEMENT comme à l'encodage
        # (gx = int(x - cx + centre)) — cf. correctif v27.
        occupied = set(locs)
        free = {(x + dx, y + dy) for x, y in locs
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - occupied
        cells = {}
        for rx, ry in free:
            gx = int(rx - cx + GRID_CENTER)
            gy = int(ry - cy + GRID_CENTER)
            if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
                cells[(rx, ry)] = gy * GRID_SIZE + gx
        return maps, cells

    def get_policy(self, state_dict: dict, player_idx: int = 0) -> dict:
        """
        Policy par CASE : {(x, y): probabilité}, rotations additionnées.
        (Même format qu'avant la v28 : utilisable tel quel par le MCTS.)
        """
        out = self._policy_maps(state_dict, player_idx)
        if out is None:
            return {}
        maps, cells = out
        pcell = maps.sum(axis=0)
        result = {}
        for c, idx in cells.items():
            prob = float(pcell[idx])
            if prob > 0.001:  # ignorer les probabilités négligeables
                result[c] = prob
        return result

    def get_policy_rot(self, state_dict: dict, player_idx: int = 0) -> dict:
        """
        v28 — Policy par COUP : {(x, y, rotation): probabilité}.
        Avec un ancien modèle (une seule carte), la probabilité de la case est
        répartie également entre les 4 rotations.
        """
        out = self._policy_maps(state_dict, player_idx)
        if out is None:
            return {}
        maps, cells = out
        result = {}
        for (x, y), idx in cells.items():
            if self.n_rot == 1:
                for r in range(4):
                    result[(x, y, r)] = float(maps[0, idx]) / 4
            else:
                for r in range(self.n_rot):
                    result[(x, y, r)] = float(maps[r, idx])
        return result


# ============================================================
# CLI
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python neural_evaluator.py train <dossier_parties>")
        print("  python neural_evaluator.py eval <position.json>")
        print("  python neural_evaluator.py encode <position.json>")
        print()
        print("Entraînement:")
        print("  1. Exportez vos parties terminées avec l'extension (JSON)")
        print("  2. Placez-les dans un dossier")
        print("  3. Lancez: python neural_evaluator.py train ./mes_parties")
        print()
        print("Le modèle sera sauvegardé dans carcassonne_model.pt")
        sys.exit(1)

    command = sys.argv[1]

    if command == "train":
        data_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        args = [a for a in sys.argv[3:] if not a.startswith("--")]
        epochs = int(args[0]) if args else 100
        train(data_dir, epochs=epochs, legacy="--legacy" in sys.argv,
              value_detach="--value-joint" not in sys.argv,
              keep_split="--new-split" not in sys.argv)

    elif command == "eval":
        json_path = sys.argv[2]
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for i, p in enumerate(data.get("players", [])):
            score = evaluate_position(data, i)
            print(f"{p['name']}: {score:.1%} chance de victoire")

    elif command == "encode":
        json_path = sys.argv[2]
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        grid = encode_board(data, 0)
        scalars = encode_scalar_features(data, 0)
        print(f"Grille: {grid.shape} — {grid.nbytes} bytes")
        print(f"Scalaires: {scalars.shape} — {scalars}")
        # Visualiser les canaux actifs
        for c in range(NUM_CHANNELS):
            active = np.count_nonzero(grid[c])
            names = ["Bord haut", "Bord droit", "Bord bas", "Bord gauche",
                     "Blason", "Monastère", "Mon meeple", "Meeple adverse",
                     "Occupée", "Libre jouable", "Compatible", "Nb voisins"]
            if active > 0:
                print(f"  Canal {c:2d} ({names[c]:15s}): {active} cellules actives")

    else:
        print(f"Commande inconnue: {command}")


if __name__ == "__main__":
    main()
