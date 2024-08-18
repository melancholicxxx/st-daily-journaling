import streamlit as st
import os
from openai import OpenAI
from datetime import datetime
import psycopg2
from psycopg2 import sql
from urllib.parse import urlparse

# Load environment variables
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
today = datetime.today().strftime('%Y-%m-%d')

# Database setup and functions
def get_db_connection():
    db_url = os.environ['DATABASE_URL']
    result = urlparse(db_url)
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port
    return psycopg2.connect(
        database=database,
        user=username,
        password=password,
        host=hostname,
        port=port
    )

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS logs
        (id SERIAL PRIMARY KEY,
         user_name TEXT,
         date TEXT,
         time TEXT,
         summary TEXT)
    ''')
    conn.commit()
    cur.close()
    conn.close()

def save_to_db(user_name, summary):
    conn = get_db_connection()
    cur = conn.cursor()
    current_time = datetime.now().strftime('%H:%M:%S')
    cur.execute(
        "INSERT INTO logs (user_name, date, time, summary) VALUES (%s, %s, %s, %s)",
        (user_name, today, current_time, summary)
    )
    conn.commit()
    cur.close()
    conn.close()

def get_past_entries(user_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, time, summary FROM logs WHERE user_name = %s ORDER BY date DESC, time DESC",
        (user_name,)
    )
    entries = cur.fetchall()
    cur.close()
    conn.close()
    
    # Format the date and time
    formatted_entries = []
    for entry in entries:
        entry_id, date_str, time_str, summary = entry
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        time_obj = datetime.strptime(time_str, '%H:%M:%S')
        formatted_date = date_obj.strftime('%d %B %Y')
        formatted_time = time_obj.strftime('%I:%M%p').lower()
        formatted_entries.append((entry_id, formatted_date, formatted_time, summary))
    
    return formatted_entries

def delete_entry(entry_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM logs WHERE id = %s", (entry_id,))
    conn.commit()
    cur.close()
    conn.close()

def generate_summary(messages):
    summary_prompt = f"Summarize the main points of the conversation, highlighting key emotions and discussion points. Format the summary as a concise journal entry. Today's date is {today}."
    summary_messages = [
        {"role": "system", "content": "You are a helpful assistant tasked with summarizing the conversation for users to then log the summary into their reflection journal. Write in the first-person."},
        {"role": "user", "content": summary_prompt},
    ] + messages

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=summary_messages,
        stream=False,
    )
    return response.choices[0].message.content

# Initialize database
init_db()

# Streamlit app
st.set_page_config(layout="wide")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "conversation_ended" not in st.session_state:
    st.session_state.conversation_ended = False
if "first_response_given" not in st.session_state:
    st.session_state.first_response_given = False

# Sidebar for user info and past entries
with st.sidebar:
    st.title("Journal Dashboard")
    
    if st.session_state.user_name is None:
        user_name = st.text_input("What's your name?")
        if user_name:
            st.session_state.user_name = user_name
            st.success(f"Welcome, {user_name}!")
            st.rerun()
    else:
        st.write(f"Welcome back, {st.session_state.user_name}!")
    
    st.header("Past Entries")
    if st.session_state.user_name:
        entries = get_past_entries(st.session_state.user_name)
        if entries:
            current_date = None
            for entry_id, date, time, summary in entries:
                if date != current_date:
                    st.subheader(date)
                    current_date = date
                if st.button(f"Entry at {time}", key=f"view_{entry_id}"):
                    st.session_state.selected_entry = (entry_id, date, time, summary)
        else:
            st.info("No past entries found.")

# Main area for new entries and displaying selected past entry
st.title("Daily Reflection Journal")

if st.session_state.user_name:
    # Display selected past entry if any
    if 'selected_entry' in st.session_state:
        entry_id, date, time, summary = st.session_state.selected_entry
        st.header(f"Entry from {date} at {time}")
        st.write(summary)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Create New Entry"):
                del st.session_state.selected_entry
                st.session_state.conversation_ended = False
                st.session_state.messages = []
                st.session_state.first_response_given = False
                st.rerun()
        with col2:
            if st.button("Delete Entry"):
                delete_entry(entry_id)
                st.success("Entry deleted successfully!")
                del st.session_state.selected_entry
                st.rerun()
    else:
        # New entry interface
        st.subheader("Share your reflections for today 🧘🏻")
        
        # Display chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Chat input
        if not st.session_state.conversation_ended and (prompt := st.chat_input("How are you feeling right now?")):
            # Set first_response_given to True
            st.session_state.first_response_given = True
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Prepare messages for API call
            system_message = f"You are a close confidante. Your friend, {st.session_state.user_name}, will tell you how they are feeling and what's on their mind. Listen intently, prompt them to open up and share more about their thoughts and feelings without judgement. Be a friendly, supportive presence, and give a neutral, safe and comfortable tone. Compliment and encourage your friend as much as possible."
            
            messages = [
                {"role": "system", "content": system_message},
            ] + [
                {"role": msg["role"], "content": msg["content"]}
                for msg in st.session_state.messages
            ]

            # Create a placeholder for the assistant's response
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""

            # Stream the response
            for chunk in client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                stream=True,
            ):
                if chunk.choices[0].delta.content is not None:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + "▌")
            
            # Remove the blinking cursor
            message_placeholder.markdown(full_response)

            # Add assistant message to chat history
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        # End Conversation and Log Journal Entry button
        if st.session_state.first_response_given and not st.session_state.conversation_ended:
            if st.button("End Conversation and Log Journal Entry"):
                st.session_state.conversation_ended = True
                with st.spinner("Generating your journal entry summary..."):
                    summary = generate_summary(st.session_state.messages)
                
                # Save summary to database
                save_to_db(st.session_state.user_name, summary)
                
                st.success("Conversation ended. Here's your journal entry summary:")
                st.markdown(summary)
                st.info("Your journal entry has been saved to the database.")

        # Display a message if the conversation has ended
        if st.session_state.conversation_ended:
            if st.button("Start New Entry"):
                st.session_state.conversation_ended = False
                st.session_state.messages = []
                st.session_state.first_response_given = False
                st.rerun()
else:
    st.info("Please enter your name in the sidebar to start journaling.")
