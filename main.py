import os
import logging
from pymongo import MongoClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s', level=logging.INFO)

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://surajAura:AuraArjun@kovai.8gwiq.mongodb.net/TBot?retryWrites=true&w=majority')  # Replace with your MongoDB URI
client = MongoClient(MONGO_URI)
db = client['TBot']
users_collection = db['Users']

# List of required channel usernames
REQUIRED_CHANNELS = ['@IncomeLootOfficial', '@Share2EarnAnnouncement', '@Share2EarnUpdates', '@AbhiTrendzDeals', '@DailyCampaignZone', '@DailyEarningSathi']

app = FastAPI()
bot = Bot(token="7903693809:AAGLtWfXJZfn_4kfOqlQHdVDUWAts5nGcMA")  # Replace with your actual bot token

def capitalize_words(text):
    """Capitalize each word in the given text."""
    return ' '.join(word.capitalize() for word in text.split())

def generate_referral_link(user_id):
    """Generate a unique referral link for the user."""
    return f"https://t.me/Share2EarnCash_bot?start={user_id}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    
    # Check if there's a referral code in the URL
    referrer_id = context.args[0] if context.args else None

    # Generate referral link
    referral_link = generate_referral_link(user_id)

    # Check if the user already exists in the database
    user = users_collection.find_one({"user_id": user_id})

    if user:
        initial_balance = user.get('balance', 0)
    else:
        initial_balance = 3  # Initial balance for new users

    update_data = {
        "username": username,
        "balance": initial_balance,
        "upi_id": None,
        "referral_link": referral_link,
        "referred_by": None
    }

    if not user:
        # Register new user
        users_collection.insert_one({"user_id": user_id, **update_data})
    else:
        # Update existing user
        users_collection.update_one({"user_id": user_id}, {"$set": update_data})

    if referrer_id and (not user or user['user_id'] != int(referrer_id)):
        try:
            referrer = users_collection.find_one({"user_id": int(referrer_id)})
            if referrer:
                # Update referred user's 'referred_by'
                users_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"referred_by": int(referrer_id)}}
                )

                # Now check if the referred user has joined all channels
                all_joined = True
                for channel in REQUIRED_CHANNELS:
                    member_status = await context.bot.get_chat_member(channel, user_id)
                    if member_status.status not in ['member', 'administrator', 'creator']:
                        all_joined = False
                        break

                if all_joined:
                    # Update referrer's balance
                    users_collection.update_one(
                        {"user_id": int(referrer_id)},
                        {"$inc": {"balance": 2}}
                    )
                    await context.bot.send_message(chat_id=int(referrer_id), text="You have earned a reward for referring a new user!")

        except Exception as e:
            logging.error(f"Error updating referrer's balance: {e}")

    # The rest of your existing start function...


    # After registering the user, prompt them to join channels (same as before)
    buttons = [
        [InlineKeyboardButton("Join ", url=f"https://t.me/{channel[1:]}") for channel in REQUIRED_CHANNELS[:2]],
        [InlineKeyboardButton("Join ", url=f"https://t.me/{channel[1:]}") for channel in REQUIRED_CHANNELS][2:4],
        [InlineKeyboardButton("Join ", url=f"https://t.me/{channel[1:]}") for channel in REQUIRED_CHANNELS[4:]],
        [InlineKeyboardButton("Check Joined", callback_data='check_membership')]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    message = await update.message.reply_text(capitalize_words("Please Join The Following Channels To Use The Bot:"), reply_markup=reply_markup)
    
    context.user_data['join_channels_message_id'] = message.message_id




# Show available commands function - only called after confirming channel membership
async def show_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id if update.callback_query else update.message.from_user.id
    
    # Create a custom keyboard with command buttons
    command_buttons = [
        ["Balance", "Bonus Task"],
        ["Refer", "Link UPI"],
        ["Withdraw"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(command_buttons, one_time_keyboard=True, resize_keyboard=True)

    if update.callback_query:
        await context.bot.send_message(chat_id=user_id, text="You Can Now Use The Bot. Here Are The Available Commands:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("You Can Now Use The Bot. Here Are The Available Commands:", reply_markup=reply_markup)

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.callback_query.from_user.id if update.callback_query else update.message.from_user.id
    
    responses = []
    all_joined = True  # Track if the user has joined all channels

    for channel in REQUIRED_CHANNELS:
        try:
            member_status = await context.bot.get_chat_member(channel, user_id)
            if member_status.status not in ['member', 'administrator', 'creator']:
                all_joined = False
                responses.append(f"{channel}: Not Joined")
        except Exception as e:
            responses.append(f"{channel}: No (Error: {str(e)})")
    
    if all_joined:
        await context.bot.send_message(chat_id=user_id, text=capitalize_words("You Are A Member Of All Required Channels. You Can Now Use The Bot."))
        await show_commands(update, context)  # Show commands only after confirming membership
        
        # Delete the original join channels message
        if 'join_channels_message_id' in context.user_data:
            await context.bot.delete_message(chat_id=user_id, message_id=context.user_data['join_channels_message_id'])
            del context.user_data['join_channels_message_id']  # Clear stored ID after deletion
    else:
        failed_channel_names = "\n".join(responses)
        await context.bot.send_message(chat_id=user_id, text=capitalize_words(f"You Must Join The Following Channels To Use The Bot:\n{failed_channel_names}"))

async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = users_collection.find_one({"user_id": user_id})

    if user:
        await update.message.reply_text(capitalize_words(f"Your Balance Is: ₹{user['balance']}"))
    else:
        await update.message.reply_text(capitalize_words("You Are Not Registered."))

# Refer command
async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = users_collection.find_one({"user_id": user_id})

    if user:
        await update.message.reply_text(f" 🤑 Per Refer ₹2 UPI Cash\n\n Your Refer Link : {user['referral_link']} \n\n Share With Your Friends & Family And Earn Refer Bonus")
        
async def task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    task_lines = [
        """🎉 Website Camp: Check Credit Limit Get Rs.125 Direct in Your Upi Account\n\nLink: https://offers.fokatcash.com/camp.php?ref=195SG&camp=InstaEMI\n\n1. Enter Upi Id, Click Submit, Redirected to Partner Website \n\n2. Just Enter Basic Details, Check Your Credit Limit, If You Get Limit Go to Payment Page and Wait For 2 Minutes \n\nDone! You will Get Rs.125 in Your Upi Account within 24 Hours\n\nFull Process: https://t.me/DailyCampaignZone/10""",
    ]
    
    task_message = "\n".join(task_lines)
    await update.message.reply_text(task_message)

async def link_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = users_collection.find_one({"user_id": user_id})

    if user:
        await update.message.reply_text(capitalize_words("Please Send Me Your UPI ID To Link It."))
        context.user_data['linking_upi'] = True  # Indicate that the user is in the process of linking UPI
    else:
        await update.message.reply_text(capitalize_words("You Are Not Registered. Please Register First Using /start."))

# Handle UPI ID input
async def handle_upi_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('linking_upi'):
        user_id = update.message.from_user.id
        upi_id = update.message.text.strip()  # Clean any extra spaces

        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"upi_id": upi_id}},
            upsert=True  # This will insert a new document if no document matches the query
        )

        await update.message.reply_text(capitalize_words(f"Your UPI ID Has Been Linked Successfully: {upi_id}"))
        context.user_data['linking_upi'] = False  # Clear the state
        
        # Pass both update and context to show_commands
        await show_commands(update, context)

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = users_collection.find_one({"user_id": user_id})

    if not user:
        await update.message.reply_text(capitalize_words("You Are Not Registered. Please Register First Using /start."))
        return

    # Determine minimum withdrawal amount
    if user.get('first_withdrawal', True):
        min_withdrawal_amount = 15
    else:
        min_withdrawal_amount = 30

    # Prompt for withdrawal amount
    await update.message.reply_text(capitalize_words(f"Please Enter The Amount You Want To Withdraw ( Current Balance: ₹{user['balance']} ):"))
    
    context.user_data['withdrawing'] = True  # Indicate that the user is in the process of withdrawing
    context.user_data['min_withdrawal_amount'] = min_withdrawal_amount  # Store the minimum amount in context

async def handle_withdrawal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('withdrawing'):
        try:
            amount_str = update.message.text.strip()
            amount = float(amount_str)

            user_id = update.message.from_user.id
            user = users_collection.find_one({"user_id": user_id})

            # Check balance and conditions for withdrawal
            if amount > user['balance']:
                await update.message.reply_text(capitalize_words("Low Balance! Please enter a lesser amount."))
                return

            # Check if amount meets the minimum withdrawal requirement
            min_withdrawal_amount = context.user_data.get('min_withdrawal_amount', 30)
            if amount < min_withdrawal_amount:
                await update.message.reply_text(capitalize_words(f"Minimum withdrawal should be ₹{min_withdrawal_amount} or above."))
                return

            # Deduct the withdrawal amount from the user's balance
            new_balance = user['balance'] - amount

            # Update the database with the new balance and set the amount to withdraw
            users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"balance": new_balance, "to_withdraw": True, "to_withdraw_amount": amount}}
            )

            # Notify the user about the successful withdrawal request
            await update.message.reply_text(capitalize_words(f"Your withdrawal request of ₹{amount} has been processed. Your new balance is ₹{new_balance}."))

            # Reset withdrawal state
            context.user_data['withdrawing'] = False

        except ValueError:
            await update.message.reply_text(capitalize_words("Please enter a valid number to withdraw."))

        except Exception as e:
            logging.error(f"Error handling withdrawal: {e}")

    else:
        await update.message.reply_text(capitalize_words("Please Enter A Valid Command."))


