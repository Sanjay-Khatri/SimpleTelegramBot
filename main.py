import re
import mysql.connector
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from scraper import fetch_product_info
import asyncio
import threading
import time

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': '',  # Add your MySQL password here
    'database': 'basic_telegram_bot'
}

def load_valid_domains(filename="valid_domains.txt"):
    with open(filename, "r") as f:
        domains = [line.strip() for line in f if line.strip()]
    return domains

def extract_valid_urls(text, valid_domains):
    url_regex = re.compile(r'https?://[^\s]+')
    urls = re.findall(url_regex, text)

    valid_urls = []
    for url in urls:
        for domain in valid_domains:
            if domain in url:
                valid_urls.append(url)
                break
    return valid_urls

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

async def check_price_drops(app):
    print("check_price_drops...")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute('''
        SELECT * FROM urls
        WHERE is_pending = FALSE
    ''')
    active_urls = cursor.fetchall()

    for row in active_urls:
        user_id = row['user_id']
        url = row['url']
        old_price = row['price']
        url_id = row['id']
        product_name = row['product_name']

        new_name, new_price = fetch_product_info(url)

        if new_price < old_price:
            try:
                # Send message to user
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Update Price", callback_data=f"update_price_{url_id}_{new_price}"),
                        InlineKeyboardButton("❌ Deactivate", callback_data=f"untrack_{url_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await app.bot.send_message(
                    chat_id=user_id,
                    text=f"📉 *{product_name}* has dropped in price!\n"
                         f"💰 Old Price: ₹{old_price:.2f}\n"
                         f"🆕 Current Price: ₹{new_price:.2f}",
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )

                # Update notification count & last notified price
                cursor.execute('''
                    UPDATE urls
                    SET notification_count = notification_count + 1,
                        last_notified_price = %s
                    WHERE id = %s
                ''', (new_price, url_id))
                conn.commit()

            except Exception as e:
                print(f"Failed to notify user {user_id} for {url}: {e}")

    cursor.close()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO users (user_id, username, first_name, last_name)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            username = VALUES(username),
            first_name = VALUES(first_name),
            last_name = VALUES(last_name)
    ''', (user.id, user.username, user.first_name, user.last_name))

    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text("👋 Hello! Send a product link to track.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    VALID_DOMAINS = load_valid_domains()
    text = update.message.text.strip()
    valid_urls = extract_valid_urls(text, VALID_DOMAINS)

    if not valid_urls:
        await update.message.reply_text("⚠️ Invalid link. Please send a product URL from Flipkart, Amazon, etc.")
        return

    for url in valid_urls:
        product_name, price = fetch_product_info(url)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO urls (user_id, url, product_name, price, is_pending, notification_count)
            VALUES (%s, %s, %s, %s, TRUE, 0)
        ''', (user.id, url, product_name, price))
        url_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        await update.message.reply_text(
            f"🛍️ *{product_name}*\n💰 Price: ₹{price:.2f}",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

        keyboard = [
            [InlineKeyboardButton("✅ Yes", callback_data=f"track_yes_{url_id}"),
             InlineKeyboardButton("❌ No", callback_data=f"track_no_{url_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Do you want me to track this product?", reply_markup=reply_markup)
    # else:
    #     await update.message.reply_text("⚠️ Invalid link. Please send a product URL from Flipkart, Amazon, etc.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    action, _, url_id = data.partition('_')
    url_id = int(url_id.split('_')[-1])

    conn = get_db_connection()
    cursor = conn.cursor()

    if data.startswith('track_yes_'):
        cursor.execute('''
            SELECT COUNT(*) FROM urls
            WHERE user_id = %s AND is_pending = FALSE
        ''', (user.id,))
        active_count = cursor.fetchone()[0]

        if active_count >= 5:
            await query.edit_message_text("⚠️ You can track 5 products at once. Please turn off one before adding more.")
        else:
            cursor.execute('''
                UPDATE urls SET is_pending = FALSE
                WHERE id = %s AND user_id = %s
            ''', (url_id, user.id))
            await query.edit_message_text("✅ Tracking started.")

    elif data.startswith('track_no_'):
        cursor.execute('''
            UPDATE urls SET is_pending = TRUE
            WHERE id = %s AND user_id = %s
        ''', (url_id, user.id))
        await query.edit_message_text("👍 Alright.")

    elif data.startswith('untrack_'):
        cursor.execute('''
            UPDATE urls SET is_pending = TRUE
            WHERE id = %s AND user_id = %s
        ''', (url_id, user.id))
        await query.edit_message_text("🛑 Tracking turned off.")

    elif data.startswith('updateprice_'):
        product_name, current_price = fetch_product_info_from_db(cursor, url_id)
        cursor.execute('''
            UPDATE urls SET price = %s
            WHERE id = %s AND user_id = %s
        ''', (current_price, url_id, user.id))
        await query.edit_message_text(f"🔄 Price updated to ₹{current_price:.2f}.")

    elif data.startswith('update_price_'):
        _, url_id, new_price = data.split('_')
        url_id = int(url_id)
        new_price = float(new_price)

        cursor.execute('''
            UPDATE urls SET price = %s WHERE id = %s AND user_id = %s
        ''', (new_price, url_id, user.id))
        await query.edit_message_text(f"✅ Price updated to ₹{new_price:.2f}")

    conn.commit()
    cursor.close()
    conn.close()

async def list_tracked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, url, product_name, price FROM urls
        WHERE user_id = %s AND is_pending = FALSE
        ORDER BY id DESC
    ''', (user.id,))
    urls = cursor.fetchall()

    if not urls:
        await update.message.reply_text("📭 No products currently being tracked.")
    else:
        for url_id, url, name, price in urls:
            keyboard = [[InlineKeyboardButton("🛑 Turn Off Tracking", callback_data=f"untrack_{url_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"🛒 *{name}*\n🔗 {url}\n💰 ₹{price:.2f}",
                parse_mode="Markdown",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

    cursor.close()
    conn.close()

def fetch_product_info_from_db(cursor, url_id):
    cursor.execute('SELECT url FROM urls WHERE id = %s', (url_id,))
    result = cursor.fetchone()
    if result:
        url = result[0]
        return fetch_product_info(url)
    return "Unknown", 0.0

async def check_price_drops(app):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, user_id, url, product_name, price FROM urls
        WHERE is_pending = FALSE
    ''')
    urls = cursor.fetchall()

    for url_id, user_id, url, name, old_price in urls:
        new_name, new_price = fetch_product_info(url)
        if new_price < old_price:
            cursor.execute('''
                UPDATE urls SET notification_count = notification_count + 1
                WHERE id = %s
            ''', (url_id,))

            keyboard = [
                [InlineKeyboardButton("🔄 Update Price", callback_data=f"updateprice_{url_id}"),
                 InlineKeyboardButton("🛑 Deactivate", callback_data=f"untrack_{url_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=f"📉 Price Drop Alert!\n🛒 *{new_name}*\n💰 Now: ₹{new_price:.2f}",
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            except Exception as e:
                print(f"Failed to notify user {user_id}: {e}")

    conn.commit()
    cursor.close()
    conn.close()

def run_price_checker(app):
    async def periodic_price_check():
        while True:
            await check_price_drops(app)
            await asyncio.sleep(3600)

    # Each thread needs its own event loop
    asyncio.run(periodic_price_check())

def main():
    TOKEN = "1065793060:AAHAN4-svYeyI55Sgh1sm0auImeH7dxUZW8"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_tracked))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Start the background thread for price check
    t = threading.Thread(target=run_price_checker, args=(app,), daemon=True)
    t.start()

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()