import numpy as np
import cv2
import logging
from glob import glob


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


def infer(prompt, input_dir=None, output_dir=None):
    logger.info(f"Received args: {args}")
    if input_dir is None:
        # Create a blank 300x300 black image
        image = np.zeros((300, 300, 3), dtype="uint8")
    else:
        # Read the first image in the input directory
        try:
            paths = glob(f"{input_dir}/*")
            image = cv2.imread(paths[0])
        except Exception as e:
            logger.error(f"Error reading input directory: {e}")
            raise e

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
    cv2.putText(image, prompt, (70, 150), font, 1, text_color, 2, cv2.LINE_AA)

    # Save the image
    filename = f"{output_dir}/{prompt}.jpg"
    cv2.imwrite(filename, image)
    logger.info(f"Saved image to: {filename}")


if __name__ == "__main__":
    import argparse
    import os

    logger.info(f"Environment variables: {os.environ}")

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--prompt", type=str, default="test")
    parser.add_argument("-i", "--input_dir", type=str, default="/app/input")
    parser.add_argument("-o", "--output_dir", type=str, default="/app/output")
    args = parser.parse_args()

    infer(args.prompt, args.input_dir, args.output_dir)

