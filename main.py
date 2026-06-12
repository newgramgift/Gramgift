import os
import time
import asyncio
import httpx
import random
from fastapi import FastAPI, Request
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

# --- Database (In-Memory) ---
TOTAL_POOL = 5000.0
cached_ton_price_usd = 5.25  # Default fallback price
withdrawal_requests = {}
USERS = {}
APPROVED_WITHDRAWALS = [
    {"name": "Arsam", "amount": 2.4},
    {"name": "Mahan", "amount": 1.8},
    {"name": "Sina", "amount": 4.5}
]
CHANNELS = {}

# --- Crash Game State ---
crash_game = {
    "status": "waiting",  # waiting, flying, crashed
    "multiplier": 1.00,
    "time_left": 5.0,
    "crash_point": 1.00
}
crash_bets = {}  # user_id -> {"amount": float, "cashed_out": bool, "profit": float}

# --- Admin FSM States ---
class AdminConfig(StatesGroup):
    waiting_for_channel = State()
    waiting_for_reward = State()
    waiting_for_type = State()

class AdminRemove(StatesGroup):
    waiting_for_channel = State()

class AdminBroadcast(StatesGroup):
    waiting_for_message = State()

# --- Background Loops ---
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
    global crash_game, crash_bets
    while True:
        # 1. Waiting Phase
        crash_game["status"] = "waiting"
        crash_bets.clear()
        for i in range(50, 0, -1):
            crash_game["time_left"] = i / 10.0
            await asyncio.sleep(0.1)
        
        # 2. Calculate Crash Point
        crash_point = max(1.00, 0.98 / random.random())
        if crash_point > 50.0: 
            crash_point = round(random.uniform(10.0, 50.0), 2)
        if random.random() < 0.07: 
            crash_point = 1.00  # 7% instant crash chance
        
        crash_game["crash_point"] = round(crash_point, 2)
        crash_game["status"] = "flying"
        crash_game["multiplier"] = 1.00
        
        # 3. Flying Phase
        while crash_game["multiplier"] < crash_game["crash_point"]:
            await asyncio.sleep(0.1)
            step = 0.01 * (crash_game["multiplier"] ** 0.85)
            crash_game["multiplier"] = round(crash_game["multiplier"] + step, 2)
            if crash_game["multiplier"] >= crash_game["crash_point"]:
                crash_game["multiplier"] = crash_game["crash_point"]
                break
                
        # 4. Crashed Phase
        crash_game["status"] = "crashed"
        await asyncio.sleep(4.0)

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

# --- Telegram Handlers ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = str(message.from_user.id)
    first_name = message.from_user.first_name

    if user_id not in USERS:
        referrer_id = command.args if (command.args and command.args != user_id) else None
        USERS[user_id] = {
            "first_name": first_name, 
            "balance": 0.0, 
            "invites": [], 
            "tasks": [], 
            "withdrawals": [], 
            "last_active": time.time(),
            "pending_referrer": referrer_id  
        }

    webapp_info = types.WebAppInfo(url=WEBAPP_URL)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Open GramGift App", web_app=webapp_info)]
    ])
    await message.answer(f"<b>Welcome to GramGift, {first_name}! 💎</b>\nClick below to access your dashboard, claim rewards, and play Pepe Crash.", reply_markup=keyboard)

# --- Admin Panel ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Task/Channel", callback_data="admin_add"), InlineKeyboardButton(text="➖ Remove Channel", callback_data="admin_remove_req")],
        [InlineKeyboardButton(text="📋 List Active Channels", callback_data="admin_list")],
        [InlineKeyboardButton(text="📢 Broadcast Campaign", callback_data="admin_broadcast")]
    ])
    await message.answer(f"🛠 <b>Admin Control Terminal</b>\n\n💰 Live Pool: <code>{TOTAL_POOL}</code> TON\n\n💡 <i>Pool Metrics Optimization:</i>\n<code>/pool set 1000</code>\n<code>/pool add 500</code>\n<code>/pool sub 250</code>", reply_markup=kb)

@dp.message(Command("pool"), F.from_user.id == ADMIN_ID)
async def admin_set_pool(message: types.Message, command: CommandObject):
    global TOTAL_POOL
    args = command.args
    if not args:
        await message.answer(f"💰 <b>Current Balance:</b> {TOTAL_POOL} TON")
        return
    try:
        parts = args.split()
        action, val = parts[0].lower(), float(parts[1])
        if action == "set": TOTAL_POOL = val
        elif action == "add": TOTAL_POOL += val
        elif action == "sub": TOTAL_POOL = max(0.0, TOTAL_POOL - val)
        await message.answer(f"✅ <b>Global Reward Pool Synchronized!</b>\nNew Live Aggregate: <b>{TOTAL_POOL} TON</b>")
    except:
        await message.answer("❌ <b>Formatting Error.</b> Syntax: <code>/pool set 1000</code>")

