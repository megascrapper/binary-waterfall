#!/usr/bin/env python3

import os
import sys
from enum import Enum
import yaml
import re
import shutil
import math
import wave
import pydub
from moviepy.editor import ImageSequenceClip, AudioFileClip
import numpy as np
import time
import tempfile
import webbrowser
from proglog import ProgressBarLogger
from PIL import Image, ImageOps
from PyQt5.QtCore import Qt, QUrl, QTimer, QSize
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QGridLayout, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton,
    QFileDialog, QAction,
    QDialog, QDialogButtonBox, QComboBox, QLineEdit, QCheckBox,
    QSpinBox, QDoubleSpinBox,
    QMessageBox,
    QAbstractButton,
    QSlider, QDial,
    QStyle,
    QProgressDialog
)
from PyQt5.QtGui import (
    QImage, QPixmap, QIcon,
    QPainter
)
import multiprocessing
from itertools import repeat
from typing import Optional

# TODO: temporary imports
import cProfile

# Test if this is a PyInstaller executable or a .py file
if getattr(sys, 'frozen', False):
    IS_EXE = True
    PROG_FILE = sys.executable
    PROG_PATH = os.path.dirname(PROG_FILE)
    PATH = sys._MEIPASS
else:
    IS_EXE = False
    PROG_FILE = os.path.realpath(__file__)
    PROG_PATH = os.path.dirname(PROG_FILE)
    PATH = PROG_PATH

# Read program version file
VERSION_FILE = os.path.join(PATH, "version.yml")
with open(VERSION_FILE, "r") as f:
    version_file_dict = yaml.safe_load(f)

    VERSION = version_file_dict["Version"]
    DESCRIPTION = version_file_dict["FileDescription"]
    TITLE = version_file_dict["InternalName"]
    LONG_TITLE = version_file_dict["ProductName"]
    COPYRIGHT = version_file_dict["LegalCopyright"]

    del version_file_dict

# The path to the program's resources
RESOURCE_PATH = os.path.join(PATH, "resources")

# A dict to store icon locations
ICON_PATH = {
    "program": os.path.join(PATH, "icon.png"),
    "button": {
        "play": {
            "base": os.path.join(RESOURCE_PATH, "play.png"),
            "clicked": os.path.join(RESOURCE_PATH, "playC.png"),
            "hover": os.path.join(RESOURCE_PATH, "playH.png")
        },
        "pause": {
            "base": os.path.join(RESOURCE_PATH, "pause.png"),
            "clicked": os.path.join(RESOURCE_PATH, "pauseC.png"),
            "hover": os.path.join(RESOURCE_PATH, "pauseH.png")
        },
        "back": {
            "base": os.path.join(RESOURCE_PATH, "back.png"),
            "clicked": os.path.join(RESOURCE_PATH, "backC.png"),
            "hover": os.path.join(RESOURCE_PATH, "backH.png")
        },
        "forward": {
            "base": os.path.join(RESOURCE_PATH, "forward.png"),
            "clicked": os.path.join(RESOURCE_PATH, "forwardC.png"),
            "hover": os.path.join(RESOURCE_PATH, "forwardH.png")
        },
        "restart": {
            "base": os.path.join(RESOURCE_PATH, "restart.png"),
            "clicked": os.path.join(RESOURCE_PATH, "restartC.png"),
            "hover": os.path.join(RESOURCE_PATH, "restartH.png")
        }
    },
    "volume": {
        "base": os.path.join(RESOURCE_PATH, "volume.png"),
        "mute": os.path.join(RESOURCE_PATH, "mute.png")
    },
    "watermark": os.path.join(RESOURCE_PATH, "watermark.png")
}


# Get licensing status
class KeyValidate:
    def __init__(self,
                 program_id
                 ):
        self.set_program_id(program_id)

    def set_program_id(self, program_id):
        self.program_id = program_id.strip()
        self.program_int = 0
        for x in self.program_id:
            self.program_int += ord(x)
        self.program_int %= 0x10000
        self.program_offset = self.program_int % 5

    def get_program_hex(self):
        hex_string = hex(self.program_int)[2:].upper()
        while len(hex_string) < 4:
            hex_string = "0" + hex_string
        return hex_string

    def get_magic(self, hex_string=None):
        if hex_string is None:
            hex_string = self.get_program_hex()
        int_list = [int(x, 16) for x in hex_string]
        offset = int_list[0]
        magic_list = [(x - offset) % 16 for x in int_list]
        magic = "".join([hex(x)[2:] for x in magic_list]).upper()

        return magic

    def is_key_valid(self, key):
        if not re.match(r"^[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}$", key):
            return False

        groups = key.split("-")
        magic_hex = ""
        for idx, group in enumerate(groups):
            key_idx = (self.program_int - idx) % 5
            magic_hex += group[key_idx]

        if self.get_magic(magic_hex) == self.get_magic():
            return True
        else:
            return False


USER_DIR = os.path.expanduser("~")
if sys.platform == "win32":
    APPDATA_DIR = os.path.join(USER_DIR, "AppData", "Roaming")
elif sys.platform == "linux":
    APPDATA_DIR = os.path.join(USER_DIR, ".local", "share")
elif sys.platform == "darwin":
    APPDATA_DIR = os.path.join(USER_DIR, "Library", "Application Support")
else:
    APPDATA_DIR = USER_DIR
DATA_DIR = os.path.join(APPDATA_DIR, TITLE)
KEY_FILE = os.path.join(DATA_DIR, "key")
if os.path.isfile(KEY_FILE):
    with open(KEY_FILE, "r") as f:
        SERIAL_KEY = f.read()
    SERIAL_KEY = SERIAL_KEY.strip("\n").strip("\r").strip()
    IS_REGISTERED = KeyValidate(TITLE).is_key_valid(SERIAL_KEY)

    if not IS_REGISTERED:
        os.remove(KEY_FILE)
        SERIAL_KEY = None
else:
    IS_REGISTERED = False
    SERIAL_KEY = None
if not IS_EXE:
    IS_REGISTERED = True

DONATE_URL = "https://www.patreon.com/nimaid"
REGISTER_URL = "https://www.patreon.com/nimaid/shop/binary-waterfall-pro-serial-key-license-69386"
PROJECT_URL = "https://github.com/nimaid/binary-waterfall"


# Define some stateless helper functions used throught the program
def get_size_for_fit_frame(content_size, frame_size):
    content_width, content_height = content_size
    frame_width, frame_height = frame_size

    # First, figure out which dim is limiting
    aspect_ratio = content_width / content_height
    height_if_limit_width = round(frame_width / aspect_ratio)
    width_if_limit_height = round(frame_height * aspect_ratio)
    if height_if_limit_width > frame_height:
        limit_width = False
    else:
        limit_width = True

    # Now, compute the new content size
    if limit_width:
        fit_width = frame_width
        fit_height = height_if_limit_width
    else:
        fit_width = width_if_limit_height
        fit_height = frame_height

    fit_size = (fit_width, fit_height)

    result = {
        "size": fit_size,
        "limit_width": limit_width
    }

    return result


def fit_to_frame(
        image,
        frame_size,
        scaling=Image.NEAREST,
        transparent=False
):
    # Get new content size
    fit_settings = get_size_for_fit_frame(
        content_size=image.size,
        frame_size=frame_size
    )
    content_size = fit_settings["size"]

    content_width, content_height = content_size
    frame_width, frame_height = frame_size

    # Actually scale the content
    resized_content = image.resize(content_size, scaling)

    # Make a black image
    if transparent:
        resized = Image.new(
            mode="RGBA",
            size=frame_size,
            color=(0, 0, 0, 0)
        )
    else:
        resized = Image.new(
            mode="RGBA",
            size=frame_size,
            color=(0, 0, 0, 255)
        )

    # Paste the content onto the background
    if fit_settings["limit_width"]:
        paste_x = 0
        paste_y = round((frame_height - content_height) / 2)
    else:
        paste_x = round((frame_width - content_width) / 2)
        paste_y = 0
    resized.paste(resized_content, (paste_x, paste_y), resized_content)

    return resized


