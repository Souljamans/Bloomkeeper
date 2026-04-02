import json
import os
import uuid
import requests
from datetime import date, timedelta
from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, flash, abort
)
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "plants.json")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
PERENUAL_API_KEY = os.getenv("PERENUAL_API_KEY", "")


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

_PLANT_DEFAULTS = {
    "id": "",
    "nickname": "",
    "species": "Unknown",
    "photo": "",
    "light": "",
    "watering_frequency": 7,
    "last_watered": "",
    "notes": "",
    "auto_info": {"description": "", "origin": "", "toxicity": "", "fun_facts": ""},
}


def _normalize_plant(plant):
    """Fill in any missing fields with defaults so templates never KeyError."""
    result = {**_PLANT_DEFAULTS, **plant}
    result["auto_info"] = {**_PLANT_DEFAULTS["auto_info"], **plant.get("auto_info", {})}
    try:
        result["watering_frequency"] = int(result["watering_frequency"])
    except (ValueError, TypeError):
        result["watering_frequency"] = 7
    return result


def load_plants():
    """Read and return the list of plants from plants.json."""
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [_normalize_plant(p) for p in data if isinstance(p, dict)]
    except (json.JSONDecodeError, OSError):
        return []


def save_plants(plants):
    """Write the updated plant list back to plants.json."""
    with open(DATA_FILE, "w") as f:
        json.dump(plants, f, indent=2)


def find_plant(plant_id):
    """Return a single plant dict by ID, or None if not found."""
    for plant in load_plants():
        if plant["id"] == plant_id:
            return plant
    return None


def display_name(plant):
    """Return nickname if non-empty, otherwise species name."""
    return plant["nickname"] if plant.get("nickname", "").strip() else plant["species"]


# ---------------------------------------------------------------------------
# Watering status helper
# ---------------------------------------------------------------------------

def get_watering_status(plant):
    """
    Return a dict describing the plant's watering status.

    Keys:
      "status"  — "overdue" | "due_today" | "upcoming"
      "days"    — int: days overdue (positive) or days until due (positive)
      "label"   — human-readable string for the UI
    """
    last_watered = plant.get("last_watered", "")
    frequency = int(plant.get("watering_frequency") or 7)

    if not last_watered:
        return {"status": "overdue", "days": 0, "label": "No watering recorded"}

    try:
        last_date = date.fromisoformat(last_watered)
    except ValueError:
        return {"status": "overdue", "days": 0, "label": "Invalid date"}

    due_date = last_date + timedelta(days=frequency)
    today = date.today()
    delta = (due_date - today).days

    if delta < 0:
        return {"status": "overdue", "days": abs(delta), "label": f"Overdue by {abs(delta)} day{'s' if abs(delta) != 1 else ''}"}
    elif delta == 0:
        return {"status": "due_today", "days": 0, "label": "Water today!"}
    else:
        return {"status": "upcoming", "days": delta, "label": f"Due in {delta} day{'s' if delta != 1 else ''}"}


_STATUS_ORDER = {"overdue": 0, "due_today": 1, "upcoming": 2}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_photo(file_storage):
    """Save an uploaded photo and return the filename, or '' on failure."""
    if not file_storage or file_storage.filename == "":
        return ""
    if not _allowed_file(file_storage.filename):
        return ""
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(UPLOAD_FOLDER, filename))
    return filename


def _plant_from_form(form, files, existing=None):
    """Build a plant dict from a submitted form. Merges into existing if given."""
    plant = existing.copy() if existing else {
        "id": str(uuid.uuid4()),
        "photo": "",
        "auto_info": {"description": "", "origin": "", "toxicity": "", "fun_facts": ""},
    }

    plant["nickname"] = form.get("nickname", "").strip()
    plant["species"] = form.get("species", "").strip()
    plant["light"] = form.get("light", "")
    plant["watering_frequency"] = int(form.get("watering_frequency") or 7)
    plant["last_watered"] = form.get("last_watered", "")
    plant["notes"] = form.get("notes", "").strip()
    plant["auto_info"]["description"] = form.get("description", "").strip()
    plant["auto_info"]["origin"] = form.get("origin", "").strip()
    plant["auto_info"]["toxicity"] = form.get("toxicity", "").strip()

    photo_file = files.get("photo")
    if photo_file and photo_file.filename:
        saved = _save_photo(photo_file)
        if saved:
            plant["photo"] = saved

    return plant


