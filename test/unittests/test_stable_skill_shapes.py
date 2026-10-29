"""Resource shapes found in released skills must keep loading.

Each fixture copies the file layout of a stable skill wheel: duplicate base
names in nested folders (ovos-skill-local-media, ovos-skill-hello-world),
a dialog that mixes lines with and without a slot (ovos-skill-date-time),
empty placeholder files, and lowercase language folders.
"""
import json
import os
import random
import tempfile
import unittest
from os.path import join
from unittest import mock

from ovos_utils import camel_case_split
from ovos_utils.fakebus import FakeBus

from ovos_bus_client.message import Message
from ovos_workshop.decorators import intent_handler
from ovos_workshop.exceptions import DialogNotFound
from ovos_workshop.skills.ovos import OVOSSkill


def write_tree(root, files):
    for rel, text in files.items():
        path = join(root, "locale", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


class StableShapeCase(unittest.TestCase):
    def build(self, files, skill_class=OVOSSkill, skill_id="shape.test"):
        root = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, root, True)
        write_tree(root, files)
        self.bus = FakeBus()
        self.msgs = []
        self.bus.on("message", lambda m: self.msgs.append(json.loads(m)))
        skill = skill_class(bus=self.bus, skill_id=skill_id,
                            resources_dir=root)
        self.addCleanup(skill.default_shutdown)
        return skill

    def spoken(self):
        return [m["data"]["utterance"] for m in self.msgs
                if m["type"] in ("speak", "ovos.utterance.speak")]


class _TwoIntentSkill(OVOSSkill):
    @intent_handler("open.file.browser.intent")
    def handle_open(self, message):
        pass

    @intent_handler("good.intent")
    def handle_good(self, message):
        pass


class TestMalformedResourcesDoNotAbortInit(StableShapeCase):
    def test_duplicate_intent_in_nested_folder(self):
        skill = self.build({
            "en-us/open.file.browser.intent": "open the file browser\n",
            "en-us/intents/open.file.browser.intent": "open file browser\n",
            "en-us/good.intent": "say good\n",
        }, _TwoIntentSkill)
        registered = json.dumps([m["data"] for m in self.msgs])
        self.assertIn("say good", registered)
        self.assertIn("open the file browser", registered)
        self.assertTrue(skill._init_event.is_set())

    def test_duplicate_intent_with_mixed_case_name(self):
        skill = self.build({
            "en-us/intent/HowAreYou.intent": "how are you doing\n",
            "en-us/intents/HowAreYou.intent": "how are things\n",
            "en-us/open.file.browser.intent": "open the file browser\n",
            "en-us/good.intent": "say good\n",
        }, _TwoIntentSkill)
        skill.register_intent_file("HowAreYou.intent", lambda m: None)
        samples = [m["data"]["samples"] for m in self.msgs
                   if m["type"] == "ovos.intent.register.template"
                   and m["data"].get("intent_name", "").endswith("HowAreYou")]
        self.assertEqual(samples, [["how are things"]])
        self.assertTrue(skill._init_event.is_set())

    def test_dialog_mixing_lines_with_and_without_a_slot(self):
        skill = self.build({
            "en-us/time.current.dialog": "Uhrzeit\nes ist {time}\n"})
        for seed in range(20):
            random.seed(seed)
            self.assertIn(skill.render_dialog("time.current", {"time": "5"}),
                          {"Uhrzeit", "es ist 5"})
        skill.speak_dialog("time.current", {"time": "5"})
        self.assertNotIn("time.current", self.spoken())
        self.assertNotIn("time current", self.spoken())

    def test_empty_vocabulary_never_matches(self):
        skill = self.build({"en-us/blank.voc": "# nothing yet\n"})
        self.assertEqual(skill.voc_list("blank"), [])
        self.assertFalse(skill.voc_match("blank", "blank"))
        self.assertEqual(skill.remove_voc("some blank text", "blank"),
                         "some blank text")

    def test_duplicate_entity_registers_the_shallower_file(self):
        skill = self.build({
            "en-us/pet.entity": "cat\n",
            "en-us/sub/pet.entity": "dog\n"})
        skill.register_entity_file("pet.entity")
        pets = [m["data"]["samples"] for m in self.msgs
                if m["type"] == "ovos.entity.register"
                and m["data"].get("entity_name") == "pet"]
        self.assertEqual(pets, [["cat"]])

    def test_duplicate_entity_winner_is_by_depth_not_by_name(self):
        skill = self.build({
            "en-us/pet.entity": "cat\n",
            "en-us/a/pet.entity": "dog\n"})
        pets = [m["data"]["samples"] for m in self.msgs
                if m["type"] == "ovos.entity.register"
                and m["data"].get("entity_name") == "pet"]
        self.assertEqual(pets, [["cat"]])

    def test_duplicate_vocabulary_is_ignored_and_reported_once(self):
        skill = self.build({
            "en-us/yes.voc": "yes\n",
            "en-us/sub/yes.voc": "yep\n"})
        reports = []
        skill.log = type("L", (), {
            "warning": lambda self, m: reports.append(m),
            "debug": lambda *a: None, "info": lambda *a: None,
            "error": lambda *a: None, "exception": lambda *a: None})()
        for _ in range(3):
            self.assertFalse(skill.voc_match("yes", "yes"))
        self.assertEqual(skill.voc_list("yes"), [])
        self.assertEqual(len(reports), 1)
        self.assertIn("yes.voc", reports[0])


