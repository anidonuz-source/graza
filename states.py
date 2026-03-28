from aiogram.fsm.state import State, StatesGroup

class CreateContest(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    waiting_for_button_text = State()
    waiting_for_channels = State()
    waiting_for_winners_count = State()
    waiting_for_publish_channel = State()
    waiting_for_finish_type = State()
    waiting_for_finish_value = State()
    confirm = State()

class AddChannel(StatesGroup):
    waiting_for_channel = State()

class SendReklama(StatesGroup):
    waiting_for_ad_text = State()
    waiting_for_ad_media = State()
    confirm = State()