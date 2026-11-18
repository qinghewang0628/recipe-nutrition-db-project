"""End-to-end tests: idempotency, manifest, scale tiers."""
import json
import tempfile
import unittest
from pathlib import Path

from etl import config as C
from etl import io_utils as U
from etl import clean as CL
from etl import scale as SC

CLEAN_OK = (C.CLEAN / "recipes.csv").is_file()


class TestDeterminism(unittest.TestCase):
    def test_two_rebuilds_are_byte_identical(self):
        if not (C.MAPPINGS / "ingredient_synonyms.csv").is_file():
            self.skipTest("Run `make seed` first")
        with tempfile.TemporaryDirectory(prefix="dsc5003_test_") as td:
            a, b = Path(td) / "a", Path(td) / "b"
            CL.run(out_dir=a, verbose=False)
            CL.run(out_dir=b, verbose=False)
            for f in ["recipes.csv", "ingredients.csv", "recipe_allergens.csv",
                      "recipe_dietary_audit.csv", "ingredient_stats.csv",
                      "recipe_search_document.csv"]:
                self.assertEqual(U.sha256(a / f), U.sha256(b / f), f"{f} differs between rebuilds")


@unittest.skipUnless(CLEAN_OK, "Run `make seed` first")
class TestManifest(unittest.TestCase):
    def test_manifest_checksums_match(self):
        p = C.DATA / "manifest.json"
        if not p.is_file():
            self.skipTest("Run `make seed` first")
        m = json.loads(p.read_text(encoding="utf-8"))
        for grp in ["mappings", "clean"]:
            for k, v in m[grp].items():
                f = C.ROOT / v["path"]
                self.assertTrue(f.is_file(), v["path"])
                self.assertEqual(U.sha256(f), v["sha256"], v["path"])

    def test_scale_counts(self):
        for name, factor in C.SCALE_FACTORS.items():
            p = C.SCALES / name / "recipes.csv"
            if not p.is_file():
                self.skipTest(f"Missing {name} tier; run `make scale`")
            n = len(U.read_csv(p))
            self.assertEqual(n, 9997 * factor, f"{name} row count mismatch")

    def test_scale_primary_keys_unique(self):
        for name in C.SCALE_ORDER:
            p = C.SCALES / name / "ingredients.csv"
            if not p.is_file():
                self.skipTest(f"Missing {name} tier")
            rows = U.read_csv(p)
            keys = {(r["recipe_id"], r["ingredient_number"]) for r in rows}
            self.assertEqual(len(keys), len(rows), f"{name} duplicate composite key")


if __name__ == "__main__":
    unittest.main()
