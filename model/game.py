from dataclasses import dataclass
from typing import Optional, List, Union

@dataclass
class Game:
    appid: int
    name: str
    genre: Optional[str] = None
    categories: Optional[str] = None
    is_free: Optional[bool] = None
    price: Optional[float] = None

    @classmethod
    def from_kafka_message(cls, message_value):
        """
        Create a Game instance from a Kafka message
        """

        return cls(
            appid=int(message_value.get('appid')),
            name=message_value.get('name'),
            genre=cls.convert_list_to_string(message_value.get('genre')),
            categories=cls.convert_list_to_string(message_value.get('categories')),
            is_free=message_value.get('is_free'),
            price=message_value.get('price')
        )

    def to_cassandra_values(self):
        """
        Get tuple of values for Cassandra insert
        """
        return (
            self.appid,
            self.name,
            self.genre,
            self.categories,
            self.is_free,
            self.price
        )

    @staticmethod
    def get_cassandra_columns():
        """
        Get list of column names for Cassandra
        """
        return ['appid', 'name', 'genre', 'categories', 'is_free', 'price']

    @staticmethod
    def convert_list_to_string(lst: Union[List[str], None]) -> Optional[str]:
        """
        Convert a list to a comma-separated string
        """
        if lst is None:
            return None
        return ', '.join(lst)