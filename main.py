import re
import logging
import mysql.connector
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from scraper import fetch_product_info
import browerScraper
import asyncio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("httpx").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '',  # Add your MySQL password here
    'database': 'basic_telegram_bot'
}

def load_valid_domains(filename="valid_domains.txt"):
    domain_vendor_map = {}
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                domain, vendor = line.split(",", 1)
                domain_vendor_map[domain.strip()] = vendor.strip()
    return domain_vendor_map

def extract_valid_urls(text, domain_vendor_map):
    url_regex = re.compile(r'https?://[^\s]+')
    urls = re.findall(url_regex, text)

    valid_urls = []
    for url in urls:
        for domain, vendor in domain_vendor_map.items():
            if domain in url:
                valid_urls.append((url, vendor))
                break
    return valid_urls

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

async def check_price_drops(app):
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
        vendor = row['vendor']
        curr_notification_count = row['curr_notification_count']
        pid = row['product_id']

        new_name = None
        new_price = None

        if vendor=='amazon':
             new_name, new_price = await price_getter.get_amazon_price(url)
        if vendor=='flipkart':
            new_name, new_price, pid = await price_getter.get_flipkart_price(url, pid)
        if vendor=='myntra':
            new_name, new_price = await price_getter.get_myntra_price(url)
        if vendor=='hmt':
            new_name, new_price = await price_getter.get_hmt_price(url)


        if new_price==None or (new_price and ("out of stock" in new_price.lower() or "currently unavailable" in new_price.lower())):
            continue

        elif float(new_price) < old_price:
            try:
                # Send message to user
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Update Price", callback_data=f"updateprice_{url_id}_{new_price}"),
                        InlineKeyboardButton("❌ Deactivate", callback_data=f"untrack_{url_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await app.bot.send_message(
                    chat_id=user_id,
                    text=f"📉 *{product_name}* has dropped in price!\n\n"
                         f"💰 Old Price: ₹{old_price}\n\n"
                         f"🆕 *Current Price: ₹{new_price}*\n\n"
                         f"🆕 *{url}*",
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )

                # Update notification count & last notified price
                cursor.execute('''
                    UPDATE urls
                    SET notification_count = notification_count + 1,
                        curr_notification_count = curr_notification_count + 1,
                        last_notified_price = %s
                    WHERE id = %s
                ''', (new_price, url_id))
                conn.commit()

                if curr_notification_count+1 >= 3:
                    # Update curr_notification_count & price
                    cursor.execute('''
                                        UPDATE urls
                                        SET curr_notification_count = 0, price = %s
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


price_getter = browerScraper.price_getter(headless=False)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    VALID_DOMAINS = load_valid_domains()
    text = update.message.text.strip()
    print("RECIEVED TEXT :: ", text)
    url_vendor_pairs  = extract_valid_urls(text, VALID_DOMAINS)
    print("VENDOR :: ", url_vendor_pairs)

    if not url_vendor_pairs :
        await update.message.reply_text("⚠️ Invalid link. Please send a product URL from Flipkart, Amazon, etc.")
        return

    for url, vendor in url_vendor_pairs:

        product_name = None
        price = None
        pid = None

        if vendor == 'amazon':
            product_name, price = await price_getter.get_amazon_price(url)
        elif vendor == 'flipkart':
            product_name, price, pid = await price_getter.get_flipkart_price(url)
        elif vendor == 'myntra':
            product_name, price = await price_getter.get_myntra_price(url)
        elif vendor == 'hmt':
            product_name, price = await price_getter.get_hmt_price(url)

        print(product_name, price)

        is_out_of_stock = False
        if price==None:
            await update.message.reply_text("*Unable to fetch the price. Please try again...*", parse_mode="Markdown")
            return

        elif price and ("out of stock" in price.lower() or "currently unavailable" in price.lower()):
            is_out_of_stock = True

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO urls 
            (user_id, url, product_name, price, vendor, is_pending, notification_count, last_notified_price, is_out_of_stock, product_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (user.id, url, product_name, price, vendor, True, 0, price, is_out_of_stock, pid))
        url_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        await update.message.reply_text(
            f"🛍️ *{product_name}*\n💰 Price: ₹ {price}",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

        keyboard = [
            [InlineKeyboardButton("✅ Yes", callback_data=f"track_yes_{url_id}"),
             InlineKeyboardButton("❌ No", callback_data=f"track_no_{url_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Do you want me to track this product?", reply_markup=reply_markup)

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
        _, url_id, new_price = data.split('_')
        url_id = int(url_id)
        new_price = float(new_price)

        cursor.execute('''
            UPDATE urls SET price = %s WHERE id = %s AND user_id = %s
        ''', (new_price, url_id, user.id))
        await query.edit_message_text(f"✅ Price updated to ₹{new_price}")

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

async def periodic_price_check(app):
    while True:
        try:
            await check_price_drops(app)
        except Exception:
            logger.exception("Price checker error")
        await asyncio.sleep(10 * 60)

async def post_init(app):
    await price_getter.start()
    app.bot_data["price_checker_task"] = asyncio.create_task(periodic_price_check(app))

async def post_shutdown(app):
    task = app.bot_data.get("price_checker_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await price_getter.destroy()

def main():
    TOKEN = "1065793060:AAHAN4-svYeyI55Sgh1sm0auImeH7dxUZW8"
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_tracked))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
