import json
from node.storage.hub.hub import Hub
from node.utils import get_logger


logger = get_logger(__name__)


async def setup_payments_from_config(payments_config_path, node_id):
    hub = await Hub("seller1", "great-password")
    logger.info(f"Setting up plans and services in {payments_config_path}")
    with open(payments_config_path) as f:
        payments_config = json.load(f)

    service_config = payments_config["services"][0]
    service = await hub.create_service(service_config=service_config)

    plan_config = payments_config["plans"][0]
    plan_config["listing"] = service[0]["id"]

    plan_config["node"] = node_id
    plan = await hub.create_plan(plan_config=plan_config)

    await hub.requests_to_publish(publish={"me": hub.user_id, "auction": plan[0]["id"]})

    logger.info("Done setting up plans and services.")
