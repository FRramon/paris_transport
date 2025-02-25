import requests
import matplotlib.pyplot as plt
from collections import defaultdict
import seaborn as sns
import numpy as np 

def get_taux_de_regularite(train="intercites", departure=None, arrival=None):
    # Set parameters based on train type
    if train.lower() == "tgv":
        base_url = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/regularite-mensuelle-tgv-aqst/records"
    else:  # intercites
        base_url = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/regularite-mensuelle-intercites/records"

    limit = 100
    offset = 2000
    all_results = []
    
    while True:
        response = requests.get(f"{base_url}?limit={limit}&offset={offset}")
        
        if response.status_code != 200:
            print("Error fetching data")
            return None
        
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            break
        
        all_results.extend(results)
        offset += limit
    
    regularite_values = []

    for record in all_results:
        if train.lower() == "tgv":
            if (record.get("gare_depart") == departure and 
                record.get("gare_arrivee") == arrival):
                taux_de_regularite = 100 - 100 * record.get("nb_train_retard_sup_15", 0) / (record.get("nb_train_prevu", 0) - record.get("nb_annulation", 0))
                regularite_values.append(taux_de_regularite)
        else:
            if (record.get("depart") == departure and 
                record.get("arrivee") == arrival):
                taux_de_regularite = record.get("taux_de_regularite", 0)
                regularite_values.append(taux_de_regularite)

    return np.mean(regularite_values) if regularite_values else None


def generate_regularity_heatmap():
    # List of 10 major train stations in France
    stations = [
        "PARIS LYON",
        "MARSEILLE ST CHARLES",
        "LYON PART DIEU",
        "BORDEAUX ST JEAN", 
        "LILLE FLANDRES",
        "TOULOUSE MATABIAU",
        "NANTES",
        "STRASBOURG",
        "RENNES",
        "NICE VILLE"
    ]
    
    # Create matrices to store regularity data
    regularity_matrix = np.zeros((len(stations), len(stations)))
    
    # Calculate regularity for each station pair
    for i, departure in enumerate(stations):
        for j, arrival in enumerate(stations):
            if i != j:  # Skip same station pairs
                # Get regularity data for both TGV and Intercités
                tgv_data = get_taux_de_regularite("tgv", departure, arrival)
                intercites_data = get_taux_de_regularite("intercites", departure, arrival)
                
                # Average of available data (some routes might only have one type of train)
                valid_data = [x for x in [tgv_data, intercites_data] if x is not None]
                if valid_data:
                    regularity_matrix[i][j] = np.mean(valid_data)
    
    # Create heatmap
    plt.figure(figsize=(12, 10))
    sns.heatmap(regularity_matrix, 
                xticklabels=stations,
                yticklabels=stations,
                cmap='RdYlGn',
                center=85,
                annot=True,
                fmt='.1f')
    
    plt.title('Train Regularity Heatmap Between Major French Stations')
    plt.xlabel('Arrival Station')
    plt.ylabel('Departure Station')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

# Generate the heatmap
generate_regularity_heatmap()
