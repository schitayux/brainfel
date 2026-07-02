# brainfel/services/totaldoc_client.py

import time
import requests
import base64
from frappe.utils import now_datetime

def _nit_12(nit: str) -> str:
    # Quitar espacios/guiones
    return (nit or "").replace("-", "").strip()

def _get_api_key(settings) -> str:
    # El apiKey para Grupo CDS se guarda en contraseña_certificador
    api_key = getattr(settings, "contraseña_certificador", None)
    if not api_key:
        raise Exception("BFEL Settings: La contraseña_certificador (API Key de Grupo CDS) está vacía.")
    return api_key

def _get_url(settings, default_url: str) -> str:
    """Intenta usar la url configurada, sino usa el default."""
    return default_url

def certify_xml(settings, xml_payload: str, test_mode: bool, document_name: str):
    """
    Certifica vía Total Doc (Grupo CDS):
    1. POST a Firmar (/v1.0/signature)
    2. POST a Certificar (/v1.0/dte)
    """
    start = time.time()
    
    api_key = _get_api_key(settings)
    emisor_nit = _nit_12(settings.company_nit)
    
    # Endpoints Total Doc Ingestor
    # Se ignora base_url_test si no es compatible, usamos el estandar de Total Doc
    # O podríamos leerlo de base_url_test si se quiere
    domain = "ingestor-dev.totaldoc.io" if test_mode else "ingestor.totaldoc.io"
    
    # 1. FIRMAR
    url_firma = settings.url_firma or f"https://{domain}/v1.0/signature"
    
    xml_b64 = base64.b64encode((xml_payload or "").encode("utf-8")).decode("utf-8")
    
    firma_payload = {
        "dte": {
            "nit_transmitter": emisor_nit,
            "xml_dte": xml_b64
        }
    }
    headers = {
        "apiKey": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    r_firma = requests.post(url_firma, json=firma_payload, headers=headers, timeout=60)
    
    try:
        raw_firma = r_firma.json()
    except Exception:
        raw_firma = {}

    if r_firma.status_code != 200 or not raw_firma.get("xmlSigned"):
        msg = raw_firma.get("message") or r_firma.text or "Error desconocido al Firmar XML."
        return {
            "success": False,
            "http_status": r_firma.status_code,
            "elapsed_ms": int((time.time() - start) * 1000),
            "request_url": url_firma,
            "raw": raw_firma,
            "raw_text": r_firma.text,
            "message": f"Error al Firmar: {msg}",
            "status": "Error",
        }
        
    xml_signed = raw_firma.get("xmlSigned")
    
    # 2. CERTIFICAR
    url_certificar = settings.url_registrar or f"https://{domain}/v1.0/dte"
    
    import re
    serie = "FEL"
    number = 1
    if document_name:
        match = re.search(r'^(.*?)-?(\d+)$', str(document_name))
        if match:
            parsed_serie = match.group(1).strip("-")
            if parsed_serie:
                serie = re.sub(r'[^A-Za-z0-9_-]', '', parsed_serie) or "FEL"
            try:
                number = int(match.group(2))
            except ValueError:
                number = 1
        else:
            serie = re.sub(r'[^A-Za-z0-9_-]', '', str(document_name))[:20] or "FEL"
            number = 1

    cert_payload = {
        "dte": {
            "nit_transmitter": emisor_nit,
            "serie": serie,
            "number": number,
            "xml_dte": xml_signed
        }
    }
    
    r_cert = requests.post(url_certificar, json=cert_payload, headers=headers, timeout=60)
    
    elapsed_ms = int((time.time() - start) * 1000)
    
    try:
        raw_cert = r_cert.json()
    except Exception:
        raw_cert = {}
        
    success = r_cert.status_code == 200
    msg = raw_cert.get("message") or raw_cert.get("description") or ""
    
    uuid = None
    serie = None
    numero = None
    fecha = None
    
    if success and isinstance(raw_cert, dict):
        uuid = raw_cert.get("uuid") or raw_cert.get("Authorization")
        serie = raw_cert.get("serie") or raw_cert.get("Serial") or raw_cert.get("serial")
        numero = raw_cert.get("numero") or raw_cert.get("number") or raw_cert.get("Batch")
        fecha = raw_cert.get("fecha_certificacion") or raw_cert.get("TimeStamp")
        
        # En Total Doc a veces la data viene dentro de un nodo anidado si el éxito no está en el root
        if not uuid and raw_cert.get("dte"):
            uuid = raw_cert["dte"].get("uuid")
            serie = raw_cert["dte"].get("serie") or raw_cert["dte"].get("Serial") or raw_cert["dte"].get("serial")
            numero = raw_cert["dte"].get("numero") or raw_cert["dte"].get("number") or raw_cert["dte"].get("Batch")
            fecha = raw_cert["dte"].get("fecha_certificacion")

    if not success and not msg:
        # Extraer error desde Total Doc response (code, message, error_details)
        if raw_cert.get("code") and raw_cert.get("message"):
            msg = f"{raw_cert.get('code')} - {raw_cert.get('message')}"
            # Iterar rules si hay validation error
            error_data = raw_cert.get("error", {})
            rules = error_data.get("rules", [])
            for r in rules:
                if not r.get("pass", True):
                    msg += f" | {r.get('description', '')}"
        else:
            msg = r_cert.text or "Error al certificar DTE"

    # Total Doc devuelve "xml_dte" en la respuesta exitosa (Base64) a veces, si lo ocupamos.
    # Se usa download_and_attach_document para eso después.

    return {
        "success": success,
        "http_status": r_cert.status_code,
        "elapsed_ms": elapsed_ms,
        "request_url": url_certificar,
        "raw": raw_cert,
        "raw_text": r_cert.text,
        "message": msg,
        "uuid": uuid,
        "serie": serie,
        "numero": numero,
        "numero_acceso": None,
        "fecha_certificacion": fecha,
        "status": "Certificado" if success else "Error",
    }


def cancel_fel_document(settings, test_mode: bool, doc_uuid: str, buyer_nit: str, issue_date: str, motivo_anulacion: str):
    """
    Anulación vía Total Doc:
    1. Generar XML GTAnulacionDocumento
    2. Firmar Anulación
    3. Certificar Anulación
    """
    start = time.time()
    
    api_key = _get_api_key(settings)
    emisor_nit = _nit_12(settings.company_nit)
    receptor_nit = _nit_12(buyer_nit or "CF")
    
    # Formato requerido de fecha: 2021-12-17T12:49:06.100-06:00
    # issue_date suele ser str (ej. "2024-03-07 10:18:45.727")
    if isinstance(issue_date, str):
        # Asegurar formato estándar de GT
        issue_date = issue_date.replace(" ", "T")
        if "+" not in issue_date and "-" not in issue_date[11:]:
            # Añadir zona horaria GT si no existe
            issue_date = f"{issue_date}-06:00"
            
    fecha_anulacion = str(now_datetime()).replace(" ", "T")
    if "+" not in fecha_anulacion and "-" not in fecha_anulacion[11:]:
        fecha_anulacion = f"{fecha_anulacion}-06:00"
        
    xml_anulacion = f'''<?xml version="1.0" encoding="utf-8"?>
<dte:GTAnulacionDocumento xmlns:dte="http://www.sat.gob.gt/dte/fel/0.1.0"
                          xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
                          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                          Version="0.1">
\t<dte:SAT>
\t\t<dte:AnulacionDTE ID="DatosCertificados">
\t\t\t<dte:DatosGenerales ID="DatosAnulacion"
\t\t\t                    NumeroDocumentoAAnular="{doc_uuid}"
\t\t\t                    NITEmisor="{emisor_nit}"
\t\t\t                    IDReceptor="{receptor_nit}"
\t\t\t                    FechaEmisionDocumentoAnular="{issue_date}"
\t\t\t                    FechaHoraAnulacion="{fecha_anulacion}"
\t\t\t                    MotivoAnulacion="{motivo_anulacion}"/>
\t\t</dte:AnulacionDTE>
\t</dte:SAT>
</dte:GTAnulacionDocumento>'''

    xml_b64 = base64.b64encode(xml_anulacion.encode("utf-8")).decode("utf-8")
    
    domain = "ingestor-dev.totaldoc.io" if test_mode else "ingestor.totaldoc.io"
    
    # 1. FIRMAR ANULACIÓN
    url_sign = f"https://{domain}/v1.0/signanulacion"
    
    firma_payload = {
        "dte": {
            "nit_transmitter": emisor_nit,
            "xml_dte": xml_b64
        }
    }
    headers = {
        "apiKey": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    r_firma = requests.post(url_sign, json=firma_payload, headers=headers, timeout=60)
    
    try:
        raw_firma = r_firma.json()
    except Exception:
        raw_firma = {}

    if r_firma.status_code != 200 or not raw_firma.get("xmlSigned"):
        msg = raw_firma.get("message") or r_firma.text or "Error desconocido al Firmar Anulación."
        return {
            "success": False,
            "http_status": r_firma.status_code,
            "elapsed_ms": int((time.time() - start) * 1000),
            "request_url": url_sign,
            "raw": raw_firma,
            "raw_text": r_firma.text,
            "message": f"Error al Firmar Anulación: {msg}",
            "status": "Error",
        }
        
    xml_signed = raw_firma.get("xmlSigned")
    
    # 2. CERTIFICAR ANULACIÓN
    url_anular = settings.url_anular or f"https://{domain}/v1.0/dte-anulacion"
    
    cert_payload = {
        "dte": {
            "nit_transmitter": emisor_nit,
            "xml_dte": xml_signed
        }
    }
    
    r_cert = requests.post(url_anular, json=cert_payload, headers=headers, timeout=60)
    
    elapsed_ms = int((time.time() - start) * 1000)
    
    try:
        raw_cert = r_cert.json()
    except Exception:
        raw_cert = {}
        
    success = r_cert.status_code == 200
    msg = raw_cert.get("message") or raw_cert.get("description") or ""
    
    if not success and not msg:
        if raw_cert.get("code") and raw_cert.get("message"):
            msg = f"{raw_cert.get('code')} - {raw_cert.get('message')}"
            error_data = raw_cert.get("error", {})
            rules = error_data.get("rules", [])
            for r in rules:
                if not r.get("pass", True):
                    msg += f" | {r.get('description', '')}"
        else:
            msg = r_cert.text or "Error al certificar Anulación"

    return {
        "success": success,
        "http_status": r_cert.status_code,
        "elapsed_ms": elapsed_ms,
        "request_url": url_anular,
        "raw": raw_cert,
        "raw_text": r_cert.text,
        "message": msg,
        "request_payload": cert_payload
    }


def _consultar_identificacion(settings, url_field: str, identificacion: str):
    """
    Consulta el nombre registrado de un cliente por NIT o CUI vía Total Doc (Grupo CDS).

    Endpoint real (doc. Total Doc), igual para ambos identificadores, solo cambia
    la URL base configurada en BFEL Settings (url_retorna_cliente para NIT,
    url_retorna_cui para CUI):
        GET {url_base}{identificacion}   (ej. https://info.totaldoc.io/api/nit/33491232)
        Headers: appKey
        Sin body.
        200 -> {"nit"/"cui": "...", "name": "...", "address": "...", "message": "OK"}
        404/401 -> {"code": ..., "message": "...", "detail": "...", "detailCode": "..."}

    Retorna:
        {
            "success": bool,
            "customer_name": str | None,
            "http_status": int,
            "raw": dict,
            "message": str,
        }
    """
    start = time.time()

    url_base = (getattr(settings, url_field, None) or "").strip()
    if not url_base:
        raise Exception(f"BFEL Settings: {url_field} no está configurada.")

    api_key = _get_api_key(settings)
    id_normalizado = _nit_12(identificacion)

    if not id_normalizado:
        raise Exception("Debe indicar un valor de identificación para consultar el cliente.")

    url = f"{url_base}{id_normalizado}"
    headers = {
        "appKey": api_key,
        "Accept": "application/json",
    }

    r = requests.get(url, headers=headers, timeout=30)

    try:
        raw = r.json()
    except Exception:
        raw = {}

    elapsed_ms = int((time.time() - start) * 1000)
    success = r.status_code == 200

    customer_name = raw.get("name") if success and isinstance(raw, dict) else None

    msg = ""
    if isinstance(raw, dict):
        msg = raw.get("detail") or raw.get("message") or ""
    if not success and not msg:
        msg = r.text or "Error al consultar cliente por identificación."

    return {
        "success": success and bool(customer_name),
        "customer_name": customer_name,
        "http_status": r.status_code,
        "elapsed_ms": elapsed_ms,
        "raw": raw,
        "message": msg,
    }


def consultar_cliente(settings, nit: str):
    """Consulta por NIT vía BFEL Settings.url_retorna_cliente."""
    return _consultar_identificacion(settings, "url_retorna_cliente", nit)


def consultar_cliente_cui(settings, cui: str):
    """Consulta por CUI vía BFEL Settings.url_retorna_cui."""
    return _consultar_identificacion(settings, "url_retorna_cui", cui)
