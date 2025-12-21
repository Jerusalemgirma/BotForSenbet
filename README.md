# Sunday School Poll Bot

A Telegram bot to create questions, post them as non-anonymous polls in a group, and track individual answers.

## Features
- Create questions with up to 10 options.
- Post polls to registered groups.
- Track individual user votes (non-anonymous).
- View a summary of results for each poll.

## Setup

1. **Get a Bot Token:**
   - Message [@BotFather](https://t.me/BotFather) on Telegram.
   - Create a new bot and copy the API Token.

2. **Configure Environment:**
   - Rename `.env.example` to `.env`.
   - Paste your bot token into the `TELEGRAM_BOT_TOKEN` field.

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Bot:**
   ```bash
   python bot.py
   ```

## Usage

1. **Register a Group:**
   - Add the bot to your Telegram group.
   - Make the bot an **Admin** (required to send polls).
   - Send `/register` in the group.

2. **Create a Question:**
   - Send `/newquestion` to the bot in a **Private Chat**.
   - Follow the prompts to enter the question, options, and correct answer.
   - Select the registered group to post the poll.

3. **View Results:**
   - Send `/results` to the bot in a **Private Chat**.
   - You will see a list of your polls and who answered what.
