import os
import time
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# --- Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-app-name.up.railway.app") 
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()

# --- Database (In-Memory Secure State) ---
USERS = {}  
# Schema: user_id -> {"first_name": str, "balance": float, "invites": [], "tasks": [], "predictions": {}, "exact_wins": 0, "total_wins": 0, "last_active": float}
MATCHES = {}  
# Schema: match_id -> {"date": str, "team_a": str, "team_b": str, "start_time": int (UTC timestamp), "desc": str, "score_a": int, "score_b": int, "settled": bool}
CHANNELS = {}  
# Schema: channel -> {"reward": float, "is_force_join": bool}

# --- FSM States for Admin ---
class AdminMatch(StatesGroup):
    waiting_for_date = State()
    waiting_for_teams = State()
    waiting_for_time = State()
    waiting_for_desc = State()

class AdminAddBalls(StatesGroup):
    waiting_for_uid = State()
    waiting_for_amount = State()

class AdminBroadcast(StatesGroup):
    waiting_for_message = State()

class AdminConfig(StatesGroup):
    waiting_for_channel = State()
    waiting_for_reward = State()
    waiting_for_type = State()

class AdminRemove(StatesGroup):
    waiting_for_channel = State()

# --- Helpers ---
async def send_webapp_button(user_id: int):
    webapp_info = types.WebAppInfo(url=WEBAPP_URL)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚽️ Enter World Cup Mini-App", web_app=webapp_info)]
    ])
    await bot.send_message(
        user_id, 
        "<b>💥 Welcome to the World Cup Prediction Challenge!</b>\n\n"
        "Collect balls, predict matches accurately, climb the leaderboard, and claim massive TON rewards!", 
        reply_markup=keyboard
    )

async def get_unjoined_channels(user_id: int):
    unjoined = []
    for ch, data in CHANNELS.items():
        if data["is_force_join"]:
            try:
                status = await bot.get_chat_member(chat_id=ch, user_id=user_id)
                if status.status in ['left', 'kicked']: 
                    unjoined.append(ch)
            except: 
                unjoined.append(ch)
    return unjoined

# --- Telegram Bot Handlers ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = str(message.from_user.id)
    first_name = message.from_user.first_name

    if user_id not in USERS:
        referrer_id = command.args if (command.args and command.args != user_id) else None
        USERS[user_id] = {
            "first_name": first_name, 
            "balance": 5.0,  # Starting free balls
            "invites": [], 
            "tasks": [], 
            "predictions": {}, 
            "exact_wins": 0,
            "total_wins": 0,
            "last_active": time.time(),
            "pending_referrer": referrer_id  
        }

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="I am not a robot 🤖", callback_data="captcha_passed")]
    ])
    await message.answer("<b>Security Verification:</b>\nPlease verify that you are a human to prevent fake accounts.", reply_markup=keyboard)

@dp.callback_query(F.data == "captcha_passed")
@dp.callback_query(F.data == "check_join")
async def process_check_join(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    first_name = callback.from_user.first_name
    
    unjoined = await get_unjoined_channels(callback.from_user.id)
    if not unjoined:
        if callback.data == "check_join": 
            await callback.message.delete()
        else: 
            await callback.message.edit_reply_markup(reply_markup=None)
            
        # --- Secure Referral Payout (1 Ball per Active Referral) ---
        if user_id in USERS and USERS[user_id].get("pending_referrer"):
            ref_id = USERS[user_id]["pending_referrer"]
            if ref_id in USERS:
                already_invited = any(inv["name"] == first_name for inv in USERS[ref_id]["invites"])
                if not already_invited:
                    USERS[ref_id]["balance"] += 1.0
                    USERS[ref_id]["invites"].append({"name": first_name, "reward": 1.0})
                    try:
                        await bot.send_message(
                            int(ref_id), 
                            f"🎉 <b>{first_name}</b> joined using your link! <b>+1.0 ⚽️</b> has been credited to your balance."
                        )
                    except:
                        pass
            USERS[user_id]["pending_referrer"] = None
            
        await send_webapp_button(callback.from_user.id)
    else:
        keyboard_buttons = [[InlineKeyboardButton(text=f"Join {ch}", url=f"https://t.me/{ch.replace('@', '')}")] for ch in unjoined]
        keyboard_buttons.append([InlineKeyboardButton(text="✅ Check Membership Status", callback_data="check_join")])
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        if callback.data == "check_join":
            await callback.answer("You have not joined all required channels yet!", show_alert=True)
        else:
            await callback.message.edit_text("⚠️ <b>To unlock the app, you must join our sponsor channels:</b>", reply_markup=kb)

# --- Admin Panel Commands ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Add New Match", callback_data="admin_add_match"), InlineKeyboardButton(text="💳 Credit User Balls", callback_data="admin_credit_user")],
        [InlineKeyboardButton(text="➕ Add Channel Task", callback_data="admin_add_ch"), InlineKeyboardButton(text="➖ Remove Channel Task", callback_data="admin_remove_ch")],
        [InlineKeyboardButton(text="📢 Broadcast Message", callback_data="admin_broadcast")]
    ])
    await message.answer(
        "🛠 <b>World Cup Mini-App Admin Dashboard</b>\n\n"
        "<b>Match Settlement Command Format:</b>\n"
        "Use this command to settle a match and distribute rewards automatically:\n"
        "<code>/settle [MatchID] [ScoreA] [ScoreB]</code>\n"
        "Example: <code>/settle 1 3 1</code>", reply_markup=kb
    )

