import streamlit as st
import os
from openai import OpenAI
from datetime import datetime
import pytz
import psycopg2
from psycopg2 import sql

# Load environment variables
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Database connection function
def get_db_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])

# Function to get past entries
def get_past_entries(email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, date, time, summary FROM entries WHERE email = %s ORDER BY date DESC, time DESC", (email,))
    entries = cur.fetchall()
    cur.close()
    conn.close()
    return entries

# Initialize session state
if 'page' not in st.session_state:
    st.session_state.page = 'main'
if 'user_email' not in st.session_state:
    st.session_state.user_email = None

def show_main_page():
    st.title("Journal Entry")

    # User authentication
    if st.session_state.user_email is None:
        email = st.text_input("Enter your email:")
        if st.button("Login"):
            st.session_state.user_email = email
            st.experimental_rerun()
    else:
        st.write(f"Logged in as: {st.session_state.user_email}")
        if st.button("Logout"):
            st.session_state.user_email = None
            st.experimental_rerun()

    if st.session_state.user_email:
        # Journal entry form
        journal_entry = st.text_area("Write your journal entry here:")
        if st.button("Submit"):
            if journal_entry:
                with st.spinner("Analyzing your entry..."):
                    # Call OpenAI API for summary
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that summarizes journal entries."},
                            {"role": "user", "content": f"Please summarize this journal entry in about 50 words:\n\n{journal_entry}"}
                        ],
                        temperature=0.1,
                    )
                    summary = response.choices[0].message.content

                    # Get current date and time
                    now = datetime.now(pytz.timezone('US/Pacific'))
                    date = now.strftime("%Y-%m-%d")
                    time = now.strftime("%H:%M:%S")

                    # Save to database
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO entries (email, date, time, entry, summary) VALUES (%s, %s, %s, %s, %s)",
                        (st.session_state.user_email, date, time, journal_entry, summary)
                    )
                    conn.commit()
                    cur.close()
                    conn.close()

                    st.success("Journal entry saved successfully!")
                    st.write("Summary:", summary)

def show_rag_page():
    st.title("Ask about your journal entries")

    # Ensure user is logged in
    if st.session_state.user_email is None:
        st.warning("Please log in first.")
        st.session_state.page = 'main'
        st.experimental_rerun()

    # Fetch all user's entries
    entries = get_past_entries(st.session_state.user_email)

    # Combine all entries into a single context string
    context = "\n\n".join([f"Date: {date}, Time: {time}\n{summary}" for _, date, time, summary in entries])

    # User input
    user_query = st.text_input("What would you like to know about your journal entries?")

    if user_query:
        with st.spinner("Analyzing your journal entries..."):
            messages = [
                {"role": "system", "content": "You are an AI assistant analyzing journal entries. Use the provided context to answer the user's question."},
                {"role": "user", "content": f"Context: {context}\n\nQuestion: {user_query}"}
            ]

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.1,
            )

            st.write("Answer:")
            st.write(response.choices[0].message.content)

    if st.button("Return to Journal"):
        st.session_state.page = 'main'
        st.experimental_rerun()

# Sidebar
with st.sidebar:
    st.title("Journal App")
    
    if st.session_state.user_email:
        st.write(f"Welcome, {st.session_state.user_email}!")
        
        # Display past entries
        st.subheader("Past Entries")
        entries = get_past_entries(st.session_state.user_email)
        for entry in entries:
            with st.expander(f"{entry[1]} {entry[2]}"):
                st.write(entry[3])

        if st.button("Ask about your journal entries"):
            st.session_state.page = 'rag'
            st.experimental_rerun()

# Main content
if st.session_state.page == 'main':
    show_main_page()
elif st.session_state.page == 'rag':
    show_rag_page()
