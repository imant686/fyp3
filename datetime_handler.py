import re
from dateparser import parse
from datetime import datetime, timezone

class DateTimeHandler:
    @staticmethod
    def ensure_timezone_aware(dt):
        """Ensure a datetime is timezone-aware."""
        if dt is None:
            return None
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        return dt

    @staticmethod
    def parse_date_string(date_str):
        """Parse a date string to a timezone-aware datetime."""
        if not date_str:
            return None
        try:
            # Try standard format first
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            try:
                # Try dateparser for more flexible parsing
                dt = parse(date_str)
                if not dt:
                    return None
            except Exception:
                return None

        # Make timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def date_to_aware_datetime(date_obj, time_str=None):
        """Convert a date object to a timezone-aware datetime."""
        if not date_obj:
            return None

        if time_str:
            # Parse time if provided
            try:
                time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', time_str.lower())
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2) or "0")
                    ampm = time_match.group(3)

                    # Convert to 24-hour format
                    if ampm and ampm.lower() == 'pm' and hour < 12:
                        hour += 12
                    if ampm and ampm.lower() == 'am' and hour == 12:
                        hour = 0

                    dt = datetime.combine(date_obj, datetime.time(hour, minute))
                else:
                    dt = datetime.combine(date_obj, datetime.time(0, 0))
            except Exception:
                dt = datetime.combine(date_obj, datetime.time(0, 0))
        else:
            dt = datetime.combine(date_obj, datetime.time(0, 0))

        # Make timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
