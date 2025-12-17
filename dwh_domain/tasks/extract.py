from datetime import datetime, timedelta

from cassandra.cluster import Cluster
from minio import Minio
from prefect import task
from pymongo import MongoClient
from sqlalchemy import create_engine, text
import polars as pl


import config

"""
This class purpose is to extract data from local sources (MongoDB and Cassandra).
"""


@task(name="extract_mongodb")
def extract_from_mongodb(extraction_date):
    mongo_client = MongoClient(config.MONGO_CONNECTION_STRING)
    db = mongo_client[config.MONGO_DB_NAME]
    collection = db[config.MONGO_GAME_COLLECTION_NAME]

    target_date = datetime.strptime(extraction_date, '%Y-%m-%d')

    # Create date range for the entire day
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    # Query for records within the date range
    query = {
        'updated_at': {
            '$gte': start_of_day,
            '$lt': end_of_day
        }
    }

    return list(collection.find(query))


@task(name="extract_cassandra")
def extract_from_cassandra(extraction_date):
    cluster = Cluster(
        contact_points=[config.CASSANDRA_HOST],
        port=config.CASSANDRA_PORT
    )

    session = cluster.connect(config.CASSANDRA_KEYSPACE)

    target_date = datetime.strptime(extraction_date, '%Y-%m-%d')

    # Create date range for the entire day
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    query = """
        SELECT * FROM reviews
        WHERE updated_at >= %s AND updated_at < %s
        ALLOW FILTERING
    """

    # Execute query
    rows = session.execute(query, (start_of_day, end_of_day))

    # Convert to list
    results = list(rows)

    # Close connection
    cluster.shutdown()

    return results


@task(name="extract_from_minio")
def extract_from_minio(bucket_name, object_name):
    client = Minio(
        "localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )

    response = client.get_object(bucket_name, object_name, "./tmp/" + object_name)

    return response.data


def extract_and_update_fixed_item_tables(conn, df, df_column, table_name):
    unique_values = df[df_column].explode().drop_nulls().unique().to_list()

    for value in unique_values:
        result = conn.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE name = :value"),
            {"value": value}
        )

        if result.scalar() == 0:
            conn.execute(
                text(f"INSERT INTO {table_name} (name) VALUES (:value)"),
                {"value": value}
            )

    print(f"Updated table '{table_name}' with unique values from column '{df_column}'.")


