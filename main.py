import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, ContentType

# Инструмент для выборки путей к файлам
from glob import glob
# Файл данных
import config
# Файл для безопасного запуска бота
import launch
# Файл звковых опций
from sound_options import sound_options
# Файл обработчика запросов к БД
import db_handler
# Клавиатура
import keyboards
# Для конфигурирования и создания платежа
from yookassa import Configuration,Payment

import itertools
from os import remove, walk, path, makedirs
import json
from datetime import date, timedelta, datetime

# Установка уровня логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=config.TOKEN)
dp = Dispatcher(bot)

# Подключение Юкассы
Configuration.account_id = config.SHOP_ID
Configuration.secret_key = config.SHOP_API_TOKEN

# Цена бита
beat_price = config.beat_price # RUB

# Начальный баланс пользователя при добавлении в БД
start_balance = config.start_balance # RUB

# Количество битов для создания
beats = config.beats

# Константы сообщений
MENU_MESSAGE_TEXT = "🔣 <b>МЕНЮ</b>\n\nТы находишься в лучшем и единственном боте который может сгенерировать для тебя:\n\n— 🎙️<b>Бит под голос</b>🎙️\n— ⏩ Сделать <b>speed up</b>\n— ⏪ Сделать <b>slowed + reverb</b>\n\nНаш телеграм-канал: @beatbotnews"
STYLES_MESSAGE_TEXT = '🪩 *СТИЛИ*\n\nЯ могу генерировать в разных стилях, каждый из них имеет свои особенности. Такие биты подойдут под запись голоса.\n\n*⏺ - Стиль*\n⏺ - Темп\n⏺ - Лад\n⏺ - Формат'

# Безопасный запуск
async def safe_launch():
    if launch.mailing_list is not None:
        try:
            for chat_id in launch.mailing_list:
                beat_keyboard = InlineKeyboardMarkup().add(keyboards.btn_generate_beat)
                await bot.send_message(chat_id, '⚙️ Сожалею, но во время создания твоих битов бот перезапустился\n\nЭто происходит очень редко, но необходимо для стабильной работы бота. Деньги за транзакцию не сняты.\n\nТы можешь заказать бит ещё раз 👉', reply_markup=beat_keyboard)          
            for chat_id in launch.chat_ids_by_messages_to_del_ids:
                messages_ids = db_handler.get_beats_versions_messages_ids(chat_id).split(', ')
                for mes_id in messages_ids:
                    await bot.delete_message(chat_id, mes_id)
                db_handler.del_beats_versions_messages_ids(chat_id)
        except Exception as e:
            print(e)
    if launch.removes_mailing_list:
        try:
            for chat_id in launch.removes_mailing_list:
                beat_keyboard = InlineKeyboardMarkup().add(keyboards.btn_free_options)
                await bot.send_message(chat_id, '⚙️ Сожалею, но во время разделения трека бот перезапустился\n\nЭто происходит очень редко, но необходимо для стабильной работы бота. Твоё количество использований бесплатных опций не уменьшилось.\n\nТы можешь использовать опцию ещё раз 👉', reply_markup=beat_keyboard)          
        except Exception as e:
            print(e)

# Обработка команды /start
@dp.message_handler(commands=['start'])
async def send_hello(message: types.Message):
    # Отправка сообщения
    await bot.send_message(message.chat.id, text='Привет! 👋\n\nЯ телеграм-бот, который может генерировать биты в разных стилях.\n\nМоя главная особенность - доступная 💰 цена и большой выбор стилей. Ты можешь выбрать любой стиль, который тебе нравится, и я создам для тебя уникальный бит.\n\nНе упусти возможность создать свой собственный звук и выделиться на фоне других исполнителей! 🎶\n\nЧтобы начать, используй команду */menu*', parse_mode='Markdown')

# Обработка команды /menu
@dp.message_handler(commands=['menu'])
async def menu(message: types.Message):
    # Отправка сообщения

    await bot.send_message(message.chat.id, text=MENU_MESSAGE_TEXT, parse_mode='html', reply_markup=keyboards.menu_keyboard)
    # Добавление в БД
    # Имя и фамилия пользователя
    user_initials = f'{message.from_user.first_name} {message.from_user.last_name}'
    # Если пользователь уже добавлен то повторная запись не произойдет
    db_handler.add_user(message.chat.username, message.chat.id, user_initials, start_balance)

## Обработка текста

@dp.message_handler()
async def echo(message: types.Message):
    await bot.send_message(message.chat.id, 'Я не воспринимаю текстовые команды\n\nВызвать меню можно по команде /menu или нажав на кнопку в нижнем левом углу экрана.')

## Обработка аудио файлов.

# Функция для проверки размера директории users_sounds
def get_directory_size(directory):
    total_size = 0
    for dirpath, _, filenames in walk(directory):
        for f in filenames:
            fp = path.join(dirpath, f)
            total_size += path.getsize(fp)
    return total_size

# Функция для проверки подписки на канал
async def check_subscription(user_id, channel_username, status=None):
    chat_member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
    print(chat_member)
    try:
        if status is None:
            if chat_member['status']!='left':
                return True
        elif status=='admin':
            
            if chat_member['status']=='administrator':
                return True
            else:
                return False
    except Exception as e:
        print(repr(e))
        return False
    
# Функция для восстановления лимитов на опции
async def refill_limits(chat_id):

    date1 = date.today()
    date2 = db_handler.get_last_updated_limits(chat_id)
 
    time_difference = abs(date2 - date1)

    if time_difference > timedelta(hours=24):
        db_handler.refill_limits(chat_id)

# Функция для проверки готовности разделенного ремувером файла.
async def check_removes_response(chat_id, message_id):
    try:
        order_number = 0

        # Установить processing для пользователя
        db_handler.set_processing(chat_id)

        while True:

            if db_handler.get_removes_ready(chat_id) == 1:
                db_handler.del_removes_ready(chat_id)
                edit_message = await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f'🔄 Отправляю вокал и минус...', parse_mode='Markdown')  

                return True

            new_order_number = db_handler.get_options_query_by_chat_id(chat_id)
            if new_order_number != order_number:
                order_number = new_order_number
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f'💽 Разделяю трек, на это время бот *не будет* реагировать\n\nТвоё место в очереди: *{order_number}*\n\n🔽Вокал и минус появятся снизу🔽', parse_mode='Markdown')  

            await asyncio.sleep(2*order_number)
    except Exception as e:
        print(e)
        return False

