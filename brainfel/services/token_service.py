# brainfel/services/token_service.py

import requests


def _base_url(settings, test_mode: bool) -> str:
    base = settings.base_url_test if test_mode else settings.base_url_prod
    if not base:
        raise Exception("BFEL Settings: base_url_test/base_url_prod está vacío.")
    return base.rstrip("/")


def _join_url(base: str, endpoint: str) -> str:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        raise Exception("BFEL Settings: url_token está vacío.")
    return f"{base}/{endpoint.lstrip('/')}"


def _nit_12(nit: str) -> str:
    # Quitar espacios/guiones y completar a 12
    nit = (nit or "").replace("-", "").strip()
    if not nit.isdigit():
        raise Exception(f"company_nit inválido: {nit!r} (debe ser numérico, sin guiones).")
    return nit.zfill(12)


def get_digifact_token(settings, test_mode: bool = True) -> str:
    """
    Obtiene token JWT desde Digifact NUC.
    - Username para token: GT.{NIT_12}.{USER_CORTO}
    - POST JSON
    """

    base = _base_url(settings, test_mode)
    url = _join_url(base, settings.url_token)

    nit12 = _nit_12(settings.company_nit)
    user_short = (settings.user or "").strip()
    if not user_short:
        raise Exception("BFEL Settings: user está vacío.")
    password = getattr(settings, "contraseña_certificador", None)
    if not password:
        raise Exception("BFEL Settings: contraseña_certificador está vacío.")

    username_full = f"GT.{nit12}.{user_short}"

    payload = {
        "Username": username_full,
        "Password": password,
    }

    headers = {"Content-Type": "application/json"}

    r = requests.post(url, json=payload, headers=headers, timeout=30)

    if r.status_code != 200:
        raise Exception(
            f"Digifact Token HTTP {r.status_code}: {r.text}\n"
            f"URL: {url}\n"
            f"Username usado: {username_full}"
        )

    data = r.json() if r.text else {}
    token = data.get("Token") or data.get("token")
    if not token:
        raise Exception(f"Token no encontrado en respuesta: {data}")

    return token