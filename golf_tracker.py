"""
Golf Practice Tracker
----------------------
A Streamlit app that lets a golfer log daily practice by club, track
weekly streaks, and get rule-based "what to practice next" recommendations
tailored to their skill level.

Run with:
    streamlit run golf_tracker.py
"""
import random
import sqlite3
from datetime import date, timedelta, datetime
from contextlib import contextmanager

import pandas as pd
import streamlit as st

DB_PATH = "golf_tracker.db"

# Club setup
CLUBS = [
    "Putter",
    "60° Wedge",
    "56° Wedge",
    "52° Wedge",
    "48° Wedge",
    "P Wedge",
    "9 Iron",
    "8 Iron",
    "7 Iron",
    "6 Iron",
    "5 Iron",
    "4 Iron",
    "3 Iron",
    "2 Iron",
    "4 Hybrid",
    "5 Wood",
    "3 Wood",
    "Driver",
]

CLUB_CATEGORY = {
    "Putter": "Putting",
    "60° Wedge": "Wedges",
    "56° Wedge": "Wedges",
    "52° Wedge": "Wedges",
    "48° Wedge": "Wedges",
    "P Wedge": "Wedges",
    "9 Iron": "Short Irons",
    "8 Iron": "Short Irons",
    "7 Iron": "Short Irons",
    "6 Iron": "Mid Irons",
    "5 Iron": "Mid Irons",
    "4 Iron": "Long Irons",
    "3 Iron": "Long Irons",
    "2 Iron": "Long Irons",
    "4 Hybrid": "Woods",
    "5 Wood": "Woods",
    "3 Wood": "Woods",
    "Driver": "Driver",
}

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Skill-level priority weights per category (higher = more emphasis).
# Drives which clubs get recommended when several are equally overdue.
SKILL_WEIGHTS = {
    "Beginner": {
        "Putting": 5, "Wedges": 5, "Short Irons": 4, "Mid Irons": 2,
        "Long Irons": 1, "Woods": 1, "Driver": 1,
    },
    "Intermediate": {
        "Putting": 4, "Wedges": 4, "Short Irons": 4, "Mid Irons": 3,
        "Long Irons": 3, "Woods": 2, "Driver": 3,
    },
    "Advanced": {
        "Putting": 3, "Wedges": 4, "Short Irons": 3, "Mid Irons": 3,
        "Long Irons": 3, "Woods": 3, "Driver": 4,
    },
}