# --- Admin Add Match Flow ---
@dp.callback_query(F.data == "admin_add_match", F.from_user.id == ADMIN_ID)
async def match_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminMatch.waiting_for_date)
    await callback.message.answer("📅 Enter match date (Format Example: June 12 or YYYY-MM-DD):")
    await callback.answer()

@dp.message(AdminMatch.waiting_for_date, F.from_user.id == ADMIN_ID)
async def match_add_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text.strip())
    await state.set_state(AdminMatch.waiting_for_teams)
    await message.answer("⚔️ Enter teams with flag emojis (Example: 🏴󠁧󠁢󠁥󠁮󠁧󠁿 England - 🇫🇷 France):")

@dp.message(AdminMatch.waiting_for_teams, F.from_user.id == ADMIN_ID)
async def match_add_teams(message: types.Message, state: FSMContext):
    teams = message.text.split("-")
    if len(teams) != 2:
        await message.answer("❌ Invalid format. Please use: Team A - Team B")
        return
    await state.update_data(team_a=teams[0].strip(), team_b=teams[1].strip())
    await state.set_state(AdminMatch.waiting_for_time)
    await message.answer("⏰ Enter match start time as a UTC Unix Timestamp (Example: 1781258400):")

@dp.message(AdminMatch.waiting_for_time, F.from_user.id == ADMIN_ID)
async def match_add_time(message: types.Message, state: FSMContext):
    try:
        timestamp = int(message.text.strip())
        await state.update_data(start_time=timestamp)
        await state.set_state(AdminMatch.waiting_for_desc)
        await message.answer("📝 Enter extra details/description (or type 'none' if empty):")
    except ValueError:
        await message.answer("❌ Error! Please enter a valid integer Unix timestamp.")

@dp.message(AdminMatch.waiting_for_desc, F.from_user.id == ADMIN_ID)
async def match_add_desc(message: types.Message, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    
    match_id = str(len(MATCHES) + 1)
    MATCHES[match_id] = {
        "date": data["date"],
        "team_a": data["team_a"],
        "team_b": data["team_b"],
        "start_time": data["start_time"],
        "desc": "" if desc.lower() == "none" else desc,
        "score_a": -1,
        "score_b": -1,
        "settled": False
    }
    
    await message.answer(f"✅ Match registered successfully!\n<b>Match ID:</b> {match_id}\n🏆 {data['team_a']} VS {data['team_b']}")
    await state.clear()

# --- Settle Match Command ---
@dp.message(Command("settle"), F.from_user.id == ADMIN_ID)
async def settle_match(message: types.Message, command: CommandObject):
    try:
        args = command.args.split()
        match_id = args[0]
        act_score_a = int(args[1])
        act_score_b = int(args[2])
        
        if match_id not in MATCHES or MATCHES[match_id]["settled"]:
            await message.answer("❌ Match not found or already settled.")
            return
            
        match = MATCHES[match_id]
        match["score_a"] = act_score_a
        match["score_b"] = act_score_b
        match["settled"] = True
        
        actual_outcome = 1 if act_score_a > act_score_b else (-1 if act_score_b > act_score_a else 0)
        
        processed_users = 0
        for u_id, user in USERS.items():
            if "predictions" in user and match_id in user["predictions"]:
                pred = user["predictions"][match_id]
                if pred.get("status") != "pending":
                    continue
                    
                pred_a = pred["score_a"]
                pred_b = pred["score_b"]
                wager = pred["amount"]
                
                pred_outcome = 1 if pred_a > pred_b else (-1 if pred_b > pred_a else 0)
                
                if pred_a == act_score_a and pred_b == act_score_b:
                    # Exact Score (2x Payout)
                    payout = wager * 2.0
                    user["balance"] += payout
                    user["exact_wins"] += 1
                    user["total_wins"] += 1
                    pred["status"] = "exact"
                elif pred_outcome == actual_outcome:
                    # Correct Outcome / Goal Difference (1.5x Payout)
                    payout = wager * 1.5
                    user["balance"] += payout
                    user["total_wins"] += 1
                    pred["status"] = "outcome"
                else:
                    # Wrong Prediction (0x - Lost)
                    pred["status"] = "lost"
                processed_users += 1
                
        await message.answer(f"🏁 Match {match_id} settled with result ({act_score_a} - {act_score_b}).\nRewards calculated and processed for {processed_users} users.")
    except Exception as e:
        await message.answer("❌ Format Error! Valid syntax: <code>/settle [MatchID] [ScoreA] [ScoreB]</code>")

# --- Shop / Manual Credit System ---
@dp.callback_query(F.data == "admin_credit_user", F.from_user.id == ADMIN_ID)
async def admin_credit_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddBalls.waiting_for_uid)
    await callback.message.answer("👤 Enter the User ID to credit:")
    await callback.answer()

