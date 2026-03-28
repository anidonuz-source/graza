import asyncio
import logging
import random
import string
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode

from config import config
from database import db
from keyboards import *
from states import CreateContest, AddChannel, SendReklama

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

checker_running = False


def generate_contest_id() -> str:
    timestamp = datetime.now().strftime("%y%m%d%H%M%S")
    random_str = ''.join(random.choices(string.digits, k=4))
    return f"mylot{timestamp}{random_str}"


def format_date(date_str) -> str:
    try:
        if isinstance(date_str, str):
            date_obj = datetime.fromisoformat(date_str)
        else:
            date_obj = date_str
        return date_obj.strftime("%d.%m.%Y %H:%M")
    except:
        return str(date_str)


def escape_html(text: str) -> str:
    if not text:
        return text
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


async def check_subscription(user_id: int, channel_username: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False


async def get_channel_info(channel_username: str) -> dict:
    try:
        chat = await bot.get_chat(chat_id=channel_username)
        return {
            'id': str(chat.id),
            'username': chat.username,
            'title': chat.title
        }
    except:
        return None


async def finish_contest(contest: dict, participants_count: int, reason: str):
    """Konkursni tugatish va g'oliblarni e'lon qilish (faqat bir marta)"""
    try:
        # Konkurs allaqachon tugaganligini tekshirish
        if db.is_contest_finished(contest['contest_id']):
            logger.info(f"Konkurs allaqachon tugagan: {contest['contest_id']}")
            return

        # Konkursni tugatish
        db.finish_contest(contest['contest_id'])

        # G'oliblarni aniqlash
        winners = db.get_random_winners(contest['contest_id'], contest['winners_count'])

        channel = db.get_channel_by_id(contest['channel_id'])
        if not channel:
            logger.error(f"Kanal topilmadi: {contest['channel_id']}")
            return

        # G'oliblar matnini tayyorlash
        winners_text = ""
        if winners and len(winners) > 0:
            for i, winner in enumerate(winners, 1):
                winner_name = winner['username'] or str(winner['user_id'])
                winners_text += f"{i}. @{winner_name}\n"
        else:
            winners_text = "❌ G'oliblar aniqlanmadi"

        # YANGI XABAR MATNI
        new_text = f"<b>🏆 KONKURS YAKUNLANDI! 🏆</b>\n\n"
        new_text += f"{contest['description']}\n\n"
        new_text += f"<b>🏆 G'oliblar soni:</b> {contest['winners_count']}\n"
        new_text += f"<b>👥 Jami ishtirokchilar:</b> {participants_count}\n"
        new_text += f"<b>🎯 Tugash sababi:</b> {reason}\n\n"
        new_text += f"<b>🏆 G'OLIBLAR:</b>\n{winners_text}"

        # Kanal username ni formatlash
        channel_username = channel['channel_username']
        if not channel_username.startswith('@'):
            channel_username = '@' + channel_username

        try:
            # Xabarni edit qilish
            await bot.edit_message_text(
                chat_id=channel_username,
                message_id=contest['message_id'],
                text=new_text,
                parse_mode=ParseMode.HTML,
                reply_markup=None
            )
            logger.info(f"Konkurs tugatildi: {contest['contest_id']}, g'oliblar: {len(winners)}")
        except Exception as e:
            logger.error(f"Xabarni edit qilishda xatolik: {e}")

        # Yaratuvchiga xabar yuborish (faqat bir marta)
        creator = db.get_user_by_id(contest['creator_id'])
        if creator:
            try:
                if winners:
                    winner_names = []
                    for w in winners:
                        winner_names.append(w['username'] or str(w['user_id']))
                    winners_list = ", ".join([f"@{n}" for n in winner_names])
                else:
                    winners_list = "Yo'q"

                await bot.send_message(
                    chat_id=creator['telegram_id'],
                    text=f"✅ <b>{contest['contest_id']}</b> konkursi tugatildi!\n\n"
                         f"📊 Ishtirokchilar: {participants_count}\n"
                         f"🏆 G'oliblar soni: {contest['winners_count']}\n"
                         f"🏆 G'oliblar: {winners_list}\n"
                         f"📌 Sabab: {reason}",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Yaratuvchiga xabar yuborishda xatolik: {e}")

    except Exception as e:
        logger.error(f"Finish contest error: {e}")


async def check_contests():
    """Barcha aktiv konkurslarni tekshirish"""
    while True:
        try:
            contests = db.get_active_contests()

            for contest in contests:
                # Konkurs allaqachon tugaganligini tekshirish
                if db.is_contest_finished(contest['contest_id']):
                    continue

                # Tugmani yangilash
                await update_contest_button(contest['contest_id'])

                participants_count = db.get_participants_count(contest['contest_id'])
                should_end = False
                finish_reason = ""

                if contest['finish_type'] == 'participants':
                    target_count = int(contest['finish_value'])
                    if participants_count >= target_count:
                        should_end = True
                        finish_reason = f"{target_count} ishtirokchi yig'ildi"

                elif contest['finish_type'] == 'time':
                    finish_time = datetime.fromisoformat(contest['finish_value'])
                    if datetime.now() >= finish_time:
                        should_end = True
                        finish_reason = "Vaqt tugadi"

                if should_end:
                    # Yana bir marta tekshirish
                    if db.is_contest_finished(contest['contest_id']):
                        continue
                    await finish_contest(contest, participants_count, finish_reason)

            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Check contests error: {e}")
            await asyncio.sleep(10)

async def publish_contest(contest: dict, channel_id: str) -> dict:
    # Konkurs matnini tayyorlash
    text = f"<b>📢 YANGI KONKURS!</b>\n\n"
    text += f"{contest['description']}\n\n"
    text += f"<b>🏆 G'oliblar soni:</b> {contest['winners_count']}\n"

    if contest['finish_type'] == 'participants':
        text += f"<b>👥 Tugash:</b> {contest['finish_value']} ishtirokchi yig'ilganda\n"
    else:
        text += f"<b>⏰ Tugash:</b> {format_date(contest['finish_value'])}\n"

    text += f"\n👇 Qatnashish uchun tugmani bosing!"

    try:
        channel = db.get_channel_by_id(int(channel_id))
        if not channel:
            return {'success': False, 'error': 'Kanal topilmadi'}

        channel_username = channel['channel_username']
        if not channel_username.startswith('@'):
            channel_username = '@' + channel_username

        try:
            chat = await bot.get_chat(channel_username)
            channel_id_for_send = chat.id
        except Exception as e:
            return {'success': False, 'error': f'Kanal topilmadi: {str(e)}'}

        # Button text va ishtirokchilar soni (boshida 0)
        button_text = contest['button_text']
        participants_count = 0

        if contest['media_type'] == 'photo' and contest['media_file_id']:
            message = await bot.send_photo(
                chat_id=channel_id_for_send,
                photo=contest['media_file_id'],
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_contest_action_keyboard(contest['contest_id'], button_text, participants_count)
            )
        elif contest['media_type'] == 'video' and contest['media_file_id']:
            message = await bot.send_video(
                chat_id=channel_id_for_send,
                video=contest['media_file_id'],
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_contest_action_keyboard(contest['contest_id'], button_text, participants_count)
            )
        elif contest['media_type'] == 'animation' and contest['media_file_id']:
            message = await bot.send_animation(
                chat_id=channel_id_for_send,
                animation=contest['media_file_id'],
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_contest_action_keyboard(contest['contest_id'], button_text, participants_count)
            )
        else:
            message = await bot.send_message(
                chat_id=channel_id_for_send,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_contest_action_keyboard(contest['contest_id'], button_text, participants_count)
            )

        post_link = f"https://t.me/{channel['channel_username'].replace('@', '')}/{message.message_id}"
        return {'success': True, 'message_id': message.message_id, 'post_link': post_link}

    except Exception as e:
        return {'success': False, 'error': str(e)}


async def update_contest_button(contest_id: str):
    """Konkurs tugmasini yangilash (ishtirokchilar sonini ko'rsatish)"""
    try:
        contest = db.get_contest(contest_id)
        if not contest or not contest['is_active']:
            return

        participants_count = db.get_participants_count(contest_id)
        button_text = contest['button_text']

        channel = db.get_channel_by_id(contest['channel_id'])
        if not channel:
            return

        channel_username = channel['channel_username']
        if not channel_username.startswith('@'):
            channel_username = '@' + channel_username

        try:
            await bot.edit_message_reply_markup(
                chat_id=channel_username,
                message_id=contest['message_id'],
                reply_markup=get_contest_action_keyboard(contest_id, button_text, participants_count)
            )
        except Exception as e:
            logger.error(f"Tugmani yangilashda xatolik: {e}")
    except Exception as e:
        logger.error(f"Update button error: {e}")
# ============ START ============
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )

    welcome_text = (
        f"<b>🎉 Assalomu alaykum, {escape_html(message.from_user.full_name)}!</b>\n\n"
        f"Bu bot orqali siz o'z kanalingizda konkurslar o'tkazishingiz mumkin.\n\n"
        f"<b>📌 Bot imkoniyatlari:</b>\n"
        f"✅ Konkurs yaratish\n"
        f"✅ Obuna talab qilish\n"
        f"✅ Avtomatik g'oliblarni aniqlash\n\n"
        f"Boshlash uchun pastdagi menyudan foydalaning 👇"
    )

    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu(user['is_admin']))


