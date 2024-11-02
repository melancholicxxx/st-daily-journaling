import streamlit as st
import os
from openai import OpenAI
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import sql
from urllib.parse import urlparse
import pytz
import streamlit.components.v1 as components

# Set page config at the very beginning
st.set_page_config(layout="wide")

# Load environment variables
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
timezone = pytz.timezone('Asia/Singapore')  # GMT+8
today = datetime.now(timezone).strftime('%Y-%m-%d')

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
    
    # Create the logs table if it doesn't exist
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
    
    # Create the weekly_summaries table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS weekly_summaries
        (id SERIAL PRIMARY KEY,
         user_email TEXT,
         week_start_date TEXT,
         week_end_date TEXT,
         summary TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
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

# Add these functions after the existing database functions

def get_week_entries(user_email, start_date, end_date):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, summary FROM logs WHERE user_email = %s AND date >= %s AND date <= %s ORDER BY date, time",
        (user_email, start_date, end_date)
    )
    entries = cur.fetchall()
    cur.close()
    conn.close()
    return entries

def generate_weekly_summary(entries):
    # Concatenate all entries for the week
    concatenated_entries = "\n\n".join([f"Date: {entry[0]}\n{entry[1]}" for entry in entries])
    
    # Generate summary using GPT
    weekly_summary_prompt = "Create a comprehensive weekly summary of the following journal entries. Focus on main themes, emotional patterns, and significant events. Keep it concise but meaningful."
    
    messages = [
        {"role": "system", "content": "You are an AI assistant that creates meaningful weekly summaries from daily journal entries."},
        {"role": "user", "content": f"{weekly_summary_prompt}\n\nEntries:\n{concatenated_entries}"}
    ]
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.1,
        stream=False,
    )
    return response.choices[0].message.content

def save_weekly_summary(user_email, week_start_date, week_end_date, summary):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO weekly_summaries (user_email, week_start_date, week_end_date, summary)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (user_email, week_start_date) 
           DO UPDATE SET summary = EXCLUDED.summary, week_end_date = EXCLUDED.week_end_date""",
        (user_email, week_start_date, week_end_date, summary)
    )
    conn.commit()
    cur.close()
    conn.close()

def process_weekly_summaries(user_email):
    """
    Process and generate weekly summaries for a user's entries
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get the earliest and latest dates for the user's entries
    cur.execute(
        "SELECT MIN(date), MAX(date) FROM logs WHERE user_email = %s",
        (user_email,)
    )
    date_range = cur.fetchone()
    cur.close()
    conn.close()
    
    if not date_range[0] or not date_range[1]:
        return
    
    start_date = datetime.strptime(date_range[0], '%Y-%m-%d')
    end_date = datetime.strptime(date_range[1], '%Y-%m-%d')
    
    # Process week by week
    current_week_start = start_date - timedelta(days=start_date.weekday())
    while current_week_start <= end_date:
        current_week_end = current_week_start + timedelta(days=6)
        
        # Get entries for the current week
        entries = get_week_entries(
            user_email,
            current_week_start.strftime('%Y-%m-%d'),
            current_week_end.strftime('%Y-%m-%d')
        )
        
        # Only generate summary if there are entries
        if entries:
            weekly_summary = generate_weekly_summary(entries)
            save_weekly_summary(
                user_email,
                current_week_start.strftime('%Y-%m-%d'),
                current_week_end.strftime('%Y-%m-%d'),
                weekly_summary
            )
        
        current_week_start += timedelta(days=7)

def get_weekly_summaries(user_email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT week_start_date, week_end_date, summary 
           FROM weekly_summaries 
           WHERE user_email = %s 
           ORDER BY week_start_date DESC""",
        (user_email,)
    )
    summaries = cur.fetchall()
    cur.close()
    conn.close()
    
    # Format the dates
    formatted_summaries = []
    for week_start, week_end, summary in summaries:
        start_obj = datetime.strptime(week_start, '%Y-%m-%d')
        end_obj = datetime.strptime(week_end, '%Y-%m-%d')
        formatted_start = start_obj.strftime('%d %B %Y')
        formatted_end = end_obj.strftime('%d %B %Y')
        formatted_summaries.append((formatted_start, formatted_end, summary))
    
    return formatted_summaries

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

# Sidebar for user info and past entries
with st.sidebar:
    st.title("Journal Dashboard")
    
    if st.session_state.user_email is None or st.session_state.user_name is None:
        user_email = st.text_input("What's your email?")
        user_name = st.text_input("What's your name?")
        if user_email and user_name:
            st.session_state.user_email = user_email
            st.session_state.user_name = user_name
            st.rerun()
    else:
        entries_count = get_entries_count(st.session_state.user_email)
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
        
        # New button for Mindfulness Podcasts
        podcast_url = "https://midi-zydeco-b0b.notion.site/Mindfulness-Podcasts-109bc7bdae64802a89e5dee7493dc5c8"
        st.markdown(f'<a href="{podcast_url}" target="_blank"><button style="background-color:#FF4B4B;color:white;padding:8px 12px;border:none;border-radius:4px;cursor:pointer;">Mindfulness Podcasts</button></a>', unsafe_allow_html=True)
        
        # Only show past entries after user has logged in
        st.header("Past Entries")
        entries = get_past_entries(st.session_state.user_email)
        if entries:
            current_date = None
            for entry_id, date, time, summary, emotions, people, topics in entries:
                if date != current_date:
                    st.subheader(date)
                    current_date = date
                if st.button(f"Entry at {time}", key=f"view_{entry_id}"):
                    st.session_state.selected_entry = (entry_id, date, time, summary, emotions, people, topics)
                    st.session_state.page = "main"  # Ensure the main page is displayed
                    st.rerun()
        else:
            st.info("No past entries found.")
        
        # Add "Share Feedback" link at the bottom of the sidebar
        st.markdown("---")
        feedback_url = "https://i0cphmhv362.typeform.com/to/gL3M2OdT"  # Replace with your actual feedback URL
        st.markdown(f'<div style="text-align: center;"><a href="{feedback_url}" target="_blank">Share Feedback</a></div>', unsafe_allow_html=True)

# Main area for new entries and displaying selected past entry
if st.session_state.page == "main":
    st.title("Daily Reflection Journal")

    if st.session_state.user_email and st.session_state.user_name:
        # Display selected past entry if any
        if 'selected_entry' in st.session_state:
            entry_id, date, time, summary, emotions, people, topics = st.session_state.selected_entry
            st.header(f"Entry from {date} at {time}")
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
                    with st.spinner("Generating your journal entry summary, detecting emotions, people, and topics..."):
                        summary = generate_summary(st.session_state.messages)
                        emotions = detect_emotions(st.session_state.messages)
                        people = detect_people(st.session_state.messages)
                        topics = detect_topics(st.session_state.messages)
                    
                    # Save summary, emotions, people, and topics to database
                    save_to_db(st.session_state.user_email, st.session_state.user_name, summary, emotions, people, topics)
                    process_weekly_summaries(st.session_state.user_email)
                    
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
    analyze_button = st.button("Analyze", type="primary")

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
