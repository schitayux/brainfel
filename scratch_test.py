import frappe
from brainfel.services.token_service import get_digifact_token
from brainfel.services.digifact_client import _nit_12, _base_url
import requests

frappe.init(site="frappe.local")
frappe.connect()

settings = frappe.get_doc("BFEL Settings", {"enabled": 1})
test_mode = True

token = get_digifact_token(settings, test_mode)

url = f"{_base_url(settings, test_mode)}/api/GetDocument"
print("URL:", url)

params = {
    "TAXID": _nit_12(settings.company_nit),
    "USERNAME": settings.user,
    "AUTHNUMBER": "4C6594C4-13B7-4402-A746-8344BBA36750", # dummy or existing one? Let's use an empty one and see if we get a 404
    "FORMAT": "PDF"
}
headers = {
    "Authorization": token,
    "Accept": "application/json"
}

r = requests.get(url, params=params, headers=headers)
print("GET Status:", r.status_code)
print("GET Response:", r.text[:200])

# Just in case, let's try POST with the JSON the user provided
post_url = "https://testnucgt.digifact.com/api/GetDocument"
post_json = {
    "NIT": _nit_12(settings.company_nit),
    "TIPO": "XML",
    "FORMAT": "PDF",
    "UUID": "4C6594C4-13B7-4402-A746-8344BBA36750"
}
r2 = requests.post(post_url, json=post_json, headers=headers)
print("POST Status:", r2.status_code)
print("POST Response:", r2.text[:200])

