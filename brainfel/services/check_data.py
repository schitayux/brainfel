import frappe
import json

def get_data(docname):
    settings = frappe.get_doc("BFEL Settings", {"enabled": 1})
    sql = f"SELECT * FROM {settings.sql_func_certificar} WHERE Next_Identificador = %s"
    data = frappe.db.sql(sql, (docname,), as_dict=True)
    print(json.dumps(data, indent=2, default=str))

if __name__ == "__main__":
    get_data("FACT-GEN-0013914")
