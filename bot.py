import asyncio
import logging
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest, TimedOut
import time
import json
import os
from datetime import datetime, timedelta, timezone

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8455558290:AAHDiNfqtG7LMOWor9rHhpwtCVv-JHmt-7c')
MAIN_ADMIN_ID = 2073879359  # Главный администратор (нельзя удалить)


class ChatData:
    """Класс для управления данными чата"""

    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.admin_users = [MAIN_ADMIN_ID]
        self.last_updated = datetime.now().isoformat()

    def to_dict(self):
        return {
            'admin_users': self.admin_users,
            'last_updated': self.last_updated
        }

    @classmethod
    def from_dict(cls, chat_id, data):
        instance = cls(chat_id)
        instance.admin_users = data.get('admin_users', [MAIN_ADMIN_ID])
        instance.last_updated = data.get('last_updated', datetime.now().isoformat())

        # Гарантируем, что главный админ всегда в списке
        if MAIN_ADMIN_ID not in instance.admin_users:
            instance.admin_users.append(MAIN_ADMIN_ID)

        return instance


class DataManager:
    """Класс для управления данными бота"""

    def __init__(self, filename='bot_data.json'):
        self.filename = filename
        self.chats = {}

    def save_data(self):
        """Сохраняет данные в файл"""
        try:
            data = {
                'chats': {
                    str(chat_id): chat_data.to_dict()
                    for chat_id, chat_data in self.chats.items()
                },
                'last_updated': datetime.now().isoformat()
            }
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, default=str, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")

    def load_data(self):
        """Загружает данные из файла"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    if 'chats' in data:
                        for chat_id_str, chat_data in data['chats'].items():
                            chat_id = int(chat_id_str)
                            self.chats[chat_id] = ChatData.from_dict(chat_id, chat_data)

        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")
            self.chats = {}

    def get_chat_data(self, chat_id):
        """Получает данные чата, создает если нет"""
        if chat_id not in self.chats:
            self.chats[chat_id] = ChatData(chat_id)
        return self.chats[chat_id]


class PermissionManager:
    """Класс для управления правами доступа"""

    def __init__(self, data_manager):
        self.data_manager = data_manager

    async def is_admin(self, chat_id, user_id):
        """Проверяет, является ли пользователь администратором"""
        chat_data = self.data_manager.get_chat_data(chat_id)
        return user_id in chat_data.admin_users

    async def check_admin_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверяет права администратора и отправляет сообщение при отказе"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if not await self.is_admin(chat_id, user_id):
            await MessageSender.send_safe_message(
                context, chat_id,
                "🚫 У вас нет прав администратора в этом чате!"
            )
            return False
        return True


class MessageSender:
    """Класс для безопасной отправки сообщений"""

    @staticmethod
    async def send_safe_message(context, chat_id, text, parse_mode='HTML', reply_to_message_id=None, reply_markup=None):
        """Безопасная отправка сообщения с обработкой ошибок"""
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id,
                reply_markup=reply_markup
            )
            return True
        except BadRequest as e:
            if "Message to be replied not found" in str(e):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
                return True
            else:
                logger.error(f"Ошибка отправки сообщения: {e}")
                return False
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return False


class TimeManager:
    """Класс для работы со временем"""

    @staticmethod
    def parse_duration(duration_str):
        """Парсит строку времени в секунды"""
        try:
            duration_str = duration_str.lower().strip()

            if duration_str.endswith('m'):
                return int(duration_str[:-1]) * 60
            elif duration_str.endswith('h'):
                return int(duration_str[:-1]) * 3600
            elif duration_str.endswith('d'):
                return int(duration_str[:-1]) * 86400
            elif duration_str.endswith('w'):
                return int(duration_str[:-1]) * 604800
            else:
                return int(duration_str) * 60
        except:
            return None

    @staticmethod
    def format_duration(seconds):
        """Форматирует секунды в читаемый вид"""
        if seconds < 60:
            return f"{seconds} сек"
        elif seconds < 3600:
            return f"{seconds // 60} мин"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours} ч {minutes} мин"
            else:
                return f"{hours} ч"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            if hours > 0:
                return f"{days} дн {hours} ч"
            else:
                return f"{days} дн"


class AdminPanel:
    """Класс для управления панелью администратора"""

    def __init__(self, permission_manager, data_manager):
        self.permission_manager = permission_manager
        self.data_manager = data_manager

    async def show_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает панель администратора"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        chat_id = update.effective_chat.id
        user = update.effective_user

        keyboard = [
            [InlineKeyboardButton("👥 Управление админами", callback_data="admin_manage")],
            [InlineKeyboardButton("🔇 Мут пользователя", callback_data="admin_mute")],
            [InlineKeyboardButton("🚫 Бан пользователя", callback_data="admin_ban")],
            [InlineKeyboardButton("👢 Кик пользователя", callback_data="admin_kick")],
            [InlineKeyboardButton("📊 Статус бота", callback_data="admin_status")],
            [InlineKeyboardButton("🆔 Получить ID", callback_data="admin_get_id")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            f"👑 <b>Панель администратора</b>\n\n"
            f"👤 <b>Пользователь:</b> {user.full_name}\n"
            f"🆔 <b>Ваш ID:</b> <code>{user.id}</code>\n"
            f"💬 <b>Чат ID:</b> <code>{chat_id}</code>\n\n"
            f"⚡ <b>Выберите действие:</b>"
        )

        await MessageSender.send_safe_message(
            context, chat_id, text, reply_markup=reply_markup
        )

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нажатия на кнопки панели администратора"""
        query = update.callback_query
        await query.answer()

        if not await self.permission_manager.is_admin(query.message.chat_id, query.from_user.id):
            await query.edit_message_text("🚫 У вас нет прав администратора!")
            return

        callback_data = query.data

        if callback_data == "admin_manage":
            await self._show_admin_management(query, context)
        elif callback_data == "admin_mute":
            await self._show_mute_help(query, context)
        elif callback_data == "admin_ban":
            await self._show_ban_help(query, context)
        elif callback_data == "admin_kick":
            await self._show_kick_help(query, context)
        elif callback_data == "admin_status":
            await self._show_status(query, context)
        elif callback_data == "admin_get_id":
            await self._show_get_id_help(query, context)
        elif callback_data == "admin_back":
            await self.show_admin_panel_from_query(query, context)

    async def show_admin_panel_from_query(self, query, context):
        """Показывает панель администратора из callback query"""
        chat_id = query.message.chat_id
        user = query.from_user

        keyboard = [
            [InlineKeyboardButton("👥 Управление админами", callback_data="admin_manage")],
            [InlineKeyboardButton("🔇 Мут пользователя", callback_data="admin_mute")],
            [InlineKeyboardButton("🚫 Бан пользователя", callback_data="admin_ban")],
            [InlineKeyboardButton("👢 Кик пользователя", callback_data="admin_kick")],
            [InlineKeyboardButton("📊 Статус бота", callback_data="admin_status")],
            [InlineKeyboardButton("🆔 Получить ID", callback_data="admin_get_id")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            f"👑 <b>Панель администратора</b>\n\n"
            f"👤 <b>Пользователь:</b> {user.full_name}\n"
            f"🆔 <b>Ваш ID:</b> <code>{user.id}</code>\n"
            f"💬 <b>Чат ID:</b> <code>{chat_id}</code>\n\n"
            f"⚡ <b>Выберите действие:</b>"
        )

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    async def _show_admin_management(self, query, context):
        """Показывает управление администраторами"""
        chat_id = query.message.chat_id
        chat_data = self.data_manager.get_chat_data(chat_id)

        keyboard = [
            [InlineKeyboardButton("📋 Список админов", callback_data="admin_list")],
            [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton("➖ Удалить админа", callback_data="admin_remove")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            "👑 <b>Управление администраторами</b>\n\n"
            f"📊 <b>Всего админов:</b> {len(chat_data.admin_users)}\n\n"
            "⚡ <b>Выберите действие:</b>"
        )

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    async def _show_mute_help(self, query, context):
        """Показывает справку по муту"""
        text = (
            "🔇 <b>Мут пользователя</b>\n\n"
            "📝 <b>Использование:</b>\n"
            "<code>/mute ID</code> - мут на 10 мин\n"
            "<code>/mute ID 1h</code> - мут на 1 час\n"
            "<code>/mute ID 2d</code> - мут на 2 дня\n\n"
            "💡 <b>Примеры времени:</b>\n"
            "• 30m - 30 минут\n"
            "• 2h - 2 часа\n"
            "• 1d - 1 день\n"
            "• 1w - 1 неделя\n\n"
            "🔄 <b>Или ответьте на сообщение:</b>\n"
            "<code>/mute 1h</code>"
        )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    async def _show_ban_help(self, query, context):
        """Показывает справку по бану"""
        text = (
            "🚫 <b>Бан пользователя</b>\n\n"
            "📝 <b>Использование:</b>\n"
            "<code>/ban ID</code> - бан навсегда\n"
            "<code>/ban ID 1h</code> - бан на 1 час\n"
            "<code>/ban ID 2d</code> - бан на 2 дня\n\n"
            "💡 <b>Примеры времени:</b>\n"
            "• 30m - 30 минут\n"
            "• 2h - 2 часа\n"
            "• 1d - 1 день\n"
            "• 1w - 1 неделя\n\n"
            "🔄 <b>Или ответьте на сообщение:</b>\n"
            "<code>/ban 1h</code>"
        )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    async def _show_kick_help(self, query, context):
        """Показывает справку по кику"""
        text = (
            "👢 <b>Кик пользователя</b>\n\n"
            "📝 <b>Использование:</b>\n"
            "<code>/kick ID</code> - кикнуть пользователя\n\n"
            "🔄 <b>Или ответьте на сообщение:</b>\n"
            "<code>/kick</code>\n\n"
            "💡 <i>Пользователь сможет вернуться по приглашению</i>"
        )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    async def _show_status(self, query, context):
        """Показывает статус бота"""
        chat_id = query.message.chat_id
        chat_data = self.data_manager.get_chat_data(chat_id)

        text = (
            "🤖 <b>Статус бота</b>\n\n"
            f"✅ <b>Бот активен</b>\n"
            f"👑 <b>Администраторов:</b> {len(chat_data.admin_users)}\n"
            f"💬 <b>ID чата:</b> <code>{chat_id}</code>\n"
            f"🕒 <b>Последнее обновление:</b> {chat_data.last_updated}\n\n"
            f"💡 <i>Бот работает стабильно</i> 🚀"
        )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    async def _show_get_id_help(self, query, context):
        """Показывает справку по получению ID"""
        text = (
            "🆔 <b>Получение ID</b>\n\n"
            "📝 <b>Команды:</b>\n"
            "<code>/id</code> - ваш ID\n"
            "<code>/get_id</code> - в ответ на сообщение\n"
            "<code>/all_ids</code> - ID всех админов чата\n"
            "<code>/chat_info</code> - информация о чате\n\n"
            "💡 <i>Используйте ID для команд управления</i>"
        )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


class AdminCommands:
    """Класс для команд управления администраторами"""

    def __init__(self, data_manager, permission_manager):
        self.data_manager = data_manager
        self.permission_manager = permission_manager

    async def admins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список администраторов"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        chat_id = update.effective_chat.id
        chat_data = self.data_manager.get_chat_data(chat_id)

        if not chat_data.admin_users:
            await MessageSender.send_safe_message(context, chat_id, "📝 <b>Список администраторов пуст</b>")
            return

        admin_list = []
        for i, admin_id in enumerate(chat_data.admin_users, 1):
            try:
                user = await context.bot.get_chat(admin_id)
                admin_info = f"{i}. 👤 {user.full_name}"
                if user.username:
                    admin_info += f" (@{user.username})"
                admin_info += f" | 🆔 <code>{admin_id}</code>"

                if admin_id == MAIN_ADMIN_ID:
                    admin_info += " 👑"

                admin_list.append(admin_info)
            except:
                admin_list.append(f"{i}. 🆔 <code>{admin_id}</code>")

        text = f"👑 <b>Администраторы чата:</b>\n\n" + "\n".join(admin_list)
        text += f"\n\n📊 <b>Всего:</b> {len(chat_data.admin_users)} администраторов"

        await MessageSender.send_safe_message(context, chat_id, text)

    async def add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавляет администратора"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        if not context.args and not update.message.reply_to_message:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/add_admin 123456789</code> - добавить по ID\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /add_admin</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id
            chat_data = self.data_manager.get_chat_data(chat_id)

            if update.message.reply_to_message:
                user_id = update.message.reply_to_message.from_user.id
                user_name = update.message.reply_to_message.from_user.full_name
            else:
                user_id = int(context.args[0])
                try:
                    user = await context.bot.get_chat(user_id)
                    user_name = user.full_name
                except:
                    user_name = f"Пользователь ({user_id})"

            if user_id in chat_data.admin_users:
                await MessageSender.send_safe_message(
                    context, chat_id,
                    f"ℹ️ <b>Пользователь уже является администратором</b>\n\n"
                    f"👤 {user_name}\n🆔 <code>{user_id}</code>"
                )
                return

            chat_data.admin_users.append(user_id)
            self.data_manager.save_data()

            await MessageSender.send_safe_message(
                context, chat_id,
                f"✅ <b>Новый администратор добавлен</b>\n\n"
                f"👤 {user_name}\n🆔 <code>{user_id}</code>"
            )

        except ValueError:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID."
            )
        except Exception as e:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                f"❌ Ошибка добавления: {e}"
            )

    async def remove_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаляет администратора"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        if not context.args and not update.message.reply_to_message:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/remove_admin 123456789</code> - удалить по ID\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /remove_admin</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id
            chat_data = self.data_manager.get_chat_data(chat_id)

            if update.message.reply_to_message:
                user_id = update.message.reply_to_message.from_user.id
                user_name = update.message.reply_to_message.from_user.full_name
            else:
                user_id = int(context.args[0])
                try:
                    user = await context.bot.get_chat(user_id)
                    user_name = user.full_name
                except:
                    user_name = f"Пользователь ({user_id})"

            if user_id == MAIN_ADMIN_ID:
                await MessageSender.send_safe_message(context, chat_id, "❌ Нельзя удалить главного администратора!")
                return

            if user_id not in chat_data.admin_users:
                await MessageSender.send_safe_message(context, chat_id, "❌ Пользователь не является администратором")
                return

            chat_data.admin_users.remove(user_id)
            self.data_manager.save_data()

            await MessageSender.send_safe_message(
                context, chat_id,
                f"✅ <b>Администратор удален</b>\n\n"
                f"👤 {user_name}\n🆔 <code>{user_id}</code>"
            )

        except ValueError:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID."
            )
        except Exception as e:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                f"❌ Ошибка удаления: {e}"
            )


