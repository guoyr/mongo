"""Module for retrieving the configuration of resmoke.py test suites."""

import collections
import optparse
import os

from buildscripts.resmokelib import config as _config
from buildscripts.resmokelib import errors
from buildscripts.resmokelib import utils
from buildscripts.resmokelib.testing import suite as _suite


def get_named_suites():
    """Return a sorted list of the suites names."""
    # Skip "with_*server" and "no_server" because they do not define any test files to run.
    executor_only = {"with_server", "with_external_server", "no_server"}
    names = [name for name in _config.NAMED_SUITES.keys() if name not in executor_only]
    names.sort()
    return names


def get_named_suites_with_root_level_key(root_level_key):
    """Return the suites that contain the given root_level_key and their values."""
    all_suite_names = get_named_suites()
    suites_to_return = []

    for suite in all_suite_names:
        suite_config = _get_suite_config(suite)
        if root_level_key in suite_config.keys() and suite_config[root_level_key]:
            suites_to_return.append(
                {"origin": suite, "multiversion_name": suite_config[root_level_key]})
    return suites_to_return


def create_test_membership_map(fail_on_missing_selector=False, test_kind=None):
    """Return a dict keyed by test name containing all of the suites that will run that test.

    If 'test_kind' is specified, then only the mappings for that kind of test are returned. Multiple
    kinds of tests can be specified as an iterable (e.g. a tuple or list). This function parses the
    definition of every available test suite, which is an expensive operation. It is therefore
    desirable for it to only ever be called once.
    """
    if test_kind is not None:
        if isinstance(test_kind, str):
            test_kind = [test_kind]

        test_kind = frozenset(test_kind)

    test_membership = collections.defaultdict(list)
    suite_names = get_named_suites()
    for suite_name in suite_names:
        try:
            suite_config = _get_suite_config(suite_name)
            if test_kind and suite_config.get("test_kind") not in test_kind:
                continue
            suite = _suite.Suite(suite_name, suite_config)
        except IOError as err:
            # We ignore errors from missing files referenced in the test suite's "selector"
            # section. Certain test suites (e.g. unittests.yml) have a dedicated text file to
            # capture the list of tests they run; the text file may not be available if the
            # associated SCons target hasn't been built yet.
            if err.filename in _config.EXTERNAL_SUITE_SELECTORS:
                if not fail_on_missing_selector:
                    continue
            raise

        for testfile in suite.tests:
            if isinstance(testfile, (dict, list)):
                continue
            test_membership[testfile].append(suite_name)
    return test_membership


def get_suites(suite_files, test_files):
    """Retrieve the Suite instances based on suite configuration files and override parameters.

    Args:
        suite_files: A list of file paths pointing to suite YAML configuration files. For the suites
            defined in 'buildscripts/resmokeconfig/suites/' and matrix suites, a shorthand name consisting
            of the filename without the extension can be used.
        test_files: A list of file paths pointing to test files overriding the roots for the suites.
    """
    suite_roots = None
    if test_files:
        # Do not change the execution order of the tests passed as args, unless a tag option is
        # specified. If an option is specified, then sort the tests for consistent execution order.
        _config.ORDER_TESTS_BY_NAME = any(
            tag_filter is not None
            for tag_filter in (_config.EXCLUDE_WITH_ANY_TAGS, _config.INCLUDE_WITH_ANY_TAGS))
        # Build configuration for list of files to run.
        suite_roots = _make_suite_roots(test_files)

    suites = []
    for suite_filename in suite_files:
        suite_config = _get_suite_config(suite_filename)
        if suite_roots:
            # Override the suite's default test files with those passed in from the command line.
            suite_config.update(suite_roots)
        suite = _suite.Suite(suite_filename, suite_config)
        suites.append(suite)
    return suites


def get_suite(suite_file):
    """Retrieve the Suite instance corresponding to a suite configuration file."""
    suite_config = _get_suite_config(suite_file)
    return _suite.Suite(suite_file, suite_config)


def _make_suite_roots(files):
    return {"selector": {"roots": files}}


def _get_suite_config(pathname):
    """Attempt to read YAML configuration from 'pathname' for the suite."""
    return SuiteFinder.get_config_obj(pathname)


class SuiteConfigInterface(object):
    def __init__(self, yaml_path=None):
        self.yaml_path = yaml_path


class ExplicitSuiteConfig(SuiteConfigInterface):
    """Class for storing the resmoke.py suite YAML configuration"""
    @staticmethod
    def get_config_obj(pathname):
        # Named executors or suites are specified as the basename of the file, without the .yml
        # extension.
        if not utils.is_yaml_file(pathname) and not os.path.dirname(pathname):
            if pathname not in _config.NAMED_SUITES:  # pylint: disable=unsupported-membership-test
                # Expand 'pathname' to full path.
                return None
            pathname = _config.NAMED_SUITES[pathname]  # pylint: disable=unsubscriptable-object

        if not utils.is_yaml_file(pathname) or not os.path.isfile(pathname):
            raise optparse.OptionValueError(
                "Expected a suite YAML config, but got '%s'" % pathname)
        return utils.load_yaml_file(pathname)


class MatrixSuiteConfig(SuiteConfigInterface):
    """Class for storing the resmoke.py suite YAML configuration"""
    @staticmethod
    def get_config_obj(pathname):
        suites_dir = os.path.join(_config.CONFIG_DIR, "matrix_suites")
        mappings_dir = os.path.join(suites_dir, "mappings")
        overrides_dir = os.path.join(suites_dir, "overrides")

        def get_all_suites(target_dir):
            all_suites = {}
            root = os.path.abspath(target_dir)
            files = os.listdir(root)

            for filename in files:
                (short_name, ext) = os.path.splitext(filename)
                if ext in (".yml", ".yaml"):
                    pathname = os.path.join(root, filename)

                    if not utils.is_yaml_file(pathname) or not os.path.isfile(pathname):
                        raise optparse.OptionValueError(
                            "Expected a suite YAML config, but got '%s'" % pathname)
                    suites = utils.load_yaml_file(pathname)
                    for suite_config in suites:
                        all_suites[suite_config["suite_name"]] = suite_config

            return all_suites

        all_matrix_suites = get_all_suites(mappings_dir)
        return {}


class SuiteFinder(object):
    @staticmethod
    def get_config_obj(pathname):
        explicit_suite = ExplicitSuiteConfig.get_config_obj(pathname)
        matrix_suite = MatrixSuiteConfig.get_config_obj(pathname)

        if not (explicit_suite or matrix_suite):
            raise errors.SuiteNotFound("Unknown suite 's'" % pathname)

        if explicit_suite and matrix_suite:
            raise errors.DuplicateSuiteDefinition("Multiple definitions for suite '%s'" % pathname)

        return matrix_suite or explicit_suite

    @staticmethod
    def get_named_suites(config_dir):
        """ Populate the named suites by scanning config_dir/suites. """
        named_suites = {}

        suites_dir = os.path.join(config_dir, "suites")
        root = os.path.abspath(suites_dir)
        files = os.listdir(root)
        for filename in files:
            (short_name, ext) = os.path.splitext(filename)
            if ext in (".yml", ".yaml"):
                pathname = os.path.join(root, filename)
                # TODO: store named suite in an object
                named_suites[short_name] = pathname

        return named_suites
