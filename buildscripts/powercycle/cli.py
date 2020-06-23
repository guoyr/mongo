"""Command-line entry-point for remote_operations."""

from buildscripts.powercycle import parser


def main(argv):
    """
    Execute Main function for remote_operations.

    :param argv: sys.argv
    :return: None
    """
    subcommand = parser.parse_command_line(argv[1:])
    subcommand.execute()
