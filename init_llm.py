import os
import asyncio
from node.utils import get_logger
from node.ollama.init_ollama import setup_ollama
from node.vllm.init_vllm import setup_vllm

logger = get_logger(__name__)

async def main():
    llm_backend = os.getenv("LLM_BACKEND", "ollama").lower()
    if llm_backend == "ollama":
        ollama_models = os.getenv("OLLAMA_MODELS", "").split(",")
        await setup_ollama(ollama_models)
    elif llm_backend == "vllm":
        vllm_model = os.getenv("VLLM_MODEL")
        if not vllm_model:
            logger.error("VLLM_MODEL environment variable is not set")
            return
        await setup_vllm(vllm_model)
    else:
        logger.error(f"Unsupported LLM backend: {llm_backend}")

if __name__ == "__main__":
    asyncio.run(main())