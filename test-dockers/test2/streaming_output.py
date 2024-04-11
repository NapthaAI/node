# streaming_output.py
import time

counter = 0
while True:
    print(f"Message {counter}")
    time.sleep(1)  # Delay for 1 second
    counter += 1