# Unified command handler for regular messages and commands
async def handle_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    
    if context.user_data.get('linking_upi'):
        await handle_upi_input(update, context)  # Directly handle UPI input
    else:
        commands = {
            "balance": check_balance,
            "bonus task": task,
            "refer": refer,
            "link upi": link_upi,
            "withdraw": withdraw,
        }

        if text in commands:
            await commands[text](update, context)
        elif text.startswith('/'):
            command = text[1:]  # Remove leading '/'
            if command in commands:
                await commands[command](update, context)
            else:
                await update.message.reply_text(capitalize_words("Unknown Command. Please Use The Available Commands."))
        else:
            await handle_withdrawal_amount(update, context)  # Handle withdrawal amounts directly when in withdrawing state.

def is_start_command(update: Update) -> bool:
     """Check if the message is 'start' in any case."""
     return update.message.text.lower() == 'start'
 
@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot)
    application = ApplicationBuilder().token("YOUR_TELEGRAM_BOT_TOKEN").build()
    await application.process_update(update)
    return JSONResponse(status_code=200)


async def main():
   application = ApplicationBuilder().token("7903693809:AAGLtWfXJZfn_4kfOqlQHdVDUWAts5nGcMA").build()

   # Add handlers for commands and messages
   application.add_handler(CommandHandler("start", start))  # Handles /start
   
   application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                       lambda update, context: handle_commands(update, context) 
                                       if not is_start_command(update) 
                                       else start(update, context)))

   application.add_handler(CallbackQueryHandler(check_channel_membership, pattern='check_membership'))
   application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.TEXT & ~filters.COMMAND , handle_commands))

   # Run the bot until you send a signal (e.g., Ctrl+C)
   if os.getenv("RENDER"):
        await application.bot.set_webhook(url="https://<YOUR_RENDER_URL>/webhook")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
