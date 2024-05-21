from ecdsa import SigningKey, SECP256k1
from web3 import Web3

def get_public_key(private_key_hex):
    private_key = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    public_key = private_key.get_verifying_key()
    return public_key.to_string().hex()

def generate_user():  
    private_key = SigningKey.generate(curve=SECP256k1).to_string().hex()
    public_key = get_public_key(private_key)
    return public_key, private_key
