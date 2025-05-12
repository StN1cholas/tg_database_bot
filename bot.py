
import logging
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
import asyncio
from db import connect_to_db, close_connection, execute, fetch
from config import API_TOKEN

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Создаем маршрутизатор для команд
router = Router()

# Храним параметры подключения для каждого пользователя
user_db_params = {}  # для хранения параметров подключения к БД
user_db_states = {}  # для отслеживания состояния подключения к БД

# Отдельно храним параметры для создания таблиц
user_table_params = {}  # для хранения параметров создания таблицы
user_table_states = {}  # для отслеживания состояния создания таблицы

# Отдельно храним параметры для изменения таблиц
user_alter_params = {}  # для хранения параметров изменения таблицы
user_alter_states = {}  # для отслеживания состояния изменения таблицы

# Отдельно храним параметры для вставки данных
user_insert_params = {}  # для хранения параметров вставки данных
user_insert_states = {}  # для отслеживания состояния вставки данных

# Отдельно храним параметры для выборки данных
user_select_params = {}
user_select_states = {}

user_update_params = {}
user_update_states = {}

# Шаги для ввода параметров подключения
DB_STATE_STEP = ["user", "password", "database", "host", "port"]

# Переменная для остановки бота
stop_polling = False

# Подключение к базе данных при старте бота
async def on_startup():
    logging.info("Бот запущен.")


# Отключение от базы данных при завершении работы бота
async def on_shutdown():
    await close_connection()
    logging.info("Бот завершил работу и подключение к базе данных закрыто.")

@router.message(Command("help"))
async def send_help(message: types.Message):
    help_text = (
        "/start - Запуск бота.\n"
        "/connect - Подключение к базе данных. Пошагово вводятся параметры: пользователь, пароль, БД, хост и порт.\n"
        "/create_table - Создание новой таблицы. Введите название таблицы, колонки и их типы данных.\n"
        "/alter_table - Изменение существующей таблицы. Позволяет добавить или удалить колонки.\n"
        "/insert - Вставка данных в таблицу. Выбираете колонку, вводите значения, можно ввести несколько значений.\n"
        "/select - Выборка данных из таблицы. Позволяет просмотреть все данные из указанной таблицы.\n"
        "/update - Обновление данных в таблице. Выбираете колонку и обновляете значения существующих записей.\n"
        "/stop - Остановка бота.\n"
        "/help - Выводит список всех доступных команд."
    )
    await message.answer(help_text)

# Команда для начала ввода параметров подключения
@router.message(Command("connect"))
async def start_db_connection(message: types.Message):
    user_id = message.from_user.id
    user_db_params[user_id] = {}
    user_db_states[user_id] = 0  # Начинаем с первого шага
    await message.answer("Введите имя пользователя для подключения к базе данных:")


# Обработка ввода параметров подключения
@router.message(lambda message: message.from_user.id in user_db_states)
async def handle_db_params(message: types.Message):
    user_id = message.from_user.id
    step = user_db_states[user_id]

    # Сохраняем введенный параметр
    current_param = DB_STATE_STEP[step]
    user_db_params[user_id][current_param] = message.text

    step += 1

    # Если шаги еще не завершены, запрашиваем следующий параметр
    if step < len(DB_STATE_STEP):
        user_db_states[user_id] = step
        next_param = DB_STATE_STEP[step]
        await message.answer(f"Введите {next_param}:")
    else:
        # Все параметры получены, пытаемся подключиться
        try:
            await connect_to_db(user_db_params[user_id])  # Пытаемся подключиться с введенными параметрами
            await message.answer("Подключение к базе данных успешно установлено!")
        except Exception as e:
            logging.error(f"Ошибка подключения к базе данных: {e}")
            await message.answer("Не удалось подключиться к базе данных. Проверьте параметры подключения.")
            user_db_params.pop(user_id)

        # Сбрасываем состояние пользователя после подключения
        user_db_states.pop(user_id, None)


# Приветственная команда /start
@router.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer(
        "Привет! Я бот для взаимодействия с базой данных через DBeaver.\n"
        "Для подключения к базе данных введите команду /connect."
    )