class TestWorkshopVocabularyIsNotRegistered(StableShapeCase):
    def test_only_the_skill_vocabulary_is_registered(self):
        skill = self.build({"en-us/hello.voc": "hello\n"})
        registered = []
        with mock.patch.object(skill.intent_service, "register_keyword",
                               lambda vocab_type, *args: registered.append(
                                   vocab_type)):
            skill.load_vocab_files()
        self.assertEqual(registered, [f"{skill.alphanumeric_skill_id}hello"])

    def test_cancel_still_matches(self):
        skill = self.build({"en-us/hello.voc": "hello\n"})
        self.assertTrue(skill.voc_match("forget it", "cancel"))


class TestDuplicateIntentWinner(StableShapeCase):
    GL = {
        "gl-es/intent/HowAreYou.intent":
            "como estiveches\ncomo estás\ncomo foi o teu día\n",
        "gl-es/intents/HowAreYou.intent":
            "como  che vai\ncomo che foi\ncomo che foi o día\ncomo estás",
    }

    def templates(self, name):
        return [m["data"] for m in self.msgs
                if m["type"] == "ovos.intent.register.template"
                and m["data"].get("intent_name", "").endswith(name)]

    def test_local_media_shape_registers_the_shallower_file(self):
        skill = self.build({
            "en-us/open.file.browser.intent": "open the file browser\n",
            "en-us/intents/open.file.browser.intent": "open file browser\n"})
        skill.register_intent_file("open.file.browser.intent", lambda m: None)
        registered = self.templates("open.file.browser")
        self.assertTrue(registered)
        self.assertEqual(registered[-1]["samples"], ["open the file browser"])

    def test_hello_world_shape_ties_pick_the_last_path(self):
        skill = self.build(self.GL)
        expected = join(skill.res_dir, "locale", "gl-es", "intents",
                        "HowAreYou.intent")
        for _ in range(2):
            self.assertEqual(skill._locate_lang_file(
                "HowAreYou.intent", ".intent", "gl-ES"), expected)
        with open(expected, encoding="utf-8") as f:
            self.assertEqual(f.read(), self.GL["gl-es/intents/HowAreYou.intent"])

    def test_winner_does_not_depend_on_walk_order(self):
        from pathlib import Path
        from unittest import mock
        skill = self.build(self.GL)
        original = Path.rglob
        results = set()
        for order in (lambda x: x, reversed,
                      lambda x: sorted(x, key=lambda p: hash(str(p)))):
            with mock.patch.object(
                    Path, "rglob",
                    lambda self, pat, o=order: list(o(list(original(self, pat))))):
                results.add(skill._locate_lang_file(
                    "HowAreYou.intent", ".intent", "gl-ES"))
        self.assertEqual(len(results), 1)
        self.assertTrue(results.pop().endswith("gl-es/intents/HowAreYou.intent"))

    def test_both_paths_are_named_in_one_warning(self):
        skill = self.build(self.GL)
        reports = []
        skill.log = type("L", (), {
            "warning": lambda self, m: reports.append(m),
            "debug": lambda *a: None, "info": lambda *a: None,
            "error": lambda *a: None, "exception": lambda *a: None})()
        for _ in range(3):
            skill._locate_lang_file("HowAreYou.intent", ".intent", "gl-ES")
        self.assertEqual(len(reports), 1)
        self.assertIn("gl-es/intent/HowAreYou.intent", reports[0])
        self.assertIn("gl-es/intents/HowAreYou.intent", reports[0])


