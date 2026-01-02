import os
import polars as pl
import logging as log

from prefect import flow
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from dwh_domain.tasks.extract import (extract_from_mongodb, extract_from_cassandra, extract_from_minio)
from dwh_domain.utils.file_writer import write_parquet_file, generate_run_id
from dwh_domain.tasks.load import load_to_minio
from dwh_domain.tasks.transform import Transform
from dwh_domain.service.db_service import DwhRepository

log.basicConfig(level=log.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

@flow(name="etl_pipeline")
def etl_pipeline():
    log.info("ETL pipeline started...")

    # Extraction phase
    mongo_filename, mongo_file_path, cassandra_filename, cassandra_file_path = extract_data()

    # Transformation phase
    transformed_game_filename, transformed_review_filename, bridge_genre_filename, bridge_category_filename, bridge_publisher_filename = transform_data(mongo_filename, cassandra_filename)

    # Load phase
    load_data(transformed_game_filename, transformed_review_filename, bridge_genre_filename, bridge_category_filename, bridge_publisher_filename)

    # Clean up temporary file after the successful load
    #os.remove(mongo_file_path)
    #os.remove(mongo_file_path)
    #os.rmdir(os.path.dirname(cassandra_file_path))
    #os.rmdir(os.path.dirname(cassandra_file_path))

    log.info("ETL pipeline completed.")

@flow(name="extract_data")
def extract_data():
    log.info("Extraction phase started...")

    try:
        run_id = generate_run_id()
        mongo_data = extract_from_mongodb(extraction_date='2025-12-29')
        cassandra_data = extract_from_cassandra(extraction_date='2025-12-30')

        print(f"Extracted {len(mongo_data)} records from MongoDB.")
        print(f"Extracted {len(cassandra_data)} records from Cassandra.")

        # Create file and return the path to find the file
        mongo_file_path, mongo_filename = write_parquet_file(mongo_data, run_id=run_id, extraction_date='2025-12-29')
        cassandra_file_path, cassandra_filename = write_parquet_file(cassandra_data, run_id=run_id, extraction_date='2025-12-30')

        # Load the file to MinIO staging area
        load_to_minio(mongo_filename, mongo_file_path, "ingested-files")
        load_to_minio(cassandra_filename, cassandra_file_path, "ingested-files")

        return mongo_filename, mongo_file_path, cassandra_filename, cassandra_file_path

    except Exception as e:
        log.error(f"Error while extracting data due to: {e}")
    finally:
        log.info("Extraction phase completed...")


@flow(name="transform_data")
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
        review_final = transform.unix_timestamp_to_datetime(review_df, 'last_played')
        game_genre_df = transform.explode_array_list_column(game_df, 'appid', 'genres')
        game_categories_df = transform.explode_array_list_column(game_df, 'appid', 'categories')
        game_publishers_df = transform.explode_array_list_column(game_df, 'appid', 'publishers')

        log.info(f"Transformed game DataFrame: {len(game_df)} rows")
        log.info(f"Transformed review DataFrame: {len(review_final)} rows")
        log.info(f"Bridge dataframe (Game-Genre): {len(game_genre_df)} rows")
        log.info(f"Bridge dataframe (Game-Category): {len(game_categories_df)} rows")
        log.info(f"Bridge dataframe (Game-Publisher): {len(game_publishers_df)} rows")

        # Write transformed data to new parquet files
        # Option 1: Generate new filenames with "transformed_" prefix
        transformed_game_filename = f"final_{mongo_filename}"
        transformed_review_filename = f"final_{cassandra_filename}"
        bridge_genre_filename = f"bridge_genre_{mongo_filename}"
        bridge_category_filename = f"bridge_category_{mongo_filename}"
        bridge_publisher_filename = f"bridge_publisher_{mongo_filename}"

        # Create temporary directory for transformed files
        os.makedirs("tmp/transformed", exist_ok=True)
        transformed_game_path = f"tmp/transformed/{transformed_game_filename}"
        transformed_review_path = f"tmp/transformed/{transformed_review_filename}"
        bridge_genre_path = f"tmp/transformed/{bridge_genre_filename}"
        bridge_category_path = f"tmp/transformed/{bridge_category_filename}"
        bridge_publisher_path = f"tmp/transformed/{bridge_publisher_filename}"

        # Save transformed DataFrames
        game_df.write_parquet(transformed_game_path)
        review_final.write_parquet(transformed_review_path)
        game_genre_df.write_parquet(bridge_genre_path)
        game_categories_df.write_parquet(bridge_category_path)
        game_publishers_df.write_parquet(bridge_publisher_path)

        # Load transformed files to MinIO
        load_to_minio(transformed_game_filename, transformed_game_path, "trasformed-files")
        load_to_minio(transformed_review_filename, transformed_review_path, "trasformed-files")
        load_to_minio(bridge_genre_filename, bridge_genre_path, "trasformed-files")
        load_to_minio(bridge_category_filename, bridge_category_path, "trasformed-files")
        load_to_minio(bridge_publisher_filename, bridge_publisher_path, "trasformed-files")

        return transformed_game_filename, transformed_review_filename, bridge_genre_filename, bridge_category_filename, bridge_publisher_filename
    except Exception as e:
        log.error(f"Error while transforming data due to: {e}")
    finally:
        log.info("Data transform phase completed...")

@flow(name="load_data")
def load_data(transformed_game_filename: str, transformed_review_filename: str, bridge_genre_filename: str, bridge_category_filename: str, bridge_publisher_filename: str):
    log.info("Load phase started...")
    repository = DwhRepository()
    engine = create_engine(config.POSTGRES_CONNECTION_STRING)

    try:
        game_downloaded_file_path = extract_from_minio("trasformed-files", transformed_game_filename)
        review_downloaded_file_path = extract_from_minio("trasformed-files", transformed_review_filename)
        game_genre_downloaded_file_path = extract_from_minio("trasformed-files", bridge_genre_filename)
        game_category_downloaded_file_path = extract_from_minio("trasformed-files", bridge_category_filename)
        game_publisher_downloaded_file_path = extract_from_minio("trasformed-files", bridge_publisher_filename)
        game_df = pl.read_parquet(game_downloaded_file_path)
        review_df = pl.read_parquet(review_downloaded_file_path)
        genre_bridge_df = pl.read_parquet(game_genre_downloaded_file_path)
        category_bridge_df = pl.read_parquet(game_category_downloaded_file_path)
        publisher_bridge_df = pl.read_parquet(game_publisher_downloaded_file_path)

        with engine.connect() as conn:
            repository.extract_and_update_fixed_item_tables(conn, game_df, 'genres', 'Genre')
            repository.extract_and_update_fixed_item_tables(conn, game_df, 'categories', 'Category')
            repository.extract_and_update_fixed_item_tables(conn, game_df, 'publishers', 'Publisher')
            conn.commit()

        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            repository.bulk_insert_games_and_bridge(session, game_df, genre_bridge_df, category_bridge_df, publisher_bridge_df)
            repository.bulk_insert_user_table(session, review_df)
            review_df_updated = repository.bulk_insert_date_table(session, review_df)
            repository.bulk_insert_review(session, review_df_updated)
        finally:
            session.close()
    except Exception as e:
        log.error(f"Error while loading data due to: {e}")
    finally:
        log.info("Load phase completed.")