import asyncio
import logging
import os
from datetime import datetime, timedelta
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ==========================================
#                  SOZLAMALAR
# ==========================================
BOT_TOKEN = "8923619414:AAFPj4c3ptkintGA3fYyX5l1LQuOmCSRsaw"
ADMIN_IDS = {5018078645, 8631477823}
CARD_NUMBER = "9860 1901 0314 2450"
CARD_OWNER = "BAZARBAEV T"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==========================================
#          CALLBACK DATA FABRIKALARI
# ==========================================
class TariffCB(CallbackData, prefix="tariff"):
    days: int
    price: int

class ApproveCB(CallbackData, prefix="approve"):
    user_id: int
    days: int

class RejectCB(CallbackData, prefix="reject"):
    user_id: int

class ChannelDelCB(CallbackData, prefix="ch_del"):
    channel_id: int

# ==========================================
#          MA'LUMOTLAR BAZASI (SQLITE)
# ==========================================
async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                premium_until DATETIME,
                joined_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                code INTEGER PRIMARY KEY,
                file_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                name TEXT,
                type TEXT
            )
        """)
        await db.commit()

async def add_user(user_id):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()

async def is_premium(user_id) -> bool:
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    premium_until = datetime.fromisoformat(row[0])
                    return datetime.now() < premium_until
                except:
                    pass
        return False

# ==========================================
#      MAJBURIY OBUNA VA ZAYAVKALARNI TEKSHIRISH
# ==========================================
async def check_subscription(user_id: int) -> bool:
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT chat_id, type FROM channels") as cursor:
            channels = await cursor.fetchall()
    
    if not channels:
        return True

    for chat_id, ch_type in channels:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            pass
    return True

async def get_sub_keyboard():
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT chat_id, name FROM channels") as cursor:
            channels = await cursor.fetchall()

    builder = []
    for chat_id, name in channels:
        if chat_id.startswith("http"):
            url = chat_id
        else:
            url = f"https://t.me/{chat_id.replace('@', '')}"
        builder.append([InlineKeyboardButton(text=name, url=url)])
    
    builder.append([InlineKeyboardButton(text="⚡️ TEKSHIRISH ⚡️", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

# Foydalanuvchi klaviaturasi
main_reply_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💎 PREMIUM VIP 💎")]
    ],
    resize_keyboard=True
)

# ADMIN PANEL TUGMALARI
admin_reply_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 Kanallarni sozlash")],
        [KeyboardButton(text="🎬 Kino Yuklash"), KeyboardButton(text="📬 Xabar Yuborish")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📁 Backup")],
        [KeyboardButton(text="📥 Bazani Tiklash (Restore)"), KeyboardButton(text="◀️ Orqaga")]
    ],
    resize_keyboard=True
)

# ==========================================
#              KLAVIATURALAR
# ==========================================
def get_tariffs_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ 1 KUNLIK OBUNA — 5 000 SO'M ⚡️", callback_data=TariffCB(days=1, price=5000).pack())],
        [InlineKeyboardButton(text="🔥 1 HAFTALIK OBUNA — 10 000 SO'M 🔥", callback_data=TariffCB(days=7, price=10000).pack())],
        [InlineKeyboardButton(text="👑 1 OYLIK OBUNA — 20 000 SO'M 👑", callback_data=TariffCB(days=30, price=20000).pack())],
        [InlineKeyboardButton(text="◀️ ORQAGA ◀️", callback_data="back_to_start")]
    ])

# ==========================================
#              FSM STATE'LAR
# ==========================================
class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_channel_info = State()
    waiting_for_restore_db = State()

class PaymentState(StatesGroup):
    waiting_for_receipt = State()

# ==========================================
#        FOYDALANUVCHI HANDLERLARI
# ==========================================
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await add_user(message.from_user.id)
    subscribed = await check_subscription(message.from_user.id)
    
    if subscribed:
        await message.answer(
            f"👋 <b>Assalomu alaykum</b> <b>{message.from_user.first_name}</b>, <b>botimizga xush kelibsiz!</b> 🎉\n\n"
            f"✍️ <b>Kino kodini yuboring...</b> 🎬", 
            reply_markup=main_reply_keyboard, 
            parse_mode="HTML"
        )
    else:
        text = (
            "⚠️ <b>Kechirasiz, botimizdan foydalanish uchun ushbu kanallarga obuna bo'lishingiz/zayavka yuborishingiz kerak!</b> 📌\n\n"
            "💎 <b>Premium obuna sotib olib, kanallarga obuna bo'lmasdan foydalanishingiz ham mumkin.</b> 🚀"
        )
        await message.answer(text, reply_markup=await get_sub_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "check_sub")
async def check_sub_handler(call: types.CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        await call.message.answer(
            "✅ <b>Obuna muvaffaqiyatli tasdiqlandi!</b> 🎉\n\n✍️ <b>Kino kodini yuboring...</b> 🎬", 
            reply_markup=main_reply_keyboard, 
            parse_mode="HTML"
        )
    else:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)

@dp.callback_query(F.data == "back_to_start")
async def back_to_start_handler(call: types.CallbackQuery):
    await call.message.delete()
    fake_msg = types.Message(
        message_id=call.message.message_id,
        date=call.message.date,
        chat=call.message.chat,
        from_user=call.from_user
    )
    await start_handler(fake_msg)

@dp.message(F.text.contains("PREMIUM VIP") | (F.text == "💎 Premium"))
async def premium_text_handler(message: types.Message):
    text = (
        "💎 <b>PREMIUM OBUNA</b> 👑\n\n"
        "✨ <b>Premium orqali quyidagilarga ega bo'lasiz:</b>\n"
        "🟢 <b>Kanallarga obuna bo'lmasdan kino ko'rish</b>\n"
        "🟢 <b>Reklamalarsiz tezkor foydalanish</b>\n"
        "🟢 <b>Yuqori sifatdagi kinolarni tomosha qilish</b>\n\n"
        "📋 <b>Quyidagi tariflardan birini tanlang:</b> ⬇️"
    )
    await message.answer(text, reply_markup=get_tariffs_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "premium_menu")
async def premium_menu_handler(call: types.CallbackQuery):
    text = (
        "💎 <b>PREMIUM OBUNA</b> 👑\n\n"
        "✨ <b>Premium orqali quyidagilarga ega bo'lasiz:</b>\n"
        "🟢 <b>Kanallarga obuna bo'lmasdan kino ko'rish</b>\n"
        "🟢 <b>Reklamalarsiz tezkor foydalanish</b>\n"
        "🟢 <b>Yuqori sifatdagi kinolarni tomosha qilish</b>\n\n"
        "📋 <b>Quyidagi tariflardan birini tanlang:</b> ⬇️"
    )
    try:
        await call.message.edit_text(text, reply_markup=get_tariffs_keyboard(), parse_mode="HTML")
    except:
        await call.message.answer(text, reply_markup=get_tariffs_keyboard(), parse_mode="HTML")

@dp.callback_query(TariffCB.filter())
async def tariff_selected_handler(call: types.CallbackQuery, callback_data: TariffCB, state: FSMContext):
    await state.update_data(days=callback_data.days, price=callback_data.price)
    
    price_formatted = f"{callback_data.price:,}".replace(",", " ")
    text = (
        "💳 <b>PREMIUM OBUNA — TO'LOV MA'LUMOTLARI</b> 💸\n\n"
        f"📦 <b>Tarif:</b> <b>{callback_data.days} kunlik obuna</b>\n"
        f"💳 <b>Karta raqami:</b> <code>{CARD_NUMBER}</code>\n"
        f"👤 <b>Karta egasi:</b> <b>{CARD_OWNER}</b>\n"
        f"💰 <b>To'lov summasi:</b> <b>{price_formatted} so'm</b>\n\n"
        "⚠️ <b>Diqqat:</b>\n"
        "📸 <b>Pulni o'tkazgandan so'ng, chekni (skrinshotni) yuborish uchun pastdagi tugmani bosing!</b> ⬇️"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 CHEK RASMINI YUBORISH 📤", callback_data="send_receipt")],
        [InlineKeyboardButton(text="◀️ ORQAGA ◀️", callback_data="premium_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "send_receipt")
async def ask_receipt_handler(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(PaymentState.waiting_for_receipt)
    await call.message.answer("📸 <b>Iltimos, to'lovni tasdiqlovchi chek (skrinshot) rasmini shu yerga yuboring:</b>", parse_mode="HTML")
    await call.answer()

@dp.message(PaymentState.waiting_for_receipt, F.photo)
async def receipt_received_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    days = data.get("days", 30)
    price = data.get("price", 0)
    price_formatted = f"{price:,}".replace(",", " ")
    photo_file_id = message.photo[-1].file_id
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=ApproveCB(user_id=message.from_user.id, days=days).pack()),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=RejectCB(user_id=message.from_user.id).pack())
        ]
    ])
    
    caption = (
        "💳 <b>YANGI TO'LOV CHEKI KELDI!</b> 🚨\n\n"
        f"👤 <b>Foydalanuvchi:</b> <b>{message.from_user.full_name}</b>\n"
        f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n"
        f"📦 <b>Tarif:</b> <b>{days} kunlik</b>\n"
        f"💰 <b>Summa:</b> <b>{price_formatted} so'm</b>"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(chat_id=admin_id, photo=photo_file_id, caption=caption, reply_markup=admin_kb, parse_mode="HTML")
        except Exception:
            pass

    await message.answer("✅ <b>Chekingiz adminga yuborildi!</b> ⏳\n<b>Adminlar tekshirib chiqquncha kuting.</b>", parse_mode="HTML", reply_markup=main_reply_keyboard)
    await state.clear()

@dp.callback_query(ApproveCB.filter(), F.from_user.id.in_(ADMIN_IDS))
async def approve_payment_handler(call: types.CallbackQuery, callback_data: ApproveCB):
    user_id = callback_data.user_id
    days = callback_data.days
    
    now = datetime.now()
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        
        if row and row[0]:
            try:
                current_expiry = datetime.fromisoformat(row[0])
                if current_expiry > now:
                    new_expiry = current_expiry + timedelta(days=days)
                else:
                    new_expiry = now + timedelta(days=days)
            except:
                new_expiry = now + timedelta(days=days)
        else:
            new_expiry = now + timedelta(days=days)
        
        await db.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_expiry.isoformat(), user_id))
        await db.commit()
        
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"🎉 <b>Tabriklaymiz! To'lovingiz tasdiqlandi.</b> 👑\n<b>Sizga {days} kunlik Premium obuna berildi. Endi kino kodlarini yuborishingiz mumkin!</b> 🎬",
            parse_mode="HTML"
        )
    except Exception:
        pass
        
    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode="HTML")
    await call.answer("To'lov tasdiqlandi!", show_alert=True)

@dp.callback_query(RejectCB.filter(), F.from_user.id.in_(ADMIN_IDS))
async def reject_payment_handler(call: types.CallbackQuery, callback_data: RejectCB):
    user_id = callback_data.user_id
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text="❌ <b>Kechirasiz, to'lov chekingiz rad etildi.</b> ⚠️\n<b>Iltimos, to'g'ri chek yuborganingizga ishonch hosil qiling.</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass
        
    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ <b>RAD ETILDI</b>", parse_mode="HTML")
    await call.answer("To'lov rad etildi.", show_alert=True)

# Kino qidirish
@dp.message(F.text.regexp(r'^\d+$'))
async def find_movie_handler(message: types.Message):
    movie_code = int(message.text)
    
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT file_id FROM movies WHERE code = ?", (movie_code,)) as cursor:
            row = await cursor.fetchone()
        
    if not row:
        await message.reply("❌ <b>Kino kodini noto'g'ri yubordingiz!</b> ⚠️", parse_mode="HTML")
        return

    if not await is_premium(message.from_user.id) and message.from_user.id not in ADMIN_IDS:
        text = (
            "🔒 <b>Ushbu kino faqat «Premium» foydalanuvchilar uchun!</b> 👑\n\n"
            "❗ <b>Premium obunaga ega bo'ling.</b> 🚀"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 PREMIUM OLISH 💎", callback_data="premium_menu")]
        ])
        await message.reply(text, reply_markup=kb, parse_mode="HTML")
        return

    bot_info = await bot.get_me()
    await message.reply_video(video=row[0], caption=f"🎬 <b>Kino kodi:</b> <b>{movie_code}</b>\n\n🤖 <b>@{bot_info.username}</b>", parse_mode="HTML")

# ==========================================
#          ADMIN PANEL FUNKSIYALARI
# ==========================================
@dp.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
@dp.message(F.text == "◀️ Orqaga", F.from_user.id.in_(ADMIN_IDS))
async def admin_panel_handler(message: types.Message):
    await message.answer(
        "👨‍💻 <b>Admin panelga xush kelibsiz!</b> ⚙️\n\n<b>Quyidagi menyudan kerakli bo'limni tanlang:</b>", 
        reply_markup=admin_reply_keyboard, 
        parse_mode="HTML"
    )

@dp.message(Command("prem"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_prem(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ <b>Ishlatish:</b> <code>/prem user_id [kun]</code>\nMisol: <code>/prem 123456789 30</code>", parse_mode="HTML")
        return
    try:
        user_id = int(args[1])
        days = int(args[2]) if len(args) > 2 else 30
        new_expiry = datetime.now() + timedelta(days=days)
        
        async with aiosqlite.connect("bot_database.db") as db:
            await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            await db.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_expiry.isoformat(), user_id))
            await db.commit()
            
        await message.answer(f"✅ <b>{user_id}</b> ID raqamli foydalanuvchiga <b>{days}</b> kunlik Premium berildi! 🎉", parse_mode="HTML")
        try:
            await bot.send_message(user_id, f"🎉 <b>Admin tomonidan sizga {days} kunlik Premium obuna taqdim etildi!</b> 👑", parse_mode="HTML")
        except:
            pass
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

@dp.message(Command("unprem"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_unprem(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ <b>Ishlatish:</b> <code>/unprem user_id</code>", parse_mode="HTML")
        return
    try:
        user_id = int(args[1])
        async with aiosqlite.connect("bot_database.db") as db:
            await db.execute("UPDATE users SET premium_until = NULL WHERE user_id = ?", (user_id,))
            await db.commit()
            
        await message.answer(f"✅ <b>{user_id}</b> ID raqamli foydalanuvchidan Premium olib tashlandi! ⚠️", parse_mode="HTML")
        try:
            await bot.send_message(user_id, "⚠️ <b>Admin tomonidan Premium obunangiz tugatildi.</b>", parse_mode="HTML")
        except:
            pass
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

@dp.message(F.text == "📁 Backup", F.from_user.id.in_(ADMIN_IDS))
async def backup_handler(message: types.Message):
    db_file = "bot_database.db"
    if os.path.exists(db_file):
        document = BufferedInputFile.from_file(db_file, filename=f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db")
        await message.answer_document(document=document, caption="📁 <b>Mana bazaning zaxira nusxasi (Backup)!</b> 🛡️", parse_mode="HTML")
    else:
        await message.answer("❌ <b>Ma'lumotlar bazasi topilmadi!</b>", parse_mode="HTML")

@dp.message(F.text == "📥 Bazani Tiklash (Restore)", F.from_user.id.in_(ADMIN_IDS))
async def restore_start_handler(message: types.Message, state: FSMContext):
    await message.answer(
        "📥 <b>Bazani tiklash uchun (.db) formatdagi zaxira faylini shu yerga yuboring:</b>\n\n"
        "⚠️ <i>Diqqat: Hozirgi mavjud baza yuborgan faylingiz bilan almashtiriladi!</i>\n"
        "Bekor qilish uchun /cancel yuboring.",
        parse_mode="HTML",
        reply_markup=admin_reply_keyboard
    )
    await state.set_state(AdminState.waiting_for_restore_db)

@dp.message(AdminState.waiting_for_restore_db, F.from_user.id.in_(ADMIN_IDS))
async def restore_process_handler(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == '/cancel':
        await message.answer("❌ <b>Bazani tiklash bekor qilindi.</b>", parse_mode="HTML", reply_markup=admin_reply_keyboard)
        await state.clear()
        return

    if not message.document:
        await message.reply("❌ <b>Iltimos, `.db` formatdagi faylni hujjat (document) ko'rinishida yuboring!</b>", parse_mode="HTML")
        return

    if not message.document.file_name.endswith('.db'):
        await message.reply("❌ <b>Faqat `.db` kengaytmali fayl qabul qilinadi! Qaytadan yuboring.</b>", parse_mode="HTML")
        return

    try:
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        
        with open("bot_database.db", "wb") as new_db:
            new_db.write(downloaded_file.read())

        # Restore qilingandan keyin jadvallar eski bo'lsa ham xatolik bermasligi uchun tuzilmani yangilab olamiz
        await init_db()

        await message.answer("✅ <b>Ma'lumotlar bazasi muvaffaqiyatli tiklandi (Restore qilindi)!</b> 🎉", parse_mode="HTML", reply_markup=admin_reply_keyboard)
        await state.clear()
    except Exception as e:
        await message.reply(f"❌ Xatolik yuz berdi: {e}", reply_markup=admin_reply_keyboard)
        await state.clear()

# 1. KANALLARNI SOZLASH (Xatoliklarga qarshi himoyalangan)
@dp.message(F.text == "📢 Kanallarni sozlash", F.from_user.id.in_(ADMIN_IDS))
async def channels_settings_menu(message: types.Message):
    await init_db()  # Jadval mavjudligini kafolatlash uchun
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT id, chat_id, name, type FROM channels") as cursor:
            channels = await cursor.fetchall()
    
    text = "📢 <b>Kanallarni sozlash bo'limi</b>\n\n📋 <b>Hozirgi ulangan kanallar:</b>\n"
    kb = []
    
    if channels:
        for ch_id, chat_id, name, ch_type in channels:
            text += f"• {name} ({chat_id}) - [{ch_type}]\n"
            kb.append([InlineKeyboardButton(text=f"❌ O'chirish: {name}", callback_data=ChannelDelCB(channel_id=ch_id).pack())])
    else:
        text += "<i>Hozircha kanallar ulanmagan.</i>\n"

    kb.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel_start")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(ChannelDelCB.filter(), F.from_user.id.in_(ADMIN_IDS))
async def delete_channel_cb(call: types.CallbackQuery, callback_data: ChannelDelCB):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("DELETE FROM channels WHERE id = ?", (callback_data.channel_id,))
        await db.commit()
    await call.answer("Kanal o'chirildi!", show_alert=True)
    
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT id, chat_id, name, type FROM channels") as cursor:
            channels = await cursor.fetchall()
            
    text = "📢 <b>Kanallarni sozlash bo'limi</b>\n\n📋 <b>Hozirgi ulangan kanallar:</b>\n"
    kb = []
    if channels:
        for ch_id, chat_id, name, ch_type in channels:
            text += f"• {name} ({chat_id}) - [{ch_type}]\n"
            kb.append([InlineKeyboardButton(text=f"❌ O'chirish: {name}", callback_data=ChannelDelCB(channel_id=ch_id).pack())])
    else:
        text += "<i>Hozircha kanallar ulanmagan.</i>\n"
    kb.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel_start")])
    
    try:
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except:
        pass

@dp.callback_query(F.data == "add_channel_start", F.from_user.id.in_(ADMIN_IDS))
async def add_channel_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(
        "➕ <b>Yangi kanal qo'shish uchun quyidagi formatda yuboring:</b>\n\n"
        "<code>Kanal_Nomi | @kanal_username_yoki_havola | Majburiy_oki_Zayavka</code>\n\n"
        "<b>Misol:</b>\n<code>Asosiy Kanal | @yangikinoobott | Majburiy</code>",
        parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_channel_info)
    await call.answer()

@dp.message(AdminState.waiting_for_channel_info, F.from_user.id.in_(ADMIN_IDS))
async def save_channel_handler(message: types.Message, state: FSMContext):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) != 3:
            await message.reply("❌ <b>Format xato! Qaytadan yuboring:</b>", parse_mode="HTML")
            return
        
        name, chat_id, ch_type = parts
        async with aiosqlite.connect("bot_database.db") as db:
            await db.execute("INSERT INTO channels (chat_id, name, type) VALUES (?, ?, ?)", (chat_id, name, ch_type))
            await db.commit()
            
        await message.reply("✅ <b>Kanal muvaffaqiyatli qo'shildi!</b> 🎉", parse_mode="HTML", reply_markup=admin_reply_keyboard)
        await state.clear()
    except Exception as e:
        await message.reply(f"❌ Xatolik yuz berdi: {e}")

# 2. KINO YUKLASH
@dp.message(F.text == "🎬 Kino Yuklash", F.from_user.id.in_(ADMIN_IDS))
async def upload_movie_menu(message: types.Message):
    await message.answer("🎬 <b>Kino qo'shish uchun video bilan birga uning kodini (faqat raqam) caption (izoh) qismiga yozib yuboring!</b>", parse_mode="HTML", reply_markup=admin_reply_keyboard)

@dp.message(F.video & (F.from_user.id.in_(ADMIN_IDS)))
async def add_movie_handler(message: types.Message):
    if not message.caption or not message.caption.isdigit():
        await message.reply("❌ <b>Kino qo'shish uchun video bilan birga uning kodini (faqat raqam) yozib yuboring!</b>", parse_mode="HTML")
        return
    
    movie_code = int(message.caption)
    file_id = message.video.file_id
    
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("INSERT OR REPLACE INTO movies (code, file_id) VALUES (?, ?)", (movie_code, file_id))
        await db.commit()
        
    await message.reply(f"✅ <b>Kino bazaga qo'shildi!</b> 🎬\n<b>Kodi:</b> <b>{movie_code}</b>", parse_mode="HTML")

# 3. XABAR YUBORISH (Broadcast)
@dp.message(F.text == "📬 Xabar Yuborish", F.from_user.id.in_(ADMIN_IDS))
async def broadcast_menu(message: types.Message, state: FSMContext):
    await message.answer("📢 <b>Barcha foydalanuvchilarga yuboriladigan xabarni yuboring:</b>\n\nBekor qilish uchun /cancel yuboring.", parse_mode="HTML", reply_markup=admin_reply_keyboard)
    await state.set_state(AdminState.waiting_for_broadcast)

@dp.message(AdminState.waiting_for_broadcast, F.from_user.id.in_(ADMIN_IDS))
async def send_broadcast_handler(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == '/cancel':
        await message.answer("❌ <b>Xabar tarqatish bekor qilindi.</b>", parse_mode="HTML", reply_markup=admin_reply_keyboard)
        await state.clear()
        return

    await message.answer("⏳ <b>Xabar tarqatish boshlandi...</b>", parse_mode="HTML")
    
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
        
    count = 0
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ <b>Xabar {count} ta foydalanuvchiga muvaffaqiyatli yuborildi!</b> 🎉", parse_mode="HTML", reply_markup=admin_reply_keyboard)
    await state.clear()

# 4. STATISTIKA (Xatoliklarga qarshi tekshiruv bilan)
@dp.message(F.text == "📊 Statistika", F.from_user.id.in_(ADMIN_IDS))
async def stats_menu(message: types.Message):
    await init_db()
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            users_count_res = await cursor.fetchone()
        async with db.execute("SELECT COUNT(*) FROM movies") as cursor:
            movies_count_res = await cursor.fetchone()
        
        users_cnt = users_count_res[0] if users_count_res else 0
        movies_cnt = movies_count_res[0] if movies_count_res else 0
        
        now = datetime.now()
        day_ago = (now - timedelta(days=1)).isoformat()
        week_ago = (now - timedelta(days=7)).isoformat()
        month_ago = (now - timedelta(days=30)).isoformat()
        
        try:
            async with db.execute("SELECT COUNT(*) FROM users WHERE joined_date >= ?", (day_ago,)) as cursor:
                day_users = await cursor.fetchone()
            async with db.execute("SELECT COUNT(*) FROM users WHERE joined_date >= ?", (week_ago,)) as cursor:
                week_users = await cursor.fetchone()
            async with db.execute("SELECT COUNT(*) FROM users WHERE joined_date >= ?", (month_ago,)) as cursor:
                month_users = await cursor.fetchone()

            day_cnt = day_users[0] if day_users else 0
            week_cnt = week_users[0] if week_users else 0
            month_cnt = month_users[0] if month_users else 0
        except:
            day_cnt, week_cnt, month_cnt = 0, 0, 0

    text = (
        "📊 <b>Statistika</b>\n"
        f"• Obunachilar soni: {users_cnt} ta\n"
        f"• Faol obunachilar: {users_cnt} ta\n\n"
        "📈 <b>Obunachilar qo'shilishi</b>\n"
        f"• Oxirgi 24 soat: +{day_cnt} obunachi\n"
        f"• Oxirgi 7 kun: +{week_cnt} obunachi\n"
        f"• Oxirgi 30 kun: +{month_cnt} obunachi\n\n"
        f"🎬 <b>Kinolar soni:</b> {movies_cnt} ta"
    )
    
    await message.answer(text, reply_markup=admin_reply_keyboard, parse_mode="HTML")

# ==========================================
#                MAIN
# ==========================================
async def handle_ping(request):
    return web.Response(text="Bot ishlamoqda!")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
