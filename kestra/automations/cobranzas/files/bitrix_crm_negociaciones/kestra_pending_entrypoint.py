#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from typing import Any, Dict

from . import service

try:
    from kestra import Kestra
except ImportError:  # pragma: no cover - optional outside Kestra
    Kestra = None


def main() -> int:
    try:
        result = handle_pending_action()
    except Exception as exc:
        result = _result(
            ok=False,
            action="error",
            reason="exception",
            message=str(exc),
            should_update=False,
            action_key="",
            updated_action_json="",
            action_ttl="P45D",
        )

    _emit_outputs_if_available(result)
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    return 0


def handle_pending_action() -> Dict[str, Any]:
    action = _load_json_env("ACTION_JSON")
    dependency = _load_json_env("DEPENDENCY_JSON")

    if not isinstance(action, dict) or not action:
        return _result(ok=True, action="ignored", reason="missing_action", should_update=False)

    now = service.get_now()
    status = str(action.get("status") or "pending")
    action_key = str(action.get("key") or "")

    if status != "pending":
        return _result(
            ok=True,
            action="ignored",
            reason="already_finalized",
            should_update=False,
            action_key=action_key,
        )

    due_at = service.parse_bitrix_datetime(str(action.get("due_at") or ""))
    if due_at is None:
        updated = service.finalize_action(
            action,
            status="error",
            reason="invalid_due_at",
            processed_at=now.isoformat(),
        )
        return _result(
            ok=False,
            action="error",
            reason="invalid_due_at",
            should_update=True,
            action_key=action_key,
            updated_action_json=json.dumps(updated, ensure_ascii=True),
        )

    if due_at > now:
        return _result(
            ok=True,
            action="pending",
            reason="not_due",
            should_update=False,
            action_key=action_key,
        )

    dependency_check = _validate_dependency(action, dependency)
    if dependency_check is not None:
        return dependency_check

    deal_id = str(action.get("deal_id") or "")
    expected_stage = str(action.get("expected_stage") or "")
    previous_sent_at = str(action.get("previous_sent_at") or "")

    deal_data, contact_data = service.fetch_deal_with_contact(deal_id)
    current_stage = str(deal_data.get("STAGE_ID") or "")
    if expected_stage and current_stage != expected_stage:
        updated = service.finalize_action(
            action,
            status="cancelled",
            reason="stage_mismatch",
            processed_at=now.isoformat(),
        )
        return _result(
            ok=True,
            action="cancelled",
            reason="stage_mismatch",
            should_update=True,
            action_key=action_key,
            updated_action_json=json.dumps(updated, ensure_ascii=True),
        )

    if previous_sent_at and service.has_new_communication_since(deal_data, previous_sent_at):
        updated = service.finalize_action(
            action,
            status="cancelled",
            reason="new_communication",
            processed_at=now.isoformat(),
        )
        return _result(
            ok=True,
            action="cancelled",
            reason="new_communication",
            should_update=True,
            action_key=action_key,
            updated_action_json=json.dumps(updated, ensure_ascii=True),
        )

    action_kind = str(action.get("action_kind") or "")
    if action_kind == "send_or_noop":
        template_id = str(action.get("template_id") or "")
        if not template_id:
            updated = service.finalize_action(
                action,
                status="cancelled",
                reason="missing_template_id",
                processed_at=now.isoformat(),
            )
            return _result(
                ok=True,
                action="cancelled",
                reason="missing_template_id",
                should_update=True,
                action_key=action_key,
                updated_action_json=json.dumps(updated, ensure_ascii=True),
            )

        edna_result = service.send_to_edna(int(template_id), deal_data, contact_data)
        updated = service.finalize_action(
            action,
            status="completed",
            reason="sent",
            processed_at=now.isoformat(),
            edna_status=str(edna_result.get("status_code") or ""),
        )
        return _result(
            ok=True,
            action="completed",
            reason="sent",
            should_update=True,
            action_key=action_key,
            updated_action_json=json.dumps(updated, ensure_ascii=True),
            edna_status=str(edna_result.get("status_code") or ""),
        )

    if action_kind == "move_or_noop":
        next_stage = str(action.get("next_stage") or "")
        if not next_stage:
            updated = service.finalize_action(
                action,
                status="cancelled",
                reason="missing_next_stage",
                processed_at=now.isoformat(),
            )
            return _result(
                ok=True,
                action="cancelled",
                reason="missing_next_stage",
                should_update=True,
                action_key=action_key,
                updated_action_json=json.dumps(updated, ensure_ascii=True),
            )

        service.update_deal_stage(deal_id, next_stage)
        updated = service.finalize_action(
            action,
            status="completed",
            reason="moved",
            processed_at=now.isoformat(),
        )
        return _result(
            ok=True,
            action="completed",
            reason="moved",
            should_update=True,
            action_key=action_key,
            updated_action_json=json.dumps(updated, ensure_ascii=True),
        )

    updated = service.finalize_action(
        action,
        status="error",
        reason="unknown_action_kind",
        processed_at=now.isoformat(),
    )
    return _result(
        ok=False,
        action="error",
        reason="unknown_action_kind",
        should_update=True,
        action_key=action_key,
        updated_action_json=json.dumps(updated, ensure_ascii=True),
    )


def _validate_dependency(action: Dict[str, Any], dependency: Any) -> Dict[str, Any] | None:
    depends_on_key = str(action.get("depends_on_key") or "")
    if not depends_on_key:
        return None

    action_key = str(action.get("key") or "")
    if not isinstance(dependency, dict) or not dependency:
        return _result(
            ok=True,
            action="pending",
            reason="waiting_dependency",
            should_update=False,
            action_key=action_key,
        )

    dependency_status = str(dependency.get("status") or "pending")
    if dependency_status == "pending":
        return _result(
            ok=True,
            action="pending",
            reason="waiting_dependency",
            should_update=False,
            action_key=action_key,
        )

    if dependency_status != "completed":
        updated = service.finalize_action(
            action,
            status="cancelled",
            reason="dependency_not_completed",
            processed_at=service.get_now().isoformat(),
        )
        return _result(
            ok=True,
            action="cancelled",
            reason="dependency_not_completed",
            should_update=True,
            action_key=action_key,
            updated_action_json=json.dumps(updated, ensure_ascii=True),
        )

    processed_at = str(dependency.get("processed_at") or "")
    if processed_at and not action.get("previous_sent_at"):
        action["previous_sent_at"] = processed_at
    return None


def _load_json_env(name: str) -> Any:
    raw = service.get_env(name, "").strip()
    if not raw:
        return None
    return json.loads(raw)


def _result(
    *,
    ok: bool,
    action: str,
    reason: str,
    message: str = "",
    should_update: bool,
    action_key: str = "",
    updated_action_json: str = "",
    action_ttl: str = "P45D",
    edna_status: str = "",
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "action": action,
        "reason": reason,
        "message": message,
        "should_update": should_update,
        "action_key": action_key,
        "updated_action_json": updated_action_json,
        "action_ttl": action_ttl,
        "edna_status": edna_status,
    }


def _emit_outputs_if_available(result: Dict[str, Any]) -> None:
    if Kestra is None:
        return
    Kestra.outputs(result)


if __name__ == "__main__":
    raise SystemExit(main())
