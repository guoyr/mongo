#!/usr/bin/env python3
"""Generate multiversion tests to run in evergreen in parallel."""

from datetime import datetime, timedelta
import os
import re
import tempfile
from typing import Optional, List
from collections import defaultdict
from sys import platform

from subprocess import check_output

import inject
import requests
import click
import structlog

from shrub.v2 import ExistingTask
from evergreen.api import RetryingEvergreenApi, EvergreenApi

from buildscripts.resmokelib.multiversionconstants import (LAST_LTS_MONGO_BINARY, REQUIRES_FCV_TAG)
from buildscripts.task_generation.evg_config_builder import EvgConfigBuilder
from buildscripts.task_generation.evg_expansions import EvgExpansions, DEFAULT_CONFIG_DIRECTORY
from buildscripts.task_generation.gen_config import GenerationConfiguration
from buildscripts.task_generation.generated_config import GeneratedConfiguration
from buildscripts.task_generation.multiversion_util import MultiversionUtilService
from buildscripts.task_generation.resmoke_proxy import ResmokeProxyConfig
from buildscripts.task_generation.suite_split import SuiteSplitConfig
from buildscripts.task_generation.suite_split_strategies import SplitStrategy, FallbackStrategy, \
    greedy_division, round_robin_fallback
from buildscripts.task_generation.task_types.gentask_options import GenTaskOptions
from buildscripts.util.cmdutils import enable_logging
from buildscripts.util.fileops import read_yaml_file
import buildscripts.evergreen_generate_resmoke_tasks as generate_resmoke
import buildscripts.evergreen_gen_fuzzer_tests as gen_fuzzer
import buildscripts.ciconfig.tags as _tags

# pylint: disable=len-as-condition
from buildscripts.util.taskname import remove_gen_suffix

LOGGER = structlog.getLogger(__name__)

DEFAULT_TEST_SUITE_DIR = os.path.join("buildscripts", "resmokeconfig", "suites")
LOOKBACK_DURATION_DAYS = 14
CONFIG_FILE = generate_resmoke.EVG_CONFIG_FILE

BURN_IN_TASK = "burn_in_tests_multiversion"
MULTIVERSION_CONFIG_KEY = "use_in_multiversion"
PASSTHROUGH_TAG = "multiversion_passthrough"
RANDOM_REPLSETS_TAG = "random_multiversion_ds"
BACKPORT_REQUIRED_TAG = "backport_required_multiversion"
EXCLUDE_TAGS = f"{REQUIRES_FCV_TAG},multiversion_incompatible,{BACKPORT_REQUIRED_TAG}"
EXCLUDE_TAGS_FILE = "multiversion_exclude_tags.yml"
GEN_PARENT_TASK = "generator_tasks"
ASAN_SIGNATURE = "detect_leaks=1"

# The directory in which BACKPORTS_REQUIRED_FILE resides.
ETC_DIR = "etc"
BACKPORTS_REQUIRED_FILE = "backports_required_for_multiversion_tests.yml"
BACKPORTS_REQUIRED_BASE_URL = "https://raw.githubusercontent.com/mongodb/mongo"


def get_backports_required_hash_for_shell_version(mongo_shell_path=None):
    """Parse the last-lts shell binary to get the commit hash."""
    if platform.startswith("win"):
        shell_version = check_output([mongo_shell_path + ".exe", "--version"]).decode('utf-8')
    else:
        shell_version = check_output([mongo_shell_path, "--version"]).decode('utf-8')
    for line in shell_version.splitlines():
        if "gitVersion" in line:
            version_line = line.split(':')[1]
            # We identify the commit hash as the string enclosed by double quotation marks.
            result = re.search(r'"(.*?)"', version_line)
            if result:
                commit_hash = result.group().strip('"')
                if not commit_hash.isalnum():
                    raise ValueError(f"Error parsing commit hash. Expected an "
                                     f"alpha-numeric string but got: {commit_hash}")
                return commit_hash
            else:
                break
    raise ValueError("Could not find a valid commit hash from the last-lts mongo binary.")


