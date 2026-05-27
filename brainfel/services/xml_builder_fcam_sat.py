# =========================================================
# FILE:
# apps/brainfel/brainfel/services/xml_builder_fcam_sat.py
# =========================================================

from typing import Any, Dict, List
from xml.etree.ElementTree import (
    Element,
    SubElement,
    tostring,
    register_namespace,
    _namespace_map,
)
from datetime import datetime
import os


# =========================================================
# NAMESPACES
# =========================================================

DTE_NS = "http://www.sat.gob.gt/dte/fel/0.2.0"
CFC_NS = "http://www.sat.gob.gt/dte/fel/CompCambiaria/0.1.0"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
DTECOMM_NS = "https://www.digifact.com.gt/dtecomm"

# FORZAR PREFIJOS
_namespace_map[DTE_NS] = "dte"
_namespace_map[CFC_NS] = "cfc"
_namespace_map[XSI_NS] = "xsi"
_namespace_map[DTECOMM_NS] = "dtecomm"

register_namespace("dte", DTE_NS)
register_namespace("cfc", CFC_NS)
register_namespace("xsi", XSI_NS)
register_namespace("dtecomm", DTECOMM_NS)


# =========================================================
# HELPERS
# =========================================================

def dte(tag: str) -> str:
    return f"{{{DTE_NS}}}{tag}"


def cfc(tag: str) -> str:
    return f"{{{CFC_NS}}}{tag}"


# =========================================================
# MAIN
# =========================================================