class TestUserOverride(StableShapeCase):
    def test_user_dialog_wins_over_the_skill_dialog(self):
        from unittest import mock
        user_root = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, user_root, True)
        os.makedirs(join(user_root, "resources", "shape.test", "en-US"))
        with open(join(user_root, "resources", "shape.test", "en-US",
                       "hello.dialog"), "w") as f:
            f.write("from the user\n")
        with mock.patch("ovos_workshop.skills.ovos.get_xdg_data_save_path",
                        return_value=user_root):
            skill = self.build({"en-us/hello.dialog": "from the skill\n"})
            self.assertEqual(skill.render_dialog("hello"), "from the user")


class TestLegacyVocabularyApi(StableShapeCase):
    def test_vocabularies_without_a_language(self):
        skill = self.build({"en-us/yes.voc": "yes\n"})
        legacy = skill.load_lang(lang="en-US").vocabularies()
        self.assertEqual(legacy["yes"], ["yes"])
        self.assertEqual(skill.load_lang().vocabularies("en-US")["yes"],
                         ["yes"])
        self.assertIn("cancel", legacy)

    def test_vocabulary_file_keeps_the_written_order(self):
        skill = self.build({"en-us/pick.voc": "(sure|ok)\n"})
        self.assertEqual(
            skill.load_lang(lang="en-US").load_vocabulary_file("pick"),
            [["sure", "ok"]])


class TestSkillJsonFolderCase(StableShapeCase):
    def test_lowercase_language_folder(self):
        self.build({"en-us/skill.json": json.dumps(
            {"examples": ["what time is it"]})})
        examples = [m["data"] for m in self.msgs
                    if m["type"] == "homescreen.register.examples"]
        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["utterances"], ["what time is it"])
        self.assertEqual(examples[0]["lang"], "en-US")


class TestLoadLangKeepsTheResourcesApi(StableShapeCase):
    FILES = {
        "en-us/hello.dialog": "hello there\n",
        "en-us/quote.dialog": "quote one\n",
        "en-us/yes.voc": "yes\nsure\n",
    }

    def test_vocabulary_file_and_dialog_renderer(self):
        # ovos-good-manners-pipeline-plugin opm.py:234 and :246
        skill = self.build(self.FILES)
        resources = skill.load_lang(lang="en-US")
        self.assertEqual(sorted(sum(resources.load_vocabulary_file("yes"),
                                    [])), ["sure", "yes"])
        self.assertEqual(resources.dialog_renderer.render("hello"),
                         "hello there")

    def test_render_dialog_and_dialog_file(self):
        skill = self.build(self.FILES)
        resources = skill.load_lang(skill.res_dir, "en-us")
        self.assertEqual(resources.render_dialog("hello"), "hello there")
        self.assertEqual(resources.load_dialog_file("hello"),
                         ["hello there"])

    def test_legacy_method_warns_with_a_computed_removal_version(self):
        import warnings
        from ovos_workshop.version import VERSION_MAJOR
        skill = self.build(self.FILES)
        logged = []
        import ovos_workshop.skills._legacy_resources as legacy
        original = legacy.log_deprecation
        legacy.log_deprecation = lambda msg, version: logged.append(version)
        self.addCleanup(setattr, legacy, "log_deprecation", original)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            skill.load_lang(lang="en-US").load_vocabulary_file("yes")
        self.assertTrue(any(issubclass(w.category, DeprecationWarning)
                            for w in caught))
        self.assertEqual(logged, [f"{VERSION_MAJOR + 1}.0.0"])

    def test_still_a_locale_resources(self):
        from ovos_spec_tools import LocaleResources
        skill = self.build(self.FILES)
        resources = skill.load_lang()
        self.assertIsInstance(resources, LocaleResources)
        self.assertEqual(resources.load_vocabulary("yes", "en-US"),
                         ["yes", "sure"])


