from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.models import Variable
from kafka import KafkaProducer
from datetime import datetime, timedelta
import json
import requests
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'weather_topic')
KAFKA_SERVER = os.getenv('KAFKA_SERVER', 'localhost:9092')
API_CITY_IDS = os.getenv('API_CITY_IDS', '2538474,1053384,1850147').split(',')
API_URL = os.getenv('API_URL', 'http://api.openweathermap.org/data/2.5/forecast')
API_LANG = os.getenv('API_LANG', 'fr')
API_KEY = os.getenv('API_KEY', 'YOUR_API_KEY')
API_UNITS = os.getenv('API_UNITS', 'metric')
EMAIL_RECIPIENT = "your_email@example.com"
FETCH_INTERVAL = int(os.getenv('FETCH_INTERVAL', '10'))

# Default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# DAG Definition
with DAG(
    "weather_kafka_producer",
    default_args=default_args,
    description="Pipeline to fetch data, process via Kafka, and notify via email",
    schedule_interval=timedelta(seconds=FETCH_INTERVAL),
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:

    def fetch_and_publish_weather(**context):
        """Fetch weather data for a city and publish it to Kafka."""
        # Récupérer l'index courant depuis la Variable persistante
        current_index = Variable.get("current_city_index", default_var=0)
        current_index = int(current_index)

        city_id = API_CITY_IDS[current_index]
        try:
            # Appel API
            api_url = f"{API_URL}?id={city_id}&lang={API_LANG}&appid={API_KEY}&units={API_UNITS}"
            response = requests.get(api_url)
            response.raise_for_status()
            weather_data = response.json()

            # Envoi à Kafka
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_SERVER,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            producer.send(KAFKA_TOPIC, weather_data)
            producer.flush()

            print(f"Weather data for city ID {city_id} published to Kafka successfully.")

            # Mise à jour de l'index pour la prochaine exécution
            next_index = (current_index + 1) % len(API_CITY_IDS)
            Variable.set("current_city_index", next_index)

            # Sauvegarder le city_id dans XCom
            context['ti'].xcom_push(key='city_id', value=city_id)
        except Exception as e:
            print(f"Error processing city ID {city_id}: {e}")
            raise

    fetch_weather_task = PythonOperator(
        task_id="fetch_data_and_push_to_kafka",
        python_callable=fetch_and_publish_weather,
    )

    def build_email_content(**context):
        """Generate email content dynamically."""
        city_id = context['ti'].xcom_pull(key='city_id', task_ids='fetch_data_and_push_to_kafka')
        pipeline_start_time = context['execution_date']
        pipeline_end_time = context['dag_run'].end_date if context['dag_run'] else 'N/A'

        return f"""
        <html>
        <body>
            <h1>Weather Data Pipeline</h1>
            <p>The pipeline executed successfully!</p>
            <ul>
                <li><b>City ID Processed:</b> {city_id}</li>
                <li><b>Start Time:</b> {pipeline_start_time}</li>
                <li><b>End Time:</b> {pipeline_end_time}</li>
                <li><b>Kafka Topic:</b> {KAFKA_TOPIC}</li>
            </ul>
        </body>
        </html>
        """

    def send_email(**context):
        """Send the success email with the generated content."""
        email_content = build_email_content(**context)
        email_operator = EmailOperator(
            task_id="send_success_email",
            to=EMAIL_RECIPIENT,
            subject="Weather Airflow Producer Pipeline Success",
            html_content=email_content,
        )
        email_operator.execute(context)

    email_task = PythonOperator(
        task_id="generate_and_send_email",
        python_callable=send_email,
    )

    # Task Dependencies
    fetch_weather_task >> email_task
