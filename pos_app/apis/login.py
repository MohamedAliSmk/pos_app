import frappe
import jwt
import datetime
from frappe import _
import hashlib
from frappe.auth import LoginManager

SECRET_KEY = frappe.conf.get("jwt_secret")

def normalize_url(url):
    import re
    return re.sub(r'^https?:\/\/(www\.)?', '', url).rstrip('/')

@frappe.whitelist(allow_guest=True)
def login_pos_user(site_url=None, usr=None, pswd=None):
    import json
    customer = None
    site_url = site_url or frappe.form_dict.get("site_url")
    usr = usr or frappe.form_dict.get("usr")
    pswd = pswd or frappe.form_dict.get("pswd")

    if not site_url or not usr or not pswd:
        try:
            if frappe.request and frappe.request.data:
                body = json.loads(frappe.request.data)
                site_url = site_url or body.get("site_url")
                usr = usr or body.get("usr")
                pswd = pswd or body.get("pswd")
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to parse JSON body: {str(e)}"
            }

    if not site_url or not usr or not pswd:
        return {
            "status": "error",
            "message": _("Missing required parameters")
        }

    try:
        if normalize_url(site_url) != normalize_url(frappe.utils.get_url()):
            return {
                "status": "error",
                "message": _("Invalid Site URL")
            }

        login_manager = LoginManager()
        login_manager.authenticate(user=usr, pwd=pswd)
        login_manager.post_login()

        user = frappe.get_doc("User", frappe.session.user)
        pos_profile = frappe.db.get_value("POS Profile User",{"user":user.name},"parent")
        # Prepare dict and add fields only if they are not None
        pos_profile_dict = {}

        if pos_profile and frappe.db.exists("POS Profile", pos_profile):
            profile = frappe.get_doc("POS Profile", pos_profile)
            
            
            if profile.company_address:
                pos_profile_dict["company_address"] = profile.company_address
            
            if profile.custom_logo:
                pos_profile_dict["custom_logo"] = frappe.utils.get_url() + profile.custom_logo
            
            if profile.crno:
                pos_profile_dict["crno"] = profile.crno
            if profile.gsm:
                pos_profile_dict["gsm"] = profile.gsm
            if profile.p_o_box:
                pos_profile_dict["p_o_box"] = profile.p_o_box
            if profile.address:
                pos_profile_dict["address"] = profile.address
            if profile.terms:
                pos_profile_dict["terms"] = profile.terms

            
            if profile.customer:
                customer= profile.customer

        # Create JWT Token
        payload = {
            "sub": user.name,
            "email": user.email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        return {
            "status": "success",
            "token": token,
            "pos_profile_dict": pos_profile_dict if pos_profile_dict else None,
            "user": {
                "user_id": user.name,
                "customer":customer,
                "full_name": user.full_name,
                "email": user.email,
                "user_image": frappe.utils.get_url() + user.user_image if user.user_image else None ,
                "roles": [role.role for role in user.get("roles")]
            }
        }

    except frappe.AuthenticationError:
        frappe.clear_messages()
        return {
            "status": "error",
            "message": _("Invalid login credentials")
        }

@frappe.whitelist(allow_guest=True)
def logout_pos_user():
    try:
        auth_header = frappe.get_request_header("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
            # Insert into blacklisted_jwt_token
            name = hashlib.sha1(token.encode()).hexdigest()
            frappe.db.sql("""
                INSERT IGNORE INTO `blacklisted_jwt_token` (name, token)
                VALUES (%s, %s)
            """, (name, token))
            frappe.db.commit()

        if hasattr(frappe.local, 'login_manager'):
            frappe.local.login_manager.logout()

        return {
            "status": "success",
            "message": _("Logged out successfully")
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Logout Failed")
        return {
            "status": "error",
            "message": _("Logout failed: {0}").format(str(e))
        }

def verify_jwt_token():
    auth_header = frappe.get_request_header("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return {
            "status": "error",
            "code": 401,
            "message": "Missing or invalid Authorization header"
        }

    token = auth_header.split(" ")[1]
    name = hashlib.sha1(token.encode()).hexdigest()

    # Check blacklist
    res = frappe.db.sql("""
        SELECT name FROM `blacklisted_jwt_token` WHERE name = %s
    """, (name,), as_dict=True)

    if res:
        return {
            "status": "error",
            "code": 401,
            "message": "Token is revoked"
        }

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return {
            "status": "success",
            "payload": payload
        }
    except jwt.ExpiredSignatureError:
        return {
            "status": "error",
            "code": 401,
            "message": "Token has expired"
        }
    except jwt.InvalidTokenError:
        return {
            "status": "error",
            "code": 401,
            "message": "Invalid token"
        }
