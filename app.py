import streamlit as st
import pandas as pd
import datetime
import requests
import time

# --- CONFIGURATION ---
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT43MImVIp6adY__EY41RO6KeVQ0j-zkwXkSQqKPp7F3X53bFzIJij32--uii2rqNsyHhjtmpmox5hK/pub?output=csv"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSc9X8zW7LDbk_j4sZvvzrLCtn9jqHyBvnONgrgRsle0Xqt-Eg/formResponse"

ENTRY_IDS = {
    "User": "entry.240380346",    
    "Date": "entry.1665164856",   
    "Day": "entry.425091818",     
    "Result": "entry.1179485822", 
    "Amount": "entry.1710124537"  
}

# --- APP SETUP ---
st.set_page_config(page_title="Services Jeopardy Tracker", layout="wide")
st.title("🏆 Services Jeopardy Tracker")

VALUES = {0: 200, 1: 600, 2: 1000, 3: 400, 4: 1200, 5: 2000, 6: 0}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# Short names for the column headers
DAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# --- FUNCTIONS ---
@st.cache_data(ttl=300)
def get_data():
    try:
        timestamp = datetime.datetime.now().timestamp()
        df = pd.read_csv(f"{CSV_URL}&t={timestamp}")
        return df
    except Exception:
        return pd.DataFrame(columns=["User", "Date", "Day", "Result", "Amount"])

def send_data_to_google(user, date, day, result, amount):
    form_data = {
        ENTRY_IDS["User"]: user,
        ENTRY_IDS["Date"]: str(date),
        ENTRY_IDS["Day"]: day,
        ENTRY_IDS["Result"]: result,
        ENTRY_IDS["Amount"]: str(amount)
    }
    try:
        response = requests.post(FORM_URL, data=form_data)
        return response.status_code == 200
    except:
        return False

# --- SESSION STATE ---
if 'temp_data' not in st.session_state:
    st.session_state.temp_data = []

# --- LOAD & PROCESS DATA ---
csv_df = get_data()

# Merge CSV with Session State
if st.session_state.temp_data:
    temp_df = pd.DataFrame(st.session_state.temp_data)
    full_df = pd.concat([csv_df, temp_df], ignore_index=True)
else:
    full_df = csv_df

# Standardize Data
if not full_df.empty:
    full_df['Date'] = pd.to_datetime(full_df['Date'], errors='coerce')
    full_df['Amount'] = pd.to_numeric(full_df['Amount'], errors='coerce').fillna(0)
    
    # Clean duplicates (Edits)
    raw_df = full_df.copy() 
    clean_df = full_df.drop_duplicates(subset=['User', 'Date'], keep='last')
else:
    raw_df = pd.DataFrame()
    clean_df = pd.DataFrame()

# --- SIDEBAR: INPUT ---
st.sidebar.header("📝 Log Today's Score")

if not full_df.empty and 'User' in full_df.columns:
    all_users = sorted(list(set(full_df['User'].dropna().astype(str).unique())))
else:
    all_users = []

user_mode = st.sidebar.radio("User Mode", ["Existing Player", "New Player"], horizontal=True)

if user_mode == "Existing Player" and all_users:
    user = st.sidebar.selectbox("Select Player", all_users)
else:
    user = st.sidebar.text_input("Enter Name")

date = st.sidebar.date_input("Date", datetime.date.today())
day_index = date.weekday()
day_name = DAYS[day_index]
base_value = VALUES[day_index]

st.sidebar.markdown(f"**Day:** {day_name}")

# --- SUBMISSION CONTROLS ---
allowed_to_submit = True

if user:
    if not raw_df.empty:
        user_entries_today = raw_df[
            (raw_df['User'] == user) & 
            (pd.to_datetime(raw_df['Date']).dt.date == date)
        ]
        entry_count = len(user_entries_today)
        
        if entry_count == 0:
            st.sidebar.info("First entry for this date.")
        elif entry_count == 1:
            st.sidebar.warning(f"⚠️ You have 1 entry. You may edit (submit again) ONCE.")
        else:
            st.sidebar.error("⛔ Only one edit allowed per day. You have reached the limit.")
            allowed_to_submit = False

# --- GAME LOGIC ---
final_amount = 0
result_log = ""
ready_to_submit = False

if user and allowed_to_submit:
    if day_index == 6: # Sunday
        st.sidebar.info("🎲 It's Sunday! Wager time.")
        
        if not clean_df.empty:
            start_of_week = date - datetime.timedelta(days=date.weekday())
            mask = (clean_df['User'] == user) & (clean_df['Date'].dt.date >= start_of_week) & (clean_df['Date'].dt.date < date)
            current_week_total = clean_df[mask]['Amount'].sum()
        else:
            current_week_total = 0
            
        wager_limit = abs(current_week_total)
        st.sidebar.write(f"Week Total: **${current_week_total:,.0f}**")
        
        wager = st.sidebar.number_input("Wager Amount", min_value=0, max_value=int(wager_limit) if wager_limit > 0 else 0, value=0)
        outcome = st.sidebar.radio("Did you get it right?", ["Correct", "Incorrect"])
        
        if outcome == "Correct":
            final_amount = wager
            result_log = "Correct (Wager)"
        else:
            final_amount = -wager
            result_log = "Incorrect (Wager)"
        ready_to_submit = True

    else: # Mon-Sat
        st.sidebar.markdown(f"Value: **${base_value}**")
        outcome = st.sidebar.radio("Result", ["Correct", "Incorrect", "Pass/No Answer"])
        
        if outcome == "Correct":
            final_amount = base_value
            result_log = "Correct"
        elif outcome == "Incorrect":
            final_amount = -base_value
            result_log = "Incorrect"
        else:
            final_amount = 0
            result_log = "Pass"
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
                    "Amount": final_amount
                })
                st.sidebar.success("✅ Success! Score saved.")
                time.sleep(1) 
                st.rerun()
            else:
                st.sidebar.error("❌ Failed to save. Please try again.")

