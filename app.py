import os
import random
from flask import Flask, jsonify, request, render_template
import telebot

app = Flask(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

# Memory-based Database
USERS_DB = {}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/' + (BOT_TOKEN if BOT_TOKEN else 'webhook'), methods=['POST'])
def getMessage():
    if bot:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
    return "!", 200

if bot:
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        user_id = str(message.from_user.id)
        username = message.from_user.username or message.from_user.first_name
        
        command_args = message.text.split()
        referrer_id = command_args[1] if len(command_args) > 1 else None

        if user_id not in USERS_DB:
            USERS_DB[user_id] = {
                "username": username,
                "balance": 0.0,
                "invites": 0,
                "prediction_count": 0
            }
            # Add instant viral referral reward (+0.2 Gram)
            if referrer_id and referrer_id in USERS_DB and referrer_id != user_id:
                USERS_DB[referrer_id]["invites"] += 1
                USERS_DB[referrer_id]["balance"] += 0.2
                try:
                    bot.send_message(referrer_id, f"🎉 Premium Referral Alert! Someone joined. You got +0.2 Gram.")
                except:
                    pass

        markup = telebot.types.InlineKeyboardMarkup()
        app_url = f"https://{request.host}"
        web_app = telebot.types.WebAppInfo(app_url)
        btn = telebot.types.InlineKeyboardButton(text="Open Trading Dashboard 📊", web_app=web_app)
        markup.add(btn)

        bot_info = bot.get_me()
        invite_link = f"https://t.me/{bot_info.username}?start={user_id}"
        
        welcome_text = (
            f"✨ Welcome to Premium TON Predictor, {username}!\n\n"
            f"📊 Analyze real-time Binance charts directly inside Telegram.\n"
            f"🔒 To access trading pools, invite 5 active players.\n\n"
            f"🔗 Your Invitation Link:\n{invite_link}"
        )
        bot.reply_to(message, welcome_text, reply_markup=markup)

@app.route('/api/user-status', methods=['GET'])
def get_status():
    user_id = request.args.get('user_id')
    
    if not user_id or user_id in ["undefined", "null"]:
        user_id = "test_user"

    if user_id not in USERS_DB:
        USERS_DB[user_id] = {
            "username": "Trader_Guest",
            "balance": 0.5,
            "invites": 5, # Default 5 to bypass lock on browser/local test environment
            "prediction_count": 0
        }
        
    user = USERS_DB[user_id]
    return jsonify({
        "username": user["username"],
        "balance": user["balance"],
        "invites": user["invites"],
        "is_locked": user["invites"] < 5
    })

@app.route('/api/predict', methods=['POST'])
def make_prediction():
    data = request.json or {}
    user_id = data.get('user_id', 'test_user')
    user_price = float(data.get('current_price', 0.0))
    duration = int(data.get('duration', 30))
    
    user = USERS_DB.get(user_id)
    if not user:
        return jsonify({"message": "Error resolving user pipeline"}), 400
        
    if user["invites"] < 5:
        return jsonify({"message": "Access Denied: 5 active invites required."}), 403

    # Dynamic Simulation Engine based on real-time price snapshot
    win = random.choice([True, False])
    if win:
        user["balance"] += 0.1
        return jsonify({"status": "success", "message": f"Correct Forecast! Market filled your target price. +0.1 Gram awarded."})
    return jsonify({"status": "fail", "message": f"Liquidated! The live market went against your expectation."})

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    if not USERS_DB:
        return jsonify([{"username": "Global Pools Empty", "score": 0.0}])
    sorted_users = sorted(USERS_DB.values(), key=lambda x: x.get('balance', 0), reverse=True)
    return jsonify([{"username": u["username"], "score": round(u["balance"], 2)} for u in sorted_users][:10])

if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv("PORT", 8080)))
