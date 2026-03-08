import requests
import base64
from datetime import datetime, timedelta, timezone
from models import db, Setting, Subscription, Transaction, User
from utils.logger import log_event

def get_revenue_metrics():
    """Calculate MRR and ARR based on active subscriptions."""
    from models import PricingTier
    
    active_subs = Subscription.query.filter_by(status="active").all()
    
    # Map tier names to their price and interval
    tiers = {t.name: t for t in PricingTier.query.all()}
    
    mrr = 0.0
    for sub in active_subs:
        tier = tiers.get(sub.plan_name)
        if tier:
            if tier.interval == "monthly":
                mrr += tier.price
            elif tier.interval == "yearly":
                mrr += tier.price / 12.0
            # Lifetime/one-time do not count toward MRR
            
    arr = mrr * 12.0
    
    return {
        "mrr": mrr,
        "arr": arr,
        "active_subscribers": len(active_subs)
    }

# --- PayPal Helpers ---

def get_paypal_access_token():
    client_id = Setting.get("paypal_client_id")
    secret = Setting.get("paypal_secret")
    mode = Setting.get("paypal_mode", "sandbox")
    
    url = "https://api-m.sandbox.paypal.com/v1/oauth2/token" if mode == "sandbox" else "https://api-m.paypal.com/v1/oauth2/token"
    
    auth_str = f"{client_id}:{secret}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=10)
        return resp.json().get("access_token")
    except Exception as e:
        log_event("PayPal Auth", "error", str(e))
        return None

# --- M-Pesa Helpers (Daraja API) ---

def get_mpesa_access_token():
    consumer_key = Setting.get("mpesa_consumer_key")
    consumer_secret = Setting.get("mpesa_consumer_secret")
    mode = Setting.get("mpesa_mode", "sandbox")
    
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials" if mode == "sandbox" else "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    
    try:
        resp = requests.get(url, auth=(consumer_key, consumer_secret), timeout=10)
        return resp.json().get("access_token")
    except Exception as e:
        log_event("M-Pesa Auth", "error", str(e))
        return None

def initiate_stk_push(phone_number, amount, account_ref="ContextaSubscription"):
    """Trigger M-Pesa STK Push."""
    access_token = get_mpesa_access_token()
    if not access_token:
        return {"success": False, "error": "Auth failed"}
        
    shortcode = Setting.get("mpesa_shortcode")
    passkey = Setting.get("mpesa_passkey")
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    password_str = shortcode + passkey + timestamp
    password = base64.b64encode(password_str.encode()).decode()
    
    mode = Setting.get("mpesa_mode", "sandbox")
    url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest" if mode == "sandbox" else "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": shortcode,
        "PhoneNumber": phone_number,
        "CallBackURL": Setting.get("mpesa_callback_url"),
        "AccountReference": account_ref,
        "TransactionDesc": "Contexta Subscription"
    }
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return resp.json()
    except Exception as e:
        log_event("M-Pesa STK", "error", str(e))
        return {"success": False, "error": str(e)}
