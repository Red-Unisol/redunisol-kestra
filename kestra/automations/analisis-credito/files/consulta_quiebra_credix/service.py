from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

RESULT_LINK_SELECTOR = "a.btn-sm.btn-info[data-href]"
RESULTS_ROW_SELECTOR = "table tbody tr"
NEXT_BUTTON_SELECTOR = "#btn_siguiente"
UPDATE_ALL_SELECTOR = "#procesar_todo_auto"
EDICTS_TABLE_SELECTOR = "table.table.table-sm.table-striped.table-bordered"
NO_RESULTS_SELECTOR = "text=No se encontraron"
EDICTS_TABLE_TEXT = "Edictos judiciales"
DETAIL_NEXT_TEXT = "Siguiente"
PROCESSING_TEXT = "Procesando"
CACHE_VERSION = 1
CACHE_TTL = "P8D"
CACHE_MAX_AGE_DAYS = 7
CACHE_DUMMY_KEY = "credixsa.cache.lookup.none"


@dataclass(frozen=True)
class SearchRequest:
    cuit: str
    nombre: str


@dataclass(frozen=True)
class CredixConfig:
    cliente: str
    usuario: str
    password: str
    login_url: str
    timeout_ms: int
    debug_enabled: bool
    cache_by_cuil: dict[str, Any] | None = None
    cache_by_name: dict[str, Any] | None = None
    cache_max_age_days: int = CACHE_MAX_AGE_DAYS


@dataclass(frozen=True)
class CandidateRow:
    cuit: str
    nombre: str
    documento: str
    link: "Locator"


def parse_search_request(payload: Any) -> SearchRequest:
    if isinstance(payload, dict):
        cuit = normalize_cuit(payload.get("cuit"))
        nombre = normalize_name(payload.get("nombre"))
    elif payload is None:
        raise ValueError("Missing request body.")
    elif isinstance(payload, (list, tuple)):
        raise ValueError("Body must be an object or string.")
    else:
        cuit = normalize_cuit(payload)
        nombre = ""

    if not cuit and not nombre:
        raise ValueError("At least one of 'cuit' or 'nombre' is required.")

    return SearchRequest(cuit=cuit, nombre=nombre)


def load_config_from_env() -> CredixConfig:
    cliente = os.getenv("CREDIX_CLIENTE", "").strip()
    usuario = os.getenv("CREDIX_USER", "").strip()
    password = os.getenv("CREDIX_PASS", "").strip()
    login_url = os.getenv("CREDIX_LOGIN_URL", "https://www.credixsa.com/nuevo/login.php").strip()
    timeout_raw = os.getenv("CREDIX_TIMEOUT_SECONDS", "30").strip() or "30"
    debug_raw = os.getenv("CREDIX_DEBUG", "").strip().lower()
    cache_max_age_raw = os.getenv("CREDIX_CACHE_MAX_AGE_DAYS", str(CACHE_MAX_AGE_DAYS)).strip()

    if not cliente or not usuario or not password:
        raise ValueError("Missing CREDIX_CLIENTE, CREDIX_USER or CREDIX_PASS.")
    if not login_url:
        raise ValueError("Missing CREDIX_LOGIN_URL.")

    timeout_seconds = float(timeout_raw)
    if timeout_seconds <= 0:
        raise ValueError("CREDIX_TIMEOUT_SECONDS must be greater than 0.")

    return CredixConfig(
        cliente=cliente,
        usuario=usuario,
        password=password,
        login_url=login_url,
        timeout_ms=int(timeout_seconds * 1000),
        debug_enabled=debug_raw in {"1", "true", "yes"},
        cache_by_cuil=decode_cache_env(os.getenv("CREDIX_CACHE_BY_CUIL_JSON", "")),
        cache_by_name=decode_cache_env(os.getenv("CREDIX_CACHE_BY_NAME_JSON", "")),
        cache_max_age_days=int(cache_max_age_raw or CACHE_MAX_AGE_DAYS),
    )


