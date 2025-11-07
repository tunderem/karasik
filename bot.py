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
ADMIN_USER_ID = 2073879359  # Ваш ID


class MondayAttendanceBot:
    def __init__(self, token):
        self.token = token
        self.chat_id = None
        self.last_poll_message_id = None
        self.current_poll_id = None
        self.votes = {}
        self.mute_settings = {
            'enabled': True,
            'duration': 300,  # 5 минут по умолчанию
            'reply_to_mute': True
        }
        self.allowed_users = [ADMIN_USER_ID]  # Список разрешенных пользователей
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
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("fix_rights", self.fix_rights_command))
        self.application.add_handler(CommandHandler("find", self.find_user_command))

        # Команды управления доступом
        self.application.add_handler(CommandHandler("access", self.access_command))
        self.application.add_handler(CommandHandler("add_user", self.add_user_command))
        self.application.add_handler(CommandHandler("remove_user", self.remove_user_command))
        self.application.add_handler(CommandHandler("users", self.users_command))

        # Команды мута
        self.application.add_handler(CommandHandler("mute", self.mute_command))
        self.application.add_handler(CommandHandler("unmute", self.unmute_command))
        self.application.add_handler(CommandHandler("mute_settings", self.mute_settings_command))
        self.application.add_handler(CommandHandler("mute_enable", self.mute_enable_command))
        self.application.add_handler(CommandHandler("mute_disable", self.mute_disable_command))
        self.application.add_handler(CommandHandler("mutelist", self.mute_list_command))

        # Обработчики callback'ов
        self.application.add_handler(CallbackQueryHandler(self.handle_vote, pattern="^vote_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_admin, pattern="^admin_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_mute, pattern="^mute_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_access, pattern="^access_"))

        # Обработчик ответов на сообщения для мута
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/mute\b'), self.handle_reply_mute))
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/unmute\b'), self.handle_reply_unmute))

    def save_data(self):
        """Сохраняем данные голосования с обработкой кодировки"""
        try:
            data = {
                'chat_id': self.chat_id,
                'last_poll_message_id': self.last_poll_message_id,
                'current_poll_id': self.current_poll_id,
                'votes': self.votes,
                'mute_settings': self.mute_settings,
                'allowed_users': self.allowed_users,
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
                    self.mute_settings = data.get('mute_settings', {
                        'enabled': True,
                        'duration': 300,
                        'reply_to_mute': True
                    })
                    self.allowed_users = data.get('allowed_users', [ADMIN_USER_ID])
                    logger.info("Данные загружены")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка JSON: {e}. Создаем новые данные.")
            if os.path.exists('attendance_data.json'):
                os.rename('attendance_data.json', f'attendance_data_backup_{int(time.time())}.json')
            self.votes = {}
            self.allowed_users = [ADMIN_USER_ID]
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            self.votes = {}
            self.allowed_users = [ADMIN_USER_ID]

    def get_next_monday_date(self):
        """Получаем дату следующего понедельника"""
        today = datetime.now()
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_monday = today + timedelta(days=days_ahead)
        return next_monday.strftime('%d.%m.%Y')

    async def is_admin(self, user_id):
        """Проверяет, является ли пользователь администратором"""
        return user_id == ADMIN_USER_ID

    async def is_allowed(self, user_id):
        """Проверяет, есть ли у пользователя доступ к боту"""
        return user_id in self.allowed_users

    async def check_access(self, update: Update):
        """Проверяет доступ пользователя к командам"""
        user_id = update.effective_user.id

        if not await self.is_allowed(user_id):
            if await self.is_admin(user_id):
                # Если это админ, но его нет в списке - добавляем
                if user_id not in self.allowed_users:
                    self.allowed_users.append(user_id)
                    self.save_data()
                return True
            await update.message.reply_text(
                "🚫 <b>Доступ запрещен!</b>\n\n"
                "💡 <i>У вас нет прав для использования этого бота. "
                "Обратитесь к администратору для получения доступа.</i>",
                parse_mode='HTML'
            )
            return False
        return True

    async def check_admin_access(self, update: Update):
        """Проверяет права администратора"""
        user_id = update.effective_user.id
        if not await self.is_admin(user_id):
            await update.message.reply_text("🚫 Пошёл нахуй, петушара! Ты кто такой чтобы мне команды раздавать?")
            return False
        return True

    # ========== КОМАНДЫ УПРАВЛЕНИЯ ДОСТУПОМ ==========

    async def access_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Управление доступом к боту"""
        if not await self.check_admin_access(update):
            return

        keyboard = [
            [InlineKeyboardButton("👥 Список пользователей", callback_data="access_list")],
            [InlineKeyboardButton("➕ Добавить пользователя", callback_data="access_add")],
            [InlineKeyboardButton("➖ Удалить пользователя", callback_data="access_remove")],
            [InlineKeyboardButton("🔄 Обновить список", callback_data="access_refresh")],
            [InlineKeyboardButton("📊 Статистика доступа", callback_data="access_stats")]
        ]

        await update.message.reply_text(
            "🔐 <b>Управление доступом к боту</b>\n\n"
            f"👑 <b>Администратор:</b> {ADMIN_USER_ID}\n"
            f"👥 <b>Пользователей с доступом:</b> {len(self.allowed_users)}\n\n"
            f"💡 <i>Используйте кнопки для управления доступом</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def add_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить пользователя в список разрешенных"""
        if not await self.check_admin_access(update):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/add_user @username</code> - добавить по username\n"
                "<code>/add_user 123456789</code> - добавить по ID\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /add_user</i>",
                parse_mode='HTML'
            )
            return

        target = context.args[0]

        try:
            # Ищем пользователя
            user_id, user_name = await self.find_user_in_chat(update.effective_chat.id, target, context)

            if not user_id:
                await update.message.reply_text(
                    f"❌ <b>Пользователь '{target}' не найден</b>\n\n"
                    f"💡 <i>Проверьте:\n"
                    f"• Правильность написания username\n"
                    f"• Что пользователь есть в этом чате\n"
                    f"• Что ID пользователя верный</i>\n\n"
                    f"🔍 <b>Совет:</b> Используйте команду /id чтобы узнать ID пользователя",
                    parse_mode='HTML'
                )
                return

            # Проверяем, не добавлен ли уже пользователь
            if user_id in self.allowed_users:
                await update.message.reply_text(
                    f"ℹ️ <b>Пользователь уже имеет доступ</b>\n\n"
                    f"👤 <b>Имя:</b> {user_name}\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>",
                    parse_mode='HTML'
                )
                return

            # Добавляем пользователя
            self.allowed_users.append(user_id)
            self.save_data()

            await update.message.reply_text(
                f"✅ <b>Пользователь добавлен</b>\n\n"
                f"👤 <b>Имя:</b> {user_name}\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                f"💡 <i>Теперь пользователь может использовать команды бота</i>",
                parse_mode='HTML'
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка добавления пользователя: {e}")

    async def remove_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удалить пользователя из списка разрешенных"""
        if not await self.check_admin_access(update):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/remove_user @username</code> - удалить по username\n"
                "<code>/remove_user 123456789</code> - удалить по ID\n\n"
                "💡 <i>Нельзя удалить администратора</i>",
                parse_mode='HTML'
            )
            return

        target = context.args[0]

        try:
            # Ищем пользователя
            user_id, user_name = await self.find_user_in_chat(update.effective_chat.id, target, context)

            if not user_id:
                await update.message.reply_text(
                    f"❌ <b>Пользователь '{target}' не найден</b>\n\n"
                    f"💡 <i>Проверьте правильность введенных данных</i>",
                    parse_mode='HTML'
                )
                return

            # Проверяем, не пытаемся ли удалить администратора
            if await self.is_admin(user_id):
                await update.message.reply_text("❌ Нельзя удалить администратора!")
                return

            # Проверяем, есть ли пользователь в списке
            if user_id not in self.allowed_users:
                await update.message.reply_text(
                    f"ℹ️ <b>Пользователь не имеет доступа</b>\n\n"
                    f"👤 <b>Имя:</b> {user_name}\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>",
                    parse_mode='HTML'
                )
                return

            # Удаляем пользователя
            self.allowed_users.remove(user_id)
            self.save_data()

            await update.message.reply_text(
                f"✅ <b>Пользователь удален</b>\n\n"
                f"👤 <b>Имя:</b> {user_name}\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                f"💡 <i>Пользователь больше не может использовать команды бота</i>",
                parse_mode='HTML'
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка удаления пользователя: {e}")

    async def users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список пользователей с доступом"""
        if not await self.check_admin_access(update):
            return

        if not self.allowed_users:
            await update.message.reply_text("📝 <b>Список пользователей пуст</b>", parse_mode='HTML')
            return

        users_list = []
        for i, user_id in enumerate(self.allowed_users, 1):
            try:
                user_info = f"{i}. 🆔 <code>{user_id}</code>"

                # Помечаем администратора
                if await self.is_admin(user_id):
                    user_info += " 👑"

                users_list.append(user_info)
            except Exception as e:
                logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
                users_list.append(f"{i}. 🆔 <code>{user_id}</code> (ошибка получения данных)")

        text = "👥 <b>Пользователи с доступом к боту:</b>\n\n" + "\n".join(users_list)
        text += f"\n\n📊 <b>Всего:</b> {len(self.allowed_users)} пользователей"

        await update.message.reply_text(text, parse_mode='HTML')

    async def handle_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка управления доступом"""
        query = update.callback_query
        user = query.from_user

        if not await self.is_admin(user.id):
            await query.answer("🚫 Нет прав!", show_alert=True)
            return

        data = query.data

        try:
            if data == "access_list":
                await query.answer()
                await self.users_command(update, context)
                return

            elif data == "access_add":
                await query.answer()
                await query.message.reply_text(
                    "➕ <b>Добавление пользователя</b>\n\n"
                    "Отправьте команду:\n"
                    "<code>/add_user @username</code>\n"
                    "или\n"
                    "<code>/add_user 123456789</code>\n\n"
                    "💡 <i>Или ответьте на сообщение пользователя с командой /add_user</i>",
                    parse_mode='HTML'
                )
                return

            elif data == "access_remove":
                await query.answer()
                await query.message.reply_text(
                    "➖ <b>Удаление пользователя</b>\n\n"
                    "Отправьте команду:\n"
                    "<code>/remove_user @username</code>\n"
                    "или\n"
                    "<code>/remove_user 123456789</code>\n\n"
                    "💡 <i>Нельзя удалить администратора</i>",
                    parse_mode='HTML'
                )
                return

            elif data == "access_refresh":
                await self.update_access_message(query)
                await query.answer("✅ Список обновлен")

            elif data == "access_stats":
                stats_text = (
                    f"📊 <b>Статистика доступа</b>\n\n"
                    f"👑 <b>Администраторов:</b> 1\n"
                    f"👥 <b>Пользователей с доступом:</b> {len(self.allowed_users)}\n"
                    f"🔓 <b>Всего учетных записей:</b> {len(self.allowed_users)}\n\n"
                    f"💡 <b>Команды управления:</b>\n"
                    f"/access - панель управления\n"
                    f"/users - список пользователей\n"
                    f"/add_user - добавить пользователя\n"
                    f"/remove_user - удалить пользователя"
                )
                await query.answer()
                await query.message.reply_text(stats_text, parse_mode='HTML')
                return

        except BadRequest as e:
            if "not modified" in str(e).lower():
                await query.answer()
            else:
                logger.error(f"Ошибка BadRequest в handle_access: {e}")
                await query.answer("❌ Ошибка")
        except Exception as e:
            logger.error(f"Ошибка обработки доступа: {e}")
            await query.answer("❌ Ошибка")

    async def update_access_message(self, query):
        """Обновляет сообщение управления доступом"""
        keyboard = [
            [InlineKeyboardButton("👥 Список пользователей", callback_data="access_list")],
            [InlineKeyboardButton("➕ Добавить пользователя", callback_data="access_add")],
            [InlineKeyboardButton("➖ Удалить пользователя", callback_data="access_remove")],
            [InlineKeyboardButton("🔄 Обновить список", callback_data="access_refresh")],
            [InlineKeyboardButton("📊 Статистика доступа", callback_data="access_stats")]
        ]

        text = (
            "🔐 <b>Управление доступом к боту</b>\n\n"
            f"👑 <b>Администратор:</b> {ADMIN_USER_ID}\n"
            f"👥 <b>Пользователей с доступом:</b> {len(self.allowed_users)}\n\n"
            f"💡 <i>Используйте кнопки для управления доступом</i>"
        )

        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except BadRequest as e:
            if "not modified" in str(e).lower():
                pass
            else:
                raise

    # ========== КОМАНДЫ МУТА ==========

    async def mute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мут пользователя на указанное время"""
        if not await self.check_access(update):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/mute @username</code> - замутить на время по умолчанию\n"
                "<code>/mute @username 10m</code> - замутить на 10 минут\n"
                "<code>/mute 123456789</code> - замутить по ID\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /mute</i>",
                parse_mode='HTML'
            )
            return

        # Получаем username/id и время
        target = context.args[0]
        duration_str = context.args[1] if len(context.args) > 1 else "10m"

        # Парсим время
        duration = await self.parse_duration(duration_str)
        if not duration:
            await update.message.reply_text("❌ Неверный формат времени. Используйте: 10m, 1h, 1d, 1w")
            return

        try:
            # Ищем пользователя
            user_id, user_name = await self.find_user_in_chat(update.effective_chat.id, target, context)

            if not user_id:
                await update.message.reply_text(
                    f"❌ <b>Пользователь '{target}' не найден</b>\n\n"
                    f"💡 <i>Проверьте:\n"
                    f"• Правильность написания username\n"
                    f"• Что пользователь есть в этом чате\n"
                    f"• Что ID пользователя верный</i>\n\n"
                    f"🔍 <b>Совет:</b> Используйте команду /id чтобы узнать ID пользователя",
                    parse_mode='HTML'
                )
                return

            # Проверяем, не пытаемся ли замутить бота или администратора
            if user_id == context.bot.id:
                await update.message.reply_text("❌ Не могу замутить самого себя!")
                return

            # Проверяем, является ли пользователь администратором
            try:
                chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                if chat_member.status in ['administrator', 'creator']:
                    await update.message.reply_text("❌ Нельзя замутить администратора!")
                    return
            except Exception as e:
                logger.error(f"Ошибка проверки прав пользователя: {e}")

            # Выполняем мут
            until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=self.get_mute_permissions(),
                until_date=until_date
            )

            await update.message.reply_text(
                f"🔇 <b>{user_name} замьючен на {self.format_duration(duration)}</b>\n\n"
                f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"🆔 ID: <code>{user_id}</code>\n\n"
                f"💡 <i>Используйте /unmute {target} для размута</i>",
                parse_mode='HTML'
            )

        except BadRequest as e:
            error_msg = str(e).lower()
            if "not enough rights" in error_msg:
                await update.message.reply_text("❌ У бота недостаточно прав для ограничения пользователей")
            elif "user is an administrator" in error_msg:
                await update.message.reply_text("❌ Нельзя замутить администратора")
            elif "user not found" in error_msg:
                await update.message.reply_text(f"❌ Пользователь '{target}' не найден в этом чате")
            else:
                await update.message.reply_text(f"❌ Ошибка мута: {e}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка мута: {e}")

    async def unmute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Размут пользователя"""
        if not await self.check_access(update):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/unmute @username</code>\n"
                "<code>/unmute 123456789</code> - размутить по ID\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /unmute</i>",
                parse_mode='HTML'
            )
            return

        target = context.args[0]

        try:
            # Ищем пользователя
            user_id, user_name = await self.find_user_in_chat(update.effective_chat.id, target, context)

            if not user_id:
                await update.message.reply_text(
                    f"❌ <b>Пользователь '{target}' не найден</b>\n\n"
                    f"💡 <i>Проверьте правильность введенных данных</i>",
                    parse_mode='HTML'
                )
                return

            # Выполняем размут
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=self.get_unmute_permissions()
            )

            await update.message.reply_text(
                f"🔊 <b>{user_name} размьючен</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>\n\n"
                f"💡 <i>Пользователь снова может писать сообщения</i>",
                parse_mode='HTML'
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await update.message.reply_text("❌ У бота недостаточно прав для изменения прав пользователей")
            else:
                await update.message.reply_text(f"❌ Ошибка размута: {e}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка размута: {e}")

    async def find_user_in_chat(self, chat_id, target, context):
        """Находит пользователя в чате по username, ID или имени"""
        target = target.lstrip('@')  # Убираем @ если есть

        # Сценарий 1: target - это числовой ID
        if target.isdigit():
            try:
                user_id = int(target)
                member = await context.bot.get_chat_member(chat_id, user_id)
                return user_id, member.user.full_name
            except (ValueError, BadRequest):
                pass

        # Сценарий 2: target - это username
        try:
            # Пробуем получить пользователя по username
            user = await context.bot.get_chat(f"@{target}")
            # Проверяем, что пользователь в чате
            member = await context.bot.get_chat_member(chat_id, user.id)
            return user.id, user.full_name
        except BadRequest:
            pass

        # Сценарий 3: Ищем среди администраторов чата по имени
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            for admin in admins:
                user = admin.user

                # Точное совпадение имени
                if user.full_name.lower() == target.lower():
                    return user.id, user.full_name

                # Частичное совпадение имени
                if target.lower() in user.full_name.lower():
                    return user.id, user.full_name

                # Совпадение username (без @)
                if user.username and user.username.lower() == target.lower():
                    return user.id, user.full_name
        except Exception as e:
            logger.error(f"Ошибка поиска среди администраторов: {e}")

        return None, None

    async def find_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для поиска пользователя (отладка)"""
        if not await self.check_admin_access(update):
            return

        if not context.args:
            await update.message.reply_text("❌ Укажите username или ID пользователя")
            return

        target = context.args[0]

        try:
            user_id, user_name = await self.find_user_in_chat(update.effective_chat.id, target, context)

            if user_id:
                await update.message.reply_text(
                    f"✅ <b>Пользователь найден:</b>\n\n"
                    f"👤 <b>Имя:</b> {user_name}\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                    f"🔍 <b>Запрос:</b> {target}",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    f"❌ <b>Пользователь '{target}' не найден</b>\n\n"
                    f"💡 <i>Попробуйте:\n"
                    f"• Указать точный username (без @)\n"
                    f"• Использовать числовой ID\n"
                    f"• Убедиться, что пользователь в чате</i>",
                    parse_mode='HTML'
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка поиска: {e}")

    async def mute_list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список замьюченных пользователей"""
        if not await self.check_access(update):
            return

        try:
            chat_id = update.effective_chat.id
            muted_users = []

            # Используем get_chat_administrators вместо get_chat_members
            members = await context.bot.get_chat_administrators(chat_id)
            for member in members:
                user = member.user

                # Получаем полную информацию о пользователе
                try:
                    chat_member = await context.bot.get_chat_member(chat_id, user.id)

                    if chat_member.status in ['restricted', 'kicked']:
                        permissions = chat_member.permissions

                        if not permissions.can_send_messages:
                            user_info = f"👤 {user.full_name}"
                            if user.username:
                                user_info += f" (@{user.username})"
                            user_info += f" | ID: <code>{user.id}</code>"

                            if chat_member.until_date:
                                time_left = chat_member.until_date - datetime.now(timezone.utc)
                                if time_left.total_seconds() > 0:
                                    user_info += f" | ⏰ {self.format_duration(int(time_left.total_seconds()))}"

                            muted_users.append(user_info)
                except Exception as e:
                    continue

            if muted_users:
                text = "🔇 <b>Замьюченные пользователи:</b>\n\n" + "\n".join(muted_users)
            else:
                text = "✅ <b>Нет замьюченных пользователей</b>"

            await update.message.reply_text(text, parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка получения списка: {e}")

    async def mute_settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки автоматического мута"""
        if not await self.check_admin_access(update):
            return

        keyboard = [
            [
                InlineKeyboardButton("✅ Включить авто-мут", callback_data="mute_enable"),
                InlineKeyboardButton("❌ Выключить авто-мут", callback_data="mute_disable")
            ],
            [
                InlineKeyboardButton("⏰ 5 минут", callback_data="mute_duration_300"),
                InlineKeyboardButton("⏰ 15 минут", callback_data="mute_duration_900"),
                InlineKeyboardButton("⏰ 1 час", callback_data="mute_duration_3600")
            ],
            [
                InlineKeyboardButton("⏰ 1 день", callback_data="mute_duration_86400"),
                InlineKeyboardButton("⏰ 1 неделя", callback_data="mute_duration_604800")
            ],
            [
                InlineKeyboardButton("📋 Помощь по муту", callback_data="mute_help"),
                InlineKeyboardButton("👥 Список мутов", callback_data="mute_list")
            ]
        ]

        status = "✅ ВКЛЮЧЕН" if self.mute_settings['enabled'] else "❌ ВЫКЛЮЧЕН"
        duration = self.format_duration(self.mute_settings['duration'])

        await update.message.reply_text(
            f"⚙️ <b>Настройки автоматического мута</b>\n\n"
            f"📊 <b>Статус:</b> {status}\n"
            f"⏰ <b>Длительность по умолчанию:</b> {duration}\n"
            f"🔗 <b>Мут по ответу:</b> {'✅' if self.mute_settings['reply_to_mute'] else '❌'}\n\n"
            f"💡 <i>Чтобы замьютить пользователя, просто ответьте на его сообщение командой /mute</i>\n\n"
            f"🔧 <i>Команды: /mute @user 1h • /unmute @user • /mutelist • /mute_settings</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def mute_enable_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Включить авто-мут"""
        if not await self.check_admin_access(update):
            return

        self.mute_settings['enabled'] = True
        self.save_data()
        await update.message.reply_text(
            "✅ <b>Автоматический мут включен</b>\n\n"
            "💡 <i>Теперь можно мутить пользователей через ответ на их сообщения</i>",
            parse_mode='HTML'
        )

    async def mute_disable_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выключить авто-мут"""
        if not await self.check_admin_access(update):
            return

        self.mute_settings['enabled'] = False
        self.save_data()
        await update.message.reply_text(
            "❌ <b>Автоматический мут выключен</b>\n\n"
            "💡 <i>Мут через ответ на сообщения больше не работает</i>",
            parse_mode='HTML'
        )

    async def handle_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка настроек мута"""
        query = update.callback_query
        user = query.from_user

        if not await self.is_admin(user.id):
            await query.answer("🚫 Нет прав!", show_alert=True)
            return

        data = query.data

        try:
            if data == "mute_enable":
                self.mute_settings['enabled'] = True
                await query.answer("✅ Авто-мут включен")
                await self.update_mute_settings_message(query)

            elif data == "mute_disable":
                self.mute_settings['enabled'] = False
                await query.answer("❌ Авто-мут выключен")
                await self.update_mute_settings_message(query)

            elif data.startswith("mute_duration_"):
                duration = int(data.split('_')[2])
                self.mute_settings['duration'] = duration
                await query.answer(f"⏰ Длительность установлена: {self.format_duration(duration)}")
                await self.update_mute_settings_message(query)

            elif data == "mute_help":
                await query.answer()
                await query.message.reply_text(
                    "📋 <b>Помощь по командам мута:</b>\n\n"
                    "🔇 <b>Основные команды:</b>\n"
                    "<code>/mute @username 10m</code> - мут на 10 минут\n"
                    "<code>/mute @username 1h</code> - мут на 1 час\n"
                    "<code>/mute @username 1d</code> - мут на 1 день\n"
                    "<code>/mute @username 1w</code> - мут на 1 неделю\n"
                    "<code>/unmute @username</code> - размутить\n"
                    "<code>/mutelist</code> - список мутов\n\n"
                    "⚡ <b>Быстрый мут:</b>\n"
                    "Ответьте на сообщение командой <code>/mute</code>\n"
                    "Ответьте на сообщение командой <code>/unmute</code>\n\n"
                    "⚙️ <b>Настройки:</b>\n"
                    "<code>/mute_settings</code> - панель управления\n"
                    "<code>/mute_enable</code> - включить авто-мут\n"
                    "<code>/mute_disable</code> - выключить авто-мут\n\n"
                    "🔧 <b>Проверка прав:</b>\n"
                    "<code>/fix_rights</code> - проверить права бота",
                    parse_mode='HTML'
                )
                return

            elif data == "mute_list":
                await query.answer()
                await self.mute_list_command(update, context)
                return

            self.save_data()

        except BadRequest as e:
            if "not modified" in str(e).lower():
                await query.answer()
            else:
                logger.error(f"Ошибка BadRequest в handle_mute: {e}")
                await query.answer("❌ Ошибка")
        except Exception as e:
            logger.error(f"Ошибка обработки мута: {e}")
            await query.answer("❌ Ошибка")

    async def update_mute_settings_message(self, query):
        """Обновляет сообщение с настройками мута"""
        status = "✅ ВКЛЮЧЕН" if self.mute_settings['enabled'] else "❌ ВЫКЛЮЧЕН"
        duration = self.format_duration(self.mute_settings['duration'])

        keyboard = [
            [
                InlineKeyboardButton("✅ Включить авто-мут", callback_data="mute_enable"),
                InlineKeyboardButton("❌ Выключить авто-мут", callback_data="mute_disable")
            ],
            [
                InlineKeyboardButton("⏰ 5 минут", callback_data="mute_duration_300"),
                InlineKeyboardButton("⏰ 15 минут", callback_data="mute_duration_900"),
                InlineKeyboardButton("⏰ 1 час", callback_data="mute_duration_3600")
            ],
            [
                InlineKeyboardButton("⏰ 1 день", callback_data="mute_duration_86400"),
                InlineKeyboardButton("⏰ 1 неделя", callback_data="mute_duration_604800")
            ],
            [
                InlineKeyboardButton("📋 Помощь по муту", callback_data="mute_help"),
                InlineKeyboardButton("👥 Список мутов", callback_data="mute_list")
            ]
        ]

        text = (
            f"⚙️ <b>Настройки автоматического мута</b>\n\n"
            f"📊 <b>Статус:</b> {status}\n"
            f"⏰ <b>Длительность по умолчанию:</b> {duration}\n"
            f"🔗 <b>Мут по ответу:</b> {'✅' if self.mute_settings['reply_to_mute'] else '❌'}\n\n"
            f"💡 <i>Чтобы замьютить пользователя, просто ответьте на его сообщение командой /mute</i>\n\n"
            f"🔧 <i>Команды: /mute @user 1h • /unmute @user • /mutelist • /mute_settings</i>"
        )

        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except BadRequest as e:
            if "not modified" in str(e).lower():
                # Сообщение не изменилось - это нормально
                pass
            else:
                raise

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ МУТА ==========

    async def parse_duration(self, duration_str):
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
                # Если просто число, считаем минутами
                return int(duration_str) * 60
        except:
            return None

    def format_duration(self, seconds):
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

    def get_mute_permissions(self):
        """Возвращает права для мута"""
        return ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )

    def get_unmute_permissions(self):
        """Возвращает стандартные права"""
        return ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )

    # ========== ОСНОВНЫЕ КОМАНДЫ ==========

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь по всем командам"""
        if not await self.check_access(update):
            return

        help_text = (
            "🤖 <b>Помощь по командам бота</b>\n\n"

            "📅 <b>Посещаемость:</b>\n"
            "<code>/start</code> - активация бота (админ)\n"
            "<code>/attendance</code> - текущее голосование\n"
            "<code>/results</code> - результаты голосования\n"
            "<code>/voters</code> - кто как голосовал\n"
            "<code>/admin</code> - панель управления (админ)\n"
            "<code>/status</code> - статус бота\n\n"

            "🔐 <b>Управление доступом (админ):</b>\n"
            "<code>/access</code> - панель управления доступом\n"
            "<code>/users</code> - список пользователей\n"
            "<code>/add_user @user</code> - добавить пользователя\n"
            "<code>/remove_user @user</code> - удалить пользователя\n\n"

            "🔇 <b>Модерация:</b>\n"
            "<code>/mute @user 1h</code> - мут пользователя\n"
            "<code>/unmute @user</code> - размутить\n"
            "<code>/mutelist</code> - список мутов\n"
            "<code>/mute_settings</code> - настройки мута (админ)\n"
            "<code>/fix_rights</code> - проверить права (админ)\n\n"

            "🎯 <b>Другие команды:</b>\n"
            "<code>/id</code> - узнать свой ID\n"
            "<code>/fuck</code> - отправить нахуй\n"
            "<code>/help</code> - эта справка\n"
            "<code>/find</code> - найти пользователя (админ)\n\n"

            "⚡ <b>Быстрые действия:</b>\n"
            "• Ответьте <code>/mute</code> на сообщение для мута\n"
            "• Ответьте <code>/unmute</code> на сообщение для размута\n"
            "• Нажмите кнопку в закрепленном сообщении для голосования\n\n"

            "💡 <i>Бот автоматически создает голосования каждый понедельник в 19:00</i>"
        )

        await update.message.reply_text(help_text, parse_mode='HTML')

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_admin_access(update):
            return

        self.chat_id = update.effective_chat.id

        await update.message.reply_text(
            "✅ <b>Бот для учета посещаемости активирован!</b>\n\n"
            "📅 <b>Каждый понедельник в 19:00</b> я буду создавать новое голосование.\n\n"
            "⚡ <b>Основные команды:</b>\n"
            "<code>/attendance</code> - голосование\n"
            "<code>/results</code> - результаты\n"
            "<code>/mute @user 1h</code> - мут\n"
            "<code>/mutelist</code> - список мутов\n"
            "<code>/mute_settings</code> - настройки\n"
            "<code>/access</code> - управление доступом\n\n"
            "💡 <i>Используйте /help для полного списка команд</i>",
            parse_mode='HTML'
        )
        self.save_data()

        await self.create_monday_poll()

    async def attendance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_access(update):
            return

        if not self.current_poll_id:
            await update.message.reply_text(
                "❌ Сейчас нет активного голосования\n\n"
                "💡 <i>Новое создастся в понедельник в 19:00 или через /admin</i>",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "✅ Голосование уже активно!\n\n"
                "💡 <i>Используйте кнопки в закрепленном сообщении</i>",
                parse_mode='HTML'
            )

    async def results_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_access(update):
            return

        if not self.current_poll_id:
            await update.message.reply_text("❌ Сейчас нет активного голосования")
            return

        results_text = await self.get_results_text()
        await update.message.reply_text(results_text, parse_mode='HTML')

    async def voters_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_access(update):
            return

        if not self.current_poll_id:
            await update.message.reply_text("❌ Сейчас нет активного голосования")
            return

        voters_text = await self.get_voters_text()
        await update.message.reply_text(voters_text, parse_mode='HTML')

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"📅 Следующий понедельник: {self.get_next_monday_date()}\n"
            f"👥 Проголосовало: {len(self.votes)} человек\n\n"
            f"💡 <i>Используйте кнопки для управления</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_access(update):
            return

        status_text = (
            "🤖 <b>Статус бота:</b>\n\n"
            f"✅ <b>Бот активен</b>\n"
            f"📅 <b>Расписание:</b> Каждый понедельник в 19:00\n"
            f"🕐 <b>Следующий понедельник:</b> {self.get_next_monday_date()}\n"
            f"👥 <b>Текущие голоса:</b> {len(self.votes)}\n"
            f"🔇 <b>Авто-мут:</b> {'✅ ВКЛ' if self.mute_settings['enabled'] else '❌ ВЫКЛ'}\n"
            f"👤 <b>Пользователей с доступом:</b> {len(self.allowed_users)}\n\n"
            f"💡 <i>Бот работает стабильно</i> 🚀"
        )
        await update.message.reply_text(status_text, parse_mode='HTML')

    async def id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_access(update):
            return

        user = update.effective_user
        await update.message.reply_text(
            f"🆔 <b>Ваш ID:</b> <code>{user.id}</code>\n"
            f"👤 <b>Имя:</b> {user.full_name}\n"
            f"📛 <b>Username:</b> @{user.username if user.username else 'нет'}\n\n"
            f"💡 <i>Этот ID нужен для настройки прав доступа</i>",
            parse_mode='HTML'
        )

    async def fuck_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_access(update):
            return

        user = update.effective_user
        await update.message.reply_text(
            f"🖕 {user.full_name}, пошёл нахуй! Не командуй тут, уёбок!\n\n"
            f"💡 <i>Используйте нормальные команды, а не хамите</i>"
        )

    async def fix_rights_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_admin_access(update):
            return

        chat_id = update.effective_chat.id

        try:
            chat = await self.application.bot.get_chat(chat_id)
            bot_member = await self.application.bot.get_chat_member(chat_id, self.application.bot.id)

            rights_info = (
                "🔧 <b>Проверка прав бота:</b>\n\n"
                f"💬 <b>Чат:</b> {chat.title}\n"
                f"🆔 <b>ID чата:</b> <code>{chat_id}</code>\n\n"
                f"🤖 <b>Права бота:</b>\n"
            )

            if bot_member.status == 'administrator':
                rights_info += "✅ <b>Статус:</b> Администратор\n"

                if bot_member.can_restrict_members:
                    rights_info += "✅ <b>Может ограничивать пользователей</b>\n"
                else:
                    rights_info += "❌ <b>НЕ может ограничивать пользователей</b>\n"

                if bot_member.can_pin_messages:
                    rights_info += "✅ <b>Может закреплять сообщения</b>\n"
                else:
                    rights_info += "❌ <b>НЕ может закреплять сообщения</b>\n"

            else:
                rights_info += "❌ <b>Статус:</b> НЕ администратор\n"

            rights_info += "\n⚡ <b>Для полной работы нужно:</b>\n"
            rights_info += "• Права администратора\n"
            rights_info += "• Право 'Ограничивать пользователей'\n"
            rights_info += "• Право 'Закреплять сообщения'\n\n"
            rights_info += "💡 <i>Обратитесь к создателю чата для выдачи прав</i>"

            await update.message.reply_text(rights_info, parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>Ошибка проверки прав:</b>\n\n"
                f"<code>{e}</code>\n\n"
                f"💡 <i>Убедитесь что бот добавлен в группу и является администратором</i>",
                parse_mode='HTML'
            )

    # ========== СИСТЕМНЫЕ МЕТОДЫ ==========

    async def create_monday_poll(self):
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
                "💡 <i>Отметьтесь, пожалуйста, чтобы все были в курсе</i>"
            )

            keyboard = await self.create_voting_keyboard()

            message = await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )

            try:
                if self.last_poll_message_id:
                    try:
                        await self.application.bot.unpin_chat_message(
                            chat_id=self.chat_id,
                            message_id=self.last_poll_message_id
                        )
                    except:
                        pass

                await self.application.bot.pin_chat_message(
                    chat_id=self.chat_id,
                    message_id=message.message_id,
                    disable_notification=True
                )

                self.last_poll_message_id = message.message_id
                logger.info("✅ Сообщение закреплено")

            except Exception as e:
                logger.warning(f"❌ Не удалось закрепить: {e}")
                await self.application.bot.send_message(
                    chat_id=self.chat_id,
                    text="⚠️ <b>Не могу закрепить сообщение!</b>\n\n"
                         "💡 <i>Дайте боту права 'Закреплять сообщения'\n"
                         "Используйте /fix_rights для проверки</i>",
                    parse_mode='HTML'
                )

            self.save_data()
            logger.info(f"✅ Новое голосование создано")

        except Exception as e:
            logger.error(f"❌ Ошибка создания голосования: {e}")

    async def create_voting_keyboard(self):
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

        if await self.is_admin(ADMIN_USER_ID):
            keyboard.append([InlineKeyboardButton("📊 Посмотреть результаты", callback_data="admin_full_stats")])

        return InlineKeyboardMarkup(keyboard)

    async def get_results_text(self):
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
        text += f"\n\n💡 <i>Используйте /voters чтобы посмотреть кто как голосовал</i>"
        return text

    async def get_voters_text(self):
        if not self.votes:
            return "Пока никто не отметился"

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

        text += "💡 <i>Голосование обновляется в реальном времени</i>"
        return text

    async def get_full_stats_text(self):
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
                for voter in voters[:10]:
                    text += f"   👤 {voter}\n"
                if len(voters) > 10:
                    text += f"   ... и еще {len(voters) - 10}\n"
            text += "\n"

        text += "💡 <i>Используйте /admin для управления голосованием</i>"
        return text

    async def handle_vote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = query.from_user

        try:
            message_time = query.message.date.replace(tzinfo=timezone.utc)
            current_time = datetime.now(timezone.utc)
            time_diff = (current_time - message_time).seconds

            if time_diff > 600:
                await query.answer("❌ Голосование устарело", show_alert=True)
                return

            option = query.data.split('_')[1]

            self.votes[str(user.id)] = {
                'option': option,
                'name': user.full_name,
                'timestamp': datetime.now().isoformat(),
                'username': user.username
            }

            keyboard = await self.create_voting_keyboard()

            try:
                await query.edit_message_reply_markup(reply_markup=keyboard)
            except BadRequest as e:
                if "not modified" in str(e).lower():
                    # Сообщение не изменилось - это нормально
                    pass
                else:
                    raise

            option_names = {'1': 'К 1', '2': 'Ко 2', '3': 'Не прихожу'}
            await query.answer(f"✅ {option_names[option]}")
            self.save_data()

            logger.info(f"Пользователь {user.full_name} проголосовал")

        except BadRequest as e:
            if "not modified" in str(e).lower():
                await query.answer()
            else:
                logger.error(f"Ошибка BadRequest: {e}")
                await query.answer("❌ Ошибка, попробуйте снова")
        except Exception as e:
            logger.error(f"Ошибка голосования: {e}")
            await query.answer("❌ Ошибка, попробуйте снова")

    async def handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = query.from_user

        if not await self.is_admin(user.id):
            try:
                await query.answer("🚫 Ты кто такой? Пошёл нахуй!", show_alert=True)
            except:
                pass
            return

        try:
            data = query.data

            if data == "admin_full_stats":
                stats_text = await self.get_full_stats_text()
                await query.message.reply_text(stats_text, parse_mode='HTML')

            elif data == "admin_refresh":
                keyboard = await self.create_voting_keyboard()
                try:
                    await query.edit_message_reply_markup(reply_markup=keyboard)
                except BadRequest as e:
                    if "not modified" in str(e).lower():
                        pass
                    else:
                        raise
                await query.answer("✅ Голосование обновлено!")

            elif data == "admin_clear":
                self.votes = {}
                keyboard = await self.create_voting_keyboard()
                try:
                    await query.edit_message_reply_markup(reply_markup=keyboard)
                except BadRequest as e:
                    if "not modified" in str(e).lower():
                        pass
                    else:
                        raise
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

    async def handle_reply_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ответов на сообщения для мута"""
        if not self.mute_settings['enabled']:
            return

        if not await self.is_admin(update.effective_user.id):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_mute = replied_message.from_user

        # Проверяем, не пытаемся ли замутить бота или администратора
        if user_to_mute.id == context.bot.id:
            await update.message.reply_text("❌ Не могу замутить самого себя!")
            return

        try:
            # Проверяем, является ли пользователь администратором
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_to_mute.id)
            if chat_member.status in ['administrator', 'creator']:
                await update.message.reply_text("❌ Нельзя замутить администратора!")
                return
        except:
            pass

        # Парсим время из команды
        command_parts = update.message.text.split()
        duration_str = command_parts[1] if len(command_parts) > 1 else None

        duration = self.mute_settings['duration']
        if duration_str:
            parsed_duration = await self.parse_duration(duration_str)
            if parsed_duration:
                duration = parsed_duration

        try:
            until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_to_mute.id,
                permissions=self.get_mute_permissions(),
                until_date=until_date
            )

            await update.message.reply_text(
                f"🔇 <b>{user_to_mute.full_name} замьючен на {self.format_duration(duration)}</b>\n\n"
                f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"🆔 ID: <code>{user_to_mute.id}</code>\n\n"
                f"💡 <i>Используйте /unmute @{user_to_mute.username or user_to_mute.id} для размута</i>",
                parse_mode='HTML'
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await update.message.reply_text("❌ У бота недостаточно прав для ограничения пользователей")
            elif "user is an administrator" in str(e).lower():
                await update.message.reply_text("❌ Нельзя замутить администратора")
            else:
                await update.message.reply_text(f"❌ Ошибка мута: {e}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка мута: {e}")

    async def handle_reply_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ответов на сообщения для размута"""
        if not await self.is_admin(update.effective_user.id):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_unmute = replied_message.from_user

        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_to_unmute.id,
                permissions=self.get_unmute_permissions()
            )

            await update.message.reply_text(
                f"🔊 <b>{user_to_unmute.full_name} размьючен</b>\n\n"
                f"🆔 ID: <code>{user_to_unmute.id}</code>\n\n"
                f"💡 <i>Пользователь снова может писать сообщения</i>",
                parse_mode='HTML'
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await update.message.reply_text("❌ У бота недостаточно прав для изменения прав пользователей")
            else:
                await update.message.reply_text(f"❌ Ошибка размута: {e}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка размута: {e}")

    async def check_schedule(self):
        while True:
            try:
                now = datetime.now()
                if now.weekday() == 0 and now.hour == 19 and now.minute == 0:
                    logger.info("Создаем новое голосование по расписанию!")
                    await self.create_monday_poll()
                    await asyncio.sleep(61)
                else:
                    await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                await asyncio.sleep(60)

    async def run(self):
        self.load_data()

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("🤖 Бот запущен!")

        if not self.current_poll_id and self.chat_id:
            logger.info("Создаем первое голосование...")
            await self.create_monday_poll()

        await self.check_schedule()


if __name__ == "__main__":
    print("🚀 Запуск бота для учета посещаемости...")
    print(f"📅 Расписание: каждый понедельник в 19:00")
    print("🤖 Токен бота: 8455558290:AAHDiNfqtG7LMOWor9rHhpwtCVv-JHmt-7c")
    print(f"👑 Админ ID: {ADMIN_USER_ID}")
    print("💡 Используйте /help для списка команд")

    bot = MondayAttendanceBot(BOT_TOKEN)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")