import json
from datetime import date
from pathlib import Path

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

topic = 'games-topic'
file_path = Path("E:\Projects\LargeScaleProject\\file-example\games_concat.parquet")

# Check if the file exists
if not file_path.exists():
    raise FileNotFoundError(f"File not found: {file_path.resolve()}")

df = pl.read_parquet(file_path)

for row in df.to_dicts():
    print(row)
    producer.send(topic, row)