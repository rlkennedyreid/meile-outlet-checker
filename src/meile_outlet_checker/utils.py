"""Module for simple helper methods with no dependencies within the package"""

from functools import cache, partial
from importlib.metadata import version as _version
from logging import Formatter, getLogger
from pathlib import Path
from sys import maxsize
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


@cache
def package() -> str:
    """Get the name of the top-level package"""
    return __name__.split(".")[0]


@cache
def version() -> str:
    """Get the version of the top-level package"""
    return _version(package())


def create_basic_logger(
    name: str, log_level: Optional[str] = None, clear_current_handlers: bool = False
):
    logger = getLogger(name)
    if clear_current_handlers:
        logger.handlers.clear()

    handler = RichHandler(rich_tracebacks=True, level=logger.level)

    handler.setFormatter(Formatter(fmt="%(name)s:%(message)s"))

    if log_level:
        logger.setLevel(log_level)

    logger.addHandler(handler)


def create_directory(path: Path) -> None:
    """Create a directory if it doesn't exist already"""
    path.mkdir(parents=True, exist_ok=True)


uopen = partial(open, encoding="UTF-8")
err_console = Console(stderr=True, style="red")
console = Console(stderr=False)
file_console = partial(Console, width=maxsize)
