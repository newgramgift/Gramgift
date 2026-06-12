import os
import time
import asyncio
import httpx
import random
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-app-name.up.railway.app") 
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Databases (In-Memory) ---
TOTAL_POOL = 5000.0
cached_ton_price_usd = 0.0
withdrawal_requests = {}
USERS = {}
APPROVED_WITHDRAWALS = [] 
CHANNELS = {}

# --- Crash Game Structural State with Saved History Records ---
CRASH_GAME = {
    "status": "waiting",  # waiting, flying, crashed
    "multiplier": 1.0,
    "time_left": 5.0,
    "bets": {},  # user_id -> {"amount": float, "cashed_out": bool, "profit": float}
    "history": [1.24, 3.52, 1.85, 12.40, 2.15, 0.98, 5.20]  # Initial values seed
}

class AdminConfig(StatesGroup):
    waiting_for_channel = State()
    waiting_for_reward = State()
    waiting_for_type = State()

class AdminRemove(StatesGroup):
    waiting_for_channel = State()

class AdminBroadcast(StatesGroup):
    waiting_for_message = State()

async def update_ton_price():
    global cached_ton_price_usd
    while True:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd')
                cached_ton_price_usd = res.json()['the-open-network']['usd']
        except:
            pass
        await asyncio.sleep(300)

async def run_crash_game():
    """Background engine managing game math calculations and tracking variables."""
    while True:
        if CRASH_GAME["status"] == "waiting":
            CRASH_GAME["time_left"] -= 0.1
            if CRASH_GAME["time_left"] <= 0:
                CRASH_GAME["status"] = "flying"
                CRASH_GAME["multiplier"] = 1.0
            await asyncio.sleep(0.1)

        elif CRASH_GAME["status"] == "flying":
            CRASH_GAME["multiplier"] += 0.006 * CRASH_GAME["multiplier"]
            
            # Simulated outcome generator logic algorithms (~1.6% crash vulnerability threshold index)
            if random.random() < 0.016 or CRASH_GAME["multiplier"] > 80.0:
                CRASH_GAME["status"] = "crashed"
                CRASH_GAME["time_left"] = 4.0
                
                # Dynamic array validation storage mechanics
                CRASH_GAME["history"].append(round(CRASH_GAME["multiplier"], 2))
                if len(CRASH_GAME["history"]) > 8:
                    CRASH_GAME["history"].pop(0) # Keep history bar perfectly clean and responsive
            await asyncio.sleep(0.1)

        elif CRASH_GAME["status"] == "crashed":
            CRASH_GAME["time_left"] -= 0.1
            if CRASH_GAME["time_left"] <= 0:
                CRASH_GAME["status"] = "waiting"
                CRASH_GAME["time_left"] = 4.5
                CRASH_GAME["bets"] = {}
            await asyncio.sleep(0.1)

async def send_webapp_button(user_id: int):
    webapp_info = types.WebAppInfo(url=WEBAPP_URL)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Enter GramGift App", web_app=webapp_info)]
    ])
    await bot.send_message(user_id, "<b>Verification Successful! 🎉</b>\nClick below to access your dashboard.", reply_markup=keyboard)

async def get_unjoined_channels(user_id: int):
    unjoined = []
    for ch, data in CHANNELS.items():
        if data["is_force_join"]:
            try:
                status = await bot.get_chat_member(chat_id=ch, user_id=user_id)
                if status.status in ['left', 'kicked']: unjoined.append(ch)
            except: unjoined.append(ch)
    return unjoined

# --- Telegram Handlers ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = str(message.from_user.id)
    first_name = message.from_user.first_name

    if user_id not in USERS:
        referrer_id = command.args if (command.args and command.args != user_id) else None
        USERS[user_id] = {
            "first_name": first_name, "balance": 0.0, "invites": [], 
            "tasks": [], "withdrawals": [], "last_active": time.time(),
            "pending_referrer": referrer_id  
        }

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="I am human 🤖", callback_data="captcha_passed")]
    ])
    await message.answer("<b>GramGift Security Portal:</b>\nPlease verify that you are a human.", reply_markup=keyboard)

