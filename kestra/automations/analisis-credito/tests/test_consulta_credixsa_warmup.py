from __future__ import annotations

from pathlib import Path
import sys
import unittest

FILES_ROOT = (
    Path(__file__).resolve().parent.parent / "files"
)
if str(FILES_ROOT) not in sys.path:
    sys.path.insert(0, str(FILES_ROOT))

from consulta_quiebra_credix.service import cache_key_for_name  # noqa: E402
from consulta_quiebra_credix.warmup_entrypoint import (  # noqa: E402
    CoreSolicitud,
    decode_daily_index,
    mark_daily_index,
    select_candidates,
)


class ConsultaCredixsaWarmupTests(unittest.TestCase):
    def test_decode_daily_index_resets_other_dates(self) -> None:
        index = decode_daily_index(
            '{"date":"2026-05-12","processed_oids":["1"],"cuils":["201"],"name_keys":["n"]}',
            "2026-05-13",
        )

        self.assertEqual(index["date"], "2026-05-13")
        self.assertEqual(index["processed_oids"], [])
        self.assertEqual(index["cuils"], [])
        self.assertEqual(index["name_keys"], [])

    def test_select_candidates_skips_already_processed_today(self) -> None:
        solicitudes = [
            CoreSolicitud("1", "2026-05-13", "Nueva", "20111111112", "11111111", "Uno"),
            CoreSolicitud("2", "2026-05-13", "Nueva", "20222222223", "22222222", "Dos"),
            CoreSolicitud("3", "2026-05-13", "Nueva", "", "33333333", "Tres"),
        ]
        index = {
            "date": "2026-05-13",
            "processed_oids": ["1"],
            "cuils": ["20222222223"],
            "name_keys": [],
        }

        selected = select_candidates(solicitudes, index, 5)

        self.assertEqual([item.oid for item in selected], ["3"])

    def test_mark_daily_index_records_cuil_and_name_key(self) -> None:
        index = {"date": "2026-05-13", "processed_oids": [], "cuils": [], "name_keys": []}
        solicitud = CoreSolicitud("10", "2026-05-13", "Nueva", "20123456783", "12345678", "Juan Perez")

        mark_daily_index(index, solicitud, {"nombre": "Juan Perez"})

        self.assertEqual(index["processed_oids"], ["10"])
        self.assertEqual(index["cuils"], ["20123456783"])
        self.assertEqual(index["name_keys"], [cache_key_for_name("Juan Perez")])


if __name__ == "__main__":
    unittest.main()
