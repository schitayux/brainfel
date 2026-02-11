
import sys
import os

# Add app path to sys.path
sys.path.append("/home/frappe/frappe-bench/apps/brainfel")

from brainfel.services.xml_builder_fact_cf import build_fact_cf

# Mock dataset row
mock_row = {
    "DatosGenerales_Tipo": "FACT",
    "DatosGenerales_FechaHoraEmision": "2023-10-27 12:00:00",
    "DatosGenerales_CodigoMoneda": "GTQ",
    "Emisor_NITEmisor": "12345678",
    "Emisor_NombreEmisor": "Empresa Demo",
    "Emisor_AfiliacionIVA": "GEN",
    "Emisor_DireccionEmisor_Direccion": "Ciudad",
    "Receptor_IDReceptor": "CF",
    "Receptor_NombreReceptor": "Consumidor Final",
    "Items_BienOServicio": "B",
    "Items_Descripcion": "Producto Demo",
    "Items_Cantidad": 1,
    "Items_Price": 100,
    "Items_Total": 100,
    "Frases_Escenarios": "" # Empty to test default fallback to 1|2
}

print("Invoking build_fact_cf...")
try:
    result = build_fact_cf([mock_row])
    print("Result Type:", result["type"])
    print("XML Length:", len(result["xml"]))
    print("Success!")
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()