## Обработчик для аудиофайлов в формате mp3

@dp.message_handler(content_types=ContentType.AUDIO)
async def handle_audio_file(message: types.Message):
    chat_id = message.chat.id
    try: 
        if await get_user(chat_id):
            # Проверить, не находится ли пользователь в processing
            if db_handler.get_processing(chat_id) == 0:
                user = message.from_user
                is_subscribed = await check_subscription(user.id, '@beatbotnews')
                if is_subscribed:
                    if db_handler.get_wait_for_file(chat_id) == 1:
                        
                        db_handler.del_wait_for_file(chat_id)

                        audio = message.audio
                        chosen_style = db_handler.get_chosen_style(chat_id)

                        # Восстановить лимиты если прошло время
                        await refill_limits(chat_id)

                        audio_extension = audio.file_name.split('.')[-1]

                        if chosen_style in [keyboards.options[keyboards.OPTIONS_BUTTONS[1]], keyboards.options[keyboards.OPTIONS_BUTTONS[0]], keyboards.options[keyboards.OPTIONS_BUTTONS[2]]]:   
                            # Установить processing для пользователя
                            db_handler.set_processing(chat_id)
                            
                            if audio_extension == 'mp3' and chosen_style in [keyboards.options[keyboards.OPTIONS_BUTTONS[1]], keyboards.options[keyboards.OPTIONS_BUTTONS[0]]]:
                                if db_handler.get_free_options_limit(chat_id) > 0:
                                    
                                    # Проверяем размер директории users_sounds
                                    total_size_mb = get_directory_size("users_sounds") / (1024 * 1024)
                                    
                                    if total_size_mb > 500:
                                        await bot.send_message(chat_id, "Извините, бот перегружен. Пожалуйста, попробуйте позже.")
                                        
                                        # Удалить processing для пользователя
                                        db_handler.del_processing(chat_id)
                                        
                                        return

                                    # Проверяем размер загруженного файла
                                    if audio.file_size > 15360 * 1024:
                                        await bot.send_message(chat_id, "🔊 Файл слишком большой. Пожалуйста, загрузите файл размером до 15мб.")
                                        
                                        # Удалить processing для пользователя
                                        db_handler.del_processing(chat_id)
                                        
                                        return

                                    # Путь к директории для сохранения файла
                                    user_dir = f"users_sounds/{chat_id}"

                                    # Создаем директорию пользователя, если она не существует
                                    makedirs(user_dir, exist_ok=True)

                                    # Скачиваем файл на сервер
                                    await audio.download(destination_file=f'{user_dir}/sound.mp3')

                                    if db_handler.get_chosen_style(chat_id) == keyboards.options[keyboards.OPTIONS_BUTTONS[0]]:
                                        # УСКОРИТЬ ЗВУК
                                        sound_options.speed_up(audio, user_dir)

                                        # Отправляем обратно пользователю обработанный файл
                                        with open(f'{user_dir}/sound.mp3', 'rb') as f:
                                            await bot.send_audio(chat_id, audio=f, title='tg: @NeuralBeatBot - speed up')

                                        # Прибавляем к количеству исопльзуемых опции
                                        db_handler.get_free_option(chat_id)

                                        # Удаляем временный файл
                                        remove(f'{user_dir}/sound.mp3')

                                        # Если нет премиум подписки, отнять от дневного лимита
                                        if db_handler.get_has_subscription(chat_id):
                                            # Если подписка устарела
                                            if db_handler.get_subscription_expiry_date(chat_id) < datetime.now().date():        
                                                db_handler.del_subscription(chat_id)
                                                db_handler.draw_free_options_limit(chat_id)
                                                await bot.send_message(chat_id, "🌀 Ваша подписка закончилась, для вас снова действуют лимиты.")
                                        else:  
                                            db_handler.draw_free_options_limit(chat_id)
                                        
                                    elif db_handler.get_chosen_style(chat_id) == keyboards.options[keyboards.OPTIONS_BUTTONS[1]]:
                                        # ЗАМЕДЛИТЬ ЗВУК
                                        sound_options.slow_down(audio, user_dir)

                                        # Отправляем обратно пользователю обработанный файл
                                        with open(f'{user_dir}/sound.mp3', 'rb') as f:
                                            await bot.send_audio(chat_id, audio=f, title='tg: @NeuralBeatBot - slowed + rvb')

                                        # Прибавляем к количеству исопльзуемых опции
                                        db_handler.get_free_option(chat_id)

                                        # Удаляем временный файл
                                        remove(f'{user_dir}/sound.mp3')

                                        # Если нет премиум подписки, отнять от дневного лимита
                                        if db_handler.get_has_subscription(chat_id):
                                            # Если подписка устарела
                                            if db_handler.get_subscription_expiry_date(chat_id) < datetime.now().date():        
                                                db_handler.del_subscription(chat_id)
                                                db_handler.draw_free_options_limit(chat_id)
                                                await bot.send_message(chat_id, "🌀 Ваша подписка закончилась, для вас снова действуют лимиты.")    
                                        else:  
                                            db_handler.draw_free_options_limit(chat_id)

                                else:
                                    await bot.send_message(chat_id, 'Ваш лимит по бесплатным опциям на сегодня исчерпан.')

                            elif audio_extension in ['mp3', 'wav'] and db_handler.get_chosen_style(chat_id) == keyboards.options[keyboards.OPTIONS_BUTTONS[2]]:
                                if db_handler.get_removes_limit(chat_id) > 0:
                                    # Проверяем размер директории users_sounds
                                    total_size_mb = get_directory_size("users_sounds") / (1024 * 1024)
                                    
                                    if total_size_mb > 300:
                                        await bot.send_message(chat_id, "Извините, бот перегружен. Пожалуйста, попробуйте позже.")
                                        
                                        # Удалить processing для пользователя
                                        db_handler.del_processing(chat_id)
                                        
                                        return

                                    # Проверяем размер загруженного файла
                                    if audio.file_size > 80000 * 1024:
                                        await bot.send_message(chat_id, "🔊 Файл слишком большой. Пожалуйста, загрузите файл размером до 80мб.")
                                        
                                        # Удалить processing для пользователя
                                        db_handler.del_processing(chat_id)
                                        
                                        return
                                    
                                    # Проверяем длительность аудио
                                    max_duration_seconds = 4 * 60  # 4 минуты в секундах
                                    print(audio.duration)
                                    if audio.duration > max_duration_seconds:  # Преобразуем в миллисекунды
                                        await bot.send_message(chat_id, "🔊 Аудио слишком длинное. Пожалуйста, загрузите аудио длительностью до 4 минут.")
                                        # Удалить processing для пользователя
                                        db_handler.del_processing(chat_id)
                                        return

                                    # Путь к директории для сохранения файла
                                    user_dir = f"users_sounds/{chat_id}"

                                    # Создаем директорию пользователя, если она не существует
                                    makedirs(user_dir, exist_ok=True)

                                    file = f'sound.{audio.file_name.split(".")[-1]}'

                                    edit_message = await bot.send_message(chat_id, '🔄 Подготавливаю ремувер...')

                                    # Скачиваем файл на сервер
                                    await audio.download(destination_file=f'{user_dir}/{file}')

                                    edit_message = await bot.edit_message_text(chat_id=chat_id, message_id=edit_message.message_id, text=f'✅ Подготавливаю ремувер...', parse_mode='Markdown') 
                                    
                                    # Добавить в очередь 
                                    db_handler.set_options_query(chat_id, audio_extension)

                                    await asyncio.sleep(1)

                                    db_handler.del_removes_ready(chat_id)
                                    
                                    if await check_removes_response(chat_id, edit_message.message_id):

                                        # Отправляем обратно пользователю обработанныt файлы
                                        with open(f'{user_dir}/final_vocals.{audio_extension}', 'rb') as f:
                                            await bot.send_audio(chat_id, audio=f, title='tg: @NeuralBeatBot - Vocals')

                                        with open(f'{user_dir}/final_accompaniment.{audio_extension}', 'rb') as f:
                                            await bot.send_audio(chat_id, audio=f, title='tg: @NeuralBeatBot - Instruments')
                                        
                                        edit_message = await bot.edit_message_text(chat_id=chat_id, message_id=edit_message.message_id, text=f'✅ Отправлено', parse_mode='Markdown') 

                                        # Прибавляем к количеству исопльзуемых опции
                                        db_handler.get_free_option(chat_id)
                                        
                                        # Если нет премиум подписки, отнять от дневного лимита
                                        if db_handler.get_has_subscription(chat_id):
                                            # Если подписка устарела
                                            if db_handler.get_subscription_expiry_date(chat_id) < datetime.now().date():        
                                                db_handler.del_subscription(chat_id)
                                                db_handler.draw_removes_limit(chat_id)
                                                await bot.send_message(chat_id, "🌀 Ваша подписка закончилась, для вас снова действуют лимиты.")    
                                        else:  
                                            db_handler.draw_free_options_limit(chat_id)
                                        
                                    
                                    for file in glob(f'{user_dir}/*.*'):
                                        remove(file)

                                else:
                                    await bot.send_message(chat_id, 'Ваш лимит по бесплатным ремувам на сегодня исчерпан.')
                            else:
                                await bot.send_message(chat_id, '⚠️ Неподдерживаемый формат аудиофайла')

                            # Удалить processing для пользователя
                            db_handler.del_processing(chat_id)
                        else:
                            await bot.send_message(chat_id, '🔀 Похоже, вы начали генерацию бита. Если вы хотите воспользоваться бесплатными функциями: выберите нужную в разделе с бесплатными функциями.')
                    else:
                        await bot.send_message(chat_id, 'Сначала выбери бесплатную опцию', reply_markup=keyboards.free_keyboard)
                else:
                    await bot.send_message(chat_id, text=' Бесплатные опции доступны только подписчикам канала', parse_mode='Markdown')
    except Exception as e:
        print(repr(e))
        await bot.send_message(chat_id, '⚠️ Произошла ошибка на сервере, попробуйте ещё раз, и если она повторится обратитесь в поддержку.', reply_markup=keyboards.free_keyboard)
        # Удалить processing для пользователя
        db_handler.del_processing(message.chat.id)   
        db_handler.del_options_query_by_chat_id(chat_id)

