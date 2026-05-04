import asyncio
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import aiohttp
import json
from typing import List, Dict, Optional
import re
import os
import tempfile
import shutil
import time

# ======================
# CONFIGURAZIONE
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8216455195:AAG8gZQRp49URVtWV10V-uw64jhSaSoGGkE"

DEEPSEEK_API_KEY = "sk-7e2b6eb1c4ff4b4aa1046a6ae500a40e"
ADMIN_USER_ID = 7097140504
ADMIN_USERNAME = "famn25"

if os.path.exists('/app'):
    DATA_FOLDER = "/app/data"
else:
    DATA_FOLDER = "."

# Archivos
THREADS_MODELS_FILE = os.path.join(DATA_FOLDER, "threads_models.json")
PHOTO_CATEGORIES_FILE = os.path.join(DATA_FOLDER, "photo_categories.json")
CUSTOM_LANGUAGES_FILE = os.path.join(DATA_FOLDER, "custom_languages.json")
PHOTOS_DB_FILE = os.path.join(DATA_FOLDER, "fotos_db.json")
REELS_DB_FILE = os.path.join(DATA_FOLDER, "reels_db.json")
USER_CONFIG_FILE = os.path.join(DATA_FOLDER, "user_config.json")
USER_STATE_FILE = os.path.join(DATA_FOLDER, "user_state.json")
PHOTOS_FOLDER = os.path.join(DATA_FOLDER, "fotos")
REELS_FOLDER = os.path.join(DATA_FOLDER, "reels")

MAX_VARIATIONS = 50
THRESHOLD_FOTOS = 40
THRESHOLD_REELS = 3
PHOTO_CONFIRMATION_BATCH = 50

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Estados para creación
waiting_for_new_threads_model = {}
waiting_for_new_photo_category = {}
waiting_for_new_photo_model = {}
waiting_for_new_language = {}
waiting_for_file = {}
waiting_for_photo_upload = {}
waiting_for_reel_upload = {}
pending_uploads = {}
waiting_for_reels_iguser = {}

user_threads_state = {}
user_config = {}
user_photo_config = {}
fotos_global_state = {}
reels_global_state = {}

# ======================
# IDIOMAS POR DEFECTO
# ======================

DEFAULT_LANGUAGES = {
    "italian": {"name": "🇮🇹 Italiano", "code": "it",
        "replacements": {
            "[MEN]": "uomini italiani", "[MEN_SINGULAR]": "un uomo italiano", "[COUNTRY]": "Italia",
            "[COUNTRY_ADJ]": "italiana", "[FLAG]": "🇮🇹", "[FOOD]": "pasta e pizza",
            "[CULTURE]": "la Dolce Vita", "[LOVE_SYMBOL]": "🍝"
        }
    },
    "german": {"name": "🇩🇪 Deutsch", "code": "de",
        "replacements": {
            "[MEN]": "deutsche Männer", "[MEN_SINGULAR]": "ein deutscher Mann", "[COUNTRY]": "Deutschland",
            "[COUNTRY_ADJ]": "deutsche", "[FLAG]": "🇩🇪", "[FOOD]": "Bratwurst",
            "[CULTURE]": "Oktoberfest", "[LOVE_SYMBOL]": "🍺"
        }
    },
    "english": {"name": "🇺🇸 English", "code": "en",
        "replacements": {
            "[MEN]": "American men", "[MEN_SINGULAR]": "an American man", "[COUNTRY]": "USA",
            "[COUNTRY_ADJ]": "American", "[FLAG]": "🇺🇸", "[FOOD]": "burgers",
            "[CULTURE]": "Hollywood", "[LOVE_SYMBOL]": "💕"
        }
    },
    "spanish": {"name": "🇪🇸 Español", "code": "es",
        "replacements": {
            "[MEN]": "hombres españoles", "[MEN_SINGULAR]": "un hombre español", "[COUNTRY]": "España",
            "[COUNTRY_ADJ]": "española", "[FLAG]": "🇪🇸", "[FOOD]": "paella",
            "[CULTURE]": "flamenco", "[LOVE_SYMBOL]": "💃"
        }
    },
    "french": {"name": "🇫🇷 Français", "code": "fr",
        "replacements": {
            "[MEN]": "hommes français", "[MEN_SINGULAR]": "un homme français", "[COUNTRY]": "France",
            "[COUNTRY_ADJ]": "française", "[FLAG]": "🇫🇷", "[FOOD]": "croissant",
            "[CULTURE]": "l'élégance", "[LOVE_SYMBOL]": "🥖"
        }
    }
}

# ======================
# FUNCIONES DE CARGA/GUARDADO
# ======================

def load_json(file_path, default):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Cargar datos
THREADS_MODELS = load_json(THREADS_MODELS_FILE, {
    "mila": {"name": "🇨🇳 Mila", "origin": "China", "origin_text": "I'm Chinese", "full_name": "Mila"},
    "yuna": {"name": "🇯🇵 Yuna", "origin": "Japan", "origin_text": "I'm Japanese", "full_name": "Yuna"},
    "ita": {"name": "🇮🇹 ITA Models", "origin": "Italy", "origin_text": "I'm Italian", "full_name": "ITA Models"},
    "comments": {"name": "💬 Comments", "origin": "None", "origin_text": "", "full_name": "Comment"}
})

