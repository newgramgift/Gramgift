import os
import time
import asyncio
import httpx
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
cached_ton_price_usd = 0.0
withdrawal_requests = {}

USERS = {}
APPROVED_WITHDRAWALS = [] 
CHANNELS = {}

# --- Admin FSM States ---
class AdminConfig(StatesGroup):
    waiting_for_channel = State()
    waiting_for_reward = State()
    waiting_for_type = State()

class AdminRemove(StatesGroup):
    waiting_for_channel = State()

class AdminBroadcast(StatesGroup):
    waiting_for_message = State()

# --- Helpers ---
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="I am human 🤖", callback_data="captcha_passed")]
    ])
    await message.answer("<b>GramGift Security Portal:</b>\nPlease verify that you are a human to prevent automated bot entries.", reply_markup=keyboard)

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
            
        # --- Referral Logic (Unlimited) ---
        if user_id in USERS and USERS[user_id].get("pending_referrer"):
            ref_id = USERS[user_id]["pending_referrer"]
            if ref_id in USERS:
                already_invited = any(inv["name"] == first_name for inv in USERS[ref_id]["invites"])
                if not already_invited:
                    USERS[ref_id]["balance"] += 0.2
                    USERS[ref_id]["invites"].append({"name": first_name, "reward": 0.2})
                    try:
                        await bot.send_message(
                            int(ref_id), 
                            f"🎉 User <b>{first_name}</b> joined via your link! <b>+0.2 TON</b> credited to your balance."
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
            await callback.answer("Verification failed! You haven't joined all required channels yet.", show_alert=True)
        else:
            await callback.message.edit_text("⚠️ <b>Please join our mandatory partner channels to continue:</b>", reply_markup=kb)

# --- Admin Panel Handlers ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Task/Channel", callback_data="admin_add"), InlineKeyboardButton(text="➖ Remove Channel", callback_data="admin_remove_req")],
        [InlineKeyboardButton(text="📋 List Active Channels", callback_data="admin_list")],
        [InlineKeyboardButton(text="📢 Broadcast Campaign", callback_data="admin_broadcast")]
    ])
    await message.answer("🛠 <b>Admin Control Terminal</b>\n\n💡 <i>Pool Pool Configuration Management:</i>\n<code>/pool set 1000</code> (Reset absolute pool balance)\n<code>/pool add 500</code> (Inject rewards into current pool)\n<code>/pool sub 250</code> (Deduct metrics from current pool)", reply_markup=kb)

# --- Admin Pool Command ---
@dp.message(Command("pool"), F.from_user.id == ADMIN_ID)
async def admin_set_pool(message: types.Message, command: CommandObject):
    global TOTAL_POOL
    args = command.args
    if not args:
        await message.answer(f"💰 <b>Current Reserve:</b> {TOTAL_POOL} TON\n\n<b>Syntax Commands:</b>\n<code>/pool set 5000</code>\n<code>/pool add 100</code>\n<code>/pool sub 50</code>")
        return
    try:
        parts = args.split()
        action = parts[0].lower()
        val = float(parts[1])
        if action == "set":
            TOTAL_POOL = val
        elif action == "add":
            TOTAL_POOL += val
        elif action == "sub":
            TOTAL_POOL = max(0.0, TOTAL_POOL - val)
        await message.answer(f"✅ <b>Global Reward Pool Synchronized!</b>\nNew Live Aggregate: <b>{TOTAL_POOL} TON</b>")
    except:
        await message.answer("❌ <b>Formatting Error:</b> Invalid numeric inputs. Syntax: <code>/pool set 1000</code>")

# --- Broadcast Logic ---
@dp.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminBroadcast.waiting_for_message)
    await callback.message.answer("📢 Send the message content you wish to distribute to all users:")
    await callback.answer()

@dp.message(AdminBroadcast.waiting_for_message, F.from_user.id == ADMIN_ID)
async def confirm_broadcast(message: types.Message, state: FSMContext):
    await state.update_data(msg_id=message.message_id, chat_id=message.chat.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Dispatch to All", callback_data="confirm_broadcast")],
        [InlineKeyboardButton(text="❌ Abort Broadcast", callback_data="cancel_broadcast")]
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
            
    await callback.message.answer(f"✅ Distribution finished!\nDelivered: {success}\nFailed/Blocked: {fail}")
    await state.clear()

@dp.callback_query(F.data == "cancel_broadcast", F.from_user.id == ADMIN_ID)
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Broadcast canceled.")
    await state.clear()

# --- Admin Channels Add Logic ---
@dp.callback_query(F.data == "admin_add", F.from_user.id == ADMIN_ID)
async def admin_add_ch_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminConfig.waiting_for_channel)
    await callback.message.answer("Enter target handle username (e.g., @mychannel):")
    await callback.answer()

