import logging
import datetime
from io import StringIO

import streamlit as st
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
CSV_URL = st.secrets["CSV_URL"]
FORM_URL = st.secrets["FORM_URL"]
ENTRY_IDS = dict(st.secrets["entry_ids"])

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_VALUES = dict(zip(DAYS, [200, 600, 1000, 400, 1200, 2000, 0]))
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MAX_USERNAME_LENGTH = 30

# --- APP SETUP ---
st.set_page_config(page_title="Services Jeopardy Tracker", layout="wide")
st.title("🏆 Services Jeopardy Tracker")


# --- FUNCTIONS ---
@st.cache_data(ttl=300)
def get_data() -> pd.DataFrame:
    """Fetch score data from the published Google Sheet."""
    try:
        response = requests.get(CSV_URL, timeout=10)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        return df
    except Exception as e:
        logger.error("Failed to fetch data from Google Sheets: %s", e)
        st.warning("Could not load data from Google Sheets. Showing local data only.")
        return pd.DataFrame(columns=["User", "Date", "Day", "Result", "Amount"])


def send_data_to_google(user: str, date: datetime.date, day: str, result: str, amount: int) -> bool:
    """Submit a score entry to the Google Form."""
    form_data = {
        ENTRY_IDS["User"]: user,
        ENTRY_IDS["Date"]: str(date),
        ENTRY_IDS["Day"]: day,
        ENTRY_IDS["Result"]: result,
        ENTRY_IDS["Amount"]: str(amount),
    }
    try:
        response = requests.post(FORM_URL, data=form_data, timeout=10)
        if response.status_code != 200:
            logger.warning("Google Form returned status %d", response.status_code)
        return response.status_code == 200
    except requests.RequestException as e:
        logger.error("Failed to submit to Google Form: %s", e)
        return False


# --- SESSION STATE ---
if "temp_data" not in st.session_state:
    st.session_state.temp_data = []

# --- LOAD & PROCESS DATA ---
csv_df = get_data()

if st.session_state.temp_data:
    temp_df = pd.DataFrame(st.session_state.temp_data)
    full_df = pd.concat([csv_df, temp_df], ignore_index=True)
else:
    full_df = csv_df

if not full_df.empty:
    full_df["Date"] = pd.to_datetime(full_df["Date"], errors="coerce")
    full_df["Amount"] = pd.to_numeric(full_df["Amount"], errors="coerce").fillna(0)

    coerced_rows = full_df["Date"].isna().sum()
    if coerced_rows > 0:
        st.warning(f"{coerced_rows} row(s) had invalid dates and were excluded.")
        full_df = full_df.dropna(subset=["Date"])

    # Keep last entry per user/date — Google Sheets appends at the bottom,
    # so the last row for a given (User, Date) pair is the most recent edit.
    raw_df = full_df.copy()
    clean_df = full_df.drop_duplicates(subset=["User", "Date"], keep="last")
else:
    raw_df = pd.DataFrame()
    clean_df = pd.DataFrame()

# --- SIDEBAR ---
st.sidebar.header("📝 Log Scores")

if not full_df.empty and "User" in full_df.columns:
    all_users = sorted(set(full_df["User"].dropna().astype(str).unique()))
else:
    all_users = []

entry_mode = st.sidebar.radio("Entry Mode", ["Single Player", "Group Entry"], horizontal=True)

date = st.sidebar.date_input("Date", datetime.date.today(), max_value=datetime.date.today() + datetime.timedelta(days=2))
day_index = date.weekday()
day_name = DAYS[day_index]
base_value = DAY_VALUES[day_name]
is_sunday = day_index == 6

st.sidebar.markdown(f"**Day:** {day_name}")
if not is_sunday:
    st.sidebar.markdown(f"**Value:** ${base_value}")


def get_user_entry_count(username: str, target_date: datetime.date) -> int:
    """Count how many raw entries a user has for a given date."""
    if raw_df.empty:
        return 0
    matches = raw_df[
        (raw_df["User"] == username)
        & (pd.to_datetime(raw_df["Date"]).dt.date == target_date)
    ]
    return len(matches)


