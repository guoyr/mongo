"""Setup multiversion config."""
from typing import List

SETUP_MULTIVERSION_CONFIG = "buildscripts/resmokeconfig/setup_multiversion/setup_multiversion_config.yml"

REPL_MIXED_VERSION_CONFIGS = ["new-old-new", "new-new-old", "old-new-new"]
SHARDED_MIXED_VERSION_CONFIGS = ["new-old-old-new"]


def get_version_configs(is_sharded: bool) -> List[str]:
    """Get the version configurations to use."""
    if is_sharded:
        return SHARDED_MIXED_VERSION_CONFIGS
    return REPL_MIXED_VERSION_CONFIGS


def get_multiversion_resmoke_args(is_sharded: bool) -> str:
    """Return resmoke args used to configure a cluster for multiversion testing."""
    if is_sharded:
        return "--numShards=2 --numReplSetNodes=2 "
    return "--numReplSetNodes=3 --linearChain=on "


class Buildvariant:
    """Class represents buildvariant in setup multiversion config."""

    name: str
    edition: str
    platform: str
    architecture: str
    versions: List[str]

    def __init__(self, buildvariant_yaml: dict):
        """Initialize."""
        self.name = buildvariant_yaml.get("name", "")
        self.edition = buildvariant_yaml.get("edition", "")
        self.platform = buildvariant_yaml.get("platform", "")
        self.architecture = buildvariant_yaml.get("architecture", "")
        self.versions = buildvariant_yaml.get("versions", [])


class SetupMultiversionConfig:
    """Class represents setup multiversion config."""

    evergreen_projects: List[str]
    evergreen_buildvariants: List[Buildvariant]

    def __init__(self, raw_yaml: dict):
        """Initialize."""
        self.evergreen_projects = raw_yaml.get("evergreen_projects", [])
        self.evergreen_buildvariants = []
        buildvariants_raw_yaml = raw_yaml.get("evergreen_buildvariants", "")
        for buildvariant_yaml in buildvariants_raw_yaml:
            self.evergreen_buildvariants.append(Buildvariant(buildvariant_yaml))
