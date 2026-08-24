from datetime import UTC, datetime
from uuid import uuid4

from ima.api.contracts import DiagnosticJob, SseEvent


def test_contract_aliases_are_stable() -> None:
    now = datetime.now(UTC)
    job = DiagnosticJob(
        id=uuid4(),
        status="queued",
        attempts=0,
        correlationId="c",
        createdAt=now,
        updatedAt=now,
    )
    assert set(job.model_dump(by_alias=True)) == {
        "id",
        "status",
        "attempts",
        "correlationId",
        "createdAt",
        "updatedAt",
    }
    event = SseEvent[dict](id="1", type="system.event.v1", data={})
    assert event.model_dump(by_alias=True)["occurredAt"].tzinfo is UTC
