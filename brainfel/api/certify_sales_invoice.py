# apps/brainfel/brainfel/api/certify_sales_invoice.py
from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from brainfel.sql.executor import run_sql_function
from brainfel.services.xml_builder_fact_cf import build_fact_cf as build_xml_from_dataset
from brainfel.services.token_service import get_digifact_token
from brainfel.services.digifact_client import certify_xml
from brainfel.services.bfel_log_service import create_bfel_log


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _should_log(settings) -> bool:
    # Se mantiene por compatibilidad, pero YA NO se usa
    return bool(getattr(settings, "generate_log", 0))


def _map_status_success() -> str:
    # 00 No enviar | 01 Enviar | 02 Procesada | 03 No Procesada
    return "02 Procesada"


def _map_status_error() -> str:
    return "03 No Procesada"


def _db_set_if_exists(doc, fieldname: str, value):
    """Actualiza campo vía db_set solo si existe en el DocType."""
    if value is None:
        return
    if doc.meta.has_field(fieldname):
        doc.db_set(fieldname, value)


def _load_settings_for_company(company: str):
    row = frappe.get_all(
        "BFEL Settings",
        filters={"company": company, "enabled": 1},
        limit=1,
    )
    if not row:
        frappe.throw(f"No existe BFEL Settings activo para la empresa {company}")
    return frappe.get_doc("BFEL Settings", row[0].name)


def _get_certification_datetime(response):
    """
    Obtiene la fecha/hora oficial de certificación desde el certificador.
    Prioridad:
      1) issuedTimeStamp
      2) enrolledTimeStamp
      3) fechaCertificacion
      4) now_datetime() (fallback extremo)
    """
    if not isinstance(response, dict):
        return now_datetime()

    for key in ("issuedTimeStamp", "enrolledTimeStamp", "fechaCertificacion"):
        value = response.get(key)
        if value:
            return value

    return now_datetime()


# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------

