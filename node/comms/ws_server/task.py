import json
from node.comms.task import create_task, check_task
from naptha_sdk.schemas import ModuleRun, ModuleRunInput


async def create_task_ws(websocket, message: dict) -> ModuleRun:
    """
    Create a task and return the task
    """
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    try:
        module_run_input = ModuleRunInput(**params)
        result = await create_task(module_run_input)
        response['params'] = result.model_dict()
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))


async def check_task_ws(websocket, message: dict) -> ModuleRun:
    """
    Check a task and return the task
    """
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    module_run = ModuleRun(**params)
    try:
        result = await check_task(module_run)
        response['params'] = result.model_dict()
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))
