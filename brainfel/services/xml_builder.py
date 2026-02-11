# brainfel/brainfel/services/xml_builder.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import re
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


FEL_NS = "http://www.sat.gob.gt/dte/fel/0.2.0"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def _norm_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _require(v: Any, label: str) -> str:
    s = _norm_str(v)
    if not s:
        raise ValueError(f"XML FEL: campo obligatorio vacío: {label}")
    return s


def _norm_country(v: Any) -> str:
    s = _norm_str(v)
    if not s:
        return "GT"
    s_up = s.upper()
    if re.fullmatch(r"[A-Z]{2}", s_up):
        return s_up
    if s_up in {"GUATEMALA", "GTM", "GT"}:
        return "GT"
    return "GT"


def _to_decimal(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fmt_num(v: Any, decimals: int = 6) -> str:
    n = _to_decimal(v)
    q = Decimal("1." + ("0" * decimals))
    s = str(n.quantize(q))
    # quitar ceros finales
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def _pretty_xml(elem: Element) -> str:
    raw = tostring(elem, encoding="utf-8", xml_declaration=True)
    parsed = minidom.parseString(raw)
    return parsed.toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")


def _parse_frases(frases_raw: str) -> List[Tuple[str, str]]:
    s = _norm_str(frases_raw)
    if not s:
        return []
    s = s.replace(";", ",")
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out: List[Tuple[str, str]] = []
    for p in parts:
        if "|" in p:
            a, b = p.split("|", 1)
        elif ":" in p:
            a, b = p.split(":", 1)
        else:
            continue
        a = a.strip()
        b = b.strip()
        if a and b:
            out.append((a, b))
    return out


def build_xml_from_dataset(dataset: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    XML FEL SAT 0.2.0 (Digifact NUC) — alineado a tus XML originales:
    - Root: dte:GTDocumento Version="0.1"
    - SAT: dte:SAT ClaseDocumento="dte"
    Retorna: {"xml": "...", "type": "<TipoDTE>"}
    """
    if not dataset:
        raise ValueError("Dataset vacío: no se puede generar XML.")

    h = dataset[0]

    tipo_dte = _norm_str(h.get("DatosGenerales_Tipo") or h.get("TipoDocumento") or "FACT")
    fecha = _require(h.get("DatosGenerales_FechaHoraEmision"), "DatosGenerales_FechaHoraEmision")
    moneda = _require(h.get("DatosGenerales_CodigoMoneda") or "GTQ", "DatosGenerales_CodigoMoneda")

    # ROOT EXACTO como tus XML originales
    root = Element(
        "dte:GTDocumento",
        {
            "xmlns:dte": FEL_NS,
            "xmlns:xsi": XSI_NS,
            "Version": "0.1",
        },
    )

    sat = SubElement(root, "dte:SAT", {"ClaseDocumento": "dte"})
    dte = SubElement(sat, "dte:DTE", {"ID": "DatosCertificados"})
    datos_emision = SubElement(dte, "dte:DatosEmision", {"ID": "DatosEmision"})

    # DatosGenerales
    dg_attrib = {"FechaHoraEmision": fecha, "CodigoMoneda": moneda, "Tipo": tipo_dte}
    na = _norm_str(h.get("DatosGenerales_NumeroAcceso"))
    if na:
        dg_attrib["NumeroAcceso"] = na
    SubElement(datos_emision, "dte:DatosGenerales", dg_attrib)

    # Emisor (obligatorios)
    emisor = SubElement(
        datos_emision,
        "dte:Emisor",
        {
            "NITEmisor": _require(h.get("Emisor_NITEmisor"), "Emisor_NITEmisor"),
            "NombreEmisor": _require(h.get("Emisor_NombreEmisor"), "Emisor_NombreEmisor"),
            "CodigoEstablecimiento": _norm_str(h.get("Emisor_CodigoEstablecimiento") or "1"),
            "NombreComercial": _require(h.get("Emisor_NombreComercial"), "Emisor_NombreComercial"),
            "AfiliacionIVA": _norm_str(h.get("Emisor_AfiliacionIVA") or "GEN"),
        },
    )

    dir_emisor = SubElement(emisor, "dte:DireccionEmisor")

    # IMPORTANTÍSIMO: NO permitir vacío (en tu XML impreso salió <Direccion />)
    SubElement(dir_emisor, "dte:Direccion").text = _require(
        h.get("Emisor_DireccionEmisor_Direccion"), "Emisor_DireccionEmisor_Direccion"
    )
    SubElement(dir_emisor, "dte:CodigoPostal").text = _norm_str(h.get("Emisor_DireccionEmisor_CodigoPostal") or "01001")
    SubElement(dir_emisor, "dte:Municipio").text = _norm_str(h.get("Emisor_DireccionEmisor_Municipio") or "GUATEMALA")
    SubElement(dir_emisor, "dte:Departamento").text = _norm_str(h.get("Emisor_DireccionEmisor_Departamento") or "GUATEMALA")
    SubElement(dir_emisor, "dte:Pais").text = _norm_country(h.get("Emisor_DireccionEmisor_Pais"))

    # Receptor
    receptor_id = _norm_str(h.get("Receptor_IDReceptor") or "CF")
    receptor_nombre = _norm_str(h.get("Receptor_NombreReceptor") or "CONSUMIDOR FINAL")

    receptor_attrib = {"IDReceptor": receptor_id, "NombreReceptor": receptor_nombre}

    correo = _norm_str(h.get("Receptor_CorreoReceptor"))
    if correo:
        receptor_attrib["CorreoReceptor"] = correo

    tipo_especial = _norm_str(h.get("Receptor_TipoEspecial"))
    if tipo_especial:
        receptor_attrib["TipoEspecial"] = tipo_especial

    receptor = SubElement(datos_emision, "dte:Receptor", receptor_attrib)

    # DireccionReceptor (siempre)
    dir_r = _norm_str(h.get("Receptor_DireccionReceptor_Direccion")) or "CIUDAD"
    cp_r = _norm_str(h.get("Receptor_DireccionReceptor_CodigoPostal")) or "01001"
    mun_r = _norm_str(h.get("Receptor_DireccionReceptor_Municipio")) or "GUATEMALA"
    dep_r = _norm_str(h.get("Receptor_DireccionReceptor_Departamento")) or "GUATEMALA"
    pais_r = _norm_country(h.get("Receptor_DireccionReceptor_Pais"))

    dir_receptor = SubElement(receptor, "dte:DireccionReceptor")
    SubElement(dir_receptor, "dte:Direccion").text = dir_r
    SubElement(dir_receptor, "dte:CodigoPostal").text = cp_r
    SubElement(dir_receptor, "dte:Municipio").text = mun_r
    SubElement(dir_receptor, "dte:Departamento").text = dep_r
    SubElement(dir_receptor, "dte:Pais").text = pais_r

    # Frases: si no vienen, usar default 1|1 (como tus XML originales FACT)
    frases_list = _parse_frases(_norm_str(h.get("Frases_Escenarios")))
    if not frases_list:
        frases_list = [("1", "1")]

    frases = SubElement(datos_emision, "dte:Frases")
    for tipo_frase, cod_esc in frases_list:
        SubElement(frases, "dte:Frase", {"TipoFrase": tipo_frase, "CodigoEscenario": cod_esc})

    # Items
    items_node = SubElement(datos_emision, "dte:Items")

    for row in dataset:
        num_linea = _norm_str(row.get("Items_NumeroLinea"))
        if not num_linea:
            continue

        item = SubElement(items_node, "dte:Item", {
            "NumeroLinea": num_linea,
            "BienOServicio": _norm_str(row.get("Items_BienOServicio") or "B"),
        })

        SubElement(item, "dte:Cantidad").text = _fmt_num(row.get("Items_Cantidad"), 6)
        SubElement(item, "dte:UnidadMedida").text = _norm_str(row.get("Items_UnidadMedida") or "UND")
        SubElement(item, "dte:Descripcion").text = _require(row.get("Items_Descripcion"), "Items_Descripcion")
        SubElement(item, "dte:PrecioUnitario").text = _fmt_num(row.get("Items_PrecioUnitario"), 6)
        SubElement(item, "dte:Precio").text = _fmt_num(row.get("Items_Precio"), 6)
        SubElement(item, "dte:Descuento").text = _fmt_num(row.get("Items_Descuento"), 6)

        impuestos_node = SubElement(item, "dte:Impuestos")
        imp = SubElement(impuestos_node, "dte:Impuesto")

        SubElement(imp, "dte:NombreCorto").text = _norm_str(row.get("Items_IVA_NombreCorto") or "IVA")
        SubElement(imp, "dte:CodigoUnidadGravable").text = _norm_str(row.get("Items_IVA_CodigoUnidadGravable") or "1")
        SubElement(imp, "dte:MontoGravable").text = _fmt_num(row.get("Items_IVA_MontoGravable"), 6)
        SubElement(imp, "dte:MontoImpuesto").text = _fmt_num(row.get("Items_IVA_MontoImpuesto"), 6)

        SubElement(item, "dte:Total").text = _fmt_num(row.get("Items_Total"), 6)

    # Totales
    totales = SubElement(datos_emision, "dte:Totales")
    total_impuestos = SubElement(totales, "dte:TotalImpuestos")

    total_iva = _norm_str(h.get("Totales_TotalIVA_TotalMontoImpuesto"))
    if not total_iva:
        total_iva_val = sum(_to_decimal(r.get("Items_IVA_MontoImpuesto")) for r in dataset)
        total_iva = _fmt_num(total_iva_val, 6)

    SubElement(total_impuestos, "dte:TotalImpuesto", {
        "NombreCorto": "IVA",
        "TotalMontoImpuesto": _fmt_num(total_iva, 6),
    })

    gran_total = _norm_str(h.get("Totales_GranTotal"))
    if not gran_total:
        gt_val = sum(_to_decimal(r.get("Items_Total")) for r in dataset)
        gran_total = _fmt_num(gt_val, 6)

    SubElement(totales, "dte:GranTotal").text = _fmt_num(gran_total, 6)

    return {"xml": _pretty_xml(root), "type": tipo_dte}