def get_wager_limit(username: str, target_date: datetime.date) -> int:
    """Calculate Sunday wager limit based on the user's Mon-Sat total for the week."""
    if clean_df.empty:
        return 0
    start_of_week = target_date - datetime.timedelta(days=target_date.weekday())
    mask = (
        (clean_df["User"] == username)
        & (clean_df["Date"].dt.date >= start_of_week)
        & (clean_df["Date"].dt.date < target_date)
    )
    return int(abs(clean_df[mask]["Amount"].sum()))


def compute_amount(result: str, value: int) -> int:
    """Convert a result string and point value into a signed amount."""
    if result == "Correct":
        return value
    elif result == "Incorrect":
        return -value
    return 0


# =============================================
# SINGLE PLAYER MODE
# =============================================
if entry_mode == "Single Player":
    user_mode = st.sidebar.radio("User Mode", ["Existing Player", "New Player"], horizontal=True)

    if user_mode == "Existing Player" and all_users:
        user = st.sidebar.selectbox("Select Player", all_users)
    else:
        user = st.sidebar.text_input("Enter Name", max_chars=MAX_USERNAME_LENGTH).strip()

    allowed_to_submit = bool(user)

    if not user and user_mode == "New Player":
        st.sidebar.info("Enter a player name to get started.")

    if user:
        entry_count = get_user_entry_count(user, date)
        if entry_count == 0:
            st.sidebar.info("No score logged for this date yet.")
        elif entry_count == 1:
            st.sidebar.warning("Score already logged. Submitting again will replace your previous entry (1 edit allowed).")
        else:
            st.sidebar.error("You've already used your one edit for this date.")
            allowed_to_submit = False

    final_amount = 0
    result_log = ""
    ready_to_submit = False

    if user and allowed_to_submit:
        if is_sunday:
            st.sidebar.info("🎲 It's Sunday! Wager time.")
            wager_limit = get_wager_limit(user, date)
            st.sidebar.write(f"Week Total: **${wager_limit:,}**")

            if wager_limit == 0:
                st.sidebar.warning("No games played this week — nothing to wager.")
            else:
                st.sidebar.caption(f"You can wager up to **${wager_limit:,}** (your absolute weekly total).")
                wager = st.sidebar.number_input("Wager Amount", min_value=0, max_value=wager_limit, value=0)
                outcome = st.sidebar.radio("Did you get it right?", ["Correct", "Incorrect"])

                if outcome == "Correct":
                    final_amount = wager
                    result_log = "Correct (Wager)"
                else:
                    final_amount = -wager
                    result_log = "Incorrect (Wager)"
                ready_to_submit = True
        else:
            outcome = st.sidebar.radio("Result", ["Correct", "Incorrect", "Pass/No Answer"])
            final_amount = compute_amount(outcome.split("/")[0], base_value)
            result_log = outcome.split("/")[0]
            ready_to_submit = True

        if ready_to_submit:
            st.sidebar.divider()
            st.sidebar.write(f"Saving Score: **${final_amount}**")

            if st.sidebar.button("Submit Score", type="primary"):
                success = send_data_to_google(user, date, day_name, result_log, final_amount)
                if success:
                    st.session_state.temp_data.append({
                        "User": user,
                        "Date": str(date),
                        "Day": day_name,
                        "Result": result_log,
                        "Amount": final_amount,
                    })
                    st.toast("Score saved!")
                    st.rerun()
                else:
                    st.sidebar.error("Failed to save. Check your connection and try again.")