def consultar_tabla(request: SearchRequest, config: CredixConfig) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    _log_event("consulta_quiebra_start", cuit=request.cuit, nombre=request.nombre)
    cached_result = find_cached_result(request, config)
    if cached_result is not None:
        return cached_result

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage"],
        )
        page = browser.new_page()
        page.set_default_timeout(config.timeout_ms)

        try:
            _login(page, config, request)
            _search(page, request)
            _wait_search_results(page, config)

            candidates = _extract_candidates(page)
            if not candidates:
                _debug_dump(page, config, "no_results", request)
                return build_none_result(request)

            if len(candidates) > 1:
                return build_multiple_result(request, candidates)

            selected_candidate = candidates[0]
            selected_candidate.link.click()
            page.wait_for_load_state("networkidle")
            _refresh_online_updates_if_available(page, config, request)
            _wait_next_ui_step(page, request)
            _wait_report_tables_stable(page, config, request)
            data = _extract_report_sections(page, config, request)
            if not data and not _is_detail_summary_page(page):
                raise TimeoutError("Timed out waiting for CredixSA report sections.")
            return build_single_result(
                request,
                data,
                cuit=normalize_cuit(selected_candidate.cuit) or request.cuit,
                nombre=selected_candidate.nombre,
            )
        finally:
            browser.close()


def build_none_result(request: SearchRequest) -> dict[str, Any]:
    return _base_result(request, status="none", rows=[], data=[], error="")


def build_multiple_result(
    request: SearchRequest,
    candidates: list[CandidateRow],
) -> dict[str, Any]:
    rows = [
        {
            "cuit": candidate.cuit,
            "nombre": candidate.nombre,
            "documento": candidate.documento,
        }
        for candidate in candidates
    ]
    return _base_result(request, status="multiple", rows=rows, data=[], error="")


def build_single_result(
    request: SearchRequest,
    data: list[dict[str, Any]],
    *,
    cuit: str | None = None,
    nombre: str | None = None,
) -> dict[str, Any]:
    return _base_result(
        request,
        status="single",
        rows=[],
        data=data,
        error="",
        cuit=cuit,
        nombre=nombre,
    )


def build_error_result(
    request: SearchRequest | None,
    error: str,
) -> dict[str, Any]:
    safe_request = request or SearchRequest(cuit="", nombre="")
    return _base_result(safe_request, status="error", rows=[], data=[], error=error, ok=False)


def build_output_payload(result: dict[str, Any]) -> dict[str, Any]:
    response_payload = build_legacy_response(result)
    cache_entry = build_cache_entry(result)
    cuil_cache_key = cache_key_for_cuil(result.get("cuit")) if cache_entry else ""
    name_cache_key = cache_key_for_name(result.get("nombre")) if cache_entry else ""
    cache_value_json = (
        json.dumps(cache_entry, ensure_ascii=True, separators=(",", ":"))
        if cache_entry is not None
        else ""
    )
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
        "cache_should_persist": cache_entry is not None,
        "cache_ttl": CACHE_TTL if cache_entry is not None else "",
        "cache_value_json": cache_value_json,
        "cuil_cache_key": cuil_cache_key,
        "name_cache_key": name_cache_key,
        "cuil_cache_should_persist": bool(cuil_cache_key and cache_entry is not None),
        "name_cache_should_persist": bool(name_cache_key and cache_entry is not None),
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


def build_cache_lookup(payload: Any) -> dict[str, Any]:
    request = parse_search_request(payload)
    cuil_key = cache_key_for_cuil(request.cuit)
    name_key = cache_key_for_name(request.nombre)
    return {
        "cuit": request.cuit,
        "nombre": request.nombre,
        "cuil_cache_key": cuil_key,
        "name_cache_key": name_key,
        "cuil_cache_lookup_key": cuil_key or CACHE_DUMMY_KEY,
        "name_cache_lookup_key": name_key or CACHE_DUMMY_KEY,
    }


def decode_cache_env(value: str) -> dict[str, Any] | None:
    raw_value = (value or "").strip()
    if not raw_value or raw_value == "null":
        return None
    payload = json.loads(raw_value)
    if not isinstance(payload, dict):
        return None
    return payload


def find_cached_result(request: SearchRequest, config: CredixConfig) -> dict[str, Any] | None:
    return find_cached_result_in_payloads(
        request,
        config.cache_by_cuil,
        config.cache_by_name,
        config.cache_max_age_days,
    )


def find_cached_result_in_payloads(
    request: SearchRequest,
    cache_by_cuil: dict[str, Any] | None,
    cache_by_name: dict[str, Any] | None,
    max_age_days: int = CACHE_MAX_AGE_DAYS,
) -> dict[str, Any] | None:
    for cache_payload, cache_source in (
        (cache_by_cuil, "cuil"),
        (cache_by_name, "name"),
    ):
        result = cached_result_if_fresh(cache_payload, max_age_days)
        if result is None:
            continue
        if cache_source == "name" and request.cuit:
            cached_cuil = normalize_cuit(result.get("cuit"))
            if cached_cuil and cached_cuil != request.cuit:
                continue
        result["cache_hit"] = True
        result["cache_source"] = cache_source
        result["cached_at"] = str(cache_payload.get("cached_at") or "")
        return result
    return None


