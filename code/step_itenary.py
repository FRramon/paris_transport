import requests
from datetime import datetime
from typing import Dict, Any, Optional
import folium
from folium import plugins
import webbrowser
import os
from IPython.display import display, HTML
from flask import Flask, request, jsonify
import threading
from math import radians, sin, cos, sqrt, atan2

# CO2 emissions in g/passenger-km
EMISSIONS = {
    'RER': 3.8,
    'Metro': 3.2,
    'Bus': 95.3,
    'Tramway': 3.3,
    'Train': 3.8,  # Using RER value for trains
    'Car': 206.0   # Average for small car
}

def calculate_step_length(height_cm: float) -> float:
    """
    Calculate average step length based on height.
    Formula: step length ≈ height * 0.413 for women and height * 0.415 for men
    Using average of 0.414
    """
    return (height_cm / 100) * 0.414  # Returns step length in meters

def calculate_steps(distance_meters: float, step_length: float) -> int:
    """Calculate number of steps for a given distance"""
    return int(distance_meters / step_length)

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the distance between two points on Earth using the Haversine formula.
    Returns distance in meters.
    """
    R = 6371000  # Earth's radius in meters

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c

    return distance

def calculate_walking_distance(journey_section: Dict[Any, Any]) -> float:
    """Calculate walking distance between coordinates in a section"""
    if not journey_section.get('from') or not journey_section.get('to'):
        return 0
    
    try:
        # Get "from" coordinates
        if journey_section['from'].get('embedded_type') == 'address':
            from_coord = journey_section['from']['address']['coord']
        else:  # stop_point
            from_coord = journey_section['from']['stop_point']['coord']
            
        # Get "to" coordinates
        if journey_section['to'].get('embedded_type') == 'address':
            to_coord = journey_section['to']['address']['coord']
        else:  # stop_point
            to_coord = journey_section['to']['stop_point']['coord']
        
        return haversine_distance(
            float(from_coord['lat']),
            float(from_coord['lon']),
            float(to_coord['lat']),
            float(to_coord['lon'])
        )
    except KeyError as e:
        print(f"KeyError: {e}")
        print("Structure not found in section")
        return 0

def get_stations_on_route(journey: Dict[Any, Any]) -> list:
    """Extract all stations on the route"""
    stations = []
    for section in journey['sections']:
        if section['type'] == 'public_transport':
            stations.append({
                'from': section['from'],
                'to': section['to'],
                'mode': section['display_informations'].get('physical_mode', '').split()[0],
                'line': section['display_informations'].get('code', '')
            })
    return stations

def create_walking_alternatives(stations: list, target_steps: int, step_length: float) -> list:
    """Create alternative routes by walking between some stations"""
    alternatives = []
    
    # Get initial direct journey as baseline
    base_journey = get_itinerary(
        api_key=API_KEY,
        from_lat=float(stations[0]['from']['stop_point']['coord']['lat']),
        from_lon=float(stations[0]['from']['stop_point']['coord']['lon']),
        to_lat=float(stations[-1]['to']['stop_point']['coord']['lat']),
        to_lon=float(stations[-1]['to']['stop_point']['coord']['lon'])
    )
    alternatives.append(base_journey)
    
    # Try skipping 1-3 stations at a time
    for skip_count in range(1, 4):
        for i in range(len(stations) - skip_count):
            # Create journey where we walk between stations i and i+skip_count
            from_station = stations[i]['from']
            to_station = stations[i + skip_count]['to']
            
            # Get journey with walking section
            alternative = get_itinerary(
                api_key=API_KEY,
                from_lat=float(from_station['stop_point']['coord']['lat']),
                from_lon=float(from_station['stop_point']['coord']['lon']),
                to_lat=float(to_station['stop_point']['coord']['lat']),
                to_lon=float(to_station['stop_point']['coord']['lon'])
            )
            alternatives.append(alternative)
    
    return alternatives

def get_itinerary(
    api_key: str,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    datetime: Optional[datetime] = None
) -> Dict[Any, Any]:
    """Get itinerary from the API"""
    base_url = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
    from_coords = f"{from_lon};{from_lat}"
    to_coords = f"{to_lon};{to_lat}"
    
    headers = {
        "Accept": "application/json",
        "apiKey": api_key
    }
    
    params = {
        "from": from_coords,
        "to": to_coords,
        "datetime": datetime.strftime("%Y%m%dT%H%M%S") if datetime else None,
        "count": 5,
        "disable_geojson": False
    }
    
    try:
        response = requests.get(
            f"{base_url}/journeys",
            headers=headers,
            params={k: v for k, v in params.items() if v is not None}
        )
        response.raise_for_status()
        return response.json()
        
    except requests.RequestException as e:
        print(f"Error fetching itinerary: {e}")
        raise

def format_itinerary_with_steps(journey_data: Dict[Any, Any], step_length: float) -> None:
    """Format and print itinerary details with step count information."""
    if not journey_data.get('journeys'):
        print("No journeys found!")
        return
    
    journey = journey_data['journeys'][0]
    total_walking_distance = 0
    total_distance = 0
    total_co2 = 0
    
    print("\nOptimal Itinerary:")
    print("-" * 30)
    print(f"Duration: {journey['duration'] // 60} minutes")
    
    for section in journey['sections']:
        if section['type'] == 'public_transport':
            # For public transport sections, use the coordinates to calculate actual distance
            distance = calculate_walking_distance(section) / 1000  # Convert to km
            total_distance += distance
            
            mode = section['display_informations'].get('physical_mode', '').split()[0]
            emission_factor = EMISSIONS.get(mode, 0)
            total_co2 += distance * emission_factor
            
            print(f"- Take {section['display_informations']['physical_mode']} {section['display_informations']['code']} "
                  f"from {section['from']['name']} to {section['to']['name']} "
                  f"({section['duration'] // 60} min, {distance:.1f} km)")
        
        elif section['type'] == 'street_network' and section['mode'] == 'walking':
            walking_distance = calculate_walking_distance(section)
            total_walking_distance += walking_distance
            steps = calculate_steps(walking_distance, step_length)
            
            print(f"- Walk for {section['duration'] // 60} minutes "
                  f"({steps} steps, {walking_distance/1000:.1f} km)")
        
        elif section['type'] == 'waiting':
            print(f"- Wait for {section['duration'] // 60} minutes")
    
    total_steps = calculate_steps(total_walking_distance, step_length)
    car_co2 = total_distance * EMISSIONS['Car']
    
    print("\nSummary:")
    print("-" * 30)
    print(f"Total steps: {total_steps}")
    print(f"Total walking distance: {total_walking_distance/1000:.1f} km")
    print(f"Total journey distance: {total_distance:.1f} km")
    print(f"CO2 emissions (public transport): {total_co2:.1f}g")
    print(f"CO2 emissions (if by car): {car_co2:.1f}g")
    print(f"CO2 saved: {car_co2 - total_co2:.1f}g")

if __name__ == "__main__":
    API_KEY = "FKAm2gGNePhDQ7PUrZUGxnqk6NEhMoi4"  # Replace with your actual API key
    
    # Get user inputs
    height = float(input("Enter your height in cm: "))
    
    # Calculate step length
    step_length = calculate_step_length(height)
    
    # Bastille to trocadero
    from_lat, from_lon = 48.853288, 2.368622
    to_lat, to_lon = 48.863146, 2.286460      # Hôpital Louis-Mourier, Colombes
    
    try:
        result = get_itinerary(
            api_key=API_KEY,
            from_lat=from_lat,
            from_lon=from_lon,
            to_lat=to_lat,
            to_lon=to_lon
        )
        format_itinerary_with_steps(result, step_length)
    except requests.RequestException as e:
        print("Please make sure you have a valid API key from IDFM")
        print("You can get one at: https://prim.iledefrance-mobilites.fr/fr/compte")
        print(f"Error details: {e}")