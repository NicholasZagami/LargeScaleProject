from datetime import datetime, timedelta

from cassandra.cluster import Cluster
from minio import Minio
from prefect import task
from pymongo import MongoClient


import config

"""
This class purpose is to extract data from local sources (MongoDB and Cassandra).
"""


@task(name="extract_mongodb")
def extract_from_mongodb(extraction_date):
    mongo_client = MongoClient(config.MONGO_CONNECTION_STRING)
    db = mongo_client[config.MONGO_DB_NAME]
    collection = db[config.MONGO_GAME_COLLECTION_NAME]

    target_date = datetime.strptime(extraction_date, '%Y-%m-%d')

    # Create date range for the entire day
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    # Query for records within the date range
    query = {
        'updated_at': {
            '$gte': start_of_day,
            '$lt': end_of_day
        }
    }

    return list(collection.find(query))


@task(name="extract_cassandra")
def extract_from_cassandra(extraction_date):
    cluster = Cluster(
        contact_points=[config.CASSANDRA_HOST],
        port=config.CASSANDRA_PORT
    )

    session = cluster.connect(config.CASSANDRA_KEYSPACE)

    target_date = datetime.strptime(extraction_date, '%Y-%m-%d')

    # Create date range for the entire day
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    query = """
        SELECT * FROM reviews
        WHERE updated_at >= %s AND updated_at < %s
        ALLOW FILTERING
    """

    # Execute query
    rows = session.execute(query, (start_of_day, end_of_day))

    # Convert to list
    results = list(rows)

    # Close connection
    cluster.shutdown()

    return results


@task(name="extract_from_minio")
def extract_from_minio(bucket_name, object_name):
    client = Minio(
        "localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )

    response = client.get_object(bucket_name, object_name, "./tmp/" + object_name)

    return response.data