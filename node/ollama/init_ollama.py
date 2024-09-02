import asyncio
import platform
from node.utils import get_logger


logger = get_logger(__name__)


async def run(cmd):
    logger.info(f'Running command: {" ".join(cmd)}')
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()
    return stdout.decode().strip(), stderr.decode().strip()


async def install_ollama():
    operating_system = platform.system()
    if operating_system == "Darwin":
        logger.info(
            """\nOllama is not installed. Please install it manually.\nAutomated installation for macOS is not supported yet.\nhttps://ollama.ai/download"""
        )
        return False
    elif operating_system == "Linux":
        cmd = ["curl", "-sSf", "https://ollama.ai/install.sh", "|", "sh"]

    else:
        logger.error(f"Unsupported OS: {operating_system}")
        return False

    stdout, stderr = await run(cmd)
    logger.info(f"stdout: {stdout}")
    logger.info(f"stderr: {stderr}")

    return True


async def check_ollama():
    try:
        stdout, stderr = await run(["ollama", "-v"])
        logger.info(f"stdout: {stdout}")
        logger.info(f"stderr: {stderr}")
        return True
    except FileNotFoundError:
        return False


async def pull_model(model):
    try:
        stdout, stderr = await run(["ollama", "pull", model])
        logger.info(f"stdout: {stdout}")
        logger.info(f"stderr: {stderr}")
        return True
    except Exception as e:
        logger.error(f"Error while pulling model: {e}")
        return False


async def check_model(model):
    try:
        stdout, stderr = await run(["ollama", "list"])
        logger.info(f"stdout: {stdout}")
        logger.info(f"stderr: {stderr}")
        return True
    except Exception as e:
        logger.error(f"Error while checking model: {e}")
        return False


async def setup_ollama(ollama_models):
    if not await check_ollama():
        out = await install_ollama()

        if not out:
            return
        
    # wait for ollama to start
    await asyncio.sleep(20)

    for model in ollama_models:
        await pull_model(model)