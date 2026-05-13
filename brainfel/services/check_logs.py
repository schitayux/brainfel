import frappe

def get_successful_nuc():
    logs = frappe.get_all("BFEL Log", 
                         filters={"action": "CERTIFY", "status": "Success"}, 
                         fields=["request_xml"], 
                         limit=5)
    for log in logs:
        if log.request_xml and "<Header>" in log.request_xml:
            # Check if it has complements
            if "FCAM" in log.request_xml:
                print("FOUND FCAM SUCCESSFUL NUC:")
                print(log.request_xml)
                return
    print("No successful FCAM NUC logs found.")

if __name__ == "__main__":
    get_successful_nuc()
