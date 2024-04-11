import os
import pytz
import asyncio
from typing import Dict
from celery import Celery
from datetime import datetime
from dotenv import load_dotenv
from node.utils import get_logger
from node.celery_worker.celery_utils import (
    run_container,
    run_template,
)
from node.storage.db.db import update_db_with_status_sync

logger = get_logger(__name__)

# Load environment variables
load_dotenv(".env")

# Celery config
BROKER_URL = os.environ.get("CELERY_BROKER_URL")

# Make sure OPENAI_API_KEY is set
try:
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    logger.info("OPENAI_API_KEY found in environment")
except KeyError:
    logger.error("OPENAI_API_KEY not found in environment")
    raise Exception("OPENAI_API_KEY not found in environment")

# Celery app
app = Celery(
    "docker_tasks",
    broker=BROKER_URL,
)


# Function to execute a docker job
@app.task
def execute_docker_job(job: Dict) -> None:
    """
    Execute a docker job
    :param job: Job details
    :param hub_config: Hub config
    """

    logger.info(f"Executing docker job: {job}")

    job["status"] = "processing"
    job["start_processing_time"] = datetime.now(pytz.utc).isoformat()

    # Remove None values from job recursively
    def remove_none_values_from_dict(d):
        for key, value in list(d.items()):
            if value is None:
                del d[key]
            elif isinstance(value, dict):
                remove_none_values_from_dict(value)
        return d

    job = remove_none_values_from_dict(job)

    # Update the job status to processing
    asyncio.run(
        update_db_with_status_sync(
            job_data=job,
        )
    )
    try:
        run_container(
            job=job,
        )

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")

        job["status"] = "error"
        job["reply"] = {"output": ""}
        job["error"] = True
        job["error_message"] = str(e)
        job["completed_time"] = datetime.now(pytz.utc).isoformat()

        asyncio.run(
            update_db_with_status_sync(
                job_data=job,
            )
        )


# Function to execute a template job
@app.task
def execute_template_job(job: Dict) -> None:
    """
    Execute a template job
    :param job: Job details
    :param hub_config: Hub config
    """

    logger.info(f"Executing template job: {job}")

    job["status"] = "processing"
    job["start_processing_time"] = datetime.now(pytz.utc).isoformat()

    # remove None values from job
    job = {k: v for k, v in job.items() if v is not None}

    # Update the job status to processing
    asyncio.run(
        update_db_with_status_sync(
            job_data=job,
        )
    )

    try:
        output = run_template(
            job=job,
        )
        logger.info(f"Template output: {output}")
        logger.info(f"Output type: {type(output)}")

        job["reply"] = {"output": output}
        job["status"] = "completed"
        job["completed_time"] = datetime.now(pytz.utc).isoformat()

        # Update the job status to completed
        asyncio.run(
            update_db_with_status_sync(
                job_data=job,
            )
        )

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")

        job["status"] = "error"
        job["reply"] = {"output": ""}
        job["error"] = True
        job["error_message"] = str(e)
        job["completed_time"] = datetime.now(pytz.utc).isoformat()

        asyncio.run(
            update_db_with_status_sync(
                job_data=job,
            )
        )
