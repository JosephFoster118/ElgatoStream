#!/usr/bin/env python3
import json
import os
import sys
import glob
import queue
import threading
import time
import signal
from PokemonOcr import PokemonOcr, ImageSectionParameters, PreprocessImage

# Set PulseAudio/PipeWire application properties so Discord can identify
# and capture this app's audio stream when screen-sharing.
os.environ.setdefault("PULSE_PROP_application.name", "Elgato Stream Viewer")
os.environ.setdefault("PULSE_PROP_application.process.id", str(os.getpid()))
os.environ.setdefault("PULSE_PROP_application.process.binary", "ElgatoStream")
os.environ.setdefault("PULSE_PROP_media.role", "game")

import cv2
import sounddevice as sd
from ScreenshotSaver import ScreenshotSaver
from VideoRecorder import VideoRecorder

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QSlider, QFormLayout, QSizePolicy, QDialog, QDialogButtonBox,
    QCheckBox, QSpinBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap

SAMPLE_RATE = 48000

RESOLUTIONS = {
    "640x480 (480p)":    (640,  480),
    "1280x720 (720p)":   (1280, 720),
    "1920x1080 (1080p)": (1920, 1080),
}


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class VideoWorker(QThread):
    frame_ready = Signal(QImage)
    frame_captured = Signal(object)

    def __init__(self, device, width, height):
        super().__init__()
        self.device = device
        self.width = width
        self.height = height
        self._running = True

    def run(self):
        cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        while self._running:
            ret, frame = cap.read()
            if ret:
                self.frame_captured.emit(frame.copy())
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                self.frame_ready.emit(img.copy())

        cap.release()

    def stop(self):
        self._running = False


class AudioWorker(QThread):
    def __init__(self, device, gain_getter, output_device=None):
        super().__init__()
        self.device = device
        self.output_device = output_device
        self.gain_getter = gain_getter
        self._running = True
        self._queue = queue.Queue(maxsize=10)

    def run(self):
        def input_cb(indata, frames, time, status):
            try:
                self._queue.put_nowait(indata.copy() * self.gain_getter())
            except queue.Full:
                pass

        def output_cb(outdata, frames, time, status):
            try:
                data = self._queue.get_nowait()
                outdata[: len(data)] = data
                if len(data) < len(outdata):
                    outdata[len(data) :] = 0
            except queue.Empty:
                outdata[:] = 0

        with sd.InputStream(
            device=self.device, channels=2, samplerate=SAMPLE_RATE,
            callback=input_cb, blocksize=1024,
        ):
            with sd.OutputStream(
                device=self.output_device, channels=2, samplerate=SAMPLE_RATE,
                callback=output_cb, blocksize=1024,
            ):
                while self._running:
                    sd.sleep(100)

    def stop(self):
        self._running = False


class OcrWorker(QThread):
    ocr_result = Signal(dict)

    def __init__(self, pokemon_names: list, section_group: str, locations_json: str):
        super().__init__()
        self._pokemon_names = pokemon_names
        self._section_group = section_group
        self._locations_json = locations_json
        self._frame = None
        self._frame_lock = threading.Lock()
        self._running = True

    def updateFrame(self, frame) -> None:
        with self._frame_lock:
            self._frame = frame.copy()

    def run(self):
        ocr = PokemonOcr(self._pokemon_names, gpu=True)
        ocr.addImageSectionParametersFromJson(self._section_group, self._locations_json)
        while self._running:
            with self._frame_lock:
                frame = self._frame
            if frame is not None:
                try:
                    results = ocr.ocrSections(frame, self._section_group)
                    self.ocr_result.emit(results)
                except Exception as e:
                    print(f"[OcrWorker] {e}")
            QThread.sleep(1)

    def stop(self):
        self._running = False

