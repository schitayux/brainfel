import frappe
import html

def save_successful_xml():
    logs = frappe.db.sql("""
        SELECT request_payload 
        FROM `tabBFEL Log` 
        WHERE request_payload LIKE '%%AdditionlInfo%%' 
        AND status = 'Success'
        LIMIT 1
    """, as_dict=True)
    
    if logs:
        xml = html.unescape(logs[0]['request_payload'])
        with open("/home/frappe/frappe-bench/apps/brainfel/brainfel/services/success_sample.xml", "w") as f:
            f.write(xml)
        print("Saved to success_sample.xml")
    else:
        print("No logs with AdditionlInfo found.")

if __name__ == "__main__":
    save_successful_xml()