@dp.callback_query(F.data == "captcha_passed")
@dp.callback_query(F.data == "check_join")
async def process_check_join(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    first_name = callback.from_user.first_name
    
    unjoined = await get_unjoined_channels(callback.from_user.id)
    if not unjoined:
        if callback.data == "check_join": await callback.message.delete()
        else: await callback.message.edit_reply_markup(reply_markup=None)
            
        if user_id in USERS and USERS[user_id].get("pending_referrer"):
            ref_id = str(USERS[user_id]["pending_referrer"])
            if ref_id in USERS:
                already_invited = any(inv["name"] == first_name for inv in USERS[ref_id]["invites"])
                if not already_invited:
                    USERS[ref_id]["balance"] += 0.20
                    USERS[ref_id]["invites"].append({"name": first_name, "reward": 0.20})
                    try: await bot.send_message(int(ref_id), f"🎉 User <b>{first_name}</b> joined! <b>+0.2 TON</b>.")
                    except: pass
            USERS[user_id]["pending_referrer"] = None
        await send_webapp_button(callback.from_user.id)
    else:
        keyboard_buttons = [[InlineKeyboardButton(text=f"Join {ch}", url=f"https://t.me/{ch.replace('@', '')}")] for ch in unjoined]
        keyboard_buttons.append([InlineKeyboardButton(text="✅ Check Membership Status", callback_data="check_join")])
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        if callback.data == "check_join":
            await callback.answer("Verification failed! join all required channels.", show_alert=True)
        else:
            await callback.message.edit_text("⚠️ <b>Please join our mandatory partner channels to continue:</b>", reply_markup=kb)

# --- Admin Modules ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Task", callback_data="admin_add"), InlineKeyboardButton(text="➖ Remove Task", callback_data="admin_remove_req")],
        [InlineKeyboardButton(text="📋 List Active Channels", callback_data="admin_list")],
        [InlineKeyboardButton(text="📢 Broadcast Campaign", callback_data="admin_broadcast")]
    ])
    await message.answer("🛠 <b>Admin Management Console Panel</b>", reply_markup=kb)

@dp.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminBroadcast.waiting_for_message)
    await callback.message.answer("📢 Send message body content:")
    await callback.answer()

@dp.message(AdminBroadcast.waiting_for_message, F.from_user.id == ADMIN_ID)
async def confirm_broadcast(message: types.Message, state: FSMContext):
    await state.update_data(msg_id=message.message_id, chat_id=message.chat.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Dispatch", callback_data="confirm_broadcast"), InlineKeyboardButton(text="❌ Abort", callback_data="cancel_broadcast")]
    ])
    await bot.copy_message(chat_id=message.chat.id, from_chat_id=message.chat.id, message_id=message.message_id, reply_markup=kb)

@dp.callback_query(F.data == "confirm_broadcast", F.from_user.id == ADMIN_ID)
async def do_broadcast(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id, chat_id = data.get("msg_id"), data.get("chat_id")
    success = 0
    for uid in USERS.keys():
        try:
            await bot.copy_message(chat_id=int(uid), from_chat_id=chat_id, message_id=msg_id)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await callback.message.answer(f"✅ Finished. Delivered to: {success} users.")
    await state.clear()

@dp.callback_query(F.data == "admin_add", F.from_user.id == ADMIN_ID)
async def admin_add_ch_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminConfig.waiting_for_channel)
    await callback.message.answer("Enter target handle username (e.g., @mychannel):")
    await callback.answer()

@dp.message(AdminConfig.waiting_for_channel, F.from_user.id == ADMIN_ID)
async def admin_add_ch_name(message: types.Message, state: FSMContext):
    await state.update_data(channel=message.text.strip())
    await state.set_state(AdminConfig.waiting_for_reward)
    await message.answer("Enter validation reward TON balance amount:")

