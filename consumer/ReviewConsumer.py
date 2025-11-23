import os
import sys
from cassandra.cluster import Cluster
from consumer.consumer import BaseConsumer

# Aggiungi la root del progetto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Connect to MongoDB con connection string
print("Connecting to Cassandra...")
# Connessione a Cassandra
cluster = Cluster(
    contact_points=[config.CASSANDRA_HOST],
    port=config.CASSANDRA_PORT
)
session = cluster.connect()

# Crea Keyspace se non esiste
keyspace_query = f"""
    CREATE KEYSPACE IF NOT EXISTS {config.CASSANDRA_KEYSPACE}
    WITH replication = {{
        'class': 'SimpleStrategy',
        'replication_factor': 1
    }}
"""
session.execute(keyspace_query)
print(f"✓ Keyspace '{config.CASSANDRA_KEYSPACE}' created/verified")

# Usa il keyspace
session.set_keyspace(config.CASSANDRA_KEYSPACE)

games_table_query = """
    CREATE TABLE IF NOT EXISTS games (
        appid int PRIMARY KEY,
        name text,
        genre text,
        categories text,
        is_free boolean,
        price decimal
    )
"""
session.execute(games_table_query)
print(f"✓ Table 'review' created/verified")
print(f"✓ Connected to Cassandra: {config.CASSANDRA_KEYSPACE}.review\n")

print("\n=== Starting Review Consumer ===\n")
review_consumer = BaseConsumer(
    topic_name=config.KAFKA_REVIEW_TOPIC_NAME,
    bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
    group_id=config.KAFKA_REVIEW_GROUP_ID,
    auto_offset_reset='earliest'
)

# Start consuming
review_consumer.consume_messages(
    db_type="cassandra",
    mongo_collection=session)