class PokemonStats():

    class PokemonStat:
        def __init__(self, name: str, types: list[str], stats: dict[str, int]):
            self.name = name
            self.types = types
            self.attack = stats.get("attack", 0)
            self.defense = stats.get("defense", 0)
            self.hp = stats.get("hp", 0)
            self.special_attack = stats.get("special-attack", 0)
            self.special_defense = stats.get("special-defense", 0)
            self.speed = stats.get("speed", 0)
            self.mega_name = None

        def hasMega(self) -> bool:
            return self.mega_name is not None

    def __init__(self, stats_json_path: str):
        with open(stats_json_path, "r") as f:
            data = json.load(f)
        self.stats = {}
        for p in data:
            name = p["name"]
            types = p["types"]
            stats = p["stats"]
            self.stats[name] = self.PokemonStat(name, types, stats)
            if name.endswith("-mega"):
                non_mega_name = name[:-5]
                if non_mega_name in self.stats:
                    self.stats[non_mega_name].mega_name = name

        #List all pokemon that have mega_name set and print their name and mega_name
        for p in self.stats.values():
            if p.hasMega():
                print(f"{p.name} has mega evolution: {p.mega_name}")

    def getStats(self, pokemon_name: str) -> dict | None:
        if pokemon_name in self.stats:
            return self.stats[pokemon_name]
        return None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def findElgatoAudio():
    for i, dev in enumerate(sd.query_devices()):
        if "elgato" in dev["name"].lower() and dev["max_input_channels"] > 0:
            print(f"Found Elgato audio device: [{i}] {dev['name']}")
            return i
    print("Warning: No Elgato audio device found, using system default.")
    return sd.default.device[0]


def findPulseOutput():
    """Find the 'pulse' ALSA output device so audio streams carry proper
    PulseAudio metadata (PID, app name) that Discord needs to capture them."""
    for i, dev in enumerate(sd.query_devices()):
        if dev["name"] == "pulse" and dev["max_output_channels"] > 0:
            print(f"Using PulseAudio output device: [{i}] {dev['name']}")
            return i
    return None


def listVideoDevices():
    """Return list of (path, label) for available V4L2 video devices."""
    devices = []
    for path in sorted(glob.glob("/dev/video*")):
        dev_name = path.split("/")[-1]
        try:
            with open(f"/sys/class/video4linux/{dev_name}/name") as f:
                card = f.read().strip()
            label = f"{card}  ({path})"
        except OSError:
            label = path
        devices.append((path, label))
    return devices


def listAudioInputDevices():
    """Return list of (index, label) for audio input devices."""
    result = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            result.append((i, f"[{i}] {dev['name']}"))
    return result


