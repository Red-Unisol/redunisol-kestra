#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import requests

try:
    from kestra import Kestra
except ImportError:  # pragma: no cover - optional outside Kestra
    Kestra = None


APP_TOKEN_ENV = "BITRIX24_APP_TOKEN"
BITRIX_BASE_URL_ENV = "BITRIX24_BASE_URL"
BITRIX_WEBHOOK_PATH_ENV = "BITRIX24_WEBHOOK_PATH"
BITRIX_TIMEOUT_ENV = "BITRIX24_TIMEOUT_SECONDS"
EDNA_API_KEY_ENV = "EDNA_API_KEY"

TARGET_STAGE_ID = "C11:PREPARATION"
TARGET_CATEGORY_ID = "11"

PROMISE_DATE_FIELD = "UF_CRM_1724427951"
PROMISE_AMOUNT_FIELD = "UF_CRM_1724429048"

PROMISE_SEND_HOUR = 9
PROMISE_SEND_MINUTE = 0

BUSINESS_START_HOUR = 9
BUSINESS_START_MINUTE = 0
BUSINESS_END_HOUR = 17
BUSINESS_END_MINUTE = 0

LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

EDNA_URL = "https://app.edna.io/api/v1/out-messages/whatsapp/template"
EDNA_SENDER = "5493513105768_WA"
EDNA_TEMPLATE_ID = 51764


def main() -> int:
    try:
        payload = _load_trigger_body()
        result = process_webhook(payload)
    except Exception as exc:
        result = {
            "ok": False,
            "action": "error",
            "reason": "exception",
            "message": str(exc),
            "scheduled_for": "",
            "deal_id": "",
            "edna_status": "",
        }

    _emit_outputs_if_available(result)
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    return 0


def process_webhook(payload: Any) -> Dict[str, Any]:
    form = _normalize_payload(payload)
    app_token = _get_value(form, "auth[application_token]", ("auth", "application_token"))
    expected_token = _require_env(APP_TOKEN_ENV)

    if app_token != expected_token:
        return _result(ok=False, action="invalid_token", reason="invalid_token")

    event = _get_value(form, "event", ("event",))
    if event != "ONCRMDEALUPDATE":
        return _result(ok=True, action="ignored", reason="event_not_deal_update")

    deal_id = _get_value(form, "data[FIELDS][ID]", ("data", "FIELDS", "ID"))
    if not deal_id:
        return _result(ok=False, action="error", reason="missing_deal_id")

    deal_data, contact_data = fetch_deal_with_contact(str(deal_id))

    stage_id = str(deal_data.get("STAGE_ID") or "")
    category_id = str(deal_data.get("CATEGORY_ID") or "")
    prev_stage_id = (
        _get_value(form, "data[PREVIOUS][STAGE_ID]", ("data", "PREVIOUS", "STAGE_ID"))
        or str(deal_data.get("PREVIOUS_STAGE_ID") or "")
    )

    if not _is_entering_target_stage(stage_id, category_id, prev_stage_id):
        return _result(ok=True, action="ignored", reason="stage_not_target")

    promise_value = str(deal_data.get(PROMISE_DATE_FIELD) or "")
    target_dt = parse_promise_datetime(promise_value)
    if not target_dt:
        return _result(ok=True, action="ignored", reason="invalid_promise_date")

    target_dt = adjust_to_business_hours(target_dt)
    send_info = _wait_and_send(str(deal_id), promise_value, target_dt)
    return _result(
        ok=send_info["ok"],
        action=send_info["action"],
        reason=send_info["reason"],
        scheduled_for=send_info["scheduled_for"],
        deal_id=str(deal_id),
        edna_status=send_info["edna_status"],
    )


