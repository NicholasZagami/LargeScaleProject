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
from dwh_domain.service.db_service import DwhRepository

@flow(name="etl_pipeline")
def etl_pipeline():
    log.info("ETL pipeline started...")
    
    repository = DwhRepository()

    engine = create_engine(config.POSTGRES_CONNECTION_STRING)
    with engine.connect() as conn:
        repository.extract_and_update_fixed_item_tables(conn, game_df,  'genres', 'Genre')
        repository.extract_and_update_fixed_item_tables(conn, game_df, 'categories', 'Category')
        repository.extract_and_update_fixed_item_tables(conn, game_df, 'publishers', 'Publisher')
        conn.commit()

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        repository.bulk_insert_games_and_bridge(session, game_df)
        repository.bulk_insert_user_table(session, review_df)
        review_df_updated = repository.bulk_insert_date_table(session, review_df)
        repository.bulk_insert_review(session, review_df_updated)
    finally:
        session.close()

    log.info("ETL pipeline completed.")

@flow(name="extract_data")
def extract_data(extraction_date: str):
    log.info("Extraction phase started...")

    try:
        run_id = generate_run_id()
        mongo_data = extract_from_mongodb(extraction_date=extraction_date)
        cassandra_data = extract_from_cassandra(extraction_date=extraction_date)

        print(f"Extracted {len(mongo_data)} records from MongoDB.")
        print(f"Extracted {len(cassandra_data)} records from Cassandra.")

        # Create file and return the path to find the file
        mongo_file_path, mongo_filename = write_parquet_file(mongo_data, run_id=run_id, extraction_date=extraction_date)
        cassandra_file_path, cassandra_filename = write_parquet_file(cassandra_data, run_id=run_id, extraction_date=extraction_date)

        # Load the file to MinIO staging area
        load_to_minio(mongo_filename, mongo_file_path)
        load_to_minio(cassandra_filename, cassandra_file_path)

        # Clean up temporary file after the successful load
        os.remove(mongo_file_path)
        os.remove(mongo_file_path)
        os.rmdir(os.path.dirname(cassandra_file_path))
        os.rmdir(os.path.dirname(cassandra_file_path))

        return mongo_filename, cassandra_filename

    except Exception as e:
        log.error(f"Error while extracting data due to: {e}")
    finally:
        log.info("Extraction phase completed...")


@flow(name="transform_data")
def transform_data(mongo_filename: str, cassandra_filename: str):
    log.info("Transform phase started...")
    try:
        # Extract from MinIO and read into DataFrame
        game_downloaded_file_path = extract_from_minio("ingested-files", mongo_filename)
        game_df = pl.read_parquet(game_downloaded_file_path)
        review_downloaded_file_path = extract_from_minio("ingested-files", cassandra_filename)
        review_df = pl.read_parquet(review_downloaded_file_path)

        log.info(f"Loaded DataFrame with {len(game_df)} rows and {len(game_df.columns)} columns")
        log.info(f"Loaded DataFrame with {len(review_df)} rows and {len(review_df.columns)} columns")

    except Exception as e:
        log.error(f"Error while transforming data due to: {e}")
    finally:
        log.info("Data transform phase completed...")