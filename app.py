
# ============================================================
# HATEGUARD - AI POWERED HATE SPEECH DETECTION SYSTEM
# Complete Updated Flask Application
# ============================================================

import os
import sqlite3
import joblib

from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "HATEGUARD_SECRET_KEY",
    "HateGuard_Development_Key_2026"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE = os.path.join(BASE_DIR, "hate_speech.db")

MODEL_PATH = os.path.join(
    BASE_DIR, "model", "hate_model.pkl"
)

VECTORIZER_PATH = os.path.join(
    BASE_DIR, "model", "vectorizer.pkl"
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = get_db()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT
        )
    """)

    # Add missing columns to existing users table
    cursor.execute("PRAGMA table_info(users)")
    user_columns = {
        row["name"] for row in cursor.fetchall()
    }

    if "email" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN email TEXT"
        )

    if "created_at" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN created_at TEXT"
        )

    if "role" not in user_columns:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN role TEXT NOT NULL DEFAULT 'user'
        """)

    # Create predictions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            text TEXT NOT NULL,
            prediction TEXT NOT NULL,
            confidence REAL,
            created_at TEXT,
            status TEXT DEFAULT 'Safe'
        )
    """)

    # Add missing columns to existing predictions table
    cursor.execute("PRAGMA table_info(predictions)")
    prediction_columns = {
        row["name"] for row in cursor.fetchall()
    }

    if "username" not in prediction_columns:
        cursor.execute(
            "ALTER TABLE predictions ADD COLUMN username TEXT"
        )

    if "confidence" not in prediction_columns:
        cursor.execute(
            "ALTER TABLE predictions ADD COLUMN confidence REAL"
        )

    if "created_at" not in prediction_columns:
        cursor.execute(
            "ALTER TABLE predictions ADD COLUMN created_at TEXT"
        )

    if "status" not in prediction_columns:
        cursor.execute("""
            ALTER TABLE predictions
            ADD COLUMN status TEXT DEFAULT 'Safe'
        """)

    # Set initial status for old records
    cursor.execute("""
        UPDATE predictions
        SET status = CASE
            WHEN prediction IN ('Hate Speech', 'Offensive')
                THEN 'Flagged'
            ELSE 'Safe'
        END
        WHERE status IS NULL OR status = ''
    """)

    # Create default moderator if it does not exist
    admin = cursor.execute("""
        SELECT id FROM users WHERE username = ?
    """, ("admin",)).fetchone()

    if admin is None:

        hashed_password = generate_password_hash(
            "admin123",
            method="pbkdf2:sha256"
        )

        cursor.execute("""
            INSERT INTO users
            (username, email, password, role, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "admin",
            "admin@hateguard.local",
            hashed_password,
            "moderator",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        print("Default moderator account created.")
        print("Username: admin")
        print("Password: admin123")

    else:
        # Ensure the default admin account has moderator access
        cursor.execute("""
            UPDATE users
            SET role = 'moderator'
            WHERE username = 'admin'
        """)

    conn.commit()
    conn.close()

    print("DATABASE INITIALIZED SUCCESSFULLY")


# ============================================================
# LOAD MACHINE LEARNING MODEL
# ============================================================

model = None
vectorizer = None


def load_model():

    global model, vectorizer

    if not os.path.exists(MODEL_PATH):
        print("ERROR: Model file not found:", MODEL_PATH)
        return

    if not os.path.exists(VECTORIZER_PATH):
        print("ERROR: Vectorizer file not found:", VECTORIZER_PATH)
        return

    try:
        model = joblib.load(MODEL_PATH)
        vectorizer = joblib.load(VECTORIZER_PATH)

        print("MODEL LOADED SUCCESSFULLY")

    except Exception as error:
        print("MODEL LOADING ERROR:", error)
        model = None
        vectorizer = None


# ============================================================
# LOGIN REQUIRED DECORATOR
# ============================================================

def login_required(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if "user_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return decorated_function


# ============================================================
# MODERATOR REQUIRED DECORATOR
# ============================================================

def moderator_required(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))

        if session.get("role") not in ("admin", "moderator"):
            flash(
                "Access denied. Moderator privileges required.",
                "danger"
            )
            return redirect(url_for("dashboard"))

        return function(*args, **kwargs)

    return decorated_function


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ============================================================
# REGISTER - EVERYONE CAN REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password", ""
        )

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        if len(password) < 4:
            flash(
                "Password must contain at least 4 characters.",
                "warning"
            )
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(
            password,
            method="pbkdf2:sha256"
        )

        created_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn = get_db()

        try:
            conn.execute("""
                INSERT INTO users
                (username, email, password, role, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                username,
                email,
                hashed_password,
                "user",
                created_at
            ))

            conn.commit()

            flash(
                "Registration successful. Please login.",
                "success"
            )

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash(
                "Username or email already exists.",
                "danger"
            )
            return redirect(url_for("register"))

        finally:
            conn.close()

    return render_template("register.html")


# ============================================================
# LOGIN - EVERY REGISTERED USER CAN LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash(
                "Please enter username and password.",
                "danger"
            )
            return redirect(url_for("login"))

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE username = ?
        """, (username,)).fetchone()

        conn.close()

        if user:

            try:
                valid_password = check_password_hash(
                    user["password"],
                    password
                )
            except (ValueError, TypeError):
                valid_password = False

            if valid_password:

                session.clear()

                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = user["role"] or "user"
                session["email"] = user["email"] or ""

                print("LOGIN USER:", session["username"])
                print("LOGIN ROLE:", session["role"])

                flash("Login successful.", "success")

                return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