@dp.message(AdminConfig.waiting_for_reward, F.from_user.id == ADMIN_ID)
async def admin_add_ch_reward(message: types.Message, state: FSMContext):
    try:
        reward_amount = float(message.text.strip())
        await state.update_data(reward=reward_amount)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Force Join Gate", callback_data="type_force")],
            [InlineKeyboardButton(text="🎯 Native Earn List Task", callback_data="type_task")]
        ])
        await state.set_state(AdminConfig.waiting_for_type)
        await message.answer("Select configuration task layout visibility module placement:", reply_markup=kb)
    except: await message.answer("Error. Enter real numeric floats.")

@dp.callback_query(AdminConfig.waiting_for_type, F.from_user.id == ADMIN_ID)
async def admin_add_ch_type(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    CHANNELS[data['channel']] = {"reward": data['reward'], "is_force_join": (callback.data == "type_force")}
    await callback.message.edit_text(f"✅ Integrated: {data['channel']}")
    await state.clear()

# --- Payout Approval Triggers ---
@dp.callback_query(F.data.startswith("approve_"))
async def approve_withdraw(callback: types.CallbackQuery):
    global TOTAL_POOL
    req_id = callback.data.replace("approve_", "")
    req = withdrawal_requests.pop(req_id, None)
    if req:
        amt, u_id = float(req['amount']), str(req['user_id'])
        TOTAL_POOL = max(0.0, TOTAL_POOL - amt)
        if u_id in USERS:
            for w in USERS[u_id].get("withdrawals", []):
                if w["id"] == req_id: w["status"] = "Approved" 
        APPROVED_WITHDRAWALS.append({"name": USERS.get(u_id, {}).get("first_name", "User"), "amount": amt})
        try: await bot.send_message(u_id, f"🎉 <b>Payout Approved:</b> {amt} TON sent.")
        except: pass
    await callback.message.edit_text(callback.message.html_text + "\n\n<b>Status: ✅ Approved</b>", reply_markup=None)

@dp.callback_query(F.data.startswith("reject_"))
async def reject_withdraw(callback: types.CallbackQuery):
    req_id = callback.data.replace("reject_", "")
    req = withdrawal_requests.pop(req_id, None)
    if req:
        u_id = str(req['user_id'])
        if u_id in USERS:
            USERS[u_id]['balance'] += float(req['amount'])
            for w in USERS[u_id].get("withdrawals", []):
                if w["id"] == req_id: w["status"] = "Rejected" 
        try: await bot.send_message(u_id, f"❌ <b>Withdrawal Rejected.</b> Balance refunded.")
        except: pass
    await callback.message.edit_text(callback.message.html_text + "\n\n<b>Status: ❌ Rejected</b>", reply_markup=None)

# --- REST FastAPI Routing Endpoints ---
@app.get("/")
async def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/data")
async def get_live_data(user_id: str = None):
    if user_id and user_id in USERS: USERS[user_id]["last_active"] = time.time()
    online_count = sum(1 for u in USERS.values() if time.time() - u.get("last_active", 0) < 35)
    return {"total_pool": TOTAL_POOL, "ton_price": cached_ton_price_usd, "online_count": max(1, online_count)}

@app.get("/api/user/{user_id}")
async def get_user_data(user_id: str):
    if user_id not in USERS: return {"balance": 0.0, "invites": [], "invite_count": 0, "withdrawals": []}
    return {
        "balance": USERS[user_id]["balance"],
        "invites": USERS[user_id]["invites"],
        "invite_count": len(USERS[user_id]["invites"]),
        "withdrawals": USERS[user_id].get("withdrawals", [])[::-1]
    }

@app.get("/api/tasks/{user_id}")
async def get_user_tasks(user_id: str):
    user_tasks = USERS.get(user_id, {}).get("tasks", [])
    active_tasks = [{"channel": ch, "reward": d["reward"]} for ch, d in CHANNELS.items() if not d["is_force_join"] and ch not in user_tasks]
    return {"tasks": active_tasks}

@app.post("/api/check_task")
async def api_check_task(request: Request):
    data = await request.json()
    u_id, channel = str(data['user_id']), data['channel']
    status = await bot.get_chat_member(chat_id=channel, user_id=int(u_id))
    if status.status in ['left', 'kicked']: return {"status": "error", "message": "Membership check tracking verification failure."}
    
    reward = CHANNELS[channel]["reward"]
    USERS[u_id]["balance"] += reward
    USERS[u_id]["tasks"].append(channel)
    return {"status": "success", "reward": reward}

@app.get("/api/leaderboard")
async def get_leaderboard():
    sorted_users = sorted(USERS.items(), key=lambda x: len(x[1]["invites"]), reverse=True)[:50]
    return {"leaders": [{"name": u[1]["first_name"], "invites": len(u[1]["invites"]), "reward": len(u[1]["invites"])*0.2} for u in sorted_users if len(u[1]["invites"]) > 0]}

@app.post("/api/withdraw")
async def api_withdraw(request: Request):
    data = await request.json()
    u_id, amt = str(data['user_id']), float(data['amount'])
    if USERS[u_id]['balance'] < amt: return {"status": "error", "message": "Insufficient resources balance."}
    
    req_id = f"req_{int(time.time()*1000)}"
    USERS[u_id]['balance'] -= amt
    w_data = {"id": req_id, "amount": amt, "address": data['address'], "status": "Pending", "date": time.strftime("%Y-%m-%d %H:%M")}
    USERS[u_id].setdefault("withdrawals", []).append(w_data)
    
    withdrawal_requests[req_id] = {"user_id": u_id, "amount": amt, "address": data['address']}
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{req_id}"), InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{req_id}")]])
    await bot.send_message(ADMIN_ID, f"🔔 <b>New Payout Request:</b>\nUser: <code>{u_id}</code>\nAmount: {amt} TON", reply_markup=kb)
    return {"status": "success"}

