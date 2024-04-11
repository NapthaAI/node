import numpy as np
import cv2
import logging


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)
    return logger


logger = get_logger(__name__)


def infer(args):
    logger.info(f"Received args: {args}")
    # Create a blank 300x300 black image
    image = np.zeros((300, 300, 3), dtype="uint8")

    # Draw a green rectangle
    top_left_vertex = (50, 50)
    bottom_right_vertex = (250, 250)
    green_color = (0, 255, 0)
    cv2.rectangle(image, top_left_vertex, bottom_right_vertex, green_color, -1)

    # Draw a red circle
    center_coordinates = (150, 150)
    radius = 50
    red_color = (0, 0, 255)
    cv2.circle(image, center_coordinates, radius, red_color, -1)

    # Put white text
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_color = (255, 255, 255)
    cv2.putText(image, args.prompt, (70, 150), font, 1, text_color, 2, cv2.LINE_AA)

    # Save the image
    filename = f"{args.output_dir}/{args.prompt}.jpg"
    cv2.imwrite(filename, image)
    logger.info(f"Saved image to: {filename}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, default="test")
    parser.add_argument("--output_dir", type=str, default="/app/output")
    args = parser.parse_args()

    infer(args)

    # Log all environment variables
    import os

    logger.info(f"Environment variables: {os.environ}")
