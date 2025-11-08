"""
Adhera — Your Daily Health Companion
All accent/green text changed to WHITE (#FFFFFF).
Features:
- User login (per-user JSON persistence)
- CSV import for medicines
- Next-dose card + countdown
- Weekly adherence chart (last 14 days) using matplotlib
- Missed-dose notification + 'Send reminder' simulation
- Safe generated plant image if no external logo provided
"""

import streamlit as st
from datetime import datetime, date, time, timedelta
import pandas as pd
import json
from pathlib import Path
from PIL import Image, ImageDraw
import io
import base64
import matplotlib.pyplot as plt
import urllib.parse

# -------------------------
# CONFIG / THEME
# -------------------------
DEFAULT_DATA_FILE = Path("adhera_data.json")
PAGE_TITLE = "Adhera — Your Daily Health Companion"
PAGE_ICON = "🌿"

# ALL GREEN/ACCENT -> WHITE
ACCENT = "#FFFFFF"
TEXT_COLOR = "#FFFFFF"
BG = "#101010"      # dark background so white text is readable
CARD_BG = "#202020"

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide", initial_sidebar_state="expanded")

st.markdown(
    f"""
    <style>
    .stApp {{ background: {BG}; }}
    .block-container {{
        background: {CARD_BG};
        padding: 1.2rem 2rem;
        border-radius: 10px;
        color: {TEXT_COLOR};
    }}
    header[data-testid="stHeader"] {{ background: {CARD_BG} !important; box-shadow: none !important; }}
    .stSidebar, .css-1q8dd3e {{ background: {CARD_BG} !important; color: {TEXT_COLOR} !important; }}
    .css-1v3fvcr, .css-1d391kg {{ color: {TEXT_COLOR} !important; }}
    body, .stApp, h1, h2, h3, h4, h5, h6, p, span, div {{ color: {TEXT_COLOR} !important; }}
    .stDataFrame table td, .stDataFrame table th {{ color: {TEXT_COLOR} !important; }}
    button[role="button"] {{
        color: {TEXT_COLOR} !important;
        border-radius: 8px;
        border: 1px solid #555 !important;
        background: #333 !important;
    }}
    .stMetric, .stMetric label {{ color: {TEXT_COLOR} !important; }}
    .adhera-enc-card {{
        background: #2a2a2a;
        border: 1px solid #333;
        padding: 14px;
        border-radius: 10px;
        color: {TEXT_COLOR};
    }}
    .next-dose-card {{
        background: #2a2a2a;
        border: 1px solid #333;
        padding: 12px;
        border-radius: 10px;
        color: {TEXT_COLOR};
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------
# Helper: user-specific data file
# -------------------------
def get_data_file():
    """Return Path for current user. Uses st.session_state.user_file if set, else default file."""
    if "user_file" in st.session_state and st.session_state.user_file:
        return st.session_state.user_file
    return DEFAULT_DATA_FILE

# -------------------------
# Persistence (load/save)
# -------------------------
def load_state_from_disk():
    DATA_FILE = get_data_file()
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.session_state.medicines = data.get("medicines", [])
            st.session_state.history = data.get("history", [])
            st.session_state.next_id = data.get("next_id", 1)
        except Exception:
            st.session_state.medicines = []
            st.session_state.history = []
            st.session_state.next_id = 1
    else:
        st.session_state.medicines = []
        st.session_state.history = []
        st.session_state.next_id = 1

def save_state_to_disk():
    DATA_FILE = get_data_file()
    data = {
        "medicines": st.session_state.medicines,
        "history": st.session_state.history,
        "next_id": st.session_state.next_id
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        st.error(f"Could not save data: {e}")

# -------------------------
# Session init
# -------------------------
if "initialized" not in st.session_state:
    # prepare defaults until user logs in (login may override file)
    st.session_state.medicines = []
    st.session_state.history = []
    st.session_state.next_id = 1
    st.session_state.user = None
    st.session_state.user_file = None
    st.session_state.initialized = True
    # attempt to load default file so app shows existing data if present
    if DEFAULT_DATA_FILE.exists():
        load_state_from_disk()

# -------------------------
# Small utility helpers
# -------------------------
def safe_rerun():
    if hasattr(st, "experimental_rerun"):
        try:
            st.experimental_rerun()
        except Exception:
            pass
    elif hasattr(st, "rerun"):
        try:
            st.rerun()
        except Exception:
            pass

def friendly_time_str(hhmm: str) -> str:
    try:
        dt = datetime.strptime(hhmm, "%H:%M")
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return hhmm

# -------------------------
# Core actions: add/delete/mark
# -------------------------
def add_medicine(name: str, sched_time_str: str, notes: str = ""):
    med = {"id": st.session_state.next_id, "name": name.strip(), "sched_time": sched_time_str, "notes": notes.strip()}
    st.session_state.next_id += 1
    st.session_state.medicines.append(med)
    save_state_to_disk()

def delete_medicine(med_id: int):
    st.session_state.medicines = [m for m in st.session_state.medicines if m["id"] != med_id]
    save_state_to_disk()

def mark_taken(name: str, sched_time_str: str):
    today = date.today().isoformat()
    now_str = datetime.now().strftime("%H:%M")
    existing = next((h for h in st.session_state.history if h["date"] == today and h["name"] == name and h["sched_time"] == sched_time_str), None)
    if existing:
        existing["taken"] = True
        existing["taken_time"] = now_str
    else:
        st.session_state.history.append({"date": today, "name": name, "sched_time": sched_time_str, "taken": True, "taken_time": now_str})
    save_state_to_disk()

def mark_missed(name: str, sched_time_str: str):
    today = date.today().isoformat()
    existing = next((h for h in st.session_state.history if h["date"] == today and h["name"] == name and h["sched_time"] == sched_time_str), None)
    if not existing:
        st.session_state.history.append({"date": today, "name": name, "sched_time": sched_time_str, "taken": False, "taken_time": ""})
    save_state_to_disk()

# -------------------------
# Chart helpers (visual analytics)
# -------------------------
def daily_adherence_series(days_back=14):
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(days_back-1, -1, -1)]
    rows = []
    for d in dates:
        dstr = d.isoformat()
        scheduled_count = len(st.session_state.medicines) if st.session_state.medicines else 0
        if scheduled_count == 0:
            rows.append((d, 100.0))
            continue
        records = [h for h in st.session_state.history if h["date"] == dstr]
        taken_count = 0
        for s in st.session_state.medicines:
            found = any(r["name"] == s["name"] and r["sched_time"] == s["sched_time"] and r["taken"] for r in records)
            if found:
                taken_count += 1
        pct = (taken_count / scheduled_count) * 100
        rows.append((d, pct))
    df = pd.DataFrame(rows, columns=["date", "adherence"]).set_index("date")
    return df["adherence"]

def show_adherence_chart():
    ser = daily_adherence_series(days_back=14)
    if ser.empty:
        st.info("No adherence data to show.")
        return
    fig, ax = plt.subplots(figsize=(5,2.4))
    ax.plot(ser.index, ser.values, marker="o", linewidth=2)
    ax.set_ylim(0,100)
    ax.set_ylabel("Adherence %")
    ax.set_title("Last 14 days — Adherence")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    st.pyplot(fig)

# -------------------------
# Next-dose helpers
# -------------------------
def next_scheduled_dose(now=None):
    if now is None:
        now = datetime.now()
    upcoming = []
    for med in st.session_state.medicines:
        try:
            hh, mm = map(int, med["sched_time"].split(":"))
        except Exception:
            continue
        today_dt = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=hh, minutes=mm)
        if today_dt >= now:
            upcoming.append((today_dt, med))
        else:
            upcoming.append((today_dt + timedelta(days=1), med))
    if not upcoming:
        return None, None
    upcoming.sort(key=lambda x: x[0])
    return upcoming[0][1], upcoming[0][0]

def human_delta(dt):
    now = datetime.now()
    if dt <= now:
        return "Now"
    delta = dt - now
    days = delta.days
    secs = delta.seconds
    hours = secs // 3600
    mins = (secs % 3600) // 60
    if days > 0:
        return f"in {days}d {hours}h"
    if hours > 0:
        return f"in {hours}h {mins}m"
    if mins > 0:
        return f"in {mins}m"
    return "in a few moments"

# -------------------------
# Notification / reminder simulation
# -------------------------
def check_and_notify():
    today = date.today().isoformat()
    now = datetime.now()
    missed_records = [h for h in st.session_state.history if h["date"] == today and not h.get("taken", False)]
    scheduled_missed = []
    for med in st.session_state.medicines:
        try:
            hh, mm = map(int, med["sched_time"].split(":"))
        except Exception:
            continue
        sched_dt = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=hh, minutes=mm)
        rec = next((h for h in st.session_state.history if h["date"] == today and h["name"] == med["name"] and h["sched_time"] == med["sched_time"]), None)
        if sched_dt < now and not rec:
            scheduled_missed.append(med)
    total_missed = len(missed_records) + len(scheduled_missed)
    if total_missed > 0:
        st.warning(f"You have {total_missed} missed dose(s) today.")
        if st.button("Send reminder (mock)"):
            st.success("Reminder sent (simulation).")
    else:
        st.success("No missed doses detected today.")

# -------------------------
# CSV import helper
# -------------------------
def import_medicines_from_csv(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error("Could not read CSV: " + str(e))
        return
    required = {"name", "sched_time"}
    if not required.issubset(set(df.columns.str.lower())):
        st.error("CSV must contain at least 'name' and 'sched_time' columns.")
        return
    df.columns = [c.lower() for c in df.columns]
    added = 0
    for _, row in df.iterrows():
        nm = str(row.get("name","")).strip()
        stime = str(row.get("sched_time","")).strip()
        notes = str(row.get("notes","")).strip() if "notes" in df.columns else ""
        try:
            datetime.strptime(stime, "%H:%M")
        except Exception:
            continue
        add_medicine(nm, stime, notes)
        added += 1
    if added:
        st.success(f"Imported {added} medicines.")
    else:
        st.info("No valid medicines were imported (check time format HH:MM).")

# -------------------------
# Simple plant image generator (safe integers)
# -------------------------
def generate_plant_image(size=260, leaf_color=(34,139,86)):
    W = int(size); H = int(size)
    im = Image.new("RGBA", (W, H), (255,255,255,0))
    draw = ImageDraw.Draw(im)
    draw.ellipse([(int(W*0.05), int(H*0.05)), (int(W*0.95), int(H*0.95))], fill=(240,255,250,255))
    stem_x = int(W*0.5); stem_top = int(H*0.22); stem_bottom = int(H*0.72)
    draw.line([(stem_x, stem_top), (stem_x, stem_bottom)], fill=(70,110,60), width=6)
    leaves = [
        [(int(W*0.5)-6, int(H*0.36)), (int(W*0.32), int(H*0.28)), (int(W*0.30), int(H*0.36)), (int(W*0.5)-6, int(H*0.42))],
        [(int(W*0.5)+6, int(H*0.36)), (int(W*0.68), int(H*0.28)), (int(W*0.70), int(H*0.36)), (int(W*0.5)+6, int(H*0.42))],
        [(int(W*0.5)-6, int(H*0.52)), (int(W*0.36), int(H*0.48)), (int(W*0.34), int(H*0.56)), (int(W*0.5)-6, int(H*0.60))],
        [(int(W*0.5)+6, int(H*0.52)), (int(W*0.64), int(H*0.48)), (int(W*0.66), int(H*0.56)), (int(W*0.5)+6, int(H*0.60))],
        [(int(W*0.5)-6, int(H*0.28)), (int(W*0.40), int(H*0.24)), (int(W*0.39), int(H*0.30)), (int(W*0.5)-6, int(H*0.32))],
        [(int(W*0.5)+6, int(H*0.28)), (int(W*0.60), int(H*0.24)), (int(W*0.61), int(H*0.30)), (int(W*0.5)+6, int(H*0.32))],
    ]
    for poly in leaves:
        draw.polygon(poly, fill=leaf_color + (255,), outline=(int(leaf_color[0]*0.6), int(leaf_color[1]*0.6), int(leaf_color[2]*0.6)))
    draw.ellipse([(int(W*0.20), int(H*0.18)), (int(W*0.27), int(H*0.25))], fill=(200,245,220))
    draw.ellipse([(int(W*0.72), int(H*0.16)), (int(W*0.79), int(H*0.23))], fill=(200,245,220))
    draw.ellipse([(int(W*0.17), int(H*0.74)), (int(W*0.24), int(H*0.80))], fill=(255,230,230))
    return im.convert("RGB")

# -------------------------
# USER LOGIN UI (top)
# -------------------------
st.title(PAGE_TITLE)
st.write("A simple, caring interface to track medicines and daily adherence.")

if "user" not in st.session_state or not st.session_state.user:
    col1, col2 = st.columns([3,1])
    with col1:
        user_text = st.text_input("Enter your name to continue (optional):", value="")
    with col2:
        if st.button("Start"):
            if user_text.strip():
                safe_name = urllib.parse.quote_plus(user_text.strip().lower())
                st.session_state.user = user_text.strip()
                st.session_state.user_file = Path(f"adhera_{safe_name}.json")
            else:
                # anonymous mode uses default file
                st.session_state.user = None
                st.session_state.user_file = None
            load_state_from_disk()
            safe_rerun()
else:
    st.write(f"Welcome back, **{st.session_state.user}**")

# -------------------------
# LAYOUT: sidebar (logo, add, CSV import), main, right
# -------------------------
with st.sidebar:
    # logo: use external file if present else generated plant
    used_logo = False
    for candidate in ["logo.png", "logo.jpg", "logo.jpeg", "Logo.png"]:
        p = Path(candidate)
        if p.exists():
            try:
                st.image(str(p), width=140)
                used_logo = True
            except Exception:
                used_logo = False
            break
    if not used_logo:
        st.image(generate_plant_image(260, leaf_color=(34,139,86)), width=140)

    st.write("")  # spacer
    st.header("Add Medicine")
    with st.form("add_medicine_form", clear_on_submit=True):
        name = st.text_input("Medicine name", placeholder="e.g., Paracetamol")
        sched_time = st.time_input("Scheduled time", value=time(9,0))
        notes = st.text_area("Notes (optional)", placeholder="Dosage, after food, etc.")
        add_btn = st.form_submit_button("Add")
        if add_btn:
            if not name.strip():
                st.warning("Please enter a medicine name.")
            else:
                add_medicine(name, sched_time.strftime("%H:%M"), notes)
                st.success(f"Added {name} at {friendly_time_str(sched_time.strftime('%H:%M'))}")

    st.markdown("---")
    st.header("Bulk import (CSV)")
    st.write("CSV columns: name, sched_time (HH:MM), optional notes.")
    uploaded = st.file_uploader("Upload CSV to add medicines", type=["csv"])
    if uploaded:
        import_medicines_from_csv(uploaded)

    st.markdown("---")
    st.header("Your Medicines")
    if st.session_state.medicines:
        for med in st.session_state.medicines:
            cols = st.columns([3,1])
            cols[0].markdown(f"**{med['name']}** — {friendly_time_str(med['sched_time'])}")
            if cols[1].button("❌", key=f"del_{med['id']}"):
                delete_medicine(med["id"])
                safe_rerun()
    else:
        st.info("No medicines yet. Add one above or import a CSV.")

# -------------------------
# Main: Today's checklist + history
# -------------------------
left, right = st.columns([2,1])

with left:
    st.subheader("Today's Checklist")
    now = datetime.now()
    now_mins = now.hour * 60 + now.minute
    if st.session_state.medicines:
        for med in sorted(st.session_state.medicines, key=lambda x: x.get("sched_time","")):
            sched = med["sched_time"]
            try:
                hh, mm = map(int, sched.split(":"))
                sched_mins = hh*60 + mm
            except Exception:
                sched_mins = 0
            today_str = date.today().isoformat()
            rec = next((h for h in st.session_state.history if h["date"]==today_str and h["name"]==med["name"] and h["sched_time"]==sched), None)
            if rec:
                if rec["taken"]:
                    st.markdown(f"✅ **{med['name']}** — {friendly_time_str(sched)} (Taken at {rec['taken_time']})")
                else:
                    st.markdown(f"🔴 **{med['name']}** — {friendly_time_str(sched)} (Missed)")
            else:
                if now_mins < sched_mins - 15:
                    st.markdown(f"🟡 **{med['name']}** — {friendly_time_str(sched)} (Upcoming)")
                elif sched_mins - 15 <= now_mins <= sched_mins + 30:
                    st.markdown(f"⚪ **{med['name']}** — {friendly_time_str(sched)} (Due now/soon)")
                else:
                    st.markdown(f"🔴 **{med['name']}** — {friendly_time_str(sched)} (Missed)")
            c1,c2,c3 = st.columns([1,1,4])
            if c1.button("Taken", key=f"take_{med['id']}"):
                mark_taken(med["name"], sched)
                safe_rerun()
            if c2.button("Missed", key=f"miss_{med['id']}"):
                mark_missed(med["name"], sched)
                safe_rerun()
            if med.get("notes"):
                st.caption(f"Notes: {med['notes']}")
    else:
        st.info("No medicines added yet. Use the sidebar to add or import.")

    st.markdown("---")
    st.subheader("History (Recent First)")
    if st.session_state.history:
        df = pd.DataFrame(sorted(st.session_state.history, key=lambda x: (x["date"], x["sched_time"]), reverse=True))
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No history yet. Mark doses to build records.")

# -------------------------
# Right column: adherence, actions, encouragement, next-dose, chart, notifications
# -------------------------
with right:
    st.subheader("Adherence & Actions")

    # weekly adherence calculation (same logic as earlier)
    adherence = 100.0
    if st.session_state.medicines:
        scheduled = st.session_state.medicines
        today_d = date.today()
        start = today_d - timedelta(days=6)
        days = [(start + timedelta(days=i)).isoformat() for i in range(7)]
        scores = []
        for d in days:
            records = [h for h in st.session_state.history if h["date"]==d]
            taken_count = 0
            for s in scheduled:
                found = any(r["name"]==s["name"] and r["sched_time"]==s["sched_time"] and r["taken"] for r in records)
                if found:
                    taken_count += 1
            scores.append(taken_count/len(scheduled))
        adherence = round(sum(scores)/len(scores) * 100, 1)
    st.metric("Weekly adherence", f"{adherence}%")
    st.progress(min(max(int(adherence),0),100))

    # Export CSV
    csv_str = pd.DataFrame(st.session_state.history).to_csv(index=False)
    try:
        st.download_button("Export CSV", csv_str, file_name="adhera_history.csv", mime="text/csv")
    except Exception:
        st.markdown(f'<a href="data:file/csv;base64,{base64.b64encode(csv_str.encode()).decode()}" download="adhera_history.csv">Download CSV</a>', unsafe_allow_html=True)

    # Clear today's records
    if st.button("Clear today's records"):
        today = date.today().isoformat()
        st.session_state.history = [h for h in st.session_state.history if h["date"] != today]
        save_state_to_disk()
        safe_rerun()

    st.markdown("---")
    # Encouragement card (ACCENT is white as requested)
    badge_img = generate_plant_image(120, leaf_color=(200,200,200))
    buf = io.BytesIO(); badge_img.save(buf, format="PNG"); b64 = base64.b64encode(buf.getvalue()).decode()
    badge_datauri = f"data:image/png;base64,{b64}"

    if adherence >= 90:
        title = "Outstanding — keep it up!"
        message = "Your consistency is excellent. Small daily steps create big health wins."
    elif adherence >= 75:
        title = "Great job!"
        message = "You're staying steady — keep following the routine and celebrate progress."
    elif adherence >= 50:
        title = "You're doing well"
        message = "Good progress. Try small reminders to make it even easier to stay consistent."
    else:
        title = "Let's improve together"
        message = "Little changes help — set one reminder or ask a family member to help you today."

    enc_html = f"""
    <div class="adhera-enc-card">
      <div style="display:flex; align-items:center;">
        <div style="flex:1;">
          <div style="font-weight:700; color:{ACCENT}; margin-bottom:6px;">{title}</div>
          <div style="font-size:14px; margin-bottom:6px;">{message}</div>
          <div style="font-size:12px; color:{ACCENT};">Weekly adherence: <strong>{adherence}%</strong></div>
        </div>
        <div style="width:64px; margin-left:8px;"><img src="{badge_datauri}" style="width:64px; height:64px; border-radius:8px;"/></div>
      </div>
    </div>
    """
    st.markdown(enc_html, unsafe_allow_html=True)

    st.markdown("---")
    # Next dose card
    med_next, dt_next = next_scheduled_dose()
    if med_next:
        delta_txt = human_delta(dt_next)
        dt_str = dt_next.strftime("%a %d %b %I:%M %p")
        st.markdown("<div class='next-dose-card'>", unsafe_allow_html=True)
        st.markdown(f"**Next dose:** {med_next['name']} — {friendly_time_str(med_next['sched_time'])}")
        st.markdown(f"**When:** {dt_str} — **{delta_txt}**")
        if dt_next.date() == date.today():
            if st.button("Mark next as taken"):
                mark_taken(med_next["name"], med_next["sched_time"])
                st.success("Marked as taken.")
                safe_rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No scheduled medicines to compute the next dose.")

    st.markdown("---")
    # Show adherence chart (visual analytics)
    show_adherence_chart()

    st.markdown("---")
    # Notification simulation
    check_and_notify()

# -------------------------
# Admin options (danger) - optional
# -------------------------
st.markdown("---")
if st.checkbox("Show admin options"):
    if st.button("Reset ALL data (delete medicines & history)"):
        st.session_state.medicines = []
        st.session_state.history = []
        st.session_state.next_id = 1
        # remove user file if set
        try:
            df = get_data_file()
            if df.exists():
                df.unlink()
        except Exception:
            pass
        save_state_to_disk()
        st.success("All data cleared.")
    st.caption("Admin options are for advanced use. Use with caution.")
