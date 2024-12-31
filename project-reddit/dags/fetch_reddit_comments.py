from airflow import DAG
from airflow.operators.python import PythonOperator
from kafka import KafkaProducer
import requests
import os
import json
from dotenv import load_dotenv
from datetime import datetime
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

# Informations nécessaires
ACCESS_TOKEN = os.getenv('REDDIT_ACCESS_TOKEN')  # Utiliser une variable plus descriptive
USER_AGENT = 'my-example-app (by /u/Fantastic_Solid7943)'

KAFKA_SERVER = os.getenv('KAFKA_SERVER', 'kafka:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'reddit_comments')
POST_ID = os.getenv('REDDIT_POST_ID', '1hpbrbh/are_moroccans_racist/') # ID du post dans une variable d'environnement

if not ACCESS_TOKEN:
    raise ValueError("REDDIT_ACCESS_TOKEN est manquant dans les variables d'environnement.")
if not KAFKA_SERVER or not KAFKA_TOPIC:
    raise ValueError("KAFKA_SERVER et KAFKA_TOPIC doivent être définis dans les variables d'environnement.")
if not POST_ID:
    raise ValueError("REDDIT_POST_ID doit être défini dans les variables d'environnement.")


# Default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
}

# Définir le DAG
with DAG(
    'fetch_reddit_comments',
    default_args=default_args,
    description="Un DAG pour récupérer les commentaires d'un post Reddit et les envoyer dans Kafka",
    schedule_interval='@daily',
    start_date=datetime(2024, 12, 31),
    catchup=False,
) as dag:

    # Fonction pour récupérer les commentaires et les envoyer à Kafka
    def fetch_and_publish_comments(**context):
        COMMENTS_URL = f'https://oauth.reddit.com/comments/{POST_ID}'

        headers = {
            'Authorization': f'Bearer {ACCESS_TOKEN}',
            'User-Agent': USER_AGENT
        }

        try:
            response = requests.get(COMMENTS_URL, headers=headers)
            response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP (4xx ou 5xx)
            comments = response.json()

            # Configuration du producteur Kafka à l'intérieur de la tâche
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_SERVER,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )

            for comment in comments[1]['data']['children']:
                if comment['kind'] == 't1':
                    comment_data = {
                        'author': comment['data']['author'],
                        'body': comment['data']['body'],
                        'created_utc': comment['data']['created_utc'],  # Ajout du timestamp
                        'permalink': comment['data']['permalink'], # Ajout du lien permanent
                        'id': comment['data']['id'] # Ajout de l'id
                    }
                    producer.send(KAFKA_TOPIC, value=comment_data)
                    logger.info(f"Commentaire envoyé à Kafka : {comment_data}") # Utilisation du logger

            producer.flush() # Assure que tous les messages sont envoyés
            producer.close()
            logger.info("Envoi des commentaires vers Kafka terminé.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la requête Reddit : {e}")
            if response is not None :
                try:
                    logger.error(f"Contenu de l'erreur : {response.json()}")
                except ValueError :
                    logger.error("La réponse n'est pas au format JSON")
        except json.JSONDecodeError as e:
            logger.error(f"Erreur lors du décodage JSON : {e}. Contenu de la réponse : {response.text}") # Affiche le contenu de la réponse pour le debug
        except Exception as e: # Catch les autres exceptions
            logger.error(f"Une erreur inattendue s'est produite : {e}")

    # Définir la tâche dans le DAG
    fetch_comments_task = PythonOperator(
        task_id='fetch_data_and_push_to_kafka',
        python_callable=fetch_and_publish_comments,
    )