def bulk_insert_all_data(game_df: pl.DataFrame, review_df: pl.DataFrame):
    """
    Bulk insert all data (Games, Users, Dates, Reviews, and Bridge tables) using raw SQL
    for maximum performance.

    Args:
        game_df: Polars DataFrame with game information
        review_df: Polars DataFrame with review information
    """
    engine = create_engine(config.POSTGRES_CONNECTION_STRING)

    with engine.begin() as conn:  # auto-commit on success, rollback on error

        # ====================================
        # STEP 1: Bulk Insert Games
        # ====================================
        print("Bulk inserting games...")

        # Prepare unique games
        unique_games = game_df.select([
            'appid', 'name', 'price', 'review_score',
            'required_age', 'is_free'
        ]).unique()

        # Rename is_free to free_to_play for database
        unique_games = unique_games.rename({
            'is_free': 'free_to_play',
            'appid': 'ID_game'
        })

        # Convert to list of dicts for bulk insert
        games_data = unique_games.to_dicts()

        if games_data:
            # Bulk insert with ON CONFLICT DO NOTHING to skip duplicates
            conn.execute(text("""
                INSERT INTO Game (ID_game, name, review_score, required_age, free_to_play)
                VALUES (:ID_game, :name, :review_score, :required_age, :free_to_play)
                ON CONFLICT (ID_game) DO NOTHING
            """), games_data)

        print(f"Inserted {len(games_data)} games")

        # ====================================
        # STEP 2: Bulk Insert Users
        # ====================================
        print("Bulk inserting users...")

        # Prepare unique users from review_df
        unique_users = review_df.select([
            'playtime_at_review',
            'playtime_forever',
            'num_reviews',
            'language',
            'last_played'
        ]).unique()

        # Convert Unix timestamp to datetime
        unique_users = unique_users.with_columns([
            pl.when(pl.col('last_played').is_not_null())
            .then(pl.from_epoch('last_played', time_unit='s'))
            .otherwise(None)
            .alias('last_played')
        ])

        # Rename num_reviews to review_number for database
        unique_users = unique_users.rename({'num_reviews': 'review_number'})

        users_data = unique_users.to_dicts()

        if users_data:
            # Insert users - they will get auto-generated IDs
            conn.execute(text("""
                INSERT INTO UserTable (playtime_at_review, playtime_forever, review_number, 
                                      language, last_played)
                VALUES (:playtime_at_review, :playtime_forever, :review_number,
                        :language, :last_played)
            """), users_data)

        print(f"Inserted {len(users_data)} users")

        # ====================================
        # STEP 3: Bulk Insert Dates
        # ====================================
        print("Bulk inserting dates...")

        # Extract unique dates from scrape_date in game_df
        unique_dates = (
            game_df
            .select('scrape_date')
            .unique()
            .with_columns([
                pl.col('scrape_date').str.to_date('%Y-%m-%d').alias('scrape_date_parsed')
            ])
            .with_columns([
                pl.col('scrape_date_parsed').dt.year().alias('year'),
                pl.col('scrape_date_parsed').dt.month().alias('month'),
                pl.col('scrape_date_parsed').dt.day().alias('day')
            ])
            .select(['year', 'month', 'day'])
        )

        dates_data = unique_dates.to_dicts()

        if dates_data:
            conn.execute(text("""
                INSERT INTO Date (year, month, day)
                VALUES (:year, :month, :day)
                ON CONFLICT (year, month, day) DO NOTHING
            """), dates_data)

        print(f"Inserted {len(dates_data)} dates")

        # ====================================
        # STEP 4: Populate Bridge Tables
        # ====================================
        print("Populating bridge tables...")

        # === Genre Bridge ===
        games_genres = (
            game_df.select(['name', 'genres'])
            .explode('genres')
            .drop_nulls()
            .unique()
            .rename({'genres': 'genre'})
        )

        genre_bridge_data = games_genres.to_dicts()

        if genre_bridge_data:
            conn.execute(text("""
                INSERT INTO Genre_Game (ID_game, ID_genre)
                SELECT g.ID_game, gen.ID_genre
                FROM (VALUES (:name, :genre)) AS v(game_name, genre_name)
                JOIN Game g ON g.name = v.game_name
                JOIN Genre gen ON gen.name = v.genre_name
                ON CONFLICT (ID_game, ID_genre) DO NOTHING
            """), genre_bridge_data)

        print(f"Inserted {len(genre_bridge_data)} genre-game relationships")

        # === Category Bridge ===
        games_categories = (
            game_df.select(['name', 'categories'])
            .explode('categories')
            .drop_nulls()
            .unique()
            .rename({'categories': 'category'})
        )

        category_bridge_data = games_categories.to_dicts()

        if category_bridge_data:
            conn.execute(text("""
                INSERT INTO Category_Game (ID_game, ID_category)
                SELECT g.ID_game, cat.ID_category
                FROM (VALUES (:name, :category)) AS v(game_name, category_name)
                JOIN Game g ON g.name = v.game_name
                JOIN Category cat ON cat.name = v.category_name
                ON CONFLICT (ID_game, ID_category) DO NOTHING
            """), category_bridge_data)

        print(f"Inserted {len(category_bridge_data)} category-game relationships")

        # === Publisher Bridge ===
        games_publishers = (
            game_df.select(['name', 'publishers'])
            .explode('publishers')
            .drop_nulls()
            .unique()
            .rename({'publishers': 'publisher'})
        )

        publisher_bridge_data = games_publishers.to_dicts()

        if publisher_bridge_data:
            conn.execute(text("""
                INSERT INTO Publisher_Game (ID_game, ID_publisher)
                SELECT g.ID_game, pub.ID_publisher
                FROM (VALUES (:name, :publisher)) AS v(game_name, publisher_name)
                JOIN Game g ON g.name = v.game_name
                JOIN Publisher pub ON pub.name = v.publisher_name
                ON CONFLICT (ID_game, ID_publisher) DO NOTHING
            """), publisher_bridge_data)

        print(f"Inserted {len(publisher_bridge_data)} publisher-game relationships")

        # ====================================
        # STEP 5: Bulk Insert Reviews
        # ====================================
        print("Bulk inserting reviews...")

        # DEBUG: Check the appid values
        print(f"Sample review_df appids: {review_df.select('appid').head(5)}")
        print(f"Sample game_df appids: {game_df.select('appid').head(5)}")
        print(f"Review appid dtype: {review_df['appid'].dtype}")
        print(f"Game appid dtype: {game_df['appid'].dtype}")

        # Check if there are any matches
        common_appids = set(review_df['appid'].to_list()).intersection(set(game_df['appid'].to_list()))
        print(f"Common appids count: {len(common_appids)}")
        print(f"Total review appids: {review_df['appid'].n_unique()}")
        print(f"Total game appids: {game_df['appid'].n_unique()}")

        # If data types don't match, cast them to ensure compatibility
        review_df_cast = review_df.with_columns([
            pl.col('appid').cast(pl.Int64).alias('appid')
        ])

        game_df_for_join = game_df.with_columns([
            pl.col('appid').cast(pl.Int64).alias('appid')
        ])

        # Join review_df with game_df to get scrape dates
        reviews_with_dates = (
            review_df_cast
            .join(
                game_df_for_join.select(['appid', 'scrape_date']),
                on='appid',
                how='left'
            )
        )

        # DEBUG: Check if join worked
        print(f"After join - null scrape_dates: {reviews_with_dates.select('scrape_date').null_count()}")
        print(f"Sample joined data:")
        print(reviews_with_dates.select(['appid', 'scrape_date']).head(5))

        # Filter out rows where scrape_date is null (no matching game)
        reviews_with_dates_filtered = reviews_with_dates.filter(pl.col('scrape_date').is_not_null())
        print(f"Reviews with valid scrape_date: {len(reviews_with_dates_filtered)}")

        if len(reviews_with_dates_filtered) == 0:
            print("⚠️ No reviews have matching games with scrape_date. Skipping review insertion.")
        else:
            # Parse scrape_date and extract year/month/day
            reviews_with_dates_filtered = (
                reviews_with_dates_filtered
                .with_columns([
                    pl.col('scrape_date').str.to_date().alias('scrape_date_parsed')
                ])
                .with_columns([
                    pl.col('scrape_date_parsed').dt.year().alias('year'),
                    pl.col('scrape_date_parsed').dt.month().alias('month'),
                    pl.col('scrape_date_parsed').dt.day().alias('day')
                ])
            )

            # Convert last_played from Unix timestamp to datetime
            reviews_with_dates_filtered = reviews_with_dates_filtered.with_columns([
                pl.when(pl.col('last_played').is_not_null() & (pl.col('last_played') > 0))
                .then(pl.from_epoch('last_played', time_unit='s'))
                .otherwise(None)
                .alias('last_played')
            ])

            # Select only review-related columns
            reviews_data_df = reviews_with_dates_filtered.select([
                'rec_id', 'appid',
                'playtime_at_review', 'playtime_forever', 'num_reviews',
                'language', 'last_played',
                'year', 'month', 'day',
                'votes_up', 'votes_funny', 'sentiment_0_10_round', 'review'
            ])

            # Rename for database columns
            reviews_data_df = reviews_data_df.rename({
                'rec_id': 'ID_rec',
                'appid': 'ID_game',
                'num_reviews': 'review_number',
                'sentiment_0_10_round': 'sentiment_round',
                'review': 'review_text'
            })

            reviews_data = reviews_data_df.to_dicts()

            print(f"Reviews to insert: {len(reviews_data)}")
            if len(reviews_data) > 0:
                print(f"Sample review data: {reviews_data[0]}")

            if reviews_data:
                conn.execute(text("""
                    INSERT INTO Review (ID_rec, ID_UserTable, ID_game, ID_date, votes_up, votes_funny, sentiment_round, review_text)
                    SELECT 
                        v.ID_rec,
                        u.ID_UserTable,
                        v.ID_game,
                        d.ID_date,
                        v.votes_up,
                        v.votes_funny,
                        v.sentiment_round,
                        v.review_text
                    FROM (VALUES (
                        :ID_rec::BIGINT, :ID_game::INTEGER, :playtime_at_review::INTEGER, :playtime_forever::INTEGER, :review_number::INTEGER,
                        :language::TEXT, :last_played::TIMESTAMP, :year::INTEGER, :month::INTEGER, :day::INTEGER,
                        :votes_up::INTEGER, :votes_funny::INTEGER, :sentiment_round::INTEGER, :review_text::TEXT
                    )) AS v(
                        ID_rec, ID_game, playtime_at_review, playtime_forever, review_number,
                        language, last_played, year, month, day,
                        votes_up, votes_funny, sentiment_round, review_text
                    )
                    JOIN UserTable u ON 
                        u.playtime_at_review = v.playtime_at_review AND
                        u.playtime_forever = v.playtime_forever AND
                        u.review_number = v.review_number AND
                        u.language = v.language AND
                        COALESCE(u.last_played, '1970-01-01'::timestamp) = COALESCE(v.last_played, '1970-01-01'::timestamp)
                    JOIN Date d ON 
                        d.year = v.year AND
                        d.month = v.month AND
                        d.day = v.day
                    ON CONFLICT (ID_rec) DO NOTHING
                """), reviews_data)

                print(f"✅ Inserted {len(reviews_data)} reviews")

        print("✅ Bulk insert completed successfully!")