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
from pathlib import Path
import time

# ======================
# CONFIGURAZIONE
# ======================

BOT_TOKEN = "8216455195:AAG8gZQRp49URVtWV10V-uw64jhSaSoGGkE"
DEEPSEEK_API_KEY = "sk-7e2b6eb1c4ff4b4aa1046a6ae500a40e"
ADMIN_USER_ID = 7097140504  # @famn25
ADMIN_USERNAME = "famn25"

# Detecta el entorno
if os.path.exists('/app'):
    DATA_FOLDER = "/app/data"
else:
    DATA_FOLDER = "."

# Archivos
USER_CONFIG_FILE = os.path.join(DATA_FOLDER, "user_config.json")
USER_STATE_FILE = os.path.join(DATA_FOLDER, "user_state.json")
USER_PHOTO_CONFIG_FILE = os.path.join(DATA_FOLDER, "user_photo_config.json")
PHOTOS_FOLDER = os.path.join(DATA_FOLDER, "fotos")
PHOTOS_DB_FILE = os.path.join(DATA_FOLDER, "fotos_db.json")

# Modelos para THREADS (solo 3)
THREADS_MODELS = {
    "mila": {
        "name": "🇨🇳 Mila",
        "origin": "Chinese",
        "origin_text": "I'm Chinese",
        "full_name": "Mila",
        "category": "threads"
    },
    "yuna": {
        "name": "🇯🇵 Yuna",
        "origin": "Japanese",
        "origin_text": "I'm Japanese",
        "full_name": "Yuna",
        "category": "threads"
    },
    "ita": {
        "name": "🇮🇹 ITA Models",
        "origin": "Italian",
        "origin_text": "I'm Italian",
        "full_name": "ITA Models",
        "category": "threads"
    }
}

# Modelos para FOTOS (usa e getta)
PHOTO_MODELS = {
    # Asian category
    "mila_photo": {"name": "🇨🇳 Mila", "category": "asian", "display": "Mila"},
    "yuna_photo": {"name": "🇯🇵 Yuna", "category": "asian", "display": "Yuna"},
    "model1": {"name": "🇨🇳 Model 1", "category": "asian", "display": "Model 1"},
    "model2": {"name": "🇨🇳 Model 2", "category": "asian", "display": "Model 2"},
    "model3": {"name": "🇨🇳 Model 3", "category": "asian", "display": "Model 3"},
    "model4": {"name": "🇨🇳 Model 4", "category": "asian", "display": "Model 4"},
    "model5": {"name": "🇨🇳 Model 5", "category": "asian", "display": "Model 5"},
    "model6": {"name": "🇨🇳 Model 6", "category": "asian", "display": "Model 6"},
    "model7": {"name": "🇨🇳 Model 7", "category": "asian", "display": "Model 7"},
    "model8": {"name": "🇨🇳 Model 8", "category": "asian", "display": "Model 8"},
    "model9": {"name": "🇨🇳 Model 9", "category": "asian", "display": "Model 9"},
    "model10": {"name": "🇨🇳 Model 10", "category": "asian", "display": "Model 10"},
    "model11": {"name": "🇨🇳 Model 11", "category": "asian", "display": "Model 11"},
    "model12": {"name": "🇨🇳 Model 12", "category": "asian", "display": "Model 12"},
    # Italian category
    "elira": {"name": "🇮🇹 Elira", "category": "italian", "display": "Elira"},
    "bella": {"name": "🇮🇹 Bella", "category": "italian", "display": "Bella"},
    "milena": {"name": "🇮🇹 Milena", "category": "italian", "display": "Milena"},
    "isabella": {"name": "🇮🇹 Isabella", "category": "italian", "display": "Isabella"},
    "laura": {"name": "🇮🇹 Laura", "category": "italian", "display": "Laura"},
    "aurora": {"name": "🇮🇹 Aurora", "category": "italian", "display": "Aurora"}
}

# Idiomas disponibles para THREADS
LANGUAGES = {
    "italian": {
        "name": "🇮🇹 Italiano",
        "code": "it",
        "context": "Italian men, Italian food (pasta, pizza, gelato, tiramisu), Italian places (Rome, Milan, Venice, Florence), Italian culture, Italian traditions",
        "first_person": "io",
        "possessive": "mia"
    },
    "german": {
        "name": "🇩🇪 Deutsch",
        "code": "de",
        "context": "German men, German food (Bratwurst, Sauerkraut, Pretzels, Schnitzel), German places (Berlin, Munich, Hamburg, Cologne), German culture, Oktoberfest",
        "first_person": "ich",
        "possessive": "mein"
    },
    "portuguese": {
        "name": "🇧🇷 Português (Brasil)",
        "code": "pt",
        "context": "Brazilian men, Brazilian food (Feijoada, Pão de Queijo, Brigadeiro, Coxinha), Brazilian places (Rio de Janeiro, São Paulo, Salvador, Brasília), Brazilian culture, Samba, Carnival",
        "first_person": "eu",
        "possessive": "minha"
    },
    "english": {
        "name": "🇺🇸 English (USA)",
        "code": "en",
        "context": "American men, American food (Burgers, Pizza, BBQ, Apple Pie), American places (New York, Los Angeles, Chicago, Miami), American culture",
        "first_person": "I",
        "possessive": "my"
    },
    "spanish": {
        "name": "🇪🇸 Español (España)",
        "code": "es",
        "context": "Spanish men, Spanish food (Paella, Tapas, Jamón, Tortilla), Spanish places (Madrid, Barcelona, Seville, Valencia), Spanish culture, Flamenco",
        "first_person": "yo",
        "possessive": "mi"
    }
}

# Estados
waiting_for_file = {}  # {user_id: model_name}
waiting_for_photo_upload = {}  # {user_id: photo_model}
pending_photos = {}  # {user_id: [paths]}
waiting_for_threads_number = {}  # {user_id: True}
waiting_for_photos_number = {}  # {user_id: photo_model} - aspettando che l'utente scriva un numero per le foto

