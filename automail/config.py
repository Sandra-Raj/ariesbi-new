# config.py
# import mysql.connector

# db = mysql.connector.connect(
#     host="192.168.41.3",
#     user="erp_country",
#     password="ariesbi",
#     database="countryanalysis"
# )
# cursor = db.cursor()


# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',       # Default phpMyAdmin user
    'password': '',       # Default is empty for local XAMPP/WAMP
    'database': 'countryanalysis'
}

# Email Configuration
EMAIL_CONFIG = {
    'sender_email': 'plssaveme784@gmail.com',
    'admin_email': 'plssaveme784@gmail.com',
    'password': "elga jwje zkfr lgwy",  # Use an App Password, not your login password
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587
}

API_IDLE_BASE_URL = "http://localhost:8000/listing/client-listings-idle"

IMAGE_PATH = "C:/xampp/htdocs/ariesbi/automail/images"

DATA_PATH = "C:/xampp/htdocs/ariesbi/ariesbi-analytics/data"
