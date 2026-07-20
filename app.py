from flask import Flask, jsonify, render_template, request, session
from functools import wraps
import uuid
from datetime import datetime
import resend
import json
import random
import time
import os
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import threading

# Resend API Key 
resend.api_key = "re_Use1fV2g_7uP3F5e7EMjXGyBZ6nFf19wV"

app = Flask(__name__)
app.secret_key = "ydv-glory-simple-key"   # No encryption, just session

# Security settings for session cookie to prevent client-side/custom inspect theft
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

def get_client_ip():
    if 'CF-Connecting-IP' in request.headers:
        return request.headers['CF-Connecting-IP']
    if 'X-Forwarded-For' in request.headers:
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr

def get_client_country():
    return request.headers.get('CF-IPCountry', 'Unknown')

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.before_request
def cloudflare_security():
    # Bypass security check for local loopback/health checks and the AI Studio run.app preview host
    host = request.host.lower() if request.host else ""
    is_preview = 'localhost' in host or '127.0.0.1' in host or host.endswith('.run.app') or request.remote_addr in ('127.0.0.1', '::1')

    if not is_preview:
        # 1. CF-Connecting-IP header check (blocks direct access)
        if not request.headers.get('CF-Connecting-IP'):
            return jsonify({"error": "Access Denied"}), 403
            
        # 2. Empty User-Agent block
        if not request.headers.get('User-Agent', '').strip():
            return jsonify({"error": "Invalid Request"}), 403
            
        # 3. Known bot patterns block
        bot_patterns = ['python', 'curl', 'wget', 'headlesschrome', 'phantomjs', 'selenium', 'scrapy']
        ua = request.headers.get('User-Agent', '').lower()
        if any(bot in ua for bot in bot_patterns):
            return jsonify({"error": "Bot Detected"}), 403

    # Turnstile Verification check
    # Except for home page, verify-captcha API, and logo/video assets
    exempt_paths = ['/', '/api/verify-captcha', '/logo.jpg', '/video.mp4']
    if request.path not in exempt_paths and not request.path.startswith('/uploads/'):
        if not session.get('turnstile_verified'):
            return jsonify({"error": "Turnstile Verification Required", "require_captcha": True}), 403

# ─── UPI CONFIG ───────────────────────────────────────────
# ─── FAMPAY CONFIG ───────────────────────────────────────────
FAMPAY_API_KEY = "FAM_abcf6524d550262d3905933b996806dcc952cfa5ec131d82"
UPI_ID = "adityahere777@fam"
PAYEE_NAME = "Aditya"
PAYEE_EMAIL = "adiu4047@gmail.com"
PAYEE_NUMBER = "7004973360"

FAMPAY_QR_API = "https://fampay.anujbots.xyz/qr.php"
FAMPAY_VERIFY_API = "https://fampay.anujbots.xyz/verify.php"

# ─── STATE (Backend only) ────────────────────────────────────────────────────
STATE = {
    "users": {
        "YDV-ROOT": {
            "username": "YDV-ROOT",
            "email": "ydvroot@admin.com",
            "password": "7004973360@211735xxx",
            "credits": 999,
            "role": "admin",
            "banned": False
        }
    },
    "orders": [],
    "bots": {},
    "coupons": {
        "WELCOME10": {"credits": 2, "maxUses": 100, "uses": 0},
        "GLORY50": {"credits": 5, "maxUses": 50, "uses": 0}
    },
    "redeemedBy": {},
    "pricePacks": [
        {"id": "p1", "icon": "⚡", "name": "1 CREDIT — STARTER", "desc": "4 Glory Bots · 1 Squad", "credits": 1, "price": 499, "badge": "POPULAR", "qrImage": None},
        {"id": "p2", "icon": "💎", "name": "5 CREDITS — PRO", "desc": "20 Glory Bots · 5 Squads", "credits": 5, "price": 2499, "badge": "", "qrImage": None},
        {"id": "p3", "icon": "👑", "name": "10 CREDITS — ELITE", "desc": "40 Glory Bots · Best Value!", "credits": 10, "price": 3999, "badge": "", "qrImage": None}
    ],
    "announcement": "⚡ Welcome to GLORY BOT PRO — 24/7 bots running NON-STOP!",
    "maintenance": False,
    "siteLogo": "⚡",   # Simple emoji, no base64
    "tg_users": {}
}

# ─── SUPABASE CONFIG ─────────────────────────────────────
SUPABASE_URL = "https://uamtokyocsatauzdiihp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVhbXRva3lvY3NhdGF1emRpaWhwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQzNjQzNDYsImV4cCI6MjA5OTk0MDM0Nn0.wovPIdIdUQvWVQf8yfzRCBe-dIMeQ1_YiK6qSBde-rw"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

STATE_FILE = os.path.join(app.root_path, "state_db.json")

