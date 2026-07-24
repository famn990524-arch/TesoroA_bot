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
# CONFIGURAZIONE - VARIABLES DE ENTORNO
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado en variables de entorno")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("❌ DEEPSEEK_API_KEY no configurado en variables de entorno")

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 7097140504))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "famn25")

# Configuración de archivos y carpetas
if os.path.exists('/app'):
    DATA_FOLDER = "/app/data"
else:
    DATA_FOLDER = "."

# Archivos
THREADS_MODELS_FILE = os.path.join(DATA_FOLDER, "threads_models.json")
PHOTO_CATEGORIES_FILE = os.path.join(DATA_FOLDER, "photo_categories.json")
CUSTOM_LANGUAGES_FILE = os.path.join(DATA_FOLDER, "custom_languages.json")
PHOTOS_DB_FILE = os.path.join(DATA_FOLDER, "fotos_db.json")
USER_CONFIG_FILE = os.path.join(DATA_FOLDER, "user_config.json")
USER_STATE_FILE = os.path.join(DATA_FOLDER, "user_state.json")
PHOTOS_FOLDER = os.path.join(DATA_FOLDER, "fotos")
FRASES_FOLDER = os.path.join(DATA_FOLDER, "frases")

MAX_VARIATIONS = int(os.getenv("MAX_VARIATIONS", 50))
THRESHOLD_FOTOS = int(os.getenv("THRESHOLD_FOTOS", 40))
PHOTO_CONFIRMATION_BATCH = int(os.getenv("PHOTO_CONFIRMATION_BATCH", 50))

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Estados
waiting_for_file = {}
waiting_for_photo_upload = {}
pending_uploads = {}
waiting_for_new_threads_model = {}
waiting_for_new_photo_category = {}
waiting_for_new_photo_model = {}
waiting_for_new_language = {}
waiting_for_delete_threads_model = {}
waiting_for_delete_photo_category = {}
waiting_for_delete_photo_model = {}

# ======================
# DATOS INICIALES
# ======================

user_threads_state = {}
user_config = {}
user_photo_config = {}
fotos_global_state = {}

