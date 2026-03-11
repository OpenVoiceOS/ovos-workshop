# Copyright 2018 Mycroft AI Inc.
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
#
"""Handling of skill data such as intents and regular expressions."""
import abc
import json
import re
from collections import namedtuple
from os import walk
from os.path import dirname
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from langcodes import tag_distance
from ovos_config.locations import get_xdg_data_save_path
from ovos_utils import flatten_list
from ovos_utils.bracket_expansion import expand_template
from ovos_utils.dialog import MustacheDialogRenderer, load_dialogs
from ovos_utils.log import LOG

SkillResourceTypes = namedtuple(
    "SkillResourceTypes",
    [
        "dialog",
        "entity",
        "intent",
        "list",
        "named_value",
        "regex",
        "template",
        "vocabulary",
        "word",
        "qml",
        "json"
    ]
)


def locate_base_directories(skill_directory: str,
                            resource_subdirectory: Optional[str] = None) -> \
        List[Path]:
    """
    Locate all possible resource directories found in the given skill_directory
    @param skill_directory: skill base directory to search for resources
    @param resource_subdirectory: optional extra resource directory to prepend
    @return: list of existing skill resource directories
    """
    base_dirs = [Path(skill_directory, resource_subdirectory)] if \
        resource_subdirectory else []
    base_dirs += [Path(skill_directory, "locale")]
    candidates = []
    for directory in base_dirs:
        if directory.exists():
            candidates.append(directory)
    return candidates


def locate_lang_directories(lang: str, skill_directory: str,
                            resource_subdirectory: Optional[str] = None) -> List[Path]:
    """
    Locate all possible resource directories found in the given skill_directory
    for the specified language
    @param lang: BCP-47 language code to get resources for
    @param skill_directory: skill base directory to search for resources
    @param resource_subdirectory: optional extra resource directory to prepend
    @return: list of existing skill resource directories for the given lang
    """
    base_dirs = [Path(skill_directory, "locale")]
    if resource_subdirectory:
        base_dirs.append(Path(skill_directory, resource_subdirectory))
    candidates = []
    for directory in base_dirs:
        if directory.exists():
            for folder in directory.iterdir():
                if folder.is_dir():
                    try:
                        score = tag_distance(lang, folder.name)
                    except:  # not a valid language code
                        continue
                    # https://langcodes-hickford.readthedocs.io/en/sphinx/index.html#distance-values
                    # 0 -> These codes represent the same language, possibly after filling in values and normalizing.
                    # 1- 3 -> These codes indicate a minor regional difference.
                    # 4 - 10 -> These codes indicate a significant but unproblematic regional difference.
                    if score < 10:
                        candidates.append((folder, score))
    # sort by distance to target lang code
    candidates = sorted(candidates, key=lambda k: k[1])
    return [c[0] for c in candidates]


def find_resource(res_name: str, root_dir: str, res_dirname: str,
                  lang: Optional[str] = None) -> Optional[Path]:
    """
    Find a resource file.

    Searches for the given filename using this scheme:
        1. Search the resource lang directory:
            <skill>/<res_dirname>/<lang>/<res_name>
        2. Search the resource directory:
            <skill>/<res_dirname>/<res_name>
        3. Search the locale lang directory or other subdirectory:
            <skill>/locale/<lang>/<res_name> or
            <skill>/locale/<lang>/.../<res_name>

    Args:
        res_name (string): The resource name to be found
        root_dir (string): A skill root directory
        res_dirname (string): A skill sub directory
        lang (string): language folder to be used

    Returns:
        Path: The full path to the resource file or None if not found
    """
    if lang:
        for directory in locate_lang_directories(lang, root_dir, '.'):
            # Iterate over nodes in the language directory
            for x in directory.iterdir():
                if x.is_file() and res_name == x.name:
                    return x
                elif x.is_dir() and x.name == res_dirname:
                    for y in x.iterdir():
                        # Iterate over resource subdirectories within a lang dir
                        if y.is_file() and res_name == y.name:
                            return y

    for directory in locate_base_directories(root_dir, res_dirname):
        for d, _, file_names in walk(directory):
            if res_name in file_names:
                return Path(directory, d, res_name)