# --- Admin Custom Channel Add/Remove Workflow ---
@dp.callback_query(F.data == "admin_add", F.from_user.id == ADMIN_ID)
async def admin_add_ch_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminConfig.waiting_for_channel)
    await callback.message.answer("Enter target handle username (e.g., @mychannel):")
    await callback.answer()

@dp.message(AdminConfig.waiting_for_channel, F.from_user.id == ADMIN_ID)
async def admin_add_ch_name(message: types.Message, state: FSMContext):
    await state.update_data(channel=message.text.strip())
    await state.set_state(AdminConfig.waiting_for_reward)
    await message.answer("Enter allocated TON bounty reward payout:")

@dp.message(AdminConfig.waiting_for_reward, F.from_user.id == ADMIN_ID)
async def admin_add_ch_reward(message: types.Message, state: FSMContext):
    try:
        reward_amount = float(message.text.strip())
        await state.update_data(reward=reward_amount)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Force Join (Gatekeeper)", callback_data="type_force")],
            [InlineKeyboardButton(text="🎯 Native In-App Task List", callback_data="type_task")]
        ])
        await state.set_state(AdminConfig.waiting_for_type)
        await message.answer("Define operational interface placement Type:", reply_markup=kb)
    except ValueError:
        await message.answer("❌ Enter a valid number:")

@dp.callback_query(AdminConfig.waiting_for_type, F.from_user.id == ADMIN_ID)
async def admin_add_ch_type(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    CHANNELS[data['channel']] = {"reward": data['reward'], "is_force_join": (callback.data == "type_force")}
    await callback.message.edit_text(f"✅ Channel node {data['channel']} integrated successfully!")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "admin_remove_req", F.from_user.id == ADMIN_ID)
async def admin_remove_ch_start(callback: types.CallbackQuery, state: FSMContext):
    if not CHANNELS:
        await callback.answer("Active records map is empty!", show_alert=True)
        return
    await state.set_state(AdminRemove.waiting_for_channel)
    await callback.message.answer("Identify system target username for deletion:")
    await callback.answer()

@dp.message(AdminRemove.waiting_for_channel, F.from_user.id == ADMIN_ID)
async def admin_remove_ch_process(message: types.Message, state: FSMContext):
    channel_to_remove = message.text.strip()
    if channel_to_remove in CHANNELS:
        del CHANNELS[channel_to_remove]
        await message.answer(f"✅ Channel node {channel_to_remove} stripped.")
    else:
        await message.answer("❌ Entry not found.")
    await state.clear()

@dp.callback_query(F.data == "admin_list", F.from_user.id == ADMIN_ID)
async def admin_list_ch(callback: types.CallbackQuery):
    text = "📋 <b>Active Channels:</b>\n" + "\n".join([f"• {ch} | {d['reward']} TON | {'Force' if d['is_force_join'] else 'Task'}" for ch, d in CHANNELS.items()]) if CHANNELS else "No channels registered."
    await callback.message.answer(text)
    await callback.answer()

# --- Broadcast Engine ---
@dp.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminBroadcast.waiting_for_message)
    await callback.message.answer("📢 Send the message content you wish to distribute:")
    await callback.answer()

@dp.message(AdminBroadcast.waiting_for_message, F.from_user.id == ADMIN_ID)
async def confirm_broadcast(message: types.Message, state: FSMContext):
    await state.update_data(msg_id=message.message_id, chat_id=message.chat.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Dispatch", callback_data="confirm_broadcast")],
        [InlineKeyboardButton(text="❌ Abort", callback_data="cancel_broadcast")]
    ])
    await bot.copy_message(chat_id=message.chat.id, from_chat_id=message.chat.id, message_id=message.message_id, reply_markup=kb)