def load_state():
    global STATE
    url = f"{SUPABASE_URL}/rest/v1/app_state?id=eq.1"
    try:
        print(f"Loading state from Supabase: {url}")
        r = requests.get(url, headers=SUPABASE_HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list) and len(data) > 0:
                loaded = data[0].get("data")
                if loaded and isinstance(loaded, dict) and "users" in loaded:
                    for k, v in loaded.items():
                        STATE[k] = v
                    if "tg_users" not in STATE:
                        STATE["tg_users"] = {}
                    print("Successfully loaded state from Supabase.")
                    
                    # Cache locally as fallback
                    try:
                        with open(STATE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(STATE, f, indent=4)
                    except Exception as cache_err:
                        print(f"Error caching Supabase state locally: {cache_err}")
                    return True
            print("No state row with id=1 found in Supabase.")
        else:
            print(f"Error loading state from Supabase. Status: {r.status_code}, response: {r.text}")
    except Exception as e:
        print(f"Exception loading state from Supabase: {e}")
    
    # Local fallback
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if loaded and isinstance(loaded, dict) and "users" in loaded:
                    for k, v in loaded.items():
                        STATE[k] = v
                    if "tg_users" not in STATE:
                        STATE["tg_users"] = {}
                    print("Successfully loaded state from local file fallback.")
                    return True
        except Exception as e:
            print(f"Error loading state from local file fallback: {e}")
            
    return False

def save_state_to_supabase():
    url = f"{SUPABASE_URL}/rest/v1/app_state?id=eq.1"
    try:
        payload = {"data": STATE}
        r = requests.patch(url, headers=SUPABASE_HEADERS, json=payload, timeout=10)
        if r.status_code in (200, 201, 204):
            print("Successfully saved state to Supabase.")
        else:
            print(f"Failed to save state to Supabase. Status: {r.status_code}, response: {r.text}")
    except Exception as e:
        print(f"Error saving state to Supabase: {e}")

def save_state_to_file():
    # Save locally as cache fallback
    try:
        tmp_file = STATE_FILE + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(STATE, f, indent=4)
        os.replace(tmp_file, STATE_FILE)
    except Exception as e:
        print(f"Error saving local state cache: {e}")

    # Save to Supabase asynchronously using PATCH
    threading.Thread(target=save_state_to_supabase, daemon=True).start()

# Startup code: load from Supabase -> if fail, use default and save to Supabase
loaded_ok = load_state()
local_logo_path = os.path.join(app.root_path, "logo.jpg")
if os.path.exists(local_logo_path):
    current_logo = STATE.get("siteLogo")
    if current_logo == "⚡" or not current_logo or current_logo == "/logo.jpg":
        STATE["siteLogo"] = "/logo.jpg"
        print("Detected logo.jpg, setting siteLogo path to /logo.jpg in memory.")
    
if not loaded_ok:
    print("Initial state not found or failed to load. Initializing Supabase with default state...")
    if "tg_users" not in STATE:
        STATE["tg_users"] = {}
    
    # Save default state to local file
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(STATE, f, indent=4)
        print("Created initial local fallback state file.")
    except Exception as e:
        print(f"Error creating local state file: {e}")
        
    # Insert default state row to Supabase via POST (with upsert handling just in case)
    try:
        url = f"{SUPABASE_URL}/rest/v1/app_state"
        headers = {**SUPABASE_HEADERS, "Prefer": "resolution=merge-duplicates"}
        payload = {"id": 1, "data": STATE}
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code in (200, 201, 204):
            print("Successfully initialized default state in Supabase.")
        else:
            print(f"Failed to initialize default state in Supabase. Status: {r.status_code}, response: {r.text}")
    except Exception as e:
        print(f"Exception initializing default state in Supabase: {e}")

# Save state if we overrode the logo on startup
if os.path.exists(local_logo_path) and STATE.get("siteLogo") == "/logo.jpg":
    try:
        # Save locally and asynchronously to Supabase
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(STATE, f, indent=4)
        threading.Thread(target=save_state_to_supabase, daemon=True).start()
    except Exception as e:
        pass

# Helper to generate QR with Logo overlay
def generate_qr_with_logo(data_str, logo_path=None):
    import qrcode
    from PIL import Image, ImageDraw
    
    if logo_path is None:
        logo_path = os.path.join(app.root_path, "logo.jpg")
    
    # Generate QR Code with High Error Correction
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    if os.path.exists(logo_path) and os.path.getsize(logo_path) > 0:
        try:
            logo = Image.open(logo_path).convert("RGBA")
            qr_width, qr_height = qr_img.size
            logo_size = int(qr_width * 0.20) # 20% size
            
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            
            # Create a circular mask for the logo
            mask = Image.new("L", (logo_size, logo_size), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, logo_size, logo_size), fill=255)
            
            # Create circular logo with transparency
            circular_logo = Image.new("RGBA", (logo_size, logo_size), (0, 0, 0, 0))
            circular_logo.paste(logo, (0, 0), mask)
            
            # Create a larger white circle as background/border
            border_padding = int(logo_size * 0.12)
            if border_padding < 3:
                border_padding = 3
            border_size = logo_size + 2 * border_padding
            
            circular_border = Image.new("RGBA", (border_size, border_size), (0, 0, 0, 0))
            draw_border = ImageDraw.Draw(circular_border)
            draw_border.ellipse((0, 0, border_size, border_size), fill="white")
            
            # Paste circular logo onto circular white border
            circular_border.paste(circular_logo, (border_padding, border_padding), circular_logo)
            
            # Paste circular_border onto QR image using its transparency as a mask
            pos = ((qr_width - border_size) // 2, (qr_height - border_size) // 2)
            qr_img.paste(circular_border, pos, circular_border)
        except Exception as e:
            print(f"Error overlaying logo onto QR: {e}")
            
    return qr_img
    
@app.route('/logo.jpg')
def serve_logo():
    return send_from_directory(app.root_path, 'logo.jpg')

@app.route('/api/qr')
def serve_qr_code():
    import io
    from flask import send_file
    data_str = request.args.get('data', '')
    if not data_str:
        return "No data provided", 400
    
    img = generate_qr_with_logo(data_str)
    bio = io.BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    return send_file(bio, mimetype='image/png')

def fetch_guild_info(clan_id, region):
    if not region:
        region = "IND"
    region = str(region).strip().upper()
    url = f"https://star-guild-info.lovable.app/api/public/info?clan_id={clan_id}&region={region}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            res = r.json()
            if res.get("status") == "success":
                return res
    except Exception as e:
        print(f"Error fetching guild info for clan_id={clan_id}, region={region}: {e}")
    return None

def auto_update_bots_loop():
    # Wait for startup
    time.sleep(10)
    while True:
        try:
            bot_ids = list(STATE.get("bots", {}).keys())
            for bid in bot_ids:
                bot = STATE["bots"].get(bid)
                if not bot:
                    continue
                if bot.get("approved") and not bot.get("rejected"):
                    clan_id = bot.get("uid")
                    region = bot.get("server", "IND")
                    if clan_id:
                        res = fetch_guild_info(clan_id, region)
                        if res:
                            bot['guildName'] = res.get('clan_name', bot.get('guildName', 'Guild'))
                            bot['level'] = res.get('guild_level', res.get('level', bot.get('level', 1)))
                            bot['members'] = res.get('current_members', bot.get('members', 5))
                            bot['maxMembers'] = res.get('total_members', bot.get('maxMembers', 25))
                            
                            current_glory = res.get('glory_points', res.get('score', 0))
                            if 'initialGlory' not in bot or bot['initialGlory'] is None:
                                bot['initialGlory'] = current_glory
                                
                            gained = max(0, current_glory - bot['initialGlory'])
                            bot['glory'] = gained
                            bot['score'] = current_glory
                            print(f"Auto-updated bot {bid} ({bot['guildName']}): current={current_glory}, initial={bot['initialGlory']}, gained={gained}")
            save_state_to_file()
        except Exception as e:
            print(f"Error in auto_update_bots_loop: {e}")
        time.sleep(30)

auto_update_thread = threading.Thread(target=auto_update_bots_loop, daemon=True)
auto_update_thread.start()


# ─── HELPERS ──────────────────────────────────────────────────────────────────
CODE_FILE = 'code.json'

def load_codes():
    if not os.path.exists(CODE_FILE):
        return {}
    try:
        with open(CODE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_codes(codes):
    with open(CODE_FILE, 'w') as f:
        json.dump(codes, f)

def clean_expired_codes():
    codes = load_codes()
    current_time = time.time()
    # जो कोड 5 मिनट (300 सेकंड) से पुराने हैं, उन्हें डिलीट कर दो
    codes = {email: data for email, data in codes.items() if current_time - data['timestamp'] < 300}
    save_codes(codes)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ─── ROUTES ──────────────────────────────────────────────────────────────────

from flask import send_from_directory

@app.route('/')
def home():
    # Clear Turnstile verification on page load/refresh to force captcha verification every time they visit or refresh!
    session.pop('turnstile_verified', None)
    return render_template('index.html')

@app.route('/api/verify-captcha', methods=['POST'])
def verify_captcha():
    data = request.json or {}
    token = data.get('token')
    
    if not token:
        return jsonify({"success": False, "error": "Token missing"}), 400
        
    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": "0x4AAAAAAD5yepiZxfwhvHO1O66POlyJDjA",
                "response": token,
                "remoteip": get_client_ip()
            },
            timeout=10
        )
        
        result = response.json()
        
        if result.get("success"):
            session['turnstile_verified'] = True
            return jsonify({"success": True})
        else:
            error_codes = result.get('error-codes', ['Unknown error'])
            error_msg = error_codes[0] if error_codes else 'Unknown error'
            return jsonify({"success": False, "error": f"Verification failed: {error_msg}"}), 400
            
    except Exception as e:
        return jsonify({"success": False, "error": f"Network error: {str(e)}"}), 500