# =============================================
# GROUP ENTRY MODE
# =============================================
elif entry_mode == "Group Entry":
    if not all_users:
        st.sidebar.info("No players found yet. Use Single Player mode to add the first player.")
    else:
        st.sidebar.caption("Select players and set results in the table below, then click Submit All.")

        selected_users = st.sidebar.multiselect(
            "Select Players",
            all_users,
            default=all_users,
        )

        if selected_users:
            RESULT_OPTIONS = ["—", "Correct", "Incorrect", "Pass"]

            if is_sunday:
                rows = []
                for u in selected_users:
                    entry_count = get_user_entry_count(u, date)
                    limit = get_wager_limit(u, date)
                    rows.append({
                        "Player": u,
                        "Result": "—",
                        "Wager": 0,
                        "Max Wager": limit,
                        "Entries": entry_count,
                    })
                grid_df = pd.DataFrame(rows)

                st.subheader(f"🎲 Group Wager Entry — {day_name}, {date.strftime('%b %d')}")
                st.caption("It's Sunday! Set each player's wager and result. Max Wager is based on their weekly total.")

                edited = st.data_editor(
                    grid_df,
                    column_config={
                        "Player": st.column_config.TextColumn("Player", disabled=True),
                        "Result": st.column_config.SelectboxColumn("Result", options=["—", "Correct", "Incorrect"], required=True),
                        "Wager": st.column_config.NumberColumn("Wager", min_value=0, format="$%d"),
                        "Max Wager": st.column_config.NumberColumn("Max Wager", format="$%d", disabled=True),
                        "Entries": None,
                    },
                    width="stretch",
                    hide_index=True,
                    key="group_sunday_editor",
                )
            else:
                rows = []
                for u in selected_users:
                    entry_count = get_user_entry_count(u, date)
                    rows.append({
                        "Player": u,
                        "Result": "—",
                        "Entries": entry_count,
                    })
                grid_df = pd.DataFrame(rows)

                st.subheader(f"Group Entry — {day_name}, {date.strftime('%b %d')} (${base_value})")
                st.caption("Set each player's result, then click Submit All Scores.")

                edited = st.data_editor(
                    grid_df,
                    column_config={
                        "Player": st.column_config.TextColumn("Player", disabled=True),
                        "Result": st.column_config.SelectboxColumn("Result", options=RESULT_OPTIONS, required=True),
                        "Entries": None,
                    },
                    width="stretch",
                    hide_index=True,
                    key="group_editor",
                )

            # --- Submission logic ---
            to_submit = edited[edited["Result"] != "—"].copy()
            skipped_edit_limit = []
            for _, row in to_submit.iterrows():
                if row["Entries"] > 1:
                    skipped_edit_limit.append(row["Player"])
            submittable = to_submit[~to_submit["Player"].isin(skipped_edit_limit)]

            if skipped_edit_limit:
                st.warning(f"Edit limit reached for: {', '.join(skipped_edit_limit)}. These players will be skipped.")

            pending_count = len(submittable)
            if pending_count == 0:
                st.info("Set at least one player's result to enable submission.")
            else:
                # Preview amounts
                preview_rows = []
                for _, row in submittable.iterrows():
                    if is_sunday:
                        wager = min(int(row["Wager"]), int(row["Max Wager"]))
                        amt = wager if row["Result"] == "Correct" else -wager
                        res = f"{row['Result']} (Wager)"
                    else:
                        amt = compute_amount(row["Result"], base_value)
                        res = row["Result"]
                    preview_rows.append({"Player": row["Player"], "Result": res, "Amount": amt})

                preview_df = pd.DataFrame(preview_rows)
                st.dataframe(
                    preview_df,
                    column_config={"Amount": st.column_config.NumberColumn("Amount", format="$%d")},
                    width="stretch",
                    hide_index=True,
                )

                if st.button(f"Submit All Scores ({pending_count} player{'s' if pending_count != 1 else ''})", type="primary"):
                    successes = 0
                    failures = []
                    for _, prow in preview_df.iterrows():
                        ok = send_data_to_google(prow["Player"], date, day_name, prow["Result"], prow["Amount"])
                        if ok:
                            st.session_state.temp_data.append({
                                "User": prow["Player"],
                                "Date": str(date),
                                "Day": day_name,
                                "Result": prow["Result"],
                                "Amount": prow["Amount"],
                            })
                            successes += 1
                        else:
                            failures.append(prow["Player"])

                    if successes > 0:
                        st.toast(f"{successes} score{'s' if successes != 1 else ''} saved!")
                    if failures:
                        st.error(f"Failed to save for: {', '.join(failures)}. Check your connection and try again.")
                    if successes > 0:
                        st.rerun()

# --- DASHBOARD ---
if clean_df.empty:
    st.info("No data found yet. Be the first to add a score!")