# Binary Waterfall abstraction class
#   Provides an abstract object for converting binary files
#   into audio files and image frames. This object does not
#   track time or handle playback, it only provides resources
#   to other code in order to produce the videos
class BinaryWaterfall:
    def __init__(self,
                 filename=None,
                 width=48,
                 height=48,
                 color_format_string="bgrx",
                 num_channels=1,
                 sample_bytes=1,
                 sample_rate=32000,
                 volume=100
                 ):
        self.temp_dir = tempfile.mkdtemp()

        self.audio_filename = None  # Pre-init this to make sure delete_audio works
        self.set_filename(filename=filename)

        self.set_dims(
            width=width,
            height=height
        )

        self.set_color_format(color_format_string=color_format_string)

        self.set_audio_settings(
            num_channels=num_channels,
            sample_bytes=sample_bytes,
            sample_rate=sample_rate,
            volume=volume
        )

    # def __del__(self):
    #     self.cleanup()

    def set_filename(self, filename):
        # Delete current audio file if it exists
        self.delete_audio()

        if filename is None:
            # Reset all vars
            self.filename = None
            self.bytes = None
            self.total_bytes = None
            self.audio_filename = None
            return

        if not os.path.isfile(filename):
            raise FileNotFoundError(f"File not found: \"{filename}\"")

        self.filename = os.path.realpath(filename)

        # Load bytes
        with open(self.filename, "rb") as f:
            self.bytes = f.read()
        self.total_bytes = len(self.bytes)

        # Compute audio file name
        file_path, file_main_name = os.path.split(self.filename)
        self.audio_filename = os.path.join(
            self.temp_dir,
            file_main_name + os.path.extsep + "wav"
        )

    class ColorFmtCode(Enum):
        RED = "r"
        GREEN = "g"
        BLUE = "b"
        WHITE = "w"
        UNUSED = "x"
        VALID_OPTIONS = "rgbwx"

    class ColorModeCode(Enum):
        GRAYSCALE = 0
        RGB = 1

    def set_dims(self, width, height):
        if width < 4:
            raise ValueError("Visualization width must be at least 4")

        if height < 4:
            raise ValueError("Visualization height must be at least 4")

        self.width = width
        self.height = height
        self.dim = (self.width, self.height)

    def parse_color_format(self, color_format_string):
        result = {
            "is_valid": True
        }

        color_format_string = color_format_string.strip().lower()

        red_count = color_format_string.count(self.ColorFmtCode.RED.value)
        green_count = color_format_string.count(self.ColorFmtCode.GREEN.value)
        blue_count = color_format_string.count(self.ColorFmtCode.BLUE.value)
        white_count = color_format_string.count(self.ColorFmtCode.WHITE.value)
        unused_count = color_format_string.count(self.ColorFmtCode.UNUSED.value)

        rgb_count = red_count + green_count + blue_count

        if white_count > 0:
            color_mode = self.ColorModeCode.GRAYSCALE

            if rgb_count > 0:
                result["is_valid"] = False
                result[
                    "message"] = (f"When using the grayscale mode formatter \"{self.ColorFmtCode.WHITE.value}\", "
                                  f"you cannot use any of the RGB mode formatters \"{self.ColorFmtCode.RED.value}\", "
                                  f"\"{self.ColorFmtCode.GREEN.value}\", or \"{self.ColorFmtCode.BLUE.value}\"")
                return result

            if white_count > 1:
                result["is_valid"] = False
                result[
                    "message"] = (f"Exactly 1 white channel format specifier \"{self.ColorFmtCode.WHITE.value}\" "
                                  f"needed, but {white_count} were given in format string \"{color_format_string}\"")
                return result
        else:
            color_mode = self.ColorModeCode.RGB

            if rgb_count < 1:
                result["is_valid"] = False
                result[
                    "message"] = (f"A minimum of 1 color format specifer (\"{self.ColorFmtCode.RED.value}\", "
                                  f"\"{self.ColorFmtCode.GREEN.value}\", \"{self.ColorFmtCode.BLUE.value}\", "
                                  f"or \"{self.ColorFmtCode.WHITE.value}\") "
                                  f"is required, but none were given in format string \"{color_format_string}\"")
                return result

            if red_count > 1:
                result["is_valid"] = False
                result[
                    "message"] = (f"Exactly 1 red channel format specifier \"{self.ColorFmtCode.RED.value}\" "
                                  f"allowed, but {red_count} were given in format string \"{color_format_string}\"")
                return result

            if green_count > 1:
                result["is_valid"] = False
                result[
                    "message"] = (f"Exactly 1 green channel format specifier \"{self.ColorFmtCode.GREEN.value}\" "
                                  f"allowed, but {green_count} were given in format string \"{color_format_string}\"")
                return result

            if blue_count > 1:
                result["is_valid"] = False
                result[
                    "message"] = (f"Exactly 1 blue channel format specifier \"{self.ColorFmtCode.BLUE.value}\" "
                                  f"allowed, but {blue_count} were given in format string \"{color_format_string}\"")
                return result

        color_format_list = list()
        for c in color_format_string:
            if c not in self.ColorFmtCode.VALID_OPTIONS.value:
                result["is_valid"] = False
                result[
                    "message"] = (f"Color formatting codes only accept \"{self.ColorFmtCode.RED.value}\" = red, "
                                  f"\"{self.ColorFmtCode.GREEN.value}\" = green, "
                                  f"\"{self.ColorFmtCode.BLUE.value}\" = blue, "
                                  f"\"{self.ColorFmtCode.WHITE.value}\" = white, "
                                  f"\"{self.ColorFmtCode.UNUSED.value}\" = unused")
                return result
            if c == self.ColorFmtCode.RED.value:
                color_format_list.append(self.ColorFmtCode.RED)
            elif c == self.ColorFmtCode.GREEN.value:
                color_format_list.append(self.ColorFmtCode.GREEN)
            elif c == self.ColorFmtCode.BLUE.value:
                color_format_list.append(self.ColorFmtCode.BLUE)
            elif c == self.ColorFmtCode.WHITE.value:
                color_format_list.append(self.ColorFmtCode.WHITE)
            elif c == self.ColorFmtCode.UNUSED.value:
                color_format_list.append(self.ColorFmtCode.UNUSED)

        result["used_color_bytes"] = rgb_count + white_count
        result["unused_color_bytes"] = unused_count
        result["color_bytes"] = result["used_color_bytes"] + result["unused_color_bytes"]
        result["color_mode"] = color_mode
        result["color_format"] = color_format_list

        return result

    def set_color_format(self, color_format_string):
        parsed_string = self.parse_color_format(color_format_string)

        if not parsed_string["is_valid"]:
            raise ValueError(parsed_string["message"])

        self.used_color_bytes = parsed_string["used_color_bytes"]
        self.unused_color_bytes = parsed_string["unused_color_bytes"]
        self.color_bytes = parsed_string["color_bytes"]
        self.color_format = parsed_string["color_format"]

    def get_color_format_string(self):
        color_format_string = ""
        for x in self.color_format:
            color_format_string += x.value

        return color_format_string

    def is_color_format_valid(self, color_format_string):
        return self.parse_color_format(color_format_string)["is_valid"]

    def set_audio_settings(self,
                           num_channels,
                           sample_bytes,
                           sample_rate,
                           volume
                           ):
        if num_channels not in [1, 2]:
            raise ValueError("Invalid number of audio channels, must be either 1 or 2")

        if sample_bytes not in [1, 2, 3, 4]:
            raise ValueError("Invalid sample size (bytes), must be either 1, 2, 3, or 4")

        if sample_rate < 1:
            raise ValueError("Invalid sample rate, must be at least 1")

        if volume < 0 or volume > 100:
            raise ValueError("Volume must be between 0 and 100")

        self.num_channels = num_channels
        self.sample_bytes = sample_bytes
        self.sample_rate = sample_rate
        self.volume = volume

        # Re-compute audio file
        self.compute_audio()

    def delete_audio(self):
        if self.audio_filename == None:
            # Do nothing
            return
        try:
            os.remove(self.audio_filename)
        except FileNotFoundError:
            pass

    def get_audio_length(self):
        audio_length = pydub.AudioSegment.from_file(self.audio_filename).duration_seconds
        audio_length_ms = math.ceil(audio_length * 1000)

        return audio_length_ms

    def compute_audio(self):
        if self.filename == None:
            # If there is no file set, reset the vars
            self.audio_length_ms = None
            return

        # Delete current file if it exists
        self.delete_audio()

        # Compute the new file (full volume)
        with wave.open(self.audio_filename, "wb") as f:
            f.setnchannels(self.num_channels)
            f.setsampwidth(self.sample_bytes)
            f.setframerate(self.sample_rate)
            f.writeframesraw(self.bytes)

        if self.volume != 100:
            # Reduce the audio volume
            factor = self.volume / 100
            audio = pydub.AudioSegment.from_file(file=self.audio_filename, format="wav")
            audio += pydub.audio_segment.ratio_to_db(factor)
            temp_filename = self.audio_filename + ".temp"
            audio.export(temp_filename, format="wav")
            self.delete_audio()
            shutil.move(temp_filename, self.audio_filename)

        # Get audio length
        self.audio_length_ms = self.get_audio_length()

    def change_filename(self, new_filename):
        self.set_filename(new_filename)
        self.compute_audio()

    def get_address(self, ms):
        address_block_size = self.width * self.color_bytes
        total_blocks = math.ceil(self.total_bytes / address_block_size)
        address_block_offset = round(ms * total_blocks / self.audio_length_ms)
        return address_block_offset * address_block_size

    # A 1D Python byte string
    def get_frame_bytestring(self, ms):
        picture_bytes = bytes()
        current_address = self.get_address(ms)
        for row in range(self.height):
            for col in range(self.width):
                # Fill one BGR byte value
                this_byte = [b'\x00', b'\x00', b'\x00']
                for c in self.color_format:
                    if c == self.ColorFmtCode.RED:
                        this_byte[0] = self.bytes[current_address:current_address + 1]  # Red
                    elif c == self.ColorFmtCode.GREEN:
                        this_byte[1] = self.bytes[current_address:current_address + 1]  # Green
                    elif c == self.ColorFmtCode.BLUE:
                        this_byte[2] = self.bytes[current_address:current_address + 1]  # Blue
                    elif c == self.ColorFmtCode.WHITE:
                        this_byte[0] = self.bytes[current_address:current_address + 1]  # Red
                        this_byte[1] = self.bytes[current_address:current_address + 1]  # Green
                        this_byte[2] = self.bytes[current_address:current_address + 1]  # Blue

                    current_address += 1

                picture_bytes += b"".join(this_byte)

        full_length = (self.width * self.height * 3)
        picture_bytes_length = len(picture_bytes)
        # Pad picture data if we're near the end of the file
        if picture_bytes_length < full_length:
            pad_length = full_length - picture_bytes_length
            picture_bytes += b"\x00" * pad_length

        return picture_bytes

    # A PIL Image (RGB)
    def get_frame_image(self, ms, flip=True):
        frame_bytesring = self.get_frame_bytestring(ms)
        img = Image.frombytes("RGB", (self.width, self.height), frame_bytesring)

        if flip:
            img = ImageOps.flip(img)

        return img

    # A QImage (RGB)
    def get_frame_qimage(self, ms, flip=True):
        frame_bytesring = self.get_frame_bytestring(ms)
        qimg = QImage(
            frame_bytesring,
            self.width,
            self.height,
            3 * self.width,
            QImage.Format.Format_RGB888
        )
        if flip:
            # Flip vertically
            qimg = qimg.mirrored(horizontal=False, vertical=True)

        return qimg

    def cleanup(self):
        self.delete_audio()
        shutil.rmtree(self.temp_dir)


# Watermarker class
#   Handles watermarking images
class Watermarker:
    def __init__(self):
        self.img = Image.open(ICON_PATH["watermark"]).convert("RGBA")

    def mark(self, image):
        this_mark = self.img.copy()
        this_mark = fit_to_frame(
            image=this_mark,
            frame_size=image.size,
            scaling=Image.BICUBIC,
            transparent=True
        )

        output_image = image.copy()
        output_image.paste(this_mark, (0, 0), this_mark)

        return output_image


# Custom proglog class for QProgressDialogs
#   Handles updating the progress in a QProgressDialog
#   Designed to work with moviepy's export option
class QtBarLoggerMoviepy(ProgressBarLogger):
    def set_progress_dialog(self, progress_dialog, start_progress=0):
        self.progress_dialog = progress_dialog
        progress_dialog.setMaximum(100)
        self.set_progress(start_progress)

    def set_progress(self, value):
        self.progress_dialog.setValue(value)

    def callback(self, **changes):
        if "message" in changes:
            message = changes["message"].lower()
            if "building" in message:
                self.set_progress(5)
            elif "writing" in message:
                self.set_progress(50)
            elif "ready" in message:
                self.set_progress(100)