@app.route('/video.mp4')
def serve_video():
    # यह app.py वाले फोल्डर से सीधा video.mp4 को फ्रंटएंड में भेज देगा
    return send_from_directory(app.root_path, 'video.mp4')

@app.route('/uploads/<filename>')
def serve_uploads(filename):
    return send_from_directory(os.path.join(app.root_path, 'uploads'), filename)

# ─── PUBLIC API ─────────────────────────────────────────────────────────────


@app.route('/api/get-private-data', methods=['GET'])
def get_private_data():
    username = session.get('username')
    user = STATE.get('users', {}).get(username) if username else None
    
    # Base public state fields
    public_state = {
        "pricePacks": STATE.get("pricePacks", []),
        "announcement": STATE.get("announcement", ""),
        "maintenance": STATE.get("maintenance", False),
        "siteLogo": STATE.get("siteLogo", "⚡"),
        "users": {},
        "orders": [],
        "bots": {},
        "coupons": {},
        "redeemedBy": {}
    }
    
    if not user:
        # Unauthenticated guest: return public fields only
        return jsonify(public_state)
        
    user_role = user.get('role', 'user')
    
    if user_role in ('admin', 'staff'):
        # Admin or Staff: return full state with all passwords completely stripped
        sanitized_users = {}
        for un, u_data in STATE.get("users", {}).items():
            u_info = dict(u_data)
            u_info.pop('password', None)  # Strictly strip passwords from API responses
            sanitized_users[un] = u_info
            
        return jsonify({
            "pricePacks": STATE.get("pricePacks", []),
            "announcement": STATE.get("announcement", ""),
            "maintenance": STATE.get("maintenance", False),
            "siteLogo": STATE.get("siteLogo", "⚡"),
            "users": sanitized_users,
            "orders": STATE.get("orders", []),
            "bots": STATE.get("bots", {}),
            "coupons": STATE.get("coupons", {}),
            "redeemedBy": STATE.get("redeemedBy", {})
        })
    else:
        # Regular logged-in user: return public state + their own profile (sans password) + their own orders + their own bots
        user_info = dict(user)
        user_info.pop('password', None)  # Strictly strip user's password from response
        
        my_orders = [o for o in STATE.get("orders", []) if o.get("username") == username]
        my_bots = {bid: b for bid, b in STATE.get("bots", {}).items() if b.get("owner") == username}
        
        return jsonify({
            "pricePacks": STATE.get("pricePacks", []),
            "announcement": STATE.get("announcement", ""),
            "maintenance": STATE.get("maintenance", False),
            "siteLogo": STATE.get("siteLogo", "⚡"),
            "users": {
                username: user_info
            },
            "orders": my_orders,
            "bots": my_bots,
            "coupons": {},
            "redeemedBy": {}
        })


