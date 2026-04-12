import os
import threading
from datetime import datetime

import cv2


class VideoRecorder:
    def __init__(self, output_dir: str, fps: float = 60.0):
        self.output_dir = output_dir
        self.fps = fps
        self._lock = threading.Lock()
        self._writer = None
        self._current_path = None

    def startRecording(self, frame_width: int, frame_height: int) -> str:
        with self._lock:
            if self._writer is not None:
                return self._current_path

            os.makedirs(self.output_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._current_path = os.path.join(self.output_dir, f"recording_{timestamp}.mp4")

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(
                self._current_path,
                fourcc,
                self.fps,
                (frame_width, frame_height),
            )

            if not self._writer.isOpened():
                self._writer.release()
                self._writer = None
                path = self._current_path
                self._current_path = None
                raise RuntimeError(f"Failed to open video writer for {path}")

            return self._current_path

    def writeFrame(self, frame) -> None:
        with self._lock:
            if self._writer is None:
                return
            self._writer.write(frame)

    def stopRecording(self) -> str | None:
        with self._lock:
            if self._writer is None:
                return None

            self._writer.release()
            self._writer = None

            path = self._current_path
            self._current_path = None
            return path

    def isRecording(self) -> bool:
        with self._lock:
            return self._writer is not None

    def getCurrentPath(self) -> str | None:
        with self._lock:
            return self._current_path