# apps/brainfel/brainfel/api/certify_sales_invoice.py
from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from brainfel.sql.executor import run_sql_function
from brainfel.services.xml_builder_fact_cf import build_fact_cf as build_xml_from_dataset
from brainfel.services.xml_builder_fcam_sat import build_fcam_sat_xml
from brainfel.services.token_service import get_digifact_token
from brainfel.services.digifact_client import certify_xml as digifact_certify_xml, cancel_fel_document as digifact_cancel_fel_document
from brainfel.services.totaldoc_client import certify_xml as totaldoc_certify_xml, cancel_fel_document as totaldoc_cancel_fel_document
from brainfel.services import totaldoc_client
from brainfel.services.bfel_log_service import create_bfel_log
from brainfel.utils.company_utils import validate_user_company_access, get_bfel_settings_for_document

@frappe.whitelist()
def debug_last_log():
    logs = frappe.get_all("BFEL Log", order_by="creation desc", limit=1)
    if logs:
        log = frappe.get_doc("BFEL Log", logs[0].name)
        print("KEYS:", list(log.as_dict().keys()))
        print("RAW TEXT (first 300):", (getattr(log, "raw_text", "") or "")[:300])
        print("RESPONSE DATA:", getattr(log, "response_data", ""))
        print("REQUEST DATA:", getattr(log, "request_data", ""))
    else:
        print("No logs")


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
def certify_sales_invoice(sales_invoice_name: str, force_test_mode: int = 0, motivo_ajuste: str = None):
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
    sales_invoice_name = (sales_invoice_name or "").strip()
    si = frappe.get_doc("Sales Invoice", sales_invoice_name)

    if getattr(si, "bfel_uuid", None):
        frappe.throw("Este documento ya fue certificado FEL (bfel_uuid existe).")

    validate_user_company_access(si.company)
    settings = get_bfel_settings_for_document(si)
    test_mode = bool(force_test_mode) or (getattr(settings, "test_mode", "N") == "Y")

    # ------------------------------------------------------------------
    # 1) Dataset SQL
    # ------------------------------------------------------------------
    dataset = run_sql_function(
        settings.sql_func_certificar,
        {"docname": sales_invoice_name},
    )

    # Si se proporcionó un motivo de ajuste (para NCRE/NDEB), lo inyectamos en el dataset
    if dataset and motivo_ajuste:
        # Debug: Log keys of the first row
        frappe.log_error(title="DEBUG FEL Dataset Keys", message=f"Keys: {list(dataset[0].keys())}")
        for row in dataset:
            row["MotivoAjuste"] = motivo_ajuste

    if not dataset:
        msg = "La vista/función SQL no retornó datos v1."

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
    if settings.certifier == "Grupo CDS":
        from brainfel.services.totaldoc_xml_builder import build_totaldoc_xml
        xml_info = build_totaldoc_xml(dataset, settings)
    else:
        xml_info = build_xml_from_dataset(dataset, settings)
        
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
        if settings.certifier == "Grupo CDS":
            response = totaldoc_client.certify_xml(
                settings=settings,
                xml_payload=xml_payload,
                test_mode=test_mode,
                document_name=sales_invoice_name,
            )
            token = ""
        else:
            token = get_digifact_token(settings, test_mode)
            response = digifact_certify_xml(
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
    _db_set_if_exists(si, "bfel_docto_serie", response.get("numero"))
    _db_set_if_exists(si, "bfel_docto_no", response.get("serie"))
    _db_set_if_exists(si, "bfel_numero_acceso", response.get("numero_acceso"))
    _db_set_if_exists(si, "bfel_request_id", response.get("request_id"))

    fecha_cert = _get_certification_datetime(response)
    _db_set_if_exists(si, "bfel_fechacertificacion", fecha_cert)

    _db_set_if_exists(si, "bfel_mensaje", response.get("message"))
    _db_set_if_exists(si, "bfel_status", _map_status_success())

    frappe.db.commit()

    # Si hubo motivo de ajuste, lo insertamos como comentario
    if motivo_ajuste:
        comment_text = f"<b>Motivo de Ajuste (Nota):</b> {motivo_ajuste}"
        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Comment",
            "reference_doctype": "Sales Invoice",
            "reference_name": si.name,
            "content": comment_text
        }).insert(ignore_permissions=True)

    # Recargamos para evitar errores de 'Document Modified' en el cliente
    si.reload()

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

    # ------------------------------------------------------------------
    # 6) DESCARGAR Y ADJUNTAR DOCUMENTO (PDF/XML)
    # ------------------------------------------------------------------
    if response.get("uuid"):
        # Importante: se manda a llamar en background o síncrono.
        # Lo haremos síncrono para que aparezca de una vez al recargar.
        download_and_attach_document(si.name, response.get("uuid"), token, settings, test_mode)

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


