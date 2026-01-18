-- ============================================
-- Create DWH Database
-- ============================================
-- 1) Create schema for the data warehouse

\c prefect;
CREATE SCHEMA IF NOT EXISTS dwh;

-- Connect to the DWH database

-- ============================================
-- Drop tables if they exist (for clean rebuild)
-- ============================================

DROP TABLE IF EXISTS dwh.Genre_Game CASCADE;
DROP TABLE IF EXISTS dwh.Category_Game CASCADE;
DROP TABLE IF EXISTS dwh.Publisher_Game CASCADE;
DROP TABLE IF EXISTS dwh.Review CASCADE;
DROP TABLE IF EXISTS dwh.UserTable CASCADE;
DROP TABLE IF EXISTS dwh.Game CASCADE;
DROP TABLE IF EXISTS dwh.Date CASCADE;
DROP TABLE IF EXISTS dwh.Genre CASCADE;
DROP TABLE IF EXISTS dwh.Category CASCADE;
DROP TABLE IF EXISTS dwh.Publisher CASCADE;
DROP TABLE IF EXISTS dwh.Failed_Review CASCADE;
DROP TABLE IF EXISTS dwh.Pipeline_Run CASCADE;

-- ============================================
-- 3) Dimension Tables (schema dwh)
-- ============================================

CREATE TABLE dwh.Date (
    ID_date TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL
);

CREATE TABLE dwh.UserTable (
    ID_UserTable TEXT PRIMARY KEY,
    playtime_at_review INTEGER,
    playtime_forever INTEGER,
    review_number INTEGER,
    language VARCHAR(50),
    owned_games INTEGER,
    last_played TIMESTAMP
);

CREATE TABLE dwh.Genre (
    ID_genre SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE dwh.Category (
    ID_category SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE dwh.Publisher (
    ID_publisher SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE dwh.Game (
    ID_game TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    review_score INTEGER,
    required_age INTEGER,
    price FLOAT,
    free_to_play BOOLEAN,
    release_date TEXT
);

-- ============================================
-- 4) Fact Table (schema dwh)
-- ============================================

CREATE TABLE dwh.Review (
    ID_rec TEXT PRIMARY KEY,
    ID_UserTable TEXT NOT NULL,
    ID_game TEXT NOT NULL,
    ID_date TEXT NOT NULL,
    votes_up BIGINT DEFAULT 0,
    votes_funny BIGINT DEFAULT 0,
    comment_count BIGINT DEFAULT 0,
    review_word_count BIGINT DEFAULT 0,
    sentiment_round BIGINT DEFAULT 0,
    review_text TEXT,
    FOREIGN KEY (ID_UserTable) REFERENCES dwh.UserTable(ID_UserTable),
    FOREIGN KEY (ID_game) REFERENCES dwh.Game(ID_game),
    FOREIGN KEY (ID_date) REFERENCES dwh.Date(ID_date)
);

-- ============================================
-- 5) Bridge Tables (schema dwh)
-- ============================================

-- Game-Genre Bridge Table
CREATE TABLE dwh.Genre_Game (
    ID_game TEXT NOT NULL,
    ID_genre INTEGER NOT NULL,
    PRIMARY KEY (ID_game, ID_genre),
    FOREIGN KEY (ID_game) REFERENCES dwh.Game(ID_game) ON DELETE CASCADE,
    FOREIGN KEY (ID_genre) REFERENCES dwh.Genre(ID_genre) ON DELETE CASCADE
);

-- Game-Category Bridge Table
CREATE TABLE dwh.Category_Game (
    ID_game TEXT NOT NULL,
    ID_category INTEGER NOT NULL,
    PRIMARY KEY (ID_game, ID_category),
    FOREIGN KEY (ID_game) REFERENCES dwh.Game(ID_game) ON DELETE CASCADE,
    FOREIGN KEY (ID_category) REFERENCES dwh.Category(ID_category) ON DELETE CASCADE
);

-- Game-Publisher Bridge Table
CREATE TABLE dwh.Publisher_Game (
    ID_game TEXT NOT NULL,
    ID_publisher INTEGER NOT NULL,
    PRIMARY KEY (ID_game, ID_publisher),
    FOREIGN KEY (ID_game) REFERENCES dwh.Game(ID_game) ON DELETE CASCADE,
    FOREIGN KEY (ID_publisher) REFERENCES dwh.Publisher(ID_publisher) ON DELETE CASCADE
);

-- ============================================
-- 6) Queue Tables (schema dwh)
-- ============================================

-- Failed Reviews Queue Table
-- Stores reviews that failed processing (e.g., missing game reference)
-- Preserves original_date instead of modifying updated_at in Cassandra
CREATE TABLE dwh.Failed_Review (
    rec_id TEXT PRIMARY KEY,
    original_date TIMESTAMP NOT NULL,
    retry_after TIMESTAMP NOT NULL,
    failure_count INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    appid TEXT,
    created_at TIMESTAMP NOT NULL
);

-- Index for efficient querying of reviews ready for retry
CREATE INDEX idx_failed_review_retry_after ON dwh.Failed_Review (retry_after);

-- Pipeline Run Tracker Table
-- Tracks which extraction dates have been processed successfully
CREATE TABLE dwh.Pipeline_Run (
    extraction_date DATE PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0
);

-- Index for efficient querying of pending/failed runs
CREATE INDEX idx_pipeline_run_status ON dwh.Pipeline_Run (status);

-- ============================================
-- 7) Grants and Permissions
-- ============================================

-- IMPORTANT:
-- - dwh is a SCHEMA, not a DATABASE
-- - do not lock down public schema here: Prefect needs it.

-- Replace 'prefect' with your app user if needed, but keeping 'prefect' is ok
GRANT USAGE, CREATE ON SCHEMA dwh TO prefect;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA dwh
TO prefect;

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA dwh
TO prefect;

-- Default privileges for future tables/sequences created in dwh
ALTER DEFAULT PRIVILEGES IN SCHEMA dwh
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO prefect;

ALTER DEFAULT PRIVILEGES IN SCHEMA dwh
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO prefect;

-- (Optional) if Streamlit connects with another user, grant to it too:
-- GRANT USAGE, CREATE ON SCHEMA dwh TO streamlit;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA dwh TO streamlit;
-- GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA dwh TO streamlit;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA dwh GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO streamlit;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA dwh GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO streamlit;