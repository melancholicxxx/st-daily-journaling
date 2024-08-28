import streamlit as st
import os
from openai import OpenAI
from app_heroku import get_db_connection, get_past_entries
from streamlit_extras.switch_page_button import switch_page


# Load environment variables
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

st.title("Ask about your journal entries")

# Ensure user is logged in
if "user_email" not in st.session_state or st.session_state.user_email is None:
    st.warning("Please log in on the main page first.")
    st.stop()

# Fetch all user's entries
entries = get_past_entries(st.session_state.user_email)

# Combine all entries into a single context string
context = "\n\n".join([f"Date: {date}, Time: {time}\n{summary}" for _, date, time, summary in entries])

# User input
user_query = st.text_input("What would you like to know about your journal entries?")

if user_query:
    with st.spinner("Analyzing your journal entries..."):
        # Prepare the messages for the API call
        messages = [
            {"role": "system", "content": "You are an AI assistant analyzing journal entries. Use the provided context to answer the user's question."},
            {"role": "user", "content": f"Context: {context}\n\nQuestion: {user_query}"}
        ]

        # Call the OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.1,
        )

        # Display the response
        st.write("Answer:")
        st.write(response.choices[0].message.content)

# Add a button to return to the main page
if st.button("Return to Journal"):
    switch_page("app_heroku")
