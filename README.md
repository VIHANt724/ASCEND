# ASCEND — Full-stack progression app

A Flask + SQLite web application for quests, XP, levels, skills, achievements, profiles and a community leaderboard.

## Requirements
- Python 3.10+
- pip

## Run locally (Windows / VS Code)

1. Extract this ZIP.
2. Open the `ascend_fullstack` folder in VS Code.
3. Open the terminal in that folder.
4. Create and activate a virtual environment:

```powershell
py -m venv .venv
.venv\Scripts\activate
```

5. Install dependencies:

```powershell
pip install -r requirements.txt
```

6. Start the app:

```powershell
py app.py
```

7. Open http://127.0.0.1:5000

The SQLite database (`ascend.db`) is created automatically on first run. Your data persists locally.

## Features
- Account registration and login with Werkzeug password hashing
- Session-based authentication
- CSRF protection on POST forms
- User-specific quests with categories, due dates and XP rewards
- Completing a quest awards XP once and adds XP to its skill
- Level progression (100 XP per level)
- Achievement unlocks
- Skill tracker
- Community leaderboard
- Profile username editing
- Responsive Vektor-inspired visual direction

## Important notes
- This is a local starter app, not yet production-deployed.
- Before deployment, set a strong `SECRET_KEY` environment variable. Set `COOKIE_SECURE=1` when serving over HTTPS.
- Use a production WSGI server (for example, Waitress on Windows or Gunicorn on Linux), disable debug mode, and use HTTPS.
- Add email verification, password reset, rate limiting, moderation/reporting, database backups and privacy terms before opening registration publicly.
- Streak display is reserved for a future implementation; it currently remains 0.
- Daily quests and automatic recurring quest generation are not implemented yet.
- Leaderboard currently shows all registered users; consider opt-in visibility before public launch.
