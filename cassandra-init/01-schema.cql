-- Create keyspace
CREATE KEYSPACE IF NOT EXISTS steam_keyspace
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

-- Use the keyspace
USE steam_keyspace;

-- Create reviews table
CREATE TABLE IF NOT EXISTS reviews (
    rec_id bigint,
    author_id bigint,
    appid bigint,
    playtime_forever bigint,
    playtime_at_review bigint,
    num_reviews bigint,
    last_played bigint,
    language text,
    review text,
    voted_up boolean,
    votes_up bigint,
    votes_funny bigint,
    received_for_free boolean,
    written_during_early_access boolean,
    sent_compound float,
    sentiment_0_10 float,
    sentiment_0_10_round int,
    updated_at timestamp,
    PRIMARY KEY (rec_id)
);
