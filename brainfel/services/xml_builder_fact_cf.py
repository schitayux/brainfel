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

    doc_type = txt(h.get("DatosGenerales_Tipo") or h.get("TipoDocumento") or "FACT")
    # SQL views might return 1 as int or '1' as string
    is_export = str(h.get("bfel_es_exportacion")).strip() == "1"
    
    frases_raw = txt(h.get("Frases_Escenarios"))
    # If the user sends 4|1 in the phrase field, it's an export even if bfel_es_exportacion is missing
    if frases_raw and "4|1" in frases_raw:
        is_export = True

    def money(v) -> str:
        try:
            val = float(v)
            if doc_type == "NCRE":
                val = abs(val)
            return f"{val:.6f}"
        except Exception:
            return "0.000000"

    def qty(v) -> str:
        try:
            val = float(v)
            if doc_type == "NCRE":
                val = abs(val)
            return f"{val:.6f}"
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
    header = SubElement(root, "Header")
    SubElement(header, "DocType").text = doc_type
    SubElement(header, "IssuedDateTime").text = issued_dt(h.get("DatosGenerales_FechaHoraEmision"))
    SubElement(header, "Currency").text = txt(
        h.get("DatosGenerales_CodigoMoneda") or "GTQ"
    )

    if is_export:
        aidi = SubElement(header, "AdditionalIssueDocInfo")
        SubElement(aidi, "Info", {"Name": "Exp", "Value": "SI"})

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
    # We build a list of unique phrases, ensuring mandatory ones exist
    final_phrases = []
    seen_phrases = set()

    def add_phrase(p_str):
        p_str = p_str.strip()
        if not p_str:
            return
            
        if "|" in p_str:
            parts = p_str.split("|")
            tf, sc = parts[0].strip(), parts[1].strip()
        else:
            tf, sc = "1", p_str.strip()
            
        # Ignore invalid scenarios that the SQL view might be sending by mistake
        # Scenario 44 is not valid for Type 1 and conflicts with the correct 1|2 phrase
        if tf == "1" and sc == "44":
            return
            
        # Deduplicate based on final (tf, sc) pair
        pair_key = f"{tf}|{sc}"
        if pair_key in seen_phrases:
            return

        final_phrases.append((tf, sc))
        seen_phrases.add(pair_key)

    # 1. Start with phrases from SQL
    if frases_raw:
        for p in frases_raw.replace(";", ",").split(","):
            add_phrase(p)
    
    # 2. Ensure Type 1 (ISR/Exento) exists if needed. 
    # Defaulting to 1|2 (ISR Retención) as it is required for ISR OPC issuers 
    # and has been the working default for this company.
    # FCAM ALWAYS requires a Type 1 phrase, regardless of whether it is an export or not.
    has_type_1 = any(f[0] == "1" for f in final_phrases)
    
    if not has_type_1:
        if doc_type == "FCAM":
            add_phrase("1|2")
        elif not is_export and afiliacion.upper() == "GEN":
            add_phrase("1|2")
    
    # 3. Ensure Type 4 (Export) exists if it's an export
    if is_export and not any(f[0] == "4" for f in final_phrases):
        add_phrase("4|1")

    # FINAL DEDUPLICATION BY TYPE: SAT only allows ONE phrase per type
    unique_types = {}
    for tf, sc in final_phrases:
        if tf not in unique_types:
            unique_types[tf] = sc
    
    final_phrases = [(tf, sc) for tf, sc in unique_types.items()]

    if final_phrases:
        phrases_node = SubElement(seller, "AdditionlInfo")
        for ie, (tf, sc) in enumerate(final_phrases):
            pid = str(ie + 1)
            SubElement(phrases_node, "Info", {"Name": "TipoFrase", "Data": pid, "Value": tf})
            SubElement(phrases_node, "Info", {"Name": "Escenario", "Data": pid, "Value": sc})

    branch = SubElement(seller, "BranchInfo")
    SubElement(branch, "Code").text = txt(h.get("Emisor_CodigoEstablecimiento") or "1")
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

    # Support for CUI / DPI (Manual flag or automatic detection by length)
    tipo_especial = txt(h.get("Receptor_TipoEspecial")).upper()
    is_cui = (tipo_especial in ["CUI DPI", "CUI"]) or (len(nit_receptor) == 13 and nit_receptor.isdigit())
    
    if is_cui:
        SubElement(buyer, "TaxIDType").text = "CUI"

    SubElement(buyer, "Name").text = nombre_receptor
    
    # Contact/EmailList as per new structure - MUST BE BEFORE AddressInfo
    email_receptor = txt(h.get("Receptor_CorreoReceptor"))
    if email_receptor:
        contact = SubElement(buyer, "Contact")
        email_list = SubElement(contact, "EmailList")
        SubElement(email_list, "Email").text = email_receptor

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

    taxes_summary = {} # Group taxes by code for the footer
    grand_total = 0.0

    for r in rows:
        item = SubElement(items, "Item")

        # Bien o Servicio
        bos = txt(r.get("Items_BienOServicio") or "B")
        SubElement(item, "Type").text = "Bien" if bos == "B" else "Servicio"
        
        # Elimino Code por validación de esquema (no permitido en este NUC)
        # SubElement(item, "Code").text = txt(r.get("Items_NumeroLinea") or (rows.index(r) + 1))
        
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

        grand_total += line_total

        taxes = SubElement(item, "Taxes")
        t = SubElement(taxes, "Tax")
        # Respect the dataset's tax code (e.g., 2 for Exempt). 
        # Only fall back to defaults if not provided.
        tax_code = txt(r.get("Items_IVA_CodigoUnidadGravable"))
        if not tax_code:
            tax_code = "2" if is_export else "1"
            
        if taxable == 0:
            taxable = (float(r.get("Items_Cantidad", 1)) * float(r.get("Items_PrecioUnitario", 0))) - discount_val
            
        SubElement(t, "Code").text = tax_code
        SubElement(t, "Description").text = "IVA"
        SubElement(t, "TaxableAmount").text = money(taxable)
        SubElement(t, "Amount").text = f"{tax:.2f}"

        # Track for footer
        if tax_code not in taxes_summary:
            taxes_summary[tax_code] = 0.0
        taxes_summary[tax_code] += tax

        it = SubElement(item, "Totals")
        SubElement(it, "TotalItem").text = money(line_total)

    # =================================================
    # ROOT TOTALS
    # =================================================
    rt = SubElement(root, "Totals")

    # Always include TotalTaxes, even if 0, for Exempt/Export validation (Error 5004)
    tt = SubElement(rt, "TotalTaxes")
    
    # If no taxes recorded (exempt), ensure at least one TotalTax node exists
    if not taxes_summary:
        default_code = "2" if is_export else "1"
        taxes_summary[default_code] = 0.0

    for code, amount in taxes_summary.items():
        tax_node = SubElement(tt, "TotalTax")
        # Removing Code node from footer to match working export XMLs
        # SubElement(tax_node, "Code").text = code
        SubElement(tax_node, "Description").text = "IVA"
        # Digifact suele requerir exactamente 2 decimales en los totales de impuestos
        SubElement(tax_node, "Amount").text = f"{amount:.2f}"

    gt = SubElement(rt, "GrandTotal")
    SubElement(gt, "InvoiceTotal").text = money(grand_total)

    # =================================================
    # ADDITIONAL DOCUMENT INFO (Observaciones y Complementos FCAM, EXP, NCRE)
    # =================================================
    adi = SubElement(root, "AdditionalDocumentInfo")

    if is_export:
        # Export Complement - Mandatory for exports
        exp_ai = SubElement(adi, "AdditionalInfo")
        SubElement(exp_ai, "Code").text = "EXP"
        SubElement(exp_ai, "Type").text = "COMPLEMENTO"
        exp_node = SubElement(exp_ai, "AditionalInfo")
        
        mapping = {
            "NombreConsignatarioODestinatario": "Complementos_exportacion_NombreConsignatarioODestinatario",
            "DireccionConsignatarioODestinatario": "Complementos_exportacion_DireccionConsignatarioODestinatario",
            "CodigoConsignatarioODestinatario": "Complementos_exportacion_CodigoConsignatarioODestinatario",
            "NombreComprador": "Complementos_exportacion_NombreComprador",
            "DireccionComprador": "Complementos_exportacion_DireccionComprador",
            "CodigoComprador": "Complementos_exportacion_CodigoComprador",
            "INCOTERM": "Complementos_exportacion_INCOTERM",
            "OtraReferencia": "Complementos_exportacion_OtraReferencia",
            "NombreExportador": "Complementos_exportacion_NombreExportador",
            "CodigoExportador": "Complementos_exportacion_CodigoExportador"
        }
        
        for xml_name, ds_key in mapping.items():
            val = txt(h.get(ds_key))
            if val:
                # INCOTERM might require Data attribute as per example, but usually empty
                attrs = {"Name": xml_name, "Value": val}
                if xml_name == "INCOTERM":
                    attrs["Data"] = ""
                SubElement(exp_node, "Info", attrs)
    
    if doc_type == "FCAM":
        # FCAM Complemento - New Structure
        comp_ai = SubElement(adi, "AdditionalInfo")
        SubElement(comp_ai, "Code").text = "FCAMB"
        SubElement(comp_ai, "Type").text = "COMPLEMENTO"
        
        # Usamos AditionalData con una sola 'd' como pide Digifact NUC
        comp_data_node = SubElement(comp_ai, "AditionalData")
        
        idx = 1
        processed_keys = set()
        for r in rows:
            num = txt(r.get("Complementos_AbonosFacturaCambiaria_NumeroAbono"), str(idx))
            f_venc = txt(r.get("Complementos_AbonosFacturaCambiaria_FechaVencimiento") or h.get("DatosGenerales_FechaHoraEmision") or datetime.now().strftime("%Y-%m-%d"))
            m_abono = money(r.get("Complementos_AbonosFacturaCambiaria_MontoAbono") or grand_total)
            
            key = f"{num}-{f_venc}-{m_abono}"
            if key not in processed_keys:
                data_node = SubElement(comp_data_node, "Data")
                SubElement(data_node, "Info", {"Name": "NumeroAbono", "Value": num})
                SubElement(data_node, "Info", {"Name": "FechaVencimiento", "Value": f_venc[:10]})
                SubElement(data_node, "Info", {"Name": "MontoAbono", "Value": m_abono})
                
                processed_keys.add(key)
                idx += 1

    if doc_type in ["NCRE", "NDEB"]:
        # NCRE/NDEB Complement - Reference to original document
        ref_ai = SubElement(adi, "AdditionalInfo")
        SubElement(ref_ai, "Code").text = doc_type
        SubElement(ref_ai, "Type").text = "COMPLEMENTO"
        
        # Digifact NUC for NCRE/NDEB requires AditionalInfo (one 'd') instead of AditionalData
        comp_ref_node = SubElement(ref_ai, "AditionalInfo")
        
        # Mapping fields from dataset with individual fallbacks from example
        val_uuid = txt(h.get("NumeroAutorizacionDocumentoOrigen")) 
        val_fecha = txt(h.get("FechaEmisionDocumentoOrigen")) 
        val_serie = txt(h.get("SerieDocumentoOrigen")) 
        val_numero = txt(h.get("NumeroDocumentoOrigen")) 
        val_motivo = txt(h.get("MotivoAjuste")) 

        SubElement(comp_ref_node, "Info", {"Name": "NumeroAutorizacionDocumentoOrigen", "Value": val_uuid})
        SubElement(comp_ref_node, "Info", {"Name": "FechaEmisionDocumentoOrigen", "Value": val_fecha[:10]})
        SubElement(comp_ref_node, "Info", {"Name": "MotivoAjuste", "Value": val_motivo})
        SubElement(comp_ref_node, "Info", {"Name": "SerieDocumentoOrigen", "Value": val_serie})
        SubElement(comp_ref_node, "Info", {"Name": "NumeroDocumentoOrigen", "Value": val_numero})

    # ADENDA section
    adenda_ai = SubElement(adi, "AdditionalInfo")
    # Usamos el name del documento como referencia interna si existe
    internal_ref = txt(h.get("Next_Identificador") or "BRAINFEL-REF")
    SubElement(adenda_ai, "Code").text = internal_ref
    SubElement(adenda_ai, "Type").text = "ADENDA"
    
    adenda_data = SubElement(adenda_ai, "AditionalData")
    
    # INFORMACION_ADICIONAL
    info_adj = SubElement(adenda_data, "Data", {"Name": "INFORMACION_ADICIONAL"})

    observaciones = txt(
        h.get("Next_Identificador")
        or h.get("name")
        or "Documento generado por Soluciones Integrales Chapp, S.A."
    )

    SubElement(
        info_adj,
        "Info",
        {
            "Name": "OBSERVACIONES",
            "Value": observaciones
        }
    )
    # Cantidad en letras si está disponible en el dataset
    letras = txt(h.get("Totales_GranTotal_Letras"))
    if letras:
        SubElement(info_adj, "Info", {"Name": "CANTIDAD_LETRAS", "Value": letras})

    # VALIDAR_REFERENCIA_INTERNA en AditionalInfo
    val_ref = SubElement(adenda_ai, "AditionalInfo")
    SubElement(val_ref, "Info", {"Name": "VALIDAR_REFERENCIA_INTERNA", "Value": "NO_VALIDAR"})

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