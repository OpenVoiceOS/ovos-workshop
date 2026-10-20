# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import shutil
from os.path import join, expanduser, isdir
from typing import TextIO

from ovos_config.locations import get_xdg_data_save_path
from ovos_config.meta import get_xdg_base
from ovos_utils.log import log_deprecation


class FileSystemAccess:
    def __init__(self, path: str):
        """
        Create a filesystem in a valid location.
        @param path: path basename/name of the module requesting a filesystem
        """
        self.path = self.__init_path(path)

    @staticmethod
    def __init_path(path: str):
        """
        Initialize a directory for filesystem access.
        @param path: path basename to initialize
        @return: validated existing path for this filesystem
        """
        if not isinstance(path, str) or len(path) == 0:
            raise ValueError("path must be initialized as a non empty string")

        old_path = expanduser(f'~/.{get_xdg_base()}/{path}')
        xdg_path = expanduser(f'{get_xdg_data_save_path()}/filesystem/{path}')
        # Migrate from the old location if it still exists
        if isdir(old_path) and not isdir(xdg_path):
            log_deprecation(f"Settings at {old_path} will be ignored", "0.1.0")
            shutil.move(old_path, xdg_path)

        os.makedirs(xdg_path, exist_ok=True)
        return xdg_path

    def open(self, filename: str, mode: str) -> TextIO:
        """
        Open the requested file in this FileSystem in the requested mode.
        @param filename: string filename, relative to this FileSystemAccess
        @param mode: mode to open file with (i.e. `rb`, `w+`)
        @return: TextIO object for the requested file in the requested mode
        """
        file_path = join(self.path, filename)
        return open(file_path, mode)

    def exists(self, filename: str) -> bool:
        """
        Check if a file exists in the namespace.
        @param filename: string filename, relative to this FileSystemAccess
        @return: True if the filename exists, else False
        """
        return os.path.exists(join(self.path, filename))
