import streamlit as st
import pandas as pd
import datetime
import requests

# --- CONFIGURATION ---

# 1. Your Public Data Link
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT43MImVIp6adY__EY41RO6KeVQ0j-zkwXkSQqKPp7F3X53bFzIJij32--uii2rqNsyHhjtmpmox5hK/pub?output=csv"

# 2. Your Google Form URL (Converted to formResponse for automation)
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSc9X8zW7LDbk_j4sZvvzrLCtn9jqHyBvnONgrgRsle0Xqt-Eg/formResponse"

# 3. Your Form Entry IDs
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

# Game Rules: Day Index 0=Mon, 6=Sun
VALUES = {0: 200, 1: 600, 2: 1000, 3: 400, 4: 1200, 5: 2000, 6: 0}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# --- FUNCTIONS ---
@st.cache_data(ttl=300) # Cache for 5 mins to align with Google Sheets publish rate
def get_data():
    try:
        # Timestamp hack to bypass some caching
        timestamp = datetime.datetime.now().timestamp()
        df = pd.read_csv(f"{CSV_URL}&t={timestamp}")
        return df
    except Exception:
        # Return empty structure if read fails
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
        # Silent background submission
        response = requests.post(FORM_URL, data=form_data)
        return response.status_code == 200
    except:
        return False

# --- SESSION STATE (For Instant Feedback) ---
if 'temp_data' not in st.session_state:
    st.session_state.temp_data = []

# --- LOAD DATA ---
csv_df = get_data()

# Merge CSV data with session state data (scores submitted in this session)
if st.session_state.temp_data:
    temp_df = pd.DataFrame(st.session_state.temp_data)
    # Ensure columns match for concatenation
    full_df = pd.concat([csv_df, temp_df], ignore_index=True)
else:
    full_df = csv_df

# --- SIDEBAR: INPUT ---
st.sidebar.header("📝 Log Today's Score")

# 1. User Selection
# Safely get unique users from the dataframe
if not full_df.empty and 'User' in full_df.columns:
    all_users = sorted(list(set(full_df['User'].dropna().astype(str).unique())))
else:
    all_users = []

user_mode = st.sidebar.radio("User Mode", ["Existing Player", "New Player"], horizontal=True)

if user_mode == "Existing Player" and all_users:
    user = st.sidebar.selectbox("Select Player", all_users)
else:
    user = st.sidebar.text_input("Enter Name")

# 2. Date Selection
date = st.sidebar.date_input("Date", datetime.date.today())
day_index = date.weekday()
day_name = DAYS[day_index]
base_value = VALUES[day_index]

st.sidebar.markdown(f"**Day:** {day_name}")

# 3. Game Logic
final_amount = 0
result_log = ""
ready_to_submit = False

if user:
    # --- SUNDAY (Wager Logic) ---
    if day_index == 6: 
        st.sidebar.info("🎲 It's Sunday! Wager time.")
        
        # Calculate Wager Limit (Sum of Mon-Sat for this specific week)
        if not full_df.empty and 'Date' in full_df.columns and 'Amount' in full_df.columns:
            full_df['DateObj'] = pd.to_datetime(full_df['Date'], errors='coerce').dt.date
            full_df['AmountNumeric'] = pd.to_numeric(full_df['Amount'], errors='coerce').fillna(0)
            
            # Find the Monday of this selected week
            start_of_week = date - datetime.timedelta(days=date.weekday())
            # Sum only amounts from this week, up to yesterday (Saturday)
            mask = (full_df['User'] == user) & (full_df['DateObj'] >= start_of_week) & (full_df['DateObj'] < date)
            current_week_total = full_df[mask]['AmountNumeric'].sum()
        else:
            current_week_total = 0
            
        wager_limit = abs(current_week_total)
        st.sidebar.write(f"Week Total: **${current_week_total:,.0f}**")
        st.sidebar.write(f"Max Wager: **${wager_limit:,.0f}**")
        
        # Wager Input
        wager = st.sidebar.number_input("Wager Amount", min_value=0, max_value=int(wager_limit) if wager_limit > 0 else 0, value=0)
        outcome = st.sidebar.radio("Did you get it right?", ["Correct", "Incorrect"])
        
        if outcome == "Correct":
            final_amount = wager
            result_log = "Correct (Wager)"
        else:
            final_amount = -wager
            result_log = "Incorrect (Wager)"
        
        ready_to_submit = True

    # --- MON-SAT (Fixed Value Logic) ---
    else:
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

    # --- SUBMIT BUTTON ---
    if ready_to_submit:
        st.sidebar.divider()
        st.sidebar.write(f"Saving Score: **${final_amount}**")
        
        if st.sidebar.button("Submit Score", type="primary"):
            success = send_data_to_google(user, date, day_name, result_log, final_amount)
            
            if success:
                st.sidebar.success("✅ Saved Successfully!")
                # Add to session state so it shows up instantly without waiting for Google Sheet refresh
                st.session_state.temp_data.append({
                    "User": user,
                    "Date": str(date),
                    "Day": day_name,
                    "Result": result_log,
                    "Amount": final_amount
                })
                st.rerun()
            else:
                st.sidebar.error("❌ Network Error: Could not connect to Google Forms.")

# --- DASHBOARD ---
if full_df.empty:
    st.info("No data found yet. Be the first to add a score!")
else:
    # Data Cleaning for Display
    if 'Date' in full_df.columns:
        full_df['Date'] = pd.to_datetime(full_df['Date'], errors='coerce')
    if 'Amount' in full_df.columns:
        full_df['Amount'] = pd.to_numeric(full_df['Amount'], errors='coerce').fillna(0)
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["Weekly Leaderboard", "Annual Leaderboard", "All Time"])
    
    def render_leaderboard(dataframe, time_filter=None):
        if dataframe.empty:
            st.write("No data available.")
            return

        if time_filter == "Weekly":
            today = pd.Timestamp.today()
            start_week = today - pd.Timedelta(days=today.dayofweek)
            start_week = start_week.replace(hour=0, minute=0, second=0, microsecond=0)
            dataframe = dataframe[dataframe['Date'] >= start_week]
        elif time_filter == "Annual":
             today = pd.Timestamp.today()
             dataframe = dataframe[dataframe['Date'].dt.year == today.year]
             
        if not dataframe.empty:
            leaderboard = dataframe.groupby('User')['Amount'].sum().sort_values(ascending=False).reset_index()
            leaderboard['Amount'] = leaderboard['Amount'].apply(lambda x: f"${x:,.0f}")
            # Add ranking index
            leaderboard.index = leaderboard.index + 1
            st.dataframe(leaderboard, use_container_width=True)
        else:
            st.write("No scores for this period yet.")

    with tab1:
        st.subheader("Current Week (Mon-Sun)")
        render_leaderboard(full_df, "Weekly")
    with tab2:
        st.subheader("This Year")
        render_leaderboard(full_df, "Annual")
    with tab3:
        st.subheader("All Time Hall of Fame")
        render_leaderboard(full_df)
    
    st.divider()
    st.caption("Updates sync to Google Sheets every ~5 minutes. Recent inputs are shown locally.")
