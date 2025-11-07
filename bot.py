import asyncio
import logging
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest, TimedOut
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

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8455558290:AAHDiNfqtG7LMOWor9rHhpwtCVv-JHmt-7c')
ADMIN_USER_ID = 2073879359  # Ваш ID


class MondayAttendanceBot:
    def __init__(self, token):
        self.token = token
        self.chat_id = None
        self.last_poll_message_id = None
        self.current_poll_id = None
        self.votes = {}
        self.application = Application.builder().token(token).build()

        # Обработчики команд
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("attendance", self.attendance_command))
        self.application.add_handler(CommandHandler("results", self.results_command))
        self.application.add_handler(CommandHandler("voters", self.voters_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("id", self.id_command))
        self.application.add_handler(CommandHandler("fuck", self.fuck_command))

        # Обработчики callback'ов
        self.application.add_handler(CallbackQueryHandler(self.handle_vote, pattern="^vote_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_admin, pattern="^admin_"))

    def save_data(self):
        """Сохраняем данные голосования с обработкой кодировки"""
        try:
            data = {
                'chat_id': self.chat_id,
                'last_poll_message_id': self.last_poll_message_id,
                'current_poll_id': self.current_poll_id,
                'votes': self.votes,
                'last_updated': datetime.now().isoformat()
            }
            with open('attendance_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, default=str, indent=2)
            logger.info("Данные сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")

    def load_data(self):
        """Загружаем данные голосования с обработкой ошибок"""
        try:
            if os.path.exists('attendance_data.json'):
                with open('attendance_data.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.chat_id = data.get('chat_id')
                    self.last_poll_message_id = data.get('last_poll_message_id')
                    self.current_poll_id = data.get('current_poll_id')
                    self.votes = data.get('votes', {})
                    logger.info("Данные загружены")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка JSON: {e}. Создаем новые данные.")
            # Создаем backup поврежденного файла
            if os.path.exists('attendance_data.json'):
                os.rename('attendance_data.json', f'attendance_data_backup_{int(time.time())}.json')
            self.votes = {}
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            self.votes = {}

    def get_next_monday_date(self):
        """Получаем дату следующего понедельника"""
        today = datetime.now()
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_monday = today + timedelta(days=days_ahead)
        return next_monday.strftime('%d.%m.%Y')

    async def is_admin(self, user_id):
        return user_id == ADMIN_USER_ID

    async def check_admin_access(self, update: Update):
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

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_admin_access(update):
            return

        self.chat_id = update.effective_chat.id
        user = update.effective_user

        logger.info(f"Бот активирован в чате {self.chat_id}")

        await update.message.reply_text(
            "✅ <b>Бот для учета посещаемости активирован!</b>\n\n"
            "📅 <b>Каждый понедельник в 19:00</b> я буду создавать новое голосование.\n\n"
            "📋 <b>Команды:</b>\n"
            "/attendance - текущее голосование\n"
            "/results - результаты\n"
            "/voters - кто как голосовал\n"
            "/admin - управление\n"
            "/status - статус бота\n"
            "/fuck - отправить нахуй\n\n"
            "<i>Просто нажмите на кнопку в закрепленном сообщении чтобы отметить свое присутствие</i>",
            parse_mode='HTML'
        )
        self.save_data()

        # Создаем голосование после активации
        await self.create_monday_poll()

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

    async def create_monday_poll(self):
        """Создаем голосование на понедельник"""
        if not self.chat_id:
            logger.warning("Чат не настроен")
            return

        try:
            self.current_poll_id = str(int(datetime.now().timestamp()))

            message_text = (
                f"<b>🗓️ Посещаемость на следующий понедельник</b>\n"
                f"<b>📅 {self.get_next_monday_date()} (Понедельник)</b>\n\n"
                "❓ <b>Кто приходит?</b>\n\n"
                "✅ <b>К 1</b> - приду к первому уроку\n"
                "⏰ <b>Ко 2</b> - приду ко второму уроку\n"
                "❌ <b>Не прихожу</b> - не буду\n\n"
                "<i>Отметьтесь, пожалуйста, чтобы все были в курсе</i>"
            )

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
                    logger.warning(f"Не удалось открепить: {e}")

            # Закрепляем новое сообщение
            await self.application.bot.pin_chat_message(
                chat_id=self.chat_id,
                message_id=message.message_id,
                disable_notification=True
            )

            self.last_poll_message_id = message.message_id
            self.save_data()

            logger.info(f"✅ Новое голосование создано")

        except Exception as e:
            logger.error(f"❌ Ошибка создания голосования: {e}")

    async def create_voting_keyboard(self):
        """Создаем клавиатуру для голосования"""
        votes_count = {'1': 0, '2': 0, '3': 0}
        for vote_data in self.votes.values():
            option = vote_data['option']
            votes_count[option] += 1

        total_votes = len(self.votes)

        keyboard = []
        options = [
            ('1', 'К 1', '✅'),
            ('2', 'Ко 2', '⏰'),
            ('3', 'Не прихожу', '❌')
        ]

        for option, label, emoji in options:
            count = votes_count[option]
            percentage = (count / total_votes * 100) if total_votes > 0 else 0
            text = f"{emoji} {label} ({count} - {percentage:.1f}%)"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"vote_{option}")])

        # Кнопка для просмотра результатов (только для админа)
        if await self.is_admin(ADMIN_USER_ID):
            keyboard.append([InlineKeyboardButton("📊 Посмотреть результаты", callback_data="admin_full_stats")])

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
        """Полная статистика"""
        total_users = len(self.votes)

        text = f"<b>📈 Статистика посещаемости:</b>\n"
        text += f"<b>📅 {self.get_next_monday_date()}</b>\n\n"

        votes_count = {'1': 0, '2': 0, '3': 0}
        voters_by_option = {'1': [], '2': [], '3': []}

        for vote_data in self.votes.values():
            option = vote_data['option']
            name = vote_data['name']
            votes_count[option] += 1
            voters_by_option[option].append(name)

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
                for voter in voters[:10]:  # Ограничиваем вывод
                    text += f"   👤 {voter}\n"
                if len(voters) > 10:
                    text += f"   ... и еще {len(voters) - 10}\n"
            text += "\n"

        return text

    async def handle_vote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка голосования с обработкой ошибок"""
        query = update.callback_query
        user = query.from_user

        try:
            # Проверяем, не устарел ли callback
            if (datetime.now() - query.message.date).seconds > 120:
                await query.answer("❌ Голосование устарело", show_alert=True)
                return

            option = query.data.split('_')[1]

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

            option_names = {'1': 'К 1', '2': 'Ко 2', '3': 'Не прихожу'}
            await query.answer(f"✅ {option_names[option]}")
            self.save_data()

            logger.info(f"Пользователь {user.full_name} проголосовал")

        except BadRequest as e:
            if "not modified" in str(e).lower():
                # Игнорируем ошибку "сообщение не изменено"
                await query.answer()
            else:
                logger.error(f"Ошибка BadRequest: {e}")
                await query.answer("❌ Ошибка, попробуйте снова")
        except Exception as e:
            logger.error(f"Ошибка голосования: {e}")
            await query.answer("❌ Ошибка, попробуйте снова")

    async def handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка админ-команд"""
        query = update.callback_query
        user = query.from_user

        if not await self.is_admin(user.id):
            try:
                await query.answer("🚫 Ты кто такой? Пошёл нахуй!", show_alert=True)
            except:
                pass  # Игнорируем ошибки ответа
            return

        try:
            data = query.data

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

        except Exception as e:
            logger.error(f"Ошибка админ-команды: {e}")
            try:
                await query.answer("❌ Ошибка")
            except:
                pass

    async def check_schedule(self):
        """Проверяем расписание"""
        while True:
            try:
                now = datetime.now()
                # Каждый понедельник в 19:00
                if now.weekday() == 0 and now.hour == 19 and now.minute == 0:
                    logger.info("Создаем новое голосование по расписанию!")
                    await self.create_monday_poll()
                    # Ждем 61 минуту чтобы не создавать повторно
                    await asyncio.sleep(61)
                else:
                    await asyncio.sleep(30)  # Проверяем каждые 30 секунд

            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                await asyncio.sleep(60)

    async def run(self):
        """Запуск бота"""
        self.load_data()

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("🤖 Бот запущен!")

        # Создаем голосование если его нет
        if not self.current_poll_id and self.chat_id:
            logger.info("Создаем первое голосование...")
            await self.create_monday_poll()

        # Запускаем планировщик
        await self.check_schedule()


if __name__ == "__main__":
    print("🚀 Запуск бота для учета посещаемости...")
    print(f"📅 Расписание: каждый понедельник в 19:00")
    print("🤖 Токен бота: 8455558290:AAHDiNfqtG7LMOWor9rHhpwtCVv-JHmt-7c")
    print(f"👑 Админ ID: {ADMIN_USER_ID}")

    bot = MondayAttendanceBot(BOT_TOKEN)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")