# Idiomas por defecto
DEFAULT_LANGUAGES = {
    "italian": {
        "name": "🇮🇹 Italiano",
        "code": "it",
        "replacements": {
            "[MEN]": "uomini italiani", "[MEN_SINGULAR]": "un uomo italiano",
            "[COUNTRY]": "Italia", "[COUNTRY_ADJ]": "italiana", "[FLAG]": "🇮🇹",
            "[FOOD]": "pasta e pizza", "[CULTURE]": "la Dolce Vita", "[LOVE_SYMBOL]": "🍝"
        }
    },
    "german": {
        "name": "🇩🇪 Deutsch",
        "code": "de",
        "replacements": {
            "[MEN]": "deutsche Männer", "[MEN_SINGULAR]": "ein deutscher Mann",
            "[COUNTRY]": "Deutschland", "[COUNTRY_ADJ]": "deutsche", "[FLAG]": "🇩🇪",
            "[FOOD]": "Bratwurst", "[CULTURE]": "Oktoberfest", "[LOVE_SYMBOL]": "🍺"
        }
    },
    "english": {
        "name": "🇺🇸 English",
        "code": "en",
        "replacements": {
            "[MEN]": "American men", "[MEN_SINGULAR]": "an American man",
            "[COUNTRY]": "USA", "[COUNTRY_ADJ]": "American", "[FLAG]": "🇺🇸",
            "[FOOD]": "burgers", "[CULTURE]": "Hollywood", "[LOVE_SYMBOL]": "💕"
        }
    },
    "spanish": {
        "name": "🇪🇸 Español",
        "code": "es",
        "replacements": {
            "[MEN]": "hombres españoles", "[MEN_SINGULAR]": "un hombre español",
            "[COUNTRY]": "España", "[COUNTRY_ADJ]": "española", "[FLAG]": "🇪🇸",
            "[FOOD]": "paella", "[CULTURE]": "flamenco", "[LOVE_SYMBOL]": "💃"
        }
    },
    "french": {
        "name": "🇫🇷 Français",
        "code": "fr",
        "replacements": {
            "[MEN]": "hommes français", "[MEN_SINGULAR]": "un homme français",
            "[COUNTRY]": "France", "[COUNTRY_ADJ]": "française", "[FLAG]": "🇫🇷",
            "[FOOD]": "croissant", "[CULTURE]": "l'élégance", "[LOVE_SYMBOL]": "🥖"
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
    "asian": {
        "name": "🇦🇸 Asian",
        "models": {
            "mila_photo": {"name": "🇨🇳 Mila", "display": "Mila"},
            "yuna_photo": {"name": "🇯🇵 Yuna", "display": "Yuna"},
            "model1": {"name": "🇨🇳 Model 1", "display": "Model 1"},
            "model2": {"name": "🇨🇳 Model 2", "display": "Model 2"},
            "model3": {"name": "🇨🇳 Model 3", "display": "Model 3"},
            "model4": {"name": "🇨🇳 Model 4", "display": "Model 4"},
            "model5": {"name": "🇨🇳 Model 5", "display": "Model 5"},
            "model6": {"name": "🇨🇳 Model 6", "display": "Model 6"},
            "model7": {"name": "🇨🇳 Model 7", "display": "Model 7"},
            "model8": {"name": "🇨🇳 Model 8", "display": "Model 8"},
            "model9": {"name": "🇨🇳 Model 9", "display": "Model 9"},
            "model10": {"name": "🇨🇳 Model 10", "display": "Model 10"},
            "model11": {"name": "🇨🇳 Model 11", "display": "Model 11"},
            "model12": {"name": "🇨🇳 Model 12", "display": "Model 12"}
        }
    },
    "italian": {
        "name": "🇮🇹 Italian",
        "models": {
            "elira": {"name": "🇮🇹 Elira", "display": "Elira"},
            "bella": {"name": "🇮🇹 Bella", "display": "Bella"},
            "milena": {"name": "🇮🇹 Milena", "display": "Milena"},
            "isabella": {"name": "🇮🇹 Isabella", "display": "Isabella"},
            "laura": {"name": "🇮🇹 Laura", "display": "Laura"},
            "aurora": {"name": "🇮🇹 Aurora", "display": "Aurora"}
        }
    }
})

CUSTOM_LANGUAGES = load_json(CUSTOM_LANGUAGES_FILE, {})
LANGUAGES = {**DEFAULT_LANGUAGES, **CUSTOM_LANGUAGES}

fotos_global_state = load_json(PHOTOS_DB_FILE, {})
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
    available = [n for n in range(1, MAX_VARIATIONS + 1) if n not in used]
    if not available:
        used = set()
        available = list(range(1, MAX_VARIATIONS + 1))
    random.shuffle(available)
    return available[:qty], used

def mark_sent(user_id, numbers):
    state = get_user_state(user_id)
    used = set(state["sent"])
    used.update(numbers)
    new_total = state["total"] + len(numbers)
    save_user_state(user_id, used, new_total)

def get_photo_stats(model):
    if model not in fotos_global_state:
        return 0, 0, 0
    used = len(fotos_global_state[model].get("used", []))
    avail = len([m for m in fotos_global_state[model].get("meta", {}).values() if not m.get("used", False)])
    total = fotos_global_state[model].get("total", 0)
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
# FUNCIONES API DEEPSEEK
# ======================

def aplicar_marcadores(texto, language):
    lang_config = LANGUAGES.get(language, DEFAULT_LANGUAGES["english"])
    replacements = lang_config.get("replacements", {})
    resultado = texto
    for marker, value in replacements.items():
        resultado = resultado.replace(marker, value)
    return resultado

async def generare_variazione(
    model,
    language,
    frase_originale,
    frase_numero,
    variazione_num
):
    model_info = THREADS_MODELS.get(
        model,
        {
            "name": model,
            "origin": "None",
            "origin_text": "",
            "full_name": model
        }
    )

    lang_info = LANGUAGES.get(
        language,
        DEFAULT_LANGUAGES["english"]
    )

    frase_con_marcadores = aplicar_marcadores(
        frase_originale,
        language
    )

    system_prompt = f"""You are a copywriter. Create ONE variation of the given phrase in {lang_info['name']}.

CRITICAL RULES:
1. Maintain EXACTLY the same structure and meaning.
2. Keep censorship as in original (use * or emojis).
3. Change words, NOT the meaning. Variation number {variazione_num}.
4. PRESERVE format: line breaks, emojis, numbers, lists.
5. Keep teen feminine tone, FIRST PERSON.
6. Adapt cultural references appropriately.
7. DO NOT add extra information.
8. Reply ONLY with the variation text.

Original phrase: {frase_con_marcadores}

Generate variation {variazione_num} in {lang_info['name']}:"""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": f"Generate variation {variazione_num}:"
        }
    ]

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "deepseek-v4-flash",
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": 800,
        "thinking": {
            "type": "disabled"
        }
    }

    timeout = aiohttp.ClientTimeout(total=90)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=payload
            ) as response:

                response_text = await response.text()

                if response.status != 200:
                    logger.error(
                        "DeepSeek API error | "
                        f"status={response.status} | "
                        f"variation={variazione_num} | "
                        f"response={response_text}"
                    )
                    return (
                        f"❌ DeepSeek API Error "
                        f"{response.status}: {response_text}"
                    )

                try:
                    result = json.loads(response_text)
                    content = result["choices"][0]["message"]["content"]

                    if not content:
                        logger.error(
                            f"DeepSeek returned empty content: {result}"
                        )
                        return "❌ DeepSeek returned empty content"

                    return content.strip()

                except (KeyError, IndexError, json.JSONDecodeError) as e:
                    logger.exception(
                        "Unexpected DeepSeek response: "
                        f"{response_text}"
                    )
                    return f"❌ Invalid DeepSeek response: {e}"

    except asyncio.TimeoutError:
        logger.error(
            f"DeepSeek timeout on variation {variazione_num}"
        )
        return "❌ DeepSeek request timed out"

    except aiohttp.ClientError as e:
        logger.exception(
            f"DeepSeek connection error: {e}"
        )
        return f"❌ DeepSeek connection error: {e}"

    except Exception as e:
        logger.exception(
            f"Unexpected DeepSeek error: {e}"
        )
        return f"❌ Unexpected error: {e}"