## Обработка кнопок

# Обработка кнопок интерфейса
async def get_user(chat_id):
    if db_handler.get_user(chat_id) == False:
        # Отправка сообщения
        await bot.send_message(chat_id, 'Нужно перезапустить бота командой /start')
        return False
    else:
        return True

async def reset_chosen_params(chat_id: int) -> None:
    db_handler.del_chosen_bpm(chat_id)
    db_handler.del_chosen_style(chat_id)

@dp.callback_query_handler(lambda c: c.data in keyboards.STYLES_BUTTON)
async def return_to_styles(c: types.CallbackQuery):
    chat_id = c.message.chat.id
    if await get_user(chat_id):
        # Проверить, не находится ли пользователь в beats_generating
        if db_handler.get_beats_generating(chat_id) == 0:
            # Проверить, не находится ли пользователь в processing
            if db_handler.get_processing(chat_id) == 0:
                # Установить processing для пользователя
                db_handler.set_processing(chat_id)

                # Обнулить выбранные пользователем параметры бита
                await reset_chosen_params(chat_id)

                if user_chosen_bpm_style.get(chat_id) is not None: 
                    del user_chosen_bpm_style[chat_id]
                
                # Отправка сообщения
                await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=STYLES_MESSAGE_TEXT, reply_markup=keyboards.styles_keyboard, parse_mode='Markdown')
                
                # Удалить processing для пользователя
                db_handler.del_processing(chat_id)
        else:
            # Отправка оповещения
            await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Ты не можешь заказать еще один бит во время осуществления текущего заказа.', show_alert=True)

@dp.callback_query_handler(lambda c: c.data in keyboards.UNDO_BUTTON or c.data in keyboards.MENU_BUTTON)
async def return_to_menu(c: types.CallbackQuery):
    chat_id = c.message.chat.id
    if await get_user(chat_id):
        # Обнулить выбранные пользователем параметры бита
        await reset_chosen_params(chat_id)
        # Отправка сообщения
        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=MENU_MESSAGE_TEXT, reply_markup=keyboards.menu_keyboard, parse_mode='html')

