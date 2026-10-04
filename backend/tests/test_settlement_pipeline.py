from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.models import SettlementStatus
from app.repositories import TradeRepository
from app.services.rigs import requires_settlement_review


class SettlementConnection:
    def __init__(self, claim_results: list[object | None] | None = None) -> None:
        self.claim_results = claim_results or []
        self.queries: list[str] = []
        self.args: list[tuple[object, ...]] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchval(self, query: str, *args: object) -> object | None:
        self.queries.append(query)
        self.args.append(args)
        return self.claim_results.pop(0) if self.claim_results else None

    async def fetchrow(self, query: str, *args: object) -> object | None:
        self.queries.append(query)
        self.args.append(args)
        return None


class SettlementPool:
    def __init__(self, connection: SettlementConnection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


@pytest.mark.parametrize(
    ("score", "requires_review"),
    [(0.749, True), (0.75, False), (0.9, False), (None, False)],
)
def test_rigs_trust_gate_has_an_exact_seventy_five_point_boundary(
    score: float | None, requires_review: bool
) -> None:
    assert requires_settlement_review(score) is requires_review


@pytest.mark.asyncio
async def test_payout_claim_is_idempotent_and_transitions_pending_once() -> None:
    trade_id = uuid4()
    connection = SettlementConnection([trade_id, None])
    repository = TradeRepository(SettlementPool(connection))  # type: ignore[arg-type]

    first = await repository.start_payout(
        uuid4(), trade_id, f"originsync-{trade_id}"
    )
    duplicate = await repository.start_payout(
        uuid4(), trade_id, f"originsync-{trade_id}"
    )

    assert first is True
    assert duplicate is False
    assert all("settlement_status = 'pending'" in query for query in connection.queries)
    assert all("paypal_sender_batch_id is null" in query for query in connection.queries)
    assert connection.args[0][2] == f"originsync-{trade_id}"


@pytest.mark.asyncio
async def test_payout_completion_update_only_applies_from_processing() -> None:
    connection = SettlementConnection()
    repository = TradeRepository(SettlementPool(connection))  # type: ignore[arg-type]

    await repository.set_payout(uuid4(), uuid4(), "batch-1", "completed")

    assert "settlement_status = 'processing'" in connection.queries[0]
    assert "returning id" in connection.queries[0].lower()


@pytest.mark.asyncio
async def test_webhook_cannot_regress_terminal_payout_or_match_multiple_ids() -> None:
    connection = SettlementConnection()
    repository = TradeRepository(SettlementPool(connection))  # type: ignore[arg-type]

    await repository.apply_paypal_payout_event(
        "event-1", "batch-1", "sender-1", uuid4(), "processing"
    )

    query = connection.queries[0]
    assert "settlement_status in ('pending', 'processing')" in query
    assert "and ($1 is null or paypal_payout_batch_id = $1)" in query
    assert "and ($4 is null or paypal_sender_batch_id = $4)" in query
    assert "and ($5 is null or id = $5)" in query
    assert SettlementStatus.FLAGGED_FOR_REVIEW.value == "flagged_for_review"