"""CLI commands and pytest hooks."""

from agent_eval.cli.pytest_plugin import (
    agent_client,
    eval_config,
    eval_dataset,
    eval_judge,
    pytest_addoption,
)

__all__ = [
    "pytest_addoption",
    "eval_config",
    "agent_client",
    "eval_judge",
    "eval_dataset",
]
