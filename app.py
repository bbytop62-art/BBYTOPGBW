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
    "siteLogo": "⚡"   # Simple emoji, no base64
}

STATE_FILE = "state_db.json"

def load_state():
    global STATE
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # Update current state keys
                for k, v in loaded.items():
                    STATE[k] = v
            print("Successfully loaded state from file.")
        except Exception as e:
            print(f"Error loading state from file: {e}")
    else:
        # Save initial state
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(STATE, f, indent=4)
            print("Created initial state file.")
        except Exception as e:
            print(f"Error creating initial state file: {e}")

def save_state_to_file():
    try:
        tmp_file = STATE_FILE + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(STATE, f, indent=4)
        os.replace(tmp_file, STATE_FILE)
    except Exception as e:
        print(f"Error saving state to file: {e}")

# Load state on startup
load_state()

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
                            bot['members'] = res.get('current_members', res.get('current_members', bot.get('members', 5)))
                            
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
    return render_template('index.html')

@app.route('/video.mp4')
def serve_video():
    # यह app.py वाले फोल्डर से सीधा video.mp4 को फ्रंटएंड में भेज देगा
    return send_from_directory('.', 'video.mp4')

@app.route('/uploads/<filename>')
def serve_uploads(filename):
    return send_from_directory('uploads', filename)

# ─── PUBLIC API ─────────────────────────────────────────────────────────────


@app.route('/api/get-private-data', methods=['GET'])
def get_private_data():
    # Return full state (frontend will use it)
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

    # Save user to state
    STATE['users'][username] = {
        "username": username,
        "password": password,
        "email": email,
        "credits": 0,
        "role": "user",
        "banned": False
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
    return jsonify({"success": True, "role": user['role']})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({"success": True})

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

            return jsonify({
                "verified": True,
                "transaction_id": data["transaction_id"],
                "utr": data["utr"],
                "sender": data["sender_name"],
                "amount": data["amount"],
                "payment_time": data["payment_time_ist"]
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
                            incoming_bot['members'] = res.get('total_members', res.get('current_members', incoming_bot.get('members', 5)))
                            print(f"Newly approved bot {bid} immediately updated from API. initialGlory={current_glory}")

        # Admin or staff can modify all allowed keys, including 'users'
        allowed_keys = ['users', 'orders', 'bots', 'coupons', 'redeemedBy', 'pricePacks', 'announcement', 'maintenance', 'siteLogo']
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
OWNERS = [8703570301, 8726156194]
bot = telebot.TeleBot(BOT_TOKEN, threaded=False) 

def check_sub(user_id):
    # Added @glorybothelp to the list
    channels = ["@keshvexffmethod", "@glorybotpro", "@glorybothelp"]
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
    markup.add(InlineKeyboardButton("Join Channel 1", url="https://t.me/keshvexffmethod"))
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
        r = requests.get(
            FAMPAY_QR_API,
            params={
                "upi": UPI_ID,
                "amount": amt
            },
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
    bot.send_message(
        cid,
        "⏳ Waiting for auto verification...\nPlease don't close the bot."
    )

    threading.Thread(
        target=wait_for_payment_verification,
        args=(cid, order_id, amt),
        daemon=True
    ).start()

def wait_for_payment_verification(cid, order_id, amt):
    attempts = 0
    while attempts < 60: # Poll for 5 mins
        try:
            verify = requests.get(
                FAMPAY_VERIFY_API,
                params={
                    "order_id": order_id,
                    "api_key": FAMPAY_API_KEY
                },
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
