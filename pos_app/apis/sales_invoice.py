import json
import frappe
from frappe import _
from frappe.utils import nowdate, getdate
from datetime import datetime
from pos_app.apis.login import verify_jwt_token

@frappe.whitelist(allow_guest=True)
def create_sales_invoice():
    """
    Create Sales Invoice from API.
    Mandatory fields: customer, due_date, items (as list of dicts)
    """
    # Verify token first
    result = verify_jwt_token()

    if result["status"] == "error":
        frappe.local.response["http_status_code"] = result["code"]
        return result

    payload = result["payload"]

    # Parse raw JSON body
    try:
        data = json.loads(frappe.request.data)
    except Exception:
        frappe.throw(_("Invalid JSON request body."))

    # Extract required fields
    usr = payload["sub"]
    pos_profile = frappe.db.get_value("POS Profile User",{"user":usr},"parent")
    if pos_profile:
        profile = frappe.get_doc("POS Profile", pos_profile)
        customer = profile.customer
    else:
        customer = data.get("customer")

    due_date = data.get("due_date")
    items = data.get("items")
    mobile = data.get("mobile_no")
    app_series = data.get("app_series")
    payments = data.get("payments")
    if not customer or not due_date or not items:
        frappe.throw(_("Missing mandatory fields: customer, due_date, or items."))

    if not isinstance(items, list) or not items:
        frappe.throw(_("Items must be a non-empty list."))

    try:
        # Create Sales Invoice
        doc = frappe.new_doc("Sales Invoice")
        doc.customer = customer
        doc.due_date = due_date
        doc.posting_date = nowdate()
        doc.custom_mobile_no = mobile
        doc.app_series = app_series
        doc.is_pos = 1
        for item in items:
            if not item.get("item_code") or not item.get("qty"):
                frappe.throw(_("Each item must have 'item_code' and 'qty'."))
            doc.append("items", {
                "item_code": item["item_code"],
                "qty": item["qty"],
                "rate": item.get("rate")  # optional
            })

        for pay in payments:
            doc.append("payments",{
                "mode_of_payment":pay["mode_of_payment"],
                "amount":pay["amount"]
                })

        doc.insert(ignore_permissions=True)
        doc.submit()
        return {
            "success_key": 1,
            "message": "Sales Invoice created",
            "name": doc.name
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Sales Invoice API Error")
        frappe.throw(_("Failed to create Sales Invoice: {0}").format(str(e)))


@frappe.whitelist(allow_guest=True)
def sales_invoice_history(from_date=None, to_date=None, min_amount=None, max_amount=None):
    """
    API to get Sales Invoices by date and amount filters with items and payments.
    """
    try:
        verify_jwt_token()
    except Exception as e:
        frappe.throw(_("Unauthorized: {0}").format(str(e)))

    # Build filters
    conditions = []
    if from_date:
        from_date = getdate(from_date)
        conditions.append("posting_date >= %(from_date)s")
    if to_date:
        to_date = getdate(to_date)
        conditions.append("posting_date <= %(to_date)s")
    if min_amount:
        min_amount = float(min_amount)
        conditions.append("grand_total >= %(min_amount)s")
    if max_amount:
        max_amount = float(max_amount)
        conditions.append("grand_total <= %(max_amount)s")

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
        SELECT name, customer, posting_date, grand_total, status,mobile_no, app_series
        FROM `tabSales Invoice`
        WHERE {where_clause}
        ORDER BY posting_date DESC
    """

    invoices = frappe.db.sql(query, {
        "from_date": from_date,
        "to_date": to_date,
        "min_amount": min_amount,
        "max_amount": max_amount
    }, as_dict=True)

    # Fetch items and payments separately
    for inv in invoices:
        inv["items"] = frappe.get_all("Sales Invoice Item", filters={"parent": inv["name"]},
                                      fields=["item_code", "item_name", "qty", "rate", "amount"])
        inv["payments"] = frappe.get_all("Sales Invoice Payment", filters={"parent": inv["name"]},
                                         fields=["mode_of_payment", "amount"])

    return {
        "success_key": 1,
        "sales_invoices": invoices
    }

@frappe.whitelist(allow_guest=True)
def create_bulk_sales_invoices():
    """
    Create multiple Sales Invoices from a single API call.
    Expects request body to be a JSON object with key 'invoices'.
    Each invoice must include: customer, due_date, items (list), payments (list)
    """
    result = verify_jwt_token()
    if result["status"] == "error":
        frappe.local.response["http_status_code"] = result["code"]
        return result

    try:
        data = json.loads(frappe.request.data)
    except Exception:
        frappe.throw(_("Invalid JSON request body."))

    # Expecting object with key "invoices"
    invoices_data = data.get("invoices")
    if not isinstance(invoices_data, list):
        frappe.throw(_("Expected 'invoices' to be a list of invoice objects."))

    payload = result["payload"]
    usr = payload["sub"]
    
    pos_profile = frappe.db.get_value("POS Profile User", {"user": usr}, "parent")
    default_customer = frappe.get_value("POS Profile", pos_profile, "customer") if pos_profile else None

    created_invoices = []
    errors = []

    for idx, invoice_data in enumerate(invoices_data):
        try:
            # Fields
            customer = default_customer or invoice_data.get("customer")
            due_date = invoice_data.get("due_date")
            items = invoice_data.get("items")
            payments = invoice_data.get("payments")
            mobile = invoice_data.get("mobile_no")
            app_series = invoice_data.get("app_series")

            if not customer or not due_date or not items:
                raise Exception(_("Missing mandatory fields: customer, due_date, or items."))

            if not isinstance(items, list) or not items:
                raise Exception(_("Items must be a non-empty list."))

            if not isinstance(payments, list) or not payments:
                raise Exception(_("Payments must be a non-empty list."))

            # Create Sales Invoice
            doc = frappe.new_doc("Sales Invoice")
            doc.customer = customer
            doc.due_date = due_date
            doc.posting_date = nowdate()
            doc.custom_mobile_no = mobile
            doc.app_series = app_series
            doc.is_pos = 1

            # Add items
            for item in items:
                if not item.get("item_code") or not item.get("qty"):
                    raise Exception(_("Each item must have 'item_code' and 'qty'."))
                doc.append("items", {
                    "item_code": item["item_code"],
                    "qty": item["qty"],
                    "rate": item.get("rate")
                })

            # Add payments
            for pay in payments:
                if not pay.get("mode_of_payment") or not pay.get("amount"):
                    raise Exception(_("Each payment must have 'mode_of_payment' and 'amount'."))
                doc.append("payments", {
                    "mode_of_payment": pay["mode_of_payment"],
                    "amount": pay["amount"]
                })

            doc.insert(ignore_permissions=True)
            doc.submit()

            created_invoices.append({
                "index": idx,
                "invoice_name": doc.name
            })

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Bulk Sales Invoice Error")
            errors.append({
                "index": idx,
                "error": str(e),
                "data": invoice_data
            })

    return {
        "success_key": 1 if not errors else 0,
        "created_invoices": created_invoices,
        "errors": errors
    }