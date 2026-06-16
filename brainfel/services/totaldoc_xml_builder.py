# brainfel/services/totaldoc_xml_builder.py
from typing import Any, Dict, List
from xml.etree.ElementTree import Element, SubElement, tostring, register_namespace, _namespace_map
from datetime import datetime
import re

DTE_NS = "http://www.sat.gob.gt/dte/fel/0.2.0"
CFC_NS = "http://www.sat.gob.gt/dte/fel/CompCambiaria/0.1.0"
CEX_NS = "http://www.sat.gob.gt/face2/ComplementoExportaciones/0.1.0"
CNO_NS = "http://www.sat.gob.gt/face2/ComplementoReferenciaNota/0.1.0"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

_namespace_map[DTE_NS] = "dte"
_namespace_map[CFC_NS] = "cfc"
_namespace_map[CEX_NS] = "cex"
_namespace_map[CNO_NS] = "cno"
_namespace_map[XSI_NS] = "xsi"

register_namespace("dte", DTE_NS)
register_namespace("cfc", CFC_NS)
register_namespace("cex", CEX_NS)
register_namespace("cno", CNO_NS)
register_namespace("xsi", XSI_NS)

def dte(tag): return f"{{{DTE_NS}}}{tag}"
def cfc(tag): return f"{{{CFC_NS}}}{tag}"
def cex(tag): return f"{{{CEX_NS}}}{tag}"
def cno(tag): return f"{{{CNO_NS}}}{tag}"