PHOTO_CATEGORIES = load_json(PHOTO_CATEGORIES_FILE, {
    "asian": {"name": "🇦🇸 Asian", "models": {}},
    "italian": {"name": "🇮🇹 Italian", "models": {}}
})

CUSTOM_LANGUAGES = load_json(CUSTOM_LANGUAGES_FILE, {})
LANGUAGES = {**DEFAULT_LANGUAGES, **CUSTOM_LANGUAGES}

fotos_global_state = load_json(PHOTOS_DB_FILE, {})
reels_global_state = load_json(REELS_DB_FILE, {})
user_config = load_json(USER_CONFIG_FILE, {})
user_threads_state = load_json(USER_STATE_FILE, {})

# ======================
# FUNCIONES DE AYUDA
# ======================

def save_all():
    save_json(THREADS_MODELS_FILE, THREADS_MODELS)
    save_json(PHOTO_CATEGORIES_FILE, PHOTO_CATEGORIES)
    save_json(CUSTOM_LANGUAGES_FILE, CUSTOM_LANGUAGES)
    save_json(PHOTOS_DB_FILE, fotos_global_state)
    save_json(REELS_DB_FILE, reels_global_state)
    save_json(USER_CONFIG_FILE, user_config)
    save_json(USER_STATE_FILE, user_threads_state)

def get_user_cfg(user_id):
    uid = str(user_id)
    if uid not in user_config:
        user_config[uid] = {"threads_model": "mila", "threads_language": "italian"}
        save_all()
    return user_config[uid]

def set_user_cfg(user_id, model=None, lang=None):
    uid = str(user_id)
    if uid not in user_config:
        user_config[uid] = {"threads_model": "mila", "threads_language": "italian"}
    if model:
        user_config[uid]["threads_model"] = model
    if lang:
        user_config[uid]["threads_language"] = lang
    save_all()

def get_photo_cfg(user_id):
    uid = str(user_id)
    if uid not in user_photo_config:
        user_photo_config[uid] = {"photo_model": None, "waiting": False}
    return user_photo_config[uid]

def set_photo_cfg(user_id, model=None, waiting=False):
    uid = str(user_id)
    user_photo_config[uid] = {"photo_model": model, "waiting": waiting}
    save_all()

# ======================
# FUNCIONES THREADS
# ======================

def get_user_state(user_id):
    uid = str(user_id)
    if uid not in user_threads_state:
        user_threads_state[uid] = {"sent": [], "total": 0}
        save_all()
    return user_threads_state[uid]

def save_user_state(user_id, sent, total):
    uid = str(user_id)
    user_threads_state[uid] = {"sent": list(sent), "total": total}
    save_all()

def get_numbers(user_id, qty):
    state = get_user_state(user_id)
    used = set(state["sent"])
    available = [n for n in range(1, 51) if n not in used]
    if not available:
        used = set()
        available = list(range(1, 51))
    random.shuffle(available)
    return available[:qty], used

def mark_sent(user_id, numbers):
    state = get_user_state(user_id)
    used = set(state["sent"])
    used.update(numbers)
    new_total = state["total"] + len(numbers)
    save_user_state(user_id, used, new_total)

# ======================
# FUNCIONES FOTOS
# ======================

def add_photo(model, path):
    if model not in fotos_global_state:
        fotos_global_state[model] = {"total": 0, "available": [], "used": [], "meta": {}}
    new_id = fotos_global_state[model]["total"] + 1
    ext = os.path.splitext(path)[1]
    new_path = os.path.join(PHOTOS_FOLDER, f"{model}_{new_id}{ext}")
    shutil.copy2(path, new_path)
    fotos_global_state[model]["meta"][str(new_id)] = {"path": new_path, "used": False}
    fotos_global_state[model]["total"] += 1
    fotos_global_state[model]["available"].append(new_id)
    save_all()

def get_photos(model, qty):
    if model not in fotos_global_state:
        return []
    available = [int(i) for i, m in fotos_global_state[model]["meta"].items() if not m["used"]]
    random.shuffle(available)
    return available[:qty]

def mark_photos_used(model, ids):
    if model not in fotos_global_state:
        return
    for fid in ids:
        fid_str = str(fid)
        if fid_str in fotos_global_state[model]["meta"]:
            fotos_global_state[model]["meta"][fid_str]["used"] = True
            if fid in fotos_global_state[model]["available"]:
                fotos_global_state[model]["available"].remove(fid)
            fotos_global_state[model]["used"].append(fid)
    save_all()

def get_photo_stats(model):
    if model not in fotos_global_state:
        return 0, 0, 0
    used = len(fotos_global_state[model]["used"])
    avail = len([m for m in fotos_global_state[model]["meta"].values() if not m["used"]])
    total = fotos_global_state[model]["total"]
    return used, avail, total

