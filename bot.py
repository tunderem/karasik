import asyncio
import logging
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import time
import json
import os
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ⚠️ ВАЖНО: Используйте переменную окружения для безопасности!
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8455558290:AAHDiNfqtG7LMOWor9rHhpwtCVv-JHmt-7c')

# ⚡ НАСТРОЙТЕ СВОЙ USER ID ЗДЕСЬ ⚡
# Чтобы получить свой ID: отправьте /id боту @userinfobot
ADMIN_USER_ID = 2073879359  # ЗАМЕНИТЕ НА ВАШ REAL USER ID


class MondayAttendanceBot:
    def __init__(self, token):
        self.token = token
        self.chat_id = None
        self.last_poll_message_id = None
        self.current_poll_id = None
        self.votes = {}  # {user_id: {'option': option, 'name': name, 'timestamp': timestamp}}
        self.application = Application.builder().token(token).build()

        # Обработчики команд
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("attendance", self.attendance_command))
        self.application.add_handler(CommandHandler("results", self.results_command))
        self.application.add_handler(CommandHandler("voters", self.voters_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("id", self.id_command))  # Новоя команда для получения ID

        # Обработчики callback'ов (работают для всех)
        self.application.add_handler(CallbackQueryHandler(self.handle_vote, pattern="^vote_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_admin, pattern="^admin_"))

        # Обработчик для всех сообщений (отправляет всех нахуй)
        self.application.add_handler(CommandHandler("fuck", self.fuck_command))

    async def is_admin(self, user_id):
        """Проверяем, является ли пользователь администратором"""
        return user_id == ADMIN_USER_ID

    async def check_admin_access(self, update: Update):
        """Проверяет доступ и отправляет сообщение если не админ"""
        user_id = update.effective_user.id
        if not await self.is_admin(user_id):
            await update.message.reply_text("🚫 Пошёл нахуй, петушара! Ты кто такой чтобы мне команды раздавать?")
            return False
        return True

    async def fuck_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для отправки нахуй"""
        user = update.effective_user
        await update.message.reply_text(
            f"🖕 {user.full_name}, пошёл нахуй! Не командуй тут, уёбок!"
        )

    async def id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает ID пользователя"""
        user = update.effective_user
        await update.message.reply_text(
            f"🆔 Твой ID: <code>{user.id}</code>\n"
            f"👤 Имя: {user.full_name}\n"
            f"📛 Username: @{user.username if user.username else 'нет'}\n\n"
            f"<i>Отправь этот ID создателю бота</i>",
            parse_mode='HTML'
        )

    def save_data(self):
        """Сохраняем данные голосования"""
        try:
            data = {
                'chat_id': self.chat_id,
                'last_poll_message_id': self.last_poll_message_id,
                'current_poll_id': self.current_poll_id,
                'votes': self.votes,
                'last_updated': datetime.now().isoformat()
            }
            with open('attendance_data.json', 'w') as f:
                json.dump(data, f, ensure_ascii=False, default=str)
            logger.info("Данные сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")

    def load_data(self):
        """Загружаем данные голосования"""
        try:
            if os.path.exists('attendance_data.json'):
                with open('attendance_data.json', 'r') as f:
                    data = json.load(f)
                    self.chat_id = data.get('chat_id')
                    self.last_poll_message_id = data.get('last_poll_message_id')
                    self.current_poll_id = data.get('current_poll_id')
                    self.votes = data.get('votes', {})
                    last_updated = data.get('last_updated')
                    logger.info(f"Данные загружены (обновлены: {last_updated})")
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")

    def get_next_monday_date(self):
        """Получаем дату следующего понедельника"""
        today = datetime.now()
        days_ahead = 0 - today.weekday()  # 0 = Monday
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        next_monday = today + timedelta(days=days_ahead)
        return next_monday.strftime('%d.%m.%Y')

    def get_next_monday_weekday(self):
        """Получаем день недели следующего понедельника"""
        return "Понедельник"

    def should_create_new_poll(self):
        """Проверяем, нужно ли создавать новое голосование"""
        # Создаем новое голосование каждый понедельник в 19:00
        now = datetime.now()

        # Если сейчас понедельник и время после 19:00
        if now.weekday() == 0 and now.hour >= 19:
            # Проверяем, создавали ли мы уже голосование на этой неделе
            if not self.current_poll_id:
                return True

            # Проверяем дату создания текущего голосования
            try:
                poll_timestamp = int(self.current_poll_id)
                poll_date = datetime.fromtimestamp(poll_timestamp)
                # Если голосование создано до сегодняшнего дня, создаем новое
                if poll_date.date() < now.date():
                    return True
            except:
                return True

        return False

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start для настройки бота"""
        # Проверяем доступ
        if not await self.check_admin_access(update):
            return

        self.chat_id = update.effective_chat.id
        user = update.effective_user

        logger.info(f"Бот активирован в чате {self.chat_id} пользователем {user.full_name}")

        await update.message.reply_text(
            "✅ <b>Бот для учета посещаемости активирован!</b>\n\n"
            "📅 <b>Каждый понедельник в 19:00</b> я буду создавать новое голосование "
            "на следующий понедельник.\n\n"
            "📋 <b>Команды:</b>\n"
            "/attendance - текущее голосование\n"
            "/results - результаты\n"
            "/voters - кто как голосовал\n"
            "/admin - управление\n"
            "/status - статус бота\n\n"
            "<i>Просто нажмите на кнопку в закрепленном сообщении чтобы отметить свое присутствие</i>",
            parse_mode='HTML'
        )
        self.save_data()

    async def attendance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /attendance для быстрого голосования"""
        # Проверяем доступ
        if not await self.check_admin_access(update):
            return

        if not self.current_poll_id:
            await update.message.reply_text("❌ Сейчас нет активного голосования. Новое создастся в понедельник в 19:00")
        else:
            await update.message.reply_text(
                "Голосование уже активно! Используйте кнопки в закрепленном сообщении."
            )

    async def results_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /results для показа результатов"""
        # Проверяем доступ
        if not await self.check_admin_access(update):
            return

        if not self.current_poll_id:
            await update.message.reply_text("❌ Сейчас нет активного голосования")
            return

        results_text = await self.get_results_text()
        await update.message.reply_text(results_text, parse_mode='HTML')

    async def voters_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /voters для показа кто как голосовал"""
        # Проверяем доступ
        if not await self.check_admin_access(update):
            return

        if not self.current_poll_id:
            await update.message.reply_text("❌ Сейчас нет активного голосования")
            return

        voters_text = await self.get_voters_text()
        await update.message.reply_text(voters_text, parse_mode='HTML')

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ-панель"""
        # Проверяем доступ
        if not await self.check_admin_access(update):
            return

        keyboard = [
            [InlineKeyboardButton("📊 Полная статистика", callback_data="admin_full_stats")],
            [InlineKeyboardButton("🔄 Обновить голосование", callback_data="admin_refresh")],
            [InlineKeyboardButton("🗑️ Очистить голоса", callback_data="admin_clear")],
            [InlineKeyboardButton("📅 Создать голосование сейчас", callback_data="admin_create_now")],
        ]

        await update.message.reply_text(
            "⚙️ <b>Панель управления посещаемостью</b>\n\n"
            f"Следующий понедельник: {self.get_next_monday_date()}\n"
            f"Проголосовало: {len(self.votes)} человек",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status для проверки статуса бота"""
        # Проверяем доступ
        if not await self.check_admin_access(update):
            return

        now = datetime.now()
        next_monday = self.get_next_monday_date()

        status_text = (
            "🤖 <b>Статус бота:</b>\n\n"
            f"✅ <b>Бот активен</b>\n"
            f"📅 <b>Расписание:</b> Каждый понедельник в 19:00\n"
            f"🕐 <b>Следующий понедельник:</b> {next_monday}\n"
            f"👥 <b>Текущие голоса:</b> {len(self.votes)}\n"
            f"💾 <b>Данные:</b> Сохранены и загружены\n\n"
            f"<i>Бот работает стабильно</i> 🚀"
        )
        await update.message.reply_text(status_text, parse_mode='HTML')

    async def handle_vote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка голосования (доступно всем)"""
        query = update.callback_query
        user = query.from_user
        data = query.data

        # Разбираем callback_data: vote_option
        option = data.split('_')[1]

        # Сохраняем голос
        self.votes[str(user.id)] = {
            'option': option,
            'name': user.full_name,
            'timestamp': datetime.now().isoformat(),
            'username': user.username
        }

        # Обновляем клавиатуру
        keyboard = await self.create_voting_keyboard()
        await query.edit_message_reply_markup(reply_markup=keyboard)

        await query.answer(f"✅ {self.get_option_name(option)}")
        self.save_data()

        logger.info(f"Пользователь {user.full_name} проголосовал: {self.get_option_name(option)}")

    async def handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка админ-команд (только для админа)"""
        query = update.callback_query
        user = query.from_user

        # Проверяем доступ для админ-команд
        if not await self.is_admin(user.id):
            await query.answer("🚫 Ты кто такой? Пошёл нахуй!", show_alert=True)
            return

        data = query.data

        logger.info(f"Админ команда от {user.full_name}: {data}")

        if data == "admin_full_stats":
            stats_text = await self.get_full_stats_text()
            await query.message.reply_text(stats_text, parse_mode='HTML')

        elif data == "admin_refresh":
            keyboard = await self.create_voting_keyboard()
            await query.edit_message_reply_markup(reply_markup=keyboard)
            await query.answer("✅ Голосование обновлено!")

        elif data == "admin_clear":
            self.votes = {}
            keyboard = await self.create_voting_keyboard()
            await query.edit_message_reply_markup(reply_markup=keyboard)
            await query.answer("✅ Все голоса очищены!")
            self.save_data()

        elif data == "admin_create_now":
            await self.create_monday_poll()
            await query.answer("✅ Голосование создано!")

        await query.answer()

    def get_option_name(self, option):
        """Названия вариантов ответа"""
        options = {
            '1': '✅ К 1',
            '2': '⏰ Ко 2',
            '3': '❌ Не прихожу'
        }
        return options.get(option, option)

    def get_option_emoji(self, option):
        """Эмодзи для вариантов"""
        options = {
            '1': '✅',
            '2': '⏰',
            '3': '❌'
        }
        return options.get(option, '')

    async def create_voting_keyboard(self):
        """Создаем клавиатуру для голосования"""
        # Считаем голоса для каждого варианта
        votes_count = {'1': 0, '2': 0, '3': 0}
        for vote_data in self.votes.values():
            option = vote_data['option']
            votes_count[option] += 1

        total_votes = len(self.votes)

        keyboard = []
        options = [
            ('1', 'К 1'),
            ('2', 'Ко 2'),
            ('3', 'Не прихожу')
        ]

        for option, label in options:
            count = votes_count[option]
            percentage = (count / total_votes * 100) if total_votes > 0 else 0
            emoji = self.get_option_emoji(option)
            text = f"{emoji} {label} ({count} - {percentage:.1f}%)"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"vote_{option}")])

        # Добавляем кнопку для просмотра результатов (только для админа)
        if await self.is_admin(ADMIN_USER_ID):
            keyboard.append([InlineKeyboardButton("👁️ Посмотреть кто идет", callback_data="admin_full_stats")])

        return InlineKeyboardMarkup(keyboard)

    async def get_results_text(self):
        """Текст с результатами голосования"""
        if not self.current_poll_id:
            return "Нет активного голосования"

        votes_count = {'1': 0, '2': 0, '3': 0}
        for vote_data in self.votes.values():
            option = vote_data['option']
            votes_count[option] += 1

        total_votes = len(self.votes)

        text = f"<b>📊 Посещаемость на следующий понедельник:</b>\n"
        text += f"<b>📅 {self.get_next_monday_date()}</b>\n\n"

        options = [
            ('1', '✅ К 1'),
            ('2', '⏰ Ко 2'),
            ('3', '❌ Не прихожу')
        ]

        for option, label in options:
            count = votes_count[option]
            percentage = (count / total_votes * 100) if total_votes > 0 else 0
            bar = "█" * int(percentage / 10) + "░" * (10 - int(percentage / 10))
            text += f"{label}: {bar} {count} ({percentage:.1f}%)\n"

        text += f"\n<b>Всего ответило:</b> {total_votes}"
        text += f"\n\n<code>/voters</code> - посмотреть кто как голосовал"
        return text

    async def get_voters_text(self):
        """Текст с информацией о голосовавших"""
        if not self.votes:
            return "Пока никто не отметился"

        # Группируем голоса по вариантам
        votes_by_option = {
            '1': [],
            '2': [],
            '3': []
        }

        for vote_data in self.votes.values():
            option = vote_data['option']
            name = vote_data['name']
            username = vote_data.get('username')
            display_name = f"{name} (@{username})" if username else name
            votes_by_option[option].append(display_name)

        text = f"<b>👥 Кто приходит в следующий понедельник:</b>\n"
        text += f"<b>📅 {self.get_next_monday_date()}</b>\n\n"

        options = [
            ('1', '✅ К 1:'),
            ('2', '⏰ Ко 2:'),
            ('3', '❌ Не приходят:')
        ]

        for option, label in options:
            voters = votes_by_option.get(option, [])
            text += f"<b>{label}</b> ({len(voters)})\n"

            if voters:
                for voter in voters:
                    text += f"• {voter}\n"
            else:
                text += "—\n"
            text += "\n"

        return text

    async def get_full_stats_text(self):
        """Полная статистика для админа"""
        total_users = len(self.votes)

        text = f"<b>📈 Статистика посещаемости:</b>\n"
        text += f"<b>📅 {self.get_next_monday_date()} (Понедельник)</b>\n\n"

        # Подсчет по вариантам
        votes_count = {'1': 0, '2': 0, '3': 0}
        voters_by_option = {'1': [], '2': [], '3': []}

        for vote_data in self.votes.values():
            option = vote_data['option']
            name = vote_data['name']
            username = vote_data.get('username')
            display_name = f"{name} (@{username})" if username else name
            votes_count[option] += 1
            voters_by_option[option].append(display_name)

        text += f"<b>Всего отметилось:</b> {total_users}\n\n"

        options = [
            ('1', '✅ К 1:', '🟢'),
            ('2', '⏰ Ко 2:', '🟡'),
            ('3', '❌ Не приходят:', '🔴')
        ]

        for option, label, emoji in options:
            count = votes_count[option]
            percentage = (count / total_users * 100) if total_users > 0 else 0
            text += f"<b>{emoji} {label}</b> {count} ({percentage:.1f}%)\n"

            voters = voters_by_option[option]
            if voters:
                for voter in voters:
                    text += f"   👤 {voter}\n"
            text += "\n"

        return text

    async def create_monday_poll(self):
        """Создаем голосование на понедельник"""
        if not self.chat_id:
            logger.warning("Чат не настроен. Отправьте /start в группе")
            return

        try:
            # Создаем новый ID для голосования
            self.current_poll_id = str(int(datetime.now().timestamp()))

            # Очищаем голоса для новой недели
            self.votes = {}

            # Текст сообщения
            message_text = (
                f"<b>🗓️ Посещаемость на следующий понедельник</b>\n"
                f"<b>📅 {self.get_next_monday_date()} (Понедельник)</b>\n\n"
                "❓ <b>Кто приходит?</b>\n\n"
                "✅ <b>К 1</b> - приду к первому уроку\n"
                "⏰ <b>Ко 2</b> - приду ко второму уроку\n"
                "❌ <b>Не прихожу</b> - не буду\n\n"
                "<i>Отметьтесь, пожалуйста, чтобы все были в курсе</i>\n\n"
                "<code>/attendance</code> - обновить голосование\n"
                "<code>/results</code> - результаты\n"
                "<code>/voters</code> - список участников"
            )

            # Создаем клавиатуру
            keyboard = await self.create_voting_keyboard()

            # Отправляем сообщение
            message = await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )

            # Открепляем старое сообщение если есть
            if self.last_poll_message_id:
                try:
                    await self.application.bot.unpin_chat_message(
                        chat_id=self.chat_id,
                        message_id=self.last_poll_message_id
                    )
                except Exception as e:
                    logger.warning(f"Не удалось открепить старое сообщение: {e}")

            # Закрепляем новое сообщение
            await self.application.bot.pin_chat_message(
                chat_id=self.chat_id,
                message_id=message.message_id,
                disable_notification=True
            )

            self.last_poll_message_id = message.message_id
            self.save_data()

            logger.info(f"✅ Новое голосование создано на {self.get_next_monday_date()}")

            # Отправляем уведомление
            await self.application.bot.send_message(
                chat_id=self.chat_id,
                text="🔄 <b>Создано новое голосование на следующий понедельник!</b>\n"
                     "Отметьтесь в закрепленном сообщении 📍",
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"❌ Ошибка создания голосования: {e}")

    async def check_schedule(self):
        """Проверяем расписание и создаем голосование если нужно"""
        while True:
            try:
                if self.should_create_new_poll():
                    logger.info("Время создавать новое голосование!")
                    await self.create_monday_poll()

                # Ждем 1 минуту перед следующей проверкой
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                await asyncio.sleep(60)

    async def run(self):
        """Запуск бота"""
        # Загружаем данные
        self.load_data()

        # Инициализируем бота
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("🤖 Бот для учета посещаемости запущен!")
        logger.info("⏰ Расписание настроено: каждый понедельник в 19:00")
        logger.info(f"👑 Админ бота: {ADMIN_USER_ID}")

        # Создаем голосование при запуске, если его нет
        if not self.current_poll_id:
            logger.info("Создаем первое голосование...")
            await self.create_monday_poll()
        else:
            logger.info("Голосование уже активно, обновляем клавиатуру...")
            # Обновляем сообщение если оно есть
            if self.last_poll_message_id and self.chat_id:
                try:
                    keyboard = await self.create_voting_keyboard()
                    await self.application.bot.edit_message_reply_markup(
                        chat_id=self.chat_id,
                        message_id=self.last_poll_message_id,
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logger.warning(f"Не удалось обновить сообщение: {e}")

        logger.info("✅ Бот готов к работе!")

        # Запускаем планировщик
        await self.check_schedule()


# Запуск бота
if __name__ == "__main__":
    print("🚀 Запуск бота для учета посещаемости...")
    print(f"📅 Расписание: каждый понедельник в 19:00")
    print("🤖 Токен бота: 8455558290:AAHDiNfqtG7LMOWor9rHhpwtCVv-JHmt-7c")
    print(f"👑 Админ ID: {ADMIN_USER_ID}")
    print("⚠️  ВАЖНО: Замени ADMIN_USER_ID на свой реальный ID!")

    bot = MondayAttendanceBot(BOT_TOKEN)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")