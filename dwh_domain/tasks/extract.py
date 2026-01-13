import logging as log
from datetime import datetime, timedelta

import polars as pl
from cassandra.cluster import Cluster
from minio import Minio
from prefect import task
from pymongo import MongoClient
from cassandra.query import BatchStatement
from cassandra import ConsistencyLevel

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


@task(name="update_cassandra_reviews_date")
def update_cassandra_reviews_date(review_df: pl.DataFrame, days_to_add: int = 1):
    """
    Update the updated_at field in Cassandra for reviews that failed to load due to missing games.
    This postpones their processing to a future run using batch operations for efficiency.

    Args:
        review_df: Polars DataFrame containing reviews with 'rec_id' column
        days_to_add: Number of days to add to the updated_at field (default: 1)
    """

    cluster = Cluster(
        contact_points=[config.CASSANDRA_HOST],
        port=config.CASSANDRA_PORT
    )

    session = cluster.connect(config.CASSANDRA_KEYSPACE)

    try:
        # Calculate the new timestamp (current time + days_to_add)
        # This assumes all reviews should be postponed to the same future date
        new_updated_at = datetime.now() + timedelta(days=days_to_add)

        # Prepare the update statement
        update_query = "UPDATE reviews SET updated_at = ? WHERE rec_id = ?"
        update_stmt = session.prepare(update_query)

        # Process in batches to avoid overwhelming Cassandra
        # Using smaller batch size to avoid "Batch too large" error
        batch_size = 50
        total_reviews = len(review_df)
        updated_count = 0
        failed_count = 0

        log.info(f"Postponing {total_reviews} reviews by {days_to_add} day(s) to {new_updated_at}...")

        for batch_start in range(0, total_reviews, batch_size):
            batch_end = min(batch_start + batch_size, total_reviews)
            batch_reviews = review_df[batch_start:batch_end]

            # Create a batch statement
            batch = BatchStatement(consistency_level=ConsistencyLevel.QUORUM)

            for row in batch_reviews.iter_rows(named=True):
                rec_id = row.get('rec_id')
                if rec_id:
                    try:
                        batch.add(update_stmt, (new_updated_at, rec_id))
                    except Exception as e:
                        log.error(f"Failed to add review {rec_id} to batch: {e}")
                        failed_count += 1

            # Execute the batch
            try:
                session.execute(batch)
                batch_count = batch_end - batch_start
                updated_count += batch_count
                log.info(f"Batch {batch_start // batch_size + 1}/{(total_reviews + batch_size - 1) // batch_size}: "
                        f"Updated {batch_count} reviews (Total: {updated_count}/{total_reviews})")
            except Exception as e:
                log.error(f"Failed to execute batch {batch_start // batch_size + 1}: {e}")
                failed_count += batch_end - batch_start

        log.info(f"✅ Successfully postponed {updated_count} reviews by {days_to_add} day(s)")
        if failed_count > 0:
            log.warning(f"⚠️  Failed to update {failed_count} reviews")

    except Exception as e:
        log.error(f"Error updating Cassandra reviews: {e}")
        raise
    finally:
        cluster.shutdown()