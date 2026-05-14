#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

try:
    from kestra import Kestra
except ImportError:  # pragma: no cover - optional outside Kestra
    Kestra = None


FINAL_STATUSES = {"completed", "cancelled", "error"}


def main() -> int:
    new_plan = _load_json_env("NEW_PLAN_JSON")
    legacy_plan = _load_json_env("LEGACY_PLAN_JSON")
    result = evaluate_plan_guard(new_plan, legacy_plan)

    _emit_outputs_if_available(result)
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    return 0


def evaluate_plan_guard(new_plan: Any, legacy_plan: Any) -> Dict[str, Any]:
    if _plan_exists(new_plan):
        return {
            "should_schedule": False,
            "plan_already_exists": True,
            "reason": "new_plan_exists",
        }

    if _plan_is_active(legacy_plan):
        return {
            "should_schedule": False,
            "plan_already_exists": True,
            "reason": "legacy_plan_active",
        }

    if _plan_exists(legacy_plan):
        return {
            "should_schedule": True,
            "plan_already_exists": False,
            "reason": "legacy_plan_finalized",
        }

    return {
        "should_schedule": True,
        "plan_already_exists": False,
        "reason": "no_existing_plan",
    }


def _plan_is_active(plan: Any) -> bool:
    if not _plan_exists(plan):
        return False

    if not isinstance(plan, dict):
        return True

    plan_status = str(plan.get("status") or "").strip().lower()
    if plan_status not in FINAL_STATUSES:
        return True

    actions = plan.get("actions") or []
    if not isinstance(actions, list):
        return False

    for action in actions:
        if not isinstance(action, dict):
            return True
        action_status = str(action.get("status") or "").strip().lower()
        if action_status not in FINAL_STATUSES:
            return True

    return False


def _plan_exists(plan: Any) -> bool:
    return plan not in (None, "", [], {})


def _load_json_env(name: str) -> Any:
    raw = os.getenv(name, "").strip()
    if not raw or raw == "null":
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _emit_outputs_if_available(result: Dict[str, Any]) -> None:
    if Kestra is None:
        return

    Kestra.outputs(result)


if __name__ == "__main__":
    raise SystemExit(main())