# Команда для остановки бота
@router.message(Command("stop"))
async def stop_bot(message: types.Message):
    global stop_polling
    await message.answer("Останавливаю бота...")

    stop_polling = True
    await on_shutdown()
    await bot.session.close()
    logging.info("Бот остановлен.")


# DDL - создание таблицы, где пользователь вводит параметры (используем отдельные переменные)
@router.message(Command("create_table"))
async def create_table(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_db_params:
        await message.answer("Пожалуйста, сначала подключитесь к базе данных с помощью команды /connect.")
        return

    await message.answer("Введите название таблицы для создания:")

    # Включаем пользователя в состояние ожидания имени таблицы
    user_table_params[user_id] = {}  # Инициализируем параметры таблицы для этого пользователя
    user_table_states[user_id] = 'waiting_table_name'


# Обработка ввода названия таблицы и параметров колонок
@router.message(lambda message: message.from_user.id in user_table_states and user_table_states[
    message.from_user.id] == 'waiting_table_name')
async def handle_table_creation(message: types.Message):
    user_id = message.from_user.id
    table_name = message.text

    # Спрашиваем пользователя о колонках
    await message.answer(f"Введите колонки для таблицы {table_name} в формате: column_name data_type, ...")
    user_table_params[user_id]['table_name'] = table_name
    user_table_states[user_id] = 'waiting_columns'


# Обработка ввода колонок таблицы
@router.message(lambda message: message.from_user.id in user_table_states and user_table_states[
    message.from_user.id] == 'waiting_columns')
async def handle_columns_creation(message: types.Message):
    user_id = message.from_user.id
    columns = message.text

    table_name = user_table_params[user_id].get('table_name')

    if not table_name:
        await message.answer("Ошибка: не найдено название таблицы.")
        user_table_states.pop(user_id, None)
        return

    # Создаем запрос для создания таблицы
    create_table_query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns});"

    try:
        await execute(create_table_query)
        await message.answer(f"Таблица '{table_name}' успешно создана с колонками: {columns}.")
    except Exception as e:
        logging.error(f"Ошибка создания таблицы: {e}")
        await message.answer(f"Ошибка при создании таблицы '{table_name}'.")

    # После создания таблицы сбрасываем состояние
    user_table_states.pop(user_id, None)
    user_table_params.pop(user_id, None)


