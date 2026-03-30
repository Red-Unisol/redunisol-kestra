from __future__ import annotations

from dataclasses import dataclass

import requests
import urllib3

from .config import AppConfig
from .logger import Logger


@dataclass(frozen=True)
class CoreSocioResult:
    bitrix_label: str
    is_member: bool | None
    reason: str


def resolve_member_status(
    cuil_digits: str,
    config: AppConfig,
    logger: Logger,
) -> CoreSocioResult:
    base_url = config.core_socio.base_url
    if not base_url:
        logger.info("Consulta de socio omitida: CORE_SOCIO_API_BASE_URL no configurada.")
        return CoreSocioResult(
            bitrix_label=config.member_status.unknown,
            is_member=None,
            reason="core_not_configured",
        )

    document = _extract_document(cuil_digits)
    if not document:
        logger.error("No se pudo derivar el documento desde el CUIL para consultar socio.")
        return CoreSocioResult(
            bitrix_label=config.member_status.unknown,
            is_member=None,
            reason="invalid_cuil",
        )

    if not config.core_socio.verify_tls:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    payload = {
        "cmd": f"[NroDoc]={document}",
        "tipo": "F.Module.SocioMutual",
        "campos": "NombreCompleto;NroSocio",
        "max": 1,
    }

    try:
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            f"{base_url}/api/Empresa/EvaluateList",
            json=payload,
            verify=config.core_socio.verify_tls,
            timeout=config.core_socio.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()
    except requests.exceptions.Timeout:
        logger.info(f"Consulta de socio agotada para documento {document}.")
        return CoreSocioResult(
            bitrix_label=config.member_status.unknown,
            is_member=None,
            reason="core_timeout",
        )
    except (requests.exceptions.RequestException, ValueError) as exc:
        logger.error(f"Fallo la consulta de socio en core: {exc}")
        return CoreSocioResult(
            bitrix_label=config.member_status.unknown,
            is_member=None,
            reason="core_error",
        )

    if isinstance(rows, list) and rows:
        return CoreSocioResult(
            bitrix_label=config.member_status.yes,
            is_member=True,
            reason="member_found",
        )

    if isinstance(rows, list):
        return CoreSocioResult(
            bitrix_label=config.member_status.no,
            is_member=False,
            reason="member_not_found",
        )

    logger.error("La consulta de socio devolvio un payload inesperado.")
    return CoreSocioResult(
        bitrix_label=config.member_status.unknown,
        is_member=None,
        reason="core_invalid_response",
    )


def _extract_document(cuil_digits: str) -> str:
    digits = "".join(ch for ch in str(cuil_digits or "") if ch.isdigit())
    if len(digits) != 11:
        return ""
    return digits[2:10]