@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    if not username or not password or not email:
        return jsonify({"error": "Missing fields"}), 400
        
    if username in STATE['users']:
        return jsonify({"error": "Username already exists"}), 400

    # Save user to state
    STATE['users'][username] = {
        "username": username,
        "password": password,
        "email": email,
        "credits": 0,
        "role": "user",
        "banned": False,
        "registration_ip": get_client_ip(),
        "registration_country": get_client_country(),
        "last_login_ip": get_client_ip(),
        "last_login_country": get_client_country(),
        "last_active": datetime.now().isoformat()
    }
    save_state_to_file()

    # Welcome Email (optional — won't block registration if it fails)
    try:
        resend.Emails.send({
            "from": "info@glorybot.pro",
            "to": email,
            "subject": "Welcome to GLORY BOT PRO!",
            "html": f"<strong>Hello {username},</strong><br><br>Your account has been created successfully. Welcome to GLORY BOT PRO!"
        })
    except Exception as e:
        print(f"Email failed to send: {e}")

    return jsonify({"success": True, "message": "Account created successfully"})

FAILED_LOGINS = {}

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Missing fields"}), 400
        
    now = time.time()
    lock_info = FAILED_LOGINS.get(username)
    if lock_info and lock_info["count"] >= 5:
        if now < lock_info["lock_until"]:
            remaining = int(lock_info["lock_until"] - now)
            return jsonify({"error": f"Too many failed attempts. Try again in {remaining} seconds."}), 429
        else:
            FAILED_LOGINS[username] = {"count": 0, "lock_until": 0}
            
    user = STATE['users'].get(username)
    if not user or user['password'] != password:
        if username not in FAILED_LOGINS:
            FAILED_LOGINS[username] = {"count": 0, "lock_until": 0}
        FAILED_LOGINS[username]["count"] += 1
        if FAILED_LOGINS[username]["count"] >= 5:
            FAILED_LOGINS[username]["lock_until"] = now + 300  # Lock for 5 minutes
            return jsonify({"error": "Too many failed attempts. Account locked for 5 minutes."}), 429
            
        return jsonify({"error": "Invalid credentials"}), 401
        
    if username in FAILED_LOGINS:
        del FAILED_LOGINS[username]
        
    if user['banned']:
        return jsonify({"error": "Account banned"}), 403
    session['username'] = username
    
    # Update IP log and active timestamp
    user['last_login_ip'] = get_client_ip()
    user['last_login_country'] = get_client_country()
    user['last_active'] = datetime.now().isoformat()
    save_state_to_file()
    
    return jsonify({"success": True, "role": user['role']})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({"success": True})

