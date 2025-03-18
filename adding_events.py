import os
import mysql.connector
from datetime import datetime, timedelta
import pytz
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import json
from dotenv import load_dotenv

class EventHandler:
    def __init__(self, llm_interface=None, db_config=None):
        load_dotenv()
        self.llm_interface = llm_interface

        # Initialize DB config if not provided
        if db_config is None:
            self.db_config = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'user': os.getenv('DB_USER', 'root'),
                'password': os.getenv('DB_PASSWORD', ''),
                'database': os.getenv('DB_NAME', 'events_db')
            }
        else:
            self.db_config = db_config

        # Google Calendar API setup
        self.SCOPES = ['https://www.googleapis.com/auth/calendar']
        self.calendar_service = self._setup_calendar_api()

        # Event details tracking
        self.current_event = {
            'name': None,
            'date': None,
            'time': None,
            'location': None,
            'details': 'No details provided',  # Default value
            'reminder': 'No reminder'  # Default value
        }

        # Event creation state
        self.is_creating_event = False
        self.is_updating_event = False
        self.current_question = None
        self.awaiting_confirmation = False

        # Reminder options (in minutes before event)
        self.reminder_options = {
            "5 minutes": 5,
            "10 minutes": 10,
            "15 minutes": 15,
            "30 minutes": 30,
            "1 hour": 60,
            "2 hours": 120,
            "1 day": 1440
        }

    def _setup_calendar_api(self):
        """Set up and return Google Calendar API service."""
        creds = None
        token_path = 'token.json'
        credentials_path = 'credentials.json'

        # Check if token file exists
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_info(
                json.loads(open(token_path).read()),
                self.SCOPES
            )

        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Only run this if credentials.json exists
                if os.path.exists(credentials_path):
                    flow = InstalledAppFlow.from_client_secrets_file(
                        credentials_path, self.SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    print("WARNING: credentials.json not found. Calendar integration disabled.")
                    return None

            # Save credentials for future use
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

        try:
            service = build('calendar', 'v3', credentials=creds)
            return service
        except Exception as e:
            print(f"Failed to build calendar service: {e}")
            return None

    def connect_to_db(self):
        """Connect to the MySQL database."""
        try:
            conn = mysql.connector.connect(**self.db_config)
            return conn
        except mysql.connector.Error as e:
            print(f"Error connecting to MySQL database: {e}")
            return None

    def save_event_to_db(self, event_data):
        """Save event to MySQL database."""
        conn = self.connect_to_db()
        if not conn:
            return False, "Database connection error"

        try:
            cursor = conn.cursor()

            # Convert reminder text to minutes
            reminder_minutes = None
            reminder_text = event_data.get('reminder')

            if reminder_text and reminder_text != 'No reminder':
                # Extract the numeric part if it's in our expected format
                for option, minutes in self.reminder_options.items():
                    if option.lower() in reminder_text.lower():
                        reminder_minutes = minutes
                        break

                # If we couldn't match a preset, use a default
                if reminder_minutes is None:
                    reminder_minutes = 10  # Default to 10 minutes

            # Insert the event into the database
            query = """
            INSERT INTO my_table
            (event_name, event_date, event_time, location, details, reminder)
            VALUES (%s, %s, %s, %s, %s, %s)
            """

            values = (
                event_data.get('name'),
                event_data.get('date'),
                event_data.get('time'),
                event_data.get('location'),
                event_data.get('details', 'No details provided'),
                f"{reminder_minutes} minutes before" if reminder_minutes else "No reminder"
            )

            cursor.execute(query, values)
            conn.commit()

            event_id = cursor.lastrowid
            return True, event_id

        except mysql.connector.Error as e:
            print(f"Database error: {e}")
            return False, str(e)

        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

    def add_to_google_calendar(self, event_data):
        """Add event to Google Calendar."""
        if not self.calendar_service:
            return False, "Calendar service not available"

        try:
            # Parse date and time
            date_str = event_data.get('date')
            time_str = event_data.get('time')

            try:
                # Try to parse the combined date and time
                start_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")

                # Assume events last 1 hour by default
                end_datetime = start_datetime + timedelta(hours=1)

                # Convert to RFC3339 format
                timezone = pytz.timezone('Europe/London')  # Adjust for your timezone
                start_datetime = timezone.localize(start_datetime)
                end_datetime = timezone.localize(end_datetime)

                start_time = start_datetime.isoformat()
                end_time = end_datetime.isoformat()

                # Create event body
                event_body = {
                    'summary': event_data.get('name'),
                    'location': event_data.get('location'),
                    'description': event_data.get('details', 'No details provided'),
                    'start': {
                        'dateTime': start_time,
                        'timeZone': 'Europe/London',  # Adjust for your timezone
                    },
                    'end': {
                        'dateTime': end_time,
                        'timeZone': 'Europe/London',  # Adjust for your timezone
                    }
                }

                # Add reminder if specified
                reminder_text = event_data.get('reminder')
                if reminder_text and reminder_text != 'No reminder':
                    reminder_minutes = None
                    for option, minutes in self.reminder_options.items():
                        if option.lower() in reminder_text.lower():
                            reminder_minutes = minutes
                            break

                    if reminder_minutes:
                        event_body['reminders'] = {
                            'useDefault': False,
                            'overrides': [
                                {'method': 'popup', 'minutes': reminder_minutes}
                            ]
                        }

                # Insert the event
                event = self.calendar_service.events().insert(
                    calendarId='primary',
                    body=event_body
                ).execute()

                return True, event.get('id')

            except ValueError as date_error:
                print(f"Error parsing date/time: {date_error}")
                return False, f"Invalid date or time format: {date_error}"

        except Exception as e:
            print(f"Google Calendar API error: {e}")
            return False, str(e)

    def is_event_query(self, query):
        """Check if the user's query is related to creating a calendar event."""
        # List of phrases that indicate an event creation intent
        event_phrases = [
            "add event", "create event", "schedule event", "new event",
            "add to calendar", "put in calendar", "create a reminder",
            "add appointment", "schedule appointment", "new appointment",
            "add meeting", "schedule meeting", "new meeting",
            "add to my calendar", "schedule in my calendar"
        ]

        query = query.lower()
        return any(phrase in query for phrase in event_phrases)

    def extract_event_details(self, query):
        """Extract event details from user input using LLM instead of regex."""
        if not self.llm_interface:
            return {}

        prompt = f"""
        Extract event details from this text: "{query}"

        If present, identify the following information:
        - Event name/title
        - Date (in YYYY-MM-DD format if possible)
        - Time (in HH:MM format if possible)
        - Location
        - Details or description
        - Reminder preferences

        Return only the extracted information in JSON format with the keys:
        name, date, time, location, details, reminder.
        If information is not present, use null for that field.
        """

        try:
            # Query the LLM
            response = self.llm_interface.query_llm(prompt, temperature=0.1, max_tokens=300)

            # Try to find and parse a JSON object in the response
            try:
                # Look for JSON patterns
                response = response.strip()
                if '```json' in response:
                    json_text = response.split('```json')[1].split('```')[0].strip()
                elif '```' in response:
                    json_text = response.split('```')[1].strip()
                else:
                    json_text = response

                # Try to parse the JSON
                extracted_details = json.loads(json_text)
                return extracted_details

            except json.JSONDecodeError as json_err:
                print(f"Failed to decode JSON from LLM response: {json_err}")
                print(f"Raw response: {response}")
                return {}

        except Exception as e:
            print(f"Error in extract_event_details: {e}")
            return {}

    def _format_event_summary(self):
        """Format a summary of the current event details."""
        event = self.current_event

        summary = "Event Summary: Here are the event details:\n"
        summary += f"Name: {event['name']}.\n"
        summary += f"Date: {event['date']}\n"
        summary += f"Time: {event['time']}\n"
        summary += f"Location: {event['location']}.\n"
        summary += f"Details: {event['details']}\n"
        summary += f"Reminder: {event['reminder']}\n"
        summary += "Are you happy with this event? Please say yes or no."

        return summary

    def check_conflicts(self, date_str, start_time_str, end_time_str=None):
        """Check for scheduling conflicts."""
        if not end_time_str:
            # Assume events last 1 hour by default
            try:
                start_dt = datetime.strptime(f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M:%S")
                end_dt = start_dt + timedelta(hours=1)
                end_time_str = end_dt.strftime("%H:%M:%S")
            except ValueError:
                return "Could not parse date and time for conflict checking"

        conflict_check_msg = (
            f"Checking conflicts between {date_str}T{start_time_str}+00:00 and "
            f"{date_str}T{end_time_str}+00:00"
        )
        print(conflict_check_msg)

        # Here you would implement actual conflict checking with your calendar
        # For now we'll just return no conflicts
        return "No conflicts found"

    def process_query(self, query):
        """Process a user query related to event creation or modification."""
        # If we're not in event creation mode, check if this is an event query
        if not self.is_creating_event and not self.is_updating_event:
            if self.is_event_query(query):
                # Extract details from the initial query
                extracted_details = self.extract_event_details(query)

                # Update current event with any extracted details
                for key, value in extracted_details.items():
                    if value:  # Only update if value is not None or empty
                        self.current_event[key] = value

                # Start event creation process
                self.is_creating_event = True

                # Determine what to ask next
                return self._get_next_question()
            return None  # Not an event query

        # Handle confirmation response
        if self.awaiting_confirmation:
            if "yes" in query.lower():
                return self._finalize_event()
            elif "no" in query.lower():
                self.awaiting_confirmation = False
                self.is_updating_event = True
                return "What details would you like to change?"
            else:
                return "Please say yes to confirm or no to modify the event details."

        # Handle update requests
        if self.is_updating_event:
            # Use LLM to figure out what the user wants to change
            prompt = f"""
            The user wants to update an event with these current details:
            {json.dumps(self.current_event)}

            From this update request: "{query}"

            Identify which field(s) they want to change and the new value(s).
            Return a JSON with only the fields to update, like:
            {{"field_name": "new value"}}
            """

            response = self.llm_interface.query_llm(prompt, temperature=0.1, max_tokens=200)

            try:
                # Extract JSON
                if '```json' in response:
                    json_text = response.split('```json')[1].split('```')[0].strip()
                elif '```' in response:
                    json_text = response.split('```')[1].strip()
                else:
                    json_text = response

                updates = json.loads(json_text)

                # Apply updates
                for field, value in updates.items():
                    if field in self.current_event:
                        self.current_event[field] = value

                # Show updated summary and ask for confirmation
                self.is_updating_event = False
                self.awaiting_confirmation = True
                return self._format_event_summary()

            except (json.JSONDecodeError, Exception) as e:
                print(f"Error processing update: {e}")
                return "I didn't understand which details you want to change. Please specify more clearly, like 'change the date to March 21st'."

        # Handle responses to specific questions during event creation
        if self.current_question:
            field = self.current_question

            # If dealing with a specific field question, update that field
            if field in self.current_event:
                # For date and time fields, we might want special handling
                if field == 'date':
                    # Try to parse the date with LLM
                    prompt = f"""
                    Extract a date in YYYY-MM-DD format from: "{query}"
                    Return only the date in YYYY-MM-DD format with no other text.
                    """
                    response = self.llm_interface.query_llm(prompt, temperature=0.1, max_tokens=50)
                    extracted_date = response.strip()

                    if extracted_date and len(extracted_date) == 10:  # Simple length check
                        self.current_event['date'] = extracted_date
                    else:
                        return "I couldn't understand that date. Please provide a date like 'March 20, 2025' or '2025-03-20'."

                elif field == 'time':
                    # Try to parse the time with LLM
                    prompt = f"""
                    Extract a time in HH:MM:SS 24-hour format from: "{query}"
                    Return only the time in HH:MM:SS format with no other text.
                    """
                    response = self.llm_interface.query_llm(prompt, temperature=0.1, max_tokens=50)
                    extracted_time = response.strip()

                    if extracted_time:
                        self.current_event['time'] = extracted_time
                    else:
                        return "I couldn't understand that time. Please provide a time like '3:00 PM' or '15:00'."
                else:
                    # For other fields, just use the response directly
                    self.current_event[field] = query

                # Check if we need to ask another question
                return self._get_next_question()

        # If we're here, something went wrong
        return "I'm having trouble processing your request. Let's try again. What event would you like to add to your calendar?"

    def _get_next_question(self):
        """Determine the next question to ask based on missing event details."""
        # Check each required field in order of importance
        if not self.current_event['name']:
            self.current_question = 'name'
            return "What's the name of the event?"

        if not self.current_event['date']:
            self.current_question = 'date'
            return "What date is the event? (e.g., March 20, 2025)"

        if not self.current_event['time']:
            self.current_question = 'time'
            return "What time is the event? (e.g., 3:00 PM)"

        if not self.current_event['location']:
            self.current_question = 'location'
            return "Where is the event located?"

        # Details is optional but we'll ask anyway
        if self.current_event['details'] == 'No details provided':
            self.current_question = 'details'
            return "Do you want to add any details for the event? If not, just say 'no details'."

        # Reminder is optional but we'll ask anyway
        if self.current_event['reminder'] == 'No reminder':
            self.current_question = 'reminder'
            options = ", ".join(self.reminder_options.keys())
            return f"Would you like a reminder? Options are: {options}. Or say 'no reminder'."

        # If we've collected all details, show summary and ask for confirmation
        self.current_question = None
        self.awaiting_confirmation = True

        # Check for conflicts if we have date and time
        if self.current_event['date'] and self.current_event['time']:
            conflict_message = self.check_conflicts(self.current_event['date'], self.current_event['time'])
            print(conflict_message)

        return self._format_event_summary()

    def _finalize_event(self):
        """Finalize the event creation by saving to DB and calendar."""
        # Save to database
        db_success, db_result = self.save_event_to_db(self.current_event)

        # Add to Google Calendar
        calendar_success = False
        calendar_result = "Calendar integration not attempted"

        if db_success and self.calendar_service:
            calendar_success, calendar_result = self.add_to_google_calendar(self.current_event)

        # Prepare result message
        if db_success:
            result = f"Event '{self.current_event['name']}' has been added to your calendar."
            if calendar_success:
                result += " It's been synced with Google Calendar as well."
        else:
            result = f"There was a problem adding your event: {db_result}"

        # Reset event creation state
        self.is_creating_event = False
        self.is_updating_event = False
        self.awaiting_confirmation = False
        self.current_question = None
        self.current_event = {
            'name': None,
            'date': None,
            'time': None,
            'location': None,
            'details': 'No details provided',
            'reminder': 'No reminder'
        }

        return result