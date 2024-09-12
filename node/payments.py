from dotenv import load_dotenv
import json
import os
from payments_py import Payments, Environment
from node.utils import get_logger, run_subprocess
from web3 import Web3

logger = get_logger(__name__)

load_dotenv()

def get_balance(wallet_address):
    web3_provider_url = os.getenv("WEB3_PROVIDER_URL")
    web3 = Web3(Web3.HTTPProvider(web3_provider_url))
    balance = web3.eth.get_balance(wallet_address)
    balance_in_ether = web3.fromWei(balance, 'ether')
    return balance_in_ether

def get_credits(payments, subscription_did, account_address):
    response = payments.get_subscription_balance(subscription_did, account_address)
    print('REPONSE: ', response.content)

def generate_keyfile(config):
    web3 = Web3(Web3.HTTPProvider(config["WEB3_PROVIDER_URL"]))
    encrypted_private_key = web3.eth.account.encrypt(config["PRIVATE_KEY"], config["PASSWORD"])
    with open("keyfile.json", 'w') as file:
        json.dump(encrypted_private_key, file)

def get_subscription_details(payments, subscription_did):
    response = payments.get_subscription_details(subscription_did)
    print('REPONSE: ', response.content)

def get_service_endpoints(self, service_did):
    response = payments.get_asset_ddo(service_did)
    result = json.loads(response.content.decode())
    service_name = result['service'][0]['attributes']['main']['name']
    service_endpoints = result['service'][0]['attributes']['main']['webService']['endpoints']
    service_endpoint = service_endpoints[0]['post']
    return service_endpoint

def order_free_plan(config):
    plan_did = config["FREEPLAN_DID"]
    run_subprocess(["ncli", "app", "order", plan_did])

def register_service(payments, subscription_did):
    print('SUBSCRIPTION DID: ', subscription_did)
    response = payments.create_service(
        subscription_did,    
        name="AI Node 0",
        description="AI Node 0",
        price=1,
        token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
        service_charge_type="fixed",
        auth_type="none",
        amount_of_credits=1,
        endpoints=[{"post":"http://hub.algoverai.link:7001/CreateTask"}]
    )
    print('REPONSE: ', response.content)


def setup_payments_from_config(config):
    logger.info(f"Setting up payments and services.")
    payments = Payments(session_key=config['SESSION_KEY'], environment=Environment.appTesting, version="0.1.0", marketplace_auth_token=config['MARKETPLACE_AUTH_TOKEN'])

    logger.info(f"Getting details for Subscrition DID {config["PAIDPLAN_DID"]}.")
    get_subscription_details(payments, config["PAIDPLAN_DID"])
    
    logger.info(f"Checking balance for Subscrition DID {config["PAIDPLAN_DID"]}.")
    get_credits(payments, config["PAIDPLAN_DID"], "0x0106B8532816e6DAdC377697CC58072eD6023075")
    
    logger.info(f"Registering service with Subscrition DID {config["PAIDPLAN_DID"]}.")
    register_service(payments, config["PAIDPLAN_DID"])
    logger.info("Done setting up.")

    get_service_endpoints(payments, config["PAIDPLAN_DID"])