# ======================
# FUNCIONES REELS
# ======================

def add_reel(iguser, path):
    if iguser not in reels_global_state:
        reels_global_state[iguser] = {"total": 0, "available": [], "used": [], "meta": {}}
    new_id = reels_global_state[iguser]["total"] + 1
    ext = os.path.splitext(path)[1]
    new_path = os.path.join(REELS_FOLDER, f"{iguser}_{new_id}{ext}")
    shutil.copy2(path, new_path)
    reels_global_state[iguser]["meta"][str(new_id)] = {"path": new_path, "used": False}
    reels_global_state[iguser]["total"] += 1
    reels_global_state[iguser]["available"].append(new_id)
    save_all()

def get_reel(iguser):
    if iguser not in reels_global_state:
        return None
    available = [int(i) for i, m in reels_global_state[iguser]["meta"].items() if not m["used"]]
    if not available:
        return None
    random.shuffle(available)
    return available[0]

def mark_reel_used(iguser, rid):
    if iguser not in reels_global_state:
        return
    rid_str = str(rid)
    if rid_str in reels_global_state[iguser]["meta"]:
        reels_global_state[iguser]["meta"][rid_str]["used"] = True
        if rid in reels_global_state[iguser]["available"]:
            reels_global_state[iguser]["available"].remove(rid)
        reels_global_state[iguser]["used"].append(rid)
    save_all()

def get_reel_stats(iguser):
    if iguser not in reels_global_state:
        return 0, 0, 0
    used = len(reels_global_state[iguser]["used"])
    avail = len([m for m in reels_global_state[iguser]["meta"].values() if not m["used"]])
    total = reels_global_state[iguser]["total"]
    return used, avail, total

# ======================
# NOTIFICACIONES
# ======================

async def notify_admin(context, msg, is_admin=False):
    try:
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"{'👑 ADMIN: ' if is_admin else ''}{msg}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Notify error: {e}")

# ======================
# CREACIÓN DE MODELOS (CORREGIDO)
# ======================

async def add_threads_model_start(update, context):
    query = update.callback_query
    await query.answer()
    waiting_for_new_threads_model[ADMIN_USER_ID] = {"step": "name"}
    await query.edit_message_text(
        "➕ <b>Add Threads Model</b>\n\nSend model name with emoji.\nExample: 🇰🇷 Hana\n\nType /cancel to abort.",
        parse_mode="HTML"
    )

async def add_threads_model_input(update, context):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID or uid not in waiting_for_new_threads_model:
        return
    if update.message.text.startswith('/'):
        if update.message.text.lower() == '/cancel':
            del waiting_for_new_threads_model[uid]
            await update.message.reply_text("❌ Cancelled.")
            await admin_menu(update, context)
        return
    state = waiting_for_new_threads_model[uid]
    text = update.message.text.strip()
    
    if state["step"] == "name":
        key = text.lower().replace(" ", "_").replace("🇨🇳", "").replace("🇯🇵", "").replace("🇮🇹", "").replace("🇰🇷", "").strip()
        if not key:
            key = text.lower().replace(" ", "_")
        orig = key
        cnt = 1
        while key in THREADS_MODELS:
            key = f"{orig}_{cnt}"
            cnt += 1
        state["key"] = key
        state["name"] = text
        state["step"] = "origin"
        await update.message.reply_text(f"✅ Name: {text}\nKey: {key}\n\nSend country of origin.\nExample: Korea", parse_mode="HTML")
    elif state["step"] == "origin":
        state["origin"] = text
        state["step"] = "origin_text"
        await update.message.reply_text(f"✅ Origin: {text}\n\nSend origin text.\nExample: I'm Korean", parse_mode="HTML")
    elif state["step"] == "origin_text":
        state["origin_text"] = text
        state["step"] = "full_name"
        await update.message.reply_text(f"✅ Origin text: {text}\n\nSend full name.\nExample: Hana", parse_mode="HTML")
    elif state["step"] == "full_name":
        state["full_name"] = text
        THREADS_MODELS[state["key"]] = {
            "name": state["name"],
            "origin": state["origin"],
            "origin_text": state["origin_text"],
            "full_name": state["full_name"]
        }
        save_all()
        await update.message.reply_text(
            f"✅ <b>Threads model added!</b>\n\n📝 {state['name']}\n🔑 {state['key']}\n🌍 {state['origin']}\n\nUse /admin → Upload Threads to add phrases.",
            parse_mode="HTML"
        )
        await notify_admin(context, f"➕ Added threads model: {state['name']}", True)
        del waiting_for_new_threads_model[uid]

async def add_photo_category_start(update, context):
    query = update.callback_query
    await query.answer()
    waiting_for_new_photo_category[ADMIN_USER_ID] = {"step": "name"}
    await query.edit_message_text(
        "➕ <b>Add Photo Category</b>\n\nSend category name with emoji.\nExample: 🇫🇷 French\n\nType /cancel to abort.",
        parse_mode="HTML"
    )

