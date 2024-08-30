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
         user_email TEXT,
         user_name TEXT,
         date TEXT,
         time TEXT,
         summary TEXT)
    ''')
    conn.commit()
    cur.close()
    conn.close()

def save_to_db(user_email, user_name, summary):
    conn = get_db_connection()
    cur = conn.cursor()
    current_time = datetime.now().strftime('%H:%M:%S')
    cur.execute(
        "INSERT INTO logs (user_email, user_name, date, time, summary) VALUES (%s, %s, %s, %s, %s)",
        (user_email, user_name, today, current_time, summary)
    )
    conn.commit()
    cur.close()
    conn.close()

def get_past_entries(user_email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, time, summary FROM logs WHERE user_email = %s ORDER BY date DESC, time DESC",
        (user_email,)
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
    summary_prompt = f"Summarize the main points of the conversation, highlighting key emotions and discussion points. Format the summary as a concise journal entry. Today's date is {today}. Do not add extra information or assumptions which are not part of the conversation."
    summary_messages = [
        {"role": "system", "content": "You are a helpful assistant tasked with summarizing the conversation for users to then log the summary into their reflection journal. Write in the first-person."},
        {"role": "user", "content": summary_prompt},
    ] + messages

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=summary_messages,
        temperature=0.1,
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
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "conversation_ended" not in st.session_state:
    st.session_state.conversation_ended = False
if "first_response_given" not in st.session_state:
    st.session_state.first_response_given = False
if "summary_generated" not in st.session_state:
    st.session_state.summary_generated = False
if "page" not in st.session_state:
    st.session_state.page = "main"

# Sidebar for user info and past entries
with st.sidebar:
    st.title("Journal Dashboard")
    
    if st.session_state.user_email is None or st.session_state.user_name is None:
        user_email = st.text_input("What's your email?")
        user_name = st.text_input("What's your name?")
        if user_email and user_name:
            st.session_state.user_email = user_email
            st.session_state.user_name = user_name
            st.success(f"Welcome, {user_name}!")
            st.rerun()
    else:
        st.write(f"Welcome back, {st.session_state.user_name}!")
        
        # Add button to go to new journal entry page
        if st.button("New Journal Entry", key="new_entry_button", type="primary"):
            st.session_state.page = "main"
            st.session_state.conversation_ended = False
            st.session_state.messages = []
            st.session_state.first_response_given = False
            st.session_state.summary_generated = False
            if 'summary' in st.session_state:
                del st.session_state.summary
            if 'selected_entry' in st.session_state:
                del st.session_state.selected_entry
            st.rerun()
        
        # Add button to go to RAG page
        if st.button("Ask anything about yourself", key="rag_button", help="Ask questions about your past journal entries", type="primary"):
            st.session_state.page = "rag"
            st.rerun()
        
        # Only show past entries after user has logged in
        st.header("Past Entries")
        entries = get_past_entries(st.session_state.user_email)
        if entries:
            current_date = None
            for entry_id, date, time, summary in entries:
                if date != current_date:
                    st.subheader(date)
                    current_date = date
                if st.button(f"Entry at {time}", key=f"view_{entry_id}"):
                    st.session_state.selected_entry = (entry_id, date, time, summary)
                    st.session_state.page = "main"  # Ensure the main page is displayed
                    st.rerun()
        else:
            st.info("No past entries found.")

# Main area for new entries and displaying selected past entry
if st.session_state.page == "main":
    st.title("Daily Reflection Journal")

    if st.session_state.user_email and st.session_state.user_name:
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
                    st.session_state.summary_generated = False
                    if 'summary' in st.session_state:
                        del st.session_state.summary
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
                    temperature=0.1,
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
            if st.session_state.first_response_given and not st.session_state.conversation_ended and not st.session_state.summary_generated:
                if st.button("Finish Conversation and Log Entry"):
                    st.session_state.conversation_ended = True
                    with st.spinner("Generating your journal entry summary..."):
                        summary = generate_summary(st.session_state.messages)
                    
                    # Save summary to database
                    save_to_db(st.session_state.user_email, st.session_state.user_name, summary)
                    
                    st.session_state.summary = summary
                    st.session_state.summary_generated = True
                    st.rerun()  # Force a rerun to update the UI

            # Display summary if it has been generated
            if st.session_state.summary_generated:
                st.success("Great job reflecting on your day! Here's your journal entry summary:")
                st.markdown(st.session_state.summary)
                st.info("You can view past journal entries on the left")

            # Display a message if the conversation has ended
            if st.session_state.conversation_ended:
                if st.button("Log a New Entry"):
                    st.session_state.conversation_ended = False
                    st.session_state.messages = []
                    st.session_state.first_response_given = False
                    st.session_state.summary_generated = False
                    if 'summary' in st.session_state:
                        del st.session_state.summary
                    st.rerun()
    else:
        st.info("Please enter your email and name in the sidebar to start journaling.")

elif st.session_state.page == "rag":
    st.title("Ask anything about yourself")

    if st.session_state.user_email is None:
        st.warning("Please log in first.")
        st.session_state.page = "main"
        st.rerun()

    # Fetch all user's entries
    entries = get_past_entries(st.session_state.user_email)

    # Combine all entries into a single context string
    context = "\n\n".join([f"Date: {date}, Time: {time}\n{summary}" for _, date, time, summary in entries])

    # Text input for custom or selected question
    user_query = st.text_input("Select a question from below or type your own:", value=st.session_state.get('selected_question', ''))

    # Predefined questions
    predefined_questions = [
        "What brings me the most joy?",
        "What drains my energy most?",
        "How do I demonstrate love and care?",
        "What are some recurring themes from my entries?",
        "What book recommendations do you have based on my entries?"
    ]

    # Create buttons for predefined questions
    for question in predefined_questions:
        if st.button(question, key=f"btn_{question}"):
            st.session_state.selected_question = question
            st.rerun()  # Add this line to update the input box immediately

    # Create columns for the "Analyze" and "Return to Journal" buttons
    col1, col2 = st.columns(2)

    with col1:
        analyze_button = st.button("Analyze", type="primary")

    with col2:
        if st.button("Return to Journal"):
            st.session_state.page = "main"
            # Reset session state for new journal entry
            st.session_state.conversation_ended = False
            st.session_state.messages = []
            st.session_state.first_response_given = False
            st.session_state.summary_generated = False
            if 'summary' in st.session_state:
                del st.session_state.summary
            if 'selected_entry' in st.session_state:
                del st.session_state.selected_entry
            if 'selected_question' in st.session_state:
                del st.session_state.selected_question
            st.rerun()

    if user_query and analyze_button:
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

    # Clear the selected question when leaving the RAG page
    if st.session_state.page != "rag":
        if 'selected_question' in st.session_state:
            del st.session_state.selected_question
