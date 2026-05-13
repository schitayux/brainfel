import frappe

def execute():
    try:
        views = frappe.db.sql("SHOW FULL TABLES WHERE Table_type = 'VIEW'", as_dict=True)
        for v in views:
            vname = list(v.values())[0]
            if "bfel" in vname.lower() or "fel" in vname.lower():
                print(vname)
    except Exception as e:
        print("Error:", e)
