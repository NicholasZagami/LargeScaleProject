import logging as log
import os
from datetime import datetime
from typing import Optional

import polars as pl
from cassandra.cluster import Cluster
from prefect import flow
from prefect.logging import get_run_logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from dwh_domain.model.dwh_model import Game
from dwh_domain.service.db_service import DwhRepository
from dwh_domain.tasks.extract import (
    extract_from_mongodb,
    extract_from_cassandra,
    extract_from_minio,
    add_to_failed_reviews_queue,
    get_failed_reviews_ready_for_retry,
    remove_from_failed_reviews_queue,
    get_pending_extraction_dates,
    register_pipeline_run,
    mark_pipeline_run_completed,
    mark_pipeline_run_failed
)
from dwh_domain.tasks.load import load_to_minio
from dwh_domain.tasks.transform import Transform
from dwh_domain.utils.file_writer import write_parquet_file, generate_run_id
from dwh_domain.utils.schemas import MONGO_GAME_SCHEMA, CASSANDRA_REVIEW_SCHEMA

log.basicConfig(level=log.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

@flow(name="etl_pipeline")
def etl_pipeline(extraction_date: Optional[str] = None):
    """
    Main ETL pipeline flow.

    Processes pending/failed dates first (oldest to newest), then today's date.
    File names use the actual extraction_date being processed.

    Args:
        extraction_date: Date to extract data (format: YYYY-MM-DD).
                        If None, uses current date.
    """
    # Default to current date if not provided
    if extraction_date is None:
        extraction_date = datetime.now().strftime('%Y-%m-%d')

    log.info(f"ETL pipeline started with target date: {extraction_date}")

    # First, process any failed reviews that are ready for retry
    try:
        process_failed_reviews_queue(extraction_date)
    except Exception as e:
        log.warning(f"Failed to process failed reviews queue: {e}")
        # Continue with main pipeline even if queue processing fails

    # Get any pending/failed dates that need to be processed before today
    pending_dates = get_pending_extraction_dates(extraction_date)

    # Build list of all dates to process: pending dates + today's date
    dates_to_process = pending_dates + [extraction_date]

    log.info(f"Dates to process: {dates_to_process}")

    # Process each date
    for date in dates_to_process:
        log.info(f"Processing extraction date: {date}")
        run_etl_for_date(date)


@flow(name="run_etl_for_date")
def run_etl_for_date(extraction_date: str):
    """
    Run the ETL pipeline for a specific extraction date.
    Tracks the run status in pipeline_run table.

    Args:
        extraction_date: Date to extract data (format: YYYY-MM-DD)
    """
    # Register this run as 'running'
    register_pipeline_run(extraction_date)

    try:
        # Extraction phase
        mongo_filename, mongo_file_path, cassandra_filename, cassandra_file_path = extract_data(extraction_date)

        # Transformation phase
        file_path_to_remove, transformed_game_filename, transformed_review_filename, transformed_date_filename, bridge_genre_filename, bridge_category_filename, bridge_publisher_filename = transform_data(
            mongo_filename, cassandra_filename)

        # Load phase with retry handling
        load_data(transformed_game_filename, transformed_review_filename, transformed_date_filename, bridge_genre_filename, bridge_category_filename, bridge_publisher_filename)

        log.info(f"ETL pipeline for {extraction_date} completed successfully.")

        # Mark as completed
        mark_pipeline_run_completed(extraction_date)

        log.info("Cleaning up temporary files...")

        file_path_to_remove.append(mongo_file_path)
        file_path_to_remove.append(cassandra_file_path)

        for file in file_path_to_remove:
            if os.path.exists(file):
                os.remove(file)

        log.info(f"{len(file_path_to_remove)} files removed.")

        extracted_dir = os.path.dirname(mongo_file_path)
        transformed_dir = os.path.dirname(file_path_to_remove[0])
        if os.path.exists(transformed_dir) and not os.listdir(transformed_dir):
            os.rmdir(transformed_dir)

        if os.path.exists(extracted_dir) and not os.listdir(extracted_dir):
            os.rmdir(extracted_dir)

        log.info(f"{extracted_dir} and {transformed_dir} path deleted.")

    except Exception as e:
        error_msg = str(e)
        log.warning(f"Pipeline failed for {extraction_date}. Error: {error_msg}")

        # Mark as failed
        mark_pipeline_run_failed(extraction_date, error_msg)

        log.warning("Adding reviews to failed_reviews queue for later retry...")

        try:
            # Read the review dataframe to get the review IDs that failed
            review_downloaded_file_path = extract_from_minio("transformed-files", transformed_review_filename)
            review_df = pl.read_parquet(review_downloaded_file_path)

            # Add to failed reviews queue instead of modifying updated_at
            add_to_failed_reviews_queue(
                review_df,
                error_message=f"Pipeline failure for {extraction_date}: {error_msg}"
            )
            log.info("Reviews added to failed_reviews queue. They will be retried in future runs.")
        except Exception as queue_error:
            log.error(f"Failed to add reviews to failed queue: {queue_error}")
            # Don't re-raise, the date is already marked as failed

@flow(name="extract_data", retries=3, retry_delay_seconds=5)
def extract_data(extraction_date: str):
    log.info(f"Extraction phase started for date: {extraction_date}")

    try:
        run_id = generate_run_id()
        mongo_data = extract_from_mongodb(extraction_date=extraction_date)
        cassandra_data = extract_from_cassandra(extraction_date=extraction_date)

        mongo_run_id = "GAMES_" + run_id
        cassandra_run_id = "REVIEWS_" + run_id

        print(f"Extracted {len(mongo_data)} records from MongoDB.")
        print(f"Extracted {len(cassandra_data)} records from Cassandra.")

        # Create file and return the path to find the file
        # Pass schema to handle empty data gracefully
        mongo_file_path, mongo_filename = write_parquet_file(
            mongo_data,
            run_id=mongo_run_id,
            extraction_date=extraction_date,
            schema=MONGO_GAME_SCHEMA if not mongo_data else None
        )
        cassandra_file_path, cassandra_filename = write_parquet_file(
            cassandra_data,
            run_id=cassandra_run_id,
            extraction_date=extraction_date,
            schema=CASSANDRA_REVIEW_SCHEMA if not cassandra_data else None
        )

        # Load the file to MinIO staging area
        load_to_minio(mongo_filename, mongo_file_path, "ingested-files")
        load_to_minio(cassandra_filename, cassandra_file_path, "ingested-files")

        return mongo_filename, mongo_file_path, cassandra_filename, cassandra_file_path

    except Exception as e:
        log.error(f"Error while extracting data due to: {e}")
    finally:
        log.info("Extraction phase completed...")


@flow(name="transform_data", retries=3, retry_delay_seconds=5)
def transform_data(mongo_filename: str, cassandra_filename: str):
    log.info("Transform phase started...")
    transform = Transform()

    try:
        # Extract from MinIO and read into DataFrame
        game_downloaded_file_path = extract_from_minio("ingested-files", mongo_filename)
        review_downloaded_file_path = extract_from_minio("ingested-files", cassandra_filename)
        game_df = pl.read_parquet(game_downloaded_file_path)
        review_df = pl.read_parquet(review_downloaded_file_path)

        log.info(f"Loaded game DataFrame with {len(game_df)} rows and {len(game_df.columns)} columns")
        log.info(f"Loaded review DataFrame with {len(review_df)} rows and {len(review_df.columns)} columns")

        # Apply transformations
        review_df = transform.unix_timestamp_to_datetime(review_df, 'last_played')
        date_df, review_final = transform.extract_unique_dates_df_from_review_df(review_df)
        filtered_game_df = transform.filter_unique_games(game_df)
        game_genre_df = transform.explode_array_list_column(filtered_game_df, 'appid', 'genres')
        game_categories_df = transform.explode_array_list_column(filtered_game_df, 'appid', 'categories')
        game_publishers_df = transform.explode_array_list_column(filtered_game_df, 'appid', 'publishers')

        log.info(f"Transformed game DataFrame: {len(game_df)} rows")
        log.info(f"Transformed review DataFrame: {len(review_final)} rows")
        log.info(f"Date DataFrame: {len(date_df)} rows")
        log.info(f"Bridge dataframe (Game-Genre): {len(game_genre_df)} rows")
        log.info(f"Bridge dataframe (Game-Category): {len(game_categories_df)} rows")
        log.info(f"Bridge dataframe (Game-Publisher): {len(game_publishers_df)} rows")

        # Write transformed data to new parquet files
        transformed_game_filename = f"final_game_{mongo_filename}"
        transformed_review_filename = f"final_review_{cassandra_filename}"
        transformed_date_filename = f"final_date_{cassandra_filename}"
        bridge_genre_filename = f"bridge_genre_{mongo_filename}"
        bridge_category_filename = f"bridge_category_{mongo_filename}"
        bridge_publisher_filename = f"bridge_publisher_{mongo_filename}"

        # Create temporary directory for transformed files
        os.makedirs("tmp/transformed", exist_ok=True)
        transformed_game_path = f"tmp/transformed/{transformed_game_filename}"
        transformed_review_path = f"tmp/transformed/{transformed_review_filename}"
        transformed_date_path = f"tmp/transformed/{transformed_date_filename}"
        bridge_genre_path = f"tmp/transformed/{bridge_genre_filename}"
        bridge_category_path = f"tmp/transformed/{bridge_category_filename}"
        bridge_publisher_path = f"tmp/transformed/{bridge_publisher_filename}"

        file_path_to_remove = [transformed_game_path, transformed_review_path, transformed_date_path, bridge_genre_path, bridge_category_path, bridge_publisher_path]

        # Save transformed DataFrames
        filtered_game_df.write_parquet(transformed_game_path)
        review_final.write_parquet(transformed_review_path)
        date_df.write_parquet(transformed_date_path)
        game_genre_df.write_parquet(bridge_genre_path)
        game_categories_df.write_parquet(bridge_category_path)
        game_publishers_df.write_parquet(bridge_publisher_path)

        # Load transformed files to MinIO
        load_to_minio(transformed_game_filename, transformed_game_path, "transformed-files")
        load_to_minio(transformed_review_filename, transformed_review_path, "transformed-files")
        load_to_minio(transformed_date_filename, transformed_date_path, "transformed-files")
        load_to_minio(bridge_genre_filename, bridge_genre_path, "transformed-files")
        load_to_minio(bridge_category_filename, bridge_category_path, "transformed-files")
        load_to_minio(bridge_publisher_filename, bridge_publisher_path, "transformed-files")

        return file_path_to_remove, transformed_game_filename, transformed_review_filename, transformed_date_filename, bridge_genre_filename, bridge_category_filename, bridge_publisher_filename
    except Exception as e:
        log.error(f"Error while transforming data due to: {e}")
    finally:
        log.info("Data transform phase completed...")

@flow(name="load_data", retries=3, retry_delay_seconds=5)
def load_data(transformed_game_filename: str, transformed_review_filename: str, transformed_date_filename:str, bridge_genre_filename: str, bridge_category_filename: str, bridge_publisher_filename: str):
    log.info("Load phase started...")
    repository = DwhRepository()
    engine = create_engine(config.POSTGRES_CONNECTION_STRING)

    try:
        game_downloaded_file_path = extract_from_minio("transformed-files", transformed_game_filename)
        review_downloaded_file_path = extract_from_minio("transformed-files", transformed_review_filename)
        date_downloaded_file_path = extract_from_minio("transformed-files", transformed_date_filename)
        game_genre_downloaded_file_path = extract_from_minio("transformed-files", bridge_genre_filename)
        game_category_downloaded_file_path = extract_from_minio("transformed-files", bridge_category_filename)
        game_publisher_downloaded_file_path = extract_from_minio("transformed-files", bridge_publisher_filename)
        game_df = pl.read_parquet(game_downloaded_file_path)
        review_df = pl.read_parquet(review_downloaded_file_path)
        date_df = pl.read_parquet(date_downloaded_file_path)
        genre_bridge_df = pl.read_parquet(game_genre_downloaded_file_path)
        category_bridge_df = pl.read_parquet(game_category_downloaded_file_path)
        publisher_bridge_df = pl.read_parquet(game_publisher_downloaded_file_path)

        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            repository.extract_and_update_fixed_item_tables(session, game_df, 'genres', 'dwh.Genre')
            repository.extract_and_update_fixed_item_tables(session, game_df, 'categories', 'dwh.Category')
            repository.extract_and_update_fixed_item_tables(session, game_df, 'publishers', 'dwh.Publisher')
            session.commit()

            batch_size = 30000 #parametro configurabile
            repository.bulk_insert_games_and_bridge(session, game_df, genre_bridge_df, category_bridge_df, publisher_bridge_df, batch_size)
            repository.bulk_insert_user_table(session, review_df, batch_size)
            repository.bulk_insert_date_table(session, date_df, batch_size)
            repository.bulk_insert_review(session, review_df, batch_size)
        except Exception as e:
            session.rollback()
            log.error(f"Error during data loading: {e}")
            raise  # Re-raise to trigger Prefect retry
        finally:
            session.close()
    except Exception as e:
        log.error(f"Error while loading data due to: {e}")
        raise  # Re-raise to trigger Prefect retry mechanism
    finally:
        log.info("Load phase completed.")


@flow(name="process_failed_reviews_queue")
def process_failed_reviews_queue(extraction_date: str = None):
    """
    Process reviews from the failed_review queue (PostgreSQL) that are ready for retry.
    This flow retrieves the full review data from Cassandra and attempts
    to load them into the DWH.

    Args:
        extraction_date: Reference date for retry eligibility check (format: YYYY-MM-DD).
                        If None, uses current system time.
    """
    logger = get_run_logger()
    logger.info("Checking failed_review queue for reviews ready to retry...")

    # Get failed reviews ready for retry, using extraction_date as reference
    failed_reviews_df = get_failed_reviews_ready_for_retry(max_failures=10, reference_date=extraction_date)

    if len(failed_reviews_df) == 0:
        logger.info("No failed reviews ready for retry")
        return

    logger.info(f"Found {len(failed_reviews_df)} reviews to retry")

    # Get the full review data from Cassandra
    cluster = Cluster(
        contact_points=[config.CASSANDRA_HOST],
        port=config.CASSANDRA_PORT
    )
    cassandra_session = cluster.connect(config.CASSANDRA_KEYSPACE)

    try:
        rec_ids = failed_reviews_df['rec_id'].to_list()

        # Fetch full review data
        query = cassandra_session.prepare("""
            SELECT rec_id, author_id, appid, playtime_forever, playtime_at_review,
                   num_reviews, last_played, language, review, voted_up,
                   votes_up, votes_funny, received_for_free, written_during_early_access,
                   sent_compound, sentiment_0_10, sentiment_0_10_round, updated_at
            FROM reviews WHERE rec_id = ?
        """)

        reviews_data = []
        for rec_id in rec_ids:
            result = cassandra_session.execute(query, (int(rec_id),)).one()
            if result:
                reviews_data.append({
                    'rec_id': result.rec_id,
                    'author_id': result.author_id,
                    'appid': result.appid,
                    'playtime_forever': result.playtime_forever,
                    'playtime_at_review': result.playtime_at_review,
                    'num_reviews': result.num_reviews,
                    'last_played': result.last_played,
                    'language': result.language,
                    'review': result.review,
                    'voted_up': result.voted_up,
                    'votes_up': result.votes_up,
                    'votes_funny': result.votes_funny,
                    'received_for_free': result.received_for_free,
                    'written_during_early_access': result.written_during_early_access,
                    'sent_compound': result.sent_compound,
                    'sentiment_0_10': result.sentiment_0_10,
                    'sentiment_0_10_round': result.sentiment_0_10_round,
                    'updated_at': result.updated_at,
                })

        if not reviews_data:
            logger.warning("No review data found in Cassandra for failed reviews")
            return

        review_df = pl.DataFrame(reviews_data, schema=CASSANDRA_REVIEW_SCHEMA)

    finally:
        cluster.shutdown()

    # Transform the review data (same as normal pipeline)
    transform = Transform()
    review_df = transform.unix_timestamp_to_datetime(review_df, 'last_played')
    date_df, review_final = transform.extract_unique_dates_df_from_review_df(review_df)

    # Attempt to load into DWH
    repository = DwhRepository()
    engine = create_engine(config.POSTGRES_CONNECTION_STRING)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Insert user and dates
        repository.bulk_insert_date_table(session, date_df, batch_size=30000)
        repository.bulk_insert_user_table(session, review_final, batch_size=30000)

        # Track which reviews can be successfully processed (game exists)
        existing_games = {str(game.ID_game) for game in session.query(Game.ID_game).all()}

        successfully_processed = []
        still_failing = []

        for row in review_final.iter_rows(named=True):
            rec_id = str(row.get('rec_id'))
            game_id = str(row.get('appid'))

            if game_id in existing_games:
                successfully_processed.append(rec_id)
            else:
                still_failing.append(rec_id)

        if successfully_processed:
            # Insert only the reviews that can now be processed
            processable_df = review_final.filter(
                pl.col('rec_id').cast(str).is_in(successfully_processed)
            )
            repository.bulk_insert_review(session, processable_df, batch_size=30000)

            # Remove successfully processed reviews from the failed queue
            remove_from_failed_reviews_queue(successfully_processed)
            logger.info(f"Successfully processed {len(successfully_processed)} previously failed reviews")

        if still_failing:
            logger.info(f"{len(still_failing)} reviews still cannot be processed (games still missing)")
            # Increment failure count for reviews that still can't be processed
            still_failing_df = review_final.filter(
                pl.col('rec_id').cast(str).is_in(still_failing)
            )
            add_to_failed_reviews_queue(
                still_failing_df,
                error_message="Game still missing in DWH during retry"
            )

        session.commit()

    except Exception as e:
        session.rollback()
        logger.error(f"Error processing failed reviews queue: {e}")
        # Re-queue all reviews with updated failure count
        add_to_failed_reviews_queue(
            review_final,
            error_message=f"Retry failed: {str(e)}"
        )
        raise
    finally:
        session.close()