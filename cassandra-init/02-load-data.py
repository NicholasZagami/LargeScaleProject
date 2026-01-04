#!/usr/bin/env python3
"""
Script to load Steam reviews data into Cassandra from JSON export file.
"""

import json
import time
from datetime import datetime
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider


def wait_for_cassandra(max_retries=30, retry_delay=5):
    """Wait for Cassandra to be ready."""
    print("Waiting for Cassandra to be ready...")
    for i in range(max_retries):
        try:
            cluster = Cluster(['cassandra'])
            session = cluster.connect()
            session.execute("SELECT now() FROM system.local")
            print("Cassandra is ready!")
            session.shutdown()
            cluster.shutdown()
            return True
        except Exception as e:
            print(f"Attempt {i+1}/{max_retries}: Cassandra not ready yet. Waiting {retry_delay}s... ({str(e)})")
            time.sleep(retry_delay)

    raise Exception("Cassandra did not become ready in time")


def load_data():
    """Load data from JSON export into Cassandra."""
    print("Connecting to Cassandra...")
    cluster = Cluster(['cassandra'])
    session = cluster.connect('steam_keyspace')

    # Prepare the insert statement
    insert_query = """
    INSERT INTO reviews (
        rec_id, author_id, appid, playtime_forever, playtime_at_review,
        num_reviews, last_played, language, review, voted_up,
        votes_up, votes_funny, received_for_free, written_during_early_access,
        sent_compound, sentiment_0_10, sentiment_0_10_round, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    prepared = session.prepare(insert_query)

    # Read and insert data
    data_file = '/data-export/steam_keyspace-reviews'
    print(f"Loading data from {data_file}...")

    total_records = 0
    skipped_records = 0

    with open(data_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                # Parse JSON line - it could be an array or a single object
                data = json.loads(line.strip())

                # If it's a list, process each record in the list
                if isinstance(data, list):
                    records = data
                else:
                    records = [data]

                # Process each record
                for record in records:
                    # Convert string values to appropriate types
                    rec_id = int(record['rec_id'])
                    author_id = int(record.get('author_id', 0))
                    appid = int(record.get('appid', 0))
                    playtime_forever = int(record.get('playtime_forever', 0))
                    playtime_at_review = int(record.get('playtime_at_review', 0))
                    num_reviews = int(record.get('num_reviews', 0))
                    last_played = int(record.get('last_played', 0))
                    language = record.get('language', '')
                    review = record.get('review', '')
                    voted_up = record.get('voted_up', False)
                    votes_up = int(record.get('votes_up', 0))
                    votes_funny = int(record.get('votes_funny', 0))
                    received_for_free = record.get('received_for_free', False)
                    written_during_early_access = record.get('written_during_early_access', False)
                    sent_compound = float(record.get('sent_compound', 0.0))
                    sentiment_0_10 = float(record.get('sentiment_0_10', 0.0))
                    sentiment_0_10_round = int(record.get('sentiment_0_10_round', 0))

                    # Parse timestamp
                    updated_at_str = record.get('updated_at', '')
                    if updated_at_str:
                        updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                    else:
                        updated_at = datetime.now()

                    # Insert the record
                    session.execute(prepared, (
                        rec_id, author_id, appid, playtime_forever, playtime_at_review,
                        num_reviews, last_played, language, review, voted_up,
                        votes_up, votes_funny, received_for_free, written_during_early_access,
                        sent_compound, sentiment_0_10, sentiment_0_10_round, updated_at
                    ))

                    total_records += 1

                    # Progress indicator
                    if total_records % 100 == 0:
                        print(f"Loaded {total_records} records...")

            except Exception as e:
                print(f"Error processing line {line_num}: {str(e)}")
                print(f"Line content: {line[:200]}...")
                skipped_records += 1
                continue

    print(f"\nData loading completed!")
    print(f"Total records loaded: {total_records}")
    print(f"Skipped records: {skipped_records}")

    # Verify data
    result = session.execute("SELECT COUNT(*) FROM reviews")
    count = result.one()[0]
    print(f"Total records in database: {count}")

    session.shutdown()
    cluster.shutdown()


if __name__ == "__main__":
    try:
        wait_for_cassandra()
        load_data()
        print("Success!")
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)