class ResourceType:
    """Defines the attributes of a type of skill resource.

    Examples:
        dialog = ResourceType("dialog", ".dialog")
        dialog.locate_base_directory(self.root_dir, self.lang)

        named_value = ResourceType("named_value", ".value")
        named_value.locate_base_directory(self.root_dir, self.lang)

    Attributes:
        resource_type: one of a predefined set of resource types for skills
        file_extension: the file extension associated with the resource type
        base_directory: directory containing all files for the resource type
    """

    def __init__(self, resource_type: str, file_extension: str,
                 language: Optional[str] = None):
        self.resource_type = resource_type
        self.file_extension = file_extension
        self.language = language
        self.base_directory = None
        self.user_directory = None
        self.workshop_directory = None

    def locate_workshop_directory(self):
        if not self.language:
            return
        for path in locate_lang_directories(self.language, dirname(__file__)):
            self.workshop_directory = path
            return

    def locate_lang_directories(self, skill_directory):
        if not self.language:
            return []
        resource_subdirectory = self._get_resource_subdirectory()
        return locate_lang_directories(self.language,
                                       skill_directory,
                                       resource_subdirectory)

    def locate_user_directory(self, skill_id):
        skill_directory = Path(get_xdg_data_save_path(), "resources", skill_id)
        if skill_directory.exists():
            self.user_directory = skill_directory

    def _locate_base_no_lang(self, skill_directory, resource_subdirectory):
        possible_directories = (
            Path(skill_directory, resource_subdirectory),
            Path(skill_directory),
        )
        for directory in possible_directories:
            if directory.exists():
                self.base_directory = directory
                return

        # check for lang resources defined by the user
        # user data is usually meant as an override for skill data
        # but it may be the only data source in some rare instances
        if self.user_directory:
            self.base_directory = self.user_directory

    def locate_base_directory(self, skill_directory: str) -> Optional[str]:
        """Find the skill's base directory for the specified resource type.

        There are three supported methodologies for storing resource files.
        The preferred method is to use the "locale" directory but older methods
        are included in the search for backwards compatibility.  The three
        directory schemes are:
           <skill>/locale/<lang>/.../<resource_type>
           <skill>/<resource_subdirectory>/<lang>/
           <skill>/<resource_subdirectory>
        If the directory for the specified language doesn't exist, fall back to
        the default "en-us".

        Args:
            skill_directory: the root directory of a skill
        Returns:
            the skill's directory for the resource type or None if not found
        """
        resource_subdirectory = self._get_resource_subdirectory()
        if not self.language:
            self._locate_base_no_lang(skill_directory, resource_subdirectory)
            return

        # check for lang resources shipped by the skill
        possible_directories = []
        if resource_subdirectory:
            subdirectory_path = Path(skill_directory).joinpath(resource_subdirectory)
            possible_directories += self.locate_lang_directories(str(subdirectory_path))
        possible_directories += self.locate_lang_directories(skill_directory)

        for directory in possible_directories:
            if directory.exists():
                self.base_directory = directory
                return

        # check for lang resources defined by the user
        # user data is usually meant as an override for skill data
        # but it may be the only data source in some rare instances
        if self.user_directory:
            self.base_directory = self.user_directory

    def _get_resource_subdirectory(self) -> Optional[str]:
        """Returns the subdirectory for this resource type.

        In the older directory schemes, several resource types were stored
        in the same set of three directories (dialog, regex, vocab).
        """
        subdirectories = dict(
            dialog="dialog",
            entity="vocab",
            intent="vocab",
            list="dialog",
            named_value="dialog",
            regex="regex",
            template="dialog",
            vocab="vocab",
            word="dialog",
            qml="gui"
        )

        return subdirectories.get(self.resource_type)


