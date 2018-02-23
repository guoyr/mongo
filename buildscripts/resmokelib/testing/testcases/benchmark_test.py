"""
unittest.TestCase for tests using a MongoDB vendored version of Google Benchmark.
"""

from __future__ import absolute_import

import optparse

from . import interface
from ... import core
from ... import utils
from ... import config as _config


class BenchmarkTestCase(interface.TestCase):
    """
    A Benchmark test to execute.
    """

    REGISTERED_NAME = "benchmark_test"

    def __init__(self,
                 logger,
                 program_executable,
                 program_options=None):
        """
        Initializes the BenchmarkTestCase with the executable to run.
        """

        interface.TestCase.__init__(self, logger, "Program", program_executable)

        self.report_incompatible_options()

        self.program_executable = program_executable

        # Program options are set from the suite yaml config, which overrides any command line
        # values or default values set through resmoke.py. In general, there should not be a
        # need for suite specific configurations.
        suite_config_program_options = utils.default_if_none(program_options, {}).copy()

        # 1. Set the default benchmark out file path based on the executable path. Keep the
        #    existing extension (if any) to simplify parsing.
        combined_program_options = {
            "benchmark_out": self.program_executable + '.json'
        }

        # 2. Override with options set through resmoke.py.
        for key, value in _config.BENCHMARK_CONFIG.items():
            if value is not None:
                combined_program_options[key.lower()] = value

        # 3. Override any options explicitly set through the suite YAML config.
        combined_program_options.update(suite_config_program_options)

        self.program_options = combined_program_options

    def report_incompatible_options(self):
        """
        Some options are incompatible with benchmark test suites, we error out early if any of
        these options are specified.

        :return: None
        """

        if _config.REPEAT > 1:
            raise optparse.OptionValueError(
                "--repeat cannot be used with benchmark tests; please use --benchmarMinTimeSecs "
                "if you'd like to change the runtime of a single benchmark."
            )

        if _config.JOBS > 1:
            raise optparse.OptionValueError(
                "--jobs=%d cannot be used for benchmark tests"
                % _config.JOBS
            )

        if _config.SHUFFLE is not False:
            raise optparse.OptionValueError(
                "--shuffle is not supported for benchmark tests at the moment"
            )

    def run_test(self):
        try:
            program = self._make_process()
            self._execute(program)
        except self.failureException:
            raise
        except:
            self.logger.exception(
                "Encountered an error running Benchmark test %s.", self.basename())
            raise

    def _make_process(self):
        return core.programs.generic_program(self.logger,
                                             [self.program_executable],
                                             **self.program_options)
