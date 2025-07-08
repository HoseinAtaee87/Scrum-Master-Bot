# admin.py

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import ContextTypes, ConversationHandler
from database.db import SessionLocal
from database.models import (
    User,
    Project,
    Sprint,
    Task,
    DailyReport,
    SprintReview,
    Retrospective
)
from datetime import datetime
from bot import start
# ============================
# Conversation States
# ============================
ADD_PROJECT_NAME = 1
SELECT_PROJECT_FOR_BACKLOG, ENTER_BACKLOG_TASKS = range(20, 22)

# States for review flow
REVIEW_DECISION, REVIEW_REASON = range(100, 102)


# ============================
# Add Project
# ============================
async def add_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    session.close()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("⛔️ دسترسی فقط برای مدیر محصول امکان‌پذیر است.")
        return ConversationHandler.END

    keyboard = [["🔙 انصراف"]]
    await update.message.reply_text(
        "📝 لطفاً نام پروژه جدید را وارد کنید:\n(برای بازگشت «🔙 انصراف» را بزنید)",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ADD_PROJECT_NAME

async def save_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 انصراف":
        await update.message.reply_text("❌ عملیات افزودن پروژه لغو شد.")
        return ConversationHandler.END

    name = text
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not name:
        await update.message.reply_text("❌ نام پروژه نمی‌تواند خالی باشد.")
        session.close()
        return ConversationHandler.END

    project = Project(
        name=name,
        description="پروژه ایجادشده از طریق ربات",
        created_by=user.id,
        created_at=datetime.now()
    )
    session.add(project)
    session.commit()
    session.close()

    await update.message.reply_text(f"✅ پروژه '{name}' با موفقیت ثبت شد.")
    return ConversationHandler.END


# ============================
# List Projects
# ============================
async def list_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("⛔️ شما دسترسی به این دستور ندارید.")
        session.close()
        return

    projects = session.query(Project).filter_by(created_by=user.id).all()
    if not projects:
        await update.message.reply_text("❌ هیچ پروژه‌ای ثبت نشده است.")
    else:
        resp = "📋 لیست پروژه‌های شما:\n\n"
        for p in projects:
            resp += f"🔹 {p.name} | ساخته‌شده در: {p.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        await update.message.reply_text(resp)

    session.close()


# ============================
# Add Task to Backlog
# ============================
async def add_task_to_backlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("⛔️ شما دسترسی به این دستور ندارید.")
        session.close()
        return ConversationHandler.END

    projects = session.query(Project).filter_by(created_by=user.id).all()
    session.close()
    if not projects:
        await update.message.reply_text("❌ شما هیچ پروژه‌ای ندارید.")
        return ConversationHandler.END

    keyboard = [[p.name] for p in projects]
    keyboard.append(["🔙 انصراف"])
    context.user_data["project_map"] = {p.name: p.id for p in projects}

    await update.message.reply_text(
        "📋 یک پروژه را برای افزودن تسک به بک‌لاگ انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return SELECT_PROJECT_FOR_BACKLOG

async def receive_backlog_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 انصراف":
        await update.message.reply_text("❌ عملیات افزودن تسک لغو شد.")
        return ConversationHandler.END

    project_map = context.user_data.get("project_map", {})
    project_id = project_map.get(text)
    if not project_id:
        await update.message.reply_text("❌ پروژه نامعتبر است.")
        return ConversationHandler.END

    context.user_data["selected_project_id"] = project_id
    await update.message.reply_text(
        "✍️ تسک‌های بک‌لاگ را وارد کنید (هر سطر: عنوان [فاصله] داستان‌پوینت).\n"
        "مثال:\nتسک1    2\nتسک2    1\n\nبرای لغو «🔙 انصراف» را بزنید."
    )
    return ENTER_BACKLOG_TASKS

async def save_backlog_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 انصراف":
        await update.message.reply_text("❌ عملیات افزودن تسک لغو شد.")
        return ConversationHandler.END

    session = SessionLocal()
    project_id = context.user_data["selected_project_id"]
    lines = text.split("\n")
    count = 0
    for line in lines:
        parts = line.strip().rsplit(maxsplit=1)
        if len(parts) != 2:
            continue
        title, sp_str = parts
        try:
            sp = int(sp_str)
        except ValueError:
            continue
        session.add(Task(
            project_id=project_id,
            title=title.strip(),
            story_point=sp,
            status="Backlog",
            created_at=datetime.now()
        ))
        count += 1

    session.commit()
    session.close()
    await update.message.reply_text(f"✅ {count} تسک به بک‌لاگ پروژه اضافه شد.")
    return ConversationHandler.END


# ============================
# Review Tasks (Admin)
# ============================
async def review_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user or user.role not in ["ProductOwner", "CEO","Developer"]:
        await update.message.reply_text("⛔️ شما دسترسی به این بخش ندارید.")
        session.close()
        return ConversationHandler.END

    tasks = session.query(Task).filter(Task.status == "InReview").all()
    if not tasks:
        await update.message.reply_text("❌ هیچ تسکی برای بازبینی موجود نیست.")
        session.close()
        return ConversationHandler.END

    for t in tasks:
        txt = (
            f"📝 [{t.id}] {t.title}\n"
            f"👤 توسعه‌دهنده: {t.assigned_to}\n"
            f"📅 تاریخ: {t.created_at.strftime('%Y-%m-%d')}\n"
            f"📝 توضیحات: {t.description or '—'}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تایید", callback_data=f"approve_{t.id}"),
                InlineKeyboardButton("❌ رد", callback_data=f"reject_{t.id}")
            ]
        ])
        await update.message.reply_text(txt, reply_markup=keyboard)

    session.close()
    return REVIEW_DECISION

