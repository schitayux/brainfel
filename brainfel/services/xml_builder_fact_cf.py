# brainfel/services/xml_builder_fact_cf.py

from typing import Any, Dict, List
from xml.etree.ElementTree import Element, SubElement, tostring
from datetime import datetime
import re

def build_fact_cf(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    if not rows:
        raise ValueError("Dataset vacío")

    h = rows[0]

    # -------------------------------
    # Helpers
    # -------------------------------
    def txt(v, default=""):
        if v is None:
            return default
        s = str(v).strip()
        return s if s else default

    def money(v) -> str:
        try:
            return f"{float(v):.6f}"
        except Exception:
            return "0.000000"

    def qty(v) -> str:
        try:
            return f"{float(v):.6f}"
        except Exception:
            return "1.000000"

    def issued_dt(val=None) -> str:
        # Convertir fecha de string a formato requerido si es necesario
        # Por default usar now si no viene
        if val:
             # Asumiendo que val viene como string YYYY-MM-DD HH:MM:SS o similar
             # Si ya es string ISO correcto, devolverlo.
             # Para simplificar, si hay valor usémoslo tal cual si parece fecha, 
             # o intentemos parsear. 
             # Digifact NUC suele pedir: YYYY-MM-DDTHH:MM:SS
             return f"{val}".replace(" ", "T")
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    def norm_country(v) -> str:
        s = txt(v).upper()
        if s in ["GUATEMALA", "GTM", "GT"]:
            return "GT"
        return s if len(s) == 2 else "GT"

    # =================================================
    # ROOT
    # =================================================
    root = Element("Root")
    SubElement(root, "Version").text = "1.00"
    SubElement(root, "CountryCode").text = "GT"

    # =================================================
    # HEADER
    # =================================================
    doc_type = txt(h.get("DatosGenerales_Tipo") or h.get("TipoDocumento") or "FACT")
    
    header = SubElement(root, "Header")
    SubElement(header, "DocType").text = doc_type
    SubElement(header, "IssuedDateTime").text = issued_dt(h.get("DatosGenerales_FechaHoraEmision"))
    SubElement(header, "Currency").text = txt(
        h.get("DatosGenerales_CodigoMoneda") or "GTQ"
    )

    # =================================================
    # SELLER
    # =================================================
    seller = SubElement(root, "Seller")
    SubElement(seller, "TaxID").text = txt(h.get("Emisor_NITEmisor")).replace("-", "")
    # SubElement(seller, "TaxIDType").text = "NIT"  <-- Removed: Not in NUC definition via documentation

    # TaxIDAdditionalInfo (B03) - Mandatory for Seller
    tax_info_node = SubElement(seller, "TaxIDAdditionalInfo")
    afiliacion = txt(h.get("Emisor_AfiliacionIVA", "GEN"))
    SubElement(tax_info_node, "Info", {"Name": "AfiliacionIVA", "Value": afiliacion})

    SubElement(seller, "Name").text = txt(h.get("Emisor_NombreEmisor"))

    # Phrases (B06) Ref: 4.2.3.2
    # Mandatory for FACT (at least Frase 1) - However, default "1|1" caused Error 9016 (Invalid for Issuer).
    # Removing default fallback as per user request. If validation fails for missing phrase (5004), 
    # the correct phrase must be provided in the source data.
    # frases_raw = txt(h.get("Frases_Escenarios"))
    
    # FORCE CORRECT TYPE 1 SCENARIO 2 AS PER USER REQUEST TO FIX VALIDATION 2.6.1.4
    frases_raw = "1|2"
    
    print(f"DEBUG PHRASES RAW: '{frases_raw}'") # Debug to confirm if DB is sending data
    
    if not frases_raw:
        # Default to Type 1 (ISR), Scenario 2 (Opcional Simplificado) based on Error 9016 and Docs 2.6.5
        # Scenario 1 ("1|1") is for "Utilidades", which caused the affiliation mismatch.
        frases_raw = "1|2"

    parts = [p.strip() for p in frases_raw.replace(";", ",").split(",") if p.strip()]
    
    # User requested to suppress phrases ... (proved incorrect by Error 5004)
    # Re-enabling logic. Validate input data against documentation.
    if parts: 
        # Check tag name: Doc says "AdditionlInfo" (B06), note the typo in "Additional" (missing 'a')
        phrases_node = SubElement(seller, "AdditionlInfo")
        for ie, p in enumerate(parts):
            # Parse Type|Scenario (e.g. "1|1")
            tf = "1"
            sc = "1"
            if "|" in p:
                pt = p.split("|")
                tf = pt[0]
                sc = pt[1]
            else:
                sc = p
            
            # Data attribute links the attributes of a single phrase (PID)
            pid = str(ie + 1)
            SubElement(phrases_node, "Info", {"Name": "TipoFrase", "Data": pid, "Value": tf})
            
            # IMPORTANT: NUC API requires Name="Escenario" to transform correctly.
            # Use of Name="CodigoEscenario" causes Error 3000 (Transformation/Incomplete Data).
            # The resulting FEL XML will correctly have CodigoEscenario.
            SubElement(phrases_node, "Info", {"Name": "Escenario", "Data": pid, "Value": sc})

    branch = SubElement(seller, "BranchInfo")
    SubElement(branch, "Code").text = txt(h.get("Emisor_CodigoEstablecimiento", "1"))
    SubElement(branch, "Name").text = txt(
        h.get("Emisor_NombreComercial") or h.get("Emisor_NombreEmisor")
    )
    
    baddr = SubElement(branch, "AddressInfo")
    SubElement(baddr, "Address").text = txt(h.get("Emisor_DireccionEmisor_Direccion", "CIUDAD"))
    SubElement(baddr, "City").text = txt(h.get("Emisor_DireccionEmisor_CodigoPostal", "01001"))
    SubElement(baddr, "District").text = txt(h.get("Emisor_DireccionEmisor_Municipio", "GUATEMALA"))
    SubElement(baddr, "State").text = txt(h.get("Emisor_DireccionEmisor_Departamento", "GUATEMALA"))
    SubElement(baddr, "Country").text = norm_country(h.get("Emisor_DireccionEmisor_Pais"))

    # =================================================
    # BUYER
    # =================================================
    buyer = SubElement(root, "Buyer")
    
    nit_receptor = txt(h.get("Receptor_IDReceptor")).replace("-", "").upper()
    if not nit_receptor or nit_receptor == "CF":
        nit_receptor = "CF"
        nombre_receptor = "CONSUMIDOR FINAL"
    else:
        nombre_receptor = txt(h.get("Receptor_NombreReceptor"))

    SubElement(buyer, "TaxID").text = nit_receptor




    SubElement(buyer, "Name").text = nombre_receptor
    
    # Campo email removido por validación de esquema
    # email_receptor = txt(h.get("Receptor_CorreoReceptor"))
    # if email_receptor:
    #    SubElement(buyer, "Email").text = email_receptor

    badr = SubElement(buyer, "AddressInfo")
    SubElement(badr, "Address").text = txt(h.get("Receptor_DireccionReceptor_Direccion") or "CIUDAD")
    SubElement(badr, "City").text = txt(h.get("Receptor_DireccionReceptor_CodigoPostal") or "01001")
    SubElement(badr, "District").text = txt(h.get("Receptor_DireccionReceptor_Municipio") or "GUATEMALA")
    SubElement(badr, "State").text = txt(h.get("Receptor_DireccionReceptor_Departamento") or "GUATEMALA")
    SubElement(badr, "Country").text = norm_country(h.get("Receptor_DireccionReceptor_Pais"))


    # =================================================
    # ITEMS
    # =================================================
    items = SubElement(root, "Items")

    total_tax = 0.0
    grand_total = 0.0

    for r in rows:
        item = SubElement(items, "Item")

        # Bien o Servicio
        bos = txt(r.get("Items_BienOServicio") or "B")
        SubElement(item, "Type").text = "Bien" if bos == "B" else "Servicio"
        
        # Elimino Code por validación de esquema
        # SubElement(item, "Code").text = txt(r.get("Items_NumeroLinea"))
        
        SubElement(item, "Description").text = txt(r.get("Items_Descripcion"), "-")
        SubElement(item, "Qty").text = qty(r.get("Items_Cantidad", 1))
        SubElement(item, "UnitOfMeasure").text = txt(r.get("Items_UnidadMedida") or "UNI")
        SubElement(item, "Price").text = money(r.get("Items_PrecioUnitario"))
        
        # Discounts
        discount_val = float(r.get("Items_Descuento", 0) or 0)
        discounts = SubElement(item, "Discounts")
        disc_node = SubElement(discounts, "Discount")
        SubElement(disc_node, "Amount").text = money(discount_val)

        # Totales linea
        taxable = float(r.get("Items_IVA_MontoGravable", 0) or 0)
        tax = float(r.get("Items_IVA_MontoImpuesto", 0) or 0)
        line_total = float(r.get("Items_Total", 0) or 0) # Debe coincidir con (Price*Qty - Disc + Tax)

        total_tax += tax
        grand_total += line_total

        taxes = SubElement(item, "Taxes")
        t = SubElement(taxes, "Tax")
        SubElement(t, "Code").text = "1" # IVA
        SubElement(t, "Description").text = "IVA"
        SubElement(t, "TaxableAmount").text = money(taxable)
        SubElement(t, "Amount").text = money(tax)

        it = SubElement(item, "Totals")
        SubElement(it, "TotalItem").text = money(line_total)

    # =================================================
    # ROOT TOTALS
    # =================================================
    rt = SubElement(root, "Totals")

    if total_tax > 0:
        tt = SubElement(rt, "TotalTaxes")
        tax_node = SubElement(tt, "TotalTax")
        SubElement(tax_node, "Description").text = "IVA"
        SubElement(tax_node, "Amount").text = money(total_tax)

    gt = SubElement(rt, "GrandTotal")
    SubElement(gt, "InvoiceTotal").text = money(grand_total)

    # =================================================
    # ADDITIONAL DOCUMENT INFO  ✅ OBLIGATORIO
    # =================================================
    adi = SubElement(root, "AdditionalDocumentInfo")
    
    # Observaciones (Primero, para ver si el orden importa, aunque AdditionalInfo es repetible)
    info = SubElement(adi, "AdditionalInfo")
    SubElement(info, "Description").text = "Observaciones: Documento generado por BrainFEL"



    # Use tostring with unicode encoding and manual header to ensure correct format
    # Previously we tried minidom but it adds whitespace that might be problematic or unnecessary
    # We use manual string construction to ensure exact <?xml ...?> format
    xml_body = tostring(root, encoding="unicode")
    xml = f'<?xml version="1.0" encoding="utf-8"?>\n{xml_body}'
    
    print(f"DEBUG NUC XML LEN: {len(xml)}")

    # Save to file as requested
    try:
        import os
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"nuc_{ts}.xml"
        # Adjust path relative to this file or use absolute path
        save_dir = "/home/frappe/frappe-bench/apps/brainfel/brainfel/services/generated_xmls"
        save_path = os.path.join(save_dir, fname)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
            
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"DEBUG: XML Saved to {save_path}")
    except Exception as e:
        print(f"DEBUG: Error saving XML file: {e}")
    
    return {"xml": xml, "type": doc_type}