@dp.callback_query(F.data == "confirm_broadcast", F.from_user.id == ADMIN_ID)
async def do_broadcast(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id, chat_id = data.get("msg_id"), data.get("chat_id")
    await callback.message.edit_text("⏳ Broadcast transmission processing...")
    success, fail = 0, 0
    for uid in USERS.keys():
        try:
            await bot.copy_message(chat_id=int(uid), from_chat_id=chat_id, message_id=msg_id)
            success += 1
            await asyncio.sleep(0.05)
        except: 
            fail += 1
    await callback.message.answer(f"✅ Distribution finished!\nDelivered: {success}\nFailed: {fail}")
    await state.clear()

@dp.callback_query(F.data == "cancel_broadcast", F.from_user.id == ADMIN_ID)
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Broadcast canceled.")
    await state.clear()

# --- Withdrawal Flow Management ---
@dp.callback_query(F.data.startswith("approve_"))
async def approve_withdraw(callback: types.CallbackQuery):
    global TOTAL_POOL
    if callback.from_user.id != ADMIN_ID: return
    req_id = callback.data.replace("approve_", "")
    req = withdrawal_requests.pop(req_id, None)
    if req:
        amt, u_id = float(req['amount']), str(req['user_id'])
        TOTAL_POOL = max(0.0, TOTAL_POOL - amt)
        if u_id in USERS:
            for w in USERS[u_id].get("withdrawals", []):
                if w["id"] == req_id: w["status"] = "Approved"
        APPROVED_WITHDRAWALS.append({"name": USERS.get(u_id, {}).get("first_name", "User"), "amount": amt})
        try: 
            await bot.send_message(u_id, f"🎉 <b>Payout Approved:</b> {amt} TON has been systematically dispatched.")
        except: pass
        await callback.message.edit_text(callback.message.html_text + "\n\n<b>Status: ✅ Approved</b>", reply_markup=None)
    await callback.answer()

@dp.callback_query(F.data.startswith("reject_"))
async def reject_withdraw(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    req_id = callback.data.replace("reject_", "")
    req = withdrawal_requests.pop(req_id, None)
    if req:
        u_id = str(req['user_id'])
        if u_id in USERS:
            USERS[u_id]['balance'] += float(req['amount'])
            for w in USERS[u_id].get("withdrawals", []):
                if w["id"] == req_id: w["status"] = "Rejected"
        try: 
            await bot.send_message(u_id, f"❌ <b>Payout Rejected:</b> Payout of {req['amount']} TON was cancelled. Refunded.")
        except: pass
        await callback.message.edit_text(callback.message.html_text + "\n\n<b>Status: ❌ Rejected</b>", reply_markup=None)
    await callback.answer()

# --- FastAPI API Routing Endpoints ---
@app.get("/")
async def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/data")
async def get_live_data(user_id: str = None):
    if user_id and user_id in USERS: 
        USERS[user_id]["last_active"] = time.time()
    online_count = sum(1 for u in USERS.values() if time.time() - u.get("last_active", 0) < 30)
    return {
        "total_pool": TOTAL_POOL, 
        "ton_price": cached_ton_price_usd, 
        "online_count": max(1, online_count),
        "recent_payouts": APPROVED_WITHDRAWALS[-6:]
    }

@app.get("/api/mandatory_check/{user_id}")
async def mandatory_check(user_id: str):
    unjoined = await get_unjoined_channels(int(user_id))
    return {"unjoined": unjoined}

@app.get("/api/user/{user_id}")
async def get_user_data(user_id: str):
    if user_id not in USERS: 
        return {"balance": 0.0, "invite_count": 0, "invites": [], "withdrawals": []}
    
    # Anti-Fraud: Referrals validation triggers ONLY when invited user explicitly fires mini-app check sequence
    if USERS[user_id].get("pending_referrer"):
        ref_id = str(USERS[user_id]["pending_referrer"])
        first_name = USERS[user_id]["first_name"]
        if ref_id in USERS and ref_id != user_id:
            already_invited = any(inv["name"] == first_name for inv in USERS[ref_id]["invites"])
            if not already_invited:
                USERS[ref_id]["balance"] += 0.2
                USERS[ref_id]["invites"].append({"name": first_name, "reward": 0.2})
                try:
                    await bot.send_message(int(ref_id), f"🎉 User <b>{first_name}</b> active! <b>+0.2 TON</b> credited.")
                except: pass
        USERS[user_id]["pending_referrer"] = None
        
    user_tasks = USERS[user_id].get("tasks", [])
    has_new = any(ch for ch, d in CHANNELS.items() if not d["is_force_join"] and ch not in user_tasks)
    
    return {
        "balance": USERS[user_id]["balance"],
        "invites": USERS[user_id]["invites"],
        "invite_count": len(USERS[user_id]["invites"]),
        "withdrawals": USERS[user_id].get("withdrawals", [])[::-1],
        "has_new_tasks": has_new
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
    if channel not in CHANNELS or u_id not in USERS or channel in USERS[u_id].get("tasks", []):
        return {"status": "error", "message": "Verification invalid or already processed."}
    try:
        status = await bot.get_chat_member(chat_id=channel, user_id=int(u_id))
        if status.status in ['left', 'kicked']: 
            return {"status": "error", "message": "Subscription verification failed."}
        reward = CHANNELS[channel]["reward"]
        USERS[u_id]["balance"] += reward
        USERS[u_id]["tasks"].append(channel)
        return {"status": "success", "reward": reward, "new_balance": USERS[u_id]["balance"]}
    except:
        return {"status": "error", "message": "System channel lookup error."}

@app.get("/api/leaderboard")
async def get_leaderboard():
    sorted_users = sorted(USERS.items(), key=lambda x: len(x[1]["invites"]), reverse=True)[:50]
    return {
        "leaders": [{"name": u[1]["first_name"], "invites": len(u[1]["invites"]), "reward": len(u[1]["invites"])*0.2} for u in sorted_users if len(u[1]["invites"]) > 0],
        "recent": APPROVED_WITHDRAWALS[-10:]
    }

@app.post("/api/withdraw")
async def api_withdraw(request: Request):
    global TOTAL_POOL
    data = await request.json()
    u_id, amt = str(data['user_id']), float(data['amount'])
    if u_id not in USERS or USERS[u_id]['balance'] < amt or amt < 1.0: 
        return {"status": "error", "message": "Insufficient active balance setup value."}
    if TOTAL_POOL < amt:
        return {"status": "error", "message": "Global reward pool exhausted. Await refilling."}
    req_id = f"req_{int(time.time()*1000)}"
    USERS[u_id]['balance'] -= amt
    w_data = {"id": req_id, "amount": amt, "address": data['address'], "status": "Pending", "date": time.strftime("%Y-%m-%d %H:%M")}
    USERS[u_id].setdefault("withdrawals", []).append(w_data)
    withdrawal_requests[req_id] = {"user_id": u_id, "amount": amt, "address": data['address']}
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{req_id}"), 
        InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{req_id}")
    ]])
    await bot.send_message(ADMIN_ID, f"🔔 <b>New Withdrawal Event Requested:</b>\n👤 User: <code>{u_id}</code>\n💰 Amount: {amt} TON\n👛 Wallet: <code>{data['address']}</code>", reply_markup=kb)
    return {"status": "success"}

