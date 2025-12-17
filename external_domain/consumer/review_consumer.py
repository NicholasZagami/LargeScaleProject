from cassandra.cluster import Cluster
from base_consumer import BaseConsumer
import config

# Connessione a Cassandra
print("Connecting to Cassandra...")

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

reviews_table_query = """
    CREATE TABLE IF NOT EXISTS reviews (
        rec_id bigint,
        author_id bigint,
        appid bigint,
        playtime_forever bigint,
        playtime_at_review bigint,
        num_reviews bigint,
        last_played bigint,
        language text,
        review text,
        voted_up boolean,
        votes_up bigint,
        votes_funny bigint,
        received_for_free boolean,
        written_during_early_access boolean,
        sent_compound float,
        sentiment_0_10 float,
        sentiment_0_10_round int,
        updated_at timestamp,
        PRIMARY KEY (rec_id)
    )
"""

session.execute(reviews_table_query)
print(f"Table 'review' created/verified")
print(f"Connected to Cassandra: {config.CASSANDRA_KEYSPACE}.review\n")

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
    cassandra_session=session)
