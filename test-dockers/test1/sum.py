# sum.py
import os
import time
import argparse
import logging


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


logger = get_logger(__name__)


def main(args):
    t = 5
    while True:
        print(f"Print round {t}")
        logger.info(f"Logger round {t}")

        if t == 0:
            break

        t -= 1

        # sleep for 1 seconds
        time.sleep(1)

    num1 = args.num1
    num2 = args.num2

    print(f"Print: The sum of {num1} and {num2} is {num1 + num2}")
    logger.info(f"Logger: The sum of {num1} and {num2} is {num1 + num2}")

    # Print env variables
    env1 = os.getenv("env1", "default_env1")
    env2 = os.getenv("env2", "default_env2")
    print(f"env1: {env1}")
    print(f"env2: {env2}")
    logger.info(f"env1: {env1}")
    logger.info(f"env2: {env2}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sum two numbers")
    parser.add_argument("--num1", type=int, help="first number")
    parser.add_argument("--num2", type=int, help="second number")
    args = parser.parse_args()

    print(f"num1: {args.num1}")
    print(f"num2: {args.num2}")

    main(args)
