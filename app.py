from flask import Flask, jsonify, render_template, request, session, send_from_directory
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
from threading import Lock

# ─── CONFIG ───────────────────────────────────────────────────────────────────
resend.api_key = "re_Use1fV2g_7uP3F5e7EMjXGyBZ6nFf19wV"

app = Flask(__name__)
app.secret_key = "ydv-glory-simple-key"

# ─── UPI / FAMPAY CONFIG ──────────────────────────────────────────────────────
FAMPAY_API_KEY = "FAM_abcf6524d550262d3905933b996806dcc952cfa5ec131d82"
UPI_ID = "adityahere777@fam"
PAYEE_NAME = "Aditya"
PAYEE_EMAIL = "adiu4047@gmail.com"
PAYEE_NUMBER = "7004973360"

FAMPAY_QR_API = "https://fampay.anujbots.xyz/qr.php"
FAMPAY_VERIFY_API = "https://fampay.anujbots.xyz/verify.php"

# ─── FILE PATHS ───────────────────────────────────────────────────────────────
DATA_DIR = 'data'
STATE_FILE = os.path.join(DATA_DIR, 'state.json')
CODE_FILE = os.path.join(DATA_DIR, 'code.json')
UPLOADS_DIR = 'uploads'

# ─── INITIAL DEFAULT STATE ────────────────────────────────────────────────────
DEFAULT_STATE = {
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
    "siteLogo": "⚡",
    "tg_users": {}
}

# ─── STATE MANAGEMENT WITH FILE PERSISTENCE ───────────────────────────────────
state_lock = Lock()

