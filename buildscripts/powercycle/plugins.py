"""Interactions with the undodb tool-suite."""
import yaml

from buildscripts.powercycle.run import RemoteOperations
from buildscripts.resmokelib.plugin import PluginInterface, Subcommand


class PowercycleCommand(Subcommand):
    @staticmethod
    def load_expansions(expansions_file):
        return yaml.safe_load(open(expansions_file))


class SetUpEC2Instance(PowercycleCommand):
    """Interact with UndoDB."""
    COMMAND = "setUpEC2Instance"

    def __init__(self, expansions_file):
        """Constructor."""
        self.expansions = self.load_expansions(expansions_file)

    def execute(self) -> None:
        """
        Work your magic.

        :return: None
        """
        ssh_connection_options = self.expansions["ssh_identity"] + " " + self.expansions["ssh_connection_options"]
        RemoteOperations


class SetUpEC2InstancePlugin(PluginInterface):
    """Interact with UndoDB."""

    def add_subcommand(self, subparsers):
        """
        Add 'undodb' subcommand.

        :param subparsers: argparse parser to add to
        :return: None
        """
        parser = subparsers.add_parser(SetUpEC2Instance.COMMAND)
        # Accept arbitrary args like 'resmoke.py undodb foobar', but ignore them.

    def parse(self, subcommand, parser, parsed_args, **kwargs):
        """
        Return UndoDb if command is one we recognize.

        :param subcommand: equivalent to parsed_args.command
        :param parser: parser used
        :param parsed_args: output of parsing
        :param kwargs: additional args
        :return: None or a Subcommand
        """
        if subcommand != SetUpEC2Instance.COMMAND:
            return None
        return SetUpEC2Instance(parsed_args.expansions_file)