async def add_photo_category_input(update, context):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID or uid not in waiting_for_new_photo_category:
        return
    if update.message.text.startswith('/'):
        if update.message.text.lower() == '/cancel':
            del waiting_for_new_photo_category[uid]
            await update.message.reply_text("❌ Cancelled.")
            await admin_menu(update, context)
        return
    text = update.message.text.strip()
    key = text.lower().replace(" ", "_").replace("🇫🇷", "").replace("🇪🇸", "").strip()
    if not key:
        key = text.lower().replace(" ", "_")
    orig = key
    cnt = 1
    while key in PHOTO_CATEGORIES:
        key = f"{orig}_{cnt}"
        cnt += 1
    PHOTO_CATEGORIES[key] = {"name": text, "models": {}}
    save_all()
    await update.message.reply_text(f"✅ <b>Photo category added!</b>\n\n📁 {text}\n🔑 {key}", parse_mode="HTML")
    await notify_admin(context, f"➕ Added photo category: {text}", True)
    del waiting_for_new_photo_category[uid]

async def add_photo_model_start(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for k, v in PHOTO_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(v["name"], callback_data=f"add_photo_model_cat_{k}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    await query.edit_message_text("➕ <b>Add Photo Model</b>\n\nSelect category:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def add_photo_model_cat(update, context, cat_key):
    query = update.callback_query
    await query.answer()
    waiting_for_new_photo_model[ADMIN_USER_ID] = {"step": "name", "cat_key": cat_key}
    await query.edit_message_text(
        f"➕ <b>Add Model to {PHOTO_CATEGORIES[cat_key]['name']}</b>\n\nSend model name with emoji.\nExample: 🇰🇷 Jiyeon\n\nType /cancel to abort.",
        parse_mode="HTML"
    )

async def add_photo_model_input(update, context):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID or uid not in waiting_for_new_photo_model:
        return
    if update.message.text.startswith('/'):
        if update.message.text.lower() == '/cancel':
            del waiting_for_new_photo_model[uid]
            await update.message.reply_text("❌ Cancelled.")
            await admin_menu(update, context)
        return
    state = waiting_for_new_photo_model[uid]
    text = update.message.text.strip()
    key = text.lower().replace(" ", "_").replace("🇨🇳", "").replace("🇯🇵", "").replace("🇮🇹", "").replace("🇰🇷", "").replace("🇫🇷", "").strip()
    if not key:
        key = text.lower().replace(" ", "_")
    orig = key
    cnt = 1
    while key in PHOTO_CATEGORIES[state["cat_key"]]["models"]:
        key = f"{orig}_{cnt}"
        cnt += 1
    PHOTO_CATEGORIES[state["cat_key"]]["models"][key] = {"name": text, "display": text}
    if key not in fotos_global_state:
        fotos_global_state[key] = {"total": 0, "available": [], "used": [], "meta": {}}
    save_all()
    await update.message.reply_text(f"✅ <b>Photo model added!</b>\n\n📸 {text}\n🔑 {key}\n📁 {PHOTO_CATEGORIES[state['cat_key']]['name']}", parse_mode="HTML")
    await notify_admin(context, f"➕ Added photo model: {text}", True)
    del waiting_for_new_photo_model[uid]

async def add_language_start(update, context):
    query = update.callback_query
    await query.answer()
    waiting_for_new_language[ADMIN_USER_ID] = {"step": "key"}
    await query.edit_message_text(
        "➕ <b>Add Language</b>\n\nSend language key (lowercase).\nExample: dutch\n\nType /cancel to abort.",
        parse_mode="HTML"
    )

async def add_language_input(update, context):
    global LANGUAGES
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID or uid not in waiting_for_new_language:
        return
    if update.message.text.startswith('/'):
        if update.message.text.lower() == '/cancel':
            del waiting_for_new_language[uid]
            await update.message.reply_text("❌ Cancelled.")
            await admin_menu(update, context)
        return
    state = waiting_for_new_language[uid]
    text = update.message.text.strip()
    
    if state["step"] == "key":
        if not text.isalpha():
            await update.message.reply_text("❌ Key must be letters only. Try again.")
            return
        state["key"] = text.lower()
        state["step"] = "name"
        await update.message.reply_text(f"✅ Key: {text.lower()}\n\nSend display name with emoji.\nExample: 🇳🇱 Nederlands", parse_mode="HTML")
    elif state["step"] == "name":
        state["name"] = text
        state["step"] = "code"
        await update.message.reply_text(f"✅ Name: {text}\n\nSend language code (ISO).\nExample: nl", parse_mode="HTML")
    elif state["step"] == "code":
        state["code"] = text.lower()
        state["step"] = "men"
        await update.message.reply_text(
            "✅ Code saved.\n\nNow send replacements as JSON:\n"
            '{"[MEN]": "Dutch men", "[MEN_SINGULAR]": "a Dutch man", "[COUNTRY]": "Netherlands", "[COUNTRY_ADJ]": "Dutch", "[FLAG]": "🇳🇱", "[FOOD]": "stroopwafels", "[CULTURE]": "bicycles", "[LOVE_SYMBOL]": "🌷"}',
            parse_mode="HTML"
        )
    elif state["step"] == "men":
        try:
            reps = json.loads(text)
            required = ["[MEN]", "[MEN_SINGULAR]", "[COUNTRY]", "[COUNTRY_ADJ]", "[FLAG]", "[FOOD]", "[CULTURE]", "[LOVE_SYMBOL]"]
            missing = [r for r in required if r not in reps]
            if missing:
                await update.message.reply_text(f"❌ Missing keys: {missing}\nTry again.")
                return
            CUSTOM_LANGUAGES[state["key"]] = {
                "name": state["name"],
                "code": state["code"],
                "replacements": reps
            }
            save_all()
            LANGUAGES = {**DEFAULT_LANGUAGES, **CUSTOM_LANGUAGES}
            await update.message.reply_text(f"✅ <b>Language added!</b>\n\n🌍 {state['name']}\n🔑 {state['key']}\n📇 {state['code']}", parse_mode="HTML")
            await notify_admin(context, f"➕ Added language: {state['name']}", True)
            del waiting_for_new_language[uid]
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON. Try again.")

# ======================
# MENUS
# ======================

async def admin_menu(update, context):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin.")
        return
    keyboard = [
        [InlineKeyboardButton("📝 Upload Threads", callback_data="admin_threads")],
        [InlineKeyboardButton("📸 Upload Photos", callback_data="admin_photos")],
        [InlineKeyboardButton("🎬 Upload Reels", callback_data="admin_reels")],
        [InlineKeyboardButton("➕ Add Threads Model", callback_data="admin_add_threads")],
        [InlineKeyboardButton("➕ Add Photo Category", callback_data="admin_add_photo_cat")],
        [InlineKeyboardButton("➕ Add Photo Model", callback_data="admin_add_photo_model")],
        [InlineKeyboardButton("➕ Add Language", callback_data="admin_add_language")],
        [InlineKeyboardButton("🔄 Reset Photos", callback_data="admin_reset_photos")],
        [InlineKeyboardButton("🔄 Reset Reels", callback_data="admin_reset_reels")]
    ]
    await update.message.reply_text("👑 <b>Admin Menu</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def user_menu(update, context):
    keyboard = [
        [InlineKeyboardButton("📝 Threads", callback_data="user_threads")],
        [InlineKeyboardButton("📸 Photos", callback_data="user_photos")],
        [InlineKeyboardButton("🎬 Reels", callback_data="user_reels")]
    ]
    await update.message.reply_text("📱 <b>Main Menu</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ======================
# CALLBACK HANDLER (CORREGIDO)
# ======================

async def handle_callback(update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # NAVEGACIÓN (ARREGLADO)
    if data == "admin_back":
        await admin_menu(update, context)
        return
    if data == "user_back":
        await user_menu(update, context)
        return
    
    # ADMIN - THREADS
    if data == "admin_threads":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"admin_upload_threads_{k}")] for k, v in THREADS_MODELS.items()]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
        await query.edit_message_text("📝 Select model:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("admin_upload_threads_"):
        model = data.replace("admin_upload_threads_", "")
        waiting_for_file[user_id] = model
        await query.edit_message_text(f"📁 Send .txt file for {THREADS_MODELS[model]['name']}\n\nFormat: 1. text\n2. text\n...", parse_mode="HTML")
    
    # ADMIN - PHOTOS
    elif data == "admin_photos":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"admin_photos_cat_{k}")] for k, v in PHOTO_CATEGORIES.items()]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
        await query.edit_message_text("📸 Select category:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("admin_photos_cat_"):
        cat = data.replace("admin_photos_cat_", "")
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"admin_upload_photo_{k}")] for k, v in PHOTO_CATEGORIES[cat]["models"].items()]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_photos")])
        await query.edit_message_text(f"📸 Select model for {PHOTO_CATEGORIES[cat]['name']}:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("admin_upload_photo_"):
        model = data.replace("admin_upload_photo_", "")
        waiting_for_photo_upload[user_id] = model
        if user_id not in pending_uploads:
            pending_uploads[user_id] = {"type": "photos", "target": model, "files": []}
        await query.edit_message_text(f"📸 Send photos for {model}\nWhen done, type /done", parse_mode="HTML")
    
    # ADMIN - REELS
    elif data == "admin_reels":
        await query.edit_message_text("🎬 Type Instagram username for reels.\nExample: bellamoreno\n\nThen send videos. When done, type /done", parse_mode="HTML")
        waiting_for_reels_iguser[user_id] = True
    
    # ADMIN - ADD (CORREGIDO)
    elif data == "admin_add_threads":
        await add_threads_model_start(update, context)
    elif data == "admin_add_photo_cat":
        await add_photo_category_start(update, context)
    elif data == "admin_add_photo_model":
        await add_photo_model_start(update, context)
    elif data.startswith("add_photo_model_cat_"):
        cat = data.replace("add_photo_model_cat_", "")
        await add_photo_model_cat(update, context, cat)
    elif data == "admin_add_language":
        await add_language_start(update, context)
    
    # ADMIN - RESET (SIMPLIFICADO)
    elif data == "admin_reset_photos":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"reset_photo_{k}")] for cat in PHOTO_CATEGORIES.values() for k, v in cat["models"].items()]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
        await query.edit_message_text("🔄 Select model to reset:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data == "admin_reset_reels":
        users = list(reels_global_state.keys())
        if not users:
            await query.edit_message_text("❌ No reels found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]), parse_mode="HTML")
            return
        keyboard = [[InlineKeyboardButton(f"@{u}", callback_data=f"reset_reel_{u}")] for u in users]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
        await query.edit_message_text("🔄 Select user to reset:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("reset_photo_"):
        model = data.replace("reset_photo_", "")
        if model in fotos_global_state:
            for m in fotos_global_state[model]["meta"].values():
                if os.path.exists(m["path"]):
                    try: os.unlink(m["path"])
                    except: pass
            fotos_global_state[model] = {"total": 0, "available": [], "used": [], "meta": {}}
            save_all()
        await query.edit_message_text(f"✅ Photos for {model} reset.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]), parse_mode="HTML")
    elif data.startswith("reset_reel_"):
        iguser = data.replace("reset_reel_", "")
        if iguser in reels_global_state:
            for m in reels_global_state[iguser]["meta"].values():
                if os.path.exists(m["path"]):
                    try: os.unlink(m["path"])
                    except: pass
            reels_global_state[iguser] = {"total": 0, "available": [], "used": [], "meta": {}}
            save_all()
        await query.edit_message_text(f"✅ Reels for @{iguser} reset.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]), parse_mode="HTML")
    
    # USUARIO - THREADS
    elif data == "user_threads":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"user_threads_model_{k}")] for k, v in THREADS_MODELS.items()]
        await query.edit_message_text("🌸 Choose model:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("user_threads_model_"):
        model = data.replace("user_threads_model_", "")
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"user_threads_lang_{model}_{k}")] for k, v in LANGUAGES.items()]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_threads")])
        await query.edit_message_text(f"🌍 Choose language for {THREADS_MODELS[model]['name']}:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("user_threads_lang_"):
        parts = data.split("_")
        model = parts[3]
        lang = parts[4]
        set_user_cfg(user_id, model=model, lang=lang)
        await query.edit_message_text(f"✅ Configured!\n\n🌸 {THREADS_MODELS[model]['name']}\n🌍 {LANGUAGES[lang]['name']}\n\nNow type number of threads (e.g., 5)", parse_mode="HTML")
    
    # USUARIO - PHOTOS
    elif data == "user_photos":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"user_photos_cat_{k}")] for k, v in PHOTO_CATEGORIES.items()]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_back")])
        await query.edit_message_text("📸 Select category:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("user_photos_cat_"):
        cat = data.replace("user_photos_cat_", "")
        models = PHOTO_CATEGORIES[cat]["models"]
        keyboard = []
        for k, v in models.items():
            _, avail, _ = get_photo_stats(k)
            icon = "🟢" if avail > 0 else "🔴"
            keyboard.append([InlineKeyboardButton(f"{icon} {v['name']}", callback_data=f"user_photo_model_{k}")])
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_photos")])
        await query.edit_message_text(f"📸 Select model for {PHOTO_CATEGORIES[cat]['name']}:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("user_photo_model_"):
        model = data.replace("user_photo_model_", "")
        set_photo_cfg(user_id, model=model, waiting=True)
        name = next((v["name"] for cat in PHOTO_CATEGORIES.values() for k, v in cat["models"].items() if k == model), model)
        await query.edit_message_text(f"✅ {name} selected!\n\nNow type number of photos (e.g., 3)\n⚠️ ONE-TIME USE!", parse_mode="HTML")
    
    # USUARIO - REELS
    elif data == "user_reels":
        await query.edit_message_text("🎬 Type Instagram username.\nExample: bellamoreno\n\nYou'll get ONE reel (one-time use).", parse_mode="HTML")
        context.user_data["waiting_reel"] = True

# ======================
# HANDLERS DE TEXTO
# ======================

async def handle_text(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Admin creación
    if user_id == ADMIN_USER_ID:
        if user_id in waiting_for_new_threads_model:
            await add_threads_model_input(update, context)
            return
        if user_id in waiting_for_new_photo_category:
            await add_photo_category_input(update, context)
            return
        if user_id in waiting_for_new_photo_model:
            await add_photo_model_input(update, context)
            return
        if user_id in waiting_for_new_language:
            await add_language_input(update, context)
            return
        if user_id in waiting_for_reels_iguser:
            iguser = text.lower()
            if iguser:
                del waiting_for_reels_iguser[user_id]
                waiting_for_reel_upload[user_id] = iguser
                if user_id not in pending_uploads:
                    pending_uploads[user_id] = {"type": "reels", "target": iguser, "files": []}
                await update.message.reply_text(f"🎬 Uploading reels for @{iguser}\nSend videos. When done, type /done", parse_mode="HTML")
            return
    
    # Usuario reels
    if context.user_data.get("waiting_reel"):
        context.user_data["waiting_reel"] = False
        iguser = text.lower()
        if not iguser:
            await update.message.reply_text("❌ Type valid username.")
            return
        used, avail, total = get_reel_stats(iguser)
        if avail <= THRESHOLD_REELS and avail > 0:
            await notify_admin(context, f"⚠️ LOW REELS @{iguser}: {avail} left", True)
        if avail == 0:
            await update.message.reply_text(f"❌ No reels for @{iguser}.")
            return
        rid = get_reel(iguser)
        if rid:
            path = reels_global_state[iguser]["meta"][str(rid)]["path"]
            if path and os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        await update.message.reply_video(video=f, caption=f"🎬 Reel from @{iguser}")
                    mark_reel_used(iguser, rid)
                    await notify_admin(context, f"🎬 @{update.effective_user.username} got reel from @{iguser}")
                    await update.message.reply_text(f"✅ Reel sent!", parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Reel error: {e}")
                    await update.message.reply_text("❌ Error sending reel.")
            else:
                await update.message.reply_text("❌ Reel file missing.")
        else:
            await update.message.reply_text("❌ No reels available.")
        return
    
    # Números para threads/fotos
    if text.isdigit():
        qty = int(text)
        if qty < 1 or qty > 50:
            await update.message.reply_text("❌ Number 1-50")
            return
        cfg = get_photo_cfg(user_id)
        if cfg.get("waiting"):
            model = cfg.get("photo_model")
            if model:
                used, avail, total = get_photo_stats(model)
                if avail <= THRESHOLD_FOTOS and avail > 0:
                    await notify_admin(context, f"⚠️ LOW PHOTOS {model}: {avail} left", True)
                if avail == 0:
                    await update.message.reply_text(f"❌ No photos for {model}.")
                    set_photo_cfg(user_id, waiting=False)
                    return
                if qty > avail:
                    await update.message.reply_text(f"⚠️ Only {avail} available. Sending {avail}.")
                    qty = avail
                ids = get_photos(model, qty)
                await update.message.reply_text(f"📸 Sending {len(ids)} photos...")
                sent = []
                for i, fid in enumerate(ids, 1):
                    path = fotos_global_state[model]["meta"][str(fid)]["path"]
                    if path and os.path.exists(path):
                        try:
                            with open(path, 'rb') as f:
                                await update.message.reply_photo(photo=f, caption=f"📸 Photo {i}/{len(ids)}")
                            sent.append(fid)
                            await asyncio.sleep(0.3)
                        except Exception as e:
                            logger.error(f"Photo error: {e}")
                if sent:
                    mark_photos_used(model, sent)
                await update.message.reply_text(f"✅ Sent {len(sent)} photos!", parse_mode="HTML")
                set_photo_cfg(user_id, waiting=False)
            return
        
        # Threads
        numbers, used = get_numbers(user_id, qty)
        cfg = get_user_cfg(user_id)
        model = cfg["threads_model"]
        lang = cfg["threads_language"]
        
        await update.message.reply_text(f"🎲 Generating {len(numbers)} threads for {THREADS_MODELS[model]['name']} in {LANGUAGES[lang]['name']}...", parse_mode="HTML")
        sent = []
        for i, num in enumerate(numbers):
            await update.message.reply_text(f"📝 Thread {num}/50\n\nSample text...", parse_mode="HTML")
            sent.append(num)
            await asyncio.sleep(0.5)
        mark_sent(user_id, sent)
        total = get_user_state(user_id)["total"]
        await update.message.reply_text(f"✅ Sent {len(sent)} threads!\n📊 Total: {total}", parse_mode="HTML")

# ======================
# HANDLERS DE ARCHIVOS
# ======================

async def receive_file(update, context):
    uid = update.effective_user.id
    if uid not in waiting_for_file:
        return
    model = waiting_for_file[uid]
    if not update.message.document or not update.message.document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Send .txt file")
        return
    msg = await update.message.reply_text("📥 Processing...")
    try:
        file = await context.bot.get_file(update.message.document.file_id)
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', encoding='utf-8', delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            with open(tmp.name, 'r', encoding='utf-8') as f:
                content = f.read()
        os.unlink(tmp.name)
        
        frases = []
        lines = content.strip().split('\n')
        curr_num = None
        curr_text = []
        for line in lines:
            line = line.rstrip('\n\r')
            m = re.match(r'^(\d{1,2})\.\s+(.*)', line)
            if m:
                if curr_num is not None and curr_text:
                    frases.append({"numero": curr_num, "testo": "\n".join(curr_text).strip()})
                curr_num = int(m.group(1))
                curr_text = [m.group(2)]
            else:
                if curr_text is not None:
                    curr_text.append(line)
        if curr_num is not None and curr_text:
            frases.append({"numero": curr_num, "testo": "\n".join(curr_text).strip()})
        
        if not frases:
            await msg.edit_text("❌ No numbered phrases found.")
            return
        
        save_json(os.path.join(DATA_FOLDER, f"frases_{model}.json"), frases)
        del waiting_for_file[uid]
        preview = "\n".join([f"📌 {f['numero']}: {f['testo'][:50]}..." for f in frases[:3]])
        await msg.edit_text(f"✅ Loaded {len(frases)} phrases for {THREADS_MODELS[model]['name']}\n\n{preview}", parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def receive_media(update, context):
    uid = update.effective_user.id
    if uid not in waiting_for_reel_upload and uid not in waiting_for_photo_upload:
        return
    if uid not in pending_uploads:
        return
    added = 0
    temp_path = None
    if update.message.video:
        file = await context.bot.get_file(update.message.video.file_id)
        ext = ".mp4"
        temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}{ext}"
        await file.download_to_drive(temp_path)
        added = 1
    elif update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}.jpg"
        await file.download_to_drive(temp_path)
        added = 1
    elif update.message.document:
        doc = update.message.document
        fname = doc.file_name or ""
        ext = os.path.splitext(fname)[1].lower()
        mime = doc.mime_type or ""
        if ext in ['.mov', '.mp4', '.avi'] or mime.startswith('video/') or ext in ['.jpg', '.jpeg', '.png'] or mime.startswith('image/'):
            file = await context.bot.get_file(doc.file_id)
            temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}{ext}"
            await file.download_to_drive(temp_path)
            added = 1
    if added and temp_path:
        pending_uploads[uid]["files"].append(temp_path)
        total = len(pending_uploads[uid]["files"])
        if total % 10 == 0:
            await update.message.reply_text(f"📦 Loaded {total} files.", parse_mode="HTML")

async def done_upload(update, context):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin.")
        return
    if uid not in pending_uploads or not pending_uploads[uid]["files"]:
        await update.message.reply_text("❌ No files to process.\nUse /admin first.")
        return
    upload = pending_uploads[uid]
    type_ = upload["type"]
    target = upload["target"]
    files = upload["files"]
    msg = await update.message.reply_text(f"📥 Processing {len(files)} files...")
    ok = 0
    for path in files:
        try:
            if type_ == "photos":
                add_photo(target, path)
            else:
                add_reel(target, path)
            ok += 1
        except Exception as e:
            logger.error(f"Error: {e}")
        if os.path.exists(path):
            try:
                os.unlink(path)
            except:
                pass
    del pending_uploads[uid]
    if type_ == "photos":
        used, avail, total = get_photo_stats(target)
        await msg.edit_text(f"✅ Loaded {ok}/{len(files)} photos for {target}\n📊 Total: {total}, Available: {avail}", parse_mode="HTML")
    else:
        used, avail, total = get_reel_stats(target)
        await msg.edit_text(f"✅ Loaded {ok}/{len(files)} reels for @{target}\n📊 Total: {total}, Available: {avail}", parse_mode="HTML")
    await notify_admin(context, f"📦 Loaded {ok} files for {target}", True)

# ======================
# COMANDOS BASE
# ======================

async def start(update, context):
    user = update.effective_user
    uid = user.id
    name = user.username or user.first_name
    if uid != ADMIN_USER_ID:
        await notify_admin(context, f"👤 New user: @{name}")
    cfg = get_user_cfg(uid)
    model = THREADS_MODELS[cfg["threads_model"]]["name"]
    lang = LANGUAGES[cfg["threads_language"]]["name"]
    await update.message.reply_text(
        f"Hello @{name}! 👋\n\n📱 Use /menu\n\n📊 Settings:\n🌸 Model: {model}\n🌍 Language: {lang}",
        parse_mode="HTML"
    )

async def status_cmd(update, context):
    uid = update.effective_user.id
    state = get_user_state(uid)
    total = state["total"]
    remaining = 50 - (total % 50)
    cfg = get_user_cfg(uid)
    model = THREADS_MODELS[cfg["threads_model"]]["name"]
    lang = LANGUAGES[cfg["threads_language"]]["name"]
    await update.message.reply_text(
        f"📊 Your Status\n\n🌸 Model: {model}\n🌍 Language: {lang}\n📝 Threads received: {total}\n🔄 Remaining to cycle: {remaining}",
        parse_mode="HTML"
    )

async def reset_cmd(update, context):
    uid = update.effective_user.id
    save_user_state(uid, set(), 0)
    await update.message.reply_text("🔄 Thread progress reset!")

async def menu_cmd(update, context):
    await user_menu(update, context)

# ======================
# MAIN
# ======================

def main():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    os.makedirs(PHOTOS_FOLDER, exist_ok=True)
    os.makedirs(REELS_FOLDER, exist_ok=True)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Comandos
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("done", done_upload))
    
    # Handlers
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, receive_file))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, receive_media))
    
    print("=" * 60)
    print("✅ BOT CORREGIDO")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()