def build_fcam_sat_xml(rows: List[Dict[str, Any]]) -> Dict[str, str]:

    if not rows:
        raise ValueError("Dataset vacío")

    h = rows[0]

    # =====================================================
    # HELPERS
    # =====================================================

    def txt(v, default=""):

        if v is None:
            return default

        s = str(v).strip()

        return s if s else default

    def money(v):

        try:
            return f"{float(v):.4f}"
        except Exception:
            return "0.0000"

    def qty(v):

        try:
            return f"{float(v):.4f}"
        except Exception:
            return "1.0000"

    def issued_dt(v=None):

        if v:
            return str(v).replace(" ", "T")

        return datetime.now().strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

    def country(v):

        s = txt(v).upper()

        if s in ("GT", "GTM", "GUATEMALA"):
            return "GT"

        return s if len(s) == 2 else "GT"

    # =====================================================
    # ROOT
    # =====================================================

    root = Element(
        dte("GTDocumento"),
        {
            "Version": "0.1",
        },
    )

    # =====================================================
    # SAT
    # =====================================================

    sat = SubElement(
        root,
        dte("SAT"),
        {
            "ClaseDocumento": "dte",
        },
    )

    dte_node = SubElement(
        sat,
        dte("DTE"),
        {
            "ID": "DatosCertificados",
        },
    )

    datos_emision = SubElement(
        dte_node,
        dte("DatosEmision"),
        {
            "ID": "DatosEmision",
        },
    )

    # =====================================================
    # DATOS GENERALES
    # =====================================================

    SubElement(
        datos_emision,
        dte("DatosGenerales"),
        {
            "Tipo": "FCAM",
            "FechaHoraEmision": issued_dt(
                h.get("DatosGenerales_FechaHoraEmision")
            ),
            "CodigoMoneda": txt(
                h.get("DatosGenerales_CodigoMoneda"),
                "GTQ",
            ),
        },
    )

    # =====================================================
    # EMISOR
    # =====================================================

    emisor = SubElement(
        datos_emision,
        dte("Emisor"),
        {
            "NITEmisor": txt(
                h.get("Emisor_NITEmisor")
            ).replace("-", ""),
            "NombreEmisor": txt(
                h.get("Emisor_NombreEmisor")
            ),
            "CodigoEstablecimiento": txt(
                h.get("Emisor_CodigoEstablecimiento"),
                "1",
            ),
            "NombreComercial": txt(
                h.get("Emisor_NombreComercial")
                or h.get("Emisor_NombreEmisor")
            ),
            "AfiliacionIVA": txt(
                h.get("Emisor_AfiliacionIVA"),
                "GEN",
            ),
        },
    )

    dir_emisor = SubElement(
        emisor,
        dte("DireccionEmisor"),
    )

    SubElement(
        dir_emisor,
        dte("Direccion")
    ).text = txt(
        h.get("Emisor_DireccionEmisor_Direccion"),
        "CIUDAD",
    )

    SubElement(
        dir_emisor,
        dte("CodigoPostal")
    ).text = txt(
        h.get("Emisor_DireccionEmisor_CodigoPostal"),
        "01001",
    )

    SubElement(
        dir_emisor,
        dte("Municipio")
    ).text = txt(
        h.get("Emisor_DireccionEmisor_Municipio"),
        "GUATEMALA",
    )

    SubElement(
        dir_emisor,
        dte("Departamento")
    ).text = txt(
        h.get("Emisor_DireccionEmisor_Departamento"),
        "GUATEMALA",
    )

    SubElement(
        dir_emisor,
        dte("Pais")
    ).text = country(
        h.get("Emisor_DireccionEmisor_Pais")
    )

    # =====================================================
    # RECEPTOR
    # =====================================================

    nit_receptor = txt(
        h.get("Receptor_IDReceptor"),
        "CF",
    ).replace("-", "").upper()

    if not nit_receptor:
        nit_receptor = "CF"

    nombre_receptor = txt(
        h.get("Receptor_NombreReceptor"),
        "CONSUMIDOR FINAL",
    )

    receptor = SubElement(
        datos_emision,
        dte("Receptor"),
        {
            "NombreReceptor": nombre_receptor,
            "IDReceptor": nit_receptor,
        },
    )

    dir_receptor = SubElement(
        receptor,
        dte("DireccionReceptor"),
    )

    SubElement(
        dir_receptor,
        dte("Direccion")
    ).text = txt(
        h.get("Receptor_DireccionReceptor_Direccion"),
        "CIUDAD",
    )

    SubElement(
        dir_receptor,
        dte("CodigoPostal")
    ).text = txt(
        h.get("Receptor_DireccionReceptor_CodigoPostal"),
        "01001",
    )

    SubElement(
        dir_receptor,
        dte("Municipio")
    ).text = txt(
        h.get("Receptor_DireccionReceptor_Municipio"),
        "GUATEMALA",
    )

    SubElement(
        dir_receptor,
        dte("Departamento")
    ).text = txt(
        h.get("Receptor_DireccionReceptor_Departamento"),
        "GUATEMALA",
    )

    SubElement(
        dir_receptor,
        dte("Pais")
    ).text = country(
        h.get("Receptor_DireccionReceptor_Pais")
    )

    # =====================================================
    # FRASES
    # =====================================================

    frases = SubElement(
        datos_emision,
        dte("Frases"),
    )

    frases_raw = txt(
        h.get("Frases_Escenarios"),
        "1|2",
    )

    parts = [
        p.strip()
        for p in frases_raw.replace(";", ",").split(",")
        if p.strip()
    ]

    if not parts:
        parts = ["1|2"]

    has_tipo_1 = False

    for p in parts:

        tipo = "1"
        escenario = "2"

        if "|" in p:

            pt = p.split("|")

            tipo = txt(pt[0], "1")
            escenario = txt(pt[1], "2")

        else:
            escenario = txt(p, "2")

        if tipo == "1":
            has_tipo_1 = True

        SubElement(
            frases,
            dte("Frase"),
            {
                "TipoFrase": tipo,
                "CodigoEscenario": escenario,
            },
        )

    # REGLA FCAM: Siempre debe ir una frase Tipo 1
    if not has_tipo_1:
        SubElement(
            frases,
            dte("Frase"),
            {
                "TipoFrase": "1",
                "CodigoEscenario": "2",
            },
        )

    # =====================================================
    # ITEMS
    # =====================================================

    items = SubElement(
        datos_emision,
        dte("Items"),
    )

    total_impuestos = 0.0
    gran_total = 0.0

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

        bien_o_servicio = txt(
            r.get("Items_BienOServicio"),
            "B",
        ).upper()

        item = SubElement(
            items,
            dte("Item"),
            {
                "NumeroLinea": str(idx),
                "BienOServicio": bien_o_servicio,
            },
        )

        cantidad = float(
            r.get("Items_Cantidad", 1) or 1
        )

        precio_unitario = float(
            r.get("Items_PrecioUnitario", 0) or 0
        )

        descuento = float(
            r.get("Items_Descuento", 0) or 0
        )

        monto_gravable = float(
            r.get("Items_IVA_MontoGravable", 0) or 0
        )

        monto_iva = float(
            r.get("Items_IVA_MontoImpuesto", 0) or 0
        )

        total_linea = float(
            r.get("Items_Total", 0) or 0
        )

        total_impuestos += monto_iva
        gran_total += total_linea

        SubElement(
            item,
            dte("Cantidad")
        ).text = qty(cantidad)

        SubElement(
            item,
            dte("UnidadMedida")
        ).text = txt(
            r.get("Items_UnidadMedida"),
            "UNI",
        )

        SubElement(
            item,
            dte("Descripcion")
        ).text = txt(
            r.get("Items_Descripcion"),
            "-",
        )

        SubElement(
            item,
            dte("PrecioUnitario")
        ).text = money(precio_unitario)

        SubElement(
            item,
            dte("Precio")
        ).text = money(
            cantidad * precio_unitario
        )

        SubElement(
            item,
            dte("Descuento")
        ).text = money(descuento)

        impuestos = SubElement(
            item,
            dte("Impuestos"),
        )

        impuesto = SubElement(
            impuestos,
            dte("Impuesto"),
        )

        SubElement(
            impuesto,
            dte("NombreCorto")
        ).text = "IVA"

        SubElement(
            impuesto,
            dte("CodigoUnidadGravable")
        ).text = "1"

        SubElement(
            impuesto,
            dte("MontoGravable")
        ).text = money(monto_gravable)

        SubElement(
            impuesto,
            dte("MontoImpuesto")
        ).text = money(monto_iva)

        SubElement(
            item,
            dte("Total")
        ).text = money(total_linea)

    # =====================================================
    # TOTALES
    # =====================================================

    totales = SubElement(
        datos_emision,
        dte("Totales"),
    )

    total_impuestos_node = SubElement(
        totales,
        dte("TotalImpuestos"),
    )

    SubElement(
        total_impuestos_node,
        dte("TotalImpuesto"),
        {
            "NombreCorto": "IVA",
            "TotalMontoImpuesto": money(
                total_impuestos
            ),
        },
    )

    SubElement(
        totales,
        dte("GranTotal")
    ).text = money(gran_total)

    # =====================================================
    # COMPLEMENTOS FCAM
    # =====================================================

    complementos = SubElement(
        datos_emision,
        dte("Complementos"),
    )

    complemento = SubElement(
        complementos,
        dte("Complemento"),
        {
            "URIComplemento": "dtecamb",
            "NombreComplemento": "FCAMB",
            "IDComplemento": "ID",
            f"{{{XSI_NS}}}schemaLocation": (
                "http://www.sat.gob.gt/dte/fel/CompCambiaria/0.1.0 "
                "GT_Complemento_Cambiaria-0.1.0.xsd"
            ),
            "xmlns:cfc": CFC_NS,
        },
    )

    abonos = SubElement(
        complemento,
        cfc("AbonosFacturaCambiaria"),
        {
            "Version": "1",
        },
    )

    # Recopilar abonos explícitos de las filas
    abono_list = []
    seen_abono_keys = set()
    for r in rows:
        venc = r.get("Complementos_AbonosFacturaCambiaria_FechaVencimiento")
        if venc:
            num = txt(r.get("Complementos_AbonosFacturaCambiaria_NumeroAbono") or str(len(abono_list) + 1))
            monto = money(r.get("Complementos_AbonosFacturaCambiaria_MontoAbono") or gran_total)
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
            "MontoAbono": money(gran_total)
        })
        
    for a in abono_list:
        abono_node = SubElement(abonos, cfc("Abono"))
        SubElement(abono_node, cfc("NumeroAbono")).text = a["NumeroAbono"]
        SubElement(abono_node, cfc("FechaVencimiento")).text = a["FechaVencimiento"]
        SubElement(abono_node, cfc("MontoAbono")).text = a["MontoAbono"]

    # =====================================================
    # ADENDA (Digifact Comercial)
    # =====================================================
    adenda = SubElement(sat, dte("Adenda"))
    inf_com = SubElement(adenda, f"{{{DTECOMM_NS}}}Informacion_COMERCIAL", {
        f"{{{XSI_NS}}}schemaLocation": "https://www.digifact.com.gt/dtecomm"
    })
    
    inf_adj = SubElement(inf_com, f"{{{DTECOMM_NS}}}InformacionAdicional", {
        "Version": "2020_06_01"
    })
    
    # Referencias internas
    SubElement(inf_adj, f"{{{DTECOMM_NS}}}REFERENCIA_INTERNA").text = h.get("name") or "-"
    SubElement(inf_adj, f"{{{DTECOMM_NS}}}FECHA_REFERENCIA").text = issued_dt(h.get("posting_date"))
    
    inf_extra = SubElement(inf_adj, f"{{{DTECOMM_NS}}}INFORMACION_ADICIONAL")
    SubElement(inf_extra, f"{{{DTECOMM_NS}}}Detalle", {
        "Data": "OBSERVACIONES",
        "Value": "Documento generado por Soluciones Integrales Chapp, S.A."
    })

    # =====================================================
    # XML FINAL
    # =====================================================

    xml_body = tostring(
        root,
        encoding="unicode",
        method="xml",
    )

    xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + xml_body

    # =====================================================
    # SAVE DEBUG XML
    # =====================================================

    try:

        ts = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        fname = f"fcam_sat_{ts}.xml"

        save_dir = (
            "/home/frappe/frappe-bench/apps/"
            "brainfel/brainfel/services/generated_xmls"
        )

        os.makedirs(
            save_dir,
            exist_ok=True,
        )

        save_path = os.path.join(
            save_dir,
            fname,
        )

        with open(
            save_path,
            "w",
            encoding="utf-8",
        ) as f:
            f.write(xml)

        print(
            f"DEBUG XML FCAM SAVED: {save_path}"
        )

    except Exception as e:

        print(
            f"DEBUG ERROR SAVING XML FCAM: {e}"
        )

    return {
        "xml": xml,
        "type": "FCAM",
    }