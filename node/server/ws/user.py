import  json
from typing import Dict
from node.utils import get_logger
from node.server.user import register_user, check_user

logger = get_logger(__name__)


# async def register_user_ws(user_input: Dict) -> Dict:
async def register_user_ws(websocket, message: Dict) -> Dict:
    """Register a user"""
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    try:
        result = await register_user(params)
        response['params'] = result
        await websocket.send(json.dumps(response))
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        return response


async def check_user_ws(websocket, message: Dict) -> Dict:
    """Check if a user exists"""
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    try:
        result = await check_user(params)
        response['params'] = result
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))
