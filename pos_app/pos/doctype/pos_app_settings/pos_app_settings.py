import frappe
from frappe.model.document import Document
from frappe.installer import update_site_config

class POSAppSettings(Document):
    def on_update(self):
        if self.pos_password:
            update_site_config("pos_app_password", self.pos_password)