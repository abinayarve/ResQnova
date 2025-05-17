import requests
import folium
from folium.plugins import HeatMap
from flask import Flask, render_template
import threading
import time
import rasterio
from rasterio.warp import transform
import numpy as np

app = Flask(__name__)

heatmap_data = []
population_data = {}

# Path to the WorldPop dataset
WORLDPOP_FILE = "ind_pd_2020_1km_UNadj.tif"

def fetch_usgs_earthquake_data():
    """
    Fetches real-time earthquake data from the USGS Earthquake API.
    """
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": "2023-09-01",  # Last 30 days
        "endtime": "2023-10-01",
        "minmagnitude": 4.0,  # Minimum magnitude
        "latitude": 20.5937,  # Center on India
        "longitude": 78.9629,
        "maxradiuskm": 2000,  # Radius around India
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            earthquakes = []
            for feature in data["features"]:
                lat = feature["geometry"]["coordinates"][1]
                lon = feature["geometry"]["coordinates"][0]
                magnitude = feature["properties"]["mag"]
                earthquakes.append((lat, lon, magnitude))
            return earthquakes
        else:
            print(f"Failed to fetch USGS data: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"USGS API Error: {e}")
    return None

def get_population_density(lat, lon):
    """
    Extracts population density for a given latitude and longitude from the WorldPop dataset.
    """
    try:
        with rasterio.open(WORLDPOP_FILE) as dataset:
            # Convert latitude/longitude to the dataset's coordinate reference system (CRS)
            x, y = transform("EPSG:4326", dataset.crs, [lon], [lat])
            row, col = dataset.index(x[0], y[0])  # Get the pixel coordinates
            population_density = dataset.read(1, window=((row, row + 1), (col, col + 1)))
            return float(population_density[0][0])
    except Exception as e:
        print(f"Error reading WorldPop dataset: {e}")
    return None

def estimate_affected_people(lat, lon, magnitude):
    """
    Estimates the number of affected people based on population density and earthquake magnitude.
    """
    population_density = get_population_density(lat, lon)
    if population_density is None:
        return "Unknown"

    # Define an impact radius based on earthquake magnitude
    impact_radius_km = magnitude * 10  # Example: 10 km per magnitude unit
    impact_area_km2 = np.pi * (impact_radius_km ** 2)  # Area of the impact circle

    # Estimate affected people
    affected_people = population_density * impact_area_km2
    return int(affected_people)

def process_usgs_data(usgs_data):
    """
    Processes earthquake data and estimates the number of affected people.
    """
    global heatmap_data, population_data
    if usgs_data:
        heatmap_data.clear()  # Clear previous data
        population_data.clear()  # Clear previous data
        for lat, lon, magnitude in usgs_data:
            heatmap_data.append((lat, lon, magnitude))
            
            # Estimate the number of affected people
            affected_people = estimate_affected_people(lat, lon, magnitude)
            population_data[(lat, lon)] = affected_people
    else:
        print("No results found in USGS data.")

def create_heatmap(heatmap_data, population_data):
    """
    Creates a Folium heatmap with earthquake data and affected people markers.
    """
    map = folium.Map(location=[20.5937, 78.9629], zoom_start=5)  # Centered on India

    # Add heatmap layer
    HeatMap(heatmap_data).add_to(map)

    # Add affected people markers
    for (lat, lon), affected_people in population_data.items():
        folium.Marker(
            location=[lat, lon],
            popup=f"Affected People: {affected_people}",
            icon=folium.Icon(color="red")
        ).add_to(map)

    # Add extreme disaster alert
    if heatmap_data:
        most_extreme = max(heatmap_data, key=lambda x: x[2])
        lat, lon, intensity = most_extreme
        alert_html = f"""
            <div style="position: fixed; top: 10px; right: 10px; z-index: 1000; padding: 10px; background-color: red; color: white; font-weight: bold;">
                Extreme Disaster Alert!<br>
                Location: ({lat:.2f}, {lon:.2f})<br>
                Intensity: {intensity:.2f}
            </div>
        """
        map.get_root().html.add_child(folium.Element(alert_html))

    return map

def update_heatmap():
    """
    Periodically updates the heatmap data.
    """
    global heatmap_data, population_data
    while True:
        print("Updating heatmap data...")

        # Fetch new earthquake data
        usgs_data = fetch_usgs_earthquake_data()

        # Process the new data
        if usgs_data:
            process_usgs_data(usgs_data)
        else:
            print("No new earthquake data found.")

        # Wait for 10 minutes before the next update
        time.sleep(600)

@app.route("/")
def home():
    """
    Renders the dashboard page with the heatmap.
    """
    global heatmap_data, population_data
    heatmap = create_heatmap(heatmap_data, population_data)
    return render_template("dashboard.html", map=heatmap._repr_html_())

if __name__ == "__main__":
    # Start the heatmap update thread
    threading.Thread(target=update_heatmap, daemon=True).start()

    # Run the Flask app
    app.run(debug=True)