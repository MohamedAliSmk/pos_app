# pos_app/api/auth.py

import frappe
import jwt
from frappe import _
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

def validate_auth():
    auth = frappe.get_request_header("Authorization")

    if auth and auth.startswith("Bearer "):
        token = auth.split(" ")[1]
        try:
            payload = jwt.decode(token, frappe.conf.get("jwt_secret"), algorithms=["HS256"])
            frappe.set_user(payload["sub"])
            return
        except ExpiredSignatureError:
            frappe.throw(_("Token has expired"), frappe.AuthenticationError)
        except InvalidTokenError:
            frappe.throw(_("Invalid token"), frappe.AuthenticationError)

    # If token missing or invalid
    # raise frappe.AuthenticationError(_("Missing or invalid token"))
