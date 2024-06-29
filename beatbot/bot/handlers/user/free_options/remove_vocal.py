from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.states.free_option import Remove_Vocal
from bot.keyboards.inline import KB_GO_FREE_OPTIONS
from bot.misc.messages import REMOVE_VOCAL_MESSAGE
from bot.misc.free_options_settings import is_supported_format
from bot.misc import save_audio, SubChecker, validate_msg_file
from bot.web.requests.Service import free_option_req

remove_vocal_router = Router()


@remove_vocal_router.callback_query(F.data == 'options:remove_vocal')
async def remove_vocal(c: CallbackQuery,
                   state: FSMContext,
                   user):
    if not await SubChecker.is_member(c.message.chat.id):
        return await c.message.reply('Бесплатные опции доступны только подписчикам @beatbotnews')

    await state.set_state(Remove_Vocal.audio)
    await c.message.edit_text(REMOVE_VOCAL_MESSAGE, reply_markup=KB_GO_FREE_OPTIONS)


@remove_vocal_router.message(Remove_Vocal.audio)
async def get_audio(message: Message,
                    state: FSMContext,
                    user):
    if is_supported_format(message, 'remove_vocal'):

        f_size = 20  # MB
        if not await validate_msg_file(message, f_size):
            return message.answer(f'🔊 Файл слишком большой. Пожалуйста, загрузите файл размером до {f_size}мб.')

        await state.clear()

        save_path = await save_audio(message, str(message.chat.id), random_filename=True)
        await free_option_req('remove_vocal', message.chat.id, save_path)

    else:
        await message.answer('Неподдерживаемый формат')
        await message.delete()
