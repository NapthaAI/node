import logging
from ecdsa import SigningKey, SECP256k1, VerifyingKey
from node.storage.db.db import LocalDBPostgres
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

async def register_user(user_input: Dict) -> Tuple[bool, Dict]:
    logger.info("Registering user.")
    input_ = {
        "public_key": user_input["public_key"],
        "id": "user:" + user_input["public_key"],
    }
    async with LocalDBPostgres() as db:
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
    async with LocalDBPostgres() as db:
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
    
async def get_user_public_key(user_id: str) -> str | None:
    async with LocalDBPostgres() as db:
        public_key = await db.get_public_key_by_id(user_id)

    if public_key:
        return public_key
    else:
        logger.info("No user found.")
        return None

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

def verify_signature(consumer_id, signature_hex, public_key_hex):
    public_key = VerifyingKey.from_string(bytes.fromhex(public_key_hex), curve=SECP256k1)
    consumer_id_bytes = consumer_id.encode('utf-8')
    signature = bytes.fromhex(signature_hex)
    try:
        if public_key.verify(signature, consumer_id_bytes):
            return True
    except:
        return False