# ============================================
# 🤖 بوت إدارة طلبات السنة التحضيرية - الفصل الثاني
# main.py - الملف الرئيسي
# مبني باستخدام aiogram 3.x + FSM + JSON Database
# ============================================

import asyncio
import json
import os
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
    BotCommand,
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import (
    TOKEN,
    CHANNEL_ID,
    ALLOWED_USERS,
    ADMIN_ID,
    DATABASE_FILE,
    WELCOME_MESSAGE,
    UNAUTHORIZED_MESSAGE,
)

# ============================================
# 📋 إعداد التسجيل (Logging)
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================
# 🗂️ إدارة قاعدة البيانات JSON
# ============================================

def load_database() -> dict:
    """تحميل قاعدة البيانات من ملف JSON، وإنشاؤه إذا لم يكن موجوداً."""
    default_data = {
        "statistics": {
            "accepted_students": 0,
            "total_codes": 0,
            "total_english_codes": 0,
        },
        "requests": {},
    }
    if not os.path.exists(DATABASE_FILE):
        save_database(default_data)
        logger.info("✅ تم إنشاء ملف قاعدة البيانات database.json")
        return default_data
    try:
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # التأكد من وجود المفاتيح الأساسية
        if "statistics" not in data:
            data["statistics"] = default_data["statistics"]
        if "requests" not in data:
            data["requests"] = {}
        return data
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"❌ خطأ في قراءة قاعدة البيانات: {e}")
        save_database(default_data)
        return default_data


def save_database(data: dict) -> None:
    """حفظ البيانات في ملف JSON."""
    try:
        with open(DATABASE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ قاعدة البيانات: {e}")


def save_request(request_id: str, request_data: dict) -> None:
    """حفظ طلب جديد في قاعدة البيانات."""
    db = load_database()
    db["requests"][request_id] = request_data
    save_database(db)


def update_request_status(request_id: str, status: str) -> bool:
    """تحديث حالة الطلب (accepted / rejected)."""
    db = load_database()
    if request_id in db["requests"]:
        db["requests"][request_id]["status"] = status
        save_database(db)
        return True
    return False


def update_statistics(codes_count: int, english_codes_count: int) -> None:
    """تحديث الإحصائيات بعد الموافقة على طلب."""
    db = load_database()
    db["statistics"]["accepted_students"] += 1
    db["statistics"]["total_codes"] += codes_count
    db["statistics"]["total_english_codes"] += english_codes_count
    save_database(db)


def get_statistics() -> dict:
    """الحصول على الإحصائيات الحالية."""
    db = load_database()
    return db["statistics"]


def get_request(request_id: str) -> dict | None:
    """الحصول على بيانات طلب معين."""
    db = load_database()
    return db["requests"].get(request_id)


# ============================================
# 🔄 حالات FSM لجمع بيانات الطلب
# ============================================

class RequestForm(StatesGroup):
    """حالات نموذج إرسال الطلب."""
    student_name = State()           # 1- الاسم الثلاثي
    student_number = State()         # 2- رقم الطالب
    telegram_username = State()      # 3- معرف التلغرام
    device_id = State()              # 4- معرف الجهاز ID
    subjects = State()               # 5- المواد المطلوبة
    codes_count = State()            # 6- عدد الأكواد
    has_english_codes = State()      # 7- هل يوجد أكواد إنجليزي؟
    english_codes_count = State()    # 7.1- عدد أكواد الإنجليزي
    notes = State()                  # 8- ملاحظات


# ============================================
# 🔧 إنشاء البوت والراوتر
# ============================================

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


# ============================================
# ⌨️ لوحات المفاتيح (Keyboards)
# ============================================

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """لوحة المفاتيح الرئيسية."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📩 إرسال طلب جديد")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_yes_no_keyboard() -> ReplyKeyboardMarkup:
    """لوحة مفاتيح نعم/لا."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="نعم ✅"), KeyboardButton(text="لا ❌")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """لوحة مفاتيح مع زر الإلغاء."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ إلغاء")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_approval_keyboard(request_id: str) -> InlineKeyboardMarkup:
    """أزرار الموافقة والرفض (Inline)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ موافقة",
                    callback_data=f"approve_{request_id}",
                ),
                InlineKeyboardButton(
                    text="❌ رفض",
                    callback_data=f"reject_{request_id}",
                ),
            ]
        ]
    )


# ============================================
# 🛡️ التحقق من الصلاحيات
# ============================================

def is_authorized(user_id: int) -> bool:
    """التحقق من أن المستخدم مصرح له."""
    return user_id in ALLOWED_USERS


def is_admin(user_id: int) -> bool:
    """التحقق من أن المستخدم هو الأدمن."""
    return user_id == ADMIN_ID


# ============================================
# 📌 معالج أمر /start
# ============================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """معالجة أمر /start."""
    await state.clear()

    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    await message.answer(
        WELCOME_MESSAGE,
        reply_markup=get_main_keyboard(),
    )


# ============================================
# 📊 معالج أمر /admin
# ============================================

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """عرض الإحصائيات للأدمن فقط."""
    if not is_admin(message.from_user.id):
        if not is_authorized(message.from_user.id):
            await message.answer(UNAUTHORIZED_MESSAGE)
        else:
            await message.answer("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    stats = get_statistics()
    stats_message = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>إحصائيات النظام</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👨‍🎓 عدد الطلاب المقبولين: <b>{stats['accepted_students']}</b>\n\n"
        f"🔑 مجموع الأكواد العادية: <b>{stats['total_codes']}</b>\n\n"
        f"🇬🇧 مجموع أكواد الإنجليزي: <b>{stats['total_english_codes']}</b>\n\n"
        f"📦 المجموع الكلي للأكواد: <b>{stats['total_codes'] + stats['total_english_codes']}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    await message.answer(stats_message)


# ============================================
# ❌ معالج زر الإلغاء (في أي حالة FSM)
# ============================================

@router.message(F.text == "❌ إلغاء", StateFilter("*"))
async def cancel_handler(message: Message, state: FSMContext):
    """إلغاء العملية الحالية والعودة للقائمة الرئيسية."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()

    await message.answer(
        "🔙 تم إلغاء العملية.\nيمكنك البدء من جديد.",
        reply_markup=get_main_keyboard(),
    )


