import logging
import os
import json
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
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

# Initialize FastAPI app
app = FastAPI()

# Initialize Telegram Application
ptb_application = ApplicationBuilder().token(TOKEN).build()

async def get_main_menu_keyboard():
    """Return the main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("➕ New Question", callback_data="menu_new")],
        [InlineKeyboardButton("📊 View Results", callback_data="menu_results")],
        [InlineKeyboardButton("⚙️ Register Group", callback_data="menu_register")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    reply_markup = await get_main_menu_keyboard()
    
    msg = (
        rf"Hi {user.mention_html()}! I'm the Sunday School Poll Bot. "
        "I can help you create questions and post them as native polls in your group.\n\n"
        "Please select an option below:"
    )
    
    if update.message:
        await update.message.reply_html(msg, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='HTML')

async def handle_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu button clicks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "menu_new":
        await query.edit_message_text("What is the question you want to ask?")
        return QUESTION
    elif query.data == "menu_results":
        await view_results(update, context)
    elif query.data == "menu_register":
        await query.edit_message_text("To register a group, add me to the group as an admin and send /register there.")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register a group chat or a specific topic."""
    chat = update.effective_chat
    thread_id = update.effective_message.message_thread_id
    
    if chat.type in [chat.GROUP, chat.SUPERGROUP]:
        title = chat.title
        if thread_id:
            # Try to get the topic name if possible, otherwise just use the chat title
            title = f"{chat.title} (Topic)"
            database.register_group(chat.id, title, thread_id)
            await update.message.reply_text(f"Topic in '{chat.title}' has been registered successfully!")
        else:
            database.register_group(chat.id, title)
            await update.message.reply_text(f"Group '{chat.title}' has been registered successfully!")
    else:
        await update.message.reply_text("This command can only be used in a group.")

# --- Question Creation Conversation ---

async def new_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the question creation process."""
    # Check if it's a private chat
    chat = update.effective_chat
    if chat.type != chat.PRIVATE:
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
        await update.message.reply_text("Max 10 options allowed. Please reduce the number of options.")
        return OPTIONS
    
    context.user_data['options'] = options
    
    # Create buttons for selecting the correct answer
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"correct_{i}")] for i, opt in enumerate(options)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Which one is the correct answer?", reply_markup=reply_markup)
    return CORRECT_ANSWER

async def get_correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store the correct answer and ask which group to post to."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['correct_option_id'] = int(query.data.split('_')[1])
    
    groups = database.get_registered_groups()
    if not groups:
        await query.edit_message_text("No groups registered. Please use /register in a group first.")
        return ConversationHandler.END
    
    # callback_data format: group_{chat_id}_{thread_id}
    keyboard = []
    for cid, title, tid in groups:
        tid_str = str(tid) if tid else "none"
        keyboard.append([InlineKeyboardButton(title, callback_data=f"group_{cid}_{tid_str}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("Select the group/topic to post this poll to:", reply_markup=reply_markup)
    return SELECT_GROUP

async def post_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Post the poll to the selected group/topic."""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    chat_id = int(parts[1])
    thread_id = int(parts[2]) if parts[2] != "none" else None
    
    question_text = context.user_data['question_text']
    options = context.user_data['options']
    correct_option_id = context.user_data['correct_option_id']
    
    # Save to DB first to get an ID
    q_id = database.add_question(update.effective_user.id, question_text, options, correct_option_id)
    
    try:
        # Reverting to native Telegram Poll
        message = await context.bot.send_poll(
            chat_id=chat_id,
            message_thread_id=thread_id,
            question=question_text,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False,
            type=Poll.QUIZ,
            correct_option_id=correct_option_id
        )
        
        database.update_question_poll(q_id, message.poll.id, chat_id, message.message_id)
        
        await query.edit_message_text(f"Native Poll posted to the group! Poll ID: {message.poll.id}")
        # Show main menu again
        reply_markup = await get_main_menu_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text="What would you like to do next?", reply_markup=reply_markup)
    except Exception as e:
        logging.error(f"Error posting poll: {e}")
        await query.edit_message_text(f"Failed to post poll. Error: {e}")
    
    return ConversationHandler.END

