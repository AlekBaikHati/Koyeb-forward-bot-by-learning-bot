import re
import asyncio 
from .utils import STS
from database import db
from config import temp 
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait 
from pyrogram.errors.exceptions.not_acceptable_406 import ChannelPrivate as PrivateChat
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified, ChannelPrivate
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
 


 
#===================Run Function===================#

@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot, message):
    buttons = []
    btn_data = {}
    user_id = message.from_user.id
    _bot = await db.get_bot(user_id)
    if not _bot:
      return await message.reply("You Did Not Added Any Bot. Please Add A Bot Using /settings !")
    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply_text("Please Set A To Channel In /settings Before Forwarding")
    if len(channels) > 1:
       for channel in channels:
          buttons.append([KeyboardButton(f"{channel['title']}")])
          btn_data[channel['title']] = channel['chat_id']
       buttons.append([KeyboardButton("cancel")]) 
       _toid = await bot.ask(message.chat.id, Translation.TO_MSG.format(_bot['name'], _bot['username']), reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
       if _toid.text.startswith(('/', 'cancel')):
          return await message.reply_text(Translation.CANCEL, reply_markup=ReplyKeyboardRemove())
       to_title = _toid.text
       toid = btn_data.get(to_title)
       if not toid:
          return await message.reply_text("Wrong Channel Choosen !", reply_markup=ReplyKeyboardRemove())
    else:
       toid = channels[0]['chat_id']
       to_title = channels[0]['title']
    fromid = await bot.ask(message.chat.id, Translation.FROM_MSG, reply_markup=ReplyKeyboardRemove())
    if fromid.text and fromid.text.startswith('/'):
        await message.reply(Translation.CANCEL)
        return 
    if fromid.text and not fromid.forward_date:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(+)$")
        match = regex.match(fromid.text.replace("?single", ""))
        if not match:
            return await message.reply('Invalid Link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id  = int(("-100" + chat_id))
    elif fromid.forward_from_chat.type in [enums.ChatType.CHANNEL]:
        last_msg_id = fromid.forward_from_message_id
        chat_id = fromid.forward_from_chat.username or fromid.forward_from_chat.id
        if last_msg_id == None:
           return await message.reply_text("This May Be A Forwarded Message From A Group And Sended By Anonymous Admin. Instead Of This Please Send Last Message Link From Group")
    else:
        await message.reply_text("Invalid !")
        return 
    try:
        title = (await bot.get_chat(chat_id)).title
  #  except ChannelInvalid:
        #return await fromid.reply("**Given source chat is copyrighted channel/group. you can't forward messages from there**")
    except (PrivateChat, ChannelPrivate, ChannelInvalid):
        title = "private" if fromid.text else fromid.forward_from_chat.title
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply('Invalid Link Specified.')
    except Exception as e:
        return await message.reply(f'Errors - {e}')
    skip_buttons = [[InlineKeyboardButton('Lewati 0', callback_data='skip_0'),
                     InlineKeyboardButton('Lewati 5', callback_data='skip_5'),
                     InlineKeyboardButton('Lewati 10', callback_data='skip_10')]]
    skipno = await bot.ask(message.chat.id, "Atur Jumlah Pesan yang Dilewati\n\nLewati pesan sebanyak angka yang Anda masukkan, sisanya akan diteruskan.\nLewati default = 0\ncth: Masukkan 0 = tidak ada yang dilewati\nMasukkan 5 = 5 pesan dilewati\n/cancel - Untuk membatalkan proses ini", reply_markup=InlineKeyboardMarkup(skip_buttons))
    if skipno.text.startswith('/'):
        await message.reply(Translation.CANCEL)
        return
    forward_id = f"{user_id}-{skipno.id}"
    buttons = [[
        InlineKeyboardButton('Yes', callback_data=f"start_public_{forward_id}"),
        InlineKeyboardButton('No', callback_data="close_btn")
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)
    await message.reply_text(
        text=Translation.DOUBLE_CHECK.format(botname=_bot['name'], botuname=_bot['username'], from_chat=title, to_chat=to_title, skip=skipno.text),
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )
    STS(forward_id).store(chat_id, toid, int(skipno.text), int(last_msg_id))







# Jishu Developer 
