import os

from buildscripts.resmokelib.testing.testcases import interface

from ... import core
from ... import utils

# path /opt/java/jdk9/bin
# env_vars = {'PATH': '/opt/java/jdk9/bin:' + os.environ['PATH']}

# java -jar -XX:+UseParallelGC tla2tools.jar ~/mongo-repl-tla/RaftMongo.toolbox/Model_1/MC.tla


class TLCTestCase(interface.ProcessTestCase):
    """A TLA+ Model checker test"""

    REGISTERED_NAME = "tlc_test"

    def __init__(self, logger, tla_spec_path, tla2tools_executable=None):
        interface.ProcessTestCase.__init__(self, logger, 'TLC model cheker', tla_spec_path)

        tla2tools_executable = utils.default_if_none('tla2tools.jar', tla2tools_executable)
        self.tla2tools_args = [
            'java', '-jar', '-XX:+UseParallelGC', tla2tools_executable, tla_spec_path
        ]
        self.java_executable_path = '/opt/java/jdk9/bin'

    def _make_process(self):
        env_vars = {'PATH': '/opt/java/jdk9/bin:' + os.environ['PATH']}
        return core.programs.generic_program(self.logger, self.tla2tools_args, process_kwargs={'env_vars': env_vars})
