from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📊 Yangi konkurs yaratish")],
        [KeyboardButton(text="📋 Mening konkurslarim")],
        [KeyboardButton(text="📢 Mening kanallarim")],
        [KeyboardButton(text="❓ Yordam")],
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="⚙️ Admin panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def get_contest_action_keyboard(contest_id: str, button_text: str = "Qatnashaman", participants_count: int = 0) -> InlineKeyboardMarkup:
    """Konkurs tugmasi - ishtirokchilar soni bilan birga"""
    buttons = [
        [InlineKeyboardButton(
            text=f"{button_text} ({participants_count})",
            callback_data=f"join_{contest_id}"
        )]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_finish_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="👥 Ishtirokchilar soni bo'yicha", callback_data="finish_participants")],
        [InlineKeyboardButton(text="⏰ Vaqt bo'yicha", callback_data="finish_time")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Saqlash va nashr qilish", callback_data="confirm_contest")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_contest")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_channels_keyboard(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for channel in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {channel['channel_name']}",
            callback_data=f"select_channel_{channel['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="add_new_channel")])
    buttons.append([InlineKeyboardButton(text="✅ Davom etish", callback_data="channels_done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_my_channels_keyboard(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for channel in channels:
        buttons.append([InlineKeyboardButton(
            text=f"❌ {channel['channel_name']}",
            callback_data=f"del_channel_{channel['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="add_new_channel_menu")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_my_contests_keyboard(contests: list) -> InlineKeyboardMarkup:
    buttons = []
    for contest in contests[:10]:
        status = "✅" if contest['is_active'] else "❌"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {contest['contest_id']}",
            callback_data=f"view_contest_{contest['contest_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_contest_detail_keyboard(contest_id: str, is_active: bool) -> InlineKeyboardMarkup:
    buttons = []
    if is_active:
        buttons.append([InlineKeyboardButton(text="⏹ Konkursni tugatish", callback_data=f"end_contest_{contest_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="🏆 G'oliblarni ko'rish", callback_data=f"winners_{contest_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_contests")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_panel() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📊 Konkurslar soni", callback_data="admin_all_contests")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar soni", callback_data="admin_all_users")],
        [InlineKeyboardButton(text="📢 Reklama yuborish", callback_data="admin_send_ad")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_reklama_confirm_keyboard() -> InlineKeyboardMarkup:
    """Reklamani tasdiqlash tugmalari"""
    buttons = [
        [InlineKeyboardButton(text="✅ Yuborish", callback_data="send_ad_confirm")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_ad_send")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)