@dp.callback_query_handler(lambda c: c.data in keyboards.MENU_BUTTONS)
async def show_menu(c: types.CallbackQuery):
    try:  
        chat_id = c.message.chat.id
        pressed_button = c.data

        if await get_user(chat_id):
            if pressed_button == keyboards.BUTTON_GENERATE_BEAT:
                # Проверить, не находится ли пользователь в beats_generating
                if db_handler.get_beats_generating(chat_id) == 0:
                    # Проверить, не находится ли пользователь в processing
                    if db_handler.get_processing(chat_id) == 0:
                        # Установить processing для пользователя
                        db_handler.set_processing(chat_id)

                        # Обнулить выбранные пользователем параметры бита
                        await reset_chosen_params(c.message.chat.id)

                        # Отправка сообщения
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=STYLES_MESSAGE_TEXT, reply_markup=keyboards.styles_keyboard, parse_mode='Markdown')
                        
                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                else:
                    # Отправка оповещения
                    await bot.answer_callback_query(callback_query_id=c.id, text='Ты не можешь заказать еще один бит во время осуществления текущего заказа.', show_alert=True)

            elif pressed_button == keyboards.BUTTON_BALANCE:
                # Запрос баланса пользователя в таблице users
                balance = db_handler.get_balance(chat_id)
                # Отправка сообщения
                await bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text=f'*💰 БАЛАНС*\n\nНа твоем балансе: *{balance}₽*\n\n👉 Выбери сумму для пополнения:', reply_markup=keyboards.balance_keyboard, parse_mode='Markdown')

            elif pressed_button == keyboards.BUTTON_ABOUT:
                # Отправка сообщения
                await bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text=f'*🏡 О НАС*\n\n📌 Услугу предоставляет:\n\n👤 ИНН: 910821614530\n\n✉️ Почта для связи:\ntech.beatbot@mail.ru\n\n🌐 Официальный сайт:\nhttps://beatmaker.site', reply_markup=keyboards.undo_keyboard, parse_mode='Markdown')
            
            elif pressed_button == keyboards.BUTTON_TUTORIAL:          
                # Отправка сообщения
                await bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text=f'https://t.me/beatbotnews/31', reply_markup=keyboards.undo_keyboard, parse_mode='Markdown')

    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)


# Создает платёж
async def payment(value,description):
	payment = Payment.create({
    "amount": {
        "value": value,
        "currency": "RUB"
    },
    "payment_method_data": {
        "type": "bank_card"
    },
    "confirmation": {
        "type": "redirect",
        "return_url": "https://web.telegram.org/k/#@NeuralBeatBot"
    },
    "capture": True,
    "description": description
	})

	return json.loads(payment.json())

# Подтверждает наличие "товара"
@dp.pre_checkout_query_handler()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# Перед запуском асинхронной функции создается пара ключ значение user: value.
# Это сделано для того, чтобы не создавать лишние ссылки и не запускать лишние асинхронные функции, для экономии ресурсов
users_payment_transactions = {}

# Асинхронная функция проверки статуса платежа
async def check_payment(payment_id, c, type=''):
    payment = json.loads((Payment.find_one(payment_id)).json())
    
    # db_handler.set_payment_checking(c.message.chat.id)

    # Удаление пары ключ значение user: value.
    def del_user_payment_transactions(chat_id, value):
        users_payment_transactions[chat_id].remove(value)

    while payment['status'] == 'pending':
        payment = json.loads((Payment.find_one(payment_id)).json())
        await asyncio.sleep(3)

    if payment['status']=='succeeded':
        print("SUCCSESS RETURN")
        if type == 'balance':
            # Обновить баланс в БД
            db_handler.top_balance(c.message.chat.id, c.data.split('₽')[0])
            
            await bot.send_message(c.message.chat.id, f'💵 Твой баланс пополнен на {c.data}', reply_markup=keyboards.to_menu_keyboard)
            # Удалить payment_checking для пользователя
            # db_handler.del_payment_checking(c.message.chat.id)

            del_user_payment_transactions(c.message.chat.id, c.data)
            
            return True
        
        elif type == 'subscription':
            # Получаем текущую дату
            current_date = datetime.now().date()

            # Добавляем 30 дней к текущей дате
            end_date = current_date + timedelta(days=30)

            # Преобразуем дату в строку в нужном формате (дд.мм.гггг)
            end_date_str = end_date.strftime('%d.%m.%Y')

            # Ваш код для отправки сообщения
            await bot.send_message(c.message.chat.id, f'⚡️ Твоя премиум подписка активна до *{end_date_str}*', reply_markup=keyboards.to_menu_keyboard, parse_mode='Markdown')

            db_handler.set_subscription(c.message.chat.id, end_date_str)
            
            del_user_payment_transactions(c.message.chat.id, c.data)
            
            return True
    else:
        print("BAD RETURN")
        # await bot.send_message(c.message.chat.id, 'Время ожидания на оплату по ссылке истекло.')
        # Удалить payment_checking для пользователя
        # db_handler.del_payment_checking(c.message.chat.id)

        del_user_payment_transactions(c.message.chat.id, c.data)
        return False

