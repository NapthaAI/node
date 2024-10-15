import asyncio
import subprocess
import sys
from node.config import LLM_BACKEND, OLLAMA_MODELS, VLLM_MODEL
from node.utils import get_logger
from node.ollama.init_ollama import setup_ollama
from node.vllm.init_vllm import setup_vllm

logger = get_logger(__name__)

async def install_setuptools():
    try:
        logger.info("Upgrading setuptools...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "setuptools>=74.1.1"])
        logger.info("Setuptools upgraded successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to upgrade setuptools: {e}")
        raise

async def main():
    llm_backend = LLM_BACKEND
    if llm_backend == "ollama":
        ollama_models = OLLAMA_MODELS
        await setup_ollama(ollama_models)
    elif llm_backend == "vllm":
        vllm_model = VLLM_MODEL
        if not vllm_model:
            logger.error("VLLM_MODEL environment variable is not set")
            return
        
        # Install setuptools before setting up vLLM
        await install_setuptools()
        
        await setup_vllm(vllm_model)
    else:
        logger.error(f"Unsupported LLM backend: {llm_backend}")

if __name__ == "__main__":
    asyncio.run(main())