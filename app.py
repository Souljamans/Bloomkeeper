import json
import os
import requests
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "plants.json")
PERENUAL_API_KEY = os.getenv("PERENUAL_API_KEY", "")


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def load_plants():
    """Read and return the list of plants from plants.json."""
    with open(DATA_FILE, "r") as f:
        return json.load(f)


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

    # Extract watering frequency as a number of days
    watering_map = {"frequent": 2, "average": 7, "minimum": 14, "none": 30}
    watering_str = (plant.get("watering") or "").lower()
    watering_days = watering_map.get(watering_str, 7)

    # Map sunlight list to a single label
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
    return render_template("index.html")


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


if __name__ == "__main__":
    app.run(debug=True)
