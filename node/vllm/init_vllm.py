import os
import subprocess

def setup_vllm(model):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    chat_template_path = os.path.join(current_dir, "chatml.jinja")
    
    command = [
        "vllm", "serve", model,
        "--max-model-len", "2500",
        "--chat-template", chat_template_path
    ]
    
    subprocess.run(command, check=True)