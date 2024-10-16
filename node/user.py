import logging
from ecdsa import SigningKey, SECP256k1
from node.storage.db.db import DB
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


async def register_user(user_input: Dict) -> Tuple[bool, Dict]:
    logger.info("Registering user.")
    input_ = {
        "public_key": user_input["public_key"],
        "id": "user:" + user_input["public_key"],
    }
    async with DB() as db:
        user = await db.create_user(input_)

    if user:
        user_data = user.copy()
        user_data.pop("_sa_instance_state", None)
        logger.info(f"Created user: {user_data}")
        return True, user_data
    else:
        return False, {}


async def check_user(user_input: Dict) -> Tuple[bool, Dict]:
    logger.info("Checking user.")
    async with DB() as db:
        user = await db.get_user(user_input=user_input)

    if user:
        logger.info(f"Found user: {user}")
        user_data = user.copy()
        user_data.pop("_sa_instance_state", None)
        user_data["is_registered"] = True
        return True, user_data
    else:
        logger.info("No user found.")
        user_data = user_input.copy()
        user_data["is_registered"] = False
        return False, user_data


def get_public_key(private_key_hex):
    private_key = SigningKey.from_string(
        bytes.fromhex(private_key_hex), curve=SECP256k1
    )
    public_key = private_key.get_verifying_key()
    return public_key.to_string().hex()


def generate_user():
    private_key = SigningKey.generate(curve=SECP256k1).to_string().hex()
    public_key = get_public_key(private_key)
    return public_key, private_key
