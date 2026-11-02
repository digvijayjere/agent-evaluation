"""Unit tests for pytest plugin options and fixtures."""

from bdiplus_eval.core.agent_client import MockAgent
from bdiplus_eval.metrics.judge_client import JudgeClient


def test_eval_config_defaults(eval_config):
    assert eval_config["agent_endpoint"] == "mock://compliant"
    assert eval_config["suite"] == "all"
    assert eval_config["baseline_metrics"] is None
    assert eval_config["gate"] is False
    assert eval_config["gate_threshold"] == 0.03
    assert eval_config["langfuse_sync"] is False
    assert eval_config["report_out"] == "reports/eval_report.json"


def test_agent_client_fixture(agent_client):
    assert isinstance(agent_client, MockAgent)
    assert agent_client.mode == "compliant"


def test_eval_judge_fixture(eval_judge):
    assert isinstance(eval_judge, JudgeClient)


def test_eval_dataset_fixture(eval_dataset):
    assert isinstance(eval_dataset, list)
    assert len(eval_dataset) >= 150
