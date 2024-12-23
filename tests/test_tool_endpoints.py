import httpx
import asyncio
import logging
from httpx import HTTPStatusError, RemoteProtocolError
from pydantic import BaseModel
from typing import List, Optional, Dict
import json

logger = logging.getLogger(__name__)
HTTP_TIMEOUT = 60
worker_node_url = "http://localhost:7001"

################# Toolset stuff####################
class ToolDetails(BaseModel):
    id: str
    name: str
    description: str
    source_url: str

class ToolsetDetails(BaseModel):
    id: str
    name: str
    description: str
    tools: List[ToolDetails]

class ToolsetRequest(BaseModel):
    agent_id: str

class SetToolsetRequest(BaseModel):
    agent_id: str
    toolset_name: str

class ToolsetListRequest(BaseModel):
    agent_id: str

class ToolsetLoadRepoRequest(BaseModel):
    agent_id: str
    repo_url: str
    toolset_name: str

class ToolsetList(BaseModel):
    toolsets: List[ToolsetDetails]

class ToolRunRequest(BaseModel):
    tool_run_id: str
    agent_id: str
    toolset_id: str
    tool_id: str
    params: Optional[Dict] = None

class ToolRunResult(BaseModel):
    agent_id: str
    toolset_id: str
    tool_run_id: str
    tool_id: str
    params: Optional[Dict] = None
    result: str
################# End Toolset stuff####################

async def main():
    # load repo
    try:
        print("Loading repo")
        test_repo = "https://github.com/C0deMunk33/test_toolset/"
        request = ToolsetLoadRepoRequest(agent_id="1", repo_url=test_repo, toolset_name="test")

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            load_repo_response = await client.post(
                f"{worker_node_url}/tool/add_tool_repo_to_toolset",
                json=request.model_dump()
            )
            load_repo_response.raise_for_status()
            print("repo loaded")
    except (HTTPStatusError, RemoteProtocolError) as e:
        print(f"Failed to load repo: {e}")
        raise
    except Exception as e:
        print(f"Error loading repo: {e}")
        raise


    try:
        print("Getting toolset list from worker node")
        request = ToolsetListRequest(agent_id="1")
        
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # Send agent_id as a query parameter
            toolset_list_response = await client.post(
                f"{worker_node_url}/tool/get_toolset_list",
                json=request.model_dump()
            )
            toolset_list_response.raise_for_status()
            result = ToolsetList(**json.loads(toolset_list_response.text))
            print(result)
    except (HTTPStatusError, RemoteProtocolError) as e:
        print(f"Failed to get toolset list: {e}")
        raise
    except Exception as e:
        print(f"Error getting toolset list: {e}")
        raise


    # set toolset "test"
    try:
        print("Setting toolset")
        request = SetToolsetRequest(agent_id="1", toolset_name="test")
        
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            toolset_response = await client.post(
                f"{worker_node_url}/tool/set_toolset",
                json=request.model_dump()
            )
            toolset_response.raise_for_status()
            result = ToolsetDetails(**json.loads(toolset_response.text))
            print("~"*50)
            print(result)
    except (HTTPStatusError, RemoteProtocolError) as e:
        print(f"Failed to set toolset: {e}")
        raise
    except Exception as e:
        print(f"Error setting toolset: {e}")
        raise
    


    # get current toolset
    try:
        print("Getting current toolset")
        request = ToolsetRequest(agent_id="1")
        
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            toolset_response = await client.post(
                f"{worker_node_url}/tool/get_current_toolset",
                json=request.model_dump()
            )
            toolset_response.raise_for_status()
            print("~"*50)
            result = ToolsetDetails(**json.loads(toolset_response.text))
            print("~"*50)
            print(result)
    except (HTTPStatusError, RemoteProtocolError) as e:
        print(f"Failed to get toolset list: {e}")
        raise
    except Exception as e:
        print(f"Error getting toolset list: {e}")
        raise

    # run tool
    try:
        print("Running tool")
        request = ToolRunRequest(tool_run_id="1", 
                                 agent_id="1", 
                                 toolset_id="test", 
                                 tool_id="add",
                                 params={"a": 1, "b": 2})
        
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            tool_run_response = await client.post(
                f"{worker_node_url}/tool/run_tool",
                json=request.model_dump()
            )
            tool_run_response.raise_for_status()
            print("~"*50)
            result = ToolRunResult(**json.loads(tool_run_response.text))
            print("~"*50)
            print(result)
    except (HTTPStatusError, RemoteProtocolError) as e:
        print(f"Failed to run tool: {e}")
        raise
    except Exception as e:
        print(f"Error running tool: {e}")
        raise

if __name__ == "__main__":
    response = asyncio.run(main())
    print(response)