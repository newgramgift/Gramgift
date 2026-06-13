from flask import Flask, jsonify, request, render_template
import random

app = Flask(__name__)

# Mock Database
USERS_DB = {
    "user_1024": {
        "username": "AnimeFan_99",
        "balance": 0.4,
        "invites": 5,
        "prediction_count": 12
    },
    "user_2048": {
        "username": "Zenith_Crypto",
        "balance": 5.2,
        "invites": 12,
        "prediction_count": 45
    }
}

@app.route('/')
def home():
    return render_template('index.html')

# API: Get User Status & Verification
@app.route('/api/user-status', methods=['GET'])
def get_status():
    user_id = request.args.get('user_id', 'user_1024')
    user = USERS_DB.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
        
    return jsonify({
        "username": user["username"],
        "balance": user["balance"],
        "invites": user["invites"],
        "is_locked": user["invites"] < 5
    })

# API: Core Game Logic (Predict)
@app.route('/api/predict', methods=['POST'])
def make_prediction():
    data = request.json
    user_id = data.get('user_id')
    prediction = data.get('prediction') # 'UP' or 'DOWN'
    duration = int(data.get('duration', 30))
    
    user = USERS_DB.get(user_id)
    if not user:
        return jsonify({"message": "Authentication failed"}), 400
        
    if user["invites"] < 5:
        return jsonify({"message": "Please invite 5 friends first!"}), 403

    # Simulation Outcome
    win = random.choice([True, False])
    
    if win:
        reward = 0.1
        user["balance"] += reward
        return jsonify({
            "status": "success",
            "message": f"Awesome! Your prediction was right. The price changed after {duration}s. Reward: +0.1 Gram"
        })
    else:
        return jsonify({
            "status": "fail",
            "message": f"Oops! Better luck next time. The price went the opposite way."
        })

# API: Competitive Leaderboard
@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    sorted_users = sorted(USERS_DB.values(), key=lambda x: x['balance'], reverse=True)
    
    leaderboard_data = []
    for user in sorted_users:
        leaderboard_data.append({
            "username": user["username"],
            "score": round(user["balance"], 2)
        })
        
    return jsonify(leaderboard_data)

# API: Handle Viral Referrals
@app.route('/api/referral', methods=['POST'])
def register_referral():
    data = request.json
    referrer_id = data.get('referrer_id')
    
    if referrer_id in USERS_DB:
        USERS_DB[referrer_id]["invites"] += 1
        USERS_DB[referrer_id]["balance"] += 0.2
        return jsonify({"message": "Referral recorded successfully! +0.2 Gram credited."})
        
    return jsonify({"message": "Invalid referral code"}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)