class TestRegisterRegex(StableShapeCase):
    def test_adapt_receives_a_single_prefix(self):
        skill = self.build({})
        skill.register_regex(r"(?P<testName>\w+)", "en-US")
        prefix = skill.alphanumeric_skill_id
        regexes = [m["data"]["regex"] for m in self.msgs
                   if m["type"] == "register_vocab" and "regex" in m["data"]]
        self.assertEqual(regexes, [f"(?P<{prefix}testName>\\w+)"])


class TestLegacyShims(StableShapeCase):
    def test_dialog_renderer_reads_subfolders(self):
        skill = self.build({"en-us/dialog/quote.dialog": "quote one\n"})
        self.assertEqual(skill.dialog_renderer.render("quote"), "quote one")

class TestMissingDialogRaises(StableShapeCase):
    def test_missing_dialog_raises_the_subclass(self):
        skill = self.build({"en-us/hello.dialog": "hello\n"})
        with self.assertRaises(DialogNotFound) as ctx:
            skill.render_dialog("no.such.key")
        self.assertIsInstance(ctx.exception, FileNotFoundError)
        message = str(ctx.exception)
        self.assertIn("'no.such.key'", message)
        self.assertIn("'en-US'", message)
        self.assertIn(join(skill.res_dir, "locale"), message)
        self.assertEqual(ctx.exception.name, "no.such.key")
        self.assertEqual(ctx.exception.lang, "en-US")

    def test_speak_dialog_raises_and_speaks_nothing(self):
        skill = self.build({"en-us/hello.dialog": "hello\n"})
        with self.assertRaises(FileNotFoundError):
            skill.speak_dialog("no.such.key")
        self.assertEqual(self.spoken(), [])

    def test_empty_and_duplicate_dialogs_raise(self):
        skill = self.build({
            "en-us/empty.dialog": "",
            "en-us/answer.dialog": "forty two\n",
            "en-us/sub/answer.dialog": "forty two\n"})
        for name in ("empty", "answer"):
            with self.assertRaises(DialogNotFound) as ctx:
                skill.render_dialog(name)
            self.assertIn(f"{name}.dialog", str(ctx.exception))

    def test_legacy_shims_raise_too(self):
        skill = self.build({"en-us/hello.dialog": "hello\n"})
        calls = (
            lambda: skill.resources.render_dialog("no.such.key"),
            lambda: skill.dialog_renderer.render("no.such.key"),
            lambda: skill.load_lang(lang="en-US").dialog_renderer.render(
                "no.such.key"))
        for call in calls:
            with self.assertRaises(DialogNotFound) as ctx:
                call()
            self.assertEqual(ctx.exception.name, "no.such.key")
            self.assertEqual(ctx.exception.lang, "en-US")
            self.assertEqual(ctx.exception.reason, "")
            self.assertEqual(self.spoken(), [])

    def test_the_handler_error_takes_the_normal_error_path(self):
        class Speaker(OVOSSkill):
            def initialize(self):
                self.add_event("test.speak.missing", self.handler,
                               "mycroft.skill.handler")

            def handler(self, message):
                self.speak_dialog("no.such.key")

        skill = self.build({"en-us/hello.dialog": "hello\n"}, Speaker)
        self.bus.emit(Message("test.speak.missing"))
        errors = [m for m in self.msgs
                  if m["type"] == "mycroft.skill.handler.error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("no dialog 'no.such.key'",
                      errors[0]["data"]["exception"])
        core = open(join(os.path.dirname(__import__("ovos_workshop").__file__),
                         "locale", "en-US", "skill_error.dialog")).read()
        self.assertEqual(len(self.spoken()), 1)
        self.assertIn(self.spoken()[0].split("Speaker")[0].strip(),
                      core.replace("{skill}", "Speaker"))

    def test_prompts_may_be_literal_text(self):
        # get_response, ask_yesno and ask_selection take "a dialog resource
        # or string"
        skill = self.build({"en-us/hello.dialog": "hello\n"})
        self.assertEqual(skill._dialog_or_text("do you want tea", None),
                         "do you want tea")
        self.assertEqual(skill._dialog_or_text("hello", None), "hello")

    def test_a_dialog_of_another_language_is_not_a_literal_prompt(self):
        skill = self.build({"en-us/ask_name.dialog": "what is your name\n"})
        with mock.patch.object(OVOSSkill, "lang", "de-DE"):
            with self.assertRaises(DialogNotFound) as ctx:
                skill._dialog_or_text("ask_name", None)
            self.assertEqual(ctx.exception.name, "ask_name")
            self.assertEqual(ctx.exception.lang, "de-DE")
            self.assertEqual(
                skill._dialog_or_text("what is your name", None),
                "what is your name")
        self.assertEqual(skill._dialog_or_text("ask_name", None),
                         "what is your name")

    def test_an_unrenderable_dialog_is_not_a_literal_prompt(self):
        skill = self.build({"en-us/bad.dialog": "speed {DOWN}\n"})
        with self.assertRaises(DialogNotFound) as ctx:
            skill._dialog_or_text("bad", {"DOWN": "5"})
        self.assertEqual(ctx.exception.name, "bad")
        self.assertIn("invalid slot name", ctx.exception.reason)

    def test_get_response_raises_for_an_unrenderable_prompt(self):
        skill = self.build({"en-us/bad.dialog": "speed {DOWN}\n"})
        with self.assertRaises(DialogNotFound):
            skill.get_response("bad")
        self.assertEqual(self.spoken(), [])