@dp.callback_query_handler(lambda c: c.data in keyboards.BALANCE_BUTTONS or c.data == keyboards.PREMIUM_BUTTON)
async def prepare_payment(c: types.CallbackQuery):
    try:

        chat_id = c.message.chat.id

        if await get_user(chat_id):
            # Проверить, не находится ли пользователь в beats_generating
            if db_handler.get_beats_generating(chat_id) == 0:
                # Проверить, не находится ли пользователь в processing
                if db_handler.get_processing(chat_id) == 0:
                    
                    # Установить processing для пользователя
                    db_handler.set_processing(chat_id)

                    if users_payment_transactions.get(chat_id) is not None and c.data in users_payment_transactions[chat_id]:
                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                        return await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Вам уже сгенерирована ссылка на эту сумму для оплаты, пожалуйста оплатите по ней.', show_alert=True)
                                
                    # Добавление транзакции оплаты пользователя
                    if users_payment_transactions.get(chat_id) is None:
                        users_payment_transactions[chat_id] = []
                    users_payment_transactions[chat_id].append(c.data)

                    if c.data == keyboards.PREMIUM_BUTTON:

                        # Если нет премиум подписки, отнять от дневного лимита
                        if db_handler.get_has_subscription(chat_id):
                            # Если подписка устарела
                            if db_handler.get_subscription_expiry_date(chat_id) < datetime.now().date():        
                                pass
                            else:
                                await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text='⚡️ У вас уже активна премиум подписка', reply_markup=keyboards.to_menu_keyboard, parse_mode='html')
                                
                                # Удалить processing для пользователя
                                db_handler.del_processing(chat_id)
                        else:  
                        
                            # Получение цены из callback_data
                            price = 50

                            print(users_payment_transactions)
                            
                            # Отправка счета пользователю
                            payment_data = await payment(price, f'Оплата премиум подписки на месяц: {price}₽')
                            payment_id = payment_data['id']
                            confirmation_url = payment_data['confirmation']['confirmation_url'] 
                            # Создаем объект кнопки
                            btn = types.InlineKeyboardButton(f'Оплатить {price}₽', url=confirmation_url)
                            # Создаем объект клавиатуры и добавляем на нее кнопку
                            keyboard = types.InlineKeyboardMarkup()
                            keyboard.add(btn)
                            await bot.send_message(c.message.chat.id, f'💳 Нажмите на ссылку под сообщением, оплатите удобным вам способом.\n\n💾 Идентификатор чата - *{c.message.chat.id}*\nУслугу предоставляет: ИНН: 910821614530\n\n🎟️ Заказывая услугу, вы соглашаетесь с договором оферты: https://beatmaker.site/offer\n\n✉️ Техническая поддержка: *tech.beatbot@mail.ru*\n\nПосле оплаты автоматически будет активирована премиум подписка на месяц.', reply_markup=keyboard, parse_mode='Markdown')
                            
                            # Удалить processing для пользователя
                            db_handler.del_processing(chat_id)
                            
                            await check_payment(payment_id, c, 'subscription')
                    
                    else:

                        # Получение цены из callback_data
                        price = int(c.data.split('₽')[0])

                        print(users_payment_transactions)
                        
                        # Отправка счета пользователю
                        payment_data = await payment(price, f'Пополнение баланса на {price}₽')
                        payment_id = payment_data['id']
                        confirmation_url = payment_data['confirmation']['confirmation_url'] 
                        # Создаем объект кнопки
                        btn = types.InlineKeyboardButton(f'Оплатить {price}₽', url=confirmation_url)
                        # Создаем объект клавиатуры и добавляем на нее кнопку
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(btn)
                        await bot.send_message(c.message.chat.id, f'💳 Нажмите на ссылку под сообщением, оплатите удобным вам способом.\n\n💾 Идентификатор чата - *{c.message.chat.id}*\nУслугу предоставляет: ИНН: 910821614530\n\n🎟️ Заказывая услугу, вы соглашаетесь с договором оферты: https://beatmaker.site/offer\n\n✉️ Техническая поддержка: *tech.beatbot@mail.ru*', reply_markup=keyboard, parse_mode='Markdown')
                        
                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                        
                        await check_payment(payment_id, c, 'balance')
                    
                    
            else:
                # Отправка оповещения
                await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Ты не можешь пополнить баланс во время генерации бита.', show_alert=True)
    except Exception as e:   
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id) 

@dp.callback_query_handler(lambda c: c.data in keyboards.STYLES_BUTTONS)
async def show_bpm(c: types.CallbackQuery):
    try:
        chat_id = c.message.chat.id
        user_chosen_style = c.data

        if await get_user(chat_id):     
            # Проверить, не находится ли пользователь в beats_generating
            if db_handler.get_beats_generating(chat_id) == 0:
                # Проверить, не находится ли пользователь в processing
                if db_handler.get_processing(chat_id) == 0:
                    if db_handler.get_chosen_style(chat_id) == '':
                        # Установить processing для пользователя
                        db_handler.set_processing(chat_id)

                        db_handler.set_chosen_style(chat_id, user_chosen_style)  

                        if user_chosen_bpm_style.get(chat_id) is None: 
                            current_bpm = keyboards.BPM_BUTTONS[user_chosen_style][1]
                            
                            user_chosen_bpm_style[chat_id] = [current_bpm, user_chosen_style] 

                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'🪩 *ТЕМП*\n\nТеперь отрегулируй темп:\n\n*{keyboards.BPM_BUTTONS[user_chosen_style][0]}* - замедлено\n*{keyboards.BPM_BUTTONS[user_chosen_style][1]}* - нормально\n*{keyboards.BPM_BUTTONS[user_chosen_style][2]}* - ускорено\n\nРегулируй желаемый bpm кнопками на клавиатуре. *Подтверди* выбранный темп: *{keyboards.BPM_BUTTONS[user_chosen_style][1]}*\n\n✅ - {user_chosen_style}\n*⏺ - Темп*\n⏺ - Лад\n⏺ - Формат\n\n', reply_markup=keyboards.bpm_keyboard, parse_mode='Markdown') 
                        
                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                    else:
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'⚠️ Похоже, что ты уже выбрал другой стиль в другом сообщении, закончи выбор параметров твоего бита там же\n\n...или начни новый выбор параметров здесь 👉', reply_markup=keyboards.to_styles_keyboard, parse_mode='Markdown')

            else:
                # Отправка оповещения
                await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Ты не можешь заказать еще один бит во время осуществления текущего заказа.', show_alert=True)

    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)

@dp.callback_query_handler(lambda c: c.data in keyboards.CATEGORIES_BUTTONS)
async def free_options(c: types.CallbackQuery):
    chat_id = c.message.chat.id
    pressed_button = c.data
    try:
        if await get_user(chat_id):
            if pressed_button == keyboards.BUTTON_CATEGORY_FREE_OPTIONS:
                # Проверить, не находится ли пользователь в beats_generating
                if db_handler.get_beats_generating(chat_id) == 0:
                    # Проверить, не находится ли пользователь в processing
                    if db_handler.get_processing(chat_id) == 0:
                        # Установить processing для пользователя
                        db_handler.set_processing(chat_id)

                        # Обнулить выбранные пользователем параметры бита
                        await reset_chosen_params(c.message.chat.id)

                        # Отправка сообщения
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text='🆓 *БЕСПЛАТНЫЕ ОПЦИИ*\n\nМы предоставляем некоторые бесплатные опции для обработки вашего звука.\n\nЕжесуточные лимиты:\n*3* использования Remove Vocal\n*10* использований всех остальных опций\n\nОбработчик поддерживает *.mp3* формат для всех опций, а также *.wav* для вокал-ремувера.\nБесплатные опции доступны только подписчикам нашего официального канала: *@beatbotnews*', reply_markup=keyboards.free_keyboard, parse_mode='Markdown')
                        
                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                else:
                    # Отправка оповещения
                    await bot.answer_callback_query(callback_query_id=c.id, text='Ты не можешь воспользоваться беслпатными опциями во время генерации бита', show_alert=True)

    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)
    
