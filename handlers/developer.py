from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.db import SessionLocal
from database.models import Task, DailyReport, User, Sprint, Project
from datetime import datetime

# حالات مکالمه
REPORT_COMPLETED, REPORT_PLANNED, REPORT_BLOCKERS = range(3)
TASK_SELECT_REVIEW = 10
SELECT_PROJECT_FOR_SPRINT = 20
SELECT_SPRINT = 21
SELECT_TASK_TO_START = 101
SELECT_PROJECT_FOR_SPRINT_CREATION, SELECT_TASKS_FOR_SPRINT = range(100, 102)

# --------------------
# ارسال گزارش روزانه
# --------------------
async def send_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 لطفاً تسک‌های انجام‌شده امروز را وارد کنید:")
    return REPORT_COMPLETED

async def daily_report_completed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["completed_tasks"] = update.message.text.strip()
    await update.message.reply_text("📅 برنامه تسک‌های امروز را وارد کنید:")
    return REPORT_PLANNED

async def daily_report_planned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["planned_tasks"] = update.message.text.strip()
    await update.message.reply_text("🚧 اگر مانعی هست وارد کنید، در غیر اینصورت 'ندارد' بنویسید:")
    return REPORT_BLOCKERS

async def daily_report_blockers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    blockers = update.message.text.strip()
    user_id = update.effective_user.id
    session = SessionLocal()

    user = session.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        await update.message.reply_text("❌ خطا: کاربر یافت نشد.")
        session.close()
        return ConversationHandler.END

    active_sprint = None
    tasks = session.query(Task).filter(Task.assigned_to == user.id).all()
    sprint_ids = set(t.sprint_id for t in tasks)
    for sprint_id in sprint_ids:
        sprint = session.query(Sprint).filter_by(id=sprint_id, status="Active").first()
        if sprint:
            active_sprint = sprint
            break

    if not active_sprint:
        await update.message.reply_text("❌ اسپرینت فعالی برای شما یافت نشد.")
        session.close()
        return ConversationHandler.END

    report = DailyReport(
        user_id=user.id,
        sprint_id=active_sprint.id,
        report_date=datetime.utcnow().date(),
        completed_tasks=context.user_data["completed_tasks"],
        planned_tasks=context.user_data["planned_tasks"],
        blockers=blockers
    )
    session.add(report)
    session.commit()
    session.close()

    await update.message.reply_text("✅ گزارش روزانه شما ثبت شد. ممنون!")
    return ConversationHandler.END

# --------------------
# ارسال تسک برای بازبینی
# --------------------
async def start_task_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد.")
        session.close()
        return ConversationHandler.END

    tasks = session.query(Task).filter(Task.assigned_to == user.id, Task.status == "InProgress").all()
    if not tasks:
        await update.message.reply_text("شما هیچ تسک در حال انجام ندارید که بتوانید برای بازبینی ارسال کنید.")
        session.close()
        return ConversationHandler.END

    context.user_data["task_map"] = {f"{t.id}: {t.title}": t.id for t in tasks}
    keyboard = [[f"{t.id}: {t.title}"] for t in tasks]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text("لطفاً تسکی که می‌خواهید برای بازبینی ارسال کنید را انتخاب کنید:", reply_markup=reply_markup)
    session.close()
    return TASK_SELECT_REVIEW

async def select_task_for_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected = update.message.text.strip()
    task_id = context.user_data.get("task_map", {}).get(selected)
    if not task_id:
        await update.message.reply_text("تسک نامعتبر انتخاب شده.")
        return ConversationHandler.END

    session = SessionLocal()
    task = session.query(Task).filter_by(id=task_id).first()
    if not task:
        await update.message.reply_text("تسک پیدا نشد.")
        session.close()
        return ConversationHandler.END

    task.status = "InReview"
    task_title = task.title  # ذخیره قبل از بستن session
    session.commit()
    session.close()

    await update.message.reply_text(f"✅ تسک '{task_title}' برای بازبینی ارسال شد.")
    return ConversationHandler.END

