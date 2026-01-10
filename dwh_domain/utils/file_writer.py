import os
import uuid

import polars as pl


def write_parquet_file(data, run_id, extraction_date, output_dir='./tmp/parquet', schema=None):
    """
    Giving the list of records extracted from the db produce a parquet file.
    :param data: data extracted from db
    :param run_id: id of the current flow run
    :param extraction_date: date of extraction
    :param output_dir: temporary directory where to save the parquet file (default: ./tmp/parquet)
    :param schema: optional Polars schema to use when data is empty
    :return: absolute path to the parquet file
    """
    # Create temporary output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Create full file path
    filename = f"{extraction_date}_{run_id}.parquet"
    filepath = os.path.join(output_dir, filename)

    processed_data = []
    for record in data:
        if '_id' in record:
            record['_id'] = str(record['_id'])
        processed_data.append(record)

    # Create DataFrame with schema if provided and data is empty
    if not processed_data and schema:
        df = pl.DataFrame(schema=schema)
    else:
        df = pl.DataFrame(processed_data)

    df.write_parquet(filepath, compression='snappy')

    # Get absolute path
    absolute_path = os.path.abspath(filepath)

    print(f"Parquet file created successfully: {absolute_path} ({len(df)} rows)")

    return absolute_path, filename

def generate_run_id():
    return str(uuid.uuid4())