# ============ MAIN MENU ============
@dp.message(F.text == "📊 Yangi konkurs yaratish")
async def create_new_contest(message: Message, state: FSMContext):
    await state.clear()
    db.clear_temp_contest_data(message.from_user.id)
    await state.set_state(CreateContest.waiting_for_text)

    await message.answer(
        "<b>📝 Konkurs matnini yuboring</b>\n\n"
        "Siz matn bilan birga rasm, video yoki GIF ham yuborishingiz mumkin.\n"
        "❗ Faqat 1 ta media fayl ishlatishingiz mumkin.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )


@dp.message(F.text == "📋 Mening konkurslarim")
async def my_contests(message: Message):
    user = db.get_user(message.from_user.id)
    contests = db.get_user_contests(user['id'])

    if not contests:
        await message.answer("📭 Siz hali hech qanday konkurs yaratmagansiz.",
                             reply_markup=get_main_menu(user['is_admin']))
        return

    text = "<b>📋 Sizning konkurslaringiz:</b>\n\n"
    for contest in contests[:10]:
        status = "✅ Faol" if contest['is_active'] else "❌ Tugagan"
        participants = db.get_participants_count(contest['contest_id'])
        text += f"🔹 <b>ID:</b> <code>{contest['contest_id']}</code>\n"
        text += f"   <b>Status:</b> {status}\n"
        text += f"   <b>Ishtirokchilar:</b> {participants}\n\n"

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_my_contests_keyboard(contests))