class ResourceFile:
    """Loads a resource file for the user's configured language.

    Attributes:
        resource_type: attributes of the resource type (dialog, vocab, etc.)
        resource_name: file name of the resource, with or without extension
        file_path: absolute path to the file
    """

    def __init__(self, resource_type: ResourceType, resource_name: str):
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.file_path = self._locate()

    def _locate(self) -> Optional[str]:
        """Locates a resource file in the skill's locale directory.

        A skill's locale directory can contain a subdirectory structure defined
        by the skill author.  Walk the directory and any subdirectories to
        find the resource file.
        """
        file_path = None
        if self.resource_name.endswith(self.resource_type.file_extension):
            file_name = self.resource_name
        else:
            file_name = self.resource_name + self.resource_type.file_extension

        # first check for user defined resource files
        # usually these resources are overrides to
        # customize dialogs or provide additional languages
        if self.resource_type.user_directory:
            walk_directory = str(self.resource_type.user_directory)
            for directory, _, file_names in walk(walk_directory):
                if file_name in file_names:
                    file_path = Path(directory, file_name)

        # check the skill resources
        if file_path is None:
            walk_directory = str(self.resource_type.base_directory)
            for directory, _, file_names in walk(walk_directory):
                if file_name in file_names:
                    file_path = Path(directory, file_name)

        # check ovos-workshop resources
        if file_path is None and self.resource_type.workshop_directory is not None:
            walk_directory = str(self.resource_type.workshop_directory)
            for directory, _, file_names in walk(walk_directory):
                if file_name in file_names:
                    file_path = Path(directory, file_name)

        if file_path is None:
            LOG.debug(f"Could not find resource file {file_name} for lang: {self.resource_type.language}")

        return file_path

    @abc.abstractmethod
    def load(self):
        """Override in subclass to define resource type loading behavior."""
        pass

    def _read(self) -> str:
        """Reads the specified file, removing comment and empty lines."""
        with open(self.file_path) as resource_file:
            for line in [line.strip() for line in resource_file.readlines()]:
                if not line or line.startswith("#"):
                    continue
                yield line


class QmlFile(ResourceFile):
    def _locate(self):
        """ QML files are special because we do not want to walk the directory """
        file_path = None
        if self.resource_name.endswith(self.resource_type.file_extension):
            file_name = self.resource_name
        else:
            file_name = self.resource_name + self.resource_type.file_extension

        # first check for user defined resource files
        # usually these resources are overrides
        # eg, to change hardcoded color or text
        if self.resource_type.user_directory:
            for x in self.resource_type.user_directory.iterdir():
                if x.is_file() and file_name == x.name:
                    file_path = Path(self.resource_type.user_directory, file_name)

        # check the skill resources
        if file_path is None:
            for x in self.resource_type.base_directory.iterdir():
                if x.is_file() and file_name == x.name:
                    file_path = Path(self.resource_type.base_directory, file_name)

        if file_path is None:
            LOG.error(f"Could not find resource file {file_name}")

        return file_path

    def load(self):
        return str(self.file_path)


class JsonFile(ResourceFile):
    def load(self) -> Dict[str, Any]:
        if self.file_path is not None:
            try:
                with open(self.file_path) as f:
                    return json.load(f)
            except Exception as e:
                LOG.error(f"Failed to load {self.file_path}: {e}")
        return {}


class DialogFile(ResourceFile):
    """Defines a dialog file, which is used instruct TTS what to speak."""

    def __init__(self, resource_type, resource_name):
        super().__init__(resource_type, resource_name)
        self.data = None

    def load(self) -> List[str]:
        """Load and lines from a file and populate the variables.

        Returns:
            Contents of the file with variables resolved.
        """
        dialogs = None
        if self.file_path is not None:
            dialogs = []
            for line in self._read():
                line = line.replace("{{", "{").replace("}}", "}")
                if self.data is not None:
                    line = line.format(**self.data)
                dialogs.append(line)

        return dialogs

    def render(self, dialog_renderer):
        """Renders a random phrase from a dialog file.

        If no file is found, the requested phrase is returned as the string. This
        will use the default language for translations.

        Returns:
            str: a randomized version of the phrase
        """
        return dialog_renderer.render(self.resource_name, self.data)