MAX_VARIATIONS = 50
THRESHOLD_FOTOS = 5

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# STRUTTURE DATI
# ======================

user_threads_state = {}  # {user_id: {"sent_numbers": set(), "total_sent": int}}
user_config = {}          # {user_id: {"threads_model": "mila", "threads_language": "italian"}}
user_photo_config = {}    # {user_id: {"photo_model": "mila_photo"}}
fotos_global_state = {}

# ======================
# FUNZIONI CONFIGURAZIONE UTENTE
# ======================

def caricare_config_utenti() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(USER_CONFIG_FILE):
        return {}
    with open(USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvare_config_utenti(config: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(USER_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_user_config(user_id: int) -> Dict:
    global user_config
    user_id_str = str(user_id)
    if user_id_str not in user_config:
        user_config[user_id_str] = {
            "threads_model": "mila",
            "threads_language": "italian"
        }
        salvare_config_utenti(user_config)
    return user_config[user_id_str]

def set_user_config(user_id: int, threads_model: str = None, threads_language: str = None):
    global user_config
    user_id_str = str(user_id)
    if user_id_str not in user_config:
        user_config[user_id_str] = {
            "threads_model": "mila",
            "threads_language": "italian"
        }
    if threads_model:
        user_config[user_id_str]["threads_model"] = threads_model
    if threads_language:
        user_config[user_id_str]["threads_language"] = threads_language
    salvare_config_utenti(user_config)

# ======================
# FUNZIONI CONFIGURAZIONE FOTO UTENTE
# ======================

def caricare_config_foto_utenti() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(USER_PHOTO_CONFIG_FILE):
        return {}
    with open(USER_PHOTO_CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvare_config_foto_utenti(config: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(USER_PHOTO_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_user_photo_config(user_id: int) -> Dict:
    global user_photo_config
    user_id_str = str(user_id)
    if user_id_str not in user_photo_config:
        user_photo_config[user_id_str] = {
            "photo_model": None,
            "waiting_for_number": False
        }
        salvare_config_foto_utenti(user_photo_config)
    return user_photo_config[user_id_str]

def set_user_photo_model(user_id: int, photo_model: str):
    global user_photo_config
    user_id_str = str(user_id)
    if user_id_str not in user_photo_config:
        user_photo_config[user_id_str] = {
            "photo_model": None,
            "waiting_for_number": False
        }
    user_photo_config[user_id_str]["photo_model"] = photo_model
    user_photo_config[user_id_str]["waiting_for_number"] = True
    salvare_config_foto_utenti(user_photo_config)

def set_photo_waiting_for_number(user_id: int, waiting: bool):
    global user_photo_config
    user_id_str = str(user_id)
    if user_id_str not in user_photo_config:
        user_photo_config[user_id_str] = {
            "photo_model": None,
            "waiting_for_number": False
        }
    user_photo_config[user_id_str]["waiting_for_number"] = waiting
    salvare_config_foto_utenti(user_photo_config)

def is_photo_waiting_for_number(user_id: int) -> bool:
    user_id_str = str(user_id)
    if user_id_str in user_photo_config:
        return user_photo_config[user_id_str].get("waiting_for_number", False)
    return False

def get_photo_model_for_user(user_id: int) -> str:
    user_id_str = str(user_id)
    if user_id_str in user_photo_config:
        return user_photo_config[user_id_str].get("photo_model")
    return None

def clear_photo_waiting(user_id: int):
    global user_photo_config
    user_id_str = str(user_id)
    if user_id_str in user_photo_config:
        user_photo_config[user_id_str]["waiting_for_number"] = False
        user_photo_config[user_id_str]["photo_model"] = None
        salvare_config_foto_utenti(user_photo_config)

# ======================
# FUNZIONI THREAD (VARIAZIONI)
# ======================

def caricare_frasi_per_modello(model: str) -> List[Dict]:
    file_path = os.path.join(DATA_FOLDER, f"frases_{model}.json")
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvare_frasi_per_modello(model: str, frasi: List[Dict]):
    file_path = os.path.join(DATA_FOLDER, f"frases_{model}.json")
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(frasi, f, ensure_ascii=False, indent=2)

def caricare_stato_utenti_threads() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(USER_STATE_FILE):
        return {}
    with open(USER_STATE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvare_stato_utenti_threads(stato: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(USER_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_utente_threads(user_id: int):
    stato = caricare_stato_utenti_threads()
    user_id_str = str(user_id)
    
    if user_id_str not in stato:
        stato[user_id_str] = {
            "sent_numbers": [],
            "total_sent": 0
        }
        salvare_stato_utenti_threads(stato)
    
    if user_id not in user_threads_state:
        user_threads_state[user_id] = {
            "sent_numbers": set(stato[user_id_str]["sent_numbers"]),
            "total_sent": stato[user_id_str]["total_sent"]
        }

def salvare_stato_utente_threads(user_id: int):
    if user_id in user_threads_state:
        stato = caricare_stato_utenti_threads()
        user_id_str = str(user_id)
        stato[user_id_str] = {
            "sent_numbers": list(user_threads_state[user_id]["sent_numbers"]),
            "total_sent": user_threads_state[user_id]["total_sent"]
        }
        salvare_stato_utenti_threads(stato)

def ottenere_numeri_disponibili_threads(user_id: int, quantita_desiderata: int) -> List[int]:
    inizializzare_stato_utente_threads(user_id)
    
    inviati = user_threads_state[user_id]["sent_numbers"]
    tutti_i_numeri = list(range(1, MAX_VARIATIONS + 1))
    disponibili = [n for n in tutti_i_numeri if n not in inviati]
    
    if not disponibili:
        user_threads_state[user_id] = {
            "sent_numbers": set(),
            "total_sent": 0
        }
        salvare_stato_utente_threads(user_id)
        disponibili = list(range(1, MAX_VARIATIONS + 1))
    
    random.shuffle(disponibili)
    return disponibili[:quantita_desiderata]

def marcare_come_inviate_threads(user_id: int, numeri: List[int]):
    inizializzare_stato_utente_threads(user_id)
    
    for num in numeri:
        user_threads_state[user_id]["sent_numbers"].add(num)
        user_threads_state[user_id]["total_sent"] += 1
    
    salvare_stato_utente_threads(user_id)

def resettare_tutti_gli_utenti_threads():
    global user_threads_state
    user_threads_state = {}
    salvare_stato_utenti_threads({})

async def generare_variazione(model: str, language: str, frase_originale: str, frase_numero: int, variazione_num: int) -> str:
    model_info = THREADS_MODELS[model]
    language_config = LANGUAGES[language]
    
    system_prompt = f"""You are a copywriter. Create ONE variation of the given phrase in {language_config['name']}.

CRITICAL RULES:
1. The girl's name is {model_info['full_name']}. ALWAYS use this name when referring to herself.
2. Her origin is {model_info['origin']}. ALWAYS maintain this: "{model_info['origin_text']}"
3. ALWAYS write in FIRST PERSON (I, me, my, mine / io, me, mia / ich, mein, mich / eu, minha / yo, mi)
4. Adapt ALL cultural references to: {language_config['context']}
5. Keep censorship (use * or emojis as in original)
6. Change words, not the meaning
7. This is variation number {variazione_num}
8. Keep teen tone (18 years old)
9. DO NOT include the original phrase number
10. Reply ONLY with the variation text in {language_config['name']}, nothing else

CRITICAL - The character is {model_info['origin']} and speaks in FIRST PERSON:
- "I am {model_info['origin']}..." / "Io sono {model_info['origin']}..."
- She is attracted to men from the target country
- Use cultural references from the target country
- The origin ({model_info['origin']}) is FIXED and cannot change
- Everything else adapts to the target country

Original phrase (number {frase_numero}):
{frase_originale}

Generate variation number {variazione_num} in {language_config['name']} (FIRST PERSON):"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Generate ONE variation in {language_config['name']} for {model_info['full_name']} (FIRST PERSON):"}
    ]
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": 800
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content'].strip()
                else:
                    return f"❌ API Error: {response.status}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ======================
# FUNZIONI FOTO (USA E GETTA)
# ======================

def init_fotos_db():
    os.makedirs(PHOTOS_FOLDER, exist_ok=True)

def caricare_stato_fotos() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(PHOTOS_DB_FILE):
        return {}
    with open(PHOTOS_DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvare_stato_fotos(stato: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(PHOTOS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_fotos():
    global fotos_global_state
    fotos_global_state = caricare_stato_fotos()

def salvare_stato_fotos_globale():
    salvare_stato_fotos(fotos_global_state)

def reset_fotos_per_modello(photo_model: str):
    global fotos_global_state
    
    if photo_model in fotos_global_state:
        for fid, meta in fotos_global_state[photo_model].get("metadata", {}).items():
            path = meta.get("path")
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass
    
    fotos_global_state[photo_model] = {
        "total": 0,
        "disponibili": [],
        "usate": [],
        "metadata": {}
    }
    salvare_stato_fotos_globale()

def aggiungere_foto_per_modello(photo_model: str, foto_path: str):
    global fotos_global_state
    
    if photo_model not in fotos_global_state:
        fotos_global_state[photo_model] = {
            "total": 0,
            "disponibili": [],
            "usate": [],
            "metadata": {}
        }
    
    nuovo_id = fotos_global_state[photo_model]["total"] + 1
    
    ext = os.path.splitext(foto_path)[1]
    nuovo_nome = f"{photo_model}_foto_{nuovo_id}{ext}"
    nuovo_path = os.path.join(PHOTOS_FOLDER, nuovo_nome)
    
    shutil.copy2(foto_path, nuovo_path)
    
    fotos_global_state[photo_model]["metadata"][nuovo_id] = {
        "path": nuovo_path,
        "original_name": os.path.basename(foto_path),
        "used": False
    }
    
    fotos_global_state[photo_model]["total"] += 1
    fotos_global_state[photo_model]["disponibili"].append(nuovo_id)
    
    salvare_stato_fotos_globale()
    
    return nuovo_id

def ottenere_foto_disponibili_per_modello(photo_model: str, quantita: int) -> List[int]:
    if photo_model not in fotos_global_state:
        return []
    
    disponibili = [fid for fid, meta in fotos_global_state[photo_model]["metadata"].items() 
                   if not meta.get("used", False)]
    
    random.shuffle(disponibili)
    return disponibili[:quantita]

def marcare_foto_come_usate_per_modello(photo_model: str, foto_ids: List[int]):
    if photo_model not in fotos_global_state:
        return
    
    for fid in foto_ids:
        if fid in fotos_global_state[photo_model]["metadata"]:
            fotos_global_state[photo_model]["metadata"][fid]["used"] = True
            if fid in fotos_global_state[photo_model]["disponibili"]:
                fotos_global_state[photo_model]["disponibili"].remove(fid)
            fotos_global_state[photo_model]["usate"].append(fid)
    
    salvare_stato_fotos_globale()

def get_stato_fotos_per_modello(photo_model: str) -> tuple:
    if photo_model not in fotos_global_state:
        return 0, 0, 0
    
    usate = len(fotos_global_state[photo_model]["usate"])
    disponibili = len([f for f in fotos_global_state[photo_model]["metadata"].values() if not f.get("used", False)])
    total = fotos_global_state[photo_model]["total"]
    return usate, disponibili, total

# ======================
# NOTIFICHE ADMIN
# ======================

async def notificare_admin(context: ContextTypes.DEFAULT_TYPE, messaggio: str, is_admin_action: bool = False):
    try:
        if is_admin_action:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"👑 <b>ADMIN NOTIFICATION:</b>\n{messaggio}",
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=messaggio,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")

# ======================
# MENU THREADS
# ======================

async def menu_threads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú para seleccionar el modelo de threads"""
    keyboard = []
    for key, model in THREADS_MODELS.items():
        keyboard.append([InlineKeyboardButton(model["name"], callback_data=f"threads_model_{key}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "🌸 <b>Choose your model for THREADS:</b>\n\nSelect the girl:",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "🌸 <b>Choose your model for THREADS:</b>\n\nSelect the girl:",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

async def menu_threads_language(update: Update, context: ContextTypes.DEFAULT_TYPE, model: str):
    """Muestra el menú para seleccionar el idioma de threads"""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    for lang_key, lang_info in LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(lang_info["name"], callback_data=f"threads_lang_{model}_{lang_key}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"🌸 <b>Model: {THREADS_MODELS[model]['name']}</b>\n\n"
        f"🌍 <b>Choose language for THREADS:</b>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

# ======================
# MENU FOTOS
# ======================

async def menu_photos_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú para seleccionar categoría de fotos"""
    keyboard = [
        [InlineKeyboardButton("🇦🇸 Asian Models", callback_data="photo_category_asian")],
        [InlineKeyboardButton("🇮🇹 Italian Models", callback_data="photo_category_italian")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📸 <b>Choose category for PHOTOS:</b>",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "📸 <b>Choose category for PHOTOS:</b>",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

async def menu_photos_models(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """Muestra el menú para seleccionar el modelo de fotos según categoría"""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    for key, model in PHOTO_MODELS.items():
        if model["category"] == category:
            keyboard.append([InlineKeyboardButton(model["name"], callback_data=f"photo_model_{key}")])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("◀️ Back to categories", callback_data="photo_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    category_name = "Asian" if category == "asian" else "Italian"
    await query.edit_message_text(
        f"📸 <b>Select a model ({category_name}):</b>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

# ======================
# MANEJADOR DE CALLBACKS
# ======================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # THREADS callbacks
    if data.startswith("threads_model_"):
        model = data.replace("threads_model_", "")
        context.user_data["selected_threads_model"] = model
        await menu_threads_language(update, context, model)
    
    elif data.startswith("threads_lang_"):
        parts = data.split("_")
        model = parts[2]
        language = parts[3]
        
        set_user_config(user_id, threads_model=model, threads_language=language)
        
        model_name = THREADS_MODELS[model]["name"]
        language_name = LANGUAGES[language]["name"]
        
        await query.edit_message_text(
            f"✅ <b>Threads configuration saved!</b>\n\n"
            f"🌸 Model: {model_name}\n"
            f"🌍 Language: {language_name}\n\n"
            f"📝 <b>Now just type the number of threads you want!</b>\n\n"
            f"Example: <code>5</code> - sends 5 threads\n\n"
            f"Use /threads again to change settings.",
            parse_mode="HTML"
        )
    
    # PHOTOS callbacks
    elif data == "photo_category_asian":
        await menu_photos_models(update, context, "asian")
    
    elif data == "photo_category_italian":
        await menu_photos_models(update, context, "italian")
    
    elif data == "photo_back":
        await menu_photos_category(update, context)
    
    elif data.startswith("photo_model_"):
        photo_model = data.replace("photo_model_", "")
        set_user_photo_model(user_id, photo_model)
        
        model_name = PHOTO_MODELS[photo_model]["name"]
        
        await query.edit_message_text(
            f"✅ <b>Photo model selected!</b>\n\n"
            f"📸 Model: {model_name}\n\n"
            f"📝 <b>Now just type the number of photos you want!</b>\n\n"
            f"Example: <code>5</code> - sends 5 photos\n\n"
            f"⚠️ Photos are ONE-TIME USE - they won't be sent again!\n\n"
            f"Use /photos again to change model.",
            parse_mode="HTML"
        )

# ======================
# COMANDOS ADMIN - THREADS
# ======================

async def upload_frases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ **Usage:** <code>/upload model_name</code>\n\n"
            f"Available models: mila, yuna, ita\n\n"
            "Example: <code>/upload mila</code>\n\n"
            "Then send a .txt file with numbered phrases.",
            parse_mode="HTML"
        )
        return
    
    model_name = context.args[0].lower()
    if model_name not in THREADS_MODELS:
        await update.message.reply_text(f"❌ Invalid model. Available: mila, yuna, ita")
        return
    
    waiting_for_file[user.id] = model_name
    await update.message.reply_text(
        f"📁 **Ready to receive file for {THREADS_MODELS[model_name]['name']}!**\n\n"
        "Send a .txt file with numbered phrases.\n\n"
        "📌 **Expected format:**\n"
        "<code>43. Ti amo... Non è vero bugiardo...</code>\n"
        "<code>44. Sono molto sola 😍...</code>\n\n"
        "⏳ Waiting for file...",
        parse_mode="HTML"
    )

async def receive_phrases_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id not in waiting_for_file:
        return
    
    model_name = waiting_for_file[user_id]
    
    if not update.message.document:
        await update.message.reply_text("❌ Please send a .txt file")
        return
    
    document = update.message.document
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ File must be .txt")
        return
    
    status_msg = await update.message.reply_text(f"📥 Processing file for {THREADS_MODELS[model_name]['name']}...")
    
    try:
        file = await context.bot.get_file(document.file_id)
        
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', encoding='utf-8', delete=False) as tmp_file:
            await file.download_to_drive(tmp_file.name)
            with open(tmp_file.name, 'r', encoding='utf-8') as f:
                content = f.read()
        
        os.unlink(tmp_file.name)
        
        if not content or not content.strip():
            await status_msg.edit_text("❌ File is empty")
            return
        
        frases = []
        lines = content.strip().split('\n')
        current_phrase = None
        current_number = None
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            match = re.match(r'^(\d{1,2})\.\s+(.*)', line)
            
            if match:
                if current_phrase is not None and current_number is not None:
                    frases.append({
                        "numero": current_number,
                        "testo": current_phrase.strip()
                    })
                
                current_number = int(match.group(1))
                current_phrase = match.group(2)
            else:
                if current_phrase is not None:
                    current_phrase += "\n" + line
            
            i += 1
        
        if current_phrase is not None and current_number is not None:
            frases.append({
                "numero": current_number,
                "testo": current_phrase.strip()
            })
        
        if not frases:
            await status_msg.edit_text("❌ No numbered phrases found in file.")
            return
        
        salvare_frasi_per_modello(model_name, frases)
        
        del waiting_for_file[user_id]
        
        preview = []
        for f in frases[:5]:
            preview.append(f"📌 <b>Phrase {f['numero']}:</b> {f['testo'][:60]}...")
        
        await status_msg.edit_text(
            f"✅ <b>Phrases for {THREADS_MODELS[model_name]['name']} loaded successfully!</b>\n\n"
            f"📊 <b>Total phrases:</b> {len(frases)}\n\n"
            + "\n".join(preview) +
            (f"\n... and {len(frases) - 5} more" if len(frases) > 5 else ""),
            parse_mode="HTML"
        )
        
        await notificare_admin(context, f"📝 You loaded {len(frases)} phrases for {THREADS_MODELS[model_name]['name']}", is_admin_action=True)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def view_phrases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ Usage: <code>/view model_name</code>\n\n"
            f"Available models: mila, yuna, ita",
            parse_mode="HTML"
        )
        return
    
    model_name = context.args[0].lower()
    if model_name not in THREADS_MODELS:
        await update.message.reply_text(f"❌ Invalid model. Available: mila, yuna, ita")
        return
    
    frases = caricare_frasi_per_modello(model_name)
    
    if not frases:
        await update.message.reply_text(f"❌ No phrases loaded for {THREADS_MODELS[model_name]['name']}.")
        return
    
    msg = f"📊 <b>PHRASES FOR {THREADS_MODELS[model_name]['name'].upper()}: {len(frases)}</b>\n\n"
    for f in frases[:10]:
        msg += f"• <b>{f['numero']}:</b> {f['testo'][:80]}...\n"
    
    if len(frases) > 10:
        msg += f"\n... and {len(frases) - 10} more"
    
    await update.message.reply_text(msg, parse_mode="HTML")

# ======================
# COMANDOS ADMIN - FOTOS USA E GETTA
# ======================

async def upload_photos_for_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /uploadphotos model_name - Upload photos for a specific model"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        models_list = ", ".join(PHOTO_MODELS.keys())
        await update.message.reply_text(
            f"❌ **Usage:** <code>/uploadphotos model_name</code>\n\n"
            f"Available models: {models_list}\n\n"
            "Example: <code>/uploadphotos mila_photo</code>\n\n"
            "Then send photos (one or more at a time).\n"
            "When done, use <code>/donephotos</code>",
            parse_mode="HTML"
        )
        return
    
    photo_model = context.args[0].lower()
    if photo_model not in PHOTO_MODELS:
        await update.message.reply_text(f"❌ Invalid model. Available: {', '.join(PHOTO_MODELS.keys())}")
        return
    
    waiting_for_photo_upload[user_id] = photo_model
    if user_id not in pending_photos:
        pending_photos[user_id] = []
    
    await update.message.reply_text(
        f"📸 **Uploading photos for {PHOTO_MODELS[photo_model]['name']}**\n\n"
        "Send photos (one or more at a time).\n"
        "You'll receive a confirmation every 10 photos.\n"
        "When done, type <code>/donephotos</code>\n\n"
        f"⏳ Photos received so far: 0",
        parse_mode="HTML"
    )

async def receive_photo_for_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives photos during upload session - confirms every 10 photos"""
    user = update.effective_user
    user_id = user.id
    
    if user_id not in waiting_for_photo_upload:
        return
    
    photo_model = waiting_for_photo_upload[user_id]
    photos_added = 0
    
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        temp_path = f"temp_photo_{int(time.time())}_{random.randint(1000,9999)}.jpg"
        await file.download_to_drive(temp_path)
        pending_photos[user_id].append(temp_path)
        photos_added += 1
    
    if update.message.document:
        doc = update.message.document
        if doc.mime_type and doc.mime_type.startswith('image/'):
            file = await context.bot.get_file(doc.file_id)
            ext = os.path.splitext(doc.file_name)[1]
            temp_path = f"temp_photo_{int(time.time())}_{random.randint(1000,9999)}{ext}"
            await file.download_to_drive(temp_path)
            pending_photos[user_id].append(temp_path)
            photos_added += 1
    
    if photos_added > 0:
        total = len(pending_photos[user_id])
        
        if total % 10 == 0:
            await update.message.reply_text(
                f"📸 Loaded {total} photos for {PHOTO_MODELS[photo_model]['name']}...",
                parse_mode="HTML"
            )

async def done_photos_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /donephotos - Finalizes photo upload for a model"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if user_id not in waiting_for_photo_upload:
        await update.message.reply_text(
            "❌ No active upload session.\n"
            "Use /uploadphotos model_name first"
        )
        return
    
    if user_id not in pending_photos or not pending_photos[user_id]:
        await update.message.reply_text("❌ No pending photos to process.")
        if user_id in waiting_for_photo_upload:
            del waiting_for_photo_upload[user_id]
        if user_id in pending_photos:
            del pending_photos[user_id]
        return
    
    photo_model = waiting_for_photo_upload[user_id]
    pending = pending_photos[user_id]
    total_photos = len(pending)
    
    status_msg = await update.message.reply_text(f"📥 Processing {total_photos} photos for {PHOTO_MODELS[photo_model]['name']}...")
    
    for path in pending:
        aggiungere_foto_per_modello(photo_model, path)
    
    for path in pending:
        if os.path.exists(path):
            try:
                os.unlink(path)
            except:
                pass
    
    del waiting_for_photo_upload[user_id]
    del pending_photos[user_id]
    
    used, available, total = get_stato_fotos_per_modello(photo_model)
    
    await status_msg.edit_text(
        f"✅ <b>Photos loaded successfully for {PHOTO_MODELS[photo_model]['name']}!</b>\n\n"
        f"📸 Photos added: {total_photos}\n"
        f"📊 Total in pool: {total}\n"
        f"⏳ Available: {available}\n"
        f"✅ Used: {used}",
        parse_mode="HTML"
    )
    
    await notificare_admin(context, f"📸 You loaded {total_photos} photos for {PHOTO_MODELS[photo_model]['name']}", is_admin_action=True)
    logger.info(f"Admin loaded {total_photos} photos for model: {photo_model}")

async def photo_status_for_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /photostatus model_name - Show photo pool status for a model"""
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can see this.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            f"❌ Usage: <code>/photostatus model_name</code>\n\n"
            f"Available models: {', '.join(PHOTO_MODELS.keys())}",
            parse_mode="HTML"
        )
        return
    
    photo_model = context.args[0].lower()
    if photo_model not in PHOTO_MODELS:
        await update.message.reply_text(f"❌ Invalid model. Available: {', '.join(PHOTO_MODELS.keys())}")
        return
    
    used, available, total = get_stato_fotos_per_modello(photo_model)
    
    await update.message.reply_text(
        f"📸 <b>PHOTO POOL STATUS - {PHOTO_MODELS[photo_model]['name']}</b>\n\n"
        f"• Total photos loaded: {total}\n"
        f"• Photos used: {used}\n"
        f"• Photos available: {available}\n\n"
        f"📌 Use /uploadphotos {photo_model} to add more photos.",
        parse_mode="HTML"
    )

async def reset_photos_for_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /resetphotos model_name - Reset all photos for a model"""
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            f"❌ Usage: <code>/resetphotos model_name</code>\n\n"
            f"Available models: {', '.join(PHOTO_MODELS.keys())}",
            parse_mode="HTML"
        )
        return
    
    photo_model = context.args[0].lower()
    if photo_model not in PHOTO_MODELS:
        await update.message.reply_text(f"❌ Invalid model. Available: {', '.join(PHOTO_MODELS.keys())}")
        return
    
    reset_fotos_per_modello(photo_model)
    
    await update.message.reply_text(f"✅ Photo pool for {PHOTO_MODELS[photo_model]['name']} completely reset.", parse_mode="HTML")
    await notificare_admin(context, f"🔄 You reset the photo pool for {PHOTO_MODELS[photo_model]['name']}", is_admin_action=True)

# ======================
# COMANDOS UTENTES
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"👤 New user: @{username} (ID: {user_id})")
    
    config = get_user_config(user_id)
    threads_model = config["threads_model"]
    threads_language = config["threads_language"]
    threads_model_name = THREADS_MODELS[threads_model]["name"]
    language_name = LANGUAGES[threads_language]["name"]
    
    await update.message.reply_text(
        f"Hello @{username}! 👋\n\n"
        f"📝 <b>How to use this bot:</b>\n\n"
        f"<b>📝 THREADS:</b>\n"
        f"1️⃣ Use <code>/threads</code> to choose a model and language\n"
        f"2️⃣ Then simply type the number of threads you want!\n\n"
        f"<b>📸 PHOTOS (One-time use):</b>\n"
        f"1️⃣ Use <code>/photos</code> to choose a model\n"
        f"2️⃣ Then simply type the number of photos you want!\n\n"
        f"📌 <b>Examples:</b>\n"
        f"• Type <code>5</code> after choosing threads → 5 threads\n"
        f"• Type <code>3</code> after choosing photos → 3 photos\n\n"
        f"📊 <b>Your current THREADS settings:</b>\n"
        f"🌸 Model: {threads_model_name}\n"
        f"🌍 Language: {language_name}\n\n"
        f"💡 <b>Commands:</b>\n"
        f"• <code>/threads</code> - Change threads settings\n"
        f"• <code>/photos</code> - Choose photo model\n"
        f"• <code>/status</code> - Your progress\n"
        f"• <code>/reset</code> - Reset thread progress\n"
        f"• <code>/help</code> - All commands",
        parse_mode="HTML"
    )

async def photos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /photos - Shows photo category menu"""
    await menu_photos_category(update, context)

async def threads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /threads - Shows threads model menu"""
    await menu_threads(update, context)

async def handle_number_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i messaggi che sono numeri (cantidad de threads o fotos)"""
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()
    
    if not text.isdigit():
        return
    
    quantity = int(text)
    if quantity < 1 or quantity > MAX_VARIATIONS:
        await update.message.reply_text(f"❌ Please type a number between 1 and {MAX_VARIATIONS}.")
        return
    
    # Check if user is waiting for photos
    if is_photo_waiting_for_number(user_id):
        photo_model = get_photo_model_for_user(user_id)
        if photo_model and photo_model in PHOTO_MODELS:
            await send_photos_to_user(update, context, user_id, photo_model, quantity)
            return
    
    # Otherwise, generate threads
    await generate_threads_for_user(update, context, user_id, quantity)

async def generate_threads_for_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, quantity: int):
    """Genera threads per l'utente"""
    user = update.effective_user
    username = user.username or user.first_name
    
    config = get_user_config(user_id)
    model = config["threads_model"]
    language = config["threads_language"]
    
    frases = caricare_frasi_per_modello(model)
    if not frases:
        await update.message.reply_text(
            f"❌ No phrases loaded for {THREADS_MODELS[model]['name']}.\n"
            f"Admin @{ADMIN_USERNAME} needs to upload phrases with /upload {model}"
        )
        return
    
    available_numbers = ottenere_numeri_disponibili_threads(user_id, quantity)
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"🔄 @{username} requested {len(available_numbers)} threads | Model: {THREADS_MODELS[model]['name']} | Language: {LANGUAGES[language]['name']}")
    else:
        await notificare_admin(context, f"👑 You requested {len(available_numbers)} threads | Model: {THREADS_MODELS[model]['name']} | Language: {LANGUAGES[language]['name']}", is_admin_action=True)
    
    await update.message.reply_text(
        f"🎲 Generating {len(available_numbers)} threads for {THREADS_MODELS[model]['name']} in {LANGUAGES[language]['name']}...",
        parse_mode="HTML"
    )
    
    sent = []
    mixed_phrases = frases.copy()
    random.shuffle(mixed_phrases)
    
    for i, num in enumerate(available_numbers):
        phrase = mixed_phrases[i % len(mixed_phrases)]
        
        variation = await generare_variazione(model, language, phrase["testo"], phrase["numero"], num)
        
        if variation and not variation.startswith("❌"):
            await update.message.reply_text(variation, parse_mode="HTML")
            sent.append(num)
            await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(f"❌ Error generating variation {num}")
    
    marcare_come_inviate_threads(user_id, sent)
    total_received = user_threads_state[user_id]["total_sent"]
    
    await update.message.reply_text(
        f"✅ <b>Threads sent!</b>\n\n"
        f"📨 Sent this session: {len(sent)}\n"
        f"📊 Total threads received: {total_received}",
        parse_mode="HTML"
    )
    
    logger.info(f"User {username} received {len(sent)} threads for {model}/{language}. Total: {total_received}")

async def send_photos_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, photo_model: str, quantity: int):
    """Invia foto usa e getta all'utente"""
    user = update.effective_user
    username = user.username or user.first_name
    
    used, available, total = get_stato_fotos_per_modello(photo_model)
    
    if available <= THRESHOLD_FOTOS and available > 0:
        await notificare_admin(
            context,
            f"⚠️ <b>LOW PHOTOS WARNING - {PHOTO_MODELS[photo_model]['name']}!</b>\n"
            f"📸 Photos available: {available}\n"
            f"📌 Use /uploadphotos {photo_model} to add more.",
            is_admin_action=True
        )
    
    if total == 0:
        await update.message.reply_text(
            f"❌ No photos available for {PHOTO_MODELS[photo_model]['name']}.\n"
            f"Admin needs to upload photos with /uploadphotos {photo_model}"
        )
        clear_photo_waiting(user_id)
        return
    
    if available == 0:
        await update.message.reply_text(f"❌ No photos available for {PHOTO_MODELS[photo_model]['name']}. All photos have been used!")
        clear_photo_waiting(user_id)
        return
    
    if available < quantity:
        await update.message.reply_text(
            f"⚠️ Only {available} photos available for {PHOTO_MODELS[photo_model]['name']}.\n"
            f"Sending {available} instead."
        )
        quantity = available
    
    await notificare_admin(context, f"📸 @{username} requested {quantity} photos for {PHOTO_MODELS[photo_model]['name']}")
    
    photo_ids = ottenere_foto_disponibili_per_modello(photo_model, quantity)
    
    await update.message.reply_text(f"📸 Sending {len(photo_ids)} photos for {PHOTO_MODELS[photo_model]['name']}...")
    
    sent = []
    for i, fid in enumerate(photo_ids, 1):
        metadata = fotos_global_state[photo_model]["metadata"].get(fid, {})
        photo_path = metadata.get("path")
        
        if photo_path and os.path.exists(photo_path):
            try:
                with open(photo_path, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=f"📸 Photo {i}/{len(photo_ids)}"
                    )
                sent.append(fid)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Error sending photo {fid} for {photo_model}: {e}")
    
    if sent:
        marcare_foto_come_usate_per_modello(photo_model, sent)
    
    await update.message.reply_text(
        f"✅ <b>Photos sent!</b>\n\n"
        f"📨 Sent: {len(sent)}",
        parse_mode="HTML"
    )
    
    # Clear waiting state
    clear_photo_waiting(user_id)
    
    logger.info(f"User {username} received {len(sent)} photos for {photo_model}")

async def user_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    inizializzare_stato_utente_threads(user_id)
    total = user_threads_state[user_id]["total_sent"]
    remaining_in_cycle = MAX_VARIATIONS - (total % MAX_VARIATIONS)
    
    config = get_user_config(user_id)
    threads_model = config["threads_model"]
    threads_language = config["threads_language"]
    threads_model_name = THREADS_MODELS[threads_model]["name"]
    language_name = LANGUAGES[threads_language]["name"]
    
    photo_model = get_photo_model_for_user(user_id)
    photo_info = f"None selected" if not photo_model else PHOTO_MODELS[photo_model]["name"]
    
    await update.message.reply_text(
        f"📊 <b>Your Status</b>\n\n"
        f"<b>THREADS settings:</b>\n"
        f"🌸 Model: {threads_model_name}\n"
        f"🌍 Language: {language_name}\n\n"
        f"<b>PHOTOS:</b>\n"
        f"📸 Selected model: {photo_info}\n\n"
        f"<b>Threads progress:</b>\n"
        f"• Threads received: {total}\n"
        f"• Remaining in cycle: {remaining_in_cycle}\n\n"
        f"💡 Use <code>/threads</code> to change threads settings\n"
        f"💡 Use <code>/photos</code> to choose photo model\n"
        f"💡 Type a number to get threads or photos",
        parse_mode="HTML"
    )

async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    user_threads_state[user_id] = {"sent_numbers": set(), "total_sent": 0}
    salvare_stato_utente_threads(user_id)
    
    await update.message.reply_text("🔄 Your thread progress has been reset. You can start over!")
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"🔄 User @{username} reset their thread progress")
    else:
        await notificare_admin(context, f"👑 You reset your thread progress", is_admin_action=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    base_message = (
        f"📖 <b>Bot Help</b>\n\n"
        f"<b>📝 THREADS:</b>\n"
        f"1️⃣ <code>/threads</code> - Choose model and language\n"
        f"2️⃣ Type a number (ex: <code>5</code>) - Get that many threads\n\n"
        f"<b>📸 PHOTOS (One-time use):</b>\n"
        f"1️⃣ <code>/photos</code> - Choose a model (Asian/Italian)\n"
        f"2️⃣ Type a number (ex: <code>3</code>) - Get that many photos\n\n"
        f"<b>🌍 Threads models:</b>\n"
        f"• 🇨🇳 Mila (Chinese)\n"
        f"• 🇯🇵 Yuna (Japanese)\n"
        f"• 🇮🇹 ITA Models (Italian)\n\n"
        f"<b>📸 Photo models:</b>\n"
        f"• Asian: Mila, Yuna, Model 1-12 (14 models)\n"
        f"• Italian: Elira, Bella, Milena, Isabella, Laura, Aurora (6 models)\n\n"
        f"<b>🌍 Threads languages:</b>\n"
        f"• 🇮🇹 Italian, 🇩🇪 German, 🇧🇷 Portuguese, 🇺🇸 English, 🇪🇸 Spanish\n\n"
        f"<b>💡 Commands:</b>\n"
        f"• <code>/threads</code> - Change threads settings\n"
        f"• <code>/photos</code> - Choose photo model\n"
        f"• <code>/status</code> - Your progress and settings\n"
        f"• <code>/reset</code> - Reset thread progress\n"
        f"• <code>/help</code> - This help"
    )
    
    if user_id == ADMIN_USER_ID:
        admin_message = (
            f"\n\n👑 <b>Admin Commands (@{ADMIN_USERNAME}):</b>\n"
            f"├─ <b>THREADS (upload .txt files):</b>\n"
            f"│  • <code>/upload mila</code> - Upload for Mila\n"
            f"│  • <code>/upload yuna</code> - Upload for Yuna\n"
            f"│  • <code>/upload ita</code> - Upload for ITA Models\n"
            f"│  • <code>/view mila</code> - View loaded phrases\n"
            f"├─ <b>PHOTOS (upload images):</b>\n"
            f"│  • <code>/uploadphotos mila_photo</code> - Upload for a model\n"
            f"│  • <code>/photostatus mila_photo</code> - Check status\n"
            f"│  • <code>/resetphotos mila_photo</code> - Reset pool\n"
            f"└─ <b>GENERAL:</b>\n"
            f"   • <code>/donephotos</code> - Finalize photo upload\n\n"
            f"📁 <b>All photo models:</b> {', '.join(PHOTO_MODELS.keys())}"
        )
        await update.message.reply_text(base_message + admin_message, parse_mode="HTML")
    else:
        await update.message.reply_text(base_message, parse_mode="HTML")

# ======================
# MAIN
# ======================

def main():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    os.makedirs(PHOTOS_FOLDER, exist_ok=True)
    
    for model in THREADS_MODELS.keys():
        if not os.path.exists(os.path.join(DATA_FOLDER, f"frases_{model}.json")):
            salvare_frasi_per_modello(model, [])
    
    for photo_model in PHOTO_MODELS.keys():
        if photo_model not in fotos_global_state:
            fotos_global_state[photo_model] = {
                "total": 0,
                "disponibili": [],
                "usate": [],
                "metadata": {}
            }
    
    inizializzare_stato_fotos()
    
    global user_config
    user_config = caricare_config_utenti()
    
    global user_photo_config
    user_photo_config = caricare_config_foto_utenti()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Admin commands - Threads
    application.add_handler(CommandHandler("upload", upload_frases))
    application.add_handler(CommandHandler("view", view_phrases))
    
    # Admin commands - Photos
    application.add_handler(CommandHandler("uploadphotos", upload_photos_for_model))
    application.add_handler(CommandHandler("photostatus", photo_status_for_model))
    application.add_handler(CommandHandler("resetphotos", reset_photos_for_model))
    application.add_handler(CommandHandler("donephotos", done_photos_upload))
    
    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("threads", threads_command))
    application.add_handler(CommandHandler("photos", photos_command))
    application.add_handler(CommandHandler("status", user_status))
    application.add_handler(CommandHandler("reset", reset_user))
    application.add_handler(CommandHandler("help", help_command))
    
    # File and photo handlers
    application.add_handler(MessageHandler(filters.Document.ALL, receive_phrases_file))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_photo_for_model))
    
    # Handle number messages (for threads/photos quantity)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number_message))
    
    # Callback handler for inline menus
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    print("=" * 60)
    print("✅ BOT COMPLETO - THREADS + FOTO USA E GETTA CON MENU")
    print("=" * 60)
    print(f"🤖 Bot: @TesoroA_bot")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("=" * 60)
    print("📌 ADMIN COMMANDS:")
    print("  • /upload mila/yuna/ita - upload .txt for threads")
    print("  • /uploadphotos mila_photo - upload photos for a model")
    print("  • /photostatus mila_photo - check photo status")
    print("  • /resetphotos mila_photo - reset photo pool")
    print("  • /donephotos - finalize photo upload")
    print("=" * 60)
    print("📌 USER COMMANDS:")
    print("  • /threads - choose model and language for THREADS")
    print("  • /photos - choose model for PHOTOS")
    print("  • Type a number - get threads or photos")
    print("  • /status, /reset, /help")
    print("=" * 60)
    print("📸 PHOTO MODELS:")
    print("  • Asian: Mila, Yuna, Model 1-12 (14 models)")
    print("  • Italian: Elira, Bella, Milena, Isabella, Laura, Aurora (6 models)")
    print("=" * 60)
    
    application.run_polling()

if __name__ == "__main__":
    main()