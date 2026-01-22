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

# Merge CSV with Session State (Recent submissions)
if st.session_state.temp_data:
    temp_df = pd.DataFrame(st.session_state.temp_data)
    full_df = pd.concat([csv_df, temp_df], ignore_index=True)
else:
    full_df = csv_df

# Standardize Data Types
if not full_df.empty:
    full_df['Date'] = pd.to_datetime(full_df['Date'], errors='coerce')
    full_df['Amount'] = pd.to_numeric(full_df['Amount'], errors='coerce').fillna(0)
    
    # --- CRITICAL LOGIC: HANDLE EDITS ---
    # 1. We keep ALL rows to count how many times a user submitted today (for the limit check)
    raw_df = full_df.copy() 
    
    # 2. We create a "Clean" dataframe for Leaderboards that only keeps the LAST entry per User/Date
    # This effectively allows the "Edit" to overwrite the original score in the math
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

# --- SUBMISSION CONTROLS (Rate Limiting) ---
allowed_to_submit = True
submission_message = ""

if user:
    # Check how many times this user has submitted for this specific date
    if not raw_df.empty:
        # Convert date to timestamp for comparison
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
        
        # Calculate Weekly Total from CLEAN data (Last entry wins)
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
                time.sleep(1) # Give user a moment to see the message
                st.rerun()
            else:
                st.sidebar.error("❌ Failed to save. Please try again.")

# --- DASHBOARD ---
if clean_df.empty:
    st.info("No data found yet. Be the first to add a score!")
else:
    tab1, tab2, tab3 = st.tabs(["Weekly Leaderboard", "Monthly Leaderboard", "Annual Leaderboard"])
    
    today = pd.Timestamp.today()

    # 1. WEEKLY
    with tab1:
        st.subheader("Current Week (Mon-Sun)")
        start_week = today - pd.Timedelta(days=today.dayofweek)
        start_week = start_week.replace(hour=0, minute=0, second=0, microsecond=0)
        
        weekly_df = clean_df[clean_df['Date'] >= start_week]
        if not weekly_df.empty:
            leaderboard = weekly_df.groupby('User')['Amount'].sum().sort_values(ascending=False).reset_index()
            leaderboard['Amount'] = leaderboard['Amount'].apply(lambda x: f"${x:,.0f}")
            leaderboard.index = leaderboard.index + 1
            st.dataframe(leaderboard, use_container_width=True)
        else:
            st.write("No scores this week.")

    # 2. MONTHLY
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

    # 3. ANNUAL (PIVOT TABLE)
    with tab3:
        st.subheader(f"{today.year} Performance")
        annual_df = clean_df[clean_df['Date'].dt.year == today.year].copy()
        
        if not annual_df.empty:
            # Create a Month column for sorting/pivoting
            annual_df['MonthNum'] = annual_df['Date'].dt.month
            
            # Pivot: Rows=User, Cols=MonthNum, Values=Amount (Sum)
            pivot = annual_df.pivot_table(index='User', columns='MonthNum', values='Amount', aggfunc='sum')
            
            # Ensure all relevant columns exist (1 to current month)
            current_month_num = today.month
            
            # Reindex to ensure we have columns 1..12 (or at least 1..Current)
            # We want all 12 months in the table structure
            for m in range(1, 13):
                if m not in pivot.columns:
                    pivot[m] = 0 # Temp placeholder
            
            # Sort columns
            pivot = pivot.reindex(sorted(pivot.columns), axis=1)
            
            # Rename columns to Jan, Feb... and apply "--" logic
            new_columns = {}
            for m in pivot.columns:
                if m > current_month_num:
                    # Future months: We want to mask these values entirely in the display
                    # However, pandas columns need to be same type. We'll convert whole table to object (string) later
                    pass 
                new_columns[m] = MONTHS[m-1]
            
            pivot = pivot.rename(columns=new_columns)
            
            # Format numbers as Currency strings and mask future months
            formatted_pivot = pivot.copy().astype(object) # Convert to object to allow strings
            
            for col_idx in range(1, 13):
                month_name = MONTHS[col_idx-1]
                if col_idx > current_month_num:
                    formatted_pivot[month_name] = "--"
                else:
                    # Format existing numbers to currency, handle NaNs (zeros)
                    formatted_pivot[month_name] = formatted_pivot[month_name].apply(
                        lambda x: f"${x:,.0f}" if pd.notnull(x) and x != "--" else "$0"
                    )

            st.dataframe(formatted_pivot, use_container_width=True)
        else:
            st.write("No data for this year.")
    
    st.divider()
    st.caption("Updates sync to Google Sheets every ~5 minutes. Recent inputs are shown locally.")
