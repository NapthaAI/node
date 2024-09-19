import json
from node.server.user import check_user, register_user


async def check_user_ws_direct(data: str):
    data = json.loads(data)
    response = await check_user(data)
    return json.dumps(response)

async def register_user_ws_direct(data: str):
    data = json.loads(data)
    response = await register_user(data)
    return json.dumps(response)