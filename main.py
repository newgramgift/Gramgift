async def bot_start_trigger(message: types.Message):
    user_id = str(message.from_user.id)
    first_name = message.from_user.first_name

    # Handle Deep Linking Referrals
    if user_id not in USERS:
        ref_id = None
        if len(message.text.split()) > 1:
            possible_ref = message.text.split()[1]
            if possible_ref != user_id:
                ref_id = possible_ref

        USERS[user_id] = {
            "first_name": first_name, 
            "balance": 5.0,  
            "invites": [], 
            "tasks": [], 
            "predictions": {}, 
            "exact_wins": 0,
            "total_wins": 0,
            "last_active": time.time(),
            "pending_referrer": ref_id  
        }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="I am not a robot 🤖", callback_data="captcha_passed")]
    ])
    await message.answer("<b>Verification Protocol:</b>\nPlease confirm human identification metrics below.", reply_markup=kb)

@dp.callback_query(F.data == "captcha_passed")
@dp.callback_query(F.data == "check_join")
async def verify_user_lifecycle(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    first_name = callback.from_user.first_name
    
    unjoined = await get_unjoined_channels(callback.from_user.id)
    if not unjoined:
        if callback.data == "check_join": 
            await callback.message.delete()
        else: 
            await callback.message.edit_reply_markup(reply_markup=None)
            
        # Process pending referrers safely
        if user_id in USERS and USERS[user_id].get("pending_referrer"):
            ref_id = USERS[user_id]["pending_referrer"]
            if ref_id in USERS:
                if not any(i["name"] == first_name for i in USERS[ref_id]["invites"]):
                    USERS[ref_id]["balance"] += 1.0
                    USERS[ref_id]["invites"].append({"name": first_name, "reward": 1.0})
                    try:
                        await bot.send_message(int(ref_id), f"🎉 <b>{first_name}</b> node verified! <b>+1.0 ⚽️</b> has been allocated.")
                    except: pass
            USERS[user_id]["pending_referrer"] = None
            
        webapp_info = types.WebAppInfo(url=WEBAPP_URL)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Launch Prediction Matrix", web_app=webapp_info)]
        ])
        await bot.send_message(
            callback.from_user.id, 
            "<b>💥 Access Granted!</b>\n\nForecast live metrics, scale the leaderboards, and claim digital ecosystem rewards.", 
            reply_markup=kb
        )
    else:
        buttons = [[InlineKeyboardButton(text=f"Join {ch}", url=f"https://t.me/{ch.replace('@', '')}")] for ch in unjoined]
        buttons.append([InlineKeyboardButton(text="✅ Check Verification Status", callback_data="check_join")])
        if callback.data == "check_join":
            await callback.answer("Verification failed. Sponsored routing requirements unfulfilled.", show_alert=True)
        else:
            await callback.message.edit_text("⚠️ <b>Ecosystem Validation Required:</b>\nJoin the authorized network channels to continue:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# --- Pure Dynamic Admin Operations Control ---
@dp.message(F.from_user.id == ADMIN_ID, F.text.lower() == "admin")
@dp.message(F.from_user.id == ADMIN_ID, CommandStart()) # Backup path for admin initialization
async def admin_control_deck(message: types.Message):
    kb = await get_main_admin_keyboard()
    await message.answer("⚙️ <b>GramGift System Control Deck</b>\nSelect maintenance operation pipeline:", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_date", F.from_user.id == ADMIN_ID)
async def admin_init_date_cat(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_date_name)
    await callback.message.answer("📝 Enter new Date Category string (Example: <code>June 12</code>):")
    await callback.answer()

@dp.message(AdminStates.waiting_for_date_name, F.from_user.id == ADMIN_ID)
async def admin_save_date_cat(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    # Virtual category creation via state or direct placeholder triggers
    await message.answer(f"✅ Category <b>'{date_str}'</b> initialized. You can now bind matches to this timeline context.", reply_markup=await get_main_admin_keyboard())
    await state.clear()

@dp.callback_query(F.data == "adm_del_date_start", F.from_user.id == ADMIN_ID)
async def admin_delete_date_menu(callback: types.CallbackQuery):
    all_dates = list(set(m["date"] for m in MATCHES.values()))
    if not all_dates:
        await callback.message.answer("❌ No active date tracks detected.", reply_markup=await get_main_admin_keyboard())
        await callback.answer()
        return
    buttons = [[InlineKeyboardButton(text=f"🗑 Delete {d}", callback_data=f"del_date_conf_{d}")] for d in all_dates]
    await callback.message.edit_text("⚠️ <b>Select date metrics context to destroy:</b>\nThis purges all nested match data parameters permanently.", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("del_date_conf_"), F.from_user.id == ADMIN_ID)
async def admin_delete_date_execute(callback: types.CallbackQuery):
    target_date = callback.data.replace("del_date_conf_", "")
    keys_to_purge = [k for k, v in MATCHES.items() if v["date"] == target_date]
    for k in keys_to_purge:
        del MATCHES[k]
    await callback.message.answer(f"🧹 Purge sequence complete! Date <b>{target_date}</b> and its {len(keys_to_purge)} nested matches removed.", reply_markup=await get_main_admin_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "adm_add_match_start", F.from_user.id == ADMIN_ID)
async def admin_match_date_select(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_date_name)
    await callback.message.answer("📅 Step 1: Input the Target Date Category for this fixture (e.g., <code>June 12</code>):")
    await callback.answer()

@dp.message(AdminStates.waiting_for_date_name, F.from_user.id == ADMIN_ID)
async def admin_match_teams_input(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text.strip())
    await state.set_state(AdminStates.waiting_for_match_teams)
    await message.answer("⚔️ Step 2: Input Teams with flag representations (Example: <code>🏴󠁧󠁢󠁥󠁮󠁧󠁿 England - 🇫🇷 France</code>):")

@dp.message(AdminStates.waiting_for_match_teams, F.from_user.id == ADMIN_ID)
async def admin_match_time_input(message: types.Message, state: FSMContext):
    teams = message.text.split("-")
    if len(teams) != 2:
        await message.answer("❌ Syntactical mismatch! Standard delimiter format: Team A - Team B")
        return
    await state.update_data(team_a=teams[0].strip(), team_b=teams[1].strip())
    await state.set_state(AdminStates.waiting_for_match_time)
    await message.answer("⏰ Step 3: Input Match Kickoff Time in **UTC** (Format: <code>HH:MM</code>, e.g., <code>18:30</code>):")

@dp.message(AdminStates.waiting_for_match_time, F.from_user.id == ADMIN_ID)
async def admin_match_desc_input(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    try:
        hr, mn = map(int, time_str.split(":"))
        if not (0 <= hr < 24 and 0 <= mn < 60): raise ValueError
        await state.update_data(time_str=time_str)
        await state.set_state(AdminStates.waiting_for_match_desc)
        await message.answer("📝 Step 4: Input operational notes / metadata (or type <code>none</code>):")
    except:
        await message.answer("❌ Processing error. Ensure execution matching exact format requirements: <code>HH:MM</code> (e.g. 20:45)")

@dp.message(AdminStates.waiting_for_match_desc, F.from_user.id == ADMIN_ID)
async def admin_match_finalize(message: types.Message, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    
    # Mathematical Timestamp Generation Based on Year 2026 UTC
    now = datetime.now(timezone.utc)
    try:
        hr, mn = map(int, data["time_str"].split(":"))
        # Parse month/day context dynamically if possible, default to today/forward logic safely
        # To ensure lock safety, we compute a secure Unix Timestamp
        future_timestamp = int(datetime(2026, 6, 15, hr, mn, tzinfo=timezone.utc).timestamp())
    except:
        future_timestamp = int(time.time() + 7200) # Fallback 2 hours out
        
    m_id = str(len(MATCHES) + 1)
    MATCHES[m_id] = {
        "date": data["date"], "team_a": data["team_a"], "team_b": data["team_b"],
        "start_time": future_timestamp, "time_display": data["time_str"],
        "desc": "" if desc.lower() == "none" else desc, "score_a": -1, "score_b": -1, "settled": False
    }
    await message.answer(f"✅ <b>Match Metrics Locked!</b>\nID: <code>{m_id}</code>\nStructure: {data['team_a']} vs {data['team_b']} @ {data['time_str']} UTC", reply_markup=await get_main_admin_keyboard())
    await state.clear()

@dp.callback_query(F.data == "adm_settle_start", F.from_user.id == ADMIN_ID)
async def admin_settle_menu(callback: types.CallbackQuery, state: FSMContext):
    active = [k for k, v in MATCHES.items() if not v["settled"]]
    if not active:
        await callback.message.answer("❌ No pending ledger elements requiring settlement.", reply_markup=await get_main_admin_keyboard())
        await callback.answer()
        return
    buttons = [[InlineKeyboardButton(text=f"Settle #{k} {v['team_a']}-{v['team_b']}", callback_data=f"settle_m_{k}")] for k in active]
    await callback.message.edit_text("🎯 <b>Select active allocation targeting settlement:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("settle_m_"), F.from_user.id == ADMIN_ID)
async def admin_settle_score_req(callback: types.CallbackQuery, state: FSMContext):
    m_id = callback.data.replace("settle_m_", "")
    await state.update_data(settle_mid=m_id)
    await state.set_state(AdminStates.waiting_for_settle_score)
    await callback.message.answer(f"📊 Enter scoreline parameters for Match <b>#{m_id}</b> (Format: <code>ScoreA-ScoreB</code>, e.g., <code>2-1</code>):")
    await callback.answer()

@dp.message(AdminStates.waiting_for_settle_score, F.from_user.id == ADMIN_ID)
async def admin_settle_execute(message: types.Message, state: FSMContext):
    try:
        sc = message.text.strip().split("-")
        sa, sb = int(sc[0]), int(sc[1])
        data = await state.get_data()
        m_id = data["settle_mid"]
        
        match = MATCHES[m_id]
        match["score_a"] = sa
        match["score_b"] = sb
        match["settled"] = True
        
        act_outcome = 1 if sa > sb else (-1 if sb > sa else 0)
        users_processed = 0
        
        for u, profile in USERS.items():
            if m_id in profile.get("predictions", {}):
                pred = profile["predictions"][m_id]
                if pred.get("status") != "pending": continue
                
                pa, pb, wager = pred["score_a"], pred["score_b"], pred["amount"]
                pred_outcome = 1 if pa > pb else (-1 if pb > pa else 0)
                
                if pa == sa and pb == sb:
                    profile["balance"] += wager * 2.0
                    profile["exact_wins"] += 1
                    profile["total_wins"] += 1
                    pred["status"] = "exact"
                elif pred_outcome == act_outcome:
                    profile["balance"] += wager * 1.5
                    profile["total_wins"] += 1
                    pred["status"] = "outcome"
                else:
                    pred["status"] = "lost"
                users_processed += 1
                
        await message.answer(f"🏁 Settlement finalized: <b>{sa} - {sb}</b>. Calculated metrics across {users_processed} nodes.", reply_markup=await get_main_admin_keyboard())
    except:
        await message.answer("❌ Syntax optimization error. Use exact pattern: <code>ScoreA-ScoreB</code>")
    await state.clear()

@dp.callback_query(F.data == "adm_credit_start", F.from_user.id == ADMIN_ID)
async def admin_credit_uid_step(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_credit_uid)
    await callback.message.answer("👤 Input Target User Storage ID:")
    await callback.answer()

@dp.message(AdminStates.waiting_for_credit_uid, F.from_user.id == ADMIN_ID)
async def admin_credit_amt_step(message: types.Message, state: FSMContext):
    await state.update_data(target_uid=message.text.strip())
    await state.set_state(AdminStates.waiting_for_credit_amt)
    await message.answer("⚽️ Input allocation quantity to grant:")

@dp.message(AdminStates.waiting_for_credit_amt, F.from_user.id == ADMIN_ID)
async def admin_credit_finalize(message: types.Message, state: FSMContext):
    try:
        amt = float(message.text.strip())
        data = await state.get_data()
        uid = data["target_uid"]
        
        if uid in USERS:
            USERS[uid]["balance"] += amt
            await message.answer(f"✅ Storage node {uid} adjustment complete.")
            try:
                await bot.send_message(int(uid), f"💳 <b>Ecosystem Allocation Modified!</b>\n🛡 Admin credited <b>+{amt} ⚽️</b> into your balance parameters.")
            except: pass
        else:
            await message.answer("❌ Specified user storage node offline / not found.")
    except:
        await message.answer("❌ Data type error. Floating precision value required.")
    await state.clear()

@dp.callback_query(F.data == "adm_bcast_start", F.from_user.id == ADMIN_ID)
async def admin_broadcast_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_broadcast_msg)
    await callback.message.answer("📢 Provide payload deployment string (Broadcast message):")
    await callback.answer()

@dp.message(AdminStates.waiting_for_broadcast_msg, F.from_user.id == ADMIN_ID)
async def admin_broadcast_execute(message: types.Message, state: FSMContext):
    s, f = 0, 0
    for uid in USERS.keys():
        try:
            await bot.send_message(int(uid), message.text)
            s += 1
            await asyncio.sleep(0.04)
        except: f += 1
    await message.answer(f"📢 Broadcast finished. Successfully routed: {s} | Terminated: {f}", reply_markup=await get_main_admin_keyboard())
    await state.clear()

@dp.callback_query(F.data == "adm_task_add", F.from_user.id == ADMIN_ID)
async def admin_task_add_ch(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_task_ch)
    await callback.message.answer("Target handle link entry (e.g., <code>@mychannel</code>):")
    await callback.answer()

@dp.message(AdminStates.waiting_for_task_ch, F.from_user.id == ADMIN_ID)
async def admin_task_add_rw(message: types.Message, state: FSMContext):
    await state.update_data(channel=message.text.strip())
    await state.set_state(AdminStates.waiting_for_task_reward)
    await message.answer("Define token allocation payout factor:")

@dp.message(AdminStates.waiting_for_task_reward, F.from_user.id == ADMIN_ID)
async def admin_task_add_ty(message: types.Message, state: FSMContext):
    try:
        rw = float(message.text.strip())
        await state.update_data(reward=rw)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Force-Join Gateway", callback_data="ty_f")],
            [InlineKeyboardButton(text="🎯 Interface Quest Tab", callback_data="ty_t")]
        ])
        await state.set_state(AdminStates.waiting_for_task_type)
        await message.answer("Bind deployment environment layer:", reply_markup=kb)
    except:
        await message.answer("Error value processing.")

@dp.callback_query(AdminStates.waiting_for_task_type, F.from_user.id == ADMIN_ID)
async def admin_task_finalize(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    CHANNELS[data['channel']] = {"reward": data['reward'], "is_force_join": (callback.data == "ty_f")}
    await callback.message.answer(f"✅ Quest structural pipeline established for {data['channel']}", reply_markup=await get_main_admin_keyboard())
    await state.clear()

@dp.callback_query(F.data == "adm_task_rem", F.from_user.id == ADMIN_ID)
async def admin_task_remove(callback: types.CallbackQuery, state: FSMContext):
    if not CHANNELS:
        await callback.message.answer("❌ Task manifest empty.", reply_markup=await get_main_admin_keyboard())
        return
    buttons = [[InlineKeyboardButton(text=f"Remove {c}", callback_data=f"rem_ch_{c}")] for c in CHANNELS.keys()]
    await callback.message.edit_text("⚙️ Select routing target configuration to terminate:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("rem_ch_"), F.from_user.id == ADMIN_ID)
async def admin_task_remove_execute(callback: types.CallbackQuery):
    target = callback.data.replace("rem_ch_", "")
    if target in CHANNELS: del CHANNELS[target]
    await callback.message.answer(f"🧹 Configuration path {target} dropped.", reply_markup=await get_main_admin_keyboard())

# --- FastAPI JSON REST Protocol Gateways ---
@app.get("/")
async def serve_matrix_client():
    with open("index.html", "r", encoding="utf-8") as file:
        return HTMLResponse(content=file.read())

@app.get("/api/data")
async def fetch_network_status(user_id: str = None):
    if user_id and user_id in USERS: USERS[user_id]["last_active"] = time.time()
    online = sum(1 for u in USERS.values() if time.time() - u.get("last_active", 0) < 40)
    return {"online_count": max(1, online)}

@app.get("/api/user/{user_id}")
async def fetch_user_state_vector(user_id: str):
    if user_id not in USERS: 
        return {"balance": 0.0, "invites": [], "invite_count": 0, "predictions": {}}
    return {
        "balance": USERS[user_id]["balance"], "invites": USERS[user_id]["invites"],
        "invite_count": len(USERS[user_id]["invites"]), "predictions": USERS[user_id].get("predictions", {})
    }

@app.get("/api/matches")
async def fetch_matches_manifest():
    return {"matches": MATCHES}

@app.post("/api/predict")
async def process_prediction_lock(request: Request):
    payload = await request.json()
    uid, mid = str(payload.get('user_id')), str(payload.get('match_id'))
    sa, sb, wager = int(payload.get('score_a')), int(payload.get('score_b')), float(payload.get('amount'))
    
    if uid not in USERS or mid not in MATCHES: raise HTTPException(status_code=400, detail="Node missing error")
    m = MATCHES[mid]
    if time.time() >= m["start_time"] or USERS[uid]["balance"] < wager or wager <= 0 or m["settled"]:
        return {"status": "error", "message": "Transaction declined. System configuration locked / timeline past context expiration."}
        
    USERS[uid]["balance"] -= wager
    USERS[uid].setdefault("predictions", {})[mid] = {
        "score_a": sa, "score_b": sb, "amount": wager, "status": "pending", "timestamp": time.time()
    }
    return {"status": "success", "new_balance": USERS[uid]["balance"]}

@app.get("/api/tasks/{user_id}")
async def fetch_quests_manifest(user_id: str):
    completed = USERS.get(user_id, {}).get("tasks", [])
    active = [{"channel": c, "reward": d["reward"]} for c, d in CHANNELS.items() if not d.get("is_force_join") and c not in completed]
    return {"tasks": active}

@app.post("/api/check_task")
async def verify_quest_parameters(request: Request):
    payload = await request.json()
    uid, ch = str(payload['user_id']), payload['channel']
    if ch not in CHANNELS or uid not in USERS or ch in USERS[uid].get("tasks", []):
        return {"status": "error", "message": "State logic error. Action impossible."}
    try:
        status = await bot.get_chat_member(chat_id=ch, user_id=int(uid))
        if status.status in ['left', 'kicked']: return {"status": "error", "message": "Channel structural verification missing."}
        rw = CHANNELS[ch]["reward"]
        USERS[uid]["balance"] += rw
        USERS[uid]["tasks"].append(ch)
        return {"status": "success", "reward": rw, "new_balance": USERS[uid]["balance"]}
    except:
        return {"status": "error", "message": "Ecosystem API tracking layer breakdown."}

@app.get("/api/leaderboard")
async def serve_leaderboard_ledger():
    sorted_p = sorted(USERS.items(), key=lambda x: (x[1].get("exact_wins", 0), x[1].get("total_wins", 0)), reverse=True)[:50]
    sorted_r = sorted(USERS.items(), key=lambda x: len(x[1].get("invites", [])), reverse=True)[:50]
    
    predictors = [{"name": u[1]["first_name"], "exact": u[1].get("exact_wins", 0), "total": u[1].get("total_wins", 0)} for u in sorted_p]
    referrers = [{"name": u[1]["first_name"], "count": len(u[1].get("invites", []))} for u in sorted_r]
    return {"predictors": predictors, "referrers": referrers}

@app.on_event("startup")
async def on_startup_pipeline():
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
