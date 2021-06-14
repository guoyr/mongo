from datetime import datetime

from pydantic import BaseModel
from typing import Optional, List

from buildscripts.task_generation.suite_split import SuiteSplitConfig, SuiteSplitParameters
from buildscripts.task_generation.task_types.fuzzer_tasks import FuzzerGenTaskParams
from buildscripts.task_generation.task_types.gentask_options import GenTaskOptions
from buildscripts.task_generation.task_types.multiversion_tasks import MultiversionGenTaskParams
from buildscripts.task_generation.task_types.resmoke_tasks import ResmokeGenTaskParams
from buildscripts.util.fileops import read_yaml_file
from buildscripts.util.taskname import remove_gen_suffix

DEFAULT_CONFIG_DIRECTORY = "generated_resmoke_config"
DEFAULT_MAX_TESTS_PER_SUITE = 100
DEFAULT_TARGET_RESMOKE_TIME = 60
DEFAULT_MAX_SUB_SUITES = 5

ASAN_SIGNATURE = "detect_leaks=1"

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


class EvgExpansions(BaseModel):
    """
    Evergreen expansions to read for configuration.

    build_id: ID of build being run.
    build_variant: Build Variant being run on.
    continue_on_failure: Should tests continue after encountering a failure.
    create_misc_suite: Whether to create the "_misc" suite file.
    is_patch: Are tests being run in a patch build.
    jstestfuzz_vars: Variable to pass to jstestfuzz command.
    is_jstestfuzz: Is a fuzzer task.
    large_distro_name: Name of "large" distro to use.
    max_sub_suites: Max number of sub-suites to create for a single task.
    max_tests_per_suite: Max number of tests to include in a single sub-suite.
    name: Name of task to generate.
    npm_command: NPM command to generate fuzzer tests.
    num_files: Number of fuzzer files to generate.
    num_tasks: Number of sub-tasks to generate.
    project: Evergreen project being run in.
    require_multiversion: Requires downloading Multiversion binaries.
    resmoke_args: Arguments to pass to resmoke.
    resmoke_jobs_max: Max number of jobs resmoke should execute in parallel.
    resmoke_repeat_suites: Number of times resmoke should repeat each suite.
    revision: git revision being run against.
    san_options: SAN options build variant is running under.
    should_shuffle: Should remove shuffle tests before executing.
    suite: Resmoke suite to run the tests.
    target_resmoke_time: Target time (in minutes) to keep sub-suite under.
    task_id: ID of task currently being executed.
    require_multiversion: Requires downloading Multiversion binaries.
    timeout_secs: Timeout to set for task execution.
    use_large_distro: Should tasks be generated to run on a large distro.
    """

    # Evergreen-generated expansions.
    build_id: str
    build_variant: str
    is_patch: Optional[bool]
    large_distro_name: Optional[str]
    project: str
    revision: str
    task_id: str
    task_name: str
    timeout_secs: Optional[int]
    use_large_distro: Optional[bool]

    # Resmoke expansions.
    continue_on_failure: Optional[bool]
    jstestfuzz_vars: Optional[str]  # Static split only.
    npm_command: Optional[str]  # Static split only.
    resmoke_args: str
    resmoke_jobs_max: Optional[int]
    resmoke_repeat_suites: int = 1
    should_shuffle: Optional[bool]
    suite: Optional[str]
    san_options: Optional[str]

    # Task generation expansions.
    create_misc_suite: bool = True
    is_jstestfuzz: bool = False  # Static split only.
    max_sub_suites: int = DEFAULT_MAX_SUB_SUITES
    max_tests_per_suite: int = DEFAULT_MAX_TESTS_PER_SUITE
    num_files: Optional[int]  # Static split only.
    num_tasks: Optional[int]  # Static split only.
    target_resmoke_time: int = DEFAULT_TARGET_RESMOKE_TIME
    require_multiversion: Optional[bool]

    @classmethod
    def from_yaml_file(cls, path: str) -> "EvgExpansions":
        """
        Read the generation configuration from the given file.

        :param path: Path to file.
        :return: Parse evergreen expansions.
        """
        return cls(**read_yaml_file(path))

    def config_location(self) -> str:
        """Get the location to store the configuration."""
        return f"{self.build_variant}/{self.revision}/generate_tasks/{self.task}_gen-{self.build_id}.tgz"

    def is_asan_build(self) -> bool:
        """Determine if this task is an ASAN build."""
        san_options = self.san_options
        if san_options:
            return ASAN_SIGNATURE in san_options
        return False

    @property
    def task(self) -> str:
        """Get the task being generated."""
        return remove_gen_suffix(self.task_name)

    def gen_task_options(self) -> GenTaskOptions:
        """Determine the options for generating tasks based on the given expansions."""
        return GenTaskOptions(
            is_patch=self.is_patch,
            create_misc_suite=True,
            generated_config_dir=DEFAULT_CONFIG_DIRECTORY,
            use_default_timeouts=False,
        )

    def get_suite_split_config(self, start_date: datetime, end_date: datetime) -> SuiteSplitConfig:
        """
        Get the configuration for splitting suites based on Evergreen expansions.

        :param start_date: Start date for historic stats lookup.
        :param end_date: End date for historic stats lookup.
        :return: Configuration to use for splitting suites.
        """
        return SuiteSplitConfig(
            evg_project=self.project,
            target_resmoke_time=self.target_resmoke_time,
            max_sub_suites=self.max_sub_suites,
            max_tests_per_suite=self.max_tests_per_suite,
            start_date=start_date,
            end_date=end_date,
        )

    def get_split_params(self) -> SuiteSplitParameters:
        """Get the parameters specified to split suites."""
        return SuiteSplitParameters(
            task_name=self.task_name,
            suite_name=self.suite or self.task,
            filename=self.suite or self.task,
            test_file_filter=None,
            build_variant=self.build_variant,
            is_asan=self.is_asan_build(),
        )

    def get_generation_options(self) -> GenTaskOptions:
        """Get options for how tasks should be generated."""
        return GenTaskOptions(
            create_misc_suite=self.create_misc_suite,
            is_patch=self.is_patch,
            generated_config_dir=DEFAULT_CONFIG_DIRECTORY,
            use_default_timeouts=False,
        )

    def get_gen_params(self) -> "ResmokeGenTaskParams":
        """Get the parameters to use for generating tasks."""
        return ResmokeGenTaskParams(
            use_large_distro=self.use_large_distro, large_distro_name=self.large_distro_name,
            require_multiversion=self.require_multiversion,
            repeat_suites=self.resmoke_repeat_suites, resmoke_args=self.resmoke_args,
            resmoke_jobs_max=self.resmoke_jobs_max, config_location=
            f"{self.build_variant}/{self.revision}/generate_tasks/{self.task}_gen-{self.build_id}.tgz"
        )

    def get_suite_split_params(self) -> SuiteSplitParameters:
        """Get the parameters to use for splitting suites."""
        task = remove_gen_suffix(self.task_name)
        return SuiteSplitParameters(
            build_variant=self.build_variant,
            task_name=task,
            suite_name=self.suite or task,
            filename=self.suite or task,
            test_file_filter=None,
            is_asan=self.is_asan_build(),
        )

    def get_multiversion_generation_params(self, is_sharded: bool) -> MultiversionGenTaskParams:
        """
        Get the parameters to use to generating multiversion tasks.

        :param is_sharded: True if a sharded sutie is being generated.
        :return: Parameters to use for generating multiversion tasks.
        """
        version_config_list = get_version_configs(is_sharded)
        return MultiversionGenTaskParams(
            mixed_version_configs=version_config_list,
            is_sharded=is_sharded,
            resmoke_args=self.resmoke_args,
            parent_task_name=self.task,
            origin_suite=self.suite or self.task,
            use_large_distro=self.use_large_distro,
            large_distro_name=self.large_distro_name,
            config_location=self.config_location(),
        )

    def get_evg_config_gen_options(self, generated_config_dir: str) -> GenTaskOptions:
        """
        Get the configuration for generating tasks from Evergreen expansions.

        :param generated_config_dir: Directory to write generated configuration.
        :return: Configuration to use for splitting suites.
        """
        return GenTaskOptions(
            create_misc_suite=True,
            is_patch=self.is_patch,
            generated_config_dir=generated_config_dir,
            use_default_timeouts=False,
        )

    def fuzzer_gen_task_params(self, version_config: str = None,
                               is_sharded: bool = None) -> FuzzerGenTaskParams:
        """Determine the parameters for generating fuzzer tasks based on the given expansions."""
        task_name = self.task_name
        resmoke_args = self.resmoke_args
        if version_config:
            task_name = f"{self.suite}_multiversion_{version_config}"
            add_resmoke_args = get_multiversion_resmoke_args(is_sharded)
            resmoke_args = f"{self.resmoke_args or ''} --mixedBinVersions={version_config} {add_resmoke_args}"

        return FuzzerGenTaskParams(
            task_name=task_name, num_files=self.num_files, num_tasks=self.num_tasks,
            resmoke_args=resmoke_args, npm_command=self.npm_command or "jstestfuzz",
            jstestfuzz_vars=self.jstestfuzz_vars, variant=self.build_variant,
            continue_on_failure=self.continue_on_failure, resmoke_jobs_max=self.resmoke_jobs_max,
            should_shuffle=self.should_shuffle, timeout_secs=self.timeout_secs,
            require_multiversion=self.require_multiversion, suite=self.suite,
            use_large_distro=self.use_large_distro, large_distro_name=self.large_distro_name,
            config_location=
            f"{self.build_variant}/{self.revision}/generate_tasks/{self.task}_gen-{self.build_id}.tgz"
        )
