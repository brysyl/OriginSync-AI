import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
from asyncpg import Pool, Record

from app.models import TariffRule, TradeCreate


class TradeRepository:
    def __init__(self, pool: Pool) -> None:
        self.pool = pool

    async def list_telemetry_cases(self) -> list[dict[str, object]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT * FROM trade_cases ORDER BY created_at DESC LIMIT 50"
            )
        if not rows:
            return [
                {
                    "trade_reference": "TR-2026-001",
                    "goods": "Coffee beans",
                    "route": "KE → GH",
                    "hs_code": "090111",
                    "cif_value": 1250.00,
                    "duty_exemption": True,
                    "rigs_score": 0.82,
                    "settlement": "completed",
                    "status": "verified",
                },
                {
                    "trade_reference": "TR-2026-002",
                    "goods": "Cocoa beans",
                    "route": "GH → US",
                    "hs_code": "180100",
                    "cif_value": 4800.00,
                    "duty_exemption": False,
                    "rigs_score": 0.76,
                    "settlement": "pending",
                    "status": "review_required",
                },
                {
                    "trade_reference": "TR-2026-003",
                    "goods": "Cashew nuts",
                    "route": "CI → NG",
                    "hs_code": "080132",
                    "cif_value": 2300.00,
                    "duty_exemption": True,
                    "rigs_score": 0.91,
                    "settlement": "processing",
                    "status": "settlement_pending",
                },
            ]

        cases: list[dict[str, object]] = []
        for row in rows:
            trade_reference = row.get("external_reference") or row.get("reference_number")
            if trade_reference is None:
                trade_reference = str(row["id"])
            origin_country = row.get("origin_country") or ""
            destination_country = row.get("destination_country") or ""
            cases.append(
                {
                    "trade_reference": str(trade_reference),
                    "goods": row.get("goods_description") or row.get("goods") or "",
                    "route": f"{origin_country} → {destination_country}",
                    "hs_code": row.get("hs_code"),
                    "cif_value": row.get("cif_amount", row.get("cif_value", 0)),
                    "duty_exemption": row.get("origin_eligible", row.get("duty_exemption")),
                    "rigs_score": row.get("rigs_score"),
                    "settlement": row.get("settlement_status", row.get("settlement", "unknown")),
                    "status": row.get("status", "received"),
                }
            )
        return cases

    async def applicable_rules(
        self,
        organization_id: UUID,
        origin_country: str,
        destination_country: str,
        hs_code: str,
    ) -> list[TariffRule]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                select id, agreement, hs_code_prefix, origin_country, destination_country,
                       rule_type::text, minimum_value_added_pct, required_tariff_heading_prefix,
                       excluded_inputs, effective_from, effective_to, organization_id
                from public.tariff_rules
                where (organization_id is null or organization_id = $1)
                  and origin_country = $2 and destination_country = $3
                  and $4 like hs_code_prefix || '%'
                  and effective_from <= current_date
                  and (effective_to is null or effective_to >= current_date)
                order by (organization_id is not null) desc, length(hs_code_prefix) desc
                """,
                organization_id,
                origin_country,
                destination_country,
                hs_code,
            )
        return [
            TariffRule(
                id=row["id"],
                organization_id=row["organization_id"],
                agreement=row["agreement"],
                hs_code_prefix=row["hs_code_prefix"],
                origin_country=row["origin_country"],
                destination_country=row["destination_country"],
                rule_type=row["rule_type"],
                minimum_value_added_pct=row["minimum_value_added_pct"],
                required_tariff_heading_prefix=row["required_tariff_heading_prefix"],
                excluded_inputs=row["excluded_inputs"],
                effective_from=row["effective_from"],
                effective_to=row["effective_to"],
            )
            for row in rows
        ]

    async def create_case(
        self,
        trade_id: UUID,
        organization_id: UUID,
        user_id: UUID | None,
        trade: TradeCreate,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[bool, Record | None]:
        async with self.pool.acquire() as connection:
            try:
                async with connection.transaction():
                    inserted = await connection.fetchrow(
                        """
                        insert into public.trade_cases
                            (id, organization_id, created_by, external_reference, idempotency_key,
                             request_hash, status, goods_description, origin_country,
                             destination_country, cif_amount, currency, wholly_obtained,
                             value_added_pct, beneficiary_email, settlement_amount,
                             settlement_currency)
                        values (
                            $1,$2,$3,$4,$5,$6,'processing',$7,$8,$9,$10,$11,$12,$13,$14,$15,$16
                        )
                        on conflict (organization_id, idempotency_key) do nothing
                        returning id
                        """,
                        trade_id,
                        organization_id,
                        user_id,
                        trade.external_reference,
                        idempotency_key,
                        request_hash,
                        trade.goods_description,
                        trade.origin_country,
                        trade.destination_country,
                        trade.cif_amount,
                        trade.currency,
                        trade.wholly_obtained,
                        trade.value_added_pct,
                        str(trade.beneficiary_email) if trade.beneficiary_email else None,
                        trade.settlement_amount,
                        trade.settlement_currency,
                    )
                    if inserted is None:
                        existing = await connection.fetchrow(
                            """
                            select * from public.trade_cases
                            where organization_id = $1 and idempotency_key = $2
                            """,
                            organization_id,
                            idempotency_key,
                        )
                        if existing is None or existing["request_hash"].strip() != request_hash:
                            return False, None
                        return False, existing
                    await connection.execute(
                        """
                        insert into public.agent_events
                            (organization_id, trade_case_id, stage, event_type, details)
                        values ($1,$2,'observe','trade_received',$3::jsonb)
                        """,
                        organization_id,
                        trade_id,
                        '{"status":"processing"}',
                    )
                    return True, None
            except asyncpg.UniqueViolationError as error:
                raise ValueError("trade reference is already in use") from error

    async def save_document(
        self,
        organization_id: UUID,
        trade_id: UUID,
        media_type: str,
        storage_path: str,
        sha256: str,
    ) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                insert into public.trade_documents
                    (organization_id, trade_case_id, storage_path, media_type, sha256)
                values ($1,$2,$3,$4,$5)
                """,
                organization_id,
                trade_id,
                storage_path,
                media_type,
                sha256,
            )

    async def record_stage(
        self,
        organization_id: UUID,
        trade_id: UUID,
        stage: str,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        import json

        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                insert into public.agent_events
                    (organization_id, trade_case_id, stage, event_type, details)
                values ($1,$2,$3,$4,$5::jsonb)
                """,
                organization_id,
                trade_id,
                stage,
                event_type,
                json.dumps(details, default=str),
            )

    async def record_decision(
        self,
        organization_id: UUID,
        trade_id: UUID,
        hs_code: str,
        confidence: float,
        rationale: str,
        origin_decision: dict[str, Any],
        rigs_score: float | None,
        rigs_components: dict[str, Any],
        rule_id: UUID | None,
        status: str,
        settlement_status: str,
    ) -> None:
        import json

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    update public.trade_cases
                    set hs_code = $3, hs_code_confidence = $4, hs_code_rationale = $5,
                        origin_eligible = $6, origin_rule_id = $7, origin_decision = $8::jsonb,
                        rigs_score = $9, rigs_components = $10::jsonb, status = $11,
                        settlement_status = $12, error_code = null
                    where id = $1 and organization_id = $2
                    """,
                    trade_id,
                    organization_id,
                    hs_code,
                    confidence,
                    rationale,
                    origin_decision["verified"],
                    rule_id,
                    json.dumps(origin_decision, default=str),
                    rigs_score,
                    json.dumps(rigs_components, default=str),
                    status,
                    settlement_status,
                )
                await connection.execute(
                    """
                    insert into public.agent_events
                        (organization_id, trade_case_id, stage, event_type, details)
                    values ($1,$2,'decide','compliance_decision',$3::jsonb)
                    """,
                    organization_id,
                    trade_id,
                    json.dumps(
                        {
                            "origin_verified": origin_decision["verified"],
                            "rigs_score": rigs_score,
                            "status": status,
                        }
                    ),
                )

    async def set_payout(
        self,
        organization_id: UUID,
        trade_id: UUID,
        batch_id: str,
        outcome: str,
    ) -> None:
        import json

        status = {
            "processing": "settlement_pending",
            "completed": "settled",
            "failed": "settlement_failed",
        }[outcome]
        settlement_status = outcome
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    update public.trade_cases
                    set paypal_payout_batch_id = nullif($3, ''), status = $4,
                        settlement_status = $5,
                        settled_at = case when $6 then now() else null end
                    where id = $1 and organization_id = $2
                    """,
                    trade_id,
                    organization_id,
                    batch_id,
                    status,
                    settlement_status,
                    outcome == "completed",
                )
                await connection.execute(
                    """
                    insert into public.agent_events
                        (organization_id, trade_case_id, stage, event_type, details)
                    values ($1,$2,'execute',$3,$4::jsonb)
                    """,
                    organization_id,
                    trade_id,
                    "paypal_payout_created"
                    if outcome == "processing"
                    else f"paypal_payout_{outcome}",
                    json.dumps({"batch_id": batch_id, "outcome": outcome}),
                )

    async def set_payout_started(
        self,
        organization_id: UUID,
        trade_id: UUID,
        sender_batch_id: str,
    ) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                update public.trade_cases
                set paypal_sender_batch_id = $3
                where id = $1 and organization_id = $2
                """,
                trade_id,
                organization_id,
                sender_batch_id,
            )

    async def mark_failed(self, organization_id: UUID, trade_id: UUID, code: str) -> None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                updated = await connection.fetchval(
                    """
                    update public.trade_cases set status = 'review_required', error_code = $3
                    where id = $1 and organization_id = $2 and status = 'processing'
                    returning id
                    """,
                    trade_id,
                    organization_id,
                    code,
                )
                if updated is None:
                    return
                await connection.execute(
                    """
                    insert into public.agent_events
                        (organization_id, trade_case_id, stage, event_type, details)
                    values ($1,$2,'record','processing_failed',$3::jsonb)
                    """,
                    organization_id,
                    trade_id,
                    f'{{"error_code":"{code}"}}',
                )

    async def list_cases(
        self,
        organization_id: UUID,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                with source as (
                    select to_jsonb(trade_case) as data
                    from public.trade_cases as trade_case
                    where trade_case.organization_id = $1
                ),
                normalized as (
                    select
                        (data->>'id')::uuid as id,
                        coalesce(data->>'external_reference', data->>'reference_number')
                            as external_reference,
                        coalesce(data->>'status', 'received') as status,
                        data->>'goods_description' as goods_description,
                        data->>'hs_code' as hs_code,
                        nullif(data->>'hs_code_confidence', '')::numeric as hs_code_confidence,
                        data->>'origin_country' as origin_country,
                        data->>'destination_country' as destination_country,
                        coalesce(
                            nullif(data->>'cif_amount', ''),
                            nullif(data->>'cif_value', ''),
                            '0'
                        )::numeric as cif_amount,
                        nullif(data->>'currency', '') as currency,
                        nullif(data->>'origin_eligible', '')::boolean as origin_eligible,
                        coalesce(data->'origin_decision', '{}'::jsonb) as origin_decision,
                        nullif(data->>'rigs_score', '')::numeric as rigs_score,
                        coalesce(data->'rigs_components', '{}'::jsonb) as rigs_components,
                        coalesce(data->>'settlement_status', 'not_eligible')
                            as settlement_status,
                        data->>'paypal_payout_batch_id' as paypal_payout_batch_id,
                        data->>'error_code' as error_code,
                        nullif(data->>'preferential_margin', '')::numeric as preferential_margin,
                        coalesce(
                            nullif(data->>'created_at', '')::timestamptz,
                            nullif(data->>'updated_at', '')::timestamptz,
                            to_timestamp(0)
                        ) as created_at,
                        coalesce(
                            nullif(data->>'updated_at', '')::timestamptz,
                            nullif(data->>'created_at', '')::timestamptz,
                            to_timestamp(0)
                        ) as updated_at
                    from source
                )
                select *
                from normalized
                where $2::timestamptz is null or (created_at, id) < ($2, $3)
                order by created_at desc, id desc
                limit $4
                """,
                organization_id,
                before[0] if before else None,
                before[1] if before else None,
                limit + 1,
            )

    async def list_case_by_id(self, trade_id: UUID, organization_id: UUID) -> Record | None:
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(
                """
                select * from public.trade_cases where id = $1 and organization_id = $2
                """,
                trade_id,
                organization_id,
            )

    async def historical_scores(
        self,
        organization_id: UUID,
        beneficiary_email: str | None,
        currency: str,
        origin_country: str,
        destination_country: str,
    ) -> tuple[float | None, float | None]:
        async with self.pool.acquire() as connection:
            growth = await connection.fetchrow(
                """
                select
                  count(*) filter (
                    where settled_at >= now() - interval '90 days'
                  ) as recent_count,
                  coalesce(sum(cif_amount) filter (
                    where settled_at >= now() - interval '90 days'
                  ), 0) as recent_volume,
                  count(*) filter (
                    where settled_at >= now() - interval '180 days'
                      and settled_at < now() - interval '90 days'
                  ) as previous_count,
                  coalesce(sum(cif_amount) filter (
                    where settled_at >= now() - interval '180 days'
                      and settled_at < now() - interval '90 days'
                  ), 0) as previous_volume
                from public.trade_cases
                where organization_id = $1 and currency = $2
                  and origin_country = $3 and destination_country = $4
                  and settlement_status = 'completed'
                  and settled_at is not null
                  and settled_at >= now() - interval '180 days'
                """,
                organization_id,
                currency,
                origin_country,
                destination_country,
            )
            stakeholder = None
            if beneficiary_email is not None:
                history = await connection.fetchrow(
                    """
                    select count(*) as attempts,
                           count(*) filter (where settlement_status = 'completed') as successes
                    from public.trade_cases
                    where organization_id = $1 and lower(beneficiary_email) = lower($2)
                      and settlement_status in ('completed', 'failed')
                    """,
                    organization_id,
                    beneficiary_email,
                )
                if history["attempts"] >= 3:
                    stakeholder = history["successes"] / history["attempts"]

        growth_score = None
        if growth["recent_count"] >= 3 and growth["previous_count"] >= 3:
            total = float(growth["recent_volume"] + growth["previous_volume"])
            if total > 0:
                growth_score = float(growth["recent_volume"]) / total
        return growth_score, stakeholder

    async def is_verified_beneficiary(
        self,
        organization_id: UUID,
        email: str,
    ) -> bool:
        async with self.pool.acquire() as connection:
            return await connection.fetchval(
                """
                select exists (
                    select 1
                    from public.trusted_beneficiaries
                    where organization_id = $1
                      and lower(email) = lower($2)
                      and revoked_at is null
                )
                """,
                organization_id,
                email,
            )

    async def record_webhook(
        self,
        provider: str,
        event_id: str,
        payload: dict[str, object],
        payload_hash: str,
    ) -> bool:
        async with self.pool.acquire() as connection:
            inserted = await connection.fetchval(
                """
                insert into public.webhook_events
                    (provider, event_id, payload, signature_verified, payload_sha256)
                values ($1,$2,$3::jsonb,true,$4)
                on conflict (provider, event_id) do update
                    set signature_verified = true
                    where webhook_events.processed_at is null
                      and webhook_events.payload_sha256 = excluded.payload_sha256
                returning id
                """,
                provider,
                event_id,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                payload_hash,
            )
            if inserted is None:
                existing_hash = await connection.fetchval(
                    """
                    select payload_sha256 from public.webhook_events
                    where provider = $1 and event_id = $2
                    """,
                    provider,
                    event_id,
                )
                if existing_hash is None:
                    raise RuntimeError("webhook event disappeared during deduplication")
                if existing_hash.strip() != payload_hash:
                    raise ValueError("webhook event id was reused with a different payload")
        return inserted is not None

    async def finish_webhook(self, provider: str, event_id: str) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                update public.webhook_events set processed_at = now()
                where provider = $1 and event_id = $2
                """,
                provider,
                event_id,
            )

    async def apply_paypal_payout_event(
        self,
        event_id: str,
        batch_id: str | None,
        sender_batch_id: str | None,
        trade_id: UUID | None,
        outcome: str,
    ) -> None:
        status = {
            "processing": "settlement_pending",
            "completed": "settled",
            "failed": "settlement_failed",
        }[outcome]
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                case = await connection.fetchrow(
                    """
                    update public.trade_cases
                    set status = $2, settlement_status = $3,
                        settled_at = case when $3 = 'completed' then now() else null end,
                        paypal_payout_batch_id = coalesce(paypal_payout_batch_id, $1)
                    where ($1 is not null and paypal_payout_batch_id = $1)
                       or ($4 is not null and paypal_sender_batch_id = $4)
                       or ($5 is not null and id = $5)
                    returning id, organization_id
                    """,
                    batch_id,
                    status,
                    outcome,
                    sender_batch_id,
                    trade_id,
                )
                if case:
                    await connection.execute(
                        """
                        insert into public.agent_events
                            (organization_id, trade_case_id, stage, event_type, details)
                        values ($1,$2,'record','paypal_webhook_processed',$3::jsonb)
                        """,
                        case["organization_id"],
                        case["id"],
                        json.dumps(
                            {"event_id": event_id, "outcome": outcome, "batch_id": batch_id}
                        ),
                    )
