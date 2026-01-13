"""
Schema definitions for MongoDB and Cassandra data.
Used to create empty DataFrames with correct structure when no data is extracted.
"""
import polars as pl
from datetime import datetime

# MongoDB Game schema
MONGO_GAME_SCHEMA = {
    "_id": pl.String,
    "appid": pl.Int64,
    "about_the_game": pl.String,
    "categories": pl.List(pl.String),
    "coming_soon": pl.Boolean,
    "controller_support": pl.String,
    "detailed_description": pl.String,
    "developers": pl.List(pl.String),
    "dlc": pl.List(pl.String),
    "genres": pl.List(pl.String),
    "header_image": pl.String,
    "is_free": pl.Boolean,
    "linux_support": pl.Boolean,
    "mac_support": pl.Boolean,
    "minimum_pc_requirements": pl.String,
    "name": pl.String,
    "price": pl.Float64,
    "publishers": pl.List(pl.String),
    "recommendations": pl.Int64,
    "recommended_pc_requirements": pl.String,
    "release_date": pl.String,
    "required_age": pl.Int64,
    "review_score": pl.Int64,
    "review_score_desc": pl.String,
    "scrape_date": pl.String,
    "short_description": pl.String,
    "supported_languages": pl.List(pl.String),
    "type": pl.String,
    "updated_at": pl.Datetime,
    "windows_support": pl.Boolean
}

# Cassandra Review schema
CASSANDRA_REVIEW_SCHEMA = {
    "rec_id": pl.Int64,
    "appid": pl.Int64,
    "author_id": pl.Int64,
    "language": pl.String,
    "last_played": pl.Int64,
    "num_reviews": pl.Int64,
    "playtime_at_review": pl.Int64,
    "playtime_forever": pl.Int64,
    "received_for_free": pl.Boolean,
    "review": pl.String,
    "sent_compound": pl.Float64,
    "sentiment_0_10": pl.Float64,
    "sentiment_0_10_round": pl.Int64,
    "updated_at": pl.Datetime,
    "voted_up": pl.Boolean,
    "votes_funny": pl.Int64,
    "votes_up": pl.Int64,
    "written_during_early_access": pl.Boolean
}