# ============================================================
# USER DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    username = session.get("username", "")

    conn = get_db()

    total = conn.execute("""
        SELECT COUNT(*) AS count
        FROM predictions
        WHERE username = ?
    """, (username,)).fetchone()["count"]

    hate_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM predictions
        WHERE username = ?
        AND prediction = 'Hate Speech'
    """, (username,)).fetchone()["count"]

    safe_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM predictions
        WHERE username = ?
        AND prediction = 'Safe'
    """, (username,)).fetchone()["count"]

    offensive_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM predictions
        WHERE username = ?
        AND prediction = 'Offensive'
    """, (username,)).fetchone()["count"]

    recent_predictions = conn.execute("""
        SELECT id, username, text, prediction,
               confidence, created_at
        FROM predictions
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 10
    """, (username,)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        username=username,
        total=total,
        hate_count=hate_count,
        safe_count=safe_count,
        offensive_count=offensive_count,
        recent_predictions=recent_predictions
    )


# ============================================================
# PREDICTION
# ============================================================

@app.route("/predict", methods=["POST"])
@login_required
def predict():

    text = request.form.get("text", "").strip()

    if not text:
        flash("Please enter text to analyze.", "warning")
        return redirect(url_for("dashboard"))

    if model is None or vectorizer is None:
        flash(
            "Machine learning model is not loaded.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    try:

        transformed_text = vectorizer.transform([text])

        predicted_value = model.predict(transformed_text)[0]

        predicted_string = str(
            predicted_value
        ).lower().strip()

        if predicted_string in {
            "0", "hate", "hate speech",
            "hatespeech", "hate_speech"
        }:
            prediction = "Hate Speech"

        elif predicted_string in {
            "1", "safe", "neither", "normal",
            "not hate", "not_hate",
            "not hate speech", "non-hate", "non_hate"
        }:
            prediction = "Safe"

        elif predicted_string in {
            "offensive", "offensive speech",
            "offensive_language"
        }:
            prediction = "Offensive"

        elif "hate" in predicted_string:
            prediction = "Hate Speech"

        elif "offensive" in predicted_string:
            prediction = "Offensive"

        else:
            prediction = "Safe"

        confidence = 0.0

        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(
                transformed_text
            )[0]

            confidence = float(max(probabilities) * 100)

    except Exception as error:

        app.logger.exception("Prediction failed: %s", error)

        flash(
            "Prediction failed. Please check the ML model.",
            "danger"
        )

        return redirect(url_for("dashboard"))

    status = (
        "Flagged"
        if prediction in {"Hate Speech", "Offensive"}
        else "Safe"
    )

    conn = get_db()

    conn.execute("""
        INSERT INTO predictions
        (username, text, prediction, confidence, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session.get("username"),
        text,
        prediction,
        confidence,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status
    ))

    conn.commit()
    conn.close()

    return render_template(
        "result.html",
        text=text,
        prediction=prediction,
        confidence=round(confidence, 2)
    )


# ============================================================
# ANALYTICS DASHBOARD - MODERATOR ONLY
# ============================================================

