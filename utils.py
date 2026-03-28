import random
import string
from datetime import datetime, timedelta
from aiogram.types import Message, CallbackQuery
from aiogram import Bot


def generate_contest_id() -> str:
    """Unikal konkurs ID yaratish"""
    timestamp = datetime.now().strftime("%y%m%d%H%M%S")
    random_str = ''.join(random.choices(string.digits, k=4))
    return f"mylot{timestamp}{random_str}"


def format_date(date_str) -> str:
    """Sanani formatlash"""
    if isinstance(date_str, str):
        try:
            date_obj = datetime.fromisoformat(date_str)
        except:
            return date_str
    else:
        date_obj = date_str

    return date_obj.strftime("%d.%m.%Y %H:%M")


def parse_channel_input(text: str) -> dict:
    """Kanal username yoki linkni parse qilish"""
    text = text.strip()

    # @username format
    if text.startswith('@'):
        return {'username': text, 'type': 'username'}

    # t.me/username format
    if 't.me/' in text:
        username = text.split('t.me/')[-1].split('?')[0]
        if username.startswith('+'):
            return None
        return {'username': f'@{username}', 'type': 'link'}

    # Username
    if text and not text.startswith('http'):
        return {'username': f'@{text}', 'type': 'username'}

    return None


async def check_subscription(bot: Bot, user_id: int, channel_username: str) -> bool:
    """Foydalanuvchi kanalga obuna bo'lganligini tekshirish"""
    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False


async def get_channel_info(bot: Bot, channel_username: str) -> dict:
    """Kanal haqida ma'lumot olish"""
    try:
        chat = await bot.get_chat(chat_id=channel_username)
        return {
            'id': str(chat.id),
            'username': chat.username,
            'title': chat.title
        }
    except Exception as e:
        return None


def check_contest_finish(contest: dict) -> bool:
    """Konkurs tugaganligini tekshirish"""
    if not contest['is_active']:
        return True

    finish_type = contest['finish_type']
    finish_value = contest['finish_value']

    if finish_type == 'participants':
        # Ishtirokchilar soni bo'yicha tekshirish
        from database import db
        participants_count = db.get_participants_count(contest['contest_id'])
        return participants_count >= finish_value

    elif finish_type == 'time':
        # Vaqt bo'yicha tekshirish
        finish_time = datetime.fromisoformat(str(finish_value)) if isinstance(finish_value, str) else finish_value
        return datetime.now() >= finish_time

    return False


async def publish_contest(bot: Bot, contest: dict, channel_id: str) -> dict:
    """Konkursni kanalga nashr qilish"""
    from database import db

    # Kanal ma'lumotlarini olish
    channel = db.get_channel(channel_id)
    if not channel:
        return {'success': False, 'error': 'Kanal topilmadi'}

    # Xabar matnini tayyorlash
    text = f"📢 *YANGI KONKURS!*\n\n"
    text += f"{contest['description']}\n\n"
    text += f"🏆 *G'oliblar soni:* {contest['winners_count']}\n"

    if contest['finish_type'] == 'participants':
        text += f"👥 *Tugash:* {contest['finish_value']} ishtirokchi yig'ilganda\n"
    else:
        text += f"⏰ *Tugash:* {format_date(contest['finish_value'])}\n"

    # Xabarni yuborish
    try:
        if contest['media_type'] == 'photo' and contest['media_file_id']:
            message = await bot.send_photo(
                chat_id=channel_id,
                photo=contest['media_file_id'],
                caption=text,
                parse_mode='Markdown'
            )
        elif contest['media_type'] == 'video' and contest['media_file_id']:
            message = await bot.send_video(
                chat_id=channel_id,
                video=contest['media_file_id'],
                caption=text,
                parse_mode='Markdown'
            )
        elif contest['media_type'] == 'animation' and contest['media_file_id']:
            message = await bot.send_animation(
                chat_id=channel_id,
                animation=contest['media_file_id'],
                caption=text,
                parse_mode='Markdown'
            )
        else:
            message = await bot.send_message(
                chat_id=channel_id,
                text=text,
                parse_mode='Markdown'
            )

        # Tugmani qo'shish
        from keyboards import get_contest_action_keyboard
        await bot.edit_message_reply_markup(
            chat_id=channel_id,
            message_id=message.message_id,
            reply_markup=get_contest_action_keyboard(contest['contest_id'])
        )

        post_link = f"https://t.me/{channel['channel_username'].replace('@', '')}/{message.message_id}"

        return {'success': True, 'message_id': message.message_id, 'post_link': post_link}

    except Exception as e:
        return {'success': False, 'error': str(e)}