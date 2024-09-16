import json
from node.utils import get_logger
from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from node.server.orchestration import create_task_run, update_task_run

logger = get_logger(__name__)



async def create_task_run_ws(websocket, message: dict) -> ModuleRun:
    """
    Create a task run via a websocket connection.
    """
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    try:
        module_run_input = ModuleRunInput(
            **params
        )
        module_run = await create_task_run(module_run_input)
        response['params'] = module_run.model_dict()
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))


async def update_task_run_ws(websocket, message: dict) -> ModuleRun:
    """
    Update a task run via a websocket connection.
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
        module_run = ModuleRun(**params)
        module_run = await update_task_run(module_run)
        response['params'] = module_run.model_dict()
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))

    