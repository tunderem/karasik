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


class AdvancedAdminBot:
    def __init__(self, token):
        self.token = token
        # Основная структура данных с разделением по chat_id
        self.chat_data = {}
        self.application = Application.builder().token(token).build()

        # Загружаем данные сразу при создании
        self.load_data()

        # Обработчики команд
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("id", self.id_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("fix_rights", self.fix_rights_command))
        self.application.add_handler(CommandHandler("get_id", self.get_id_command))
        self.application.add_handler(CommandHandler("status", self.status_command))

        # Команды для получения ID
        self.application.add_handler(CommandHandler("all_ids", self.all_ids_command))
        self.application.add_handler(CommandHandler("chat_info", self.chat_info_command))

        # Команды управления администраторами
        self.application.add_handler(CommandHandler("admins", self.admins_command))
        self.application.add_handler(CommandHandler("add_admin", self.add_admin_command))
        self.application.add_handler(CommandHandler("remove_admin", self.remove_admin_command))

        # Команды мута, бана и кика
        self.application.add_handler(CommandHandler("mute", self.mute_command))
        self.application.add_handler(CommandHandler("unmute", self.unmute_command))
        self.application.add_handler(CommandHandler("ban", self.ban_command))
        self.application.add_handler(CommandHandler("unban", self.unban_command))
        self.application.add_handler(CommandHandler("kick", self.kick_command))

        # Обработчик ответов на сообщения
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

        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка: {context.error}", exc_info=context.error)

        try:
            # Пытаемся отправить сообщение об ошибке
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Произошла ошибка при обработке команды. Попробуйте еще раз."
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения об ошибке: {e}")

    def get_chat_data(self, chat_id):
        """Получает данные чата, создает если нет"""
        if chat_id not in self.chat_data:
            self.chat_data[chat_id] = {
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
            with open('bot_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, default=str, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")

    def load_data(self):
        """Загружаем данные"""
        try:
            if os.path.exists('bot_data.json'):
                with open('bot_data.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    if 'chat_data' in data:
                        self.chat_data = data['chat_data']
                    else:
                        # Конвертация старого формата в новый
                        self.chat_data = {}

                    # Гарантируем, что главный админ всегда в списке для каждого чата
                    for chat_id in self.chat_data:
                        if MAIN_ADMIN_ID not in self.chat_data[chat_id]['admin_users']:
                            self.chat_data[chat_id]['admin_users'].append(MAIN_ADMIN_ID)

        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")
            self.chat_data = {}

    async def is_admin(self, chat_id, user_id):
        """Проверяет, является ли пользователь администратором в конкретном чате"""
        chat_data = self.get_chat_data(chat_id)
        return user_id in chat_data['admin_users']

    async def check_admin_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверяет права администратора в текущем чате"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if not await self.is_admin(chat_id, user_id):
            await self.send_safe_message(
                context, chat_id,
                "🚫 У вас нет прав администратора в этом чате!"
            )
            return False
        return True

    async def send_safe_message(self, context, chat_id, text, parse_mode='HTML', reply_to_message_id=None):
        """Безопасная отправка сообщения с обработкой ошибок"""
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id
            )
            return True
        except BadRequest as e:
            if "Message to be replied not found" in str(e):
                # Если сообщение для ответа не найдено, отправляем без ответа
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
                return True
            else:
                logger.error(f"Ошибка отправки сообщения: {e}")
                return False
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return False

    # ========== КОМАНДЫ УПРАВЛЕНИЯ АДМИНАМИ ==========

    async def admins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список администраторов текущего чата"""
        if not await self.check_admin_access(update, context):
            return

        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)
        admin_users = chat_data['admin_users']

        if not admin_users:
            await self.send_safe_message(context, chat_id, "📝 <b>Список администраторов пуст</b>")
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

        text = f"👑 <b>Администраторы чата:</b>\n\n" + "\n".join(admin_list)
        text += f"\n\n📊 <b>Всего:</b> {len(admin_users)} администраторов"

        await self.send_safe_message(context, chat_id, text)

    async def add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавляет администратора в текущий чат"""
        if not await self.check_admin_access(update, context):
            return

        # Если нет аргументов и нет ответа на сообщение
        if not context.args and not update.message.reply_to_message:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/add_admin 123456789</code> - добавить по ID\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /add_admin</i>"
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
                await self.send_safe_message(
                    context, chat_id,
                    f"ℹ️ <b>Пользователь уже является администратором этого чата</b>\n\n"
                    f"👤 {user_name}\n"
                    f"🆔 <code>{user_id}</code>"
                )
                return

            # Добавляем администратора
            chat_data['admin_users'].append(user_id)
            self.save_data()

            await self.send_safe_message(
                context, chat_id,
                f"✅ <b>Новый администратор добавлен в этот чат</b>\n\n"
                f"👤 {user_name}\n"
                f"🆔 <code>{user_id}</code>\n\n"
                f"💡 <i>Теперь пользователь может использовать команды администратора в этом чате</i>"
            )

        except ValueError:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID."
            )
        except Exception as e:
            await self.send_safe_message(
                context, update.effective_chat.id,
                f"❌ Ошибка добавления: {e}"
            )

    async def remove_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаляет администратора из текущего чата"""
        if not await self.check_admin_access(update, context):
            return

        # Если нет аргументов и нет ответа на сообщение
        if not context.args and not update.message.reply_to_message:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/remove_admin 123456789</code> - удалить по ID\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /remove_admin</i>"
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

            # Проверяем, не пытаемся ли удалить главного администратора
            if user_id == MAIN_ADMIN_ID:
                await self.send_safe_message(
                    context, chat_id,
                    "❌ Нельзя удалить главного администратора!"
                )
                return

            # Проверяем, есть ли пользователь в списке
            if user_id not in chat_data['admin_users']:
                await self.send_safe_message(
                    context, chat_id,
                    "❌ Пользователь не является администратором этого чата"
                )
                return

            # Удаляем администратора
            chat_data['admin_users'].remove(user_id)
            self.save_data()

            await self.send_safe_message(
                context, chat_id,
                f"✅ <b>Администратор удален из этого чата</b>\n\n"
                f"👤 {user_name}\n"
                f"🆔 <code>{user_id}</code>\n\n"
                f"💡 <i>Пользователь больше не может использовать команды администратора в этом чате</i>"
            )

        except ValueError:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID."
            )
        except Exception as e:
            await self.send_safe_message(
                context, update.effective_chat.id,
                f"❌ Ошибка удаления: {e}"
            )

    # ========== КОМАНДЫ ДЛЯ ПОЛУЧЕНИЯ ID ==========

    async def id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает ID пользователя"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        is_admin = await self.is_admin(chat_id, user.id)

        admin_status = "👑 Администратор" if is_admin else "👤 Пользователь"

        await self.send_safe_message(
            context, chat_id,
            f"👤 <b>Ваша информация:</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📛 <b>Имя:</b> {user.full_name}\n"
            f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}\n"
            f"💬 <b>ID чата:</b> <code>{chat_id}</code>\n"
            f"🎯 <b>Статус в этом чате:</b> {admin_status}"
        )

    async def get_id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получает ID пользователя по ответу на сообщение"""
        if not context.args and not update.message.reply_to_message:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/get_id</code> - в ответ на сообщение пользователя\n"
                "<code>/get_id 123456789</code> - по ID"
            )
            return

        try:
            if update.message.reply_to_message:
                # Получаем ID из ответа на сообщение
                user = update.message.reply_to_message.from_user
                await self.send_safe_message(
                    context, update.effective_chat.id,
                    f"👤 <b>Информация о пользователе:</b>\n\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"📛 <b>Имя:</b> {user.full_name}\n"
                    f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}"
                )
            elif context.args:
                target = context.args[0]

                # Пробуем как ID
                if target.isdigit():
                    user_id = int(target)
                    try:
                        # Пробуем получить информацию о пользователе
                        user = await context.bot.get_chat(user_id)
                        await self.send_safe_message(
                            context, update.effective_chat.id,
                            f"👤 <b>Информация о пользователе:</b>\n\n"
                            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                            f"📛 <b>Имя:</b> {user.full_name}\n"
                            f"🔖 <b>Username:</b> @{user.username if user.username else 'нет'}"
                        )
                        return
                    except Exception as e:
                        await self.send_safe_message(
                            context, update.effective_chat.id,
                            f"❌ Пользователь с ID {target} не найден"
                        )
                        return

                await self.send_safe_message(
                    context, update.effective_chat.id,
                    "❌ Используйте числовой ID пользователя"
                )

        except Exception as e:
            await self.send_safe_message(
                context, update.effective_chat.id,
                f"❌ Ошибка: {e}"
            )

    async def all_ids_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает ID всех администраторов чата"""
        try:
            chat_id = update.effective_chat.id
            admins = await context.bot.get_chat_administrators(chat_id)

            if not admins:
                await self.send_safe_message(context, chat_id, "❌ Не удалось получить список администраторов")
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
            await self.send_safe_message(context, chat_id, text)

        except Exception as e:
            await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка: {e}")

    async def chat_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает информацию о чате"""
        try:
            chat = update.effective_chat
            chat_id = chat.id
            chat_data = self.get_chat_data(chat_id)

            admin_count = len(chat_data['admin_users'])

            await self.send_safe_message(
                context, chat_id,
                f"💬 <b>Информация о чате:</b>\n\n"
                f"📛 <b>Название:</b> {chat.title}\n"
                f"🆔 <b>ID чата:</b> <code>{chat.id}</code>\n"
                f"👥 <b>Тип:</b> {chat.type}\n"
                f"👑 <b>Админов бота:</b> {admin_count}"
            )
        except Exception as e:
            await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка: {e}")

    # ========== КОМАНДЫ МУТА, БАНА И КИКА ==========

    async def mute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мут пользователя по ID или по ответу на сообщение"""
        if not await self.check_admin_access(update, context):
            return

        # Если ответ на сообщение
        if update.message.reply_to_message:
            await self.handle_reply_mute(update, context)
            return

        # Если нет аргументов
        if not context.args:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/mute 123456789</code> - мут по ID\n"
                "<code>/mute 123456789 1h</code> - мут на 1 час\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /mute</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id

            # Определяем ID пользователя и время
            if len(context.args) >= 1:
                # Проверяем, является ли первый аргумент ID (числом)
                if context.args[0].isdigit():
                    user_id = int(context.args[0])
                    duration_str = context.args[1] if len(context.args) > 1 else "10m"
                else:
                    # Если первый аргумент не число, значит это время, но без ID - ошибка
                    await self.send_safe_message(
                        context, chat_id,
                        "❌ <b>Не указан ID пользователя!</b>\n\n"
                        "📝 <b>Использование:</b>\n"
                        "<code>/mute 123456789 1h</code> - мут по ID\n\n"
                        "💡 <i>Или ответьте на сообщение пользователя с командой /mute</i>"
                    )
                    return
            else:
                await self.send_safe_message(
                    context, chat_id,
                    "❌ <b>Не указан ID пользователя!</b>\n\n"
                    "📝 <b>Использование:</b>\n"
                    "<code>/mute 123456789 1h</code> - мут по ID\n\n"
                    "💡 <i>Или ответьте на сообщение пользователя с командой /mute</i>"
                )
                return

            # Парсим время
            duration = self.parse_duration(duration_str)
            if not duration:
                await self.send_safe_message(
                    context, chat_id,
                    "❌ Неверный формат времени. Используйте: 10m, 1h, 1d, 1w"
                )
                return

            # Проверяем, не пытаемся ли замутить бота или администратора
            if user_id == context.bot.id:
                await self.send_safe_message(context, chat_id, "❌ Не могу замутить самого себя!")
                return

            # Проверяем, является ли пользователь администратором
            if await self.is_admin(chat_id, user_id):
                await self.send_safe_message(context, chat_id, "❌ Нельзя замутить администратора бота!")
                return

            # Проверяем, является ли пользователь администратором чата
            try:
                chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                if chat_member.status in ['administrator', 'creator']:
                    await self.send_safe_message(context, chat_id, "❌ Нельзя замутить администратора чата!")
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

            await self.send_safe_message(
                context, chat_id,
                f"🔇 <b>{user_name} замьючен на {self.format_duration(duration)}</b>\n\n"
                f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"🆔 ID: <code>{user_id}</code>"
            )

        except ValueError:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID.\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /mute</i>"
            )
        except BadRequest as e:
            error_msg = str(e).lower()
            if "not enough rights" in error_msg:
                await self.send_safe_message(context, update.effective_chat.id,
                                             "❌ У бота недостаточно прав для ограничения пользователей")
            elif "user not found" in error_msg:
                await self.send_safe_message(context, update.effective_chat.id, "❌ Пользователь не найден в этом чате")
            else:
                await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка мута: {e}")
        except Exception as e:
            await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка мута: {e}")

    async def unmute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Размут пользователя по ID"""
        if not await self.check_admin_access(update, context):
            return

        # Если ответ на сообщение
        if update.message.reply_to_message:
            await self.handle_reply_unmute(update, context)
            return

        if not context.args:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/unmute 123456789</code> - размутить по ID\n\n"
                "💡 <i>Или ответьте на сообщение командой /unmute</i>"
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

            await self.send_safe_message(
                context, chat_id,
                f"🔊 <b>{user_name} размьючен</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>"
            )

        except ValueError:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID.\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /unmute</i>"
            )
        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await self.send_safe_message(context, update.effective_chat.id,
                                             "❌ У бота недостаточно прав для изменения прав пользователей")
            else:
                await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка размута: {e}")
        except Exception as e:
            await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка размута: {e}")

    async def ban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Бан пользователя по ID"""
        if not await self.check_admin_access(update, context):
            return

        # Если ответ на сообщение
        if update.message.reply_to_message:
            await self.handle_reply_ban(update, context)
            return

        if not context.args:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/ban 123456789</code> - бан по ID\n"
                "<code>/ban 123456789 1h</code> - бан на 1 час\n\n"
                "💡 <i>Или ответьте на сообщение командой /ban</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id

            # Получаем ID и время
            if len(context.args) >= 1:
                if context.args[0].isdigit():
                    user_id = int(context.args[0])
                    duration_str = context.args[1] if len(context.args) > 1 else "forever"
                else:
                    await self.send_safe_message(
                        context, chat_id,
                        "❌ <b>Не указан ID пользователя!</b>\n\n"
                        "📝 <b>Использование:</b>\n"
                        "<code>/ban 123456789 1h</code> - бан по ID\n\n"
                        "💡 <i>Или ответьте на сообщение пользователя с командой /ban</i>"
                    )
                    return
            else:
                await self.send_safe_message(
                    context, chat_id,
                    "❌ <b>Не указан ID пользователя!</b>\n\n"
                    "📝 <b>Использование:</b>\n"
                    "<code>/ban 123456789 1h</code> - бан по ID\n\n"
                    "💡 <i>Или ответьте на сообщение пользователя с командой /ban</i>"
                )
                return

            # Парсим время
            until_date = None
            if duration_str != "forever":
                duration = self.parse_duration(duration_str)
                if not duration:
                    await self.send_safe_message(
                        context, chat_id,
                        "❌ Неверный формат времени. Используйте: 10m, 1h, 1d, 1w"
                    )
                    return
                until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)

            # Проверяем, не пытаемся ли забанить бота или администратора
            if user_id == context.bot.id:
                await self.send_safe_message(context, chat_id, "❌ Не могу забанить самого себя!")
                return

            # Проверяем, является ли пользователь администратором
            if await self.is_admin(chat_id, user_id):
                await self.send_safe_message(context, chat_id, "❌ Нельзя забанить администратора бота!")
                return

            # Проверяем, является ли пользователь администратором чата
            try:
                chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                if chat_member.status in ['administrator', 'creator']:
                    await self.send_safe_message(context, chat_id, "❌ Нельзя забанить администратора чата!")
                    return
            except:
                pass

            # Выполняем бан
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                until_date=until_date
            )

            # Пробуем получить имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            if until_date:
                duration_text = f"на {self.format_duration(duration)}"
                until_text = f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}"
            else:
                duration_text = "навсегда"
                until_text = "⏰ Навсегда"

            await self.send_safe_message(
                context, chat_id,
                f"🚫 <b>{user_name} забанен {duration_text}</b>\n\n"
                f"{until_text}\n"
                f"🆔 ID: <code>{user_id}</code>"
            )

        except ValueError:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID.\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /ban</i>"
            )
        except BadRequest as e:
            error_msg = str(e).lower()
            if "not enough rights" in error_msg:
                await self.send_safe_message(context, update.effective_chat.id,
                                             "❌ У бота недостаточно прав для бана пользователей")
            elif "user not found" in error_msg:
                await self.send_safe_message(context, update.effective_chat.id, "❌ Пользователь не найден в этом чате")
            else:
                await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка бана: {e}")
        except Exception as e:
            await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка бана: {e}")

    async def unban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Разбан пользователя по ID"""
        if not await self.check_admin_access(update, context):
            return

        # Если ответ на сообщение
        if update.message.reply_to_message:
            await self.handle_reply_unban(update, context)
            return

        if not context.args:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/unban 123456789</code> - разбанить по ID\n\n"
                "💡 <i>Или ответьте на сообщение командой /unban</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id
            user_id = int(context.args[0])

            # Выполняем разбан
            await context.bot.unban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id
            )

            # Пробуем получить имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await self.send_safe_message(
                context, chat_id,
                f"✅ <b>{user_name} разбанен</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>"
            )

        except ValueError:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID.\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /unban</i>"
            )
        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await self.send_safe_message(context, update.effective_chat.id,
                                             "❌ У бота недостаточно прав для разбана пользователей")
            else:
                await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка разбана: {e}")
        except Exception as e:
            await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка разбана: {e}")

    async def kick_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Кик пользователя по ID"""
        if not await self.check_admin_access(update, context):
            return

        # Если ответ на сообщение
        if update.message.reply_to_message:
            await self.handle_reply_kick(update, context)
            return

        if not context.args:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ <b>Использование:</b>\n"
                "<code>/kick 123456789</code> - кикнуть по ID\n\n"
                "💡 <i>Или ответьте на сообщение командой /kick</i>"
            )
            return

        try:
            chat_id = update.effective_chat.id

            # Получаем ID пользователя
            if len(context.args) >= 1:
                if context.args[0].isdigit():
                    user_id = int(context.args[0])
                else:
                    await self.send_safe_message(
                        context, chat_id,
                        "❌ <b>Не указан ID пользователя!</b>\n\n"
                        "📝 <b>Использование:</b>\n"
                        "<code>/kick 123456789</code> - кикнуть по ID\n\n"
                        "💡 <i>Или ответьте на сообщение пользователя с командой /kick</i>"
                    )
                    return
            else:
                await self.send_safe_message(
                    context, chat_id,
                    "❌ <b>Не указан ID пользователя!</b>\n\n"
                    "📝 <b>Использование:</b>\n"
                    "<code>/kick 123456789</code> - кикнуть по ID\n\n"
                    "💡 <i>Или ответьте на сообщение пользователя с командой /kick</i>"
                )
                return

            # Проверяем, не пытаемся ли кикнуть бота или администратора
            if user_id == context.bot.id:
                await self.send_safe_message(context, chat_id, "❌ Не могу кикнуть самого себя!")
                return

            # Проверяем, является ли пользователь администратором
            if await self.is_admin(chat_id, user_id):
                await self.send_safe_message(context, chat_id, "❌ Нельзя кикнуть администратора бота!")
                return

            # Проверяем, является ли пользователь администратором чата
            try:
                chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                if chat_member.status in ['administrator', 'creator']:
                    await self.send_safe_message(context, chat_id, "❌ Нельзя кикнуть администратора чата!")
                    return
            except:
                pass

            # Выполняем кик (бан на 30 секунд + разбан)
            until_date = datetime.now(timezone.utc) + timedelta(seconds=30)
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                until_date=until_date
            )

            # Сразу разбаниваем, чтобы пользователь мог вернуться по приглашению
            await context.bot.unban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id
            )

            # Пробуем получить имя пользователя
            try:
                user = await context.bot.get_chat(user_id)
                user_name = user.full_name
            except:
                user_name = f"Пользователь ({user_id})"

            await self.send_safe_message(
                context, chat_id,
                f"👢 <b>{user_name} кикнут из чата</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"💡 <i>Пользователь может вернуться по приглашению</i>"
            )

        except ValueError:
            await self.send_safe_message(
                context, update.effective_chat.id,
                "❌ Неверный формат ID. Используйте числовой ID.\n\n"
                "💡 <i>Или ответьте на сообщение пользователя с командой /kick</i>"
            )
        except BadRequest as e:
            error_msg = str(e).lower()
            if "not enough rights" in error_msg:
                await self.send_safe_message(context, update.effective_chat.id,
                                             "❌ У бота недостаточно прав для кика пользователей")
            elif "user not found" in error_msg:
                await self.send_safe_message(context, update.effective_chat.id, "❌ Пользователь не найден в этом чате")
            else:
                await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка кика: {e}")
        except Exception as e:
            await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка кика: {e}")

    # ========== ОБРАБОТЧИКИ ОТВЕТОВ НА СООБЩЕНИЯ ==========

    async def handle_reply_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мут по ответу на сообщение"""
        if not await self.check_admin_access(update, context):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_mute = replied_message.from_user
        chat_id = update.effective_chat.id

        # Проверяем, не пытаемся ли замутить бота или администратора
        if user_to_mute.id == context.bot.id:
            await self.send_safe_message(context, chat_id, "❌ Не могу замутить самого себя!")
            return

        if await self.is_admin(chat_id, user_to_mute.id):
            await self.send_safe_message(context, chat_id, "❌ Нельзя замутить администратора бота!")
            return

        try:
            # Проверяем, является ли пользователь администратором чата
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_to_mute.id)
            if chat_member.status in ['administrator', 'creator']:
                await self.send_safe_message(context, chat_id, "❌ Нельзя замутить администратора чата!")
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

            await self.send_safe_message(
                context, chat_id,
                f"🔇 <b>{user_to_mute.full_name} замьючен на {self.format_duration(duration)}</b>\n\n"
                f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"🆔 ID: <code>{user_to_mute.id}</code>"
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await self.send_safe_message(context, chat_id,
                                             "❌ У бота недостаточно прав для ограничения пользователей")
            else:
                await self.send_safe_message(context, chat_id, f"❌ Ошибка мута: {e}")
        except Exception as e:
            await self.send_safe_message(context, chat_id, f"❌ Ошибка мута: {e}")

    async def handle_reply_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Бан по ответу на сообщение"""
        if not await self.check_admin_access(update, context):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_ban = replied_message.from_user
        chat_id = update.effective_chat.id

        # Проверяем, не пытаемся ли забанить бота или администратора
        if user_to_ban.id == context.bot.id:
            await self.send_safe_message(context, chat_id, "❌ Не могу забанить самого себя!")
            return

        if await self.is_admin(chat_id, user_to_ban.id):
            await self.send_safe_message(context, chat_id, "❌ Нельзя забанить администратора бота!")
            return

        try:
            # Проверяем, является ли пользователь администратором чата
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_to_ban.id)
            if chat_member.status in ['administrator', 'creator']:
                await self.send_safe_message(context, chat_id, "❌ Нельзя забанить администратора чата!")
                return
        except:
            pass

        # Парсим время из команды
        command_parts = update.message.text.split()
        duration_str = command_parts[1] if len(command_parts) > 1 else "forever"

        until_date = None
        if duration_str != "forever":
            duration = self.parse_duration(duration_str)
            if duration:
                until_date = datetime.now(timezone.utc) + timedelta(seconds=duration)

        try:
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_to_ban.id,
                until_date=until_date
            )

            if until_date:
                duration_text = f"на {self.format_duration(duration)}"
                until_text = f"⏰ До: {until_date.strftime('%d.%m.%Y %H:%M:%S')}"
            else:
                duration_text = "навсегда"
                until_text = "⏰ Навсегда"

            await self.send_safe_message(
                context, chat_id,
                f"🚫 <b>{user_to_ban.full_name} забанен {duration_text}</b>\n\n"
                f"{until_text}\n"
                f"🆔 ID: <code>{user_to_ban.id}</code>"
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await self.send_safe_message(context, chat_id, "❌ У бота недостаточно прав для бана пользователей")
            else:
                await self.send_safe_message(context, chat_id, f"❌ Ошибка бана: {e}")
        except Exception as e:
            await self.send_safe_message(context, chat_id, f"❌ Ошибка бана: {e}")

    async def handle_reply_kick(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Кик по ответу на сообщение"""
        if not await self.check_admin_access(update, context):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_kick = replied_message.from_user
        chat_id = update.effective_chat.id

        # Проверяем, не пытаемся ли кикнуть бота или администратора
        if user_to_kick.id == context.bot.id:
            await self.send_safe_message(context, chat_id, "❌ Не могу кикнуть самого себя!")
            return

        if await self.is_admin(chat_id, user_to_kick.id):
            await self.send_safe_message(context, chat_id, "❌ Нельзя кикнуть администратора бота!")
            return

        try:
            # Проверяем, является ли пользователь администратором чата
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_to_kick.id)
            if chat_member.status in ['administrator', 'creator']:
                await self.send_safe_message(context, chat_id, "❌ Нельзя кикнуть администратора чата!")
                return
        except:
            pass

        try:
            # Выполняем кик (бан на 30 секунд + разбан)
            until_date = datetime.now(timezone.utc) + timedelta(seconds=30)
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_to_kick.id,
                until_date=until_date
            )

            # Сразу разбаниваем, чтобы пользователь мог вернуться по приглашению
            await context.bot.unban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_to_kick.id
            )

            await self.send_safe_message(
                context, chat_id,
                f"👢 <b>{user_to_kick.full_name} кикнут из чата</b>\n\n"
                f"🆔 ID: <code>{user_to_kick.id}</code>\n"
                f"💡 <i>Пользователь может вернуться по приглашению</i>"
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await self.send_safe_message(context, chat_id, "❌ У бота недостаточно прав для кика пользователей")
            else:
                await self.send_safe_message(context, chat_id, f"❌ Ошибка кика: {e}")
        except Exception as e:
            await self.send_safe_message(context, chat_id, f"❌ Ошибка кика: {e}")

    async def handle_reply_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавление админа по ответу на сообщение"""
        if not await self.check_admin_access(update, context):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_admin = replied_message.from_user
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        # Проверяем, не добавляем ли уже админа
        if user_to_admin.id in chat_data['admin_users']:
            await self.send_safe_message(
                context, chat_id,
                f"ℹ️ <b>Пользователь уже является администратором этого чата</b>\n\n"
                f"👤 {user_to_admin.full_name}\n"
                f"🆔 <code>{user_to_admin.id}</code>"
            )
            return

        # Добавляем администратора
        chat_data['admin_users'].append(user_to_admin.id)
        self.save_data()

        await self.send_safe_message(
            context, chat_id,
            f"✅ <b>Новый администратор добавлен в этот чат</b>\n\n"
            f"👤 {user_to_admin.full_name}\n"
            f"🆔 <code>{user_to_admin.id}</code>\n\n"
            f"💡 <i>Теперь пользователь может использовать команды администратора в этом чате</i>"
        )

    async def handle_reply_remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаление админа по ответу на сообщение"""
        if not await self.check_admin_access(update, context):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_remove = replied_message.from_user
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        # Проверяем, не пытаемся ли удалить главного администратора
        if user_to_remove.id == MAIN_ADMIN_ID:
            await self.send_safe_message(context, chat_id, "❌ Нельзя удалить главного администратора!")
            return

        # Проверяем, есть ли пользователь в списке
        if user_to_remove.id not in chat_data['admin_users']:
            await self.send_safe_message(context, chat_id, "❌ Пользователь не является администратором этого чата")
            return

        # Удаляем администратора
        chat_data['admin_users'].remove(user_to_remove.id)
        self.save_data()

        await self.send_safe_message(
            context, chat_id,
            f"✅ <b>Администратор удален из этого чата</b>\n\n"
            f"👤 {user_to_remove.full_name}\n"
            f"🆔 <code>{user_to_remove.id}</code>\n\n"
            f"💡 <i>Пользователь больше не может использовать команды администратора в этом чате</i>"
        )

    async def handle_reply_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Размут по ответу на сообщение"""
        if not await self.check_admin_access(update, context):
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

            await self.send_safe_message(
                context, update.effective_chat.id,
                f"🔊 <b>{user_to_unmute.full_name} размьючен</b>\n\n"
                f"🆔 ID: <code>{user_to_unmute.id}</code>"
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await self.send_safe_message(context, update.effective_chat.id,
                                             "❌ У бота недостаточно прав для изменения прав пользователей")
            else:
                await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка размута: {e}")
        except Exception as e:
            await self.send_safe_message(context, update.effective_chat.id, f"❌ Ошибка размута: {e}")

    async def handle_reply_unban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Разбан по ответу на сообщение"""
        if not await self.check_admin_access(update, context):
            return

        replied_message = update.message.reply_to_message
        if not replied_message:
            return

        user_to_unban = replied_message.from_user
        chat_id = update.effective_chat.id

        try:
            await context.bot.unban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_to_unban.id
            )

            await self.send_safe_message(
                context, chat_id,
                f"✅ <b>{user_to_unban.full_name} разбанен</b>\n\n"
                f"🆔 ID: <code>{user_to_unban.id}</code>"
            )

        except BadRequest as e:
            if "not enough rights" in str(e).lower():
                await self.send_safe_message(context, chat_id, "❌ У бота недостаточно прав для разбана пользователей")
            else:
                await self.send_safe_message(context, chat_id, f"❌ Ошибка разбана: {e}")
        except Exception as e:
            await self.send_safe_message(context, chat_id, f"❌ Ошибка разбана: {e}")

    # ========== СЛУЖЕБНЫЕ МЕТОДЫ ==========

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

    # ========== ОСНОВНЫЕ КОМАНДЫ ==========

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда start"""
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)

        # Активируем бота в чате
        await self.send_safe_message(
            context, chat_id,
            f"✅ <b>Продвинутый бот-администратор активирован!</b>\n\n"
            f"⚡ <b>Основные возможности:</b>\n"
            f"• Управление администраторами\n"
            f"• Мут, бан и кик пользователей\n"
            f"• Получение ID пользователей\n\n"
            f"💡 <i>Используйте /help для полного списка команд</i>"
        )
        self.save_data()

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь по командам"""
        chat_id = update.effective_chat.id
        is_admin = await self.is_admin(chat_id, update.effective_user.id)

        help_text = (
            "🤖 <b>Помощь по командам бота</b>\n\n"

            "🆔 <b>Получение ID:</b>\n"
            "<code>/id</code> - ваш ID\n"
            "<code>/get_id</code> - ID пользователя (в ответ на сообщение)\n"
            "<code>/all_ids</code> - ID всех администраторов чата\n"
            "<code>/chat_info</code> - информация о чате\n"
            "<code>/status</code> - статус бота\n\n"
        )

        if is_admin:
            help_text += (
                "👑 <b>Администраторские команды:</b>\n"
                "<code>/admins</code> - список администраторов бота\n"
                "<code>/add_admin ID</code> - добавить администратора\n"
                "<code>/remove_admin ID</code> - удалить администратора\n\n"

                "🔇 <b>Мут:</b>\n"
                "<code>/mute ID [время]</code> - мут пользователя\n"
                "<code>/unmute ID</code> - размутить\n\n"

                "🚫 <b>Бан:</b>\n"
                "<code>/ban ID [время]</code> - бан пользователя\n"
                "<code>/unban ID</code> - разбанить\n\n"

                "👢 <b>Кик:</b>\n"
                "<code>/kick ID</code> - кикнуть пользователя\n\n"
            )

        help_text += (
            "💡 <b>Советы:</b>\n"
            "• Используйте ID вместо username для команд\n"
            "• Для мута/бана/кика/добавления админа можно ответить на сообщение\n"
            "• Каждый чат имеет отдельный список администраторов"
        )

        await self.send_safe_message(context, chat_id, help_text)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статус бота"""
        chat_id = update.effective_chat.id
        chat_data = self.get_chat_data(chat_id)
        is_admin = await self.is_admin(chat_id, update.effective_user.id)
        admin_status = "👑 Администратор" if is_admin else "👤 Пользователь"

        status_text = (
            "🤖 <b>Статус бота:</b>\n\n"
            f"✅ <b>Бот активен</b>\n"
            f"👑 <b>Администраторов:</b> {len(chat_data['admin_users'])}\n"
            f"💬 <b>ID чата:</b> <code>{chat_id}</code>\n"
            f"🎯 <b>Ваш статус:</b> {admin_status}\n\n"
            f"💡 <i>Бот работает стабильно</i> 🚀"
        )
        await self.send_safe_message(context, chat_id, status_text)

    async def fix_rights_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка прав бота"""
        if not await self.check_admin_access(update, context):
            return

        chat_id = update.effective_chat.id

        try:
            chat = await context.bot.get_chat(chat_id)
            bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)

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

                if bot_member.can_ban_members:
                    rights_info += "✅ <b>Может банить пользователей</b>\n"
                else:
                    rights_info += "❌ <b>НЕ может банить пользователей</b>\n"

                if bot_member.can_pin_messages:
                    rights_info += "✅ <b>Может закреплять сообщения</b>\n"
                else:
                    rights_info += "❌ <b>НЕ может закреплять сообщения</b>\n"

            else:
                rights_info += "❌ <b>Статус:</b> НЕ администратор\n"

            rights_info += "\n⚡ <b>Для полной работы нужно:</b>\n"
            rights_info += "• Права администратора\n"
            rights_info += "• Право 'Ограничивать пользователей'\n"
            rights_info += "• Право 'Банить пользователей'\n"
            rights_info += "• Право 'Закреплять сообщения'\n\n"
            rights_info += "💡 <i>Обратитесь к создателю чата для выдачи прав</i>"

            await self.send_safe_message(context, chat_id, rights_info)

        except Exception as e:
            await self.send_safe_message(
                context, chat_id,
                f"❌ <b>Ошибка проверки прав:</b>\n\n"
                f"<code>{e}</code>\n\n"
                f"💡 <i>Убедитесь что бот добавлен в группу и является администратором</i>"
            )

    def run(self):
        """Запуск бота - упрощенная версия"""
        print("🚀 Запуск бота...")
        self.application.run_polling()


if __name__ == "__main__":
    print("🚀 Запуск продвинутого бота-администратора...")
    print(f"👑 Главный админ ID: {MAIN_ADMIN_ID}")
    print("💡 Возможности: мут, бан, кик, управление админами")
    print("💡 Каждый чат имеет отдельный список администраторов")
    print("💡 Используйте /help для списка команд")

    bot = AdvancedAdminBot(BOT_TOKEN)

    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()