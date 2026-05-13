import frappe

def print_successful_xml():
    logs = frappe.db.sql("""
        SELECT request_payload 
        FROM `tabBFEL Log` 
        WHERE action = 'CERTIFY' 
        AND status = 'Success'
        ORDER BY creation DESC
        LIMIT 1
    """, as_dict=True)
    
    if logs:
        print("LAST SUCCESSFUL XML:")
        print(logs[0]['request_payload'])
    else:
        print("No successful logs found.")

if __name__ == "__main__":
    print_successful_xml()
