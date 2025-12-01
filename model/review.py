from dataclasses import dataclass
from typing import Optional, List, Union

@dataclass
class Review:
    rec_id: int
    author_id: int
    appid: int
    playtime_forever: Optional[int] = None
    playtime_at_review: Optional[int] = None
    num_reviews: Optional[int] = None
    last_played: Optional[int] = None
    language: Optional[str] = None
    review: Optional[str] = None
    voted_up: Optional[bool] = None
    votes_up: Optional[int] = None
    votes_funny: Optional[int] = None
    received_for_free: Optional[bool] = None
    written_during_early_access: Optional[bool] = None
    sent_compound: Optional[float] = None
    sentiment_0_10: Optional[float] = None
    sentiment_0_10_round: Optional[int] = None

    @classmethod
    def from_kafka_message(cls, message_value):
        """
        Create a Review instance from a Kafka message
        """
        return cls(
            rec_id=int(message_value.get('rec_id')),
            author_id=int(message_value.get('author_id')),
            appid=int(message_value.get('appid')),
            playtime_forever=message_value.get('playtime_forever'),
            playtime_at_review=message_value.get('playtime_at_review'),
            num_reviews=message_value.get('num_reviews'),
            last_played=message_value.get('last_played'),
            language=message_value.get('language'),
            review=message_value.get('review'),
            voted_up=message_value.get('voted_up'),
            votes_up=message_value.get('votes_up'),
            votes_funny=message_value.get('votes_funny'),
            received_for_free=message_value.get('received_for_free'),
            written_during_early_access=message_value.get('written_during_early_access'),
            sent_compound=message_value.get('sent_compound'),
            sentiment_0_10=message_value.get('sentiment_0_10'),
            sentiment_0_10_round=message_value.get('sentiment_0_10_round')
        )

    def to_cassandra_values(self):
        """
        Get tuple of values for Cassandra insert
        """
        return (
            self.rec_id,
            self.author_id,
            self.appid,
            self.playtime_forever,
            self.playtime_at_review,
            self.num_reviews,
            self.last_played,
            self.language,
            self.review,
            self.voted_up,
            self.votes_up,
            self.votes_funny,
            self.received_for_free,
            self.written_during_early_access,
            self.sent_compound,
            self.sentiment_0_10,
            self.sentiment_0_10_round
        )

    @staticmethod
    def get_cassandra_columns():
        """
        Get list of column names for Cassandra
        """
        return [
            'rec_id', 'author_id', 'appid', 'playtime_forever',
            'playtime_at_review', 'num_reviews', 'last_played', 'language',
            'review', 'voted_up', 'votes_up', 'votes_funny',
            'received_for_free', 'written_during_early_access',
            'sent_compound', 'sentiment_0_10', 'sentiment_0_10_round'
        ]