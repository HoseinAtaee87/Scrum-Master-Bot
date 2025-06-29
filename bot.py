from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from database.db import SessionLocal, init_db
from database.models import User
from datetime import datetime
from handlers import admin, developer
import logging
import config


logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.full_name
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()

    if not user:
        user = User(
            telegram_id=user_id,
            name=name,
            role="Developer",
            joined_at=datetime.utcnow(),
            last_login=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        await update.message.reply_text("✅ شما با نقش توسعه‌دهنده ثبت شدید.")
    else:
        user.last_login = datetime.utcnow()
        db.commit()

    buttons = []

    if user.role in ["Developer", "ProductOwner", "CEO"]:
        buttons.append(["🚀 شروع اسپرینت جدید"])
        buttons.append(["📝 ارسال گزارش روزانه"])
        buttons.append(["📌 تسک‌های من"])
        buttons.append(["📌 ارسال تسک برای بازبینی"])
        buttons.append(["شروع تسک"])
        if user.role in ["ProductOwner", "CEO"]:
            buttons.extend([
                ["➕ افزودن پروژه", "📋 لیست پروژه‌ها"],
                ["➕ افزودن تسک به بک‌لاگ"],
                ["📊 گزارش‌ها", "✅ نهایی‌سازی اسپرینت"]
            ])
    if user.role == "CEO":
        buttons.append(["مدیریت کاربران 👥"])

    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(
        f"سلام {user.name} 👋\nنقش شما: {user.role}\nلطفاً یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=markup
    )
    db.close()

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    db = SessionLocal()
    requester = db.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if not requester or requester.role != "CEO":
        await query.edit_message_text("⛔️ فقط مدیرعامل مجاز است.")
        db.close()
        return

    if data.startswith("promote_user_"):
        user_id = int(data.split("_")[-1])
        user = db.query(User).filter_by(id=user_id).first()
        if user:
            if user.role == "Developer":
                user.role = "ProductOwner"
                db.commit()
                await query.edit_message_text(f"✅ {user.name} به مدیر محصول ارتقا یافت.")
            elif user.role == "ProductOwner":
                context.user_data["promote_candidate_id"] = user.id
                await query.edit_message_text(
                    f"❓ ارتقا به CEO؟ این اقدام باعث تنزل مقام شما می‌شود.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ تایید ارتقا به CEO", callback_data="confirm_promote_ceo")],
                        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_promote_ceo")]
                    ])
                )
    elif data == "confirm_promote_ceo":
        promote_id = context.user_data.get("promote_candidate_id")
        if promote_id:
            promoted = db.query(User).filter_by(id=promote_id).first()
            requester.role = "ProductOwner"
            promoted.role = "CEO"
            db.commit()
            await query.edit_message_text(f"🎉 {promoted.name} مدیرعامل شد.")
        context.user_data.pop("promote_candidate_id", None)
    elif data == "cancel_promote_ceo":
        context.user_data.pop("promote_candidate_id", None)
        await query.edit_message_text("❌ ارتقا لغو شد.")
    db.close()

async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()

    if text == "📋 لیست پروژه‌ها":
        return await admin.list_projects(update, context)
    elif text == "➕ افزودن پروژه":
        return await admin.add_project(update, context)
    elif text == "➕ افزودن تسک به بک‌لاگ":
        return await admin.add_task_to_backlog(update, context)  # فرضی، باید تو admin تعریف بشه
    elif text == "📊 گزارش‌ها":
        await update.message.reply_text("یکی از گزینه‌ها:\n- /view_daily_reports\n- /view_sprint_reviews")
    elif text == "✅ نهایی‌سازی اسپرینت":
        return await admin.finalize_sprint(update, context)
    elif text == "مدیریت کاربران 👥":
        return await admin.manage_users(update, context)
    elif text == "📝 ارسال گزارش روزانه":
        return await developer.send_daily_report(update, context)
    elif text == "📌 تسک‌های من":
        return await developer.show_my_tasks(update, context)
    elif text == "📌 ارسال تسک برای بازبینی":
        return await developer.start_task_review(update, context)
    elif text == "🚀 شروع اسپرینت جدید":
        return await developer.start_sprint_creation(update, context)
    elif text == "شروع تسک":
        return await developer.start_task_selection(update, context)
    else:
        await update.message.reply_text("❗ گزینه‌ی نامعتبر.")
    db.close()


def main():
    init_db()
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # ConversationHandlers
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 ارسال گزارش روزانه$"), developer.send_daily_report)],
        states={
            developer.REPORT_COMPLETED: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.daily_report_completed)],
            developer.REPORT_PLANNED: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.daily_report_planned)],
            developer.REPORT_BLOCKERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.daily_report_blockers)],
        },
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📌 ارسال تسک برای بازبینی$"), developer.start_task_review)],
        states={
            developer.TASK_SELECT_REVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.select_task_for_review)],
        },
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^شروع تسک$"), developer.start_task_selection)],
        states={
            developer.SELECT_TASK_TO_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.confirm_task_start)]
        },
        fallbacks=[]
    ))


    app.add_handler(ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^➕ افزودن پروژه$"), admin.add_project)],
    states={
        admin.ADD_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.save_project)],
    },
    fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^➕ افزودن تسک به بک‌لاگ$"), admin.add_task_to_backlog)],
    states={
        admin.SELECT_PROJECT_FOR_BACKLOG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_backlog_tasks)],
        admin.ENTER_BACKLOG_TASKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.save_backlog_tasks)],
    },
    fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚀 شروع اسپرینت جدید$"), developer.start_sprint_creation)],
        states={
            developer.SELECT_PROJECT_FOR_SPRINT_CREATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.show_backlog_tasks)],
            developer.SELECT_TASKS_FOR_SPRINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.collect_tasks_for_sprint)],
        },
        fallbacks=[]
    ))

    # فرمان‌ها و هندلرهای عمومی
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("view_daily_reports", admin.view_daily_reports))
    app.add_handler(CommandHandler("view_sprint_reviews", admin.view_sprint_reviews))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