# --- OPTIMIZED CRASH SYNC ENGINE ROUTERS ---
@app.get("/api/crash/state")
async def crash_state(user_id: str = None):
    return {
        "status": CRASH_GAME["status"],
        "multiplier": CRASH_GAME["multiplier"],
        "time_left": max(0.0, CRASH_GAME["time_left"]),
        "user_bet": CRASH_GAME["bets"].get(user_id) if user_id else None,
        "history": CRASH_GAME["history"] # Dispatches full tracking history values to layout
    }

@app.post("/api/crash/bet")
async def crash_bet(request: Request):
    data = await request.json()
    u_id = str(data.get("user_id"))
    amount = float(data.get("amount", 0))
    if CRASH_GAME["status"] != "waiting" or USERS[u_id]["balance"] < amount:
        return {"status": "error", "message": "Bet registration denied processing constraints."}
    
    USERS[u_id]["balance"] -= amount
    CRASH_GAME["bets"][u_id] = {"amount": amount, "cashed_out": False, "profit": 0.0}
    return {"status": "success"}

@app.post("/api/crash/cashout")
async def crash_cashout(request: Request):
    data = await request.json()
    u_id = str(data.get("user_id"))
    if CRASH_GAME["status"] != "flying" or u_id not in CRASH_GAME["bets"]:
        return {"status": "error", "message": "Action denied."}
        
    bet = CRASH_GAME["bets"][u_id]
    if bet["cashed_out"]: return {"status": "error", "message": "Already claimed asset."}
    
    profit = bet["amount"] * CRASH_GAME["multiplier"]
    bet["cashed_out"] = True
    bet["profit"] = profit
    USERS[u_id]["balance"] += profit
    return {"status": "success", "profit": profit}

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(update_ton_price())
    asyncio.create_task(run_crash_game())
    asyncio.create_task(dp.start_polling(bot))