@dp.message(AdminAddBalls.waiting_for_uid, F.from_user.id == ADMIN_ID)
async def admin_credit_uid(message: types.Message, state: FSMContext):
    await state.update_data(target_uid=message.text.strip())
    await state.set_state(AdminAddBalls.waiting_for_amount)
    await message.answer("⚽️ Enter amount of balls to add:")

@dp.message(AdminAddBalls.waiting_for_amount, F.from_user.id == ADMIN_ID)
async def admin_credit_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        data = await state.get_data()
        uid = data["target_uid"]
        
        if uid in USERS:
            USERS[uid]["balance"] += amount
            await message.answer(f"✅ User {uid} balance credited with {amount} ⚽️.")
            try:
                await bot.send_message(int(uid), f"💳 <b>Account Credited Successfully!</b>\n{amount} ⚽️ has been manually added to your balance by support.")
            except:
                pass
        else:
            await message.answer("❌ User not found in the database.")
        await state.clear()
    except ValueError:
        await message.answer("❌ Invalid number amount entered.")

# --- Admin Channels Management ---
@dp.callback_query(F.data == "admin_add_ch", F.from_user.id == ADMIN_ID)
async def admin_add_ch_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminConfig.waiting_for_channel)
    await callback.message.answer("Enter channel username (Example: @mychannel):")
    await callback.answer()

@dp.message(AdminConfig.waiting_for_channel, F.from_user.id == ADMIN_ID)
async def admin_add_ch_name(message: types.Message, state: FSMContext):
    await state.update_data(channel=message.text.strip())
    await state.set_state(AdminConfig.waiting_for_reward)
    await message.answer("Enter balls reward amount for joining:")

@dp.message(AdminConfig.waiting_for_reward, F.from_user.id == ADMIN_ID)
async def admin_add_ch_reward(message: types.Message, state: FSMContext):
    try:
        reward = float(message.text.strip())
        await state.update_data(reward=reward)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Force-Join on Bot Start", callback_data="type_force")],
            [InlineKeyboardButton(text="🎯 Display in Tasks Tab", callback_data="type_task")]
        ])
        await state.set_state(AdminConfig.waiting_for_type)
        await message.answer("Select channel layout integration type:", reply_markup=kb)
    except:
        await message.answer("❌ Reward must be a valid float number.")

@dp.callback_query(AdminConfig.waiting_for_type, F.from_user.id == ADMIN_ID)
async def admin_add_ch_type(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    CHANNELS[data['channel']] = {"reward": data['reward'], "is_force_join": (callback.data == "type_force")}
    await callback.message.edit_text(f"✅ Channel {data['channel']} successfully configured.")
    await state.clear()

@dp.callback_query(F.data == "admin_remove_ch", F.from_user.id == ADMIN_ID)
async def admin_remove_ch_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminRemove.waiting_for_channel)
    await callback.message.answer("Enter channel username to delete:")
    await callback.answer()

@dp.message(AdminRemove.waiting_for_channel, F.from_user.id == ADMIN_ID)
async def admin_remove_ch_proc(message: types.Message, state: FSMContext):
    ch = message.text.strip()
    if ch in CHANNELS:
        del CHANNELS[ch]
        await message.answer(f"✅ Channel {ch} removed.")
    else:
        await message.answer("❌ Channel not found.")
    await state.clear()

# --- Broadcast Logic ---
@dp.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminBroadcast.waiting_for_message)
    await callback.message.answer("📢 Send the broadcast message content:")
    await callback.answer()

@dp.message(AdminBroadcast.waiting_for_message, F.from_user.id == ADMIN_ID)
async def do_broadcast(message: types.Message, state: FSMContext):
    success, fail = 0, 0
    for uid in USERS.keys():
        try:
            await bot.send_message(int(uid), message.text)
            success += 1
            await asyncio.sleep(0.04)
        except: 
            fail += 1
    await message.answer(f"✅ Broadcast finished.\nSuccess: {success}\nFailed: {fail}")
    await state.clear()

