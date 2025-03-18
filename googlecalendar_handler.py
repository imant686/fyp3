import os
import re
from datetime import datetime, timedelta, timezone
from dateparser import parse
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]

class GoogleCalendarHandler:
    def __init__(self):
        """Initializes the Google Calendar handler."""
        self.service = self.initialize_google_calendar()

    def initialize_google_calendar(self):
        """Initializes the Google Calendar API service."""
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError:
                    print("Token has expired or been revoked. Re-authenticating...")
                    creds = self.authenticate()
            else:
                creds = self.authenticate()
        return build("calendar", "v3", credentials=creds)

    def authenticate(self):
        """Authenticate the user and save the credentials."""
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
        print("Saved new credentials to token.json")
        return creds

    def get_events(self, date):
        """Fetches events from Google Calendar for a specific date."""
        # Ensure date is a datetime.date object
        if isinstance(date, datetime):
            date = date.date()

        # Create timezone-aware start and end of day
        start_of_day = datetime.combine(date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_of_day = datetime.combine(date + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)

        start_of_day_iso = start_of_day.isoformat()
        end_of_day_iso = end_of_day.isoformat()

        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_of_day_iso,
                timeMax=end_of_day_iso,
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            if not events:
                return "You have no events scheduled for this date."

            event_list = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))

                # Parse start and end times - ensure timezone-aware
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

                # Format the time and date
                start_str = start_dt.strftime("%I:%M %p").lstrip('0')
                end_str = end_dt.strftime("%I:%M %p").lstrip('0')
                date_str = start_dt.strftime("%d %B")

                event_list.append(f"{event['summary']} on {date_str} from {start_str} to {end_str}")

            return "Here are your events for this date: " + "; ".join(event_list)

        except HttpError as error:
            print(f"An error occurred while fetching events: {error}")
            print(f"Error details: {error.content}")  # Log the full error response
            return "Sorry, I couldn't fetch your events. Please try again later."

    def insert_event(self, event_name, event_date, event_time, location, details, reminder):
        """Inserts an event into Google Calendar."""
        try:
            # Parse the reminder string to extract the number of minutes
            reminder_minutes = 10  # Default value
            if reminder:
                # Try to extract the number from strings like "10 minutes before"
                match = re.search(r'(\d+)\s*minutes?', reminder)
                if match:
                    reminder_minutes = int(match.group(1))

            # Format date and time properly
            if not event_date or not event_time:
                print("Warning: Missing date or time for event")
                event_date = datetime.now().strftime("%Y-%m-%d")
                event_time = "12:00"

            # Ensure we have a valid date format (YYYY-MM-DD)
            try:
                if isinstance(event_date, str) and not re.match(r'\d{4}-\d{2}-\d{2}', event_date):
                    # Try to parse and convert to YYYY-MM-DD
                    try:
                        parsed_date = parse(event_date)
                        if parsed_date:
                            event_date = parsed_date.strftime("%Y-%m-%d")
                        else:
                            raise ValueError("Date parsing failed")
                    except (ValueError, TypeError):
                        # If parsing fails, use tomorrow as fallback
                        event_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception as e:
                print(f"Error ensuring valid date format: {e}")
                event_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            # Format time (ensure HH:MM format)
            if isinstance(event_time, str):
                # Try to standardize time format
                time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', event_time.lower())
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2) or "0")
                    ampm = time_match.group(3)

                    # Handle 12-hour format
                    if ampm and ampm.lower() == 'pm' and hour < 12:
                        hour += 12
                    if ampm and ampm.lower() == 'am' and hour == 12:
                        hour = 0

                    event_time = f"{hour:02d}:{minute:02d}"
                else:
                    event_time = "12:00"  # Default time

            # Create datetime objects with timezone
            try:
                # Create start time
                start_dt = datetime.strptime(f"{event_date}T{event_time}:00", "%Y-%m-%dT%H:%M:%S")
                # Add timezone info
                start_dt = start_dt.replace(tzinfo=timezone.utc)

                # Calculate end time (1 hour after start by default)
                end_dt = start_dt + timedelta(hours=1)

                # Format for Google Calendar API
                start_time_str = start_dt.isoformat()
                end_time_str = end_dt.isoformat()
            except ValueError as e:
                print(f"Warning: Could not calculate proper times: {e}")
                # Default to 1 hour from now with timezone
                start_dt = datetime.now().replace(tzinfo=timezone.utc)
                end_dt = start_dt + timedelta(hours=1)
                start_time_str = start_dt.isoformat()
                end_time_str = end_dt.isoformat()

            event = {
                'summary': event_name,
                'location': location,
                'description': details,
                'start': {
                    'dateTime': start_time_str,
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_time_str,
                    'timeZone': 'UTC',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': reminder_minutes},
                    ],
                },
            }

            # Actually insert the event
            created_event = self.service.events().insert(calendarId='primary', body=event).execute()
            print(f"Event created in Google Calendar: {created_event.get('htmlLink')}")
            return created_event

        except HttpError as error:
            print(f"An error occurred with Google Calendar: {error}")
            print(f"Error details: {error.content}")  # Log the full error response
            raise Exception("Failed to insert event into Google Calendar")

    def check_for_conflicts(self, date, time):
        """Checks if there are any conflicts in the Google Calendar for the specified date and time."""
        try:
            # Parse the requested date
            if isinstance(date, str):
                try:
                    requested_date = datetime.strptime(date, "%Y-%m-%d").date()
                except ValueError:
                    # Try to use dateparser for more flexible date formats
                    parsed_date = parse(date)
                    if parsed_date:
                        requested_date = parsed_date.date()
                    else:
                        return None, "Could not parse the date format"
            else:
                # Assume it's already a datetime object
                if isinstance(date, datetime):
                    requested_date = date.date()
                else:
                    requested_date = date

            # Parse the time
            requested_time = None
            if isinstance(time, str):
                time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', time.lower())
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2) or "0")
                    ampm = time_match.group(3)

                    # Convert to 24-hour format
                    if ampm and ampm.lower() == 'pm' and hour < 12:
                        hour += 12
                    if ampm and ampm.lower() == 'am' and hour == 12:
                        hour = 0

                    requested_time = f"{hour:02d}:{minute:02d}"
                else:
                    return None, "Could not parse the time format"

            # Set up the time range for checking conflicts
            # We'll check for conflicts within +/- 1 hour of the requested time
            try:
                requested_datetime = datetime.combine(requested_date, datetime.strptime(requested_time, "%H:%M").time())
            except ValueError:
                # Try another time format
                requested_datetime = datetime.combine(requested_date, datetime.strptime(requested_time, "%H:%M:%S").time())

            # Make timezone-aware
            requested_datetime = requested_datetime.replace(tzinfo=timezone.utc)

            start_check = requested_datetime - timedelta(hours=1)
            end_check = requested_datetime + timedelta(hours=2)  # Buffer for 1-hour events

            # Query Google Calendar for events in this timeframe
            start_check_iso = start_check.isoformat()
            end_check_iso = end_check.isoformat()

            print(f"Checking conflicts between {start_check_iso} and {end_check_iso}")

            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_check_iso,
                timeMax=end_check_iso,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            conflicts = events_result.get('items', [])
            if conflicts:
                print(f"Found {len(conflicts)} potential conflicts")
                return conflicts, None
            print("No conflicts found")
            return None, None

        except Exception as e:
            print(f"Error checking for conflicts: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Error checking calendar: {str(e)}"

    def reschedule_event(self, event_id, new_date, new_time):
        """Reschedule an existing event in Google Calendar."""
        try:
            # First, get the event
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()

            # Parse the provided date
            if isinstance(new_date, str):
                try:
                    target_date = datetime.strptime(new_date, "%Y-%m-%d").date()
                except ValueError:
                    parsed_date = parse(new_date)
                    if parsed_date:
                        target_date = parsed_date.date()
                    else:
                        return False, "Could not parse the provided date"
            else:
                target_date = new_date.date()

            # Parse the time
            new_hour = 0
            new_minute = 0
            if isinstance(new_time, str):
                time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', new_time.lower())
                if time_match:
                    new_hour = int(time_match.group(1))
                    new_minute = int(time_match.group(2) or "0")
                    ampm = time_match.group(3)

                    # Convert to 24-hour format
                    if ampm and ampm.lower() == 'pm' and new_hour < 12:
                        new_hour += 12
                    if ampm and ampm.lower() == 'am' and new_hour == 12:
                        new_hour = 0
                else:
                    return False, "Could not parse the provided time"

            # Get the event duration
            start_dt = datetime.fromisoformat(event['start'].get('dateTime').replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(event['end'].get('dateTime').replace('Z', '+00:00'))
            event_duration = end_dt - start_dt

            # Create new start and end times with timezone
            new_start_dt = datetime.combine(target_date,
                                        datetime.strptime(f"{new_hour:02d}:{new_minute:02d}", "%H:%M").time())
            # Make timezone-aware
            new_start_dt = new_start_dt.replace(tzinfo=timezone.utc)
            new_end_dt = new_start_dt + event_duration

            # Update the event
            event['start']['dateTime'] = new_start_dt.isoformat()
            event['end']['dateTime'] = new_end_dt.isoformat()

            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event
            ).execute()

            event_name = updated_event.get('summary', 'Event')
            formatted_time = new_start_dt.strftime("%-I:%M %p")
            formatted_date = new_start_dt.strftime("%B %d")

            return True, f"Successfully rescheduled '{event_name}' to {formatted_date} at {formatted_time}."

        except Exception as e:
            print(f"Error rescheduling event: {e}")
            return False, f"Error rescheduling event: {str(e)}"

    def find_free_slots(self, date, existing_event_time=None, num_slots=3):
        """Find available time slots on the specified date, respecting existing calendar events."""
        try:
            # Parse the date if it's a string
            if isinstance(date, str):
                try:
                    # Try standard format
                    target_date = datetime.strptime(date, "%Y-%m-%d").date()
                except ValueError:
                    # Try dateparser
                    parsed_date = parse(date)
                    if parsed_date:
                        target_date = parsed_date.date()
                    else:
                        return []
            elif isinstance(date, datetime):
                target_date = date.date()
            else:
                target_date = date

            # Set up day boundaries (business hours)
            morning_time = datetime.strptime("08:00", "%H:%M").time()
            evening_time = datetime.strptime("20:00", "%H:%M").time()  # Extended to 8 PM

            # Combine date and time
            day_start = datetime.combine(target_date, morning_time)
            day_end = datetime.combine(target_date, evening_time)

            # Add timezone
            day_start = day_start.replace(tzinfo=timezone.utc)
            day_end = day_end.replace(tzinfo=timezone.utc)

            # Get events from Google Calendar
            day_start_iso = day_start.isoformat()
            day_end_iso = day_end.isoformat()

            # Get all existing calendar events for the requested date
            existing_events = []
            try:
                events_result = self.service.events().list(
                    calendarId='primary',
                    timeMin=day_start_iso,
                    timeMax=day_end_iso,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()

                existing_events = events_result.get('items', [])
                print(f"Found {len(existing_events)} existing events on {target_date}")

                # Log found events for debugging
                for event in existing_events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    print(f"Existing event: {event.get('summary')} from {start} to {end}")
            except Exception as cal_error:
                print(f"Error querying calendar: {cal_error}")

            # Define possible standard time slots (hourly slots from 8 AM to 7 PM)
            # This creates slots like 8:00-9:00, 9:00-10:00, etc.
            all_possible_slots = []
            for hour in range(8, 19):  # 8 AM to 7 PM (ending at 8 PM)
                am_pm = "AM" if hour < 12 else "PM"
                disp_hour = hour if hour <= 12 else hour - 12
                if disp_hour == 0:  # Handle 12 PM
                    disp_hour = 12

                start_time = f"{disp_hour}:00 {am_pm}"

                next_hour = hour + 1
                next_am_pm = "AM" if next_hour < 12 else "PM"
                next_disp_hour = next_hour if next_hour <= 12 else next_hour - 12
                if next_disp_hour == 0:  # Handle 12 PM
                    next_disp_hour = 12

                end_time = f"{next_disp_hour}:00 {next_am_pm}"

                slot = {
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_hours": 1,
                    "start_hour": hour,
                    "end_hour": hour + 1
                }
                all_possible_slots.append(slot)

            # Filter out slots that conflict with existing events
            available_slots = []
            for slot in all_possible_slots:
                has_conflict = False

                # Convert slot times to datetime objects for comparison
                slot_start_hour = slot["start_hour"]
                slot_end_hour = slot["end_hour"]

                slot_start = datetime.combine(target_date, datetime.strptime(f"{slot_start_hour}:00", "%H:%M").time())
                slot_end = datetime.combine(target_date, datetime.strptime(f"{slot_end_hour}:00", "%H:%M").time())

                # Add timezone
                slot_start = slot_start.replace(tzinfo=timezone.utc)
                slot_end = slot_end.replace(tzinfo=timezone.utc)

                # Check for conflicts with existing events
                for event in existing_events:
                    event_start = event['start'].get('dateTime', event['start'].get('date'))
                    event_end = event['end'].get('dateTime', event['end'].get('date'))

                    # Skip all-day events or events without proper datetime
                    if 'T' not in event_start or 'T' not in event_end:
                        continue

                    # Convert to datetime objects
                    event_start_dt = datetime.fromisoformat(event_start.replace('Z', '+00:00'))
                    event_end_dt = datetime.fromisoformat(event_end.replace('Z', '+00:00'))

                    # Check if event overlaps with this slot
                    # Overlap occurs when event starts before slot ends AND event ends after slot starts
                    if event_start_dt < slot_end and event_end_dt > slot_start:
                        has_conflict = True
                        print(f"Conflict found: {slot['start_time']} conflicts with event '{event.get('summary')}'")
                        break

                if not has_conflict:
                    available_slots.append(slot)
                    print(f"Available slot found: {slot['start_time']} to {slot['end_time']}")

            # Return the available slots (up to num_slots)
            if available_slots:
                return available_slots[:num_slots]
            else:
                print("No available slots found after checking conflicts")
                return []

        except Exception as e:
            print(f"ERROR in find_free_slots: {e}")
            import traceback
            traceback.print_exc()
            # Return empty list instead of fake data when there's an error
            return []

    def cancel_event(self, event_id):
        """Cancel an event in Google Calendar."""
        try:
            # Get the event first to confirm it exists and to get its name
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()

            event_name = event.get('summary', 'Event')

            # Delete the event
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()

            return True, f"Successfully canceled '{event_name}'."

        except Exception as e:
            print(f"Error canceling event: {e}")
            return False, f"Error canceling event: {str(e)}"

    def find_events_by_query(self, query_text, start_date=None, end_date=None):
        """Finds events matching a query in Google Calendar."""
        try:
            # If no dates provided, search within the next month
            if not start_date:
                start_date = datetime.now().replace(tzinfo=timezone.utc)
            if not end_date:
                end_date = (start_date + timedelta(days=30)).replace(tzinfo=timezone.utc)

            # Ensure dates are properly formatted
            start_date_iso = start_date.isoformat() if isinstance(start_date, datetime) else start_date
            end_date_iso = end_date.isoformat() if isinstance(end_date, datetime) else end_date

            # Execute the search
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_date_iso,
                timeMax=end_date_iso,
                q=query_text,  # This is the search query
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            return events

        except Exception as e:
            print(f"Error searching for events: {e}")
            return []

    def update_event_field(self, event_id, field, value):
        """Update a specific field of an event."""
        try:
            # First, get the event
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()

            # Update the appropriate field
            if field == "name" or field == "summary":
                event['summary'] = value
            elif field == "location":
                event['location'] = value
            elif field == "details" or field == "description":
                event['description'] = value
            elif field == "date":
                # Parse the new date
                if isinstance(value, str):
                    try:
                        new_date = datetime.strptime(value, "%Y-%m-%d").date()
                    except ValueError:
                        parsed_date = parse(value)
                        if parsed_date:
                            new_date = parsed_date.date()
                        else:
                            return False, "Could not parse the new date"
                else:
                    new_date = value.date()

                # Keep the same time, just change the date
                start_dt = datetime.fromisoformat(event['start'].get('dateTime').replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(event['end'].get('dateTime').replace('Z', '+00:00'))

                # Create new datetime objects with the new date
                new_start_dt = datetime.combine(new_date, start_dt.time())
                new_start_dt = new_start_dt.replace(tzinfo=timezone.utc)

                # Calculate the duration and apply it to the end time
                duration = end_dt - start_dt
                new_end_dt = new_start_dt + duration

                # Update the event times
                event['start']['dateTime'] = new_start_dt.isoformat()
                event['end']['dateTime'] = new_end_dt.isoformat()

            elif field == "time":
                # Parse the new time
                time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', value.lower())
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2) or "0")
                    ampm = time_match.group(3)

                    # Convert to 24-hour format
                    if ampm and ampm.lower() == 'pm' and hour < 12:
                        hour += 12
                    if ampm and ampm.lower() == 'am' and hour == 12:
                        hour = 0
                else:
                    return False, "Could not parse the new time"

                # Get current start and end times
                start_dt = datetime.fromisoformat(event['start'].get('dateTime').replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(event['end'].get('dateTime').replace('Z', '+00:00'))

                # Calculate event duration
                duration = end_dt - start_dt

                # Create new start time with the same date
                new_time = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
                new_start_dt = datetime.combine(start_dt.date(), new_time)
                new_start_dt = new_start_dt.replace(tzinfo=timezone.utc)

                # Apply the same duration to get the new end time
                new_end_dt = new_start_dt + duration

                # Update the event times
                event['start']['dateTime'] = new_start_dt.isoformat()
                event['end']['dateTime'] = new_end_dt.isoformat()

            elif field == "reminder":
                # Parse the reminder value
                reminder_minutes = 10  # Default
                if value:
                    # Try to extract the minutes
                    reminder_match = re.search(r'(\d+)\s*minutes?', value)
                    if reminder_match:
                        reminder_minutes = int(reminder_match.group(1))
                    elif value.isdigit():
                        reminder_minutes = int(value)

                # Update the reminders
                event['reminders'] = {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': reminder_minutes},
                    ],
                }

            # Update the event
            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event
            ).execute()

            return True, f"Successfully updated the {field} of the event."

        except Exception as e:
            print(f"Error updating event field: {e}")
            return False, f"Error updating event: {str(e)}"