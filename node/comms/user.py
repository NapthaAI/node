from fastapi import APIRouter
from node.storage.db.db import DB
from node.utils import get_logger
from typing import Dict

logger = get_logger(__name__)

router = APIRouter()


async def register_user(user_input: Dict) -> Dict:
    logger.info(f"Received request to register user.")
    db = await DB()
    user = await db.create_user(user_input)
    logger.info(f"Created user: {user}")
    return user


async def check_user(user_input: Dict) -> Dict:
    logger.info(f"Received request to check user.")
    user_input['id'] = f"user:{user_input['public_key']}"

    db = await DB()
    user = await db.get_user(user_input)

    if user is not None:
        logger.info(f"Found user: {user}")
        user["is_registered"] = True
    else:
        logger.info(f"No user found.")
        user = user_input 
        user["is_registered"] = False
    return user