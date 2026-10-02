import enum

from ovos_config.config import read_mycroft_config, update_mycroft_config


def blacklist_skill(skill, config=None):
    config = config or read_mycroft_config()
    skills_config = config.get("skills", {})
    blacklisted_skills = skills_config.get("blacklisted_skills", [])
    if skill not in blacklisted_skills:
        blacklisted_skills.append(skill)
        conf = {
            "skills": {
                "blacklisted_skills": blacklisted_skills
            }
        }
        update_mycroft_config(conf)
        return True
    return False


def whitelist_skill(skill, config=None):
    config = config or read_mycroft_config()
    skills_config = config.get("skills", {})
    blacklisted_skills = skills_config.get("blacklisted_skills", [])
    if skill in blacklisted_skills:
        blacklisted_skills.remove(skill)
        conf = {
            "skills": {
                "blacklisted_skills": blacklisted_skills
            }
        }
        update_mycroft_config(conf)
        return True
    return False


class ConverseMode(str, enum.Enum):
    """
    Defines a mode for handling `converse` requests.
    ACCEPT ALL - default behavior where all skills may implement `converse`
    WHITELIST - only skills explicitly allowed may implement `converse`
    BLACKLIST - all skills except those disallowed may implement `converse`
    """
    ACCEPT_ALL = "accept_all"  # Default
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"


class FallbackMode(str, enum.Enum):
    """
    Defines a mode for handling fallbacks (utterances without a matched intent)
    ACCEPT ALL - default behavior where all installed FallbackSkills are used
    WHITELIST - only explicitly allowed FallbackSkills may respond
    BLACKLIST - all FallbackSkills except those disallowed may respond
    """
    ACCEPT_ALL = "accept_all"  # Default
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"


class ConverseActivationMode(str, enum.Enum):
    """
    Defines a mode for manually activating `converse` handling
    ACCEPT ALL - default behavior where any skill may activate itself
    PRIORITY - a skill may only activate itself if no higher-priority skill is
        currently active
    WHITELIST - only explicitly allowed skills may activate themselves
    BLACKLIST - all skills except those disallowed may activate themselves
    """
    ACCEPT_ALL = "accept_all"  # Default
    PRIORITY = "priority"
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"
