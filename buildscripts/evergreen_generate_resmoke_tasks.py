#!/usr/bin/env python3
"""
Resmoke Test Suite Generator.

Analyze the evergreen history for tests run under the given task and create new evergreen tasks
to attempt to keep the task runtime under a specified amount.
"""
import os
from datetime import datetime, timedelta

import sys

import click
import inject
import structlog

from evergreen.api import EvergreenApi, RetryingEvergreenApi

# Get relative imports to work when the package is not installed on the PYTHONPATH.
from buildscripts.task_generation.evg_expansions import EvgExpansions
from buildscripts.task_generation.gen_task_validation import GenTaskValidationService

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from buildscripts.task_generation.evg_config_builder import EvgConfigBuilder
from buildscripts.task_generation.gen_config import GenerationConfiguration
from buildscripts.task_generation.gen_task_service import GenTaskOptions, ResmokeGenTaskParams
from buildscripts.task_generation.suite_split_strategies import SplitStrategy, FallbackStrategy, \
    greedy_division, round_robin_fallback
from buildscripts.task_generation.resmoke_proxy import ResmokeProxyConfig
from buildscripts.task_generation.suite_split import SuiteSplitConfig, SuiteSplitParameters
from buildscripts.util.cmdutils import enable_logging
# pylint: enable=wrong-import-position

LOGGER = structlog.getLogger(__name__)

DEFAULT_TEST_SUITE_DIR = os.path.join("buildscripts", "resmokeconfig", "suites")
EVG_CONFIG_FILE = "./.evergreen.yml"
GENERATE_CONFIG_FILE = "etc/generate_subtasks_config.yml"
LOOKBACK_DURATION_DAYS = 14
GEN_SUFFIX = "_gen"
GEN_PARENT_TASK = "generator_tasks"
GENERATED_CONFIG_DIR = "generated_resmoke_config"


class EvgGenResmokeTaskOrchestrator:
    """Orchestrator for generating an resmoke tasks."""

    @inject.autoparams()
    def __init__(self, gen_task_validation: GenTaskValidationService,
                 gen_task_options: GenTaskOptions) -> None:
        """
        Initialize the orchestrator.

        :param gen_task_validation: Generate tasks validation service.
        :param gen_task_options: Options for how tasks are generated.
        """
        self.gen_task_validation = gen_task_validation
        self.gen_task_options = gen_task_options

    def generate_task(self, task_id: str, split_params: SuiteSplitParameters,
                      gen_params: ResmokeGenTaskParams) -> None:
        """
        Generate the specified resmoke task.

        :param task_id: Task ID of generating task.
        :param split_params: Parameters describing how the task should be split.
        :param gen_params: Parameters describing how the task should be generated.
        """
        LOGGER.debug("config options", split_params=split_params, gen_params=gen_params)
        if not self.gen_task_validation.should_task_be_generated(task_id):
            LOGGER.info("Not generating configuration due to previous successful generation.")
            return

        builder = EvgConfigBuilder()  # pylint: disable=no-value-for-parameter

        builder.generate_suite(split_params, gen_params)
        builder.add_display_task(GEN_PARENT_TASK, {f"{split_params.task_name}{GEN_SUFFIX}"},
                                 split_params.build_variant)
        generated_config = builder.build(split_params.task_name + ".json")
        generated_config.write_all_to_dir(self.gen_task_options.generated_config_dir)


@click.command()
@click.option("--expansion-file", type=str, required=True,
              help="Location of expansions file generated by evergreen.")
@click.option("--evergreen-config", type=str, default=EVG_CONFIG_FILE,
              help="Location of evergreen configuration file.")
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose logging.")
def main(expansion_file: str, evergreen_config: str, verbose: bool) -> None:
    """
    Create a configuration for generate tasks to create sub suites for the specified resmoke suite.

    The `--expansion-file` should contain all the configuration needed to generate the tasks.
    \f
    :param expansion_file: Configuration file.
    :param evergreen_config: Evergreen configuration file.
    :param verbose: Use verbose logging.
    """
    enable_logging(verbose)

    end_date = datetime.utcnow().replace(microsecond=0)
    start_date = end_date - timedelta(days=LOOKBACK_DURATION_DAYS)

    evg_expansions = EvgExpansions.from_yaml_file(expansion_file)

    def dependencies(binder: inject.Binder) -> None:
        binder.bind(SuiteSplitConfig, evg_expansions.get_suite_split_config(start_date, end_date))
        binder.bind(SplitStrategy, greedy_division)
        binder.bind(FallbackStrategy, round_robin_fallback)
        binder.bind(GenTaskOptions, evg_expansions.get_evg_config_gen_options(GENERATED_CONFIG_DIR))
        binder.bind(EvergreenApi, RetryingEvergreenApi.get_api(config_file=evergreen_config))
        binder.bind(GenerationConfiguration,
                    GenerationConfiguration.from_yaml_file(GENERATE_CONFIG_FILE))
        binder.bind(ResmokeProxyConfig,
                    ResmokeProxyConfig(resmoke_suite_dir=DEFAULT_TEST_SUITE_DIR))

    inject.configure(dependencies)

    gen_task_orchestrator = EvgGenResmokeTaskOrchestrator()  # pylint: disable=no-value-for-parameter
    gen_task_orchestrator.generate_task(evg_expansions.task_id,
                                        evg_expansions.get_suite_split_params(),
                                        evg_expansions.get_gen_params())


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