class TestSkillErrorDialog(StableShapeCase):
    def test_no_error_dialog_in_the_language_speaks_nothing(self):
        skill = self.build({"en-us/hello.dialog": "hello\n"})
        # the workshop ships no zu-ZA locale
        with mock.patch.object(OVOSSkill, "lang", "zu-ZA"):
            skill._on_event_error("boom", Message("x"), "mycroft.skill.handler",
                                  {}, True)
        self.assertEqual(self.spoken(), [])
        errors = [m for m in self.msgs
                  if m["type"] == "mycroft.skill.handler.error"]
        self.assertEqual(len(errors), 1)

    def test_error_dialog_in_the_language_is_spoken(self):
        skill = self.build({"en-us/hello.dialog": "hello\n"})
        skill._on_event_error("boom", Message("x"), "mycroft.skill.handler",
                              {}, True)
        core = open(join(os.path.dirname(__import__("ovos_workshop").__file__),
                         "locale", "en-US", "skill_error.dialog"),
                    encoding="utf-8").read()
        name = camel_case_split(skill.name)
        self.assertIn(self.spoken(), [[line.replace("{skill}", name)]
                                      for line in core.splitlines() if line])


class TestFirstRunIntro(StableShapeCase):
    def intro_skill(self, intro, files):
        class Intro(OVOSSkill):
            def get_intro_message(self):
                return intro
        return self.build(files, Intro)

    def test_intro_text_without_a_dialog_is_spoken(self):
        skill = self.intro_skill("welcome stranger",
                                 {"en-us/hello.dialog": "hello\n"})
        skill._handle_first_run()
        self.assertEqual(self.spoken(), ["welcome stranger"])

    def test_intro_dialog_is_spoken_as_its_phrase(self):
        skill = self.intro_skill("intro", {"en-us/intro.dialog": "welcome\n"})
        skill._handle_first_run()
        self.assertEqual(self.spoken(), ["welcome"])

    def test_unrenderable_intro_dialog_raises_and_speaks_nothing(self):
        skill = self.intro_skill("intro_bad",
                                 {"en-us/intro_bad.dialog": "speed {DOWN}\n"})
        with self.assertRaises(DialogNotFound) as ctx:
            skill._handle_first_run()
        self.assertEqual(ctx.exception.name, "intro_bad")
        self.assertEqual(self.spoken(), [])


