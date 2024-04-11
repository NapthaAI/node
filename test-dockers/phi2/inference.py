import json
import logging
import argparse
from llama_cpp import Llama


def get_logger(__name__):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


logger = get_logger(__name__)

MODEL_PATH = "/app/model/models--TheBloke--phi-2-GGUF/snapshots/5a454d977c6438bb9fb2df233c8ca70f21c87420/phi-2.Q5_K_M.gguf"


def infer(args, model_path=MODEL_PATH):
    logger.info(f"Starting inference with args: {args}")
    logger.info("Loading model...")
    llm = Llama(model_path=model_path, chat_format="llama-2")

    logger.info("Generating response...")
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": args.system_prompt},
            {"role": "user", "content": args.user_prompt},
        ]
    )
    logger.info(response)

    # Save output to a json file
    filename = f"{args.output_dir}/output.json"
    with open(filename, "w") as f:
        f.write(json.dumps(response))

    logger.info("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--system_prompt", type=str, default="You are a story writing assistant."
    )
    parser.add_argument(
        "--user_prompt", type=str, default="write a story about llamas."
    )
    parser.add_argument("--output_dir", type=str, default="/app/output")
    args = parser.parse_args()
    infer(args)
