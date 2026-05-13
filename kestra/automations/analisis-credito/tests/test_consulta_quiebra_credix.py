from __future__ import annotations

from pathlib import Path
import sys
import unittest

FILES_ROOT = (
    Path(__file__).resolve().parent.parent / "files"
)
if str(FILES_ROOT) not in sys.path:
    sys.path.insert(0, str(FILES_ROOT))

from consulta_quiebra_credix.service import (  # noqa: E402
    SearchRequest,
    build_cache_entry,
    build_cache_lookup,
    _find_detail_next_control,
    _normalize_report_section,
    _refresh_online_updates_if_available,
    build_error_result,
    build_output_payload,
    build_single_result,
    cache_key_for_cuil,
    cache_key_for_name,
    cached_result_if_fresh,
    find_cached_result_in_payloads,
    _is_detail_summary_page,
    normalize_cuit,
    normalize_name,
    parse_search_request,
)


class ConsultaQuiebraCredixTests(unittest.TestCase):
    def test_parse_search_request_normalizes_fields(self) -> None:
        request = parse_search_request(
            {
                "cuit": "20-12345678-3",
                "nombre": "  Juan   Perez  ",
            }
        )

        self.assertEqual(request.cuit, "20123456783")
        self.assertEqual(request.nombre, "Juan Perez")

    def test_parse_search_request_accepts_plain_string_as_cuit(self) -> None:
        request = parse_search_request("20-12345678-3")

        self.assertEqual(request.cuit, "20123456783")
        self.assertEqual(request.nombre, "")

    def test_parse_search_request_requires_at_least_one_criterion(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one of 'cuit' or 'nombre' is required."):
            parse_search_request({"cuit": "", "nombre": " "})

    def test_build_output_payload_for_single_result_preserves_legacy_shape(self) -> None:
        request = SearchRequest(cuit="20123456783", nombre="Juan Perez")
        result = build_single_result(
            request,
            [
                {
                    "index": 1,
                    "title": "Datos Filiatorios",
                    "source": "",
                    "headers": [],
                    "rows": [["Cuil", "20-12345678-3"]],
                    "records": [{"Cuil": "20-12345678-3"}],
                    "text": "Datos Filiatorios Cuil 20-12345678-3",
                }
            ],
        )

        output = build_output_payload(result)

        self.assertTrue(output["ok"])
        self.assertEqual(output["status"], "single")
        self.assertEqual(
            output["response_json"],
            '{"status":"single","data":[{"index":1,"title":"Datos Filiatorios","source":"","headers":[],"rows":[["Cuil","20-12345678-3"]],"records":[{"Cuil":"20-12345678-3"}],"text":"Datos Filiatorios Cuil 20-12345678-3"}]}',
        )

    def test_normalize_report_section_builds_key_value_records(self) -> None:
        section = _normalize_report_section(
            {
                "index": 5,
                "text": "Datos Filiatorios Cuil 20-12345678-3 Documento 12.345.678",
                "rows": [
                    {"cells": [{"text": "Datos Filiatorios", "header": True}], "has_header": True},
                    {
                        "cells": [
                            {"text": "Cuil", "header": True},
                            {"text": "20-12345678-3", "header": False},
                        ],
                        "has_header": True,
                    },
                    {
                        "cells": [
                            {"text": "Documento", "header": True},
                            {"text": "12.345.678", "header": False},
                        ],
                        "has_header": True,
                    },
                ],
            }
        )

        self.assertEqual(section["index"], 5)
        self.assertEqual(section["title"], "Datos Filiatorios")
        self.assertEqual(
            section["records"],
            [{"Cuil": "20-12345678-3"}, {"Documento": "12.345.678"}],
        )

    def test_build_single_result_prefers_scraped_name_when_provided(self) -> None:
        request = SearchRequest(cuit="26967652", nombre="")

        result = build_single_result(
            request,
            [],
            nombre="GORONDON MARCELA VIVIANA",
        )

        self.assertEqual(result["nombre"], "GORONDON MARCELA VIVIANA")

    def test_build_output_payload_for_errors_sets_error_response(self) -> None:
        result = build_error_result(None, "boom")

        output = build_output_payload(result)

        self.assertFalse(output["ok"])
        self.assertEqual(output["status"], "error")
        self.assertEqual(output["response_json"], '{"status":"error","error":"boom"}')
        self.assertEqual(output["error"], "boom")

    def test_normalizers_strip_noise(self) -> None:
        self.assertEqual(normalize_cuit("20-12345678-3"), "20123456783")
        self.assertEqual(normalize_name("  Maria   del  Mar "), "Maria del Mar")

    def test_cache_lookup_builds_cuil_and_name_keys(self) -> None:
        lookup = build_cache_lookup({"cuit": "20-12345678-3", "nombre": "  José  Pérez "})

        self.assertEqual(lookup["cuil_cache_key"], "credixsa.cuil.20123456783")
        self.assertEqual(lookup["name_cache_key"], cache_key_for_name("Jose Perez"))
        self.assertNotEqual(lookup["name_cache_lookup_key"], "credixsa.cache.lookup.none")

    def test_cache_entry_round_trips_when_fresh(self) -> None:
        result = build_single_result(
            SearchRequest(cuit="20123456783", nombre=""),
            [{"title": "Datos Filiatorios", "rows": [["Cuil", "20-12345678-3"]]}],
            cuit="20123456783",
            nombre="Juan Perez",
        )

        entry = build_cache_entry(result)
        self.assertIsNotNone(entry)
        cached = cached_result_if_fresh(entry)

        self.assertIsNotNone(cached)
        self.assertEqual(cached["status"], "single")
        self.assertEqual(cached["cuit"], "20123456783")

    def test_cache_key_for_name_is_accent_insensitive(self) -> None:
        self.assertEqual(cache_key_for_name("José   Pérez"), cache_key_for_name("jose perez"))
        self.assertEqual(cache_key_for_cuil("20-12345678-3"), "credixsa.cuil.20123456783")

    def test_find_cached_result_in_payloads_rejects_mismatched_name_hit(self) -> None:
        result = build_single_result(
            SearchRequest(cuit="20999999999", nombre=""),
            [{"title": "Datos Filiatorios", "rows": [["Cuil", "20-99999999-9"]]}],
            cuit="20999999999",
            nombre="Juan Perez",
        )
        cache_entry = build_cache_entry(result)

        cached = find_cached_result_in_payloads(
            SearchRequest(cuit="20123456783", nombre="Juan Perez"),
            None,
            cache_entry,
        )

        self.assertIsNone(cached)

    def test_find_cached_result_in_payloads_returns_cuil_hit(self) -> None:
        result = build_single_result(
            SearchRequest(cuit="20123456783", nombre=""),
            [{"title": "Datos Filiatorios", "rows": [["Cuil", "20-12345678-3"]]}],
            cuit="20123456783",
            nombre="Juan Perez",
        )
        cache_entry = build_cache_entry(result)

        cached = find_cached_result_in_payloads(
            SearchRequest(cuit="20123456783", nombre=""),
            cache_entry,
            None,
        )

        self.assertIsNotNone(cached)
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(cached["cache_source"], "cuil")

    def test_is_detail_summary_page_detects_credix_detail_view(self) -> None:
        class BodyLocator:
            def inner_text(self, timeout=None):
                return "Resumen (*)\nDatos Filiatorios\nDatos Fiscales"

        class StubPage:
            url = "https://www.credixsa.com/nuevo/con_cuit3.php"

            def locator(self, selector):
                self.last_selector = selector
                return BodyLocator()

        self.assertTrue(_is_detail_summary_page(StubPage()))

    def test_find_detail_next_control_accepts_visible_button_with_text(self) -> None:
        class StubLocator:
            def __init__(self, visible):
                self.visible = visible
                self.first = self

            def count(self):
                return 1 if self.visible else 0

            def is_visible(self):
                return self.visible

        class StubPage:
            def locator(self, selector, has_text=None):
                if selector == "button" and has_text == "Siguiente":
                    return StubLocator(True)
                return StubLocator(False)

        self.assertIsNotNone(_find_detail_next_control(StubPage()))

    def test_refresh_online_updates_clicks_update_all_when_available(self) -> None:
        class StubLocator:
            def __init__(self, *, visible=True, text="", enabled=True):
                self.visible = visible
                self.text = text
                self.enabled = enabled
                self.clicked = False
                self.first = self

            def count(self):
                return 1 if self.visible else 0

            def is_visible(self):
                return self.visible

            def is_enabled(self):
                return self.enabled

            def click(self):
                self.clicked = True

            def inner_text(self, timeout=None):
                return self.text

        class StubPage:
            url = "https://www.credixsa.com/nuevo/con_cuit_pde_ajax.php"

            def __init__(self):
                self.update_all = StubLocator()
                self.next_button = StubLocator(enabled=True)
                self.body = StubLocator(text="PASO 3: Actualizaciones en linea")

            def locator(self, selector, has_text=None):
                if selector == "#procesar_todo_auto":
                    return self.update_all
                if selector == "#btn_siguiente":
                    return self.next_button
                if selector == "body":
                    return self.body
                return StubLocator(visible=False)

            def wait_for_load_state(self, state):
                return None

        config = type(
            "Config",
            (),
            {"timeout_ms": 1000, "debug_enabled": False},
        )()
        page = StubPage()

        _refresh_online_updates_if_available(
            page,
            config,
            SearchRequest(cuit="20123456783", nombre=""),
        )

        self.assertTrue(page.update_all.clicked)


if __name__ == "__main__":
    unittest.main()