class VocabularyFile(ResourceFile):
    """Defines a vocabulary file, which skill use to form intents."""

    def load(self) -> List[List[str]]:
        """Loads a vocabulary file.

        If a record in a vocabulary file contains sets of words inside
        parentheses, generate a vocabulary item for each permutation within
        the parentheses.

        Returns:
            List of lines in the file.  Each item in the list is a list of
            strings that represent different options based on regular
            expression.
        """
        vocabulary = []
        if self.file_path is not None:
            for line in self._read():
                vocabulary.append(expand_template(line.lower()))
        return vocabulary


class IntentFile(ResourceFile):
    """Defines an intent file, which skill use to form intents."""

    def __init__(self, resource_type, resource_name):
        super().__init__(resource_type, resource_name)
        self.data = None

    def load(self, entities: bool = True) -> List[str]:
        """Load file containing intents.

        Args:
            entities: include mustache entities, default True
        Returns:
            A list representation of the records in the file.
        """
        intents = []
        if self.file_path is not None:
            for line in self._read():
                line = line.replace("{{", "{").replace("}}", "}")
                intents.extend(flatten_list(expand_template(line.lower())))
            if not entities:
                intents = [re.sub(r'{.*?}\s?', '', intent).strip() for intent in intents]
            elif self.data:
                intents = [intent.format(**self.data) for intent in intents]
        return intents

    def render(self, dialog_renderer):
        """Renders a random phrase from a dialog file.

        If no file is found, the requested phrase is returned as the string. This
        will use the default language for translations.

        Returns:
            str: a randomized version of the phrase
        """
        return dialog_renderer.render(self.resource_name, self.data)


class NamedValueFile(ResourceFile):
    """Defines a named value file, which maps a variable to a values."""

    def __init__(self, resource_type, resource_name):
        super().__init__(resource_type, resource_name)
        self.delimiter = ","

    def load(self) -> dict:
        """Load file containing names and values.

        Returns:
            A dictionary representation of the records in the file.
        """
        named_values = dict()
        if self.file_path is not None:
            for line in self._read():
                name, value = self._load_line(line)
                if name is not None and value is not None:
                    named_values[name] = value
        return named_values

    def _load_line(self, line: str) -> Tuple[str, str]:
        """Attempts to split the name and value for dictionary loading.

        Args:
            line: a record in a .value file
        Returns:
            The name/value pair that will be loaded into a dictionary.
        """
        name = None
        value = None
        try:
            name, value = line.split(self.delimiter)
        except ValueError:
            LOG.exception(
                f"Failed to load value file {self.file_path} "
                f"record containing {line}"
            )

        return name, value


class ListFile(DialogFile):
    pass


class TemplateFile(DialogFile):
    pass


class RegexFile(ResourceFile):
    def load(self):
        regex_patterns = []
        if self.file_path:
            regex_patterns = [line for line in self._read()]

        return regex_patterns


class WordFile(ResourceFile):
    """Defines a word file, which defines a word in the configured language."""

    def load(self) -> Optional[str]:
        """Load and lines from a file and populate the variables.

        Returns:
            The word contained in the file
        """
        word = None
        if self.file_path is not None:
            for line in self._read():
                word = line
                break

        return word