@dp.message(F.text == "📢 Mening kanallarim")
async def my_channels(message: Message):
    user = db.get_user(message.from_user.id)
    channels = db.get_user_channels(user['id'])

    if not channels:
        text = "📭 Siz hali hech qanday kanal qo'shmagansiz.\n\n"
        text += "Kanal qo'shish uchun:\n"
        text += "1. Botni kanalingizga admin qilib qo'shing\n"
        text += "2. Kanalingizni @username formatida yuboring"
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_my_channels_keyboard([]))
        return

    text = "<b>📢 Sizning kanallaringiz:</b>\n\n"
    for channel in channels:
        text += f"🔹 <b>Nomi:</b> {escape_html(channel['channel_name'])}\n"
        text += f"   <b>Username:</b> {channel['channel_username']}\n\n"

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_my_channels_keyboard(channels))


@dp.message(F.text == "❓ Yordam")
async def help_command(message: Message):
    user = db.get_user(message.from_user.id)
    help_text = "<b>📚 Botdan foydalanish:</b>\n\n1. Kanal qo'shish: Botni kanalga admin qilib qo'shib, @username yuboring\n2. Konkurs yaratish: 'Yangi konkurs yaratish' tugmasini bosing\n3. Konkursda qatnashish: Konkurs postidagi tugmani bosing"
    await message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu(user['is_admin']))


@dp.message(F.text == "⚙️ Admin panel")
async def admin_panel(message: Message):
    user = db.get_user(message.from_user.id)
    if not user['is_admin']:
        await message.answer("❌ Siz admin emassiz!")
        return
    await message.answer("<b>⚙️ Admin panel</b>", parse_mode=ParseMode.HTML, reply_markup=get_admin_panel())


@dp.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    db.clear_temp_contest_data(message.from_user.id)
    user = db.get_user(message.from_user.id)
    await message.answer("❌ Amal bekor qilindi.", reply_markup=get_main_menu(user['is_admin']))


# ============ CREATE CONTEST ============
@dp.message(StateFilter(CreateContest.waiting_for_text))
async def get_contest_text(message: Message, state: FSMContext):
    data = {'description': message.html_text or message.text}

    if message.photo:
        data['media_type'] = 'photo'
        data['media_file_id'] = message.photo[-1].file_id
    elif message.video:
        data['media_type'] = 'video'
        data['media_file_id'] = message.video.file_id
    elif message.animation:
        data['media_type'] = 'animation'
        data['media_file_id'] = message.animation.file_id
    else:
        data['media_type'] = 'text'
        data['media_file_id'] = None

    await state.update_data(data)
    await state.set_state(CreateContest.waiting_for_button_text)
    await message.answer("<b>✏️ Tugma matnini yuboring</b> (masalan: Qatnashaman):", parse_mode=ParseMode.HTML)


