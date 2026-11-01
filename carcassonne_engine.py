"""
🏰 Carcassonne Engine + Monte Carlo Tree Search
================================================
Moteur de jeu complet pour le jeu de base (72 tuiles).
Peut charger un état depuis le JSON extrait par l'extension Firefox.

Usage:
    python carcassonne_engine.py etat_partie.json
    
Ou en mode interactif:
    python carcassonne_engine.py etat_partie.json --interactive
"""

import json
import sys
import random
import math
import time
from copy import deepcopy
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from functools import lru_cache
import os

# v28 — Guidage du MCTS par la policy du réseau :
#   "rotation" : une note par (case, rotation) si le modèle le permet (v28) ;
#   "case"     : une note par case, comme avant (pour comparer).
# Réglable sans toucher au code : variable d'environnement CARCASSONNE_POLICY.
POLICY_MODE = os.environ.get("CARCASSONNE_POLICY", "rotation").strip().lower()

# ============================================================
# TILE DEFINITIONS — Jeu de base (24 types, 72 tuiles)
# ============================================================
# Edges: T R B L  —  C=City, F=Field, R=Road
# monastery: True si la tuile contient un monastère
# shield: True si blason
# connected_city: True si les segments ville sont connectés entre eux
#   (ex: CFFC avec connected_city=True = ville en angle continue,
#    CFFC avec connected_city=False = deux villes séparées sur T et L)

@dataclass
class TileType:
    edges: str          # "CRFR" = City top, Road right, Field bottom, Road left
    count: int
    shield: bool = False
    monastery: bool = False
    connected_city: list = field(default_factory=list)
    # connected_city: liste de sets de côtés connectés
    # ex: [{0,3}] = les côtés 0(top) et 3(left) forment une seule ville
    # ex: [{0}, {2}] = côtés 0 et 2 sont deux villes séparées
    field_segments: list = field(default_factory=list)
    # field_segments: liste de sets de "demi-côtés" connectés dans le même champ
    # Chaque bord a 2 demi-côtés: bord 0 (haut) → demi-côtés 0L et 0R (gauche et droite)
    # Numérotation: bord i → demi-côté 2*i (gauche en regardant vers l'extérieur) 
    #                         et 2*i+1 (droite)
    # Haut:   0L=7(coin haut-gauche), 0R=0(coin haut-droit)
    # Droite: 1L=1(coin haut-droit),  1R=2(coin bas-droit)
    # Bas:    2L=3(coin bas-droit),   2R=4(coin bas-gauche)
    # Gauche: 3L=5(coin bas-gauche),  3R=6(coin haut-gauche)
    #
    # Coins: 0=haut-droit, 1=haut-droit(=0), 2=bas-droit, 3=bas-droit(=2),
    #        4=bas-gauche, 5=bas-gauche(=4), 6=haut-gauche, 7=haut-gauche(=6)
    # Simplifié en 8 points de connexion numérotés en sens horaire depuis haut-droit:
    #   0: entre haut et droite (coin haut-droit)
    #   1: identique à 0 si pas de ville/route dans le coin
    #   ...
    # 
    # En pratique, on utilise 8 "field nodes" aux coins/demi-côtés:
    #   Node 0: haut-droit du bord haut = gauche du bord droit
    #   Node 1: droite du bord droit = haut du bord bas  (coin bas-droit)
    #   Node 2: bas du bord bas = droite du bord gauche  (coin bas-gauche)
    #   Node 3: gauche du bord gauche = haut-gauche      (coin haut-gauche)
    # Mais c'est plus subtil: chaque bord "Field" contribue à 2 field nodes,
    # chaque bord "Road" sépare 2 field nodes, chaque bord "City" ne contribue pas.


# ============================================================
# FIELD SEGMENT SYSTEM
# ============================================================
# Chaque tuile a des "field points" aux 4 coins.
# Deux field points sont dans le même segment de champ s'ils ne sont 
# pas séparés par une route ou une ville.
#
# Convention des 8 demi-côtés (en sens horaire):
#   0: côté haut, partie droite
#   1: côté droit, partie haute
#   2: côté droit, partie basse
#   3: côté bas, partie droite
#   4: côté bas, partie gauche
#   5: côté gauche, partie basse
#   6: côté gauche, partie haute
#   7: côté haut, partie gauche
#
# Deux demi-côtés adjacents sur le même bord sont connectés SI le bord est F (champ).
# Deux demi-côtés de bords adjacents au même coin sont connectés 
# s'il n'y a pas de ville/route qui les sépare.

