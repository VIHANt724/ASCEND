import os, sqlite3, secrets
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "ascend.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-deployment-" + secrets.token_hex(16))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"

SKILLS = [
    ("Academics", "Build your knowledge", "◈"),
    ("Coding", "Create with technology", "</>"),
    ("Fitness", "Build healthy routines", "↗"),
    ("Creativity", "Make things that matter", "✳"),
    ("Mindfulness", "Train your focus", "◎"),
]

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL COLLATE NOCASE UNIQUE,
      email TEXT NOT NULL COLLATE NOCASE UNIQUE,
      password_hash TEXT NOT NULL,
      total_xp INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      last_active TEXT,
      streak INTEGER NOT NULL DEFAULT 0,
      last_quest_date TEXT
    );
    CREATE TABLE IF NOT EXISTS quests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      title TEXT NOT NULL,
      description TEXT DEFAULT '',
      category TEXT NOT NULL DEFAULT 'Academics',
      xp_reward INTEGER NOT NULL DEFAULT 20,
      due_date TEXT,
      completed INTEGER NOT NULL DEFAULT 0,
      completed_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS skills (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      name TEXT NOT NULL,
      description TEXT NOT NULL,
      icon TEXT NOT NULL,
      xp INTEGER NOT NULL DEFAULT 0,
      UNIQUE(user_id, name)
    );
    CREATE TABLE IF NOT EXISTS achievements (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      description TEXT NOT NULL,
      icon TEXT NOT NULL,
      threshold INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_achievements (
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      achievement_id INTEGER NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
      unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, achievement_id)
    );
    """)
    achievements = [
      ("first_quest","First Step","Complete your first quest","✦",1),
      ("five_quests","Getting Momentum","Complete 5 quests","↗",5),
      ("ten_quests","Consistency","Complete 10 quests","⬡",10),
      ("hundred_xp","Century","Earn 100 total XP","◎",100),
      ("five_hundred_xp","Rising","Earn 500 total XP","✳",500),
    ]
    db.executemany("INSERT OR IGNORE INTO achievements(code,name,description,icon,threshold) VALUES(?,?,?,?,?)", achievements)
    db.commit()
    db.close()

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]

@app.context_processor
def inject_globals():
    return {"csrf_token": csrf_token, "current_user": get_current_user()}

@app.before_request
def protect_posts():
    if request.method == "POST":
        token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token, session.get("_csrf", "")):
            abort(400, "Your form session expired. Refresh the page and try again.")

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Log in to access your dashboard.", "notice")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def level_for(xp):
    # Level 1 starts at 0 XP; each next level costs 100 more XP.
    level = 1
    remaining = max(0, xp)
    needed = 100
    while remaining >= needed:
        remaining -= needed
        level += 1
        needed = 100
    return level, remaining, needed

def ensure_skills(user_id):
    db = get_db()
    for name, desc, icon in SKILLS:
        db.execute("INSERT OR IGNORE INTO skills(user_id,name,description,icon) VALUES(?,?,?,?)",
                   (user_id, name, desc, icon))
    db.commit()

def completed_count(user_id):
    return get_db().execute("SELECT COUNT(*) n FROM quests WHERE user_id=? AND completed=1", (user_id,)).fetchone()["n"]

def check_achievements(user_id):
    db = get_db()
    count = completed_count(user_id)
    user = db.execute("SELECT total_xp FROM users WHERE id=?", (user_id,)).fetchone()
    for a in db.execute("SELECT * FROM achievements").fetchall():
        qualifies = (a["code"] in ("hundred_xp","five_hundred_xp") and user["total_xp"] >= a["threshold"]) or (a["code"] not in ("hundred_xp","five_hundred_xp") and count >= a["threshold"])
        if qualifies:
            db.execute("INSERT OR IGNORE INTO user_achievements(user_id,achievement_id) VALUES(?,?)", (user_id,a["id"]))
    db.commit()

@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if len(username) < 3 or len(username) > 20 or not username.replace("_","").isalnum():
            flash("Username must be 3–20 characters (letters, numbers or underscores).", "error")
        elif "@" not in email or len(email) > 120:
            flash("Enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        else:
            db = get_db()
            try:
                cur = db.execute("INSERT INTO users(username,email,password_hash) VALUES(?,?,?)",
                    (username,email,generate_password_hash(password)))
                uid = cur.lastrowid
                db.commit()
                ensure_skills(uid)
                session.clear()
                session["user_id"] = uid
                csrf_token()
                flash("Welcome to ASCEND. Your journey starts now.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("That username or email is already registered.", "error")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("identity","").strip()
        password = request.form.get("password","")
        user = get_db().execute("SELECT * FROM users WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE",
                                (identity,identity)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            csrf_token()
            get_db().execute("UPDATE users SET last_active=? WHERE id=?", (date.today().isoformat(),user["id"]))
            get_db().commit()
            ensure_skills(user["id"])
            return redirect(url_for("dashboard"))
        flash("Incorrect username/email or password.", "error")
    return render_template("auth.html", mode="login")

@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    ensure_skills(user["id"])
    level, into, needed = level_for(user["total_xp"])
    quests = get_db().execute("SELECT * FROM quests WHERE user_id=? ORDER BY completed ASC, COALESCE(due_date,'9999-12-31'), id DESC LIMIT 8",(user["id"],)).fetchall()
    skills = get_db().execute("SELECT * FROM skills WHERE user_id=? ORDER BY xp DESC",(user["id"],)).fetchall()
    count = completed_count(user["id"])
    today = date.today().isoformat()
    today_done = get_db().execute("SELECT COUNT(*) n FROM quests WHERE user_id=? AND completed=1 AND substr(completed_at,1,10)=?",(user["id"],today)).fetchone()["n"]
    unlocked = get_db().execute("""SELECT a.* FROM achievements a JOIN user_achievements ua ON ua.achievement_id=a.id WHERE ua.user_id=? ORDER BY ua.unlocked_at DESC""",(user["id"],)).fetchall()
    return render_template("dashboard.html", user=user, level=level, into=into, needed=needed,
                           quests=quests, skills=skills, count=count, today_done=today_done, unlocked=unlocked)

@app.route("/quests")
@login_required
def quests():
    user=get_current_user()
    items=get_db().execute("SELECT * FROM quests WHERE user_id=? ORDER BY completed ASC, id DESC",(user["id"],)).fetchall()
    return render_template("quests.html", quests=items)

@app.post("/quests/create")
@login_required
def create_quest():
    title=request.form.get("title","").strip()
    desc=request.form.get("description","").strip()
    category=request.form.get("category","Academics")
    due=request.form.get("due_date") or None
    try: reward=int(request.form.get("xp_reward","20"))
    except ValueError: reward=20
    allowed=[s[0] for s in SKILLS]
    if not title or len(title)>80:
        flash("Quest title is required and must be under 80 characters.","error")
    elif category not in allowed:
        flash("Choose a valid category.","error")
    else:
        reward=max(5,min(50,reward))
        get_db().execute("INSERT INTO quests(user_id,title,description,category,xp_reward,due_date) VALUES(?,?,?,?,?,?)",
            (session["user_id"],title,desc[:300],category,reward,due))
        get_db().commit()
        flash("Quest added to your list.","success")
    return redirect(request.referrer or url_for("quests"))

@app.post("/quests/<int:quest_id>/complete")
@login_required
def complete_quest(quest_id):
    db=get_db(); uid=session["user_id"]
    quest=db.execute("SELECT * FROM quests WHERE id=? AND user_id=?",(quest_id,uid)).fetchone()
    if not quest: abort(404)
    if not quest["completed"]:
        now=datetime.now().isoformat(timespec="seconds")
        db.execute("UPDATE quests SET completed=1,completed_at=? WHERE id=?",(now,quest_id))
        db.execute("UPDATE users SET total_xp=total_xp+? WHERE id=?",(quest["xp_reward"],uid))
        db.execute("UPDATE skills SET xp=xp+? WHERE user_id=? AND name=?",(quest["xp_reward"],uid,quest["category"]))
        db.commit()
        check_achievements(uid)
        flash(f"Quest complete! +{quest['xp_reward']} XP earned.","success")
    return redirect(request.referrer or url_for("quests"))

@app.post("/quests/<int:quest_id>/delete")
@login_required
def delete_quest(quest_id):
    db=get_db(); uid=session["user_id"]
    q=db.execute("SELECT * FROM quests WHERE id=? AND user_id=?",(quest_id,uid)).fetchone()
    if not q: abort(404)
    # Completed rewards remain in the lifetime XP total; deleting never reverses earned XP.
    db.execute("DELETE FROM quests WHERE id=?",(quest_id,)); db.commit()
    flash("Quest deleted. Previously earned XP is kept.","success")
    return redirect(request.referrer or url_for("quests"))

@app.route("/skills")
@login_required
def skills():
    ensure_skills(session["user_id"])
    items=get_db().execute("SELECT * FROM skills WHERE user_id=? ORDER BY xp DESC",(session["user_id"],)).fetchall()
    return render_template("skills.html", skills=items)

@app.route("/achievements")
@login_required
def achievements():
    uid=session["user_id"]; check_achievements(uid)
    items=get_db().execute("""SELECT a.*, CASE WHEN ua.user_id IS NULL THEN 0 ELSE 1 END unlocked, ua.unlocked_at
      FROM achievements a LEFT JOIN user_achievements ua ON ua.achievement_id=a.id AND ua.user_id=? ORDER BY unlocked DESC,a.threshold""",(uid,)).fetchall()
    return render_template("achievements.html", achievements=items)

@app.route("/leaderboard")
@login_required
def leaderboard():
    users=get_db().execute("SELECT username,total_xp FROM users ORDER BY total_xp DESC, username ASC LIMIT 50").fetchall()
    return render_template("leaderboard.html", users=users)

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    db=get_db(); uid=session["user_id"]
    if request.method=="POST":
        username=request.form.get("username","").strip()
        if len(username)<3 or len(username)>20 or not username.replace("_","").isalnum():
            flash("Username must be 3–20 characters (letters, numbers or underscores).","error")
        else:
            try:
                db.execute("UPDATE users SET username=? WHERE id=?",(username,uid)); db.commit()
                flash("Profile updated.","success")
            except sqlite3.IntegrityError: flash("That username is already taken.","error")
        return redirect(url_for("profile"))
    user=get_current_user()
    level,into,needed=level_for(user["total_xp"])
    return render_template("profile.html",user=user,level=level,into=into,needed=needed)

@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error,"description","Bad request")),400
@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="That page or quest could not be found."),404

init_db()

if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)