@dp.message(StateFilter(CreateContest.waiting_for_button_text))
async def get_button_text(message: Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await state.set_state(CreateContest.waiting_for_channels)

    user = db.get_user(message.from_user.id)
    channels = db.get_user_channels(user['id'])

    if not channels:
        await message.answer(
            "❗ Avval kanal qo'shishingiz kerak.\n\nBotni kanalingizga admin qilib qo'shib, @username formatida yuboring.",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AddChannel.waiting_for_channel)
    else:
        await message.answer(
            "<b>📢 Konkursda qatnashish uchun talab qilinadigan kanallarni tanlang</b>",
            parse_mode=ParseMode.HTML
        )
        await message.answer("Kanallar:", reply_markup=get_channels_keyboard(channels))


# ============ ADD CHANNEL ============
@dp.message(StateFilter(AddChannel.waiting_for_channel))
async def add_channel(message: Message, state: FSMContext):
    username = message.text.strip()
    if not username.startswith('@'):
        username = '@' + username

    try:
        chat = await bot.get_chat(username)
        channel_info = {
            'id': str(chat.id),
            'username': chat.username,
            'title': chat.title
        }
    except Exception as e:
        await message.answer(
            f"❌ Kanal topilmadi!\n\n1. Botni kanalga ADMIN qilib qo'shing\n2. To'g'ri username yuboring",
            reply_markup=get_cancel_keyboard()
        )
        return

    try:
        member = await bot.get_chat_member(chat_id=username, user_id=message.from_user.id)
        if member.status not in ['administrator', 'creator']:
            await message.answer(
                f"❌ Siz <b>{channel_info['title']}</b> kanalida admin emassiz!\nFaqat o'z kanallaringizni qo'sha olasiz.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_cancel_keyboard()
            )
            return

        bot_member = await bot.get_chat_member(chat_id=username, user_id=bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            await message.answer(
                f"❌ Bot <b>{channel_info['title']}</b> kanalida admin emas!\nBotni kanalga ADMIN qilib qo'shing.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_cancel_keyboard()
            )
            return
    except Exception as e:
        await message.answer(
            f"❌ Kanalni tekshirib bo'lmadi!\n\n1. Botni kanalga ADMIN qilib qo'shing\n2. Qayta urinib ko'ring",
            reply_markup=get_cancel_keyboard()
        )
        return

    user = db.get_user(message.from_user.id)
    success = db.add_channel(channel_info['id'], channel_info['title'], username, user['id'])

    if success:
        await message.answer(f"✅ <b>{channel_info['title']}</b> kanali qo'shildi!", parse_mode=ParseMode.HTML)
    else:
        await message.answer("❌ Bu kanal allaqachon qo'shilgan!", reply_markup=get_cancel_keyboard())
        return

    await state.set_state(CreateContest.waiting_for_channels)
    channels = db.get_user_channels(user['id'])
    await message.answer("<b>📢 Konkursda qatnashish uchun talab qilinadigan kanallarni tanlang:</b>",
                         parse_mode=ParseMode.HTML)
    await message.answer("Kanallar:", reply_markup=get_channels_keyboard(channels))


# ============ CHANNELS CALLBACKS ============
@dp.callback_query(F.data.startswith("select_channel_"))
async def select_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.replace("select_channel_", ""))
    data = await state.get_data()
    selected = data.get('selected_channels', [])

    channel = db.get_channel_by_id(channel_id)
    if channel:
        if channel_id not in [c.get('id') for c in selected]:
            selected.append(
                {'id': channel_id, 'username': channel['channel_username'], 'name': channel['channel_name']})
            await callback.answer(f"✅ {channel['channel_name']} qo'shildi")
        else:
            await callback.answer(f"❌ {channel['channel_name']} allaqachon qo'shilgan")

        await state.update_data(selected_channels=selected)
        user = db.get_user(callback.from_user.id)
        channels = db.get_user_channels(user['id'])
        try:
            await callback.message.edit_reply_markup(reply_markup=get_channels_keyboard(channels))
        except:
            pass


@dp.callback_query(F.data == "channels_done")
async def channels_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_channels = data.get('selected_channels', [])

    if not selected_channels:
        await callback.answer("❗ Kamida bitta kanal tanlashingiz kerak!", show_alert=True)
        return

    await state.update_data(selected_channels=selected_channels)
    await state.set_state(CreateContest.waiting_for_winners_count)
    await callback.message.answer("<b>🏆 Nechta g'olib bo'lsin?</b> (son kiriting):", parse_mode=ParseMode.HTML,
                                  reply_markup=get_cancel_keyboard())
    await callback.answer("✅ Kanallar saqlandi!")


@dp.callback_query(F.data == "add_new_channel")
async def add_new_channel_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.waiting_for_channel)
    await callback.message.answer(
        "<b>➕ Kanal username ni @username formatida yuboring:</b>\n\n❗ Botni kanalingizga ADMIN qilib qo'shishni unutmang!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "add_new_channel_menu")
async def add_new_channel_from_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.waiting_for_channel)
    await callback.message.answer(
        "<b>➕ Kanal username ni @username formatida yuboring:</b>\n\n❗ Botni kanalingizga ADMIN qilib qo'shishni unutmang!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


# ============ WINNERS COUNT ============
@dp.message(StateFilter(CreateContest.waiting_for_winners_count))
async def get_winners_count(message: Message, state: FSMContext):
    try:
        count = int(message.text)
        if count < 1:
            raise ValueError
        await state.update_data(winners_count=count)
        await state.set_state(CreateContest.waiting_for_publish_channel)

        user = db.get_user(message.from_user.id)
        channels = db.get_user_channels(user['id'])

        text = "<b>📢 Konkursni qaysi kanalda e'lon qilamiz?</b>"
        buttons = []
        for ch in channels:
            buttons.append([InlineKeyboardButton(text=ch['channel_name'], callback_data=f"publish_{ch['id']}")])
        await message.answer(text, parse_mode=ParseMode.HTML,
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except:
        await message.answer("❌ Iltimos, to'g'ri son kiriting!")


@dp.callback_query(F.data.startswith("publish_"))
async def select_publish_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.replace("publish_", ""))
    channel = db.get_channel_by_id(channel_id)
    if not channel:
        await callback.answer("❌ Kanal topilmadi!", show_alert=True)
        return

    await state.update_data(channel_id=channel_id)
    await state.set_state(CreateContest.waiting_for_finish_type)
    await callback.message.answer(
        "<b>⏰ Konkurs qanday tugasin?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_finish_type_keyboard()
    )
    await callback.answer(f"✅ Kanal tanlandi: {channel['channel_name']}")


# ============ FINISH TYPE ============
@dp.callback_query(F.data == "finish_participants")
async def finish_by_participants(callback: CallbackQuery, state: FSMContext):
    await state.update_data(finish_type='participants')
    await state.set_state(CreateContest.waiting_for_finish_value)
    await callback.message.answer("<b>👥 Nechta ishtirokchi yig'ilganda konkurs tugasin?</b> (son kiriting):",
                                  parse_mode=ParseMode.HTML, reply_markup=get_cancel_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "finish_time")
async def finish_by_time(callback: CallbackQuery, state: FSMContext):
    await state.update_data(finish_type='time')
    await state.set_state(CreateContest.waiting_for_finish_value)
    await callback.message.answer(
        "<b>⏰ Konkurs qachon tugasin?</b>\nFormat: YYYY-MM-DD HH:MM\nMasalan: 2024-12-31 23:59",
        parse_mode=ParseMode.HTML, reply_markup=get_cancel_keyboard())
    await callback.answer()


@dp.message(StateFilter(CreateContest.waiting_for_finish_value))
async def get_finish_value(message: Message, state: FSMContext):
    data = await state.get_data()
    finish_type = data['finish_type']

    if finish_type == 'participants':
        try:
            value = int(message.text)
            if value < 1:
                raise ValueError
            await state.update_data(finish_value=value)
        except:
            await message.answer("❌ Iltimos, to'g'ri son kiriting!")
            return
    else:
        try:
            value = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
            if value < datetime.now():
                await message.answer("❌ Vaqt hozirgi vaqtdan keyin bo'lishi kerak!")
                return
            await state.update_data(finish_value=value.isoformat())
        except:
            await message.answer("❌ Noto'g'ri format! Masalan: 2024-12-31 23:59")
            return

    await state.set_state(CreateContest.confirm)

    data = await state.get_data()
    text = "<b>📋 Konkurs ma'lumotlarini tekshiring:</b>\n\n"
    text += f"<b>📝 Matn:</b> {data.get('description', '')[:200]}...\n"
    text += f"<b>🔘 Tugma:</b> {data.get('button_text', 'Qatnashaman')}\n"
    text += f"<b>👥 G'oliblar:</b> {data.get('winners_count', 1)}\n"

    channels = data.get('selected_channels', [])
    if channels:
        text += f"<b>📢 Talab qilinadigan kanallar:</b> {', '.join([c['name'] for c in channels])}\n"

    if finish_type == 'participants':
        text += f"<b>👥 Tugash:</b> {data.get('finish_value')} ishtirokchi yig'ilganda\n"
    else:
        text += f"<b>⏰ Tugash:</b> {format_date(data.get('finish_value'))}\n"

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_confirm_keyboard())


