from aiogram.fsm.state import State, StatesGroup


class VoiceInputStates(StatesGroup):
    """Промежуточный шаг: пользователь подтверждает распознанный с голоса текст."""

    confirm_transcription = State()
