from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from typing import Any

from fastapi import FastAPI
from fastapi import Header
from fastapi import HTTPException
from pydantic import BaseModel


CACHE_VERSION = 1
DEFAULT_DB_PATH = "/data/credixsa-cache/credixsa.sqlite"
DEFAULT_MAX_AGE_DAYS = 7

app = FastAPI(title="CredixSA Cache API")


class CacheRequest(BaseModel):
    cuit: str | None = None
    nombre: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    db_path = _db_path()
    return {
        "ok": True,
        "db_path": db_path,
        "db_exists": os.path.exists(db_path),
    }


@app.post("/credixsa/cache")
def get_cached_report(
    request: CacheRequest,
    authorization: str | None = Header(default=None),
    x_api_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(authorization, x_api_token)
    cuit = normalize_cuit(request.cuit)
    nombre = normalize_name(request.nombre)
    if not cuit and not nombre:
        raise HTTPException(status_code=422, detail="At least one of cuit or nombre is required.")

    for key, source in _lookup_keys(cuit, nombre):
        cache_payload = _load_cache_payload(key)
        result = cached_result_if_fresh(cache_payload, _max_age_days())
        if result is None:
            continue
        if source == "name" and cuit:
            cached_cuit = normalize_cuit(result.get("cuit"))
            if cached_cuit and cached_cuit != cuit:
                continue
        result["cache_hit"] = True
        result["cache_source"] = source
        result["cached_at"] = str(cache_payload.get("cached_at") or "")
        return build_output_payload(result)

    raise HTTPException(
        status_code=404,
        detail={
            "ok": False,
            "status": "cache_miss",
            "cache_hit": False,
            "error": "cache_miss",
        },
    )


def _require_token(authorization: str | None, x_api_token: str | None) -> None:
    expected = os.getenv("CREDIXSA_CACHE_API_TOKEN", "").strip()
    if not expected:
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    if expected not in {bearer, (x_api_token or "").strip()}:
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _lookup_keys(cuit: str, nombre: str) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    cuil_key = cache_key_for_cuil(cuit)
    if cuil_key:
        keys.append((cuil_key, "cuil"))
    name_key = cache_key_for_name(nombre)
    if name_key:
        keys.append((name_key, "name"))
    return keys


def _load_cache_payload(key: str) -> dict[str, Any] | None:
    db_path = _db_path()
    if not os.path.exists(db_path):
        return None
    with sqlite3.connect(db_path, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT payload_json FROM credixsa_cache WHERE lookup_key = ?",
            (key,),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(str(row["payload_json"] or ""))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def cached_result_if_fresh(
    cache_payload: dict[str, Any] | None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict[str, Any] | None:
    if not isinstance(cache_payload, dict):
        return None
    if int(cache_payload.get("version") or 0) != CACHE_VERSION:
        return None
    cached_at = parse_datetime(cache_payload.get("cached_at"))
    if cached_at is None:
        return None
    if datetime.now(timezone.utc) - cached_at > timedelta(days=max_age_days):
        return None
    result = cache_payload.get("result")
    if not isinstance(result, dict):
        return None
    return dict(result)


def build_output_payload(result: dict[str, Any]) -> dict[str, Any]:
    response_payload = build_legacy_response(result)
    return {
        "ok": bool(result.get("ok", False)),
        "status": str(result.get("status") or ""),
        "cuit": str(result.get("cuit") or ""),
        "nombre": str(result.get("nombre") or ""),
        "rows_json": json.dumps(result.get("rows") or [], ensure_ascii=True, separators=(",", ":")),
        "data_json": json.dumps(result.get("data") or [], ensure_ascii=True, separators=(",", ":")),
        "response_json": json.dumps(response_payload, ensure_ascii=True, separators=(",", ":")),
        "error": str(result.get("error") or ""),
        "cache_hit": bool(result.get("cache_hit", False)),
        "cached_at": str(result.get("cached_at") or ""),
    }


def build_legacy_response(result: dict[str, Any]) -> dict[str, Any]:
    status = str(result.get("status") or "")
    if status == "single":
        return {"status": "single", "data": result.get("data") or []}
    if status in {"none", "multiple"}:
        return {"status": status, "rows": result.get("rows") or []}
    return {"status": "error", "error": str(result.get("error") or "Unknown error")}


def normalize_cuit(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def normalize_name(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def cache_key_for_cuil(value: Any) -> str:
    digits = normalize_cuit(value)
    if len(digits) != 11:
        return ""
    return f"credixsa.cuil.{digits}"


def normalize_name_for_cache(value: Any) -> str:
    normalized = normalize_name(value).lower()
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", normalized)
        if unicodedata.category(char) != "Mn"
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return normalize_name(normalized)


def cache_key_for_name(value: Any) -> str:
    normalized = normalize_name_for_cache(value)
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"credixsa.name.{digest}"


def parse_datetime(value: Any) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _db_path() -> str:
    return os.getenv("CREDIXSA_CACHE_DB_PATH", DEFAULT_DB_PATH).strip() or DEFAULT_DB_PATH


def _max_age_days() -> int:
    raw = os.getenv("CREDIXSA_CACHE_MAX_AGE_DAYS", str(DEFAULT_MAX_AGE_DAYS)).strip()
    try:
        return int(raw or DEFAULT_MAX_AGE_DAYS)
    except ValueError:
        return DEFAULT_MAX_AGE_DAYS
