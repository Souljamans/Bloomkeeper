# 🌿 Plant Care App — Claude Code Build Guide

Work through each step one at a time. Complete all subtasks in a step before moving to the next.
When finished with a step, say "Step X complete" and wait for confirmation before continuing.

---

## Step 1: Scaffold the Project Structure

Set up the full project skeleton before writing any real logic.

- Create the following folder and file structure:
  ```
  plant-app/
  ├── app.py
  ├── requirements.txt
  ├── data/
  │   └── plants.json          # starts as an empty list []
  ├── templates/
  │   ├── base.html
  │   ├── index.html
  │   ├── add_plant.html
  │   └── plant_profile.html
  └── static/
      ├── css/
      │   └── style.css
      ├── js/
      │   └── main.js
      └── uploads/             # for user-uploaded plant photos
  ```
- Initialize `plants.json` as an empty JSON array: `[]`
- Set up `app.py` as a basic Flask app that renders `index.html` at the `/` route
- Add all dependencies to `requirements.txt` (Flask, Requests, Pillow, python-dotenv)
- Create a `.env` file with a placeholder for the Perenual API key: `PERENUAL_API_KEY=your_key_here`
- Create a `base.html` template with a shared nav bar, viewport meta tag for mobile, and a link to `style.css`

---

## Step 2: Data Model and Local Storage

Define how plant data is structured and build the read/write logic.

- Define the plant data model as a Python dict with these fields:
  ```python
  {
    "id": "unique string (uuid)",
    "nickname": "",          # optional — leave blank to display species name instead
    "species": "",
    "photo": "",              # filename of uploaded image, or "" if none
    "light": "",              # e.g. "Bright Indirect", "Low", "Full Sun"
    "watering_frequency": 0,  # number of days between waterings
    "last_watered": "",       # ISO date string YYYY-MM-DD
    "notes": "",              # user-written notes
    "auto_info": {            # populated by Perenual API
      "description": "",
      "origin": "",
      "toxicity": "",
      "fun_facts": ""
    }
  }
  ```
- Write helper functions in `app.py` for:
  - `load_plants()` — reads and returns plants from `plants.json`
  - `save_plants(plants)` — writes updated list back to `plants.json`
  - `find_plant(plant_id)` — returns a single plant by ID
  - `display_name(plant)` — returns `plant["nickname"]` if it exists and is non-empty, otherwise returns `plant["species"]`. Use this helper everywhere a plant's name is shown in the UI
- Test that read/write works by manually adding a dummy plant to `plants.json` and confirming it loads correctly

---

## Step 3: Perenual API Integration

Connect to the Perenual plant database to auto-fill plant information.

- Sign up for a free API key at https://perenual.com/docs/api and add it to `.env`
- Write a function `lookup_plant_info(species_name)` in `app.py` that:
  - Calls `https://perenual.com/api/species-list?q={species_name}&key={API_KEY}`
  - Parses the first result from the response
  - Returns a dict with: description, origin/region, toxicity, and any care details available
- Create a Flask route `POST /api/lookup` that accepts a species name and returns the Perenual data as JSON
- In `add_plant.html`, add a "Look Up Plant Info" button next to the species name field that:
  - Calls `/api/lookup` via JavaScript fetch when clicked
  - Auto-fills the light, watering frequency, and auto_info fields with the returned data
  - Shows a loading spinner while the request is in flight
  - Shows a friendly error message if the plant isn't found
- Add a visible note in the UI that says info is sourced from Perenual, with a comment in the code marking where an AI-powered lookup (e.g. Claude API) could be swapped in later for richer descriptions

---

## Step 4: Core CRUD Routes

Build all the backend routes for managing plants.

- `GET /` — load and display all plants on the dashboard
- `GET /plant/<id>` — show the individual plant profile page
- `GET /plant/add` — render the add plant form
- `POST /plant/add` — handle form submission:
  - Generate a UUID for the new plant
  - Save the uploaded photo to `static/uploads/` (accept jpg, png, webp)
  - Append the new plant to `plants.json`
  - Redirect to the dashboard
- `GET /plant/<id>/edit` — render the edit form pre-filled with existing data
- `POST /plant/<id>/edit` — save changes and redirect to the plant profile
- `POST /plant/<id>/delete` — remove the plant from `plants.json` and redirect to dashboard
- `POST /plant/<id>/watered` — update `last_watered` to today's date and redirect back to the profile

---

## Step 5: Dashboard (index.html)

Build the main plant list view with watering status indicators.

- Display all plants as cards in a responsive CSS Grid layout:
  - 3 columns on desktop
  - 2 columns on tablet
  - 1 column on mobile
- Each card shows:
  - Plant photo (or a default leaf icon/placeholder if no photo)
  - Display name: show the nickname if one was entered, otherwise fall back to the species name. Never show both on the card — just whichever name is being used as the primary label
  - A watering status badge:
    - 🔴 Red — overdue (past due date)
    - 🟡 Yellow — due today
    - 🟢 Green — upcoming (not due yet)
- Sort plants by urgency: overdue first, then due today, then upcoming
- Include an "Add New Plant" button prominently at the top
- Add a summary bar at the top showing counts: e.g. "3 overdue · 1 due today · 5 upcoming"
- Make each card fully clickable, linking to `/plant/<id>`

---