# ---------------------------------------------------------------------------
# Local plant database (Perenual free plan returns null for care data)
# ---------------------------------------------------------------------------

# Keys are lowercase common/scientific name fragments for fuzzy matching.
# Fields: light, watering_frequency (days), description, origin, toxicity
_LOCAL_PLANTS = {
    "pothos": {
        "light": "Bright Indirect", "watering_frequency": 10,
        "description": "A vigorous trailing vine with heart-shaped leaves, popular for its extreme adaptability and air-purifying qualities. Tolerates low light and irregular watering better than most houseplants.",
        "origin": "Solomon Islands", "toxicity": "Toxic to cats and dogs"},
    "epipremnum": {
        "light": "Bright Indirect", "watering_frequency": 10,
        "description": "A vigorous trailing vine with heart-shaped leaves, popular for its extreme adaptability and air-purifying qualities.",
        "origin": "Solomon Islands", "toxicity": "Toxic to cats and dogs"},
    "snake plant": {
        "light": "Low", "watering_frequency": 21,
        "description": "A tough, architectural plant with stiff upright leaves. Thrives on neglect, tolerates low light, and is one of the best air-purifying houseplants.",
        "origin": "West Africa", "toxicity": "Mildly toxic to cats and dogs"},
    "sansevieria": {
        "light": "Low", "watering_frequency": 21,
        "description": "A tough, architectural plant with stiff upright leaves. Thrives on neglect and tolerates low light.",
        "origin": "West Africa", "toxicity": "Mildly toxic to cats and dogs"},
    "dracaena trifasciata": {
        "light": "Low", "watering_frequency": 21,
        "description": "Formerly classified as Sansevieria. Stiff, sword-like leaves with yellow margins. Extremely drought tolerant.",
        "origin": "West Africa", "toxicity": "Mildly toxic to cats and dogs"},
    "peace lily": {
        "light": "Low", "watering_frequency": 7,
        "description": "One of the few flowering plants that thrives in low light. White spathe blooms and glossy dark leaves. Droops visibly when it needs water.",
        "origin": "Central and South America", "toxicity": "Toxic to cats and dogs"},
    "spathiphyllum": {
        "light": "Low", "watering_frequency": 7,
        "description": "One of the few flowering plants that thrives in low light. White spathe blooms and glossy dark leaves.",
        "origin": "Central and South America", "toxicity": "Toxic to cats and dogs"},
    "spider plant": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Fast-growing with arching green-and-white striped leaves that produce cascading baby plants. Extremely forgiving and safe for pets.",
        "origin": "South Africa", "toxicity": "Non-toxic"},
    "chlorophytum": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Fast-growing with arching striped leaves that produce cascading baby plants. Extremely forgiving and safe for pets.",
        "origin": "South Africa", "toxicity": "Non-toxic"},
    "fiddle leaf fig": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "A statement plant with large, violin-shaped leaves. Loves consistency — hates being moved or overwatered.",
        "origin": "West Africa", "toxicity": "Toxic to cats and dogs"},
    "ficus lyrata": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "A statement plant with large, violin-shaped leaves. Loves consistency and bright indirect light.",
        "origin": "West Africa", "toxicity": "Toxic to cats and dogs"},
    "monstera": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Iconic split leaves (fenestrations) develop as the plant matures. Fast-growing and dramatic; a staple of modern interior design.",
        "origin": "Central America", "toxicity": "Toxic to cats and dogs"},
    "zz plant": {
        "light": "Low", "watering_frequency": 21,
        "description": "Virtually indestructible — tolerates low light, drought, and neglect. Glossy oval leaflets grow on graceful arching stems.",
        "origin": "Eastern Africa", "toxicity": "Toxic to cats and dogs"},
    "zamioculcas": {
        "light": "Low", "watering_frequency": 21,
        "description": "Virtually indestructible — tolerates low light, drought, and neglect. Glossy oval leaflets on arching stems.",
        "origin": "Eastern Africa", "toxicity": "Toxic to cats and dogs"},
    "aloe vera": {
        "light": "Full Sun", "watering_frequency": 14,
        "description": "Succulent with thick fleshy leaves filled with soothing gel. Needs bright light and infrequent watering. The gel inside treats minor burns and skin irritation.",
        "origin": "Arabian Peninsula", "toxicity": "Mildly toxic to cats and dogs"},
    "aloe": {
        "light": "Full Sun", "watering_frequency": 14,
        "description": "Succulent with thick fleshy leaves filled with soothing gel. Needs bright light and infrequent watering.",
        "origin": "Africa", "toxicity": "Mildly toxic to cats and dogs"},
    "rubber plant": {
        "light": "Bright Indirect", "watering_frequency": 10,
        "description": "Bold, glossy leaves in deep green or burgundy. Fast-growing and dramatic once established; enjoys being pot-bound.",
        "origin": "South and Southeast Asia", "toxicity": "Mildly toxic to cats and dogs"},
    "ficus elastica": {
        "light": "Bright Indirect", "watering_frequency": 10,
        "description": "Bold, glossy leaves in deep green or burgundy. Fast-growing and dramatic once established.",
        "origin": "South and Southeast Asia", "toxicity": "Mildly toxic to cats and dogs"},
    "chinese evergreen": {
        "light": "Low", "watering_frequency": 10,
        "description": "One of the most adaptable houseplants. Wide range of leaf patterns from deep green to pink and red. Tolerates low light and irregular watering.",
        "origin": "Asia", "toxicity": "Toxic to cats and dogs"},
    "aglaonema": {
        "light": "Low", "watering_frequency": 10,
        "description": "Widely adaptable with striking leaf patterns from deep green to pink and red. Tolerates low light.",
        "origin": "Asia", "toxicity": "Toxic to cats and dogs"},
    "philodendron": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Heart-shaped or deeply lobed leaves depending on the variety. Fast-growing, easygoing, and great for beginners.",
        "origin": "Tropical Americas", "toxicity": "Toxic to cats and dogs"},
    "calathea": {
        "light": "Medium", "watering_frequency": 7,
        "description": "Stunning patterned leaves that fold up at night (a movement called nyctinasty). Needs humidity and indirect light; sensitive to tap water minerals.",
        "origin": "Tropical Americas", "toxicity": "Non-toxic"},
    "bird of paradise": {
        "light": "Full Sun", "watering_frequency": 7,
        "description": "Large, paddle-shaped leaves that split naturally as they age. Needs lots of bright light to thrive indoors; rewards with dramatic tropical presence.",
        "origin": "South Africa", "toxicity": "Mildly toxic to cats and dogs"},
    "strelitzia": {
        "light": "Full Sun", "watering_frequency": 7,
        "description": "Large, paddle-shaped leaves that split naturally. Needs lots of bright light indoors.",
        "origin": "South Africa", "toxicity": "Mildly toxic to cats and dogs"},
    "boston fern": {
        "light": "Bright Indirect", "watering_frequency": 5,
        "description": "Lush, arching fronds that thrive in humidity. One of the best air-purifying plants; loves a bathroom or kitchen with indirect light.",
        "origin": "Tropical regions worldwide", "toxicity": "Non-toxic"},
    "nephrolepis": {
        "light": "Bright Indirect", "watering_frequency": 5,
        "description": "Lush, arching fronds that thrive in humidity. One of the best air-purifying plants.",
        "origin": "Tropical regions worldwide", "toxicity": "Non-toxic"},
    "jade plant": {
        "light": "Full Sun", "watering_frequency": 14,
        "description": "Thick, woody stems and plump oval leaves store water. Long-lived and said to bring good luck. Needs bright light and infrequent watering.",
        "origin": "South Africa and Mozambique", "toxicity": "Toxic to cats and dogs"},
    "crassula": {
        "light": "Full Sun", "watering_frequency": 14,
        "description": "Thick woody stems and plump oval leaves store water. Long-lived; needs bright light and infrequent watering.",
        "origin": "South Africa", "toxicity": "Toxic to cats and dogs"},
    "african violet": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Compact flowering plant that blooms almost continuously under the right conditions. Needs bright indirect light and water at the base, not on the leaves.",
        "origin": "Tanzania", "toxicity": "Non-toxic"},
    "saintpaulia": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Compact flowering plant that blooms almost continuously. Needs bright indirect light.",
        "origin": "Tanzania", "toxicity": "Non-toxic"},
    "english ivy": {
        "light": "Medium", "watering_frequency": 7,
        "description": "Classic trailing or climbing vine with iconic lobed leaves. Great for hanging baskets; effective air purifier.",
        "origin": "Europe and Western Asia", "toxicity": "Toxic to cats, dogs, and humans"},
    "hedera": {
        "light": "Medium", "watering_frequency": 7,
        "description": "Classic trailing or climbing vine with iconic lobed leaves. Great for hanging baskets.",
        "origin": "Europe and Western Asia", "toxicity": "Toxic to cats, dogs, and humans"},
    "dieffenbachia": {
        "light": "Medium", "watering_frequency": 7,
        "description": "Bold tropical plant with large patterned leaves in shades of green and cream. Tolerates low light but grows fastest in medium light.",
        "origin": "Tropical Americas", "toxicity": "Toxic to cats, dogs, and humans"},
    "prayer plant": {
        "light": "Medium", "watering_frequency": 7,
        "description": "Leaves fold upward at night like praying hands. Distinctive herringbone pattern in red, green, and cream. Loves humidity.",
        "origin": "Brazil", "toxicity": "Non-toxic"},
    "maranta": {
        "light": "Medium", "watering_frequency": 7,
        "description": "Leaves fold upward at night like praying hands. Distinctive herringbone pattern. Loves humidity.",
        "origin": "Brazil", "toxicity": "Non-toxic"},
    "peperomia": {
        "light": "Bright Indirect", "watering_frequency": 10,
        "description": "Hundreds of varieties with thick, waxy leaves in diverse shapes and textures. Stores water in its leaves so tolerates some neglect.",
        "origin": "Tropical and subtropical regions", "toxicity": "Non-toxic"},
    "hoya": {
        "light": "Bright Indirect", "watering_frequency": 10,
        "description": "Waxy, semi-succulent leaves and clusters of star-shaped flowers. Grows slowly but rewards patience with beautiful blooms.",
        "origin": "Asia and Australia", "toxicity": "Non-toxic"},
    "tradescantia": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Fast-growing trailing plant with striking purple, green, or striped leaves. Easy to propagate — snip a stem and pop it in water.",
        "origin": "Americas", "toxicity": "Mildly toxic to cats and dogs"},
    "string of pearls": {
        "light": "Bright Indirect", "watering_frequency": 14,
        "description": "Cascading stems of bead-like leaves that store water. Stunning in a hanging pot; needs bright light and excellent drainage.",
        "origin": "South Africa", "toxicity": "Toxic to cats and dogs"},
    "senecio rowleyanus": {
        "light": "Bright Indirect", "watering_frequency": 14,
        "description": "Cascading stems of bead-like leaves. Stunning in a hanging pot; needs bright light and excellent drainage.",
        "origin": "South Africa", "toxicity": "Toxic to cats and dogs"},
    "yucca": {
        "light": "Full Sun", "watering_frequency": 14,
        "description": "Bold, sword-like leaves on a thick trunk. Extremely drought tolerant once established; needs bright light to stay compact.",
        "origin": "Americas and Caribbean", "toxicity": "Toxic to cats and dogs"},
    "anthurium": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Glossy heart-shaped leaves and waxy, long-lasting blooms in red, pink, or white. Thrives in humidity with bright indirect light.",
        "origin": "Central and South America", "toxicity": "Toxic to cats and dogs"},
    "oxalis": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Clover-like leaves in rich purple or green that fold up at night. Produces delicate pink or white flowers. Goes dormant in summer.",
        "origin": "Brazil", "toxicity": "Toxic to cats and dogs"},
    "dracaena": {
        "light": "Low", "watering_frequency": 14,
        "description": "Long, strappy leaves in green, yellow, or tricolor. Extremely tolerant of low light and dry air. One of the best plants for office environments.",
        "origin": "Africa and Asia", "toxicity": "Toxic to cats and dogs"},
    "croton": {
        "light": "Full Sun", "watering_frequency": 7,
        "description": "Fiery, multicolored leaves in red, orange, yellow, and green. Needs lots of bright light to maintain its vivid colors.",
        "origin": "Malaysia and Pacific Islands", "toxicity": "Toxic to cats and dogs"},
    "codiaeum": {
        "light": "Full Sun", "watering_frequency": 7,
        "description": "Fiery, multicolored leaves in red, orange, yellow, and green. Needs lots of bright light.",
        "origin": "Malaysia and Pacific Islands", "toxicity": "Toxic to cats and dogs"},
    "nerve plant": {
        "light": "Medium", "watering_frequency": 5,
        "description": "Tiny but striking, with vivid red, pink, or white veins on deep green leaves. Loves humidity and consistent moisture.",
        "origin": "Peru", "toxicity": "Non-toxic"},
    "fittonia": {
        "light": "Medium", "watering_frequency": 5,
        "description": "Vivid red, pink, or white veins on deep green leaves. Loves humidity and consistent moisture.",
        "origin": "Peru", "toxicity": "Non-toxic"},
    "cast iron plant": {
        "light": "Low", "watering_frequency": 14,
        "description": "Lives up to its name — nearly impossible to kill. Thrives in deep shade, irregular watering, and temperature extremes.",
        "origin": "China and Japan", "toxicity": "Non-toxic"},
    "aspidistra": {
        "light": "Low", "watering_frequency": 14,
        "description": "Nearly impossible to kill. Thrives in deep shade and tolerates irregular watering.",
        "origin": "China and Japan", "toxicity": "Non-toxic"},
    "begonia": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Diverse genus with waxy, often colorful foliage and cheerful blooms. Needs bright indirect light and well-draining soil.",
        "origin": "Tropical and subtropical regions", "toxicity": "Toxic to cats and dogs"},
    "lavender": {
        "light": "Full Sun", "watering_frequency": 10,
        "description": "Fragrant silver-green foliage and purple flower spikes beloved by pollinators. Needs full sun and excellent drainage; drought-tolerant once established.",
        "origin": "Mediterranean", "toxicity": "Mildly toxic to cats and dogs"},
    "orchid": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Long-lasting blooms in almost every color. Water sparingly and let the roots dry between waterings. Prefers bright light without direct sun.",
        "origin": "Tropical Asia", "toxicity": "Non-toxic"},
    "phalaenopsis": {
        "light": "Bright Indirect", "watering_frequency": 7,
        "description": "Moth orchid with long-lasting blooms in almost every color. Let roots dry between waterings.",
        "origin": "Tropical Asia", "toxicity": "Non-toxic"},
}