@dp.message(AdminConfig.waiting_for_channel, F.from_user.id == ADMIN_ID)
async def admin_add_ch_name(message: types.Message, state: FSMContext):
    await state.update_data(channel=message.text.strip())
    await state.set_state(AdminConfig.waiting_for_reward)
    await message.answer("Enter allocated TON bounty reward payout per validation:")

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
        await message.answer("Define operational interface logic placement Type:", reply_markup=kb)
    except ValueError:
        await message.answer("❌ Operational error: Enter a valid floating point number:")

@dp.callback_query(AdminConfig.waiting_for_type, F.from_user.id == ADMIN_ID)
async def admin_add_ch_type(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    CHANNELS[data['channel']] = {"reward": data['reward'], "is_force_join": (callback.data == "type_force")}
    await callback.message.edit_text(f"✅ Channel node {data['channel']} integrated successfully!")
    await state.clear()
    await callback.answer()

# --- Admin Channels Remove Logic ---
@dp.callback_query(F.data == "admin_remove_req", F.from_user.id == ADMIN_ID)
async def admin_remove_ch_start(callback: types.CallbackQuery, state: FSMContext):
    if not CHANNELS:
        await callback.answer("Active records map is empty!", show_alert=True)
        return
    await state.set_state(AdminRemove.waiting_for_channel)
    await callback.message.answer("Identify system target username for deletion (e.g., @mychannel):")
    await callback.answer()

@dp.message(AdminRemove.waiting_for_channel, F.from_user.id == ADMIN_ID)
async def admin_remove_ch_process(message: types.Message, state: FSMContext):
    channel_to_remove = message.text.strip()
    if channel_to_remove in CHANNELS:
        del CHANNELS[channel_to_remove]
        await message.answer(f"✅ Channel node {channel_to_remove} stripped from runtime indexes.")
    else:
        await message.answer(f"❌ Entry not found: {channel_to_remove} lacks active indexing.")
    await state.clear()

@dp.callback_query(F.data == "admin_list", F.from_user.id == ADMIN_ID)
async def admin_list_ch(callback: types.CallbackQuery):
    text = "📋 <b>Active Channel Configurations:</b>\n" + "\n".join([f"• {ch} | {d['reward']} TON" for ch, d in CHANNELS.items()]) if CHANNELS else "No channels registered."
    await callback.message.answer(text)
    await callback.answer()

# --- WITHDRAWALS APPROVE HANDLER ---
@dp.callback_query(F.data.startswith("approve_"))
async def approve_withdraw(callback: types.CallbackQuery):
    global TOTAL_POOL
    if callback.from_user.id != ADMIN_ID: 
        return
    
    req_id = callback.data.replace("approve_", "")
    req = withdrawal_requests.pop(req_id, None)
    
    if req:
        amt, u_id = float(req['amount']), str(req['user_id'])
        TOTAL_POOL = max(0.0, TOTAL_POOL - amt)
        
        if u_id in USERS:
            for w in USERS[u_id].get("withdrawals", []):
                if w["id"] == req_id: 
                    w["status"] = "Approved" 
            
        APPROVED_WITHDRAWALS.append({"name": USERS.get(u_id, {}).get("first_name", "User"), "amount": amt})
        try: 
            await bot.send_message(u_id, f"🎉 <b>Payout Approved:</b> {amt} TON has been systematically dispatched to your address.")
        except: 
            pass
        await callback.message.edit_text(callback.message.html_text + "\n\n<b>Status: ✅ Approved</b>", reply_markup=None)
    else:
        await callback.message.edit_text(callback.message.html_text + "\n\n<b>Status: ✅ Approved (Processed)</b>", reply_markup=None)
        
    await callback.answer() 

# --- WITHDRAWALS REJECT HANDLER ---
@dp.callback_query(F.data.startswith("reject_"))
async def reject_withdraw(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: 
        return
    
    req_id = callback.data.replace("reject_", "")
    req = withdrawal_requests.pop(req_id, None)
    
    if req:
        u_id = str(req['user_id'])
        if u_id in USERS:
            USERS[u_id]['balance'] += float(req['amount'])
            for w in USERS[u_id].get("withdrawals", []):
                if w["id"] == req_id: 
                    w["status"] = "Rejected" 
                
        try: 
            await bot.send_message(u_id, f"❌ <b>Payout Rejected:</b> Your withdrawal request of {req['amount']} TON was cancelled. Balance refunded.")
        except: 
            pass
        await callback.message.edit_text(callback.message.html_text + "\n\n<b>Status: ❌ Rejected</b>", reply_markup=None)
    else:
        await callback.message.edit_text(callback.message.html_text + "\n\n<b>Status: ❌ Rejected (Processed)</b>", reply_markup=None)
        
    await callback.answer()

# --- FastAPI Endpoints ---
@app.get("/")
async def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/data")
async def get_live_data(user_id: str = None):
    if user_id and user_id in USERS: 
        USERS[user_id]["last_active"] = time.time()
    online_count = sum(1 for u in USERS.values() if time.time() - u.get("last_active", 0) < 30)
    
    return {"total_pool": TOTAL_POOL, "ton_price": cached_ton_price_usd, "online_count": max(1, online_count)}

@app.get("/api/user/{user_id}")
async def get_user_data(user_id: str):
    if user_id not in USERS: 
        return {"balance": 0.0, "invites": [], "invite_count": 0, "withdrawals": [], "has_new_tasks": False}
    
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
    
    if channel not in CHANNELS: 
        return {"status": "error", "message": "Configuration element missing."}
    if u_id not in USERS: 
        return {"status": "error", "message": "User sequence identification failure."}
    if channel in USERS[u_id].get("tasks", []): 
        return {"status": "error", "message": "Task already verified."}
        
    try:
        status = await bot.get_chat_member(chat_id=channel, user_id=int(u_id))
        if status.status in ['left', 'kicked']: 
            return {"status": "error", "message": "You are not indexed as an active subscriber to this node."}
            
        reward = CHANNELS[channel]["reward"]
        USERS[u_id]["balance"] += reward
        USERS[u_id]["tasks"].append(channel)
        return {"status": "success", "reward": reward, "new_balance": USERS[u_id]["balance"]}
    except: 
        return {"status": "error", "message": "System integrity check error."}

@app.get("/api/leaderboard")
async def get_leaderboard():
    # Top 100 entries mapping index
    sorted_users = sorted(USERS.items(), key=lambda x: len(x[1]["invites"]), reverse=True)[:100]
    return {
        "leaders": [{"name": u[1]["first_name"], "invites": len(u[1]["invites"]), "reward": len(u[1]["invites"])*0.2} for u in sorted_users if len(u[1]["invites"]) > 0],
        "recent": APPROVED_WITHDRAWALS[-10:] 
    }

@app.post("/api/withdraw")
async def api_withdraw(request: Request):
    global TOTAL_POOL
    data = await request.json()
    u_id, amt = str(data['user_id']), float(data['amount'])
    
    if u_id not in USERS or USERS[u_id]['balance'] < amt: 
        return {"status": "error", "message": "Insufficient account liquid value"}
        
    if TOTAL_POOL < amt:
        return {"status": "error", "message": "Global reward distribution pool exhausted. Please await admin refill."}
        
    req_id = f"req_{int(time.time()*1000)}" 
    USERS[u_id]['balance'] -= amt
    
    w_data = {"id": req_id, "amount": amt, "address": data['address'], "status": "Pending", "date": time.strftime("%Y-%m-%d %H:%M")}
    USERS[u_id].setdefault("withdrawals", []).append(w_data)
    
    data['user_id'] = u_id
    withdrawal_requests[req_id] = data
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{req_id}"), 
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{req_id}")
        ]
    ])
    
    await bot.send_message(
        ADMIN_ID, 
        f"🔔 <b>New Withdrawal Event Requested:</b>\n👤 User: <code>{u_id}</code>\n💰 Amount: {amt} TON\n👛 Wallet: <code>{data['address']}</code>", 
        reply_markup=kb
    )
    return {"status": "success"}

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(update_ton_price())
    asyncio.create_task(dp.start_polling(bot))
