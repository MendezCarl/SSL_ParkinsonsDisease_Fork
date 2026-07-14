from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from client import AnomalyApiClient
from config import WorkerConfig


@pytest.fixture
def config(monkeypatch) -> WorkerConfig:
    monkeypatch.setenv("API_BASE_URL", "http://backend.local")
    monkeypatch.setenv("ANOMALY_WORKER_TOKEN", "secret-token")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "5")
    return WorkerConfig()


def test_client_sets_auth_header_from_config(config):
    client = AnomalyApiClient(config)
    assert client._session.headers["Authorization"] == "Bearer secret-token"


def test_list_pending_calls_expected_url(config):
    client = AnomalyApiClient(config)
    fake_response = MagicMock()
    fake_response.json.return_value = [{"job_id": "abc"}]
    fake_response.raise_for_status.return_value = None

    with patch.object(client._session, "get", return_value=fake_response) as mock_get:
        result = client.list_pending()

    assert result == [{"job_id": "abc"}]
    args, kwargs = mock_get.call_args
    assert args[0] == "http://backend.local/ml/anomaly/jobs"
    assert kwargs["params"] == {"status": "pending"}


def test_fetch_video_streams_chunks_to_dest_path(config, tmp_path):
    client = AnomalyApiClient(config)
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.iter_content.return_value = [b"chunk1", b"chunk2"]

    dest = tmp_path / "job123.mp4"
    with patch.object(client._session, "get", return_value=fake_response):
        result_path = client.fetch_video("job123", dest)

    assert result_path == dest
    assert dest.read_bytes() == b"chunk1chunk2"


def test_post_complete_sends_result_body(config):
    client = AnomalyApiClient(config)
    fake_response = MagicMock()
    fake_response.json.return_value = {"job_id": "abc", "status": "done"}
    fake_response.raise_for_status.return_value = None

    with patch.object(client._session, "post", return_value=fake_response) as mock_post:
        result = client.post_complete("abc", result={"chunks": []})

    assert result == {"job_id": "abc", "status": "done"}
    args, kwargs = mock_post.call_args
    assert args[0] == "http://backend.local/ml/anomaly/jobs/abc/complete"
    assert kwargs["json"] == {"result": {"chunks": []}}


def test_post_complete_sends_error_body(config):
    client = AnomalyApiClient(config)
    fake_response = MagicMock()
    fake_response.json.return_value = {"job_id": "abc", "status": "failed"}
    fake_response.raise_for_status.return_value = None

    with patch.object(client._session, "post", return_value=fake_response) as mock_post:
        client.post_complete("abc", error="boom")

    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {"error": "boom"}
