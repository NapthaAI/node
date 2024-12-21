import asyncio
import httpx
import logging
import uuid
import numpy as np
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:7001"  # Adjust if needed

async def test_regular_table_via_http():
    logger.info("\n=== Testing Regular Table via HTTP ===")

    # 1) Define schema
    regular_schema = {
        "id": {"type": "text", "primary_key": True},
        "name": {"type": "text"},
        "age": {"type": "integer"},
        "metadata": {"type": "jsonb"},
        "scores": {"type": "float[]"},
        "created_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"},
    }
    table_name = "test_regular_http"

    # 2) Prepare data
    test_data = [
        {
            "id": str(uuid.uuid4()),
            "name": "Alice",
            "age": 25,
            "metadata": {"city": "New York", "role": "engineer"},
            "scores": [85.5, 92.0, 88.5],
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Bob",
            "age": 30,
            "metadata": {"city": "San Francisco", "role": "designer"},
            "scores": [90.0, 88.5, 95.0],
        },
    ]

    async with httpx.AsyncClient() as client:
        # 3) Drop table (if exists)
        drop_payload = {"query_str": f"DROP TABLE IF EXISTS {table_name} CASCADE"}
        resp = await client.post(f"{BASE_URL}/local-db/query", json=drop_payload)
        logger.info(f"Drop table response: {resp.text}")

        # 4) Create table
        create_payload = {"table_name": table_name, "schema": regular_schema}
        resp = await client.post(f"{BASE_URL}/local-db/create-table", json=create_payload)
        logger.info(f"Create table response: {resp.json()}")

        # 5) Add rows
        for item in test_data:
            add_payload = {"table_name": table_name, "data": item}
            resp = await client.post(f"{BASE_URL}/local-db/add-row", json=add_payload)
            logger.info(f"Add row response: {resp.json()}")

        # 6) Query with filter (age=25)
        filter_query = f"?columns=id,name,age&condition={{\"age\":25}}"
        resp = await client.get(f"{BASE_URL}/local-db/table/{table_name}/rows{filter_query}")
        logger.info(f"Filtered query result: {resp.json()}")

        # 7) Update (set age=26 where name='Alice')
        update_payload = {
            "table_name": table_name,
            "data": {"age": 26},
            "condition": {"name": "Alice"},
        }
        resp = await client.post(f"{BASE_URL}/local-db/update-row", json=update_payload)
        logger.info(f"Update rows response: {resp.json()}")

        # 8) Schema retrieval
        resp = await client.get(f"{BASE_URL}/local-db/table/{table_name}")
        logger.info(f"Table schema: {resp.json()}")

        # 9) List tables
        resp = await client.get(f"{BASE_URL}/local-db/tables")
        logger.info(f"List tables response: {resp.json()}")

        # 10) Delete row (name='Bob')
        delete_payload = {"table_name": table_name, "condition": {"name": "Bob"}}
        resp = await client.post(f"{BASE_URL}/local-db/delete-row", json=delete_payload)
        logger.info(f"Delete rows response: {resp.json()}")

        # 11) Final query (verify changes)
        resp = await client.get(f"{BASE_URL}/local-db/table/{table_name}/rows")
        logger.info(f"Final table state: {resp.json()}")


async def test_vector_table_via_http():
    logger.info("\n=== Testing Vector Table via HTTP ===")

    # 1) Define schema for vectors
    vector_schema = {
        "id": {"type": "text", "primary_key": True},
        "text": {"type": "text"},
        "embedding": {"type": "vector", "dimension": 4},
        "metadata": {"type": "jsonb"},
    }
    table_name = "test_vectors_http"

    async with httpx.AsyncClient() as client:
        # 2) Drop existing table
        drop_payload = {"query_str": f"DROP TABLE IF EXISTS {table_name} CASCADE"}
        await client.post(f"{BASE_URL}/local-db/query", json=drop_payload)

        # 3) Create table
        create_payload = {"table_name": table_name, "schema": vector_schema}
        resp = await client.post(f"{BASE_URL}/local-db/create-table", json=create_payload)
        logger.info(f"Create vector table response: {resp.json()}")

        # Helper function for random vectors
        def generate_random_vector(dim: int = 4) -> List[float]:
            return list(np.random.randn(dim).astype(float))

        # 4) Insert sample documents
        test_docs = [
            ("First document", "test"),
            ("Second document", "test"),
            ("Third document", "other"),
        ]
        for text_doc, category in test_docs:
            row_data = {
                "id": str(uuid.uuid4()),
                "text": text_doc,
                "embedding": generate_random_vector(),
                "metadata": {"category": category},
            }
            add_payload = {"table_name": table_name, "data": row_data}
            await client.post(f"{BASE_URL}/local-db/add-row", json=add_payload)

        # 5) Basic retrieval
        resp = await client.get(f"{BASE_URL}/local-db/table/{table_name}/rows")
        all_docs = resp.json()
        logger.info(f"All vector table docs: {all_docs}")

        # 6) Vector similarity search (basic)
        query_vec = generate_random_vector()
        vector_search_payload = {
            "table_name": table_name,
            "vector_column": "embedding",
            "query_vector": query_vec,
            "columns": ["text"],
            "top_k": 2,
            "include_similarity": True,
        }
        resp = await client.post(f"{BASE_URL}/local-db/vector_search", json=vector_search_payload)
        logger.info(f"Similarity search (basic): {resp.json()}")

        # 7) Vector similarity search (full)
        vector_search_payload["columns"] = ["id", "text", "metadata"]
        resp = await client.post(f"{BASE_URL}/local-db/vector_search", json=vector_search_payload)
        logger.info(f"Similarity search (full): {resp.json()}")

        # 8) Update one row
        test_id = all_docs["rows"][0]["id"]
        update_payload = {
            "table_name": table_name,
            "data": {
                "embedding": generate_random_vector(),
                "metadata": {"category": "updated"},
            },
            "condition": {"id": test_id},
        }
        await client.post(f"{BASE_URL}/local-db/update-row", json=update_payload)

        # 9) Verify update
        resp = await client.get(
            f"{BASE_URL}/local-db/table/{table_name}/rows?condition={{\"id\":\"{test_id}\"}}"
        )
        logger.info(f"Updated row: {resp.json()}")

        # 10) Inspect schema
        resp = await client.get(f"{BASE_URL}/local-db/table/{table_name}")
        logger.info(f"Vector table schema: {resp.json()}")


async def main():
    try:
        await test_regular_table_via_http()
        await test_vector_table_via_http()
        logger.info("\nAll tests completed successfully via HTTP!")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
