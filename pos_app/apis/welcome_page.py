import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def get_app_logo():
    site_url = frappe.utils.get_url()
    app_logo_file = frappe.get_doc("POS App Settings").pos_logo
    return site_url + app_logo_file