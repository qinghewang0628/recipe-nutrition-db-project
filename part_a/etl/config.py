"""Central settings: paths, thresholds, seed and scale factors."""
from __future__ import annotations

from pathlib import Path

# --- paths
ROOT = Path(__file__).resolve().parents[1]          # part A/
DATA = ROOT / "data"
RAW_DIR_LOCAL = DATA / "raw"                        # optional: place the 5 raw CSVs here instead
RAW_DIR_COURSE = ROOT.parent / "archive-datasets"   # course-provided raw directory (default)
MAPPINGS = DATA / "mappings"
CLEAN = DATA / "clean"
PROFILE = DATA / "profile"
SCALES = DATA / "scales"
DOCS = ROOT / "docs"
REPORT = ROOT / "report"
SQL = ROOT / "sql"
TESTS = ROOT / "tests"

RAW_FILES = {
    "cuisines": "cuisine_metadata.csv",
    "recipes": "recipes_master.csv",
    "ingredients": "recipe_ingredients.csv",
    "nutrition": "recipe_nutrition.csv",
    "steps": "recipe_steps.csv",
}

# SHA-256 of the raw inputs (provenance and tamper check)
RAW_SHA256 = {
    "cuisine_metadata.csv": "1b1657c9f814d264cc026a316538074c9ba8f39b53d9bd9d9a95c3e4ea71431e",
    "recipe_ingredients.csv": "f535e10ccd5929c5ea0d51b528349bf1a2b48e17d3afeab82f9816a06bdf24a2",
    "recipe_nutrition.csv": "271cdf41fcbb35d0d351f3902880a73a59efa426cc895441ab36a00969af2d18",
    "recipe_steps.csv": "b4b3cfac0ec582432583a90c0f9d41f87bf7784b8bcdd46aff2041f110921a5b",
    "recipes_master.csv": "f585abc3f5db50d9e1798b04002ebdebee30c5f918c11bd0cc884a720126e31e",
}

# --- reproducibility
RANDOM_SEED = 20261116
SCALE_FACTORS = {"small": 1, "medium": 5, "large": 20}
SCALE_ORDER = ["small", "medium", "large"]

# --- unit conversion
# Dimensions: mass->g, volume->ml, count->piece; approx_g is an estimate
UNIT_ALIASES = {
    "g": "g", "gram": "g", "grams": "g", "gm": "g", "kg": "kg", "kilogram": "kg",
    "ml": "ml", "milliliter": "ml", "millilitre": "ml", "l": "l", "litre": "l", "liter": "l",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp", "tbs": "tbsp",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "cup": "cup", "cups": "cup",
    "clove": "cloves", "cloves": "cloves",
    "medium": "medium", "med": "medium", "piece": "piece", "pcs": "piece", "pc": "piece",
}
UNIT_DIMENSION = {
    "g": "mass", "kg": "mass",
    "ml": "volume", "l": "volume", "tbsp": "volume", "tsp": "volume", "cup": "volume",
    "cloves": "count", "medium": "count", "piece": "count",
}
UNIT_CANONICAL = {
    "g": ("g", 1.0), "kg": ("g", 1000.0),
    "ml": ("ml", 1.0), "l": ("ml", 1000.0), "tbsp": ("ml", 15.0), "tsp": ("ml", 5.0), "cup": ("ml", 240.0),
    "cloves": ("piece", 1.0), "medium": ("piece", 1.0), "piece": ("piece", 1.0),
}
# Gram equivalents for shopping lists and cost roll-ups; see docs/cleaning_rules.md
UNIT_GRAM_EQUIV = {
    "g": 1.0, "kg": 1000.0,
    "ml": 1.0, "l": 1000.0, "tbsp": 15.0, "tsp": 5.0, "cup": 240.0,
    "cloves": 3.0,      # one garlic clove ~ 3 g
    "medium": 100.0,    # one medium onion/potato/carrot ~ 100 g
    "piece": 100.0,
}
PLACEHOLDER_CODES = {
    "to taste": "TO_TASTE", "as needed": "AS_NEEDED", "a pinch": "PINCH",
    "pinch": "PINCH", "n/a": "UNSPECIFIED", "na": "UNSPECIFIED",
    "-": "UNSPECIFIED", "": "UNSPECIFIED", "unknown": "UNSPECIFIED",
    "to taste ": "TO_TASTE", "as required": "AS_NEEDED", "optional": "OPTIONAL",
}