# --- Crash Engine Endpoints Integration ---
@app.get("/api/crash/state")
async def get_crash_state(user_id: str = None):
    user_bet = crash_bets.get(user_id) if user_id else None
    return {
        "status": crash_game["status"],
        "multiplier": crash_game["multiplier"],
        "time_left": crash_game["time_left"],
        "user_bet": user_bet
    }

@app.post("/api/crash/bet")
async def place_crash_bet(request: Request):
    data = await request.json()
    u_id, amount = str(data['user_id']), float(data['amount'])
    if crash_game["status"] != "waiting":
        return {"status": "error", "message": "Game already in progress!"}
    if u_id not in USERS or USERS[u_id]['balance'] < amount or amount <= 0:
        return {"status": "error", "message": "Insufficient token balance allocation!"}
    USERS[u_id]['balance'] -= amount
    crash_bets[u_id] = {"amount": amount, "cashed_out": False, "profit": 0.0}
    return {"status": "success", "new_balance": USERS[u_id]['balance']}

@app.post("/api/crash/cashout")
async def cashout_crash(request: Request):
    data = await request.json()
    u_id = str(data['user_id'])
    if crash_game["status"] != "flying":
        return {"status": "error", "message": "Cannot cash out now!"}
    if u_id not in crash_bets or crash_bets[u_id]["cashed_out"]:
        return {"status": "error", "message": "No active bet context found!"}
    multiplier = crash_game["multiplier"]
    profit = round(crash_bets[u_id]["amount"] * multiplier, 2)
    crash_bets[u_id]["cashed_out"] = True
    crash_bets[u_id]["profit"] = profit
    USERS[u_id]['balance'] = round(USERS[u_id]['balance'] + profit, 2)
    return {"status": "success", "profit": profit, "multiplier": multiplier, "new_balance": USERS[u_id]['balance']}

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(update_ton_price())
    asyncio.create_task(run_crash_game())
    asyncio.create_task(dp.start_polling(bot))
