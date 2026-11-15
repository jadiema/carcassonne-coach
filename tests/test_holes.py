"""Tests des trous du plateau (onglet « Probabilités »).   Lancer : python tests/test_holes.py"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import browser_coach as B
import carcassonne_engine as E

L = B.letter_tile_type


def fusion_position():
    """Case (0, 0) : ma ville à gauche (partisan du joueur 0), ville adverse en haut (joueur 1)."""
    st = E.GameState()
    st.place_tile(L("E"), -1, 0, 1, 0, "city_1")     # ville tournée vers la droite
    st.place_tile(L("E"), 0, -1, 2, 1, "city_2")     # ville tournée vers le bas
    st.place_tile(L("V"), -1, -1, 0)
    return st


def hole(st, bag, x=0, y=0, me=0):
    return next(h for h in B.holes_for_state(st, me, bag)["holes"] if (h["x"], h["y"]) == (x, y))


class TestFusion(unittest.TestCase):
    def test_I_plus_M(self):
        h = hole(fusion_position(), {"I": 2, "M": 1})
        self.assertIn("opp_city", h["kinds"])
        self.assertTrue(h["fusion"])
        self.assertEqual((h["n"], h["m"], h["N"]), (1, 2, 3))   # seule M relie ; les deux I ferment
        self.assertEqual((h["fits"], h["others"]), (["M"], ["I"]))

    def test_I_seul_pas_de_fusion(self):
        h = hole(fusion_position(), {"I": 2})
        self.assertNotIn("opp_city", h["kinds"])
        self.assertNotIn("fusion", h)
        self.assertEqual(h["n"], 2)                             # case de ma ville : toutes les tuiles légales

    def test_reserve_ne_suffit_pas(self):
        st = E.GameState()
        st.place_tile(L("E"), 0, 0, 0, 1, "city_0")             # ville adverse seule
        st.meeples = [7, 6]
        self.assertEqual(B.holes_for_state(st, 0, {"N": 3, "E": 5})["holes"], [])

    def test_ville_adverse_sans_partisan(self):
        st = E.GameState()
        st.place_tile(L("E"), -1, 0, 1, 0, "city_1")
        st.place_tile(L("E"), 0, -1, 2)
        st.place_tile(L("V"), -1, -1, 0)
        self.assertNotIn("opp_city", hole(st, {"N": 3})["kinds"])

    def test_refus_sans_preuve(self):
        r = B.board_holes({"players": [], "board": []}, 0, {})
        self.assertEqual(r["status"], "error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