@app.route("/api/fampay/create", methods=["POST"])
@login_required
def create_fampay_payment():
    import urllib.parse
    data = request.json
    amount = int(data.get("amount", 0))

    try:
        order_id = f"GB-{uuid.uuid4().hex[:8].upper()}"
        upi_link = f"upi://pay?pa={UPI_ID}&pn={urllib.parse.quote(PAYEE_NAME)}&am={amount}&cu=INR&tn={order_id}"
        encoded_upi = urllib.parse.quote_plus(upi_link)
        qr_url = f"/api/qr?data={encoded_upi}"

        return jsonify({
            "success": True,
            "order_id": order_id,
            "qr": qr_url,
            "amount": amount,
            "expires": "15 Minutes"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
@app.route('/api/current-user', methods=['GET'])        
def current_user():
    if 'username' in session:
        user = STATE['users'].get(session['username'])
        if user:
            return jsonify({
                "username": session['username'],
                "role": user['role'],
                "credits": user.get("credits", 0)
            })
    return jsonify({"error": "Not logged in"}), 401

@app.route('/api/security-status', methods=['GET'])
@login_required
def security_status():
    current_username = session['username']
    user = STATE['users'].get(current_username)
    if not user or user.get('role') not in ('admin', 'staff'):
        return jsonify({"error": "Forbidden"}), 403
        
    is_cf = 'CF-Connecting-IP' in request.headers
    return jsonify({
        "success": True,
        "is_cloudflare": is_cf,
        "ip": request.headers.get('CF-Connecting-IP', request.remote_addr),
        "country": request.headers.get('CF-IPCountry', 'Unknown'),
        "ray_id": request.headers.get('CF-RAY', 'N/A'),
        "protocol": request.headers.get('X-Forwarded-Proto', 'http'),
        "user_agent": request.headers.get('User-Agent', '')
    })



@app.route("/api/fampay/verify/<order_id>", methods=["GET"])
@login_required
def verify_fampay_payment(order_id):
    return jsonify({
        "verified": False,
        "message": "Manual verification required. Please enter UTR and upload screenshot."
    })
@app.route("/api/fampay/upload", methods=["POST"])
@login_required
def upload_payment_proof():
    if "screenshot" not in request.files:
        return jsonify({"success": False, "message": "Screenshot required"}), 400

    screenshot = request.files["screenshot"]
    os.makedirs("uploads", exist_ok=True)

    filename = f"{uuid.uuid4().hex}_{screenshot.filename}"
    path = os.path.join("uploads", filename)
    screenshot.save(path)

    STATE["orders"].append({
        "id": str(uuid.uuid4()),
        "username": session["username"],
        "order_id": request.form.get("order_id"),
        "credits": int(request.form.get("credits", 1)),
        "price": int(request.form.get("amount", 0)),
        "utr": request.form.get("utr"),
        "screenshot_path": path,
        "status": "pending",
        "ts": int(time.time() * 1000)
    })
    save_state_to_file()

    return jsonify({"success": True})   
@app.route('/api/save-state', methods=['POST'])
@login_required
def save_state():
    current = STATE['users'].get(session['username'])
    if not current:
        return jsonify({"error": "Forbidden"}), 403
    data = request.json
    
    current_username = session['username']
    
    if current['role'] in ('admin', 'staff'):
        # Intercept bot approvals to fetch immediate data from external API
        if 'bots' in data and isinstance(data['bots'], dict):
            for bid, incoming_bot in data['bots'].items():
                existing_bot = STATE.get('bots', {}).get(bid)
                # If newly approved
                if incoming_bot.get('approved') and (not existing_bot or not existing_bot.get('approved')):
                    clan_id = incoming_bot.get('uid')
                    region = incoming_bot.get('server', 'IND')
                    if clan_id:
                        res = fetch_guild_info(clan_id, region)
                        if res:
                            current_glory = res.get('glory_points', res.get('score', 0))
                            incoming_bot['initialGlory'] = current_glory
                            incoming_bot['score'] = current_glory
                            incoming_bot['glory'] = 0
                            incoming_bot['guildName'] = res.get('clan_name', incoming_bot.get('guildName', 'Guild'))
                            incoming_bot['level'] = res.get('guild_level', res.get('level', incoming_bot.get('level', 1)))
                            incoming_bot['members'] = res.get('current_members', incoming_bot.get('members', 5))
                            incoming_bot['maxMembers'] = res.get('total_members', incoming_bot.get('maxMembers', 25))
                            print(f"Newly approved bot {bid} immediately updated from API. initialGlory={current_glory}")

        # Admin or staff can modify all allowed keys, excluding 'users' (modified via specific routes)
        allowed_keys = ['orders', 'bots', 'coupons', 'redeemedBy', 'pricePacks', 'announcement', 'maintenance', 'siteLogo']
        for key in allowed_keys:
            if key in data:
                STATE[key] = data[key]
        print(f"Admin/Staff {current_username} saved state.")
    else:
        # Regular user validation
        user_data = STATE['users'].get(current_username)
        if not user_data:
            return jsonify({"error": "Forbidden"}), 403
            
        # 1. Process Bots
        if 'bots' in data and isinstance(data['bots'], dict):
            incoming_bots = data['bots']
            
            # Find deleted bots of this user
            deleted_bids = []
            for bid, bot in list(STATE['bots'].items()):
                if bot.get('owner') == current_username:
                    if bid not in incoming_bots:
                        deleted_bids.append(bid)
            
            # Apply deletions
            for bid in deleted_bids:
                del STATE['bots'][bid]
                print(f"Deleted bot {bid} for user {current_username}")
                
            # Process new/updated bots
            for bid, bot in incoming_bots.items():
                if not isinstance(bot, dict):
                    continue
                if bot.get('owner') != current_username:
                    continue
                    
                # Is this a new bot launch?
                if bid not in STATE['bots']:
                    if user_data.get('credits', 0) >= 1:
                        user_data['credits'] -= 1
                        bot['id'] = bid
                        bot['approved'] = False
                        bot['rejected'] = False
                        bot['glory'] = 0
                        bot['score'] = 0
                        STATE['bots'][bid] = bot
                        print(f"New bot launch requested by {current_username}: deducted 1 credit. New credit balance: {user_data['credits']}")
                    else:
                        print(f"User {current_username} tried to launch bot {bid} but had insufficient credits.")
                else:
                    # Existing bot update (e.g. restart or other permitted changes)
                    existing_bot = STATE['bots'][bid]
                    for field in ['uid', 'server', 'guildName', 'emoji', 'level', 'members', 'goal', 'requestTime', 'startTime']:
                        if field in bot:
                            existing_bot[field] = bot[field]
                    if bot.get('startTime') is not None:
                        existing_bot['startTime'] = bot['startTime']
                        existing_bot['overrideStatus'] = None
                        existing_bot['overridePct'] = None
                    print(f"Updated bot {bid} for user {current_username}")

        # 2. Process Coupons (Redemption)
        if 'redeemedBy' in data and 'coupons' in data:
            incoming_redeemed = data['redeemedBy']
            if isinstance(incoming_redeemed, dict):
                for code, users_list in incoming_redeemed.items():
                    if isinstance(users_list, list) and current_username in users_list:
                        # Check if already redeemed in backend
                        backend_redeemed = STATE.get('redeemedBy', {}).get(code, [])
                        if current_username not in backend_redeemed:
                            coupon = STATE.get('coupons', {}).get(code)
                            if coupon and coupon.get('uses', 0) < coupon.get('maxUses', 100):
                                coupon['uses'] = coupon.get('uses', 0) + 1
                                if 'redeemedBy' not in STATE:
                                    STATE['redeemedBy'] = {}
                                if code not in STATE['redeemedBy']:
                                    STATE['redeemedBy'][code] = []
                                STATE['redeemedBy'][code].append(current_username)
                                added_credits = coupon.get('credits', 0)
                                user_data['credits'] = user_data.get('credits', 0) + added_credits
                                print(f"Coupon {code} redeemed by {current_username}: +{added_credits} credits")

    save_state_to_file()
    return jsonify({"success": True})


@app.route('/api/admin/update-user', methods=['POST'])
@login_required
def admin_update_user():
    current = STATE['users'].get(session['username'])
    if not current or current['role'] not in ('admin', 'staff'):
        return jsonify({"error": "Forbidden"}), 403
    data = request.json
    target_username = data.get('username')
    target = STATE['users'].get(target_username)
    if not target:
        return jsonify({"error": "User not found"}), 404
    # Staff cannot modify admin accounts
    if current['role'] == 'staff' and target['role'] == 'admin':
        return jsonify({"error": "Staff cannot modify admin accounts"}), 403
    if 'credits' in data:
        target['credits'] = max(0, int(data['credits']))
    if 'banned' in data:
        target['banned'] = bool(data['banned'])
    save_state_to_file()
    return jsonify({"success": True, "credits": target['credits'], "banned": target['banned']})

@app.route('/api/admin/set-role', methods=['POST'])
@login_required
def admin_set_role():
    current = STATE['users'].get(session['username'])
    if not current or current['role'] not in ('admin', 'staff'):
        return jsonify({"error": "Forbidden"}), 403
    data = request.json
    target_username = data.get('username')
    new_role = data.get('role')
    if new_role not in ('user', 'staff', 'admin'):
        return jsonify({"error": "Invalid role"}), 400
    target = STATE['users'].get(target_username)
    if not target:
        return jsonify({"error": "User not found"}), 404
    # Staff cannot modify admin accounts
    if current['role'] == 'staff' and target['role'] == 'admin':
        return jsonify({"error": "Staff cannot modify admin accounts"}), 403
    # Only admin can promote to admin
    if new_role == 'admin' and current['role'] != 'admin':
        return jsonify({"error": "Only admin can grant admin role"}), 403
    # Only admin can demote admin
    if target['role'] == 'admin' and current['role'] != 'admin':
        return jsonify({"error": "Only admin can modify admin accounts"}), 403
    target['role'] = new_role
    save_state_to_file()
    return jsonify({"success": True, "role": new_role})

# ════════════════════════════════════════════════════════════════════════
# 🤖 TELEGRAM BOT INTEGRATION
# ════════════════════════════════════════════════════════════════════════
BOT_TOKEN = "8988271223:AAEhRDyq13KnTbMufyQsjoTR9Q76Io4JK0Q"
OWNERS = [8078228501, 8726156194]
bot = telebot.TeleBot(BOT_TOKEN, threaded=False) 

def check_sub(user_id):
    # Added @glorybothelp to the list
    channels = ["@bbytopapis", "@glorybotpro", "@glorybothelp"]
    for ch in channels:
        try:
            status = bot.get_chat_member(ch, user_id).status
            if status in ['left', 'kicked']:
                return False
        except:
            pass # Fail safe agar bot channel ka admin nahi hai
    return True

def sub_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Join Channel 1", url="bbytopapis"))
    markup.add(InlineKeyboardButton("Join Channel 2", url="https://t.me/glorybotpro"))
    # Added the 3rd channel button
    markup.add(InlineKeyboardButton("Join Channel 3", url="https://t.me/glorybothelp"))
    markup.add(InlineKeyboardButton("✅ Joined", callback_data="check_joined"))
    return markup

def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("💰 Check Balance"), KeyboardButton("➕ Add Balance"))
    markup.add(KeyboardButton("🚀 Credit Guild Glory Bot"), KeyboardButton("📞 Contact Owner"))
    if user_id in OWNERS:
        markup.add(KeyboardButton("👑 Owner Panel"))
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    cid = message.chat.id
    if not check_sub(cid):
        bot.send_message(cid, "Please join our official channels to use the bot!", reply_markup=sub_markup())
        return
        
    if "tg_users" not in STATE: STATE["tg_users"] = {}
    if str(cid) not in STATE["tg_users"]:
        STATE["tg_users"][str(cid)] = {"balance": 0}
        
    bot.send_message(cid, "Welcome to GLORY BOT PRO Bot! ⚡\nChoose an option below:", reply_markup=main_menu(cid))

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    cid = message.chat.id
    text = message.text
    
    if not check_sub(cid):
        bot.send_message(cid, "Please join our channels first!", reply_markup=sub_markup())
        return

    if "tg_users" not in STATE: STATE["tg_users"] = {}
    if str(cid) not in STATE["tg_users"]:
        STATE["tg_users"][str(cid)] = {"balance": 0}

    if text == "💰 Check Balance":
        bal = STATE["tg_users"][str(cid)]["balance"]
        bot.send_message(cid, f"🏦 Your current bot balance is: ₹{bal}\n\nNote: This balance is for the bot. Use 'Credit Guild Glory Bot' to buy website credits.")
        
    elif text == "➕ Add Balance":
        msg = bot.send_message(cid, "How much money do you want to add? (Enter amount in numbers, e.g., 499)")
        bot.register_next_step_handler(msg, process_add_balance)
        
    elif text == "🚀 Credit Guild Glory Bot":
        bal = STATE["tg_users"][str(cid)]["balance"]
        # Auto sync price with website's starter pack (if price changes on site, it changes here too)
        starter_price = int(STATE["pricePacks"][0]["price"]) if STATE["pricePacks"] else 499
        
        if bal < starter_price:
            bot.send_message(cid, f"❌ Insufficient Balance.\nYou need at least ₹{starter_price} for 1 Credit. Please add balance first.")
            return
            
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Yes", callback_data="has_acc_yes"), InlineKeyboardButton("No", callback_data="has_acc_no"))
        bot.send_message(cid, "Do you have an account on our website (glorybot.pro)?", reply_markup=markup)
        
    elif text == "📞 Contact Owner":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("👑 Owner - YDV", url="https://t.me/ydv_codex"))
        markup.add(InlineKeyboardButton("👑 Owner - BBYTOP3", url="https://t.me/BBYTOP3"))
        bot.send_message(cid, "Select an owner to contact:", reply_markup=markup)
        
    elif text == "👑 Owner Panel" and cid in OWNERS:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Add Credit to Any User", callback_data="admin_add_credit"))
        bot.send_message(cid, "👑 Welcome to the Owner Panel:", reply_markup=markup)

