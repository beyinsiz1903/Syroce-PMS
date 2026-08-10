"""Nilvera HTTP client."""

from typing import Any

import httpx

from .config import get_nilvera_config
from .errors import (
    NilveraApiError,
    NilveraAuthError,
    NilveraDuplicateError,
    NilveraMalformedResponseError,
    NilveraNetworkError,
    NilveraNotFoundError,
    NilveraProviderError,
    NilveraRateLimitError,
    NilveraResponseSizeError,
    NilveraServerError,
    NilveraTimeoutError,
    NilveraValidationError,
    normalize_validation_issue,
    sanitize_provider_detail,
)


class NilveraHttpClient:
    """HTTP client for Nilvera API."""

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._config = get_nilvera_config()
        self._injected_client = client
        self._owned_client: httpx.AsyncClient | None = None
        self._last_http_status: int | None = None

    @property
    def last_http_status(self) -> int | None:
        """Expose only the latest status code for safe E2E diagnostics."""
        return self._last_http_status

    async def __aenter__(self) -> "NilveraHttpClient":
        if self._injected_client is None:
            self._owned_client = httpx.AsyncClient(base_url=self._config.base_url, timeout=httpx.Timeout(self._config.timeout_ms / 1000.0))
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    def _get_active_client(self) -> httpx.AsyncClient:
        if self._injected_client and not self._injected_client.is_closed:
            return self._injected_client
        if self._owned_client and not self._owned_client.is_closed:
            return self._owned_client
        raise RuntimeError("NilveraHttpClient must be used as an async context manager or instantiated with an open httpx.AsyncClient.")

    def _parse_error_response(
        self,
        status_code: int,
        text_content: str,
        headers: httpx.Headers,
        correlation_id: str | None,
        stage: str | None,
    ) -> NilveraApiError:
        """Safely parse error response without crashing on HTML."""
        data: dict[str, Any] = {}
        content_type = headers.get("Content-Type", "").lower().split(";", 1)[0].strip()
        if content_type == "application/json" or (content_type.startswith("application/") and content_type.endswith("+json")):
            import json

            try:
                parsed = json.loads(text_content)
                if isinstance(parsed, dict):
                    data = parsed
            except ValueError:
                pass

        errors = data.get("Errors", [])

        provider_message = data.get("Message") if isinstance(data.get("Message"), str) else None
        validation_issues: list[str] = []
        parsed_entries: list[tuple[str | None, str | None, str | None]] = []
        if isinstance(errors, list):
            for error in errors:
                if not isinstance(error, dict):
                    continue
                error_description = error.get("Description") if isinstance(error.get("Description"), str) else None
                error_detail = error.get("Detail") if isinstance(error.get("Detail"), str) else None
                raw_provider_code = error.get("Code")
                error_code = None
                if isinstance(raw_provider_code, (str, int)) and not isinstance(raw_provider_code, bool):
                    normalized_provider_code = str(raw_provider_code).strip()
                    error_code = normalized_provider_code or None
                parsed_entries.append((error_code, error_description, error_detail))
                validation_issues.append(normalize_validation_issue(provider_message, error_description, error_detail))
        if not validation_issues and provider_message:
            validation_issues.append(normalize_validation_issue(provider_message))

        error_class: type[NilveraApiError] = NilveraApiError
        classification = "UNKNOWN"
        retryable = False
        if status_code in (400, 422):
            error_class = NilveraValidationError
            classification = "VALIDATION_REJECTED"
        elif status_code in (401, 403):
            error_class = NilveraAuthError
            classification = "AUTH_FAILED"
        elif status_code == 404:
            error_class = NilveraNotFoundError
            classification = "NOT_FOUND"
        elif status_code == 409:
            error_class = NilveraDuplicateError
            classification = "DUPLICATE"
        elif status_code == 429:
            error_class = NilveraRateLimitError
            classification = "RATE_LIMITED"
            retryable = True
        elif status_code >= 500:
            error_class = NilveraServerError
            classification = "PROVIDER_ERROR"
            retryable = True

        provider_errors = tuple(
            NilveraProviderError(
                http_status=status_code,
                code=code,
                description=description,
                detail=detail,
                stage=stage,
                retryable=retryable,
                classification=classification,
                safe_detail=sanitize_provider_detail(
                    provider_message,
                    description,
                    detail,
                ),
            )
            for code, description, detail in parsed_entries
        )
        provider_code = provider_errors[0].code if provider_errors else None
        description = provider_errors[0].description if provider_errors else None
        detail = provider_errors[0].detail if provider_errors else None

        kwargs = {
            "message": "Nilvera provider request failed",
            "http_status": status_code,
            "provider_code": provider_code,
            "description": description,
            "detail": detail,
            "provider_message": provider_message,
            "validation_issues": tuple(dict.fromkeys(validation_issues)),
            "provider_errors": provider_errors,
            "stage": stage,
            "classification": classification,
            "correlation_id": correlation_id,
            "retryable": retryable,
        }
        return error_class(**kwargs)

    async def _read_bounded_response(self, response: httpx.Response, max_bytes: int, correlation_id: str | None) -> bytes:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            await response.aclose()
            raise NilveraResponseSizeError(f"Response size {content_length} exceeds limit", correlation_id=correlation_id)

        body = bytearray()
        try:
            async for chunk in response.aiter_bytes(chunk_size=8192):
                body.extend(chunk)
                if len(body) > max_bytes:
                    await response.aclose()
                    raise NilveraResponseSizeError("Response body exceeded limits while reading", correlation_id=correlation_id)
        except Exception:
            await response.aclose()
            raise
        return bytes(body)

    async def _request(
        self,
        method: str,
        path: str,
        correlation_id: str | None = None,
        retryable: bool | None = None,
        stream: bool = False,
        stage: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response | Any:
        client = self._get_active_client()
        self._last_http_status = None

        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._api_key}"
        if "json" in kwargs and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

        # Default retry behavior: GET is retryable, others are not unless explicitly stated
        is_retryable = retryable if retryable is not None else (method.upper() == "GET")
        max_attempts = self._config.retry_max if is_retryable else 0
        attempts = 0

        import asyncio

        sleeper = kwargs.pop("_sleeper", asyncio.sleep)

        while True:
            attempts += 1
            try:
                request_obj = client.build_request(method, path, headers=headers, **kwargs)
                response = await client.send(request_obj, stream=True)
                self._last_http_status = response.status_code

                if response.is_error:
                    try:
                        body_bytes = await self._read_bounded_response(response, self._config.max_response_size_bytes, correlation_id)
                        text_content = body_bytes.decode("utf-8", errors="replace")
                    finally:
                        await response.aclose()

                    error_obj = self._parse_error_response(response.status_code, text_content, response.headers, correlation_id, stage)

                    if isinstance(error_obj, NilveraRateLimitError) and is_retryable and attempts <= max_attempts:
                        retry_after = response.headers.get("Retry-After")
                        delay = int(retry_after) if retry_after and retry_after.isdigit() else self._config.retry_base_delay_ms / 1000.0
                        delay = min(delay, 10.0)
                        await sleeper(delay)
                        continue

                    if error_obj.retryable and is_retryable and attempts <= max_attempts:
                        delay = (self._config.retry_base_delay_ms / 1000.0) * (2 ** (attempts - 1))
                        await sleeper(delay)
                        continue

                    raise error_obj

                if not stream:
                    try:
                        body_bytes = await self._read_bounded_response(response, self._config.max_response_size_bytes, correlation_id)
                    finally:
                        await response.aclose()

                    response = httpx.Response(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=body_bytes,
                        request=request_obj,
                    )

                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempts <= max_attempts and is_retryable:
                    delay = (self._config.retry_base_delay_ms / 1000.0) * (2 ** (attempts - 1))
                    await sleeper(delay)
                    continue
                if isinstance(e, httpx.TimeoutException):
                    raise NilveraTimeoutError("Connection timeout while contacting provider", correlation_id=correlation_id, stage=stage) from e
                raise NilveraNetworkError("Network error while contacting provider", correlation_id=correlation_id, stage=stage) from e

    async def get(
        self,
        path: str,
        correlation_id: str | None = None,
        retryable: bool | None = None,
        stage: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = await self._request("GET", path, correlation_id=correlation_id, retryable=retryable, stream=False, stage=stage, **kwargs)
        content_type = response.headers.get("Content-Type", "").lower()
        ct = content_type.split(";")[0].strip()
        if ct != "application/json" and not (ct.startswith("application/") and ct.endswith("+json")):
            raise NilveraMalformedResponseError(
                f"Expected JSON, got {content_type}",
                correlation_id=correlation_id,
                http_status=response.status_code,
                stage=stage,
            )
        import json

        try:
            return json.loads(response.content)
        except ValueError as e:
            raise NilveraMalformedResponseError(
                "Invalid JSON response from GET request",
                correlation_id=correlation_id,
                http_status=response.status_code,
                stage=stage,
            ) from e

    async def get_binary(
        self,
        path: str,
        expected_content_types: list[str] | None = None,
        correlation_id: str | None = None,
        retryable: bool | None = None,
        **kwargs: Any,
    ) -> tuple[bytes, str]:
        response = await self._request("GET", path, correlation_id=correlation_id, retryable=retryable, stream=False, **kwargs)

        content_type = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if expected_content_types and content_type not in [t.lower() for t in expected_content_types]:
            raise NilveraValidationError(f"Unexpected content type: {content_type}", correlation_id=correlation_id)

        content = response.content
        if not content:
            raise NilveraValidationError("Empty binary response", correlation_id=correlation_id)
        return content, content_type

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        retryable: bool = False,
        stage: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        request_kwargs: dict[str, Any] = dict(kwargs)
        if json is not None:
            request_kwargs["json"] = json
        response = await self._request(
            "POST",
            path,
            correlation_id=correlation_id,
            retryable=retryable,
            stream=False,
            stage=stage,
            **request_kwargs,
        )
        import json as json_mod

        try:
            return json_mod.loads(response.content)
        except ValueError as e:
            raise NilveraMalformedResponseError(
                "Invalid JSON response from POST request",
                correlation_id=correlation_id,
                http_status=response.status_code,
                stage=stage,
            ) from e

    async def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        retryable: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = await self._request("PUT", path, json=json, correlation_id=correlation_id, retryable=retryable, stream=False, **kwargs)
        import json as json_mod

        try:
            return json_mod.loads(response.content)
        except ValueError as e:
            raise NilveraApiError("Invalid JSON response from PUT request", correlation_id=correlation_id) from e