# ============ CONFIRM ============
@dp.callback_query(F.data == "confirm_contest")
async def confirm_contest(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = db.get_user(callback.from_user.id)

    contest_id = generate_contest_id()
    contest_data = {
        'contest_id': contest_id,
        'description': data.get('description'),
        'media_type': data.get('media_type', 'text'),
        'media_file_id': data.get('media_file_id'),
        'button_text': data.get('button_text', 'Qatnashaman'),
        'winners_count': data.get('winners_count', 1),
        'finish_type': data.get('finish_type'),
        'finish_value': str(data.get('finish_value')),
        'channels': data.get('selected_channels', []),
        'channel_id': data.get('channel_id'),
        'creator_id': user['id']
    }

    contest_id = db.create_contest(contest_data)
    result = await publish_contest(contest_data, str(contest_data['channel_id']))

    if result['success']:
        db.update_contest_published(contest_id, result['message_id'], result['post_link'])
        await callback.message.answer(f"✅ Konkurs yaratildi va nashr qilindi!\n\n🔗 {result['post_link']}",
                                      reply_markup=get_main_menu(user['is_admin']))
    else:
        await callback.message.answer(f"❌ Xatolik: {result['error']}", reply_markup=get_main_menu(user['is_admin']))

    db.clear_temp_contest_data(callback.from_user.id)
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "cancel_contest")
async def cancel_contest(callback: CallbackQuery, state: FSMContext):
    db.clear_temp_contest_data(callback.from_user.id)
    await state.clear()
    user = db.get_user(callback.from_user.id)
    await callback.message.answer("❌ Konkurs yaratish bekor qilindi.", reply_markup=get_main_menu(user['is_admin']))
    await callback.answer()


