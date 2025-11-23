import sys
import os

# Aggiungi la root del progetto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from consumer.consumer import BaseConsumer
import config

# Connect to MongoDB con connection string
print("Connecting to MongoDB...")
mongo_client = MongoClient(config.MONGO_CONNECTION_STRING)

# Get database and collection
db = mongo_client[config.MONGO_DB_NAME]
games_collection = db[config.MONGO_GAME_COLLECTION_NAME]

print(f"Connected to MongoDB: {config.MONGO_DB_NAME}.{config.MONGO_GAME_COLLECTION_NAME}")

print("\n=== Starting Games Consumer ===\n")
games_consumer = BaseConsumer(
    topic_name=config.KAFKA_GAMES_TOPIC_NAME,
    bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
    group_id=config.KAFKA_GAMES_GROUP_ID,
    auto_offset_reset='earliest'
)

# Start consuming
games_consumer.consume_messages(
    db_type="mongodb",
    mongo_collection=games_collection)
