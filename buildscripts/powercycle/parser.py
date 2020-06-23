"""Parser for command line arguments."""

import argparse

_PLUGINS = []


def _add_subcommands():
    """Create and return the command line arguments parser."""
    parser = argparse.ArgumentParser()
    _add_global_arg(parser)
    subparsers = parser.add_subparsers(dest="command")

    # Add sub-commands.
    for plugin in _PLUGINS:
        plugin.add_subcommand(subparsers)

    return parser


def _add_global_arg(parser):
    """Add arguments that are global to "remote_operations.py."""
    parser.add_argument(
        "--expansions-file", dest="expansions_file", metavar="PATH",
        help=("The path of the expansions file generated for this task."))


def parse(sys_args):
    """Parse the CLI args."""

    # Split out this function for easier testing.
    parser = _add_subcommands()
    parsed_args = parser.parse_args(sys_args)

    return parser, parsed_args


def parse_command_line(sys_args, **kwargs):
    """Parse the command line arguments passed to resmoke.py and return the subcommand object to execute."""
    parser, parsed_args = parse(sys_args)

    subcommand = parsed_args.command

    for plugin in _PLUGINS:
        subcommand_obj = plugin.parse(subcommand, parser, parsed_args, **kwargs)
        if subcommand_obj is not None:
            return subcommand_obj

    raise RuntimeError(f"Resmoke configuration has invalid subcommand: {subcommand}. Try '--help'")
