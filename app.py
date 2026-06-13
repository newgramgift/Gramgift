import os
import random
import hmac
import hashlib
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# دریافت توکن ربات از تنظیمات سرور Railway
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_FALLBACK_TOKEN_FOR_LOCAL_TEST")

# دیتابیس فرضی
USERS_DB = {
    "12345678": {  # شناسه عددی تلگرام کاربر
        "username": "AnimeFan_99",
        "balance": 0.4,
        "invites": 5,
        "prediction_count": 12
    }
}

@app.route('/')
def home():
    return render_template('index.html')

# تابع امنیت تلگرام: بررسی اینکه درخواست حتماً از داخل ربات تلگرام شما آمده است
def verify_telegram_data(init_data):
    if not BOT_TOKEN:
        return False
    # در محیط واقعی، اینجا باید پارامترهای init_data را با hash سانیتایز و تایید کنید.
    # برای سادگی فعلاً فرض می‌کنیم تایید شده است یا در حالت تست هستیم.
    return True

@app.route('/api/user-status', methods=['GET'])
def get_status():
    user_id = request.args.get('user_id')
    user = USERS_DB.get(user_id)
    
    if not user:
        # اگر کاربر جدید بود، او را ثبت‌نام کن
        user_id = user_id if user_id else "guest"
        USERS_DB[user_id] = {"username": f"Player_{user_id[:4]}", "balance": 0.0, "invites": 0, "prediction_count": 0}
        user = USERS_DB[user_id]
        
    return jsonify({
        "username": user["username"],
        "balance": user["balance"],
        "invites": user["invites"],
        "is_locked": user["invites"] < 5
    })

@app.route('/api/predict', methods=['POST'])
def make_prediction():
    data = request.json
    user_id = data.get('user_id')
    prediction = data.get('prediction')
    duration = int(data.get('duration', 30))
    
    user = USERS_DB.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 400
        
    if user["invites"] < 5:
        return jsonify({"message": "Please invite 5 friends first!"}), 403

    win = random.choice([True, False])
    if win:
        reward = 0.1
        user["balance"] += reward
        return jsonify({"status": "success", "message": f"Awesome! +0.1 Gram earned!"})
    else:
        return jsonify({"status": "fail", "message": "Oops! Wrong prediction."})

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    sorted_users = sorted(USERS_DB.values(), key=lambda x: x['balance'], reverse=True)
    return jsonify([{"username": u["username"], "score": round(u["balance"], 2)} for u in sorted_users])

if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))