def load_state():
    """Load state from JSON file, create with defaults if not exists"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        save_state(DEFAULT_STATE)
        return DEFAULT_STATE.copy()
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print("⚠️ State file corrupted, creating new one")
        save_state(DEFAULT_STATE)
        return DEFAULT_STATE.copy()

def save_state(state=None):
    """Save state to JSON file with thread safety"""
    if state is None:
        state = STATE
    os.makedirs(DATA_DIR, exist_ok=True)
    with state_lock:
        try:
            # Atomic write: write to temp file then rename
            temp_file = STATE_FILE + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(temp_file, STATE_FILE)  # Atomic operation
        except Exception as e:
            print(f"❌ Failed to save state: {e}")

# Initialize STATE from file
STATE = load_state()

# ─── CODE MANAGEMENT (OTP/Verification codes) ────────────────────────────────
def load_codes():
    if not os.path.exists(CODE_FILE):
        return {}
    try:
        with open(CODE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_codes(codes):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CODE_FILE, 'w') as f:
        json.dump(codes, f)

def clean_expired_codes():
    codes = load_codes()
    current_time = time.time()
    codes = {email: data for email, data in codes.items() if current_time - data['timestamp'] < 300}
    save_codes(codes)

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Decorator for admin/staff only endpoints"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        user = STATE['users'].get(session['username'])
        if not user or user['role'] not in ('admin', 'staff'):
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated

def add_credits_safe(username, amount):
    """Safely add credits with persistence"""
    if username in STATE['users']:
        STATE['users'][username]['credits'] = max(0, STATE['users'][username].get('credits', 0) + amount)
        save_state(STATE)
        return True
    return False

def deduct_credits_safe(username, amount):
    """Safely deduct credits with persistence"""
    if username in STATE['users']:
        current = STATE['users'][username].get('credits', 0)
        if current >= amount:
            STATE['users'][username]['credits'] = current - amount
            save_state(STATE)
            return True
    return False

# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/video.mp4')
def serve_video():
    return send_from_directory('.', 'video.mp4')

@app.route('/uploads/<filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOADS_DIR, filename)

# ─── PUBLIC API ─────────────────────────────────────────────────────────────

@app.route('/api/get-private-data', methods=['GET'])
def get_private_data():
    # Return only necessary public data, not full state
    public_data = {
        "pricePacks": STATE.get('pricePacks', []),
        "announcement": STATE.get('announcement', ''),
        "maintenance": STATE.get('maintenance', False),
        "siteLogo": STATE.get('siteLogo', '⚡'),
        "coupons": STATE.get('coupons', {}),
        "bots": STATE.get('bots', {})
    }
    return jsonify(public_data)

@app.route('/api/get-full-state', methods=['GET'])
@admin_required
def get_full_state():
    """Admin only - returns complete state"""
    return jsonify(STATE)

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

    # Save user to state AND persist
    STATE['users'][username] = {
        "username": username,
        "password": password,
        "email": email,
        "credits": 0,
        "role": "user",
        "banned": False
    }
    save_state(STATE)  # ✅ PERSIST IMMEDIATELY

    # Welcome Email (non-blocking)
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

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    user = STATE['users'].get(username)
    if not user or user['password'] != password:
        return jsonify({"error": "Invalid credentials"}), 401
    if user['banned']:
        return jsonify({"error": "Account banned"}), 403
    session['username'] = username
    return jsonify({"success": True, "role": user['role'], "credits": user.get('credits', 0)})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({"success": True})

@app.route('/api/current-user', methods=['GET'])
def current_user():
    if 'username' in session:
        user = STATE['users'].get(session['username'])
        if user:
            return jsonify({
                "username": session['username'],
                "role": user['role'],
                "credits": user.get("credits", 0),
                "email": user.get("email", "")
            })
    return jsonify({"error": "Not logged in"}), 401

@app.route('/api/update-credits', methods=['POST'])
@login_required
def update_credits():
    """
    ✅ SAFE CREDIT UPDATE - Called by frontend after payment verification
    Only allows ADDING credits, never deducting via this endpoint
    """
    data = request.json
    username = data.get('username')
    amount = int(data.get('amount', 0))
    
    # Security: Only admin can update other users
    current_user = STATE['users'].get(session['username'])
    if username != session['username'] and current_user['role'] not in ('admin', 'staff'):
        return jsonify({"error": "Forbidden"}), 403
    
    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400
    
    if add_credits_safe(username, amount):
        return jsonify({
            "success": True,
            "username": username,
            "new_credits": STATE['users'][username]['credits']
        })
    return jsonify({"error": "User not found"}), 404

@app.route("/api/fampay/create", methods=["POST"])
@login_required
def create_fampay_payment():
    data = request.json
    amount = int(data.get("amount", 0))

    try:
        r = requests.get(
            FAMPAY_QR_API,
            params={
                "upi": UPI_ID,
                "amount": amount
            },
            timeout=20
        )

        res = r.json()

        if res.get("status") != "success":
            return jsonify({
                "success": False,
                "message": "Unable to generate QR"
            }), 400

        return jsonify({
            "success": True,
            "order_id": res["data"]["order_id"],
            "qr": res["data"]["qr_url"],
            "amount": res["data"]["amount"],
            "expires": res["data"]["expires_at_ist"]
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route("/api/fampay/verify/<order_id>", methods=["GET"])
@login_required
def verify_fampay_payment(order_id):
    try:
        r = requests.get(
            FAMPAY_VERIFY_API,
            params={
                "order_id": order_id,
                "api_key": FAMPAY_API_KEY
            },
            timeout=20
        )

        res = r.json()

        if res.get("status") == "success":
            data = res["data"]
            # ✅ Automatically add credits on successful payment
            credits_to_add = 0
            for pack in STATE.get('pricePacks', []):
                if pack['price'] == int(data['amount']):
                    credits_to_add = pack['credits']
                    break
            
            if credits_to_add > 0:
                add_credits_safe(session['username'], credits_to_add)
                # Save order record
                STATE['orders'].append({
                    "id": order_id,
                    "username": session['username'],
                    "credits": credits_to_add,
                    "price": int(data['amount']),
                    "utr": data['utr'],
                    "status": "completed",
                    "ts": int(time.time() * 1000)
                })
                save_state(STATE)

            return jsonify({
                "verified": True,
                "transaction_id": data["transaction_id"],
                "utr": data["utr"],
                "sender": data["sender_name"],
                "amount": data["amount"],
                "payment_time": data["payment_time_ist"],
                "credits_added": credits_to_add
            })

        return jsonify({
            "verified": False,
            "message": res.get("message", "Payment Pending")
        })

    except Exception as e:
        return jsonify({
            "verified": False,
            "message": str(e)
        }), 500

@app.route("/api/fampay/upload", methods=["POST"])
@login_required
def upload_payment_proof():
    if "screenshot" not in request.files:
        return jsonify({"success": False, "message": "Screenshot required"}), 400

    screenshot = request.files["screenshot"]
    os.makedirs(UPLOADS_DIR, exist_ok=True)

    filename = f"{uuid.uuid4().hex}_{screenshot.filename}"
    path = os.path.join(UPLOADS_DIR, filename)
    screenshot.save(path)

    order_data = {
        "id": str(uuid.uuid4()),
        "username": session["username"],
        "order_id": request.form.get("order_id"),
        "credits": int(request.form.get("credits", 1)),
        "price": int(request.form.get("amount", 0)),
        "utr": request.form.get("utr"),
        "screenshot_path": path,
        "status": "pending",
        "ts": int(time.time() * 1000)
    }
    
    STATE["orders"].append(order_data)
    save_state(STATE)  # ✅ PERSIST

    return jsonify({"success": True, "order": order_data})

@app.route('/api/save-state', methods=['POST'])
@admin_required
def save_state_endpoint():
    """
    ✅ FIXED: Now properly saves state to file
    Only admin/staff can use this
    """
    data = request.json
    allowed_keys = ['orders', 'bots', 'coupons', 'redeemedBy', 'pricePacks', 
                    'announcement', 'maintenance', 'siteLogo', 'tg_users']
    
    with state_lock:
        for key in allowed_keys:
            if key in data:
                STATE[key] = data[key]
        save_state(STATE)  # ✅ PERSIST TO FILE
    
    return jsonify({"success": True, "message": "State saved successfully"})

@app.route('/api/admin/update-user', methods=['POST'])
@admin_required
def admin_update_user():
    current = STATE['users'].get(session['username'])
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
    
    save_state(STATE)  # ✅ PERSIST
    return jsonify({"success": True, "credits": target['credits'], "banned": target['banned']})

@app.route('/api/admin/set-role', methods=['POST'])
@admin_required
def admin_set_role():
    current = STATE['users'].get(session['username'])
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
    save_state(STATE)  # ✅ PERSIST
    return jsonify({"success": True, "role": new_role})

@app.route('/api/admin/get-orders', methods=['GET'])
@admin_required
def admin_get_orders():
    """Get all orders for admin panel"""
    return jsonify({"orders": STATE.get('orders', [])})

@app.route('/api/admin/approve-order', methods=['POST'])
@admin_required
def admin_approve_order():
    """Approve a pending order and add credits"""
    data = request.json
    order_id = data.get('order_id')
    
    for order in STATE.get('orders', []):
        if order['id'] == order_id and order['status'] == 'pending':
            order['status'] = 'approved'
            add_credits_safe(order['username'], order['credits'])
            save_state(STATE)
            return jsonify({"success": True, "order": order})
    
    return jsonify({"error": "Order not found or already processed"}), 404

@app.route('/api/admin/reject-order', methods=['POST'])
@admin_required
def admin_reject_order():
    """Reject a pending order"""
    data = request.json
    order_id = data.get('order_id')
    
    for order in STATE.get('orders', []):
        if order['id'] == order_id and order['status'] == 'pending':
            order['status'] = 'rejected'
            save_state(STATE)
            return jsonify({"success": True, "order": order})
    
    return jsonify({"error": "Order not found or already processed"}), 404

# ════════════════════════════════════════════════════════════════════════
# 🤖 TELEGRAM BOT INTEGRATION (with persistence fixes)
# ════════════════════════════════════════════════════════════════════════
BOT_TOKEN = "8988271223:AAEhRDyq13KnTbMufyQsjoTR9Q76Io4JK0Q"
OWNERS = [8703570301, 8726156194]
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def check_sub(user_id):
    channels = ["@keshvexffmethod", "@glorybotpro", "@glorybothelp"]
    for ch in channels:
        try:
            status = bot.get_chat_member(ch, user_id).status
            if status in ['left', 'kicked']:
                return False
        except:
            pass
    return True

def sub_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Join Channel 1", url="https://t.me/keshvexffmethod"))
    markup.add(InlineKeyboardButton("Join Channel 2", url="https://t.me/glorybotpro"))
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
        
    if "tg_users" not in STATE:
        STATE["tg_users"] = {}
    if str(cid) not in STATE["tg_users"]:
        STATE["tg_users"][str(cid)] = {"balance": 0}
        save_state(STATE)  # ✅ PERSIST NEW TG USER
        
    bot.send_message(cid, "Welcome to GLORY BOT PRO Bot! ⚡\nChoose an option below:", reply_markup=main_menu(cid))

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    cid = message.chat.id
    text = message.text
    
    if not check_sub(cid):
        bot.send_message(cid, "Please join our channels first!", reply_markup=sub_markup())
        return

    if "tg_users" not in STATE:
        STATE["tg_users"] = {}
    if str(cid) not in STATE["tg_users"]:
        STATE["tg_users"][str(cid)] = {"balance": 0}
        save_state(STATE)

    if text == "💰 Check Balance":
        bal = STATE["tg_users"][str(cid)]["balance"]
        bot.send_message(cid, f"🏦 Your current bot balance is: ₹{bal}\n\nNote: This balance is for the bot. Use 'Credit Guild Glory Bot' to buy website credits.")
        
    elif text == "➕ Add Balance":
        msg = bot.send_message(cid, "How much money do you want to add? (Enter amount in numbers, e.g., 499)")
        bot.register_next_step_handler(msg, process_add_balance)
        
    elif text == "🚀 Credit Guild Glory Bot":
        bal = STATE["tg_users"][str(cid)]["balance"]
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
        markup.add(InlineKeyboardButton("📊 View All Orders", callback_data="admin_view_orders"))
        bot.send_message(cid, "👑 Welcome to the Owner Panel:", reply_markup=markup)

def process_add_balance(message):
    cid = message.chat.id
    try:
        amt = int(message.text)
        if amt < 1:
            raise ValueError
    except:
        bot.send_message(cid, "Invalid amount. Please click 'Add Balance' and try again with a valid number.")
        return
        
    try:
        r = requests.get(
            FAMPAY_QR_API,
            params={"upi": UPI_ID, "amount": amt},
            timeout=20
        )
        data = r.json()

        if data.get("status") != "success":
            bot.send_message(cid, "❌ QR generation failed.")
            return

        order_id = data["data"]["order_id"]
        qr_url = data["data"]["qr_url"]

    except Exception as e:
        bot.send_message(cid, f"❌ API Error:\n{e}")
        return
        
    msg_text = (f"🔰 **Pay Exact:** ₹{amt}\n"
                f"🔖 **UPI ID:** `{UPI_ID}`\n\n"
                f"⚠️ Please scan the QR code above or pay directly to the UPI ID.\n"
                f"After completing the payment, wait for auto-verification.")
    
    bot.send_photo(cid, qr_url, caption=msg_text, parse_mode="Markdown")
    bot.send_message(cid, "⏳ Waiting for auto verification...\nPlease don't close the bot.")

    threading.Thread(
        target=wait_for_payment_verification,
        args=(cid, order_id, amt),
        daemon=True
    ).start()

def wait_for_payment_verification(cid, order_id, amt):
    attempts = 0
    while attempts < 60:
        try:
            verify = requests.get(
                FAMPAY_VERIFY_API,
                params={"order_id": order_id, "api_key": FAMPAY_API_KEY},
                timeout=15
            ).json()

            if verify.get("status") == "success":
                data = verify["data"]
                bot.send_message(
                    cid,
                    f"✅ Payment Verified Successfully!\n💰 Amount: ₹{data['amount']}\n🔖 UTR: `{data['utr']}`\n\n📷 **Please send your payment screenshot** for admin approval."
                )
                msg = bot.send_message(cid, "Upload screenshot now.")
                bot.register_next_step_handler(
                    msg,
                    lambda m: process_payment_screenshot(m, order_id, data["amount"], data["utr"])
                )
                return

        except Exception as e:
            print("Verify Error:", e)

        time.sleep(5)
        attempts += 1
        
    bot.send_message(cid, "❌ Verification timeout. If you already paid, please contact admin manually.")

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
        except:
            pass

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    cid = call.message.chat.id
    
    if call.data == "check_joined":
        if check_sub(cid):
            bot.answer_callback_query(call.id, "Verification successful! ✅")
            bot.delete_message(cid, call.message.message_id)
            bot.send_message(cid, "Welcome to GLORY BOT PRO Bot! ⚡", reply_markup=main_menu(cid))
        else:
            bot.answer_callback_query(call.id, "You haven't joined all channels yet! ❌", show_alert=True)
            
    elif call.data.startswith("apptg_"):
        parts = call.data.split("_")
        target_cid = parts[1]
        amt = int(parts[2])
        
        # ✅ FIXED: Persist balance update
        if "tg_users" not in STATE:
            STATE["tg_users"] = {}
        if str(target_cid) not in STATE["tg_users"]:
            STATE["tg_users"][str(target_cid)] = {"balance": 0}
        
        STATE["tg_users"][str(target_cid)]["balance"] += amt
        save_state(STATE)  # ✅ PERSIST
        
        bot.edit_message_text(f"✅ Approved. ₹{amt} added to TG ID {target_cid}.", cid, call.message.message_id)
        try:
            bot.send_message(target_cid, f"✅ **Payment Verified & Approved!**\n₹{amt} has been added to your bot balance.", parse_mode="Markdown")
        except:
            pass
        
    elif call.data.startswith("rejtg_"):
        parts = call.data.split("_")
        target_cid = parts[1]
        amt = int(parts[2])
        
        bot.edit_message_text("❌ Request Rejected.", cid, call.message.message_id)
        try:
            bot.send_message(target_cid, f"❌ **Your payment of ₹{amt} was rejected by the admin.** Please contact support.", parse_mode="Markdown")
        except:
            pass
            
    elif call.data == "has_acc_no":
        bot.edit_message_text(
            "🔗 **Please visit** https://glorybot.pro\n\n1. Create your account.\n2. Come back to this bot.\n3. Click 'Credit Guild Glory Bot' again and select **Yes**.",
            cid, call.message.message_id, parse_mode="Markdown", disable_web_page_preview=True
        )
        
    elif call.data == "has_acc_yes":
        msg = bot.edit_message_text(
            "Great! Send your **Website Username** and **Email** separated by a space.\n\n*Example:* `Keshv keshv@gmail.com`",
            cid, call.message.message_id, parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_glory_request)
        
    elif call.data == "admin_add_credit":
        msg = bot.send_message(cid, "👤 Enter the exact **Website Username** of the user:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, admin_get_username)
        
    elif call.data == "admin_view_orders":
        orders = STATE.get('orders', [])
        pending = [o for o in orders if o['status'] == 'pending']
        if not pending:
            bot.send_message(cid, "📊 No pending orders.")
        else:
            text = f"📊 **Pending Orders ({len(pending)})**\n\n"
            for o in pending[-5:]:
                text += f"🆔 `{o['id'][:8]}...`\n👤 {o['username']}\n💰 ₹{o['price']} → {o['credits']} credits\n📅 {datetime.fromtimestamp(o['ts']/1000).strftime('%d/%m %H:%M')}\n\n"
            bot.send_message(cid, text, parse_mode="Markdown")
        
    elif call.data.startswith("approve_"):
        parts = call.data.split("_")
        target_cid = parts[1]
        target_user = parts[2]
        amt_paid = int(parts[3])
        
        # ✅ FIXED: Proper persistence
        if target_user in STATE["users"]:
            add_credits_safe(target_user, 1)  # Add 1 credit
            bot.edit_message_text(f"✅ Approved. 1 Credit added to {target_user} on website.", cid, call.message.message_id)
            try:
                bot.send_message(target_cid, "🎉 **Dear user, your approval has been confirmed!**\n\nPlease check https://glorybot.pro. Your credits have been added successfully.", parse_mode="Markdown", disable_web_page_preview=True)
            except:
                pass
        else:
            bot.answer_callback_query(call.id, "User not found in website database! Cannot add credits.", show_alert=True)
            
    elif call.data.startswith("reject_"):
        parts = call.data.split("_")
        target_cid = parts[1]
        amt_paid = int(parts[3])
        
        # ✅ FIXED: Refund balance with persistence
        if "tg_users" not in STATE:
            STATE["tg_users"] = {}
        if str(target_cid) not in STATE["tg_users"]:
            STATE["tg_users"][str(target_cid)] = {"balance": 0}
        
        STATE["tg_users"][str(target_cid)]["balance"] += amt_paid
        save_state(STATE)  # ✅ PERSIST
        
        bot.edit_message_text("❌ Request Rejected. Balance refunded to user.", cid, call.message.message_id)
        try:
            bot.send_message(target_cid, "❌ **Your credit request was rejected by the admin.**\nYour money has been refunded to your bot balance.", parse_mode="Markdown")
        except:
            pass

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
        
    # ✅ Deduct with persistence
    STATE["tg_users"][str(cid)]["balance"] -= starter_price
    save_state(STATE)  # ✅ PERSIST DEDUCTION
    
    bot.send_message(cid, "✅ Your order has been submitted to admins for approval. Please wait for the confirmation message.")
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Approve ✅", callback_data=f"approve_{cid}_{username}_{starter_price}"),
        InlineKeyboardButton("Reject ❌", callback_data=f"reject_{cid}_0_{starter_price}")
    )
    for owner in OWNERS:
        try:
            bot.send_message(owner, f"🔔 **New Credit Request!**\n\n👤 TG ID: `{cid}`\n🌐 Web User: `{username}`\n📧 Email: `{email}`\n💰 Amount Deducted: ₹{starter_price}", parse_mode="Markdown", reply_markup=markup)
        except:
            pass

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
        add_credits_safe(username, amt)  # ✅ PERSISTED
        bot.send_message(cid, f"✅ Success! Added {amt} credits to {username}.\nNew balance: {STATE['users'][username]['credits']}")
    except:
        bot.send_message(cid, "❌ Invalid number. Operation cancelled.")

# ─── BACKGROUND TASKS ─────────────────────────────────────────────────────
def run_bot():
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Telegram Bot error: {e}")
            time.sleep(3)

def periodic_cleanup():
    """Clean expired codes every 5 minutes"""
    while True:
        time.sleep(300)
        try:
            clean_expired_codes()
            print("🧹 Cleaned expired codes")
        except Exception as e:
            print(f"Cleanup error: {e}")

# Start background threads
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()

# ─── ERROR HANDLERS ──────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

# ─── MAIN ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("🚀 GLORY BOT PRO Server Starting...")
    print(f"📁 Data directory: {os.path.abspath(DATA_DIR)}")
    print(f"💾 State file: {os.path.abspath(STATE_FILE)}")
    print(f"👥 Users loaded: {len(STATE.get('users', {}))}")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
