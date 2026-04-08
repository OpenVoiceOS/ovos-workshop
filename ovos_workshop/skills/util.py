# Copyright 2026 OpenVoiceOS
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
"""
Utility functions for skills, including word list joining with language-specific euphony
and error traceback formatting.
"""

from typing import Dict, List, Optional

from ovos_utils.log import LOG
from ovos_workshop.resource_files import CoreResources


def simple_trace(stack_trace: List[str]) -> str:
    """Generate a simplified traceback.

    Args:
        stack_trace: Formatted stack trace (each string ends with \\n)

    Returns:
        Stack trace with any empty lines removed and last line removed
    """
    stack_trace = stack_trace[:-1]
    tb = 'Traceback:\n'
    for line in stack_trace:
        if line.strip():
            tb += line
    return tb


def _get_word(lang: str, connector: str) -> str:
    """Get connector word translation for a language.

    Args:
        lang: BCP-47 language code
        connector: Connector key ("and" or "or")

    Returns:
        Translated connector word, or ", " as fallback
    """
    data = CoreResources(lang).load_json_file("word_connectors")
    if connector in data:
        return data[connector]
    LOG.warning(f"untranslated word connector '{connector}' for lang: {lang}")
    return ", "


def _load_euphony_rules(lang: str) -> Optional[Dict]:
    """Load euphony.json for a language if it exists.

    Args:
        lang: BCP-47 language tag

    Returns:
        Dict with euphony rules or None if not found
    """
    try:
        return CoreResources(lang).load_json_file("euphony")
    except Exception:
        return None


def _normalize_word(word: str, rules: dict) -> str:
    """Normalize a word for euphony comparison per language rules.

    Args:
        word: The word to normalize
        rules: The euphony rules dict (may contain normalize section)

    Returns:
        Normalized word string
    """
    if not word:
        return word

    normalize = rules.get("normalize", {})

    # Strip leading h if language specifies it
    if normalize.get("strip_leading_h"):
        word = word.lstrip("h")

    # Apply character replacements if language specifies them
    replacements = normalize.get("replace_accents", {})
    for old, new in replacements.items():
        word = word.replace(old, new)

    return word


def _apply_euphony(connector: str, next_word: str, rules: dict) -> str:
    """Apply euphony transformation to connector based on rules.

    Args:
        connector: The connector word (e.g., "e", "y", "o")
        next_word: The word following the connector
        rules: The euphony rules dict

    Returns:
        Potentially transformed connector word
    """
    if not next_word or not rules:
        return connector

    # Check each rule to see if it applies
    for rule in rules.get("rules", []):
        rule_connector = rule.get("connector")
        if rule_connector != connector:
            continue

        # Check the condition type
        condition = rule.get("condition")
        normalized_next = _normalize_word(next_word.lower(), rules)
        first_char = normalized_next[0] if normalized_next else ""

        if condition == "starts_with_vowel":
            vowels = rule.get("vowels", [])
            if first_char in vowels:
                return rule.get("replace_with", connector)

        elif condition == "starts_with_letter":
            letters = rule.get("letters", [])
            if first_char in letters:
                return rule.get("replace_with", connector)

        elif condition == "starts_with_any_except":
            # Apply transformation if word does NOT start with any of the excluded patterns
            excluded = rule.get("excluded_patterns", [])
            excluded_match = any(normalized_next.startswith(p) for p in excluded)
            if not excluded_match:
                letters = rule.get("letters", [])
                if first_char in letters:
                    return rule.get("replace_with", connector)

    return connector


def join_word_list(items: List[str], connector: str, sep: str, lang: str) -> str:
    """Join a list into a phrase using language-specific connector and euphony rules.

    Supports language-specific euphony transformations via euphony.json config files.

    Examples:
        join_word_list(["a", "b", "c"], "and", ",", "en-US")
        -> "a, b and c"

        join_word_list(["inverno", "estate"], "and", ",", "it-IT")
        -> "inverno ed estate"  (euphony: e + vowel e -> ed)

        join_word_list(["Juan", "Irene"], "and", ",", "es-ES")
        -> "Juan e Irene"  (euphony: y + i -> e)

    Args:
        items: List of items to join (converted to strings)
        connector: Connector word key ("and" or "or")
        sep: Separator character between items (default ",")
        lang: BCP-47 language tag (default "en-US")

    Returns:
        Joined phrase with language-appropriate formatting
    """
    if not items:
        return ""
    if len(items) == 1:
        return str(items[0])

    # Load connector word
    connector_word = _get_word(lang, connector)

    # Load and apply euphony rules if available
    euphony_rules = _load_euphony_rules(lang)
    if euphony_rules:
        connector_word = _apply_euphony(connector_word, str(items[-1]), euphony_rules)

    # Format separator
    if not sep:
        sep = ", "
    else:
        sep += " "

    # Join: items[:-1] with sep, then connector, then final item
    if len(items) == 2:
        # Two items: no separator before connector
        return f"{items[0]} {connector_word} {items[1]}"
    else:
        # Three or more items: use separator
        return (sep.join(str(item) for item in items[:-1]) +
                " " + connector_word +
                " " + items[-1])