@frappe.whitelist()
def cancel_sales_invoice_fel(sales_invoice_name: str, motivo_anulacion: str, force_test_mode: int = 0):
    """
    Anula un Sales Invoice certificado vía Digifact (NUC).
    Llama a CancelFelGT.
    """
    sales_invoice_name = (sales_invoice_name or "").strip()
    motivo_anulacion = (motivo_anulacion or "").strip()
    
    if not motivo_anulacion:
        frappe.throw("El motivo de anulación es obligatorio para cancelar en FEL.")
        
    si = frappe.get_doc("Sales Invoice", sales_invoice_name)

    if not getattr(si, "bfel_uuid", None):
        frappe.throw("Este documento no tiene UUID (no ha sido certificado), no se puede anular en FEL.")
        
    if getattr(si, "bfel_documento_anulado", 0) == 1:
        # Ya está anulado en FEL (quizás falló la anulación en ERPNext antes)
        return {"success": True, "message": "Ya estaba anulado en FEL."}

    validate_user_company_access(si.company)
    settings = get_bfel_settings_for_document(si)
    test_mode = bool(force_test_mode) or (getattr(settings, "test_mode", "N") == "Y")
    
    # ------------------------------------------------------------------
    # Token + Anulación
    # ------------------------------------------------------------------
    try:
        buyer_nit = getattr(si, "tax_id", "") or "CF"
        issue_date = getattr(si, "bfel_fechacertificacion", "")
        if not issue_date:
            issue_date = getattr(si, "posting_date", "")
            
        if settings.certifier == "Grupo CDS":
            response = totaldoc_client.cancel_fel_document(
                settings=settings,
                test_mode=test_mode,
                doc_uuid=si.bfel_uuid,
                buyer_nit=buyer_nit,
                issue_date=str(issue_date),
                motivo_anulacion=motivo_anulacion
            )
        else:
            token = get_digifact_token(settings, test_mode)
            response = digifact_cancel_fel_document(
                settings=settings,
                token=token,
                test_mode=test_mode,
                doc_uuid=si.bfel_uuid,
                buyer_nit=buyer_nit,
                issue_date=str(issue_date),
                motivo_anulacion=motivo_anulacion
            )
    except Exception as e:
        msg = str(e) or "Error técnico al anular FEL."
        
        create_bfel_log(
            settings=settings,
            document=si,
            action="CANCEL",
            status="Error",
            request_xml=None,
            response_data={"exception": msg},
            raw_text=msg,
            message=msg,
        )
        frappe.throw(msg)

    # ------------------------------------------------------------------
    # Error FEL
    # ------------------------------------------------------------------
    if not (isinstance(response, dict) and response.get("success")):
        msg = (
            response.get("message")
            if isinstance(response, dict)
            else "Error al anular FEL"
        )
        
        create_bfel_log(
            settings=settings,
            document=si,
            action="CANCEL",
            status="Error",
            request_xml=None,
            response_data=response,
            raw_text=response.get("raw_text") if isinstance(response, dict) else None,
            message=msg,
            http_status=response.get("http_status"),
            elapsed_ms=response.get("elapsed_ms"),
            uuid=si.bfel_uuid,
        )
        frappe.throw(f"No se pudo anular en Digifact: {msg}")

    # ------------------------------------------------------------------
    # ÉXITO
    # ------------------------------------------------------------------
    si.flags.ignore_validate_update_after_submit = True
    
    _db_set_if_exists(si, "bfel_documento_anulado", 1)
    
    msg_anulacion = f"Anulado en FEL: {response.get('message') or 'OK'}"
    _db_set_if_exists(si, "bfel_mensaje", msg_anulacion)
    
    # Agregar el comentario de anulación
    comment_text = f"<b>Documento Anulado en FEL</b><br>Motivo: {motivo_anulacion}"
    frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Comment",
        "reference_doctype": "Sales Invoice",
        "reference_name": si.name,
        "content": comment_text
    }).insert(ignore_permissions=True)
    
    create_bfel_log(
        settings=settings,
        document=si,
        action="CANCEL",
        status="Success",
        request_xml=None,
        response_data=response,
        raw_text=response.get("raw_text"),
        message=response.get("message"),
        http_status=response.get("http_status"),
        elapsed_ms=response.get("elapsed_ms"),
        uuid=si.bfel_uuid,
    )
    
    return {"success": True, "message": msg_anulacion}