@dp.callback_query_handler(lambda c: c.data in keyboards.OPTIONS_BUTTONS)
async def process_the_sound(c: types.CallbackQuery):
    chat_id = c.message.chat.id
    pressed_button = c.data
    try:
        if await get_user(chat_id):
            if db_handler.get_beats_generating(chat_id) == 0:
                # Проверить, не находится ли пользователь в processing
                if db_handler.get_processing(chat_id) == 0:
                     
                    if pressed_button == keyboards.OPTIONS_BUTTONS[0]:
                        # Установить processing для пользователя
                        db_handler.set_processing(chat_id)

                        # Обнулить выбранные пользователем параметры бита
                        await reset_chosen_params(c.message.chat.id)

                        user_chosen_option = 'speed_up'

                        db_handler.set_chosen_style(chat_id, user_chosen_option)  

                        db_handler.set_wait_for_file(chat_id)

                        # Отправка сообщения
                        await bot.send_message(chat_id, text='🆓 *SPEED UP*\n\nУвеличить темп аудио\n\nСкинь сюда свой звук в формате *.mp3*', reply_markup=keyboards.to_menu_keyboard, parse_mode='Markdown')

                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                    elif pressed_button == keyboards.OPTIONS_BUTTONS[1]:

                        # Установить processing для пользователя
                        db_handler.set_processing(chat_id)

                        # Обнулить выбранные пользователем параметры бита
                        await reset_chosen_params(c.message.chat.id)

                        user_chosen_option = 'slow_down'

                        db_handler.set_chosen_style(chat_id, user_chosen_option)  

                        db_handler.set_wait_for_file(chat_id)

                        # Отправка сообщения
                        await bot.send_message(chat_id, text='🆓 *SLOWED + REVERB*\n\nЗамедлить звук\n\nСкинь сюда свой звук в формате *.mp3*', reply_markup=keyboards.to_menu_keyboard, parse_mode='Markdown')

                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                    elif pressed_button == keyboards.OPTIONS_BUTTONS[2]:
                        if await check_subscription(chat_id, '@beatbotnews'):
                            # Установить processing для пользователя
                            db_handler.set_processing(chat_id)

                            # Обнулить выбранные пользователем параметры бита
                            await reset_chosen_params(c.message.chat.id)

                            user_chosen_option = 'remove_vocal'

                            db_handler.set_chosen_style(chat_id, user_chosen_option)  

                            db_handler.set_wait_for_file(chat_id)

                            # Отправка сообщения
                            await bot.send_message(chat_id, text='🆓 *REMOVE VOCAL*\n\nРазделить трек на бит и голос\n\nСкинь сюда свой звук в формате *.mp3* или *.wav*', reply_markup=keyboards.to_menu_keyboard, parse_mode='Markdown')

                            # Удалить processing для пользователя
                            db_handler.del_processing(chat_id)
                        else:
                            await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Данная опция в разработке, но будет доступна очень скоро!', show_alert=True)
            else:
                # Отправка оповещения
                await bot.answer_callback_query(callback_query_id=c.id, text='Ты не можешь воспользоваться бесплатными опциями во время генерации бита', show_alert=True)

    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)

# Сохраняет выбранный пользователем bpm и style во время редактирования сообщения ботом. chat_id: ['bpm', 'style']
user_chosen_bpm_style = {}

@dp.callback_query_handler(lambda c: c.data  in list(itertools.chain(*keyboards.BPM_BUTTONS_CONTROLLER.values())))
async def show_bpm(c: types.CallbackQuery):
    try:
        chat_id = c.message.chat.id

        if await get_user(chat_id):     
            # Проверить, не находится ли пользователь в beats_generating
            if db_handler.get_beats_generating(chat_id) == 0:
                # Проверить, не находится ли пользователь в processing
                if db_handler.get_processing(chat_id) == 0:

                    # Установить processing для пользователя
                    db_handler.set_processing(chat_id)

                    user_chosen_style = db_handler.get_chosen_style(chat_id)
                    
                    calculate_bpm = int(user_chosen_bpm_style[chat_id][0].split('b')[0]) + int(c.data)

                    if calculate_bpm > int(keyboards.BPM_BUTTONS[user_chosen_style][2].split('b')[0]):
                        await bot.answer_callback_query(callback_query_id=c.id, text='⚠️MAX достигнут максимальный bpm для этого стиля', show_alert=True)

                    elif calculate_bpm < int(keyboards.BPM_BUTTONS[user_chosen_style][0].split('b')[0]):
                        await bot.answer_callback_query(callback_query_id=c.id, text='⚠️MIN достигнут минимальный bpm для этого стиля', show_alert=True)

                    else:
                        current_bpm = str(calculate_bpm) + 'bpm'
                        user_chosen_bpm_style[chat_id] = [current_bpm, user_chosen_style]
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'🪩 *ТЕМП*\n\nТеперь отрегулируй темп:\n\n*{keyboards.BPM_BUTTONS[user_chosen_style][0]}* - замедлено\n*{keyboards.BPM_BUTTONS[user_chosen_style][1]}* - нормально\n*{keyboards.BPM_BUTTONS[user_chosen_style][2]}* - ускорено\n\nРегулируй желаемый *bpm* кнопками на клавиатуре. *Подтверди* выбранный темп: *{current_bpm}*\n\n✅ - {user_chosen_style}\n*⏺ - Темп*\n⏺ - Лад\n⏺ - Формат', reply_markup=keyboards.bpm_keyboard, parse_mode='Markdown')                  

                    # Удалить processing для пользователя
                    db_handler.del_processing(chat_id)

            else:
                # Отправка оповещения
                await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Ты не можешь заказывать еще один бит во время осуществления заказа.', show_alert=True)

    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)

@dp.callback_query_handler(lambda c: c.data == keyboards.GET_EXAMPLE_BEAT)
async def send_example_beat(c: types.CallbackQuery):
    try:
        chat_id = c.message.chat.id
        user_chosen_style = db_handler.get_chosen_style(chat_id)

        if await get_user(chat_id):     
            # Проверить, не находится ли пользователь в beats_generating
            if db_handler.get_beats_generating(chat_id) == 0:
                # Проверить, не находится ли пользователь в processing
                if db_handler.get_processing(chat_id) == 0:
                    if user_chosen_style is not None:
                        # Установить processing для пользователя
                        db_handler.set_processing(chat_id)

                        files_list = sorted(glob(f'example_beats/style_{keyboards.aliases[db_handler.get_chosen_style(chat_id)]}/*'))
                        print(files_list)
                        for file_path in files_list:
                            with open(file_path, 'rb') as trimmed_sound:
                                await bot.send_audio(c.message.chat.id, trimmed_sound)   

                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                    else:
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'⚠️ Произошла ошибка, пожалуйста, выберите стиль ещё раз', reply_markup=keyboards.to_styles_keyboard, parse_mode='Markdown')

            else:
                # Отправка оповещения
                await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Я не могу скинуть тебе примеры во время генерации бита.', show_alert=True)
    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)