## Step 6: Add / Edit Plant Form (add_plant.html)

Build the form for creating and editing plants.

- Fields:
  - Nickname (text input, optional — include placeholder text like "e.g. My Little Fern")
  - Species name (text input) + "Look Up Info" button (from Step 3)
  - Photo upload (file input, image files only)
  - Light requirement (dropdown: Low / Medium / Bright Indirect / Full Sun)
  - Watering frequency (number input: "every ___ days")
  - Last watered date (date picker, defaults to today)
  - Notes (textarea for personal notes)
  - Auto-info fields (description, origin, toxicity) — shown as read-only previews after lookup, but editable
- Show a preview of the uploaded photo before submitting
- Validate that species name is filled in before allowing submission (nickname is optional)
- Use the same template for both Add and Edit, with the form pre-filled when editing
- On mobile: stack all fields vertically with large, tap-friendly inputs

---

## Step 7: Plant Profile Page (plant_profile.html)

Build the individual plant detail view.

- Display at the top:
  - Large plant photo (or placeholder)
  - Primary name in large text: show the nickname if one exists, otherwise show the species name
  - If a nickname is shown as the primary name, display the species name below it in smaller, muted text. If no nickname was given, only show the species name — do not show a duplicate or blank line
- Show an info section with icon-labeled rows for:
  - 💧 Watering frequency ("Every X days")
  - ☀️ Light requirement
  - 📅 Last watered date
  - ⏳ Days until next watering (calculated, shown as "Due in X days" or "Overdue by X days")
- Show a card for "About This Plant" with the auto_info fields (description, origin, toxicity)
- Show a "Personal Notes" card with the user's notes
- Action buttons:
  - ✅ "Mark as Watered" — POST to `/plant/<id>/watered`
  - ✏️ "Edit Plant" — links to the edit form
  - 🗑️ "Delete Plant" — with a confirmation prompt before submitting
- On mobile: stack all sections vertically, make buttons full-width

---

## Step 8: Styling (style.css)

Apply a clean, botanical aesthetic across the whole app.

- Color palette:
  - Primary green: `#4a7c59` (nav bar, primary buttons, badges)
  - Secondary green (light): `#a8c5a0` (hover states, subtle accents)
  - Blush pink: `#e8a0a0` (accent highlights, "Mark as Watered" button, overdue badges)
  - Soft pink background tint: `#fdf0f0` (card hover tint or section backgrounds)
  - Warm brown: `#7b4f2e` (headings, plant card titles, icon accents)
  - Light brown / tan: `#c9a07a` (borders, dividers, secondary text)
  - Page background: `#f8f5f0` (warm off-white with a slight earthy tone)
  - Card white: `#ffffff`
  - Text dark: `#2d2d2d`
- Typography: Use Google Fonts — "Lato" for body text, "Playfair Display" for headings
- Style plant cards with:
  - Soft box shadow
  - Rounded corners (12px)
  - Smooth hover lift effect (`transform: translateY(-4px)`)
- Style watering badges as pill-shaped colored tags
- Style the nav bar with the primary green and white text
- Make all buttons large enough for easy tapping on mobile (min height 44px)
- Add smooth page transitions with a subtle fade-in on load
- Ensure all text has sufficient contrast for readability
- Test layout at these widths: 390px (iPhone 14), 768px (iPad), 1280px (desktop)

---

## Step 9: Watering Reminder Logic

Add the logic that drives watering status throughout the app.

- Write a helper function `get_watering_status(plant)` that returns:
  - `"overdue"` if today is past the due date
  - `"due_today"` if today is the due date
  - `"upcoming"` with the number of days remaining
- Due date = `last_watered` date + `watering_frequency` days
- Use this function consistently across the dashboard cards and the plant profile page
- On the dashboard, sort plants using this status as the primary sort key
- On the profile page, display the result as a human-readable string ("Due in 3 days" / "Overdue by 2 days" / "Water today!")

---

## Step 10: Final Polish and Testing

Review the full app and fix any remaining issues.

- Test the full add → view → edit → water → delete flow for at least two plants
- Test the Perenual lookup with a common plant (e.g. "Pothos", "Snake Plant", "Peace Lily")
- Test on mobile screen size (390px) — check that all buttons, cards, and forms are usable
- Test on desktop (1280px) — check that the grid layout looks balanced
- Add a favicon (a small leaf emoji or simple SVG)
- Add a 404 page for unknown routes
- Make sure `plants.json` handles edge cases: empty list, missing fields, invalid dates
- Add a `README.md` with:
  - How to install dependencies (`pip install -r requirements.txt`)
  - How to add the Perenual API key to `.env`
  - How to run the app (`flask run`)
  - A note about where to integrate Claude API in the future (Step 3 lookup function)

---

## Future Upgrade Notes (Do Not Implement Now)

Leave clearly marked comments in the code for these planned features:

- **Claude API integration** — in the `lookup_plant_info()` function, add a comment block explaining that this is where a Claude API call could be added to generate a richer, more conversational plant description based on the species name
- **Push notifications** — the watering reminder logic in Step 9 is the foundation for a future notification system
- **SQLite or PostgreSQL** — `plants.json` can be swapped for a real database by replacing the `load_plants()` and `save_plants()` helper functions
- **User accounts** — the app currently has no login; multi-user support can be layered on later with Flask-Login
