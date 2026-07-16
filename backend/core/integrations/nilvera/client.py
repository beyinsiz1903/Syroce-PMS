"""Nilvera HTTP client."""

import logging
from typing import Any

import httpx

from .config import get_nilvera_config
from .errors import (
    NilveraApiError,
    NilveraAuthError,
    NilveraBusinessRuleError,
    NilveraDuplicateError,
    NilveraNotFoundError,
    NilveraRateLimitError,
    NilveraResponseSizeError,
    NilveraServerError,
    NilveraTimeoutError,
    NilveraValidationError,
)

logger = logging.getLogger(__name__)


class NilveraHttpClient:
    """HTTP client for Nilvera API."""

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._config = get_nilvera_config()
        self._injected_client = client
        self._owned_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "NilveraHttpClient":
        if self._injected_client is None:
            self._owned_client = httpx.AsyncClient(
                base_url=self._config.base_url, timeout=httpx.Timeout(self._config.timeout_ms / 1000.0)
            )
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
        raise RuntimeError(
            "NilveraHttpClient must be used as an async context manager or instantiated with an open httpx.AsyncClient."
        )

    def _parse_error_response(self, status_code: int, text_content: str, headers: httpx.Headers, correlation_id: str | None) -> NilveraApiError:
        """Safely parse error response without crashing on HTML."""
        data = {}
        if "application/json" in headers.get("Content-Type", "").lower():
            import json
            try:
                data = json.loads(text_content)
            except ValueError:
                pass

        message = data.get("Message", "Unknown error")
        errors = data.get("Errors", [])

        provider_code = None
        description = None
        detail = None
        if errors and isinstance(errors, list) and len(errors) > 0:
            first_err = errors[0]
            if isinstance(first_err, dict):
                provider_code = first_err.get("Code")
                description = first_err.get("Description")
                detail = first_err.get("Detail")

        kwargs = {
            "message": message,
            "http_status": status_code,
            "provider_code": provider_code,
            "description": description,
            "detail": detail,
            "correlation_id": correlation_id,
            "raw_response": data if data else text_content,
        }

        if status_code == 400:
            return NilveraValidationError(**kwargs)
        elif status_code in (401, 403):
            return NilveraAuthError(**kwargs)
        elif status_code == 404:
            return NilveraNotFoundError(**kwargs)
        elif status_code == 409:
            return NilveraDuplicateError(**kwargs)
        elif status_code == 422:
            return NilveraBusinessRuleError(**kwargs)
        elif status_code == 429:
            retry_after = headers.get("Retry-After")
            kwargs["retryable"] = True
            kwargs["detail"] = f"Retry-After: {retry_after}" if retry_after else detail
            return NilveraRateLimitError(**kwargs)
        elif status_code >= 500:
            kwargs["retryable"] = True
            return NilveraServerError(**kwargs)

        return NilveraApiError(**kwargs)

    async def _request(
        self,
        method: str,
        path: str,
        correlation_id: str | None = None,
        retryable: bool | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> httpx.Response | Any:
        client = self._get_active_client()

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
                # If streaming, we must handle reading safely inside the caller,
                # but for simplicity, we do standard request unless stream is requested.
                request_obj = client.build_request(method, path, headers=headers, **kwargs)
                response = await client.send(request_obj, stream=True)

                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self._config.max_response_size_bytes:
                    await response.aclose()
                    raise NilveraResponseSizeError(
                        f"Response size {content_length} exceeds limit", correlation_id=correlation_id
                    )

                if response.is_error:
                    await response.aread()  # safe because it's an error and likely small
                    error_obj = self._parse_error_response(
                        response.status_code, response.text, response.headers, correlation_id
                    )

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
                    # Enforce stream size locally
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > self._config.max_response_size_bytes:
                            await response.aclose()
                            raise NilveraResponseSizeError("Response body exceeded limits while reading", correlation_id=correlation_id)
                    # We emulate a full httpx response for consistency
                    response = httpx.Response(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=bytes(body),
                        request=request_obj,
                    )

                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempts <= max_attempts and is_retryable:
                    delay = (self._config.retry_base_delay_ms / 1000.0) * (2 ** (attempts - 1))
                    await sleeper(delay)
                    continue
                if isinstance(e, httpx.TimeoutException):
                    raise NilveraTimeoutError("Connection timeout while contacting provider", correlation_id=correlation_id) from e
                raise NilveraApiError(f"Network error: {str(e)}", correlation_id=correlation_id, retryable=True) from e

    async def get(self, path: str, correlation_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        response = await self._request("GET", path, correlation_id=correlation_id, stream=False, **kwargs)
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" not in content_type:
            raise NilveraValidationError(f"Expected JSON, got {content_type}", correlation_id=correlation_id)
        import json
        try:
            return json.loads(response.content)
        except ValueError as e:
            raise NilveraApiError("Invalid JSON response from GET request", correlation_id=correlation_id) from e

    async def get_binary(
        self,
        path: str,
        expected_content_types: list[str] | None = None,
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        response = await self._request("GET", path, correlation_id=correlation_id, stream=False, **kwargs)

        content_type = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if expected_content_types and content_type not in [t.lower() for t in expected_content_types]:
            raise NilveraValidationError(f"Unexpected content type: {content_type}", correlation_id=correlation_id)

        content = response.content
        if not content:
            raise NilveraValidationError("Empty binary response", correlation_id=correlation_id)
        return content

    async def post(
        self, path: str, json: dict[str, Any], correlation_id: str | None = None, retryable: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        response = await self._request("POST", path, json=json, correlation_id=correlation_id, retryable=retryable, stream=False, **kwargs)
        import json as json_mod
        try:
            return json_mod.loads(response.content)
        except ValueError as e:
            raise NilveraApiError("Invalid JSON response from POST request", correlation_id=correlation_id) from e

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