# --- FastAPI Rest API Endpoints (Anti-Tamper Design) ---
@app.get("/")
async def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/data")
async def get_live_data(user_id: str = None):
    if user_id and user_id in USERS: 
        USERS[user_id]["last_active"] = time.time()
    online_count = sum(1 for u in USERS.values() if time.time() - u.get("last_active", 0) < 45)
    return {"online_count": max(1, online_count)}

@app.get("/api/user/{user_id}")
async def get_user_data(user_id: str):
    if user_id not in USERS: 
        return {"balance": 0.0, "invites": [], "invite_count": 0, "predictions": {}, "has_new_tasks": False}
    
    user_tasks = USERS[user_id].get("tasks", [])
    has_new = any(ch for ch, d in CHANNELS.items() if not d["is_force_join"] and ch not in user_tasks)
    
    return {
        "balance": USERS[user_id]["balance"],
        "invites": USERS[user_id]["invites"],
        "invite_count": len(USERS[user_id]["invites"]),
        "predictions": USERS[user_id].get("predictions", {}),
        "has_new_tasks": has_new
    }

@app.get("/api/matches")
async def get_matches():
    return {"matches": MATCHES}

@app.post("/api/predict")
async def api_predict(request: Request):
    data = await request.json()
    u_id = str(data.get('user_id'))
    match_id = str(data.get('match_id'))
    score_a = int(data.get('score_a'))
    score_b = int(data.get('score_b'))
    wager = float(data.get('amount'))
    
    if u_id not in USERS:
        raise HTTPException(status_code=400, detail="User sequence invalid")
    if match_id not in MATCHES:
        raise HTTPException(status_code=400, detail="Match not registered")
        
    match = MATCHES[match_id]
    
    if time.time() >= match["start_time"]:
        return {"status": "error", "message": "Prediction time has closed for this match."}
    if USERS[u_id]["balance"] < wager or wager <= 0:
        return {"status": "error", "message": "Insufficient balls ⚽️ balance to register wager."}
    if match["settled"]:
        return {"status": "error", "message": "This match has already ended and settled."}
        
    # Secure server-side calculation and lock-in
    USERS[u_id]["balance"] -= wager
    USERS[u_id].setdefault("predictions", {})[match_id] = {
        "score_a": score_a,
        "score_b": score_b,
        "amount": wager,
        "status": "pending",
        "timestamp": time.time()
    }
    return {"status": "success", "new_balance": USERS[u_id]["balance"]}

@app.get("/api/tasks/{user_id}")
async def get_user_tasks(user_id: str):
    user_tasks = USERS.get(user_id, {}).get("tasks", [])
    active_tasks = [{"channel": ch, "reward": d["reward"]} for ch, d in CHANNELS.items() if not d["is_force_join"] and ch not in user_tasks]
    return {"tasks": active_tasks}

@app.post("/api/check_task")
async def api_check_task(request: Request):
    data = await request.json()
    u_id, channel = str(data['user_id']), data['channel']
    
    if channel not in CHANNELS or u_id not in USERS: 
        return {"status": "error", "message": "Structural authorization failure encountered."}
    if channel in USERS[u_id].get("tasks", []): 
        return {"status": "error", "message": "This task has already been completed."}
        
    try:
        status = await bot.get_chat_member(chat_id=channel, user_id=int(u_id))
        if status.status in ['left', 'kicked']: 
            return {"status": "error", "message": "You have not joined the channel yet."}
            
        reward = CHANNELS[channel]["reward"]
        USERS[u_id]["balance"] += reward
        USERS[u_id]["tasks"].append(channel)
        return {"status": "success", "reward": reward, "new_balance": USERS[u_id]["balance"]}
    except: 
        return {"status": "error", "message": "Error validating Telegram tracking status."}

@app.get("/api/leaderboard")
async def get_leaderboard():
    sorted_predictors = sorted(USERS.items(), key=lambda x: (x[1].get("exact_wins", 0), x[1].get("total_wins", 0)), reverse=True)[:50]
    sorted_referrers = sorted(USERS.items(), key=lambda x: len(x[1].get("invites", [])), reverse=True)[:50]
    
    leaders_list = []
    for idx, u in enumerate(sorted_predictors):
        leaders_list.append({
            "name": u[1]["first_name"],
            "exact": u[1].get("exact_wins", 0),
            "total": u[1].get("total_wins", 0)
        })
        
    ref_list = []
    for u in sorted_referrers:
        ref_list.append({
            "name": u[1]["first_name"],
            "count": len(u[1].get("invites", []))
        })
        
    return {"predictors": leaders_list, "referrers": ref_list}

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(dp.start_polling(bot))
