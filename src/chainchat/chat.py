# Copyright (C) 2024 Andrew Wason
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import readline  # for input()  # noqa: F401
from collections.abc import Callable, Iterator, Sequence
from typing import TYPE_CHECKING, Any

import click
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, trim_messages
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .attachment import Attachment, build_message_with_attachments

if TYPE_CHECKING:
    from langchain_core.prompts.chat import MessageLikeRepresentation
    from langchain_core.tools import BaseTool


class ToolLoggingHandler(BaseCallbackHandler):
    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        click.secho(
            f"Tool: {serialized["name"]} {input_str}",
            err=True,
            italic=True,
            dim=True,
        )


class Chat:
    def __init__(
        self,
        model: BaseChatModel,
        system_message: str | None = None,
        tools: Sequence[BaseTool] | None = None,
        max_history_tokens: int | None = None,
    ):
        if tools:
            tools_list = list(tools)
            tool_node = ToolNode(tools_list)
            model = model.bind_tools(tools_list)
        else:
            tool_node = None

        messages: list[MessageLikeRepresentation] = []
        if system_message is not None:
            messages.append(("system", system_message))
        messages.append(MessagesPlaceholder(variable_name="messages"))
        chain = ChatPromptTemplate.from_messages(messages)

        if max_history_tokens is not None:
            chain = chain | trim_messages(
                max_tokens=max_history_tokens,
                strategy="last",
                token_counter=model,
                include_system=True,
                allow_partial=False,
                start_on="human",
                end_on=("human", "tool"),
            )
        self.chain = chain | model

        graph = StateGraph(state_schema=MessagesState)
        graph.add_edge(START, "agent")
        graph.add_node("agent", self._run_chain)
        if tool_node:
            graph.add_conditional_edges("agent", tools_condition)
            graph.add_node("tools", tool_node)
            graph.add_edge("tools", "agent")

        # XXX make checkpointer configurable (memory or sqlite), make thread_id configurable
        self.graph = graph.compile(checkpointer=MemorySaver()).with_config(
            {"configurable": {"thread_id": "1"}},
            callbacks=[ToolLoggingHandler()],
        )

    def _run_chain(self, state: MessagesState):
        return {"messages": [self.chain.invoke(state)]}

    def invoke(self, messages: Sequence[MessageLikeRepresentation]):
        yield self.graph.invoke({"messages": messages})

    def stream(self, messages: Sequence[MessageLikeRepresentation]):
        for chunk, _ in self.graph.stream(
            {"messages": messages},
            # https://langchain-ai.github.io/langgraph/cloud/how-tos/stream_messages
            stream_mode="messages",
        ):
            if isinstance(chunk, AIMessage) and chunk.content:  # Filter to just model responses
                yield chunk.content

    def prompt(
        self,
        prompt: str,
        renderer: Callable[[Iterator[str]], None],
        attachments: tuple[Attachment] | None = None,
    ):
        renderer(self.stream(build_message_with_attachments(prompt, attachments)))

    def chat(self, renderer: Callable[[Iterator[str]], None], attachments: tuple[Attachment] | None = None):
        click.echo("Chat - Ctrl-D to exit")
        click.echo("Enter >>> for multiline mode, then <<< to finish")
        try:
            while True:
                prompt = input("> ")
                if prompt == ">>>":
                    prompt = ""
                    while prompt != "<<<":
                        prompt += input(". ") + "\n"

                self.prompt(prompt, renderer, attachments)
                attachments = None
        except EOFError:
            return
