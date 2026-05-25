import frappe
import json
import os

def get_data():
    logs = frappe.get_all("BFEL Log",
                          filters={"status": "Success"},
                          fields=["name", "certifier", "response_payload", "responsedata"],
                          limit=50)
    
    result = []
    for log in logs:
        if log.certifier == "Grupo CDS" or "cds" in str(log.certifier).lower():
            result.append({
                "name": log.name,
                "certifier": log.certifier,
                "response_payload": log.response_payload,
                "responsedata": log.responsedata
            })
            
    os.makedirs("/home/frappe/frappe-bench/scratch", exist_ok=True)
    with open("/home/frappe/frappe-bench/scratch/cds_logs.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
        
    print(f"Done! Found {len(result)} CDS logs.")

if __name__ == "__main__":
    get_data()
