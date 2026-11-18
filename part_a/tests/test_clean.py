"""Unit tests for lookup tables and cleaning rules."""
import collections
import unittest
from pathlib import Path

from etl import config as C
from etl import io_utils as U
from etl import mappings as M
from etl.clean import _merge_group
from etl.units import parse_quantity

MAPPINGS_OK = (C.MAPPINGS / "ingredient_synonyms.csv").is_file()
CLEAN_OK = (C.CLEAN / "recipes.csv").is_file()


@unittest.skipUnless(MAPPINGS_OK, "Run `make seed` first")
class TestMappings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mp = M.load_mappings()

    def test_synonym_merge(self):
        self.assertEqual(M.resolve("All-Purpose Flour", self.mp)["canonical_name"], "Wheat Flour")
        self.assertEqual(M.resolve("Wheat Flour", self.mp)["canonical_id"],
                         M.resolve("All-Purpose Flour", self.mp)["canonical_id"])

    def test_coriander_not_merged(self):
        self.assertNotEqual(M.resolve("Coriander", self.mp)["canonical_id"],
                            M.resolve("Fresh Coriander", self.mp)["canonical_id"])

    def test_query_alias(self):
        self.assertEqual(M.resolve("prawn", self.mp)["canonical_name"], "Shrimp")
        self.assertEqual(M.resolve("besan", self.mp)["canonical_name"], "Chickpea Flour")

    def test_paneer_category_fixed(self):
        self.assertEqual(M.resolve("Paneer", self.mp)["category"], "Dairy")

    def test_allergen_flags(self):
        self.assertEqual(M.load_mappings()["allergen_by_canon"]["Shrimp"]["has_shellfish"], "true")
        self.assertEqual(M.load_mappings()["allergen_by_canon"]["Semolina"]["has_gluten"], "true")


class TestMergeGroup(unittest.TestCase):
    def _row(self, qty, name="Onion"):
        return {"recipe_id": "RCP00001", "ingredient_number": "1",
                "canonical_id": "ING_ONION", "canonical_name": name,
                "ingredient_name_raw": name, "category": "Vegetables",
                "quantity_raw": qty, **parse_quantity(qty),
                "merged_row_count": "1", "merged_units": "", "qty_clipped": "false",
                "allergen_flags": "none", "match_status": "exact"}

    def test_mixed_units_are_summed_by_grams(self):
        rows = [self._row("2 medium"), self._row("100 g")]
        out = _merge_group(rows)
        self.assertEqual(out["merged_row_count"], "2")
        self.assertAlmostEqual(float(out["qty_approx_g"]), 300.0, places=2)
        self.assertIn("medium", out["merged_units"])
        self.assertIn("g", out["merged_units"])

    def test_placeholder_only_keeps_placeholder(self):
        out = _merge_group([self._row("to taste"), self._row("to taste")])
        self.assertEqual(out["qty_is_placeholder"], "true")
        self.assertEqual(out["qty_approx_g"], "")

    def test_placeholder_plus_quantified(self):
        out = _merge_group([self._row("to taste"), self._row("3 tbsp")])
        self.assertEqual(out["qty_is_placeholder"], "false")
        self.assertEqual(out["merged_row_count"], "2")
        self.assertAlmostEqual(float(out["qty_approx_g"]), 45.0, places=2)


@unittest.skipUnless(CLEAN_OK, "Run `make seed` first")
class TestCleanOutput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = U.read_csv(C.CLEAN / "recipes.csv")
        cls.I = U.read_csv(C.CLEAN / "ingredients.csv")
        cls.A = U.read_csv(C.CLEAN / "recipe_allergens.csv")

    def test_no_duplicate_canonical_ingredient(self):
        keys = [(r["recipe_id"], r["canonical_id"]) for r in self.I]
        self.assertEqual(len(keys), len(set(keys)))

    def test_parse_status_clean(self):
        self.assertFalse(any(r["qty_parse_status"] in {"UNPARSEABLE", "UNKNOWN_UNIT"} for r in self.I))

    def test_cap_respected(self):
        self.assertTrue(all(float(r["estimated_g_per_serving"]) <= C.CAP_G_PER_SERVING + 1e-6
                            for r in self.R))

    def test_dietary_recompute(self):
        by = collections.defaultdict(set)
        for r in self.I:
            by[r["recipe_id"]].add(r["canonical_name"])
        for r in self.R:
            ings = by[r["recipe_id"]]
            self.assertEqual(U.to_bool(r["is_vegetarian"]), not bool(ings & C.NON_VEG_INGREDIENTS))
            self.assertEqual(U.to_bool(r["is_vegan"]), not bool(ings & C.ANIMAL_INGREDIENTS))
            self.assertEqual(U.to_bool(r["is_gluten_free"]), not bool(ings & C.GLUTEN_INGREDIENTS))

    def test_halal_left_untouched_and_flagged(self):
        self.assertTrue(all(r["is_halal"] == r["is_halal_raw"] and
                            r["is_halal_verifiable"] == "false" for r in self.R))

    def test_allergen_union(self):
        by = collections.defaultdict(set)
        for r in self.I:
            for a in r["allergen_flags"].split("|"):
                if a and a != "none":
                    by[r["recipe_id"]].add(a)
        amap = {r["recipe_id"]: r for r in self.A}
        for r in self.R:
            got = set() if amap[r["recipe_id"]]["allergens"] == "none" else set(
                amap[r["recipe_id"]]["allergens"].split("|"))
            self.assertEqual(got, by[r["recipe_id"]])


if __name__ == "__main__":
    unittest.main()
