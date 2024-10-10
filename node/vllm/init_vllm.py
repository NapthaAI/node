import os
import logging
import subprocess
from node.config import GPU

logger = logging.getLogger(__name__)

if GPU == "false":
    GPU = False
elif GPU == "true":
    GPU = True

logger.info(f"GPU: {GPU}")


def setup_vllm(model):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    chat_template_path = os.path.join(current_dir, "chatml.jinja")
    if GPU:
        command = [
            "vllm",
            "serve",
            model,
            "--max-model-len",
            "2500",
            "--chat-template",
            chat_template_path,
        ]
    else:
        command = ["vllm", "serve", model, "--chat-template", chat_template_path]
    subprocess.run(command, check=True)
