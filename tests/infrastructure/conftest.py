"""Makes the fixtures of `local_server` available to the tests of this package."""

from tests.infrastructure.local_server import local_server, release

__all__ = ["local_server", "release"]