class UserCommands:
    """Класс для пользовательских команд"""

    def __init__(self, permission_manager, data_manager):
        self.permission_manager = permission_manager
        self.data_manager = data_manager

    async def id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает ID пользователя"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        is_admin = await self.permission_manager.is_admin(chat_id, user.id)

        admin_status = "👑 Администратор" if is_admin else "👤 Пользователь"

        await MessageSender.send_safe_message(
            context, chat_id,
            f"👤 <b>Ваша информация:</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📛 <b>Имя:</b> {user.full_name}\n"
            f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}\n"
            f"💬 <b>ID чата:</b> <code>{chat_id}</code>\n"
            f"🎯 <b>Статус:</b> {admin_status}"
        )

    async def get_id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получает ID пользователя"""
        if not context.args and not update.message.reply_to_message:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/get_id</code> - в ответ на сообщение пользователя\n"
                "<code>/get_id 123456789</code> - по ID"
            )
            return

        try:
            if update.message.reply_to_message:
                user = update.message.reply_to_message.from_user
                await MessageSender.send_safe_message(
                    context, update.effective_chat.id,
                    f"👤 <b>Информация о пользователе:</b>\n\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"📛 <b>Имя:</b> {user.full_name}\n"
                    f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}"
                )
            elif context.args:
                target = context.args[0]
                if target.isdigit():
                    user_id = int(target)
                    try:
                        user = await context.bot.get_chat(user_id)
                        await MessageSender.send_safe_message(
                            context, update.effective_chat.id,
                            f"👤 <b>Информация о пользователе:</b>\n\n"
                            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                            f"📛 <b>Имя:</b> {user.full_name}\n"
                            f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}"
                        )
                    except:
                        await MessageSender.send_safe_message(
                            context, update.effective_chat.id,
                            f"❌ Пользователь с ID {target} не найден"
                        )
                else:
                    await MessageSender.send_safe_message(
                        context, update.effective_chat.id,
                        "❌ Используйте числовой ID пользователя"
                    )

        except Exception as e:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                f"❌ Ошибка: {e}"
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает справку по командам"""
        chat_id = update.effective_chat.id
        is_admin = await self.permission_manager.is_admin(chat_id, update.effective_user.id)

        help_text = (
            "🤖 <b>Помощь по командам бота</b>\n\n"
            "🆔 <b>Получение ID:</b>\n"
            "<code>/id</code> - ваш ID\n"
            "<code>/get_id</code> - ID пользователя\n"
            "<code>/all_ids</code> - ID всех администраторов\n"
            "<code>/chat_info</code> - информация о чате\n"
            "<code>/status</code> - статус бота\n\n"
        )

        if is_admin:
            help_text += (
                "👑 <b>Администраторские команды:</b>\n"
                "<code>/admin</code> - панель администратора\n"
                "<code>/admins</code> - список администраторов\n"
                "<code>/add_admin ID</code> - добавить администратора\n"
                "<code>/remove_admin ID</code> - удалить администратора\n\n"
                "🔇 <b>Мут:</b>\n"
                "<code>/mute ID [время]</code> - мут пользователя\n"
                "<code>/unmute ID</code> - размутить\n\n"
                "🚫 <b>Бан:</b>\n"
                "<code>/ban ID [время]</code> - бан пользователя\n"
                "<code>/unban ID</code> - разбанить\n\n"
                "👢 <b>Кик:</b>\n"
                "<code>/kick ID</code> - кикнуть пользователя\n"
            )

        help_text += (
            "\n💡 <b>Советы:</b>\n"
            "• Используйте ID вместо username\n"
            "• Для команд можно отвечать на сообщения\n"
            "• Каждый чат имеет отдельный список администраторов"
        )

        await MessageSender.send_safe_message(context, chat_id, help_text)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда start"""
        chat_id = update.effective_chat.id

        await MessageSender.send_safe_message(
            context, chat_id,
            f"✅ <b>Продвинутый бот-администратор активирован!</b>\n\n"
            f"⚡ <b>Основные возможности:</b>\n"
            f"• Управление администраторами\n"
            f"• Мут, бан и кик пользователей\n"
            f"• Получение ID пользователей\n\n"
            f"💡 <i>Используйте /help для полного списка команд</i>"
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает статус бота"""
        chat_id = update.effective_chat.id
        chat_data = self.data_manager.get_chat_data(chat_id)
        is_admin = await self.permission_manager.is_admin(chat_id, update.effective_user.id)
        admin_status = "👑 Администратор" if is_admin else "👤 Пользователь"

        status_text = (
            "🤖 <b>Статус бота:</b>\n\n"
            f"✅ <b>Бот активен</b>\n"
            f"👑 <b>Администраторов:</b> {len(chat_data.admin_users)}\n"
            f"💬 <b>ID чата:</b> <code>{chat_id}</code>\n"
            f"🎯 <b>Ваш статус:</b> {admin_status}\n\n"
            f"💡 <i>Бот работает стабильно</i> 🚀"
        )
        await MessageSender.send_safe_message(context, chat_id, status_text)

    async def all_ids_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает ID всех администраторов чата"""
        try:
            chat_id = update.effective_chat.id
            admins = await context.bot.get_chat_administrators(chat_id)

            if not admins:
                await MessageSender.send_safe_message(context, chat_id, "❌ Не удалось получить список администраторов")
                return

            admin_list = []
            for i, admin in enumerate(admins, 1):
                user = admin.user
                admin_info = f"{i}. {user.full_name}"
                if user.username:
                    admin_info += f" (@{user.username})"
                admin_info += f" - <code>{user.id}</code>"

                if admin.status == 'creator':
                    admin_info += " 👑"

                admin_list.append(admin_info)

            text = "👥 <b>Администраторы чата:</b>\n\n" + "\n".join(admin_list)
            await MessageSender.send_safe_message(context, chat_id, text)

        except Exception as e:
            await MessageSender.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка: {e}")

    async def chat_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает информацию о чате"""
        try:
            chat = update.effective_chat
            chat_id = chat.id
            chat_data = self.data_manager.get_chat_data(chat_id)

            admin_count = len(chat_data.admin_users)

            await MessageSender.send_safe_message(
                context, chat_id,
                f"💬 <b>Информация о чате:</b>\n\n"
                f"📛 <b>Название:</b> {chat.title}\n"
                f"🆔 <b>ID чата:</b> <code>{chat.id}</code>\n"
                f"👥 <b>Тип:</b> {chat.type}\n"
                f"👑 <b>Админов бота:</b> {admin_count}"
            )
        except Exception as e:
            await MessageSender.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка: {e}")


