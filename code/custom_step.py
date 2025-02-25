import requests
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
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

def calculate_distance_from_steps(steps: int, step_length: float) -> float:
    """Calculate distance in meters from number of steps"""
    return steps * step_length

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

def get_itinerary(
    api_key: str,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    datetime: Optional[datetime] = None
) -> Dict[Any, Any]:
    """Get itinerary from the API with multiple alternatives"""
    base_url = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
    
    headers = {
        "Accept": "application/json",
        "apiKey": api_key
    }
    
    params = {
        "from": f"{from_lon};{from_lat}",
        "to": f"{to_lon};{to_lat}",
        "datetime": datetime.strftime("%Y%m%dT%H%M%S") if datetime else None,
        "count": 20,  # Increased from 10 to 20
        "min_nb_journeys": 10,  # Increased from 5 to 10
        "max_nb_journeys": 20   # Increased from 10 to 20
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

def find_stations_in_radius(center_lat: float, center_lon: float, radius: float, api_key: str) -> List[Dict]:
    """Find all public transport stations within a given radius"""
    base_url = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
    
    headers = {
        "Accept": "application/json",
        "apiKey": api_key
    }
    
    params = {
        "count": 100,
        "distance": int(radius),
        "type[]": ["stop_point"],
    }
    
    url = f"{base_url}/coverage/fr-idf/coords/{center_lon};{center_lat}/places_nearby"
    print(f"\nRequesting URL: {url}")
    print(f"With params: {params}")
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get('places_nearby', [])
    except requests.RequestException as e:
        print(f"Error finding stations: {e}")
        print(f"Response content: {response.text if 'response' in locals() else 'No response'}")
        return []

def find_best_route(
    from_stations: List[Dict],
    to_stations: List[Dict],
    target_steps: int,
    step_length: float,
    api_key: str
) -> Dict:
    """Find the best route that has walking distance closest to target steps"""
    best_journey = None
    best_score = float('inf')
    target_distance = calculate_distance_from_steps(target_steps, step_length)
    
    MAX_STATIONS = 10
    
    # Sort stations by distance from origin/destination
    from_stations.sort(key=lambda x: haversine_distance(
        float(x['stop_point']['coord']['lat']),
        float(x['stop_point']['coord']['lon']),
        from_lat, from_lon
    ))
    to_stations.sort(key=lambda x: haversine_distance(
        float(x['stop_point']['coord']['lat']),
        float(x['stop_point']['coord']['lon']),
        to_lat, to_lon
    ))
    
    # For high step counts, take the farthest stations from both origin and destination
    if target_steps > 3000:
        selected_from_stations = from_stations[-MAX_STATIONS:]  # Take farthest stations
        selected_to_stations = to_stations[-MAX_STATIONS:]      # Take farthest stations
        print(f"\nEvaluating routes using {MAX_STATIONS} farthest stations (high step count mode)")
    else:
        selected_from_stations = from_stations[:MAX_STATIONS]   # Take closest stations
        selected_to_stations = to_stations[:MAX_STATIONS]       # Take closest stations
        print(f"\nEvaluating routes using {MAX_STATIONS} closest stations")
    
    for from_station in selected_from_stations:
        for to_station in selected_to_stations:  # Now iterating through selected destination stations
            try:
                # Calculate walking distances to/from stations
                walk_to_station = haversine_distance(
                    from_lat, from_lon,
                    float(from_station['stop_point']['coord']['lat']),
                    float(from_station['stop_point']['coord']['lon'])
                )
                
                walk_from_station = haversine_distance(
                    float(to_station['stop_point']['coord']['lat']),
                    float(to_station['stop_point']['coord']['lon']),
                    to_lat, to_lon
                )
                
                print(f"Evaluating route: {walk_to_station/1000:.2f}km to first station, "
                      f"{walk_from_station/1000:.2f}km from last station")
                
                result = get_itinerary(
                    api_key=api_key,
                    from_lat=float(from_station['stop_point']['coord']['lat']),
                    from_lon=float(from_station['stop_point']['coord']['lon']),
                    to_lat=float(to_station['stop_point']['coord']['lat']),
                    to_lon=float(to_station['stop_point']['coord']['lon'])
                )
                
                if not result.get('journeys'):
                    continue
                
                for journey in result['journeys']:
                    total_walking_distance = sum(
                        calculate_walking_distance(section)
                        for section in journey['sections']
                        if section['type'] == 'street_network' and section['mode'] == 'walking'
                    )
                    
                    score = abs(total_walking_distance - target_distance)
                    
                    if score < best_score:
                        best_score = score
                        best_journey = journey
                        print(f"Found better route with {total_walking_distance:.0f}m walking "
                              f"(target: {target_distance:.0f}m)")
                        
            except Exception as e:
                print(f"Error processing route: {e}")
                continue
    
    return best_journey

if __name__ == "__main__":
    API_KEY = "FKAm2gGNePhDQ7PUrZUGxnqk6NEhMoi4"
    
    # Get user inputs
    height = float(input("Enter your height in cm: "))
    target_steps = int(input("Enter target number of steps: "))
    
    # Calculate parameters
    step_length = calculate_step_length(height)
    search_radius = calculate_distance_from_steps(target_steps // 2, step_length)
    
    print(f"Step length: {step_length:.2f} meters")
    print(f"Search radius: {search_radius:.2f} meters")
    
    # 49 rue Lecourbe, Paris to Hôpital Louis-Mourier, Colombes
    from_lat, from_lon = 48.843890, 2.306979
    to_lat, to_lon = 48.925073, 2.236467
    
    try:
        # Find stations within radius of both points
        print("\nSearching for stations from origin point...")
        from_stations = find_stations_in_radius(from_lat, from_lon, search_radius, API_KEY)
        print(f"Found {len(from_stations)} stations near origin")
        
        print("\nSearching for stations from destination point...")
        to_stations = find_stations_in_radius(to_lat, to_lon, search_radius, API_KEY)
        print(f"Found {len(to_stations)} stations near destination")
        
        if not from_stations or not to_stations:
            print(f"\nNo stations found within {search_radius/1000:.2f} km radius!")
            print("Try increasing the number of target steps for a larger search area.")
            exit()
        
        # Find best route
        best_journey = find_best_route(
            from_stations,
            to_stations,
            target_steps,
            step_length,
            API_KEY
        )
        
        if best_journey:
            format_itinerary_with_steps({'journeys': [best_journey]}, step_length)
        else:
            print("No suitable route found!")
            
    except requests.RequestException as e:
        print("Error accessing the API. Please check your API key and connection.")
        print(f"Error details: {e}")