# ============================================
# 📩 بدء إرسال طلب جديد
# ============================================

@router.message(F.text == "📩 إرسال طلب جديد")
async def start_new_request(message: Message, state: FSMContext):
    """بدء عملية إرسال طلب جديد."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    await state.set_state(RequestForm.student_name)
    await message.answer(
        "📝 <b>الخطوة 1 من 8</b>\n\n"
        "👤 الرجاء إدخال <b>الاسم الثلاثي للطالب</b>:",
        reply_markup=get_cancel_keyboard(),
    )


# ============================================
# 📝 خطوات FSM لجمع البيانات
# ============================================

# الخطوة 1: الاسم الثلاثي
@router.message(RequestForm.student_name)
async def process_student_name(message: Message, state: FSMContext):
    """استلام الاسم الثلاثي."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    await state.update_data(student_name=message.text.strip())
    await state.set_state(RequestForm.student_number)
    await message.answer(
        "📝 <b>الخطوة 2 من 8</b>\n\n"
        "🔢 الرجاء إدخال <b>رقم الطالب</b>:",
        reply_markup=get_cancel_keyboard(),
    )


# الخطوة 2: رقم الطالب
@router.message(RequestForm.student_number)
async def process_student_number(message: Message, state: FSMContext):
    """استلام رقم الطالب."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    await state.update_data(student_number=message.text.strip())
    await state.set_state(RequestForm.telegram_username)
    await message.answer(
        "📝 <b>الخطوة 3 من 8</b>\n\n"
        "📱 الرجاء إدخال <b>معرف التلغرام</b> الخاص بالطالب\n"
        "(مثال: @username):",
        reply_markup=get_cancel_keyboard(),
    )


# الخطوة 3: معرف التلغرام
@router.message(RequestForm.telegram_username)
async def process_telegram_username(message: Message, state: FSMContext):
    """استلام معرف التلغرام."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    await state.update_data(telegram_username=message.text.strip())
    await state.set_state(RequestForm.device_id)
    await message.answer(
        "📝 <b>الخطوة 4 من 8</b>\n\n"
        "📟 الرجاء إدخال <b>معرف الجهاز (Device ID)</b>:",
        reply_markup=get_cancel_keyboard(),
    )


