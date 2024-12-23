import asyncio
import logging
import uuid
from typing import Dict, Any, List
import numpy as np
from datetime import datetime
from node.storage.db.db import DB
from sqlalchemy import text
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clean_up_tables(db, table_names: List[str]):
    """Drop tables if they exist"""
    with db.session() as session:
        for table_name in table_names:
            session.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
        session.commit()

async def test_regular_table():
    """Test regular table without vectors"""
    logger.info("\n=== Testing Regular Table ===")


    
    # Test schema for a regular table
    regular_schema = {
        "id": {"type": "text", "primary_key": True},
        "name": {"type": "text"},
        "age": {"type": "integer"},
        "metadata": {"type": "jsonb"},
        "scores": {"type": "float[]"},
        "created_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"}
    }

    async with DB() as db:
        table_names = ["test_regular"]
        await clean_up_tables(db, table_names)
        try:
            # Test create table
            table_name = "test_regular"
            logger.info(f"Creating table: {table_name}")
            await db.create_dynamic_table(table_name, regular_schema)

            # Test add rows
            test_data = [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Alice",
                    "age": 25,
                    "metadata": {"city": "New York", "role": "engineer"},
                    "scores": [85.5, 92.0, 88.5]
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Bob",
                    "age": 30,
                    "metadata": {"city": "San Francisco", "role": "designer"},
                    "scores": [90.0, 88.5, 95.0]
                }
            ]

            logger.info("Adding test data")
            for data in test_data:
                await db.add_dynamic_row(table_name, data)

            # Test query
            logger.info("Testing query")
            results = await db.query_dynamic_table(
                table_name,
                columns=["id", "name", "age"],
                condition={"age": 25}
            )
            logger.info(f"Query results: {results}")

            # Test update
            logger.info("Testing update")
            update_data = {"age": 26}
            updated_rows = await db.update_dynamic_row(
                table_name,
                data=update_data,
                condition={"name": "Alice"}
            )
            logger.info(f"Updated {updated_rows} rows")

            # Test schema retrieval
            logger.info("Testing schema retrieval")
            schema = await db.get_dynamic_table_schema(table_name)
            logger.info(f"Table schema: {schema}")

            # Test list tables
            logger.info("Testing list tables")
            tables = await db.list_dynamic_tables()
            logger.info(f"Available tables: {tables}")

            # Test delete
            logger.info("Testing delete")
            deleted_rows = await db.delete_dynamic_row(
                table_name,
                condition={"name": "Bob"}
            )
            logger.info(f"Deleted {deleted_rows} rows")

            # Final query to verify changes
            final_results = await db.query_dynamic_table(table_name)
            logger.info(f"Final table state: {final_results}")

        except Exception as e:
            logger.error(f"Error in regular table test: {str(e)}")
            raise

async def test_vector_table():
    """Test table with vector embeddings"""
    logger.info("\n=== Testing Vector Table ===")
    
    # Test schema for vector table - using text ID for UUID storage
    vector_schema = {
        "id": {"type": "text", "primary_key": True},
        "text": {"type": "text"},
        "embedding": {"type": "vector", "dimension": 4},  # Using small dimension for testing
        "metadata": {"type": "jsonb"}
    }

    async with DB() as db:
        try:
            # Clean up existing tables
            table_name = "test_vectors"
            await clean_up_tables(db, [table_name])

            # Test table creation
            logger.info(f"Creating table: {table_name}")
            await db.create_dynamic_table(table_name, vector_schema)

            # Helper function for vector generation
            def generate_random_vector(dim: int = 4) -> List[float]:
                return [float(x) for x in np.random.randn(dim)]

            # Generate test data
            test_docs = [
                ("First document", "test"),
                ("Second document", "test"),
                ("Third document", "other")
            ]
            
            test_data = [
                {
                    "id": str(uuid.uuid4()),
                    "text": text,
                    "embedding": generate_random_vector(),
                    "metadata": {"category": category}
                }
                for text, category in test_docs
            ]

            # Test data insertion
            logger.info("Adding test documents with vectors")
            for data in test_data:
                await db.add_dynamic_row(table_name, data)

            # Test basic retrieval
            logger.info("Testing basic document retrieval")
            all_docs = await db.query_dynamic_table(table_name)
            logger.info(f"Retrieved {len(all_docs)} documents")

            # Test vector similarity search with different options
            logger.info("Testing vector similarity search")
            query_vector = generate_random_vector()
            
            # Test with just text and similarity
            similar_docs_basic = await db.vector_similarity_search(
                table_name=table_name,
                vector_column="embedding",
                query_vector=query_vector,
                columns=["text"],
                top_k=2,
                include_similarity=True
            )
            logger.info(f"Similar documents (basic): {similar_docs_basic}")

            # Test with all fields
            similar_docs_full = await db.vector_similarity_search(
                table_name=table_name,
                vector_column="embedding",
                query_vector=query_vector,
                columns=["id", "text", "metadata"],
                top_k=2,
                include_similarity=True
            )
            logger.info(f"Similar documents (full): {similar_docs_full}")

            # Test document update
            test_id = test_data[0]["id"]  # Use a known ID
            logger.info(f"Testing vector update for document {test_id}")
            update_data = {
                "embedding": generate_random_vector(),
                "metadata": {"category": "updated"}
            }
            updated_rows = await db.update_dynamic_row(
                table_name,
                data=update_data,
                condition={"id": test_id}
            )
            logger.info(f"Updated {updated_rows} rows")

            # Verify update
            updated_doc = await db.query_dynamic_table(
                table_name,
                condition={"id": test_id}
            )
            logger.info(f"Updated document state: {updated_doc}")

            # Test schema inspection
            logger.info("Testing vector table schema retrieval")
            schema = await db.get_dynamic_table_schema(table_name)
            logger.info(f"Vector table schema: {schema}")

        except Exception as e:
            logger.error(f"Error in vector table test: {str(e)}")
            raise

        
async def main():
    """Run all tests"""
    try:
        # Test regular table operations
        await test_regular_table()
        
        # Test vector table operations
        await test_vector_table()
        
        logger.info("\nAll tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())