# Sample drills shown alongside a recommended club, tuned by skill level.
DRILLS = {
    "Putting": {
        "Beginner": ["Gate drill from 3ft - build a onsistent stroke path.", 
                    "Make 10 putts from 3ft - focus on starting the ball on line.",
                    "Around the world - set up tees around the hole from 5 feet."],
        "Intermediate": ["Clock drill: putt 6 balls from 3/6/9 ft around the hole.",
                        "Lag putting: hit 10 putts from 20–30 ft and track distance from the hole.",
                         "Pressure putting: make 5 consecutive putts from 5 ft."],
        "Advanced": ["Lag putting ladder: 20/40/60 ft, focus on speed control.",
                     "Random-distance putting — change distance every putt.",
                     "One-putt challenge from 6–10 ft."],
    },
    "Wedges": {
        "Beginner": ["Land 10 balls on a towel 20 yards out, focus on contact.",
                    "Bump-and-run drill from just off the green.",
                    "Half-swing wedge shots to a wide landing zone."],
        "Intermediate": ["Hit to 3 landing zones (30/50/70 yds), track proximity.",
                        "Spin control drill: same distance, high vs low trajectory.",
                        "Up-and-down challenge from 3 spots around the green."],
        "Advanced": ["Trajectory control: same distance, 3 different ball flights.",
                    "Landing-zone precision from 3 distances, track feet from target.",
                    "Flop shot and low spinner from the same lie."],
    },
    "Short Irons":{
        "Beginner": ["Half-swing contact drill — ball-then-turf, low tee line.",
                    "Alignment stick drill for consistent swing path.",
                    "Target practice: 10 balls at one flag, count solid strikes."],
        "Intermediate": ["9-shot shape drill: high/low, draw/fade/straight.",
                        "Distance-matching drill between two clubs (e.g. 8i vs 9i).",
                        "Divot-direction drill to check swing path consistency."],
        "Advanced": ["Flighted approach shots into tight pins, track strokes gained.",
                    "Windy-day simulation: knockdown shots under a low ceiling.",
                    "Random distance drill — no repeats, adapt shot-to-shot."],
    },
    "Mid Irons":{
        "Beginner": ["Alignment stick drill for swing path, slow-motion reps.",
                    "Tee-height contact drill for consistent ball-first strikes."],
        "Intermediate": ["Distance control ladder in 10-yard increments.",
                        "Compare carry distance across 5i/6i to sharpen club selection."],
        "Advanced": ["Work a controlled draw and fade on demand.",
                    "Trajectory windows: low punch vs full flight, same club."],
    },
    "Long Irons":{
        "Beginner": ["Tee it slightly up, focus on solid contact over distance.",
                    "Hybrid vs long iron comparison — pick your go-to."],
        "Intermediate": [ "Compare iron vs hybrid dispersion on the range.",
                        "Fairway lie simulation drill for long-iron contact."],
        "Advanced": ["Low punch shots and stinger practice for course management.",
                    "Long-iron approach into a tight target, track proximity."],
    },
    "Woods":{
        "Beginner": ["Sweep drill off a low tee — focus on the strike, not power.",
                    "Fairway wood off the deck, focus on ball-first contact."],
        "Intermediate": ["Fairway wood accuracy: 10 balls at a target flag.",
                        "3-wood vs 5-wood distance-gap check."],
        "Advanced": ["Work both a fade and draw off the deck.",
                    "Low-trajectory fairway wood into the wind."],
    },
    "Driver":{
        "Beginner": ["Tee height and ball position drill for consistent contact.",
                    "Slow-tempo swings focused on balance, not distance."],
        "Intermediate": ["Fairway-finder: track % hit into a 30-yard-wide target.",
                        "Tempo drill: 3/4 swing for consistency before adding speed."],
        "Advanced": ["Launch monitor session: optimize launch angle and spin rate.",
                    "Shot-shape-on-demand: draw and fade off the tee."],
    },
}



# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                skill_level TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                practice_date TEXT NOT NULL,
                club TEXT NOT NULL,
                minutes INTEGER NOT NULL,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )


def get_or_create_user(name: str, skill_level: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET skill_level = ? WHERE id = ?", (skill_level, row["id"])
            )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO users (name, skill_level, created_at) VALUES (?, ?, ?)",
            (name, skill_level, datetime.now().isoformat()),
        )
        return cur.lastrowid


def log_practice(user_id: int, practice_date: date, club: str, minutes: int, notes: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, practice_date, club, minutes, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, practice_date.isoformat(), club, minutes, notes),
        )


def get_sessions_df(user_id: int) -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT practice_date, club, minutes, notes FROM sessions WHERE user_id = ? "
            "ORDER BY practice_date DESC",
            (user_id,),
        ).fetchall()
    df = pd.DataFrame(rows, columns=["practice_date", "club", "minutes", "notes"])
    if not df.empty:
        df["practice_date"] = pd.to_datetime(df["practice_date"]).dt.date
    return df


# ---------------------------------------------------------------------------
# Streak + recommendation logic
# ---------------------------------------------------------------------------

def compute_streak(practice_dates: set) -> int:
    """Consecutive-day streak ending today or yesterday (so a rest day today
    doesn't zero out a streak still 'alive' from yesterday)."""
    if not practice_dates:
        return 0
    today = date.today()
    anchor = today if today in practice_dates else today - timedelta(days=1)
    if anchor not in practice_dates:
        return 0
    streak = 0
    cursor = anchor
    while cursor in practice_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def days_since_last_practice(df: pd.DataFrame, club: str) -> int:
    club_rows = df[df["club"] == club]
    if club_rows.empty:
        return 999  # never practiced -> maximally overdue
    last = club_rows["practice_date"].max()
    return (date.today() - last).days