# الخطوة 4: معرف الجهاز ID
@router.message(RequestForm.device_id)
async def process_device_id(message: Message, state: FSMContext):
    """استلام معرف الجهاز."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    await state.update_data(device_id=message.text.strip())
    await state.set_state(RequestForm.subjects)
    await message.answer(
        "📝 <b>الخطوة 5 من 8</b>\n\n"
        "📚 الرجاء إدخال <b>المواد المطلوبة</b>:\n"
        "(يمكنك كتابة عدة مواد مفصولة بفاصلة)",
        reply_markup=get_cancel_keyboard(),
    )


# الخطوة 5: المواد المطلوبة
@router.message(RequestForm.subjects)
async def process_subjects(message: Message, state: FSMContext):
    """استلام المواد المطلوبة."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    await state.update_data(subjects=message.text.strip())
    await state.set_state(RequestForm.codes_count)
    await message.answer(
        "📝 <b>الخطوة 6 من 8</b>\n\n"
        "🔑 كم <b>عدد الأكواد المطلوبة</b> لهذا الطالب؟\n"
        "(أدخل رقماً فقط)",
        reply_markup=get_cancel_keyboard(),
    )


# الخطوة 5: عدد الأكواد
@router.message(RequestForm.codes_count)
async def process_codes_count(message: Message, state: FSMContext):
    """استلام عدد الأكواد."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    # التحقق من أن المدخل رقم
    if not message.text.strip().isdigit():
        await message.answer("⚠️ الرجاء إدخال <b>رقم صحيح</b> فقط:")
        return

    await state.update_data(codes_count=int(message.text.strip()))
    await state.set_state(RequestForm.has_english_codes)
    await message.answer(
        "📝 <b>الخطوة 7 من 8</b>\n\n"
        "🇬🇧 هل يوجد <b>أكواد إنجليزي</b>؟",
        reply_markup=get_yes_no_keyboard(),
    )


# الخطوة 7: هل يوجد أكواد إنجليزي؟
@router.message(RequestForm.has_english_codes)
async def process_has_english_codes(message: Message, state: FSMContext):
    """استلام ما إذا كان هناك أكواد إنجليزي."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    text = message.text.strip()

    if text == "نعم ✅":
        await state.update_data(has_english_codes=True)
        await state.set_state(RequestForm.english_codes_count)
        await message.answer(
            "🇬🇧 كم <b>عدد أكواد الإنجليزي</b>؟\n"
            "(أدخل رقماً فقط)",
            reply_markup=get_cancel_keyboard(),
        )
    elif text == "لا ❌":
        await state.update_data(has_english_codes=False, english_codes_count=0)
        await state.set_state(RequestForm.notes)
        await message.answer(
            "📝 <b>الخطوة 8 من 8</b>\n\n"
            "📋 أدخل <b>الملاحظات</b>:\n"
            '(اختياري – يمكنك كتابة "لا يوجد")',
            reply_markup=get_cancel_keyboard(),
        )
    else:
        await message.answer(
            '⚠️ الرجاء اختيار "نعم ✅" أو "لا ❌" من الأزرار.',
            reply_markup=get_yes_no_keyboard(),
        )


