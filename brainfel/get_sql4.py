import frappe

def execute():
    try:
        res = frappe.db.sql("SHOW CREATE VIEW v_bfel_sales_invoice_fact", as_dict=True)
        print(res[0].get("Create View") or res[0])
    except Exception as e:
        print("Not a view:", e)
