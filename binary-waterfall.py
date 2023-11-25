#!/usr/bin/env python3

import os
import sys
import argparse
from enum import Enum
import yaml
import shutil
import math
import wave
import pydub
import mutagen.wave
import numpy as np
import time
from PIL import Image
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QGridLayout, QHBoxLayout,
    QLabel, QPushButton,
    QFileDialog, QAction,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QDialog, QDialogButtonBox, QSpinBox, QComboBox, QLineEdit,
    QMessageBox,
    QAbstractButton
)
from PyQt5.QtGui import (
    QImage, QPixmap, QIcon, QPainter
)

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
    COPYRIGHT = version_file_dict["LegalCopyright"]
    
    del(version_file_dict)


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
    }
}

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
    
    def __del__(self):
        self.cleanup()
    
    def set_filename(self, filename):
        # Delete current audio file if it exists
        self.delete_audio()
        
        if filename == None:
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
            PATH,
            file_main_name + os.path.extsep + "wav"
        )
    
    class ColorFmtCode(Enum):
        RED = "r"
        GREEN = "g"
        BLUE = "b"
        UNUSED = "x"
        VALID_OPTIONS = "rgbx"
    
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
        if red_count != 1:
            result["is_valid"] = False
            result["message"] = f"Exactly 1 red channel format specifier \"{self.ColorFmtCode.RED.value}\" needed, but {red_count} were given in format string \"{color_format_string}\""
            return result
        
        green_count = color_format_string.count(self.ColorFmtCode.GREEN.value)
        if green_count != 1:
            result["is_valid"] = False
            result["message"] = f"Exactly 1 green channel format specifier \"{self.ColorFmtCode.GREEN.value}\" needed, but {green_count} were given in format string \"{color_format_string}\""
            return result
        
        blue_count = color_format_string.count(self.ColorFmtCode.BLUE.value)
        if blue_count != 1:
            result["is_valid"] = False
            result["message"] = f"Exactly 1 blue channel format specifier \"{self.ColorFmtCode.BLUE.value}\" needed, but {blue_count} were given in format string \"{color_format_string}\""
            return result
        
        unused_count = color_format_string.count(self.ColorFmtCode.UNUSED.value)
        
        color_format_list = list()
        for c in color_format_string:
            if c not in self.ColorFmtCode.VALID_OPTIONS.value:
                result["is_valid"] = False
                result["message"] = f"Color formatting codes only accept \"{self.ColorFmtCode.RED.value}\" = red, \"{self.ColorFmtCode.GREEN.value}\" = green, \"{self.ColorFmtCode.BLUE.value}\" = blue, \"{self.ColorFmtCode.UNUSED.value}\" = unused"
                return result
            if c == self.ColorFmtCode.RED.value:
                color_format_list.append(self.ColorFmtCode.RED)
            elif c == self.ColorFmtCode.GREEN.value:
                color_format_list.append(self.ColorFmtCode.GREEN)
            elif c == self.ColorFmtCode.BLUE.value:
                color_format_list.append(self.ColorFmtCode.BLUE)
            elif c == self.ColorFmtCode.UNUSED.value:
                color_format_list.append(self.ColorFmtCode.UNUSED)
        
        result["used_color_bytes"] = red_count + green_count + blue_count
        result["unused_color_bytes"] = unused_count
        result["color_bytes"] = result["used_color_bytes"] + result["unused_color_bytes"]
        result["color_format"] = color_format_list
        
        return result
    
    def set_color_format(self, color_format_string):
        parsed_string = self.parse_color_format(color_format_string)
        
        if parsed_string["is_valid"] == False:
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
        audio_length = mutagen.wave.WAVE(self.audio_filename).info.length
        self.audio_length_ms = math.ceil(audio_length * 1000)
    
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
                        this_byte[0] = self.bytes[current_address:current_address+1] # Red
                    elif c == self.ColorFmtCode.GREEN:
                        this_byte[1] = self.bytes[current_address:current_address+1] # Green
                    elif c == self.ColorFmtCode.BLUE:
                        this_byte[2] = self.bytes[current_address:current_address+1] # Blue
                    
                    current_address += 1
                
                picture_bytes += b"".join(this_byte)
        
        full_length = (self.width * self.height * self.used_color_bytes)
        picture_bytes_length = len(picture_bytes)
        # Pad picture data if we're near the end of the file
        if picture_bytes_length < full_length:
            pad_length = full_length - picture_bytes_length
            picture_bytes += b"\x00" * pad_length

        return picture_bytes
    
    # A 3D Numpy array (RGB)
    def get_frame_array(self, ms, flip=True):
        frame_bytesring = self.get_frame_bytestring(ms)
        frame_np = np.frombuffer(frame_bytesring, dtype=np.uint8)
        frame_array = frame_np.reshape((self.width, self.height, 3))
        if flip:
            # Flip vertically
            frame_array = np.flip(frame_array, axis=0)
        
        return frame_array
    
    # A PIL Image (RGB)
    def get_frame_image(self, ms, flip=True):
        frame_array = self.get_frame_array(ms, flip=flip)
        img = Image.fromarray(frame_array)
        
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

