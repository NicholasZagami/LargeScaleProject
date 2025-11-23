import json
from datetime import date

from kafka import KafkaProducer
import polars as pl

def custom_serializer(obj):
    if isinstance(obj, date):
        return obj.isoformat()  # Convert date to ISO 8601 string
    raise TypeError(f"Type {type(obj)} not serializable")

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v, default=custom_serializer).encode('utf-8')
)

topic = 'review-topic'

df = pl.read_parquet("")

for row in df.to_dicts():
    print(row)
    producer.send(topic, row)