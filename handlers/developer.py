# handlers/developer.py

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.db import SessionLocal
from database.models import Task, DailyReport, User, Sprint, Project
from datetime import datetime

# Conversation states for daily report
REPORT_COMPLETED, REPORT_PLANNED, REPORT_BLOCKERS = range(3)
# Conversation states for self‑review
TASK_SELECT_REVIEW = 10
# Conversation states for starting tasks
SELECT_TASK_FOR_START = 101
# Conversation states for adding tasks to sprint
SELECT_PROJECT_FOR_SPRINT_CREATION, SELECT_TASKS_FOR_SPRINT = range(100, 102)
# Conversation states for reviewing others’ tasks
REVIEW_SELECT_TASK, REVIEW_DECISION, REVIEW_REASON = range(200, 203)
# ثابتی که bot.py منتظر آن است:
SELECT_TASK_TO_START = 101

# --------------------
# ارسال گزارش روزانه
# --------------------
async def send_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 لطفاً تسک‌های انجام‌شده امروز را وارد کنید:\n(🔙 انصراف برای خروج)"
    )
    return REPORT_COMPLETED

async def daily_report_completed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "🔙 انصراف":
        return ConversationHandler.END
    context.user_data["completed_tasks"] = update.message.text.strip()
    await update.message.reply_text("📅 برنامه تسک‌های امروز را وارد کنید:")
    return REPORT_PLANNED

async def daily_report_planned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "🔙 انصراف":
        return ConversationHandler.END
    context.user_data["planned_tasks"] = update.message.text.strip()
    await update.message.reply_text("🚧 اگر مانعی هست وارد کنید، در غیر اینصورت ‘ندارد’ بنویسید:")
    return REPORT_BLOCKERS

async def daily_report_blockers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "🔙 انصراف":
        return ConversationHandler.END

    blockers = update.message.text.strip()
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user:
        session.close()
        await update.message.reply_text("❌ کاربر یافت نشد.")
        return ConversationHandler.END

    sprint_ids = {
        t.sprint_id for t in session.query(Task).filter_by(assigned_to=user.id) if t.sprint_id
    }
    active = None
    for sid in sprint_ids:
        s = session.query(Sprint).filter_by(id=sid, status="Active").first()
        if s:
            active = s
            break

    if not active:
        session.close()
        await update.message.reply_text("❌ اسپرینت فعالی یافت نشد.")
        return ConversationHandler.END

    report = DailyReport(
        user_id=user.id,
        sprint_id=active.id,
        report_date=datetime.utcnow().date(),
        completed_tasks=context.user_data["completed_tasks"],
        planned_tasks=context.user_data["planned_tasks"],
        blockers=blockers
    )
    session.add(report)
    session.commit()
    session.close()

    await update.message.reply_text("✅ گزارش روزانه شما ثبت شد.")
    return ConversationHandler.END