def process_add_balance(message):
    cid = message.chat.id
    try:
        amt = int(message.text)
        if amt < 1: raise ValueError
    except:
        bot.send_message(cid, "Invalid amount. Please click 'Add Balance' and try again with a valid number.")
        return
        
    try:
        import urllib.parse
        import io
        order_id = f"GB-{uuid.uuid4().hex[:8].upper()}"
        upi_link = f"upi://pay?pa={UPI_ID}&pn={urllib.parse.quote(PAYEE_NAME)}&am={amt}&cu=INR&tn={order_id}"
        
        qr_img = generate_qr_with_logo(upi_link)
        bio = io.BytesIO()
        bio.name = 'qr.png'
        qr_img.save(bio, 'PNG')
        bio.seek(0)
    except Exception as e:
        bot.send_message(cid, f"❌ Error generating QR code: {e}")
        return
        
    msg_text = (f"🔰 **Pay Exact:** ₹{amt}\n"
                f"🔖 **UPI ID:** `{UPI_ID}`\n\n"
                f"⚠️ Please scan the QR code above or pay directly to the UPI ID.\n"
                f"Once paid, send your **12-digit UPI UTR / Transaction Reference Number**:")
    
    bot.send_photo(cid, bio, caption=msg_text, parse_mode="Markdown")
    bot.register_next_step_handler(message, lambda m: get_utr_for_balance(m, order_id, amt))

