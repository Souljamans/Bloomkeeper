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
# Perenual API helper
# ---------------------------------------------------------------------------

def lookup_plant_info(species_name):
    """
    Query the Perenual API for a species and return a dict with care details.

    # FUTURE: Claude API integration point
    # This function currently uses the Perenual REST API to fetch plant info.
    # To upgrade to AI-powered descriptions, replace (or supplement) the block
    # below with a call to the Claude API (anthropic.Anthropic().messages.create),
    # passing the species name and asking Claude to return a structured JSON with
    # description, origin, toxicity, light, and watering details. This would
    # produce richer, more conversational plant profiles than the Perenual data.
    """
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
    watering_str = (plant.get("watering") or "").lower()
    watering_days = watering_map.get(watering_str, 7)

    sunlight = plant.get("sunlight") or []
    if isinstance(sunlight, list) and sunlight:
        sunlight_label = sunlight[0].replace("_", " ").title()
    else:
        sunlight_label = ""

    return {
        "light": sunlight_label,
        "watering_frequency": watering_days,
        "auto_info": {
            "description": plant.get("description", ""),
            "origin": ", ".join(plant.get("origin", []) or []),
            "toxicity": str(plant.get("poisonous_to_humans", "") or ""),
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
