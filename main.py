# -*- coding: utf-8 -*-

import logging
import re

import telegram
from functools import wraps
from threading import Lock

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters,CallbackQueryHandler

from db_wrapper import DBwrapper as sqlitedb
from telegram import TelegramObject
from telegram import InlineKeyboardButton, InlineKeyboardMarkup,utils,keyboardbutton



__author__ = 'Rico'

BOT_TOKEN = "1271168319:AAEj22-Uly9mG_zjPGo4yNVZ7HDAEdPGusU"
LIST_OF_ADMINS = [1061660183]  # Enter your Telegram ID here to use /ban, /unban and /broadcast

BOT_SENDS = "\U0001F916 *Bot:*"
BOT_BROADCAST = "\U0001F916 *Bot (Broadcast):*"
STRANGER_SENDS = "\U0001F464:"

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

if not re.match(r"[0-9]+:[a-zA-Z0-9\-_]+", BOT_TOKEN):
    logging.error("Bot token not correct - please check.")
    exit(1)

updater = Updater(token=BOT_TOKEN)
dispatcher = updater.dispatcher
tg_bot = updater.bot
lock = Lock()

chatting_users = []
# TODO searching_users list must have as many fields, as there are search filters + 1.
searching_users = []


def restricted(func):
    @wraps(func)
    def wrapped(bot, update, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in LIST_OF_ADMINS:
            logger.info("Unauthorized access denied for method '{}' for user {}.".format(func.__name__, user_id))
            return
        return func(bot, update, *args, **kwargs)

    return wrapped


def start(bot, update):
    user_id = update.message.from_user.id
    user = update.message.from_user
    db = sqlitedb.get_instance()

    if user_id in db.get_banned_users():
        bot.send_message(user_id, "{} You have been banned from using this bot!".format(BOT_SENDS), parse_mode="Markdown")
        return

    db.add_user(user.id, "en", user.first_name, user.last_name, user.username)

    if (user_id not in searching_users) and (user_already_chatting(user_id) == -1):
        # search for another "searching" user in searching_users list
        if len(searching_users) > 0:
            # delete the other searching users from the list of searching_users
            logger.debug("Another user is searching now. There are 2 users. Matching them now!")

            with lock:
                partner_id = searching_users[0]
                del searching_users[0]

            # add both users to the list of chatting users with the user_id of the other user.
            chatting_users.append([user_id, partner_id])
            chatting_users.append([partner_id, user_id])

            text = "You are connected to a stranger. Have fun and be nice! Skip stranger with /next."
            bot.send_message(user_id, "{} {}".format(BOT_SENDS, text), parse_mode="Markdown")
            bot.send_message(partner_id, "{} {}".format(BOT_SENDS, text), parse_mode="Markdown")
        else:
            # if no user is searching, add him to the list of searching users.
            # TODO later when you can search for specific gender, this condition must be changed
            searching_users.append(user_id)
            bot.send_message(user_id, "{} {}".format(BOT_SENDS, "Searching for strangers!"), parse_mode="Markdown")

    elif user_id in searching_users:
        bot.send_message(user_id, "{} {}".format(BOT_SENDS, "You are already searching. Please wait!"), parse_mode="Markdown")


def stop(bot, update):
    user_id = update.message.from_user.id
    db = sqlitedb.get_instance()

    if user_id in db.get_banned_users():
        bot.send_message(user_id, "{} You have been banned from using this bot!".format(BOT_SENDS), parse_mode="Markdown")
        return

    if (user_id in searching_users) or (user_already_chatting(user_id) >= 0):

        if user_id in searching_users:
            # remove user from searching users
            index = user_already_searching(user_id)
            del searching_users[index]

        elif user_already_chatting(user_id) >= 0:
            # remove both users from chatting users
            partner_id = get_partner_id(user_id)

            index = user_already_chatting(user_id)
            del chatting_users[index]

            partner_index = user_already_chatting(partner_id)
            del chatting_users[partner_index]

            # send message that other user left the chat
            bot.send_message(partner_id, "{} {}".format(BOT_SENDS, "Your partner left the chat"), parse_mode="Markdown")
            bot.send_message(user_id, "{} {}".format(BOT_SENDS, "You left the chat!"), parse_mode="Markdown")


def next(bot, update):
    """Go to next user if currently in a conversation"""
    user_id = update.message.from_user.id
    if user_already_chatting(user_id) >= 0:
        stop(bot, update)
        start(bot, update)


@restricted
def ban(bot, update, args):
    """Bans a user from using this bot - does not end a running chat of that user"""
    if len(args) == 0:
        return
    db = sqlitedb.get_instance()

    banned_user_id = args[0]
    logger.info("Banning user {}".format(banned_user_id))
    if not re.match("[0-9]+", banned_user_id):
        update.message.reply_text("{} UserID is in invalid format!".format(BOT_SENDS), parse_mode="Markdown")
        return

    db.ban(banned_user_id)
    update.message.reply_text("{} Banned user {}".format(BOT_SENDS, banned_user_id), parse_mode="Markdown")


@restricted
def unban(bot, update, args):
    """Unbans a user from using this bot"""
    if len(args) == 0:
        return
    db = sqlitedb.get_instance()

    banned_user_id = args[0]
    logger.info("Unbanning user {}".format(banned_user_id))
    if not re.match("[0-9]+", banned_user_id):
        update.message.reply_text("{} UserID is in invalid format!".format(BOT_SENDS), parse_mode="Markdown")
        return

    db.unban(banned_user_id)
    update.message.reply_text("{} Unbanned user {}".format(BOT_SENDS, banned_user_id), parse_mode="Markdown")


@restricted
def broadcast(bot, update, args):
    """Sends a broadcast message to all known users"""
    if len(args) == 0:
        return
    text = " ".join(args)
    db = sqlitedb.get_instance()

    users = db.get_all_users()
    print(users)

    for user_id in users:
        bot.send_message(user_id, "{} {}".format(BOT_BROADCAST, text), parse_mode="Markdown")


def in_chat(bot, update):
    user_id = update.message.from_user.id

    if update.message.photo is not None:
        try:
            photo = update.message.photo[0].file_id
        except IndexError:
            photo = None

    text = update.message.text
    audio = update.message.audio
    voice = update.message.voice
    document = update.message.document
    caption = update.message.caption
    video = update.message.video
    video_note = update.message.video_note
    sticker = update.message.sticker
    location = update.message.location

    partner_id = get_partner_id(user_id)
    if partner_id != -1:
        if photo is not None:
            bot.send_photo(partner_id, photo=photo, caption=caption)
        elif audio is not None:
            bot.send_audio(partner_id, audio=audio.file_id)
        elif voice is not None:
            bot.send_voice(partner_id, voice=voice.file_id)
        elif video is not None:
            bot.send_video(partner_id, video=video.file_id)
        elif document is not None:
            bot.send_document(partner_id, document=document.file_id, caption=caption)
        elif sticker is not None:
            bot.send_sticker(partner_id, sticker=sticker.file_id)
        elif location is not None:
            bot.send_location(partner_id, location=location)
        elif video_note is not None:
            bot.send_video_note(partner_id, video_note=video_note.file_id)
        else:
            bot.send_message(partner_id, text="{} {}".format(STRANGER_SENDS, text))


def get_partner_id(user_id):
    if len(chatting_users) > 0:
        for pair in chatting_users:
            if pair[0] == user_id:
                return int(pair[1])

    return -1


# checks if user is already chatting with someone
# returns index in the list if yes
# returns -1 if user is not chatting
def user_already_chatting(user_id):
    counter = 0
    if len(chatting_users) > 0:
        for pair in chatting_users:
            if pair[0] == user_id:
                return counter
            counter += 1

    return -1


# checks if a user is already searching for a chat partner
# returns index in list of searching users, if yes
# returns -1 if user is not searching
def user_already_searching(user_id):
    counter = 0
    if len(searching_users) > 0:
        for user in searching_users:
            if user == user_id:
                return counter
            counter += 1

    return -1
    



def start_tcb( bot, update, args):

        """
        start_tcb - callback triggered on /start command

        :param bot: bot object comes from telegram API
        :param update: update object comes from telegram API
        :param args: our custom args

        """

        user_data = bot.get_chat(update.message.chat_id)

        bot.sendMessage(
            chat_id=update.message.chat_id, text="Hello {}, I'm HMSU Radio Bot.".format(user_data.username)
        )

        # keyboard = [[InlineKeyboardButton("Get radiokey", callback_data='1'), InlineKeyboardButton("Help", callback_data='2')]]

        # reply_markup = InlineKeyboardMarkup(keyboard)

        # update.message.reply_text('Please choose:', reply_markup=reply_markup)
        # bot.send_photo(chat_id=update.message.chat_id, photo='https://telegram.org/img/t_logo.png')
       
        # button_list = [  InlineKeyboardButton("col1", callback_data="ghfg"),  InlineKeyboardButton("col2", callback_data="fghfd"), InlineKeyboardButton("row 2", callback_data="gfh")]
        # reply_markup = InlineKeyboardMarkup(util.build_menu(button_list, n_cols=2))
        # bot.send_message(chat_id=update.message.chat_id, text="A two-column menu", reply_markup=reply_markup)



        keyboard = [[InlineKeyboardButton("START", callback_data='1'),InlineKeyboardButton("Settings", callback_data='2')], [InlineKeyboardButton("Help & Info", callback_data='3')]]
        reply_markup = telegram.ReplyKeyboardMarkup(keyboard)
        bot.send_message(chat_id=update.message.chat_id, text="Custom Keyboard Test", reply_markup=reply_markup)


        # bot.sendMessage(chat_id=update.message.chat_id, text="Type /help for full list of commands")     


def button(update):
    logger.debug("Another user is searching now. There are 2 users. Matching them now!")

         
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    query.edit_message_text(text="Selected option: {}".format(query.data))




handlers = []

# handlers.append(CommandHandler('help', get_help))
handlers.append(CommandHandler('start',start))
handlers.append(CallbackQueryHandler(button))

# updater.dispatcher.add_handler(CallbackQueryHandler(button))
handlers.append(CommandHandler('stop', stop))
handlers.append(CallbackQueryHandler(button))
handlers.append(CommandHandler('next', next))
handlers.append(CommandHandler('ban', ban, pass_args=True))
handlers.append(CommandHandler('unban', unban, pass_args=True))
handlers.append(CommandHandler('broadcast', broadcast, pass_args=True))
handlers.append(MessageHandler(Filters.all, in_chat))
handlers.append(CallbackQueryHandler(button))


for handler in handlers:
    dispatcher.add_handler(handler)

updater.start_polling()
