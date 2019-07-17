from buildscripts.resmokelib.testing.testcases import interface

from ... import utils

# path /opt/java/jdk9/bin
# env_vars = {'PATH': '/opt/java/jdk9/bin:' + os.environ['PATH']}


# java -jar -XX:+UseParallelGC tla2tools.jar ~/mongo-repl-tla/RaftMongo.toolbox/Model_1/MC.tla


class TLCTestCase(interface.ProcessTestCase):
    """A TLA+ Model checker test"""

    REGISTERED_NAME = "tlc_test"

    def __init__(self, logger, tla_spec, tla2tools_executable=None, tla2tools_options=None):
        interface.ProcessTestCase.__init__(self, logger, 'TLC model cheker', tla_spec)

        self.tla2tools_executable = utils.default_if_none('tla2tools', tla2tools_executable)
