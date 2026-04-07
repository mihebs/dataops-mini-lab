from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from temporalio import activity
import os
import pandas as pd

load_dotenv()


@activity.defn
async def generate_csv_activity() -> str:
    from app.generate_fake_csv import main as generate_csv_main

    generate_csv_main()
    return "data/raw/orders_fake_10mb.csv"


@activity.defn
async def load_csv_to_mongodb_activity(csv_path: str) -> str:
    mongodb_uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE", "dataops_lab")
    collection_name = os.getenv("MONGODB_COLLECTION", "orders_raw")

    if not mongodb_uri:
        raise ValueError("MONGODB_URI not found in environment variables")

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    print("Reading CSV...")
    df = pd.read_csv(path)

    print("Converting to records...")
    records = df.to_dict(orient="records")

    print("Connecting to MongoDB...")
    client = MongoClient(mongodb_uri)
    db = client[database_name]
    collection = db[collection_name]

    print("Cleaning collection...")
    collection.delete_many({})

    if records:
        print("Inserting data into MongoDB...")
        collection.insert_many(records)

    inserted_count = collection.count_documents({})

    client.close()

    print(f"Inserted {inserted_count} documents.")

    return f"Inserted {inserted_count} documents into {database_name}.{collection_name}"


@activity.defn
async def aggregate_orders_activity() -> list[dict]:
    mongodb_uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE", "dataops_lab")
    collection_name = os.getenv("MONGODB_COLLECTION", "orders_raw")

    if not mongodb_uri:
        raise ValueError("MONGODB_URI not found in environment variables")

    print("Running aggregation in MongoDB...")

    client = MongoClient(mongodb_uri)
    db = client[database_name]
    collection = db[collection_name]

    pipeline = [
        {
            "$group": {
                "_id": "$status",
                "total_orders": {"$sum": 1},
                "total_amount": {"$sum": "$amount"},
            }
        },
        {"$sort": {"total_amount": -1}},
    ]

    result = list(collection.aggregate(pipeline))

    client.close()

    normalized = []
    for item in result:
        normalized.append(
            {
                "status": item["_id"],
                "total_orders": item["total_orders"],
                "total_amount": round(float(item["total_amount"]), 2),
            }
        )

    print("Aggregation completed.")

    return normalized