class ModerationCommands:
    """Класс для команд модерации"""

    def __init__(self, permission_manager, time_manager):
        self.permission_manager = permission_manager
        self.time_manager = time_manager

    async def mute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мут пользователя"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        if not context.args and not update.message.reply_to_message:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/mute ID</code> - мут на 10 мин\n"
                "<code>/mute ID 1h</code> - мут на 1 час\n\n"
                "💡 <i>Или ответьте на сообщение командой /mute</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id

            if update.message.reply_to_message:
                user_to_mute = update.message.reply_to_message.from_user
                user_id = user_to_mute.id
                duration_str = context.args[0] if context.args else "10m"
            else:
                user_id = int(context.args[0])
                duration_str = context.args[1] if len(context.args) > 1 else "10m"

            duration = self.time_manager.parse_duration(duration_str)
            if not duration:
                await MessageSender.send_safe_message(
                    context, chat_id,
                    "❌ Неверный формат времени. Используйте: 10m, 1h, 1d, 1w"
                )
                return

            # Проверки
            if user_id == context.bot.id:
                await MessageSender.send_safe_message(context, chat_id, "❌ Не могу замутить самого себя!")
                return

            if await self.permission_manager.is_admin(chat_id, user_id):
                await MessageSender.send_safe_message(context, chat_id, "❌ Нельзя замутить администратора бота!")
                return

            # Выполняем мут
            until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )

            # Получаем имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await MessageSender.send_safe_message(
                context, chat_id,
                f"🔇 <b>{user_name} замьючен на {self.time_manager.format_duration(duration)}</b>\n\n"
                f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"🆔 ID: <code>{user_id}</code>"
            )

        except Exception as e:
            await MessageSender.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка мута: {e}")

    async def unmute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Размут пользователя"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        if not context.args and not update.message.reply_to_message:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/unmute ID</code> - размутить по ID\n\n"
                "💡 <i>Или ответьте на сообщение командой /unmute</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id

            if update.message.reply_to_message:
                user_id = update.message.reply_to_message.from_user.id
            else:
                user_id = int(context.args[0])

            # Размут - используем только совместимые параметры
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )

            # Получаем имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await MessageSender.send_safe_message(
                context, chat_id,
                f"🔊 <b>{user_name} размьючен</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>"
            )

        except Exception as e:
            await MessageSender.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка размута: {e}")

    async def ban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Бан пользователя"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        if not context.args and not update.message.reply_to_message:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/ban ID</code> - бан навсегда\n"
                "<code>/ban ID 1h</code> - бан на 1 час\n\n"
                "💡 <i>Или ответьте на сообщение командой /ban</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id

            if update.message.reply_to_message:
                user_to_ban = update.message.reply_to_message.from_user
                user_id = user_to_ban.id
                duration_str = context.args[0] if context.args else "forever"
            else:
                user_id = int(context.args[0])
                duration_str = context.args[1] if len(context.args) > 1 else "forever"

            # Парсим время
            until_date = None
            if duration_str != "forever":
                duration = self.time_manager.parse_duration(duration_str)
                if not duration:
                    await MessageSender.send_safe_message(
                        context, chat_id,
                        "❌ Неверный формат времени. Используйте: 10m, 1h, 1d, 1w"
                    )
                    return
                until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)

            # Проверки
            if user_id == context.bot.id:
                await MessageSender.send_safe_message(context, chat_id, "❌ Не могу забанить самого себя!")
                return

            if await self.permission_manager.is_admin(chat_id, user_id):
                await MessageSender.send_safe_message(context, chat_id, "❌ Нельзя забанить администратора бота!")
                return

            # Выполняем бан
            await context.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=until_date
            )

            # Получаем имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            if until_date:
                duration_text = f"на {self.time_manager.format_duration(duration)}"
                until_text = f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}"
            else:
                duration_text = "навсегда"
                until_text = "⏰ Навсегда"

            await MessageSender.send_safe_message(
                context, chat_id,
                f"🚫 <b>{user_name} забанен {duration_text}</b>\n\n"
                f"{until_text}\n"
                f"🆔 ID: <code>{user_id}</code>"
            )

        except Exception as e:
            await MessageSender.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка бана: {e}")

    async def unban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Разбан пользователя"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        if not context.args and not update.message.reply_to_message:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/unban ID</code> - разбанить по ID\n\n"
                "💡 <i>Или ответьте на сообщение командой /unban</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id

            if update.message.reply_to_message:
                user_id = update.message.reply_to_message.from_user.id
            else:
                user_id = int(context.args[0])

            # Выполняем разбан
            await context.bot.unban_chat_member(
                chat_id=chat_id,
                user_id=user_id
            )

            # Получаем имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await MessageSender.send_safe_message(
                context, chat_id,
                f"✅ <b>{user_name} разбанен</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>"
            )

        except Exception as e:
            await MessageSender.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка разбана: {e}")

    async def kick_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Кик пользователя"""
        if not await self.permission_manager.check_admin_access(update, context):
            return

        if not context.args and not update.message.reply_to_message:
            await MessageSender.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/kick ID</code> - кикнуть по ID\n\n"
                "💡 <i>Или ответьте на сообщение командой /kick</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id

            if update.message.reply_to_message:
                user_id = update.message.reply_to_message.from_user.id
            else:
                user_id = int(context.args[0])

            # Проверки
            if user_id == context.bot.id:
                await MessageSender.send_safe_message(context, chat_id, "❌ Не могу кикнуть самого себя!")
                return

            if await self.permission_manager.is_admin(chat_id, user_id):
                await MessageSender.send_safe_message(context, chat_id, "❌ Нельзя кикнуть администратора бота!")
                return

            # Выполняем кик (бан на 30 секунд + разбан)
            until_date = datetime.now(timezone.utc) + timedelta(seconds=30)
            await context.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=until_date
            )

            # Сразу разбаниваем, чтобы пользователь мог вернуться по приглашению
            await context.bot.unban_chat_member(
                chat_id=chat_id,
                user_id=user_id
            )

            # Получаем имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await MessageSender.send_safe_message(
                context, chat_id,
                f"👢 <b>{user_name} кикнут из чата</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"💡 <i>Пользователь может вернуться по приглашению</i>"
            )

        except Exception as e:
            await MessageSender.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка кика: {e}")


class AdvancedAdminBot:
    """Главный класс бота"""

    def __init__(self, token):
        self.token = token
        self.data_manager = DataManager()
        self.permission_manager = PermissionManager(self.data_manager)
        self.time_manager = TimeManager()

        # Инициализация компонентов
        self.admin_panel = AdminPanel(self.permission_manager, self.data_manager)
        self.admin_commands = AdminCommands(self.data_manager, self.permission_manager)
        self.user_commands = UserCommands(self.permission_manager, self.data_manager)
        self.moderation_commands = ModerationCommands(self.permission_manager, self.time_manager)

        # Создание приложения
        self.application = Application.builder().token(token).build()

        # Загрузка данных и настройка обработчиков
        self.data_manager.load_data()
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.user_commands.start_command))
        self.application.add_handler(CommandHandler("id", self.user_commands.id_command))
        self.application.add_handler(CommandHandler("help", self.user_commands.help_command))
        self.application.add_handler(CommandHandler("status", self.user_commands.status_command))
        self.application.add_handler(CommandHandler("get_id", self.user_commands.get_id_command))
        self.application.add_handler(CommandHandler("all_ids", self.user_commands.all_ids_command))
        self.application.add_handler(CommandHandler("chat_info", self.user_commands.chat_info_command))

        # Команды администраторов
        self.application.add_handler(CommandHandler("admin", self.admin_panel.show_admin_panel))
        self.application.add_handler(CommandHandler("admins", self.admin_commands.admins_command))
        self.application.add_handler(CommandHandler("add_admin", self.admin_commands.add_admin_command))
        self.application.add_handler(CommandHandler("remove_admin", self.admin_commands.remove_admin_command))

        # Команды модерации
        self.application.add_handler(CommandHandler("mute", self.moderation_commands.mute_command))
        self.application.add_handler(CommandHandler("unmute", self.moderation_commands.unmute_command))
        self.application.add_handler(CommandHandler("ban", self.moderation_commands.ban_command))
        self.application.add_handler(CommandHandler("unban", self.moderation_commands.unban_command))
        self.application.add_handler(CommandHandler("kick", self.moderation_commands.kick_command))

        # Обработчики ответов на сообщения
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/mute\b'), self.handle_reply_mute))
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/unmute\b'), self.handle_reply_unmute))
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/ban\b'), self.handle_reply_ban))
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/unban\b'), self.handle_reply_unban))
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/kick\b'), self.handle_reply_kick))
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/add_admin\b'), self.handle_reply_add_admin))
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/remove_admin\b'),
                           self.handle_reply_remove_admin))

        # Обработчик callback-ов для панели администратора
        self.application.add_handler(CallbackQueryHandler(
            self.admin_panel.handle_admin_callback,
            pattern=r"^admin_"
        ))

        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)

    async def handle_reply_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик мута по ответу на сообщение"""
        await self.moderation_commands.mute_command(update, context)

    async def handle_reply_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик размута по ответу на сообщение"""
        await self.moderation_commands.unmute_command(update, context)

    async def handle_reply_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик бана по ответу на сообщение"""
        await self.moderation_commands.ban_command(update, context)

    async def handle_reply_unban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик разбана по ответу на сообщение"""
        await self.moderation_commands.unban_command(update, context)

    async def handle_reply_kick(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кика по ответу на сообщение"""
        await self.moderation_commands.kick_command(update, context)

    async def handle_reply_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик добавления админа по ответу на сообщение"""
        await self.admin_commands.add_admin_command(update, context)

    async def handle_reply_remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик удаления админа по ответу на сообщение"""
        await self.admin_commands.remove_admin_command(update, context)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка: {context.error}", exc_info=context.error)

        try:
            if update and update.effective_chat:
                await MessageSender.send_safe_message(
                    context, update.effective_chat.id,
                    "❌ Произошла ошибка при обработке команды. Попробуйте еще раз."
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения об ошибке: {e}")

    def run(self):
        """Запуск бота"""
        print("🚀 Запуск продвинутого бота-администратора...")
        print(f"👑 Главный админ ID: {MAIN_ADMIN_ID}")
        print("💡 Возможности: мут, бан, кик, управление админами")
        print("💡 Панель администратора: /admin")
        print("💡 Используйте /help для списка команд")

        try:
            self.application.run_polling()
        except KeyboardInterrupt:
            print("\n🛑 Бот остановлен пользователем")
            self.data_manager.save_data()
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    bot = AdvancedAdminBot(BOT_TOKEN)
    bot.run()