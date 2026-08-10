"""Nilvera integration errors."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from core.integrations.errors import IntegrationError

_SAFE_VALIDATION_ISSUE_MAX_LENGTH = 160
_SAFE_VALIDATION_ISSUE_PATTERN = re.compile(r"^FIELD=[A-Za-z0-9_.]+;REASON=[A-Z0-9_]+$")
_SAFE_DETAIL_MAX_LENGTH = 256
_ISO_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SAFE_PROVIDER_CODE_PATTERN = re.compile(r"^[A-Z0-9_.-]{1,64}$", re.IGNORECASE)
_VALIDATION_FIELD_ALIASES = {
    "allowancecharge": "InvoiceLines.AllowanceTotal",
    "allowancetotal": "InvoiceLines.AllowanceTotal",
    "companyinfo": "CompanyInfo",
    "currencycode": "InvoiceInfo.CurrencyCode",
    "customeralias": "CustomerAlias",
    "customerinfo": "CustomerInfo",
    "generalallowancetotal": "InvoiceInfo.GeneralAllowanceTotal",
    "generalkdv1total": "InvoiceInfo.GeneralKDV1Total",
    "generalkdv8total": "InvoiceInfo.GeneralKDV8Total",
    "generalkdv10total": "InvoiceInfo.GeneralKDV10Total",
    "generalkdv18total": "InvoiceInfo.GeneralKDV18Total",
    "generalkdv20total": "InvoiceInfo.GeneralKDV20Total",
    "invoicelines": "InvoiceLines",
    "invoicelinesallowancetotal": "InvoiceLines.AllowanceTotal",
    "invoicelineskdvpercent": "InvoiceLines.KDVPercent",
    "invoicelineskdvtotal": "InvoiceLines.KDVTotal",
    "invoiceprofile": "InvoiceInfo.InvoiceProfile",
    "invoiceserieornumber": "InvoiceInfo.InvoiceSerieOrNumber",
    "invoicetype": "InvoiceInfo.InvoiceType",
    "issuedate": "InvoiceInfo.IssueDate",
    "kdvpercent": "InvoiceLines.KDVPercent",
    "kdvtotal": "InvoiceInfo.KdvTotal",
    "legalmonetarytotal": "LegalMonetaryTotal",
    "lineextensionamount": "InvoiceInfo.LineExtensionAmount",
    "payableamount": "InvoiceInfo.PayableAmount",
    "scenario": "InvoiceInfo.InvoiceProfile",
    "supplier": "CompanyInfo",
    "taxtotal": "InvoiceInfo.KdvTotal",
    "withholdingtax": "WithholdingTaxTotal",
    "withholdingtaxamount": "WithholdingTaxTotal",
    "withholdingtaxtotal": "WithholdingTaxTotal",
}
_TOTAL_FIELDS = {
    "InvoiceInfo.GeneralAllowanceTotal",
    "InvoiceInfo.GeneralKDV1Total",
    "InvoiceInfo.GeneralKDV8Total",
    "InvoiceInfo.GeneralKDV10Total",
    "InvoiceInfo.GeneralKDV18Total",
    "InvoiceInfo.GeneralKDV20Total",
    "InvoiceInfo.KdvTotal",
    "InvoiceInfo.LineExtensionAmount",
    "InvoiceInfo.PayableAmount",
    "InvoiceLines.AllowanceTotal",
    "InvoiceLines.KDVPercent",
    "InvoiceLines.KDVTotal",
    "LegalMonetaryTotal",
    "WithholdingTaxTotal",
}


def _redact_validation_text(value: Any) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    content = str(value)[:2048]
    content = re.sub(
        r"(?i)\b(authorization|api[ _-]?key|bearer|password|secret|token)\b\s*[:=]?\s*[^\s,;]+",
        r"\1 [REDACTED]",
        content,
    )
    content = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,36}\b", "[REDACTED_UUID]", content)
    content = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[REDACTED_EMAIL]", content)
    content = re.sub(r"(?i)\b(vkn|tckn|ettn)\b\s*[:=]?\s*[A-Za-z0-9-]+", r"\1 [REDACTED]", content)
    content = re.sub(r"\b[A-Z]{3}\d{13}\b", "[REDACTED_DOCUMENT]", content)
    return re.sub(r"\b\d{10,}\b", "[REDACTED_NUM]", content)


def _validation_field(content: str) -> str:
    lowered = content.casefold()
    if (
        "tarihleri arasında" in lowered
        or "tarihleri arasinda" in lowered
        or "date must be between" in lowered
        or "dates must be between" in lowered
    ):
        return "InvoiceInfo.IssueDate"
    normalized = "".join(character for character in content.lower() if character.isalnum())
    for alias in sorted(_VALIDATION_FIELD_ALIASES, key=len, reverse=True):
        if alias in normalized:
            return _VALIDATION_FIELD_ALIASES[alias]
    return "UNKNOWN"


def _validation_reason(content: str, field: str) -> str:
    lowered = content.casefold()
    if field == "InvoiceInfo.IssueDate" and (
        "tarihleri arasında" in lowered
        or "tarihleri arasinda" in lowered
        or "date must be between" in lowered
        or "dates must be between" in lowered
    ):
        return "DATE_OUT_OF_RANGE"
    if any(token in lowered for token in ("zorunlu", "required", "missing", "eksik", "boş olamaz", "bos olamaz", "null")):
        return "FIELD_MISSING"
    if any(token in lowered for token in ("uyuşm", "uyusm", "eşleşm", "eslesm", "mismatch", "tutarsız", "tutarsiz")):
        return "TOTAL_MISMATCH" if field in _TOTAL_FIELDS else "VALUE_MISMATCH"
    if any(token in lowered for token in ("format", "geçersiz", "gecersiz", "invalid", "uygun değil", "uygun degil", "enum")):
        return "FORMAT_INVALID"
    if any(token in lowered for token in ("duplicate", "mükerrer", "mukerrer", "zaten mevcut")):
        return "DUPLICATE_VALUE"
    if any(token in lowered for token in ("kayıt başarısız", "kayit basarisiz", "record failed", "could not be saved")):
        return "RECORD_FAILED"
    if any(token in lowered for token in ("iş kural", "is kural", "business rule")):
        return "BUSINESS_RULE_REJECTED"
    return "VALIDATION_REJECTED"


def normalize_validation_issue(*parts: Any) -> str:
    """Reduce provider validation prose to a bounded field/reason classification."""
    content = " ".join(filter(None, (_redact_validation_text(part) for part in parts)))
    field = _validation_field(content)
    reason = _validation_reason(content, field)
    return f"FIELD={field};REASON={reason}"[:_SAFE_VALIDATION_ISSUE_MAX_LENGTH]


def sanitize_provider_detail(*parts: Any) -> str | None:
    """Return bounded actionable validation metadata without provider identifiers."""
    content = " ".join(filter(None, (_redact_validation_text(part) for part in parts)))
    if not content:
        return None

    issue = normalize_validation_issue(content)
    dates: list[str] = []
    for candidate in _ISO_DATE_PATTERN.findall(content):
        try:
            parsed = date.fromisoformat(candidate)
        except ValueError:
            continue
        normalized = parsed.isoformat()
        dates.append(normalized)

    if issue.endswith("REASON=DATE_OUT_OF_RANGE") and len(dates) >= 2:
        issue = f"{issue};WINDOW_START={dates[0]};WINDOW_END={dates[1]}"
    return issue[:_SAFE_DETAIL_MAX_LENGTH]


@dataclass(frozen=True, repr=False)
class NilveraProviderError:
    """Lossless provider validation entry whose representation is always redacted."""

    http_status: int
    code: str | None
    description: str | None
    detail: str | None
    stage: str | None
    retryable: bool
    classification: str
    safe_detail: str | None

    def __repr__(self) -> str:
        return (
            "<NilveraProviderError "
            f"http_status={self.http_status} code_present={self.code is not None} "
            f"classification={self.classification} retryable={self.retryable}>"
        )


class NilveraApiError(IntegrationError):
    """Base exception for Nilvera API errors."""

    def __init__(
        self,
        message: str,
        safe_user_message: str | None = None,
        http_status: int | None = None,
        provider_code: str | None = None,
        description: str | None = None,
        detail: str | None = None,
        provider_message: str | None = None,
        validation_issues: tuple[str, ...] | None = None,
        provider_errors: tuple[NilveraProviderError, ...] | None = None,
        stage: str | None = None,
        classification: str = "UNKNOWN",
        correlation_id: str | None = None,
        retryable: bool = False,
        raw_response: str | dict[str, Any] | None = None,
        category: str = "UNKNOWN",
        safe_code: str = "NILVERA_UNKNOWN_ERROR",
    ):
        safe_msg = safe_user_message or "E-Belge entegratörü ile iletişimde bir sorun oluştu."
        super().__init__(
            safe_user_message=safe_msg,
            category=category,
            safe_code=safe_code,
            retryable=retryable,
            http_status=http_status,
            provider="NILVERA",
            provider_code=provider_code,
            correlation_id=correlation_id,
        )
        self.message = message
        self.stage = stage
        self.classification = classification
        self.provider_message = provider_message

        parsed_errors = tuple(error for error in (provider_errors or ()) if isinstance(error, NilveraProviderError))
        if not parsed_errors and any((provider_code, description, detail)) and http_status is not None:
            parsed_errors = (
                NilveraProviderError(
                    http_status=http_status,
                    code=provider_code,
                    description=description,
                    detail=detail,
                    stage=stage,
                    retryable=retryable,
                    classification=classification,
                    safe_detail=sanitize_provider_detail(provider_message, description, detail),
                ),
            )
        self.provider_errors = parsed_errors

        primary_error = parsed_errors[0] if parsed_errors else None
        primary_description = primary_error.description if primary_error else description
        primary_detail = primary_error.detail if primary_error else detail
        combined_validation_issue = normalize_validation_issue(provider_message, primary_description, primary_detail)

        self.sanitized_description: str | None = None
        if primary_description:
            self.sanitized_description = combined_validation_issue

        self.sanitized_detail: str | None = None
        if primary_detail:
            self.sanitized_detail = sanitize_provider_detail(provider_message, primary_description, primary_detail)

        normalized_issues = [
            issue
            for issue in (validation_issues or ())
            if isinstance(issue, str)
            and len(issue) <= _SAFE_VALIDATION_ISSUE_MAX_LENGTH
            and _SAFE_VALIDATION_ISSUE_PATTERN.fullmatch(issue) is not None
        ]
        if not normalized_issues and any((provider_message, primary_description, primary_detail)):
            normalized_issues.append(combined_validation_issue)
        self.safe_validation_issues = tuple(normalized_issues)

        self.safe_provider_details = tuple(
            error.safe_detail for error in parsed_errors if error.safe_detail is not None
        )
        self.sanitized_context.update(
            {
                "classification": self.classification,
                "retryable": self.retryable,
            }
        )
        if self.stage:
            self.sanitized_context["stage"] = self.stage
        if self.safe_provider_details:
            self.sanitized_context["provider_errors"] = self.safe_provider_details

        self.sanitized_preview: str | None = None
        if raw_response is not None:
            self.sanitized_preview = self._create_sanitized_preview(raw_response)
            self.sanitized_context["preview"] = self.sanitized_preview

    def _create_sanitized_preview(self, raw_response: str | dict[str, Any]) -> str:
        """Never mirror arbitrary provider content into telemetry-compatible context."""
        return "[REDACTED_PROVIDER_RESPONSE]"

    def __str__(self) -> str:
        parts = []
        if self.http_status:
            parts.append(f"HTTP {self.http_status}")
        if isinstance(self.provider_code, str) and _SAFE_PROVIDER_CODE_PATTERN.fullmatch(self.provider_code):
            parts.append(f"Code {self.provider_code}")
        ctx = f" [{', '.join(parts)}]" if parts else ""
        return f"{self.message}{ctx}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} code={self.safe_code} classification={self.classification}>"


class NilveraValidationError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "VALIDATION")
        kwargs.setdefault("safe_code", "NILVERA_VALIDATION_FAILED")
        kwargs.setdefault("classification", "VALIDATION_REJECTED")
        super().__init__(message, **kwargs)


class NilveraAuthError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "AUTHENTICATION")
        kwargs.setdefault("safe_code", "NILVERA_AUTH_FAILED")
        kwargs.setdefault("classification", "AUTH_FAILED")
        super().__init__(message, **kwargs)


class NilveraNotFoundError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "NOT_FOUND")
        kwargs.setdefault("safe_code", "NILVERA_NOT_FOUND")
        kwargs.setdefault("classification", "NOT_FOUND")
        super().__init__(message, **kwargs)


class NilveraDuplicateError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "DUPLICATE")
        kwargs.setdefault("safe_code", "NILVERA_DUPLICATE")
        kwargs.setdefault("classification", "DUPLICATE")
        super().__init__(message, **kwargs)


class NilveraBusinessRuleError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "BUSINESS_RULE")
        kwargs.setdefault("safe_code", "NILVERA_BUSINESS_RULE")
        kwargs.setdefault("classification", "BUSINESS_RULE_REJECTED")
        super().__init__(message, **kwargs)


class NilveraRateLimitError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "RATE_LIMIT")
        kwargs.setdefault("safe_code", "NILVERA_RATE_LIMIT")
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("classification", "RATE_LIMITED")
        super().__init__(message, **kwargs)


class NilveraServerError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "PROVIDER_UNAVAILABLE")
        kwargs.setdefault("safe_code", "NILVERA_SERVER_ERROR")
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("classification", "PROVIDER_ERROR")
        super().__init__(message, **kwargs)


class NilveraTimeoutError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "TIMEOUT")
        kwargs.setdefault("safe_code", "NILVERA_TIMEOUT")
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("classification", "NETWORK_ERROR")
        super().__init__(message, **kwargs)


class NilveraResponseSizeError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "INVALID_PROVIDER_RESPONSE")
        kwargs.setdefault("safe_code", "NILVERA_RESPONSE_TOO_LARGE")
        kwargs.setdefault("classification", "MALFORMED_RESPONSE")
        super().__init__(message, **kwargs)


class NilveraMalformedResponseError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "INVALID_PROVIDER_RESPONSE")
        kwargs.setdefault("safe_code", "NILVERA_MALFORMED_RESPONSE")
        kwargs.setdefault("classification", "MALFORMED_RESPONSE")
        super().__init__(message, **kwargs)


class NilveraNetworkError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "TRANSPORT")
        kwargs.setdefault("safe_code", "NILVERA_NETWORK_ERROR")
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("classification", "NETWORK_ERROR")
        super().__init__(message, **kwargs)
