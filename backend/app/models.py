from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$", min_length=2, max_length=2)]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$", min_length=3, max_length=3)]
HsCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6,10}$", min_length=6, max_length=10)]
GoodsDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)
]


class TradeStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    VERIFIED = "verified"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"
    SETTLEMENT_PENDING = "settlement_pending"
    FLAGGED_FOR_REVIEW = "flagged_for_review"
    SETTLED = "settled"
    SETTLEMENT_FAILED = "settlement_failed"


class SettlementStatus(StrEnum):
    NOT_ELIGIBLE = "not_eligible"
    PENDING = "pending"
    PROCESSING = "processing"
    FLAGGED_FOR_REVIEW = "flagged_for_review"
    COMPLETED = "completed"
    FAILED = "failed"


class OriginDecisionStatus(StrEnum):
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    PENDING_AUDIT = "PENDING_AUDIT"


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_type: Literal["application/pdf", "image/jpeg", "image/png"]
    data_base64: str = Field(min_length=1)


class TradeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_reference: str | None = Field(default=None, max_length=200)
    goods_description: GoodsDescription
    invoice_goods_description: GoodsDescription | None = None
    origin_country: CountryCode
    destination_country: CountryCode
    cif_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: CurrencyCode
    wholly_obtained: bool | None = None
    value_added_pct: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    non_originating_tariff_heading: str | None = Field(default=None, pattern=r"^[0-9]{2,6}$")
    beneficiary_email: EmailStr | None = None
    settlement_amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    settlement_currency: CurrencyCode | None = None
    document: DocumentInput | None = None

    @model_validator(mode="after")
    def require_settlement_details(self) -> "TradeCreate":
        if (self.beneficiary_email is None) != (self.settlement_amount is None):
            raise ValueError("beneficiary_email and settlement_amount must be provided together")
        if self.settlement_amount is not None and self.settlement_currency is None:
            raise ValueError("settlement_currency is required when settlement_amount is provided")
        if self.settlement_amount is not None:
            if self.settlement_currency != self.currency:
                raise ValueError("settlement currency must match the trade currency")
            if self.settlement_amount > self.cif_amount:
                raise ValueError("settlement amount cannot exceed the documented CIF amount")
        return self


class N8nTradeTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    organization_id: UUID
    trade: TradeCreate


class OriginDecision(BaseModel):
    status: OriginDecisionStatus
    verified: bool
    rule_id: UUID | None = None
    agreement: str | None = None
    reason: str
    confidence: float = Field(ge=0, le=1)
    evaluated_at: datetime


class RigsComponents(BaseModel):
    risk: float | None = Field(default=None, ge=0, le=1)
    intent: float | None = Field(default=None, ge=0, le=1)
    growth: float | None = Field(default=None, ge=0, le=1)
    stakeholder: float | None = Field(default=None, ge=0, le=1)
    missing_evidence: list[str] = Field(default_factory=list)


class TradeResult(BaseModel):
    id: UUID
    external_reference: str | None
    status: TradeStatus
    goods_description: str
    hs_code: str | None
    hs_code_confidence: float | None
    origin_country: str
    destination_country: str
    cif_amount: Decimal
    currency: str | None
    origin_eligible: bool | None
    origin_decision: dict[str, object]
    rigs_score: float | None
    rigs_components: dict[str, object]
    settlement_status: SettlementStatus
    paypal_payout_batch_id: str | None
    error_code: str | None
    preferential_margin: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class TradePage(BaseModel):
    items: list[TradeResult]
    next_cursor: str | None


class TelemetryCase(BaseModel):
    trade_reference: str
    goods: str
    route: str
    hs_code: str | None
    cif_value: float
    duty_exemption: float
    rigs_score: float | None
    settlement: str
    status: str


class TradeTelemetry(BaseModel):
    trade_cases: list[TelemetryCase]
    trade_cases_count: int
    preferential_origin: int
    active_settlements: int
    avg_rigs: float


class TariffRule(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    agreement: str
    hs_code_prefix: str
    origin_country: str
    destination_country: str
    rule_type: Literal[
        "wholly_obtained",
        "value_added",
        "change_in_tariff_classification",
        "specific_process",
        "alternative",
    ]
    minimum_value_added_pct: Decimal | None
    required_tariff_heading_prefix: str | None
    excluded_inputs: list[dict[str, object]]
    effective_from: date
    effective_to: date | None
