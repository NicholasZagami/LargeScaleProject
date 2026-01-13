"""
Prefect deployment script for ETL pipeline.

This script creates a deployment with scheduling capabilities.
"""
from dwh_domain.flows.etl_flow import etl_pipeline

if __name__ == "__main__":
    # Etl deployment - Run daily at 2:00 AM
    # The pipeline will use current date by default when extraction_date is not provided
    etl_pipeline.serve(
        name="etl-pipeline-daily",
        tags=["etl"],
        cron="0 2 * * *"  # Run daily at 2:00 AM (adjust for your timezone)
    )
