from ecdsa import SigningKey, SECP256k1
from node.storage.db.db import DB
from node.utils import get_logger
from typing import Dict

logger = get_logger(__name__)

async def register_user(user_input: Dict) -> Dict:
    logger.info(f"Registering user.")
    async with DB() as db:
        user = await db.create_user(user_input)
    logger.info(f"Created user: {user}")
    return user

async def check_user(user_input: Dict) -> Dict:
    logger.info(f"Checking user.")

    async with DB() as db:
        user = await db.get_user_by_public_key(user_input['public_key'])

    if user is not None:
        logger.info(f"Found user: {user}")
        user["is_registered"] = True
    else:
        logger.info(f"No user found.")
        user = user_input 
        user["is_registered"] = False
    return user

def get_public_key(private_key_hex):
    private_key = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    public_key = private_key.get_verifying_key()
    return public_key.to_string().hex()

def generate_user():  
    private_key = SigningKey.generate(curve=SECP256k1).to_string().hex()
    public_key = get_public_key(private_key)
    return public_key, private_key
