import os
import sys
import math
import time
import asyncio
import logging
from collections import defaultdict

from .utils import STS
from database import db
from .test import CLIENT, start_clone_bot
from config import Config, temp
from translation import Translation

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
)

CLIENT = CLIENT()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
TEXT = Translation.TEXT

@Client.on_callback_query(filters.regex(r'^start_public'))
async def pub_(bot, message):
    user = message.from_user.id
    temp.CANCEL[user] = False
    frwd_id = message.data.split("_")[2]
    if temp.lock.get(user) and str(temp.lock.get(user)) == "True":
        return await message.answer("Please Wait Until Previous Task Complete", show_alert=True)
    
    sts = STS(frwd_id)
    if not sts.verify():
        await message.answer("Your Are Clicking On My Old Button", show_alert=True)
        return await message.message.delete()

    i = sts.get(full=True)
    if i.TO in temp.IS_FRWD_CHAT:
        return await message.answer("In Target Chat A Task Is Progressing. Please Wait Until Task Complete", show_alert=True)

    m = await msg_edit(message.message, "Verifying Your Data's, Please Wait.")
    _bot, caption, forward_tag, data, protect, button = await sts.get_data(user)
    if not _bot:
        return await msg_edit(m, "You Didn't Added Any Bot. Please Add A Bot Using /settings !", wait=True)

    try:
        client_instance = CLIENT.client(_bot)
        client = await start_clone_bot(client_instance)
    except Exception as e:
        return await m.edit(str(e))

    await msg_edit(m, "Processing...")
    try:
        await client.get_messages(sts.get("FROM"), 1)
    except:
        await msg_edit(m, f"Source Chat May Be A Private Channel / Group. Use Userbot (User Must Be Member Over There) Or Make Your [Bot](t.me/{_bot['username']}) An Admin Over There", retry_btn(frwd_id), True)
        return await stop(client, user)

    try:
        k = await client.send_message(i.TO, "Testing")
        await k.delete()
    except:
        await msg_edit(m, f"Please Make Your [UserBot / Bot](t.me/{_bot['username']}) Admin In Target Channel With Full Permissions", retry_btn(frwd_id), True)
        return await stop(client, user)

    temp.forwardings += 1
    await db.add_frwd(user)
    await send(client, user, "🖥️ Forwarding Started")
    sts.add(time=True)
    sleep = 1 if _bot['is_bot'] else 10
    await msg_edit(m, "Processing...")
    temp.IS_FRWD_CHAT.append(i.TO)
    temp.lock[user] = True

    try:
        MSG = []
        pling = 0
        media_groups = defaultdict(list)
        last_group_time = 0
        group_timeout = 2

        await edit(m, 'Progressing', 10, sts)
        async for message in client.iter_messages(
            chat_id=sts.get('FROM'),
            limit=int(sts.get('limit')),
            offset=int(sts.get('skip')) if sts.get('skip') else 0
        ):
            if await is_cancelled(client, user, m, sts):
                return

            if pling % 20 == 0:
                await edit(m, 'Progressing', 10, sts)
            pling += 1
            sts.add('fetched')

            if message == "DUPLICATE":
                sts.add('duplicate')
                continue
            elif message == "FILTERED":
                sts.add('filtered')
                continue
            if message.empty or message.service:
                sts.add('deleted')
                continue

            if message.media_group_id:
                media_groups[message.media_group_id].append(message)
                last_group_time = time.time()
                continue

            if media_groups and time.time() - last_group_time > group_timeout:
                for group_id, group_msgs in media_groups.items():
                    if forward_tag:
                        MSG.extend([m.id for m in group_msgs])
                        await forward(client, MSG, m, sts, protect)
                        sts.add('total_files', len(group_msgs))
                        await asyncio.sleep(10)
                        MSG = []
                    else:
                        album = []
                        for msg in reversed(group_msgs):
                            new_caption = custom_caption(msg, caption)
                            media_item = {
                                "msg_id": msg.id,
                                "media": media(msg),
                                "caption": new_caption,
                                "button": button,
                                "protect": protect
                            }
                            album.append(media_item)
                        await copy_album(client, album, m, sts)
                        sts.add('total_files', len(album))
                        await asyncio.sleep(sleep)
                media_groups.clear()
                continue


            if forward_tag:
                MSG.append(message.id)
                notcompleted = len(MSG)
                completed = sts.get('total') - sts.get('fetched')
                if notcompleted >= 100 or completed <= 100:
                    await forward(client, MSG, m, sts, protect)
                    sts.add('total_files', notcompleted)
                    await asyncio.sleep(10)
                    MSG = []
            else:
                new_caption = custom_caption(message, caption)
                details = {
                    "msg_id": message.id,
                    "media": media(message),
                    "caption": new_caption,
                    'button': button,
                    "protect": protect
                }
                await copy(client, details, m, sts)
                sts.add('total_files')
                await asyncio.sleep(sleep)

    except Exception as e:
        await msg_edit(m, f'<b>Error :</b>\n<code>{e}</code>', wait=True)
        temp.IS_FRWD_CHAT.remove(sts.TO)
        return await stop(client, user)

    temp.IS_FRWD_CHAT.remove(sts.TO)
    await send(client, user, "🎉 Forwarding Completed")
    await edit(m, 'Completed', "completed", sts)
    await stop(client, user)


