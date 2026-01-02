import polars as pl
from prefect import task


class Transform:
    def __init__(self):
        pass

    @staticmethod
    @task(name="convert_unix_timestamp_to_datetime")
    def unix_timestamp_to_datetime(df: pl.DataFrame, column: str):
        # Convert Unix timestamp to datetime if needed
        return df.with_columns([
            # TODO: capire se serve, se no togliere
            pl.when(pl.col(column).is_not_null() & (pl.col(column) > 0))
            .then(pl.from_epoch(column, time_unit='s'))
            .otherwise(None)
            .alias(column)
        ])

    @staticmethod
    @task(name="explode_array_list_column")
    def explode_array_list_column(df: pl.DataFrame, unique_column:str, column_to_explode: str):
        """
        Explode array list column like [val1, val2, val3] to single line
        in order to process it on the db

        Args:
            df: dataframe
            unique_column: column that contains the unique value that will be exploded in more than one
                           occurrence (example: game id)
            column_to_explode: column to explode
        """

        return (df.select([unique_column, column_to_explode])
                .explode(column_to_explode)
                .drop_nulls())