@dp.callback_query_handler(lambda c: c.data in keyboards.BPM_CONFIRM)
async def configure_bpm(c: types.CallbackQuery):
    try:

        chat_id = c.message.chat.id
        print(user_chosen_bpm_style)
        user_chosen_bpm = user_chosen_bpm_style[chat_id][0]

        if await get_user(chat_id):     
            # Проверить, не находится ли пользователь в beats_generating
            if db_handler.get_beats_generating(chat_id) == 0:
                # Проверить, не находится ли пользователь в processing
                if db_handler.get_processing(chat_id) == 0:
                    user_chosen_style = user_chosen_bpm_style[chat_id][1]
                    db_handler.set_chosen_style(chat_id, user_chosen_style)

                    if user_chosen_bpm_style.get(chat_id) is not None:
                        del user_chosen_bpm_style[chat_id]
                    # Проверить, есть ли в базе выбранный пользователем стиль
                    if  user_chosen_style != '':
                        # Установить processing для пользователя
                        db_handler.set_processing(chat_id)

                        db_handler.set_chosen_bpm(chat_id, user_chosen_bpm)
                        # Отправка сообщения
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'🪩 *ЛАД*\n\n*major* - больше подходит для энергичных треков с более весёлым звучанием (Heroinwater, Big Baby Tape, MORGENSHTERN, Lil Tecca)\n\n*minor* - отлично подойдёт для лиричных треков (Большинство битов: OG BUDA, Гуф, THRILL PILL, Juice WRLD, XXXTENTACION)\n\n✅ - {user_chosen_style}\n✅ - {user_chosen_bpm}\n*⏺ - Лад*\n⏺ - Формат', reply_markup=keyboards.keys_keyboard, parse_mode='Markdown')       

                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                    else:
                        # Отправка сообщения
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.mesмsage_id, text=f'⚠️ Не удалось выбрать bpm, пожалуйста выбери стиль ещё раз', reply_markup=keyboards.to_styles_keyboard, parse_mode='Markdown')
            else:
                # Отправка оповещения
                await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Ты не можешь заказать еще один бит во время осуществления текущего заказа.', show_alert=True)

    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)

@dp.callback_query_handler(lambda c: c.data in keyboards.KEY_BUTTONS)
async def show_extensions(c: types.CallbackQuery):
    try:

        chat_id = c.message.chat.id
        user_chosen_bpm = db_handler.get_chosen_bpm(chat_id)
        user_chosen_harmony = c.data

        if await get_user(chat_id):     
            # Проверить, не находится ли пользователь в beats_generating
            if db_handler.get_beats_generating(chat_id) == 0:
                # Проверить, не находится ли пользователь в processing
                if db_handler.get_processing(chat_id) == 0:
                    user_chosen_style = db_handler.get_chosen_style(chat_id)
                    # Проверить, есть ли в базе выбранный пользователем стиль
                    if  user_chosen_style != '':
                        # Установить processing для пользователя
                        db_handler.set_processing(chat_id)

                        db_handler.set_chosen_harmony(chat_id, user_chosen_harmony)
                        # Отправка сообщения
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'🪩 *ФОРМАТ*\n\nВ каком формате скинуть финальный бит?\n\n*.wav* - оригинальное качество, используется профессионалами для записи. (Не воспроизводится на iphone)\n\n*.mp3* - более низкое качество, значительно меньше весит, не подходит для профессиональной записи.\n\n✅ - {user_chosen_style}\n✅ - {user_chosen_bpm}\n✅ - {user_chosen_harmony}\n*⏺ - Формат*\n\nПосле выбора формата начнётся генерация битов', reply_markup=keyboards.extensions_keyboard, parse_mode='Markdown')       
                        
                        # Удалить processing для пользователя
                        db_handler.del_processing(chat_id)
                    else:
                        # Отправка сообщения
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'⚠️ Не удалось выбрать bpm, пожалуйста выбери стиль ещё раз', reply_markup=keyboards.to_styles_keyboard, parse_mode='Markdown')
            else:
                # Отправка оповещения
                await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Ты не можешь заказать еще один бит во время осуществления текущего заказа.', show_alert=True)

    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)

# Сообщение для редактирования
message_to_edit = {}

async def check_response(chat_id, message_id):
    order_number = 0

    while True:

        if db_handler.get_beats_ready(chat_id) == 1:
            db_handler.del_beats_ready(chat_id)
            return True

        new_order_number = db_handler.get_query_by_chat_id(chat_id)
        if new_order_number != order_number:
            order_number = new_order_number
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f'💽 Создаю версии битов, это может занять несколько минут...\n\nТвоё место в очереди: *{order_number}*\n\n🔽Версии появятся внизу🔽', parse_mode='Markdown')  

        await asyncio.sleep(2*order_number)
  