# DML - вставка данных в любую таблицу
# DML - вставка данных в любую колонку таблицы
@router.message(Command("insert"))
async def start_insert_data(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_db_params:
        await message.answer("Пожалуйста, сначала подключитесь к базе данных с помощью команды /connect.")
        return

    await message.answer("Введите название таблицы, в которую хотите вставить данные:")

    # Инициализируем параметры вставки данных
    user_insert_params[user_id] = {}
    user_insert_states[user_id] = 'waiting_table_name'


# Обработка ввода названия таблицы для вставки данных
@router.message(lambda message: message.from_user.id in user_insert_states and user_insert_states[message.from_user.id] == 'waiting_table_name')
async def handle_insert_table_name(message: types.Message):
    user_id = message.from_user.id
    table_name = message.text.strip()

    user_insert_params[user_id]['table_name'] = table_name

    try:
        # Получаем список колонок и их типов данных
        columns_query = f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}';
        """
        columns = await fetch(columns_query)

        if not columns:
            await message.answer(f"Таблица '{table_name}' не найдена.")
            user_insert_states.pop(user_id, None)
            user_insert_params.pop(user_id, None)
            return

        # Сохраняем информацию о колонках
        user_insert_params[user_id]['available_columns'] = columns

        # Формируем ответ для пользователя
        columns_info = "\n".join([f"{col['column_name']} ({col['data_type']})" for col in columns])
        await message.answer(f"Таблица '{table_name}' содержит следующие колонки:\n{columns_info}\n\nВведите название колонки, в которую хотите вставить данные:")

        user_insert_states[user_id] = 'waiting_column_name'

    except Exception as e:
        logging.error(f"Ошибка получения колонок таблицы: {e}")
        await message.answer("Ошибка при получении информации о колонках таблицы.")
        user_insert_states.pop(user_id, None)
        user_insert_params.pop(user_id, None)


# Обработка ввода названия колонки для вставки данных
@router.message(lambda message: message.from_user.id in user_insert_states and user_insert_states[message.from_user.id] == 'waiting_column_name')
async def handle_insert_column_name(message: types.Message):
    user_id = message.from_user.id
    column_name = message.text.strip()
    table_name = user_insert_params[user_id]['table_name']

    # Проверяем, что колонка существует
    available_columns = [col['column_name'] for col in user_insert_params[user_id]['available_columns']]
    if column_name not in available_columns:
        await message.answer(f"Колонка '{column_name}' не найдена. Пожалуйста, выберите корректную колонку.")
        return

    user_insert_params[user_id]['column_name'] = column_name

    # Получаем тип данных колонки
    column_type = next(col['data_type'] for col in user_insert_params[user_id]['available_columns'] if col['column_name'] == column_name)
    user_insert_params[user_id]['column_type'] = column_type

    await message.answer(f"Вы выбрали колонку '{column_name}' с типом данных '{column_type}'. Введите значение:")

    user_insert_states[user_id] = 'waiting_value'


# Обработка ввода значения для вставки данных
@router.message(lambda message: message.from_user.id in user_insert_states and user_insert_states[message.from_user.id] == 'waiting_value')
async def handle_insert_value(message: types.Message):
    user_id = message.from_user.id
    value = message.text.strip()
    column_name = user_insert_params[user_id]['column_name']
    table_name = user_insert_params[user_id]['table_name']
    column_type = user_insert_params[user_id]['column_type']

    try:
        # Преобразуем значение в нужный тип данных в зависимости от типа колонки
        if column_type in ('integer', 'int4'):
            value = int(value)
        elif column_type in ('numeric', 'float8', 'double precision'):
            value = float(value)
        # Для строковых типов (text, varchar и т.д.) преобразование не нужно
        # Пропускаем преобразование для этих типов

        # Выполняем вставку данных
        insert_query = f"INSERT INTO {table_name} ({column_name}) VALUES ($1);"
        await execute(insert_query, value)

        await message.answer(f"Значение '{value}' успешно вставлено в колонку '{column_name}' таблицы '{table_name}'.")
    except ValueError:
        await message.answer(f"Некорректное значение для типа данных '{column_type}'. Пожалуйста, введите корректное значение.")
    except Exception as e:
        logging.error(f"Ошибка вставки данных: {e}")
        await message.answer("Произошла ошибка при вставке данных.")

    # Очищаем состояние после вставки данных
    user_insert_states.pop(user_id, None)
    user_insert_params.pop(user_id, None)

# DDL - изменение таблицы (добавление или удаление столбцов)
@router.message(Command("alter_table"))
async def alter_table(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_db_params:
        await message.answer("Пожалуйста, сначала подключитесь к базе данных с помощью команды /connect.")
        return

    await message.answer("Введите название таблицы, которую хотите изменить:")

    # Инициализируем параметры изменения таблицы
    user_alter_params[user_id] = {}
    user_alter_states[user_id] = 'waiting_table_name'

# Обработка ввода названия таблицы для изменения
@router.message(lambda message: message.from_user.id in user_alter_states and user_alter_states[
    message.from_user.id] == 'waiting_table_name')
async def handle_alter_table_name(message: types.Message):
    user_id = message.from_user.id
    table_name = message.text

    # Сохраняем название таблицы
    user_alter_params[user_id]['table_name'] = table_name
    await message.answer(
        f"Вы хотите добавить или удалить столбец из таблицы {table_name}? Введите 'add' для добавления или 'remove' для удаления.")
    user_alter_states[user_id] = 'waiting_action'

# Обработка действия (добавить или удалить столбец)
@router.message(lambda message: message.from_user.id in user_alter_states and user_alter_states[
    message.from_user.id] == 'waiting_action')
async def handle_alter_action(message: types.Message):
    user_id = message.from_user.id
    action = message.text.lower()

    if action == 'add':
        await message.answer("Введите название и тип данных нового столбца в формате: column_name data_type")
        user_alter_states[user_id] = 'waiting_add_column'
    elif action == 'remove':
        await message.answer("Введите название столбца, который хотите удалить:")
        user_alter_states[user_id] = 'waiting_remove_column'
    else:
        await message.answer("Неверный ввод. Введите 'add' для добавления или 'remove' для удаления столбца.")

# Обработка добавления нового столбца
@router.message(lambda message: message.from_user.id in user_alter_states and user_alter_states[
    message.from_user.id] == 'waiting_add_column')
async def handle_add_column(message: types.Message):
    user_id = message.from_user.id
    column_info = message.text.split()

    if len(column_info) != 2:
        await message.answer("Неверный формат. Введите данные в формате: column_name data_type")
        return

    column_name, data_type = column_info
    table_name = user_alter_params[user_id].get('table_name')

    if not table_name:
        await message.answer("Ошибка: не найдено название таблицы.")
        user_alter_states.pop(user_id, None)
        return

    try:
        # Формируем запрос для добавления столбца
        alter_query = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {data_type};"
        await execute(alter_query)
        await message.answer(f"Столбец '{column_name}' успешно добавлен в таблицу '{table_name}'.")
    except Exception as e:
        logging.error(f"Ошибка добавления столбца: {e}")
        await message.answer(f"Ошибка при добавлении столбца '{column_name}'.")

    # Очищаем состояния после добавления столбца
    user_alter_states.pop(user_id, None)
    user_alter_params.pop(user_id, None)

# Обработка удаления столбца
@router.message(lambda message: message.from_user.id in user_alter_states and user_alter_states[
    message.from_user.id] == 'waiting_remove_column')
async def handle_remove_column(message: types.Message):
    user_id = message.from_user.id
    column_name = message.text
    table_name = user_alter_params[user_id].get('table_name')

    if not table_name:
        await message.answer("Ошибка: не найдено название таблицы.")
        user_alter_states.pop(user_id, None)
        return

    try:
        # Формируем запрос для удаления столбца
        alter_query = f"ALTER TABLE {table_name} DROP COLUMN {column_name};"
        await execute(alter_query)
        await message.answer(f"Столбец '{column_name}' успешно удален из таблицы '{table_name}'.")
    except Exception as e:
        logging.error(f"Ошибка удаления столбца: {e}")
        await message.answer(f"Ошибка при удалении столбца '{column_name}'.")

    # Очищаем состояния после удаления столбца
    user_alter_states.pop(user_id, None)
    user_alter_params.pop(user_id, None)

# DML - получение данных из любой таблицы
@router.message(Command("select"))
async def start_select_data(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_db_params:
        await message.answer("Пожалуйста, сначала подключитесь к базе данных с помощью команды /connect.")
        return

    await message.answer("Введите название таблицы, из которой хотите получить данные:")

    # Инициализируем параметры выборки данных
    user_select_params[user_id] = {}
    user_select_states[user_id] = 'waiting_table_name'

# Обработка ввода названия таблицы для выборки данных
@router.message(lambda message: message.from_user.id in user_select_states and user_select_states[
    message.from_user.id] == 'waiting_table_name')
async def handle_select_table_name(message: types.Message):
    user_id = message.from_user.id
    table_name = message.text

    user_select_params[user_id]['table_name'] = table_name

    try:
        # Получаем список колонок и их типов
        columns_query = f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}';
        """
        columns = await fetch(columns_query)

        if not columns:
            await message.answer(f"Таблица '{table_name}' не найдена.")
            user_select_states.pop(user_id, None)
            user_select_params.pop(user_id, None)
            return

        # Сохраняем информацию о колонках
        user_select_params[user_id]['available_columns'] = columns

        # Формируем ответ для пользователя
        columns_info = ", ".join([col['column_name'] for col in columns])
        await message.answer(
            f"Таблица '{table_name}' содержит следующие колонки:\n{columns_info}\n\nВыберите, хотите ли вы получить все данные из таблицы или выбрать конкретные колонки. Введите 'all' для всех данных или введите названия колонок через запятую:")

        user_select_states[user_id] = 'waiting_column_choice'

    except Exception as e:
        logging.error(f"Ошибка получения колонок таблицы: {e}")
        await message.answer("Ошибка при получении информации о колонках таблицы.")
        user_select_states.pop(user_id, None)
        user_select_params.pop(user_id, None)