@app.route("/analytics")
@moderator_required
def analytics():

    conn = get_db()

    try:

        total = conn.execute("""
            SELECT COUNT(*) FROM predictions
        """).fetchone()[0]

        hate = conn.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE prediction = 'Hate Speech'
        """).fetchone()[0]

        safe = conn.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE prediction = 'Safe'
        """).fetchone()[0]

        flagged = conn.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE status = 'Flagged'
        """).fetchone()[0]

        reviewed = conn.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE status = 'Reviewed'
        """).fetchone()[0]

        approved = conn.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE status = 'Approved'
        """).fetchone()[0]

        removed = conn.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE status = 'Removed'
        """).fetchone()[0]

        safe_status = conn.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE status = 'Safe'
        """).fetchone()[0]

        hate_percentage = (
            round((hate / total) * 100, 2)
            if total > 0 else 0
        )

        return render_template(
            "analytics.html",
            total=total,
            hate=hate,
            safe=safe,
            hate_percentage=hate_percentage,
            flagged=flagged,
            reviewed=reviewed,
            approved=approved,
            removed=removed,
            safe_status=safe_status
        )

    except sqlite3.Error as error:

        app.logger.exception("Analytics database error")

        return f"Analytics database error: {error}", 500

    finally:
        conn.close()


# ============================================================
# MODERATOR DASHBOARD
# ============================================================

@app.route("/moderator")
@moderator_required
def moderator():

    conn = get_db()

    predictions = conn.execute("""
        SELECT id, username, text, prediction,
               confidence, created_at, status
        FROM predictions
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "moderator.html",
        predictions=predictions
    )


# ============================================================
# MODERATOR - UPDATE PREDICTION STATUS
# ============================================================

@app.route(
    "/moderator/update/<int:prediction_id>",
    methods=["POST"]
)
@moderator_required
def update_prediction_status(prediction_id):

    new_status = request.form.get("status", "").strip()

    allowed_statuses = {
        "Pending",
        "Flagged",
        "Reviewed",
        "Approved",
        "Removed",
        "Safe"
    }

    if new_status not in allowed_statuses:
        flash("Invalid moderation status.", "danger")
        return redirect(url_for("moderator"))

    conn = get_db()

    cursor = conn.execute("""
        UPDATE predictions
        SET status = ?
        WHERE id = ?
    """, (new_status, prediction_id))

    conn.commit()

    updated = cursor.rowcount

    conn.close()

    if updated:
        flash("Prediction status updated.", "success")
    else:
        flash("Prediction record not found.", "warning")

    return redirect(url_for("moderator"))


# ============================================================
# USER HISTORY
# ============================================================

@app.route("/history")
@login_required
def history():

    username = session.get("username", "")

    conn = get_db()

    predictions = conn.execute("""
        SELECT id, username, text, prediction,
               confidence, created_at
        FROM predictions
        WHERE username = ?
        ORDER BY id DESC
    """, (username,)).fetchall()

    conn.close()

    return render_template(
        "history.html",
        username=username,
        predictions=predictions
    )


# ============================================================
# DELETE USER PREDICTION
# ============================================================

@app.route(
    "/delete/<int:prediction_id>",
    methods=["POST"]
)
@login_required
def delete_prediction(prediction_id):

    username = session.get("username", "")

    conn = get_db()

    conn.execute("""
        DELETE FROM predictions
        WHERE id = ?
        AND username = ?
    """, (prediction_id, username))

    conn.commit()
    conn.close()

    flash("Prediction deleted successfully.", "success")

    return redirect(url_for("history"))


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


# ============================================================
# 404 ERROR HANDLER
# ============================================================

@app.errorhandler(404)
def page_not_found(error):

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>404 - HateGuard</title>
    </head>
    <body style="
        background:#020617;
        color:white;
        font-family:Arial;
        text-align:center;
        padding-top:100px;
    ">
        <h1 style="color:#38bdf8;font-size:60px">404</h1>
        <h2>Page Not Found</h2>
        <p>The requested HateGuard page does not exist.</p>
        <a style="color:#60a5fa" href="/">Return to HateGuard</a>
    </body>
    </html>
    """, 404


# ============================================================
# 500 ERROR HANDLER
# ============================================================

@app.errorhandler(500)
def internal_server_error(error):

    app.logger.exception(
        "Internal server error: %s", error
    )

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>500 - HateGuard</title>
    </head>
    <body style="
        background:#020617;
        color:white;
        font-family:Arial;
        text-align:center;
        padding-top:100px;
    ">
        <h1 style="color:#ef4444;font-size:60px">500</h1>
        <h2>Internal Server Error</h2>
        <p>Something went wrong in HateGuard.</p>
    </body>
    </html>
    """, 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    print("==============================================")
    print("              HATEGUARD AI")
    print("     HATE SPEECH DETECTION SYSTEM")
    print("==============================================")

    init_db()
    load_model()

    print("")
    print("Login:     http://127.0.0.1:5000/login")
    print("Register:  http://127.0.0.1:5000/register")
    print("Dashboard: http://127.0.0.1:5000/dashboard")
    print("Analytics: http://127.0.0.1:5000/analytics")
    print("Moderator: http://127.0.0.1:5000/moderator")
    print("==============================================")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
