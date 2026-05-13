import frappe

def search_fcam_logs():
    logs = frappe.db.sql("""
        SELECT request_xml 
        FROM `tabBFEL Log` 
        WHERE request_xml LIKE '%%FCAM%%' 
        AND status = 'Success'
        LIMIT 1
    """, as_dict=True)
    
    if logs:
        print("FOUND SUCCESSFUL FCAM XML:")
        print(logs[0]['request_xml'])
    else:
        print("No successful FCAM logs found with FCAM in XML.")

if __name__ == "__main__":
    search_fcam_logs()
