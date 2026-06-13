import os
import sqlite3
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

# حل مشکل CORS برای ارتباط امن فرانت‌اند و بک‌اند
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# دریافت توکن ربات از متغیرهای محیطی Railway (امنیت بالا)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_DEFAULT_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# راه‌اندازی دیتابیس
# نکته برای Railway: برای ماندگاری طولانی‌مدت داده‌های SQLite، یک Volume به مسیر پروژه اتچ کنید.
DB_PATH = os.environ.get("DB_PATH", "miniapp.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users 
             (user_id INTEGER PRIMARY KEY, timezone TEXT, lang TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS tasks 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_date TEXT, title TEXT, duration TEXT, status TEXT)''')
conn.commit()

class UserData(BaseModel):
    user_id: int
    timezone: str
    lang: str

class TaskData(BaseModel):
    user_id: int
    task_date: str
    title: str
    duration: str

class TaskUpdate(BaseModel):
    status: str

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# ذخیره یا آپدیت اطلاعات کاربر (منطقه زمانی و زبان انتخابی)
@app.post("/api/user")
async def save_user(data: UserData):
    c.execute("INSERT OR REPLACE INTO users (user_id, timezone, lang) VALUES (?, ?, ?)", 
              (data.user_id, data.timezone, data.lang))
    conn.commit()
    return {"status": "success"}

# دریافت تسک‌های کاربر برای یک تاریخ خاص
@app.get("/api/tasks/{user_id}/{date}")
async def get_tasks(user_id: int, date: str):
    c.execute("SELECT id, title, duration, status FROM tasks WHERE user_id=? AND task_date=?", (user_id, date))
    tasks = [{"id": row[0], "title": row[1], "duration": row[2], "status": row[3]} for row in c.fetchall()]
    return tasks

# ثبت تسک جدید برای فردا
@app.post("/api/tasks")
async def create_task(data: TaskData):
    c.execute("INSERT INTO tasks (user_id, task_date, title, duration, status) VALUES (?, ?, ?, ?, 'pending')", 
              (data.user_id, data.task_date, data.title, data.duration))
    conn.commit()
    return {"status": "success"}

# تغییر وضعیت تسک (انجام شد / نشد) توسط کاربر در روز جاری
@app.put("/api/tasks/{task_id}")
async def update_task(task_id: int, data: TaskUpdate):
    c.execute("UPDATE tasks SET status=? WHERE id=?", (data.status, task_id))
    conn.commit()
    return {"status": "success"}

# سیستم هوشمند نوتیفیکیشن بر اساس تایم‌زون محلی هر کاربر
def check_and_send_notifications():
    c.execute("SELECT user_id, timezone, lang FROM users")
    users = c.fetchall()
    
    for user_id, tz_str, lang in users:
        try:
            tz = pytz.timezone(tz_str)
            local_time = datetime.now(tz)
            
            # ارسال اعلان راس ساعت ۸ صبح به وقت محلی کاربر
            if local_time.hour == 8 and local_time.minute == 0:
                today_str = local_time.strftime("%Y-%m-%d")
                c.execute("SELECT title FROM tasks WHERE user_id=? AND task_date=?", (user_id, today_str))
                tasks = c.fetchall()
                if tasks:
                    if lang == "fa":
                        msg = "برنامه‌های امروز شما:\n" + "\n".join([f"- {t[0]}" for t in tasks])
                    else:
                        msg = "Your tasks for today:\n" + "\n".join([f"- {t[0]}" for t in tasks])
                        
                    requests.post(TELEGRAM_API_URL, json={"chat_id": user_id, "text": msg})
        except Exception as e:
            print(f"Error executing notification for {user_id}: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(check_and_send_notifications, 'interval', minutes=1)
scheduler.start()

if __name__ == "__main__":
    import uvicorn
    # Railway پورت را از طریق متغیر PORT پاس می‌دهد، در غیر این صورت روی 8000 اجرا می‌شود
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
