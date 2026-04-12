import os
import threading
from datetime import datetime

import cv2


class ScreenshotSaver:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self._lock = threading.Lock()

    def saveFrame(self, frame) -> str:
        with self._lock:
            os.makedirs(self.output_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = os.path.join(self.output_dir, f"screenshot_{timestamp}.png")

            if not cv2.imwrite(path, frame):
                raise RuntimeError(f"Failed to save screenshot to {path}")

            return path