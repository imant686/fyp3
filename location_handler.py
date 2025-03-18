import os
import requests
import re
from dotenv import load_dotenv

class LocationHandler:
    def __init__(self):
        load_dotenv()
        self.google_api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        self.places_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        self.nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        self.details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        self.geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
        self.directions_url = "https://maps.googleapis.com/maps/api/directions/json"

        # Hard-coded heriot watt univeristy coordinates.
        self.default_lat = 55.9086
        self.default_lng = -3.3203
        self.default_location_name = "Heriot-Watt University"

        # Test API connection on initialization
        is_working, message = self.test_api_connection()
        if not is_working:
            print(f"WARNING: Google Places API connection issue: {message}")

    def process_location_query(self, query):
        """
        Main entry point for location-related queries.
        Analyzes the query and dispatches to the appropriate API endpoint.
        """
        query = query.lower()

        # Check for directions request
        if any(term in query for term in ["directions to", "how to get to", "route to"]):
            return self._handle_directions_query(query)

        # Check for "nearest" or "nearby" query
        if any(term in query for term in ["nearest", "nearby", "closest", "near me"]):
            return self._handle_nearby_query(query)

        # Default to a general place search
        return self._handle_general_query(query)

    def _handle_general_query(self, query):
        """Handle general queries like 'restaurants in Edinburgh' or 'best coffee shop'"""
        try:
            # Extract location if specified
            location = self._extract_location_from_query(query)

            # Build parameters
            params = {
                'key': self.google_api_key,
                'query': query,
                'language': 'en'
            }

            # If we extracted a specific location, add it to narrow results
            if location:
                params['location'] = f"{location['lat']},{location['lng']}"
                params['radius'] = 5000  # 5km radius for better results

            response = requests.get(self.places_url, params=params)
            response.raise_for_status()
            data = response.json

            if data['status'] != 'OK' or not data.get('results'):
                if data['status'] == 'ZERO_RESULTS':
                    return f"I couldn't find any places matching '{query}'."
                elif data['status'] == 'REQUEST_DENIED':
                    print(f"API request denied: {data.get('error_message', 'No error message')}")
                    return "I'm having trouble connecting to the location service. Please try again later."
                else:
                    print(f"API error: {data['status']} - {data.get('error_message', 'No error message')}")
                    return "I couldn't find any places matching your search."

            # Format results
            results = data['results'][:5]  # Limit to top 5 for voice response
            response_text = "Here's what I found:\n"

            for i, place in enumerate(results, 1):
                name = place['name']
                address = place.get('formatted_address', 'Address not available')
                rating = place.get('rating', None)

                response_text += f"{i}. {name} - {address}. "
                if rating:
                    response_text += f"Rated {rating}/5. "

                # Add opening hours if available
                if 'opening_hours' in place:
                    is_open = place['opening_hours'].get('open_now', False)
                    response_text += "Currently " + ("open" if is_open else "closed") + ". "

                response_text += "\n"

            return response_text

        except Exception as e:
            print(f"Error in general query: {e}")
            return "I encountered an error while searching. Please try again."

    def _handle_nearby_query(self, query):
        """Handle 'nearest' or 'closest' type queries with progressive radius expansion"""
        try:
            # Extract the place type
            place_type = None
            radius = 2000  # Start with 2km radius

            # Common types that might be in the query
            type_patterns = {
                "restaurant": "restaurant",
                "restaurants": "restaurant",
                "dining": "restaurant",
                "diner": "restaurant",
                "café": "cafe",
                "cafe": "cafe",
                "coffee": "cafe",
                "coffee shop": "cafe",
                "gas": "gas_station",
                "gas station": "gas_station",
                "petrol": "gas_station",
                "fuel": "gas_station",
                "petrol station": "gas_station",
                "grocery": "grocery_store",
                "supermarket": "grocery_store",
                "food store": "grocery_store",
                "grocery store": "grocery_store",
                "markets": "grocery_store",
                "pharmacy": "pharmacy",
                "chemist": "pharmacy",
                "drugstore": "pharmacy",
                "hospital": "hospital",
                "medical center": "hospital",
                "emergency room": "hospital",
                "atm": "atm",
                "cash machine": "atm",
                "bank": "bank",
                "hotel": "lodging",
                "motel": "lodging",
                "lodging": "lodging",
                "inn": "lodging",
                "accommodation": "lodging",
                "school": "school",
                "university": "university",
                "college": "university",
                "park": "park",
                "playground": "park",
                "garden": "park",
                "parking": "parking",
                "car park": "parking",
                "post office": "post_office",
                "postal": "post_office",
                "cinema": "movie_theater",
                "theater": "movie_theater",
                "movie": "movie_theater",
                "films": "movie_theater",
                "mall": "shopping_mall",
                "shopping center": "shopping_mall",
                "shopping": "shopping_mall",
                "shopping centre": "shopping_mall",
                "store": "store",
                "shop": "store",
                "retail": "store",
                "library": "library",
                "book store": "book_store",
                "bookstore": "book_store",
                "museum": "museum",
                "gallery": "museum",
                "exhibition": "museum",
                "bar": "bar",
                "pub": "bar",
                "tavern": "bar",
                "night club": "night_club",
                "nightclub": "night_club",
                "club": "night_club",
                "disco": "night_club"
            }

            for pattern, type_value in type_patterns.items():
                if pattern in query:
                    place_type = type_value
                    break

            if not place_type:
                # If we couldn't determine a specific type, extract any nouns after "nearest"
                type_match = re.search(r'(nearest|closest|nearby)\s+([a-z\s]+)', query)
                if type_match:
                    extracted_type = type_match.group(2).strip()
                    print(f"Extracted type from query: '{extracted_type}'")

                    # Check if this extracted type matches any known type
                    for pattern, type_value in type_patterns.items():
                        if pattern in extracted_type:
                            place_type = type_value
                            break

                    # If still no match, use the extracted text as a keyword
                    if not place_type:
                        place_type = extracted_type

            # Extract location or use default
            location_info = self._extract_location_from_query(query)
            if location_info:
                lat, lng = location_info['lat'], location_info['lng']
                location_name = location_info['name']
            else:
                lat, lng = self.default_lat, self.default_lng
                location_name = self.default_location_name
            results = []

            # Build base parameters
            base_params = {
                'key': self.google_api_key,
                'location': f"{lat},{lng}",
                'language': 'en'
            }

            # Add type if available (otherwise will use keyword)
            if place_type in type_patterns.values():
                base_params['type'] = place_type

                # Special case for grocery stores - use both type AND keyword
                if place_type == "grocery_store":
                    base_params['keyword'] = "supermarket grocery"
            else:
                base_params['keyword'] = place_type

            # Try increasingly larger radii until we find results
            for radius in [2000, 5000, 10000, 20000]:  # 2km, 5km, 10km, 20km
                try:
                    params = base_params.copy()
                    params['radius'] = radius

                    response = requests.get(self.nearby_url, params=params)
                    response.raise_for_status()
                    data = response.json()


                    if data['status'] == 'OK' and data.get('results'):
                        results = data['results']
                        break

                    if data['status'] == 'INVALID_REQUEST':
                        print("Invalid request, trying textSearch instead of nearbySearch")
                        # Fall back to text search
                        text_params = {
                            'key': self.google_api_key,
                            'query': f"{place_type} near {location_name}",
                            'language': 'en'
                        }
                        text_response = requests.get(self.places_url, params=text_params)
                        text_data = text_response.json()

                        if text_data['status'] == 'OK' and text_data.get('results'):
                            results = text_data['results']
                            print(f"Text search found {len(results)} results")
                            break

                except Exception as radius_error:
                    print(f"Error with radius {radius}m: {radius_error}")
                    continue

            if not results:
                if place_type:
                    # Try one last fallback using textSearch
                    try:
                        fallback_params = {
                            'key': self.google_api_key,
                            'query': f"{place_type} near {location_name}",
                            'language': 'en'
                        }
                        fallback_response = requests.get(self.places_url, params=fallback_params)
                        fallback_data = fallback_response.json()

                        if fallback_data['status'] == 'OK' and fallback_data.get('results'):
                            results = fallback_data['results']
                            print(f"Fallback search found {len(results)} results")
                    except Exception as fallback_error:
                        print(f"Error in fallback search: {fallback_error}")

                if not results:
                    type_str = place_type if place_type else "places"
                    return f"I couldn't find any {type_str} nearby {location_name}."

            # Special filter for grocery stores to remove hotels and other irrelevant results
            if place_type == "grocery_store":
                filtered_results = []
                for place in results:
                    # Check if name or vicinity contains grocery-related terms
                    name = place.get('name', '').lower()
                    vicinity = place.get('vicinity', '').lower()

                    # Skip hotels and other irrelevant results
                    if any(term in name for term in ['hotel', 'apartment', 'accommodation']):
                        continue

                    # Prioritize places that contain grocery keywords
                    if any(term in name for term in ['grocery', 'supermarket', 'food', 'market', 'store']):
                        filtered_results.insert(0, place)  # Add to beginning
                    else:
                        filtered_results.append(place)  # Add to end

                # Use filtered results if we found any
                if filtered_results:
                    results = filtered_results

            # Format results
            results = results[:3]  # Limit to top 3 for voice response

            type_display = place_type if place_type else "places"
            response_text = f"Here are the results"

            for i, place in enumerate(results, 1):
                name = place['name']
                vicinity = place.get('vicinity', place.get('formatted_address', 'Address not available'))
                rating = place.get('rating', None)

                response_text += f"{i}. {name} - {vicinity}. "
                if rating:
                    response_text += f"Rated {rating}/5. "

                # Add opening hours if available
                if 'opening_hours' in place:
                    is_open = place['opening_hours'].get('open_now', False)
                    response_text += "Currently " + ("open" if is_open else "closed") + ". "

                response_text += "\n"

            return response_text

        except Exception as e:
            print(f"Error in nearby query: {e}")
            import traceback
            traceback.print_exc()
            return "I encountered an error while searching for nearby places. Please try again."

    def _handle_directions_query(self, query):
        """Handle directions queries"""
        try:
            # Extract destination
            dest_match = re.search(r'(directions to|how to get to|route to) (.+?)(?:$|\?)', query)
            if not dest_match:
                return "I need a destination to provide directions. Where would you like to go?"

            destination = dest_match.group(2).strip()

            # Try to extract origin if provided (e.g., "from Central Park")
            origin = None
            origin_match = re.search(r'from (.+?) to', query, re.IGNORECASE)
            if origin_match:
                origin = origin_match.group(1).strip()

            # If no explicit origin, use default
            if not origin:
                origin = self.default_location_name

            # Extract travel mode
            mode = "driving"  # Default
            if "walking" in query or "on foot" in query or "walk" in query:
                mode = "walking"
            elif "transit" in query or "bus" in query or "train" in query or "public transport" in query:
                mode = "transit"
            elif "bicycle" in query or "bike" in query or "cycling" in query:
                mode = "bicycling"

            # Build parameters
            params = {
                'key': self.google_api_key,
                'origin': origin,
                'destination': destination,
                'mode': mode,
                'language': 'en'
            }

            print(f"Directions query params: {params}")

            # Make the API call
            response = requests.get(self.directions_url, params=params)
            response.raise_for_status()
            data = response.json()

            print(f"Directions API response status: {data['status']}")

            if data['status'] != 'OK':
                if data['status'] == 'ZERO_RESULTS':
                    return f"I couldn't find directions from {origin} to {destination} by {mode}."
                else:
                    print(f"Directions API error: {data['status']} - {data.get('error_message', 'No error message')}")
                    return f"I couldn't find directions to {destination}."

            # Extract route information
            route = data['routes'][0]
            leg = route['legs'][0]

            distance = leg['distance']['text']
            duration = leg['duration']['text']

            # Format a simplified response appropriate for voice
            response_text = f"To get from {origin} to {destination}: "
            response_text += f"It's about {distance} away and will take approximately {duration} by {mode}. "

            # Add key steps (limited for voice response)
            steps = leg['steps']
            if len(steps) <= 3:
                # If few steps, include all
                response_text += "Here are the directions: "
                for i, step in enumerate(steps, 1):
                    # Remove HTML tags
                    instruction = re.sub('<[^<]+?>', '', step['html_instructions'])
                    response_text += f"{i}. {instruction}. "
            else:
                # If many steps, just give the first couple
                response_text += "Here's how to start: "
                for i in range(2):  # Just the first 2 steps
                    instruction = re.sub('<[^<]+?>', '', steps[i]['html_instructions'])
                    response_text += f"{i+1}. {instruction}. "
                response_text += "Would you like the complete directions?"

            return response_text

        except Exception as e:
            print(f"Error in directions query: {e}")
            return "I encountered an error while getting directions. Please try again."

    def _extract_location_from_query(self, query):
        """Extract location information from a query string."""
        # Check for "near me" without actual location
        if "near me" in query.lower():
            return {
                'lat': self.default_lat,
                'lng': self.default_lng,
                'name': self.default_location_name
            }

        # Check for specific location mentioned (e.g., "in New York", "near London")
        location_match = re.search(r'(?:in|near|around|at) ([A-Za-z\s]+)(?:\s|$|\.|\?)', query)
        if location_match:
            location_name = location_match.group(1).strip()

            # Skip generic terms like "the area", "the city", etc.
            generic_terms = ["the area", "the city", "here", "there", "the location", "this place"]
            if location_name.lower() in generic_terms:
                return {
                    'lat': self.default_lat,
                    'lng': self.default_lng,
                    'name': self.default_location_name
                }

            # For a real app, you would geocode this location name
            # For now, we'll just return the default location with the extracted name
            # In a full implementation, you'd call the Geocoding API here

            try:
                # Try to geocode the location name
                geocode_params = {
                    'key': self.google_api_key,
                    'address': location_name
                }
                geocode_response = requests.get(self.geocode_url, params=geocode_params)
                geocode_data = geocode_response.json()

                if geocode_data['status'] == 'OK' and geocode_data.get('results'):
                    location = geocode_data['results'][0]['geometry']['location']
                    return {
                        'lat': location['lat'],
                        'lng': location['lng'],
                        'name': location_name
                    }
            except Exception as geocode_error:
                print(f"Geocoding error for '{location_name}': {geocode_error}")

            # Fallback to default if geocoding fails
            return {
                'lat': self.default_lat,
                'lng': self.default_lng,
                'name': location_name
            }

        # No location specified, use default
        return None

    def test_api_connection(self):
        """Test if the Google Places API connection is working."""
        try:
            # Verify API key is not empty
            if not self.google_api_key:
                return False, "API key is missing or empty"

            params = {
                'key': self.google_api_key,
                'query': "coffee shop Edinburgh",
            }

            response = requests.get(self.places_url, params=params)

            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'OK':
                    return True, "API connection successful"
                elif data['status'] == 'REQUEST_DENIED':
                    return False, f"API request denied: {data.get('error_message', 'No error message')}"
                else:
                    return False, f"API error: {data['status']} - {data.get('error_message', 'No error message')}"
            else:
                return False, f"HTTP error: {response.status_code}"

        except Exception as e:
            return False, f"Exception: {str(e)}"