class SkillResources:
    def __init__(self, skill_directory: str,
                 language: str,
                 dialog_renderer: Optional[MustacheDialogRenderer] = None,
                 skill_id: Optional[str] = None):
        self.skill_directory = skill_directory
        self.language = language
        self.skill_id = skill_id
        self.types = self._define_resource_types()
        self._dialog_renderer = dialog_renderer
        self.static = dict()

    @property
    def dialog_renderer(self) -> MustacheDialogRenderer:
        """
        Get a dialog renderer object for these resources
        """
        if not self._dialog_renderer:
            self._load_dialog_renderer()
        return self._dialog_renderer

    @dialog_renderer.setter
    def dialog_renderer(self, val: MustacheDialogRenderer):
        """
        Set the dialog renderer object for these resources
        """
        self._dialog_renderer = val

    def _load_dialog_renderer(self):
        """
        Initialize a MustacheDialogRenderer object for these resources
        """
        base_dirs = locate_lang_directories(self.language,
                                            self.skill_directory,
                                            "dialog")
        for directory in base_dirs:
            if directory.exists():
                dialog_dir = str(directory)
                self._dialog_renderer = load_dialogs(dialog_dir)
                return
        LOG.debug(f'No dialog loaded for {self.language}')

    def _define_resource_types(self) -> SkillResourceTypes:
        """
        Defines all known types of skill resource files.

        A resource file contains information the skill needs to function.
        Examples include dialog files to be spoken and vocab files for intent
        matching.
        """
        resource_types = dict(
            dialog=ResourceType("dialog", ".dialog", self.language),
            entity=ResourceType("entity", ".entity", self.language),
            intent=ResourceType("intent", ".intent", self.language),
            list=ResourceType("list", ".list", self.language),
            named_value=ResourceType("named_value", ".value", self.language),
            regex=ResourceType("regex", ".rx", self.language),
            template=ResourceType("template", ".template", self.language),
            vocabulary=ResourceType("vocab", ".voc", self.language),
            word=ResourceType("word", ".word", self.language),
            qml=ResourceType("qml", ".qml"),
            json=ResourceType("json", ".json", self.language)
        )
        for resource_type in resource_types.values():
            if self.skill_id:
                resource_type.locate_user_directory(self.skill_id)
            resource_type.locate_base_directory(self.skill_directory)
            resource_type.locate_workshop_directory()
        return SkillResourceTypes(**resource_types)

    def load_json_file(self, name: str = "skill.json") -> Dict[str, str]:
        jsonf = JsonFile(self.types.json, name)
        return jsonf.load()

    def load_dialog_file(self, name: str,
                         data: Optional[dict] = None) -> List[str]:
        """
        Loads the contents of a dialog file into memory.

        Named variables in the dialog are populated with values found in the
        data dictionary.

        Args:
            name: name of the dialog file (no extension needed)
            data: keyword arguments used to populate variables
        Returns:
            A list of phrases with variables resolved
        """
        dialog_file = DialogFile(self.types.dialog, name)
        dialog_file.data = data
        return dialog_file.load()

    def load_intent_file(self, name: str,
                         data: Optional[dict] = None,
                         entities: bool = True) -> List[str]:
        """
        Loads the contents of an intent file.

        Named entities in the intent are populated with values found in the
        data dictionary (if entities is True, default: True).

        If entities is False, the entities will be removed from the intent

        Args:
            name: name of the dialog file (no extension needed)
            data: optional keyword arguments used to populate entities
            entities: include mustache entities, default True
        Returns:
            A list of intent phrases
        """
        intent_file = IntentFile(self.types.intent, name)
        intent_file.data = data
        return intent_file.load(entities)

    def locate_qml_file(self, name: str) -> str:
        qml_file = QmlFile(self.types.qml, name)
        return qml_file.load()

    def load_list_file(self, name: str,
                       data: Optional[dict] = None) -> List[str]:
        """
        Load a file containing a list of words or phrases

        Named variables in the dialog are populated with values found in the
        data dictionary.

        Args:
            name: name of the list file (no extension needed)
            data: keyword arguments used to populate variables
        Returns:
            List of words or phrases read from the list file.
        """
        list_file = ListFile(self.types.list, name)
        list_file.data = data
        return list_file.load()

    def load_named_value_file(self, name: str,
                              delimiter: Optional[str] = None) -> dict:
        """
        Load file containing a set names and values.

        Loads a simple delimited file of name/value pairs.
        The name is the first item, the value is the second.

        Args:
            name: name of the .value file, no extension needed
            delimiter: delimiter character used
        Returns:
            File contents represented as a dictionary
        """
        if name in self.static:
            named_values = self.static[name]
        else:
            named_value_file = NamedValueFile(self.types.named_value, name)
            if delimiter is not None:
                named_value_file.delimiter = delimiter
            named_values = named_value_file.load()
            self.static[name] = named_values

        return named_values

    def load_regex_file(self, name: str) -> List[str]:
        """
        Loads a file containing regular expression patterns.

        The regular expression patterns are generally used to find a value
        in a user utterance the skill needs to properly perform the requested
        function.

        Args:
            name: name of the regular expression file, no extension needed
        Returns:
            List representation of the regular expression file.
        """
        regex_file = RegexFile(self.types.regex, name)
        return regex_file.load()

    def load_template_file(self, name: str,
                           data: Optional[dict] = None) -> List[str]:
        """
        Loads the contents of a dialog file into memory.

        Named variables in the dialog are populated with values found in the
        data dictionary.

        Args:
            name: name of the dialog file (no extension needed)
            data: keyword arguments used to populate variables
        Returns:
            A list of phrases with variables resolved
        """
        template_file = TemplateFile(self.types.template, name)
        template_file.data = data
        return template_file.load()

    def load_vocabulary_file(self, name: str) -> List[List[str]]:
        """
        Loads a file containing variations of words meaning the same thing.

        A vocabulary file defines words a skill uses for intent matching.
        It can also be used to match words in an utterance after intent
        matching is complete.

        Args:
            name: name of the regular expression file, no extension needed
        Returns:
            List representation of the regular expression file.
        """
        vocabulary_file = VocabularyFile(self.types.vocabulary, name)
        return vocabulary_file.load()

    def load_word_file(self, name: str) -> Optional[str]:
        """Loads a file containing a word.

        Args:
            name: name of the regular expression file, no extension needed
        Returns:
            List representation of the regular expression file.
        """
        word_file = WordFile(self.types.word, name)
        return word_file.load()

    def render_dialog(self, name: str, data: Optional[dict] = None) -> str:
        """
        Selects a record from a dialog file at random for TTS purposes.

        Args:
            name: name of the list file (no extension needed)
            data: keyword arguments used to populate variables
        Returns:
            Random record from the file with variables resolved.
        """
        resource_file = DialogFile(self.types.dialog, name)
        resource_file.data = data
        return resource_file.render(self.dialog_renderer)

    def load_skill_vocabulary(self, alphanumeric_skill_id: str) -> dict:
        """
        Load all vocabulary files in the skill's resources
        @param alphanumeric_skill_id: alphanumeric ID of the skill associated
            with these resources.
        @return: dict of vocab name to loaded contents
        """
        skill_vocabulary = {}
        base_directory = self.types.vocabulary.base_directory
        for directory, _, files in walk(base_directory):
            vocabulary_files = (
                file_name for file_name in files if file_name.endswith(".voc")
            )
            for file_name in vocabulary_files:
                vocab_type = alphanumeric_skill_id + file_name[:-4].title()
                vocabulary = self.load_vocabulary_file(file_name)
                if vocabulary:
                    skill_vocabulary[vocab_type] = vocabulary

        return skill_vocabulary

    def load_skill_regex(self, alphanumeric_skill_id: str) -> List[str]:
        """
        Load all regex files in the skill's resources
        @param alphanumeric_skill_id: alphanumeric ID of the skill associated
            with these resources.
        @return: list of string regex expressions
        """
        skill_regexes = []
        base_directory = self.types.regex.base_directory
        for directory, _, files in walk(base_directory):
            regex_files = (
                file_name for file_name in files if file_name.endswith(".rx")
            )
            for file_name in regex_files:
                skill_regexes.extend(self.load_regex_file(file_name))

        skill_regexes = self._make_unique_regex_group(
            skill_regexes, alphanumeric_skill_id
        )

        return skill_regexes

    @classmethod
    def get_available_languages(cls, skill_directory: str) -> List[str]:
        """
        Get all available languages for a skill
        @param skill_directory: skill base directory
        @return: list of available languages
        """
        base_dirs = locate_base_directories(skill_directory, "locale")
        languages = []
        for directory in base_dirs:
            for folder in directory.iterdir():
                if folder.name not in languages:
                    languages.append(folder.name)
        return languages

    def get_inventory(self, specific_type: str = "", language: str = "en-us"):
        """
        Get all available resources for a skill
        @param specific_type: optional, filter by resource type
        @param language: BCP-47 language code, defaults to en-us
        @return: dict of available resources
        """
        languages = SkillResources.get_available_languages(self.skill_directory)
        if language not in languages:
            raise ValueError(f"Language {language} not available for skill")

        inventory = dict()
        for type_ in self.types:
            if specific_type and type_.resource_type != specific_type:
                continue

            inventory[type_.resource_type] = list()

            # search all files in the directory and subdirectories and dump its name in a list
            base_dirs = locate_lang_directories(language, self.skill_directory)
            for directory in base_dirs:
                for file in directory.iterdir():
                    if file.suffix == type_.file_extension:
                        inventory[type_.resource_type].append(file.stem)

        inventory["languages"] = languages

        return inventory

    @staticmethod
    def _make_unique_regex_group(regexes: List[str],
                                 alphanumeric_skill_id: str) -> List[str]:
        """Adds skill ID to group ID in a regular expression for uniqueness.

        Args:
            regexes: regex string
            alphanumeric_skill_id: skill identifier
        Returns:
            regular expressions with uniquely named group IDs
        Raises:
            re.error if the regex does not compile
        """
        modified_regexes = []
        for regex in regexes:
            base = "(?P<" + alphanumeric_skill_id
            modified_regex = base.join(regex.split("(?P<"))
            re.compile(modified_regex)
            modified_regexes.append(modified_regex)

        return modified_regexes


