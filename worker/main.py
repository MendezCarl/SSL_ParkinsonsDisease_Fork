from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

from client import AnomalyApiClient
from config import load_config
from processor import AnomalyProcessor, StubAnomalyProcessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("anomaly-worker")


def run_once(client: AnomalyApiClient, processor: AnomalyProcessor, workdir: Path) -> int:
    jobs = client.list_pending()
    for job in jobs:
        job_id = job["job_id"]
        logger.info("Picked up job %s (patient=%s test=%s)", job_id, job.get("patient_id"), job.get("test_name"))
        video_path = workdir / f"{job_id}.mp4"
        try:
            client.fetch_video(job_id, video_path)
            report = processor.process(video_path)
            client.post_complete(job_id, result=report)
            logger.info("Job %s completed", job_id)
        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            try:
                client.post_complete(job_id, error=str(exc))
            except Exception:
                logger.exception("Failed to report failure for job %s back to the API", job_id)
        finally:
            video_path.unlink(missing_ok=True)
    return len(jobs)


def main() -> None:
    config = load_config()
    config.validate()
    client = AnomalyApiClient(config)
    processor: AnomalyProcessor = StubAnomalyProcessor()

    logger.info(
        "Anomaly worker started; polling %s every %ss",
        config.api_base_url,
        config.poll_interval_seconds,
    )
    with tempfile.TemporaryDirectory(prefix="anomaly-worker-") as tmp:
        workdir = Path(tmp)
        while True:
            try:
                run_once(client, processor, workdir)
            except Exception:
                logger.exception("Poll cycle failed")
            time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    main()
