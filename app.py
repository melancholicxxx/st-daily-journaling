import streamlit as st
import os
from openai import OpenAI
from datetime import datetime
import psycopg2
from psycopg2 import sql
from urllib.parse import urlparse
import pytz
import streamlit.components.v1 as components
from st_supabase_connection import SupabaseConnection, execute_query
from streamlit_cookies_controller import CookieController
import time

# Set page config at the very beginning
st.set_page_config(layout="wide")

# Load environment variables
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
timezone = pytz.timezone('Asia/Singapore')  # GMT+8
today = datetime.now(timezone).strftime('%Y-%m-%d')

st_supabase = st.connection(
    name="supabase",
    type=SupabaseConnection,
    ttl=None,
    url=os.environ["SUPABASE_URL"],
    key=os.environ["SUPABASE_KEY"]
)

# Database setup and functions
def get_db_connection():
    db_url = os.environ['DATABASE_URL']
    result = urlparse(db_url)
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port
    conn = psycopg2.connect(
        database=database,
        user=username,
        password=password,
        host=hostname,
        port=port
    )
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Asia/Singapore';")
    conn.commit()
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create the table if it doesn't exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS logs
        (id SERIAL PRIMARY KEY,
         user_email TEXT,
         user_name TEXT,
         date TEXT,
         time TEXT,
         summary TEXT,
         emotions TEXT,
         people TEXT,
         topics TEXT)
    ''')
    conn.commit()
    cur.close()
    conn.close()

def save_to_db(user_email, user_name, summary, emotions, people, topics):
    conn = get_db_connection()
    cur = conn.cursor()
    current_time = datetime.now(timezone).strftime('%H:%M:%S')
    cur.execute(
        "INSERT INTO logs (user_email, user_name, date, time, summary, emotions, people, topics) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (user_email, user_name, today, current_time, summary, emotions, people, topics)
    )
    conn.commit()
    cur.close()
    conn.close()

def get_entries_count(user_email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM logs WHERE user_email = %s", (user_email,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

def get_past_entries(user_email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, time, summary, emotions, people, topics FROM logs WHERE user_email = %s ORDER BY date DESC, time DESC",
        (user_email,)
    )
    entries = cur.fetchall()
    cur.close()
    conn.close()
    
    # Format the date and time
    formatted_entries = []
    for entry in entries:
        entry_id, date_str, time_str, summary, emotions, people, topics = entry
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        time_obj = datetime.strptime(time_str, '%H:%M:%S')
        formatted_date = date_obj.strftime('%d %B %Y')
        formatted_time = time_obj.strftime('%I:%M%p').lower()
        formatted_entries.append((entry_id, formatted_date, formatted_time, summary, emotions, people, topics))
    
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

def detect_emotions(messages):
    emotion_prompt = "Analyze the conversation and detect the predominant emotions expressed. Tag the conversation with one or more of the following emotions: Joy, Sadness, Fear, Anger, Frustration. Return only the emotion tags separated by commas, without any additional text or explanation."
    emotion_messages = [
        {"role": "system", "content": "You are an emotion detection assistant. Analyze the conversation and return only the relevant emotion tags."},
        {"role": "user", "content": emotion_prompt},
    ] + messages

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=emotion_messages,
        temperature=0.1,
        stream=False,
    )
    return response.choices[0].message.content

def detect_people(messages):
    people_prompt = "Analyze the conversation and identify the names of people mentioned. Return only the names of people separated by commas, without any additional text or explanation. If no names are mentioned, return 'None'."
    people_messages = [
        {"role": "system", "content": "You are a people detection assistant. Analyze the conversation and return only the names of people mentioned."},
        {"role": "user", "content": people_prompt},
    ] + messages

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=people_messages,
        temperature=0.1,
        stream=False,
    )
    return response.choices[0].message.content

def detect_topics(messages):
    topics_prompt = "Analyze the conversation and identify the main topics discussed. Return only the topic names separated by commas, without any additional text or explanation. If no specific topics are identified, return 'None'."
    topics_messages = [
        {"role": "system", "content": "You are a topic detection assistant. Analyze the conversation and return only the main topics discussed."},
        {"role": "user", "content": topics_prompt},
    ] + messages

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=topics_messages,
        temperature=0.1,
        stream=False,
    )
    return response.choices[0].message.content

def emotion_tag(emotion):
    emotion_colors = {
        "Joy": ("#322E1D", "#FFD700"),  # Gold background, Black text
        "Sadness": ("#1F2B3F", "#90B7F9"),  # Royal Blue background, White text
        "Fear": ("#2A273D", "#B6ACF1"),  # Purple background, White text
        "Anger": ("#3E2420", "#EF9D94"),  # Red-Orange background, White text
        "Frustration": ("#292D33", "#A2ADBB")  # Saddle Brown background, White text
    }
    bg_color, text_color = emotion_colors.get(emotion.strip(), ("#808080", "#FFFFFF"))  # Default to gray bg, white text
    return f'<span style="background-color: {bg_color}; color: {text_color}; padding: 2px 6px; border-radius: 3px; margin-right: 5px;">{emotion}</span>'

def people_tag(person):
    return f'<span style="background-color: #4B0082; color: #FFFFFF; padding: 2px 6px; border-radius: 3px; margin-right: 5px;">{person}</span>'

def topic_tag(topic):
    return f'<span style="background-color: #008080; color: #FFFFFF; padding: 2px 6px; border-radius: 3px; margin-right: 5px;">{topic}</span>'

# Add these functions for auth management
def register_user(email, password, name):
    try:
        response = st_supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "name": name
                }
            }
        })
        return response
    except Exception as e:
        st.error(f"Registration failed: {str(e)}")
        return None

def login_user(email, password):
    try:
        response = st_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        if response:
            persist_login(response.user)
            time.sleep(0.5)
            st.rerun()
        return response
    except Exception as e:
        st.error(f"Login failed: {str(e)}")
        return None

# Initialize the cookies controller
cookie_controller = CookieController()

def persist_login(user_data):
    """Persist login data in cookies and session state"""
    cookie_controller.set("user_email", user_data.email)
    cookie_controller.set("user_name", user_data.user_metadata.get('name', ''))
    st.session_state.user_email = user_data.email
    st.session_state.user_name = user_data.user_metadata.get('name', '')

def clear_login():
    """Clear login data from cookies and session state"""
    cookie_controller.set("user_email", "", max_age=0)
    cookie_controller.set("user_name", "", max_age=0)
    st.session_state.user_email = None
    st.session_state.user_name = None

def check_login_session():
    """Check if user is logged in via cookies"""
    user_email = cookie_controller.get("user_email")
    user_name = cookie_controller.get("user_name")
    if user_email and user_name:
        st.session_state.user_email = user_email
        st.session_state.user_name = user_name
        return True
    return False

# Initialize database
init_db()

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

# Check for existing login session
check_login_session()

# Sidebar for user info and past entries
with st.sidebar:    
    if st.session_state.user_email is None or st.session_state.user_name is None:
        st.title("Login or Register")
        tab1, tab2 = st.tabs(["Login", "Register"])
        
        with tab1:
            login_email = st.text_input("Email", key="login_email")
            login_password = st.text_input("Password", type="password", key="login_password")
            
            if st.button("Login", key="login_button"):
                if login_email and login_password:
                    response = login_user(login_email, login_password)
                    if response:
                        user_data = response.user
                        st.session_state.user_email = user_data.email
                        st.session_state.user_name = user_data.user_metadata.get('name', '')
                        st.rerun()
            
            # Add contact support email link
            st.markdown('<div style="text-align: center;"><a href="mailto:support@mydailyjournal.xyz">Contact Support</a></div>', unsafe_allow_html=True)
        
        with tab2:
            reg_email = st.text_input("Email", key="reg_email")
            reg_name = st.text_input("Name", key="reg_name")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            
            if st.button("Register", key="register_button"):
                if reg_email and reg_name and reg_password:
                    response = register_user(reg_email, reg_password, reg_name)
                    if response:
                        st.success("Check your email for verification.")
                        time.sleep(10)
                        st.rerun()
    else:
        entries_count = get_entries_count(st.session_state.user_email)
        st.title("Dashboard")
        st.markdown(f"Welcome back, {st.session_state.user_name}! You've created **{entries_count}** entries so far. Continue on the path!")
        
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
        if st.button("Ask anything about yourself", key="rag_button", type="primary"):
            st.session_state.page = "rag"
            st.rerun()
        
        # Add Past Journal Entries button
        if st.button("Past Journal Entries", key="past_entries_button", type="primary"):
            st.session_state.page = "past_entries"
            st.rerun()
        
        # Add "Share Feedback" and "Logout" link at the bottom of the sidebar
        if st.button("Logout"):
            # Sign out from Supabase
            st_supabase.auth.sign_out()
            # Clear local session data
            clear_login()
            # Rerun the app to refresh the state
            st.rerun()

        #Mindfulness Podcasts link
        st.markdown("---")
        podcast_url = "https://midi-zydeco-b0b.notion.site/Mindfulness-Podcasts-109bc7bdae64802a89e5dee7493dc5c8"
        st.markdown(f'<div style="text-align: center;"><a href="{podcast_url}" target="_blank">Mindfulness Podcasts</a></div>', unsafe_allow_html=True)
        
        # Keep the feedback link
        feedback_url = "https://i0cphmhv362.typeform.com/to/gL3M2OdT"
        st.markdown(f'<div style="text-align: center;"><a href="{feedback_url}" target="_blank">Share Feedback</a></div>', unsafe_allow_html=True)

# Main area for new entries and displaying selected past entry
if st.session_state.page == "main":
    st.title("Daily Reflection Journal")

    if st.session_state.user_email and st.session_state.user_name:
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
                with st.spinner("Generating your journal entry summary, detecting emotions, people, and topics..."):
                    summary = generate_summary(st.session_state.messages)
                    emotions = detect_emotions(st.session_state.messages)
                    people = detect_people(st.session_state.messages)
                    topics = detect_topics(st.session_state.messages)
                
                # Save summary, emotions, people, and topics to database
                save_to_db(st.session_state.user_email, st.session_state.user_name, summary, emotions, people, topics)
                
                st.session_state.summary = summary
                st.session_state.emotions = emotions
                st.session_state.people = people
                st.session_state.topics = topics
                st.session_state.summary_generated = True
                st.rerun()  # Force a rerun to update the UI

        # Display summary, emotions, people, and topics if they have been generated
        if st.session_state.summary_generated:
            st.success("Great job reflecting on your day! Here's your journal entry summary:")
            st.markdown(st.session_state.summary)
            
            # Display emotions with colored tags
            st.write("Detected emotions:")
            emotion_html = "".join(emotion_tag(e.strip()) for e in st.session_state.emotions.split(','))
            st.markdown(emotion_html, unsafe_allow_html=True)
            
            # Display people with colored tags
            st.write("People mentioned:")
            people_html = "".join(people_tag(p.strip()) for p in st.session_state.people.split(',') if p.strip() != 'None')
            st.markdown(people_html if people_html else "No specific people mentioned", unsafe_allow_html=True)
            
            # Display topics with colored tags
            st.write("Topics discussed:")
            topics_html = "".join(topic_tag(t.strip()) for t in st.session_state.topics.split(',') if t.strip() != 'None')
            st.markdown(topics_html if topics_html else "No specific topics identified", unsafe_allow_html=True)

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
        st.info("Enter your email and name in the sidebar to start journaling.")

elif st.session_state.page == "rag":
    st.title("Ask anything about yourself, based on past journal entries")

    if st.session_state.user_email is None:
        st.warning("Please log in first.")
        st.session_state.page = "main"
        st.rerun()

    # Fetch all user's entries
    entries = get_past_entries(st.session_state.user_email)

    # Combine all entries into a single context string
    context = "\n\n".join([f"Date: {date}, Time: {time}\n{summary}\nEmotions: {emotions}\nPeople: {people}\nTopics: {topics}" for _, date, time, summary, emotions, people, topics in entries])

    # Text input for custom or selected question
    user_query = st.text_input("", value=st.session_state.get('selected_question', ''), placeholder="Select a question from below or type your own")

    # Predefined questions
    predefined_questions = [
        "What brings me the most joy?",
        "What drains my energy most?",
        "What are some recurring topics from my entries?",
        "What book recommendations do you have based on my entries?",
        "Count of entries by emotions and give the corresponding dates",
    ]

    # Create buttons for predefined questions
    for question in predefined_questions:
          if st.button(question, key=f"btn_{question}"):
            st.session_state.selected_question = question
            st.rerun()  # Add this line to update the input box immediately

    # Create a single column for the "Analyze" button
    analyze_button = st.button("Analyze Question", type="primary")

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

    # Add horizontal line and Visualisations header
    st.markdown("---")
    st.header("Visualisations")

    # Clear the selected question when leaving the RAG page
    if st.session_state.page != "rag":
        if 'selected_question' in st.session_state:
            del st.session_state.selected_question

# Add new elif condition for past_entries page after the RAG page condition
elif st.session_state.page == "past_entries":
    st.title("Past Journal Entries")
    
    if st.session_state.user_email is None:
        st.warning("Please log in first.")
        st.session_state.page = "main"
        st.rerun()
    
    entries = get_past_entries(st.session_state.user_email)
    if entries:
        # Create sets of unique emotions, people, and topics from all entries
        all_emotions = set()
        all_people = set()
        all_topics = set()
        
        for _, _, _, _, emotions, people, topics in entries: # _ means fields we don't need in entries. We only need emotions, people, and topics.
            all_emotions.update([e.strip() for e in emotions.split(',')]) # Splits the emotions, people, and topics strings (which are comma-separated) and Updates sets with unique values.
            if people != 'None':
                all_people.update([p.strip() for p in people.split(',')])
            if topics != 'None':
                all_topics.update([t.strip() for t in topics.split(',')])
        
        # Convert sets to sorted lists
        all_emotions = sorted(list(all_emotions))
        all_people = sorted(list(all_people))
        all_topics = sorted(list(all_topics))
        
        # Create filter columns
        col1, col2, col3 = st.columns(3)
        
        with col1:
            selected_emotions = st.multiselect(
                "Filter by Emotions",
                all_emotions,
                placeholder="Select emotions..."
            )
            
        with col2:
            selected_people = st.multiselect(
                "Filter by People",
                all_people,
                placeholder="Select people..."
            )
            
        with col3:
            selected_topics = st.multiselect(
                "Filter by Topics",
                all_topics,
                placeholder="Select topics..."
            )
        
        # Filter entries based on selections
        filtered_entries = entries
        if selected_emotions:
            filtered_entries = [
                entry for entry in filtered_entries
                if any(emotion.strip() in selected_emotions # If any emotion in the entry matches the selected emotions, then include the entry in filtered_entries.
                      for emotion in entry[4].split(',')) #4 cos emotions is the 5th column in entries
            ]
        
        if selected_people:
            filtered_entries = [
                entry for entry in filtered_entries
                if entry[5] != 'None' and
                any(person.strip() in selected_people 
                    for person in entry[5].split(',')) #5 cos people is the 6th column in entries
            ]
            
        if selected_topics:
            filtered_entries = [
                entry for entry in filtered_entries
                if entry[6] != 'None' and
                any(topic.strip() in selected_topics 
                    for topic in entry[6].split(',')) #6 cos topics is the 7th column in entries
            ]
        
        # Display filtered entries
        current_date = None
        for entry_id, date, time, summary, emotions, people, topics in filtered_entries:
            if date != current_date:
                st.header(date)
                current_date = date
            
            with st.expander(f"Entry at {time}"):
                st.write(summary)
                
                # Display emotions as colored tags
                st.write("Emotions:")
                emotion_html = "".join(emotion_tag(e) for e in emotions.split(','))
                st.markdown(emotion_html, unsafe_allow_html=True)
                
                # Display people as colored tags
                st.write("People:")
                people_html = "".join(people_tag(p) for p in people.split(',') if p.strip() != 'None')
                st.markdown(people_html if people_html else "No specific people mentioned", unsafe_allow_html=True)
                
                # Display topics as colored tags
                st.write("Topics:")
                topics_html = "".join(topic_tag(t) for t in topics.split(',') if t.strip() != 'None')
                st.markdown(topics_html if topics_html else "No specific topics identified", unsafe_allow_html=True)
                
                # Delete button for each entry
                if st.button("Delete Entry", key=f"delete_{entry_id}"):
                    delete_entry(entry_id)
                    st.success("Entry deleted successfully!")
                    st.rerun()
                    
        if not filtered_entries:
            st.info("No entries match the selected filters.")
    else:
        st.info("No past entries found.")
    
    # Button to return to main page
    if st.button("Back to Journal"):
        st.session_state.page = "main"
        st.rerun()