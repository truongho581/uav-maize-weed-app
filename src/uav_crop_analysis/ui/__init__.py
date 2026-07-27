"""PySide6 desktop presentation layer."""

from typing import Any

__all__ = ["MainWindow"]


def __getattr__(name: str) -> Any:
    if name == "MainWindow":
        from .shell import MainWindow

        return MainWindow
    raise AttributeError(name)