# Audio settings input window
#   User interface to set the audio settings (for computation)
class AudioSettings(QDialog):
    def __init__(self,
        num_channels,
        sample_bytes,
        sample_rate,
        volume
    ):
        super().__init__()
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
        color_format
    ):
        super().__init__()
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
            
            error_popup = QMessageBox()
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
    ):
        super().__init__()
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

# Custom image-based button
#   Allows very swaggy custom buttons
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
        return self.pixmap.size()

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
        
        self.player_label = QLabel()
        self.player_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.player = Player(
            binary_waterfall=self.bw,
            display=self.player_label,
            set_playbutton_function=self.set_play_button
        )
        
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
        self.transport_play.setFixedSize(self.transport_play.width, self.transport_play.height)
        self.transport_play.clicked.connect(self.play_clicked)
        
        self.transport_forward = ImageButton(
            pixmap=QPixmap(ICON_PATH["button"]["forward"]["base"]),
            pixmap_hover=QPixmap(ICON_PATH["button"]["forward"]["hover"]),
            pixmap_pressed=QPixmap(ICON_PATH["button"]["forward"]["clicked"]),
            scale=0.75,
            parent=self
        )
        self.transport_forward.setFixedSize(self.transport_forward.width, self.transport_forward.height)
        self.transport_forward.clicked.connect(self.forward_clicked)
        
        self.transport_back = ImageButton(
            pixmap=QPixmap(ICON_PATH["button"]["back"]["base"]),
            pixmap_hover=QPixmap(ICON_PATH["button"]["back"]["hover"]),
            pixmap_pressed=QPixmap(ICON_PATH["button"]["back"]["clicked"]),
            scale=0.75,
            parent=self
        )
        self.transport_back.setFixedSize(self.transport_back.width, self.transport_back.height)
        self.transport_back.clicked.connect(self.back_clicked)
        
        self.transport_restart = ImageButton(
            pixmap=QPixmap(ICON_PATH["button"]["restart"]["base"]),
            pixmap_hover=QPixmap(ICON_PATH["button"]["restart"]["hover"]),
            pixmap_pressed=QPixmap(ICON_PATH["button"]["restart"]["clicked"]),
            scale=0.5,
            parent=self
        )
        self.transport_restart.setFixedSize(self.transport_restart.width, self.transport_restart.height)
        self.transport_restart.clicked.connect(self.restart_clicked)
        
        self.transport_left_layout = QHBoxLayout()
        self.transport_left_layout.setSpacing(10)
        self.transport_left_layout.addWidget(self.transport_restart,)
        self.transport_left_layout.addWidget(self.transport_back)
        
        self.transport_right_layout = QHBoxLayout()
        self.transport_right_layout.setSpacing(10)
        self.transport_right_layout.addWidget(self.transport_forward)
        
        self.main_layout = QGridLayout()
        self.main_layout.setContentsMargins(0,0,0,10)
        self.main_layout.setSpacing(10)
        
        self.main_layout.addWidget(self.player_label, 0, 0, 1, 5, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addLayout(self.transport_left_layout, 1, 1, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.main_layout.addWidget(self.transport_play, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addLayout(self.transport_right_layout, 1, 3, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        
        self.main_widget = QWidget()
        self.main_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.main_widget)
        
        self.main_menu = self.menuBar()
        
        self.file_menu = self.main_menu.addMenu("&File")
        
        self.file_menu_open = QAction("&Open...", self)
        self.file_menu_open.triggered.connect(self.open_file_clicked)
        self.file_menu.addAction(self.file_menu_open)
        
        self.file_menu_close = QAction("&Close", self)
        self.file_menu_close.triggered.connect(self.close_file_clicked)
        self.file_menu.addAction(self.file_menu_close)
        
        self.settings_menu = self.file_menu = self.main_menu.addMenu("&Settings")
        
        self.settings_menu_audio = QAction("&Audio...", self)
        self.settings_menu_audio.triggered.connect(self.audio_settings_clicked)
        self.settings_menu.addAction(self.settings_menu_audio)
        
        self.settings_menu_video = QAction("&Video...", self)
        self.settings_menu_video.triggered.connect(self.video_settings_clicked)
        self.settings_menu.addAction(self.settings_menu_video)
        
        self.settings_menu_player = QAction("&Player...", self)
        self.settings_menu_player.triggered.connect(self.player_settings_clicked)
        self.settings_menu.addAction(self.settings_menu_player)
        
        # Set window to content size
        self.resize_window()
    
    def resize_window(self):
        self.setFixedSize(self.sizeHint())
    
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
            self.setWindowTitle(f"{TITLE} | {file_title}")
    
    def close_file_clicked(self):
        self.pause_player()
        
        self.player.close_file()
        self.setWindowTitle(f"{TITLE}")
    
    def audio_settings_clicked(self):
        popup = AudioSettings(
            num_channels=self.bw.num_channels,
            sample_bytes=self.bw.sample_bytes,
            sample_rate=self.bw.sample_rate,
            volume=self.bw.volume
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
            color_format=self.bw.get_color_format_string()
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
            fps=self.player.fps
        )
        
        result = popup.exec()
        
        if result:
            player_settings = popup.get_player_settings()
            self.player.set_fps(fps=player_settings["fps"])
            self.player.update_dims(max_dim=player_settings["max_view_dim"])
            # We need to wait a moment for the size hint to be computed
            QTimer.singleShot(10, self.resize_window)
    
    #TODO: Add transport bar (read-only)
    #TODO: Make transport bar seekable
    #TODO: Add player volume slider
    #TODO: Add export screenshot option
    #TODO: Add export audio option
    #TODO: Add export image sequence option
    #TODO: Add export video option

# Image playback class
#   Provides an abstraction for displaying images and audio in the GUI
class Player:
    def __init__(self,
        binary_waterfall,
        display,
        set_playbutton_function=None,
        max_dim=640,
        fps=120
    ):
        self.bw = binary_waterfall
        
        self.display = display
        
        self.set_dims(max_dim=max_dim)
        
        self.set_play_button = set_playbutton_function
        
        # Initialize player as black
        self.clear_image()
        
        # Make the QMediaPlayer for audio playback
        self.audio = QMediaPlayer()
        #self.audio_output = QAudioOutput()
        #self.audio.setAudioOutput(self.audio_output)
        
        # Set audio playback settings
        self.set_volume(100)
        
        # Set set_image_timestamp to run when the audio position is changed
        self.audio.positionChanged.connect(self.set_image_timestamp)
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
        self.fps_delay_ms = math.floor(1000 / self.fps)
        self.audio.setNotifyInterval(self.fps_delay_ms)
    
    def clear_image(self):
        img_bytestring = bytes([0 for x in range(self.width * self.height * 3)])
        
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
        time.sleep(0.001) # Without a short delay here, we crash
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



# A helper function for the argument parser
def file_path(string):
    if os.path.isfile(string):
        return string
    else:
        raise FileNotFoundError(string)

# Parse arguments
def parse_args(args):
    parser = argparse.ArgumentParser(
        description=f"{DESCRIPTION}\n\nDefault parameters are shown in [brackets].",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    '''
    parser.add_argument("-1", "--first", dest="first_arg", type=float, required=True,
        help="the first argument")
    parser.add_argument("-2", "--second", dest="second_arg", type=float, required=False, default=1.0,
        help="the second argument [1]")
    parser.add_argument("-o", "--operaton", dest="opcode", type=str, required=False, default="+",
        help="the operation to perform on the arguments, either \"+\", \"-\", \"*\", or \"/\" [+]")
    '''
    
    parsed_args, unparsed_args = parser.parse_known_args()
    return parsed_args, unparsed_args

def main(args):
    parsed_args, unparsed_args = parse_args(args)
    qt_args = [sys.argv[0]] + unparsed_args
    
    main_window = MainWindow(qt_args)
    main_window.run()

def run():
    main(sys.argv[1:])

if __name__ == "__main__":
    run()
