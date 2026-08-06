"""Nilvera integration errors."""

import json
import re
from typing import Any

from core.integrations.errors import IntegrationError

_SAFE_VALIDATION_ISSUE_MAX_LENGTH = 160
_SAFE_VALIDATION_ISSUE_PATTERN = re.compile(r"^FIELD=[A-Za-z0-9_.]+;REASON=[A-Z0-9_]+$")
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
    normalized = "".join(character for character in content.lower() if character.isalnum())
    for alias in sorted(_VALIDATION_FIELD_ALIASES, key=len, reverse=True):
        if alias in normalized:
            return _VALIDATION_FIELD_ALIASES[alias]
    return "UNKNOWN"


def _validation_reason(content: str, field: str) -> str:
    lowered = content.casefold()
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
        combined_validation_issue = normalize_validation_issue(provider_message, description, detail)

        self.sanitized_description: str | None = None
        if description:
            self.sanitized_description = combined_validation_issue

        self.sanitized_detail: str | None = None
        if detail:
            self.sanitized_detail = combined_validation_issue

        normalized_issues = [
            issue
            for issue in (validation_issues or ())
            if isinstance(issue, str)
            and len(issue) <= _SAFE_VALIDATION_ISSUE_MAX_LENGTH
            and _SAFE_VALIDATION_ISSUE_PATTERN.fullmatch(issue) is not None
        ]
        if not normalized_issues and any((provider_message, description, detail)):
            normalized_issues.append(combined_validation_issue)
        self.safe_validation_issues = tuple(dict.fromkeys(normalized_issues))[:5]

        self.sanitized_preview: str | None = None
        if raw_response is not None:
            self.sanitized_preview = self._create_sanitized_preview(raw_response)
            self.sanitized_context["preview"] = self.sanitized_preview

    def _create_sanitized_preview(self, raw_response: str | dict[str, Any]) -> str:
        """Create a bounded, safe preview of the response."""
        if isinstance(raw_response, dict):
            try:
                # remove sensitive keys if any
                safe_dict = {k: v for k, v in raw_response.items() if k.lower() not in ["authorization", "apikey", "vkn", "tckn", "password"]}
                content = json.dumps(safe_dict)
            except Exception:
                content = str(raw_response)
        else:
            content = str(raw_response)

        # Hard redaction of common sensitive patterns
        content_lower = content.lower()
        if "authorization" in content_lower or "api_key" in content_lower or "bearer" in content_lower or "password" in content_lower:
            content = "[REDACTED_POTENTIAL_SECRETS]"

        # Redact VKN/TCKN-like values or any 10+ digit number in the string
        content = re.sub(r'(?i)(vkn|tckn)["\'\s:=]+([0-9]{10,11})', r'\1: [REDACTED]', content)
        content = re.sub(r'\b\d{10,}\b', '[REDACTED_NUM]', content)

        # Redact emails
        content = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '[REDACTED_EMAIL]', content)

        return content[:512]

    def __str__(self) -> str:
        parts = []
        if self.http_status:
            parts.append(f"HTTP {self.http_status}")
        if self.provider_code:
            parts.append(f"Code {self.provider_code}")
        if self.correlation_id:
            parts.append(f"CorrID {self.correlation_id}")
        ctx = f" [{', '.join(parts)}]" if parts else ""
        return f"{self.message}{ctx}"

    def __repr__(self) -> str:
        # Prevent any automatic exposure of detail, description, or sanitized_preview
        return f"{self.__class__.__name__}('{self.message}')"


class NilveraValidationError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "VALIDATION")
        kwargs.setdefault("safe_code", "NILVERA_VALIDATION_FAILED")
        super().__init__(message, **kwargs)


class NilveraAuthError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "AUTHENTICATION")
        kwargs.setdefault("safe_code", "NILVERA_AUTH_FAILED")
        super().__init__(message, **kwargs)


class NilveraNotFoundError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "NOT_FOUND")
        kwargs.setdefault("safe_code", "NILVERA_NOT_FOUND")
        super().__init__(message, **kwargs)


class NilveraDuplicateError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "DUPLICATE")
        kwargs.setdefault("safe_code", "NILVERA_DUPLICATE")
        super().__init__(message, **kwargs)


class NilveraBusinessRuleError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "BUSINESS_RULE")
        kwargs.setdefault("safe_code", "NILVERA_BUSINESS_RULE")
        super().__init__(message, **kwargs)


class NilveraRateLimitError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "RATE_LIMIT")
        kwargs.setdefault("safe_code", "NILVERA_RATE_LIMIT")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class NilveraServerError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "PROVIDER_UNAVAILABLE")
        kwargs.setdefault("safe_code", "NILVERA_SERVER_ERROR")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class NilveraTimeoutError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "TIMEOUT")
        kwargs.setdefault("safe_code", "NILVERA_TIMEOUT")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class NilveraResponseSizeError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "INVALID_PROVIDER_RESPONSE")
        kwargs.setdefault("safe_code", "NILVERA_RESPONSE_TOO_LARGE")
        super().__init__(message, **kwargs)
