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