def _local_plant_lookup(species_name):
    """Check the local plant database for a case-insensitive partial match."""
    name_lower = species_name.lower()
    # Exact match first
    if name_lower in _LOCAL_PLANTS:
        return _LOCAL_PLANTS[name_lower]
    # Partial match — return first entry whose key appears in the query or vice versa
    for key, data in _LOCAL_PLANTS.items():
        if key in name_lower or name_lower in key:
            return data
    return None


# ---------------------------------------------------------------------------
# Perenual API helper
# ---------------------------------------------------------------------------

def lookup_plant_info(species_name):
    """
    Return care info for a species. Checks the local database first, then
    falls back to the Perenual API (care fields require a paid Perenual plan).

    # FUTURE: Claude API integration point
    # Replace or supplement this function with a call to the Claude API
    # (anthropic.Anthropic().messages.create) passing the species name and
    # asking Claude to return structured JSON with description, origin,
    # toxicity, light, and watering details. This would provide richer,
    # AI-powered profiles for any plant, not just those in the local database.
    """
    # 1. Check local database first (reliable, no API limits)
    local = _local_plant_lookup(species_name)
    if local:
        return {
            "light": local["light"],
            "watering_frequency": local["watering_frequency"],
            "auto_info": {
                "description": local["description"],
                "origin": local["origin"],
                "toxicity": local["toxicity"],
                "fun_facts": "",
            },
        }

    # 2. Fall back to Perenual API
    url = "https://perenual.com/api/species-list"
    params = {"q": species_name, "key": PERENUAL_API_KEY}

    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    results = data.get("data", [])
    if not results:
        return None

    plant = results[0]

    watering_map = {"frequent": 2, "average": 7, "minimum": 14, "none": 30}
    watering_str = (plant.get("watering") or "").strip().lower()
    watering_days = watering_map.get(watering_str, 7)

    sunlight_raw = plant.get("sunlight") or []
    if isinstance(sunlight_raw, str):
        sunlight_raw = [sunlight_raw]
    sunlight_str = " ".join(sunlight_raw).lower()

    if any(k in sunlight_str for k in ("full sun", "full_sun")) or \
            ("direct" in sunlight_str and "indirect" not in sunlight_str):
        sunlight_label = "Full Sun"
    elif any(k in sunlight_str for k in ("indirect", "filtered", "bright", "part sun")):
        sunlight_label = "Bright Indirect"
    elif any(k in sunlight_str for k in ("part shade", "part_shade", "dappled", "medium")):
        sunlight_label = "Medium"
    elif any(k in sunlight_str for k in ("shade", "low", "deep")):
        sunlight_label = "Low"
    else:
        sunlight_label = ""

    return {
        "light": sunlight_label,
        "watering_frequency": watering_days,
        "auto_info": {
            "description": plant.get("description") or "",
            "origin": ", ".join(plant.get("origin", []) or []),
            "toxicity": str(plant.get("poisonous_to_humans") or ""),
            "fun_facts": "",
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    plants = load_plants()

    # Attach watering status to each plant for the template
    for plant in plants:
        plant["_status"] = get_watering_status(plant)

    # Sort: overdue → due today → upcoming
    # Within overdue: most overdue first (days descending)
    # Within upcoming: soonest first (days ascending)
    def sort_key(p):
        s = p["_status"]
        days = -s["days"] if s["status"] == "overdue" else s["days"]
        return (_STATUS_ORDER[s["status"]], days)

    plants.sort(key=sort_key)

    counts = {
        "overdue":   sum(1 for p in plants if p["_status"]["status"] == "overdue"),
        "due_today": sum(1 for p in plants if p["_status"]["status"] == "due_today"),
        "upcoming":  sum(1 for p in plants if p["_status"]["status"] == "upcoming"),
    }

    return render_template("index.html", plants=plants, display_name=display_name, counts=counts)


@app.route("/plant/add", methods=["GET", "POST"])
def add_plant():
    if request.method == "POST":
        if not request.form.get("species", "").strip():
            flash("Species name is required.", "error")
            return redirect(url_for("add_plant"))

        plant = _plant_from_form(request.form, request.files)
        plants = load_plants()
        plants.append(plant)
        save_plants(plants)
        flash(f"{display_name(plant)} added!", "success")
        return redirect(url_for("index"))

    return render_template("add_plant.html", plant=None, today=date.today().isoformat())


@app.route("/plant/<plant_id>")
def plant_profile(plant_id):
    plant = find_plant(plant_id)
    if plant is None:
        abort(404)
    return render_template(
        "plant_profile.html",
        plant=plant,
        display_name=display_name(plant),
        status=get_watering_status(plant),
    )


@app.route("/plant/<plant_id>/edit", methods=["GET", "POST"])
def edit_plant(plant_id):
    plants = load_plants()
    idx = next((i for i, p in enumerate(plants) if p["id"] == plant_id), None)
    if idx is None:
        abort(404)

    if request.method == "POST":
        if not request.form.get("species", "").strip():
            flash("Species name is required.", "error")
            return redirect(url_for("edit_plant", plant_id=plant_id))

        plants[idx] = _plant_from_form(request.form, request.files, existing=plants[idx])
        save_plants(plants)
        flash("Plant updated.", "success")
        return redirect(url_for("plant_profile", plant_id=plant_id))

    return render_template(
        "add_plant.html",
        plant=plants[idx],
        today=date.today().isoformat(),
    )


@app.route("/plant/<plant_id>/delete", methods=["POST"])
def delete_plant(plant_id):
    plants = load_plants()
    plants = [p for p in plants if p["id"] != plant_id]
    save_plants(plants)
    flash("Plant deleted.", "success")
    return redirect(url_for("index"))


@app.route("/plant/<plant_id>/watered", methods=["POST"])
def mark_watered(plant_id):
    plants = load_plants()
    for plant in plants:
        if plant["id"] == plant_id:
            plant["last_watered"] = date.today().isoformat()
            break
    else:
        abort(404)
    save_plants(plants)
    flash("Watering recorded!", "success")
    return redirect(url_for("plant_profile", plant_id=plant_id))


@app.route("/api/search")
def api_search():
    """Return a list of matching plant names for autocomplete."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])

    try:
        resp = requests.get(
            "https://perenual.com/api/species-list",
            params={"q": q, "key": PERENUAL_API_KEY},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except requests.RequestException:
        return jsonify([])

    suggestions = []
    for plant in data[:10]:
        common = (plant.get("common_name") or "").strip()
        scientific = (plant.get("scientific_name") or [])
        if isinstance(scientific, list):
            scientific = scientific[0] if scientific else ""
        label = f"{common} ({scientific})" if common and scientific else common or scientific
        if label:
            suggestions.append({"label": label, "scientific": scientific, "common": common})

    return jsonify(suggestions)


@app.route("/api/lookup", methods=["POST"])
def api_lookup():
    """Return Perenual plant data for a given species name."""
    species = (request.json or {}).get("species", "").strip()
    if not species:
        return jsonify({"error": "Species name is required."}), 400

    try:
        info = lookup_plant_info(species)
    except requests.RequestException as e:
        return jsonify({"error": f"API request failed: {e}"}), 502

    if info is None:
        return jsonify({"error": f"No results found for \"{species}\"."}), 404

    return jsonify(info)


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
