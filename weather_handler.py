import os
import requests
from datetime import datetime, timedelta
import re

class WeatherHandler:
    def __init__(self):
        # Load API key from environment variable
        self.api_key = os.getenv("WEATHER_API_KEY")
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        self.forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
        self.default_location = "Edinburgh"

    def get_current_weather(self, location):
        """Get current weather for a specific location."""
        try:
            params = {
                'q': location,
                'appid': self.api_key,
                'units': 'metric'  # Use metric units for temperatures in Celsius
            }
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors

            data = response.json()

            # Extract relevant information
            weather_description = data['weather'][0]['description']
            temperature = round(data['main']['temp'])
            feels_like = round(data['main']['feels_like'])
            humidity = data['main']['humidity']
            wind_speed = data['wind']['speed']

            # Format the response
            weather_info = (
                f"Current weather in {data['name']}: {weather_description}. "
                f"Temperature is {temperature}°C, feels like {feels_like}°C. "
                f"Humidity is {humidity}% with wind speeds of {wind_speed} m/s."
            )

            return weather_info

        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                return f"I couldn't find weather information for '{location}'. Please check the location name and try again."
            else:
                print(f"Weather API HTTP error: {e}")
                return "I'm sorry, I encountered an error while fetching the weather information. Please try again later."

        except Exception as e:
            print(f"Error in get_current_weather: {e}")
            return "I'm sorry, I had trouble getting weather information. Please try again later."

    def get_weather_forecast(self, location, date_str=None):
        """Get weather forecast for a location and date."""
        try:
            # If no date is provided, default to tomorrow
            if not date_str:
                target_date = datetime.now() + timedelta(days=1)
            else:
                # Try to parse the date string
                try:
                    # Check if date_str is already a date object
                    if isinstance(date_str, datetime):
                        target_date = date_str
                    else:
                        # Try to parse various date formats
                        target_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    # If standard format fails, try more flexible parsing
                    try:
                        from dateparser import parse
                        parsed_date = parse(date_str)
                        if parsed_date:
                            target_date = parsed_date
                        else:
                            return "I couldn't understand the date format. Please try something like 'tomorrow' or 'March 15th'."
                    except ImportError:
                        return "I'm having trouble parsing the date. Please provide a date in YYYY-MM-DD format."

            # Check if date is within forecast range (5 days)
            now = datetime.now()
            days_from_now = (target_date - now).days

            if days_from_now < 0:
                return "I can't provide weather forecasts for past dates."

            if days_from_now > 5:
                return f"I can only provide weather forecasts up to 5 days in advance. The date you requested is {days_from_now} days from now."

            # Format the target date for display
            formatted_date = target_date.strftime("%A, %B %d")

            # Request forecast data
            params = {
                'q': location,
                'appid': self.api_key,
                'units': 'metric'  # Changed to metric for Celsius
            }

            response = requests.get(self.forecast_url, params=params)
            response.raise_for_status()

            data = response.json()

            # The API returns forecast data in 3-hour intervals
            # We need to find the entries for our target date
            target_date_str = target_date.strftime("%Y-%m-%d")
            day_forecasts = []

            for entry in data['list']:
                entry_date = entry['dt_txt'].split(' ')[0]
                if entry_date == target_date_str:
                    day_forecasts.append(entry)

            if not day_forecasts:
                return f"I couldn't find weather forecast data for {formatted_date}."

            # Calculate average or pick a representative time (like noon)
            # For simplicity, we'll use the noon forecast or the closest to it
            noon_forecast = None
            for forecast in day_forecasts:
                time = forecast['dt_txt'].split(' ')[1]
                if '12:00:00' in time:
                    noon_forecast = forecast
                    break

            # If no noon forecast, take the middle of the day
            if not noon_forecast and day_forecasts:
                noon_forecast = day_forecasts[len(day_forecasts) // 2]

            if noon_forecast:
                weather_description = noon_forecast['weather'][0]['description']
                temperature = round(noon_forecast['main']['temp'])
                feels_like = round(noon_forecast['main']['feels_like'])
                humidity = noon_forecast['main']['humidity']
                wind_speed = noon_forecast['wind']['speed']

                weather_info = (
                    f"Weather forecast for {location} on {formatted_date}: {weather_description}. "
                    f"Expected temperature around {temperature}°C, feeling like {feels_like}°C. "
                    f"Humidity will be around {humidity}% with wind speeds of {wind_speed} m/s."
                )

                return weather_info

            return f"I couldn't process the weather forecast for {formatted_date}."

        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                return f"I couldn't find weather information for '{location}'. Please check the location name and try again."
            else:
                print(f"Weather Forecast API HTTP error: {e}")
                return "I'm sorry, I encountered an error while fetching the forecast. Please try again later."

        except Exception as e:
            print(f"Error in get_weather_forecast: {e}")
            return "I'm sorry, I had trouble getting the weather forecast. Please try again later."

    def is_weather_query(self, user_input):
        """Determine if the user input is asking about weather."""
        weather_keywords = [
            "weather", "temperature", "forecast", "rain", "sunny", "cloudy",
            "snow", "hot", "cold", "humid", "precipitation", "storm",
            "thunderstorm", "climate", "degrees", "celsius", "fahrenheit"
        ]

        time_keywords = ["today", "tomorrow", "weekend", "week", "forecast"]

        # Check if the input contains weather-related keywords
        has_weather_keyword = any(keyword in user_input.lower() for keyword in weather_keywords)

        # Also detect queries like "How's the weather in New York?"
        weather_phrases = [
            "how's the weather", "how is the weather", "what's the weather",
            "what is the weather", "weather like"
        ]
        has_weather_phrase = any(phrase in user_input.lower() for phrase in weather_phrases)

        return has_weather_keyword or has_weather_phrase

    def extract_location_from_query(self, user_input):
        """Extract location from a weather query with improved filtering."""
        # First, clean up the query to handle "weather like today" pattern
        # This pattern is being incorrectly parsed as a location "like today"
        user_input = re.sub(r'weather\s+like\s+(today|tomorrow)', 'weather today', user_input, flags=re.IGNORECASE)

        # Look for patterns like "weather in [location]" or "temperature at [location]"
        location_patterns = [
            r"(?:weather|temperature|forecast)(?:\s+(?:in|at|for|of))?\s+([A-Za-z\s]+(?:,\s*[A-Za-z\s]+)?)",
            r"(?:in|at|for)\s+([A-Za-z\s]+(?:,\s*[A-Za-z\s]+)?)\s+(?:weather|temperature|forecast)",
            r"(?:how's|what's|how is|what is)(?:\s+the)?\s+weather(?:\s+(?:in|at|for))?\s+([A-Za-z\s]+(?:,\s*[A-Za-z\s]+)?)"
        ]

        # Expanded list of words to filter out that aren't locations
        filter_words = [
            'today', 'tomorrow', 'tonight', 'morning', 'afternoon', 'evening',
            'weekend', 'week', 'month', 'year', 'current', 'now', 'later', 'soon',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'like', 'going', 'to', 'be', 'the', 'will', 'is', 'are', 'was', 'were', 'am'
        ]

        for pattern in location_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                # Clean up any trailing punctuation
                location = re.sub(r'[^\w\s,]', '', location).strip()

                # Filter out common time and filler words
                location_words = location.lower().split()
                filtered_words = [word for word in location_words if word not in filter_words]

                # If we have any words left after filtering
                if filtered_words:
                    location = ' '.join(filtered_words)
                    print(f"Extracted location: {location}")
                    return location
        return self.default_location  # Return default location

    def extract_date_from_query(self, user_input):
        """Extract date from a weather query."""
        # Handle common time expressions
        if "tomorrow" in user_input.lower():
            return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "today" in user_input.lower():
            return datetime.now().strftime("%Y-%m-%d")
        elif "day after tomorrow" in user_input.lower() or "in 2 days" in user_input.lower():
            return (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

        # Look for date patterns (this is simplified, for robust parsing use dateparser)
        date_pattern = r'(?:on|for|this|next)\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+)'
        match = re.search(date_pattern, user_input, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            try:
                from dateparser import parse
                parsed_date = parse(date_str)
                if parsed_date:
                    return parsed_date.strftime("%Y-%m-%d")
            except:
                pass

        # If weekend is mentioned, return the next Saturday
        if "weekend" in user_input.lower():
            today = datetime.now()
            days_until_saturday = (5 - today.weekday()) % 7
            if days_until_saturday == 0:
                days_until_saturday = 7  # If today is Saturday, get next Saturday
            next_saturday = today + timedelta(days=days_until_saturday)
            return next_saturday.strftime("%Y-%m-%d")

        return None

    def process_weather_query(self, user_input, date_extractor=None):
        """Process a weather-related query and return an appropriate response."""
        try:
            # Extract location from query
            location = self.extract_location_from_query(user_input)

            # If no location found, use the default location
            if not location:
                print(f"No location specified, using default: {self.default_location}")
                location = self.default_location

            is_forecast = any(word in user_input.lower() for word in ["forecast", "tomorrow", "weekend", "next", "upcoming"])

            if is_forecast:
                # Extract date if possible
                date_str = self.extract_date_from_query(user_input)

                # If date extractor is provided and our extraction failed, try that
                if not date_str and date_extractor:
                    date_str = date_extractor(user_input)

                # Get forecast for the specified date
                return self.get_weather_forecast(location, date_str)
            else:
                # Get current weather
                return self.get_current_weather(location)
        except Exception as e:
            print(f"Error in process_weather_query: {e}")
            import traceback
            traceback.print_exc()
            return "I'm sorry, I had trouble processing your weather query. Please try again."