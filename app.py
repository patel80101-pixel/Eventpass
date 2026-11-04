"""
EventPass - Event Registration & Ticketing System
Cloud Native Orchestration (CSA3004) project by Pooja Patel (PRN 20240801035)

Features
  1. Event management   - create / edit / delete events, search & filter by category
  2. Registration       - book 1-5 tickets per person, seat capacity enforced (no overbooking)
  3. Digital tickets    - every booking gets a unique ticket code (EP-XXXXXX)
  4. Check-in desk      - verify a ticket code at the venue, double check-in is blocked
  5. Cancellation       - cancelling a booking releases the seats
  6. Dashboard          - events, tickets sold, revenue, check-in rate, sold-out events
  7. JSON API + /health - used by Kubernetes liveness / readiness probes
"""
import os
import random
import sqlite3
import string
from datetime import datetime

from flask import (Flask, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

CATEGORIES = ["Technical", "Cultural", "Sports", "Workshop", "Seminar", "Music"]
MAX_TICKETS_PER_BOOKING = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    venue       TEXT    NOT NULL,
    event_date  TEXT    NOT NULL,
    event_time  TEXT    NOT NULL,
    capacity    INTEGER NOT NULL CHECK (capacity > 0),
    price       REAL    NOT NULL DEFAULT 0 CHECK (price >= 0),
    description TEXT,
    created_at  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS registrations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL,
    phone         TEXT    NOT NULL,
    tickets       INTEGER NOT NULL CHECK (tickets > 0),
    amount        REAL    NOT NULL,
    ticket_code   TEXT    NOT NULL UNIQUE,
    status        TEXT    NOT NULL DEFAULT 'CONFIRMED',
    checked_in_at TEXT,
    created_at    TEXT    NOT NULL
);
"""

SAMPLE_EVENTS = [
    ("Cloud Native 101: Kubernetes Live", "Technical", "Seminar Hall A", "2026-12-05", "10:00", 120, 0,
     "Hands-on intro to containers, Kubernetes and GitOps."),
    ("Rhythm Night 2026", "Music", "Open Air Theatre", "2026-12-12", "18:30", 300, 149,
     "Live bands and DJ night for the annual fest."),
    ("Inter-College Football Cup", "Sports", "University Ground", "2026-12-08", "08:00", 200, 50,
     "Knockout football tournament - spectator passes."),
    ("UI/UX Design Sprint", "Workshop", "Lab 304", "2026-12-10", "14:00", 40, 99,
     "Figma basics to a clickable prototype in 3 hours."),
]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "eventpass-dev-key"),
        DATABASE=os.environ.get("DB_PATH", os.path.join(app.instance_path, "eventpass.db")),
        APP_VERSION=os.environ.get("APP_VERSION", "local-dev"),
        SEED_DATA=os.environ.get("SEED_DATA", "true").lower() == "true",
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)

    # ---------------- database helpers ----------------
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = sqlite3.connect(app.config["DATABASE"])
        db.executescript(SCHEMA)
        if app.config["SEED_DATA"] and db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO events (title, category, venue, event_date, event_time, capacity, price,"
                " description, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                [e + (now(),) for e in SAMPLE_EVENTS])
        db.commit()
        db.close()

    init_db()

    def seats_booked(event_id):
        row = get_db().execute(
            "SELECT COALESCE(SUM(tickets),0) FROM registrations WHERE event_id=? AND status!='CANCELLED'",
            (event_id,)).fetchone()
        return row[0]

    def get_event(event_id):
        ev = get_db().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if ev is None:
            abort(404)
        return ev

    def event_with_stats(ev):
        booked = seats_booked(ev["id"])
        d = dict(ev)
        d["booked"] = booked
        d["available"] = ev["capacity"] - booked
        d["fill_pct"] = round(booked * 100 / ev["capacity"]) if ev["capacity"] else 0
        return d

    def new_ticket_code():
        db = get_db()
        while True:
            code = "EP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not db.execute("SELECT 1 FROM registrations WHERE ticket_code=?", (code,)).fetchone():
                return code

    def read_event_form(form):
        errors = []
        data = {k: form.get(k, "").strip() for k in
                ("title", "category", "venue", "event_date", "event_time", "capacity", "price", "description")}
        if not data["title"]:
            errors.append("Title is required.")
        if data["category"] not in CATEGORIES:
            errors.append("Choose a valid category.")
        if not data["venue"]:
            errors.append("Venue is required.")
        try:
            datetime.strptime(data["event_date"], "%Y-%m-%d")
        except ValueError:
            errors.append("Enter a valid date.")
        try:
            datetime.strptime(data["event_time"], "%H:%M")
        except ValueError:
            errors.append("Enter a valid time.")
        try:
            data["capacity"] = int(data["capacity"])
            if data["capacity"] <= 0:
                raise ValueError
        except ValueError:
            errors.append("Capacity must be a positive whole number.")
        try:
            data["price"] = float(data["price"] or 0)
            if data["price"] < 0:
                raise ValueError
        except ValueError:
            errors.append("Price cannot be negative.")
        return data, errors

    @app.context_processor
    def inject_globals():
        return {"app_version": app.config["APP_VERSION"], "categories": CATEGORIES,
                "pod_name": os.environ.get("HOSTNAME", "local")}

    # ---------------- pages ----------------
    @app.route("/")
    def dashboard():
        db = get_db()
        events = [event_with_stats(e) for e in
                  db.execute("SELECT * FROM events ORDER BY event_date, event_time").fetchall()]
        stats = db.execute(
            "SELECT COALESCE(SUM(tickets),0) AS sold, COALESCE(SUM(amount),0) AS revenue,"
            " COUNT(*) AS bookings,"
            " COALESCE(SUM(CASE WHEN checked_in_at IS NOT NULL THEN tickets END),0) AS checked_in"
            " FROM registrations WHERE status!='CANCELLED'").fetchone()
        sold = stats["sold"]
        summary = {
            "events": len(events),
            "bookings": stats["bookings"],
            "sold": sold,
            "revenue": stats["revenue"],
            "checkin_rate": round(stats["checked_in"] * 100 / sold) if sold else 0,
            "sold_out": sum(1 for e in events if e["available"] <= 0),
        }
        recent = db.execute(
            "SELECT r.*, e.title FROM registrations r JOIN events e ON e.id=r.event_id"
            " ORDER BY r.id DESC LIMIT 5").fetchall()
        return render_template("dashboard.html", summary=summary, events=events[:6], recent=recent)

    @app.route("/events")
    def events_list():
        q = request.args.get("q", "").strip()
        cat = request.args.get("category", "")
        sql, args = "SELECT * FROM events WHERE 1=1", []
        if q:
            sql += " AND (title LIKE ? OR venue LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        if cat in CATEGORIES:
            sql += " AND category=?"
            args.append(cat)
        sql += " ORDER BY event_date, event_time"
        events = [event_with_stats(e) for e in get_db().execute(sql, args).fetchall()]
        return render_template("events.html", events=events, q=q, cat=cat)

    @app.route("/events/new", methods=["GET", "POST"])
    def event_new():
        if request.method == "POST":
            data, errors = read_event_form(request.form)
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("event_form.html", event=data, mode="new"), 400
            db = get_db()
            db.execute(
                "INSERT INTO events (title, category, venue, event_date, event_time, capacity, price,"
                " description, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (data["title"], data["category"], data["venue"], data["event_date"], data["event_time"],
                 data["capacity"], data["price"], data["description"], now()))
            db.commit()
            flash(f"Event '{data['title']}' created.", "success")
            return redirect(url_for("events_list"))
        return render_template("event_form.html", event={}, mode="new")

    @app.route("/events/<int:event_id>")
    def event_detail(event_id):
        ev = event_with_stats(get_event(event_id))
        regs = get_db().execute(
            "SELECT * FROM registrations WHERE event_id=? ORDER BY id DESC", (event_id,)).fetchall()
        return render_template("event_detail.html", event=ev, regs=regs,
                               max_tickets=MAX_TICKETS_PER_BOOKING)

    @app.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
    def event_edit(event_id):
        ev = get_event(event_id)
        if request.method == "POST":
            data, errors = read_event_form(request.form)
            booked = seats_booked(event_id)
            if not errors and data["capacity"] < booked:
                errors.append(f"Capacity cannot be lower than seats already booked ({booked}).")
            if errors:
                for e in errors:
                    flash(e, "error")
                data["id"] = event_id
                return render_template("event_form.html", event=data, mode="edit"), 400
            db = get_db()
            db.execute(
                "UPDATE events SET title=?, category=?, venue=?, event_date=?, event_time=?, capacity=?,"
                " price=?, description=? WHERE id=?",
                (data["title"], data["category"], data["venue"], data["event_date"], data["event_time"],
                 data["capacity"], data["price"], data["description"], event_id))
            db.commit()
            flash("Event updated.", "success")
            return redirect(url_for("event_detail", event_id=event_id))
        return render_template("event_form.html", event=dict(ev), mode="edit")

    @app.route("/events/<int:event_id>/delete", methods=["POST"])
    def event_delete(event_id):
        ev = get_event(event_id)
        db = get_db()
        db.execute("DELETE FROM events WHERE id=?", (event_id,))
        db.commit()
        flash(f"Event '{ev['title']}' deleted.", "success")
        return redirect(url_for("events_list"))

    @app.route("/events/<int:event_id>/register", methods=["POST"])
    def register(event_id):
        ev = get_event(event_id)
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        try:
            tickets = int(request.form.get("tickets", "1"))
        except ValueError:
            tickets = 0
        error = None
        if not name or "@" not in email or len(phone) < 10:
            error = "Enter a name, a valid email and a 10-digit phone number."
        elif not 1 <= tickets <= MAX_TICKETS_PER_BOOKING:
            error = f"You can book 1 to {MAX_TICKETS_PER_BOOKING} tickets."
        elif get_db().execute(
                "SELECT 1 FROM registrations WHERE event_id=? AND email=? AND status!='CANCELLED'",
                (event_id, email)).fetchone():
            error = "This email is already registered for this event."
        else:
            available = ev["capacity"] - seats_booked(event_id)
            if tickets > available:
                error = ("Sorry, this event is sold out." if available <= 0
                         else f"Only {available} seat(s) left.")
        if error:
            flash(error, "error")
            return redirect(url_for("event_detail", event_id=event_id))
        code = new_ticket_code()
        db = get_db()
        db.execute(
            "INSERT INTO registrations (event_id, name, email, phone, tickets, amount, ticket_code, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (event_id, name, email, phone, tickets, tickets * ev["price"], code, now()))
        db.commit()
        flash("Booking confirmed! Save your ticket code.", "success")
        return redirect(url_for("ticket", code=code))

    @app.route("/ticket/<code>")
    def ticket(code):
        reg = get_db().execute(
            "SELECT r.*, e.title, e.venue, e.event_date, e.event_time FROM registrations r"
            " JOIN events e ON e.id=r.event_id WHERE r.ticket_code=?", (code.upper(),)).fetchone()
        if reg is None:
            abort(404)
        return render_template("ticket.html", reg=reg)

    @app.route("/ticket/<code>/cancel", methods=["POST"])
    def cancel(code):
        db = get_db()
        reg = db.execute("SELECT * FROM registrations WHERE ticket_code=?", (code.upper(),)).fetchone()
        if reg is None:
            abort(404)
        if reg["status"] == "CANCELLED":
            flash("This booking is already cancelled.", "error")
        elif reg["checked_in_at"]:
            flash("Checked-in tickets cannot be cancelled.", "error")
        else:
            db.execute("UPDATE registrations SET status='CANCELLED' WHERE id=?", (reg["id"],))
            db.commit()
            flash(f"Booking cancelled - {reg['tickets']} seat(s) released.", "success")
        return redirect(url_for("ticket", code=code.upper()))

    @app.route("/checkin", methods=["GET", "POST"])
    def checkin():
        result = None
        if request.method == "POST":
            code = request.form.get("code", "").strip().upper()
            db = get_db()
            reg = db.execute(
                "SELECT r.*, e.title FROM registrations r JOIN events e ON e.id=r.event_id"
                " WHERE r.ticket_code=?", (code,)).fetchone()
            if reg is None:
                result = ("error", f"No ticket found for code {code or '(empty)'}.")
            elif reg["status"] == "CANCELLED":
                result = ("error", f"Ticket {code} was cancelled - entry not allowed.")
            elif reg["checked_in_at"]:
                result = ("error", f"Ticket {code} was already checked in at {reg['checked_in_at']}.")
            else:
                db.execute("UPDATE registrations SET checked_in_at=? WHERE id=?", (now(), reg["id"]))
                db.commit()
                result = ("success", f"Welcome {reg['name']}! {reg['tickets']} entry pass(es) for "
                                     f"{reg['title']}.")
        return render_template("checkin.html", result=result)

    # ---------------- API ----------------
    @app.route("/api/events")
    def api_events():
        events = [event_with_stats(e) for e in
                  get_db().execute("SELECT * FROM events ORDER BY event_date").fetchall()]
        return jsonify(events)

    @app.route("/api/stats")
    def api_stats():
        db = get_db()
        row = db.execute("SELECT COALESCE(SUM(tickets),0), COALESCE(SUM(amount),0) FROM registrations"
                         " WHERE status!='CANCELLED'").fetchone()
        return jsonify({"events": db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                        "tickets_sold": row[0], "revenue": row[1], "version": app.config["APP_VERSION"]})

    @app.route("/health")
    def health():
        try:
            get_db().execute("SELECT 1")
            return jsonify({"status": "ok", "app": "eventpass", "version": app.config["APP_VERSION"]})
        except sqlite3.Error as exc:
            return jsonify({"status": "error", "detail": str(exc)}), 500

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
