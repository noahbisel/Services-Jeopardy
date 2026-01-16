import streamlit as st
import pandas as pd
import datetime
import urllib.parse

# --- CONFIGURATION (UPDATE THESE!) ---
# 1. The "Published to Web" CSV link from File -> Share -> Publish to Web
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT43MImVIp6adY__EY41RO6KeVQ0j-zkwXkSQqKPp7F3X53bFzIJij32--uii2rqNsyHhjtmpmox5hK/pub?output=csv"

# 2. Your Google Form Base URL (everything before ?usp=pp_url)
FORM_BASE_URL = "https://docs.google.com/forms/d/e/1FAIpQLSc9X8zW7LDbk_j4sZvvzrLCtn9jqHyBvnONgrgRsle0Xqt-Eg/viewform"

# 3. The Entry IDs found in your "Get pre-filled link" (Step 1.3)
# Replace these numbers with YOUR specific entry IDs
ENTRY_IDS = {
    "User": "entry.240380346",    # Look for entry.ID for User
    "Date": "entry.1665164856",    # Look for entry.ID for Date
    "Day": "entry.425091818",     # Look for entry.ID for Day
    "Result": "entry.1179485822",  # Look for entry.ID for Result
    "Amount": "entry.1710124537"   # Look for entry.ID for Amount
}

# --- APP SETUP ---
st.set_page_config(page_title="Services Jeopardy Tracker", layout="wide")
st.title("Services Jeopardy Tracker")

VALUES = {0: 200, 1: 600, 2: 1000, 3: 400, 4: 1200, 5: 2000, 6: 0}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# --- FUNCTIONS ---
def get_data():
    try:
        # We add a timestamp to the URL to try and trick the cache, 
        # though Google often caches "Publish to Web" for ~5 mins regardless.
        df = pd.read_csv(f"{CSV_URL}&cachebuster={datetime.datetime.now().timestamp()}")
        return df
    except Exception as e:
        st.error("Could not read data. Check your CSV_URL.")
        return pd.DataFrame()

def generate_form_link(user, date, day_name, result, amount):
    params = {
        ENTRY_IDS["User"]: user,
        ENTRY_IDS["Date"]: str(date),
        ENTRY_IDS["Day"]: day_name,
        ENTRY_IDS["Result"]: result,
        ENTRY_IDS["Amount"]: str(amount) # Google forms expect strings
    }
    query_string = urllib.parse.urlencode(params)
    return f"{FORM_BASE_URL}?{query_string}"

# --- SIDEBAR ---
st.sidebar.header("📝 Log Today's Score")
df = get_data()

# User Selection
existing_users = sorted(df['User'].unique().tolist()) if not df.empty else []
user_mode = st.sidebar.radio("User Mode", ["Existing Player", "New Player"], horizontal=True)
if user_mode == "Existing Player" and existing_users:
    user = st.sidebar.selectbox("Select Player", existing_users)
else:
    user = st.sidebar.text_input("Enter Name")

# Date Selection
date = st.sidebar.date_input("Date", datetime.date.today())
day_index = date.weekday()
day_name = DAYS[day_index]
base_value = VALUES[day_index]
st.sidebar.markdown(f"**Day:** {day_name}")

# Logic
final_amount = 0
result_log = ""
ready_to_submit = False

if user:
    # SUNDAY LOGIC
    if day_index == 6: 
        st.sidebar.info("🎲 It's Sunday! Wager time.")
        
        # Calculate Wager Limit
        if not df.empty:
            df['DateObj'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
            start_of_week = date - datetime.timedelta(days=date.weekday())
            mask = (df['User'] == user) & (df['DateObj'] >= start_of_week) & (df['DateObj'] < date)
            current_week_total = df[mask]['Amount'].sum()
        else:
            current_week_total = 0
            
        wager_limit = abs(current_week_total) if not pd.isna(current_week_total) else 0
        st.sidebar.write(f"Week Total: **${current_week_total}** | Max Wager: **${wager_limit}**")
        
        wager = st.sidebar.number_input("Wager", min_value=0, max_value=int(wager_limit) if wager_limit > 0 else 0, value=0)
        outcome = st.sidebar.radio("Result", ["Correct", "Incorrect"])
        
        if outcome == "Correct":
            final_amount = wager
            result_log = "Correct (Wager)"
        else:
            final_amount = -wager
            result_log = "Incorrect (Wager)"
        
        ready_to_submit = True

    # MON-SAT LOGIC
    else:
        st.sidebar.markdown(f"Value: **${base_value}**")
        outcome = st.sidebar.radio("Result", ["Correct", "Incorrect", "Pass"])
        
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

    # SUBMIT BUTTON (LINK GENERATOR)
    if ready_to_submit:
        st.sidebar.divider()
        st.sidebar.write("### Confirm Score")
        st.sidebar.write(f"Amount to save: **${final_amount}**")
        
        # Generate the magic link
        submit_url = generate_form_link(user, date, day_name, result_log, final_amount)
        
        # We use a link button because we cannot POST directly without an API Key
        st.sidebar.markdown(f'''
        <a href="{submit_url}" target="_blank">
            <button style="width:100%; background-color:#FF4B4B; color:white; border:none; padding:10px; border-radius:5px; font-weight:bold; cursor:pointer;">
                Step 1: Click to Submit to Google
            </button>
        </a>
        ''', unsafe_allow_html=True)
        
        st.sidebar.info("ℹ️ After clicking, hit 'Submit' on the form tab. Data will appear here in ~5 mins.")

# --- DASHBOARD (Leaderboards) ---
if df.empty:
    st.info("No data found. Submit a score via the sidebar!")
else:
    # Basic cleaning
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
    
    tab1, tab2, tab3 = st.tabs(["Weekly", "Annual", "All Time"])
    
    def render_leaderboard(dataframe, time_filter=None):
        if time_filter == "Weekly":
            today = pd.Timestamp.today()
            start_week = today - pd.Timedelta(days=today.dayofweek)
            start_week = start_week.replace(hour=0, minute=0, second=0, microsecond=0)
            dataframe = dataframe[dataframe['Date'] >= start_week]
        elif time_filter == "Annual":
             today = pd.Timestamp.today()
             dataframe = dataframe[dataframe['Date'].dt.year == today.year]
             
        leaderboard = dataframe.groupby('User')['Amount'].sum().sort_values(ascending=False).reset_index()
        leaderboard['Amount'] = leaderboard['Amount'].apply(lambda x: f"${x:,.0f}")
        st.dataframe(leaderboard, use_container_width=True, hide_index=True)

    with tab1:
        st.subheader("Current Week")
        render_leaderboard(df, "Weekly")
    with tab2:
        st.subheader("This Year")
        render_leaderboard(df, "Annual")
    with tab3:
        st.subheader("All Time")
        render_leaderboard(df)
        
    st.divider()
    st.caption("Data refreshes automatically every ~5 minutes via Google Sheets.")