def get_utr_for_balance(message, order_id, amt):
    cid = message.chat.id
    utr = message.text.strip() if message.text else ""
    if not utr or len(utr) < 6:
        bot.send_message(cid, "❌ Invalid UTR. Payment request cancelled. Please click 'Add Balance' and try again.")
        return
        
    msg = bot.send_message(cid, "📷 Now, please upload the **payment screenshot** for verification:")
    bot.register_next_step_handler(msg, lambda m: process_payment_screenshot(m, order_id, amt, utr))

def process_payment_screenshot(message, order_id, amt, utr):
    cid = message.chat.id
    
    if not message.photo:
        bot.send_message(cid, "❌ You didn't send a valid screenshot. Request cancelled.")
        return

    file_info = bot.get_file(message.photo[-1].file_id)
    bot.send_message(cid, "✅ Your payment request and screenshot have been sent to admins for approval. Please wait for confirmation.")

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Approve ✅", callback_data=f"apptg_{cid}_{amt}_{utr}"),
        InlineKeyboardButton("Reject ❌", callback_data=f"rejtg_{cid}_{amt}")
    )
    
    caption_text = f"🔔 **New Wallet Add Request!**\n\n👤 TG ID: `{cid}`\n💰 Amount: ₹{amt}\n🔖 UTR: `{utr}`\n🆔 Order ID: `{order_id}`"
    
    for owner in OWNERS:
        try:
            bot.send_photo(owner, file_info.file_id, caption=caption_text, parse_mode="Markdown", reply_markup=markup)
        except: pass

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    cid = call.message.chat.id
    
    if call.data == "check_joined":
        if check_sub(cid):
            bot.answer_callback_query(call.id, "Verification successful! ✅")
            bot.delete_message(cid, call.message.message_id)
            bot.send_message(cid, "Welcome to GLORY BOT PRO Bot! ⚡", reply_markup=main_menu(cid))
        else:
            bot.answer_callback_query(call.id, "You haven't joined both channels yet! ❌", show_alert=True)
            
    elif call.data.startswith("apptg_"):
        parts = call.data.split("_")
        target_cid = parts[1]
        amt = int(parts[2])
        
        STATE["tg_users"][str(target_cid)]["balance"] += amt
        save_state_to_file()
        bot.edit_message_text(f"✅ Approved. ₹{amt} added to TG ID {target_cid}.", cid, call.message.message_id)
        try:
            bot.send_message(target_cid, f"✅ **Payment Verified & Approved!**\n₹{amt} has been added to your bot balance.", parse_mode="Markdown")
        except: pass
        
    elif call.data.startswith("rejtg_"):
        parts = call.data.split("_")
        target_cid = parts[1]
        amt = int(parts[2])
        bot.edit_message_text("❌ Request Rejected.", cid, call.message.message_id)
        try:
            bot.send_message(target_cid, f"❌ **Your payment of ₹{amt} was rejected by the admin.** Please contact support.", parse_mode="Markdown")
        except: pass
            
    elif call.data == "has_acc_no":
        bot.edit_message_text("🔗 **Please visit** https://glorybot.pro\n\n1. Create your account.\n2. Come back to this bot.\n3. Click 'Credit Guild Glory Bot' again and select **Yes**.", cid, call.message.message_id, parse_mode="Markdown", disable_web_page_preview=True)
        
    elif call.data == "has_acc_yes":
        msg = bot.edit_message_text("Great! Send your **Website Username** and **Email** separated by a space.\n\n*Example:* `Keshv keshv@gmail.com`", cid, call.message.message_id, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_glory_request)
        
    elif call.data == "admin_add_credit":
        msg = bot.send_message(cid, "👤 Enter the exact **Website Username** of the user:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, admin_get_username)
        
    elif call.data.startswith("approve_"):
        parts = call.data.split("_")
        target_cid = parts[1]
        target_user = parts[2]
        amt_paid = int(parts[3])
        
        if target_user in STATE["users"]:
            STATE["users"][target_user]["credits"] += 1
            save_state_to_file()
            bot.edit_message_text(f"✅ Approved. 1 Credit added to {target_user} on website.", cid, call.message.message_id)
            try:
                bot.send_message(target_cid, "🎉 **Dear user, your approval has been confirmed!**\n\nPlease check https://glorybot.pro. Your credits have been added successfully.", parse_mode="Markdown", disable_web_page_preview=True)
            except: pass
        else:
            bot.answer_callback_query(call.id, "User not found in website database! Cannot add credits.", show_alert=True)
            
    elif call.data.startswith("reject_"):
        parts = call.data.split("_")
        target_cid = parts[1]
        amt_paid = int(parts[3])
        bot.edit_message_text("❌ Request Rejected. Balance refunded to user.", cid, call.message.message_id)
        STATE["tg_users"][str(target_cid)]["balance"] += amt_paid
        save_state_to_file()
        try:
            bot.send_message(target_cid, "❌ **Your credit request was rejected by the admin.**\nYour money has been refunded to your bot balance.", parse_mode="Markdown")
        except: pass

def process_glory_request(message):
    cid = message.chat.id
    try:
        username, email = message.text.split(" ", 1)
    except:
        bot.send_message(cid, "❌ Invalid format. Please send Username and Email separated by a space.")
        return
        
    starter_price = int(STATE["pricePacks"][0]["price"]) if STATE["pricePacks"] else 499
    
    if STATE["tg_users"][str(cid)]["balance"] < starter_price:
        bot.send_message(cid, "❌ Insufficient balance.")
        return
        
    # User ka paisa wallet se cut gaya
    STATE["tg_users"][str(cid)]["balance"] -= starter_price
    save_state_to_file()
    
    bot.send_message(cid, "✅ Your order has been submitted to admins for approval. Please wait for the confirmation message.")
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Approve ✅", callback_data=f"approve_{cid}_{username}_{starter_price}"),
        InlineKeyboardButton("Reject ❌", callback_data=f"reject_{cid}_0_{starter_price}")
    )
    for owner in OWNERS:
        try:
            bot.send_message(owner, f"🔔 **New Credit Request!**\n\n👤 TG ID: `{cid}`\n🌐 Web User: `{username}`\n📧 Email: `{email}`\n💰 Amount Deducted: ₹{starter_price}", parse_mode="Markdown", reply_markup=markup)
        except: pass

def admin_get_username(message):
    cid = message.chat.id
    username = message.text.strip()
    if username not in STATE["users"]:
        bot.send_message(cid, f"❌ User '{username}' not found in website database.")
        return
    current_credits = STATE['users'][username].get('credits', 0)
    msg = bot.send_message(cid, f"✅ User found: **{username}** (Current Credits: {current_credits})\n\nHow many credits do you want to add? (Enter a number)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: admin_add_credits_final(m, username))

def admin_add_credits_final(message, username):
    cid = message.chat.id
    try:
        amt = int(message.text)
        STATE["users"][username]["credits"] += amt
        save_state_to_file()
        bot.send_message(cid, f"✅ Success! Added {amt} credits to {username}.\nNew balance: {STATE['users'][username]['credits']}")
    except:
        bot.send_message(cid, "❌ Invalid number. Operation cancelled.")

# Background thread taaki Flask aur Bot ek saath chal saken
def run_bot():
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Telegram Bot error: {e}")
            time.sleep(3)

bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False)
