import sys
import torch
import logging
import argparse
from diffusers import StableDiffusionXLPipeline


def get_logger(name=__name__):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = get_logger()


def inference(args):
    pipeline_text2image = StableDiffusionXLPipeline.from_single_file(
        "https://huggingface.co/stabilityai/sdxl-turbo/blob/main/sd_xl_turbo_1.0_fp16.safetensors",
        torch_dtype=torch.float16,
    )

    # Set device
    if args.device is None:
        if torch.cuda.is_available():
            logger.info("Using CUDA")
            pipeline_text2image = pipeline_text2image.to("cuda")
        elif sys.platform == "darwin":
            logger.info("Using Metal")
            pipeline_text2image = pipeline_text2image.to("mps")
        else:
            logger.info("Using CPU")
            pipeline_text2image = pipeline_text2image.to("cpu")
    else:
        logger.info(f"Using {args.device}")
        pipeline_text2image = pipeline_text2image.to(args.device)

    image = pipeline_text2image(
        prompt=args.prompt, guidance_scale=0.0, num_inference_steps=1, seed=args.seed
    ).images[0]

    # Save image filename
    filename = f"{args.output_dir}/image_{args.seed}.png"
    image.save(filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--seed", type=int, default=42)
    # Add optional device argument - cuda, cpu, mps
    parser.add_argument("--device", type=str, default=None)
    args = parser.parse_args()
    inference(args)
