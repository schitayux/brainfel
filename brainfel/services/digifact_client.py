# brainfel/services/digifact_client.py

import time
import requests


def _base_url(settings, test_mode: bool) -> str:
    base = settings.base_url_test if test_mode else settings.base_url_prod
    if not base:
        raise Exception("BFEL Settings: base_url_test/base_url_prod está vacío.")
    return base.rstrip("/")


def _nit_12(nit: str) -> str:
    nit = (nit or "").replace("-", "").strip()
    if not nit.isdigit():
        raise Exception(f"company_nit inválido: {nit!r} (debe ser numérico, sin guiones).")
    return nit.zfill(12)


def certify_xml(settings, xml_payload: str, token: str, test_mode: bool = True):
    """
    Certifica vía NUC:
    POST {base_url}/{url_registrar}
    Query: TAXID (12), USERNAME (corto), FORMAT=XML
    Header: Authorization: <token>
    Body: XML
    """

    start = time.time()

    base = _base_url(settings, test_mode)
    endpoint = (settings.url_registrar or "").strip()
    if not endpoint:
        raise Exception("BFEL Settings: url_registrar está vacío.")

    url = f"{base}/{endpoint.lstrip('/')}"

    user_short = (settings.user or "").strip()
    if not user_short:
        raise Exception("BFEL Settings: user está vacío.")

    params = {
        "TAXID": _nit_12(settings.company_nit),
        "USERNAME": user_short,   # 👈 IMPORTANTE: USER CORTO para /transform/nuc
        "FORMAT": "XML",
    }

    headers = {
        # 👇 En documentación lo usan directo, no "Bearer"
        "Authorization": token,
        "Content-Type": "application/xml",
        "Accept": "application/json",
    }

    r = requests.post(
        url,
        params=params,
        data=(xml_payload or "").encode("utf-8"),
        headers=headers,
        timeout=60,
    )

    elapsed_ms = int((time.time() - start) * 1000)

    try:
        raw = r.json()
    except Exception:
        raw = None

    msg = None
    uuid = None
    serie = None
    numero = None
    fecha = None
    
    if isinstance(raw, dict):
        msg = raw.get("description") or raw.get("message")
        
        # Extract FEL fields
        # Try multiple keys to be robust (PascalCase vs camelCase)
        uuid = raw.get("Authorization") or raw.get("authNumber")
        serie = raw.get("Serial") or raw.get("serial")
        numero = raw.get("Batch") or raw.get("batch")
        fecha = raw.get("TimeStamp") or raw.get("issuedTimeStamp") or raw.get("enrolledTimeStamp")

    if not msg:
        msg = r.text or ""

    return {
        "success": r.status_code == 200,
        "http_status": r.status_code,
        "elapsed_ms": elapsed_ms,
        "request_url": r.url,
        "raw": raw,
        "raw_text": r.text,
        "message": msg,
        # Mapped FEL Fields
        "uuid": uuid,
        "serie": serie,
        "numero": numero,
        "numero_acceso": None,
        "fecha_certificacion": fecha,
        "status": "Certificado" if (r.status_code == 200 and uuid) else "Error",
    }


def cancel_fel_document(settings, token: str, test_mode: bool, doc_uuid: str, buyer_nit: str, issue_date: str, motivo_anulacion: str):
    """
    Anula un documento electrónico vía Digifact (NUC) - CancelFelGT.
    Endpoint: /api/CancelFelGT
    Body (JSON): Taxid, Autorizacion, IdReceptor, FechaEmisionDocumentoAnular, MotivoAnulacion, Username
    """
    start = time.time()
    
    base = _base_url(settings, test_mode)
    
    # El endpoint de cancelación suele ser fijo según la documentación, 
    # pero revisamos si hay url_anular configurada, si no, usamos el default.
    endpoint = (settings.url_anular or "api/CancelFelGT").strip()
    url = f"{base}/{endpoint.lstrip('/')}"
    
    user_short = (settings.user or "").strip()
    
    # Formatear NIT emisor a 12 caracteres sin guiones como pide la documentación, 
    # o usar el que viene en configuracion normal. La doc pide NIT normal, pero usemos la func.
    emisor_nit = settings.company_nit.replace("-", "").strip()
    
    buyer_nit = (buyer_nit or "CF").replace("-", "").strip()
    
    # El formato de fecha requerido es: YYYY-MM-DDTHH:MM:SS
    # Nos aseguramos que no lleve milisegundos ni zona horaria si no es compatible
    if isinstance(issue_date, str):
        issue_date = issue_date.replace(" ", "T")
        if "." in issue_date:
            issue_date = issue_date.split(".")[0]
            
    payload = {
        "Taxid": emisor_nit,
        "Autorizacion": doc_uuid,
        "IdReceptor": buyer_nit,
        "FechaEmisionDocumentoAnular": issue_date,
        "MotivoAnulacion": motivo_anulacion,
        "Username": user_short
    }
    
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    r = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=60
    )
    
    elapsed_ms = int((time.time() - start) * 1000)
    
    try:
        raw = r.json()
    except Exception:
        raw = None
        
    msg = None
    success = False
    
    if isinstance(raw, dict):
        # La documentación de Digifact indica que Retorna un Mensaje, 
        # y variables como ACUSE_RECIBO_ANULACION
        msg = raw.get("Mensaje") or raw.get("message") or raw.get("description")
        
        # Analizamos código de respuesta SAT o si hay ACUSE
        acuse = raw.get("AcuseReciboSAT") or raw.get("ACUSE_RECIBO_ANULACION")
        
        if r.status_code == 200 and acuse:
            success = True
        elif r.status_code == 200 and raw.get("Codigo") == "1":
            success = True
    
    if not msg:
        msg = r.text or "Sin respuesta del servidor"
        
    # Si la respuesta es HTTP 200, asumimos éxito a menos que haya un mensaje claro de error
    if r.status_code == 200 and not success:
        if "anulad" in str(msg).lower() or "exito" in str(msg).lower():
            success = True
            
    return {
        "success": success,
        "http_status": r.status_code,
        "elapsed_ms": elapsed_ms,
        "request_url": r.url,
        "raw": raw,
        "raw_text": r.text,
        "message": msg,
        "request_payload": payload
    }
