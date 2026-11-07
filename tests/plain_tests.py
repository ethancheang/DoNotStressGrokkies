"""Helpers for running the tests as plain functions.

The project brief requires the whole codebase to be procedural (functions
only), so every test is a top-level ``test_`` function that checks results
with ``assert``.

``function_suite`` lets the usual command still find and run those functions:

    python -m unittest discover -s tests -v

Each test file ends with a ``load_tests`` function that calls it. pytest can
also collect the same ``test_`` functions directly.
"""
import logging
import logging.handlers
import unittest
from contextlib import contextmanager
from types import SimpleNamespace


def function_suite(namespace: dict) -> unittest.TestSuite:
    """Wrap every test_ function defined in one test file, in file order."""
    module_name = namespace["__name__"]
    tests = [
        unittest.FunctionTestCase(value)
        for name, value in namespace.items()
        if name.startswith("test_")
        and callable(value)
        and getattr(value, "__module__", None) == module_name
    ]
    return unittest.TestSuite(tests)


@contextmanager
def case(**details):
    """Label one case in a loop, so a failure says which case broke.

    Replaces unittest's subTest. Unlike subTest, the test stops at the first
    failing case.
    """
    try:
        yield
    except AssertionError as error:
        raise AssertionError(f"{error} [case: {details}]") from error


@contextmanager
def capture_logs(logger_name: str, level: str = "INFO"):
    """Collect log messages from one logger, like unittest's assertLogs.

    Yields an object whose ``output`` list holds "LEVEL:logger:message"
    strings once the block ends. Fails if nothing was logged at ``level`` or
    above.
    """
    logger = logging.getLogger(logger_name)
    handler = logging.handlers.BufferingHandler(capacity=10_000)
    handler.setLevel(level)
    old_level, old_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    captured = SimpleNamespace(output=[], records=handler.buffer)
    try:
        yield captured
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate
    captured.output.extend(
        f"{record.levelname}:{record.name}:{record.getMessage()}"
        for record in handler.buffer
    )
    assert handler.buffer, f"no logs of level {level} or higher on {logger_name!r}"