@dp.callback_query_handler(lambda c: c.data in keyboards.EXTENSIONS_BUTTONS)
async def make_query(c: types.CallbackQuery):
    try:
        chat_id = c.message.chat.id
        user_chosen_extension = c.data

        if await get_user(chat_id):     
            # Проверить, не находится ли пользователь в beats_generating
            if db_handler.get_beats_generating(chat_id) == 0:
                # Проверить, не находится ли пользователь в processing
                if db_handler.get_processing(chat_id) == 0:
                    # Установить processing для пользователя
                    db_handler.set_processing(chat_id)

                    user_chosen_style = db_handler.get_chosen_style(chat_id)
                    user_chosen_bpm = db_handler.get_chosen_bpm(chat_id)

                    # Проверить, есть ли в базе выбранный пользователем style и bpm
                    if db_handler.get_balance(chat_id) >= beat_price:
                        if  user_chosen_style != '' and user_chosen_bpm != '':
                            
                            # Установить processing для пользователя
                            db_handler.set_chosen_extension(chat_id, user_chosen_extension)

                            # Добавить пользователя в beats_generating
                            db_handler.set_beats_generating(chat_id)

                            message = await bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text='💽 Создаю версии битов, это может занять несколько минут...\n\n🔽Версии появятся внизу🔽')
                            message_to_edit[chat_id] = message.message_id

                            # Удалить файлы
                            for file in glob(f'output_beats/{chat_id}_[1-{beats}]*.*'):
                                remove(file)
                                                        
                            # Добавить в очередь 
                            db_handler.set_query(chat_id, db_handler.get_chosen_style(chat_id), db_handler.get_chosen_bpm(chat_id), db_handler.get_chosen_extension(chat_id).split('.')[-1], db_handler.get_chosen_harmony(chat_id))
                            
                            if await check_response(chat_id, message_to_edit[chat_id]):
                                files_list = sorted(glob(f'output_beats/{chat_id}_[1-{beats}]_short.*'))

                                messages_ids = []

                                await bot.delete_message(chat_id=chat_id, message_id=c.message.message_id)

                                message = await bot.send_message(chat_id=chat_id, text=f'✅ Вот 3 демо-версии битов, выбери ту, которая понравилась, и я скину полную версию:\n\nСтиль - *{user_chosen_style}* Темп - *{user_chosen_bpm}*', parse_mode='Markdown')
                                message_to_edit[chat_id] = message.message_id

                                for file_path in files_list:
                                    with open(file_path, 'rb') as trimmed_sound:
                                        if files_list.index(file_path) == len(files_list)-1:
                                            message = await bot.send_audio(c.message.chat.id, trimmed_sound, title='demo - @NeuralBeatBot gen.', reply_markup=keyboards.beats_keyboard)
                                            messages_ids.append(message.message_id)
                                            db_handler.set_beats_versions_messages_ids(c.message.chat.id, ', '.join(str(messages_id) for messages_id in messages_ids))
                                            trimmed_sound.close()
                                            for file in files_list:         
                                                remove(file)
                                            del messages_ids
                                            
                                        else:
                                            message = await bot.send_audio(c.message.chat.id, trimmed_sound, title='demo - @NeuralBeatBot gen.')
                                            messages_ids.append(message.message_id)
                                # Удалить processing для пользователя
                                db_handler.del_processing(chat_id)
                        else:
                            # Отправка сообщения
                            await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'⚠️ Не удалось выбрать расширение, попробуй ещё раз. Выбрать параметры бита нужно строго в предлагаемом ботом порядке и в одном сообщении', reply_markup=keyboards.to_styles_keyboard, parse_mode='Markdown')
                    else:
                        balance_keyboard = InlineKeyboardMarkup().add(keyboards.btn_balance)
                        await bot.edit_message_text(chat_id=chat_id, message_id=c.message.message_id, text=f'⚠️ Сперва тебе нужно пополнить баланс', reply_markup=balance_keyboard, parse_mode='Markdown')

                # Удалить processing для пользователя
                db_handler.del_processing(chat_id)
            else:
                # Отправка оповещения
                await bot.answer_callback_query(callback_query_id=c.id, text='⚠️ Ты не можешь заказать еще один бит во время осуществления текущего заказа.', show_alert=True)

    except Exception as e:
        print(repr(e))
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)
        # Удалить beats_generating для пользователя
        db_handler.del_beats_generating(c.message.chat.id)
        # Удалить файлы 
        for file in glob(f'output_beats/{c.message.chat.id}_[1-{beats}]*.*'):
            remove(file)
            
        await bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text=f'⚠️ Не удалось отправить бит, деньги за транзакцию не сняты. Попробуйте ещё раз.', reply_markup=keyboards.undo_keyboard)

@dp.callback_query_handler(lambda c: c.data in keyboards.BEATS_BUTTONS)
async def send_beat(c: types.CallbackQuery):
    try:  
        chat_id = c.message.chat.id
        pressed_button = c.data

        if await get_user(chat_id):

            # Проверить, не находится ли пользователь в processing
            if db_handler.get_processing(chat_id) == 0:
                # Установить processing для пользователя
                db_handler.set_processing(chat_id)

                message = await bot.edit_message_text(chat_id=chat_id, message_id=message_to_edit[chat_id], text='📤 Скидываю полную версию... 📤')
                message_to_edit[chat_id] = message.message_id

                # Удалить примеры битов
                messages_to_delete_ids = db_handler.get_beats_versions_messages_ids(chat_id)
                if messages_to_delete_ids != '':
                    for mes_id in messages_to_delete_ids.split(', '):
                        await bot.delete_message(chat_id, mes_id)
                db_handler.del_beats_versions_messages_ids(chat_id)

                # Открыть файл
                beat = open(f'output_beats/{chat_id}_{pressed_button}.{db_handler.get_chosen_extension(chat_id).split(".")[-1]}', 'rb')

                # Скинуть файл
                await bot.send_audio(chat_id, beat, title='BEAT - tg: @NeuralBeatBot')

                # Закрыть файл
                beat.close()

                # Отправка сообщения
                message = await bot.edit_message_text(chat_id=chat_id, message_id=message_to_edit[chat_id], text='🔽 Держи 🔽')
                message_to_edit[chat_id] = message.message_id
                await bot.send_message(chat_id, f'С твоего баланса снято *{beat_price}₽*\nНадеюсь, тебе понравится бит 😉', reply_markup=keyboards.to_menu_keyboard, parse_mode='Markdown')                        

                # Удалить файлы
                for file in glob(f'output_beats/{chat_id}_[1-{beats}]*.*'):
                    remove(file)

                # Снять деньги
                db_handler.pay(chat_id, beat_price)

                # Увеличеть количество купленых битов на аккаунте
                db_handler.get_beat(chat_id)
             
                # Обнулить выбранные пользователем параметры бита
                await reset_chosen_params(chat_id)
                # Удалить processing для пользователя
                db_handler.del_processing(chat_id)
                # Удалить beats_generating для пользователя
                db_handler.del_beats_generating(chat_id)
                # Удалить chosen_extension для пользователя
                db_handler.del_chosen_extension(chat_id)

    except Exception as e:
        print(repr(e))
        # Обнулить выбранные пользователем параметры бита
        await reset_chosen_params(c.message.chat.id)
        # Удалить processing для пользователя
        db_handler.del_processing(c.message.chat.id)
        # Удалить beats_generating для пользователя
        db_handler.del_beats_generating(c.message.chat.id)
        # Удалить файлы
        for file in glob(f'output_beats/{c.message.chat.id}_[1-{beats}].*'):
            remove(file)

        await bot.send_message(c.message.chat.id, '⚠️ Не удалось отправить бит, деньги за транзакцию не сняты. Попробуйте ещё раз.', reply_markup=keyboards.undo_keyboard)

# Запуск бота
if __name__ == '__main__':
    executor.start(dp, safe_launch())
    executor.start_polling(dp, skip_updates=True)