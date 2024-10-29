# Copyright (C) 2024 Andrew Wason
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import typing
from collections.abc import Callable

import click
from pluggy import HookimplMarker, HookspecMarker

if typing.TYPE_CHECKING:
    from langchain_core.tools import BaseTool


hookspec = HookspecMarker("elelem")
hookimpl = HookimplMarker("elelem")


@hookspec
def register_providers(register: Callable[[click.Group], None]):
    """Register LLM model providers click groups"""


@hookspec
def register_tools(register: Callable[[BaseTool], None]):
    """Register LLM tools"""
