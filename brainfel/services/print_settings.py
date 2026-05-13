import frappe
import json

def print_settings():
    settings = frappe.get_doc("BFEL Settings", {"enabled": 1})
    print(json.dumps(settings.as_dict(), indent=2, default=str))

if __name__ == "__main__":
    print_settings()
