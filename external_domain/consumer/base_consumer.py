import json
import logging
from kafka import KafkaConsumer
from external_domain.model.review import Review

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BaseConsumer:
    def __init__(
            self,
            topic_name,
            bootstrap_servers,
            group_id,
            auto_offset_reset
    ):
        # Create Kafka consumer
        self.consumer = KafkaConsumer(
            topic_name,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=True,
            auto_commit_interval_ms=1000,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')) if x else None,
            key_deserializer=lambda x: x.decode('utf-8') if x else None
        )

    def process_and_save_message(self, message, db_type, mongo_collection=None, cassandra_session=None):
        """
        Save message to the specified database type
        """

        if db_type == 'mongodb':
            try:
                # extract message properties to save on db
                value = message.value
                mongo_collection.update_one(
                    {'appid': value['appid']},
                    {'$set': value},
                    upsert=True
                )
                logger.info(f"Game inserted: {value.get('name')}")
            except Exception as e:
                logger.error(f"Error inserting game into MongoDB: {e}")
            pass
        elif db_type == 'cassandra':
            try:
                review = Review.from_kafka_message(message.value)
                columns = Review.get_cassandra_columns()
                placeholders = ', '.join(['?' for _ in columns])
                column_names = ', '.join(columns)
                query = f"INSERT INTO reviews ({column_names}) VALUES ({placeholders})"

                prepared = cassandra_session.prepare(query)
                cassandra_session.execute(prepared, review.to_cassandra_values())
                logger.info(f"Review inserted into Cassandra: {review.rec_id}")
            except Exception as e:
                logger.error(f"Error inserting reviews into Cassandra: {e}")
                pass
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    def consume_messages(self, db_type, mongo_collection=None, cassandra_session=None):
        """
        Consume messages from the Kafka topic
        """
        try:
            for message in self.consumer:
                self.process_and_save_message(message, db_type, mongo_collection, cassandra_session)
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")
        finally:
            self.consumer.close()
