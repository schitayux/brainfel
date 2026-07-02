# brainfel/services/adenda_builder.py
"""
Construye el bloque <dte:Adenda> del XML FEL a partir de la configuración
definida en el Doctype "BFEL Set Adendas".

Lógica:
  - Filas con fuente="Factura" → se emiten UNA sola vez al inicio del bloque
    (ej. CORRELATIVO_INT que es único por factura)
  - Filas con fuente="Item" → se emiten dentro de <LINEA_N> por cada línea
    del documento que pertenezca al grupo configurado

Uso desde certify_sales_invoice:
    from brainfel.services.adenda_builder import build_adenda
    adenda_xml = build_adenda(si, si.company)
    if adenda_xml:
        xml_payload = xml_payload.replace("</dte:DTE>", f"</dte:DTE>\n\t\t\t{adenda_xml}", 1)
"""
from __future__ import annotations

import frappe
from xml.sax.saxutils import escape


def build_adenda(doc, company: str) -> str:
    """
    Retorna el string XML del bloque <dte:Adenda> listo para insertar,
    o cadena vacía si no hay configuración activa o no aplica ningún tag.

    Args:
        doc: documento Sales Invoice (frappe.Document) con .items cargados
        company: nombre de la empresa para buscar la configuración
    """
    config = _get_config(company)
    if not config:
        return ""

    # Construir índice de config por grupo: { "ARMAS": {"factura": [...], "item": [...]} }
    config_por_grupo: dict = {}
    for row in config.adenda_rows:
        if not row.activo:
            continue
        grupo_key = (row.grupo_articulo or "").strip().upper()
        if not grupo_key:
            continue
        if grupo_key not in config_por_grupo:
            config_por_grupo[grupo_key] = {"factura": [], "item": []}
        bucket = "factura" if row.fuente == "Factura" else "item"
        config_por_grupo[grupo_key][bucket].append(row)

    if not config_por_grupo:
        return ""

    # Grupos presentes en la factura
    grupos_en_factura = {
        (item.item_group or "").strip().upper()
        for item in doc.items
        if item.item_group
    }
    grupos_activos = grupos_en_factura & set(config_por_grupo.keys())

    if not grupos_activos:
        return ""

    tags: list[str] = []

    # ── Etiquetas a nivel factura (una sola vez, sin importar cuántas líneas) ──
    tags_factura_escritos: set = set()
    for grupo_key in sorted(grupos_activos):
        for row in sorted(config_por_grupo[grupo_key]["factura"], key=lambda r: r.orden or 0):
            tag = (row.tag_xml or "").strip()
            if tag in tags_factura_escritos:
                continue
            valor = _get_field(doc, row.campo_erpnext)
            if valor:
                tags.append(f"\t\t\t\t<{tag}>{escape(str(valor))}</{tag}>")
                tags_factura_escritos.add(tag)

    # ── Etiquetas a nivel ítem: una <LINEA_N> por cada línea con grupo activo ──
    for item in doc.items:
        grupo_key = (item.item_group or "").strip().upper()
        if grupo_key not in grupos_activos:
            continue
        item_rows = sorted(
            config_por_grupo[grupo_key]["item"],
            key=lambda r: r.orden or 0,
        )
        if not item_rows:
            continue

        linea_tags: list[str] = []
        for row in item_rows:
            tag = (row.tag_xml or "").strip()
            valor = _get_field(item, row.campo_erpnext)
            if valor:
                linea_tags.append(f"\t\t\t\t\t<{tag}>{escape(str(valor))}</{tag}>")

        if linea_tags:
            linea_n = f"LINEA_{item.idx}"
            tags.append(f"\t\t\t\t<{linea_n}>")
            tags.extend(linea_tags)
            tags.append(f"\t\t\t\t</{linea_n}>")

    if not tags:
        return ""

    return "<dte:Adenda>\n" + "\n".join(tags) + "\n\t\t\t</dte:Adenda>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_config(company: str):
    """Retorna el primer registro activo de BFEL Set Adendas para la empresa."""
    try:
        names = frappe.get_all(
            "BFEL Set Adendas",
            filters={"company": company, "activo": 1},
            pluck="name",
            limit=1,
        )
        if not names:
            return None
        return frappe.get_doc("BFEL Set Adendas", names[0])
    except Exception:
        return None


def _get_field(obj, fieldname: str) -> str:
    """Lee un campo de un doc/dict de Frappe devolviendo string limpio."""
    if not fieldname:
        return ""
    if isinstance(obj, dict):
        valor = obj.get(fieldname, "")
    else:
        valor = getattr(obj, fieldname, None)
    if valor is None:
        return ""
    return str(valor).strip()