# --------------------
# ارسال تسک برای بازبینی (توسط خود کاربر)
# --------------------
async def start_task_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    tasks = session.query(Task).filter_by(assigned_to=user.id, status="InProgress").all() if user else []
    session.close()

    if not tasks:
        await update.message.reply_text("❌ تسک در حال انجام ندارید.")
        return ConversationHandler.END

    context.user_data["task_map"] = {f"{t.id}: {t.title}": t.id for t in tasks}
    keyboard = [[f"{t.id}: {t.title}"] for t in tasks] + [["🔙 انصراف"]]
    await update.message.reply_text(
        "📌 تسکی را برای ارسال به بازبینی انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return TASK_SELECT_REVIEW

async def select_task_for_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sel = update.message.text.strip()
    if sel == "🔙 انصراف":
        return ConversationHandler.END

    tid = context.user_data.get("task_map", {}).get(sel)
    if not tid:
        await update.message.reply_text("❌ انتخاب نامعتبر.")
        return ConversationHandler.END

    session = SessionLocal()
    task = session.query(Task).get(tid)
    if not task:
        session.close()
        await update.message.reply_text("❌ تسک یافت نشد.")
        return ConversationHandler.END

    title = task.title
    task.status = "InReview"
    session.commit()
    session.close()

    await update.message.reply_text(f"✅ تسک ‘{title}’ برای بازبینی ارسال شد.")
    return ConversationHandler.END


# --------------------
# مشاهده تسک‌های من
# --------------------
async def show_my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    tasks = session.query(Task).filter(Task.assigned_to==user.id, Task.status!="Completed").all() if user else []
    session.close()

    if not tasks:
        await update.message.reply_text("❌ تسکی ندارید.")
        return

    lines = [f"🔹 [{t.id}] {t.title} | {t.status}" for t in tasks]
    await update.message.reply_text("📝 تسک‌های شما:\n" + "\n".join(lines))


# --------------------
# شروع تسک
# --------------------
async def start_task_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    tasks = session.query(Task).filter_by(assigned_to=user.id, status="NotStarted").all() if user else []
    session.close()

    if not tasks:
        await update.message.reply_text("❌ تسک شروع‌نشده ندارید.")
        return ConversationHandler.END

    context.user_data["start_task_map"] = {f"{t.id}: {t.title}": t.id for t in tasks}
    keyboard = [[lbl] for lbl in context.user_data["start_task_map"].keys()] + [["❌ انصراف"]]
    await update.message.reply_text(
        "▶️ تسکی را برای شروع انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return SELECT_TASK_FOR_START

async def confirm_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sel = update.message.text.strip()
    if sel == "❌ انصراف":
        return ConversationHandler.END

    tid = context.user_data.get("start_task_map", {}).get(sel)
    if not tid:
        await update.message.reply_text("❌ نامعتبر.")
        return ConversationHandler.END

    session = SessionLocal()
    task = session.query(Task).get(tid)
    if not task:
        session.close()
        await update.message.reply_text("❌ تسک نیست.")
        return ConversationHandler.END

    title = task.title
    task.status = "InProgress"
    session.commit()
    session.close()

    await update.message.reply_text(f"✅ تسک ‘{title}’ شروع شد.")
    return ConversationHandler.END


# --------------------
# افزودن تسک جدید به پروژه
# --------------------
async def start_sprint_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    projects = session.query(Project).all()
    session.close()

    if not projects:
        await update.message.reply_text("❌ پروژه‌ای نیست.")
        return ConversationHandler.END

    context.user_data["project_map"] = {p.name:p.id for p in projects}
    keyboard = [[p.name] for p in projects] + [["🔙 انصراف"]]
    await update.message.reply_text(
        "🚀 پروژه‌ای را برای افزودن تسک انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return SELECT_PROJECT_FOR_SPRINT_CREATION

async def show_backlog_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 انصراف":
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END

    session = SessionLocal()
    project_map = context.user_data.get("project_map", {})
    project_id = project_map.get(text)
    if not project_id:
        await update.message.reply_text("❌ پروژه نامعتبر است.")
        session.close()
        return ConversationHandler.END

    tasks = session.query(Task).filter_by(project_id=project_id, status="Backlog").all()
    session.close()
    if not tasks:
        await update.message.reply_text("❌ این پروژه تسک Backlog ندارد.")
        return ConversationHandler.END

    context.user_data["task_map"] = {f"{t.title} ({t.story_point})": t.id for t in tasks}
    context.user_data["selected_task_ids"] = []

    keyboard = [[k] for k in context.user_data["task_map"].keys()]
    keyboard += [
        ["پایان"],
        ["🔙 انتخاب پروژه مجدد"],
        ["🔙 انصراف"],
    ]
    await update.message.reply_text(
        "✅ تسک‌هایی که می‌خواهید اضافه کنید را انتخاب کنید.\n(برای پایان «پایان» را بزنید)",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return SELECT_TASKS_FOR_SPRINT

async def collect_tasks_for_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "پایان":
        selected = context.user_data.get("selected_task_ids", [])
        if not selected:
            await update.message.reply_text("❌ هیچ تسکی انتخاب نشده.")
            return ConversationHandler.END
        session = SessionLocal()
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        sprint = Sprint(start_date=datetime.utcnow(), status="Active", created_by=user.id)
        session.add(sprint); session.flush()
        for tid in selected:
            task = session.query(Task).get(tid)
            if task:
                task.sprint_id = sprint.id
                task.status = "NotStarted"
                task.assigned_to = user.id
        session.commit(); session.close()
        await update.message.reply_text("✅ تسک‌ها اضافه شدند.")
        return ConversationHandler.END

    if text == "🔙 انصراف":
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END

    if text == "🔙 انتخاب پروژه مجدد":
        return await start_sprint_creation(update, context)

    tid = context.user_data.get("task_map", {}).get(text)
    if tid and tid not in context.user_data["selected_task_ids"]:
        context.user_data["selected_task_ids"].append(tid)
        await update.message.reply_text(f"➕ تسک ‘{text}’ اضافه شد؛ برای پایان «پایان» را بزنید.")
    else:
        await update.message.reply_text("❌ نامعتبر یا تکراری است.")
    return SELECT_TASKS_FOR_SPRINT


# --------------------
# بازبینی و تأیید/رد تسک‌های دیگران
# --------------------
async def start_review_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    me = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    tasks = session.query(Task).filter(Task.status=="InReview", Task.assigned_to!=me.id).all() if me else []
    session.close()

    if not tasks:
        await update.message.reply_text("❌ کاری برای بازبینی ندارید.")
        return ConversationHandler.END

    context.user_data["review_map"] = {f"{t.id}: {t.title}": t.id for t in tasks}
    keyboard = [[f"{t.id}: {t.title}"] for t in tasks] + [["🔙 انصراف"]]
    await update.message.reply_text(
        "🧐 تسکی برای بازبینی انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return REVIEW_SELECT_TASK

async def review_select_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sel = update.message.text.strip()
    if sel == "🔙 انصراف":
        return ConversationHandler.END
    tid = context.user_data.get("review_map", {}).get(sel)
    if not tid:
        await update.message.reply_text("❌ نامعتبر.")
        return ConversationHandler.END

    session = SessionLocal()
    task = session.query(Task).get(tid)
    session.close()
    context.user_data["review_task_id"] = tid

    keyboard = [["✅ تأیید"], ["❌ رد"]]
    await update.message.reply_text(f"🧐 تسک ‘{task.title}’؟", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return REVIEW_DECISION

async def review_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    tid = context.user_data.get("review_task_id")

    if choice == "✅ تأیید":
        session = SessionLocal()
        task = session.query(Task).get(tid)
        title, sp = task.title, task.story_point
        dev = session.query(User).get(task.assigned_to)
        # اضافه کردن امتیاز
        if dev:
            dev.total_points += sp
        task.status = "Completed"
        task.reviewed = True
        session.commit()
        session.close()

        await update.message.reply_text(f"✅ تسک ‘{title}’ تأیید شد و {sp} امتیاز اضافه شد.")
        # پیام تأیید دریافت‌شدن توسط ربات
        await update.message.reply_text("🤖 درخواست شما ثبت شد و ربات آن را دریافت کرد.")
        return ConversationHandler.END

    elif choice == "❌ رد":
        # ابتدا به کاربر اعلام می‌کنیم که دلیل بنویسد
        await update.message.reply_text("📝 لطفاً دلیل رد را بنویسید:")
        return REVIEW_REASON

    else:
        await update.message.reply_text("❌ لطفاً یکی از دو گزینه را انتخاب کنید.")
        return REVIEW_DECISION
    
async def review_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    tid = context.user_data.get("review_task_id")
    session = SessionLocal()
    task = session.query(Task).get(tid)
    title = task.title

    # برگرداندن وضعیت به 'InProgress'
    task.reason = reason
    task.status = "InProgress"
    session.commit()
    session.close()

    await update.message.reply_text(f"✅ تسک ‘{title}’ رد شد و دلیل شما ثبت گردید.")
    # پیام ضبط‌شدن توسط ربات
    await update.message.reply_text("🤖 درخواست شما ثبت شد و ربات آن را دریافت کرد.")
    return ConversationHandler.END