# bot.py

import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
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

    # ساخت منو
    buttons = []
    if user.role in ["Developer", "ProductOwner", "CEO"]:
        buttons += [
            ["🚀 افزودن تسک جدید"],
            ["📝 ارسال گزارش روزانه"],
            ["📌 تسک‌های من"],
            ["📌 ارسال تسک برای بازبینی"],
            ["🧐 بازبینی تسک‌ها"],
            ["شروع تسک"]
        ]
    if user.role in ["ProductOwner", "CEO"]:
        buttons += [
            ["➕ افزودن پروژه", "📋 لیست پروژه‌ها"],
            ["➕ افزودن تسک به بک‌لاگ"],
            ["📊 گزارش‌ها", "✅ نهایی‌سازی اسپرینت"]
        ]
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

    # ارتقا/تنزل کاربر
    if data.startswith("promote_user_"):
        uid = int(data.split("_")[-1])
        user = db.query(User).filter_by(id=uid).first()
        if user and user.role == "Developer":
            user.role = "ProductOwner"
            db.commit()
            await query.edit_message_text(f"✅ {user.name} به مدیر محصول ارتقا یافت.")
        elif user and user.role == "ProductOwner":
            context.user_data["promote_candidate_id"] = user.id
            await query.edit_message_text(
                "❓ ارتقا به CEO؟ این اقدام باعث تنزل مقام شما می‌شود.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ تایید", callback_data="confirm_promote_ceo"),
                    InlineKeyboardButton("❌ انصراف", callback_data="cancel_promote_ceo")
                ]])
            )
    elif data == "confirm_promote_ceo":
        pid = context.user_data.pop("promote_candidate_id", None)
        if pid:
            promoted = db.query(User).filter_by(id=pid).first()
            requester.role = "ProductOwner"
            promoted.role = "CEO"
            db.commit()
            await query.edit_message_text(f"🎉 {promoted.name} مدیرعامل جدید شد.")
    elif data == "cancel_promote_ceo":
        context.user_data.pop("promote_candidate_id", None)
        await query.edit_message_text("❌ ارتقا لغو شد.")

    db.close()

async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # انصراف به منوی اصلی
    if text == "🔙 انصراف":
        return await start(update, context)

    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()

    # مسیردهی گزینه‌ها
    if text == "📋 لیست پروژه‌ها":
        db.close()
        return await admin.list_projects(update, context)
    elif text == "➕ افزودن پروژه":
        db.close()
        return await admin.add_project(update, context)
    elif text == "➕ افزودن تسک به بک‌لاگ":
        db.close()
        return await admin.add_task_to_backlog(update, context)
    elif text == "📊 گزارش‌ها":
        db.close()
        await update.message.reply_text("یکی از گزینه‌ها:\n- /view_daily_reports\n- /view_sprint_reviews")
    elif text == "✅ نهایی‌سازی اسپرینت":
        db.close()
        return await admin.finalize_sprint(update, context)
    elif text == "مدیریت کاربران 👥":
        db.close()
        return await admin.manage_users(update, context)
    elif text == "📝 ارسال گزارش روزانه":
        db.close()
        return await developer.send_daily_report(update, context)
    elif text == "📌 تسک‌های من":
        db.close()
        return await developer.show_my_tasks(update, context)
    elif text == "📌 ارسال تسک برای بازبینی":
        db.close()
        return await developer.start_task_review(update, context)
    elif text == "🧐 بازبینی تسک‌ها":
        db.close()
        return await admin.review_tasks(update, context)
    elif text == "🚀 افزودن تسک جدید":
        db.close()
        return await developer.start_sprint_creation(update, context)
    elif text == "شروع تسک":
        db.close()
        return await developer.start_task_selection(update, context)
    else:
        db.close()
        await update.message.reply_text("❗ گزینه‌ی نامعتبر.")

def main():
    init_db()
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # گزارش روزانه
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 ارسال گزارش روزانه$"), developer.send_daily_report)],
        states={
            developer.REPORT_COMPLETED: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.daily_report_completed)],
            developer.REPORT_PLANNED:   [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.daily_report_planned)],
            developer.REPORT_BLOCKERS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.daily_report_blockers)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🔙 انصراف$"), start)]
    ))

    # ارسال تسک برای بازبینی
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📌 ارسال تسک برای بازبینی$"), developer.start_task_review)],
        states={
            developer.TASK_SELECT_REVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.select_task_for_review)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ انصراف$"), start)]
    ))

    # شروع تسک
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^شروع تسک$"), developer.start_task_selection)],
        states={
            developer.SELECT_TASK_TO_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.confirm_task_start)]
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ انصراف$"), start)]
    ))

    # افزودن پروژه
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ افزودن پروژه$"), admin.add_project)],
        states={admin.ADD_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.save_project)]},
        fallbacks=[MessageHandler(filters.Regex("^🔙 انصراف$"), start)]
    ))

    # افزودن تسک به بک‌لاگ
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ افزودن تسک به بک‌لاگ$"), admin.add_task_to_backlog)],
        states={
            admin.SELECT_PROJECT_FOR_BACKLOG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_backlog_tasks)],
            admin.ENTER_BACKLOG_TASKS:        [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.save_backlog_tasks)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🔙 انصراف$"), start)]
    ))

    # ساخت اسپرینت (افزودن تسک جدید)
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚀 افزودن تسک جدید$"), developer.start_sprint_creation)],
        states={
            developer.SELECT_PROJECT_FOR_SPRINT_CREATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.show_backlog_tasks)],
            developer.SELECT_TASKS_FOR_SPRINT:            [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.collect_tasks_for_sprint)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🔙 انصراف$"), start)]
    ))
    
    # داخل main() بعد از سایر ConversationHandlers:
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🧐 بازبینی تسک‌ها$"), developer.start_review_tasks)],
        states={
            developer.REVIEW_SELECT_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.review_select_task)],
            developer.REVIEW_DECISION:    [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.review_decision)],
            developer.REVIEW_REASON:      [MessageHandler(filters.TEXT & ~filters.COMMAND, developer.review_reason)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🔙 انصراف$"), developer.start_review_tasks)]
    ))


    # دستورهای تکمیلی
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("view_daily_reports", admin.view_daily_reports))
    app.add_handler(CommandHandler("view_sprint_reviews", admin.view_sprint_reviews))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
