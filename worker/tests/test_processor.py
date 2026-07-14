from __future__ import annotations

from processor import StubAnomalyProcessor


def test_stub_processor_returns_anomaly_report_shape(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake")

    processor = StubAnomalyProcessor()
    report = processor.process(video_path)

    assert report["chunks"] == []
    assert report["model_version"] == "stub-v0"
    assert report["generated_at"]


def test_stub_processor_simulated_latency(tmp_path, monkeypatch):
    slept = {}

    def fake_sleep(seconds):
        slept["seconds"] = seconds

    monkeypatch.setattr("processor.time.sleep", fake_sleep)
    processor = StubAnomalyProcessor(simulated_latency_seconds=2.5)
    processor.process(tmp_path / "clip.mp4")

    assert slept["seconds"] == 2.5
