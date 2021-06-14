"""Task generation for multiversion resmoke tasks."""
from typing import Set, List, Optional

from shrub.v2 import Task

from buildscripts.resmokelib.multiversionconstants import REQUIRES_FCV_TAG
from buildscripts.task_generation.suite_split import GeneratedSuite, SubSuite
from buildscripts.task_generation.task_types.resmoke_tasks import ResmokeGenTaskParams, ResmokeGenTaskService
from buildscripts.util import taskname

BACKPORT_REQUIRED_TAG = "backport_required_multiversion"
EXCLUDE_TAGS = f"{REQUIRES_FCV_TAG},multiversion_incompatible,{BACKPORT_REQUIRED_TAG}"
EXCLUDE_TAGS_FILE = "multiversion_exclude_tags.yml"


class MultiversionGenTaskParams(ResmokeGenTaskParams):
    """
    Parameters for how multiversion tests should be generated.

    mixed_version_configs: List of version configuration to generate.
    is_sharded: Whether sharded tests are being generated.
    resmoke_args: Arguments to pass to resmoke.
    parent_task_name: Name of parent task containing all sub tasks.
    origin_suite: Resmoke suite generated tests are based off.
    """

    mixed_version_configs: List[str]
    is_sharded: bool
    parent_task_name: str
    origin_suite: str
    test_list: Optional[str] = None

    @property
    def mixed_version_config(self):
        """Get the version config if there is exactly one config in self.mixed_version_configs"""
        if len(self.mixed_version_configs) != 1:
            raise ValueError("Must have a single config in mixed_version_configs, %s",
                             self.mixed_version_configs)
        return self.mixed_version_configs[0]


class MultiversionGenTaskService(ResmokeGenTaskService):
    """A service for generating multiversion tests."""

    def generate_tasks(self, generated_suite: GeneratedSuite,
                       params: MultiversionGenTaskParams) -> Set[Task]:
        """
        Generate multiversion tasks for the given suite.

        :param generated_suite: Suite to generate multiversion tasks for.
        :param params: Parameters for how tasks should be generated.
        :return: Evergreen configuration to generate the specified tasks.
        """
        sub_tasks = set()
        for version_config in params.mixed_version_configs:
            sub_task_param = params.copy()
            sub_task_param.mixed_version_configs = [version_config]
            sub_task_base_name = f"{generated_suite.task_name}_{sub_task_param.mixed_version_config}"

            for sub_suite in generated_suite.sub_suites:
                sub_tasks.add(
                    self._create_sub_task(sub_task_base_name, generated_suite, sub_task_param,
                                          sub_suite))

            if self.gen_task_options.create_misc_suite:
                # Also generate the misc task.
                sub_tasks.add(
                    self._create_sub_task(sub_task_base_name, generated_suite, sub_task_param,
                                          None))
        return sub_tasks

    def _generate_resmoke_args(self, params: MultiversionGenTaskParams, suite_file: str,
                               suite_name: str) -> str:
        """Return resmoke args used to configure a cluster for multiversion testing."""

        shared_resmoke_args = super()._generate_resmoke_args(params, suite_file, suite_name)

        # TODO SERVER-55857: move this to the multiversion fixture definition files.
        if params.is_sharded:
            resmoke_fixture_args = "--numShards=2 --numReplSetNodes=2 "
        else:
            resmoke_fixture_args = "--numReplSetNodes=3 --linearChain=on "

        tag_file_location = self.gen_task_options.generated_file_location(EXCLUDE_TAGS_FILE)

        return (
            f" {shared_resmoke_args}"
            f" --mixedBinVersions={params.mixed_version_config}"
            f" --excludeWithAnyTags={EXCLUDE_TAGS},{params.parent_task_name}_{BACKPORT_REQUIRED_TAG} "
            f" --tagFile={tag_file_location} "
            f" {resmoke_fixture_args} "
            f" {params.test_list if params.test_list else ''} ")