async def review_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. "approve_5" or "reject_7"
    action, tid = data.split("_")
    context.user_data["review_task_id"] = int(tid)

    session = SessionLocal()
    task = session.query(Task).get(int(tid))

    if action == "approve":
        dev = session.query(User).get(task.assigned_to)
        if dev:
            dev.total_points += task.story_point
        task.status = "Completed"
        session.commit()
        session.close()
        await query.edit_message_text(f"✅ تسک [{tid}] تایید و تکمیل شد.")
        return ConversationHandler.END

    # action == "reject"
    session.close()
    await query.edit_message_text("❌ لطفاً دلیل رد تسک را وارد کنید (یا «🔙 انصراف»):")
    return REVIEW_REASON

async def review_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 انصراف":
        return await start(update, context)

    reason = text
    tid = context.user_data.get("review_task_id")

    session = SessionLocal()
    task = session.query(Task).get(tid)
    if task:
        task.status = "Backlog"
        task.reason = reason
        session.commit()
    session.close()

    await update.message.reply_text(f"✅ تسک [{tid}] رد شد و دلیل ثبت گردید.")
    return ConversationHandler.END


# ============================
# View Daily Reports (Admin)
# ============================
async def view_daily_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from database.models import DailyReport
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("⛔️ شما دسترسی به این بخش ندارید.")
        session.close()
        return

    reports = session.query(DailyReport).order_by(DailyReport.report_date.desc()).limit(5).all()
    if not reports:
        await update.message.reply_text("❌ هیچ گزارشی ثبت نشده است.")
    else:
        for rep in reports:
            msg = (
                f"📅 {rep.report_date}\n"
                f"👤 توسعه‌دهنده ID: {rep.user_id}\n"
                f"✅ انجام‌شده‌ها: {rep.completed_tasks}\n"
                f"📌 برنامه امروز: {rep.planned_tasks}\n"
                f"🚫 موانع: {rep.blockers}"
            )
            await update.message.reply_text(msg)
        await update.message.reply_text("✅ پایان نمایش گزارش‌های روزانه.")

    session.close()


# ============================
# View Sprint Review Reports (Admin)
# ============================
async def view_sprint_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from database.models import SprintReview
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("⛔️ دسترسی محدود است.")
        session.close()
        return

    reviews = session.query(SprintReview).order_by(SprintReview.review_date.desc()).limit(5).all()
    if not reviews:
        await update.message.reply_text("❌ هیچ گزارش اسپرینت ریویو ثبت نشده است.")
    else:
        for r in reviews:
            msg = (
                f"🗓️ تاریخ: {r.review_date}\n"
                f"🧩 اسپرینت ID: {r.sprint_id}\n"
                f"📄 توضیحات: {r.notes}\n"
                f"📊 درصد انجام‌شده: {r.completed_percentage}%"
            )
            await update.message.reply_text(msg)
        await update.message.reply_text("✅ پایان نمایش گزارش‌های اسپرینت ریویو.")

    session.close()


# ============================
# Finalize Sprint & Create Retrospective
# ============================
async def finalize_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("⛔️ دسترسی محدود است.")
        session.close()
        return

    active_sprints = session.query(Sprint).filter_by(status="Active").all()
    if not active_sprints:
        await update.message.reply_text("❌ هیچ اسپرینت فعالی وجود ندارد.")
        session.close()
        return

    for s in active_sprints:
        s.status = "Completed"
        session.add(Retrospective(
            sprint_id=s.id,
            held_by=user.id,
            retro_date=datetime.now(),
            discussion_points="جمع‌بندی خودکار ربات."
        ))

    session.commit()
    session.close()
    await update.message.reply_text("✅ تمامی اسپرینت‌های فعال بسته شدند و رتروسپکتیو ثبت شد.")


# ============================
# CEO: Manage Users
# ============================
async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user or user.role != "CEO":
        await update.message.reply_text("❌ فقط مدیرعامل می‌تواند به این بخش دسترسی داشته باشد.")
        session.close()
        return

    users = session.query(User).filter(User.role.in_(["Developer", "ProductOwner"])).all()
    if not users:
        await update.message.reply_text("❌ هیچ کاربری برای مدیریت یافت نشد.")
        session.close()
        return

    for u in users:
        text = f"👤 {u.name} - نقش فعلی: {u.role}"
        buttons = []
        if u.role == "Developer":
            buttons.append(InlineKeyboardButton("⬆️ ارتقا به مدیر", callback_data=f"promote_user_{u.id}"))
        else:
            buttons.extend([
                InlineKeyboardButton("⬆️ ارتقا به CEO", callback_data=f"promote_user_{u.id}"),
                InlineKeyboardButton("⬇️ تنزل به توسعه‌دهنده", callback_data=f"demote_user_{u.id}"),
                InlineKeyboardButton("❌ حذف", callback_data=f"remove_user_{u.id}")
            ])
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup.from_column(buttons))

    session.close()


# ============================
# Approve Reviewed Tasks (alternative bulk)
# ============================
async def approve_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("⛔️ دسترسی ندارید.")
        session.close()
        return

    tasks = session.query(Task).filter_by(status="InReview").all()
    if not tasks:
        await update.message.reply_text("❌ هیچ تسکی در وضعیت بازبینی نیست.")
        session.close()
        return

    for t in tasks:
        dev = session.query(User).get(t.assigned_to)
        if dev:
            dev.total_points += t.story_point
        t.status = "Completed"
        t.reviewed = True
        session.commit()
        await update.message.reply_text(
            f"✅ تسک '{t.title}' تایید شد و {t.story_point} امتیاز به {dev.name} اضافه شد."
        )

    session.close()