@frappe.whitelist()
def certify_sales_invoice(sales_invoice_name: str, force_test_mode: int = 0):
    """
    Certifica un Sales Invoice vía Digifact (NUC).

    ✔ Compatible con documentos Submitted
    ✔ Actualiza Sales Invoice vía db_set
    ✔ GRABA BFEL Log SIEMPRE
    ✔ Usa fecha/hora REAL del certificador
    """

    # ------------------------------------------------------------------
    # 0) Documento
    # ------------------------------------------------------------------
    si = frappe.get_doc("Sales Invoice", sales_invoice_name)

    if getattr(si, "bfel_uuid", None):
        frappe.throw("Este documento ya fue certificado FEL (bfel_uuid existe).")

    settings = _load_settings_for_company(si.company)
    test_mode = bool(force_test_mode) or bool(getattr(settings, "test_mode", 0))

    # ------------------------------------------------------------------
    # 1) Dataset SQL
    # ------------------------------------------------------------------
    dataset = run_sql_function(
        settings.sql_func_certificar,
        {"docname": sales_invoice_name},
    )

    if not dataset:
        msg = "La vista/función SQL no retornó datos."

        si.flags.ignore_validate_update_after_submit = True
        _db_set_if_exists(si, "bfel_status", _map_status_error())
        _db_set_if_exists(si, "bfel_mensaje", msg)
        frappe.db.commit()

        create_bfel_log(
            settings=settings,
            document=si,
            action="CERTIFY",
            status="Error",
            request_xml=None,
            response_data={"error": msg},
            raw_text=msg,
            message=msg,
        )

        frappe.throw(msg)

    # ------------------------------------------------------------------
    # 2) XML
    # ------------------------------------------------------------------
    xml_info = build_xml_from_dataset(dataset)
    xml_payload = (xml_info or {}).get("xml") or ""

    if not xml_payload.strip():
        msg = "No se generó XML (payload vacío)."

        si.flags.ignore_validate_update_after_submit = True
        _db_set_if_exists(si, "bfel_status", _map_status_error())
        _db_set_if_exists(si, "bfel_mensaje", msg)
        frappe.db.commit()

        create_bfel_log(
            settings=settings,
            document=si,
            action="CERTIFY",
            status="Error",
            request_xml=None,
            response_data={"error": msg},
            raw_text=msg,
            message=msg,
        )

        frappe.throw(msg)

    # ------------------------------------------------------------------
    # 3) Token + Certificación
    # ------------------------------------------------------------------
    try:
        token = get_digifact_token(settings, test_mode)
        response = certify_xml(
            settings=settings,
            xml_payload=xml_payload,
            token=token,
            test_mode=test_mode,
        )
    except Exception as e:
        msg = str(e) or "Error técnico al certificar FEL."

        si.flags.ignore_validate_update_after_submit = True
        _db_set_if_exists(si, "bfel_status", _map_status_error())
        _db_set_if_exists(si, "bfel_mensaje", msg)
        frappe.db.commit()

        create_bfel_log(
            settings=settings,
            document=si,
            action="CERTIFY",
            status="Error",
            request_xml=xml_payload,
            response_data={"exception": msg},
            raw_text=msg,
            message=msg,
        )

        frappe.throw(msg)

    # ------------------------------------------------------------------
    # 4) Error FEL
    # ------------------------------------------------------------------
    if not (isinstance(response, dict) and response.get("success")):
        msg = (
            response.get("message")
            if isinstance(response, dict)
            else "Error al certificar FEL"
        )

        si.flags.ignore_validate_update_after_submit = True
        _db_set_if_exists(si, "bfel_status", _map_status_error())
        _db_set_if_exists(si, "bfel_mensaje", msg)
        _db_set_if_exists(si, "bfel_request_id", response.get("request_id"))
        frappe.db.commit()

        create_bfel_log(
            settings=settings,
            document=si,
            action="CERTIFY",
            status="Error",
            request_xml=xml_payload,
            response_data=response,
            raw_text=response.get("raw_text") if isinstance(response, dict) else None,
            message=msg,
            http_status=response.get("http_status"),
            elapsed_ms=response.get("elapsed_ms"),
            request_id=response.get("request_id"),
            uuid=response.get("uuid"),
        )

        frappe.throw(msg)

    # ------------------------------------------------------------------
    # 5) ÉXITO (LOG SIEMPRE)
    # ------------------------------------------------------------------
    si.flags.ignore_validate_update_after_submit = True

    _db_set_if_exists(si, "bfel_uuid", response.get("uuid"))
    _db_set_if_exists(si, "bfel_docto_serie", response.get("serie"))
    _db_set_if_exists(si, "bfel_docto_no", response.get("numero"))
    _db_set_if_exists(si, "bfel_numero_acceso", response.get("numero_acceso"))
    _db_set_if_exists(si, "bfel_request_id", response.get("request_id"))

    fecha_cert = _get_certification_datetime(response)
    _db_set_if_exists(si, "bfel_fechacertificacion", fecha_cert)

    _db_set_if_exists(si, "bfel_mensaje", response.get("message"))
    _db_set_if_exists(si, "bfel_status", _map_status_success())

    frappe.db.commit()

    create_bfel_log(
        settings=settings,
        document=si,
        action="CERTIFY",
        status="Success",
        request_xml=xml_payload,
        response_data=response,
        raw_text=response.get("raw_text"),
        message=response.get("message"),
        http_status=response.get("http_status"),
        elapsed_ms=response.get("elapsed_ms"),
        request_id=response.get("request_id"),
        uuid=response.get("uuid"),
    )

    return {
        "success": True,
        "sales_invoice": si.name,
        "uuid": response.get("uuid"),
        "serie": response.get("serie"),
        "numero": response.get("numero"),
        "status": _map_status_success(),
        "test_mode": test_mode,
        "fecha_certificacion": fecha_cert,
    }