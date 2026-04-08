"""Pydantic models for complaint classification output."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ProductCategory(str, Enum):
    CREDIT_REPORTING = "credit_reporting"
    DEBT_COLLECTION = "debt_collection"
    MORTGAGE = "mortgage"
    CREDIT_CARD = "credit_card"
    CHECKING_SAVINGS = "checking_savings"
    STUDENT_LOAN = "student_loan"
    VEHICLE_LOAN = "vehicle_loan"
    PAYDAY_LOAN = "payday_loan"
    MONEY_TRANSFER = "money_transfer"
    PREPAID_CARD = "prepaid_card"
    OTHER = "other"


class IssueType(str, Enum):
    INCORRECT_INFO = "incorrect_information"
    COMMUNICATION_TACTICS = "communication_tactics"
    ACCOUNT_MANAGEMENT = "account_management"
    BILLING_DISPUTES = "billing_disputes"
    FRAUD_SCAM = "fraud_or_scam"
    LOAN_MODIFICATION = "loan_modification"
    PAYMENT_PROCESSING = "payment_processing"
    DISCLOSURE_TRANSPARENCY = "disclosure_transparency"
    CLOSING_CANCELLING = "closing_or_cancelling"
    OTHER = "other"


class ClassificationResult(BaseModel):
    """Structured output produced by the classification agent."""

    product_category: ProductCategory
    issue_type: IssueType
    sub_issue: Optional[str] = None
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Model confidence score"
    )
    reasoning: str = Field(
        ..., description="Brief chain‑of‑thought justification"
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Key phrases extracted from the narrative",
    )
    review_recommended: bool = Field(
        default=False,
        description="True if downstream QA or human review is advised",
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description="Machine-readable tags for audit (e.g. narrative_missing)",
    )
    alternate_candidates: list[dict] = Field(
        default_factory=list,
        description="Optional runner-up label hypotheses for reconciliation",
    )

    @field_validator("reason_codes", mode="before")
    @classmethod
    def _reason_codes_as_list(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

    @field_validator("keywords", mode="before")
    @classmethod
    def _keywords_as_list(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            for sep in (";", ","):
                if sep in s:
                    return [p.strip() for p in s.split(sep) if p.strip()]
            return [s]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

    @field_validator("alternate_candidates", mode="before")
    @classmethod
    def _alternate_candidates_as_list(cls, v: object) -> list[dict]:
        if v is None:
            return []
        if isinstance(v, dict):
            return [v]
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
        return []