# ======================
# CREACIÓN DE MODELOS (THREADS)
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
            f"✅ <b>Threads model added!</b>\n\n📝 {state['name']}\n🔑 {state['key']}\n🌍 {state['origin']}",
            parse_mode="HTML"
        )
        await notify_admin(context, f"➕ Added threads model: {state['name']}", True)
        del waiting_for_new_threads_model[uid]

# ======================
# ELIMINACIÓN DE MODELOS (THREADS)
# ======================

async def delete_threads_model_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, model in THREADS_MODELS.items():
        keyboard.append([InlineKeyboardButton(f"❌ {model['name']}", callback_data=f"delete_threads_model_{key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    await query.edit_message_text(
        "🗑️ <b>Delete Threads Model</b>\n\nSelect model to delete:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def confirm_delete_threads_model(update, context, model_key):
    query = update.callback_query
    await query.answer()
    model_name = THREADS_MODELS[model_key]["name"]
    keyboard = [
        [InlineKeyboardButton("✅ YES, DELETE", callback_data=f"confirm_del_threads_{model_key}")],
        [InlineKeyboardButton("❌ NO, CANCEL", callback_data="admin_delete_threads")]
    ]
    await query.edit_message_text(
        f"⚠️ <b>Confirm Delete</b>\n\nDelete threads model: {model_name}\n\nThis will also delete all phrases for this model.\n\nAre you sure?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def execute_delete_threads_model(update, context, model_key):
    query = update.callback_query
    await query.answer()
    model_name = THREADS_MODELS[model_key]["name"]
    
    frases_file = os.path.join(DATA_FOLDER, f"frases_{model_key}.json")
    if os.path.exists(frases_file):
        os.remove(frases_file)
    
    del THREADS_MODELS[model_key]
    save_all()
    
    await query.edit_message_text(
        f"✅ <b>Threads model deleted!</b>\n\n📝 {model_name} has been removed.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]),
        parse_mode="HTML"
    )
    await notify_admin(context, f"🗑️ Deleted threads model: {model_name}", True)

# ======================
# CATEGORÍAS DE FOTOS
# ======================

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

async def delete_photo_category_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, cat in PHOTO_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(f"❌ {cat['name']}", callback_data=f"delete_photo_cat_{key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    await query.edit_message_text(
        "🗑️ <b>Delete Photo Category</b>\n\nSelect category to delete (will delete all models inside):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def confirm_delete_photo_category(update, context, cat_key):
    query = update.callback_query
    await query.answer()
    cat_name = PHOTO_CATEGORIES[cat_key]["name"]
    keyboard = [
        [InlineKeyboardButton("✅ YES, DELETE", callback_data=f"confirm_del_cat_{cat_key}")],
        [InlineKeyboardButton("❌ NO, CANCEL", callback_data="admin_delete_category")]
    ]
    await query.edit_message_text(
        f"⚠️ <b>Confirm Delete</b>\n\nDelete category: {cat_name}\n\nThis will delete ALL models and photos in this category.\n\nAre you sure?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def execute_delete_photo_category(update, context, cat_key):
    query = update.callback_query
    await query.answer()
    cat_name = PHOTO_CATEGORIES[cat_key]["name"]
    
    for model_key in list(PHOTO_CATEGORIES[cat_key]["models"].keys()):
        if model_key in fotos_global_state:
            for meta in fotos_global_state[model_key].get("meta", {}).values():
                if os.path.exists(meta["path"]):
                    try:
                        os.unlink(meta["path"])
                    except:
                        pass
            del fotos_global_state[model_key]
    
    del PHOTO_CATEGORIES[cat_key]
    save_all()
    
    await query.edit_message_text(
        f"✅ <b>Photo category deleted!</b>\n\n📁 {cat_name} has been removed.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]),
        parse_mode="HTML"
    )
    await notify_admin(context, f"🗑️ Deleted photo category: {cat_name}", True)

# ======================
# MODELOS DE FOTOS
# ======================

async def add_photo_model_start(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for k, v in PHOTO_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(v["name"], callback_data=f"add_photo_model_cat_{k}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    await query.edit_message_text(
        "➕ <b>Add Photo Model</b>\n\nSelect category:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

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
    await update.message.reply_text(
        f"✅ <b>Photo model added!</b>\n\n📸 {text}\n🔑 {key}\n📁 {PHOTO_CATEGORIES[state['cat_key']]['name']}",
        parse_mode="HTML"
    )
    await notify_admin(context, f"➕ Added photo model: {text}", True)
    del waiting_for_new_photo_model[uid]

async def delete_photo_model_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for cat_key, cat in PHOTO_CATEGORIES.items():
        for model_key, model in cat["models"].items():
            keyboard.append([InlineKeyboardButton(f"❌ {cat['name']} - {model['name']}", callback_data=f"delete_photo_model_{model_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    await query.edit_message_text(
        "🗑️ <b>Delete Photo Model</b>\n\nSelect model to delete:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def confirm_delete_photo_model(update, context, model_key):
    query = update.callback_query
    await query.answer()
    model_name = model_key
    cat_name = ""
    for cat_key, cat in PHOTO_CATEGORIES.items():
        if model_key in cat["models"]:
            model_name = cat["models"][model_key]["name"]
            cat_name = cat["name"]
            break
    keyboard = [
        [InlineKeyboardButton("✅ YES, DELETE", callback_data=f"confirm_del_model_{model_key}")],
        [InlineKeyboardButton("❌ NO, CANCEL", callback_data="admin_delete_model")]
    ]
    await query.edit_message_text(
        f"⚠️ <b>Confirm Delete</b>\n\nDelete model: {model_name}\nCategory: {cat_name}\n\nThis will delete ALL photos for this model.\n\nAre you sure?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def execute_delete_photo_model(update, context, model_key):
    query = update.callback_query
    await query.answer()
    model_name = model_key
    cat_key = None
    for ck, cat in PHOTO_CATEGORIES.items():
        if model_key in cat["models"]:
            model_name = cat["models"][model_key]["name"]
            cat_key = ck
            break
    
    if model_key in fotos_global_state:
        for meta in fotos_global_state[model_key].get("meta", {}).values():
            if os.path.exists(meta["path"]):
                try:
                    os.unlink(meta["path"])
                except:
                    pass
        del fotos_global_state[model_key]
    
    if cat_key and model_key in PHOTO_CATEGORIES[cat_key]["models"]:
        del PHOTO_CATEGORIES[cat_key]["models"][model_key]
    save_all()
    
    await query.edit_message_text(
        f"✅ <b>Photo model deleted!</b>\n\n📸 {model_name} has been removed.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]),
        parse_mode="HTML"
    )
    await notify_admin(context, f"🗑️ Deleted photo model: {model_name}", True)

# ======================
# IDIOMAS
# ======================

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
        state["step"] = "replacements"
        await update.message.reply_text(
            "✅ Code saved.\n\nNow send replacements as JSON:\n"
            '{"[MEN]": "Dutch men", "[MEN_SINGULAR]": "a Dutch man", "[COUNTRY]": "Netherlands", "[COUNTRY_ADJ]": "Dutch", "[FLAG]": "🇳🇱", "[FOOD]": "stroopwafels", "[CULTURE]": "bicycles", "[LOVE_SYMBOL]": "🌷"}',
            parse_mode="HTML"
        )
    elif state["step"] == "replacements":
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
            await update.message.reply_text(
                f"✅ <b>Language added!</b>\n\n🌍 {state['name']}\n🔑 {state['key']}\n📇 {state['code']}",
                parse_mode="HTML"
            )
            await notify_admin(context, f"➕ Added language: {state['name']}", True)
            del waiting_for_new_language[uid]
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON. Try again.")

# ======================
# SUBIR ARCHIVOS
# ======================

async def upload_threads_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, model in THREADS_MODELS.items():
        keyboard.append([InlineKeyboardButton(f"📝 {model['name']}", callback_data=f"upload_threads_{key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    await query.edit_message_text(
        "📝 <b>Upload Threads</b>\n\nSelect model to upload phrases:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def upload_photos_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for cat_key, cat in PHOTO_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(f"📁 {cat['name']}", callback_data=f"upload_photos_cat_{cat_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    await query.edit_message_text(
        "📸 <b>Upload Photos</b>\n\nSelect category:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def upload_photos_models(update, context, cat_key):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for model_key, model in PHOTO_CATEGORIES[cat_key]["models"].items():
        keyboard.append([InlineKeyboardButton(f"📸 {model['name']}", callback_data=f"upload_photo_{model_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_photos")])
    await query.edit_message_text(
        f"📸 <b>Upload Photos to {PHOTO_CATEGORIES[cat_key]['name']}</b>\n\nSelect model:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# ======================
# MENÚS PRINCIPALES
# ======================

async def admin_menu(update, context):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin can use this.")
        return
    keyboard = [
        [InlineKeyboardButton("📝 Upload Threads", callback_data="admin_upload_threads")],
        [InlineKeyboardButton("➕ Add Threads Model", callback_data="admin_add_threads")],
        [InlineKeyboardButton("🗑️ Delete Threads Model", callback_data="admin_delete_threads")],
        [InlineKeyboardButton("📸 Upload Photos", callback_data="admin_upload_photos")],
        [InlineKeyboardButton("➕ Add Photo Category", callback_data="admin_add_photo_cat")],
        [InlineKeyboardButton("🗑️ Delete Photo Category", callback_data="admin_delete_photo_cat")],
        [InlineKeyboardButton("➕ Add Photo Model", callback_data="admin_add_photo_model")],
        [InlineKeyboardButton("🗑️ Delete Photo Model", callback_data="admin_delete_photo_model")],
        [InlineKeyboardButton("🌍 Add Language", callback_data="admin_add_language")]
    ]
    await update.message.reply_text("👑 <b>Admin Menu</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def user_menu(update, context):
    keyboard = [
        [InlineKeyboardButton("📝 Threads", callback_data="user_threads")],
        [InlineKeyboardButton("📸 Photos", callback_data="user_photos")]
    ]
    await update.message.reply_text("📱 <b>Main Menu</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ======================
# CALLBACK HANDLER
# ======================

async def handle_callback(update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    user = query.from_user
    username = user.username or user.first_name
    
    # Navegación principal
    if data == "admin_back":
        await admin_menu(update, context)
        return
    if data == "user_back":
        await user_menu(update, context)
        return
    
    # ADMIN - UPLOAD THREADS
    if data == "admin_upload_threads":
        await upload_threads_menu(update, context)
        return
    if data.startswith("upload_threads_"):
        model = data.replace("upload_threads_", "")
        waiting_for_file[user_id] = model
        await query.edit_message_text(
            f"📁 Send .txt file for {THREADS_MODELS[model]['name']}\n\nFormat: 1. text\n2. text\n...",
            parse_mode="HTML"
        )
        return
    
    # ADMIN - ADD THREADS MODEL
    if data == "admin_add_threads":
        await add_threads_model_start(update, context)
        return
    
    # ADMIN - DELETE THREADS MODEL
    if data == "admin_delete_threads":
        await delete_threads_model_menu(update, context)
        return
    if data.startswith("delete_threads_model_"):
        model_key = data.replace("delete_threads_model_", "")
        await confirm_delete_threads_model(update, context, model_key)
        return
    if data.startswith("confirm_del_threads_"):
        model_key = data.replace("confirm_del_threads_", "")
        await execute_delete_threads_model(update, context, model_key)
        return
    
    # ADMIN - UPLOAD PHOTOS
    if data == "admin_upload_photos":
        await upload_photos_menu(update, context)
        return
    if data.startswith("upload_photos_cat_"):
        cat_key = data.replace("upload_photos_cat_", "")
        await upload_photos_models(update, context, cat_key)
        return
    if data.startswith("upload_photo_"):
        model = data.replace("upload_photo_", "")
        waiting_for_photo_upload[user_id] = model
        if user_id not in pending_uploads:
            pending_uploads[user_id] = {"type": "photos", "target": model, "files": []}
        await query.edit_message_text(
            f"📸 Send photos for {model}\n\nWhen done, type /done",
            parse_mode="HTML"
        )
        return
    
    # ADMIN - ADD PHOTO CATEGORY
    if data == "admin_add_photo_cat":
        await add_photo_category_start(update, context)
        return
    
    # ADMIN - DELETE PHOTO CATEGORY
    if data == "admin_delete_photo_cat":
        await delete_photo_category_menu(update, context)
        return
    if data.startswith("delete_photo_cat_"):
        cat_key = data.replace("delete_photo_cat_", "")
        await confirm_delete_photo_category(update, context, cat_key)
        return
    if data.startswith("confirm_del_cat_"):
        cat_key = data.replace("confirm_del_cat_", "")
        await execute_delete_photo_category(update, context, cat_key)
        return
    
    # ADMIN - ADD PHOTO MODEL
    if data == "admin_add_photo_model":
        await add_photo_model_start(update, context)
        return
    if data.startswith("add_photo_model_cat_"):
        cat_key = data.replace("add_photo_model_cat_", "")
        await add_photo_model_cat(update, context, cat_key)
        return
    
    # ADMIN - DELETE PHOTO MODEL
    if data == "admin_delete_photo_model":
        await delete_photo_model_menu(update, context)
        return
    if data.startswith("delete_photo_model_"):
        model_key = data.replace("delete_photo_model_", "")
        await confirm_delete_photo_model(update, context, model_key)
        return
    if data.startswith("confirm_del_model_"):
        model_key = data.replace("confirm_del_model_", "")
        await execute_delete_photo_model(update, context, model_key)
        return
    
    # ADMIN - ADD LANGUAGE
    if data == "admin_add_language":
        await add_language_start(update, context)
        return
    
    # USER - THREADS
    if data == "user_threads":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"user_threads_model_{k}")] for k, v in THREADS_MODELS.items()]
        await query.edit_message_text("🌸 Choose model:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    if data.startswith("user_threads_model_"):
        model = data.replace("user_threads_model_", "")
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"user_threads_lang_{model}_{k}")] for k, v in LANGUAGES.items()]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_threads")])
        await query.edit_message_text(f"🌍 Choose language for {THREADS_MODELS[model]['name']}:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    if data.startswith("user_threads_lang_"):
        parts = data.split("_")
        model = parts[3]
        lang = parts[4]
        set_user_cfg(user_id, model=model, lang=lang)
        
        # NOTIFICACIÓN: Usuario cambió configuración
        await notify_admin(context, f"⚙️ <b>@{username}</b> changed settings: {THREADS_MODELS[model]['name']} / {LANGUAGES[lang]['name']}")
        
        await query.edit_message_text(
            f"✅ Configured!\n\n🌸 {THREADS_MODELS[model]['name']}\n🌍 {LANGUAGES[lang]['name']}\n\nNow type number of threads (e.g., 5)",
            parse_mode="HTML"
        )
        return
    
    # USER - PHOTOS
    if data == "user_photos":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"user_photos_cat_{k}")] for k, v in PHOTO_CATEGORIES.items()]
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_back")])
        await query.edit_message_text("📸 Select category:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    if data.startswith("user_photos_cat_"):
        cat_key = data.replace("user_photos_cat_", "")
        models = PHOTO_CATEGORIES[cat_key]["models"]
        keyboard = []
        for k, v in models.items():
            _, avail, _ = get_photo_stats(k)
            icon = "🟢" if avail > 0 else "🔴"
            keyboard.append([InlineKeyboardButton(f"{icon} {v['name']}", callback_data=f"user_photo_model_{k}")])
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_photos")])
        await query.edit_message_text(f"📸 Select model for {PHOTO_CATEGORIES[cat_key]['name']}:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    if data.startswith("user_photo_model_"):
        model = data.replace("user_photo_model_", "")
        user_photo_config[user_id] = {"photo_model": model, "waiting": True}
        name = next((v["name"] for cat in PHOTO_CATEGORIES.values() for k, v in cat["models"].items() if k == model), model)
        await query.edit_message_text(
            f"✅ {name} selected!\n\nNow type number of photos (e.g., 3)\n⚠️ ONE-TIME USE!",
            parse_mode="HTML"
        )
        return

# ======================
# HANDLERS DE TEXTO Y ARCHIVOS
# ======================

async def handle_text(update, context):
    user_id = update.effective_user.id
    user = update.effective_user
    username = user.username or user.first_name
    text = update.message.text.strip()
    
    # Admin: creación de modelos
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
    
    # Números para threads/fotos
    if text.isdigit():
        qty = int(text)
        if qty < 1 or qty > MAX_VARIATIONS:
            await update.message.reply_text(f"❌ Number 1-{MAX_VARIATIONS}")
            return
        
        # Verificar si está esperando fotos
        if user_id in user_photo_config and user_photo_config[user_id].get("waiting"):
            model = user_photo_config[user_id].get("photo_model")
            if model:
                # NOTIFICACIÓN: Usuario pidió fotos
                await notify_admin(context, f"📸 <b>@{username}</b> requested {qty} photos for {model}")
                
                used, avail, total = get_photo_stats(model)
                if avail <= THRESHOLD_FOTOS and avail > 0:
                    await notify_admin(context, f"⚠️ LOW PHOTOS {model}: {avail} left", True)
                if avail == 0:
                    await update.message.reply_text(f"❌ No photos for {model}.")
                    user_photo_config[user_id]["waiting"] = False
                    return
                if qty > avail:
                    await update.message.reply_text(f"⚠️ Only {avail} available. Sending {avail}.")
                    qty = avail
                
                available = [int(i) for i, m in fotos_global_state[model]["meta"].items() if not m["used"]]
                random.shuffle(available)
                photo_ids = available[:qty]
                
                await update.message.reply_text(f"📸 Sending {len(photo_ids)} photos...")
                sent = []
                for i, fid in enumerate(photo_ids, 1):
                    path = fotos_global_state[model]["meta"][str(fid)]["path"]
                    if path and os.path.exists(path):
                        try:
                            with open(path, 'rb') as f:
                                await update.message.reply_photo(photo=f, caption=f"📸 Photo {i}/{len(photo_ids)}")
                            sent.append(fid)
                            await asyncio.sleep(0.3)
                        except Exception as e:
                            logger.error(f"Photo error: {e}")
                if sent:
                    for fid in sent:
                        fid_str = str(fid)
                        fotos_global_state[model]["meta"][fid_str]["used"] = True
                        if fid in fotos_global_state[model].get("available", []):
                            fotos_global_state[model]["available"].remove(fid)
                        fotos_global_state[model]["used"].append(fid)
                    save_all()
                await update.message.reply_text(f"✅ Sent {len(sent)} photos!", parse_mode="HTML")
                user_photo_config[user_id]["waiting"] = False
            return
        
        # Threads
        numbers, used = get_numbers(user_id, qty)
        cfg = get_user_cfg(user_id)
        model = cfg["threads_model"]
        lang = cfg["threads_language"]
        
        # NOTIFICACIÓN: Usuario pidió threads
        await notify_admin(context, f"🔄 <b>@{username}</b> requested {len(numbers)} threads | Model: {THREADS_MODELS[model]['name']} | Language: {LANGUAGES[lang]['name']}")
        
        frases_file = os.path.join(DATA_FOLDER, f"frases_{model}.json")
        if not os.path.exists(frases_file):
            await update.message.reply_text(f"❌ No phrases for {THREADS_MODELS[model]['name']}.")
            return
        with open(frases_file, 'r', encoding='utf-8') as f:
            frases = json.load(f)
        if not frases:
            await update.message.reply_text(f"❌ No phrases for {THREADS_MODELS[model]['name']}.")
            return
        
        await update.message.reply_text(f"🎲 Generating {len(numbers)} threads for {THREADS_MODELS[model]['name']} in {LANGUAGES[lang]['name']}...", parse_mode="HTML")
        sent_nums = []
        mixed = frases.copy()
        random.shuffle(mixed)
        for i, num in enumerate(numbers):
            phrase = mixed[i % len(mixed)]
            variation = await generare_variazione(model, lang, phrase["testo"], phrase["numero"], num)
            if variation and not variation.startswith("❌"):
                await update.message.reply_text(variation, parse_mode="HTML")
                sent_nums.append(num)
                await asyncio.sleep(0.5)
            else:
                await update.message.reply_text(f"❌ Error generating variation {num}")
        mark_sent(user_id, sent_nums)
        total = get_user_state(user_id)["total"]
        await update.message.reply_text(f"✅ Sent {len(sent_nums)} threads!\n📊 Total: {total}", parse_mode="HTML")

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
    if uid not in waiting_for_photo_upload:
        return
    if uid not in pending_uploads:
        return
    added = 0
    temp_path = None
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}.jpg"
        await file.download_to_drive(temp_path)
        added = 1
    elif update.message.document:
        doc = update.message.document
        fname = doc.file_name or ""
        ext = os.path.splitext(fname)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png']:
            file = await context.bot.get_file(doc.file_id)
            temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}{ext}"
            await file.download_to_drive(temp_path)
            added = 1
    if added and temp_path:
        pending_uploads[uid]["files"].append(temp_path)
        total = len(pending_uploads[uid]["files"])
        if total % PHOTO_CONFIRMATION_BATCH == 0:
            await update.message.reply_text(f"📦 Loaded {total} photos.", parse_mode="HTML")

async def done_upload(update, context):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin.")
        return
    if uid not in pending_uploads or not pending_uploads[uid]["files"]:
        await update.message.reply_text("❌ No files to process.\nUse /admin first.")
        return
    upload = pending_uploads[uid]
    target = upload["target"]
    files = upload["files"]
    msg = await update.message.reply_text(f"📥 Processing {len(files)} files...")
    ok = 0
    for path in files:
        try:
            if target not in fotos_global_state:
                fotos_global_state[target] = {"total": 0, "available": [], "used": [], "meta": {}}
            new_id = fotos_global_state[target]["total"] + 1
            ext = os.path.splitext(path)[1]
            new_path = os.path.join(PHOTOS_FOLDER, f"{target}_{new_id}{ext}")
            shutil.copy2(path, new_path)
            fotos_global_state[target]["meta"][str(new_id)] = {"path": new_path, "used": False}
            fotos_global_state[target]["total"] += 1
            fotos_global_state[target]["available"].append(new_id)
            ok += 1
        except Exception as e:
            logger.error(f"Error: {e}")
        if os.path.exists(path):
            try:
                os.unlink(path)
            except:
                pass
    save_all()
    del pending_uploads[uid]
    used, avail, total = get_photo_stats(target)
    await msg.edit_text(f"✅ Loaded {ok}/{len(files)} photos for {target}\n📊 Total: {total}, Available: {avail}", parse_mode="HTML")
    await notify_admin(context, f"📦 Loaded {ok} photos for {target}", True)

# ======================
# COMANDOS BASE
# ======================

async def start(update, context):
    user = update.effective_user
    uid = user.id
    name = user.username or user.first_name
    
    # NOTIFICACIÓN: Nuevo usuario
    if uid != ADMIN_USER_ID:
        await notify_admin(context, f"👤 <b>New user:</b> @{name} (ID: {uid})")
    
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
    remaining = MAX_VARIATIONS - (total % MAX_VARIATIONS)
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
    os.makedirs(FRASES_FOLDER, exist_ok=True)
    
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
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receive_media))
    
    print("=" * 60)
    print("✅ BOT CONFIGURADO CON VARIABLES DE ENTORNO")
    print("=" * 60)
    print(f"🤖 Bot online con token de entorno")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("=" * 60)
    print("📝 NOTIFICACIONES ACTIVAS:")
    print("  • Nuevos usuarios")
    print("  • Solicitudes de threads")
    print("  • Solicitudes de fotos")
    print("  • Cambios de configuración")
    print("  • Bajas existencias (fotos)")
    print("=" * 60)
    print("📌 VARIABLES DE ENTORNO USADAS:")
    print(f"  BOT_TOKEN: {'✅ Configurado' if BOT_TOKEN else '❌ Faltante'}")
    print(f"  DEEPSEEK_API_KEY: {'✅ Configurado' if DEEPSEEK_API_KEY else '❌ Faltante'}")
    print(f"  ADMIN_USER_ID: {ADMIN_USER_ID}")
    print(f"  ADMIN_USERNAME: {ADMIN_USERNAME}")
    print(f"  MAX_VARIATIONS: {MAX_VARIATIONS}")
    print(f"  THRESHOLD_FOTOS: {THRESHOLD_FOTOS}")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()
