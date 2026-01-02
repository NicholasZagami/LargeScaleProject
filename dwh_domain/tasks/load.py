from minio import Minio
from prefect import task
import logging as log


@task(name="load_data_to_staging_area")
def load_to_minio(filename, file_path):
    try:
        client = Minio(
            "localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            secure=False
        )

        # TODO: add a config to give the bucket as a parameter
        client.fput_object("ingested-files", filename, file_path)
    except Exception as e:
        log.error(f"Upload failed due to: {e}")

@task(name="load_data_to_dwh")
def load_to_dwh():
    pass