# Plant Care App

A lightweight Flask web app for tracking your houseplants — watering schedules, care info, photos, and notes.

## Features

- Add, edit, and delete plants
- Upload plant photos
- Automatic plant info lookup via the [Perenual API](https://perenual.com)
- Watering status badges (overdue / due today / upcoming) with dashboard sorting
- Mobile-friendly responsive layout

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Add your Perenual API key

Sign up for a free key at https://perenual.com/docs/api, then create a `.env` file:

```
PERENUAL_API_KEY=your_key_here
```

### 3. Run the app

```bash
flask run
```

Then open **http://127.0.0.1:5000** in your browser. That's it — the dashboard loads immediately.

> **Tip:** If port 5000 is already in use, run on a different port:
> ```bash
> flask run --port 5001
> ```
> Then visit http://127.0.0.1:5001 instead.

## Project structure

```
plant-app/
├── app.py               # Flask app, routes, and helpers
├── requirements.txt
├── data/
│   └── plants.json      # Plant data (flat-file storage)
├── templates/
│   ├── base.html
│   ├── index.html       # Dashboard
│   ├── add_plant.html   # Add / Edit form
│   ├── plant_profile.html
│   └── 404.html
└── static/
    ├── css/style.css
    ├── js/main.js
    ├── favicon.svg
    └── uploads/         # User-uploaded plant photos
```

## Future upgrade notes

- **Claude API** — see the `lookup_plant_info()` function in `app.py` for the marked comment block where a Claude API call can be swapped in to generate richer, AI-powered plant descriptions.
- **Push notifications** — the `get_watering_status()` helper is the foundation for a future notification system.
- **Database** — replace `load_plants()` / `save_plants()` with SQLite or PostgreSQL queries to scale beyond flat-file storage.
- **User accounts** — add [Flask-Login](https://flask-login.readthedocs.io) for multi-user support.