async def receive_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle native poll answers."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    
    logging.info(f"Received poll answer: poll_id={poll_id}, user={user.full_name}, options={answer.option_ids}")
    
    if answer.option_ids is not None:
        # If option_ids is empty, it means the user retracted their vote
        if not answer.option_ids:
            logging.info(f"User {user.full_name} retracted their vote for poll {poll_id}")
            # Optional: remove from DB or mark as retracted
            return

        option_id = answer.option_ids[0]
        database.save_answer(poll_id, user.id, user.full_name, option_id)
        logging.info(f"Saved native poll answer for {poll_id} from {user.full_name} (Option {option_id})")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    await update.message.reply_text("Action cancelled.")
    reply_markup = await get_main_menu_keyboard()
    await update.message.reply_text("Back to main menu:", reply_markup=reply_markup)
    return ConversationHandler.END

# --- Results ---

async def view_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show results of questions created by the user."""
    user_id = update.effective_user.id
    questions = database.get_user_questions(user_id)
    
    if not questions:
        msg = "You haven't posted any polls yet."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    text = "📊 <b>Sunday School Poll Results</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    found_any = False
    for q_id, q_text, poll_id in questions:
        found_any = True
        results = database.get_results(poll_id)
        q_data = database.get_question_by_poll_id(poll_id)
        
        if not q_data: 
            logging.warning(f"No question data found for poll_id {poll_id}")
            continue

        correct_count = 0
        total_votes = len(results)
        
        text += f"❓ <b>Question:</b> {q_text}\n"
        text += f"📝 <b>Options:</b>\n"
        for i, opt in enumerate(q_data['options']):
            marker = "✅" if i == q_data['correct_option_id'] else "🔹"
            text += f"  {marker} {opt}\n"
        
        text += f"\n👥 <b>Votes ({total_votes}):</b>\n"
        if total_votes == 0:
            text += "  <i>No votes recorded yet.</i>\n"
        else:
            for user_name, opt_id in results:
                is_correct = "✅" if opt_id == q_data['correct_option_id'] else "❌"
                if opt_id == q_data['correct_option_id']:
                    correct_count += 1
                
                # Get the text of the chosen option
                chosen_option_text = q_data['options'][opt_id] if opt_id < len(q_data['options']) else "Unknown"
                text += f"  • {user_name}: <b>{chosen_option_text}</b> {is_correct}\n"
            
            percentage = (correct_count / total_votes) * 100 if total_votes > 0 else 0
            text += f"\n📈 <b>Summary:</b> {correct_count}/{total_votes} correct ({percentage:.1f}%)\n"
        
        text += "\n" + "━" * 20 + "\n\n"
    
    if not found_any:
        text = "You haven't posted any polls yet."

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML')
        # Show main menu again
        reply_markup = await get_main_menu_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text="What would you like to do next?", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='HTML')

# --- Setup Application ---

def setup_application():
    """Configure the Telegram application handlers."""
    database.init_db()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("newquestion", new_question),
            CallbackQueryHandler(handle_menu_click, pattern="^menu_new$")
        ],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_options)],
            CORRECT_ANSWER: [CallbackQueryHandler(get_correct_answer, pattern="^correct_")],
            SELECT_GROUP: [CallbackQueryHandler(post_poll, pattern="^group_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    ptb_application.add_handler(CommandHandler("start", start))
    ptb_application.add_handler(CommandHandler("register", register))
    ptb_application.add_handler(CommandHandler("results", view_results))
    ptb_application.add_handler(conv_handler)
    ptb_application.add_handler(CallbackQueryHandler(handle_menu_click, pattern="^menu_"))
    ptb_application.add_handler(PollAnswerHandler(receive_poll_answer))
    
    return ptb_application

# Initialize handlers once
setup_application()

# --- FastAPI Endpoints ---

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates via Webhook."""
    try:
        data = await request.json()
        update = Update.de_json(data, ptb_application.bot)
        
        async with ptb_application:
            await ptb_application.process_update(update)
            
        return Response(status_code=200)
    except Exception as e:
        logging.error(f"Error processing update: {e}")
        return Response(status_code=500)

@app.get("/")
async def index():
    return {"status": "Bot is running"}

# For local testing
if __name__ == "__main__":
    import uvicorn
    if os.getenv("RUN_POLLING", "false").lower() == "true":
        logging.info("Starting bot in POLLING mode for local testing...")
        ptb_application.run_polling()
    else:
        logging.info("Starting bot in WEBHOOK mode (FastAPI)...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