# --- cleaning policy
# Upper bound on estimated grams per serving; P99 is about 1285.5
# Values above the bound are scaled proportionally and flagged as clipped
CAP_G_PER_SERVING = 1200.0

# Dietary flags are recomputed from the ingredient set
NON_VEG_INGREDIENTS = {"Beef", "Chicken", "Fish", "Mutton", "Shrimp", "Eggs"}
ANIMAL_INGREDIENTS = NON_VEG_INGREDIENTS | {
    "Milk", "Butter", "Ghee", "Cream", "Yogurt", "Paneer",
}
GLUTEN_INGREDIENTS = {"Wheat Flour", "All-Purpose Flour", "Semolina"}
HALAL_SENSITIVE_INGREDIENTS: set[str] = set()  # no pork or alcohol ingredients in this dataset
DIETARY_FLAGS = ["is_vegetarian", "is_vegan", "is_gluten_free", "is_halal"]

# is_halal cannot be verified: slaughter and certification data are absent
HALAL_VERIFIABLE = False

# --- allergens
ALLERGEN_COLUMNS = [
    "gluten", "milk", "egg", "fish", "shellfish", "tree_nuts",
    "sesame", "soy", "mustard", "peanut",
]
ALLERGEN_BY_INGREDIENT = {
    "Wheat Flour": ["gluten"], "All-Purpose Flour": ["gluten"], "Semolina": ["gluten"],
    "Milk": ["milk"], "Butter": ["milk"], "Ghee": ["milk"], "Cream": ["milk"],
    "Yogurt": ["milk"], "Paneer": ["milk"],
    "Eggs": ["egg"], "Fish": ["fish"], "Shrimp": ["shellfish"],
    "Almonds": ["tree_nuts"], "Cashews": ["tree_nuts"],
    "Sesame Seeds": ["sesame"], "Tofu": ["soy"], "Mustard Seeds": ["mustard"],
}

# Canonical ingredient names: raw name / alias -> canonical name
# Coriander (seed) and Fresh Coriander (leaf) are distinct; do not merge
CANONICAL_MERGE = {
    "All-Purpose Flour": "Wheat Flour",
}
# Override inconsistent source categories (Paneer appeared as Dairy and Proteins)
CATEGORY_OVERRIDE = {"Paneer": "Dairy"}
DEFAULT_CATEGORY = "Others"

