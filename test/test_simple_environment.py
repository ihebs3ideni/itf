"""
A dummy test using the logging_fixture.

The fixture used as the function argument will ensure several
basic services are started before the code executed in the test body.

Run with the logs enabled to see the output.
"""

import logging
import score.sctf as sctf

logger = logging.getLogger(__name__)


def test_simple_environment_example(basic_sandbox):
    logger.info("Hello Simple SCTF!")
    pass


if __name__ == "__main__":
    sctf.run(__file__)
