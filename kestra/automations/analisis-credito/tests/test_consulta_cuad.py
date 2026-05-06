from __future__ import annotations

from pathlib import Path
import sys
import unittest

FILES_ROOT = Path(__file__).resolve().parent.parent / "files"
if str(FILES_ROOT) not in sys.path:
    sys.path.insert(0, str(FILES_ROOT))

from consulta_cuad.service import (  # noqa: E402
    SearchRequest,
    build_error_result,
    build_not_found_result,
    build_output_payload,
    build_success_result,
    decodificar_respuesta_http,
    es_respuesta_sin_resultado,
    normalize_cuil,
    obtener_frames,
    parse_search_request,
    parsear_totales_cuad,
)


class ConsultaCuadTests(unittest.TestCase):
    class StubLocator:
        def __init__(self, count: int) -> None:
            self._count = count

        def count(self) -> int:
            return self._count

    class StubFrame:
        def __init__(self, url: str, selectors: dict[str, int], *, name: str = "") -> None:
            self.url = url
            self.name = name
            self._selectors = selectors

        def locator(self, selector: str) -> "ConsultaCuadTests.StubLocator":
            return ConsultaCuadTests.StubLocator(self._selectors.get(selector, 0))

    class StubPage:
        def __init__(self, frames: list["ConsultaCuadTests.StubFrame"]) -> None:
            self.frames = frames

    def test_parse_search_request_normalizes_cuil(self) -> None:
        request = parse_search_request({"cuil": "23-33312151-4"})

        self.assertEqual(request, SearchRequest(cuil="23333121514"))

    def test_parse_search_request_accepts_plain_string(self) -> None:
        request = parse_search_request("23-33312151-4")

        self.assertEqual(request.cuil, "23333121514")

    def test_normalize_cuil_requires_eleven_digits(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 11 digits"):
            normalize_cuil("1234")

    def test_parsear_totales_cuad_extracts_expected_fields(self) -> None:
        html = (
            "<script>parent.setTotales("
            "'100','90','80','70','60%','50','40%','30','20%','10'"
            ");</script>"
        )

        data = parsear_totales_cuad(html)

        self.assertEqual(
            data,
            {
                "bruto": "100",
                "neto": "90",
                "cupo": "80",
                "afectado": "70",
                "porcentaje_afectado": "60%",
                "precancelado": "50",
                "porcentaje_precancelado": "40%",
                "disponible": "30",
                "porcentaje_disponible": "20%",
                "deuda": "10",
            },
        )

    def test_es_respuesta_sin_resultado_detects_empty_case(self) -> None:
        html = "foo parent.Emp_Id = -1 bar parent.Display('N') baz"
        self.assertTrue(es_respuesta_sin_resultado(html))

    def test_build_output_payload_for_success_includes_serialized_response(self) -> None:
        result = build_success_result(
            SearchRequest(cuil="23333121514"),
            {
                "bruto": "100",
                "neto": "90",
                "cupo": "80",
                "afectado": "70",
                "porcentaje_afectado": "60%",
                "precancelado": "50",
                "porcentaje_precancelado": "40%",
                "disponible": "30",
                "porcentaje_disponible": "20%",
                "deuda": "10",
            },
            captcha_attempts=3,
        )

        output = build_output_payload(result)

        self.assertTrue(output["ok"])
        self.assertTrue(output["found"])
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["captcha_attempts"], 3)
        self.assertIn('"source":"cuad_movimiento"', output["response_json"])
        self.assertEqual(output["data_json"], '{"bruto":"100","neto":"90","cupo":"80","afectado":"70","porcentaje_afectado":"60%","precancelado":"50","porcentaje_precancelado":"40%","disponible":"30","porcentaje_disponible":"20%","deuda":"10"}')

    def test_build_output_payload_for_not_found_keeps_ok_true(self) -> None:
        result = build_not_found_result(
            SearchRequest(cuil="23333121514"),
            captcha_attempts=2,
        )

        output = build_output_payload(result)

        self.assertTrue(output["ok"])
        self.assertFalse(output["found"])
        self.assertEqual(output["status"], "sin_resultado")
        self.assertEqual(output["data_json"], "{}")

    def test_build_output_payload_for_error_keeps_error_text(self) -> None:
        result = build_error_result(
            SearchRequest(cuil="23333121514"),
            "sesion_invalida",
            "La sesion vencio",
            captcha_attempts=1,
        )

        output = build_output_payload(result)

        self.assertFalse(output["ok"])
        self.assertEqual(output["status"], "sesion_invalida")
        self.assertEqual(output["error"], "La sesion vencio")

    def test_decodificar_respuesta_http_falls_back_to_cp1252(self) -> None:
        class StubResponse:
            headers = {"content-type": "text/html"}

            def body(self):
                return b"Identificaci\xf3n"

        self.assertEqual(decodificar_respuesta_http(StubResponse()), "Identificaci\u00f3n")

    def test_obtener_frames_falls_back_to_selector_detection(self) -> None:
        login_frame = self.StubFrame(
            "https://www.santafe.gov.ar/cuad/",
            {
                "#user": 1,
                "#password": 1,
                "#txtCaptcha": 1,
                "img": 1,
            },
            name="main",
        )
        other_frame = self.StubFrame(
            "https://www.santafe.gov.ar/otra",
            {"img": 0},
            name="other",
        )
        page = self.StubPage([login_frame, other_frame])

        detected_login_frame, detected_captcha_frame = obtener_frames(page)

        self.assertIs(detected_login_frame, login_frame)
        self.assertIs(detected_captcha_frame, login_frame)


if __name__ == "__main__":
    unittest.main()
