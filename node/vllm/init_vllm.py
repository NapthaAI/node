import os
import subprocess


def setup_vllm(model):
    subprocess.run(["vllm", "serve", model], check=True)