# Обработка выбора колонок для выборки данных
@router.message(lambda message: message.from_user.id in user_select_states and user_select_states[
    message.from_user.id] == 'waiting_column_choice')
async def handle_column_choice_for_select(message: types.Message):
    user_id = message.from_user.id
    choice = message.text.strip().lower()
    table_name = user_select_params[user_id]['table_name']

    try:
        if choice == 'all':
            select_query = f"SELECT * FROM {table_name};"
        else:
            columns = choice.split(',')
            columns = [col.strip() for col in columns if col.strip()]  # Убираем лишние пробелы

            # Проверяем, что все указанные колонки существуют в таблице
            available_columns = [col['column_name'] for col in user_select_params[user_id]['available_columns']]
            for col in columns:
                if col not in available_columns:
                    await message.answer(f"Колонка '{col}' не найдена. Пожалуйста, выберите корректные колонки.")
                    return

            select_query = f"SELECT {', '.join(columns)} FROM {table_name};"

        records = await fetch(select_query)

        if records:
            response = "\n".join([str(record) for record in records])
            await message.answer(f"Результаты выборки:\n{response}")
        else:
            await message.answer("Записей пока нет.")

    except Exception as e:
        logging.error(f"Ошибка получения записей: {e}")
        await message.answer("Произошла ошибка при получении записей.")

    # Очищаем состояние после выборки данных
    user_select_states.pop(user_id, None)
    user_select_params.pop(user_id, None)


