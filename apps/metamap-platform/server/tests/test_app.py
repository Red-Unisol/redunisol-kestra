import hashlib
import hmac
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from metamap_server import __version__
from metamap_server.api import create_app
from metamap_server.config import AppSettings, BootstrapClient
from metamap_server.store_sql import DeliveryRow, MetamapWebhookReceiptRow
from metamap_server.workflow import ClientRole


class MetaMapServerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmpdir.name) / "metamap-server.sqlite3"
        self.settings = AppSettings(
            database_url=f"sqlite+pysqlite:///{self.database_path.as_posix()}",
            bootstrap_clients=[
                BootstrapClient(
                    client_id="validador-dev-1",
                    client_secret="secret-validador",
                    role=ClientRole.VALIDADOR,
                    display_name="Validador Dev 1",
                ),
                BootstrapClient(
                    client_id="transferencias-dev-1",
                    client_secret="secret-transferencias",
                    role=ClientRole.TRANSFERENCIAS_CELESOL,
                    display_name="Transferencias Dev 1",
                ),
            ],
            webhook_secret="MetaSecret1234Ab",
            bank_callback_token="bank-token",
        )
        self.client = TestClient(create_app(settings=self.settings))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.workflow_store.close()
        self._tmpdir.cleanup()

    def test_healthcheck(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "metamap-platform-server",
                "version": __version__,
            },
        )

    def test_metamap_completion_goes_directly_to_transferencias_flow(self) -> None:
        ingest = self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-100",
                metadata={"userId": "user-7"},
            )
        )
        self.assertEqual(ingest.status_code, 200)
        self.assertEqual(ingest.json()["processing_status"], "enqueued")
        self.assertEqual(
            ingest.json()["case"]["current_stage"],
            "approved_by_validador",
        )
        self.assertEqual(
            ingest.json()["case"]["resource_url"],
            "https://api.getmati.com/v2/verifications/verif-100",
        )

        queue_validador = self.client.get(
            "/api/v1/queues/validador",
            headers=self._client_headers(ClientRole.VALIDADOR),
        )
        self.assertEqual(queue_validador.status_code, 200)
        self.assertEqual(queue_validador.json()["cases"], [])

        queue_transferencias = self.client.get(
            "/api/v1/queues/transferencias_celesol",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
        )
        self.assertEqual(queue_transferencias.status_code, 200)
        self.assertEqual(len(queue_transferencias.json()["cases"]), 1)
        self.assertEqual(
            queue_transferencias.json()["cases"][0]["pending_roles"],
            ["transferencias_celesol"],
        )
        self.assertEqual(
            queue_transferencias.json()["cases"][0]["queue_payload"],
            {
                "verification_id": "verif-100",
                "resource_url": "https://api.getmati.com/v2/verifications/verif-100",
            },
        )

        transfer = self.client.post(
            "/api/v1/cases/verif-100/actions",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
            json={
                "role": "transferencias_celesol",
                "action": "transfer_submitted",
                "actor": "operador_a",
                "external_transfer_id": "trx-001",
            },
        )
        self.assertEqual(transfer.status_code, 200)
        self.assertEqual(
            transfer.json()["case"]["current_stage"],
            "transfer_submitted",
        )

        callback = self.client.post(
            "/api/v1/bank/callbacks/aviso-transferencia-cbu",
            headers=self._bank_headers(),
            json={
                "payload": {
                    "IdAviso": "cb-001",
                    "external_transfer_id": "trx-001",
                }
            },
        )
        self.assertEqual(callback.status_code, 200)
        self.assertFalse(callback.json()["duplicate"])
        self.assertEqual(
            callback.json()["case"]["current_stage"],
            "bank_confirmed",
        )

    def test_state_persists_across_app_restarts(self) -> None:
        self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-persist",
            )
        )

        restarted_client = TestClient(create_app(settings=self.settings))
        try:
            queue_transferencias = restarted_client.get(
                "/api/v1/queues/transferencias_celesol",
                headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
            )
            self.assertEqual(queue_transferencias.status_code, 200)
            self.assertEqual(len(queue_transferencias.json()["cases"]), 1)
            self.assertEqual(
                queue_transferencias.json()["cases"][0]["verification_id"],
                "verif-persist",
            )
        finally:
            restarted_client.close()
            restarted_client.app.state.workflow_store.close()

    def test_non_completed_event_is_logged_but_not_enqueued(self) -> None:
        response = self._post_metamap_webhook(
            self._metamap_payload(
                event_name="step_completed",
                verification_id="verif-step",
                step={
                    "status": 200,
                    "id": "document-reading",
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["processing_status"], "ignored")
        self.assertIsNone(response.json()["case"])

        queue_transferencias = self.client.get(
            "/api/v1/queues/transferencias_celesol",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
        )
        self.assertEqual(queue_transferencias.status_code, 200)
        self.assertEqual(queue_transferencias.json()["cases"], [])

        receipts = self._webhook_receipts()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].processing_status, "ignored")
        self.assertEqual(receipts[0].event_name, "step_completed")
        self.assertEqual(receipts[0].verification_id, "verif-step")

    def test_validador_cannot_act_on_auto_validated_case(self) -> None:
        self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-200",
            )
        )

        reject = self.client.post(
            "/api/v1/cases/verif-200/actions",
            headers=self._client_headers(ClientRole.VALIDADOR),
            json={
                "role": "validador",
                "action": "rejected",
                "actor": "operador_b",
                "notes": "No cumple criterios.",
            },
        )
        self.assertEqual(reject.status_code, 409)
        self.assertIn("no esta esperando revision", reject.json()["detail"])

        queue_transferencias = self.client.get(
            "/api/v1/queues/transferencias_celesol",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
        )
        self.assertEqual(queue_transferencias.status_code, 200)
        self.assertEqual(len(queue_transferencias.json()["cases"]), 1)

    def test_duplicate_bank_callback_is_idempotent(self) -> None:
        self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-300",
            )
        )
        self.client.post(
            "/api/v1/cases/verif-300/actions",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
            json={
                "role": "transferencias_celesol",
                "action": "transfer_submitted",
                "actor": "operador_a",
                "external_transfer_id": "trx-300",
            },
        )

        first = self.client.post(
            "/api/v1/bank/callbacks/aviso-transferencia-cbu",
            headers=self._bank_headers(),
            json={"payload": {"IdAviso": "dup-1", "external_transfer_id": "trx-300"}},
        )
        second = self.client.post(
            "/api/v1/bank/callbacks/aviso-transferencia-cbu",
            headers=self._bank_headers(),
            json={"payload": {"IdAviso": "dup-1", "external_transfer_id": "trx-300"}},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(second.json()["case"]["current_stage"], "bank_confirmed")

    def test_queue_items_are_abandoned_after_24_hours(self) -> None:
        self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-400",
            )
        )
        expired_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        store = self.client.app.state.workflow_store
        with store._session_factory() as session:
            delivery = session.execute(
                select(DeliveryRow).where(DeliveryRow.case_id == "verif-400")
            ).scalar_one()
            delivery.updated_at = expired_at
            session.commit()

        queue_transferencias = self.client.get(
            "/api/v1/queues/transferencias_celesol",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
        )
        self.assertEqual(queue_transferencias.status_code, 200)
        self.assertEqual(queue_transferencias.json()["cases"], [])

        case_response = self.client.get(
            "/api/v1/cases/verif-400",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
        )
        self.assertEqual(case_response.status_code, 200)
        self.assertEqual(
            case_response.json()["case"]["current_stage"],
            "manual_intervention_required",
        )
        self.assertEqual(
            case_response.json()["case"]["deliveries"][0]["status"],
            "abandoned",
        )

    def test_duplicate_verification_completed_does_not_reopen_transfer_queue(self) -> None:
        self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-410",
            )
        )
        self.client.post(
            "/api/v1/cases/verif-410/actions",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
            json={
                "role": "transferencias_celesol",
                "action": "transfer_submitted",
                "actor": "operador_a",
                "external_transfer_id": "trx-410",
            },
        )

        duplicate = self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-410",
            )
        )
        self.assertEqual(duplicate.status_code, 200)

        queue_transferencias = self.client.get(
            "/api/v1/queues/transferencias_celesol",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
        )
        self.assertEqual(queue_transferencias.status_code, 200)
        self.assertEqual(queue_transferencias.json()["cases"], [])

    def test_internal_webhook_receipts_endpoint_prunes_logs_older_than_one_week(self) -> None:
        self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_started",
                verification_id="verif-old-receipt",
            )
        )
        self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-recent-receipt",
            )
        )

        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        store = self.client.app.state.workflow_store
        with store._session_factory() as session:
            old_receipt = session.execute(
                select(MetamapWebhookReceiptRow).where(
                    MetamapWebhookReceiptRow.verification_id == "verif-old-receipt"
                )
            ).scalar_one()
            old_receipt.received_at = old_timestamp
            session.commit()

        response = self.client.get(
            "/api/v1/internal/metamap/webhook-receipts",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
        )
        self.assertEqual(response.status_code, 200)
        receipts = response.json()["receipts"]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["verification_id"], "verif-recent-receipt")
        self.assertEqual(receipts[0]["processing_status"], "enqueued")

    def test_queue_requires_valid_client_auth(self) -> None:
        response = self.client.get("/api/v1/queues/validador")
        self.assertEqual(response.status_code, 401)

        wrong_secret = self.client.get(
            "/api/v1/queues/validador",
            headers={
                "X-Client-Id": "validador-dev-1",
                "X-Client-Secret": "secret-invalido",
            },
        )
        self.assertEqual(wrong_secret.status_code, 401)

    def test_role_mismatch_is_forbidden(self) -> None:
        response = self.client.get(
            "/api/v1/queues/validador",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
        )
        self.assertEqual(response.status_code, 403)

    def test_webhook_signature_and_bank_callbacks_require_auth_when_configured(self) -> None:
        payload = self._metamap_payload(
            event_name="verification_completed",
            verification_id="verif-500",
        )
        webhook_response = self._post_metamap_webhook(payload, include_signature=False)
        self.assertEqual(webhook_response.status_code, 401)

        receipts = self._webhook_receipts()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].processing_status, "invalid_signature")
        self.assertFalse(receipts[0].signature_valid)

        self._post_metamap_webhook(
            self._metamap_payload(
                event_name="verification_completed",
                verification_id="verif-501",
            )
        )
        self.client.post(
            "/api/v1/cases/verif-501/actions",
            headers=self._client_headers(ClientRole.TRANSFERENCIAS_CELESOL),
            json={
                "role": "transferencias_celesol",
                "action": "transfer_submitted",
                "actor": "operador_a",
                "external_transfer_id": "trx-501",
            },
        )

        callback_response = self.client.post(
            "/api/v1/bank/callbacks/aviso-transferencia-cbu",
            json={"payload": {"IdAviso": "cb-501", "external_transfer_id": "trx-501"}},
        )
        self.assertEqual(callback_response.status_code, 401)

    def _client_headers(self, role: ClientRole) -> dict[str, str]:
        if role == ClientRole.VALIDADOR:
            return {
                "X-Client-Id": "validador-dev-1",
                "X-Client-Secret": "secret-validador",
            }
        return {
            "X-Client-Id": "transferencias-dev-1",
            "X-Client-Secret": "secret-transferencias",
        }

    def _bank_headers(self) -> dict[str, str]:
        return {"X-Bank-Callback-Token": "bank-token"}

    def _metamap_payload(
        self,
        *,
        event_name: str,
        verification_id: str,
        metadata: dict | None = None,
        **extra: object,
    ) -> dict:
        payload = {
            "eventName": event_name,
            "resource": f"https://api.getmati.com/v2/verifications/{verification_id}",
            "flowId": "flow-dev-1",
            "timestamp": "2026-04-07T15:00:00.000Z",
            "metadata": metadata or {},
        }
        payload.update(extra)
        return payload

    def _post_metamap_webhook(
        self,
        payload: dict,
        *,
        include_signature: bool = True,
    ):
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        headers = {
            "Content-Type": "application/json",
        }
        if include_signature:
            headers["x-signature"] = hmac.new(
                self.settings.webhook_secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        return self.client.post(
            "/api/v1/metamap/webhooks",
            content=body,
            headers=headers,
        )

    def _webhook_receipts(self) -> list[MetamapWebhookReceiptRow]:
        store = self.client.app.state.workflow_store
        with store._session_factory() as session:
            return session.execute(
                select(MetamapWebhookReceiptRow).order_by(MetamapWebhookReceiptRow.id)
            ).scalars().all()