# الخطوة 7.1: عدد أكواد الإنجليزي
@router.message(RequestForm.english_codes_count)
async def process_english_codes_count(message: Message, state: FSMContext):
    """استلام عدد أكواد الإنجليزي."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    if not message.text.strip().isdigit():
        await message.answer("⚠️ الرجاء إدخال <b>رقم صحيح</b> فقط:")
        return

    await state.update_data(english_codes_count=int(message.text.strip()))
    await state.set_state(RequestForm.notes)
    await message.answer(
        "📝 <b>الخطوة 8 من 8</b>\n\n"
        "📋 أدخل <b>الملاحظات</b>:\n"
        '(اختياري – يمكنك كتابة "لا يوجد")',
        reply_markup=get_cancel_keyboard(),
    )


# الخطوة 8: الملاحظات وإرسال الطلب
@router.message(RequestForm.notes)
async def process_notes(message: Message, state: FSMContext):
    """استلام الملاحظات وإرسال الطلب النهائي."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    if message.text == "❌ إلغاء":
        await cancel_handler(message, state)
        return

    await state.update_data(notes=message.text.strip())

    # جمع كل البيانات
    data = await state.get_data()
    await state.clear()

    # إنشاء معرف فريد للطلب
    request_id = f"REQ_{message.from_user.id}_{int(datetime.now().timestamp())}"

    # معلومات مقدم الطلب
    submitter_name = message.from_user.full_name or "غير معروف"
    submitter_id = message.from_user.id
    submitter_username = f"@{message.from_user.username}" if message.from_user.username else "لا يوجد"

    # التاريخ والوقت
    now = datetime.now().strftime("%Y-%m-%d | %H:%M:%S")

    # تحديد نص أكواد الإنجليزي
    english_codes_text = "لا يوجد"
    english_codes_count = data.get("english_codes_count", 0)
    if data.get("has_english_codes") and english_codes_count > 0:
        english_codes_text = str(english_codes_count)

    # بناء رسالة القناة
    channel_message = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📨 <b>طلب جديد</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>اسم الطالب:</b> {data['student_name']}\n\n"
        f"🔢 <b>رقم الطالب:</b> {data['student_number']}\n\n"
        f"📱 <b>معرف التلغرام:</b> {data['telegram_username']}\n\n"
        f"📟 <b>معرف الجهاز:</b> <code>{data['device_id']}</code>\n\n"
        f"📚 <b>المواد المطلوبة:</b> {data['subjects']}\n\n"
        f"🔑 <b>عدد الأكواد:</b> {data['codes_count']}\n\n"
        f"🇬🇧 <b>أكواد الإنجليزي:</b> {english_codes_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👨‍💼 <b>مقدم الطلب:</b> {submitter_name}\n"
        f"🆔 <b>آيدي مقدم الطلب:</b> <code>{submitter_id}</code>\n"
        f"📎 <b>يوزر مقدم الطلب:</b> {submitter_username}\n\n"
        f"📋 <b>ملاحظات:</b> {data['notes']}\n\n"
        f"🕐 <b>التاريخ والوقت:</b> {now}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    # حفظ الطلب في قاعدة البيانات
    request_data = {
        "student_name": data["student_name"],
        "student_number": data["student_number"],
        "telegram_username": data["telegram_username"],
        "device_id": data["device_id"],
        "subjects": data["subjects"],
        "codes_count": data["codes_count"],
        "has_english_codes": data.get("has_english_codes", False),
        "english_codes_count": english_codes_count,
        "notes": data["notes"],
        "submitter_id": submitter_id,
        "submitter_name": submitter_name,
        "submitter_username": submitter_username,
        "timestamp": now,
        "status": "pending",  # pending / accepted / rejected
    }
    save_request(request_id, request_data)

    try:
        # إرسال الرسالة للقناة مع أزرار الموافقة/الرفض
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=channel_message,
            reply_markup=get_approval_keyboard(request_id),
        )

        await message.answer(
            "✅ <b>تم إرسال الطلب بنجاح!</b>\n\n"
            "📨 تم إرسال الطلب إلى القناة للمراجعة.",
            reply_markup=get_main_keyboard(),
        )
        logger.info(f"✅ تم إرسال طلب جديد: {request_id} من المستخدم {submitter_id}")

    except Exception as e:
        logger.error(f"❌ خطأ في إرسال الطلب للقناة: {e}")
        await message.answer(
            "❌ حدث خطأ أثناء إرسال الطلب.\n"
            "الرجاء المحاولة لاحقاً.",
            reply_markup=get_main_keyboard(),
        )


