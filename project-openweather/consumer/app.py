from datetime import datetime
from kafka import KafkaConsumer
from pymongo import MongoClient
import json
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC')
KAFKA_SERVER = os.getenv('KAFKA_SERVER')
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB = os.getenv('MONGO_DB')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION')

# Initialiser le client MongoDB
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB]
mongo_collection = mongo_db[MONGO_COLLECTION]

# Initialiser le consommateur Kafka
consumer = KafkaConsumer(
    KAFKA_TOPIC,
    bootstrap_servers=KAFKA_SERVER,
    auto_offset_reset='earliest',
    enable_auto_commit=True,
    value_deserializer=lambda v: json.loads(v.decode('utf-8'))
)

def process_weather_data(data):
    """Traiter les données météo et les insérer dans MongoDB."""
    try:
        # Exemple : extraction des champs pertinents
        processed_data = {
            "ville": data.get("city", {}).get("name"),  # Ville
            "pays": data.get("city", {}).get("country"),  # Pays
            "horodatage": data.get("list", [{}])[0].get("dt"),  # Timestamp brut
            "temps_formaté": datetime.utcfromtimestamp(data.get("list", [{}])[0].get("dt")).strftime('%Y-%m-%d %H:%M:%S'),  # Temps formaté
            "température": data.get("list", [{}])[0].get("main", {}).get("temp"),  # Température
            "température_ressentie": data.get("list", [{}])[0].get("main", {}).get("feels_like"),  # Température ressentie
            "température_minimale": data.get("list", [{}])[0].get("main", {}).get("temp_min"),  # Température minimale
            "température_maximale": data.get("list", [{}])[0].get("main", {}).get("temp_max"),  # Température maximale
            "pression": data.get("list", [{}])[0].get("main", {}).get("pressure"),  # Pression atmosphérique
            "humidité": data.get("list", [{}])[0].get("main", {}).get("humidity"),  # Humidité
            "description_météo": data.get("list", [{}])[0].get("weather", [{}])[0].get("description"),  # Description météo
            "icône_météo": data.get("list", [{}])[0].get("weather", [{}])[0].get("icon"),  # Icône météo
            "vitesse_vent": data.get("list", [{}])[0].get("wind", {}).get("speed"),  # Vitesse du vent
            "direction_vent": data.get("list", [{}])[0].get("wind", {}).get("deg"),  # Direction du vent
            "couverture_nuageuse": data.get("list", [{}])[0].get("clouds", {}).get("all"),  # Couverture nuageuse
            "visibilité": data.get("list", [{}])[0].get("visibility"),  # Visibilité
            "précipitations": data.get("list", [{}])[0].get("rain", {}).get("3h", 0),  # Précipitations sur 3 heures
            "neige": data.get("list", [{}])[0].get("snow", {}).get("3h", 0)  # Neige sur 3 heures
        }


        # Insérer dans MongoDB
        mongo_collection.insert_one(processed_data)
        print("Données insérées dans MongoDB avec succès.")
    except Exception as e:
        print(f"Erreur lors du traitement ou de l'insertion des données : {e}")

if __name__ == '__main__':
    print("Démarrage du consommateur Kafka...")
    try:
        for message in consumer:
            print("Message reçu de Kafka.")
            process_weather_data(message.value)
    except KeyboardInterrupt:
        print("Consommateur Kafka arrêté.")