# Audio settings input window
#   User interface to set the audio settings (for computation)
class AudioSettings(QDialog):
    def __init__(self,
                 num_channels,
                 sample_bytes,
                 sample_rate,
                 volume,
                 parent=None
                 ):
        super().__init__(parent=parent)
        self.setWindowTitle("Audio Settings")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.num_channels = num_channels
        self.sample_bytes = sample_bytes
        self.sample_rate = sample_rate
        self.volume = volume

        self.channels_label = QLabel("Channels:")
        self.channels_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.channels_entry = QComboBox()
        self.channels_entry.addItems(["1 (mono)", "2 (stereo)"])
        if self.num_channels == 1:
            self.channels_entry.setCurrentIndex(0)
        elif self.num_channels == 2:
            self.channels_entry.setCurrentIndex(1)
        self.channels_entry.currentIndexChanged.connect(self.channel_entry_changed)

        self.sample_size_label = QLabel("Sample Size:")
        self.sample_size_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.sample_size_entry = QComboBox()
        self.sample_size_entry.addItems(["8-bit", "16-bit", "24-bit", "32-bit"])
        if self.sample_bytes == 1:
            self.sample_size_entry.setCurrentIndex(0)
        elif self.sample_bytes == 2:
            self.sample_size_entry.setCurrentIndex(1)
        elif self.sample_bytes == 3:
            self.sample_size_entry.setCurrentIndex(2)
        elif self.sample_bytes == 4:
            self.sample_size_entry.setCurrentIndex(3)
        self.sample_size_entry.currentIndexChanged.connect(self.sample_size_entry_changed)

        self.sample_rate_label = QLabel("Sample Rate:")
        self.sample_rate_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.sample_rate_entry = QSpinBox()
        self.sample_rate_entry.setMinimum(1)
        self.sample_rate_entry.setMaximum(192000)
        self.sample_rate_entry.setSingleStep(1000)
        self.sample_rate_entry.setSuffix("Hz")
        self.sample_rate_entry.setValue(self.sample_rate)
        self.sample_rate_entry.valueChanged.connect(self.sample_rate_entry_changed)

        self.volume_label = QLabel("File Volume:")
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.volume_entry = QSpinBox()
        self.volume_entry.setMinimum(0)
        self.volume_entry.setMaximum(100)
        self.volume_entry.setSingleStep(5)
        self.volume_entry.setSuffix("%")
        self.volume_entry.setValue(self.volume)
        self.volume_entry.valueChanged.connect(self.volume_entry_changed)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.confirm_buttons.accepted.connect(self.accept)
        self.confirm_buttons.rejected.connect(self.reject)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.channels_label, 0, 0)
        self.main_layout.addWidget(self.channels_entry, 0, 1)
        self.main_layout.addWidget(self.sample_size_label, 1, 0)
        self.main_layout.addWidget(self.sample_size_entry, 1, 1)
        self.main_layout.addWidget(self.sample_rate_label, 2, 0)
        self.main_layout.addWidget(self.sample_rate_entry, 2, 1)
        self.main_layout.addWidget(self.volume_label, 3, 0)
        self.main_layout.addWidget(self.volume_entry, 3, 1)
        self.main_layout.addWidget(self.confirm_buttons, 4, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def get_audio_settings(self):
        result = dict()
        result["num_channels"] = self.num_channels
        result["sample_bytes"] = self.sample_bytes
        result["sample_rate"] = self.sample_rate
        result["volume"] = self.volume

        return result

    def channel_entry_changed(self, idx):
        if idx == 0:
            self.num_channels = 1
        elif idx == 1:
            self.num_channels = 2

    def sample_size_entry_changed(self, idx):
        if idx == 0:
            self.sample_bytes = 1
        elif idx == 1:
            self.sample_bytes = 2
        elif idx == 2:
            self.sample_bytes = 3
        elif idx == 3:
            self.sample_bytes = 4

    def sample_rate_entry_changed(self, value):
        self.sample_rate = value

    def volume_entry_changed(self, value):
        self.volume = value

    def resize_window(self):
        self.setFixedSize(self.sizeHint())


# Video settings input window
#   User interface to set the video settings (for computation)
class VideoSettings(QDialog):
    def __init__(self,
                 bw,
                 width,
                 height,
                 color_format,
                 parent=None
                 ):
        super().__init__(parent=parent)
        self.setWindowTitle("Video Settings")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.bw = bw

        self.width = width
        self.height = height
        self.color_format = color_format

        self.width_label = QLabel("Width:")
        self.width_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.width_entry = QSpinBox()
        self.width_entry.setMinimum(4)
        self.width_entry.setMaximum(1024)
        self.width_entry.setSingleStep(4)
        self.width_entry.setSuffix("px")
        self.width_entry.setValue(self.width)
        self.width_entry.valueChanged.connect(self.width_entry_changed)

        self.height_label = QLabel("Height:")
        self.height_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.height_entry = QSpinBox()
        self.height_entry.setMinimum(4)
        self.height_entry.setMaximum(1024)
        self.height_entry.setSingleStep(4)
        self.height_entry.setSuffix("px")
        self.height_entry.setValue(self.height)
        self.height_entry.valueChanged.connect(self.height_entry_changed)

        self.color_format_label = QLabel("Color Format:")
        self.color_format_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.color_format_entry = QLineEdit()
        self.color_format_entry.setMaxLength(64)
        self.color_format_entry.setText(self.color_format)
        self.color_format_entry.editingFinished.connect(self.color_format_entry_changed)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.confirm_buttons.accepted.connect(self.accept)
        self.confirm_buttons.rejected.connect(self.reject)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.width_label, 0, 0)
        self.main_layout.addWidget(self.width_entry, 0, 1)
        self.main_layout.addWidget(self.height_label, 1, 0)
        self.main_layout.addWidget(self.height_entry, 1, 1)
        self.main_layout.addWidget(self.color_format_label, 2, 0)
        self.main_layout.addWidget(self.color_format_entry, 2, 1)
        self.main_layout.addWidget(self.confirm_buttons, 3, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def get_video_settings(self):
        result = dict()
        result["width"] = self.width
        result["height"] = self.height
        result["color_format"] = self.color_format

        return result

    def width_entry_changed(self, value):
        self.width = value

    def height_entry_changed(self, value):
        self.height = value

    def color_format_entry_changed(self):
        color_format = self.color_format_entry.text()
        parsed = self.bw.parse_color_format(color_format)
        if parsed["is_valid"]:
            self.color_format = color_format
        else:
            self.color_format_entry.setText(self.color_format)
            self.color_format_entry.setFocus()

            error_popup = QMessageBox(parent=self)
            error_popup.setIcon(QMessageBox.Critical)
            error_popup.setText("Invalid Color Format")
            error_popup.setInformativeText(parsed["message"])
            error_popup.setWindowTitle("Error")
            error_popup.exec()

    def resize_window(self):
        self.setFixedSize(self.sizeHint())


# Player settings input window
#   User interface to set the player settings (for playback)
class PlayerSettings(QDialog):
    def __init__(self,
                 max_view_dim,
                 fps,
                 parent=None
                 ):
        super().__init__(parent=parent)
        self.setWindowTitle("Player Settings")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.max_view_dim = max_view_dim
        self.fps = fps

        self.max_dim_label = QLabel("Max. Dimension:")
        self.max_dim_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.max_dim_entry = QSpinBox()
        self.max_dim_entry.setMinimum(256)
        self.max_dim_entry.setMaximum(7680)
        self.max_dim_entry.setSingleStep(64)
        self.max_dim_entry.setSuffix("px")
        self.max_dim_entry.setValue(self.max_view_dim)
        self.max_dim_entry.valueChanged.connect(self.max_dim_entry_changed)

        self.fps_label = QLabel("Framerate:")
        self.fps_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.fps_entry = QSpinBox()
        self.fps_entry.setMinimum(1)
        self.fps_entry.setMaximum(120)
        self.fps_entry.setSingleStep(1)
        self.fps_entry.setSuffix("fps")
        self.fps_entry.setValue(self.fps)
        self.fps_entry.valueChanged.connect(self.fps_entry_changed)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.confirm_buttons.accepted.connect(self.accept)
        self.confirm_buttons.rejected.connect(self.reject)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.max_dim_label, 0, 0)
        self.main_layout.addWidget(self.max_dim_entry, 0, 1)
        self.main_layout.addWidget(self.fps_label, 1, 0)
        self.main_layout.addWidget(self.fps_entry, 1, 1)
        self.main_layout.addWidget(self.confirm_buttons, 2, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def get_player_settings(self):
        result = dict()
        result["max_view_dim"] = self.max_view_dim
        result["fps"] = self.fps

        return result

    def max_dim_entry_changed(self, value):
        self.max_view_dim = value

    def fps_entry_changed(self, value):
        self.fps = value

    def resize_window(self):
        self.setFixedSize(self.sizeHint())


# Export image dialog
#   User interface to export a single frame
class ExportFrame(QDialog):
    def __init__(self,
                 width,
                 height,
                 parent=None
                 ):
        super().__init__(parent=parent)
        self.setWindowTitle("Export Image")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.width = width
        self.height = height
        self.keep_aspect = False

        self.width_label = QLabel("Export Width:")
        self.width_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.width_entry = QSpinBox()
        self.width_entry.setMinimum(64)
        self.width_entry.setMaximum(7680)
        self.width_entry.setSingleStep(64)
        self.width_entry.setSuffix("px")
        self.width_entry.setValue(self.width)
        self.width_entry.valueChanged.connect(self.width_entry_changed)

        self.height_label = QLabel("Export Height:")
        self.height_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.height_entry = QSpinBox()
        self.height_entry.setMinimum(64)
        self.height_entry.setMaximum(7680)
        self.height_entry.setSingleStep(64)
        self.height_entry.setSuffix("px")
        self.height_entry.setValue(self.height)
        self.height_entry.valueChanged.connect(self.height_entry_changed)

        self.aspect_label = QLabel("Aspect Ratio:")
        self.aspect_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.aspect_entry = QCheckBox("Force")
        self.aspect_entry.setChecked(self.keep_aspect)
        self.aspect_entry.stateChanged.connect(self.aspect_entry_changed)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.confirm_buttons.accepted.connect(self.accept)
        self.confirm_buttons.rejected.connect(self.reject)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.width_label, 0, 0)
        self.main_layout.addWidget(self.width_entry, 0, 1)
        self.main_layout.addWidget(self.height_label, 1, 0)
        self.main_layout.addWidget(self.height_entry, 1, 1)
        self.main_layout.addWidget(self.aspect_label, 2, 0)
        self.main_layout.addWidget(self.aspect_entry, 2, 1)
        self.main_layout.addWidget(self.confirm_buttons, 3, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def resize_window(self):
        self.setFixedSize(self.sizeHint())

    def get_settings(self):
        result = dict()
        result["width"] = self.width
        result["height"] = self.height
        result["keep_aspect"] = self.keep_aspect

        return result

    def width_entry_changed(self, value):
        self.width = value

    def height_entry_changed(self, value):
        self.height = value

    def aspect_entry_changed(self, value):
        if value == 0:
            self.keep_aspect = False
        else:
            self.keep_aspect = True


# Export image sequence dialog
#   User interface to export an image sequence
class ExportSequence(QDialog):
    def __init__(self,
                 width,
                 height,
                 parent=None
                 ):
        super().__init__(parent=parent)
        self.setWindowTitle("Export Sequence")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.width = width
        self.height = height
        self.fps = 60.0
        self.keep_aspect = False
        self.format = Renderer.ImageFormatCode.PNG

        self.fps_label = QLabel("FPS:")
        self.fps_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.fps_entry = QDoubleSpinBox()
        self.fps_entry.setMinimum(1.0)
        self.fps_entry.setMaximum(120.0)
        self.fps_entry.setSingleStep(1.0)
        self.fps_entry.setSuffix("fps")
        self.fps_entry.setValue(self.fps)
        self.fps_entry.valueChanged.connect(self.fps_entry_changed)

        self.width_label = QLabel("Export Width:")
        self.width_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.width_entry = QSpinBox()
        self.width_entry.setMinimum(64)
        self.width_entry.setMaximum(7680)
        self.width_entry.setSingleStep(64)
        self.width_entry.setSuffix("px")
        self.width_entry.setValue(self.width)
        self.width_entry.valueChanged.connect(self.width_entry_changed)

        self.height_label = QLabel("Export Height:")
        self.height_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.height_entry = QSpinBox()
        self.height_entry.setMinimum(64)
        self.height_entry.setMaximum(7680)
        self.height_entry.setSingleStep(64)
        self.height_entry.setSuffix("px")
        self.height_entry.setValue(self.height)
        self.height_entry.valueChanged.connect(self.height_entry_changed)

        self.aspect_label = QLabel("Aspect Ratio:")
        self.aspect_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.aspect_entry = QCheckBox("Force")
        self.aspect_entry.setChecked(self.keep_aspect)
        self.aspect_entry.stateChanged.connect(self.aspect_entry_changed)

        self.format_label = QLabel("Image Format:")
        self.format_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.format_entry = QComboBox()
        self.format_entry.addItems(["PNG (.png)", "JPEG (.jpg)", "BMP (.bmp)"])
        if self.format == Renderer.ImageFormatCode.PNG:
            self.format_entry.setCurrentIndex(0)
        elif self.format == Renderer.ImageFormatCode.JPEG:
            self.format_entry.setCurrentIndex(1)
        elif self.format == Renderer.ImageFormatCode.BITMAP:
            self.format_entry.setCurrentIndex(2)
        self.format_entry.currentIndexChanged.connect(self.format_entry_changed)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.confirm_buttons.accepted.connect(self.accept)
        self.confirm_buttons.rejected.connect(self.reject)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.fps_label, 0, 0)
        self.main_layout.addWidget(self.fps_entry, 0, 1)
        self.main_layout.addWidget(self.width_label, 1, 0)
        self.main_layout.addWidget(self.width_entry, 1, 1)
        self.main_layout.addWidget(self.height_label, 2, 0)
        self.main_layout.addWidget(self.height_entry, 2, 1)
        self.main_layout.addWidget(self.aspect_label, 3, 0)
        self.main_layout.addWidget(self.aspect_entry, 3, 1)
        self.main_layout.addWidget(self.format_label, 4, 0)
        self.main_layout.addWidget(self.format_entry, 4, 1)
        self.main_layout.addWidget(self.confirm_buttons, 5, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def resize_window(self):
        self.setFixedSize(self.sizeHint())

    def get_settings(self):
        result = dict()
        result["width"] = self.width
        result["height"] = self.height
        result["fps"] = self.fps
        result["keep_aspect"] = self.keep_aspect
        result["format"] = self.format

        return result

    def width_entry_changed(self, value):
        self.width = value

    def height_entry_changed(self, value):
        self.height = value

    def aspect_entry_changed(self, value):
        if value == 0:
            self.keep_aspect = False
        else:
            self.keep_aspect = True

    def fps_entry_changed(self, value):
        self.fps = value

    def format_entry_changed(self, value):
        if value == 0:
            self.format = Renderer.ImageFormatCode.PNG
        elif value == 1:
            self.format = Renderer.ImageFormatCode.JPEG
        elif value == 2:
            self.format = Renderer.ImageFormatCode.BITMAP


# Export video dialog
#   User interface to export a video
class ExportVideo(QDialog):
    def __init__(self,
                 width,
                 height,
                 parent=None
                 ):
        super().__init__(parent=parent)
        self.setWindowTitle("Export Video")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.width = width
        self.height = height
        self.fps = 60.0
        self.keep_aspect = False

        self.fps_label = QLabel("FPS:")
        self.fps_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.fps_entry = QDoubleSpinBox()
        self.fps_entry.setMinimum(1.0)
        self.fps_entry.setMaximum(120.0)
        self.fps_entry.setSingleStep(1.0)
        self.fps_entry.setSuffix("fps")
        self.fps_entry.setValue(self.fps)
        self.fps_entry.valueChanged.connect(self.fps_entry_changed)

        self.width_label = QLabel("Export Width:")
        self.width_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.width_entry = QSpinBox()
        self.width_entry.setMinimum(64)
        self.width_entry.setMaximum(7680)
        self.width_entry.setSingleStep(64)
        self.width_entry.setSuffix("px")
        self.width_entry.setValue(self.width)
        self.width_entry.valueChanged.connect(self.width_entry_changed)

        self.height_label = QLabel("Export Height:")
        self.height_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.height_entry = QSpinBox()
        self.height_entry.setMinimum(64)
        self.height_entry.setMaximum(7680)
        self.height_entry.setSingleStep(64)
        self.height_entry.setSuffix("px")
        self.height_entry.setValue(self.height)
        self.height_entry.valueChanged.connect(self.height_entry_changed)

        self.aspect_label = QLabel("Aspect Ratio:")
        self.aspect_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.aspect_entry = QCheckBox("Force")
        self.aspect_entry.setChecked(self.keep_aspect)
        self.aspect_entry.stateChanged.connect(self.aspect_entry_changed)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.confirm_buttons.accepted.connect(self.accept)
        self.confirm_buttons.rejected.connect(self.reject)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.fps_label, 0, 0)
        self.main_layout.addWidget(self.fps_entry, 0, 1)
        self.main_layout.addWidget(self.width_label, 1, 0)
        self.main_layout.addWidget(self.width_entry, 1, 1)
        self.main_layout.addWidget(self.height_label, 2, 0)
        self.main_layout.addWidget(self.height_entry, 2, 1)
        self.main_layout.addWidget(self.aspect_label, 3, 0)
        self.main_layout.addWidget(self.aspect_entry, 3, 1)
        self.main_layout.addWidget(self.confirm_buttons, 4, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def resize_window(self):
        self.setFixedSize(self.sizeHint())

    def get_settings(self):
        result = dict()
        result["width"] = self.width
        result["height"] = self.height
        result["fps"] = self.fps
        result["keep_aspect"] = self.keep_aspect

        return result

    def width_entry_changed(self, value):
        self.width = value

    def height_entry_changed(self, value):
        self.height = value

    def aspect_entry_changed(self, value):
        if value == 0:
            self.keep_aspect = False
        else:
            self.keep_aspect = True

    def fps_entry_changed(self, value):
        self.fps = value


# Hotkey info dialog
#   Lists the program hotkeys
class HotkeysInfo(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("Hotkey Info")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.play_label = QLabel("Play / Pause:")
        self.play_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.play_key_label = QLabel("Spacebar")
        self.play_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.forward_label = QLabel("Forward:")
        self.forward_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.forward_key_label = QLabel("Right")
        self.forward_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.back_label = QLabel("Back:")
        self.back_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.back_key_label = QLabel("Left")
        self.back_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.frame_forward_label = QLabel("Frame Forward:")
        self.frame_forward_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.frame_forward_key_label = QLabel(">")
        self.frame_forward_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.frame_back_label = QLabel("Frame Back:")
        self.frame_back_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.frame_back_key_label = QLabel("<")
        self.frame_back_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.restart_label = QLabel("Restart:")
        self.restart_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.restart_key_label = QLabel("R")
        self.restart_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.volume_up_label = QLabel("Volume Up:")
        self.volume_up_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.volume_up_key_label = QLabel("Up")
        self.volume_up_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.volume_down_label = QLabel("Volume Down:")
        self.volume_down_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.volume_down_key_label = QLabel("Down")
        self.volume_down_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.mute_label = QLabel("Mute:")
        self.mute_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.mute_key_label = QLabel("M")
        self.mute_key_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        self.confirm_buttons.accepted.connect(self.accept)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.play_label, 0, 0)
        self.main_layout.addWidget(self.play_key_label, 0, 1)
        self.main_layout.addWidget(self.back_label, 1, 0)
        self.main_layout.addWidget(self.back_key_label, 1, 1)
        self.main_layout.addWidget(self.forward_label, 2, 0)
        self.main_layout.addWidget(self.forward_key_label, 2, 1)
        self.main_layout.addWidget(self.frame_back_label, 3, 0)
        self.main_layout.addWidget(self.frame_back_key_label, 3, 1)
        self.main_layout.addWidget(self.frame_forward_label, 4, 0)
        self.main_layout.addWidget(self.frame_forward_key_label, 4, 1)
        self.main_layout.addWidget(self.restart_label, 5, 0)
        self.main_layout.addWidget(self.restart_key_label, 5, 1)
        self.main_layout.addWidget(self.volume_up_label, 6, 0)
        self.main_layout.addWidget(self.volume_up_key_label, 6, 1)
        self.main_layout.addWidget(self.volume_down_label, 7, 0)
        self.main_layout.addWidget(self.volume_down_key_label, 7, 1)
        self.main_layout.addWidget(self.mute_label, 8, 0)
        self.main_layout.addWidget(self.mute_key_label, 8, 1)
        self.main_layout.addWidget(self.confirm_buttons, 9, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def resize_window(self):
        self.setFixedSize(self.sizeHint())


# Registration info dialog
#   Displays registration info and a button to register
class RegistrationInfo(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("Registration Info")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.status_label = QLabel("Status:")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.status_value = QLabel()
        self.status_value.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.set_registered_value()

        self.serial_label = QLabel("Serial Number:")
        self.serial_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.serial_value = QLabel()
        self.serial_value.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.set_serial_value()

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Close | QDialogButtonBox.Help)
        self.confirm_buttons.button(QDialogButtonBox.Help).setText("Register...")
        self.confirm_buttons.helpRequested.connect(self.register_clicked)
        self.confirm_buttons.rejected.connect(self.reject)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.status_label, 0, 0)
        self.main_layout.addWidget(self.status_value, 0, 1)
        self.main_layout.addWidget(self.serial_label, 1, 0)
        self.main_layout.addWidget(self.serial_value, 1, 1)
        self.main_layout.addWidget(self.confirm_buttons, 2, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def resize_window(self):
        self.setFixedSize(self.sizeHint())

    def set_registered_value(self):
        global IS_REGISTERED

        if IS_REGISTERED:
            reg_status = "Activated!"
        else:
            reg_status = "Unregistered"

        self.status_value.setText(reg_status)

    def set_serial_value(self):
        global SERIAL_KEY

        if SERIAL_KEY is None:
            self.serial_value.setText("None")
        else:
            self.serial_value.setText(SERIAL_KEY)

    def register_clicked(self):
        global SERIAL_KEY
        global IS_REGISTERED

        if SERIAL_KEY is None:
            popup = RegistrationEntry(parent=self)

            result = popup.exec()

            if result:
                settings = popup.get_settings()
                if settings["key_is_valid"]:
                    IS_REGISTERED = True
                    SERIAL_KEY = settings["serial"]

                    # Register product
                    os.makedirs(DATA_DIR, exist_ok=True)
                    with open(KEY_FILE, "w") as f:
                        f.write(SERIAL_KEY)

                    self.set_registered_value()
                    self.set_serial_value()
                    self.resize_window()

                    choice = QMessageBox.information(
                        self,
                        "Registration Complete",
                        f"Thank you for registering {TITLE}!",
                        QMessageBox.Ok
                    )
                else:
                    choice = QMessageBox.critical(
                        self,
                        "Serial Not Valid",
                        "You have entered an invalid serial key.",
                        QMessageBox.Ok
                    )
        else:
            choice = QMessageBox.warning(
                self,
                "Already Registered",
                "You have already registered this product!",
                QMessageBox.Ok
            )


# Registration entry dialog
#   Prompts the user to enter a serial number
#   Also gives the user a button to buy a serial key (open link)
class RegistrationEntry(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("Registration Info")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.serial = ""
        self.key_is_valid = False
        self.validator = KeyValidate(TITLE)

        self.info_label = QLabel(f"You can buy a key at the following link:\n{DONATE_URL}")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.serial_label = QLabel("Serial:")
        self.serial_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.serial_entry = QLineEdit()
        self.serial_entry.setMaxLength((5 * 4) + 3)
        self.serial_entry.setText(self.serial)
        self.serial_entry.editingFinished.connect(self.serial_entry_changed)

        self.buy_button = QPushButton("Buy...")
        self.buy_button.clicked.connect(self.buy_button_clicked)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.confirm_buttons.button(QDialogButtonBox.Ok).setText("Register")
        self.confirm_buttons.addButton(self.buy_button, QDialogButtonBox.ResetRole)
        self.confirm_buttons.accepted.connect(self.accept)
        self.confirm_buttons.rejected.connect(self.reject)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.info_label, 0, 0, 1, 2)
        self.main_layout.addWidget(self.serial_label, 1, 0)
        self.main_layout.addWidget(self.serial_entry, 1, 1)
        self.main_layout.addWidget(self.confirm_buttons, 2, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def resize_window(self):
        self.setFixedSize(self.sizeHint())

    def get_settings(self):
        result = dict()
        result["serial"] = self.serial
        result["key_is_valid"] = self.key_is_valid

        return result

    def serial_entry_changed(self):
        self.serial = self.serial_entry.text().strip()

        if self.validator.is_key_valid(self.serial):
            self.key_is_valid = True
        else:
            self.key_is_valid = False

    def buy_button_clicked(self):
        webbrowser.open(REGISTER_URL)


# About dialog
#   Gives info about the program
class About(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(f"About {TITLE}")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        # Hide "?" button
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self.icon_size = 200

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(QPixmap(ICON_PATH["program"]))
        self.icon_label.setScaledContents(True)
        self.icon_label.setFixedSize(self.icon_size, self.icon_size)

        self.about_text = QLabel(
            f"{TITLE} v{VERSION}\nby {COPYRIGHT}\nCopyright 2023\n\n{DESCRIPTION}\n\nProject Home Page:\n{PROJECT_URL}\n\nPatreon:\n{DONATE_URL}")
        self.about_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.confirm_buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        self.confirm_buttons.accepted.connect(self.accept)

        self.main_layout = QGridLayout()

        self.main_layout.addWidget(self.icon_label, 0, 0, 2, 1)
        self.main_layout.addWidget(self.about_text, 0, 1)
        self.main_layout.addWidget(self.confirm_buttons, 1, 0, 1, 2)

        self.setLayout(self.main_layout)

        self.resize_window()

    def resize_window(self):
        self.setFixedSize(self.sizeHint())


# Custom image-based button
#   Allows for very fancy custom buttons
class ImageButton(QAbstractButton):
    def __init__(self,
                 pixmap,
                 pixmap_hover,
                 pixmap_pressed,
                 scale=1.0,
                 parent=None
                 ):
        super(ImageButton, self).__init__(parent)

        self.set_scale(scale)
        self.change_pixmaps(
            pixmap=pixmap,
            pixmap_hover=pixmap_hover,
            pixmap_pressed=pixmap_pressed
        )

        self.pressed.connect(self.update)
        self.released.connect(self.update)

    def change_pixmaps(self,
                       pixmap,
                       pixmap_hover,
                       pixmap_pressed
                       ):
        self.pixmap = pixmap
        self.pixmap_hover = pixmap_hover
        self.pixmap_pressed = pixmap_pressed

        self.width = round(self.pixmap.width() * self.scale)
        self.height = round(self.pixmap.height() * self.scale)

        self.update()

    def set_scale(self, scale_factor):
        self.scale = scale_factor

    def paintEvent(self, event):
        if self.isDown():
            pix = self.pixmap_pressed
        elif self.underMouse():
            pix = self.pixmap_hover
        else:
            pix = self.pixmap

        painter = QPainter(self)
        painter.drawPixmap(event.rect(), pix)

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def sizeHint(self):
        return QSize(self.width, self.height)


# Custom seekbar class
#   A customized slider
class SeekBar(QSlider):
    def __init__(self,
                 position_changed_function=None,
                 parent=None
                 ):
        super(SeekBar, self).__init__(parent)

        self.handle_size = 10
        # TODO: Fix handle width not changing
        # TODO: Fix handle not hanging over the side

        self.setFixedHeight(self.handle_size)

        self.setStyleSheet(
            "QSlider::handle {{ background: #666; height: {0}px; width: {0}px; border-radius: {1}px; }} QSlider::handle:hover {{ background: #000; height: {0}px; width: {0}px; border-radius: {1}px; }}".format(
                self.handle_size, math.floor(self.handle_size / 2)))

        self.position_changed_function = position_changed_function

    def set_position_changed_function(self, position_changed_function):
        self.position_changed_function = position_changed_function

    def set_position_if_set(self, value):
        if self.position_changed_function == None:
            self.setValue(value)
        else:
            self.position_changed_function(value)

    def mousePressEvent(self, event):
        value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width())
        self.set_position_if_set(value)

    def mouseMoveEvent(self, event):
        value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width())
        self.set_position_if_set(value)


# My QMainWindow class
#   Used to customize the main window.
#   The actual object used to programmatically reference
#   the "main window" is MainWindow
class MyQMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{TITLE}")
        self.setWindowIcon(QIcon(ICON_PATH["program"]))

        self.bw = BinaryWaterfall()

        self.last_save_location = PROG_PATH

        self.renderer = Renderer(
            binary_waterfall=self.bw
        )

        self.padding_px = 10

        self.seek_bar = SeekBar()
        self.seek_bar.setFocusPolicy(Qt.NoFocus)
        self.seek_bar.setOrientation(Qt.Horizontal)
        self.seek_bar.setMinimum(0)
        self.update_seekbar()
        self.seek_bar.sliderMoved.connect(self.seekbar_moved)

        self.player_label = QLabel()
        self.player_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.player = Player(
            binary_waterfall=self.bw,
            display=self.player_label,
            set_playbutton_function=self.set_play_button,
            set_seekbar_function=self.seek_bar.setValue
        )

        self.current_volume = self.player.volume

        # Setup seek bar to correctly change player location
        self.seek_bar.set_position_changed_function(self.seekbar_moved)

        self.set_file_savename()

        # Save the pixmaps for later
        self.play_icons = {
            "play": {
                "base": QPixmap(ICON_PATH["button"]["play"]["base"]),
                "hover": QPixmap(ICON_PATH["button"]["play"]["hover"]),
                "clicked": QPixmap(ICON_PATH["button"]["play"]["clicked"])
            },
            "pause": {
                "base": QPixmap(ICON_PATH["button"]["pause"]["base"]),
                "hover": QPixmap(ICON_PATH["button"]["pause"]["hover"]),
                "clicked": QPixmap(ICON_PATH["button"]["pause"]["clicked"])
            }
        }

        self.transport_play = ImageButton(
            pixmap=self.play_icons["play"]["base"],
            pixmap_hover=self.play_icons["play"]["hover"],
            pixmap_pressed=self.play_icons["play"]["clicked"],
            scale=1.0,
            parent=self
        )
        self.transport_play.setFocusPolicy(Qt.NoFocus)
        self.transport_play.setFixedSize(self.transport_play.width, self.transport_play.height)
        self.transport_play.clicked.connect(self.play_clicked)

        self.transport_forward = ImageButton(
            pixmap=QPixmap(ICON_PATH["button"]["forward"]["base"]),
            pixmap_hover=QPixmap(ICON_PATH["button"]["forward"]["hover"]),
            pixmap_pressed=QPixmap(ICON_PATH["button"]["forward"]["clicked"]),
            scale=0.75,
            parent=self
        )
        self.transport_forward.setFocusPolicy(Qt.NoFocus)
        self.transport_forward.setFixedSize(self.transport_forward.width, self.transport_forward.height)
        self.transport_forward.clicked.connect(self.forward_clicked)

        self.transport_back = ImageButton(
            pixmap=QPixmap(ICON_PATH["button"]["back"]["base"]),
            pixmap_hover=QPixmap(ICON_PATH["button"]["back"]["hover"]),
            pixmap_pressed=QPixmap(ICON_PATH["button"]["back"]["clicked"]),
            scale=0.75,
            parent=self
        )
        self.transport_back.setFocusPolicy(Qt.NoFocus)
        self.transport_back.setFixedSize(self.transport_back.width, self.transport_back.height)
        self.transport_back.clicked.connect(self.back_clicked)

        self.transport_restart = ImageButton(
            pixmap=QPixmap(ICON_PATH["button"]["restart"]["base"]),
            pixmap_hover=QPixmap(ICON_PATH["button"]["restart"]["hover"]),
            pixmap_pressed=QPixmap(ICON_PATH["button"]["restart"]["clicked"]),
            scale=0.5,
            parent=self
        )
        self.transport_restart.setFocusPolicy(Qt.NoFocus)
        self.transport_restart.setFixedSize(self.transport_restart.width, self.transport_restart.height)
        self.transport_restart.clicked.connect(self.restart_clicked)

        self.volume_icons = {
            "base": QPixmap(ICON_PATH["volume"]["base"]),
            "mute": QPixmap(ICON_PATH["volume"]["mute"]),
        }

        self.volume_icon = QLabel()
        self.volume_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.volume_icon.setScaledContents(True)
        self.volume_icon.setFixedSize(20, 20)
        self.set_volume_icon(mute=self.is_player_muted())
        self.unmute_volume = self.current_volume
        self.volume_icon.mousePressEvent = self.volume_icon_clicked

        self.volume_label = QLabel()
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.volume_label.setFixedWidth(30)
        self.set_volume_label_value(self.current_volume)

        self.volume_slider = QSlider(Qt.Vertical)
        self.volume_slider.setStyleSheet(
            "QSlider::handle { background: #666; } QSlider::handle:hover { background: #000; }")
        self.volume_slider.setFocusPolicy(Qt.NoFocus)
        self.volume_slider.setFixedSize(20, 50)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.valueChanged.connect(self.volume_slider_changed)

        self.transport_left_layout = QHBoxLayout()
        self.transport_left_layout.setSpacing(self.padding_px)
        self.transport_left_layout.addWidget(self.transport_restart)
        self.transport_left_layout.addWidget(self.transport_back)

        self.restart_counterpad = QLabel()

        self.transport_right_layout = QHBoxLayout()
        self.transport_right_layout.setSpacing(self.padding_px)
        self.transport_right_layout.addWidget(self.transport_forward)
        self.transport_right_layout.addWidget(self.restart_counterpad)

        self.voume_layout = QGridLayout()
        self.voume_layout.setContentsMargins(0, 0, self.padding_px, 0)

        self.voume_layout.addWidget(self.volume_icon, 0, 0,
                                    alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.voume_layout.addWidget(self.volume_label, 1, 0,
                                    alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.voume_layout.addWidget(self.volume_slider, 0, 1, 2, 1,
                                    alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.main_layout = QGridLayout()
        self.main_layout.setContentsMargins(0, 0, 0, self.padding_px)
        self.main_layout.setSpacing(self.padding_px)

        self.main_layout.addWidget(self.player_label, 0, 0, 1, 5, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.seek_bar, 1, 0, 1, 5, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addLayout(self.transport_left_layout, 2, 1,
                                   alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.main_layout.addWidget(self.transport_play, 2, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addLayout(self.transport_right_layout, 2, 3,
                                   alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.main_layout.addLayout(self.voume_layout, 2, 4, alignment=Qt.AlignmentFlag.AlignCenter)

        self.main_widget = QWidget()
        self.main_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.main_widget)

        self.main_menu = self.menuBar()

        self.file_menu = self.main_menu.addMenu("File")

        self.file_menu_open = QAction("Open...", self)
        self.file_menu_open.triggered.connect(self.open_file_clicked)
        self.file_menu.addAction(self.file_menu_open)

        self.file_menu_close = QAction("Close", self)
        self.file_menu_close.triggered.connect(self.close_file_clicked)
        self.file_menu.addAction(self.file_menu_close)

        self.settings_menu = self.main_menu.addMenu("Settings")

        self.settings_menu_audio = QAction("Audio...", self)
        self.settings_menu_audio.triggered.connect(self.audio_settings_clicked)
        self.settings_menu.addAction(self.settings_menu_audio)

        self.settings_menu_video = QAction("Video...", self)
        self.settings_menu_video.triggered.connect(self.video_settings_clicked)
        self.settings_menu.addAction(self.settings_menu_video)

        self.settings_menu_player = QAction("Player...", self)
        self.settings_menu_player.triggered.connect(self.player_settings_clicked)
        self.settings_menu.addAction(self.settings_menu_player)

        self.export_menu = self.main_menu.addMenu("Export")

        self.export_menu_audio = QAction("Audio...", self)
        self.export_menu_audio.triggered.connect(self.export_audio_clicked)
        self.export_menu.addAction(self.export_menu_audio)

        self.export_menu_image = QAction("Image...", self)
        self.export_menu_image.triggered.connect(self.export_image_clicked)
        self.export_menu.addAction(self.export_menu_image)

        self.export_menu_sequence = QAction("Image Sequence...", self)
        self.export_menu_sequence.triggered.connect(self.export_sequence_clicked)
        self.export_menu.addAction(self.export_menu_sequence)

        self.export_menu_video = QAction("Video...", self)
        self.export_menu_video.triggered.connect(self.export_video_clicked)
        self.export_menu.addAction(self.export_menu_video)

        self.help_menu = self.main_menu.addMenu("Help")

        self.help_menu_hotkeys = QAction("Hotkeys...", self)
        self.help_menu_hotkeys.triggered.connect(self.hotkeys_clicked)
        self.help_menu.addAction(self.help_menu_hotkeys)

        self.help_menu_registration = QAction("Registration...", self)
        self.help_menu_registration.triggered.connect(self.registration_clicked)
        self.help_menu.addAction(self.help_menu_registration)

        self.help_menu_about = QAction("About...", self)
        self.help_menu_about.triggered.connect(self.about_clicked)
        self.help_menu.addAction(self.help_menu_about)

        self.set_volume(self.current_volume)

        # Set window to content size
        self.resize_window()

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_Space:
            self.play_clicked()
        elif key == Qt.Key_Left:
            self.back_clicked()
        elif key == Qt.Key_Right:
            self.forward_clicked()
        elif key == Qt.Key_Up:
            new_volume = min(self.current_volume + 5, 100)
            self.set_volume(new_volume)
        elif key == Qt.Key_Down:
            new_volume = max(self.current_volume - 5, 0)
            self.set_volume(new_volume)
        elif key == Qt.Key_M:
            self.toggle_mute()
        elif key == Qt.Key_R:
            self.restart_clicked()
        elif key == Qt.Key_Comma:
            self.player.frame_back()
        elif key == Qt.Key_Period:
            self.player.frame_forward()

    def resize_window(self):
        # First, make largest elements smaller
        self.seek_bar.setFixedWidth(20)

        # Next, we update counterpadding
        self.update_counterpad_size()

        # We need to wait a sec for the sizeHint to recompute
        QTimer.singleShot(10, self.resize_window_helper)

    def resize_window_helper(self):
        size_hint = self.sizeHint()
        self.setFixedSize(size_hint)

        self.seek_bar.setFixedWidth(size_hint.width() - (self.padding_px * 2))

    def update_counterpad_size(self):
        self.restart_counterpad.setFixedSize(self.transport_restart.sizeHint())

    def set_play_button(self, play):
        if play:
            self.transport_play.change_pixmaps(
                pixmap=self.play_icons["play"]["base"],
                pixmap_hover=self.play_icons["play"]["hover"],
                pixmap_pressed=self.play_icons["play"]["clicked"]
            )
        else:
            self.transport_play.change_pixmaps(
                pixmap=self.play_icons["pause"]["base"],
                pixmap_hover=self.play_icons["pause"]["hover"],
                pixmap_pressed=self.play_icons["pause"]["clicked"]
            )

    def is_player_muted(self):
        if self.player.volume == 0:
            return True
        else:
            return False

    def set_volume_icon(self, mute):
        if mute:
            self.volume_icon.setPixmap(self.volume_icons["mute"])
        else:
            self.volume_icon.setPixmap(self.volume_icons["base"])

    def set_volume_label_value(self, value):
        self.volume_label.setText(f"{value}%")

    def set_volume(self, value):
        self.current_volume = value

        self.player.set_volume(self.current_volume)
        self.set_volume_label_value(self.current_volume)
        self.volume_slider.setValue(self.player.volume)

        if self.current_volume > 0:
            self.unmute_volume = self.current_volume

        if self.current_volume == 0:
            self.set_volume_icon(mute=True)
        else:
            self.set_volume_icon(mute=False)

    def update_seekbar(self):
        if self.bw.filename == None:
            self.seek_bar.setEnabled(False)
            self.seek_bar.setValue(0)
        else:
            self.seek_bar.setMaximum(self.bw.audio_length_ms)
            self.seek_bar.setEnabled(True)

    def seekbar_moved(self, position):
        self.player.set_position(position)

    def pause_player(self):
        self.player.pause()

    def play_player(self):
        self.player.play()

    def play_clicked(self):
        if self.player.is_playing():
            # Already playing, pause
            self.pause_player()
        else:
            # Paused, start playing
            self.play_player()

    def forward_clicked(self):
        self.player.forward()

    def back_clicked(self):
        self.player.back()

    def restart_clicked(self):
        self.player.restart()

    def toggle_mute(self):
        if self.is_player_muted():
            self.muted = False
            self.volume_slider.setValue(self.unmute_volume)
        else:
            self.muted = True
            self.volume_slider.setValue(0)

    def volume_icon_clicked(self, event):
        self.toggle_mute()

    def volume_slider_changed(self, value):
        self.set_volume(value)

    def set_file_savename(self, name=None):
        if name == None:
            self.file_savename = "Untitled"
        else:
            self.file_savename = name

    def open_file_clicked(self):
        self.pause_player()

        filename, filetype = QFileDialog.getOpenFileName(
            self,
            "Open File",
            PROG_PATH,
            "All Binary Files (*)"
        )

        if filename != "":
            self.player.open_file(filename=filename)

            file_path, file_title = os.path.split(filename)
            file_savename, file_ext = os.path.splitext(file_title)
            self.set_file_savename(file_savename)
            self.setWindowTitle(f"{TITLE} | {file_title}")

            self.update_seekbar()

    def close_file_clicked(self):
        self.pause_player()

        self.player.close_file()

        self.set_file_savename()
        self.setWindowTitle(f"{TITLE}")

        self.update_seekbar()

    def audio_settings_clicked(self):
        popup = AudioSettings(
            num_channels=self.bw.num_channels,
            sample_bytes=self.bw.sample_bytes,
            sample_rate=self.bw.sample_rate,
            volume=self.bw.volume,
            parent=self
        )

        result = popup.exec()

        if result:
            audio_settings = popup.get_audio_settings()
            self.player.set_audio_settings(
                num_channels=audio_settings["num_channels"],
                sample_bytes=audio_settings["sample_bytes"],
                sample_rate=audio_settings["sample_rate"],
                volume=audio_settings["volume"],
            )

    def video_settings_clicked(self):
        popup = VideoSettings(
            bw=self.bw,
            width=self.bw.width,
            height=self.bw.height,
            color_format=self.bw.get_color_format_string(),
            parent=self
        )

        result = popup.exec()

        if result:
            video_settings = popup.get_video_settings()
            self.bw.set_dims(
                width=video_settings["width"],
                height=video_settings["height"]
            )
            self.bw.set_color_format(video_settings["color_format"])
            self.player.refresh_dims()
            self.player.update_image()
            # We need to wait a moment for the size hint to be computed
            QTimer.singleShot(10, self.resize_window)

    def player_settings_clicked(self):
        popup = PlayerSettings(
            max_view_dim=self.player.max_dim,
            fps=self.player.fps,
            parent=self
        )

        result = popup.exec()

        if result:
            player_settings = popup.get_player_settings()
            self.player.set_fps(fps=player_settings["fps"])
            self.player.update_dims(max_dim=player_settings["max_view_dim"])
            # We need to wait a moment for the size hint to be computed
            QTimer.singleShot(10, self.resize_window)

    def export_image_clicked(self):
        if self.bw.audio_filename == None:
            choice = QMessageBox.critical(
                self,
                "Error",
                "There is no file open in the viewer to export.\n\nPlease open a file and try again.",
                QMessageBox.Cancel
            )
            return

        popup = ExportFrame(
            width=self.player.width,
            height=self.player.height,
            parent=self
        )

        result = popup.exec()

        if result:
            settings = popup.get_settings()

            filename, filetype = QFileDialog.getSaveFileName(
                self,
                "Export Image As...",
                os.path.join(self.last_save_location, f"{self.file_savename}{self.renderer.ImageFormatCode.PNG.value}"),
                f"PNG (*{self.renderer.ImageFormatCode.PNG.value});;JPEG (*{self.renderer.ImageFormatCode.JPEG.value});;BMP (*{self.renderer.ImageFormatCode.BITMAP.value})"
            )

            if filename != "":
                file_path, file_title = os.path.split(filename)
                self.last_save_location = file_path
                self.renderer.export_frame(
                    ms=self.player.get_position(),
                    filename=filename,
                    size=(settings["width"], settings["height"]),
                    keep_aspect=settings["keep_aspect"]
                )

                choice = QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Export image successful!",
                    QMessageBox.Ok
                )

    def export_audio_clicked(self):
        if self.bw.audio_filename == None:
            choice = QMessageBox.critical(
                self,
                "Error",
                "There is no file open in the viewer to export.\n\nPlease open a file and try again.",
                QMessageBox.Cancel
            )
            return

        filename, filetype = QFileDialog.getSaveFileName(
            self,
            "Export Audio As...",
            os.path.join(self.last_save_location, f"{self.file_savename}{self.renderer.AudioFormatCode.MP3.value}"),
            f"MP3 (*{self.renderer.AudioFormatCode.MP3.value});;WAV (*{self.renderer.AudioFormatCode.WAVE.value});;FLAC (*{self.renderer.AudioFormatCode.FLAC.value})"
        )

        if filename != "":
            file_path, file_title = os.path.split(filename)
            self.last_save_location = file_path
            self.renderer.export_audio(
                filename=filename
            )

            choice = QMessageBox.information(
                self,
                "Export Complete",
                f"Export audio successful!",
                QMessageBox.Ok
            )

    def export_sequence_clicked(self):
        if self.bw.audio_filename == None:
            choice = QMessageBox.critical(
                self,
                "Error",
                "There is no file open in the viewer to export.\n\nPlease open a file and try again.",
                QMessageBox.Cancel
            )
            return

        popup = ExportSequence(
            width=self.player.width,
            height=self.player.height,
            parent=self
        )

        result = popup.exec()

        if result:
            settings = popup.get_settings()

            file_dir = QFileDialog.getExistingDirectory(
                self,
                "Export Image Sequence To...",
                self.last_save_location
            )

            if file_dir != "":
                file_dir_parent, file_dir_title = os.path.split(file_dir)
                self.last_save_location = file_dir_parent
                frame_count = self.renderer.get_frame_count(
                    fps=settings["fps"]
                )
                progress_popup = QProgressDialog("Exporting image sequence...", "Abort", 0, frame_count, self)
                progress_popup.setWindowModality(Qt.WindowModal)
                progress_popup.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)
                progress_popup.setWindowTitle("Exporting Images...")
                progress_popup.setFixedSize(300, 100)

                self.renderer.export_sequence(
                    directory=file_dir,
                    size=(settings["width"], settings["height"]),
                    fps=settings["fps"],
                    keep_aspect=settings["keep_aspect"],
                    format=settings["format"],
                    progress_dialog=progress_popup
                )

                if progress_popup.wasCanceled():
                    # shutil.rmtree(file_dir) # Dangerous! May delete user data
                    choice = QMessageBox.warning(
                        self,
                        "Export Aborted",
                        f"Export image sequence aborted!",
                        QMessageBox.Ok
                    )
                else:
                    choice = QMessageBox.information(
                        self,
                        "Export Complete",
                        f"Export image sequence successful!",
                        QMessageBox.Ok
                    )

    def export_video_clicked(self):
        if self.bw.audio_filename == None:
            choice = QMessageBox.critical(
                self,
                "Error",
                "There is no file open in the viewer to export.\n\nPlease open a file and try again.",
                QMessageBox.Cancel
            )
            return

        if not IS_REGISTERED:
            choice = QMessageBox.warning(
                self,
                "Warning",
                f"{TITLE} is currently unregistered,\na watermark will be added to the final video.\n\nPlease see the Help menu for info on how to register.\n\nProceede anyway?",
                QMessageBox.Cancel | QMessageBox.Ok
            )
            if choice == QMessageBox.Cancel:
                return

        popup = ExportVideo(
            width=self.player.width,
            height=self.player.height,
            parent=self
        )

        result = popup.exec()

        if result:
            settings = popup.get_settings()

            filename, filetype = QFileDialog.getSaveFileName(
                self,
                "Export Video As...",
                os.path.join(self.last_save_location, f"{self.file_savename}{self.renderer.VideoFormatCode.MP4.value}"),
                f"MP4 (*{self.renderer.VideoFormatCode.MP4.value});;MKV (*{self.renderer.VideoFormatCode.MKV.value});;AVI (*{self.renderer.VideoFormatCode.AVI.value})"
            )

            if filename != "":
                file_path, file_title = os.path.split(filename)
                self.last_save_location = file_path
                frame_count = self.renderer.get_frame_count(
                    fps=settings["fps"]
                )
                progress_popup = QProgressDialog("Rendering frames...", "Abort", 0, frame_count, self)
                progress_popup.setWindowModality(Qt.WindowModal)
                progress_popup.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)
                progress_popup.setWindowTitle("Exporting Video...")
                progress_popup.setFixedSize(300, 100)

                if IS_REGISTERED:
                    add_watermark = False
                else:
                    add_watermark = True

                profiler = cProfile.Profile()
                profiler.enable()
                self.renderer.export_video(
                    filename=filename,
                    size=(settings["width"], settings["height"]),
                    fps=settings["fps"],
                    keep_aspect=settings["keep_aspect"],
                    watermark=add_watermark,
                    progress_dialog=progress_popup
                )
                profiler.disable()
                profiler.dump_stats(os.path.join("out", f"{filename}.prof"))

                if progress_popup.wasCanceled():
                    choice = QMessageBox.warning(
                        self,
                        "Export Aborted",
                        f"Export video aborted!",
                        QMessageBox.Ok
                    )
                else:
                    choice = QMessageBox.information(
                        self,
                        "Export Complete",
                        f"Export video successful!",
                        QMessageBox.Ok
                    )

    def hotkeys_clicked(self):
        popup = HotkeysInfo(parent=self)

        result = popup.exec()

    def registration_clicked(self):
        popup = RegistrationInfo(parent=self)

        result = popup.exec()

    def about_clicked(self):
        popup = About(parent=self)

        result = popup.exec()

    # TODO: Add unit testing (https://realpython.com/python-testing/)
    # TODO: Add documentation (https://realpython.com/python-doctest/)


# Image playback class
#   Provides an abstraction for displaying images and audio in the GUI
class Player:
    def __init__(self,
                 binary_waterfall,
                 display,
                 set_playbutton_function=None,
                 set_seekbar_function=None,
                 max_dim=512,
                 fps=120
                 ):
        self.bw = binary_waterfall

        self.display = display

        self.set_dims(max_dim=max_dim)

        self.set_play_button = set_playbutton_function
        self.set_seekbar_function = set_seekbar_function

        # Initialize player as black
        self.clear_image()

        # Make the QMediaPlayer for audio playback
        self.audio = QMediaPlayer()
        # self.audio_output = QAudioOutput()
        # self.audio.setAudioOutput(self.audio_output)

        # Set audio playback settings
        self.set_volume(100)

        # Set set_image_timestamp to run when the audio position is changed
        self.audio.positionChanged.connect(self.set_image_timestamp)
        self.audio.positionChanged.connect(self.set_seekbar_if_given)
        # Also, make sure it's updating more frequently (default is too slow when playing)
        self.fps_min = 1
        self.fps_max = 120
        self.set_fps(fps)

        # Setup change state handler
        self.audio.stateChanged.connect(self.state_changed_handler)

    def __del__(self):
        self.running = False

    def set_dims(self, max_dim):
        self.max_dim = max_dim
        if self.bw.width > self.bw.height:
            self.width = round(max_dim)
            self.height = round(self.width * (self.bw.height / self.bw.width))
        else:
            self.height = round(max_dim)
            self.width = round(self.height * (self.bw.width / self.bw.height))

        self.dim = (self.width, self.height)

    def set_fps(self, fps):
        self.fps = min(max(fps, self.fps_min), self.fps_max)
        self.frame_ms = math.floor(1000 / self.fps)
        self.audio.setNotifyInterval(self.frame_ms)

    def clear_image(self):
        background_image = Image.new(
            mode="RGBA",
            size=(self.width, self.height),
            color="#000"
        )

        background_image = Watermarker().mark(background_image)

        img_bytestring = background_image.convert("RGB").tobytes()

        qimg = QImage(
            img_bytestring,
            self.width,
            self.height,
            3 * self.width,
            QImage.Format.Format_RGB888
        )

        self.set_image(qimg)

    def update_dims(self, max_dim):
        # Change dims
        self.set_dims(max_dim=max_dim)

        # Update image
        if self.bw.filename == None:
            self.clear_image()
        else:
            self.set_image(self.image)

    def refresh_dims(self):
        self.update_dims(self.max_dim)

    def set_volume(self, volume):
        self.volume = volume
        self.audio.setVolume(volume)

    def scale_image(self, image):
        return image.scaled(self.width, self.height)

    def set_image(self, image):
        self.image = self.scale_image(image)

        # Compute the QPixmap version
        qpixmap = QPixmap.fromImage(self.image)

        # Set the picture
        self.display.setPixmap(qpixmap)

    def get_position(self):
        return self.audio.position()

    def get_duration(self):
        return self.audio.duration()

    def set_position(self, ms):
        duration = self.get_duration()

        # Validate it's in range, and if it's not, clip it
        ms = math.ceil(ms)
        if ms < 0:
            ms = 0
        if ms > duration:
            ms = duration

        if self.bw.filename != None:
            self.audio.setPosition(ms)

        # If the file is at the end, pause
        if ms == duration:
            self.pause()

    def set_playbutton_if_given(self, play):
        if self.set_play_button != None:
            self.set_play_button(play=play)

    def set_seekbar_if_given(self, ms):
        if self.set_seekbar_function != None:
            self.set_seekbar_function(ms)

    def state_changed_handler(self, media_state):
        if media_state == self.audio.PlayingState:
            self.set_playbutton_if_given(play=False)
        elif media_state == self.audio.PausedState:
            self.set_playbutton_if_given(play=True)
        elif media_state == self.audio.StoppedState:
            self.set_playbutton_if_given(play=True)

    def play(self):
        self.audio.play()

    def pause(self):
        self.audio.pause()

    def forward(self, ms=5000):
        new_pos = self.get_position() + ms
        self.set_position(new_pos)

    def back(self, ms=5000):
        new_pos = self.get_position() - ms
        self.set_position(new_pos)

    def frame_forward(self):
        self.forward(ms=self.frame_ms)

    def frame_back(self):
        self.back(ms=self.frame_ms)

    def restart(self):
        self.set_position(0)

    def set_audio_file(self, filename):
        if filename == None:
            url = QUrl(None)
        else:
            url = QUrl.fromLocalFile(self.bw.audio_filename)
        media = QMediaContent(url)
        self.audio.setMedia(media)

    def open_file(self, filename):
        self.close_file()

        self.bw.change_filename(filename)
        self.bw.compute_audio()

        self.set_audio_file(self.bw.audio_filename)

        self.set_image_timestamp(self.get_position())

    def close_file(self):
        self.pause()

        self.audio.stop()
        time.sleep(0.001)  # Without a short delay here, we crash
        self.set_audio_file(None)

        self.bw.change_filename(None)
        self.bw.compute_audio()

        self.restart()
        self.clear_image()

    def file_is_open(self):
        if self.bw.filename == None:
            return False
        else:
            return True

    def is_playing(self):
        if self.audio.state() == self.audio.PlayingState:
            return True
        else:
            return False

    def set_image_timestamp(self, ms):
        if self.bw.filename == None:
            self.clear_image()
        else:
            self.set_image(self.bw.get_frame_qimage(ms))

    def update_image(self):
        ms = self.get_position()
        self.set_image_timestamp(ms)

    def set_audio_settings(self,
                           num_channels,
                           sample_bytes,
                           sample_rate,
                           volume
                           ):
        self.bw.set_audio_settings(
            num_channels=num_channels,
            sample_bytes=sample_bytes,
            sample_rate=sample_rate,
            volume=volume
        )
        # Re-open newly computed file
        self.set_audio_file(None)
        self.set_audio_file(self.bw.audio_filename)


# Renderer class
#   Provides an abstraction for rendering images, audio, and video to files
class Renderer:
    def __init__(self,
                 binary_waterfall,
                 ):
        self.bw = binary_waterfall
        self.watermarker = Watermarker()

    class ImageFormatCode(Enum):
        JPEG = ".jpg"
        PNG = ".png"
        BITMAP = ".bmp"

    class AudioFormatCode(Enum):
        WAVE = ".wav"
        MP3 = ".mp3"
        FLAC = ".flac"

    class VideoFormatCode(Enum):
        MP4 = ".mp4"
        MKV = ".mkv"
        AVI = ".avi"

    def make_file_path(self, filename):
        file_path, file_title = os.path.split(filename)
        os.makedirs(file_path, exist_ok=True)

    def export_frame(self,
                     ms,
                     filename,
                     size=None,
                     keep_aspect=False,
                     watermark=False
                     ):
        self.make_file_path(filename)

        if self.bw.audio_filename == None:
            # If no file is loaded, make a black image
            source = Image.new(
                mode="RGBA",
                size=(self.bw.width, self.bw.height),
                color="#000"
            )
        else:
            source = self.bw.get_frame_image(ms).convert("RGBA")

        # Resize with aspect ratio, paste onto black
        if size == None:
            resized = source
        else:
            resized = fit_to_frame(
                image=source,
                frame_size=size,
                scaling=Image.NEAREST,
                transparent=False
            )

        # Watermark
        if watermark:
            resized = self.watermarker.mark(resized)

        final = resized.convert("RGB")

        final.save(filename)

    def export_audio(self, filename):
        filename_main, filename_ext = os.path.splitext(filename)
        filename_ext = filename_ext.lower()

        self.make_file_path(filename)

        if filename_ext == self.AudioFormatCode.WAVE.value:
            # Just copy the .wav file
            shutil.copy(self.bw.audio_filename, filename)
        elif filename_ext == self.AudioFormatCode.MP3.value:
            # Use Pydub to export MP3
            pydub.AudioSegment.from_wav(self.bw.audio_filename).export(filename, format="mp3")
        elif filename_ext == self.AudioFormatCode.FLAC.value:
            # Use Pydub to export FLAC
            pydub.AudioSegment.from_wav(self.bw.audio_filename).export(filename, format="flac")

    def get_frame_count(self, fps):
        audio_duration = self.bw.get_audio_length() / 1000
        frame_count = round(audio_duration * fps)

        return frame_count

    def export_sequence(self,
                        directory,
                        fps,
                        size=None,
                        keep_aspect=False,
                        format=None,
                        watermark=False,
                        progress_dialog=None
                        ):
        self.make_file_path(directory)

        frame_count = self.get_frame_count(fps)

        frame_number_digits = len(str(frame_count))

        if format is None:
            format = self.ImageFormatCode.PNG

        frames = range(frame_count)
        if progress_dialog is not None:
            progress_dialog.setValue(0)

        with multiprocessing.Pool() as pool:
            pool.starmap(self.process_frame, zip(frames, repeat(format), repeat(frame_number_digits), repeat(directory), repeat(fps), repeat(size), repeat(keep_aspect), repeat(watermark)))

        if progress_dialog is not None:
            progress_dialog.setValue(frame_count)

    def process_frame(self, frame: int, image_format: ImageFormatCode, frame_number_digits: int, directory: any, fps: float, size: Optional[any], keep_aspect: bool, watermark: bool, progress_dialog: Optional[any] = None) -> None:
        frame_number = str(frame).rjust(frame_number_digits, "0")
        frame_filename = os.path.join(directory, f"{frame_number}{image_format.value}")
        frame_ms = round((frame / fps) * 1000)

        self.export_frame(
            ms=frame_ms,
            filename=frame_filename,
            size=size,
            keep_aspect=keep_aspect,
            watermark=watermark
        )

    def export_video(self,
                     filename,
                     fps,
                     size=None,
                     keep_aspect=False,
                     watermark=False,
                     progress_dialog=None
                     ):
        # Get temporary directory
        temp_dir = tempfile.mkdtemp()

        # Make file names
        image_dir = os.path.join(temp_dir, "images")
        audio_file = os.path.join(temp_dir, "audio.wav")
        filename_main, filename_ext = os.path.splitext(filename)
        filename_path, filename_title = os.path.split(filename)
        frames_file = os.path.join(temp_dir, "frames.txt")
        video_file = os.path.join(temp_dir, f"video{filename_ext}")

        # Set progress dialog to not close when at max
        if progress_dialog is not None:
            progress_dialog.setAutoReset(False)

        # Export image sequence
        self.export_sequence(
            directory=image_dir,
            fps=fps,
            size=size,
            keep_aspect=keep_aspect,
            format=self.ImageFormatCode.PNG,
            watermark=watermark,
            progress_dialog=progress_dialog
        )

        if progress_dialog is not None:
            if progress_dialog.wasCanceled():
                shutil.rmtree(temp_dir)
                return

        # Export audio
        self.export_audio(audio_file)

        # Prepare the custom logger to update the progress box
        custom_logger = QtBarLoggerMoviepy()
        if progress_dialog is not None:
            progress_dialog.setLabelText("Splicing final video file...")
            custom_logger.set_progress_dialog(progress_dialog, start_progress=0)

        # Make a list of the image filenames
        frames_list = list()
        for frame_filename in os.listdir(image_dir):
            full_frame_filename = os.path.join(image_dir, frame_filename)
            frames_list.append(full_frame_filename)

        # Merge image sequence and audio into final video
        sequence_clip = ImageSequenceClip(frames_list, fps=fps)
        audio_clip = AudioFileClip(audio_file)

        video_clip = sequence_clip.set_audio(audio_clip)
        video_clip.write_videofile(video_file, logger=custom_logger)

        if progress_dialog is not None:
            if progress_dialog.wasCanceled():
                shutil.rmtree(temp_dir)
                return

            # Reset progress dialog and set to exit on completion
            progress_dialog.setLabelText("Wrapping up...")
            progress_dialog.setValue(0)
            progress_dialog.setMaximum(100)
            progress_dialog.setAutoReset(True)

        # Move video to final location
        os.makedirs(filename_path, exist_ok=True)
        shutil.move(video_file, filename)

        # Delete temporary files
        shutil.rmtree(temp_dir)

        if progress_dialog is not None:
            progress_dialog.setValue(100)


# Main window class
#   Handles variables related to the main window.
#   Any actual program functionality or additional dialogs are
#   handled using different classes
class MainWindow:
    def __init__(self, qt_args):
        self.app = QApplication(qt_args)
        self.window = MyQMainWindow()

    def run(self):
        self.window.show()
        self.app.exec()


def main(args):
    main_window = MainWindow(args)
    main_window.run()


def run():
    main(sys.argv)


if __name__ == "__main__":
    run()
