import frappe
import json

def print_settings(company=None):
    filters = {"enabled": 1}
    if company:
        filters["company"] = company
        
    settings = frappe.get_all("BFEL Settings", filters=filters)
    for s in settings:
        doc = frappe.get_doc("BFEL Settings", s.name)
        print(f"--- Settings for: {doc.company} ---")
        print(json.dumps(doc.as_dict(), indent=2, default=str))

if __name__ == "__main__":
    print_settings()
