import datetime as _dt
from pathlib import Path
import sys
import unittest
from decimal import Decimal

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from exportador_bancor.core import (
    Attempt,
    AttemptSummary,
    ConsolidatedPlanilla,
    classify_planillas,
    compute_shots,
    determine_planilla_outcome,
    sort_api_rows,
)


class _PlanillaFactory:
    """Helper to build consistent ConsolidatedPlanilla instances for tests."""

    def __init__(self) -> None:
        self.default_attempts = AttemptSummary.empty()

    def build(
        self,
        *,
        loan_status: str = "old",
        attempts: AttemptSummary | None = None,
        outstanding: str = "100000.00",
        installment: str = "50000.00",
        cbu: str = "0200123412341234567890",
        caja40: int | None = 10,
    ) -> ConsolidatedPlanilla:
        attempt_summary = attempts or AttemptSummary.empty()
        caja40_raw = "" if caja40 is None else str(caja40)
        return ConsolidatedPlanilla(
            planilla="998668",
            nro_socio="5003000130",
            nro_doc="20111222",
            linea_codigo="LN01",
            cbu=cbu,
            fecha_emision=_dt.date(2025, 9, 1),
            total_installments=12,
            outstanding_amount=Decimal(outstanding),
            installment_value=Decimal(installment),
            caja40_raw=caja40_raw,
            caja40_int=caja40,
            sucursal_banco="001",
            nro_cuenta_banco="1234567890",
            latest_fecha=_dt.date(2025, 10, 10),
            latest_nro_cuota=2,
            attempts=attempt_summary,
            loan_status="new" if loan_status == "new" else "old",
        )


class ComputeShotsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = _PlanillaFactory()

    def test_new_loan_single_shot(self) -> None:
        planilla = self.factory.build(
            loan_status="new",
            attempts=AttemptSummary.empty(),
            outstanding="60000.00",
            installment="40000.00",
        )
        shots = compute_shots(planilla)
        self.assertEqual(shots, [Decimal("60000.00")])

    def test_old_loan_with_entered_attempts(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        attempts.register(Attempt(amount=Decimal("8000.00"), entered=False, response="R10"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="120000.00",
            installment="40000.00",
        )
        shots = compute_shots(planilla)
        self.assertEqual(len(shots), 6)
        self.assertTrue(all(value == Decimal("10000.00") for value in shots))
        self.assertEqual(sum(shots), Decimal("60000.00"))

    def test_shots_are_rounded_to_thousands(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("9999.00"), entered=True, response="COB"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="25762.00",
            installment="40000.00",
        )
        shots = compute_shots(planilla)
        self.assertEqual(shots, [Decimal("10000.00"), Decimal("10000.00"), Decimal("5762.00")])

    def test_small_remainder_merges_with_first_shot(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("9000.00"), entered=True, response="COB"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="36400.00",
            installment="40000.00",
        )
        shots = compute_shots(planilla)
        self.assertEqual(shots, [Decimal("9400.00"), Decimal("9000.00"), Decimal("9000.00"), Decimal("9000.00")])

    def test_small_remainder_adjusts_from_previous_shot_when_first_capped(self) -> None:
        planilla = ConsolidatedPlanilla(
            planilla="TEST",
            nro_socio="5003000130",
            nro_doc="20111222",
            linea_codigo="LN01",
            cbu="0200123412341234567890",
            fecha_emision=_dt.date(2025, 9, 1),
            total_installments=12,
            outstanding_amount=Decimal("160300.00"),
            installment_value=Decimal("160300.00"),
            caja40_raw="10",
            caja40_int=10,
            sucursal_banco="001",
            nro_cuenta_banco="1234567890",
            latest_fecha=_dt.date(2025, 10, 10),
            latest_nro_cuota=2,
            attempts=AttemptSummary.empty(),
            loan_status="new",
        )
        shots = compute_shots(planilla)
        self.assertEqual(shots, [Decimal("80000.00"), Decimal("79300.00"), Decimal("1000.00")])

    def test_old_loan_without_entered_attempts(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("20000.00"), entered=False, response="R10"))
        attempts.register(Attempt(amount=Decimal("15000.00"), entered=False, response="R10"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="120000.00",
            installment="40000.00",
        )
        shots = compute_shots(planilla)
        self.assertEqual(len(shots), 8)
        self.assertEqual(shots[0], Decimal("8000.00"))
        self.assertEqual(sum(shots), Decimal("60000.00"))

    def test_shot_cap_applied(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="300000.00",
            installment="100000.00",
        )
        shots = compute_shots(planilla)
        self.assertEqual(len(shots), 10)
        self.assertTrue(all(value == Decimal("10000.00") for value in shots))
        self.assertEqual(sum(shots), Decimal("100000.00"))

    def test_trim_uses_cap_when_sufficient(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="200000.00",
            installment="80000.00",
        )
        shots = compute_shots(planilla)
        self.assertEqual(len(shots), 10)
        self.assertTrue(all(value == Decimal("10000.00") for value in shots))
        self.assertEqual(sum(shots), Decimal("100000.00"))

    def test_trim_uses_installment_split_when_cap_too_small(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="500000.00",
            installment="200000.00",
        )
        shots = compute_shots(planilla)
        self.assertEqual(len(shots), 10)
        self.assertTrue(all(value == Decimal("20000.00") for value in shots))
        self.assertEqual(sum(shots), Decimal("200000.00"))

    def test_max_shots_for_two_planillas(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="500000.00",
            installment="200000.00",
        )
        planilla.planillas_per_socio = 2
        shots = compute_shots(planilla)
        self.assertEqual(len(shots), 5)
        self.assertTrue(all(value == Decimal("40000.00") for value in shots))
        self.assertEqual(sum(shots), Decimal("200000.00"))

    def test_max_shots_for_three_or_more_planillas(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="150000.00",
            installment="60000.00",
        )
        planilla.planillas_per_socio = 3
        shots = compute_shots(planilla)
        self.assertEqual(len(shots), 3)
        self.assertTrue(all(value == Decimal("20000.00") for value in shots))
        self.assertEqual(sum(shots), Decimal("60000.00"))

        larger_planilla = self.factory.build(
            loan_status="old",
            attempts=attempts,
            outstanding="500000.00",
            installment="200000.00",
        )
        larger_planilla.planillas_per_socio = 4
        larger_shots = compute_shots(larger_planilla)
        self.assertEqual(len(larger_shots), 3)
        self.assertAlmostEqual(float(sum(larger_shots)), 200000.0, places=2)


class ClassificationOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = _PlanillaFactory()

    def test_forbidden_response_goes_to_rechazados(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=False, response="R8"))
        planilla = self.factory.build(attempts=attempts, outstanding="50000.00", installment="30000.00")
        outcome = determine_planilla_outcome(planilla, arrastre_mode=False)
        self.assertEqual(outcome.category, "bancor-pero-no-enviamos")
        self.assertEqual(outcome.reason, "respuesta_excel_no_permitida")
        self.assertEqual(outcome.estado_cbu, "Regular")
        self.assertEqual(outcome.caja40_clasificacion, "GRUPOS 1-20")

    def test_special_cbu_without_attempts_goes_to_revisar(self) -> None:
        planilla = self.factory.build(cbu="000123456789", attempts=AttemptSummary.empty(), loan_status="new")
        outcome = determine_planilla_outcome(planilla, arrastre_mode=False)
        self.assertEqual(outcome.category, "posiblemente-bancor")
        self.assertEqual(outcome.estado_cbu, "Especial")

    def test_cbu_outside_rules_is_discarded(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        planilla = self.factory.build(cbu="123456789000", attempts=attempts)
        outcome = determine_planilla_outcome(planilla, arrastre_mode=False)
        self.assertEqual(outcome.category, "no-bancor")
        self.assertEqual(outcome.estado_cbu, "Fuera de Regla")

    def test_discarded_entries_are_exported(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("5000.00"), entered=True, response="COB"))
        planilla = self.factory.build(cbu="123456789000", attempts=attempts)
        outputs, discarded_entries, report_rows = classify_planillas(
            [planilla], _dt.date(2025, 10, 16), dev_mode=True, arrastre_mode=False
        )
        self.assertIn("no-bancor", outputs)
        self.assertEqual(len(outputs["no-bancor"]), 1)
        self.assertEqual(outputs["no-bancor"][0]["NROPLAN"], planilla.planilla)
        self.assertEqual(discarded_entries[0]["planilla"], planilla.planilla)
        self.assertEqual(len(report_rows), 1)
        row = report_rows[0]
        self.assertEqual(row["Clasificación Final"], "No Bancor")
        self.assertEqual(row["Clasificación CBU"], "No Bancor")
        self.assertEqual(row["Mes Actual - Monto Total"], Decimal("0.00"))
        self.assertEqual(row["Mes Actual - Disparo Máximo"], Decimal("0.00"))
        self.assertEqual(row["Mes Pasado - Total Enviado"], Decimal("5000.00"))
        self.assertEqual(row["Mes Actual - ¿Se Envía?"], "NO")
        self.assertEqual(row["Mes Pasado - ¿Se Envió?"], "SI")
        self.assertEqual(row["Clasificación Caja40"], "GRUPOS 1-20")
        self.assertEqual(row["¿Es Nuevo o Viejo?"], "Viejo")
        self.assertEqual(row["Mes Actual - Detalle Disparos"], "")
        self.assertEqual(row["Mes Pasado - Detalle Disparos"], "5000.00 (COB)")
        self.assertEqual(row["Mes Pasado - Total Cobrado"], Decimal("5000.00"))
        self.assertEqual(row["Mes Pasado - Total sin Cobrar"], Decimal("0.00"))
        self.assertEqual(row["Mes Pasado - Máximo Cobrado"], Decimal("5000.00"))

    def test_arrastre_toggle_affects_caja40(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        caja_20_planilla = self.factory.build(caja40=5, attempts=attempts)
        caja_arrastre_planilla = self.factory.build(caja40=60, attempts=attempts)

        outcome_main_mode = determine_planilla_outcome(caja_20_planilla, arrastre_mode=False)
        outcome_blocked = determine_planilla_outcome(caja_arrastre_planilla, arrastre_mode=False)

        self.assertEqual(outcome_main_mode.category, "a-enviar")
        self.assertTrue(outcome_main_mode.shots)
        self.assertEqual(outcome_main_mode.caja40_clasificacion, "GRUPOS 1-20")
        self.assertEqual(outcome_blocked.category, "bancor-pero-no-enviamos")
        self.assertEqual(outcome_blocked.reason, "caja40_no_enviar")
        self.assertEqual(outcome_blocked.caja40_clasificacion, "ARRASTRE")

        outcome_arrastre_mode = determine_planilla_outcome(caja_arrastre_planilla, arrastre_mode=True)
        self.assertEqual(outcome_arrastre_mode.category, "a-enviar")
        self.assertTrue(outcome_arrastre_mode.shots)
        self.assertEqual(outcome_arrastre_mode.caja40_clasificacion, "ARRASTRE")

    def test_report_rows_include_shot_and_attempt_totals(self) -> None:
        attempts = AttemptSummary.empty()
        attempts.register(Attempt(amount=Decimal("10000.00"), entered=True, response="COB"))
        attempts.register(Attempt(amount=Decimal("4000.00"), entered=False, response="R10"))
        planilla = self.factory.build(attempts=attempts, outstanding="120000.00", installment="40000.00")
        outputs, discarded_entries, report_rows = classify_planillas(
            [planilla], _dt.date(2025, 10, 16), dev_mode=False, arrastre_mode=False
        )
        self.assertFalse(discarded_entries)
        self.assertEqual(len(outputs["a-enviar"]), 6)
        row = report_rows[0]
        self.assertEqual(row["Clasificación Final"], "A Enviar")
        self.assertEqual(row["Mes Actual - ¿Se Envía?"], "SI")
        self.assertEqual(row["Mes Actual - Monto Total"], Decimal("60000.00"))
        self.assertEqual(row["Mes Actual - Disparo Máximo"], Decimal("10000.00"))
        self.assertEqual(row["Mes Pasado - ¿Se Envió?"], "SI")
        self.assertEqual(row["Mes Pasado - Total Enviado"], Decimal("14000.00"))
        self.assertEqual(row["Mes Actual - Cantidad Disparos"], 6)
        self.assertEqual(row["Clasificación Caja40"], "GRUPOS 1-20")
        self.assertEqual(row["Clasificación CBU"], "Bancor")
        self.assertEqual(row["¿Es Nuevo o Viejo?"], "Viejo")
        self.assertEqual(row["Mes Actual - Detalle Disparos"], ", ".join(["10000.00"] * 6))
        self.assertEqual(row["Mes Pasado - Detalle Disparos"], "10000.00 (COB), 4000.00 (R10)")
        self.assertEqual(row["Mes Pasado - Total Cobrado"], Decimal("10000.00"))
        self.assertEqual(row["Mes Pasado - Total sin Cobrar"], Decimal("4000.00"))
        self.assertEqual(row["Mes Pasado - Máximo Cobrado"], Decimal("10000.00"))



    def test_report_planillas_match_unique_exports(self) -> None:
        factory = _PlanillaFactory()

        # a-enviar planilla
        attempts_send = AttemptSummary.empty()
        attempts_send.register(Attempt(amount=Decimal('10000.00'), entered=True, response='COB'))
        planilla_send = factory.build(attempts=attempts_send)
        planilla_send.planilla = '100'

        # bancor-pero-no-enviamos planilla
        attempts_block = AttemptSummary.empty()
        attempts_block.register(Attempt(amount=Decimal('10000.00'), entered=False, response='R8'))
        planilla_block = factory.build(attempts=attempts_block)
        planilla_block.planilla = '200'

        # no-bancor planilla
        attempts_no = AttemptSummary.empty()
        attempts_no.register(Attempt(amount=Decimal('10000.00'), entered=True, response='COB'))
        planilla_no = factory.build(cbu='123456789000', attempts=attempts_no)
        planilla_no.planilla = '300'

        # posiblemente-bancor planilla
        planilla_pos = factory.build(cbu='000123456789', attempts=AttemptSummary.empty(), loan_status='new')
        planilla_pos.planilla = '400'

        outputs, discarded_entries, report_rows = classify_planillas(
            [planilla_send, planilla_block, planilla_no, planilla_pos],
            _dt.date(2025, 10, 31),
            dev_mode=False,
            arrastre_mode=False,
        )

        self.assertFalse(discarded_entries)

        base_categories = {'a-enviar', 'bancor-pero-no-enviamos', 'no-bancor', 'posiblemente-bancor'}
        unique_planillas = set()
        for category in base_categories:
            for record in outputs[category]:
                unique_planillas.add(record['NROPLAN'])

        self.assertEqual(len(unique_planillas), len(report_rows))
        self.assertEqual(unique_planillas, {row['Número Planilla'] for row in report_rows})
class SortApiRowsTests(unittest.TestCase):
    def _make_row(self, planilla: int, nro_cuota: int, fecha: str, saldo: float) -> list:
        return [
            "5003000000",
            planilla,
            12,
            "LN01",
            "0200123412341234567890",
            "20111222",
            "2025-01-01",
            saldo,
            nro_cuota,
            fecha,
            "001",
            "1234567890",
            "10",
            40000.0,
        ]

    def test_rows_are_ordered_by_planilla_and_cuota(self) -> None:
        unsorted_rows = [
            self._make_row(200, 2, "2025-02-01", 1500.0),
            self._make_row(200, 1, "2025-01-01", 2000.0),
            self._make_row(100, 3, "2025-03-01", 1000.0),
        ]
        sorted_rows = sort_api_rows(unsorted_rows)
        planillas = [str(row[1]) for row in sorted_rows]
        cuotas = [row[8] for row in sorted_rows]
        self.assertEqual(planillas, ["100", "200", "200"])
        self.assertEqual(cuotas, [3, 1, 2])


if __name__ == "__main__":
    unittest.main()
