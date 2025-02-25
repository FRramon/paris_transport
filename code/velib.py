import requests
import folium

def get_velib_station_status(api_key: str, station_id: str) -> dict:
    """
    Fetch Vélib' station status from RATP API.
    
    Args:
        api_key (str): Your RATP API key
        station_id (str): Vélib' station ID
        
    Returns:
        dict: Station information including:
            - station_code: str
            - total_bikes: int
            - mechanical_bikes: int
            - ebikes: int
            - available_docks: int
            - is_installed: bool
            - is_returning: bool
            - is_renting: bool
        Returns None if station not found
        
    Raises:
        requests.RequestException: If the API request fails
    """
    base_url = "https://prim.iledefrance-mobilites.fr/marketplace/velib"
    params = {
        "apikey": api_key
    }
    headers = {
        "Accept": "application/json"
    }
    
    try:
        # Get the full station status JSON file
        response = requests.get(
            f"{base_url}/station_status.json",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        # Find the specific station in the data
        data = response.json()
        for station in data.get('data', {}).get('stations', []):
            print(station)
            if int(station.get('station_id')) == int(station_id):
                # Extract bike counts from types array
                mechanical_bikes = 0
                ebikes = 0
                for bike_type in station.get('num_bikes_available_types', []):
                    if 'mechanical' in bike_type:
                        mechanical_bikes = bike_type['mechanical']
                    elif 'ebike' in bike_type:
                        ebikes = bike_type['ebike']
                
                # Return formatted station data
                return {
                    'station_code': station.get('stationCode'),
                    'total_bikes': station.get('num_bikes_available', 0),
                    'mechanical_bikes': mechanical_bikes,
                    'ebikes': ebikes,
                    'available_docks': station.get('num_docks_available', 0),
                    'is_installed': bool(station.get('is_installed')),
                    'is_returning': bool(station.get('is_returning')),
                    'is_renting': bool(station.get('is_renting'))
                }
                
        return None  # Return None if station not found
        
    except requests.RequestException as e:
        print(f"Error fetching Vélib' data: {e}")
        raise

def get_velib_station_info(api_key: str, station_id: str) -> dict:
    """
    Fetch Vélib' station information (name, location, etc.) from RATP API.
    
    Args:
        api_key (str): Your RATP API key
        station_id (str): Vélib' station ID
        
    Returns:
        dict: Station information including:
            - name: str
            - address: str
            - lat: float
            - lon: float
            - capacity: int
        Returns None if station not found
        
    Raises:
        requests.RequestException: If the API request fails
    """
    base_url = "https://prim.iledefrance-mobilites.fr/marketplace/velib"
    params = {
        "apikey": api_key
    }
    headers = {
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(
            f"{base_url}/station_information.json",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        data = response.json()

        for station in data.get('data', {}).get('stations', []):
            print(station)
            if int(station.get('station_id')) == int(station_id):
                return {
                    'name': station.get('name'),
                    'address': station.get('address'),
                    'lat': station.get('lat'),
                    'lon': station.get('lon'),
                    'capacity': station.get('capacity')
                }
                
        return None
        
    except requests.RequestException as e:
        print(f"Error fetching Vélib' station information: {e}")
        raise

def create_velib_map(api_key: str) -> None:
    """
    Create an interactive map showing all Vélib' stations with their e-bike availability.
    
    Args:
        api_key (str): Your RATP API key
    """
    # Create a map centered on Paris
    paris_map = folium.Map(location=[48.8566, 2.3522], zoom_start=13)
    
    # Get all station information
    base_url = "https://prim.iledefrance-mobilites.fr/marketplace/velib"
    params = {"apikey": api_key}
    headers = {"Accept": "application/json"}
    
    try:
        # Get all station information
        info_response = requests.get(
            f"{base_url}/station_information.json",
            headers=headers,
            params=params
        )
        info_response.raise_for_status()
        info_data = info_response.json()
        
        # Get all station statuses
        status_response = requests.get(
            f"{base_url}/station_status.json",
            headers=headers,
            params=params
        )
        status_response.raise_for_status()
        status_data = status_response.json()
        
        # Create a dictionary of station statuses for quick lookup
        status_dict = {
            station['station_id']: station 
            for station in status_data.get('data', {}).get('stations', [])
        }
        
        # Process each station
        for station in info_data.get('data', {}).get('stations', []):
            station_id = station.get('station_id')
            status = status_dict.get(station_id)
            
            if status:
                # Extract bike counts
                mechanical_bikes = 0
                ebikes = 0
                for bike_type in status.get('num_bikes_available_types', []):
                    if 'mechanical' in bike_type:
                        mechanical_bikes = bike_type['mechanical']
                    elif 'ebike' in bike_type:
                        ebikes = bike_type['ebike']
                
                # Create popup content
                popup_content = f"""
                    <b>{station.get('name')}</b><br>
                    Available e-bikes: {ebikes}<br>
                    Available mechanical bikes: {mechanical_bikes}<br>
                    Free docks: {status.get('num_docks_available', 0)}
                """
                
                # Add marker to map
                folium.Marker(
                    location=[station.get('lat'), station.get('lon')],
                    popup=popup_content,
                    tooltip=f"{station.get('name')} ({ebikes} e-bikes)",
                    icon=folium.Icon(color='red' if ebikes == 0 else 'green')
                ).add_to(paris_map)
    
        # Save the map to an HTML file
        paris_map.save('/Users/francoisramon/Desktop/Perso/public_transports/velib_map.html')
        print("Map has been created successfully!")
        
    except requests.RequestException as e:
        print(f"Error fetching Vélib' data: {e}")
        raise

# Example usage:
api_key = "FKAm2gGNePhDQ7PUrZUGxnqk6NEhMoi4"
create_velib_map(api_key)