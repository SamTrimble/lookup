import os
import streamlit as st
import requests
import pandas as pd
import sqlite3
from datetime import date

# ==============================
# CONFIG
# ==============================
API_KEY = os.environ.get("API_KEY") or "YOUR_CONGRESS_GOV_API_KEY"
BASE_URL = "https://api.congress.gov/v3"

# Initialize SQLite DB
conn = sqlite3.connect("bills_cache.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS votes_cache (
    congress TEXT,
    bill_number TEXT,
    data TEXT,
    PRIMARY KEY (congress, bill_number)
)
""")
conn.commit()

# ==============================
# API FUNCTIONS
# ==============================
def search_bills(query, chamber_filter=None, congress_filter=None):
    url = f"{BASE_URL}/bill?query={query}&api_key={API_KEY}"
    r = requests.get(url)
    data = r.json()
    bills = []
    for b in data.get('bills', []):
        chamber = b.get('originChamber', '')
        congress = str(b.get('congress', ''))
        if chamber_filter and chamber.lower() != chamber_filter.lower():
            continue
        if congress_filter and congress != congress_filter:
            continue
        bills.append((b['title'], congress, b['number'], chamber))
    return bills

def get_votes(congress, number):
    c.execute("SELECT data FROM votes_cache WHERE congress=? AND bill_number=?", (congress, number))
    row = c.fetchone()
    if row:
        return pd.read_json(row[0])

    url = f"{BASE_URL}/bill/{congress}/{number}/votes?api_key={API_KEY}"
    r = requests.get(url)
    data = r.json()
    votes_list = []
    for v in data.get('votes', []):
        for mem in v.get('members', []):
            votes_list.append({
                'Member': mem.get('name'),
                'Party': mem.get('party'),
                'Vote': mem.get('vote'),
                'Chamber': v.get('chamber', ''),
                'Date': v.get('date', ''),
                'Bill': f"{congress}-{number}"
            })
    df = pd.DataFrame(votes_list)
    if not df.empty:
        c.execute("INSERT OR REPLACE INTO votes_cache (congress,bill_number,data) VALUES (?,?,?)",
                  (congress, number, df.to_json()))
        conn.commit()
    return df

# ==============================
# STREAMLIT UI
# ==============================
st.set_page_config(page_title="Congress Bill Lookup", layout="wide")
st.title("🔎 Special Interest Bill Lookup")
st.markdown("Search for bills by keyword, filter by chamber or session, and view votes!")

# Sidebar filters
st.sidebar.header("Filters")
search_term = st.sidebar.text_input("Enter a special interest keyword:", "")
chamber_filter = st.sidebar.selectbox("Filter by Chamber", ["", "House", "Senate"])
session_filter = st.sidebar.text_input("Filter by Congress Session (e.g., 118):")
vote_type = st.sidebar.selectbox("Show only votes of type:", ["All", "Yea", "Nay"])

if st.sidebar.button("Search Bills"):
    if not search_term.strip():
        st.warning("Please enter a search term.")
    else:
        bills = search_bills(search_term, chamber_filter if chamber_filter else None, session_filter if session_filter else None)
        if not bills:
            st.error("No bills found.")
        else:
            st.write(f"### Found {len(bills)} bills:")
            for title, congress, number, chamber in bills:
                if st.button(f"View Votes: {title} ({congress}-{number}) [{chamber}]"):
                    votes_df = get_votes(congress, number)
                    if votes_df.empty:
                        st.warning("No vote data available.")
                    else:
                        if vote_type != "All":
                            votes_df = votes_df[votes_df['Vote'] == vote_type]
                        st.write(f"#### Vote results for {title}")
                        st.dataframe(votes_df)
                        csv = votes_df.to_csv(index=False).encode('utf-8')
                        st.download_button("📥 Download CSV", csv, "votes.csv", "text/csv")
                        excel_file = "votes.xlsx"
                        votes_df.to_excel(excel_file, index=False)
                        with open(excel_file, "rb") as f:
                            st.download_button("📥 Download Excel", f, file_name="votes.xlsx")
