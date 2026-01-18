import logging as log
from datetime import datetime, timedelta
from typing import List

import polars as pl
from cassandra.cluster import Cluster
from minio import Minio
from prefect import task
from pymongo import MongoClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from dwh_domain.model.dwh_model import FailedReview

log.basicConfig(level=log.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

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


@task(name="add_to_failed_reviews_queue")
def add_to_failed_reviews_queue(
    review_df: pl.DataFrame,
    error_message: str,
    base_retry_delay_days: int = 1
):
    """
    Add reviews to the failed_review queue in PostgreSQL (dwh schema).
    Uses exponential backoff based on failure_count.

    Args:
        review_df: Polars DataFrame containing reviews with 'rec_id', 'appid', 'updated_at' columns
        error_message: Description of why the reviews failed
        base_retry_delay_days: Base delay before retry (will be multiplied by 2^failure_count)
    """
    if len(review_df) == 0:
        log.info("No reviews to add to failed queue")
        return

    engine = create_engine(config.POSTGRES_CONNECTION_STRING)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        now = datetime.now()
        added_count = 0
        updated_count = 0
        total_reviews = len(review_df)

        log.info(f"Adding {total_reviews} reviews to failed_review queue in PostgreSQL...")

        for row in review_df.iter_rows(named=True):
            rec_id = row.get('rec_id')
            appid = row.get('appid')
            original_updated_at = row.get('updated_at')

            if rec_id is None:
                continue

            rec_id_str = str(rec_id)
            appid_str = str(appid) if appid else None

            # Check if already in queue
            existing = session.query(FailedReview).filter(
                FailedReview.rec_id == rec_id_str
            ).first()

            if existing:
                # Update existing entry with incremented failure count
                existing.failure_count += 1
                # Exponential backoff: 1, 2, 4, 8, 16, 32 days (capped)
                retry_delay = timedelta(days=base_retry_delay_days * (2 ** min(existing.failure_count - 1, 5)))
                existing.retry_after = now + retry_delay
                existing.last_error = error_message
                updated_count += 1
            else:
                # New entry
                retry_after = now + timedelta(days=base_retry_delay_days)
                failed_review = FailedReview(
                    rec_id=rec_id_str,
                    original_date=original_updated_at,
                    retry_after=retry_after,
                    failure_count=1,
                    last_error=error_message,
                    appid=appid_str,
                    created_at=now
                )
                session.add(failed_review)
                added_count += 1

        session.commit()
        log.info(f"Successfully added {added_count} new reviews and updated {updated_count} existing reviews in failed_review queue")

    except Exception as e:
        session.rollback()
        log.error(f"Error adding to failed_review queue: {e}")
        raise
    finally:
        session.close()


@task(name="get_failed_reviews_ready_for_retry")
def get_failed_reviews_ready_for_retry(max_failures: int = 10, reference_date: str = None) -> pl.DataFrame:
    """
    Get reviews from failed_review queue in PostgreSQL that are ready to be retried.

    Args:
        max_failures: Maximum failure count before giving up (default: 10)
        reference_date: Date to compare against retry_after (format: YYYY-MM-DD).
                       If None, uses current system time.

    Returns:
        Polars DataFrame with failed reviews ready for retry
    """
    engine = create_engine(config.POSTGRES_CONNECTION_STRING)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        if reference_date:
            # Parse the reference date and set to end of day for comparison
            check_time = datetime.strptime(reference_date, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            )
        else:
            check_time = datetime.now()

        log.info(f"Checking for failed reviews with retry_after <= {check_time}")

        # Query reviews ready for retry
        results = session.query(FailedReview).filter(
            FailedReview.retry_after <= check_time,
            FailedReview.failure_count < max_failures
        ).all()

        log.info(f"Found {len(results)} failed reviews ready for retry")

        if not results:
            return pl.DataFrame()

        # Convert to DataFrame
        data = {
            'rec_id': [r.rec_id for r in results],
            'original_date': [r.original_date for r in results],
            'appid': [r.appid for r in results],
            'failure_count': [r.failure_count for r in results],
            'last_error': [r.last_error for r in results],
            'created_at': [r.created_at for r in results],
        }

        print(data)
        return pl.DataFrame(data)

    except Exception as e:
        log.error(f"Error getting failed reviews: {e}")
        raise
    finally:
        session.close()


@task(name="remove_from_failed_reviews_queue")
def remove_from_failed_reviews_queue(rec_ids: List[str]):
    """
    Remove successfully processed reviews from the failed_review queue in PostgreSQL.

    Args:
        rec_ids: List of rec_id values to remove (as strings)
    """
    if not rec_ids:
        log.info("No reviews to remove from failed queue")
        return

    engine = create_engine(config.POSTGRES_CONNECTION_STRING)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        total = len(rec_ids)
        log.info(f"Removing {total} reviews from failed_review queue...")

        deleted_count = session.query(FailedReview).filter(
            FailedReview.rec_id.in_(rec_ids)
        ).delete(synchronize_session=False)

        session.commit()
        log.info(f"Successfully removed {deleted_count} reviews from failed_review queue")

    except Exception as e:
        session.rollback()
        log.error(f"Error removing from failed_review queue: {e}")
        raise
    finally:
        session.close()