# ============ CONTEST ACTIONS ============
@dp.callback_query(F.data.startswith("join_"))
async def join_contest(callback: CallbackQuery):
    contest_id = callback.data.replace("join_", "")
    contest = db.get_contest(contest_id)

    if not contest or not contest['is_active']:
        await callback.answer("❌ Konkurs tugagan!", show_alert=True)
        return

    user = db.get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name
    )

    # Obuna tekshirish
    for channel in contest.get('channels', []):
        subscribed = await check_subscription(callback.from_user.id, channel['channel_username'])
        if not subscribed:
            await callback.answer(
                f"❌ {channel['channel_name']} kanaliga obuna bo'ling!",
                show_alert=True
            )
            return

    # Ishtirokchini qo'shish
    if db.add_participant(contest_id, user['id']):
        await callback.answer("✅ Siz konkursda qatnashdingiz!")

        # Tugmani yangilash
        await update_contest_button(contest_id)

        # Ishtirokchilar sonini tekshirish
        participants_count = db.get_participants_count(contest_id)

        # Agar ishtirokchilar soni finish_value ga yetgan bo'lsa
        if contest['finish_type'] == 'participants':
            target_count = int(contest['finish_value'])
            if participants_count >= target_count:
                # Yana bir marta tekshirish - konkurs hali tugamagan bo'lsa
                if db.is_contest_finished(contest_id):
                    logger.info(f"Konkurs allaqachon tugagan: {contest_id}")
                    return
                await finish_contest(contest, participants_count, f"{target_count} ishtirokchi yig'ildi")
    else:
        await callback.answer("❌ Siz allaqachon qatnashgansiz!")


@dp.callback_query(F.data.startswith("stats_"))
async def contest_stats(callback: CallbackQuery):
    contest_id = callback.data.replace("stats_", "")
    count = db.get_participants_count(contest_id)
    await callback.answer(f"📊 Ishtirokchilar soni: {count}", show_alert=True)


@dp.callback_query(F.data.startswith("view_contest_"))
async def view_contest(callback: CallbackQuery):
    contest_id = callback.data.replace("view_contest_", "")
    contest = db.get_contest(contest_id)
    if contest:
        text = f"<b>📋 Konkurs ID:</b> <code>{contest['contest_id']}</code>\n"
        text += f"<b>📊 Ishtirokchilar:</b> {db.get_participants_count(contest_id)}\n"
        text += f"<b>🏆 G'oliblar:</b> {contest['winners_count']}\n"
        text += f"<b>📢 Holat:</b> {'✅ Faol' if contest['is_active'] else '❌ Tugagan'}"
        await callback.message.answer(text, parse_mode=ParseMode.HTML,
                                      reply_markup=get_contest_detail_keyboard(contest_id, contest['is_active']))
    await callback.answer()


@dp.callback_query(F.data.startswith("end_contest_"))
async def end_contest_manual(callback: CallbackQuery):
    contest_id = callback.data.replace("end_contest_", "")
    contest = db.get_contest(contest_id)

    if not contest:
        await callback.answer("❌ Konkurs topilmadi!", show_alert=True)
        return

    user = db.get_user(callback.from_user.id)
    if contest['creator_id'] != user['id'] and not user['is_admin']:
        await callback.answer("❌ Siz bu konkursni tugata olmaysiz!", show_alert=True)
        return

    participants_count = db.get_participants_count(contest_id)
    await finish_contest(contest, participants_count, "Admin tomonidan tugatildi")
    await callback.answer("✅ Konkurs tugatildi va xabar yangilandi!")

@dp.callback_query(F.data.startswith("winners_"))
async def show_winners(callback: CallbackQuery):
    contest_id = callback.data.replace("winners_", "")
    contest = db.get_contest(contest_id)
    if contest:
        winners = db.get_random_winners(contest_id, contest['winners_count'])
        if not winners:
            await callback.answer("❌ Hali ishtirokchilar yo'q!")
            return
        text = "<b>🏆 G'oliblar:</b>\n\n"
        for i, winner in enumerate(winners, 1):
            name = winner['username'] or winner['full_name']
            text += f"{i}. @{name}\n"
        await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()


