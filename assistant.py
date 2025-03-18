import os
import mysql.connector
from datetime import datetime, timedelta
import pytz
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
from dotenv import load_dotenv
from speech_handler import SpeechHandler
from llm_interface import LLMInterface
from location_handler import LocationHandler
from weather_handler import WeatherHandler
from adding_events import EventHandler

class AI_Assistant:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        tts_url = "http://localhost:58851/speak"
        lm_studio_url = "http://localhost:1234/v1/chat/completions"

        # Initialize database connection
        self.db_connection = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'events_db')
        )
        self.db_cursor = self.db_connection.cursor()
        self.google_calendar_service = self.initialize_google_calendar()

        # Initialize LLM interface
        self.llm_interface = LLMInterface()

        # Initialize speech handler
        speech_key = os.getenv("speech_key")
        speech_region = os.getenv("speech_region")
        self.speech_handler = SpeechHandler(speech_key, speech_region)
        self.speech_handler.set_callback(self.process_user_input)

        # Initialize specialized handlers
        self.location_handler = LocationHandler()
        self.weather_handler = WeatherHandler()
        self.event_handler = EventHandler(llm_interface=self.llm_interface)

        # State tracking
        self.in_event_creation = False

    def __del__(self):
        # Clean up database connection when the object is destroyed
        try:
            if hasattr(self, "db_cursor") and self.db_cursor:
                self.db_cursor.close()
            if hasattr(self, "db_connection") and self.db_connection:
                self.db_connection.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def initialize_google_calendar(self):
        """Initializes the Google Calendar API service."""
        creds = None
        token_path = 'token.json'

        # Load existing token if available
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)

        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Only run this if credentials.json exists
                if os.path.exists("credentials.json"):
                    flow = InstalledAppFlow.from_client_secrets_file(
                        "credentials.json", self.SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    print("WARNING: credentials.json not found. Calendar integration disabled.")
                    return None

            # Save the credentials for future use
            with open(token_path, "w") as token:
                token.write(creds.to_json())

        try:
            service = build("calendar", "v3", credentials=creds)
            return service
        except Exception as e:
            print(f"Failed to build calendar service: {e}")
            return None

    def start_transcription(self):
        """Start listening for user input."""
        self.speech_handler.start_transcription()

    def pause_transcription(self):
        """Pause listening for user input."""
        self.speech_handler.pause_transcription()

    def send_to_tts(self, text):
        """Send text to text-to-speech service."""
        return self.speech_handler.send_to_tts(text)

    def process_user_input(self, user_input):
        """Process user input and determine appropriate response."""
        try:
            print(f"Processing input: {user_input}")

            # Log the conversation in the database
            self.insert_conversation(user_input)

            # Check if we're in active event creation
            if self.in_event_creation or self.event_handler.is_creating_event or self.event_handler.is_updating_event or self.event_handler.awaiting_confirmation:
                # Let the event handler process this input
                response = self.event_handler.process_query(user_input)

                if response:
                    # Check if we're still in event creation mode
                    self.in_event_creation = (
                        self.event_handler.is_creating_event or
                        self.event_handler.is_updating_event or
                        self.event_handler.awaiting_confirmation
                    )
                    self.send_to_tts(response)
                    return

            # Check if this is a new event query
            event_response = self.event_handler.process_query(user_input)
            if event_response:
                self.in_event_creation = True
                self.send_to_tts(event_response)
                return

            # Check if it's a weather-related query
            if self.weather_handler.is_weather_query(user_input):
                response = self.weather_handler.process_weather_query(user_input)
                self.send_to_tts(response)
                return

            # Check if it's a location-related query
            location_keywords = ["where", "location", "nearby", "directions", "how to get", "find", "restaurant", "shop", "store"]
            if any(keyword in user_input.lower() for keyword in location_keywords):
                response = self.location_handler.process_location_query(user_input)
                self.send_to_tts(response)
                return

            # If none of the specialized handlers matched, use the LLM for general queries
            response = self.llm_interface.query_llm(user_input)
            self.send_to_tts(response)

        except Exception as e:
            print(f"Error in process_user_input: {e}")
            import traceback
            traceback.print_exc()
            self.send_to_tts("I'm sorry, I encountered an error. Please try again.")

    def insert_conversation(self, user_input):
        """Inserts the conversation into the database."""
        try:
            # Get the latest assistant response
            assistant_response = self.speech_handler.get_last_response() if hasattr(self.speech_handler, 'get_last_response') else "No response generated"

            # Insert into conversations table (if it exists)
            try:
                query = "INSERT INTO conversations (user_input, assistant_response, timestamp) VALUES (%s, %s, %s)"
                values = (user_input, assistant_response, datetime.now())

                self.db_cursor.execute(query, values)
                self.db_connection.commit()
            except mysql.connector.Error as db_err:
                # If table doesn't exist, just log the error but don't crash
                print(f"Database error when logging conversation: {db_err}")
                self.db_connection.rollback()

        except Exception as e:
            print(f"Error logging conversation: {e}")