def listAudioOutputDevices():
    """Return list of (index, label) for audio output devices."""
    result = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] > 0:
            result.append((i, f"[{i}] {dev['name']}"))
    return result


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Video device
        self.video_combo = QComboBox()
        for path, label in listVideoDevices():
            self.video_combo.addItem(label, path)
        idx = self.video_combo.findData(settings["video_dev"])
        if idx >= 0:
            self.video_combo.setCurrentIndex(idx)
        form.addRow("Video device:", self.video_combo)

        # Audio input device
        self.audio_combo = QComboBox()
        for dev_idx, label in listAudioInputDevices():
            self.audio_combo.addItem(label, dev_idx)
        idx = self.audio_combo.findData(settings["audio_dev"])
        if idx >= 0:
            self.audio_combo.setCurrentIndex(idx)
        form.addRow("Audio input:", self.audio_combo)

        # Audio output device
        self.audio_out_combo = QComboBox()
        self.audio_out_combo.addItem("System default", None)
        for dev_idx, label in listAudioOutputDevices():
            self.audio_out_combo.addItem(label, dev_idx)
        idx = self.audio_out_combo.findData(settings.get("audio_out_dev"))
        if idx >= 0:
            self.audio_out_combo.setCurrentIndex(idx)
        form.addRow("Audio output:", self.audio_out_combo)

        # Resolution
        self.res_combo = QComboBox()
        for label in RESOLUTIONS:
            self.res_combo.addItem(label)
        cur = f"{settings['width']}x{settings['height']}"
        for i in range(self.res_combo.count()):
            if self.res_combo.itemText(i).startswith(cur):
                self.res_combo.setCurrentIndex(i)
                break
        form.addRow("Resolution:", self.res_combo)

        self.fps_enabled = QCheckBox("Show FPS counter")
        self.fps_enabled.setChecked(settings.get("show_fps", False))
        form.addRow("FPS overlay:", self.fps_enabled)

        self.fps_font_size = QSpinBox()
        self.fps_font_size.setRange(10, 48)
        self.fps_font_size.setValue(settings.get("fps_font_size", 18))
        self.fps_font_size.setSuffix(" px")
        form.addRow("FPS font size:", self.fps_font_size)

        self.fps_opacity = QSpinBox()
        self.fps_opacity.setRange(10, 100)
        self.fps_opacity.setValue(int(settings.get("fps_opacity", 0.75) * 100))
        self.fps_opacity.setSuffix(" %")
        form.addRow("FPS background opacity:", self.fps_opacity)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def getSettings(self):
        w, h = RESOLUTIONS[self.res_combo.currentText()]
        return {
            "video_dev": self.video_combo.currentData(),
            "audio_dev": self.audio_combo.currentData(),
            "audio_out_dev": self.audio_out_combo.currentData(),
            "width": w,
            "height": h,
            "show_fps": self.fps_enabled.isChecked(),
            "fps_font_size": self.fps_font_size.value(),
            "fps_opacity": self.fps_opacity.value() / 100.0,
        }


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        #Pokemon stats
        self.pokemon_stats = PokemonStats("resources/pokemon_stats.json")

        #Window setup
        self.setWindowTitle("Elgato Stream Viewer")
        self.resize(1280, 800)
        self._screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
        self._recordings_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
        self._screenshot_saver = ScreenshotSaver(self._screenshots_dir)
        self._video_recorder = VideoRecorder(self._recordings_dir)

        self._settings = {
            "video_dev": "/dev/video0",
            "audio_dev": findElgatoAudio(),
            "audio_out_dev": findPulseOutput(),
            "width": 1920,
            "height": 1080,
            "show_fps": False,
            "fps_font_size": 18,
            "fps_opacity": 0.75,
        }
        self._gain = 1.0
        self._fullscreen = False
        self._video_worker = None
        self._audio_worker = None
        self._ocr_worker = None
        self._fps_last_time = None
        self._fps_frame_count = 0
        self._latest_frame = None
        self._last_frame_size = None
        self._record_indicator_visible = True

        base_dir = os.path.dirname(os.path.abspath(__file__))
        pokemon_names_path = os.path.join(base_dir, "resources", "pokemon_names.json")
        with open(pokemon_names_path) as f:
            self._pokemon_names = json.load(f)
        self._ocr_locations_json = os.path.join(base_dir, "resources", "singles_pokemon_locations.json")

        # Auto-hide toolbar timer (2 s of inactivity)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(2000)
        self._hide_timer.timeout.connect(self._hideToolbar)

        # -- Layout --
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Video pane
        self.video_label = QLabel("Connecting…")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setMinimumSize(1, 1)
        self.video_label.setStyleSheet("background: black; color: #888; font-size: 18px;")
        self.video_label.setMouseTracking(True)

        self.fps_label = QLabel("FPS: --", self.video_label)
        self.fps_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.fps_label.move(12, 12)
        self.fps_label.hide()

        self.record_indicator = QLabel("REC", self.video_label)
        self.record_indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.record_indicator.setStyleSheet(
            "color: white;"
            "font-size: 12px;"
            "font-weight: bold;"
            "background-color: rgba(210, 32, 32, 220);"
            "padding: 3px 10px;"
            "border-radius: 10px;"
        )
        self.record_indicator.adjustSize()
        self.record_indicator.hide()

        self._record_indicator_timer = QTimer(self)
        self._record_indicator_timer.setInterval(500)
        self._record_indicator_timer.timeout.connect(self._blinkRecordingIndicator)

        root.addWidget(self.video_label)
        central.setMouseTracking(True)
        self.setMouseTracking(True)

        # Toolbar
        self.toolbar = QWidget()
        toolbar = self.toolbar
        toolbar.setFixedHeight(50)
        toolbar.setMouseTracking(True)
        toolbar.setStyleSheet("background: #1e1e1e; color: white;")
        tbl = QHBoxLayout(toolbar)
        tbl.setContentsMargins(10, 4, 10, 4)

        self.fs_btn = QPushButton("⛶  Fullscreen")
        self.fs_btn.setFixedHeight(36)
        self.fs_btn.clicked.connect(self.toggleFullscreen)
        tbl.addWidget(self.fs_btn)

        tbl.addStretch()

        tbl.addWidget(QLabel("Volume:"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 200)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(160)
        self.vol_slider.setToolTip("0 – 200 %")
        self.vol_slider.valueChanged.connect(self._onVolume)
        tbl.addWidget(self.vol_slider)

        self.vol_label = QLabel("100 %")
        self.vol_label.setFixedWidth(44)
        tbl.addWidget(self.vol_label)

        tbl.addSpacing(16)

        self.record_btn = QPushButton("Record")
        self.record_btn.setFixedHeight(36)
        self.record_btn.clicked.connect(self.startRecording)
        tbl.addWidget(self.record_btn)

        self.stop_record_btn = QPushButton("Stop Recording")
        self.stop_record_btn.setFixedHeight(36)
        self.stop_record_btn.clicked.connect(self.stopRecording)
        self.stop_record_btn.setEnabled(False)
        tbl.addWidget(self.stop_record_btn)

        self.recording_label = QLabel("Not recording")
        self.recording_label.setFixedWidth(180)
        tbl.addWidget(self.recording_label)

        tbl.addSpacing(16)

        self.screenshot_btn = QPushButton("Screenshot")
        self.screenshot_btn.setFixedHeight(36)
        self.screenshot_btn.clicked.connect(self.saveScreenshot)
        tbl.addWidget(self.screenshot_btn)

        self.screenshot_label = QLabel("No screenshot")
        self.screenshot_label.setFixedWidth(220)
        tbl.addWidget(self.screenshot_label)

        tbl.addSpacing(16)

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.setFixedHeight(36)
        settings_btn.clicked.connect(self.openSettings)
        tbl.addWidget(settings_btn)

        root.addWidget(toolbar)

        self._startWorkers()
        self._applyFpsOverlayStyle()
        self._hide_timer.start()


    # -- Workers --

    def _getGain(self):
        return self._gain

    def _startWorkers(self):
        self._stopWorkers()
        s = self._settings
        self._fps_last_time = None
        self._fps_frame_count = 0

        self._video_worker = VideoWorker(s["video_dev"], s["width"], s["height"])
        self._video_worker.frame_ready.connect(self._onFrame)
        self._video_worker.frame_captured.connect(self._onFrameCaptured)
        self._video_worker.start()

        self._audio_worker = AudioWorker(s["audio_dev"], self._getGain, s.get("audio_out_dev"))
        self._audio_worker.start()

        self._ocr_worker = OcrWorker(self._pokemon_names, "singles", self._ocr_locations_json)
        self._ocr_worker.ocr_result.connect(self._onOcrResult)
        self._ocr_worker.start()

    def _stopWorkers(self):
        for w in (self._video_worker, self._audio_worker, self._ocr_worker):
            if w:
                w.stop()
                w.wait(2000)
        self._video_worker = None
        self._audio_worker = None
        self._ocr_worker = None

    # -- Slots --

    def _onFrame(self, image: QImage):
        pixmap = QPixmap.fromImage(image).scaled(
            self.video_label.size(), Qt.KeepAspectRatio, Qt.FastTransformation
        )
        self.video_label.setPixmap(pixmap)

        if self._settings.get("show_fps", False):
            now = time.perf_counter()
            self._fps_frame_count += 1
            if self._fps_last_time is None:
                self._fps_last_time = now
            else:
                elapsed = now - self._fps_last_time
                if elapsed >= 0.5:
                    fps = self._fps_frame_count / elapsed
                    self.fps_label.setText(f"FPS: {fps:.1f}")
                    self.fps_label.adjustSize()
                    self._fps_last_time = now
                    self._fps_frame_count = 0

    def _onFrameCaptured(self, frame):
        self._latest_frame = frame.copy()
        self._last_frame_size = (frame.shape[1], frame.shape[0])
        self._video_recorder.writeFrame(frame)
        if self._ocr_worker is not None:
            self._ocr_worker.updateFrame(frame)

    def _onOcrResult(self, results: dict) -> None:
        for section, (name, score) in results.items():
            print(f"[OCR] {section}: {name} (score: {score:.2f})")
            if score > 0.85 and name is not None:
                lowercase_name = name.lower()
                stats = self.pokemon_stats.getStats(lowercase_name)
                if stats:
                    print(f"  Types: {', '.join(stats.types)}")
                    print(f"  HP: {stats.hp}, Attack: {stats.attack}, Defense: {stats.defense}")
                    print(f"  Sp. Atk: {stats.special_attack}, Sp. Def: {stats.special_defense}, Speed: {stats.speed}")

    def _applyFpsOverlayStyle(self):
        alpha = max(0.1, min(1.0, self._settings.get("fps_opacity", 0.75)))
        alpha_255 = int(alpha * 255)
        font_size = self._settings.get("fps_font_size", 18)
        self.fps_label.setStyleSheet(
            "color: white;"
            f"font-size: {font_size}px;"
            f"background-color: rgba(0, 0, 0, {alpha_255});"
            "padding: 4px 8px;"
            "border-radius: 4px;"
        )
        self.fps_label.adjustSize()
        self.fps_label.setVisible(self._settings.get("show_fps", False))

    def resizeEvent(self, event):
        self.fps_label.move(12, 12)
        self.record_indicator.adjustSize()
        self.record_indicator.move(
            self.video_label.width() - self.record_indicator.width() - 12,
            12,
        )
        super().resizeEvent(event)

    def _onVolume(self, value: int):
        self._gain = value / 100.0
        self.vol_label.setText(f"{value} %")

    def startRecording(self):
        if self._video_recorder.isRecording():
            return

        if self._last_frame_size is None:
            frame_width = self._settings["width"]
            frame_height = self._settings["height"]
        else:
            frame_width, frame_height = self._last_frame_size

        path = self._video_recorder.startRecording(frame_width, frame_height)
        self.record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(True)
        self.recording_label.setText(f"Recording: {os.path.basename(path)}")
        self._setRecordingIndicator(True)

    def stopRecording(self):
        path = self._video_recorder.stopRecording()
        if path is None:
            return

        self.record_btn.setEnabled(True)
        self.stop_record_btn.setEnabled(False)
        self.recording_label.setText(f"Saved: {os.path.basename(path)}")
        self._setRecordingIndicator(False)

    def _setRecordingIndicator(self, is_recording: bool):
        if is_recording:
            self._record_indicator_visible = True
            self.record_indicator.show()
            self.record_indicator.adjustSize()
            self.record_indicator.move(
                self.video_label.width() - self.record_indicator.width() - 12,
                12,
            )
            self._record_indicator_timer.start()
        else:
            self._record_indicator_timer.stop()
            self.record_indicator.hide()

    def _blinkRecordingIndicator(self):
        self._record_indicator_visible = not self._record_indicator_visible
        self.record_indicator.setVisible(self._record_indicator_visible)

    def saveScreenshot(self):
        if self._latest_frame is None:
            self.screenshot_label.setText("No frame available")
            return

        path = self._screenshot_saver.saveFrame(self._latest_frame)
        self.screenshot_label.setText(f"Saved: {os.path.basename(path)}")

    def toggleFullscreen(self):
        if self._fullscreen:
            self.showNormal()
            self.fs_btn.setText("⛶  Fullscreen")
            self._fullscreen = False
        else:
            self.showFullScreen()
            self.fs_btn.setText("✕  Exit Fullscreen")
            self._fullscreen = True

    def _hideToolbar(self):
        if self.toolbar.underMouse():
            self._hide_timer.start()
            return
        self.toolbar.hide()

    def _showToolbar(self):
        self.toolbar.show()
        self._hide_timer.start()

    def mouseMoveEvent(self, event):
        self._showToolbar()
        super().mouseMoveEvent(event)

    def changeEvent(self, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.ActivationChange:
            if not self.isActiveWindow():
                self._hide_timer.stop()
                self._hideToolbar()
            else:
                self._showToolbar()
        super().changeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self._fullscreen:
            self.toggleFullscreen()
        super().keyPressEvent(event)

    def openSettings(self):
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec():
            new = dlg.getSettings()
            needs_restart = any(
                self._settings[k] != new[k]
                for k in ("video_dev", "audio_dev", "audio_out_dev", "width", "height")
            )
            self._settings.update(new)
            self._applyFpsOverlayStyle()
            if needs_restart:
                self.stopRecording()
                self._startWorkers()

    def closeEvent(self, event):
        self.stopRecording()
        self._stopWorkers()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()

    def handleSigInt(signum, frame):
        win.close()

    signal.signal(signal.SIGINT, handleSigInt)

    # Use a timer to allow signal handling
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    win.show()
    sys.exit(app.exec())