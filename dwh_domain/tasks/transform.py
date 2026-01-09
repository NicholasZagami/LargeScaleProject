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

    @staticmethod
    @task(name="filter_unique_games")
    def filter_unique_games(df: pl.DataFrame):
        """
        For unique appids the data provide the same game sometimes.
        :param df: dataframe
        :param subset_column: column used to filter the unique games
        :return: filtered dataframe
        """
        return df.select(df.columns).unique(subset=['name'], keep='first')

    @staticmethod
    def _create_date_id(date_col: str) -> pl.Expr:
        """
        Create a date ID in format YYYYMMDD from a datetime column.

        Args:
            date_col: name of the datetime column

        Returns:
            Polars expression for the date ID
        """
        return (
            pl.col(date_col).dt.year().cast(pl.Utf8) +
            pl.col(date_col).dt.month().cast(pl.Utf8).str.zfill(2) +
            pl.col(date_col).dt.day().cast(pl.Utf8).str.zfill(2)
        )

    @staticmethod
    @task(name="extract_unique_dates_df_from_review_df")
    def extract_unique_dates_df_from_review_df(review_df: pl.DataFrame):
        # Extract unique dates with year, month, day components and ID
        unique_dates_df = (
            review_df
            .select('updated_at')
            .unique()
            .drop_nulls()
            .with_columns([
                pl.col('updated_at').dt.year().alias('year'),
                pl.col('updated_at').dt.month().alias('month'),
                pl.col('updated_at').dt.day().alias('day'),
                Transform._create_date_id('updated_at').alias('date_id')
            ])
            .select(['date_id', 'year', 'month', 'day'])
            .unique()
        )

        # Add date ID to review dataframe and drop the original timestamp
        review_df = (
            review_df
            .with_columns(Transform._create_date_id('updated_at').alias('date_id'))
            .drop('updated_at')
        )

        return unique_dates_df, review_df