async def copy_album(bot, album_msgs, m, sts):
    media_list = []
    for idx, msg in enumerate(album_msgs):
        file_id = msg["media"]
        caption = msg["caption"] if idx == 0 else None
        if not file_id:
            continue
        if "video" in file_id:
            media_obj = InputMediaVideo(media=file_id, caption=caption)
        elif "photo" in file_id:
            media_obj = InputMediaPhoto(media=file_id, caption=caption)
        elif "document" in file_id:
            media_obj = InputMediaDocument(media=file_id, caption=caption)
        elif "audio" in file_id:
            media_obj = InputMediaAudio(media=file_id, caption=caption)
        else:
            continue
        media_list.append(media_obj)

    try:
        await bot.send_media_group(
            chat_id=sts.get("TO"),
            media=media_list,
            protect_content=album_msgs[0]["protect"] if album_msgs else False
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await copy_album(bot, album_msgs, m, sts)
    except Exception as e:
        print("Album Copy Error:", e)
        sts.add("deleted")

        
async def forward(bot, msg_ids, m, sts, protect):
    try:
        messages = await bot.get_messages(chat_id=sts.get('FROM'), message_ids=msg_ids)
        caption_template = sts.get("caption")
        if messages and messages[0].media_group_id:
            media = []
            for idx, message in enumerate(messages):
                new_caption = custom_caption(message, caption_template) if idx == 0 else None
                file_id = media(message)
                if not file_id:
                    continue
                if message.photo:
                    media.append(InputMediaPhoto(file_id, caption=new_caption))
                elif message.video:
                    media.append(InputMediaVideo(file_id, caption=new_caption))
                elif message.document:
                    media.append(InputMediaDocument(file_id, caption=new_caption))
                elif message.audio:
                    media.append(InputMediaAudio(file_id, caption=new_caption))
            await bot.send_media_group(
                chat_id=sts.get("TO"),
                media=media,
                protect_content=protect
            )
        else:
            await bot.forward_messages(
                chat_id=sts.get('TO'),
                from_chat_id=sts.get('FROM'), 
                message_ids=msg_ids,
                protect_content=protect
            )
    except FloodWait as e:
        await edit(m, 'Progressing', e.value, sts)
        await asyncio.sleep(e.value)
        await forward(bot, msg_ids, m, sts, protect)

PROGRESS = """
📈 Percetage : {0} %

♻️ Fetched : {1}

🔥 Forwarded : {2}

🫠 Remaining : {3}

📊 Status : {4}

⏳️ ETA : {5}
"""

async def msg_edit(msg, text, button=None, wait=None):
    try:
        return await msg.edit(text, reply_markup=button)
    except MessageNotModified:
        pass 
    except FloodWait as e:
        if wait:
           await asyncio.sleep(e.value)
           return await msg_edit(msg, text, button, wait)
        
async def edit(msg, title, status, sts):
   i = sts.get(full=True)
   status = 'Forwarding' if status == 10 else f"Sleeping {status} s" if str(status).isnumeric() else status
   percentage = "{:.0f}".format(float(i.fetched)*100/float(i.total))
   
   now = time.time()
   diff = int(now - i.start)
   speed = sts.divide(i.fetched, diff)
   elapsed_time = round(diff) * 1000
   time_to_completion = round(sts.divide(i.total - i.fetched, int(speed))) * 1000
   estimated_total_time = elapsed_time + time_to_completion  
   progress = "▰{0}{1}".format(
       ''.join(["▰" for i in range(math.floor(int(percentage) / 10))]),
       ''.join(["▱" for i in range(10 - math.floor(int(percentage) / 10))]))
   button =  [[InlineKeyboardButton(title, f'fwrdstatus#{status}#{estimated_total_time}#{percentage}#{i.id}')]]
   estimated_total_time = TimeFormatter(milliseconds=estimated_total_time)
   estimated_total_time = estimated_total_time if estimated_total_time != '' else '0 s'

   text = TEXT.format(i.fetched, i.total_files, i.duplicate, i.deleted, i.skip, status, percentage, estimated_total_time, progress)
   if status in ["cancelled", "completed"]:
      button.append(
         [InlineKeyboardButton('📢 Updates', url='https://t.me/learningbots79'),
         InlineKeyboardButton('💬 Support', url='https://t.me/learning_bots')]
         )
   else:
      button.append([InlineKeyboardButton('✖️ Cancel ✖️', 'terminate_frwd')])
   await msg_edit(msg, text, InlineKeyboardMarkup(button))
   
async def is_cancelled(client, user, msg, sts):
   if temp.CANCEL.get(user)==True:
      temp.IS_FRWD_CHAT.remove(sts.TO)
      await edit(msg, "Cancelled", "completed", sts)
      await send(client, user, "❌ Forwarding Process Cancelled")
      await stop(client, user)
      return True 
   return False 

async def stop(client, user):
   try:
     await client.stop()
   except:
     pass 
   await db.rmve_frwd(user)
   temp.forwardings -= 1
   temp.lock[user] = False 
    
async def send(bot, user, text):
   try:
      await bot.send_message(user, text=text)
   except:
      pass 
     
def custom_caption(msg, caption):
  if msg.media:
    if (msg.video or msg.document or msg.audio or msg.photo):
      media = getattr(msg, msg.media.value, None)
      if media:
        file_name = getattr(media, 'file_name', '')
        file_size = getattr(media, 'file_size', '')
        fcaption = getattr(msg, 'caption', '')
        if fcaption:
          fcaption = fcaption.html
        if caption:
          return caption.format(filename=file_name, size=get_size(file_size), caption=fcaption)
        return fcaption
  return None

def get_size(size):
  units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
  size = float(size)
  i = 0
  while size >= 1024.0 and i < len(units):
     i += 1
     size /= 1024.0
  return "%.2f %s" % (size, units[i]) 

def media(msg):
  if msg.media:
     media = getattr(msg, msg.media.value, None)
     if media:
        return getattr(media, 'file_id', None)
  return None 

def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s, ") if seconds else "") + \
        ((str(milliseconds) + "ms, ") if milliseconds else "")
    return tmp[:-2]

def retry_btn(id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('♻️ Retry ♻️', f"start_public_{id}")]])




@Client.on_callback_query(filters.regex(r'^terminate_frwd$'))
async def terminate_frwding(bot, m):
    user_id = m.from_user.id 
    temp.lock[user_id] = False
    temp.CANCEL[user_id] = True 
    await m.answer("Forwarding Cancelled !", show_alert=True)
          



@Client.on_callback_query(filters.regex(r'^fwrdstatus'))
async def status_msg(bot, msg):
    _, status, est_time, percentage, frwd_id = msg.data.split("#")
    sts = STS(frwd_id)
    if not sts.verify():
       fetched, forwarded, remaining = 0
    else:
       fetched, forwarded = sts.get('fetched'), sts.get('total_files')
       remaining = fetched - forwarded 
    est_time = TimeFormatter(milliseconds=est_time)
    est_time = est_time if (est_time != '' or status not in ['completed', 'cancelled']) else '0 s'
    return await msg.answer(PROGRESS.format(percentage, fetched, forwarded, remaining, status, est_time), show_alert=True)
                  


                  
@Client.on_callback_query(filters.regex(r'^close_btn$'))
async def close(bot, update):
    await update.answer()
    await update.message.delete()
    await update.message.reply_to_message.delete()







# Jishu Developer 
