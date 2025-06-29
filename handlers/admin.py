from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.db import SessionLocal
from database.models import User, Project, Sprint, Task
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ============================
# Conversation States
# ============================
ADD_PROJECT_NAME = 1
SELECT_PROJECT, ENTER_START_DATE, ENTER_END_DATE = range(2, 5)
SELECT_PROJECT_FOR_TASK, SELECT_SPRINT_FOR_TASK, ENTER_TASK_TITLE, ENTER_TASK_DESCRIPTION = range(5, 9)
SELECT_PROJECT_FOR_BACKLOG, ENTER_BACKLOG_TASKS = range(20, 22)

# ============================
# Add Project
# ============================
async def add_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("دسترسی فقط برای مدیر محصول امکان‌پذیر است.")
        session.close()
        return ConversationHandler.END

    await update.message.reply_text("📝 لطفاً نام پروژه جدید را وارد کنید:")
    session.close()
    return ADD_PROJECT_NAME

async def save_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    name = update.message.text.strip()
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
    tg_id = update.effective_user.id
    user = session.query(User).filter_by(telegram_id=tg_id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("شما دسترسی به این دستور ندارید.")
        session.close()
        return

    projects = session.query(Project).filter_by(created_by=user.id).all()
    if not projects:
        await update.message.reply_text("هیچ پروژه‌ای ثبت نشده است.")
    else:
        response = "📋 لیست پروژه‌های شما:\n\n"
        for p in projects:
            response += f"🔹 {p.name} | ساخته‌شده در: {p.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        await update.message.reply_text(response)

    session.close()


# ============================
# Add Task to Sprint
# ============================
async def add_task_to_backlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("شما دسترسی به این دستور ندارید.")
        session.close()
        return ConversationHandler.END

    projects = session.query(Project).filter_by(created_by=user.id).all()
    if not projects:
        await update.message.reply_text("❌ شما هیچ پروژه‌ای ندارید.")
        session.close()
        return ConversationHandler.END

    context.user_data["project_map"] = {p.name: p.id for p in projects}
    keyboard = [[p.name] for p in projects]
    await update.message.reply_text("📋 یک پروژه را برای افزودن تسک به بک‌لاگ انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    session.close()
    return SELECT_PROJECT_FOR_BACKLOG

async def receive_backlog_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    selected = update.message.text.strip()
    project_id = context.user_data["project_map"].get(selected)

    if not project_id:
        await update.message.reply_text("❌ پروژه نامعتبر است.")
        session.close()
        return ConversationHandler.END

    context.user_data["selected_project_id"] = project_id
    await update.message.reply_text("✍️ تسک‌های بک‌لاگ را وارد کنید.\n\nفرمت:\nتسک1    2\nتسک2    1\nتسک3    3")
    session.close()
    return ENTER_BACKLOG_TASKS

async def save_backlog_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    text = update.message.text.strip()
    project_id = context.user_data["selected_project_id"]

    lines = text.split("\n")
    success_count = 0
    for line in lines:
        if not line.strip():
            continue
        parts = line.strip().rsplit(maxsplit=1)
        if len(parts) != 2:
            continue
        title, point_str = parts
        try:
            point = int(point_str)
        except ValueError:
            continue

        task = Task(
            project_id=project_id,
            title=title.strip(),
            story_point=point,
            status="Backlog",
            created_at=datetime.now()
        )
        session.add(task)
        success_count += 1

    session.commit()
    session.close()
    await update.message.reply_text(f"✅ {success_count} تسک به بک‌لاگ پروژه اضافه شد.")
    return ConversationHandler.END


# ============================
# Review Tasks (Admin)
# ============================
async def review_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("شما به این بخش دسترسی ندارید.")
        session.close()
        return

    tasks = session.query(Task).filter(Task.status == 'InReview').all()
    if not tasks:
        await update.message.reply_text("هیچ تسکی در وضعیت بازبینی وجود ندارد.")
        session.close()
        return

    for task in tasks:
        status_text = f"📌 عنوان: {task.title}\n📝 توضیحات: {task.description}\n👤 شناسه توسعه‌دهنده: {task.assigned_to}\n📅 تاریخ: {task.created_at.strftime('%Y-%m-%d')}"
        await update.message.reply_text(status_text)

    session.close()
    await update.message.reply_text("تمام تسک‌های در حال بازبینی نمایش داده شدند.")

# ============================
# View Daily Reports (Admin)
# ============================
async def view_daily_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from database.models import DailyReport  # import here if not already
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("شما دسترسی به این بخش ندارید.")
        session.close()
        return

    reports = session.query(DailyReport).order_by(DailyReport.report_date.desc()).limit(5).all()
    if not reports:
        await update.message.reply_text("هیچ گزارشی ثبت نشده است.")
        session.close()
        return

    for report in reports:
        rep = f"📅 {report.report_date}\n👤 توسعه‌دهنده ID: {report.user_id}\n✅ انجام‌شده‌ها: {report.completed_tasks}\n📌 برنامه امروز: {report.planned_tasks}\n🚫 موانع: {report.blockers}"
        await update.message.reply_text(rep)

    session.close()
    await update.message.reply_text("تمام گزارش‌های روزانه‌ی اخیر نمایش داده شدند.")

# ============================
# View Sprint Review Reports
# ============================
async def view_sprint_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from database.models import SprintReview
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("دسترسی محدود است. فقط مدیر محصول مجاز است.")
        session.close()
        return

    reviews = session.query(SprintReview).order_by(SprintReview.review_date.desc()).limit(5).all()
    if not reviews:
        await update.message.reply_text("هیچ گزارش اسپرینت ریویویی ثبت نشده است.")
        session.close()
        return

    for review in reviews:
        text = f"🗓️ تاریخ: {review.review_date}\n🧩 اسپرینت ID: {review.sprint_id}\n📄 توضیحات: {review.notes}\n📊 درصد انجام‌شده: {review.completed_percentage}%"
        await update.message.reply_text(text)

    session.close()
    await update.message.reply_text("نمایش گزارش‌های اسپرینت ریویو به پایان رسید.")

# ============================
# Finalize Sprint & Create Retrospective
# ============================
async def finalize_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from database.models import Retrospective
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("دسترسی محدود است.")
        session.close()
        return

    active_sprints = session.query(Sprint).filter_by(status="Active").all()
    if not active_sprints:
        await update.message.reply_text("هیچ اسپرینت فعالی وجود ندارد.")
        session.close()
        return

    for s in active_sprints:
        s.status = "Completed"
        retro = Retrospective(
            sprint_id=s.id,
            held_by=user.id,
            retro_date=datetime.now(),
            discussion_points="جمع‌بندی خودکار ربات."
        )
        session.add(retro)

    session.commit()
    session.close()
    await update.message.reply_text("✅ تمامی اسپرینت‌های فعال بسته شدند و جلسه رتروسپکتیو ثبت شد.")



# ============================
# CEO: Manage Users
# ============================
async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role != "CEO":
        await update.message.reply_text("❌ فقط مدیرعامل (CEO) می‌تواند به این بخش دسترسی داشته باشد.")
        session.close()
        return

    users = session.query(User).filter(User.role.in_(["Developer", "ProductOwner"])).all()
    if not users:
        await update.message.reply_text("هیچ کاربری برای مدیریت یافت نشد.")
        session.close()
        return

    for u in users:
        text = f"👤 {u.name} - نقش فعلی: {u.role}"
        buttons = [
            InlineKeyboardButton("⬆️ ارتقا به مدیر", callback_data=f"promote_user_{u.id}") if u.role == "Developer" else None,
            InlineKeyboardButton("❌ حذف", callback_data=f"remove_user_{u.id}") if u.role == "ProductOwner" else None
        ]
        buttons = [btn for btn in buttons if btn]
        markup = InlineKeyboardMarkup.from_column(buttons)
        await update.message.reply_text(text, reply_markup=markup)

    session.close()


async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role != "CEO":
        await update.message.reply_text("❌ فقط مدیرعامل (CEO) می‌تواند به این بخش دسترسی داشته باشد.")
        session.close()
        return

    users = session.query(User).filter(User.role.in_(["Developer", "ProductOwner"])).all()
    if not users:
        await update.message.reply_text("هیچ کاربری برای مدیریت یافت نشد.")
        session.close()
        return

    for u in users:
        text = f"👤 {u.name} - نقش فعلی: {u.role}"
        buttons = []

        if u.role == "Developer":
            buttons.append(InlineKeyboardButton("⬆️ ارتقا به مدیر", callback_data=f"promote_user_{u.id}"))
        elif u.role == "ProductOwner":
            buttons.append(InlineKeyboardButton("⬆️ ارتقا به CEO", callback_data=f"promote_user_{u.id}"))
            buttons.append(InlineKeyboardButton("⬇️ تنزل به توسعه‌دهنده", callback_data=f"demote_user_{u.id}"))
            buttons.append(InlineKeyboardButton("❌ حذف", callback_data=f"remove_user_{u.id}"))

        markup = InlineKeyboardMarkup.from_column(buttons)
        await update.message.reply_text(text, reply_markup=markup)

    session.close()


async def approve_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not user or user.role not in ["ProductOwner", "CEO"]:
        await update.message.reply_text("دسترسی ندارید.")
        session.close()
        return

    tasks = session.query(Task).filter_by(status="InReview").all()
    if not tasks:
        await update.message.reply_text("هیچ تسکی در وضعیت بازبینی نیست.")
        session.close()
        return

    for task in tasks:
        developer = session.query(User).filter_by(id=task.assigned_to).first()
        if developer:
            developer.total_points += task.story_point

        task.status = "Completed"
        task.reviewed = True
        session.commit()

        await update.message.reply_text(
            f"✅ تسک '{task.title}' تایید شد و {task.story_point} امتیاز به {developer.name} اضافه شد."
        )

    session.close()