def download_and_attach_document(si_name: str, uuid: str, token: str, settings, test_mode: bool):
    """
    Descarga el PDF/XML desde el certificador y lo adjunta a la factura con un comentario.
    """
    import requests
    import base64

    try:
        si = frappe.get_doc("Sales Invoice", si_name)
        
        if settings.certifier == "Grupo CDS":
            url_pdf_setting = getattr(settings, "url_pdf", None)
            if url_pdf_setting:
                url_pdf = f"{url_pdf_setting}{uuid}"
            else:
                domain = "print-dev.totaldoc.io" if test_mode else "print.totaldoc.io"
                url_pdf = f"https://{domain}/pdf?uuid={uuid}"
            
            r = requests.get(url_pdf, timeout=60)
            if r.status_code == 200:
                # Silenciado - Solo log en consola
                print("Se descargó el PDF de Total Doc. Adjuntando...")
                file_doc = frappe.get_doc({
                    "doctype": "File",
                    "file_name": f"FEL_{si.name}_{uuid}.pdf",
                    "attached_to_doctype": "Sales Invoice",
                    "attached_to_name": si.name,
                    "content": r.content,
                    "is_private": 0
                })
                file_doc.save(ignore_permissions=True)
                
                frappe.get_doc({
                    "doctype": "Comment",
                    "comment_type": "Comment",
                    "reference_doctype": "Sales Invoice",
                    "reference_name": si.name,
                    "content": f"Documento FEL PDF Certificado: <a href='{file_doc.file_url}' target='_blank'>Descargar PDF</a>"
                }).insert(ignore_permissions=True)
            else:
                frappe.log_error(title="Error al descargar PDF de Total Doc", message=f"{r.status_code} - {r.text[:200]}")
            return
            
        from brainfel.services.digifact_client import _base_url, _nit_12
        base = _base_url(settings, test_mode)
        url = f"{base}/api/GetDocument"

        # La API de NUC exige estos parámetros en la URL (GET)
        params = {
            "TAXID": _nit_12(settings.company_nit),
            "USERNAME": settings.user,
            "AUTHNUMBER": uuid,
            "FORMAT": "PDF"
        }
        headers = {
            "Authorization": token,
            "Accept": "application/json"
        }

        r = requests.get(url, params=params, headers=headers, timeout=60)

        # DEBUG: Log silencioso
        print(f"Status API GetDocument: {r.status_code}")
        
        if r.status_code == 200:
            resp = r.json()

            # ResponseDATA3 suele ser el PDF en Base64
            b64_pdf = resp.get("ResponseDATA3")
            if b64_pdf:
                print("Se encontró el PDF en ResponseDATA3. Adjuntando...")
                file_doc = frappe.get_doc({
                    "doctype": "File",
                    "file_name": f"FEL_{si.name}_{uuid}.pdf",
                    "attached_to_doctype": "Sales Invoice",
                    "attached_to_name": si.name,
                    "content": base64.b64decode(b64_pdf),
                    "is_private": 0
                })
                file_doc.save(ignore_permissions=True)

                frappe.get_doc({
                    "doctype": "Comment",
                    "comment_type": "Comment",
                    "reference_doctype": "Sales Invoice",
                    "reference_name": si.name,
                    "content": f"Documento FEL PDF Certificado: <a href='{file_doc.file_url}' target='_blank'>Descargar PDF</a>"
                }).insert(ignore_permissions=True)

            # ResponseDATA1 suele ser el XML en Base64
            b64_xml = resp.get("ResponseDATA1")
            if b64_xml:
                xml_doc = frappe.get_doc({
                    "doctype": "File",
                    "file_name": f"FEL_{si.name}_{uuid}.xml",
                    "attached_to_doctype": "Sales Invoice",
                    "attached_to_name": si.name,
                    "content": base64.b64decode(b64_xml),
                    "is_private": 0
                })
                xml_doc.save(ignore_permissions=True)

                frappe.get_doc({
                    "doctype": "Comment",
                    "comment_type": "Comment",
                    "reference_doctype": "Sales Invoice",
                    "reference_name": si.name,
                    "content": f"Documento FEL XML: <a href='{xml_doc.file_url}' target='_blank'>Descargar XML</a>"
                }).insert(ignore_permissions=True)
            
            if not b64_pdf and not b64_xml:
                frappe.log_error(title="Error Digifact GetDocument", message=f"El API respondió 200 OK pero no devolvió PDF ni XML. Respuesta cruda: {r.text[:500]}")
        else:
            frappe.log_error(title="Error al descargar PDF de Digifact", message=f"{r.text[:500]}")

    except Exception as e:
        frappe.log_error(title=f"Error descargando documento FEL para {si_name}", message=frappe.get_traceback())
