import frappe

def execute():
    settings = frappe.get_all("BFEL Settings", fields=["name", "sql_func_certificar", "company", "enabled"])
    for s in settings:
        if not s.enabled:
            continue
        func = s.sql_func_certificar
        print(f"Settings: {s.name} (Company: {s.company}), Func: {func}")
        try:
            res = frappe.db.sql(f"SHOW CREATE VIEW {func}", as_dict=True)
            print(res[0].get("Create View") or res[0])
        except Exception as e:
            print("Not a view:", e)
            try:
                res = frappe.db.sql(f"SHOW CREATE FUNCTION {func}", as_dict=True)
                print(res)
            except Exception as e2:
                print("Not a function either:", e2)
