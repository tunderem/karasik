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


class SimpleAttendanceBot:
    def __init__(self, token):
        self.token = token
        # Основная структура данных с разделением по chat_id
        self.chat_data = {}
        self.application = Application.builder().token(token).build()

        # Обработчики команд
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("attendance", self.attendance_command))
        self.application.add_handler(CommandHandler("results", self.results_command))
        self.application.add_handler(CommandHandler("voters", self.voters_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("id", self.id_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("fix_rights", self.fix_rights_command))
        self.application.add_handler(CommandHandler("get_id", self.get_id_command))

        # Команды для получения ID
        self.application.add_handler(CommandHandler("all_ids", self.all_ids_command))
        self.application.add_handler(CommandHandler("chat_info", self.chat_info_command))

        # Команды управления администраторами
        self.application.add_handler(CommandHandler("admins", self.admins_command))
        self.application.add_handler(CommandHandler("add_admin", self.add_admin_command))
        self.application.add_handler(CommandHandler("remove_admin", self.remove_admin_command))

        # Команды мута
        self.application.add_handler(CommandHandler("mute", self.mute_command))
        self.application.add_handler(CommandHandler("unmute", self.unmute_command))
        self.application.add_handler(CommandHandler("mutelist", self.mute_list_command))

        # Обработчики callback'ов
        self.application.add_handler(CallbackQueryHandler(self.handle_vote, pattern="^vote_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_admin, pattern="^admin_"))

        # Обработчик ответов на сообщения для мута
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/mute\b'), self.handle_reply_mute))
        self.application.add_handler(
            MessageHandler(filters.REPLY & filters.TEXT & filters.Regex(r'^/unmute\b'), self.handle_reply_unmute))

    def get_chat_data(self, chat_id):
        """Получает данные чата, создает если нет"""
        if chat_id not in self.chat_data:
            self.chat_data[chat_id] = {
                'last_poll_message_id': None,
                'current_poll_id': None,
                'votes': {},
                'admin_users': [MAIN_ADMIN_ID],  # Главный админ всегда в списке
                'last_updated': datetime.now().isoformat()
            }
        return self.chat_data[chat_id]

    def save_data(self):
        """Сохраняем данные"""
        try:
            data = {
                'chat_data': self.chat_data,
                'last_updated': datetime.now().isoformat()
            }
            with open('attendance_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, default=str, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")

    def load_data(self):
        """Загружаем данные"""
        try:
            if os.path.exists('attendance_data.json'):
                with open('attendance_data.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # Поддержка старого формата данных
                    if 'chat_data' in data:
                        self.chat_data = data['chat_data']
                    else:
                        # Конвертация старого формата в новый
                        old_chat_id = data.get('chat_id')
                        if old_chat_id:
                            self.chat_data[old_chat_id] = {
                                'last_poll_message_id': data.get('last_poll_message_id'),
                                'current_poll_id': data.get('current_poll_id'),
                                'votes': data.get('votes', {}),
                                'admin_users': data.get('admin_users', [MAIN_ADMIN_ID])
                            }

                    # Гарантируем, что главный админ всегда в списке для каждого чата
                    for chat_id in self.chat_data:
                        if MAIN_ADMIN_ID not in self.chat_data[chat_id]['admin_users']:
                            self.chat_data[chat_id]['admin_users'].append(MAIN_ADMIN_ID)

        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")
            self.chat_data = {}

    def get_next_monday_date(self):
        """Получаем дату следующего понедельника"""
        today = datetime.now()
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_monday = today + timedelta(days=days_ahead)
        return next_monday.strftime('%d.%m.%Y')

    async def is_admin(self, chat_id, user_id):
        """Проверяет, является ли пользователь администратором в конкретном чате"""
        chat_data = self.get_chat_data(chat_id)
        return user_id in chat_data['admin_users']

    async def check_admin_access(self, update: Update):
        """Проверяет права администратора в текущем чате"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if not await self.is_admin(chat_id, user_id):
            await update.message.reply_text("🚫 У вас нет прав администратора в этом чате!")
            return False
        return True

    # ========== КОМАНДЫ УПРАВЛЕНИЯ АДМИНАМИ ==========

    async def admins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список администраторов текущего чата"""
        if not await self.check_admin_access(update):
            return

        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)
        admin_users = chat_data['admin_users']

        if not admin_users:
            await update.message.reply_text("📝 <b>Список администраторов пуст</b>", parse_mode='HTML')
            return

        admin_list = []
        for i, admin_id in enumerate(admin_users, 1):
            try:
                admin_info = f"{i}. 🆔 <code>{admin_id}</code>"

                # Пробуем получить информацию о пользователе
                try:
                    user = await context.bot.get_chat(admin_id)
                    admin_info = f"{i}. 👤 {user.full_name}"
                    if user.username:
                        admin_info += f" (@{user.username})"
                    admin_info += f" | 🆔 <code>{admin_id}</code>"
                except:
                    pass

                # Помечаем главного администратора
                if admin_id == MAIN_ADMIN_ID:
                    admin_info += " 👑"

                admin_list.append(admin_info)
            except Exception as e:
                admin_list.append(f"{i}. 🆔 <code>{admin_id}</code>")

        text = f"👑 <b>Администраторы чата {chat_id}:</b>\n\n" + "\n".join(admin_list)
        text += f"\n\n📊 <b>Всего:</b> {len(admin_users)} администраторов"

        await update.message.reply_text(text, parse_mode='HTML')

    async def add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавляет администратора в текущий чат"""
        if not await self.check_admin_access(update):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/add_admin 123456789</code> - добавить по ID\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /add_admin</i>",
                parse_mode='HTML'
            )
            return

        try:
            chat_id = update.effective_chat.id
            chat_data = self.get_chat_data(chat_id)

            # Получаем ID пользователя
            if update.message.reply_to_message:
                # Из ответа на сообщение
                user_id = update.message.reply_to_message.from_user.id
                user_name = update.message.reply_to_message.from_user.full_name
            else:
                # Из аргументов команды
                user_id = int(context.args[0])
                # Пробуем получить имя пользователя
                try:
                    user = await context.bot.get_chat(user_id)
                    user_name = user.full_name
                except:
                    user_name = f"Пользователь ({user_id})"

            # Проверяем, не добавлен ли уже
            if user_id in chat_data['admin_users']:
                await update.message.reply_text(
                    f"ℹ️ <b>Пользователь уже является администратором этого чата</b>\n\n"
                    f"👤 {user_name}\n"
                    f"🆔 <code>{user_id}</code>",
                    parse_mode='HTML'
                )
                return

            # Добавляем администратора
            chat_data['admin_users'].append(user_id)
            self.save_data()

            await update.message.reply_text(
                f"✅ <b>Новый администратор добавлен в этот чат</b>\n\n"
                f"👤 {user_name}\n"
                f"🆔 <code>{user_id}</code>\n\n"
                f"💡 <i>Теперь пользователь может использовать команды администратора в этом чате</i>",
                parse_mode='HTML'
            )

        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Используйте числовой ID.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка добавления: {e}")

    async def remove_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаляет администратора из текущего чата"""
        if not await self.check_admin_access(update):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/remove_admin 123456789</code> - удалить по ID\n\n"
                "💡 <i>Нельзя удалить главного администратора</i>",
                parse_mode='HTML'
            )
            return

        try:
            chat_id = update.effective_chat.id
            chat_data = self.get_chat_data(chat_id)
            user_id = int(context.args[0])

            # Проверяем, не пытаемся ли удалить главного администратора
            if user_id == MAIN_ADMIN_ID:
                await update.message.reply_text("❌ Нельзя удалить главного администратора!")
                return

            # Проверяем, есть ли пользователь в списке
            if user_id not in chat_data['admin_users']:
                await update.message.reply_text("❌ Пользователь не является администратором этого чата")
                return

            # Удаляем администратора
            chat_data['admin_users'].remove(user_id)
            self.save_data()

            # Пробуем получить имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await update.message.reply_text(
                f"✅ <b>Администратор удален из этого чата</b>\n\n"
                f"👤 {user_name}\n"
                f"🆔 <code>{user_id}</code>\n\n"
                f"💡 <i>Пользователь больше не может использовать команды администратора в этом чате</i>",
                parse_mode='HTML'
            )

        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Используйте числовой ID.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка удаления: {e}")

    # ========== КОМАНДЫ ДЛЯ ПОЛУЧЕНИЯ ID ==========

    async def id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает ID пользователя"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        is_admin = await self.is_admin(chat_id, user.id)

        admin_status = "👑 Администратор" if is_admin else "👤 Пользователь"

        await update.message.reply_text(
            f"👤 <b>Ваша информация:</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📛 <b>Имя:</b> {user.full_name}\n"
            f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}\n"
            f"💬 <b>ID чата:</b> <code>{chat_id}</code>\n"
            f"🎯 <b>Статус в этом чате:</b> {admin_status}",
            parse_mode='HTML'
        )

    async def get_id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получает ID пользователя по ответу на сообщение"""
        if not context.args and not update.message.reply_to_message:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/get_id</code> - в ответ на сообщение пользователя\n"
                "<code>/get_id 123456789</code> - по ID",
                parse_mode='HTML'
            )
            return

        try:
            if update.message.reply_to_message:
                # Получаем ID из ответа на сообщение
                user = update.message.reply_to_message.from_user
                await update.message.reply_text(
                    f"👤 <b>Информация о пользователе:</b>\n\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"📛 <b>Имя:</b> {user.full_name}\n"
                    f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}",
                    parse_mode='HTML'
                )
            elif context.args:
                target = context.args[0]

                # Пробуем как ID
                if target.isdigit():
                    user_id = int(target)
                    try:
                        # Пробуем получить информацию о пользователе
                        user = await context.bot.get_chat(user_id)
                        await update.message.reply_text(
                            f"👤 <b>Информация о пользователе:</b>\n\n"
                            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                            f"📛 <b>Имя:</b> {user.full_name}\n"
                            f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}",
                            parse_mode='HTML'
                        )
                        return
                    except Exception as e:
                        await update.message.reply_text(f"❌ Пользователь с ID {target} не найден")
                        return

                await update.message.reply_text("❌ Используйте числовой ID пользователя")

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def all_ids_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает ID всех администраторов чата"""
        try:
            chat_id = update.effective_chat.id
            admins = await context.bot.get_chat_administrators(chat_id)

            if not admins:
                await update.message.reply_text("❌ Не удалось получить список администраторов")
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
            await update.message.reply_text(text, parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def chat_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает информацию о чате"""
        try:
            chat = update.effective_chat
            chat_id = chat.id
            chat_data = self.get_chat_data(chat_id)

            admin_count = len(chat_data['admin_users'])
            votes_count = len(chat_data['votes'])

            await update.message.reply_text(
                f"💬 <b>Информация о чате:</b>\n\n"
                f"📛 <b>Название:</b> {chat.title}\n"
                f"🆔 <b>ID чата:</b> <code>{chat.id}</code>\n"
                f"👥 <b>Тип:</b> {chat.type}\n"
                f"👑 <b>Админов бота:</b> {admin_count}\n"
                f"🗳️ <b>Голосов:</b> {votes_count}",
                parse_mode='HTML'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    # ========== КОМАНДЫ МУТА ==========

    async def mute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мут пользователя"""
        if not await self.check_admin_access(update):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/mute 123456789</code> - мут по ID\n"
                "<code>/mute 123456789 1h</code> - мут на 1 час\n\n"
                "💡 <i>Или ответьте на сообщение командой /mute</i>",
                parse_mode='HTML'
            )
            return

        try:
            chat_id = update.effective_chat.id
            chat_data = self.get_chat_data(chat_id)

            # Получаем ID и время
            target_id = context.args[0]
            duration_str = context.args[1] if len(context.args) > 1 else "10m"

            # Парсим время
            duration = self.parse_duration(duration_str)
            if not duration:
                await update.message.reply_text("❌ Неверный формат времени. Используйте: 10m, 1h, 1d, 1w")
                return

            user_id = int(target_id)

            # Проверяем, не пытаемся ли замутить бота или администратора
            if user_id == context.bot.id:
                await update.message.reply_text("❌ Не могу замутить самого себя!")
                return

            # Проверяем, является ли пользователь администратором
            if await self.is_admin(chat_id, user_id):
                await update.message.reply_text("❌ Нельзя замутить администратора бота!")
                return

            # Проверяем, является ли пользователь администратором чата
            try:
                chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                if chat_member.status in ['administrator', 'creator']:
                    await update.message.reply_text("❌ Нельзя замутить администратора чата!")
                    return
            except:
                pass

            # Выполняем мут
            until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )

            # Пробуем получить имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await update.message.reply_text(
                f"🔇 <b>{user_name} замьючен на {self.format_duration(duration)}</b>\n\n"
                f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"🆔 ID: <code>{user_id}</code>",
                parse_mode='HTML'
            )

        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Используйте числовой ID.")
        except BadRequest as e:
            error_msg = str(e).lower()
            if "not enough rights" in error_msg:
                await update.message.reply_text("❌ У бота недостаточно прав для ограничения пользователей")
            elif "user not found" in error_msg:
                await update.message.reply_text("❌ Пользователь не найден в этом чате")
            else:
                await update.message.reply_text(f"❌ Ошибка мута: {e}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка мута: {e}")

    async def unmute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Размут пользователя"""
        if not await self.check_admin_access(update):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ <b>Использование:</b>\n"
                "<code>/unmute 123456789</code> - размутить по ID\n\n"
                "💡 <i>Или ответьте на сообщение командой /unmute</i>",
                parse_mode='HTML'
            )
            return

        try:
            chat_id = update.effective_chat.id
            user_id = int(context.args[0])

            # Выполняем размут
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )

            # Пробуем получить имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await update.message.reply_text(
                f"🔊 <b>{user_name} размьючен</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>",
                parse_mode='HTML'
            )

        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Используйте числовой ID.")
        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await update.message.reply_text("❌ У бота недостаточно прав для изменения прав пользователей")
            else:
                await update.message.reply_text(f"❌ Ошибка размута: {e}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка размута: {e}")

    async def mute_list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список замьюченных пользователей"""
        try:
            chat_id = update.effective_chat.id
            muted_users = []

            # Получаем администраторов и проверяем их статус
            admins = await context.bot.get_chat_administrators(chat_id)
            for admin in admins:
                user = admin.user
                try:
                    chat_member = await context.bot.get_chat_member(chat_id, user.id)
                    if (chat_member.status == 'restricted' and
                            not chat_member.permissions.can_send_messages):

                        user_info = f"👤 {user.full_name}"
                        if user.username:
                            user_info += f" (@{user.username})"
                        user_info += f" | ID: <code>{user.id}</code>"

                        if chat_member.until_date:
                            time_left = chat_member.until_date - datetime.now(timezone.utc)
                            if time_left.total_seconds() > 0:
                                user_info += f" | ⏰ {self.format_duration(int(time_left.total_seconds()))}"

                        muted_users.append(user_info)
                except:
                    continue

            if muted_users:
                text = "🔇 <b>Замьюченные пользователи:</b>\n\n" + "\n".join(muted_users)
            else:
                text = "✅ <b>Нет замьюченных пользователей</b>"

            await update.message.reply_text(text, parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка получения списка: {e}")

    async def handle_reply_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мут по ответу на сообщение"""
        if not await self.check_admin_access(update):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_mute = replied_message.from_user
        chat_id = update.effective_chat.id

        # Проверяем, не пытаемся ли замутить бота или администратора
        if user_to_mute.id == context.bot.id:
            await update.message.reply_text("❌ Не могу замутить самого себя!")
            return

        if await self.is_admin(chat_id, user_to_mute.id):
            await update.message.reply_text("❌ Нельзя замутить администратора бота!")
            return

        try:
            # Проверяем, является ли пользователь администратором чата
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_to_mute.id)
            if chat_member.status in ['administrator', 'creator']:
                await update.message.reply_text("❌ Нельзя замутить администратора чата!")
                return
        except:
            pass

        # Парсим время из команды
        command_parts = update.message.text.split()
        duration_str = command_parts[1] if len(command_parts) > 1 else "10m"

        duration = self.parse_duration(duration_str) or 600  # 10 минут по умолчанию

        try:
            until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_to_mute.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )

            await update.message.reply_text(
                f"🔇 <b>{user_to_mute.full_name} замьючен на {self.format_duration(duration)}</b>\n\n"
                f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"🆔 ID: <code>{user_to_mute.id}</code>",
                parse_mode='HTML'
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await update.message.reply_text("❌ У бота недостаточно прав для ограничения пользователей")
            else:
                await update.message.reply_text(f"❌ Ошибка мута: {e}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка мута: {e}")

    async def handle_reply_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Размут по ответу на сообщение"""
        if not await self.check_admin_access(update):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_unmute = replied_message.from_user

        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_to_unmute.id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )

            await update.message.reply_text(
                f"🔊 <b>{user_to_unmute.full_name} размьючен</b>\n\n"
                f"🆔 ID: <code>{user_to_unmute.id}</code>",
                parse_mode='HTML'
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await update.message.reply_text("❌ У бота недостаточно прав для изменения прав пользователей")
            else:
                await update.message.reply_text(f"❌ Ошибка размута: {e}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка размута: {e}")

    def parse_duration(self, duration_str):
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
                return int(duration_str) * 60  # По умолчанию считаем минутами
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

    # ========== ОСНОВНЫЕ КОМАНДЫ ==========

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь по командам"""
        chat_id = update.effective_chat.id
        is_admin = await self.is_admin(chat_id, update.effective_user.id)

        help_text = (
            "🤖 <b>Помощь по командам бота</b>\n\n"

            "📅 <b>Посещаемость:</b>\n"
            "<code>/start</code> - активация бота\n"
            "<code>/attendance</code> - текущее голосование\n"
            "<code>/results</code> - результаты голосования\n"
            "<code>/voters</code> - кто как голосовал\n"
            "<code>/status</code> - статус бота\n\n"

            "🆔 <b>Получение ID:</b>\n"
            "<code>/id</code> - ваш ID\n"
            "<code>/get_id</code> - ID пользователя (в ответ на сообщение)\n"
            "<code>/all_ids</code> - ID всех администраторов чата\n"
            "<code>/chat_info</code> - информация о чате\n\n"
        )

        if is_admin:
            help_text += (
                "👑 <b>Администраторские команды:</b>\n"
                "<code>/admin</code> - панель управления\n"
                "<code>/admins</code> - список администраторов бота\n"
                "<code>/add_admin ID</code> - добавить администратора\n"
                "<code>/remove_admin ID</code> - удалить администратора\n"
                "<code>/mute ID</code> - мут пользователя\n"
                "<code>/unmute ID</code> - размутить\n"
                "<code>/mutelist</code> - список мутов\n"
                "<code>/fix_rights</code> - проверить права бота\n\n"
            )

        help_text += (
            "💡 <b>Советы:</b>\n"
            "• Используйте ID вместо username для команд\n"
            "• Для мута ответьте на сообщение командой /mute\n"
            "• Бот создает голосования каждый понедельник в 19:00\n"
            "• Каждый чат имеет отдельный список администраторов"
        )

        await update.message.reply_text(help_text, parse_mode='HTML')

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда start"""
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        # Активируем бота в чате
        await update.message.reply_text(
            f"✅ <b>Бот для учета посещаемости активирован в этом чате!</b>\n\n"
            f"📅 <b>Каждый понедельник в 19:00</b> я буду создавать новое голосование.\n\n"
            f"⚡ <b>Основные команды:</b>\n"
            f"<code>/attendance</code> - голосование\n"
            f"<code>/results</code> - результаты\n"
            f"<code>/mute ID</code> - мут пользователя\n"
            f"<code>/id</code> - узнать ID\n"
            f"<code>/admins</code> - управление администраторами\n\n"
            f"💡 <i>Используйте /help для полного списка команд</i>",
            parse_mode='HTML'
        )
        self.save_data()

        await self.create_monday_poll(chat_id)

    async def attendance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Текущее голосование"""
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        if not chat_data['current_poll_id']:
            await update.message.reply_text(
                "❌ Сейчас нет активного голосования\n\n"
                "💡 <i>Новое создастся в понедельник в 19:00</i>",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "✅ Голосование уже активно!\n\n"
                "💡 <i>Используйте кнопки в закрепленном сообщении</i>",
                parse_mode='HTML'
            )

    async def results_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Результаты голосования"""
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        if not chat_data['current_poll_id']:
            await update.message.reply_text("❌ Сейчас нет активного голосования")
            return

        results_text = await self.get_results_text(chat_id)
        await update.message.reply_text(results_text, parse_mode='HTML')

    async def voters_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Список голосовавших"""
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        if not chat_data['current_poll_id']:
            await update.message.reply_text("❌ Сейчас нет активного голосования")
            return

        voters_text = await self.get_voters_text(chat_id)
        await update.message.reply_text(voters_text, parse_mode='HTML')

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Панель управления"""
        if not await self.check_admin_access(update):
            return

        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        keyboard = [
            [InlineKeyboardButton("📊 Полная статистика", callback_data="admin_full_stats")],
            [InlineKeyboardButton("🔄 Обновить голосование", callback_data="admin_refresh")],
            [InlineKeyboardButton("🗑️ Очистить голоса", callback_data="admin_clear")],
            [InlineKeyboardButton("📅 Создать голосование сейчас", callback_data="admin_create_now")],
        ]

        await update.message.reply_text(
            "⚙️ <b>Панель управления посещаемостью</b>\n\n"
            f"📅 Следующий понедельник: {self.get_next_monday_date()}\n"
            f"👥 Проголосовало: {len(chat_data['votes'])} человек\n"
            f"👑 Администраторов: {len(chat_data['admin_users'])}\n"
            f"💬 ID чата: <code>{chat_id}</code>\n\n"
            f"💡 <i>Используйте кнопки для управления</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статус бота"""
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)
        is_admin = await self.is_admin(chat_id, update.effective_user.id)
        admin_status = "👑 Администратор" if is_admin else "👤 Пользователь"

        status_text = (
            "🤖 <b>Статус бота:</b>\n\n"
            f"✅ <b>Бот активен</b>\n"
            f"📅 <b>Расписание:</b> Каждый понедельник в 19:00\n"
            f"🕐 <b>Следующий понедельник:</b> {self.get_next_monday_date()}\n"
            f"👥 <b>Текущие голоса:</b> {len(chat_data['votes'])}\n"
            f"👑 <b>Администраторов:</b> {len(chat_data['admin_users'])}\n"
            f"💬 <b>ID чата:</b> <code>{chat_id}</code>\n"
            f"🎯 <b>Ваш статус:</b> {admin_status}\n\n"
            f"💡 <i>Бот работает стабильно</i> 🚀"
        )
        await update.message.reply_text(status_text, parse_mode='HTML')

    async def fix_rights_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка прав бота"""
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

    async def create_monday_poll(self, chat_id):
        """Создает голосование о посещаемости для конкретного чата"""
        chat_data = self.get_chat_data(chat_id)

        try:
            chat_data['current_poll_id'] = str(int(datetime.now().timestamp()))

            message_text = (
                f"<b>🗓️ Посещаемость на следующий понедельник</b>\n"
                f"<b>📅 {self.get_next_monday_date()} (Понедельник)</b>\n\n"
                "❓ <b>Кто приходит?</b>\n\n"
                "✅ <b>К 1</b> - приду к первому уроку\n"
                "⏰ <b>Ко 2</b> - приду ко второму уроку\n"
                "❌ <b>Не прихожу</b> - не буду\n\n"
                "💡 <i>Отметьтесь, пожалуйста, чтобы все были в курсе</i>"
            )

            keyboard = await self.create_voting_keyboard(chat_id)

            message = await self.application.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )

            try:
                if chat_data['last_poll_message_id']:
                    try:
                        await self.application.bot.unpin_chat_message(
                            chat_id=chat_id,
                            message_id=chat_data['last_poll_message_id']
                        )
                    except:
                        pass

                await self.application.bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=message.message_id,
                    disable_notification=True
                )

                chat_data['last_poll_message_id'] = message.message_id
                logger.info(f"✅ Сообщение закреплено в чате {chat_id}")

            except Exception as e:
                logger.warning(f"❌ Не удалось закрепить в чате {chat_id}: {e}")

            self.save_data()
            logger.info(f"✅ Новое голосование создано в чате {chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка создания голосования в чате {chat_id}: {e}")

    async def create_voting_keyboard(self, chat_id):
        """Создает клавиатуру для голосования"""
        chat_data = self.get_chat_data(chat_id)
        votes_count = {'1': 0, '2': 0, '3': 0}
        for vote_data in chat_data['votes'].values():
            option = vote_data['option']
            votes_count[option] += 1

        total_votes = len(chat_data['votes'])

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

        # Только администраторы видят кнопку результатов
        keyboard.append([InlineKeyboardButton("📊 Посмотреть результаты", callback_data="admin_full_stats")])

        return InlineKeyboardMarkup(keyboard)

    async def get_results_text(self, chat_id):
        """Текст результатов голосования"""
        chat_data = self.get_chat_data(chat_id)

        if not chat_data['current_poll_id']:
            return "Нет активного голосования"

        votes_count = {'1': 0, '2': 0, '3': 0}
        for vote_data in chat_data['votes'].values():
            option = vote_data['option']
            votes_count[option] += 1

        total_votes = len(chat_data['votes'])

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

    async def get_voters_text(self, chat_id):
        """Текст списка голосовавших"""
        chat_data = self.get_chat_data(chat_id)

        if not chat_data['votes']:
            return "Пока никто не отметился"

        votes_by_option = {
            '1': [],
            '2': [],
            '3': []
        }

        for vote_data in chat_data['votes'].values():
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

    async def get_full_stats_text(self, chat_id):
        """Полная статистика"""
        chat_data = self.get_chat_data(chat_id)
        total_users = len(chat_data['votes'])

        text = f"<b>📈 Статистика посещаемости:</b>\n"
        text += f"<b>📅 {self.get_next_monday_date()}</b>\n\n"

        votes_count = {'1': 0, '2': 0, '3': 0}
        voters_by_option = {'1': [], '2': [], '3': []}

        for vote_data in chat_data['votes'].values():
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
        """Обработка голосования"""
        query = update.callback_query
        user = query.from_user
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        try:
            option = query.data.split('_')[1]

            chat_data['votes'][str(user.id)] = {
                'option': option,
                'name': user.full_name,
                'timestamp': datetime.now().isoformat(),
                'username': user.username
            }

            keyboard = await self.create_voting_keyboard(chat_id)

            try:
                await query.edit_message_reply_markup(reply_markup=keyboard)
            except BadRequest:
                pass  # Сообщение не изменилось - это нормально

            option_names = {'1': 'К 1', '2': 'Ко 2', '3': 'Не прихожу'}
            await query.answer(f"✅ {option_names[option]}")
            self.save_data()

        except Exception as e:
            await query.answer("❌ Ошибка, попробуйте снова")

    async def handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка админ-команд"""
        query = update.callback_query
        user = query.from_user
        chat_id = update.effective_chat.id

        if not await self.is_admin(chat_id, user.id):
            await query.answer("🚫 Нет прав!")
            return

        try:
            data = query.data
            chat_data = self.get_chat_data(chat_id)

            if data == "admin_full_stats":
                stats_text = await self.get_full_stats_text(chat_id)
                await query.message.reply_text(stats_text, parse_mode='HTML')

            elif data == "admin_refresh":
                keyboard = await self.create_voting_keyboard(chat_id)
                try:
                    await query.edit_message_reply_markup(reply_markup=keyboard)
                except BadRequest:
                    pass
                await query.answer("✅ Голосование обновлено!")

            elif data == "admin_clear":
                chat_data['votes'] = {}
                keyboard = await self.create_voting_keyboard(chat_id)
                try:
                    await query.edit_message_reply_markup(reply_markup=keyboard)
                except BadRequest:
                    pass
                await query.answer("✅ Все голоса очищены!")
                self.save_data()

            elif data == "admin_create_now":
                await self.create_monday_poll(chat_id)
                await query.answer("✅ Голосование создано!")

            await query.answer()

        except Exception as e:
            await query.answer("❌ Ошибка")

    async def check_schedule(self):
        """Проверка расписания для всех активных чатов"""
        while True:
            try:
                now = datetime.now()
                if now.weekday() == 0 and now.hour == 19 and now.minute == 0:
                    logger.info("Создаем новое голосование по расписанию для всех чатов!")

                    # Создаем голосование для каждого активного чата
                    for chat_id in self.chat_data.keys():
                        try:
                            await self.create_monday_poll(chat_id)
                        except Exception as e:
                            logger.error(f"Ошибка создания голосования в чате {chat_id}: {e}")

                    await asyncio.sleep(61)
                else:
                    await asyncio.sleep(30)
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
        logger.info(f"📊 Активных чатов: {len(self.chat_data)}")

        # Создаем голосования для всех активных чатов
        for chat_id in self.chat_data.keys():
            chat_data = self.get_chat_data(chat_id)
            if not chat_data['current_poll_id']:
                logger.info(f"Создаем первое голосование в чате {chat_id}...")
                await self.create_monday_poll(chat_id)

        await self.check_schedule()


if __name__ == "__main__":
    print("🚀 Запуск бота для учета посещаемости с системой админов...")
    print(f"📅 Расписание: каждый понедельник в 19:00")
    print(f"👑 Главный админ ID: {MAIN_ADMIN_ID}")
    print("💡 Каждый чат имеет отдельный список администраторов")
    print("💡 Используйте /help для списка команд")

    bot = SimpleAttendanceBot(BOT_TOKEN)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")