def _wait_and_send(deal_id: str, expected_promise_value: str, target_dt: datetime) -> Dict[str, str]:
    now = datetime.now(LOCAL_TZ)
    scheduled_for = target_dt
    delay_seconds = (scheduled_for - now).total_seconds()

    start = dtime(BUSINESS_START_HOUR, BUSINESS_START_MINUTE)
    end = dtime(BUSINESS_END_HOUR, BUSINESS_END_MINUTE)

    if delay_seconds <= 0:
        if start <= now.time() <= end:
            return _send_if_still_valid(deal_id, expected_promise_value, scheduled_for)

        scheduled_for = adjust_to_business_hours(now)
        delay_seconds = (scheduled_for - now).total_seconds()

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    return _send_if_still_valid(deal_id, expected_promise_value, scheduled_for)


def _send_if_still_valid(deal_id: str, expected_promise_value: str, scheduled_for: datetime) -> Dict[str, str]:
    deal_data, contact_data = fetch_deal_with_contact(deal_id)
    if not should_send(deal_data, expected_promise_value):
        return {
            "ok": True,
            "action": "skipped",
            "reason": "stale_deal",
            "scheduled_for": scheduled_for.isoformat(),
            "edna_status": "",
        }

    status = send_to_edna(deal_data, contact_data)
    return {
        "ok": True,
        "action": "sent",
        "reason": "sent",
        "scheduled_for": scheduled_for.isoformat(),
        "edna_status": str(status),
    }


def _is_entering_target_stage(stage_id: str, category_id: str, prev_stage_id: str) -> bool:
    if stage_id != TARGET_STAGE_ID:
        return False
    if category_id != TARGET_CATEGORY_ID:
        return False
    if prev_stage_id == TARGET_STAGE_ID:
        return False
    return True


