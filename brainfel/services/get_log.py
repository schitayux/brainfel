import frappe

def get_log():
    logs = frappe.db.sql("""
        SELECT request_payload 
        FROM `tabBFEL Log` 
        WHERE request_payload LIKE '%%AbonosFacturaCambiaria%%' 
        AND status = 'Success'
        LIMIT 1
    """, as_dict=True)
    if logs:
        print(logs[0]['request_payload'])
    else:
        print("No logs found.")

if __name__ == "__main__":
    get_log()
