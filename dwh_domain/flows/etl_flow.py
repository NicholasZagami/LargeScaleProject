import os
import polars as pl
import logging as log
from datetime import datetime, timedelta
from typing import Optional

from prefect import flow
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from dwh_domain.tasks.extract import (extract_from_mongodb, extract_from_cassandra, extract_from_minio, update_cassandra_reviews_date)
from dwh_domain.utils.file_writer import write_parquet_file, generate_run_id
from dwh_domain.utils.schemas import MONGO_GAME_SCHEMA, CASSANDRA_REVIEW_SCHEMA
from dwh_domain.tasks.load import load_to_minio
from dwh_domain.tasks.transform import Transform
from dwh_domain.service.db_service import DwhRepository

log.basicConfig(level=log.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

@flow(name="etl_pipeline")
def etl_pipeline(extraction_date: Optional[str] = None):
    """
    Main ETL pipeline flow.

    Args:
        extraction_date: Date to extract data (format: YYYY-MM-DD).
                        If None, uses current date.
    """
    # Default to current date if not provided
    if extraction_date is None:
        extraction_date = datetime.now().strftime('%Y-%m-%d')

    log.info(f"ETL pipeline started with extraction date: {extraction_date}")

    try:
        # Extraction phase
        mongo_filename, mongo_file_path, cassandra_filename, cassandra_file_path = extract_data(extraction_date)

        # Transformation phase
        file_path_to_remove, transformed_game_filename, transformed_review_filename, transformed_date_filename, bridge_genre_filename, bridge_category_filename, bridge_publisher_filename = transform_data(
            mongo_filename, cassandra_filename)

        # Load phase with retry handling
        load_data(transformed_game_filename, transformed_review_filename, transformed_date_filename, bridge_genre_filename, bridge_category_filename, bridge_publisher_filename)

        log.info("ETL pipeline completed successfully.")

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
        # If all retries failed, postpone review processing
        log.warning(f"All retries exhausted. Error: {e}")
        log.warning("Postponing review processing by updating Cassandra updated_at field...")

        try:
            # Read the review dataframe to get the review IDs that failed
            review_downloaded_file_path = extract_from_minio("transformed-files", transformed_review_filename)
            review_df = pl.read_parquet(review_downloaded_file_path)

            # Update the updated_at field in Cassandra for these reviews
            update_cassandra_reviews_date(review_df, days_to_add=1)
            log.info("Reviews postponed by 1 day in Cassandra. They will be processed in the next run.")
        except Exception as postpone_error:
            log.error(f"Failed to postpone reviews: {postpone_error}")
            raise e  # Re-raise the original error

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