# ============ DELETE CHANNEL ============
@dp.callback_query(F.data.startswith("del_channel_"))
async def delete_channel(callback: CallbackQuery):
    channel_id = int(callback.data.replace("del_channel_", ""))
    channel = db.get_channel_by_id(channel_id)
    user = db.get_user(callback.from_user.id)

    if channel and channel['owner_id'] != user['id']:
        await callback.answer("❌ Bu sizning kanalingiz emas!", show_alert=True)
        return

    db.delete_channel(channel_id)
    await callback.answer("✅ Kanal o'chirildi!")
    channels = db.get_user_channels(user['id'])
    try:
        await callback.message.edit_reply_markup(reply_markup=get_my_channels_keyboard(channels))
    except:
        pass


# ============ BACK MENU ============
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    await callback.message.answer("🏠 Asosiy menyu:", reply_markup=get_main_menu(user['is_admin']))
    await callback.answer()


@dp.callback_query(F.data == "back_to_contests")
async def back_to_contests(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    contests = db.get_user_contests(user['id'])
    await callback.message.answer("📋 Sizning konkurslaringiz:", reply_markup=get_my_contests_keyboard(contests))
    await callback.answer()


# ============ ADMIN ============
@dp.callback_query(F.data == "admin_all_contests")
async def admin_all_contests(callback: CallbackQuery):
    try:
        cursor = db.conn.cursor()

        # Jami konkurslar soni
        cursor.execute('SELECT COUNT(*) FROM contests')
        total_contests = cursor.fetchone()[0]

        # Aktiv konkurslar soni
        cursor.execute('SELECT COUNT(*) FROM contests WHERE is_active = 1')
        active_contests = cursor.fetchone()[0]

        # Tugagan konkurslar soni
        cursor.execute('SELECT COUNT(*) FROM contests WHERE is_active = 0')
        finished_contests = cursor.fetchone()[0]

        text = f"<b>📊 KONKURSLAR STATISTIKASI</b>\n\n"
        text += f"📋 <b>Jami:</b> {total_contests}\n"
        text += f"✅ <b>Aktiv:</b> {active_contests}\n"
        text += f"❌ <b>Tugagan:</b> {finished_contests}"

        await callback.message.answer(text, parse_mode=ParseMode.HTML)
        await callback.answer()

    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {str(e)}")
        await callback.answer()


@dp.callback_query(F.data == "admin_all_users")
async def admin_all_users(callback: CallbackQuery):
    try:
        cursor = db.conn.cursor()

        # Jami foydalanuvchilar soni
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]

        # Adminlar soni
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        admin_users = cursor.fetchone()[0]

        # Oddiy foydalanuvchilar soni
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 0')
        normal_users = cursor.fetchone()[0]

        text = f"<b>👥 FOYDALANUVCHILAR STATISTIKASI</b>\n\n"
        text += f"👤 <b>Jami:</b> {total_users}\n"
        text += f"👑 <b>Adminlar:</b> {admin_users}\n"
        text += f"📝 <b>Oddiy:</b> {normal_users}"

        await callback.message.answer(text, parse_mode=ParseMode.HTML)
        await callback.answer()

    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {str(e)}")
        await callback.answer()


# ============ REKLAMA FUNKSIYALARI ============

@dp.callback_query(F.data == "admin_send_ad")
async def admin_send_ad(callback: CallbackQuery, state: FSMContext):
    """Admin reklama yuborish"""
    user = db.get_user(callback.from_user.id)
    if not user['is_admin']:
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    await state.set_state(SendReklama.waiting_for_ad_text)
    await callback.message.answer(
        "<b>📢 REKLAMA YUBORISH</b>\n\n"
        "Yubormoqchi bo'lgan reklama matnini yozing.\n"
        "Matn bilan birga rasm, video yoki GIF ham yuborishingiz mumkin.\n\n"
        "❗ Faqat 1 ta media fayl ishlatishingiz mumkin.\n\n"
        "Reklama BARCHA foydalanuvchilarga yuboriladi.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@dp.message(StateFilter(SendReklama.waiting_for_ad_text))
async def get_ad_text(message: Message, state: FSMContext):
    """Reklama matnini olish"""
    data = {'ad_text': message.html_text or message.text}

    if message.photo:
        data['ad_media_type'] = 'photo'
        data['ad_media_file_id'] = message.photo[-1].file_id
    elif message.video:
        data['ad_media_type'] = 'video'
        data['ad_media_file_id'] = message.video.file_id
    elif message.animation:
        data['ad_media_type'] = 'animation'
        data['ad_media_file_id'] = message.animation.file_id
    else:
        data['ad_media_type'] = 'text'
        data['ad_media_file_id'] = None

    await state.update_data(data)

    # Tasdiqlash uchun oldindan ko'rsatish
    ad_text = data['ad_text']
    ad_media_type = data['ad_media_type']
    ad_media_file_id = data['ad_media_file_id']

    # Foydalanuvchilar sonini olish
    cursor = db.conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]

    text = "<b>📢 REKLAMA MA'LUMOTLARI</b>\n\n"
    text += f"<b>📝 Matn:</b>\n{ad_text[:200]}...\n\n"
    text += f"<b>👥 Yuboriladigan foydalanuvchilar:</b> {total_users} ta\n\n"
    text += "✅ Reklamani yuborishni tasdiqlaysizmi?"

    await state.set_state(SendReklama.confirm)

    # Media bilan yuborish
    if ad_media_type == 'photo' and ad_media_file_id:
        await message.answer_photo(
            photo=ad_media_file_id,
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_reklama_confirm_keyboard()
        )
    elif ad_media_type == 'video' and ad_media_file_id:
        await message.answer_video(
            video=ad_media_file_id,
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_reklama_confirm_keyboard()
        )
    elif ad_media_type == 'animation' and ad_media_file_id:
        await message.answer_animation(
            animation=ad_media_file_id,
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_reklama_confirm_keyboard()
        )
    else:
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_reklama_confirm_keyboard()
        )