def build_totaldoc_xml(rows: List[Dict[str, Any]], settings=None) -> Dict[str, str]:
    if not rows:
        raise ValueError("Dataset vacío")

    h = rows[0]

    def txt(v, default=""):
        if v is None: return default
        s = str(v).strip()
        return s if s else default

    doc_type = txt(h.get("DatosGenerales_Tipo") or h.get("TipoDocumento") or "FACT")
    is_export = str(h.get("bfel_es_exportacion")).strip() == "1"
    
    afiliacion = txt(h.get("Emisor_AfiliacionIVA"), "GEN")
    is_pequeno = False
    if settings and getattr(settings, "pequeño_contribuyente", 0):
        is_pequeno = True
    elif afiliacion.upper() == "PEQ" or doc_type == "FPEQ":
        is_pequeno = True

    frases_raw = txt(h.get("Frases_Escenarios"))
    if frases_raw and "4|1" in frases_raw:
        is_export = True

    def money(v) -> str:
        try:
            val = float(v)
            if doc_type in ["NCRE", "NDEB"]: val = abs(val)
            return f"{val:.6f}"
        except Exception: return "0.000000"

    def money_totals(v) -> str:
        try:
            val = float(v)
            if doc_type in ["NCRE", "NDEB"]: val = abs(val)
            # Generalmente totales requieren menos decimales pero lo dejamos en 6 por si acaso
            # O mejor lo ajustamos a lo que el SAT pide usualmente (hasta 6)
            s = f"{val:.6f}"
            if "." in s: s = s.rstrip("0").rstrip(".")
            if not s: s = "0"
            return s
        except Exception: return "0"

    def qty(v) -> str:
        try:
            val = float(v)
            if doc_type in ["NCRE", "NDEB"]: val = abs(val)
            s = f"{val:.6f}"
            if "." in s: s = s.rstrip("0").rstrip(".")
            if not s: s = "0"
            return s
        except Exception: return "1"

    def issued_dt(val=None) -> str:
        if val:
            dt_str = f"{val}".replace(" ", "T")
            if "+" not in dt_str and "-" not in dt_str[11:]:
                dt_str = f"{dt_str}-06:00"
            return dt_str
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00")

    def norm_country(v) -> str:
        s = txt(v).upper()
        if s in ["GUATEMALA", "GTM", "GT"]: return "GT"
        return s if len(s) == 2 else "GT"

    root = Element(dte("GTDocumento"), {"Version": "0.1"})
    sat = SubElement(root, dte("SAT"), {"ClaseDocumento": "dte"})
    dte_node = SubElement(sat, dte("DTE"), {"ID": "DatosCertificados"})
    datos_emision = SubElement(dte_node, dte("DatosEmision"), {"ID": "DatosEmision"})

    # DATOS GENERALES
    dg_attrs = {
        "Tipo": doc_type,
        "FechaHoraEmision": issued_dt(h.get("DatosGenerales_FechaHoraEmision")),
        "CodigoMoneda": txt(h.get("DatosGenerales_CodigoMoneda") or "GTQ")
    }
    if is_export:
        dg_attrs["Exp"] = "SI"
        
    SubElement(datos_emision, dte("DatosGenerales"), dg_attrs)

    # EMISOR
    emisor_attrs = {
        "NITEmisor": txt(h.get("Emisor_NITEmisor")).replace("-", ""),
        "NombreEmisor": txt(h.get("Emisor_NombreEmisor")),
        "CodigoEstablecimiento": txt(h.get("Emisor_CodigoEstablecimiento"), "1"),
        "NombreComercial": txt(h.get("Emisor_NombreComercial") or h.get("Emisor_NombreEmisor")),
        "AfiliacionIVA": txt(h.get("Emisor_AfiliacionIVA"), "GEN")
    }
    correo_emisor = txt(h.get("Emisor_CorreoEmisor"))
    if correo_emisor: emisor_attrs["CorreoEmisor"] = correo_emisor
    
    emisor = SubElement(datos_emision, dte("Emisor"), emisor_attrs)

    dir_emisor = SubElement(emisor, dte("DireccionEmisor"))
    SubElement(dir_emisor, dte("Direccion")).text = txt(h.get("Emisor_DireccionEmisor_Direccion"), "CIUDAD")
    SubElement(dir_emisor, dte("CodigoPostal")).text = txt(h.get("Emisor_DireccionEmisor_CodigoPostal"), "01001")
    SubElement(dir_emisor, dte("Municipio")).text = txt(h.get("Emisor_DireccionEmisor_Municipio"), "GUATEMALA")
    SubElement(dir_emisor, dte("Departamento")).text = txt(h.get("Emisor_DireccionEmisor_Departamento"), "GUATEMALA")
    SubElement(dir_emisor, dte("Pais")).text = norm_country(h.get("Emisor_DireccionEmisor_Pais"))

    # RECEPTOR
    nit_receptor = txt(h.get("Receptor_IDReceptor")).strip().replace("-", "").upper()
    if not nit_receptor or nit_receptor == "CF":
        nit_receptor = "CF"
        nombre_receptor = "CONSUMIDOR FINAL"
    else:
        nombre_receptor = txt(h.get("Receptor_NombreReceptor"))

    rec_attrs = {
        "IDReceptor": nit_receptor,
        "NombreReceptor": nombre_receptor
    }
    correo_receptor = txt(h.get("Receptor_CorreoReceptor"))
    if correo_receptor: rec_attrs["CorreoReceptor"] = correo_receptor

    tipo_especial = txt(h.get("Receptor_TipoEspecial")).upper()
    is_cui = (tipo_especial in ["CUI DPI", "CUI"]) or (len(nit_receptor) == 13 and nit_receptor.isdigit())
    if is_cui:
        rec_attrs["TipoEspecial"] = "CUI"

    receptor = SubElement(datos_emision, dte("Receptor"), rec_attrs)

    dir_receptor = SubElement(receptor, dte("DireccionReceptor"))
    SubElement(dir_receptor, dte("Direccion")).text = txt(h.get("Receptor_DireccionReceptor_Direccion") or "CIUDAD")
    SubElement(dir_receptor, dte("CodigoPostal")).text = txt(h.get("Receptor_DireccionReceptor_CodigoPostal") or "01001")
    SubElement(dir_receptor, dte("Municipio")).text = txt(h.get("Receptor_DireccionReceptor_Municipio") or "GUATEMALA")
    SubElement(dir_receptor, dte("Departamento")).text = txt(h.get("Receptor_DireccionReceptor_Departamento") or "GUATEMALA")
    SubElement(dir_receptor, dte("Pais")).text = norm_country(h.get("Receptor_DireccionReceptor_Pais"))

    # FRASES
    final_phrases = []
    seen_phrases = set()

    def add_phrase(p_str):
        p_str = p_str.strip()
        if not p_str: return
        if "|" in p_str:
            tf, sc = p_str.split("|")[0].strip(), p_str.split("|")[1].strip()
        else:
            tf, sc = "1", p_str.strip()
        if tf == "1" and sc == "44": return
        if sc == "0" or not sc: return
        pair_key = f"{tf}|{sc}"
        if pair_key in seen_phrases: return
        final_phrases.append((tf, sc))
        seen_phrases.add(pair_key)

    if frases_raw:
        for p in frases_raw.replace(";", ",").split(","):
            add_phrase(p)
            
    # 1b. If the emisor is a small taxpayer (Es Pequeño Contribuyente), add Type 3 Scenario 1
    if is_pequeno:
        add_phrase("3|1")
    
    has_type_1 = any(f[0] == "1" for f in final_phrases)
    if not has_type_1 and not is_pequeno:
        phrase = None
        if settings and getattr(settings, "isr_regime", None):
            regime = str(settings.isr_regime).lower()
            if "trimestrales" in regime:
                phrase = "1|1"
            elif "retencion" in regime or "retención" in regime or "definitiva" in regime or "simplificado" in regime:
                phrase = "1|2"
            elif "exento" in regime:
                phrase = "1|3"
        
        if not phrase:
            if doc_type == "FCAM": phrase = "1|2"
            elif not is_export and txt(h.get("Emisor_AfiliacionIVA"), "GEN").upper() == "GEN": phrase = "1|2"
            
        if phrase:
            add_phrase(phrase)
    
    if is_export and not any(f[0] == "4" for f in final_phrases):
        add_phrase("4|1")

    unique_types = {}
    for tf, sc in final_phrases:
        if tf not in unique_types: unique_types[tf] = sc
    final_phrases = [(tf, sc) for tf, sc in unique_types.items()]

    if final_phrases:
        frases_node = SubElement(datos_emision, dte("Frases"))
        for tf, sc in final_phrases:
            SubElement(frases_node, dte("Frase"), {"TipoFrase": tf, "CodigoEscenario": sc})

    # ITEMS
    items = SubElement(datos_emision, dte("Items"))
    taxes_summary = {}
    grand_total = 0.0

    # Deduplicate items to avoid duplicate detail lines
    unique_items = []
    seen_items = set()
    for r in rows:
        line_no = txt(r.get("Items_NumeroLinea"))
        if not line_no:
            line_no = f"{txt(r.get('Items_Descripcion'))}-{qty(r.get('Items_Cantidad'))}-{money(r.get('Items_PrecioUnitario'))}"
        if line_no not in seen_items:
            seen_items.add(line_no)
            unique_items.append(r)

    for idx, r in enumerate(unique_items, start=1):
        bos = txt(r.get("Items_BienOServicio") or "B")
        item = SubElement(items, dte("Item"), {
            "NumeroLinea": str(idx),
            "BienOServicio": bos
        })
        
        SubElement(item, dte("Cantidad")).text = qty(r.get("Items_Cantidad", 1))
        SubElement(item, dte("UnidadMedida")).text = txt(r.get("Items_UnidadMedida") or "UNI")
        SubElement(item, dte("Descripcion")).text = txt(r.get("Items_Descripcion"), "-")
        SubElement(item, dte("PrecioUnitario")).text = money(r.get("Items_PrecioUnitario"))
        SubElement(item, dte("Precio")).text = money(float(r.get("Items_Cantidad", 1)) * float(r.get("Items_PrecioUnitario", 0)))
        
        discount_val = float(r.get("Items_Descuento", 0) or 0)
        SubElement(item, dte("Descuento")).text = money(discount_val)

        taxable = float(r.get("Items_IVA_MontoGravable", 0) or 0)
        tax = float(r.get("Items_IVA_MontoImpuesto", 0) or 0)
        line_total = float(r.get("Items_Total", 0) or 0)
        grand_total += line_total

        tax_code = txt(r.get("Items_IVA_CodigoUnidadGravable"))
        if not tax_code: tax_code = "2" if is_export else "1"
        if taxable == 0: taxable = (float(r.get("Items_Cantidad", 1)) * float(r.get("Items_PrecioUnitario", 0))) - discount_val
            
        if not is_pequeno:
            impuestos = SubElement(item, dte("Impuestos"))
            impuesto = SubElement(impuestos, dte("Impuesto"))
            SubElement(impuesto, dte("NombreCorto")).text = "IVA"
            SubElement(impuesto, dte("CodigoUnidadGravable")).text = tax_code
            SubElement(impuesto, dte("MontoGravable")).text = money(taxable)
            SubElement(impuesto, dte("MontoImpuesto")).text = money(tax)

            if tax_code not in taxes_summary: taxes_summary[tax_code] = 0.0
            taxes_summary[tax_code] += tax

        SubElement(item, dte("Total")).text = money(line_total)

    # TOTALES
    rt = SubElement(datos_emision, dte("Totales"))
    if not is_pequeno:
        tt = SubElement(rt, dte("TotalImpuestos"))
        if not taxes_summary:
            default_code = "2" if is_export else "1"
            taxes_summary[default_code] = 0.0

        for code, amount in taxes_summary.items():
            tax_node = SubElement(tt, dte("TotalImpuesto"), {
                "NombreCorto": "IVA",
                "TotalMontoImpuesto": money_totals(amount)
            })

    SubElement(rt, dte("GranTotal")).text = money_totals(grand_total)

    # COMPLEMENTOS
    # We add Complementos container if needed
    has_complement = is_export or doc_type == "FCAM" or doc_type in ["NCRE", "NDEB"]
    if has_complement:
        comps = SubElement(datos_emision, dte("Complementos"))
        
        if is_export:
            comp = SubElement(comps, dte("Complemento"), {
                "IDComplemento": "EXP",
                "NombreComplemento": "Exportacion",
                "URIComplemento": "http://www.sat.gob.gt/face2/ComplementoExportaciones/0.1.0"
            })
            cex_node = SubElement(comp, cex("Exportacion"), {"Version": "1"})
            
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
                    SubElement(cex_node, cex(xml_name)).text = val
                    
        elif doc_type == "FCAM":
            comp = SubElement(comps, dte("Complemento"), {
                "IDComplemento": "ID",
                "NombreComplemento": "FCAMB",
                "URIComplemento": "http://www.sat.gob.gt/dte/fel/CompCambiaria/0.1.0"
            })
            cfc_node = SubElement(comp, cfc("AbonosFacturaCambiaria"), {"Version": "1"})
            
            # Recopilar abonos explícitos de las filas
            abono_list = []
            seen_abono_keys = set()
            for r in rows:
                venc = r.get("Complementos_AbonosFacturaCambiaria_FechaVencimiento")
                if venc:
                    num = txt(r.get("Complementos_AbonosFacturaCambiaria_NumeroAbono") or str(len(abono_list) + 1))
                    monto = money_totals(r.get("Complementos_AbonosFacturaCambiaria_MontoAbono") or grand_total)
                    key = f"{num}-{venc}-{monto}"
                    if key not in seen_abono_keys:
                        seen_abono_keys.add(key)
                        abono_list.append({
                            "NumeroAbono": num,
                            "FechaVencimiento": venc[:10],
                            "MontoAbono": monto
                        })
            
            # Si no hay abonos explícitos, crear exactamente uno por defecto por el total
            if not abono_list:
                due_date = txt(h.get("due_date") or h.get("posting_date") or h.get("DatosGenerales_FechaHoraEmision") or datetime.now().strftime("%Y-%m-%d"))
                abono_list.append({
                    "NumeroAbono": "1",
                    "FechaVencimiento": due_date[:10],
                    "MontoAbono": money_totals(grand_total)
                })
                
            for a in abono_list:
                abono = SubElement(cfc_node, cfc("Abono"))
                SubElement(abono, cfc("NumeroAbono")).text = a["NumeroAbono"]
                SubElement(abono, cfc("FechaVencimiento")).text = a["FechaVencimiento"]
                SubElement(abono, cfc("MontoAbono")).text = a["MontoAbono"]
                    
        elif doc_type in ["NCRE", "NDEB"]:
            comp = SubElement(comps, dte("Complemento"), {
                "IDComplemento": "ReferenciasNota",
                "NombreComplemento": "ReferenciasNota",
                "URIComplemento": "http://www.sat.gob.gt/face2/ComplementoReferenciaNota/0.1.0"
            })
            
            val_uuid = txt(h.get("NumeroAutorizacionDocumentoOrigen")) 
            val_fecha = txt(h.get("FechaEmisionDocumentoOrigen")) 
            val_serie = txt(h.get("SerieDocumentoOrigen")) 
            val_numero = txt(h.get("NumeroDocumentoOrigen")) 
            val_motivo = txt(h.get("MotivoAjuste"))
            
            SubElement(comp, cno("ReferenciasNota"), {
                "Version": "0",
                "NumeroAutorizacionDocumentoOrigen": val_uuid,
                "SerieDocumentoOrigen": val_serie,
                "NumeroDocumentoOrigen": val_numero,
                "FechaEmisionDocumentoOrigen": val_fecha[:10],
                "MotivoAjuste": val_motivo
            })

    # ADENDA
    adenda = SubElement(sat, dte("Adenda"))
    SubElement(adenda, "Adenda1").text = txt(h.get("name") or "Adenda Info")

    xml_body = tostring(root, encoding="unicode", method="xml")
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + xml_body

    return {"xml": xml, "type": doc_type}