# --------------------
# مشاهده تسک‌های من
# --------------------
async def show_my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد.")
        session.close()
        return

    tasks = session.query(Task).filter(Task.assigned_to == user.id).filter(Task.status != "Completed").all()
    if not tasks:
        await update.message.reply_text("شما هیچ تسک فعالی ندارید.")
        session.close()
        return

    msg = "📝 تسک‌های شما:\n\n"
    for t in tasks:
        msg += f"🔹 [{t.id}] {t.title} | وضعیت: {t.status}\n"

    await update.message.reply_text(msg)
    session.close()

# --------------------
# انتخاب اسپرینت و اختصاص تسک‌ها
# --------------------
async def select_project_for_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    projects = session.query(Project).all()
    if not projects:
        await update.message.reply_text("❌ پروژه‌ای وجود ندارد.")
        session.close()
        return ConversationHandler.END

    project_map = {p.name: p.id for p in projects}
    context.user_data["project_map"] = project_map

    keyboard = [[p.name] for p in projects]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("لطفاً پروژه را انتخاب کنید:", reply_markup=reply_markup)
    session.close()
    return SELECT_PROJECT_FOR_SPRINT

async def select_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_project = update.message.text.strip()
    project_map = context.user_data.get("project_map", {})
    if selected_project not in project_map:
        await update.message.reply_text("❌ پروژه نامعتبر انتخاب شده.")
        return ConversationHandler.END

    project_id = project_map[selected_project]
    session = SessionLocal()
    sprints = session.query(Sprint).filter_by(project_id=project_id, status="Active").all()
    if not sprints:
        await update.message.reply_text("❌ اسپرینت فعالی برای این پروژه وجود ندارد.")
        session.close()
        return ConversationHandler.END

    sprint_map = {f"Sprint {s.id}": s.id for s in sprints}
    context.user_data["sprint_map"] = sprint_map

    keyboard = [[f"Sprint {s.id}"] for s in sprints]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("✅ لطفاً یک اسپرینت را انتخاب کنید:", reply_markup=reply_markup)
    session.close()
    return SELECT_SPRINT

async def show_tasks_in_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_sprint = update.message.text.strip()
    sprint_map = context.user_data.get("sprint_map", {})
    if selected_sprint not in sprint_map:
        await update.message.reply_text("❌ اسپرینت نامعتبر است.")
        return ConversationHandler.END

    sprint_id = sprint_map[selected_sprint]
    user_id = update.effective_user.id

    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد.")
        session.close()
        return ConversationHandler.END

    # فقط تسک‌های بدون صاحب
    unassigned_tasks = session.query(Task).filter_by(sprint_id=sprint_id, assigned_to=None).all()
    if not unassigned_tasks:
        await update.message.reply_text("❌ تسک بدون مالک در این اسپرینت وجود ندارد.")
        session.close()
        return ConversationHandler.END

    # اختصاص همه‌ی تسک‌های بدون مالک به کاربر
    for task in unassigned_tasks:
        task.assigned_to = user.id

    session.commit()

    msg = f"✅ {len(unassigned_tasks)} تسک از اسپرینت «{selected_sprint}» به شما اختصاص داده شد:\n\n"
    for t in unassigned_tasks:
        msg += f"🔹 [{t.id}] {t.title} | وضعیت: {t.status}\n"

    session.close()
    await update.message.reply_text(msg)
    return ConversationHandler.END


async def start_task_selection(update:
    Update, context: 
    ContextTypes.DEFAULT_TYPE): 
    user_id = update.effective_user.id 
    session = SessionLocal() 
    user = session.query(User).filter_by(telegram_id=user_id).first() 
    if not user: 
        await update.message.reply_text("❌ کاربر یافت نشد.") 
        session.close() 
        return ConversationHandler.END 
    tasks = session.query(Task).filter(Task.assigned_to == user.id, Task.status == "NotStarted").all() 
    if not tasks: 
        await update.message.reply_text("هیچ تسک شروع‌نشده‌ای برای شما یافت نشد.") 
        session.close() 
        return ConversationHandler.END 
    task_map = {f"{t.id}: {t.title}": t.id for t in tasks} 
    context.user_data["start_task_map"] = task_map 
    keyboard = [[label] for label in task_map] 
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True) 
    await update.message.reply_text("لطفاً تسکی که می‌خواهید شروع کنید را انتخاب کنید:", reply_markup=reply_markup) 
    session.close() 
    return SELECT_TASK_TO_START