def get_last_lts_yaml(commit_hash):
    """Download BACKPORTS_REQUIRED_FILE from the last LTS commit and return the yaml."""
    LOGGER.info(f"Downloading file from commit hash of last-lts branch {commit_hash}")
    response = requests.get(
        f'{BACKPORTS_REQUIRED_BASE_URL}/{commit_hash}/{ETC_DIR}/{BACKPORTS_REQUIRED_FILE}')
    # If the response was successful, no exception will be raised.
    response.raise_for_status()

    last_lts_file = f"{commit_hash}_{BACKPORTS_REQUIRED_FILE}"
    temp_dir = tempfile.mkdtemp()
    with open(os.path.join(temp_dir, last_lts_file), "w") as fileh:
        fileh.write(response.text)

    backports_required_last_lts = read_yaml_file(os.path.join(temp_dir, last_lts_file))
    return backports_required_last_lts


class MultiVersionGenerateOrchestrator:
    """An orchestrator for generating multiversion tasks."""

    @inject.autoparams()
    def __init__(self, evg_api: EvergreenApi, multiversion_util: MultiversionUtilService,
                 gen_task_options: GenTaskOptions) -> None:
        """
        Initialize the orchestrator.

        :param evg_api: Evergreen API client.
        :param multiversion_util: Multiverison utilities service.
        :param gen_task_options: Options to use for generating tasks.
        """
        self.evg_api = evg_api
        self.multiversion_util = multiversion_util
        self.gen_task_options = gen_task_options

    def generate_fuzzer(self, evg_expansions: EvgExpansions) -> GeneratedConfiguration:
        """
        Generate configuration for the fuzzer task specified by the expansions.

        :param evg_expansions: Evergreen expansions describing what to generate.
        :return: Configuration to generate the specified task.
        """
        suite = evg_expansions.suite
        is_sharded = self.multiversion_util.is_suite_sharded(suite)
        gen_params = evg_expansions.get_multiversion_generation_params(is_sharded)

        builder = EvgConfigBuilder()  # pylint: disable=no-value-for-parameter

        fuzzer_task_set = set()
        for version_config in gen_params.mixed_version_configs:
            fuzzer_params = evg_expansions.fuzzer_gen_task_params(version_config, is_sharded)
            fuzzer_task = builder.generate_fuzzer(fuzzer_params)
            fuzzer_task_set = fuzzer_task_set.union(fuzzer_task.sub_tasks)

        existing_tasks = {ExistingTask(task) for task in fuzzer_task_set}
        existing_tasks.add({ExistingTask(f"{suite}_multiversion_gen")})
        builder.add_display_task(evg_expansions.task, existing_tasks, evg_expansions.build_variant)
        return builder.build(f"{evg_expansions.task}.json")

    def generate_resmoke_suite(self, evg_expansions: EvgExpansions) -> GeneratedConfiguration:
        """
        Generate configuration for the resmoke task specified by the expansions.

        :param evg_expansions: Evergreen expansions describing what to generate.
        :return: Configuration to generate the specified task.
        """
        suite = evg_expansions.suite or evg_expansions.task
        is_sharded = self.multiversion_util.is_suite_sharded(suite)

        split_params = evg_expansions.get_split_params()
        gen_params = evg_expansions.get_multiversion_generation_params(is_sharded)

        builder = EvgConfigBuilder()  # pylint: disable=no-value-for-parameter
        builder.add_multiversion_suite(split_params, gen_params)
        builder.add_display_task(GEN_PARENT_TASK, {f"{split_params.task_name}"},
                                 evg_expansions.build_variant)
        return builder.build(f"{evg_expansions.task}.json")

    def generate(self, evg_expansions: EvgExpansions) -> None:
        """
        Generate configuration for the specified task and save it to disk.

        :param evg_expansions: Evergreen expansions describing what to generate.
        """
        if evg_expansions.is_jstestfuzz:
            generated_config = self.generate_fuzzer(evg_expansions)
        else:
            generated_config = self.generate_resmoke_suite(evg_expansions)
        generated_config.write_all_to_dir(DEFAULT_CONFIG_DIRECTORY)


@click.group()
def main():
    """Serve as an entry point for the 'run' and 'generate-exclude-tags' commands."""
    pass


@main.command("run")
@click.option("--expansion-file", type=str, required=True,
              help="Location of expansions file generated by evergreen.")
@click.option("--evergreen-config", type=str, default=CONFIG_FILE,
              help="Location of evergreen configuration file.")
