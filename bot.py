import logging
import os
import json
from dotenv import load_dotenv
from telegram import Update, Poll, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    PollAnswerHandler,
    CallbackQueryHandler,
)
import database

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Conversation states
QUESTION, OPTIONS, CORRECT_ANSWER, SELECT_GROUP = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! I'm the Sunday School Poll Bot. "
        "I can help you create questions and post them as polls in your group.\n\n"
        "<b>Commands:</b>\n"
        "/newquestion - Create a new question (Private Chat only)\n"
        "/results - View results of your posted questions\n"
        "/register - Register this group (Group Chat only)"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register a group chat."""
    chat = update.effective_chat
    if chat.type in [chat.GROUP, chat.SUPERGROUP]:
        database.register_group(chat.id, chat.title)
        await update.message.reply_text(f"Group '{chat.title}' has been registered successfully!")
    else:
        await update.message.reply_text("This command can only be used in a group.")

# --- Question Creation Conversation ---

async def new_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the question creation process."""
    if update.effective_chat.type != update.effective_chat.PRIVATE:
        await update.message.reply_text("Please use /newquestion in a private chat with me.")
        return ConversationHandler.END

    await update.message.reply_text("What is the question you want to ask?")
    return QUESTION

async def get_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store the question text and ask for options."""
    context.user_data['question_text'] = update.message.text
    await update.message.reply_text(
        "Great! Now send me the options, separated by a new line. (Max 10 options)"
    )
    return OPTIONS

async def get_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store the options and ask for the correct answer."""
    options = update.message.text.split('\n')
    if len(options) < 2:
        await update.message.reply_text("Please provide at least 2 options.")
        return OPTIONS
    if len(options) > 10:
        await update.message.reply_text("Telegram polls only support up to 10 options. Please reduce the number of options.")
        return OPTIONS
    
    context.user_data['options'] = options
    
    # Create buttons for selecting the correct answer
    keyboard = [[InlineKeyboardButton(opt, callback_data=str(i))] for i, opt in enumerate(options)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Which one is the correct answer?", reply_markup=reply_markup)
    return CORRECT_ANSWER

async def get_correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store the correct answer and ask which group to post to."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['correct_option_id'] = int(query.data)
    
    groups = database.get_registered_groups()
    if not groups:
        await query.edit_message_text("No groups registered. Please use /register in a group first.")
        return ConversationHandler.END
    
    keyboard = [[InlineKeyboardButton(title, callback_data=f"group_{cid}")] for cid, title in groups]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("Select the group to post this poll to:", reply_markup=reply_markup)
    return SELECT_GROUP

async def post_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Post the poll to the selected group."""
    query = update.callback_query
    await query.answer()
    
    chat_id = int(query.data.split('_')[1])
    question_text = context.user_data['question_text']
    options = context.user_data['options']
    correct_option_id = context.user_data['correct_option_id']
    
    # Save to DB first to get an ID (though we update it later with poll_id)
    q_id = database.add_question(update.effective_user.id, question_text, options, correct_option_id)
    
    try:
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False,
            type=Poll.QUIZ,
            correct_option_id=correct_option_id
        )
        
        database.update_question_poll(q_id, message.poll.id, chat_id, message.message_id)
        await query.edit_message_text(f"Poll posted to the group! Poll ID: {message.poll.id}")
    except Exception as e:
        logging.error(f"Error posting poll: {e}")
        await query.edit_message_text(f"Failed to post poll. Make sure I am an admin in the group. Error: {e}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    await update.message.reply_text("Question creation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- Poll Answer Handling ---

async def receive_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarize a users poll vote."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    
    # Telegram sends option_ids as a list
    if answer.option_ids:
        option_id = answer.option_ids[0]
        database.save_answer(poll_id, user.id, user.full_name, option_id)
        logging.info(f"Saved answer for poll {poll_id} from user {user.full_name}")

# --- Results ---

async def view_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show results of questions created by the user."""
    user_id = update.effective_user.id
    questions = database.get_user_questions(user_id)
    
    if not questions:
        await update.message.reply_text("You haven't posted any polls yet.")
        return

    text = "<b>Your Poll Results:</b>\n\n"
    for q_id, q_text, poll_id in questions:
        results = database.get_results(poll_id)
        q_data = database.get_question_by_poll_id(poll_id)
        
        correct_count = 0
        total_votes = len(results)
        
        text += f"❓ <b>{q_text}</b>\n"
        if total_votes == 0:
            text += "No votes yet.\n\n"
            continue
            
        for user_name, opt_id in results:
            is_correct = "✅" if opt_id == q_data['correct_option_id'] else "❌"
            if opt_id == q_data['correct_option_id']:
                correct_count += 1
            text += f"- {user_name}: {q_data['options'][opt_id]} {is_correct}\n"
        
        text += f"Summary: {correct_count}/{total_votes} correct\n\n"
    
    await update.message.reply_text(text, parse_mode='HTML')

def main():
    """Start the bot."""
    database.init_db()
    
    application = ApplicationBuilder().token(TOKEN).build()

    # Conversation handler for creating questions
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("newquestion", new_question)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_options)],
            CORRECT_ANSWER: [CallbackQueryHandler(get_correct_answer)],
            SELECT_GROUP: [CallbackQueryHandler(post_poll, pattern="^group_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("results", view_results))
    application.add_handler(conv_handler)
    application.add_handler(PollAnswerHandler(receive_poll_answer))

    application.run_polling()

if __name__ == '__main__':
    main()