async def confirm_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    selected = update.message.text.strip() 
    task_id = context.user_data.get("start_task_map", {}).get(selected) 
    if not task_id: 
        await update.message.reply_text("❌ تسک انتخاب‌شده نامعتبر است.") 
        return ConversationHandler.END 

    session = SessionLocal() 
    task = session.query(Task).filter_by(id=task_id).first() 
    if not task: 
        await update.message.reply_text("❌ تسک یافت نشد.") 
        session.close() 
        return ConversationHandler.END 

    task.status = "InProgress"
    task_title = task.title  # 👈 ذخیره قبل از بستن session
    session.commit()
    session.close() 

    await update.message.reply_text(f"✅ تسک '{task_title}' به وضعیت 'در حال انجام' تغییر یافت.") 
    return ConversationHandler.END


async def start_sprint_creation(update, context):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    projects = session.query(Project).all()
    if not projects:
        await update.message.reply_text("❌ هیچ پروژه‌ای ثبت نشده است.")
        session.close()
        return ConversationHandler.END

    context.user_data["project_map"] = {p.name: p.id for p in projects}
    keyboard = [[p.name] for p in projects]

    await update.message.reply_text(
        "📋 لطفاً پروژه‌ای را برای ساخت اسپرینت انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    session.close()
    return SELECT_PROJECT_FOR_SPRINT_CREATION

async def show_backlog_tasks(update, context):
    session = SessionLocal()
    selected_project = update.message.text.strip()
    project_id = context.user_data["project_map"].get(selected_project)

    if not project_id:
        await update.message.reply_text("❌ پروژه نامعتبر است.")
        session.close()
        return ConversationHandler.END

    tasks = session.query(Task).filter_by(project_id=project_id, status="Backlog").all()
    if not tasks:
        await update.message.reply_text("❌ این پروژه تسک در وضعیت Backlog ندارد.")
        session.close()
        return ConversationHandler.END

    context.user_data["selected_project_id"] = project_id
    context.user_data["task_map"] = {f"{t.title} ({t.story_point})": t.id for t in tasks}

    keyboard = [[title] for title in context.user_data["task_map"].keys()]
    keyboard.append(["🔙 بازگشت به انتخاب پروژه"])  # 👈 اضافه کردن گزینه بازگشت
    await update.message.reply_text(
        "✅ تسک‌هایی که می‌خواهید در اسپرینت قرار دهید انتخاب کنید. (یک‌به‌یک ارسال کنید. وقتی تمام شد، بنویسید: پایان)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


    context.user_data["selected_task_ids"] = []
    session.close()
    return SELECT_TASKS_FOR_SPRINT

async def collect_tasks_for_sprint(update, context):
    session = SessionLocal()
    text = update.message.text.strip()
    if text == "🔙 بازگشت به انتخاب پروژه":
    # بازنشانی لیست تسک‌ها و پروژه انتخاب شده
        context.user_data.pop("selected_project_id", None)
        context.user_data.pop("task_map", None)
        context.user_data.pop("selected_task_ids", None)
        return await start_sprint_creation(update, context)
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if text == "پایان":
        if not context.user_data.get("selected_task_ids"):
            await update.message.reply_text("❌ هیچ تسکی انتخاب نشده.")
            session.close()
            return ConversationHandler.END

        sprint = Sprint(
            start_date=datetime.utcnow(),
            status="Active",
            created_by=user.id
        )
        session.add(sprint)
        session.flush()  # برای گرفتن sprint.id

        for task_id in context.user_data["selected_task_ids"]:
            task = session.query(Task).get(task_id)
            if task:
                task.sprint_id = sprint.id
                task.status = "NotStarted"
                task.assigned_to = user.id

        session.commit()
        await update.message.reply_text("✅ اسپرینت با موفقیت ساخته شد و تسک‌ها به آن اضافه شدند.")
        session.close()
        return ConversationHandler.END

    task_id = context.user_data["task_map"].get(text)
    if task_id and task_id not in context.user_data["selected_task_ids"]:
        context.user_data["selected_task_ids"].append(task_id)
        await update.message.reply_text(f"➕ تسک '{text}' اضافه شد. مورد بعدی را انتخاب کنید یا بنویسید: پایان")
    else:
        await update.message.reply_text("❌ تسک نامعتبر یا تکراری است.")

    session.close()
    return SELECT_TASKS_FOR_SPRINT

