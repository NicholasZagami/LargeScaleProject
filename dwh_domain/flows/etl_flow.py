import os
import polars as pl

from prefect import flow
from sqlalchemy import create_engine

import config
from dwh_domain.tasks.extract import (extract_from_mongodb, extract_from_cassandra, extract_from_minio, extract_and_update_fixed_item_tables, bulk_insert_all_data)
from dwh_domain.utils.file_writer import write_parquet_file
from dwh_domain.tasks.load import load_to_minio

@flow(name="etl_pipeline")
def etl_pipeline():
    print("ETL pipeline started...")

    mongo_data = extract_from_mongodb(extraction_date='2025-12-14')
    cassandra_data = extract_from_cassandra(extraction_date='2025-12-17')

    print(f"Extracted {len(mongo_data)} records from MongoDB.")
    print(f"Extracted {len(cassandra_data)} records from Cassandra.")

    # Create file and return the path to find the file
    mongo_file_path, mongo_filename = write_parquet_file(mongo_data, run_id='001', extraction_date='2025-12-14')
    cassandra_file_path, cassandra_filename = write_parquet_file(cassandra_data, run_id='001', extraction_date='2025-12-17')

    # Load the file to MinIO staging area
    load_to_minio(mongo_filename, mongo_file_path)
    load_to_minio(cassandra_filename, cassandra_file_path)

    # Clean up temporary file after the successful load
    #os.remove(mongo_file_path)
    #os.rmdir(os.path.dirname(mongo_file_path))

    # Extract from MinIO and read into DataFrame
    game_downloaded_file_path = extract_from_minio("ingested-files", mongo_filename)
    game_df = pl.read_parquet(game_downloaded_file_path)
    review_downloaded_file_path = extract_from_minio("ingested-files", cassandra_filename)
    review_df = pl.read_parquet(review_downloaded_file_path)

    print(f"Loaded DataFrame with {len(game_df)} rows and {len(game_df.columns)} columns")
    print(f"Loaded DataFrame with {len(review_df)} rows and {len(review_df.columns)} columns")

    engine = create_engine(config.POSTGRES_CONNECTION_STRING)
    with engine.connect() as conn:
        extract_and_update_fixed_item_tables(conn, game_df,  'genres', 'Genre')
        extract_and_update_fixed_item_tables(conn, game_df, 'categories', 'Category')
        extract_and_update_fixed_item_tables(conn, game_df, 'publishers', 'Publisher')
        conn.commit()

    bulk_insert_all_data(game_df, review_df)

    print("ETL pipeline completed.")
