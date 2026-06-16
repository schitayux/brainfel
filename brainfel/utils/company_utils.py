import frappe

def validate_user_company_access(company):
    """
    Verifica que el usuario actual tenga acceso a la compañía proporcionada.
    """
    user = frappe.session.user
    if user == "Administrator":
        return

    # User Permissions check
    user_permissions = frappe.get_all(
        "User Permission", 
        filters={"user": user, "allow": "Company"}, 
        fields=["for_value"]
    )
    
    if user_permissions:
        allowed_companies = [p.for_value for p in user_permissions]
        if company not in allowed_companies:
            frappe.throw(f"El usuario {user} no está autorizado para certificar documentos de la compañía {company}.")
        return

    # Fallback: Revisar si existe empleado enlazado al usuario y si tiene compañía restrictiva.
    employees = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"}, fields=["company"])
    if employees and employees[0].company:
        emp_company = employees[0].company
        if emp_company != company:
            frappe.throw(f"El usuario {user} no está autorizado para certificar documentos de la compañía {company}.")
            
    # Si no hay configuraciones estrictas, permitimos el paso libre para soportar sitios mono-empresa.
    return


def get_bfel_settings_for_document(doc):
    """
    Retorna la configuración BFEL activa para la compañía del documento.
    Lanza error si no encuentra configuración o si existe más de una habilitada para la empresa.
    """
    if not hasattr(doc, "company") or not doc.company:
        frappe.throw("El documento no tiene una compañía asociada.")
    
    rows = frappe.get_all(
        "BFEL Settings",
        filters={"company": doc.company, "enabled": 1}
    )
    
    if not rows:
        frappe.throw(f"No existe BFEL Settings activo para la compañía {doc.company}.")
    
    if len(rows) > 1:
        frappe.throw(f"Existe más de un BFEL Settings activo para la compañía {doc.company}. Corrija la configuración.")
        
    return frappe.get_doc("BFEL Settings", rows[0].name)
