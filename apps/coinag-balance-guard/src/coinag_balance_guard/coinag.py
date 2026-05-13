from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from requests import Response

from .config import CoinagConfig


class CoinagClient:
    def __init__(self, config: CoinagConfig) -> None:
        self.config = config
        self._token: Optional[str] = None
        self._session = requests.Session()

    def fetch_balance(self, cbu: str) -> Decimal:
        body = self._authorized_request(
            "GET",
            f"{self.config.balance_api_base}/SaldoActual",
            params={"cbu": cbu},
        )
        amount = extract_balance_amount(body.get("response", body))
        if amount is None:
            raise RuntimeError("SaldoActual no devolvio un campo Saldo interpretable.")
        return amount

    def transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._authorized_request(
            "POST",
            f"{self.config.transfer_api_base}{self.config.transfer_endpoint}",
            json=payload,
        )

    def _authorized_request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        token = self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"{self.config.auth_scheme} {token}"
        response = self._session.request(
            method,
            url,
            headers=headers,
            timeout=self.config.request_timeout_seconds,
            verify=not self.config.allow_invalid_certs,
            **kwargs,
        )
        self._log_http_exchange(method, url, headers=headers, kwargs=kwargs, response=response)
        if response.status_code == 401:
            self._token = None
            headers["Authorization"] = f"{self.config.auth_scheme} {self._ensure_token()}"
            response = self._session.request(
                method,
                url,
                headers=headers,
                timeout=self.config.request_timeout_seconds,
                verify=not self.config.allow_invalid_certs,
                **kwargs,
            )
            self._log_http_exchange(
                method,
                url,
                headers=headers,
                kwargs=kwargs,
                response=response,
                retry=True,
            )
        response.raise_for_status()
        return response.json()

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        data = {
            "grant_type": "password",
            "username": self.config.username,
            "password": self.config.password,
        }
        if self.config.scope:
            data["scope"] = self.config.scope
        auth = None
        if self.config.client_id and self.config.client_secret:
            auth = (self.config.client_id, self.config.client_secret)
        else:
            if self.config.client_id:
                data["client_id"] = self.config.client_id
            if self.config.client_secret:
                data["client_secret"] = self.config.client_secret
        response = self._session.post(
            self.config.token_url,
            data=data,
            auth=auth,
            timeout=self.config.request_timeout_seconds,
            verify=not self.config.allow_invalid_certs,
        )
        self._log_http_exchange(
            "POST",
            self.config.token_url,
            headers={},
            kwargs={"data": data, "auth": auth},
            response=response,
        )
        response.raise_for_status()
        body = response.json()
        token = body.get("access_token") or body.get("accessToken") or body.get("token")
        if not token:
            raise RuntimeError("Coinag no devolvio access_token.")
        self._token = str(token)
        return self._token

    def _log_http_exchange(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        kwargs: dict[str, Any],
        response: Response,
        retry: bool = False,
    ) -> None:
        if self.config.http_log_path is None:
            return
        append_http_event(
            self.config.http_log_path,
            {
                "event": "http_exchange",
                "retry": retry,
                "method": method,
                "url": sanitize_url(url, kwargs.get("params")),
                "request_headers": sanitize_headers(headers),
                "request_body": sanitize_value(
                    kwargs.get("json") if "json" in kwargs else kwargs.get("data")
                ),
                "response_status": response.status_code,
                "response_headers": sanitize_headers(dict(response.headers)),
                "response_body": sanitize_response_body(response),
            },
        )


def extract_balance_amount(value: Any) -> Optional[Decimal]:
    if isinstance(value, list):
        for item in value:
            amount = extract_balance_amount(item)
            if amount is not None:
                return amount
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() == "saldo":
                return parse_decimal_value(item)
        for item in value.values():
            amount = extract_balance_amount(item)
            if amount is not None:
                return amount
    return None


def parse_decimal_value(value: Any) -> Optional[Decimal]:
    raw = str(value).strip()
    if not raw:
        return None
    filtered = "".join(ch for ch in raw if ch.isdigit() or ch in ",.-")
    if "," in filtered and "." in filtered:
        filtered = filtered.replace(".", "").replace(",", ".")
    elif "," in filtered:
        filtered = filtered.replace(",", ".")
    try:
        return Decimal(filtered)
    except InvalidOperation:
        return None


def append_http_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=True, default=str))
        file.write("\n")


def sanitize_url(url: str, params: Any = None) -> str:
    split = urlsplit(url)
    query_items = parse_qsl(split.query, keep_blank_values=True)
    if isinstance(params, dict):
        query_items.extend((str(key), str(value)) for key, value in params.items())
    sanitized_query = urlencode(
        [(key, sanitize_scalar(key, value)) for key, value in query_items]
    )
    return urlunsplit((split.scheme, split.netloc, split.path, sanitized_query, split.fragment))


def sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            parts = str(value).split(" ", 1)
            sanitized[key] = f"{parts[0]} {mask_value(parts[1], 4)}" if len(parts) == 2 else mask_value(str(value), 4)
        else:
            sanitized[key] = sanitize_scalar(key, value)
    return sanitized


def sanitize_response_body(response: Response) -> Any:
    text = response.text
    if not text:
        return ""
    try:
        return sanitize_value(response.json())
    except ValueError:
        return text[:1000]


def sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): sanitize_value_for_key(str(key), inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    return value


def sanitize_value_for_key(key: str, value: Any) -> Any:
    if is_sensitive_key(key):
        return mask_value(str(value), 4)
    if is_identifier_key(key):
        return mask_value(str(value), 6)
    return sanitize_value(value)


def sanitize_scalar(key: str, value: Any) -> Any:
    if is_sensitive_key(key):
        return mask_value(str(value), 4)
    if is_identifier_key(key):
        return mask_value(str(value), 6)
    return value


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in ("password", "secret", "token", "authorization"))


def is_identifier_key(key: str) -> bool:
    lowered = key.lower()
    return "cbu" in lowered or "cuit" in lowered or "cuil" in lowered


def mask_value(value: str, visible_suffix: int) -> str:
    trimmed = value.strip()
    if len(trimmed) <= visible_suffix:
        return "*" * len(trimmed)
    return f"***{trimmed[-visible_suffix:]}"