else:
    tab1, tab2, tab3 = st.tabs(["Weekly Leaderboard", "Monthly Leaderboard", "Annual Leaderboard"])

    today = pd.Timestamp.today()

    # --- 1. WEEKLY DASHBOARD ---
    with tab1:
        st.subheader("Current Week (Mon-Sun)")

        start_week = today - pd.Timedelta(days=today.dayofweek)
        start_week = start_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_week = start_week + pd.Timedelta(days=7)

        weekly_df = clean_df[(clean_df["Date"] >= start_week) & (clean_df["Date"] < end_week)].copy()

        if not weekly_df.empty:
            weekly_df["DayAbbrev"] = weekly_df["Date"].dt.day_name().str[:3]

            totals = weekly_df.groupby("User")["Amount"].sum().reset_index()
            totals.rename(columns={"Amount": "Total"}, inplace=True)

            def get_visual_result(result: str) -> str:
                res_lower = str(result).lower()
                if "incorrect" in res_lower:
                    return "❌"
                if "correct" in res_lower:
                    return "✅"
                if "pass" in res_lower:
                    return "**PASS**"
                return "N/A"

            weekly_df["Visual"] = weekly_df["Result"].apply(get_visual_result)

            pivot_visuals = weekly_df.pivot_table(
                index="User",
                columns="DayAbbrev",
                values="Visual",
                aggfunc="first",
            )

            for day in DAY_ABBREVIATIONS:
                if day not in pivot_visuals.columns:
                    pivot_visuals[day] = "N/A"

            pivot_visuals = pivot_visuals[DAY_ABBREVIATIONS]
            pivot_visuals = pivot_visuals.fillna("N/A")

            final_weekly_view = pivot_visuals.merge(totals, on="User", how="left")
            final_weekly_view = final_weekly_view.sort_values(by="Total", ascending=False)

            column_config = {
                "Total": st.column_config.NumberColumn("Total Score", format="$%d"),
            }
            for day in DAY_ABBREVIATIONS:
                column_config[day] = st.column_config.TextColumn(day, width="small")

            st.dataframe(
                final_weekly_view,
                width="stretch",
                column_config=column_config,
                hide_index=True,
            )
        else:
            st.write("No scores recorded for this week yet.")

    # --- 2. MONTHLY DASHBOARD ---
    with tab2:
        st.subheader(f"Leaderboard: {today.strftime('%B %Y')}")
        monthly_df = clean_df[
            (clean_df["Date"].dt.month == today.month) & (clean_df["Date"].dt.year == today.year)
        ]

        if not monthly_df.empty:
            leaderboard = monthly_df.groupby("User")["Amount"].sum().sort_values(ascending=False).reset_index()
            leaderboard.index = leaderboard.index + 1
            leaderboard.index.name = "Rank"

            st.dataframe(
                leaderboard,
                width="stretch",
                column_config={
                    "Amount": st.column_config.NumberColumn("Amount", format="$%d"),
                },
            )
        else:
            st.write("No scores this month.")

    # --- 3. ANNUAL DASHBOARD ---
    with tab3:
        st.subheader(f"{today.year} Performance")
        annual_df = clean_df[clean_df["Date"].dt.year == today.year].copy()

        if not annual_df.empty:
            annual_df["MonthNum"] = annual_df["Date"].dt.month
            pivot = annual_df.pivot_table(index="User", columns="MonthNum", values="Amount", aggfunc="sum")

            current_month_num = today.month
            for m in range(1, 13):
                if m not in pivot.columns:
                    pivot[m] = 0

            pivot = pivot.reindex(sorted(pivot.columns), axis=1)

            month_names = {m: MONTHS[m - 1] for m in pivot.columns}
            pivot = pivot.rename(columns=month_names)

            formatted_pivot = pivot.copy()

            for col_idx in range(1, 13):
                month_name = MONTHS[col_idx - 1]
                if col_idx > current_month_num:
                    formatted_pivot[month_name] = None

            # YTD total: sum only months up to and including the current month
            ytd_columns = [MONTHS[i] for i in range(current_month_num)]
            formatted_pivot["YTD Total"] = formatted_pivot[ytd_columns].sum(axis=1)
            formatted_pivot = formatted_pivot.sort_values(by="YTD Total", ascending=False)

            month_config = {
                m: st.column_config.NumberColumn(m, format="$%d") for m in MONTHS
            }
            month_config["YTD Total"] = st.column_config.NumberColumn("YTD Total", format="$%d")

            st.dataframe(
                formatted_pivot,
                width="stretch",
                column_config=month_config,
            )
        else:
            st.write("No data for this year.")

    st.divider()

    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("Data syncs from Google Sheets every 5 minutes. Recent submissions are shown locally.")
    with col2:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