@dp.callback_query(F.data == "send_ad_confirm")
async def send_ad_confirm(callback: CallbackQuery, state: FSMContext):
    """Reklamani yuborish"""
    user = db.get_user(callback.from_user.id)
    if not user['is_admin']:
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    data = await state.get_data()
    ad_text = data.get('ad_text')
    ad_media_type = data.get('ad_media_type')
    ad_media_file_id = data.get('ad_media_file_id')

    # Barcha foydalanuvchilarni olish
    cursor = db.conn.cursor()
    cursor.execute('SELECT telegram_id FROM users')
    users = cursor.fetchall()

    if not users:
        await callback.message.answer("❌ Hech qanday foydalanuvchi topilmadi!")
        await state.clear()
        await callback.answer()
        return

    await callback.message.answer(
        f"<b>📢 REKLAMA YUBORILMOQDA...</b>\n\n"
        f"👥 {len(users)} ta foydalanuvchiga reklama yuboriladi.\n"
        f"⏳ Iltimos kuting...",
        parse_mode=ParseMode.HTML
    )

    success_count = 0
    fail_count = 0

    for user_row in users:
        user_id = user_row[0]
        try:
            if ad_media_type == 'photo' and ad_media_file_id:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=ad_media_file_id,
                    caption=ad_text,
                    parse_mode=ParseMode.HTML
                )
            elif ad_media_type == 'video' and ad_media_file_id:
                await bot.send_video(
                    chat_id=user_id,
                    video=ad_media_file_id,
                    caption=ad_text,
                    parse_mode=ParseMode.HTML
                )
            elif ad_media_type == 'animation' and ad_media_file_id:
                await bot.send_animation(
                    chat_id=user_id,
                    animation=ad_media_file_id,
                    caption=ad_text,
                    parse_mode=ParseMode.HTML
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=ad_text,
                    parse_mode=ParseMode.HTML
                )
            success_count += 1
            # Flood oldini olish uchun biroz kutish
            await asyncio.sleep(0.05)
        except Exception as e:
            fail_count += 1
            logger.error(f"Xabar yuborilmadi {user_id}: {e}")

    # Natija haqida xabar
    result_text = f"<b>📢 REKLAMA YUBORILDI!</b>\n\n"
    result_text += f"✅ <b>Yuborilgan:</b> {success_count}\n"
    result_text += f"❌ <b>Yuborilmagan:</b> {fail_count}\n"
    result_text += f"👥 <b>Jami:</b> {len(users)}"

    await callback.message.answer(result_text, parse_mode=ParseMode.HTML)

    # Adminga log yuborish
    await callback.message.answer(
        f"📝 <b>Reklama matni:</b>\n{ad_text[:500]}",
        parse_mode=ParseMode.HTML
    )

    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "cancel_ad_send")
async def cancel_ad_send(callback: CallbackQuery, state: FSMContext):
    """Reklama yuborishni bekor qilish"""
    await state.clear()
    user = db.get_user(callback.from_user.id)
    await callback.message.answer(
        "❌ Reklama yuborish bekor qilindi.",
        reply_markup=get_main_menu(user['is_admin'])
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_panel_back")
async def admin_panel_back(callback: CallbackQuery):
    """Admin panelga qaytish"""
    await callback.message.answer(
        "⚙️ Admin panel:",
        reply_markup=get_admin_panel()
    )
    await callback.answer()

# ============ MAIN ============
async def main():
    global checker_running
    logger.info("Bot ishga tushdi...")

    if not checker_running:
        checker_running = True
        asyncio.create_task(check_contests())
        logger.info("Konkurs tekshiruvchi background task ishga tushdi")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())