class CoreResources(SkillResources):
    def __init__(self, language):
        directory = f"{dirname(__file__)}/locale"
        super().__init__(directory, language)


class UserResources(SkillResources):
    def __init__(self, language, skill_id):
        directory = f"{get_xdg_data_save_path()}/resources/{skill_id}"
        super().__init__(directory, language)


class RegexExtractor:
    def __init__(self, group_name: str, regex_patterns: List[str]):
        """
        Init an object representing an entity and a list of possible regex
        patterns for extracting it
        @param group_name: Named group entity to extract
        @param regex_patterns: List of string regex patterns to evaluate
        """
        self.group_name = group_name
        self.regex_patterns = regex_patterns

    def extract(self, utterance: str) -> Optional[str]:
        """
        Attempt to extract `group_name` from the specified `utterance`
        @param utterance: String to evaluate
        @return: Extracted `group_name` value if matched in `utterance`
        """
        extract = None
        pattern_match = self._match_utterance_to_patterns(utterance)
        if pattern_match is not None:
            extract = self._extract_group_from_match(pattern_match)
        self._log_extraction_result(extract)

        return extract

    def _match_utterance_to_patterns(self,
                                     utterance: str) -> Optional[re.Match]:
        """
        Compare `utterance` to all `regex_patterns` until a match is found.
        @param utterance: String to evaluate
        @return: re.Match object if utterance mathes any `regex_patterns`
        """
        pattern_match = None
        for pattern in self.regex_patterns:
            pattern_match = re.search(pattern, utterance)
            if pattern_match:
                break

        return pattern_match

    def _extract_group_from_match(self, pattern_match: re.Match) -> str:
        """
        Extract the specified regex group value.
        @param pattern_match: Match object associated with a particular input
        @return: String matched to `self.group_name`
        """
        extract = None
        try:
            extract = pattern_match.group(self.group_name).strip()
        except IndexError:
            pass
        else:
            if not extract:
                extract = None

        return extract

    def _log_extraction_result(self, extract: str):
        """
        Log the results of the matching.
        @param extract: the value extracted from the user utterance
        """
        if extract is None:
            LOG.info(f"No {self.group_name.lower()} extracted from utterance")
        else:
            LOG.info(f"{self.group_name} extracted from utterance: " + extract)
