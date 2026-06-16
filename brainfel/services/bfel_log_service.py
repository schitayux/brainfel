# brainfel/brainfel/services/bfel_log_service.py
from __future__ import annotations

import json
import frappe


def _to_json(value):
    """
    Convierte cualquier valor a JSON string seguro para guardar en campos Text / Long Text.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _map_environment(settings) -> str:
    """
    Mapea el environment EXACTAMENTE a las opciones del Select en BFEL Log.
    Opciones válidas:
        - Test
        - Prod
    """
    if getattr(settings, "test_mode", 0):
        return "Test"
    return "Prod"


def create_bfel_log(
    *,
    settings,
    document,
    action: str,
    status: str,
    request_xml: str | None = None,
    response_data=None,
    raw_text: str | None = None,
    message: str | None = None,
    http_status: int | None = None,
    elapsed_ms: int | None = None,
    request_id: str | None = None,
    uuid: str | None = None,
):
    """
    Crea un registro en BFEL Log.
    - Compatible con documentos Submitted
    - Compatible con Frappe v15
    - Respeta Selects (environment)
    """

    log = frappe.new_doc("BFEL Log")

    # ------------------------------------------------------------------
    # Documento origen
    # ------------------------------------------------------------------
    log.document_type = document.doctype
    log.document_name = document.name
    log.company = document.company

    # ------------------------------------------------------------------
    # Acción / estado
    # ------------------------------------------------------------------
    log.action = action
    log.status = status

    # ------------------------------------------------------------------
    # Identificadores FEL
    # ------------------------------------------------------------------
    if uuid:
        log.uuid = uuid

    if request_id:
        log.request_id = request_id

    # ------------------------------------------------------------------
    # Payloads
    # ------------------------------------------------------------------
    if request_xml:
        log.request_payload = request_xml

    if response_data is not None:
        log.response_payload = _to_json(response_data)

    # ------------------------------------------------------------------
    # Error / mensaje
    # ------------------------------------------------------------------
    if message and status != "Success":
        log.error_message = message

    # ------------------------------------------------------------------
    # HTTP metadata
    # ------------------------------------------------------------------
    if http_status is not None:
        log.http_status = http_status

    if elapsed_ms is not None:
        log.elapsed_ms = elapsed_ms

    # ------------------------------------------------------------------
    # Contexto BFEL Settings
    # ------------------------------------------------------------------
    if settings:
        log.bfel_settings = settings.name
        log.certifier = getattr(settings, "certifier", None) or "Digifact"
        log.environment = _map_environment(settings)
        log.responsedata = getattr(settings, "responsedata", None)

    # ------------------------------------------------------------------
    # Campos crudos
    # ------------------------------------------------------------------
    log.raw_text = raw_text
    log.raw = _to_json(response_data)

    # ------------------------------------------------------------------
    # Extras desde response_data (si viene dict)
    # ------------------------------------------------------------------
    if isinstance(response_data, dict):
        if response_data.get("enrolledTimeStamp"):
            log.enrolledtimestamp = response_data.get("enrolledTimeStamp")

        if response_data.get("backprocessor"):
            log.backprocessor = response_data.get("backprocessor")

    # ------------------------------------------------------------------
    # Auditoría
    # ------------------------------------------------------------------
    log.created_by = frappe.session.user

    # Insertar sin permisos (log técnico)
    log.insert(ignore_permissions=True)

    return log.name