def bitrix_call(method: str, params: dict[str, Any]) -> Dict[str, Any]:
    base_url = _require_env(BITRIX_BASE_URL_ENV).rstrip("/")
    webhook_path = _require_env(BITRIX_WEBHOOK_PATH_ENV).strip("/")
    url = f"{base_url}/{webhook_path}/{method}.json"
    timeout = _get_timeout_seconds()

    response = requests.post(url, json=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        description = data.get("error_description") or f"Bitrix24 error on {method}."
        raise RuntimeError(description)

    return data.get("result", {})


def fetch_deal_with_contact(deal_id: str) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
    deal = bitrix_call("crm.deal.get", {"ID": deal_id})
    contact_data = None
    contact_id = deal.get("CONTACT_ID")
    if contact_id and str(contact_id) != "0":
        try:
            contact_data = bitrix_call("crm.contact.get", {"ID": contact_id})
        except Exception:
            contact_data = None
    return deal, contact_data


def should_send(deal_data: Dict[str, Any], expected_promise_value: str) -> bool:
    if not deal_data:
        return False
    if str(deal_data.get("STAGE_ID") or "") != TARGET_STAGE_ID:
        return False
    if str(deal_data.get("CATEGORY_ID") or "") != TARGET_CATEGORY_ID:
        return False
    current_promise = str(deal_data.get(PROMISE_DATE_FIELD) or "")
    return current_promise == (expected_promise_value or "")


def send_to_edna(deal: Dict[str, Any], contact_data: Dict[str, Any] | None) -> int:
    contact_name = extract_contact_name(contact_data) or "cliente"
    contact_phone = extract_contact_phone(contact_data)
    if not contact_phone:
        raise ValueError("Missing contact phone.")

    amount_raw = deal.get(PROMISE_AMOUNT_FIELD) or deal.get("OPPORTUNITY")
    amount_text = format_amount(amount_raw) or "0"

    payload = {
        "messageId": f"promesa-{deal.get('ID')}-{int(time.time())}",
        "sender": EDNA_SENDER,
        "phone": contact_phone,
        "templateId": EDNA_TEMPLATE_ID,
        "textVariables": [contact_name, amount_text],
        "options": {"comment": "promesa cobranzas"},
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": _require_env(EDNA_API_KEY_ENV),
    }

    response = requests.post(EDNA_URL, json=payload, headers=headers, timeout=15)
    response.raise_for_status()
    return response.status_code


def parse_promise_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    formats = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is not None:
                return dt.astimezone(LOCAL_TZ)
            if fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                return datetime.combine(
                    dt.date(),
                    dtime(PROMISE_SEND_HOUR, PROMISE_SEND_MINUTE),
                    tzinfo=LOCAL_TZ,
                )
            return dt.replace(tzinfo=LOCAL_TZ)
        except ValueError:
            continue

    return None


def adjust_to_business_hours(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)

    start = dtime(BUSINESS_START_HOUR, BUSINESS_START_MINUTE)
    end = dtime(BUSINESS_END_HOUR, BUSINESS_END_MINUTE)

    if dt.time() < start:
        return dt.replace(
            hour=BUSINESS_START_HOUR,
            minute=BUSINESS_START_MINUTE,
            second=0,
            microsecond=0,
        )
    if dt.time() > end:
        next_day = dt.date() + timedelta(days=1)
        return datetime.combine(next_day, start, tzinfo=LOCAL_TZ)
    return dt


def normalize_phone(value: Any) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    return digits.lstrip("0")


def format_amount(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
    else:
        raw = str(value)
        if "|" in raw:
            raw = raw.split("|", 1)[0]
        raw = raw.replace(".", "").replace(",", ".")
        try:
            amount = float(raw)
        except ValueError:
            return raw
    return "$" + f"{amount:,.0f}".replace(",", ".")


def extract_contact_name(contact_data: Dict[str, Any] | None) -> str | None:
    if not contact_data:
        return None
    name = str(contact_data.get("NAME") or "").strip()
    last = str(contact_data.get("LAST_NAME") or "").strip()
    full = f"{name} {last}".strip()
    return full or None


def extract_contact_phone(contact_data: Dict[str, Any] | None) -> str | None:
    if not contact_data:
        return None
    phones = contact_data.get("PHONE") or []
    for phone in phones:
        value = phone.get("VALUE") if isinstance(phone, dict) else None
        normalized = normalize_phone(value)
        if normalized:
            return normalized
    return None


def _load_trigger_body() -> Any:
    raw = os.environ.get("TRIGGER_BODY_JSON", "").strip()
    if not raw:
        raise ValueError("Missing TRIGGER_BODY_JSON.")
    return json.loads(raw)


def _normalize_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        raw = payload.strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return _parse_querystring(raw)
        if isinstance(value, dict):
            return value
        return {"payload": value}
    return {}


def _parse_querystring(raw: str) -> Dict[str, Any]:
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[0] if len(values) == 1 else values for key, values in parsed.items()}


def _get_value(payload: Dict[str, Any], flat_key: str, nested_path: tuple[str, ...]) -> Any:
    if flat_key in payload:
        return payload.get(flat_key)
    current: Any = payload
    for key in nested_path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _get_timeout_seconds() -> float:
    raw = os.environ.get(BITRIX_TIMEOUT_ENV)
    if not raw:
        return 10.0
    try:
        value = float(raw)
    except ValueError:
        return 10.0
    return value if value > 0 else 10.0


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing environment variable {name}.")
    return value


def _result(
    *,
    ok: bool,
    action: str,
    reason: str,
    scheduled_for: str = "",
    deal_id: str = "",
    edna_status: str = "",
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "action": action,
        "reason": reason,
        "scheduled_for": scheduled_for,
        "deal_id": deal_id,
        "edna_status": edna_status,
    }


def _emit_outputs_if_available(result: Dict[str, Any]) -> None:
    if Kestra is None:
        return

    Kestra.outputs(
        {
            "ok": bool(result.get("ok", False)),
            "action": str(result.get("action") or ""),
            "reason": str(result.get("reason") or ""),
            "scheduled_for": str(result.get("scheduled_for") or ""),
            "deal_id": str(result.get("deal_id") or ""),
            "edna_status": str(result.get("edna_status") or ""),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