# DML - обновление данных в любой колонке таблицы
@router.message(Command("update"))
async def start_update_data(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_db_params:
        await message.answer("Пожалуйста, сначала подключитесь к базе данных с помощью команды /connect.")
        return

    await message.answer("Введите название таблицы, в которой хотите обновить данные:")

    # Инициализируем параметры обновления данных
    user_update_params[user_id] = {}
    user_update_states[user_id] = 'waiting_table_name'


# Обработка ввода названия таблицы для обновления данных
@router.message(lambda message: message.from_user.id in user_update_states and user_update_states[
    message.from_user.id] == 'waiting_table_name')
async def handle_update_table_name(message: types.Message):
    user_id = message.from_user.id
    table_name = message.text.strip()

    user_update_params[user_id]['table_name'] = table_name

    try:
        # Получаем список колонок
        columns_query = f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}';
        """
        columns = await fetch(columns_query)

        if not columns:
            await message.answer(f"Таблица '{table_name}' не найдена.")
            user_update_states.pop(user_id, None)
            user_update_params.pop(user_id, None)
            return

        # Сохраняем информацию о колонках
        user_update_params[user_id]['available_columns'] = columns

        # Формируем ответ для пользователя
        columns_info = ", ".join([col['column_name'] for col in columns])
        await message.answer(
            f"Таблица '{table_name}' содержит следующие колонки:\n{columns_info}\n\nВведите название колонки, которую хотите обновить:")

        user_update_states[user_id] = 'waiting_column_name'

    except Exception as e:
        logging.error(f"Ошибка получения колонок таблицы: {e}")
        await message.answer("Ошибка при получении информации о колонках таблицы.")
        user_update_states.pop(user_id, None)
        user_update_params.pop(user_id, None)


# Обработка ввода названия колонки для обновления данных
@router.message(lambda message: message.from_user.id in user_update_states and user_update_states[
    message.from_user.id] == 'waiting_column_name')
async def handle_update_column_name(message: types.Message):
    user_id = message.from_user.id
    column_name = message.text.strip()
    table_name = user_update_params[user_id]['table_name']

    # Проверяем, что колонка существует
    available_columns = [col['column_name'] for col in user_update_params[user_id]['available_columns']]
    if column_name not in available_columns:
        await message.answer(f"Колонка '{column_name}' не найдена. Пожалуйста, выберите корректную колонку.")
        return

    user_update_params[user_id]['column_name'] = column_name

    # Запрашиваем существующие значения в выбранной колонке для отображения пользователю
    try:
        values_query = f"SELECT DISTINCT {column_name} FROM {table_name};"
        values = await fetch(values_query)

        if not values:
            await message.answer(f"Нет данных для колонки '{column_name}'.")
            user_update_states.pop(user_id, None)
            user_update_params.pop(user_id, None)
            return

        # Выводим найденные значения пользователю для выбора
        values_info = ", ".join([str(val[column_name]) for val in values])
        await message.answer(f"Колонка '{column_name}' содержит следующие значения:\n{values_info}\n\nВведите значение, которое хотите обновить:")

        user_update_params[user_id]['available_values'] = values
        user_update_states[user_id] = 'waiting_value_selection'

    except Exception as e:
        logging.error(f"Ошибка получения значений колонки: {e}")
        await message.answer("Ошибка при получении значений колонки.")
        user_update_states.pop(user_id, None)
        user_update_params.pop(user_id, None)


# Обработка выбора значения для изменения
@router.message(lambda message: message.from_user.id in user_update_states and user_update_states[
    message.from_user.id] == 'waiting_value_selection')
async def handle_value_selection(message: types.Message):
    user_id = message.from_user.id
    selected_value = message.text.strip()
    column_name = user_update_params[user_id]['column_name']
    available_values = [str(val[column_name]) for val in user_update_params[user_id]['available_values']]

    # Проверяем, что значение существует в колонке
    if selected_value not in available_values:
        await message.answer(f"Значение '{selected_value}' не найдено. Пожалуйста, выберите корректное значение.")
        return

    user_update_params[user_id]['selected_value'] = selected_value
    await message.answer(f"Вы выбрали значение '{selected_value}'. Введите новое значение для замены:")

    user_update_states[user_id] = 'waiting_new_value'


# Обработка ввода нового значения для обновления данных
@router.message(lambda message: message.from_user.id in user_update_states and user_update_states[
    message.from_user.id] == 'waiting_new_value')
async def handle_new_value(message: types.Message):
    user_id = message.from_user.id
    new_value = message.text.strip()
    column_name = user_update_params[user_id]['column_name']
    table_name = user_update_params[user_id]['table_name']
    selected_value = user_update_params[user_id]['selected_value']

    try:
        # Получаем тип данных колонки
        type_query = f"""
        SELECT data_type 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}' AND column_name = '{column_name}';
        """
        column_type = await fetch(type_query)

        if not column_type:
            await message.answer("Ошибка при получении типа данных колонки.")
            return

        data_type = column_type[0]['data_type']

        # Преобразуем новое значение в соответствующий тип
        if data_type == 'integer':
            try:
                new_value = int(new_value)
                selected_value = int(selected_value)  # Преобразуем выбранное значение в целое число
            except ValueError:
                await message.answer("Пожалуйста, введите корректное целое число.")
                return
        elif data_type == 'boolean':
            if new_value.lower() in ['true', '1']:
                new_value = True
            elif new_value.lower() in ['false', '0']:
                new_value = False
            else:
                await message.answer("Пожалуйста, введите 'true' или 'false'.")
                return
        # Обработка других типов данных
        # Можно добавить дополнительные условия для других типов данных

        # Выполняем запрос на обновление данных
        update_query = f"UPDATE {table_name} SET {column_name} = $1 WHERE {column_name} = $2;"
        await execute(update_query, new_value, selected_value)

        await message.answer(f"Значение '{selected_value}' в колонке '{column_name}' успешно обновлено на '{new_value}'.")

    except Exception as e:
        logging.error(f"Ошибка обновления данных: {e}")
        await message.answer("Произошла ошибка при обновлении данных.")

    # Очищаем состояние после обновления данных
    user_update_states.pop(user_id, None)
    user_update_params.pop(user_id, None)



# Основной запуск бота
async def main():
    # Регистрируем маршрутизатор в диспетчере
    dp.include_router(router)

    # Запуск бота
    await on_startup()

    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())