def get_recommendations(skill_level: str, df: pd.DataFrame, top_n: int = 3):
    """Rank clubs by (category weight for this skill level) x (how overdue
    the club is), and return the top N with a suggested drill."""
    weights = SKILL_WEIGHTS[skill_level]
    scored = []
    for club in CLUBS:
        category = CLUB_CATEGORY[club]
        overdue_days = days_since_last_practice(df, club)
        # Cap overdue contribution so a never-practiced club doesn't dominate
        # everything forever; still ranks high, just not absurdly so.
        overdue_score = min(overdue_days, 21)
        score = weights[category] * (1 + overdue_score / 7)
        scored.append((score, club, category, overdue_days))

    scored.sort(key=lambda x: x[0], reverse=True)
    recommendations = []
    for score, club, category, overdue_days in scored[:top_n]:
        drill = DRILLS[category][skill_level]
        if overdue_days >= 999:
            recency_note = "never logged"
        elif overdue_days == 0:
            recency_note = "practiced today"
        else:
            recency_note = f"{overdue_days} day(s) since last practiced"
        recommendations.append(
            {
                "club": club,
                "category": category,
                "drill": drill,
                "recency_note": recency_note,
            }
        )
    return recommendations


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def week_dates(reference: date) -> list:
    monday = reference - timedelta(days=reference.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def main():
    st.set_page_config(page_title="Golf Practice Tracker", page_icon="⛳", layout="wide")
    init_db()

    st.title("⛳ Golf Practice Tracker")

    # --- Profile setup (sidebar) ---
    st.sidebar.header("Your Profile")
    name = st.sidebar.text_input("Name", value=st.session_state.get("name", ""))
    skill_level = st.sidebar.selectbox(
        "Skill level", ["Beginner", "Intermediate", "Advanced"],
        index=["Beginner", "Intermediate", "Advanced"].index(
            st.session_state.get("skill_level", "Beginner")
        ),
    )

    if not name:
        st.info("Enter your name in the sidebar to get started.")
        return

    user_id = get_or_create_user(name, skill_level)
    st.session_state["name"] = name
    st.session_state["skill_level"] = skill_level

    df = get_sessions_df(user_id)
    practice_dates = set(df["practice_date"]) if not df.empty else set()
    streak = compute_streak(practice_dates)

    col1, col2, col3 = st.columns(3)
    col1.metric("Current Streak", f"{streak} day{'s' if streak != 1 else ''}")
    col2.metric("Sessions Logged", len(df))
    col3.metric("Skill Level", skill_level)

    st.divider()

    # --- Weekly grid ---
    st.subheader("This Week")
    dates = week_dates(date.today())
    cols = st.columns(7)
    for i, d in enumerate(dates):
        practiced = d in practice_dates
        with cols[i]:
            marker = "✅" if practiced else ("📍" if d == date.today() else "▫️")
            st.markdown(f"**{DAYS[i][:3]}**")
            st.markdown(f"{marker} {d.strftime('%m/%d')}")

    st.divider()

    # --- Log a session ---
    st.subheader("Log Practice")
    with st.form("log_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        log_date = c1.date_input("Date", value=date.today())
        club = c2.selectbox("Club", CLUBS)
        minutes = c3.number_input("Minutes", min_value=5, max_value=300, value=20, step=5)
        notes = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("Log Session")
        if submitted:
            log_practice(user_id, log_date, club, int(minutes), notes)
            st.success(f"Logged {club} practice on {log_date.strftime('%b %d')}.")
            st.rerun()

    st.divider()

    # --- Recommendations ---
    st.subheader("What to Practice Next")
    if df.empty:
        st.write(
            "No sessions logged yet — recommendations will sharpen once you log a "
            "few practice days. For now, here's a starting point for your level:"
        )
    recs = get_recommendations(skill_level, df)
    for rec in recs:
        with st.container(border=True):
            st.markdown(f"**{rec['club']}** · _{rec['category']}_")
            st.write(rec["drill"])
            st.caption(rec["recency_note"])

    st.divider()

    # --- History ---
    with st.expander("Practice History"):
        if df.empty:
            st.write("No sessions logged yet.")
        else:
            display_df = df.copy()
            display_df.columns = ["Date", "Club", "Minutes", "Notes"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
