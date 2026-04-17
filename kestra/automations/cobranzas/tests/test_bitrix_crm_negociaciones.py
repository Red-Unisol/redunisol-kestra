from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

FILES_ROOT = Path(__file__).resolve().parent.parent / "files"
if str(FILES_ROOT) not in sys.path:
    sys.path.insert(0, str(FILES_ROOT))

from bitrix_crm_negociaciones import (  # noqa: E402
    kestra_pending_entrypoint,
    kestra_webhook_entrypoint,
    service,
)


class BitrixCrmNegociacionesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = {
            "LOCAL_TZ": "America/Argentina/Buenos_Aires",
            "BUSINESS_START_HOUR": "9",
            "BUSINESS_START_MINUTE": "0",
            "BUSINESS_END_HOUR": "17",
            "BUSINESS_END_MINUTE": "0",
            "PROMISE_DATE_FIELD": "UF_CRM_1724427951",
            "PROMISE_AMOUNT_FIELD": "UF_CRM_1724429048",
        }

    def test_add_business_hours_skips_weekend_and_after_hours(self) -> None:
        with patch.dict(os.environ, self.env, clear=False):
            start = datetime.fromisoformat("2026-04-17T16:00:00-03:00")
            result = service.add_business_hours(start, 3)

        self.assertEqual(result.isoformat(), "2026-04-20T11:00:00-03:00")

    def test_promise_send_time_moves_weekend_to_next_business_start(self) -> None:
        with patch.dict(os.environ, self.env, clear=False):
            result = service.promise_send_time("2026-04-19")

        self.assertEqual(result.isoformat(), "2026-04-20T09:00:00-03:00")

    def test_build_stage_plan_creates_three_dependent_actions(self) -> None:
        stage_cfg = {
            "name": "RECORDATORIO DE PROMESA",
            "template_id": 51765,
            "second_template_id": 51770,
            "second_wait_hours": 8,
            "final_wait_hours": 8,
            "next_stage_if_no_response": "C11:LOSE",
        }

        with patch.dict(os.environ, self.env, clear=False):
            fake_now = datetime.fromisoformat("2026-04-17T10:00:00-03:00")
            with patch.object(kestra_webhook_entrypoint.service, "get_now", return_value=fake_now):
                plan = kestra_webhook_entrypoint.build_stage_plan(
                    {"ID": "123", "STAGE_ID": "C11:UC_6KG2Z3"},
                    "C11:UC_6KG2Z3",
                    stage_cfg,
                )

        self.assertEqual(plan["plan_kind"], "double_send_then_move")
        self.assertEqual(len(plan["actions"]), 3)
        self.assertEqual(plan["actions"][0]["action_kind"], "send_or_noop")
        self.assertEqual(plan["actions"][1]["depends_on_key"], plan["actions"][0]["key"])
        self.assertEqual(plan["actions"][2]["depends_on_key"], plan["actions"][1]["key"])

    def test_pending_entrypoint_waits_if_dependency_is_pending(self) -> None:
        action = {
            "key": "bitrix_crm_negociaciones/deal/1/stage/C11_PREPARATION/action_2",
            "deal_id": "1",
            "expected_stage": "C11:PREPARATION",
            "action_kind": "send_or_noop",
            "template_id": "51770",
            "depends_on_key": "bitrix_crm_negociaciones/deal/1/stage/C11_PREPARATION/action_1",
            "due_at": "2026-04-17T10:00:00-03:00",
            "status": "pending",
        }
        dependency = {"status": "pending"}
        env = {
            "ACTION_JSON": __import__("json").dumps(action),
            "DEPENDENCY_JSON": __import__("json").dumps(dependency),
            "LOCAL_TZ": "America/Argentina/Buenos_Aires",
        }

        with patch.dict(os.environ, env, clear=False):
            result = kestra_pending_entrypoint.handle_pending_action()

        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "waiting_dependency")
        self.assertFalse(result["should_update"])

    def test_pending_entrypoint_cancels_when_dependency_failed(self) -> None:
        action = {
            "key": "bitrix_crm_negociaciones/deal/1/stage/C11_PREPARATION/action_2",
            "deal_id": "1",
            "expected_stage": "C11:PREPARATION",
            "action_kind": "send_or_noop",
            "template_id": "51770",
            "depends_on_key": "bitrix_crm_negociaciones/deal/1/stage/C11_PREPARATION/action_1",
            "due_at": "2026-04-17T10:00:00-03:00",
            "status": "pending",
        }
        dependency = {"status": "cancelled"}
        env = {
            "ACTION_JSON": __import__("json").dumps(action),
            "DEPENDENCY_JSON": __import__("json").dumps(dependency),
            "LOCAL_TZ": "America/Argentina/Buenos_Aires",
        }

        with patch.dict(os.environ, env, clear=False):
            result = kestra_pending_entrypoint.handle_pending_action()

        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "dependency_not_completed")
        self.assertTrue(result["should_update"])


if __name__ == "__main__":
    unittest.main()