class TestSpecRejectedDialogs(StableShapeCase):
    SPEEDTEST = ("Your download speed is {DOWN} Megabit per second and "
                 "your upload speed is {UP} Megabit per second.")
    DICE = ("You have a limit of {number} dice set in your settings. "
            "I will roll {number} of dice instead.")

    def test_upper_case_slots_raise_naming_the_file(self):
        # ovos-skill-speedtest 'result'; INTENT-1 §3.4 names are lowercase
        skill = self.build({"en-us/result.dialog": self.SPEEDTEST})
        with self.assertRaises(DialogNotFound) as ctx:
            skill.render_dialog("result", {"DOWN": "50", "UP": "10"})
        self.assertIn("result.dialog", str(ctx.exception))
        self.assertIn("invalid slot name", str(ctx.exception))

    def test_repeated_slot_raises_naming_the_file(self):
        # ovos-skill-randomness 'over-dice-limit'; INTENT-1 §3.6
        skill = self.build({"en-us/dialog/over-dice-limit.dialog": self.DICE})
        with self.assertRaises(DialogNotFound) as ctx:
            skill.render_dialog("over-dice-limit", {"number": 6})
        self.assertIn("over-dice-limit.dialog", str(ctx.exception))
        self.assertIn("repeated slot name", str(ctx.exception))

    def test_slot_with_spaces_raises(self):
        # ovos-skill-ip 'last digits'
        skill = self.build({
            "en-us/last digits.dialog": "My I.P. address ends with { digits }\n"
                                        "it ends with { digits }"})
        with self.assertRaises(DialogNotFound) as ctx:
            skill.render_dialog("last digits", {"digits": "4 2"})
        self.assertEqual(ctx.exception.name, "last digits")
        self.assertIn("last digits.dialog", ctx.exception.reason)
        self.assertIn("invalid slot name { digits }", ctx.exception.reason)

    def test_mixed_slots_render_the_valid_phrases_and_warn_once(self):
        skill = self.build({
            "en-us/time.current.dialog": "Uhrzeit\nes ist {time}\n"})
        reports = []
        skill.log = type("L", (), {
            "warning": lambda self, m: reports.append(m),
            "debug": lambda *a: None, "info": lambda *a: None,
            "error": lambda *a: None, "exception": lambda *a: None})()
        seen = {skill.render_dialog("time.current", {"time": "5"})
                for _ in range(60)}
        self.assertEqual(seen, {"Uhrzeit", "es ist 5"})
        self.assertEqual(len(reports), 1)
        self.assertIn("time.current.dialog", reports[0])

    def test_a_phrase_that_needs_a_missing_slot_is_not_spoken(self):
        skill = self.build({
            "en-us/time.current.dialog": "Uhrzeit\nes ist {time}\n"})
        seen = {skill.render_dialog("time.current", {}) for _ in range(40)}
        self.assertEqual(seen, {"Uhrzeit"})


class TestNoInternalLegacyUse(unittest.TestCase):
    LEGACY = {"SkillResources", "ResourceFile", "DialogFile",
              "MustacheDialogRenderer", "_legacy_skill_resources",
              "dialog_renderer", "_dialog_renderer", "_load_dialog_renderer"}
    SHIMS = {"resource_files.py", join("skills", "_legacy_resources.py")}

    def test_only_the_shims_use_the_legacy_path(self):
        import ast
        import ovos_workshop
        root = os.path.dirname(ovos_workshop.__file__)
        offenders = []
        for folder, _, names in os.walk(root):
            for name in names:
                path = join(folder, name)
                rel = os.path.relpath(path, root)
                if not name.endswith(".py") or rel in self.SHIMS:
                    continue
                with open(path, encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module and \
                            node.module.endswith("resource_files"):
                        offenders.append((rel, node.module))
                    elif isinstance(node, ast.Name) and node.id in self.LEGACY:
                        offenders.append((rel, node.id))
                    elif isinstance(node, ast.Attribute) and \
                            node.attr in self.LEGACY | {"resources"}:
                        offenders.append((rel, node.attr))
        self.assertEqual(offenders, [])

    def test_old_names_still_import_and_warn_once(self):
        import warnings
        from ovos_workshop.resource_files import SkillResources
        root = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, root, True)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            SkillResources(root, "en-US")
        deprecations = [w for w in caught
                        if issubclass(w.category, DeprecationWarning)
                        and "SkillResources is deprecated" in str(w.message)]
        self.assertEqual(len(deprecations), 1)


class TestVocListCase(StableShapeCase):
    def test_voc_list_is_lowercase(self):
        skill = self.build({"en-us/country.voc": "UK\nFrance\n"})
        self.assertEqual(sorted(skill.voc_list("country")),
                         ["france", "uk"])
        self.assertTrue(skill.voc_match("I live in the uk", "country"))


if __name__ == "__main__":
    unittest.main()
