"""Unit tests for quantity parsing and unit conversion."""
import unittest

from etl import config as C
from etl.units import canon_per_gram, parse_quantity, unit_conversion_rows


class TestParseQuantity(unittest.TestCase):
    def test_all_six_raw_units(self):
        cases = {
            "933g": ("g", "mass", "g", 933.0),
            "299 g": ("g", "mass", "g", 299.0),
            "4 tbsp": ("tbsp", "volume", "ml", 60.0),
            "2 tsp": ("tsp", "volume", "ml", 10.0),
            "752 ml": ("ml", "volume", "ml", 752.0),
            "6 cloves": ("cloves", "count", "piece", 6.0),
            "1 medium": ("medium", "count", "piece", 1.0),
        }
        for raw, (unit, dim, canon_unit, canon_value) in cases.items():
            with self.subTest(raw=raw):
                p = parse_quantity(raw)
                self.assertEqual(p["qty_parse_status"], "OK")
                self.assertEqual(p["qty_unit_norm"], unit)
                self.assertEqual(p["qty_dimension"], dim)
                self.assertEqual(p["qty_canonical_unit"], canon_unit)
                self.assertAlmostEqual(float(p["qty_canonical_value"]), canon_value, places=3)
                self.assertAlmostEqual(float(p["qty_approx_g"]),
                                       float(p["qty_value"]) * C.UNIT_GRAM_EQUIV[unit], places=3)

    def test_placeholder(self):
        for raw in ["to taste", "  to  taste  ", "as needed", "N/A", "-", ""]:
            with self.subTest(raw=raw):
                p = parse_quantity(raw)
                self.assertEqual(p["qty_is_placeholder"], "true")
                self.assertEqual(p["qty_parse_status"], "PLACEHOLDER")
                self.assertTrue(p["qty_placeholder_code"])
                self.assertEqual(p["qty_approx_g"], "")

    def test_case_and_decimals(self):
        p = parse_quantity("1.5 TBSP")
        self.assertEqual(p["qty_unit_norm"], "tbsp")
        self.assertAlmostEqual(float(p["qty_canonical_value"]), 22.5)

    def test_unitless(self):
        p = parse_quantity("3")
        self.assertEqual(p["qty_parse_status"], "OK_UNITLESS")
        self.assertEqual(p["qty_canonical_unit"], "piece")

    def test_unknown_unit_and_garbage(self):
        self.assertEqual(parse_quantity("2 furlongs")["qty_parse_status"], "UNKNOWN_UNIT")
        self.assertEqual(parse_quantity("a handful of salt")["qty_parse_status"], "UNPARSEABLE")

    def test_conversion_table_is_consistent(self):
        rows = unit_conversion_rows()
        self.assertEqual(len(rows), 10)
        for r in rows:
            self.assertIn(r["dimension"], {"mass", "volume", "count"})
            self.assertGreater(float(r["factor_to_canonical"]), 0)
            self.assertGreater(float(r["gram_equivalent_per_unit"]), 0)

    def test_canon_per_gram_identity(self):
        for unit in ["g", "ml", "tbsp", "tsp", "cloves", "medium"]:
            p = parse_quantity(f"7 {unit}")
            approx = float(p["qty_approx_g"])
            self.assertAlmostEqual(approx * canon_per_gram(unit),
                                   float(p["qty_canonical_value"]), places=3)


if __name__ == "__main__":
    unittest.main()