def run_generate_tasks(expansion_file: str, evergreen_config: Optional[str] = None):
    """
    Create a configuration for generate tasks to create sub suites for the specified resmoke suite.

    Tests using ReplicaSetFixture will be generated to use 3 nodes and linear_chain=True.
    Tests using ShardedClusterFixture will be generated to use 2 shards with 2 nodes each.
    The different binary version configurations tested are stored in REPL_MIXED_VERSION_CONFIGS
    and SHARDED_MIXED_VERSION_CONFIGS.

    The `--expansion-file` should contain all the configuration needed to generate the tasks.
    \f
    :param expansion_file: Configuration file.
    :param evergreen_config: Evergreen configuration file.
    """
    enable_logging(False)

    end_date = datetime.utcnow().replace(microsecond=0)
    start_date = end_date - timedelta(days=LOOKBACK_DURATION_DAYS)

    evg_expansions = EvgExpansions.from_yaml_file(expansion_file)

    def dependencies(binder: inject.Binder) -> None:
        binder.bind(SuiteSplitConfig, evg_expansions.get_suite_split_config(start_date, end_date))
        binder.bind(SplitStrategy, greedy_division)
        binder.bind(FallbackStrategy, round_robin_fallback)
        binder.bind(GenTaskOptions, evg_expansions.get_generation_options())
        binder.bind(EvergreenApi, RetryingEvergreenApi.get_api(config_file=evergreen_config))
        binder.bind(GenerationConfiguration,
                    GenerationConfiguration.from_yaml_file(gen_fuzzer.GENERATE_CONFIG_FILE))
        binder.bind(ResmokeProxyConfig,
                    ResmokeProxyConfig(resmoke_suite_dir=DEFAULT_TEST_SUITE_DIR))

    inject.configure(dependencies)

    generate_orchestrator = MultiVersionGenerateOrchestrator()  # pylint: disable=no-value-for-parameter
    generate_orchestrator.generate(evg_expansions)


@main.command("generate-exclude-tags")
@click.option("--output", type=str, default=os.path.join(DEFAULT_CONFIG_DIRECTORY,
                                                         EXCLUDE_TAGS_FILE), show_default=True,
              help="Where to output the generated tags.")
def generate_exclude_yaml(output: str) -> None:
    # pylint: disable=too-many-locals
    """
    Create a tag file associating multiversion tests to tags for exclusion.

    Compares the BACKPORTS_REQUIRED_FILE on the current branch with the same file on the
    last-lts branch to determine which tests should be denylisted.
    """

    enable_logging(False)

    location, _ = os.path.split(os.path.abspath(output))
    if not os.path.isdir(location):
        LOGGER.info(f"Cannot write to {output}. Not generating tag file.")
        return

    backports_required_latest = read_yaml_file(os.path.join(ETC_DIR, BACKPORTS_REQUIRED_FILE))

    # Get the state of the backports_required_for_multiversion_tests.yml file for the last-lts
    # binary we are running tests against. We do this by using the commit hash from the last-lts
    # mongo shell executable.
    last_lts_commit_hash = get_backports_required_hash_for_shell_version(
        mongo_shell_path=LAST_LTS_MONGO_BINARY)

    # Get the yaml contents from the last-lts commit.
    backports_required_last_lts = get_last_lts_yaml(last_lts_commit_hash)

    def diff(list1, list2):
        return [elem for elem in (list1 or []) if elem not in (list2 or [])]

    suites_latest = backports_required_latest["suites"] or {}
    # Check if the changed syntax for etc/backports_required_multiversion.yml has been backported.
    # This variable and all branches where it's not set can be deleted after backporting the change.
    change_backported = "all" in backports_required_last_lts.keys()
    if change_backported:
        always_exclude = diff(backports_required_latest["all"], backports_required_last_lts["all"])
        suites_last_lts: defaultdict = defaultdict(list, backports_required_last_lts["suites"])
    else:
        always_exclude = backports_required_latest["all"] or []
        suites_last_lts = defaultdict(list, backports_required_last_lts)
        for suite in suites_latest.keys():
            for elem in suites_last_lts[suite] or []:
                if elem in always_exclude:
                    always_exclude.remove(elem)

    tags = _tags.TagsConfig()

    # Tag tests that are excluded from every suite.
    for elem in always_exclude:
        tags.add_tag("js_test", elem["test_file"], BACKPORT_REQUIRED_TAG)

    # Tag tests that are excluded on a suite-by-suite basis.
    for suite in suites_latest.keys():
        test_set = set()
        for elem in diff(suites_latest[suite], suites_last_lts[suite]):
            test_set.add(elem["test_file"])
        for test in test_set:
            tags.add_tag("js_test", test, f"{suite}_{BACKPORT_REQUIRED_TAG}")

    LOGGER.info(f"Writing exclude tags to {output}.")
    tags.write_file(filename=output,
                    preamble="Tag file that specifies exclusions from multiversion suites.")


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
