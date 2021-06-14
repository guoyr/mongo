"""Task generation for split resmoke tasks."""
import os
from typing import Set, Any, Dict, Optional, List

import inject
import structlog
from pydantic import BaseModel
from shrub.v2 import Task, TaskDependency

from buildscripts.patch_builds.task_generation import resmoke_commands
from buildscripts.task_generation.suite_split import GeneratedSuite, SubSuite
from buildscripts.task_generation.task_types.gentask_options import GenTaskOptions
from buildscripts.task_generation.timeout import TimeoutEstimate
from buildscripts.util import taskname

LOGGER = structlog.getLogger(__name__)


def string_contains_any_of_args(string: str, args: List[str]) -> bool:
    """
    Return whether array contains any of a group of args.

    :param string: String being checked.
    :param args: Args being analyzed.
    :return: True if any args are found in the string.
    """
    return any(arg in string for arg in args)


class ResmokeGenTaskParams(BaseModel):
    """
    Parameters describing how a specific resmoke suite should be generated.

    use_large_distro: Whether generated tasks should be run on a "large" distro.
    named_prefix: burn_in_* can add its own prefix to generated tasks.
    require_multiversion: Requires downloading Multiversion binaries.
    repeat_suites: How many times generated suites should be repeated.
    resmoke_args: Arguments to pass to resmoke in generated tasks.
    resmoke_jobs_max: Max number of jobs that resmoke should execute in parallel.
    gen_task_config_remote_path: Remote path of generated config.
    add_to_display_task: Should generated tasks be grouped in a display task.
    """

    use_large_distro: Optional[bool]
    large_distro_name: Optional[str]
    name_prefix: Optional[str] = None
    require_multiversion: Optional[bool]
    repeat_suites: Optional[int]
    resmoke_args: str
    resmoke_jobs_max: Optional[int]
    gen_task_config_remote_path: str
    add_to_display_task: bool = True


class ResmokeGenTaskService:
    """A service to generated split resmoke suites."""

    @inject.autoparams()
    def __init__(self, gen_task_options: GenTaskOptions) -> None:
        """
        Initialize the service.

        :param gen_task_options: Global options for how tasks should be generated.
        """
        self.gen_task_options = gen_task_options

    def generate_tasks(self, generated_suite: GeneratedSuite,
                       params: ResmokeGenTaskParams) -> Set[Task]:
        """
        Build a set of shrub task for all the sub tasks.

        :param generated_suite: Suite to generate tasks for.
        :param params: Parameters describing how tasks should be generated.
        :return: Set of shrub tasks to generate the given suite.
        """
        sub_tasks = {
            self._create_sub_task(generated_suite.task_name, generated_suite, params, sub_suite)
            for sub_suite in generated_suite.sub_suites
        }

        if self.gen_task_options.create_misc_suite:
            # Add the misc suite, which does not have an existing SubSuite.
            sub_tasks.add(
                self._create_sub_task(generated_suite.task_name, generated_suite, params, None))

        return sub_tasks

    def _create_sub_task(self, sub_task_base_name: str, suite: GeneratedSuite,
                         params: ResmokeGenTaskParams, sub_suite: SubSuite = None) -> Task:
        """
        Create the sub task for the given suite.

        :param sub_task_base_name: Base name of the generated task, before indexes etc.
        :param suite: Parent suite being created.
        :param params: Parameters describing how tasks should be generated.
        :param sub_suite: Sub-Suite to generate. None if generating the "_misc" suite.
        :return: Shrub configuration for the sub-suite.
        """
        if not sub_suite:
            # We are generating the _misc suite.
            sub_suite_name = f"{os.path.basename(suite.suite_name)}_misc"
            sub_task_name = f"{sub_task_base_name}_misc_{suite.build_variant}"
            timeout_est = TimeoutEstimate.no_timeouts()
        else:
            sub_suite_name = sub_suite.name(len(suite))
            sub_task_name = taskname.name_generated_task(sub_task_base_name, sub_suite.index,
                                                         len(suite), suite.build_variant)
            timeout_est = sub_suite.get_timeout_estimate()

        return self._generate_task(sub_suite_name, sub_task_name, params, suite, timeout_est)

    def _generate_task(self, sub_suite_name: str, sub_task_name: str, params: ResmokeGenTaskParams,
                       suite: GeneratedSuite, timeout_est: TimeoutEstimate) -> Task:
        """
        Generate a shrub evergreen config for a resmoke task.

        :param sub_suite_name: Name of suite being generated.
        :param sub_task_name: Name of task to generate.
        :param params: Parameters describing how tasks should be generated.
        :param suite: Parent suite being created.
        :param timeout_est: Estimated runtime to use for calculating timeouts.
        :return: Shrub configuration for the described task.
        """
        # pylint: disable=too-many-arguments
        LOGGER.debug("generating task", sub_task_name=sub_task_name, sub_suite=sub_suite_name)

        target_suite_file = self.gen_task_options.suite_location(
            f"{sub_suite_name}_{suite.build_variant}.yml")
        run_tests_vars = self._get_run_tests_vars(target_suite_file, suite.suite_name, params)

        require_multiversion = params.require_multiversion

        timeout_cmd = timeout_est.generate_timeout_cmd(self.gen_task_options.is_patch,
                                                       params.repeat_suites,
                                                       self.gen_task_options.use_default_timeouts)
        commands = resmoke_commands("run generated tests", run_tests_vars, timeout_cmd,
                                    require_multiversion)

        return Task(sub_task_name, commands, self._get_dependencies())

    def _get_run_tests_vars(self, suite_file: str, suite_name: str,
                            params: ResmokeGenTaskParams) -> Dict[str, Any]:
        """
        Generate a dictionary of the variables to pass to the task.

        :param suite_file: Suite being generated.
        :param suite_name: Name of suite being generated
        :param params: Parameters describing how tasks should be generated.
        :return: Dictionary containing variables and value to pass to generated task.
        """
        variables = {
            "resmoke_args": self._generate_resmoke_args(params, suite_file, suite_name),
            "gen_task_config_location": params.gen_task_config_remote_path,
        }

        if params.resmoke_jobs_max:
            variables["resmoke_jobs_max"] = params.resmoke_jobs_max

        return variables

    @staticmethod
    def _get_dependencies() -> Set[TaskDependency]:
        """Get the set of dependency tasks for these suites."""
        dependencies = {TaskDependency("archive_dist_test_debug")}
        return dependencies

    def _generate_resmoke_args(self, params: ResmokeGenTaskParams, suite_file: str,
                              suite_name: str) -> str:
        """
        Generate the resmoke args for the given suite.

        :param params: Parameters describing how tasks should be generated.
        :param suite_file: File containing configuration for test suite.
        :param suite_name: Name of suite being generated.
        :return: arguments to pass to resmoke.
        """
        resmoke_args = f"--suite={suite_file} --originSuite={suite_name} {params.resmoke_args}"
        if params.repeat_suites and not string_contains_any_of_args(resmoke_args,
                                                                    ["repeatSuites", "repeat"]):
            resmoke_args += f" --repeatSuites={params.repeat_suites} "
        return resmoke_args