# Query-side aliases for reverse lookup and API parameter normalisation
QUERY_ALIASES = {
    "flour": "Wheat Flour", "atta": "Wheat Flour", "maida": "Wheat Flour",
    "all purpose flour": "Wheat Flour", "all-purpose flour": "Wheat Flour",
    "wheat flour": "Wheat Flour", "whole wheat flour": "Wheat Flour",
    "semolina": "Semolina", "sooji": "Semolina", "rava": "Semolina",
    "basmati": "Basmati Rice", "rice": "Basmati Rice",
    "chickpea flour": "Chickpea Flour", "besan": "Chickpea Flour", "gram flour": "Chickpea Flour",
    "chickpeas": "Chickpeas", "chole": "Chickpeas", "garbanzo": "Chickpeas", "chana": "Chickpeas",
    "dal": "Lentils (Dal)", "lentils": "Lentils (Dal)", "lentil": "Lentils (Dal)", "masoor dal": "Lentils (Dal)",
    "prawn": "Shrimp", "prawns": "Shrimp", "shrimp": "Shrimp", "jhinga": "Shrimp",
    "lamb": "Mutton", "mutton": "Mutton",
    "beef": "Beef", "chicken": "Chicken", "fish": "Fish", "egg": "Eggs", "eggs": "Eggs",
    "paneer": "Paneer", "cottage cheese": "Paneer",
    "yogurt": "Yogurt", "yoghurt": "Yogurt", "curd": "Yogurt", "dahi": "Yogurt",
    "ghee": "Ghee", "clarified butter": "Ghee", "butter": "Butter", "cream": "Cream", "milk": "Milk",
    "coriander leaves": "Fresh Coriander", "cilantro": "Fresh Coriander", "dhania": "Fresh Coriander",
    "fresh coriander": "Fresh Coriander",
    "coriander seeds": "Coriander", "coriander": "Coriander",
    "mint": "Mint Leaves", "mint leaves": "Mint Leaves", "pudina": "Mint Leaves",
    "curry leaves": "Curry Leaves", "kadi patta": "Curry Leaves",
    "fenugreek": "Fenugreek Leaves", "methi": "Fenugreek Leaves", "fenugreek leaves": "Fenugreek Leaves",
    "onion": "Onion", "onions": "Onion", "garlic": "Garlic", "lahsun": "Garlic",
    "tomato": "Tomato", "tomatoes": "Tomato", "potato": "Potato", "potatoes": "Potato",
    "carrot": "Carrot", "carrots": "Carrot", "peas": "Peas", "spinach": "Spinach",
    "cauliflower": "Cauliflower", "bell pepper": "Bell Pepper", "capsicum": "Bell Pepper",
    "green chili": "Green Chili", "green chilli": "Green Chili", "chilli": "Green Chili",
    "ginger": "Ginger", "adrak": "Ginger", "lemon juice": "Lemon Juice",
    "tamarind": "Tamarind Paste", "imli": "Tamarind Paste", "vinegar": "Vinegar",
    "coconut milk": "Coconut Milk", "water": "Water", "oil": "Oil", "salt": "Salt",
    "sugar": "Sugar", "raisins": "Raisins", "almonds": "Almonds", "cashews": "Cashews",
    "sesame seeds": "Sesame Seeds", "til": "Sesame Seeds", "mustard seeds": "Mustard Seeds", "rai": "Mustard Seeds",
    "tofu": "Tofu", "turmeric": "Turmeric", "haldi": "Turmeric",
    "cumin": "Cumin", "jeera": "Cumin", "cloves": "Cloves", "cardamom": "Cardamom",
    "cinnamon": "Cinnamon", "bay leaf": "Bay Leaf", "black pepper": "Black Pepper",
    "garam masala": "Garam Masala", "red chili powder": "Red Chili Powder",
    "red chilli powder": "Red Chili Powder", "curry powder": "Garam Masala",
}

# --- output tables
CLEAN_TABLES = [
    "recipes", "ingredients", "nutrition", "steps", "cuisines", "cuisine_category",
    "recipe_allergens", "recipe_dietary_audit", "ingredient_master",
    "ingredient_stats", "recipe_search_document",
]
SCALE_TABLES = [
    "recipes", "ingredients", "nutrition", "steps", "cuisines",
    "recipe_allergens", "ingredient_stats",
]


def raw_dir() -> Path:
    """Prefer data/raw/*.csv; fall back to ../archive-datasets/."""
    if all((RAW_DIR_LOCAL / f).is_file() for f in RAW_FILES.values()):
        return RAW_DIR_LOCAL
    return RAW_DIR_COURSE


def ensure_dirs() -> None:
    for p in [RAW_DIR_LOCAL, MAPPINGS, CLEAN, PROFILE, SCALES, DOCS, REPORT, SQL]:
        p.mkdir(parents=True, exist_ok=True)
    for s in SCALE_ORDER:
        (SCALES / s).mkdir(parents=True, exist_ok=True)
