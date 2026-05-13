import frappe

def test_cancel():
    si = frappe.get_last_doc("Sales Invoice", filters={"docstatus": 1})
    if not si:
        print("No submitted invoice found")
        return
    print(f"Trying to cancel {si.name}")
    try:
        si.flags.ignore_validate_update_after_submit = True
        si.cancel()
        print("Cancel success")
    except Exception as e:
        print(f"Cancel failed: {e}")
        frappe.db.rollback()

test_cancel()