# ============================================
# 🔧 دالة إعادة بناء نص رسالة القناة
# ============================================

def build_channel_text(request_data: dict) -> str:
    """إعادة بناء نص الرسالة الأصلية للقناة."""
    english_codes_text = "لا يوجد"
    if request_data.get("has_english_codes") and request_data.get("english_codes_count", 0) > 0:
        english_codes_text = str(request_data["english_codes_count"])

    return (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📨 <b>طلب</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>اسم الطالب:</b> {request_data['student_name']}\n\n"
        f"🔢 <b>رقم الطالب:</b> {request_data['student_number']}\n\n"
        f"📱 <b>معرف التلغرام:</b> {request_data['telegram_username']}\n\n"
        f"📟 <b>معرف الجهاز:</b> <code>{request_data.get('device_id', 'غير متوفر')}</code>\n\n"
        f"📚 <b>المواد المطلوبة:</b> {request_data['subjects']}\n\n"
        f"🔑 <b>عدد الأكواد:</b> {request_data['codes_count']}\n\n"
        f"🇬🇧 <b>أكواد الإنجليزي:</b> {english_codes_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👨‍💼 <b>مقدم الطلب:</b> {request_data['submitter_name']}\n"
        f"🆔 <b>آيدي مقدم الطلب:</b> <code>{request_data['submitter_id']}</code>\n"
        f"📎 <b>يوزر مقدم الطلب:</b> {request_data['submitter_username']}\n\n"
        f"📋 <b>ملاحظات:</b> {request_data['notes']}\n\n"
        f"🕐 <b>التاريخ والوقت:</b> {request_data['timestamp']}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )


# ============================================
# ✅ معالج زر الموافقة (Inline Callback)
# ============================================

@router.callback_query(F.data.startswith("approve_"))
async def handle_approval(callback: CallbackQuery):
    """
    معالجة الضغط على زر الموافقة.
    - يتم قبول الطلب مباشرة بدون طلب أكواد.
    - يتم إحصاء عدد الأكواد العادية والإنجليزي تلقائياً من بيانات الطلب.
    - يتم تحديث رسالة القناة.
    """
    request_id = callback.data.replace("approve_", "")

    # الحصول على بيانات الطلب
    request_data = get_request(request_id)

    if request_data is None:
        await callback.answer("⚠️ لم يتم العثور على هذا الطلب.", show_alert=True)
        return

    # التحقق من عدم تكرار المعالجة
    if request_data["status"] != "pending":
        status_text = "مقبول ✅" if request_data["status"] == "accepted" else "مرفوض ❌"
        await callback.answer(
            f"⚠️ هذا الطلب تم معالجته مسبقاً ({status_text})",
            show_alert=True,
        )
        return

    # تحديث حالة الطلب إلى مقبول
    update_request_status(request_id, "accepted")

    # تحديث الإحصائيات (إحصاء الأكواد من بيانات الطلب)
    codes_count = request_data["codes_count"]
    english_codes_count = request_data.get("english_codes_count", 0)
    update_statistics(codes_count, english_codes_count)

    # تحديث رسالة القناة
    approver_name = callback.from_user.full_name or "مشرف"
    now = datetime.now().strftime("%Y-%m-%d | %H:%M:%S")

    try:
        await callback.message.edit_text(
            text=(
                build_channel_text(request_data)
                + f"\n\n✅ <b>تمت الموافقة</b>\n"
                f"👨‍💼 بواسطة: {approver_name}\n"
                f"🕐 في: {now}"
            ),
            reply_markup=None,
        )
    except Exception as e:
        logger.error(f"خطأ في تحديث رسالة القناة: {e}")

    logger.info(
        f"✅ تم قبول الطلب {request_id} بواسطة {approver_name} | "
        f"أكواد عادية: {codes_count} | أكواد إنجليزي: {english_codes_count}"
    )

    await callback.answer(
        f"✅ تم قبول الطلب بنجاح!\n"
        f"📊 تم إحصاء {codes_count} كود عادي + {english_codes_count} كود إنجليزي",
        show_alert=True,
    )


# ============================================
# ❌ معالج زر الرفض (Inline Callback)
# ============================================

@router.callback_query(F.data.startswith("reject_"))
async def handle_rejection(callback: CallbackQuery):
    """
    معالجة الضغط على زر الرفض.
    - يتم رفض الطلب مباشرة.
    - يتم تحديث رسالة القناة.
    - لا يتم احتساب أي أكواد في الإحصائيات.
    """
    request_id = callback.data.replace("reject_", "")

    # الحصول على بيانات الطلب
    request_data = get_request(request_id)

    if request_data is None:
        await callback.answer("⚠️ لم يتم العثور على هذا الطلب.", show_alert=True)
        return

    # التحقق من عدم تكرار المعالجة
    if request_data["status"] != "pending":
        status_text = "مقبول ✅" if request_data["status"] == "accepted" else "مرفوض ❌"
        await callback.answer(
            f"⚠️ هذا الطلب تم معالجته مسبقاً ({status_text})",
            show_alert=True,
        )
        return

    # تحديث حالة الطلب إلى مرفوض
    update_request_status(request_id, "rejected")

    # تحديث رسالة القناة
    rejecter_name = callback.from_user.full_name or "مشرف"
    now = datetime.now().strftime("%Y-%m-%d | %H:%M:%S")

    try:
        await callback.message.edit_text(
            text=(
                build_channel_text(request_data)
                + f"\n\n❌ <b>تم الرفض</b>\n"
                f"👨‍💼 بواسطة: {rejecter_name}\n"
                f"🕐 في: {now}"
            ),
            reply_markup=None,
        )
    except Exception as e:
        logger.error(f"خطأ في تحديث رسالة القناة: {e}")

    logger.info(f"❌ تم رفض الطلب {request_id} بواسطة {rejecter_name}")

    await callback.answer("❌ تم رفض الطلب.", show_alert=True)


# ============================================
# 🚫 معالج الرسائل من غير المصرح لهم
# ============================================

@router.message(~StateFilter(None))
async def handle_unknown_state_message(message: Message, state: FSMContext):
    """التعامل مع رسائل غير متوقعة أثناء حالة FSM."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return


@router.message()
async def handle_all_messages(message: Message):
    """التعامل مع أي رسالة أخرى غير معالجة."""
    if not is_authorized(message.from_user.id):
        await message.answer(UNAUTHORIZED_MESSAGE)
        return

    # رسالة للمستخدمين المصرح لهم عند إرسال رسالة غير معروفة
    await message.answer(
        "🤔 لم أفهم طلبك.\n"
        "استخدم الأزرار أدناه أو اكتب /start للبدء.",
        reply_markup=get_main_keyboard(),
    )


# ============================================
# 🚀 تشغيل البوت
# ============================================

async def main():
    """الدالة الرئيسية لتشغيل البوت."""
    # تهيئة قاعدة البيانات
    load_database()

    logger.info("🚀 جاري تشغيل البوت...")
    logger.info(f"👥 المستخدمون المصرح لهم: {ALLOWED_USERS}")
    logger.info(f"👑 الأدمن: {ADMIN_ID}")
    logger.info(f"📢 القناة: {CHANNEL_ID}")

    # ============================================
    # 📋 تسجيل قائمة الأوامر (Bot Menu Commands)
    # ============================================
    commands = [
        BotCommand(command="start", description="🏠 بدء البوت والقائمة الرئيسية"),
        BotCommand(command="admin", description="📊 عرض الإحصائيات (للأدمن فقط)"),
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ تم تسجيل قائمة الأوامر بنجاح")

    # حذف webhook إن وجد وبدء التشغيل
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
