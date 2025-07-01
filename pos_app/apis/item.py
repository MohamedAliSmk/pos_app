import frappe
from frappe import _
from pos_app.apis.login import verify_jwt_token

def get_items_from_warhouse(warehouse):
    items = frappe.get_all("Bin",
        filters={
            "warehouse": warehouse,
            "actual_qty": [">", 0]
        },
        fields=["item_code"]
    )
    return [item.item_code for item in items]

def has_user_permission(usr, allow):
    if frappe.db.exists("User Permission", {"user": usr, "allow": allow}):
        values = frappe.db.get_all("User Permission", {"user": usr, "allow": allow}, ["for_value"])
        return [v["for_value"] for v in values]
    return []

@frappe.whitelist(allow_guest=True)
def get_pos_items():
    # Verify token first
    result = verify_jwt_token()

    if result["status"] == "error":
        frappe.local.response["http_status_code"] = result["code"]
        return result

    payload = result["payload"]
    price_list = None
    item_filters = {"disabled": 0}
    usr = payload["sub"]
    pos_profile = frappe.db.get_value("POS Profile User",{"user":usr},"parent")
    if pos_profile:
        profile = frappe.get_doc("POS Profile", pos_profile)
        price_list = profile.selling_price_list
        applicable_for_users = [row.user for row in profile.applicable_for_users]
        if usr not in applicable_for_users:
            return "users not applicable with this pos profile"

        item_groups = [row.item_group for row in profile.item_groups]
        if item_groups:
            item_filters["item_group"] = ["in", item_groups]

        # Optional warehouse filter:
        # if profile.warehouse:
        #     items_names = get_items_from_warhouse(profile.warehouse)
        #     item_filters["name"] = ["in", items_names]

    user_item_groups = has_user_permission(usr=usr, allow="Item Group")
    if user_item_groups:
        item_filters["item_group"] = ["in", user_item_groups]

    items = frappe.get_all("Item",
        filters=item_filters,
        fields=["name", "item_name", "image"]
    )

    item_names = [item["name"] for item in items]

    prices = frappe.get_all("Item Price",
        filters={
            "price_list": price_list,
            "item_code": ["in", item_names]
        },
        fields=["item_code", "price_list_rate"]
    )

    price_map = {p.item_code: p.price_list_rate for p in prices}

    result = []
    for item in items:
        result.append({
            "item_code":item.name,
            "item_name": item.item_name,
            "image": item.image,
            "price": price_map.get(item.name, 0.0)
        })

    return result