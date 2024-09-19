from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from node.server.http.orchestration import router as http_server_orchestration_router
from node.server.http.storage import router as http_server_storage_router
from node.server.http.task import router as http_server_router
from node.server.http.user import router as http_server_user_router
from node.utils import get_logger

logger = get_logger(__name__)

class HTTPServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        
        self.app = FastAPI()
        self.app.include_router(http_server_router)
        self.app.include_router(http_server_storage_router)
        self.app.include_router(http_server_user_router)
        self.app.include_router(http_server_orchestration_router)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def launch_server(self):
        logger.info(f"Launching HTTP server...")
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="debug",
            timeout_keep_alive=300,
            limit_concurrency=200,
            backlog=4096,
        )
        server = uvicorn.Server(config)
        await server.serve()