from sqlalchemy import text
import polars as pl

import logging as log
from dwh_domain.model.dwh_model import (
    DateTable, User, Game, Review,
    Genre, Category, Publisher,
    GenreGame, CategoryGame, PublisherGame
)

log.basicConfig(level=log.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

class DwhRepository:
    def __init__(self):
        pass
    @staticmethod
    def extract_and_update_fixed_item_tables(conn, df, df_column, table_name):
        unique_values = df[df_column].explode().drop_nulls().unique().to_list()

        for value in unique_values:
            # Strip whitespace from the value
            value_stripped = value.strip() if isinstance(value, str) else value

            result = conn.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE name = :value"),
                {"value": value_stripped}
            )

            if result.scalar() == 0:
                conn.execute(
                    text(f"INSERT INTO {table_name} (name) VALUES (:value)"),
                    {"value": value_stripped}
                )

        print(f"Updated table '{table_name}' with unique values from column '{df_column}'.")
        
    @staticmethod
    def bulk_insert_games_and_bridge(
            session,
            game_df: pl.DataFrame,
            genre_game_df: pl.DataFrame,
            category_game_df: pl.DataFrame,
            publisher_game_df: pl.DataFrame,
            batch_size: int = 10000):
        """
        Bulk insert games and bridge tables in batches with optimized lookups.

        Args:
            session: SQLAlchemy session
            game_df: Polars DataFrame with game information
            batch_size: Number of rows to process per batch (default: 10000)
        """
        log.info(f"Bulk inserting games and bridge tables in batches of {batch_size}...")
        log.info("Pre-loading lookup dictionaries...")

        # Load all existing games into a set for O(1) lookup
        existing_games = {game.ID_game for game in session.query(Game.ID_game).all()}
        log.info(f"Loaded {len(existing_games)} existing games")

        # Load all genres into a dictionary: {name -> ID}
        genre_lookup = {genre.genre: genre.ID_genre for genre in session.query(Genre).all()}
        log.info(f"Loaded {len(genre_lookup)} genres")

        # Load all categories into a dictionary: {name -> ID}
        category_lookup = {cat.category: cat.ID_category for cat in session.query(Category).all()}
        log.info(f"Loaded {len(category_lookup)} categories")

        # Load all publishers into a dictionary: {name -> ID}
        publisher_lookup = {pub.publisher: pub.ID_publisher for pub in session.query(Publisher).all()}
        log.info(f"Loaded {len(publisher_lookup)} publishers")

        # Load all existing bridge table relationships into sets for O(1) lookup
        existing_genre_game = {
            (str(gg.ID_game), gg.ID_genre)
            for gg in session.query(GenreGame).all()
        }
        existing_category_game = {
            (str(cg.ID_game), cg.ID_category)
            for cg in session.query(CategoryGame).all()
        }
        existing_publisher_game = {
            (str(pg.ID_game), pg.ID_publisher)
            for pg in session.query(PublisherGame).all()
        }
        log.info(f"Loaded {len(existing_genre_game)} genre-game, {len(existing_category_game)} category-game, {len(existing_publisher_game)} publisher-game relationships")

        # Get unique games
        game_columns = ['appid', 'name']
        if 'review_score' in game_df.columns:
            game_columns.append('review_score')
        if 'required_age' in game_df.columns:
            game_columns.append('required_age')
        if 'is_free' in game_df.columns:
            game_columns.append('is_free')
        if 'release_date' in game_df.columns:
            game_columns.append('release_date')

        unique_games = game_df.select(game_columns).unique()
        total_games = len(unique_games)

        log.info(f"Processing {total_games} unique games...")
        games_inserted = 0

        for batch_start in range(0, total_games, batch_size):
            batch_end = min(batch_start + batch_size, total_games)
            batch_games = unique_games[batch_start:batch_end]

            games_to_insert = []

            for row in batch_games.iter_rows(named=True):
                # Convert appid to string to correctly save it on DB
                game_id = str(row['appid'])

                # Use in-memory lookup instead of DB query
                if game_id not in existing_games:
                    game = Game(
                        ID_game=game_id,
                        name=row.get('name'),
                        review_score=row.get('review_score'),
                        required_age=row.get('required_age'),
                        free_to_play=row.get('is_free', False),
                        release_date=row.get('release_date')
                    )
                    games_to_insert.append(game)
                    # Add to existing_games set to avoid re-inserting in next batch
                    existing_games.add(game_id)

            if games_to_insert:
                session.bulk_save_objects(games_to_insert)
                session.flush()
                games_inserted += len(games_to_insert)

            print(f"Batch {batch_start // batch_size + 1}: Inserted {len(games_to_insert)} games (Total: {games_inserted}/{total_games})")

        print(f"✅ Total games inserted: {games_inserted}")

        if 'genres' in game_df.columns:
            log.info("Processing genre-game relationships...")

            total_genre_relations = len(genre_game_df)
            genre_relations_inserted = 0
            bridge_objects = []

            for batch_start in range(0, total_genre_relations, batch_size):
                batch_end = min(batch_start + batch_size, total_genre_relations)
                batch_genres = genre_game_df[batch_start:batch_end]

                for row in batch_genres.iter_rows(named=True):
                    game_id = str(row['appid'])
                    genre_name = row['genres'].strip() if isinstance(row['genres'], str) else row['genres']

                    # Use in-memory lookup instead of DB query
                    genre_id = genre_lookup.get(genre_name)
                    if genre_id:
                        # Check if relationship already exists using in-memory set
                        if (game_id, genre_id) not in existing_genre_game:
                            bridge_objects.append(GenreGame(ID_game=game_id, ID_genre=genre_id))
                            # Add to set to avoid re-inserting
                            existing_genre_game.add((game_id, genre_id))
                            genre_relations_inserted += 1

                # Bulk insert every batch_size items
                if bridge_objects:
                    session.bulk_save_objects(bridge_objects)
                    session.flush()
                    bridge_objects = []

                print(f"Batch {batch_start // batch_size + 1}: Processed genre relationships (Total: {batch_end}/{total_genre_relations})")

            print(f"✅ Total genre-game relationships inserted: {genre_relations_inserted}")

        if 'categories' in game_df.columns:
            log.info("Processing category-game relationships...")

            total_category_relations = len(category_game_df)
            category_relations_inserted = 0
            bridge_objects = []

            for batch_start in range(0, total_category_relations, batch_size):
                batch_end = min(batch_start + batch_size, total_category_relations)
                batch_categories = category_game_df[batch_start:batch_end]

                for row in batch_categories.iter_rows(named=True):
                    game_id = str(row['appid'])
                    category_name = row['categories'].strip() if isinstance(row['categories'], str) else row['categories']

                    # Use in-memory lookup instead of DB query
                    category_id = category_lookup.get(category_name)
                    if category_id:
                        # Check if relationship already exists using in-memory set
                        if (game_id, category_id) not in existing_category_game:
                            bridge_objects.append(CategoryGame(ID_game=game_id, ID_category=category_id))
                            # Add to set to avoid re-inserting
                            existing_category_game.add((game_id, category_id))
                            category_relations_inserted += 1

                # Bulk insert every batch_size items
                if bridge_objects:
                    session.bulk_save_objects(bridge_objects)
                    session.flush()
                    bridge_objects = []

                print(f"Batch {batch_start // batch_size + 1}: Processed category relationships (Total: {batch_end}/{total_category_relations})")

            print(f"✅ Total category-game relationships inserted: {category_relations_inserted}")

        if 'publishers' in game_df.columns:
            log.info("Processing publisher-game relationships...")

            total_publisher_relations = len(publisher_game_df)
            publisher_relations_inserted = 0
            bridge_objects = []

            for batch_start in range(0, total_publisher_relations, batch_size):
                batch_end = min(batch_start + batch_size, total_publisher_relations)
                batch_publishers = publisher_game_df[batch_start:batch_end]

                for row in batch_publishers.iter_rows(named=True):
                    game_id = str(row['appid'])
                    publisher_name = row['publishers'].strip() if isinstance(row['publishers'], str) else row['publishers']

                    # Use in-memory lookup instead of DB query
                    publisher_id = publisher_lookup.get(publisher_name)
                    if publisher_id:
                        # Check if relationship already exists using in-memory set
                        if (game_id, publisher_id) not in existing_publisher_game:
                            bridge_objects.append(PublisherGame(ID_game=game_id, ID_publisher=publisher_id))
                            # Add to set to avoid re-inserting
                            existing_publisher_game.add((game_id, publisher_id))
                            publisher_relations_inserted += 1

                # Bulk insert every batch_size items
                if bridge_objects:
                    session.bulk_save_objects(bridge_objects)
                    session.flush()
                    bridge_objects = []

                print(f"Batch {batch_start // batch_size + 1}: Processed publisher relationships (Total: {batch_end}/{total_publisher_relations})")

            print(f"✅ Total publisher-game relationships inserted: {publisher_relations_inserted}")

        session.commit()
        print("✅ All games and bridge tables populated successfully!")

    @staticmethod
    def bulk_insert_date_table(session, review_df: pl.DataFrame, batch_size: int = 10000):

        log.info(f"Bulk inserting dates in batches of {batch_size}...")

        # Load existing dates to avoid duplicates
        existing_dates = {date.ID_date for date in session.query(DateTable.ID_date).all()}
        log.info(f"Loaded {len(existing_dates)} existing dates")

        # Extract unique dates from review_df
        unique_dates = (
            review_df
            .select('updated_at')
            .unique()
            .drop_nulls()
        )

        # Parse dates and extract year, month, day components
        # Check if updated_at is already datetime or needs parsing
        if unique_dates.schema['updated_at'] == pl.Datetime:
            # Already datetime, use directly
            unique_dates = unique_dates.with_columns([
                pl.col('updated_at').alias('date_parsed')
            ])
        else:
            # String, needs parsing
            unique_dates = unique_dates.with_columns([
                pl.col('updated_at').str.to_datetime().alias('date_parsed')
            ])

        unique_dates = unique_dates.with_columns([
            pl.col('date_parsed').dt.year().alias('year'),
            pl.col('date_parsed').dt.month().alias('month'),
            pl.col('date_parsed').dt.day().alias('day')
        ]).with_columns([
            # Create ID_date as string: year + month (2 digits) + day (2 digits)
            (pl.col('year').cast(pl.Utf8) +
            pl.col('month').cast(pl.Utf8).str.zfill(2) +
            pl.col('day').cast(pl.Utf8).str.zfill(2)).alias('ID_date')
        ])

        # Get unique date combinations (in case multiple timestamps map to same date)
        unique_dates = unique_dates.select(['ID_date', 'year', 'month', 'day']).unique()

        total_dates = len(unique_dates)
        log.info(f"Processing {total_dates} unique dates...")

        dates_inserted = 0

        # Process dates in batches
        for batch_start in range(0, total_dates, batch_size):
            batch_end = min(batch_start + batch_size, total_dates)
            batch_dates = unique_dates[batch_start:batch_end]

            dates_to_insert = []

            for row in batch_dates.iter_rows(named=True):
                date_id = row['ID_date']

                # Only insert if date doesn't already exist
                if date_id not in existing_dates:
                    dates_to_insert.append(DateTable(
                        ID_date=date_id,
                        year=row['year'],
                        month=row['month'],
                        day=row['day']
                    ))
                    # Add to existing_dates set to avoid re-inserting in next batch
                    existing_dates.add(date_id)

            if dates_to_insert:
                session.bulk_save_objects(dates_to_insert)
                session.flush()
                dates_inserted += len(dates_to_insert)

            print(f"Batch {batch_start // batch_size + 1}: Inserted {len(dates_to_insert)} dates (Total: {dates_inserted}/{total_dates})")

        session.commit()
        print(f"✅ Total dates inserted: {dates_inserted}")

        # Add id_date column to review_df
        if review_df.schema['updated_at'] == pl.Datetime:
            review_df = review_df.with_columns([
                pl.col('updated_at').alias('date_parsed')
            ])
        else:
            review_df = review_df.with_columns([
                pl.col('updated_at').str.to_datetime().alias('date_parsed')
            ])

        review_df = review_df.with_columns([
            pl.col('date_parsed').dt.year().alias('year_temp'),
            pl.col('date_parsed').dt.month().alias('month_temp'),
            pl.col('date_parsed').dt.day().alias('day_temp')
        ]).with_columns([
            (pl.col('year_temp').cast(pl.Utf8) +
            pl.col('month_temp').cast(pl.Utf8).str.zfill(2) +
            pl.col('day_temp').cast(pl.Utf8).str.zfill(2)).alias('id_date')
        ]).drop(['date_parsed', 'year_temp', 'month_temp', 'day_temp'])

        return review_df

    @staticmethod
    def bulk_insert_user_table(session, review_df: pl.DataFrame, batch_size: int = 10000):
        """
        Bulk insert users in batches.

        Args:
            session: SQLAlchemy session
            review_df: Polars DataFrame with review information
            batch_size: Number of rows to process per batch (default: 10000)
        """
        log.info(f"Bulk inserting users in batches of {batch_size}...")

        user_columns = ['author_id']  # Always include author_id
        if 'playtime_at_review' in review_df.columns:
            user_columns.append('playtime_at_review')
        if 'playtime_forever' in review_df.columns:
            user_columns.append('playtime_forever')
        if 'num_reviews' in review_df.columns:
            user_columns.append('num_reviews')
        if 'language' in review_df.columns:
            user_columns.append('language')
        if 'last_played' in review_df.columns:
            user_columns.append('last_played')

        if len(user_columns) == 1:  # Only author_id, no additional user data
            print("⚠️ No additional user columns found in review_df. Skipping user insertion.")
            user_id_map = {}
        else:
            log.info("Pre-loading existing users...")

            # Load existing users to check for duplicates (convert to string for consistent comparison)
            existing_users = {str(user.ID_user) for user in session.query(User.ID_user).all()}
            log.info(f"Loaded {len(existing_users)} existing users")

            # Get unique users
            unique_users = review_df.select(user_columns).unique()
            total_users = len(unique_users)

            log.info(f"Processing {total_users} unique users...")
            users_inserted = 0
            user_id_map = {}  # Map user attributes to user ID

            for batch_start in range(0, total_users, batch_size):
                batch_end = min(batch_start + batch_size, total_users)
                batch_users = unique_users[batch_start:batch_end]

                users_to_insert = []

                for row in batch_users.iter_rows(named=True):
                    user_id = str(row.get('author_id'))  # Convert to string for consistency
                    # Create a unique key for the user
                    user_key = (
                        row.get('playtime_at_review'),
                        row.get('playtime_forever'),
                        row.get('num_reviews'),
                        row.get('language')
                    )

                    # Only insert if the user doesn't already exist
                    if user_id not in existing_users:
                        users_to_insert.append(User(
                            ID_user=user_id,
                            playtime_at_review=row.get('playtime_at_review'),
                            playtime_forever=row.get('playtime_forever'),
                            review_number=row.get('num_reviews'),
                            language=row.get('language'),
                            owned_games=None,  # Not in review data
                            last_played=row.get('last_played')
                        ))
                        # Add to existing_users set to avoid re-inserting in next batch
                        existing_users.add(user_id)

                    user_id_map[user_key] = user_id

                if users_to_insert:
                    session.bulk_save_objects(users_to_insert)
                    session.flush()
                    users_inserted += len(users_to_insert)

                print(f"Batch {batch_start // batch_size + 1}: Inserted {len(users_to_insert)} users (Total: {users_inserted}/{total_users})")

            session.commit()
            print(f"✅ Total users inserted: {users_inserted}")

    @staticmethod
    def bulk_insert_review(session, review_df: pl.DataFrame, batch_size: int = 10000):
        """
        Bulk insert reviews in batches.

        Args:
            session: SQLAlchemy session
            review_df: Polars DataFrame with review information
            batch_size: Number of rows to process per batch (default: 10000)
        """
        log.info(f"Bulk inserting reviews in batches of {batch_size}...")

        total_reviews = len(review_df)
        log.info(f"Processing {total_reviews} reviews...")

        existing_reviews = {str(review.ID_rec) for review in session.query(Review.ID_rec).all()}
        log.info(f"Loaded {len(existing_reviews)} existing reviews")

        reviews_inserted = 0

        # Process reviews in batches
        for batch_start in range(0, total_reviews, batch_size):
            batch_end = min(batch_start + batch_size, total_reviews)
            batch_reviews = review_df[batch_start:batch_end]

            reviews_to_insert = []

            for row in batch_reviews.iter_rows(named=True):
                review_id = str(row.get('rec_id'))
                # Only insert if review doesn't already exist
                if review_id not in existing_reviews:
                    reviews_to_insert.append(Review(
                        ID_rec=review_id,
                        ID_user=str(row.get('author_id')),
                        ID_game=str(row.get('appid')),
                        ID_date=str(row.get('id_date')),
                        votes_up=row.get('votes_up'),
                        votes_funny=row.get('votes_funny'),
                        comment_count=row.get('comment_count'),
                        review_word_count=row.get('review_word_count'),
                        sentiment=row.get('sentiment_0_10_round'),
                        review_text=row.get('review')
                    ))
                    # Add to existing_reviews set to avoid re-inserting in next batch
                    existing_reviews.add(review_id)

            if reviews_to_insert:
                session.bulk_save_objects(reviews_to_insert)
                session.flush()
                reviews_inserted += len(reviews_to_insert)

            print(f"Batch {batch_start // batch_size + 1}: Inserted {len(reviews_to_insert)} reviews (Total: {reviews_inserted}/{total_reviews})")

        session.commit()
        print(f"✅ Total reviews inserted: {reviews_inserted}")