def _hs_side(hs: int) -> int:
    """Bord (0-3) qui porte le demi-côté hs.  7,0→0  1,2→1  3,4→2  5,6→3"""
    return ((hs + 1) // 2) % 4


def _city_groups(edges: str, connected_city) -> list:
    """Groupes ville ; par défaut (TileType ad hoc) chaque bord C est isolé."""
    groups = [frozenset(g) for g in (connected_city or [])]
    covered = set().union(*groups) if groups else set()
    groups += [frozenset({s}) for s in range(4) if edges[s] == "C" and s not in covered]
    return groups


def _compute_field_segments(edges: str, connected_city: list) -> list:
    """
    Calcule les segments de champ d'une tuile (frozensets de demi-côtés 0-7).

    Convention (sens horaire) : 0 haut-droite, 1 droite-haut, 2 droite-bas,
    3 bas-droite, 4 bas-gauche, 5 gauche-bas, 6 gauche-haut, 7 haut-gauche.
    Le bord s porte les demi-côtés (2s-1)%8 et 2s ; le coin c (entre les bords
    c et c+1) porte les demi-côtés 2c et 2c+1.
    """
    key = (edges, tuple(sorted(tuple(sorted(g)) for g in (connected_city or []))))
    return _field_segments_cached(*key)


@lru_cache(maxsize=None)
def _field_segments_cached(edges: str, cc_key: tuple) -> list:
    groups = _city_groups(edges, [set(g) for g in cc_key])
    parent = list(range(8))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def is_field_hs(hs):
        return edges[_hs_side(hs)] != "C"

    # Règle 1 : coin entre deux bords non-ville (F ou R) → champ continu au coin
    for c in range(4):
        if edges[c] != "C" and edges[(c + 1) % 4] != "C":
            union(2 * c, 2 * c + 1)

    # Règle 2 : les deux demi-côtés d'un bord F sont dans le même champ
    for s in range(4):
        if edges[s] == "F":
            union((2 * s - 1) % 8, 2 * s)

    # Règle 3 (manquante dans la v23) : le champ passe DERRIÈRE une ville
    # qui occupe un seul bord (« cap ») ou deux bords adjacents (« angle »).
    # Il relie le demi-côté juste avant l'arc de ville et celui juste après.
    # Ex. CRFR : la bande de champ entre la ville et la route relie 6 et 1.
    for g in groups:
        g = sorted(g)
        if len(g) == 1:
            first = last = g[0]
        elif len(g) == 2 and (g[1] - g[0]) % 4 == 1:
            first, last = g[0], g[1]
        elif len(g) == 2 and (g[0] - g[1]) % 4 == 1:   # {0,3} → arc 3→0
            first, last = g[1], g[0]
        else:
            continue  # villes opposées (FCFC), 3 ou 4 côtés : rien derrière
        hs_before = (2 * first - 2) % 8
        hs_after = (2 * last + 1) % 8
        if is_field_hs(hs_before) and is_field_hs(hs_after):
            union(hs_before, hs_after)

    segments = defaultdict(set)
    for hs in range(8):
        if is_field_hs(hs):
            segments[find(hs)].add(hs)
    # ordre déterministe : par plus petit demi-côté
    return sorted((frozenset(s) for s in segments.values()), key=min)


def _segment_city_sides(edges: str, seg) -> set:
    """Bords ville de la tuile qui touchent le segment de champ `seg`.
    Un bord ville s touche le champ qui contient l'un de ses deux demi-côtés
    flanquants : (2s-2)%8 (bord précédent) ou (2s+1)%8 (bord suivant)."""
    return {s for s in range(4)
            if edges[s] == "C" and ((2 * s - 2) % 8 in seg or (2 * s + 1) % 8 in seg)}


def tile_field_segments(tile) -> list:
    """Segments de champ d'une PlacedTile (repère tourné), mis en cache par tuile."""
    d = getattr(tile, "__dict__", None)
    if d is None:
        return _compute_field_segments(tile.edges, tile.connected_city)
    c = d.get("_fs")
    if c is None or c[0] != tile.rotation:
        c = (tile.rotation, _compute_field_segments(tile.edges, tile.connected_city))
        d["_fs"] = c
    return c[1]


def _farmer_segment(tile):
    """Segment de champ occupé par le paysan de la tuile, ou None.
    meeple_spot = "field_<hs>" (nouveau format) ou "field" (ancien format :
    on prend alors le plus grand segment, faute de mieux)."""
    spot = tile.meeple_spot
    if tile.meeple_player is None or not spot or not spot.startswith("field"):
        return None
    segs = tile_field_segments(tile)
    if not segs:
        return None
    if spot == "field":
        return max(segs, key=len)
    hs = int(spot.split("_")[1])
    for s in segs:
        if hs in s:
            return s
    return None


HS_NAMES = {0: "haut-droite", 1: "droite-haut", 2: "droite-bas", 3: "bas-droite",
            4: "bas-gauche", 5: "gauche-bas", 6: "gauche-haut", 7: "haut-gauche"}


def describe_field_spot(edges: str, connected_city, spot: str) -> str:
    """Libellé lisible d'un spot paysan, ex. 'champ (haut-droite, droite-haut)'."""
    try:
        hs = int(spot.split("_")[1])
    except (IndexError, ValueError):
        return "champ"
    for seg in _compute_field_segments(edges, connected_city):
        if hs in seg:
            return "champ (" + ", ".join(HS_NAMES[h] for h in sorted(seg)) + ")"
    return "champ"


# Mapping: demi-côté → son correspondant sur la tuile adjacente
# Quand deux tuiles sont adjacentes, les demi-côtés du champ se connectent:
# Bord haut (side 0): nos demi-côtés 7(gauche) et 0(droite) 
#   → tuile au-dessus, bord bas (side 2): demi-côtés 4(droite) et 3(gauche)
# Donc: notre hs 7 ↔ voisin hs 4, notre hs 0 ↔ voisin hs 3
# Mapping et constantes field déplacés après les constantes directionnelles ci-dessous


def rotate_field_segments(segments: list, rotation: int) -> list:
    """Tourne les segments de champ."""
    r = rotation % 4
    if r == 0:
        return segments
    return [frozenset((hs + 2 * r) % 8 for hs in seg) for seg in segments]

# Tous les types de tuiles du jeu de base
TILE_TYPES = [
    # Monastères
    TileType("FFFF", 4, monastery=True),
    TileType("FFRF", 2, monastery=True),
    # Ville 1 côté
    TileType("CFFF", 5, connected_city=[{0}]),
    # Ville 1 côté + routes
    TileType("CRFR", 4, connected_city=[{0}]),   # route traversante
    TileType("CFRR", 3, connected_city=[{0}]),   # virage route droite
    TileType("CRRF", 3, connected_city=[{0}]),   # virage route gauche
    TileType("CRRR", 3, connected_city=[{0}]),   # carrefour 3 routes
    # Ville 2 côtés séparés
    TileType("CFCF", 3, connected_city=[{0}, {2}]),  # opposés séparés
    TileType("CFFC", 2, connected_city=[{0}, {3}]),   # adjacents séparés (T et L)
    # Ville 2 côtés opposés connectés
    TileType("FCFC", 1, connected_city=[{1, 3}]),
    TileType("FCFC", 2, shield=True, connected_city=[{1, 3}]),
    # Ville 2 côtés adjacents connectés (angle)
    TileType("CFFC", 3, connected_city=[{0, 3}]),
    TileType("CFFC", 2, shield=True, connected_city=[{0, 3}]),
    # Ville angle + route
    TileType("CRRC", 3, connected_city=[{0, 3}]),
    TileType("CRRC", 2, shield=True, connected_city=[{0, 3}]),
    # Ville 3 côtés
    TileType("CCFC", 3, connected_city=[{0, 1, 3}]),
    TileType("CCFC", 1, shield=True, connected_city=[{0, 1, 3}]),
    # Ville 3 côtés + route
    TileType("CCRC", 1, connected_city=[{0, 1, 3}]),
    TileType("CCRC", 2, shield=True, connected_city=[{0, 1, 3}]),
    # Ville 4 côtés
    TileType("CCCC", 1, shield=True, connected_city=[{0, 1, 2, 3}]),
    # Routes
    TileType("RFRF", 8),
    TileType("FFRR", 9),
    TileType("FRRR", 4),
    TileType("RRRR", 1),
]

TOP, RIGHT, BOTTOM, LEFT = 0, 1, 2, 3
OPPOSITE = {TOP: BOTTOM, BOTTOM: TOP, LEFT: RIGHT, RIGHT: LEFT}
DIRECTION_NAMES = {TOP: "haut", RIGHT: "droite", BOTTOM: "bas", LEFT: "gauche"}
DX = {TOP: 0, RIGHT: 1, BOTTOM: 0, LEFT: -1}
DY = {TOP: -1, RIGHT: 0, BOTTOM: 1, LEFT: 0}

# Field system: mapping demi-côté → demi-côté correspondant sur la tuile voisine
FIELD_NEIGHBOR_MAP = {
    (0, 7): 4, (0, 0): 3,  # Bord haut
    (1, 1): 6, (1, 2): 5,  # Bord droit
    (2, 3): 0, (2, 4): 7,  # Bord bas
    (3, 5): 2, (3, 6): 1,  # Bord gauche
}

FIELD_HALF_SIDES_FOR_EDGE = {
    0: [7, 0],  # TOP
    1: [1, 2],  # RIGHT
    2: [3, 4],  # BOTTOM
    3: [5, 6],  # LEFT
}


def rotate_edges(edges: str, rotation: int) -> str:
    """Tourne les bords de `rotation` quarts de tour horaire."""
    r = rotation % 4
    return edges[-r:] + edges[:-r] if r else edges


def rotate_connected_city(connected: list, rotation: int) -> list:
    """Tourne les indices de connexion ville."""
    r = rotation % 4
    return [frozenset((side + r) % 4 for side in group) for group in connected]


# ============================================================
# PLACED TILE
# ============================================================
@dataclass
class PlacedTile:
    tile_type: TileType
    x: int
    y: int
    rotation: int
    meeple_player: Optional[int] = None   # index du joueur (0, 1, ...)
    meeple_spot: Optional[str] = None     # "city_0", "road_1", "field", "monastery"

    @property
    def edges(self) -> str:
        # v31 : bords mis en cache (recalculés seulement si la rotation change)
        c = self.__dict__.get("_ec")
        if c is None or c[0] != self.rotation:
            c = (self.rotation, rotate_edges(self.tile_type.edges, self.rotation))
            self.__dict__["_ec"] = c
        return c[1]

    def edge(self, direction: int) -> str:
        return self.edges[direction]

    @property
    def connected_city(self) -> list:
        # v31 : mis en cache comme les bords (ne pas modifier la liste renvoyée)
        c = self.__dict__.get("_cc")
        if c is None or c[0] != self.rotation:
            c = (self.rotation, rotate_connected_city(self.tile_type.connected_city, self.rotation))
            self.__dict__["_cc"] = c
        return c[1]


# ============================================================
# GAME STATE
# ============================================================
class GameState:
    def __init__(self, num_players=2):
        self.num_players = num_players
        self.board: dict[tuple[int, int], PlacedTile] = {}
        self.scores = [0] * num_players
        self.meeples = [7] * num_players  # meeples disponibles
        self.player_names = [f"Joueur {i+1}" for i in range(num_players)]
        self.draw_pile: list[TileType] = []  # tuiles restantes
        self.current_player = 0
        self.current_tile: Optional[TileType] = None
        self.valid_positions: Optional[set] = None  # positions BGA (premier coup seulement)

    def __deepcopy__(self, memo):
        """v31 : copie rapide. Les types de tuiles (TileType) ne changent jamais :
        on les partage au lieu de les dupliquer ; seules les parties modifiables
        de l'état (plateau, scores, meeples, pioche…) sont copiées."""
        from copy import copy as _copy, deepcopy as _deepcopy
        new = GameState.__new__(GameState)
        memo[id(self)] = new
        for k, v in self.__dict__.items():
            if k == "board":
                v = {pos: _copy(t) for pos, t in v.items()}
            elif k in ("draw_pile", "scores", "meeples", "player_names"):
                v = list(v)
            elif k == "valid_positions":
                v = set(v) if v is not None else None
            elif k == "current_tile" or isinstance(v, (int, float, str, bool, type(None))):
                pass
            else:
                v = _deepcopy(v, memo)
            new.__dict__[k] = v
        return new

    def init_draw_pile(self):
        """Initialise la pioche avec toutes les tuiles (moins celles posées)."""
        self.draw_pile = []
        for tt in TILE_TYPES:
            for _ in range(tt.count):
                self.draw_pile.append(tt)
        random.shuffle(self.draw_pile)

    def draw_tile(self) -> Optional[TileType]:
        """Tire une tuile de la pioche."""
        if not self.draw_pile:
            return None
        self.current_tile = self.draw_pile.pop()
        return self.current_tile

    # --- Adjacence et contraintes ---

    def neighbors(self, x: int, y: int) -> dict[int, Optional[PlacedTile]]:
        """Retourne les tuiles adjacentes {direction: PlacedTile ou None}."""
        return {
            TOP: self.board.get((x, y - 1)),
            RIGHT: self.board.get((x + 1, y)),
            BOTTOM: self.board.get((x, y + 1)),
            LEFT: self.board.get((x - 1, y)),
        }

    def get_open_positions(self) -> set[tuple[int, int]]:
        """Positions vides adjacentes à au moins une tuile posée.
        Utilise les positions BGA si disponibles (premier coup uniquement)."""
        if hasattr(self, 'valid_positions') and self.valid_positions is not None:
            # Double sécurité : exclure toute position déjà occupée
            return self.valid_positions - set(self.board.keys())
        if not self.board:
            return {(0, 0)}
        positions = set()
        for (x, y) in self.board:
            for d in (TOP, RIGHT, BOTTOM, LEFT):
                nx, ny = x + DX[d], y + DY[d]
                if (nx, ny) not in self.board:
                    positions.add((nx, ny))
        return positions

    def can_place(self, tile_type: TileType, x: int, y: int, rotation: int) -> bool:
        """Vérifie si une tuile peut être placée à (x,y) avec cette rotation."""
        if (x, y) in self.board:
            return False
        edges = rotate_edges(tile_type.edges, rotation)
        neigh = self.neighbors(x, y)
        has_neighbor = False
        for d, adj in neigh.items():
            if adj is not None:
                has_neighbor = True
                if adj.edge(OPPOSITE[d]) != edges[d]:
                    return False
        return has_neighbor or (not self.board and x == 0 and y == 0)

    def get_legal_placements(self, tile_type: TileType) -> list[tuple[int, int, int]]:
        """Retourne tous les (x, y, rotation) légaux pour un type de tuile."""
        placements = []
        # Pré-calculer les rotations distinctes (évite de tester 4 fois si symétrique)
        distinct_rotations = []
        seen_edges = set()
        for rot in range(4):
            edges = rotate_edges(tile_type.edges, rot)
            if edges not in seen_edges:
                seen_edges.add(edges)
                distinct_rotations.append(rot)

        # v31 : bords exigés par les voisins calculés une fois par case, puis
        # comparés à chaque rotation (même résultat que can_place, 3× plus vite)
        rots = [(rot, rotate_edges(tile_type.edges, rot)) for rot in distinct_rotations]
        board = self.board
        first = not board
        for pos in self.get_open_positions():
            x, y = pos
            if pos in board:
                continue
            req = []
            for d in (TOP, RIGHT, BOTTOM, LEFT):
                adj = board.get((x + DX[d], y + DY[d]))
                if adj is not None:
                    req.append((d, adj.edges[OPPOSITE[d]]))
            if not req and not (first and x == 0 and y == 0):
                continue
            for rot, e in rots:
                for d, v in req:
                    if e[d] != v:
                        break
                else:
                    placements.append((x, y, rot))
        return placements

    # --- Placement ---

    def place_tile(self, tile_type: TileType, x: int, y: int, rotation: int,
                   meeple_player: Optional[int] = None,
                   meeple_spot: Optional[str] = None) -> PlacedTile:
        """Place une tuile et met à jour l'état."""
        placed = PlacedTile(tile_type, x, y, rotation, meeple_player, meeple_spot)
        self.board[(x, y)] = placed

        if meeple_player is not None and meeple_spot is not None:
            self.meeples[meeple_player] -= 1

        # Vérifier les structures complétées
        self._check_completed_structures(x, y)

        return placed

    # --- Scoring ---

    def _get_city_group(self, x: int, y: int, side: int) -> frozenset:
        """Retourne le groupe de connexion ville auquel ce côté appartient."""
        tile = self.board.get((x, y))
        if not tile:
            return frozenset({side})
        for group in tile.connected_city:
            if side in group:
                return group
        return frozenset({side})

    def _trace_structure(self, start_x: int, start_y: int, start_side: int,
                         struct_type: str) -> dict:
        """
        Parcourt une structure (ville ou route) en suivant les connexions.
        Retourne: {tiles: set, complete: bool, shields: int, meeples: {player: count}}
        """
        visited = set()
        to_visit = [(start_x, start_y, start_side)]
        tiles_in_struct = set()
        shields = 0
        meeples = defaultdict(int)
        meeple_tiles = set()   # tuiles dont le meeple appartient à CETTE structure
        complete = True

        while to_visit:
            x, y, side = to_visit.pop()
            if (x, y, side) in visited:
                continue
            visited.add((x, y, side))

            tile = self.board.get((x, y))
            if tile is None:
                complete = False
                continue

            tiles_in_struct.add((x, y))

            # Compter les blasons
            if tile.tile_type.shield and struct_type == "city":
                shields += 1  # sera dédupliqué par tile plus tard

            # Meeple sur cette structure ?
            if tile.meeple_player is not None and tile.meeple_spot is not None:
                if struct_type == "city" and tile.meeple_spot.startswith("city"):
                    # Vérifier que le meeple est sur le bon segment
                    spot_side = int(tile.meeple_spot.split("_")[1])
                    group = self._get_city_group(x, y, side)
                    if spot_side in group:
                        meeple_tiles.add((x, y))
                elif struct_type == "road" and tile.meeple_spot.startswith("road"):
                    spot_side = int(tile.meeple_spot.split("_")[1])
                    road_sides = [i for i, e in enumerate(tile.edges) if e == "R"]
                    # route simple (≤2 côtés) : un seul tronçon sur la tuile ;
                    # carrefour : chaque branche est distincte
                    same_road = (spot_side in road_sides) if len(road_sides) <= 2 \
                                else (spot_side == side)
                    if same_road:
                        meeple_tiles.add((x, y))

            # Trouver les côtés connectés sur la même tuile
            if struct_type == "city":
                group = self._get_city_group(x, y, side)
                for connected_side in group:
                    if (x, y, connected_side) not in visited:
                        visited.add((x, y, connected_side))
                        # Traverser vers la tuile adjacente
                        nx, ny = x + DX[connected_side], y + DY[connected_side]
                        to_visit.append((nx, ny, OPPOSITE[connected_side]))
            elif struct_type == "road":
                # Les routes connectent les côtés selon le type de tuile
                road_sides = [i for i, e in enumerate(tile.edges) if e == "R"]
                # Route droite ou virage: 2 côtés connectés
                # Carrefour: chaque branche est une route séparée
                if len(road_sides) <= 2:
                    for rs in road_sides:
                        if rs != side and (x, y, rs) not in visited:
                            visited.add((x, y, rs))
                            nx, ny = x + DX[rs], y + DY[rs]
                            to_visit.append((nx, ny, OPPOSITE[rs]))
                # Si carrefour (3 ou 4 routes), la route s'arrête ici

            # Traverser vers l'adjacent pour le côté initial
            nx, ny = x + DX[side], y + DY[side]
            if (nx, ny, OPPOSITE[side]) not in visited:
                to_visit.append((nx, ny, OPPOSITE[side]))

        # Dédupliquer les blasons par tuile
        shield_count = sum(1 for (tx, ty) in tiles_in_struct
                          if self.board[(tx, ty)].tile_type.shield)

        for (mx, my) in meeple_tiles:
            meeples[self.board[(mx, my)].meeple_player] += 1

        return {
            "tiles": tiles_in_struct,
            "meeple_tiles": meeple_tiles,
            "sides": frozenset(v for v in visited if (v[0], v[1]) in self.board),
            "complete": complete,
            "shields": shield_count if struct_type == "city" else 0,
            "meeples": dict(meeples),
        }

    def _check_completed_structures(self, x: int, y: int):
        """Vérifie et score les structures complétées autour de (x,y)."""
        tile = self.board[(x, y)]
        edges = tile.edges

        # Vérifier les villes
        checked_city_groups = set()
        for side in range(4):
            if edges[side] == "C":
                group = self._get_city_group(x, y, side)
                group_key = (x, y, group)
                if group_key not in checked_city_groups:
                    checked_city_groups.add(group_key)
                    result = self._trace_structure(x, y, side, "city")
                    if result["complete"]:
                        self._score_structure(result, "city", completed=True)

        # Vérifier les routes
        for side in range(4):
            if edges[side] == "R":
                result = self._trace_structure(x, y, side, "road")
                if result["complete"]:
                    self._score_structure(result, "road", completed=True)

        # Vérifier les monastères (celui-ci et ceux autour)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                mx, my = x + dx, y + dy
                mon_tile = self.board.get((mx, my))
                if mon_tile and mon_tile.tile_type.monastery:
                    # Compter les tuiles autour
                    count = sum(1 for ddx in range(-1, 2) for ddy in range(-1, 2)
                                if (ddx, ddy) != (0, 0) and (mx + ddx, my + ddy) in self.board)
                    if count == 8:  # 8 voisins = monastère complet
                        points = 9
                        if mon_tile.meeple_player is not None and mon_tile.meeple_spot == "monastery":
                            self.scores[mon_tile.meeple_player] += points
                            self.meeples[mon_tile.meeple_player] += 1
                            mon_tile.meeple_player = None
                            mon_tile.meeple_spot = None

    def _score_structure(self, result: dict, struct_type: str, completed: bool):
        """Score une structure et libère les meeples."""
        tiles = result["tiles"]
        meeples = result["meeples"]

        if not meeples:
            return

        # Calculer les points
        if struct_type == "city":
            points_per_tile = 2 if completed else 1
            points = len(tiles) * points_per_tile + result["shields"] * points_per_tile
        elif struct_type == "road":
            points = len(tiles)  # 1 point par tuile (complétée ou non)
        else:
            return

        # Déterminer le(s) propriétaire(s) — majorité de meeples
        max_meeples = max(meeples.values())
        owners = [p for p, count in meeples.items() if count == max_meeples]

        # Chaque propriétaire reçoit les points
        for owner in owners:
            self.scores[owner] += points

        # Libérer tous les meeples (seulement si structure complétée)
        # (v23 libérait tout meeple « ville »/« route » des tuiles de la structure,
        #  y compris celui posé sur une AUTRE ville ou une autre branche de la même tuile)
        if completed:
            for (tx, ty) in result.get("meeple_tiles", ()):
                t = self.board[(tx, ty)]
                if t.meeple_player is not None:
                    self.meeples[t.meeple_player] += 1
                    t.meeple_player = None
                    t.meeple_spot = None

    def final_scoring(self):
        """Score de fin de partie : structures incomplètes + champs."""
        # Structures incomplètes
        scored_tiles_city = set()
        scored_tiles_road = set()

        for (x, y), tile in self.board.items():
            for side in range(4):
                if tile.edges[side] == "C" and (x, y, side) not in scored_tiles_city:
                    result = self._trace_structure(x, y, side, "city")
                    if not result["complete"]:
                        self._score_structure(result, "city", completed=False)
                    # (v23 marquait les 4 côtés de chaque tuile → la 2e ville
                    #  d'une tuile CFCF/CFFC séparée n'était jamais comptée)
                    scored_tiles_city |= result["sides"]

                if tile.edges[side] == "R" and (x, y, side) not in scored_tiles_road:
                    result = self._trace_structure(x, y, side, "road")
                    if not result["complete"]:
                        self._score_structure(result, "road", completed=False)
                    # (idem : les autres routes d'un carrefour étaient ignorées)
                    scored_tiles_road |= result["sides"]

        # Monastères incomplets
        for (x, y), tile in self.board.items():
            if tile.tile_type.monastery and tile.meeple_player is not None:
                if tile.meeple_spot == "monastery":
                    count = 1 + sum(1 for dx in range(-1, 2) for dy in range(-1, 2)
                                    if (dx, dy) != (0, 0) and (x + dx, y + dy) in self.board)
                    self.scores[tile.meeple_player] += count

        # Scoring des champs
        self._score_fields()

    def _score_fields(self):
        """
        Score les champs en fin de partie : 3 points par ville COMPLÈTE adjacente,
        pour le(s) joueur(s) majoritaire(s) en paysans dans le champ.
        """
        visited_hs = set()
        city_cache = {}
        for (x, y), tile in self.board.items():
            for seg in tile_field_segments(tile):
                hs = min(seg)
                if (x, y, hs) in visited_hs:
                    continue
                field_result = self._trace_field(x, y, hs)
                visited_hs |= field_result["visited"]

                meeples = field_result["meeples"]
                if not meeples:
                    continue
                complete_cities = self._count_adjacent_complete_cities(
                    field_result["tiles_and_sides"], city_cache)
                if complete_cities == 0:
                    continue
                points = complete_cities * 3
                max_m = max(meeples.values())
                for owner, c in meeples.items():
                    if c == max_m:
                        self.scores[owner] += points

    def _trace_field(self, start_x: int, start_y: int, start_hs: int) -> dict:
        """
        Parcourt un champ segment par segment.

        Returns:
            visited: set de (x, y, hs) visités
            meeples: {player: nb de paysans DANS CE CHAMP}
            tiles_and_sides: set de (x, y, side) — bords ville qui touchent CE champ
            tiles: set de (x, y) traversées
        """
        visited = set()
        meeples = defaultdict(int)
        city_edges = set()
        tiles = set()
        stack = [(start_x, start_y, start_hs)]

        while stack:
            x, y, hs = stack.pop()
            if (x, y, hs) in visited:
                continue
            tile = self.board.get((x, y))
            if tile is None:
                continue
            seg = next((s for s in tile_field_segments(tile) if hs in s), None)
            if seg is None:
                continue  # demi-côté sur un bord ville : pas de champ

            for h in seg:
                visited.add((x, y, h))
            tiles.add((x, y))

            # Paysan : seulement s'il est sur CE segment
            if _farmer_segment(tile) == seg:
                meeples[tile.meeple_player] += 1

            # Villes qui touchent ce segment (et seulement lui)
            for s in _segment_city_sides(tile.edges, seg):
                city_edges.add((x, y, s))

            # Passage vers les voisins
            for h in seg:
                side = _hs_side(h)
                nx, ny = x + DX[side], y + DY[side]
                if (nx, ny) in self.board:
                    nhs = FIELD_NEIGHBOR_MAP[(side, h)]
                    if (nx, ny, nhs) not in visited:
                        stack.append((nx, ny, nhs))

        return {
            "visited": visited,
            "meeples": dict(meeples),
            "tiles_and_sides": city_edges,
            "tiles": tiles,
        }

    def _count_adjacent_complete_cities(self, tiles_and_sides: set, cache=None) -> int:
        """Nombre de villes COMPLÈTES distinctes parmi les bords ville donnés."""
        if cache is None:
            cache = {}
        done = set()
        count = 0
        for (x, y, side) in tiles_and_sides:
            if (x, y, side) in done:
                continue
            if (x, y, side) in cache:
                sides, complete = cache[(x, y, side)]
            else:
                result = self._trace_structure(x, y, side, "city")
                sides, complete = result["sides"], result["complete"]
                for k in sides:
                    cache[k] = (sides, complete)
            done |= sides  # même ville → ne pas recompter
            if complete:
                count += 1
        return count

    def _get_city_tiles(self, x: int, y: int, side: int) -> set:
        """Retourne l'ensemble des (x,y) d'une ville pour l'identifier."""
        result = self._trace_structure(x, y, side, "city")
        return result["tiles"]

    # --- Chargement depuis JSON ---

    @classmethod
    def from_json(cls, data: dict) -> "GameState":
        """Charge un état depuis le JSON de l'extension Firefox."""
        players = data["players"]
        gs = cls(num_players=len(players))
        gs.player_names = [p["name"] for p in players]
        gs.scores = [p["score"] for p in players]
        gs.meeples = [p["meeplesAvailable"] for p in players]

        color_to_player = {}
        for i, p in enumerate(players):
            color_to_player[p["color"]] = i

        # Placer les tuiles du plateau
        for bt in data["board"]:
            edges_orig = bt["edgesOriginal"]
            edges_rotated = bt["edges"]  # bords effectifs après rotation
            rot = bt["rotation"]
            shield = bt.get("shield", False)
            desc = bt.get("desc", "")

            # Trouver le TileType correspondant avec la description pour désambiguïser
            tile_type = _find_tile_type(edges_orig, shield, desc)
            if tile_type is None:
                # Fallback: créer un type ad hoc
                is_mon = "monastère" in desc.lower() or "monast" in desc.lower()
                tile_type = TileType(edges_orig, 1, shield=shield, monastery=is_mon)

            loc = bt["location"]
            if loc is None:
                continue

            # Vérification de cohérence : les bords après rotation doivent correspondre
            expected_edges = rotate_edges(tile_type.edges, rot)
            if expected_edges != edges_rotated:
                # Le TileType trouvé est incorrect, créer un type ad hoc avec les bons bords
                is_mon = "monastère" in desc.lower() or "monast" in desc.lower()
                tile_type = TileType(edges_orig, 1, shield=shield, monastery=is_mon)

            meeple_player = None
            meeple_spot = None
            if bt["meeple"]:
                color = bt["meeple"]["color"]
                meeple_player = color_to_player.get(color)
                spot_num = bt["meeple"]["spot"]
                meeple_spot = _guess_meeple_spot(tile_type, rot, spot_num)

            placed = PlacedTile(tile_type, loc["x"], loc["y"], rot,
                                meeple_player, meeple_spot)
            gs.board[(loc["x"], loc["y"])] = placed

        # Construire la pioche à partir des tuiles restantes
        gs.draw_pile = []
        remaining = data.get("remainingTiles", {})
        for key, count in remaining.items():
            shield = "★" in key
            edges = key.replace("★", "")
            tt = _find_tile_type(edges, shield)
            if tt:
                for _ in range(count):
                    gs.draw_pile.append(tt)
            else:
                # Fallback
                for _ in range(count):
                    gs.draw_pile.append(TileType(edges, 1, shield=shield))
        random.shuffle(gs.draw_pile)

        # Tuile en main
        if data.get("currentTile"):
            ct = data["currentTile"]
            desc = ct.get("desc", "")
            gs.current_tile = _find_tile_type(ct["edges"], ct.get("shield", False), desc)
            if gs.current_tile is None:
                is_mon = "monastère" in desc.lower() or "monast" in desc.lower()
                gs.current_tile = TileType(ct["edges"], 1,
                                           shield=ct.get("shield", False),
                                           monastery=is_mon)

        # Positions libres (extraites du DOM de BGA)
        gs.valid_positions = None
        free_places = data.get("freePlaces", None)
        if free_places and isinstance(free_places, list) and len(free_places) > 0:
            # C'est une liste de {x, y}
            if isinstance(free_places[0], dict):
                gs.valid_positions = set((p["x"], p["y"]) for p in free_places)

        return gs


def _find_tile_type(edges: str, shield: bool = False, desc: str = "") -> Optional[TileType]:
    """Trouve le TileType correspondant aux bords, blason, et description."""
    desc_lower = desc.lower()
    is_monastery = "monastère" in desc_lower or "monast" in desc_lower
    is_separated = "séparé" in desc_lower or "separe" in desc_lower
    is_angle = "angle" in desc_lower

    candidates = []
    for tt in TILE_TYPES:
        if tt.edges == edges and tt.shield == shield:
            if is_monastery and tt.monastery:
                return tt
            candidates.append(tt)

    if not candidates:
        # Chercher sans shield
        for tt in TILE_TYPES:
            if tt.edges == edges:
                candidates.append(tt)

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Plusieurs candidats — utiliser la description pour désambiguïser
    # "Ville angle" ou "Ville angle (blason)" → villes connectées (un seul groupe)
    # "Ville 2 côtés adjacents séparés" → villes non connectées (groupes séparés)
    for tt in candidates:
        has_connected = any(len(g) > 1 for g in tt.connected_city) if tt.connected_city else False
        has_separated = all(len(g) == 1 for g in tt.connected_city) if tt.connected_city else True

        if is_angle and has_connected:
            return tt  # "Ville angle" → version connectée
        if is_separated and has_separated:
            return tt  # "séparés" → version séparée
        if "3 côtés" in desc_lower and has_connected:
            return tt  # "Ville 3 côtés" → forcément connectée
        if "4 côtés" in desc_lower and has_connected:
            return tt  # "Ville 4 côtés" → forcément connectée

    # Fallback : préférer la version connectée (plus courante au jeu de base)
    for tt in candidates:
        if tt.connected_city and any(len(g) > 1 for g in tt.connected_city):
            return tt

    return candidates[0]


# Position (x, y) des milieux de côtés et des demi-côtés sur la tuile (0..1, y vers le bas)
_SIDE_CENTER = {0: (0.5, 0.0), 1: (1.0, 0.5), 2: (0.5, 1.0), 3: (0.0, 0.5)}
_HS_POINT = {0: (0.75, 0), 1: (1, 0.25), 2: (1, 0.75), 3: (0.75, 1),
             4: (0.25, 1), 5: (0, 0.75), 6: (0, 0.25), 7: (0.25, 0)}


def _reading_key(seg):
    """Clé « ordre de lecture » d'un champ : (y, x) de son centre."""
    xs = [_HS_POINT[h][0] for h in seg]; ys = [_HS_POINT[h][1] for h in seg]
    return (round(sum(ys) / len(ys), 3), round(sum(xs) / len(xs), 3))


def _bga_zones(tile_type: TileType) -> list:
    """
    Zones d'une tuile dans l'ordre de numérotation des spots BGA (1, 2, 3...),
    exprimées dans le repère NON tourné. Ordre déduit de 14 meeples observés
    (partie Jadiema / Joueur, 11/10/2026) :
      1. monastère
      2. routes : une seule zone si ≤ 2 côtés route ; carrefour : une zone par
         branche, dans l'ordre de lecture (haut, gauche, droite, bas)
      3. villes : groupes triés par plus petit côté
      4. champs : ordre de lecture (de haut en bas, puis de gauche à droite)
    """
    edges = tile_type.edges
    zones = []
    if tile_type.monastery:
        zones.append(("monastery", None))
    road_sides = [s for s in range(4) if edges[s] == "R"]
    if 0 < len(road_sides) <= 2:
        zones.append(("road", min(road_sides)))
    elif len(road_sides) > 2:
        # carrefour : ordre de lecture (haut, gauche, droite, bas)
        for s in sorted(road_sides, key=lambda s: _SIDE_CENTER[s][::-1]):
            zones.append(("road", s))
    for g in sorted(_city_groups(edges, tile_type.connected_city), key=min):
        zones.append(("city", min(g)))
    # Champs : ordre de lecture (centre du champ de haut en bas, puis de gauche
    # à droite), comme les branches de carrefour. Calibré par décompte final sur
    # les parties rejouées (carrefours, CCRC, route droite).
    segs = sorted(_compute_field_segments(edges, tile_type.connected_city),
                  key=_reading_key)
    if edges == "RFRF":
        # Route droite : BGA a 4 spots, 1 = route, 3 = champ gauche, 4 = champ
        # droit ; le n° 2 n'a jamais été observé — supposé être la route.
        zones.append(("road", min(road_sides)))
    for seg in segs:
        zones.append(("field", seg))
    return zones


def _guess_meeple_spot(tile_type: TileType, rotation: int, spot_num: int) -> str:
    """Traduit le numéro de spot BGA en spot moteur, dans le repère tourné."""
    zones = _bga_zones(tile_type)
    if not 1 <= spot_num <= len(zones):
        print(f"   ⚠️ spot BGA {spot_num} hors limites pour {tile_type.edges} "
              f"({len(zones)} zones) — paysan supposé")
        return "field"
    kind, ref = zones[spot_num - 1]
    r = rotation % 4
    if kind == "monastery":
        return "monastery"
    if kind in ("road", "city"):
        return f"{kind}_{(ref + r) % 4}"
    return f"field_{min((h + 2 * r) % 8 for h in ref)}"


# ============================================================
# MONTE CARLO TREE SEARCH — v2 optimisé
# ============================================================

class MCTSNode:
    __slots__ = ['state', 'parent', 'move', 'children', 'visits', 'wins', 'untried_moves']
    def __init__(self, state: GameState, parent=None, move=None):
        self.state = state
        self.parent = parent
        self.move = move
        self.children: list[MCTSNode] = []
        self.visits = 0
        self.wins = [0.0] * state.num_players
        self.untried_moves: Optional[list] = None

    def ucb1(self, player: int, exploration=1.41) -> float:
        if self.visits == 0:
            return float("inf")
        exploit = self.wins[player] / self.visits
        explore = exploration * math.sqrt(math.log(self.parent.visits) / self.visits)
        return exploit + explore


_LAMBDA_BY_RESERVE = {0: 2.4, 1: 1.4, 2: 0.8}      # points exigés par tour bloqué


def _reserve_value(n_meeples: int, tiles_left: int) -> float:
    """Valeur (en points) de n meeples en réserve, d'après le chapitre 8 du livre."""
    turns = min(9.5, tiles_left / 2)
    return sum(_LAMBDA_BY_RESERVE.get(k, 0.4) * turns for k in range(n_meeples))


def _evaluate_position(state: GameState, player: int) -> float:
    """
    Heuristique d'évaluation de position.
    Retourne un score entre 0 et 1 pour le joueur donné.
    Inclut maintenant l'estimation des champs.
    """
    opponent = 1 - player

    # 1. Écart de score réel
    score_diff = state.scores[player] - state.scores[opponent]

    # 2. Points en attente sur les meeples posés
    pending_points = [0.0, 0.0]
    for (x, y), tile in state.board.items():
        if tile.meeple_player is None:
            continue
        p = tile.meeple_player

        if tile.meeple_spot == "monastery":
            surrounding = 1 + sum(1 for dx in range(-1, 2) for dy in range(-1, 2)
                                  if (dx, dy) != (0, 0) and (x + dx, y + dy) in state.board)
            pending_points[p] += surrounding

        elif tile.meeple_spot and tile.meeple_spot.startswith("city"):
            side = int(tile.meeple_spot.split("_")[1])
            try:
                result = state._trace_structure(x, y, side, "city")
                n_tiles = len(result["tiles"])
                shields = result["shields"]
                if not result["complete"]:
                    potential = (n_tiles + shields) * 2
                    openings = sum(1 for (tx, ty) in result["tiles"]
                                   for s in range(4)
                                   if state.board[(tx, ty)].edges[s] == "C"
                                   and (tx + DX[s], ty + DY[s]) not in state.board)
                    close_prob = max(0.1, 1.0 - openings * 0.2)
                    pending_points[p] += potential * close_prob
            except:
                pending_points[p] += 2

        elif tile.meeple_spot and tile.meeple_spot.startswith("road"):
            pending_points[p] += 2

        elif tile.meeple_spot and tile.meeple_spot.startswith("field"):
            # Estimer la valeur du champ
            # Compter les villes complètes adjacentes à ce champ
            try:
                field_value = _estimate_field_value(state, x, y, p)
                pending_points[p] += field_value
            except:
                pending_points[p] += 3  # fallback: au moins 1 ville

    pending_diff = pending_points[player] - pending_points[opponent]

    # 3. Valeur des meeples en réserve (v32, « prix du meeple » du chapitre 8 du livre)
    #    Un meeple bloqué coûte λ points par tour, selon la réserve (0,4 à 7 meeples
    #    libres … 2,4 quand il n'en reste plus), pendant ≈ 9,5 tours. Le k-ième meeple
    #    de la réserve vaut donc λ(k) × min(9,5, tours restants). (v31 : 0,5 point fixe,
    #    presque annulé par le bonus de contrôle → le coach posait tout au début.)
    meeple_flex = _reserve_value(state.meeples[player], len(state.draw_pile)) - \
                  _reserve_value(state.meeples[opponent], len(state.draw_pile))

    # 4. Monastères en progression
    monastery_progress = 0
    for (x, y), tile in state.board.items():
        if tile.tile_type.monastery and tile.meeple_player is not None:
            surrounding = sum(1 for dx in range(-1, 2) for dy in range(-1, 2)
                              if (dx, dy) != (0, 0) and (x + dx, y + dy) in state.board)
            factor = 0.3 if tile.meeple_player == player else -0.3
            monastery_progress += surrounding * factor

    # 5. (v32) plus de bonus de « contrôle » par meeple posé : il rendait la pose gratuite
    control = 0.0

    total = score_diff + pending_diff * 0.5 + meeple_flex + monastery_progress + control

    return 1.0 / (1.0 + math.exp(-total * 0.08))


def _estimate_field_value(state: GameState, x: int, y: int, player: int) -> float:
    """Estime la valeur du paysan posé en (x,y) — sur SON segment de champ."""
    tile = state.board.get((x, y))
    if not tile:
        return 0
    seg = _farmer_segment(tile)
    if seg is None:
        return 0
    field_result = state._trace_field(x, y, min(seg))
    cities = state._count_adjacent_complete_cities(field_result["tiles_and_sides"])
    meeples = field_result.get("meeples", {})
    my_count = meeples.get(player, 0)
    opp_count = max((c for p, c in meeples.items() if p != player), default=0)
    if my_count > opp_count:
        return cities * 3.0 * 1.2
    if my_count == opp_count and my_count > 0:
        return cities * 3.0
    return -cities * 2.0


def _check_helps_opponent(state: GameState, x: int, y: int, rot: int,
                          tile_type: TileType, player: int) -> float:
    """
    Évalue à quel point placer une tuile à (x,y) aide l'adversaire.
    Retourne un score de pénalité :
      0 = neutre
      -15 = contribue à une structure adverse
      -30 = ferme une structure adverse (catastrophique)
    Vérifie la structure complète, pas seulement les voisins directs.
    """
    edges = rotate_edges(tile_type.edges, rot)
    opponent = 1 - player
    penalty = 0

    # Temporairement placer la tuile pour tracer les structures
    temp_tile = PlacedTile(tile_type, x, y, rot)
    state.board[(x, y)] = temp_tile

    for d in range(4):
        if edges[d] == "C":
            # Tracer la ville complète depuis ce côté
            result = state._trace_structure(x, y, d, "city")
            meeples = result.get("meeples", {})

            if opponent in meeples and player not in meeples:
                # Structure adverse sans notre meeple — TOUJOURS mauvais
                if result["complete"]:
                    n_tiles = len(result["tiles"])
                    shields = result["shields"]
                    points_given = (n_tiles + shields) * 2
                    penalty -= 30 + points_given
                else:
                    # Même contribuer est très mauvais
                    penalty -= 15

        if edges[d] == "R":
            result = state._trace_structure(x, y, d, "road")
            meeples = result.get("meeples", {})
            if opponent in meeples and player not in meeples:
                if result["complete"]:
                    penalty -= 20
                else:
                    penalty -= 10

    # Vérifier les monastères adverses (on les aide en posant à côté)
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            if (dx, dy) == (0, 0):
                continue
            adj = state.board.get((x + dx, y + dy))
            if adj and adj.tile_type.monastery and adj.meeple_player == opponent:
                surrounding = sum(1 for ddx in range(-1, 2) for ddy in range(-1, 2)
                                  if (ddx, ddy) != (0, 0) and (x + dx + ddx, y + dy + ddy) in state.board)
                if surrounding == 8:
                    # On vient de compléter le monastère adverse !
                    penalty -= 15
                else:
                    penalty -= 1

    # Retirer la tuile temporaire
    del state.board[(x, y)]

    return penalty


def _check_helps_self(state: GameState, x: int, y: int, rot: int,
                      tile_type: TileType, player: int) -> float:
    """
    Évalue à quel point ce coup nous aide.
    Retourne un bonus >= 0.
    """
    edges = rotate_edges(tile_type.edges, rot)
    bonus = 0

    temp_tile = PlacedTile(tile_type, x, y, rot)
    state.board[(x, y)] = temp_tile

    for d in range(4):
        if edges[d] == "C":
            try:
                result = state._trace_structure(x, y, d, "city")
                meeples = result.get("meeples", {})
                if player in meeples:
                    if result["complete"]:
                        # On ferme notre propre ville !
                        n_tiles = len(result["tiles"])
                        shields = result["shields"]
                        bonus += (n_tiles + shields) * 2 + 5  # gros bonus
                    else:
                        bonus += 2  # on contribue à notre ville
            except:
                pass

        if edges[d] == "R":
            try:
                result = state._trace_structure(x, y, d, "road")
                meeples = result.get("meeples", {})
                if player in meeples:
                    if result["complete"]:
                        bonus += len(result["tiles"]) + 3
                    else:
                        bonus += 1
            except:
                pass

    # Bonus pour compléter nos propres monastères
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            if (dx, dy) == (0, 0):
                continue
            adj = state.board.get((x + dx, y + dy))
            if adj and adj.tile_type.monastery and adj.meeple_player == player:
                surrounding = sum(1 for ddx in range(-1, 2) for ddy in range(-1, 2)
                                  if (ddx, ddy) != (0, 0) and (x + dx + ddx, y + dy + ddy) in state.board)
                if surrounding == 8:
                    bonus += 12  # monastère complété
                elif surrounding >= 6:
                    bonus += 3  # bientôt fini

    del state.board[(x, y)]
    return bonus


def _meeple_options(state: GameState, tile_type: TileType, x: int, y: int,
                    rot: int) -> list:
    """
    Spots où l'on peut LÉGALEMENT poser un meeple après avoir posé la tuile :
    un spot par structure distincte de la tuile, et seulement si cette
    structure (prolongée par la tuile) n'est pas déjà occupée.
    """
    tmp = PlacedTile(tile_type, x, y, rot)
    edges = tmp.edges
    spots = []
    state.board[(x, y)] = tmp          # pose temporaire, sans scoring
    try:
        if tile_type.monastery:
            spots.append("monastery")
        for g in _city_groups(edges, tmp.connected_city):
            s = min(g)
            if not state._trace_structure(x, y, s, "city")["meeples"]:
                spots.append(f"city_{s}")
        road_sides = [s for s in range(4) if edges[s] == "R"]
        road_reps = road_sides[:1] if len(road_sides) <= 2 else road_sides
        for s in road_reps:
            if not state._trace_structure(x, y, s, "road")["meeples"]:
                spots.append(f"road_{s}")
        for seg in tile_field_segments(tmp):
            if not state._trace_field(x, y, min(seg))["meeples"]:
                spots.append(f"field_{min(seg)}")
    finally:
        del state.board[(x, y)]
    return spots


def _generate_smart_moves(state: GameState, tile_type: TileType, player: int,
                          legal: list, policy: dict = None) -> list:
    """
    Génère les coups candidats priorisés par pertinence stratégique.
    Exclut les coups qui ferment des structures adverses (sauf s'il n'y a pas d'alternative).
    """
    moves = []
    excluded_moves = []  # coups catastrophiques gardés en backup
    opponent = 1 - player

    for (x, y, rot) in legal:
        n_neighbors = sum(1 for d in range(4) if state.board.get((x + DX[d], y + DY[d])))
        edges = rotate_edges(tile_type.edges, rot)

        # Évaluer si ce coup aide l'adversaire
        opp_penalty = _check_helps_opponent(state, x, y, rot, tile_type, player)

        # Bonus pour les coups qui ferment nos propres structures
        my_bonus = _check_helps_self(state, x, y, rot, tile_type, player)

        # v28 : exclure seulement si le BILAN est mauvais (ce qu'on donne à
        # l'adversaire moins ce que le coup nous rapporte), et non sur la seule
        # pénalité : donner 3 points pour en prendre 8 peut être un bon coup.
        is_catastrophic = opp_penalty + my_bonus <= -15

        priority = n_neighbors + opp_penalty + my_bonus
        target = excluded_moves if is_catastrophic else moves

        # DEBUG
        if opp_penalty != 0 or my_bonus != 0:
            flag = "❌ EXCLU" if is_catastrophic else "⚠️"
            print(f"   {flag} ({x},{y}) rot={rot} {edges}: opp_penalty={opp_penalty} my_bonus={my_bonus} prio={priority}")

        # Sans meeple
        target.append((x, y, rot, None, priority))

        if state.meeples[player] > 0:
            bonus = {"monastery": 5, "city": 1, "road": 0, "field": 2}
            for spot in _meeple_options(state, tile_type, x, y, rot):
                kind = spot.split("_")[0]
                if kind == "field" and is_catastrophic:
                    continue
                target.append((x, y, rot, spot, priority + bonus[kind]))

    # Si tous les coups sont catastrophiques, utiliser le backup
    if not moves and excluded_moves:
        print(f"   ⚠️ TOUS les coups sont catastrophiques ({len(excluded_moves)}) — fallback")
        moves = excluded_moves

    print(f"   📋 Coups: {len(moves)} bons, {len(excluded_moves)} exclus")

    # Dédupliquer
    seen = set()
    unique = []
    for x, y, rot, meeple, priority in moves:
        edges = rotate_edges(tile_type.edges, rot)
        key = (x, y, edges, meeple)
        if key not in seen:
            seen.add(key)
            unique.append((x, y, rot, meeple, priority))

    # Trier par priorité (plus de voisins = plus intéressant)
    unique.sort(key=lambda m: -m[4])

    # Limiter pour avoir assez de simulations par coup
    kept = [(x, y, rot, meeple) for x, y, rot, meeple, _ in unique[:40]]

    # v28 : repêchage par le réseau. La coupure à 40 et l'exclusion se font sur
    # l'heuristique, AVANT la policy : un coup que le réseau juge bon (souvent
    # un coup de joueur fort : partage, contre, préparation d'une jonction)
    # pouvait disparaître sans être examiné. On ajoute les placements les mieux
    # notés par le réseau, avec toutes leurs options de meeple.
    if policy:
        kept_set = set(kept)
        excluded_xyr = {(m[0], m[1], m[2]) for m in excluded_moves}
        pool = {}
        for x, y, rot, meeple, _ in moves + excluded_moves:
            pool.setdefault((x, y, rot), []).append(meeple)

        def pscore(xyr):
            return policy.get(xyr, policy.get(xyr[:2], 0.0))

        ranked = sorted(pool, key=pscore, reverse=True)
        added = 0
        for xyr in ranked[:8]:
            if pscore(xyr) < 0.02:
                break
            new = [(xyr[0], xyr[1], xyr[2], m) for m in pool[xyr]
                   if (xyr[0], xyr[1], xyr[2], m) not in kept_set]
            if not new:
                continue
            origin = "exclu par l’heuristique" if xyr in excluded_xyr else "au-delà des 40"
            kept += new
            kept_set.update(new)
            added += len(new)
            print(f"   🧠 Repêché par le réseau : ({xyr[0]},{xyr[1]}) rot={xyr[2]} "
                  f"p={pscore(xyr):.0%} ({origin}) — {len(new)} option(s)")
        if added:
            print(f"   🧠 {added} coups ajoutés par le réseau → {len(kept)} candidats")
    return kept


def mcts_search(state: GameState, tile_type: TileType, player: int,
                simulations: int = 1000, time_limit: float = 5.0,
                neural_eval=None) -> list[dict]:
    """
    Exécute un MCTS pour trouver le meilleur placement d'une tuile.
    En fin de partie (≤5 tuiles), utilise le scoring final direct au lieu du MCTS.
    """
    start_time = time.time()

    legal = state.get_legal_placements(tile_type)
    if not legal:
        return [{"x": 0, "y": 0, "rotation": 0, "meeple": None,
                 "score": 0, "visits": 0, "desc": "Aucun placement possible"}]

    # Mode fin de partie : scoring final direct (beaucoup plus fiable)
    if len(state.draw_pile) <= 5:
        return _endgame_search(state, tile_type, player, legal)

    # v28 : policy brute du réseau, calculée AVANT la génération des coups
    # pour qu'elle puisse repêcher des coups écartés par l'heuristique.
    raw_policy = None
    if neural_eval is not None:
        try:
            sd = _state_to_dict(state, player)
            if (POLICY_MODE == "rotation" and hasattr(neural_eval, "get_policy_rot")
                    and getattr(neural_eval, "n_rot", 1) > 1):
                raw_policy = neural_eval.get_policy_rot(sd, player)
            elif hasattr(neural_eval, "get_policy"):
                raw_policy = neural_eval.get_policy(sd, player)
        except Exception as e:
            print(f"   ⚠️ Policy indisponible pour le repêchage : {e}")
            raw_policy = None

    # Générer les coups candidats (filtrés et priorisés)
    all_moves = _generate_smart_moves(state, tile_type, player, legal, policy=raw_policy)

    if not all_moves:
        all_moves = [(legal[0][0], legal[0][1], legal[0][2], None)]

    # Obtenir la policy du réseau si disponible
    policy_priors = {}
    policy_used = "aucune"
    if neural_eval and hasattr(neural_eval, 'get_policy'):
        try:
            state_dict = _state_to_dict(state, player)
            use_rot = (POLICY_MODE == "rotation"
                       and hasattr(neural_eval, "get_policy_rot")
                       and getattr(neural_eval, "n_rot", 1) > 1)
            if use_rot:
                # v28 : note par (case, rotation), partagée entre les options
                # de meeple de ce placement (pour ne pas favoriser les poses
                # qui offrent beaucoup d'emplacements de meeple).
                policy_map = neural_eval.get_policy_rot(state_dict, player)
                n_opts = defaultdict(int)
                for mx, my, mr, _ in all_moves:
                    n_opts[(mx, my, mr)] += 1
                for move in all_moves:
                    mx, my, mr, _ = move
                    prior = max(policy_map.get((mx, my, mr), 0.0), 1e-3)
                    policy_priors[move] = prior / n_opts[(mx, my, mr)]
                policy_used = "case + rotation"
            else:
                policy_map = neural_eval.get_policy(state_dict, player)
                # Assigner un prior à chaque coup basé sur la position
                for move in all_moves:
                    mx, my, _, _ = move
                    prior = policy_map.get((mx, my), 0.01)
                    policy_priors[move] = prior
                policy_used = "case"
            # Normaliser
            total_prior = sum(policy_priors.values())
            if total_prior > 0:
                for m in policy_priors:
                    policy_priors[m] /= total_prior
        except Exception as e:
            print(f"   ⚠️ Policy non utilisée : {e}")
            policy_priors = {}
            policy_used = "aucune (erreur)"

    # Statistiques par mouvement
    move_stats = {move: {"visits": 0, "wins": 0.0} for move in all_moves}

    # Nombre de tuiles restantes dans la pioche pour calibrer la profondeur de rollout
    rollout_depth = min(len(state.draw_pile), 10)  # max 10 tuiles simulées

    sim_count = 0
    while sim_count < simulations and (time.time() - start_time) < time_limit:
        # PUCT (Predictor + UCB) pour choisir le coup à explorer
        # Si policy disponible, utilise PUCT comme AlphaZero
        # Sinon, UCB1 classique
        total_visits = sim_count + 1
        best_move = None
        best_ucb = -1

        for move, stats in move_stats.items():
            if stats["visits"] == 0:
                # Prioriser par la policy si disponible
                prior = policy_priors.get(move, 1.0 / len(all_moves))
                ucb = 1000 + prior * 100  # non visité = très haute priorité pondérée
            else:
                exploit = stats["wins"] / stats["visits"]
                prior = policy_priors.get(move, 1.0 / len(all_moves))
                # PUCT formula: exploit + c * prior * sqrt(N) / (1 + n)
                explore = 1.41 * prior * math.sqrt(total_visits) / (1 + stats["visits"])
                ucb = exploit + explore

            if ucb > best_ucb:
                best_ucb = ucb
                best_move = move

        # Simuler
        sim_state = deepcopy(state)
        sim_state.valid_positions = None
        x, y, rot, meeple = best_move
        sim_state.place_tile(tile_type, x, y, rot,
                             meeple_player=player if meeple else None,
                             meeple_spot=meeple)

        # Évaluation : réseau direct (rapide) ou rollout (lent)
        if neural_eval is not None and getattr(neural_eval, "use_value", True):
            # Mode AlphaZero : évaluation directe, pas de rollout
            try:
                state_dict = _state_to_dict(sim_state, player)
                score = neural_eval.evaluate(state_dict, player)
            except:
                score = _evaluate_position(sim_state, player)
        elif len(state.draw_pile) <= 10:
            # Fin de partie sans réseau : rollout complet jusqu'à la fin
            score = _fast_rollout(sim_state, (player + 1) % sim_state.num_players,
                                  player, len(sim_state.draw_pile), neural_eval=None)
        else:
            # Milieu de partie sans réseau : rollout tronqué
            score = _fast_rollout(sim_state, (player + 1) % sim_state.num_players,
                                  player, rollout_depth, neural_eval=None)

        move_stats[best_move]["visits"] += 1
        move_stats[best_move]["wins"] += score

        sim_count += 1

    elapsed = time.time() - start_time

    # Trier par taux de victoire
    results = []
    for move, stats in move_stats.items():
        x, y, rot, meeple = move
        edges = rotate_edges(tile_type.edges, rot)
        win_rate = stats["wins"] / max(stats["visits"], 1)

        desc_parts = [f"Position ({x}, {y})"]
        desc_parts.append(f"rotation {rot} → {edges}")

        neigh_desc = []
        for d in (TOP, RIGHT, BOTTOM, LEFT):
            adj = state.board.get((x + DX[d], y + DY[d]))
            if adj:
                neigh_desc.append(f"{DIRECTION_NAMES[d]}: {adj.edges}")
        if neigh_desc:
            desc_parts.append(f"voisins: {', '.join(neigh_desc)}")

        if meeple:
            desc_parts.append(f"meeple sur {meeple}")
        else:
            desc_parts.append("sans meeple")

        results.append({
            "x": x, "y": y, "rotation": rot,
            "meeple": meeple,
            "edges": edges,
            "score": round(win_rate * 100, 1),
            "visits": stats["visits"],
            "desc": " | ".join(desc_parts),
            "points_bonus": 0.0,
        })

    # Tri initial par taux de victoire
    results.sort(key=lambda r: r["score"], reverse=True)

    # Calculer les points bonus seulement pour les top 15 (performance)
    for r in results[:15]:
        r["points_bonus"] = _estimate_points_for_move(
            state, tile_type, r["x"], r["y"], r["rotation"], r["meeple"], player)
    for r in results[15:]:
        r["points_bonus"] = 0.0

    # Re-trier (v32) : le coup le PLUS VISITÉ d'abord (règle du MCTS, chapitre 12 du
    # livre), puis le taux de victoire et les points pour départager. (v31 triait par
    # taux de victoire : un coup exploré une seule fois, sur une simulation chanceuse,
    # passait devant celui que la recherche avait étudié des centaines de fois.)
    results.sort(key=lambda r: (r["visits"], r["score"], r["points_bonus"]), reverse=True)

    # Diversifier : montrer des positions distinctes d'abord
    diversified = []
    seen_positions = set()
    for r in results:
        pos_key = (r["x"], r["y"], r["rotation"])
        if pos_key not in seen_positions:
            seen_positions.add(pos_key)
            diversified.append(r)
    for r in results:
        if r not in diversified:
            diversified.append(r)
    results = diversified

    mode = (f"🧠 neural, policy : {policy_used}" if neural_eval is not None
            else "📐 heuristique")
    print(f"\n⏱️  {sim_count} simulations en {elapsed:.1f}s ({len(all_moves)} coups candidats) [{mode}]")
    # Top 3
    for i, r in enumerate(results[:3]):
        m = r.get("meeple") or "sans meeple"
        pb = r.get("points_bonus", 0)
        print(f"   {'🥇🥈🥉'[i]} ({r['x']},{r['y']}) rot={r['rotation']} {r['edges']} {m} → {r['score']}% pts={pb:.0f}")
    return results


def _endgame_search(state: GameState, tile_type: TileType, player: int,
                     legal: list) -> list[dict]:
    """
    Mode fin de partie : évalue chaque placement en simulant le scoring final complet.
    Retourne les coups triés par score total du joueur (pas par taux de victoire).
    """
    opponent = 1 - player
    results = []

    # Générer tous les coups (position + meeple)
    all_moves = []
    for (x, y, rot) in legal:
        edges = rotate_edges(tile_type.edges, rot)
        all_moves.append((x, y, rot, None))
        if state.meeples[player] > 0:
            for spot in _meeple_options(state, tile_type, x, y, rot):
                all_moves.append((x, y, rot, spot))

    # Dédupliquer
    seen = set()
    unique_moves = []
    for move in all_moves:
        x, y, rot, meeple = move
        edges = rotate_edges(tile_type.edges, rot)
        key = (x, y, edges, meeple)
        if key not in seen:
            seen.add(key)
            unique_moves.append(move)

    print(f"\n🏁 Mode fin de partie: {len(unique_moves)} coups à évaluer")

    best_score = -999
    for move in unique_moves:
        x, y, rot, meeple = move

        # Simuler le placement + scoring final complet
        sim = deepcopy(state)
        sim.valid_positions = None
        sim.place_tile(tile_type, x, y, rot,
                       meeple_player=player if meeple else None,
                       meeple_spot=meeple)

        # Scoring final complet (villes incomplètes + monastères + champs)
        sim.final_scoring()

        my_score = sim.scores[player]
        opp_score = sim.scores[opponent]
        diff = my_score - opp_score

        edges = rotate_edges(tile_type.edges, rot)
        desc_parts = [f"Position ({x}, {y})", f"rotation {rot} → {edges}"]
        if meeple and meeple.startswith("field"):
            cc = rotate_connected_city(tile_type.connected_city, rot)
            desc_parts.append(f"paysan sur {describe_field_spot(edges, cc, meeple)}")
        elif meeple:
            desc_parts.append(f"meeple sur {meeple}")
        else:
            desc_parts.append("sans meeple")

        results.append({
            "x": x, "y": y, "rotation": rot,
            "meeple": meeple,
            "edges": edges,
            "score": my_score,  # score absolu du joueur
            "visits": 1,
            "desc": " | ".join(desc_parts),
            "points_bonus": diff,
            "my_final": my_score,
            "opp_final": opp_score,
        })

        if diff > best_score:
            best_score = diff

    # Trier par différence de score (maximiser notre avance)
    results.sort(key=lambda r: r["points_bonus"], reverse=True)

    # Convertir le score en "pourcentage" (normalisé pour l'affichage)
    if results:
        max_pts = results[0]["points_bonus"]
        min_pts = results[-1]["points_bonus"] if len(results) > 1 else max_pts - 1
        score_range = max(max_pts - min_pts, 1)
        for r in results:
            # Score de 0 à 100 basé sur la position relative
            r["score"] = round((r["points_bonus"] - min_pts) / score_range * 100, 1)

    # Diversifier : positions distinctes d'abord
    diversified = []
    seen_positions = set()
    for r in results:
        pos_key = (r["x"], r["y"], r["rotation"])
        if pos_key not in seen_positions:
            seen_positions.add(pos_key)
            diversified.append(r)
    for r in results:
        if r not in diversified:
            diversified.append(r)
    results = diversified

    # Log
    print(f"   Top 3:")
    for i, r in enumerate(results[:3]):
        m = r.get("meeple") or "sans meeple"
        print(f"   {'🥇🥈🥉'[i]} ({r['x']},{r['y']}) rot={r['rotation']} {r['edges']} {m}")
        print(f"      → Vous: {r['my_final']}pts  Adversaire: {r['opp_final']}pts  Diff: {r['points_bonus']:+d}")

    return results


def _estimate_points_for_move(state: GameState, tile_type: TileType,
                               x: int, y: int, rot: int,
                               meeple: Optional[str], player: int) -> float:
    """
    Estime les points que ce coup rapporterait.
    Inclut les points immédiats ET les points de fin de partie (champs)
    quand il reste peu de tuiles.
    """
    sim = deepcopy(state)

    scores_before = sim.scores[player]
    meeples_before = sim.meeples[player]
    opp = 1 - player
    opp_scores_before = sim.scores[opp]

    sim.place_tile(tile_type, x, y, rot,
                   meeple_player=player if meeple else None,
                   meeple_spot=meeple)

    # Points immédiats (structures complétées)
    points = sim.scores[player] - scores_before

    # Meeples récupérés (bonus de flexibilité)
    meeples_recovered = sim.meeples[player] - meeples_before
    if meeple:
        meeples_recovered += 1
    points += max(0, meeples_recovered) * 1.5

    # Pénalité si on donne des points à l'adversaire
    opp_points = sim.scores[opp] - opp_scores_before
    points -= opp_points * 1.5

    # Points de fin de partie (champs, monastères incomplets, structures incomplètes)
    # Plus on est proche de la fin, plus ces points sont certains
    remaining = len(sim.draw_pile)
    if remaining <= 10:
        # Simuler le scoring final
        sim_final = deepcopy(sim)
        scores_before_final = [sim_final.scores[i] for i in range(sim_final.num_players)]
        sim_final.final_scoring()
        
        # Points de fin de partie pour nous vs adversaire
        our_final = sim_final.scores[player] - scores_before_final[player]
        opp_final = sim_final.scores[opp] - scores_before_final[opp]
        
        # Comparer avec ce qu'on aurait eu SANS ce coup
        # (approximation : on compare juste les points finaux de ce placement)
        sim_without = deepcopy(state)
        scores_without_before = [sim_without.scores[i] for i in range(sim_without.num_players)]
        sim_without.final_scoring()
        our_without = sim_without.scores[player] - scores_without_before[player]
        opp_without = sim_without.scores[opp] - scores_without_before[opp]
        
        # Gain net en points de fin de partie grâce à ce coup
        final_gain = (our_final - our_without) - (opp_final - opp_without)
        
        # Pondérer par la certitude (plus il reste peu de tuiles, plus c'est sûr)
        certainty = 1.0 - (remaining / 15.0)
        points += final_gain * max(0.3, certainty)

    return points


def _fast_rollout(state: GameState, current_player: int,
                  eval_player: int, max_depth: int,
                  neural_eval=None) -> float:
    """
    Rollout tronqué : joue max_depth tuiles aléatoirement,
    puis évalue la position avec l'heuristique.
    Retourne un score entre 0 et 1.
    """
    player = current_player

    for i in range(max_depth):
        if not state.draw_pile:
            break

        tile = state.draw_pile.pop()
        legal = state.get_legal_placements(tile)

        if not legal:
            continue

        x, y, rot = random.choice(legal)

        # Meeple aléatoire simplifié
        meeple_player = None
        meeple_spot = None
        if state.meeples[player] > 0 and random.random() < 0.3:
            edges = rotate_edges(tile.edges, rot)
            if tile.monastery:
                meeple_player = player
                meeple_spot = "monastery"
            else:
                for side in range(4):
                    if edges[side] == "C":
                        meeple_player = player
                        meeple_spot = f"city_{side}"
                        break

        state.place_tile(tile, x, y, rot, meeple_player, meeple_spot)
        player = (player + 1) % state.num_players

    # Si partie terminée, scoring réel
    if not state.draw_pile:
        state.final_scoring()
        max_score = max(state.scores)
        if state.scores[eval_player] == max_score:
            winners = [i for i, s in enumerate(state.scores) if s == max_score]
            return 1.0 if len(winners) == 1 else 0.5
        return 0.0

    # Sinon, évaluation heuristique ou neuronale
    if neural_eval is not None:
        try:
            # Reconstruire un dict minimal pour le réseau
            state_dict = _state_to_dict(state, eval_player)
            return neural_eval.evaluate(state_dict, eval_player)
        except:
            pass
    return _evaluate_position(state, eval_player)


def _bga_spot_number(tile) -> int:
    """Inverse de _guess_meeple_spot : numéro de spot BGA du meeple de la tuile."""
    spot = tile.meeple_spot
    if not spot:
        return 0
    r = tile.rotation % 4
    seg = _farmer_segment(tile) if spot.startswith("field") else None
    for i, (kind, ref) in enumerate(_bga_zones(tile.tile_type), start=1):
        if kind == "monastery" and spot == "monastery":
            return i
        if kind in ("road", "city") and spot == f"{kind}_{(ref + r) % 4}":
            return i
        if kind == "city" and spot.startswith("city"):
            side = int(spot.split("_")[1])
            groups = rotate_connected_city(tile.tile_type.connected_city, r)
            if any(side in g and (ref + r) % 4 in g for g in groups):
                return i
        if kind == "field" and seg is not None and \
                frozenset((h + 2 * r) % 8 for h in ref) == seg:
            return i
    return 1


def _tile_desc(tt: TileType) -> str:
    """Description suffisante pour que _find_tile_type retrouve le bon type."""
    if tt.monastery:
        return "Monastère"
    if tt.connected_city and len(tt.connected_city) > 1 and \
            all(len(g) == 1 for g in tt.connected_city):
        return "Ville 2 côtés adjacents séparés"
    if any(len(g) > 1 for g in (tt.connected_city or [])):
        return "Ville angle" if tt.edges.count("C") == 2 else "Ville"
    return ""


def _state_to_dict(state: GameState, player_idx: int) -> dict:
    """Convertit un GameState en dict pour le réseau de neurones."""
    players = []
    for i in range(state.num_players):
        meeples_used = 7 - state.meeples[i]
        players.append({
            "name": state.player_names[i],
            "color": ["Rouge", "Bleu", "Vert", "Jaune", "Noir"][i] if i < 5 else f"Joueur{i}",
            "score": state.scores[i],
            "meeplesUsed": meeples_used,
            "meeplesAvailable": state.meeples[i],
        })

    board = []
    for (x, y), tile in state.board.items():
        meeple = None
        if tile.meeple_player is not None:
            meeple = {"color": players[tile.meeple_player]["color"],
                      "spot": _bga_spot_number(tile)}
        board.append({
            "edges": tile.edges,
            "edgesOriginal": tile.tile_type.edges,
            "rotation": tile.rotation,
            "shield": tile.tile_type.shield,
            "desc": _tile_desc(tile.tile_type),
            "location": {"x": x, "y": y},
            "meeple": meeple,
        })

    d = {
        "players": players,
        "board": board,
        "remainingCount": len(state.draw_pile),
        "_state": state,   # utilisé directement par l'encodeur (non sérialisé)
    }
    if state.current_tile is not None:
        d["currentTile"] = {"edges": state.current_tile.edges,
                            "shield": state.current_tile.shield,
                            "desc": _tile_desc(state.current_tile)}
    return d


# ============================================================
# INTERFACE CLI
# ============================================================

def analyze_position(json_path: str, simulations: int = 500):
    """Charge un JSON et analyse la position."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    state = GameState.from_json(data)

    print("=" * 60)
    print("🏰 CARCASSONNE COACH — Analyse MCTS")
    print("=" * 60)

    # Infos joueurs
    for i, name in enumerate(state.player_names):
        print(f"  {name}: {state.scores[i]} pts, "
              f"{state.meeples[i]} meeples disponibles")

    print(f"\n  Tuiles posées: {len(state.board)}")
    print(f"  Tuiles restantes: {len(state.draw_pile)}")

    if state.current_tile:
        print(f"\n  Tuile en main: {state.current_tile.edges}"
              f" {'★' if state.current_tile.shield else ''}"
              f" {'(monastère)' if state.current_tile.monastery else ''}")
    else:
        print("\n  ⚠️  Pas de tuile en main détectée.")
        return

    # Trouver qui doit jouer (le premier joueur avec le moins de tuiles posées
    # ou simplement le joueur 0)
    current_player = 0  # par défaut
    print(f"\n  Joueur actif: {state.player_names[current_player]}")

    # Lancer le MCTS
    print(f"\n🔄 Lancement de {simulations} simulations Monte Carlo...")
    results = mcts_search(state, state.current_tile, current_player,
                          simulations=simulations)

    # Afficher les résultats
    print("\n" + "=" * 60)
    print("📊 RÉSULTATS — Top 10 coups")
    print("=" * 60)

    for i, r in enumerate(results[:10]):
        bar_len = int(r["score"] / 100 * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)

        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f" {i+1}."

        print(f"\n{medal} Taux de victoire: {r['score']}% [{bar}]  "
              f"({r['visits']} simulations)")
        print(f"   {r['desc']}")

    # Recommandation
    if results:
        best = results[0]
        print("\n" + "=" * 60)
        print("🎯 RECOMMANDATION")
        print("=" * 60)
        print(f"  Placer en ({best['x']}, {best['y']})")
        print(f"  Rotation: {best['rotation']} → bords {best['edges']}")
        if best['meeple']:
            print(f"  Poser un meeple sur: {best['meeple']}")
        else:
            print(f"  Ne PAS poser de meeple")
        print(f"  Taux de victoire estimé: {best['score']}%")


def main():
    if len(sys.argv) < 2:
        print("Usage: python carcassonne_engine.py <fichier.json> [--sims N]")
        print("\nExemple:")
        print("  python carcassonne_engine.py etat_partie.json")
        print("  python carcassonne_engine.py etat_partie.json --sims 2000")
        sys.exit(1)

    json_path = sys.argv[1]
    simulations = 500

    if "--sims" in sys.argv:
        idx = sys.argv.index("--sims")
        if idx + 1 < len(sys.argv):
            simulations = int(sys.argv[idx + 1])

    analyze_position(json_path, simulations)


if __name__ == "__main__":
    main()
