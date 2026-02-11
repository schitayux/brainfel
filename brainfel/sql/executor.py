# brainfel/sql/executor.py
import frappe

def run_sql_function(view_name, params):
    sql = f"""
        SELECT *
        FROM {view_name}
        WHERE Next_Identificador = %(docname)s
    """
    return frappe.db.sql(sql, params, as_dict=True)