# --- DASHBOARD ---
if clean_df.empty:
    st.info("No data found yet. Be the first to add a score!")
else:
    tab1, tab2, tab3 = st.tabs(["Weekly Leaderboard", "Monthly Leaderboard", "Annual Leaderboard"])
    
    today = pd.Timestamp.today()

    # --- 1. WEEKLY DASHBOARD (Enhanced Visuals) ---
    with tab1:
        st.subheader("Current Week (Mon-Sun)")
        
        # Calculate current week start
        start_week = today - pd.Timedelta(days=today.dayofweek)
        start_week = start_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_week = start_week + pd.Timedelta(days=7)

        # Filter for this week
        weekly_df = clean_df[(clean_df['Date'] >= start_week) & (clean_df['Date'] < end_week)].copy()

        if not weekly_df.empty:
            # Create abbreviations mapping
            # We map the full Day name to the Abbreviation (Monday -> Mon)
            # But we must be careful: if user enters data across years, 'Day' column might be tricky.
            # Best to derive Day Name directly from Date to be safe
            weekly_df['DayAbbrev'] = weekly_df['Date'].dt.day_name().apply(lambda x: x[:3])

            # 1. Calculate Totals separate from the visual table
            totals = weekly_df.groupby('User')['Amount'].sum().reset_index()
            totals.rename(columns={'Amount': 'Total'}, inplace=True)

            # 2. Create Visual Indicators
            def get_visual_result(result):
                res_lower = str(result).lower()
                if "correct" in res_lower and "incorrect" not in res_lower:
                    return "✅"
                elif "incorrect" in res_lower:
                    return "❌"
                elif "pass" in res_lower:
                    return "**PASS**"
                return "N/A"

            weekly_df['Visual'] = weekly_df['Result'].apply(get_visual_result)

            # 3. Pivot the table: Users (rows) x Days (columns)
            pivot_visuals = weekly_df.pivot_table(
                index='User', 
                columns='DayAbbrev', 
                values='Visual', 
                aggfunc='first' # Since clean_df handles duplicates, we just take the value
            )

            # 4. Reorder Columns explicitly to be Mon -> Sun
            # Ensure all days exist in columns even if no one played that day yet
            for day in DAY_ABBREVIATIONS:
                if day not in pivot_visuals.columns:
                    pivot_visuals[day] = "N/A" # Placeholder if column missing completely
            
            # Sort columns Mon-Sun
            pivot_visuals = pivot_visuals[DAY_ABBREVIATIONS]
            
            # Fill missing cells (did not play that specific day) with N/A
            pivot_visuals = pivot_visuals.fillna("N/A")

            # 5. Join with Totals
            final_weekly_view = pivot_visuals.merge(totals, on='User', how='left')
            
            # Sort by Total Descending
            final_weekly_view = final_weekly_view.sort_values(by='Total', ascending=False)
            
            # Configure formatting for Streamlit DataFrame
            # We want compact columns for days, and Currency for Total
            column_config = {
                "Total": st.column_config.NumberColumn("Total Score", format="$%d"),
            }
            # Add config for every day column to be small
            for day in DAY_ABBREVIATIONS:
                column_config[day] = st.column_config.TextColumn(day, width="small")

            st.dataframe(
                final_weekly_view, 
                use_container_width=True, 
                column_config=column_config, 
                hide_index=True
            )
        else:
            st.write("No scores recorded for this week yet.")

    # --- 2. MONTHLY DASHBOARD ---
    with tab2:
        st.subheader(f"Leaderboard: {today.strftime('%B %Y')}")
        monthly_df = clean_df[(clean_df['Date'].dt.month == today.month) & (clean_df['Date'].dt.year == today.year)]
        
        if not monthly_df.empty:
            leaderboard = monthly_df.groupby('User')['Amount'].sum().sort_values(ascending=False).reset_index()
            leaderboard['Amount'] = leaderboard['Amount'].apply(lambda x: f"${x:,.0f}")
            leaderboard.index = leaderboard.index + 1
            st.dataframe(leaderboard, use_container_width=True)
        else:
            st.write("No scores this month.")

    # --- 3. ANNUAL DASHBOARD (Pivot) ---
    with tab3:
        st.subheader(f"{today.year} Performance")
        annual_df = clean_df[clean_df['Date'].dt.year == today.year].copy()
        
        if not annual_df.empty:
            annual_df['MonthNum'] = annual_df['Date'].dt.month
            pivot = annual_df.pivot_table(index='User', columns='MonthNum', values='Amount', aggfunc='sum')
            
            current_month_num = today.month
            for m in range(1, 13):
                if m not in pivot.columns:
                    pivot[m] = 0 
            
            pivot = pivot.reindex(sorted(pivot.columns), axis=1)
            
            new_columns = {}
            for m in pivot.columns:
                new_columns[m] = MONTHS[m-1]
            
            pivot = pivot.rename(columns=new_columns)
            formatted_pivot = pivot.copy().astype(object)
            
            for col_idx in range(1, 13):
                month_name = MONTHS[col_idx-1]
                if col_idx > current_month_num:
                    formatted_pivot[month_name] = "--"
                else:
                    formatted_pivot[month_name] = formatted_pivot[month_name].apply(
                        lambda x: f"${x:,.0f}" if pd.notnull(x) and x != "--" else "$0"
                    )

            st.dataframe(formatted_pivot, use_container_width=True)
        else:
            st.write("No data for this year.")
    
    st.divider()
    st.caption("Updates sync to Google Sheets every ~5 minutes. Recent inputs are shown locally.")