def cached_result_if_fresh(
    cache_payload: dict[str, Any] | None,
    max_age_days: int = CACHE_MAX_AGE_DAYS,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if not isinstance(cache_payload, dict):
        return None
    if int(cache_payload.get("version") or 0) != CACHE_VERSION:
        return None
    cached_at = parse_datetime(cache_payload.get("cached_at"))
    if cached_at is None:
        return None
    effective_now = now or utc_now()
    if effective_now - cached_at > timedelta(days=max_age_days):
        return None
    result = cache_payload.get("result")
    if not isinstance(result, dict):
        return None
    return dict(result)


def build_cache_entry(result: dict[str, Any]) -> dict[str, Any] | None:
    if result.get("cache_hit"):
        return None
    if result.get("status") != "single" or not result.get("ok", False):
        return None
    if not result.get("data"):
        return None

    cached_at = utc_now()
    clean_result = {
        "ok": True,
        "status": "single",
        "cuit": str(result.get("cuit") or ""),
        "nombre": str(result.get("nombre") or ""),
        "rows": [],
        "data": result.get("data") or [],
        "error": "",
    }
    return {
        "version": CACHE_VERSION,
        "cached_at": cached_at.isoformat(),
        "expires_at": (cached_at + timedelta(days=CACHE_MAX_AGE_DAYS)).isoformat(),
        "result": clean_result,
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


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


def _login(page: "Page", config: CredixConfig, request: SearchRequest) -> None:
    page.goto(config.login_url, wait_until="domcontentloaded")
    page.fill("#cdxcliente", config.cliente)
    page.fill("#cdxusername", config.usuario)
    page.fill("#cdxpassword", config.password)
    page.locator("#btnSubmit").click()
    page.wait_for_load_state("networkidle")
    _debug_log(page, config, "post_login", request)


def _search(page: "Page", request: SearchRequest) -> None:
    page.fill("#cuit", request.cuit)
    page.fill("#nombre", request.nombre)
    page.locator("text=Siguiente").click()
    page.wait_for_load_state("networkidle")


def _wait_search_results(page: "Page", config: CredixConfig) -> None:
    page.locator(RESULT_LINK_SELECTOR).or_(page.locator(NO_RESULTS_SELECTOR)).first.wait_for(
        timeout=config.timeout_ms
    )


def _extract_candidates(page: "Page") -> list[CandidateRow]:
    candidates: list[CandidateRow] = []
    rows = page.locator(RESULTS_ROW_SELECTOR)

    for index in range(rows.count()):
        row = rows.nth(index)
        link = row.locator(RESULT_LINK_SELECTOR)
        if link.count() == 0:
            continue

        cells = row.locator("td")
        candidates.append(
            CandidateRow(
                cuit=link.first.inner_text().strip(),
                nombre=cells.nth(1).inner_text().strip() if cells.count() >= 2 else "",
                documento=cells.nth(2).inner_text().strip() if cells.count() >= 3 else "",
                link=link.first,
            )
        )

    return candidates


def _wait_next_ui_step(page: "Page", request: SearchRequest) -> None:
    deadline = time.monotonic() + 30.0

    while time.monotonic() < deadline:
        try:
            if _is_final_detail_step(page):
                return
        except Exception:
            pass
        try:
            next_control = _find_detail_next_control(page)
            if next_control is not None:
                next_control.click()
                page.wait_for_load_state("networkidle")
                continue
        except Exception:
            pass
        time.sleep(0.2)

    _log_event(
        "consulta_quiebra_wait_next_timeout",
        cuit=request.cuit,
        nombre=request.nombre,
        url=page.url,
    )
    raise TimeoutError(
        f"Timed out waiting for '{NEXT_BUTTON_SELECTOR}' or the final edicts table. "
        f"cuit={request.cuit!r} nombre={request.nombre!r}"
    )


def _refresh_online_updates_if_available(
    page: "Page",
    config: CredixConfig,
    request: SearchRequest,
) -> None:
    deadline = time.monotonic() + (config.timeout_ms / 1000)
    while time.monotonic() < deadline:
        if _is_detail_summary_page(page):
            return

        update_all = page.locator(UPDATE_ALL_SELECTOR)
        try:
            if update_all.count() > 0 and update_all.first.is_visible():
                _log_event("consulta_quiebra_update_all_start", cuit=request.cuit, nombre=request.nombre)
                update_all.first.click()
                page.wait_for_load_state("networkidle")
                _wait_online_updates_finished(page, config, request)
                _log_event("consulta_quiebra_update_all_done", cuit=request.cuit, nombre=request.nombre)
                return
        except Exception:
            _debug_dump(page, config, "update_all_error", request)
            raise

        if _find_detail_next_control(page) is not None:
            return

        time.sleep(0.2)


def _wait_online_updates_finished(
    page: "Page",
    config: CredixConfig,
    request: SearchRequest,
) -> None:
    deadline = time.monotonic() + max(60.0, (config.timeout_ms / 1000) * 3)

    while time.monotonic() < deadline:
        if _is_detail_summary_page(page):
            return

        body_text = page.locator("body").inner_text(timeout=5000)
        next_control = page.locator(NEXT_BUTTON_SELECTOR)
        next_enabled = False
        try:
            next_enabled = next_control.count() > 0 and next_control.first.is_enabled()
        except Exception:
            next_enabled = False

        if PROCESSING_TEXT not in body_text and next_enabled:
            return

        time.sleep(1.0)

    _debug_dump(page, config, "update_all_timeout", request)
    raise TimeoutError(
        f"Timed out waiting for CredixSA online updates to finish. "
        f"cuit={request.cuit!r} nombre={request.nombre!r}"
    )


def _extract_report_sections(
    page: "Page",
    config: CredixConfig,
    request: SearchRequest,
) -> list[dict[str, Any]]:
    try:
        page.wait_for_selector("table", timeout=config.timeout_ms)
    except Exception as exc:
        _debug_dump(page, config, "report_tables_timeout", request)
        raise TimeoutError("Timed out waiting for CredixSA report tables.") from exc

    raw_sections = page.evaluate(
        """
        () => {
            const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
            return Array.from(document.querySelectorAll('table')).map((table, index) => {
                const rows = Array.from(table.rows).map((row) => {
                    const cells = Array.from(row.cells).map((cell) => ({
                        text: normalize(cell.innerText),
                        header: cell.tagName.toLowerCase() === 'th',
                    })).filter((cell) => cell.text !== '');
                    return {
                        cells,
                        has_header: cells.some((cell) => cell.header),
                        all_header: cells.length > 0 && cells.every((cell) => cell.header),
                    };
                }).filter((row) => row.cells.length > 0);

                return {
                    index,
                    text: normalize(table.innerText),
                    rows,
                };
            }).filter((table) => table.text !== '' && table.rows.length > 0);
        }
        """
    )
    return [_normalize_report_section(section) for section in raw_sections]


def _wait_report_tables_stable(page: "Page", config: CredixConfig, request: SearchRequest) -> None:
    deadline = time.monotonic() + max(30.0, config.timeout_ms / 1000)
    started_at = time.monotonic()
    previous_count = -1
    stable_since: float | None = None

    while time.monotonic() < deadline:
        if not _is_detail_summary_page(page):
            time.sleep(0.5)
            continue

        try:
            current_count = page.locator("table").count()
            body_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            time.sleep(0.5)
            continue

        is_stable = current_count == previous_count and PROCESSING_TEXT not in body_text
        if is_stable:
            stable_since = stable_since or time.monotonic()
            if time.monotonic() - stable_since >= 2.0 and time.monotonic() - started_at >= 5.0:
                return
        else:
            stable_since = None
            previous_count = current_count

        time.sleep(1.0)

    _log_event(
        "consulta_quiebra_report_stability_timeout",
        cuit=request.cuit,
        nombre=request.nombre,
        url=page.url,
    )


def _normalize_report_section(section: dict[str, Any]) -> dict[str, Any]:
    raw_rows = [
        [str(cell.get("text") or "") for cell in row.get("cells", [])]
        for row in section.get("rows", [])
    ]
    raw_rows = [row for row in raw_rows if any(cell for cell in row)]
    header_rows = [
        index
        for index, row in enumerate(section.get("rows", []))
        if row.get("all_header")
    ]
    title = _section_title(raw_rows)
    source = _section_source(title)
    column_headers = _section_column_headers(raw_rows, header_rows)
    records = _section_records(raw_rows, column_headers)

    return {
        "index": int(section.get("index") or 0),
        "title": title,
        "source": source,
        "headers": column_headers,
        "rows": raw_rows,
        "records": records,
        "text": normalize_name(section.get("text")),
    }


def _section_title(rows: list[list[str]]) -> str:
    for row in rows:
        for cell in row:
            value = normalize_name(cell)
            if value:
                return value
    return ""


def _section_source(title: str) -> str:
    match = re.search(r"\bFuente:\s*(.+)$", title, flags=re.IGNORECASE)
    return normalize_name(match.group(1)) if match else ""


def _section_column_headers(rows: list[list[str]], header_rows: list[int]) -> list[str]:
    for index in header_rows:
        row = rows[index]
        if len(row) > 1:
            return [_deduplicate_header(value, position) for position, value in enumerate(row)]

    widest = max(rows, key=len, default=[])
    if len(widest) > 2:
        return [_deduplicate_header(value, position) for position, value in enumerate(widest)]

    return []


def _deduplicate_header(value: str, position: int) -> str:
    normalized = normalize_name(value)
    return normalized or f"columna_{position + 1}"


def _section_records(rows: list[list[str]], headers: list[str]) -> list[dict[str, str]]:
    if not rows:
        return []

    if headers:
        records: list[dict[str, str]] = []
        for row in rows:
            if row == headers:
                continue
            if len(row) != len(headers):
                continue
            records.append(dict(zip(headers, row, strict=True)))
        if records:
            return records

    key_value_rows = [
        {normalize_name(row[0]): normalize_name(row[1])}
        for row in rows
        if len(row) == 2 and normalize_name(row[0])
    ]
    return key_value_rows


def _is_detail_summary_page(page: "Page") -> bool:
    body_text = page.locator("body").inner_text(timeout=5000)
    if "Datos Filiatorios" in body_text:
        return True
    if "Resumen (*)" in body_text:
        return True
    return "con_cuit3.php" in page.url


def _is_final_detail_step(page: "Page") -> bool:
    table = page.locator(EDICTS_TABLE_SELECTOR).filter(has_text=EDICTS_TABLE_TEXT)
    if table.count() > 0 and table.first.is_visible():
        return True
    return _is_detail_summary_page(page)


def _find_detail_next_control(page: "Page") -> "Locator | None":
    candidates = [
        page.locator(NEXT_BUTTON_SELECTOR),
        page.locator("button", has_text=DETAIL_NEXT_TEXT),
        page.locator("input[type='submit'][value='Siguiente']"),
        page.locator("input[type='button'][value='Siguiente']"),
        page.locator("a", has_text=DETAIL_NEXT_TEXT),
        page.locator("text=Siguiente"),
    ]

    for locator in candidates:
        try:
            if locator.count() > 0 and locator.first.is_visible():
                return locator.first
        except Exception:
            continue

    return None


def _base_result(
    request: SearchRequest,
    *,
    status: str,
    rows: list[dict[str, str]],
    data: list[dict[str, Any]],
    error: str,
    ok: bool = True,
    cuit: str | None = None,
    nombre: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "status": status,
        "cuit": request.cuit if cuit is None else cuit,
        "nombre": request.nombre if nombre is None else nombre,
        "rows": rows,
        "data": data,
        "error": error,
        "cache_hit": False,
        "cached_at": "",
    }


def _debug_log(page: "Page", config: CredixConfig, stage: str, request: SearchRequest) -> None:
    if not config.debug_enabled:
        return

    details = {
        "event": "consulta_quiebra_debug",
        "stage": stage,
        "url": page.url,
        "cuit": request.cuit,
        "nombre": request.nombre,
    }
    sys.stderr.write(json.dumps(details, ensure_ascii=True) + "\n")


def _debug_dump(page: "Page", config: CredixConfig, prefix: str, request: SearchRequest) -> None:
    if not config.debug_enabled:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"credixsa_{prefix}_{timestamp}"
    try:
        page.screenshot(path=f"{base_name}.png", full_page=True)
        html = page.content()
        with open(f"{base_name}.html", "w", encoding="utf-8") as handle:
            handle.write(html)
    except Exception as exc:
        _log_event(
            "consulta_quiebra_debug_dump_error",
            cuit=request.cuit,
            nombre=request.nombre,
            error=str(exc),
        )


def _log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    sys.stderr.write(json.dumps(payload, ensure_ascii=True) + "\n")
