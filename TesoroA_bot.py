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

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("⚠️ BOT_TOKEN no encontrado. Usando token de prueba. Configúralo en Railway.")
    BOT_TOKEN = "8216455195:AAG8gZQRp49URVtWV10V-uw64jhSaSoGGkE"

DEEPSEEK_API_KEY = "sk-7e2b6eb1c4ff4b4aa1046a6ae500a40e"
ADMIN_USER_ID = 7097140504
ADMIN_USERNAME = "famn25"

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
PHOTO_CATEGORIES_FILE = os.path.join(DATA_FOLDER, "photo_categories.json")
REELS_FOLDER = os.path.join(DATA_FOLDER, "reels")
REELS_DB_FILE = os.path.join(DATA_FOLDER, "reels_db.json")
THREADS_MODELS_FILE = os.path.join(DATA_FOLDER, "threads_models.json")
CUSTOM_LANGUAGES_FILE = os.path.join(DATA_FOLDER, "custom_languages.json")

MAX_VARIATIONS = 50
THRESHOLD_FOTOS = 40
THRESHOLD_REELS = 3
PHOTO_CONFIRMATION_BATCH = 50

# Estados
waiting_for_file = {}
waiting_for_photo_upload = {}
waiting_for_reel_upload = {}
pending_uploads = {}
waiting_for_reels_iguser = {}
waiting_for_reset_confirmation = {}
waiting_for_new_threads_model = {}
waiting_for_new_photo_category = {}
waiting_for_new_photo_model = {}
waiting_for_new_language = {}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

user_threads_state = {}
user_config = {}
user_photo_config = {}
fotos_global_state = {}
reels_global_state = {}

# ======================
# IDIOMAS POR DEFECTO
# ======================

DEFAULT_LANGUAGES = {
    "italian": {
        "name": "🇮🇹 Italiano",
        "code": "it",
        "context": "Italian men, Italian food (pasta, pizza, gelato), Italian places (Rome, Milan, Venice), Italian culture",
        "replacements": {
            "[MEN]": "uomini italiani", "[MEN_SINGULAR]": "un uomo italiano", "[COUNTRY]": "Italia",
            "[COUNTRY_ADJ]": "italiana", "[FLAG]": "🇮🇹", "[FOOD]": "cibo italiano (pasta, pizza, gelato)",
            "[CULTURE]": "la Dolce Vita", "[LOVE_SYMBOL]": "🍝"
        }
    },
    "german": {
        "name": "🇩🇪 Deutsch", "code": "de",
        "context": "German men, German food (Bratwurst, Sauerkraut, Pretzels), German places (Berlin, Munich, Hamburg), German culture",
        "replacements": {
            "[MEN]": "deutsche Männer", "[MEN_SINGULAR]": "ein deutscher Mann", "[COUNTRY]": "Deutschland",
            "[COUNTRY_ADJ]": "deutsche", "[FLAG]": "🇩🇪", "[FOOD]": "deutsches Essen (Bratwurst, Sauerkraut, Brezeln)",
            "[CULTURE]": "das Oktoberfest", "[LOVE_SYMBOL]": "🍺"
        }
    },
    "portuguese": {
        "name": "🇧🇷 Português", "code": "pt",
        "context": "Brazilian men, Brazilian food (Feijoada, Pão de Queijo), Brazilian places (Rio de Janeiro, São Paulo), Brazilian culture",
        "replacements": {
            "[MEN]": "homens brasileiros", "[MEN_SINGULAR]": "um homem brasileiro", "[COUNTRY]": "Brasil",
            "[COUNTRY_ADJ]": "brasileira", "[FLAG]": "🇧🇷", "[FOOD]": "comida brasileira (feijoada, pão de queijo, brigadeiro)",
            "[CULTURE]": "o samba e o carnaval", "[LOVE_SYMBOL]": "🍹"
        }
    },
    "english": {
        "name": "🇺🇸 English", "code": "en",
        "context": "American men, American food (Burgers, Pizza, BBQ), American places (New York, Los Angeles, Miami), American culture",
        "replacements": {
            "[MEN]": "American men", "[MEN_SINGULAR]": "an American man", "[COUNTRY]": "USA",
            "[COUNTRY_ADJ]": "American", "[FLAG]": "🇺🇸", "[FOOD]": "American food (burgers, BBQ, pizza)",
            "[CULTURE]": "Hollywood", "[LOVE_SYMBOL]": "💕"
        }
    },
    "spanish": {
        "name": "🇪🇸 Español", "code": "es",
        "context": "Spanish men, Spanish food (Paella, Tapas, Jamón), Spanish places (Madrid, Barcelona, Seville), Spanish culture",
        "replacements": {
            "[MEN]": "hombres españoles", "[MEN_SINGULAR]": "un hombre español", "[COUNTRY]": "España",
            "[COUNTRY_ADJ]": "española", "[FLAG]": "🇪🇸", "[FOOD]": "comida española (paella, tapas, jamón)",
            "[CULTURE]": "el flamenco", "[LOVE_SYMBOL]": "💃"
        }
    },
    "french": {
        "name": "🇫🇷 Français", "code": "fr",
        "context": "French men, French food (croissant, baguette, escargot, cheese, wine), French places (Paris, Lyon, Marseille, Bordeaux), French culture",
        "replacements": {
            "[MEN]": "hommes français", "[MEN_SINGULAR]": "un homme français", "[COUNTRY]": "France",
            "[COUNTRY_ADJ]": "française", "[FLAG]": "🇫🇷", "[FOOD]": "cuisine française (croissant, baguette, fromage, escargot)",
            "[CULTURE]": "la belle vie", "[LOVE_SYMBOL]": "🥖"
        }
    }
}

# ======================
# FUNCIONES DE CARGA/GUARDADO
# ======================

def load_threads_models():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if os.path.exists(THREADS_MODELS_FILE):
        with open(THREADS_MODELS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    default = {
        "mila": {"name": "🇨🇳 Mila", "origin": "China", "origin_text": "I'm Chinese", "full_name": "Mila"},
        "yuna": {"name": "🇯🇵 Yuna", "origin": "Japan", "origin_text": "I'm Japanese", "full_name": "Yuna"},
        "ita": {"name": "🇮🇹 ITA Models", "origin": "Italy", "origin_text": "I'm Italian", "full_name": "ITA Models"},
        "comments": {"name": "💬 Comments", "origin": "None", "origin_text": "", "full_name": "Comment"}
    }
    save_threads_models(default)
    return default

def save_threads_models(models):
    with open(THREADS_MODELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(models, f, ensure_ascii=False, indent=2)

def load_photo_categories():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if os.path.exists(PHOTO_CATEGORIES_FILE):
        with open(PHOTO_CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    default = {
        "asian": {"name": "🇦🇸 Asian", "models": {}},
        "italian": {"name": "🇮🇹 Italian", "models": {}}
    }
    save_photo_categories(default)
    return default

def save_photo_categories(categories):
    with open(PHOTO_CATEGORIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(categories, f, ensure_ascii=False, indent=2)

def load_custom_languages():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if os.path.exists(CUSTOM_LANGUAGES_FILE):
        with open(CUSTOM_LANGUAGES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_custom_languages(languages):
    with open(CUSTOM_LANGUAGES_FILE, 'w', encoding='utf-8') as f:
        json.dump(languages, f, ensure_ascii=False, indent=2)

def get_all_languages():
    all_langs = DEFAULT_LANGUAGES.copy()
    all_langs.update(load_custom_languages())
    return all_langs

THREADS_MODELS = load_threads_models()
PHOTO_CATEGORIES = load_photo_categories()
LANGUAGES = get_all_languages()

# ======================
# FUNCIONES CONFIGURACIÓN USUARIOS
# ======================

def caricare_config_utenti():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if os.path.exists(USER_CONFIG_FILE):
        with open(USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salvare_config_utenti(config):
    with open(USER_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_user_config(user_id):
    global user_config
    uid = str(user_id)
    if uid not in user_config:
        user_config[uid] = {"threads_model": "mila", "threads_language": "italian"}
        salvare_config_utenti(user_config)
    return user_config[uid]

def set_user_config(user_id, threads_model=None, threads_language=None):
    global user_config
    uid = str(user_id)
    if uid not in user_config:
        user_config[uid] = {"threads_model": "mila", "threads_language": "italian"}
    if threads_model:
        user_config[uid]["threads_model"] = threads_model
    if threads_language:
        user_config[uid]["threads_language"] = threads_language
    salvare_config_utenti(user_config)

def caricare_config_foto_utenti():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if os.path.exists(USER_PHOTO_CONFIG_FILE):
        with open(USER_PHOTO_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salvare_config_foto_utenti(config):
    with open(USER_PHOTO_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_user_photo_config(user_id):
    global user_photo_config
    uid = str(user_id)
    if uid not in user_photo_config:
        user_photo_config[uid] = {"photo_model": None, "waiting_for_number": False}
        salvare_config_foto_utenti(user_photo_config)
    return user_photo_config[uid]

def set_user_photo_model(user_id, photo_model):
    global user_photo_config
    uid = str(user_id)
    if uid not in user_photo_config:
        user_photo_config[uid] = {"photo_model": None, "waiting_for_number": False}
    user_photo_config[uid]["photo_model"] = photo_model
    user_photo_config[uid]["waiting_for_number"] = True
    salvare_config_foto_utenti(user_photo_config)

def set_photo_waiting_for_number(user_id, waiting):
    global user_photo_config
    uid = str(user_id)
    if uid not in user_photo_config:
        user_photo_config[uid] = {"photo_model": None, "waiting_for_number": False}
    user_photo_config[uid]["waiting_for_number"] = waiting
    if not waiting:
        user_photo_config[uid]["photo_model"] = None
    salvare_config_foto_utenti(user_photo_config)

def is_photo_waiting_for_number(user_id):
    uid = str(user_id)
    if uid in user_photo_config:
        return user_photo_config[uid].get("waiting_for_number", False)
    return False

def get_photo_model_for_user(user_id):
    uid = str(user_id)
    if uid in user_photo_config:
        return user_photo_config[uid].get("photo_model")
    return None

# ======================
# FUNCIONES DE MARCADORES
# ======================

def aplicar_marcadores(texto, language):
    lang_config = LANGUAGES.get(language, DEFAULT_LANGUAGES["english"])
    replacements = lang_config.get("replacements", {})
    resultado = texto
    for marker, value in replacements.items():
        resultado = resultado.replace(marker, value)
    return resultado

# ======================
# FUNCIONES THREADS
# ======================

def caricare_frasi_per_modello(model):
    file_path = os.path.join(DATA_FOLDER, f"frases_{model}.json")
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvare_frasi_per_modello(model, frasi):
    file_path = os.path.join(DATA_FOLDER, f"frases_{model}.json")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(frasi, f, ensure_ascii=False, indent=2)

def caricare_stato_utenti_threads():
    if os.path.exists(USER_STATE_FILE):
        with open(USER_STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salvare_stato_utenti_threads(stato):
    with open(USER_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_utente_threads(user_id):
    stato = caricare_stato_utenti_threads()
    uid = str(user_id)
    if uid not in stato:
        stato[uid] = {"sent_numbers": [], "total_sent": 0}
        salvare_stato_utenti_threads(stato)
    if user_id not in user_threads_state:
        user_threads_state[user_id] = {
            "sent_numbers": set(stato[uid]["sent_numbers"]),
            "total_sent": stato[uid]["total_sent"]
        }

def salvare_stato_utente_threads(user_id):
    if user_id in user_threads_state:
        stato = caricare_stato_utenti_threads()
        uid = str(user_id)
        stato[uid] = {
            "sent_numbers": list(user_threads_state[user_id]["sent_numbers"]),
            "total_sent": user_threads_state[user_id]["total_sent"]
        }
        salvare_stato_utenti_threads(stato)

def ottenere_numeri_disponibili_threads(user_id, quantita):
    inizializzare_stato_utente_threads(user_id)
    inviati = user_threads_state[user_id]["sent_numbers"]
    disponibili = [n for n in range(1, MAX_VARIATIONS + 1) if n not in inviati]
    if not disponibili:
        user_threads_state[user_id] = {"sent_numbers": set(), "total_sent": 0}
        salvare_stato_utente_threads(user_id)
        disponibili = list(range(1, MAX_VARIATIONS + 1))
    random.shuffle(disponibili)
    return disponibili[:quantita]

def marcare_come_inviate_threads(user_id, numeri):
    inizializzare_stato_utente_threads(user_id)
    for num in numeri:
        user_threads_state[user_id]["sent_numbers"].add(num)
        user_threads_state[user_id]["total_sent"] += 1
    salvare_stato_utente_threads(user_id)

async def generare_variazione(model, language, frase_originale, frase_numero, variazione_num):
    model_info = THREADS_MODELS.get(model, {"name": model, "origin": "None", "origin_text": "", "full_name": model})
    lang_info = LANGUAGES.get(language, DEFAULT_LANGUAGES["english"])
    frase_con_marcadores = aplicar_marcadores(frase_originale, language)
    
    if model == "comments" or model_info.get("origin") == "None":
        system_prompt = f"""You are a copywriter. Create ONE variation in {lang_info['name']}.

CRITICAL RULES:
1. Maintain EXACTLY the same structure and meaning.
2. Keep censorship as in original (use * or emojis).
3. Change words, NOT the meaning. Variation number {variazione_num}.
4. PRESERVE format: line breaks, emojis, numbers, lists.
5. Keep teen feminine tone, FIRST PERSON.
6. Adapt cultural references to: {lang_info['context']}
7. DO NOT add extra information.
8. Reply ONLY with the variation text.

Original phrase (number {frase_numero}):
{frase_con_marcadores}

Generate variation {variazione_num} in {lang_info['name']}:"""
    else:
        menciona_nombre = model_info['full_name'].lower() in frase_originale.lower()
        menciona_origen = model_info['origin'].lower() in frase_originale.lower() or model_info['origin_text'].lower() in frase_originale.lower()
        reglas = ""
        if menciona_nombre and menciona_origen:
            reglas = f"\n6. Her name is {model_info['full_name']}. Her origin is {model_info['origin']}. Use ONLY when mentioned."
        elif menciona_nombre:
            reglas = f"\n6. Her name is {model_info['full_name']}. Use ONLY when mentioned."
        elif menciona_origen:
            reglas = f"\n6. Her origin is {model_info['origin']}. Use ONLY when mentioned."
        
        system_prompt = f"""You are a copywriter. Create ONE variation in {lang_info['name']}.

CRITICAL RULES:
1. Maintain EXACTLY the same structure and meaning.
2. Keep censorship as in original (use * or emojis).
3. Change words, NOT the meaning. Variation number {variazione_num}.
4. PRESERVE format: line breaks, emojis, numbers, lists.
{reglas}
8. Keep teen feminine tone, FIRST PERSON.
9. Adapt cultural references to: {lang_info['context']}
10. DO NOT add extra information.
11. Reply ONLY with the variation text.

Original phrase (number {frase_numero}):
{frase_con_marcadores}

Generate variation {variazione_num} in {lang_info['name']}:"""
    
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Generate variation {variazione_num}:"}]
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": messages, "temperature": 0.85, "max_tokens": 800}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content'].strip()
                return f"❌ API Error: {response.status}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ======================
# FUNCIONES FOTOS
# ======================

def init_fotos_db():
    os.makedirs(PHOTOS_FOLDER, exist_ok=True)

def caricare_stato_fotos():
    if os.path.exists(PHOTOS_DB_FILE):
        with open(PHOTOS_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salvare_stato_fotos(stato):
    with open(PHOTOS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_fotos():
    global fotos_global_state
    fotos_global_state = caricare_stato_fotos()

def salvare_stato_fotos_globale():
    salvare_stato_fotos(fotos_global_state)

def aggiungere_foto_per_modello(photo_model, foto_path):
    global fotos_global_state
    if photo_model not in fotos_global_state:
        fotos_global_state[photo_model] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    nuovo_id = fotos_global_state[photo_model]["total"] + 1
    ext = os.path.splitext(foto_path)[1]
    nuovo_nome = f"{photo_model}_foto_{nuovo_id}{ext}"
    nuovo_path = os.path.join(PHOTOS_FOLDER, nuovo_nome)
    shutil.copy2(foto_path, nuovo_path)
    fotos_global_state[photo_model]["metadata"][str(nuovo_id)] = {"path": nuovo_path, "original_name": os.path.basename(foto_path), "used": False}
    fotos_global_state[photo_model]["total"] += 1
    fotos_global_state[photo_model]["disponibili"].append(nuovo_id)
    salvare_stato_fotos_globale()

def ottenere_foto_disponibili_per_modello(photo_model, quantita):
    if photo_model not in fotos_global_state:
        return []
    disponibili = [int(fid) for fid, meta in fotos_global_state[photo_model]["metadata"].items() if not meta.get("used", False)]
    random.shuffle(disponibili)
    return disponibili[:quantita]

def marcare_foto_come_usate_per_modello(photo_model, foto_ids):
    if photo_model not in fotos_global_state:
        return
    for fid in foto_ids:
        fid_str = str(fid)
        if fid_str in fotos_global_state[photo_model]["metadata"]:
            fotos_global_state[photo_model]["metadata"][fid_str]["used"] = True
            if fid in fotos_global_state[photo_model]["disponibili"]:
                fotos_global_state[photo_model]["disponibili"].remove(fid)
            fotos_global_state[photo_model]["usate"].append(fid)
    salvare_stato_fotos_globale()

def get_stato_fotos_per_modello(photo_model):
    if photo_model not in fotos_global_state:
        return 0, 0, 0
    usate = len(fotos_global_state[photo_model]["usate"])
    disponibili = len([f for f in fotos_global_state[photo_model]["metadata"].values() if not f.get("used", False)])
    total = fotos_global_state[photo_model]["total"]
    return usate, disponibili, total

def reset_fotos_per_modello(photo_model):
    global fotos_global_state
    if photo_model in fotos_global_state:
        for fid_str, meta in fotos_global_state[photo_model].get("metadata", {}).items():
            path = meta.get("path")
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass
    fotos_global_state[photo_model] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    salvare_stato_fotos_globale()

# ======================
# FUNCIONES REELS
# ======================

def init_reels_db():
    os.makedirs(REELS_FOLDER, exist_ok=True)

def caricare_stato_reels():
    if os.path.exists(REELS_DB_FILE):
        with open(REELS_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salvare_stato_reels(stato):
    with open(REELS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_reels():
    global reels_global_state
    reels_global_state = caricare_stato_reels()

def salvare_stato_reels_globale():
    salvare_stato_reels(reels_global_state)

def aggiungere_reel_per_iguser(iguser, reel_path):
    global reels_global_state
    if iguser not in reels_global_state:
        reels_global_state[iguser] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    nuovo_id = reels_global_state[iguser]["total"] + 1
    ext = os.path.splitext(reel_path)[1]
    nuovo_nome = f"{iguser}_reel_{nuovo_id}{ext}"
    nuovo_path = os.path.join(REELS_FOLDER, nuovo_nome)
    shutil.copy2(reel_path, nuovo_path)
    reels_global_state[iguser]["metadata"][str(nuovo_id)] = {"path": nuovo_path, "original_name": os.path.basename(reel_path), "used": False}
    reels_global_state[iguser]["total"] += 1
    reels_global_state[iguser]["disponibili"].append(nuovo_id)
    salvare_stato_reels_globale()

def ottenere_reel_disponibile_per_iguser(iguser):
    if iguser not in reels_global_state:
        return None
    disponibili = [int(fid) for fid, meta in reels_global_state[iguser]["metadata"].items() if not meta.get("used", False)]
    if not disponibili:
        return None
    random.shuffle(disponibili)
    return disponibili[0]

def marcare_reel_come_usato_per_iguser(iguser, reel_id):
    if iguser not in reels_global_state:
        return
    rid = str(reel_id)
    if rid in reels_global_state[iguser]["metadata"]:
        reels_global_state[iguser]["metadata"][rid]["used"] = True
        if reel_id in reels_global_state[iguser]["disponibili"]:
            reels_global_state[iguser]["disponibili"].remove(reel_id)
        reels_global_state[iguser]["usate"].append(reel_id)
    salvare_stato_reels_globale()

def get_stato_reels_per_iguser(iguser):
    if iguser not in reels_global_state:
        return 0, 0, 0
    usate = len(reels_global_state[iguser]["usate"])
    disponibili = len([f for f in reels_global_state[iguser]["metadata"].values() if not f.get("used", False)])
    total = reels_global_state[iguser]["total"]
    return usate, disponibili, total

def reset_reels_per_iguser(iguser):
    global reels_global_state
    if iguser in reels_global_state:
        for fid_str, meta in reels_global_state[iguser].get("metadata", {}).items():
            path = meta.get("path")
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass
    reels_global_state[iguser] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    salvare_stato_reels_globale()

def get_all_igusers_with_reels():
    return list(reels_global_state.keys())

# ======================
# NOTIFICHE ADMIN
# ======================

async def notificare_admin(context, messaggio, is_admin_action=False):
    try:
        if is_admin_action:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"👑 <b>ADMIN:</b>\n{messaggio}", parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=messaggio, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")

# ======================
# GESTIÓN DINÁMICA - THREADS MODELS
# ======================

async def admin_add_threads_model(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id != ADMIN_USER_ID:
        await query.answer("❌ Solo admin", show_alert=True)
        return
    await query.answer()
    waiting_for_new_threads_model[user_id] = {"step": "name"}
    await query.edit_message_text(
        "➕ <b>Add New Threads Model</b>\n\n"
        "Step 1/4: Send the model name (with emoji).\n"
        "Example: <code>🇰🇷 Hana</code>\n\n"
        "Type the name now (or /cancel to abort):",
        parse_mode="HTML"
    )

async def handle_new_threads_model_input(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        return
    if user_id not in waiting_for_new_threads_model:
        return
    if update.message.text.startswith('/'):
        if update.message.text.lower() == '/cancel':
            del waiting_for_new_threads_model[user_id]
            await update.message.reply_text("❌ Operation cancelled.")
            await admin_menu(update, context)
        return
    state = waiting_for_new_threads_model[user_id]
    text = update.message.text.strip()
    if state["step"] == "name":
        model_key = text.lower().replace(" ", "_").replace("🇨🇳", "").replace("🇯🇵", "").replace("🇮🇹", "").replace("🇰🇷", "").strip()
        if not model_key:
            model_key = text.lower().replace(" ", "_")
        original_key = model_key
        counter = 1
        while model_key in THREADS_MODELS:
            model_key = f"{original_key}_{counter}"
            counter += 1
        state["model_key"] = model_key
        state["display_name"] = text
        state["step"] = "origin"
        await update.message.reply_text(
            f"✅ Display name: {text}\n🔑 Model key: {model_key}\n\n"
            "Step 2/4: Send the country of origin.\nExample: <code>Korea</code>",
            parse_mode="HTML"
        )
    elif state["step"] == "origin":
        state["origin"] = text
        state["step"] = "origin_text"
        await update.message.reply_text(
            f"✅ Origin: {text}\n\n"
            "Step 3/4: Send 'origin_text' (how she says her origin).\nExample: <code>I'm Korean</code>",
            parse_mode="HTML"
        )
    elif state["step"] == "origin_text":
        state["origin_text"] = text
        state["step"] = "full_name"
        await update.message.reply_text(
            f"✅ Origin text: {text}\n\n"
            "Step 4/4: Send the full name.\nExample: <code>Hana</code>",
            parse_mode="HTML"
        )
    elif state["step"] == "full_name":
        state["full_name"] = text
        new_model = {
            "name": state["display_name"],
            "origin": state["origin"],
            "origin_text": state["origin_text"],
            "full_name": state["full_name"]
        }
        THREADS_MODELS[state["model_key"]] = new_model
        save_threads_models(THREADS_MODELS)
        salvare_frasi_per_modello(state["model_key"], [])
        await update.message.reply_text(
            f"✅ <b>New threads model added!</b>\n\n"
            f"📝 Name: {state['display_name']}\n🔑 Key: {state['model_key']}\n"
            f"🌍 Origin: {state['origin']}\n👤 Full name: {state['full_name']}\n\n"
            f"Use /admin → Upload Threads → {state['display_name']} to upload phrases.",
            parse_mode="HTML"
        )
        await notificare_admin(context, f"➕ Added threads model: {state['display_name']}", True)
        del waiting_for_new_threads_model[user_id]

# ======================
# GESTIÓN DINÁMICA - PHOTO CATEGORIES
# ======================

async def admin_add_photo_category(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id != ADMIN_USER_ID:
        await query.answer("❌ Solo admin", show_alert=True)
        return
    await query.answer()
    waiting_for_new_photo_category[user_id] = {"step": "category_name"}
    await query.edit_message_text(
        "➕ <b>Add New Photo Category</b>\n\n"
        "Send the category name (with emoji).\nExample: <code>🇫🇷 French</code>\n\n"
        "Type the name now (or /cancel to abort):",
        parse_mode="HTML"
    )

async def handle_new_photo_category_input(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        return
    if user_id not in waiting_for_new_photo_category:
        return
    if update.message.text.startswith('/'):
        if update.message.text.lower() == '/cancel':
            del waiting_for_new_photo_category[user_id]
            await update.message.reply_text("❌ Operation cancelled.")
            await admin_menu(update, context)
        return
    text = update.message.text.strip()
    category_key = text.lower().replace(" ", "_").replace("🇫🇷", "").replace("🇪🇸", "").strip()
    if not category_key:
        category_key = text.lower().replace(" ", "_")
    original_key = category_key
    counter = 1
    while category_key in PHOTO_CATEGORIES:
        category_key = f"{original_key}_{counter}"
        counter += 1
    PHOTO_CATEGORIES[category_key] = {"name": text, "models": {}}
    save_photo_categories(PHOTO_CATEGORIES)
    await update.message.reply_text(
        f"✅ <b>New photo category added!</b>\n\n📁 Category: {text}\n🔑 Key: {category_key}",
        parse_mode="HTML"
    )
    await notificare_admin(context, f"➕ Added photo category: {text}", True)
    del waiting_for_new_photo_category[user_id]

# ======================
# GESTIÓN DINÁMICA - PHOTO MODELS
# ======================

async def admin_add_photo_model(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id != ADMIN_USER_ID:
        await query.answer("❌ Solo admin", show_alert=True)
        return
    await query.answer()
    keyboard = []
    for cat_key, cat_data in PHOTO_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_data["name"], callback_data=f"add_photo_model_cat_{cat_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "➕ <b>Add New Photo Model</b>\n\nSelect category:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def admin_add_photo_model_category(update, context, category_key):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    waiting_for_new_photo_model[user_id] = {"step": "model_name", "category_key": category_key}
    await query.edit_message_text(
        f"➕ <b>Add Model to {PHOTO_CATEGORIES[category_key]['name']}</b>\n\n"
        "Send the model name (with emoji).\nExample: <code>🇰🇷 Jiyeon</code>\n\n"
        "Type now (or /cancel to abort):",
        parse_mode="HTML"
    )

async def handle_new_photo_model_input(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        return
    if user_id not in waiting_for_new_photo_model:
        return
    if update.message.text.startswith('/'):
        if update.message.text.lower() == '/cancel':
            del waiting_for_new_photo_model[user_id]
            await update.message.reply_text("❌ Operation cancelled.")
            await admin_menu(update, context)
        return
    state = waiting_for_new_photo_model[user_id]
    text = update.message.text.strip()
    model_key = text.lower().replace(" ", "_").replace("🇨🇳", "").replace("🇯🇵", "").replace("🇮🇹", "").replace("🇰🇷", "").replace("🇫🇷", "").strip()
    if not model_key:
        model_key = text.lower().replace(" ", "_")
    original_key = model_key
    counter = 1
    while model_key in PHOTO_CATEGORIES[state["category_key"]]["models"]:
        model_key = f"{original_key}_{counter}"
        counter += 1
    PHOTO_CATEGORIES[state["category_key"]]["models"][model_key] = {"name": text, "display": text}
    save_photo_categories(PHOTO_CATEGORIES)
    if model_key not in fotos_global_state:
        fotos_global_state[model_key] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
        salvare_stato_fotos_globale()
    await update.message.reply_text(
        f"✅ <b>New photo model added!</b>\n\n📸 Model: {text}\n🔑 Key: {model_key}\n"
        f"📁 Category: {PHOTO_CATEGORIES[state['category_key']]['name']}\n\n"
        f"Use /admin → Upload Photos → {PHOTO_CATEGORIES[state['category_key']]['name']} → {text} to upload photos.",
        parse_mode="HTML"
    )
    await notificare_admin(context, f"➕ Added photo model: {text}", True)
    del waiting_for_new_photo_model[user_id]

# ======================
# GESTIÓN DINÁMICA - LANGUAGES
# ======================

async def admin_add_language(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id != ADMIN_USER_ID:
        await query.answer("❌ Solo admin", show_alert=True)
        return
    await query.answer()
    waiting_for_new_language[user_id] = {"step": "lang_key"}
    await query.edit_message_text(
        "➕ <b>Add New Language</b>\n\n"
        "Step 1/5: Send language key (lowercase, unique).\nExample: <code>dutch</code>\n\n"
        "Type now (or /cancel to abort):",
        parse_mode="HTML"
    )

async def handle_new_language_input(update, context):
    global LANGUAGES
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        return
    if user_id not in waiting_for_new_language:
        return
    if update.message.text.startswith('/'):
        if update.message.text.lower() == '/cancel':
            del waiting_for_new_language[user_id]
            await update.message.reply_text("❌ Operation cancelled.")
            await admin_menu(update, context)
        return
    state = waiting_for_new_language[user_id]
    text = update.message.text.strip()
    if state["step"] == "lang_key":
        if not text.isalpha():
            await update.message.reply_text("❌ Language key must contain only letters. Try again:")
            return
        state["lang_key"] = text.lower()
        state["step"] = "lang_name"
        await update.message.reply_text(
            f"✅ Language key: {text.lower()}\n\n"
            "Step 2/5: Send display name (with emoji).\nExample: <code>🇳🇱 Nederlands</code>",
            parse_mode="HTML"
        )
    elif state["step"] == "lang_name":
        state["lang_name"] = text
        state["step"] = "lang_code"
        await update.message.reply_text(
            f"✅ Display name: {text}\n\n"
            "Step 3/5: Send language code (ISO 639-1).\nExample: <code>nl</code>",
            parse_mode="HTML"
        )
    elif state["step"] == "lang_code":
        state["lang_code"] = text.lower()
        state["step"] = "context"
        await update.message.reply_text(
            f"✅ Language code: {text.lower()}\n\n"
            "Step 4/5: Send context description.\n"
            "Example: <code>Dutch men, Dutch food (stroopwafels, cheese), Dutch places (Amsterdam), Dutch culture (bicycles, canals)</code>",
            parse_mode="HTML"
        )
    elif state["step"] == "context":
        state["context"] = text
        state["step"] = "replacements"
        await update.message.reply_text(
            f"✅ Context saved.\n\n"
            "Step 5/5: Send REPLACEMENTS as JSON.\n"
            "Example:\n<code>{\n"
            '  "[MEN]": "Dutch men",\n'
            '  "[MEN_SINGULAR]": "a Dutch man",\n'
            '  "[COUNTRY]": "Netherlands",\n'
            '  "[COUNTRY_ADJ]": "Dutch",\n'
            '  "[FLAG]": "🇳🇱",\n'
            '  "[FOOD]": "Dutch food (stroopwafels, cheese)",\n'
            '  "[CULTURE]": "bicycles and canals",\n'
            '  "[LOVE_SYMBOL]": "🌷"\n'
            "}</code>",
            parse_mode="HTML"
        )
    elif state["step"] == "replacements":
        try:
            replacements = json.loads(text)
            required = ["[MEN]", "[MEN_SINGULAR]", "[COUNTRY]", "[COUNTRY_ADJ]", "[FLAG]", "[FOOD]", "[CULTURE]", "[LOVE_SYMBOL]"]
            missing = [k for k in required if k not in replacements]
            if missing:
                await update.message.reply_text(f"❌ Missing keys: {missing}. Try again.")
                return
            new_lang = {
                "name": state["lang_name"],
                "code": state["lang_code"],
                "context": state["context"],
                "replacements": replacements
            }
            custom = load_custom_languages()
            custom[state["lang_key"]] = new_lang
            save_custom_languages(custom)
            LANGUAGES = get_all_languages()
            await update.message.reply_text(
                f"✅ <b>New language added!</b>\n\n"
                f"🌍 Language: {state['lang_name']}\n🔑 Key: {state['lang_key']}\n📇 Code: {state['lang_code']}\n\n"
                f"Users can now select this language!",
                parse_mode="HTML"
            )
            await notificare_admin(context, f"➕ Added language: {state['lang_name']}", True)
            del waiting_for_new_language[user_id]
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON. Please send a valid JSON object.")

# ======================
# RESET PHOTOS/REELS
# ======================

async def reset_photos_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for cat_key, cat_data in PHOTO_CATEGORIES.items():
        for model_key, model_data in cat_data["models"].items():
            keyboard.append([InlineKeyboardButton(f"{cat_data['name']} - {model_data['name']}", callback_data=f"reset_photo_{model_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🔄 <b>RESET PHOTOS</b>\n\nSelect model to reset:", reply_markup=reply_markup, parse_mode="HTML")

async def reset_reels_menu(update, context):
    query = update.callback_query
    await query.answer()
    igusers = get_all_igusers_with_reels()
    if not igusers:
        await query.edit_message_text("❌ No reels found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]), parse_mode="HTML")
        return
    keyboard = []
    for iguser in igusers:
        used, available, total = get_stato_reels_per_iguser(iguser)
        icon = "🟢" if available > 0 else "🔴"
        keyboard.append([InlineKeyboardButton(f"{icon} @{iguser} ({available}/{total})", callback_data=f"reset_reel_{iguser}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🔄 <b>RESET REELS</b>\n\nSelect user to reset:", reply_markup=reply_markup, parse_mode="HTML")

async def confirm_reset(update, context, reset_type, target):
    query = update.callback_query
    await query.answer()
    if reset_type == "photo":
        model_name = target
        for cat_key, cat_data in PHOTO_CATEGORIES.items():
            for model_key, model_data in cat_data["models"].items():
                if model_key == target:
                    model_name = model_data["name"]
                    break
        keyboard = [
            [InlineKeyboardButton("✅ YES, RESET", callback_data=f"confirm_reset_photo_{target}")],
            [InlineKeyboardButton("❌ NO, CANCEL", callback_data="admin_reset")]
        ]
        await query.edit_message_text(
            f"⚠️ <b>CONFIRM RESET</b>\n\nReset ALL photos for:\n📸 {model_name}\n\nIRREVERSIBLE! Are you sure?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    else:
        keyboard = [
            [InlineKeyboardButton("✅ YES, RESET", callback_data=f"confirm_reset_reel_{target}")],
            [InlineKeyboardButton("❌ NO, CANCEL", callback_data="admin_reset")]
        ]
        await query.edit_message_text(
            f"⚠️ <b>CONFIRM RESET</b>\n\nReset ALL reels for:\n🎬 @{target}\n\nIRREVERSIBLE! Are you sure?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

async def execute_reset(update, context, reset_type, target):
    query = update.callback_query
    await query.answer()
    if reset_type == "photo":
        reset_fotos_per_modello(target)
        model_name = target
        for cat_key, cat_data in PHOTO_CATEGORIES.items():
            for model_key, model_data in cat_data["models"].items():
                if model_key == target:
                    model_name = model_data["name"]
                    break
        await query.edit_message_text(f"✅ Photos for {model_name} have been reset.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]), parse_mode="HTML")
    else:
        reset_reels_per_iguser(target)
        await query.edit_message_text(f"✅ Reels for @{target} have been reset.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_back")]]), parse_mode="HTML")
    await notificare_admin(context, f"🔄 Reset: {reset_type} - {target}", True)

# ======================
# MENUS ADMIN
# ======================

async def admin_menu(update, context):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin can use this.")
        return
    keyboard = [
        [InlineKeyboardButton("📝 Upload Threads", callback_data="admin_threads")],
        [InlineKeyboardButton("📸 Upload Photos", callback_data="admin_photos")],
        [InlineKeyboardButton("🎬 Upload Reels", callback_data="admin_reels")],
        [InlineKeyboardButton("➕ Add Threads Model", callback_data="admin_add_threads_model")],
        [InlineKeyboardButton("➕ Add Photo Category", callback_data="admin_add_photo_category")],
        [InlineKeyboardButton("➕ Add Photo Model", callback_data="admin_add_photo_model")],
        [InlineKeyboardButton("🌍 Add Language", callback_data="admin_add_language")],
        [InlineKeyboardButton("🔄 Reset Photos", callback_data="admin_reset_photos")],
        [InlineKeyboardButton("🔄 Reset Reels", callback_data="admin_reset_reels")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👑 <b>Admin Menu</b>", reply_markup=reply_markup, parse_mode="HTML")

async def admin_threads_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, model in THREADS_MODELS.items():
        keyboard.append([InlineKeyboardButton(model["name"], callback_data=f"admin_threads_{key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📝 Select model to upload THREADS:", reply_markup=reply_markup, parse_mode="HTML")

async def admin_photos_category(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for cat_key, cat_data in PHOTO_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_data["name"], callback_data=f"admin_photos_{cat_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📸 Select category:", reply_markup=reply_markup, parse_mode="HTML")

async def admin_photos_models(update, context, category_key):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for model_key, model_data in PHOTO_CATEGORIES[category_key]["models"].items():
        keyboard.append([InlineKeyboardButton(model_data["name"], callback_data=f"admin_photos_model_{model_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_photos")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"📸 Select model for {PHOTO_CATEGORIES[category_key]['name']}:", reply_markup=reply_markup, parse_mode="HTML")

async def admin_reels_prompt(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎬 <b>Upload REELS</b>\n\n"
        "Type the Instagram username.\nExample: <code>milae</code>\n\n"
        "Then send videos. When done, type /done",
        parse_mode="HTML"
    )
    waiting_for_reels_iguser[ADMIN_USER_ID] = True

async def admin_handle_reels_iguser(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        return
    if not waiting_for_reels_iguser.get(user_id):
        return
    iguser = update.message.text.strip().lower()
    if not iguser:
        await update.message.reply_text("❌ Type a valid username.")
        return
    del waiting_for_reels_iguser[user_id]
    waiting_for_reel_upload[user_id] = iguser
    if user_id not in pending_uploads:
        pending_uploads[user_id] = {"type": "reels", "target": iguser, "files": []}
    await update.message.reply_text(
        f"🎬 Uploading reels for @{iguser}\n\nSend videos. When done, type /done",
        parse_mode="HTML"
    )

# ======================
# MENUS USUARIO
# ======================

async def user_menu(update, context):
    keyboard = [
        [InlineKeyboardButton("📝 Threads", callback_data="user_threads")],
        [InlineKeyboardButton("📸 Photos", callback_data="user_photos")],
        [InlineKeyboardButton("🎬 Reels", callback_data="user_reels")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📱 <b>Main Menu</b>", reply_markup=reply_markup, parse_mode="HTML")

async def user_threads_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, model in THREADS_MODELS.items():
        keyboard.append([InlineKeyboardButton(model["name"], callback_data=f"user_threads_model_{key}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🌸 Choose model:", reply_markup=reply_markup, parse_mode="HTML")

async def user_threads_language(update, context, model):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for lang_key, lang_info in LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(lang_info["name"], callback_data=f"user_threads_lang_{model}_{lang_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_threads")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"🌍 Choose language for {THREADS_MODELS[model]['name']}:", reply_markup=reply_markup, parse_mode="HTML")

async def user_photos_category(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for cat_key, cat_data in PHOTO_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_data["name"], callback_data=f"user_photos_{cat_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📸 Select category:", reply_markup=reply_markup, parse_mode="HTML")

async def user_photos_models(update, context, category_key):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for model_key, model_data in PHOTO_CATEGORIES[category_key]["models"].items():
        _, available, _ = get_stato_fotos_per_modello(model_key)
        icon = "🟢" if available > 0 else "🔴"
        keyboard.append([InlineKeyboardButton(f"{icon} {model_data['name']}", callback_data=f"user_photos_model_{model_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_photos")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"📸 Select model ({PHOTO_CATEGORIES[category_key]['name']}):\n🟢=available 🔴=none", reply_markup=reply_markup, parse_mode="HTML")

async def user_reels_prompt(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎬 <b>Get a REEL</b>\n\n"
        "Type the Instagram username.\nExample: <code>bellamoreno</code>\n\n"
        "⚠️ ONE reel, one-time use.",
        parse_mode="HTML"
    )
    context.user_data["waiting_for_reel_iguser"] = True

async def user_handle_reel_request(update, context):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    if not context.user_data.get("waiting_for_reel_iguser"):
        return
    iguser = update.message.text.strip().lower()
    context.user_data["waiting_for_reel_iguser"] = False
    if not iguser:
        await update.message.reply_text("❌ Type a valid username.")
        return
    if iguser not in reels_global_state or reels_global_state[iguser]["total"] == 0:
        await update.message.reply_text(f"❌ No reels for @{iguser}.")
        return
    used, available, total = get_stato_reels_per_iguser(iguser)
    if available <= THRESHOLD_REELS and available > 0:
        await notificare_admin(context, f"⚠️ LOW REELS - @{iguser}: {available} left", True)
    if available == 0:
        await update.message.reply_text(f"❌ No reels for @{iguser}. All used!")
        return
    reel_id = ottenere_reel_disponibile_per_iguser(iguser)
    if not reel_id:
        await update.message.reply_text(f"❌ No reels available.")
        return
    meta = reels_global_state[iguser]["metadata"].get(str(reel_id), {})
    path = meta.get("path")
    if path and os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                await update.message.reply_video(video=f, caption=f"🎬 Reel from @{iguser}")
            marcare_reel_come_usato_per_iguser(iguser, reel_id)
            await notificare_admin(context, f"🎬 @{username} received reel from @{iguser}")
            await update.message.reply_text(f"✅ Reel sent!", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending reel: {e}")
            await update.message.reply_text("❌ Error sending reel.")
    else:
        await update.message.reply_text("❌ Reel file not found.")

# ======================
# HANDLERS DE ARCHIVOS
# ======================

async def receive_file(update, context):
    user_id = update.effective_user.id
    if user_id not in waiting_for_file:
        return
    model_name = waiting_for_file[user_id]
    if not update.message.document:
        return
    if not update.message.document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ File must be .txt")
        return
    status = await update.message.reply_text("📥 Processing...")
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
            match = re.match(r'^(\d{1,2})\.\s+(.*)', line)
            if match:
                if curr_num is not None and curr_text:
                    frases.append({"numero": curr_num, "testo": "\n".join(curr_text).strip()})
                curr_num = int(match.group(1))
                curr_text = [match.group(2)]
            else:
                if curr_text is not None:
                    curr_text.append(line)
        if curr_num is not None and curr_text:
            frases.append({"numero": curr_num, "testo": "\n".join(curr_text).strip()})
        if not frases:
            await status.edit_text("❌ No numbered phrases found.")
            return
        salvare_frasi_per_modello(model_name, frases)
        del waiting_for_file[user_id]
        preview = "\n".join([f"📌 <b>{f['numero']}:</b> {f['testo'][:60]}..." for f in frases[:5]])
        await status.edit_text(f"✅ Loaded {len(frases)} phrases for {THREADS_MODELS[model_name]['name']}\n\n{preview}", parse_mode="HTML")
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)}")

async def receive_media_upload(update, context):
    user_id = update.effective_user.id
    has_session = False
    upload_type = None
    target = None
    if user_id in pending_uploads:
        has_session = True
        upload_type = pending_uploads[user_id]["type"]
        target = pending_uploads[user_id]["target"]
    elif user_id in waiting_for_reel_upload:
        has_session = True
        upload_type = "reels"
        target = waiting_for_reel_upload[user_id]
        if user_id not in pending_uploads:
            pending_uploads[user_id] = {"type": "reels", "target": target, "files": []}
    elif user_id in waiting_for_photo_upload:
        has_session = True
        upload_type = "photos"
        target = waiting_for_photo_upload[user_id]
        if user_id not in pending_uploads:
            pending_uploads[user_id] = {"type": "photos", "target": target, "files": []}
    if not has_session:
        return
    added = 0
    temp_path = None
    if update.message.video:
        video = update.message.video
        file = await context.bot.get_file(video.file_id)
        ext = ".mp4" if not video.file_name else os.path.splitext(video.file_name)[1]
        temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}{ext}"
        await file.download_to_drive(temp_path)
        added += 1
    elif update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}.jpg"
        await file.download_to_drive(temp_path)
        added += 1
    elif update.message.document:
        doc = update.message.document
        fname = doc.file_name or ""
        ext = os.path.splitext(fname)[1].lower()
        mime = doc.mime_type or ""
        is_video = ext in ['.mov', '.mp4', '.avi'] or mime.startswith('video/')
        is_image = ext in ['.jpg', '.jpeg', '.png'] or mime.startswith('image/')
        if is_video or is_image:
            file = await context.bot.get_file(doc.file_id)
            temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}{ext}"
            await file.download_to_drive(temp_path)
            added += 1
    if added > 0 and temp_path:
        pending_uploads[user_id]["files"].append(temp_path)
        total = len(pending_uploads[user_id]["files"])
        if upload_type == "photos":
            if total % PHOTO_CONFIRMATION_BATCH == 0:
                await update.message.reply_text(f"📦 Loaded {total} photos for {target}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"✅ Received {total} reels for @{target}", parse_mode="HTML")

async def done_command(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin.")
        return
    if user_id not in pending_uploads or not pending_uploads[user_id]["files"]:
        await update.message.reply_text("❌ No files to process.\nUse /admin → Upload first.")
        return
    upload_type = pending_uploads[user_id]["type"]
    target = pending_uploads[user_id]["target"]
    files = pending_uploads[user_id]["files"]
    total_files = len(files)
    status = await update.message.reply_text(f"📥 Processing {total_files} files...")
    success = 0
    for path in files:
        try:
            if upload_type == "photos":
                aggiungere_foto_per_modello(target, path)
            else:
                aggiungere_reel_per_iguser(target, path)
            success += 1
        except Exception as e:
            logger.error(f"Error: {e}")
    for path in files:
        if os.path.exists(path):
            try:
                os.unlink(path)
            except:
                pass
    del pending_uploads[user_id]
    if upload_type == "photos":
        used, avail, total = get_stato_fotos_per_modello(target)
        await status.edit_text(f"✅ Loaded {success}/{total_files} photos for {target}\n📊 Total: {total}, Available: {avail}, Used: {used}", parse_mode="HTML")
    else:
        used, avail, total = get_stato_reels_per_iguser(target)
        await status.edit_text(f"✅ Loaded {success}/{total_files} reels for @{target}\n📊 Total: {total}, Available: {avail}, Used: {used}", parse_mode="HTML")
    await notificare_admin(context, f"📦 Loaded {success} files for {target}", True)

# ======================
# HANDLER NUMEROS (THREADS Y FOTOS)
# ======================

async def handle_number_message(update, context):
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()
    if not text.isdigit():
        return
    qty = int(text)
    if qty < 1 or qty > MAX_VARIATIONS:
        await update.message.reply_text(f"❌ Number 1-{MAX_VARIATIONS}")
        return
    if is_photo_waiting_for_number(user_id):
        photo_model = get_photo_model_for_user(user_id)
        if photo_model:
            await send_photos_to_user(update, context, user_id, photo_model, qty)
            set_photo_waiting_for_number(user_id, False)
            return
    await generate_threads_for_user(update, context, user_id, qty)

async def generate_threads_for_user(update, context, user_id, qty):
    user = update.effective_user
    username = user.username or user.first_name
    config = get_user_config(user_id)
    model = config["threads_model"]
    language = config["threads_language"]
    frases = caricare_frasi_per_modello(model)
    if not frases:
        await update.message.reply_text(f"❌ No phrases for {THREADS_MODELS[model]['name']}.")
        return
    numbers = ottenere_numeri_disponibili_threads(user_id, qty)
    await notificare_admin(context, f"🔄 @{username} requested {len(numbers)} threads | {THREADS_MODELS[model]['name']} | {LANGUAGES[language]['name']}")
    await update.message.reply_text(f"🎲 Generating {len(numbers)} threads...", parse_mode="HTML")
    sent = []
    mixed = frases.copy()
    random.shuffle(mixed)
    for i, num in enumerate(numbers):
        phrase = mixed[i % len(mixed)]
        var = await generare_variazione(model, language, phrase["testo"], phrase["numero"], num)
        if var and not var.startswith("❌"):
            await update.message.reply_text(var, parse_mode="HTML")
            sent.append(num)
            await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(f"❌ Error generating variation {num}")
    marcare_come_inviate_threads(user_id, sent)
    total_rec = user_threads_state[user_id]["total_sent"]
    await update.message.reply_text(f"✅ Threads sent!\n\n📨 Sent: {len(sent)}\n📊 Total: {total_rec}", parse_mode="HTML")

async def send_photos_to_user(update, context, user_id, photo_model, qty):
    user = update.effective_user
    username = user.username or user.first_name
    used, avail, total = get_stato_fotos_per_modello(photo_model)
    if avail <= THRESHOLD_FOTOS and avail > 0:
        await notificare_admin(context, f"⚠️ LOW PHOTOS - {photo_model}: {avail} left", True)
    if total == 0 or avail == 0:
        await update.message.reply_text(f"❌ No photos for {photo_model}.")
        return
    if avail < qty:
        await update.message.reply_text(f"⚠️ Only {avail} photos available. Sending {avail}.")
        qty = avail
    ids = ottenere_foto_disponibili_per_modello(photo_model, qty)
    await update.message.reply_text(f"📸 Sending {len(ids)} photos...")
    sent = []
    for i, fid in enumerate(ids, 1):
        path = fotos_global_state[photo_model]["metadata"][str(fid)]["path"]
        if path and os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    await update.message.reply_photo(photo=f, caption=f"📸 Photo {i}/{len(ids)}")
                sent.append(fid)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Error: {e}")
    if sent:
        marcare_foto_come_usate_per_modello(photo_model, sent)
    await update.message.reply_text(f"✅ Photos sent!\n\n📨 Sent: {len(sent)}", parse_mode="HTML")

# ======================
# COMANDOS ADMIN - ESTADOS
# ======================

async def all_users_status(update, context):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin.")
        return
    stato = caricare_stato_utenti_threads()
    config = caricare_config_utenti()
    if not stato:
        await update.message.reply_text("📊 No users found.")
        return
    msg = "📊 <b>ALL USERS</b>\n\n"
    for uid, data in sorted(stato.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        total = data.get("total_sent", 0)
        remaining = MAX_VARIATIONS - (total % MAX_VARIATIONS)
        user_cfg = config.get(uid, {})
        model = user_cfg.get("threads_model", "mila")
        lang = user_cfg.get("threads_language", "italian")
        try:
            chat = await context.bot.get_chat(int(uid))
            name = chat.username or chat.first_name or uid
        except:
            name = uid
        msg += f"👤 @{name}\n   📝 {total} rec, {remaining} to cycle\n   🌸 {THREADS_MODELS[model]['name']} | {LANGUAGES[lang]['name']}\n\n"
        if len(msg) > 3500:
            await update.message.reply_text(msg, parse_mode="HTML")
            msg = ""
    if msg:
        await update.message.reply_text(msg, parse_mode="HTML")

async def user_stats(update, context):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /userstats <id>")
        return
    uid = context.args[0]
    if not uid.isdigit():
        await update.message.reply_text("❌ ID must be a number.")
        return
    stato = caricare_stato_utenti_threads()
    config = caricare_config_utenti()
    data = stato.get(uid, {})
    total = data.get("total_sent", 0)
    remaining = MAX_VARIATIONS - (total % MAX_VARIATIONS)
    nums = data.get("sent_numbers", [])
    user_cfg = config.get(uid, {})
    model = user_cfg.get("threads_model", "mila")
    lang = user_cfg.get("threads_language", "italian")
    try:
        chat = await context.bot.get_chat(int(uid))
        name = chat.username or chat.first_name or uid
    except:
        name = uid
    msg = f"📊 <b>USER - @{name}</b>\n🆔 {uid}\n\n📝 THREADS:\n• Model: {THREADS_MODELS[model]['name']}\n• Language: {LANGUAGES[lang]['name']}\n• Total: {total}\n• Remaining: {remaining}\n• Numbers used: {len(nums)}/50"
    await update.message.reply_text(msg, parse_mode="HTML")

# ======================
# COMANDOS BASE
# ======================

async def start(update, context):
    user = update.effective_user
    user_id = user.id
    name = user.username or user.first_name
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"👤 New user: @{name} (ID: {user_id})")
    config = get_user_config(user_id)
    model = THREADS_MODELS[config["threads_model"]]["name"]
    lang = LANGUAGES[config["threads_language"]]["name"]
    await update.message.reply_text(
        f"Hello @{name}! 👋\n\n📱 Use /menu\n\n📊 Threads settings:\n🌸 Model: {model}\n🌍 Language: {lang}",
        parse_mode="HTML"
    )

async def status_command(update, context):
    user_id = update.effective_user.id
    inizializzare_stato_utente_threads(user_id)
    total = user_threads_state[user_id]["total_sent"]
    remaining = MAX_VARIATIONS - (total % MAX_VARIATIONS)
    config = get_user_config(user_id)
    model = THREADS_MODELS[config["threads_model"]]["name"]
    lang = LANGUAGES[config["threads_language"]]["name"]
    await update.message.reply_text(
        f"📊 Your Status\n\n🌸 Model: {model}\n🌍 Language: {lang}\n📝 Threads received: {total}\n🔄 Remaining: {remaining}",
        parse_mode="HTML"
    )

async def reset_command(update, context):
    user_id = update.effective_user.id
    user_threads_state[user_id] = {"sent_numbers": set(), "total_sent": 0}
    salvare_stato_utente_threads(user_id)
    await update.message.reply_text("🔄 Thread progress reset!")

async def menu_command(update, context):
    await user_menu(update, context)

# ======================
# MANEJADOR PRINCIPAL DE CALLBACKS
# ======================

async def handle_callback(update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # Botones de navegación
    if data == "admin_back":
        await admin_menu(update, context)
        return
    elif data == "user_back":
        await user_menu(update, context)
        return
    
    # Admin - Threads
    if data == "admin_threads":
        await admin_threads_menu(update, context)
    elif data.startswith("admin_threads_"):
        model = data.replace("admin_threads_", "")
        waiting_for_file[user_id] = model
        await query.edit_message_text(
            f"📁 Send .txt file for {THREADS_MODELS[model]['name']}\n\nFormat: 1. text\n2. text\n...",
            parse_mode="HTML"
        )
    
    # Admin - Photos
    elif data == "admin_photos":
        await admin_photos_category(update, context)
    elif data.startswith("admin_photos_") and data not in ["admin_photos", "admin_photos_asian", "admin_photos_italian"]:
        cat = data.replace("admin_photos_", "")
        if cat in PHOTO_CATEGORIES:
            await admin_photos_models(update, context, cat)
    elif data.startswith("admin_photos_model_"):
        model = data.replace("admin_photos_model_", "")
        waiting_for_photo_upload[user_id] = model
        if user_id not in pending_uploads:
            pending_uploads[user_id] = {"type": "photos", "target": model, "files": []}
        await query.edit_message_text(f"📸 Send photos for {model}\nWhen done, type /done", parse_mode="HTML")
    
    # Admin - Reels
    elif data == "admin_reels":
        await admin_reels_prompt(update, context)
    
    # Admin - Add Threads Model
    elif data == "admin_add_threads_model":
        await admin_add_threads_model(update, context)
    
    # Admin - Add Photo Category
    elif data == "admin_add_photo_category":
        await admin_add_photo_category(update, context)
    
    # Admin - Add Photo Model
    elif data == "admin_add_photo_model":
        await admin_add_photo_model(update, context)
    elif data.startswith("add_photo_model_cat_"):
        cat = data.replace("add_photo_model_cat_", "")
        await admin_add_photo_model_category(update, context, cat)
    
    # Admin - Add Language
    elif data == "admin_add_language":
        await admin_add_language(update, context)
    
    # Admin - Reset
    elif data == "admin_reset_photos":
        await reset_photos_menu(update, context)
    elif data == "admin_reset_reels":
        await reset_reels_menu(update, context)
    elif data == "admin_reset":
        await admin_menu(update, context)
    elif data.startswith("reset_photo_"):
        model = data.replace("reset_photo_", "")
        await confirm_reset(update, context, "photo", model)
    elif data.startswith("reset_reel_"):
        ig = data.replace("reset_reel_", "")
        await confirm_reset(update, context, "reel", ig)
    elif data.startswith("confirm_reset_photo_"):
        model = data.replace("confirm_reset_photo_", "")
        await execute_reset(update, context, "photo", model)
    elif data.startswith("confirm_reset_reel_"):
        ig = data.replace("confirm_reset_reel_", "")
        await execute_reset(update, context, "reel", ig)
    
    # User - Threads
    elif data == "user_threads":
        await user_threads_menu(update, context)
    elif data.startswith("user_threads_model_"):
        model = data.replace("user_threads_model_", "")
        await user_threads_language(update, context, model)
    elif data.startswith("user_threads_lang_"):
        parts = data.split("_")
        model = parts[3]
        lang = parts[4]
        set_user_config(user_id, threads_model=model, threads_language=lang)
        await query.edit_message_text(
            f"✅ Threads configured!\n\n🌸 {THREADS_MODELS[model]['name']}\n🌍 {LANGUAGES[lang]['name']}\n\nNow type number of threads (e.g., 5)",
            parse_mode="HTML"
        )
    
    # User - Photos
    elif data == "user_photos":
        await user_photos_category(update, context)
    elif data.startswith("user_photos_") and data not in ["user_photos", "user_photos_asian", "user_photos_italian"]:
        cat = data.replace("user_photos_", "")
        if cat in PHOTO_CATEGORIES:
            await user_photos_models(update, context, cat)
    elif data.startswith("user_photos_model_"):
        model = data.replace("user_photos_model_", "")
        set_user_photo_model(user_id, model)
        name = model
        for cat in PHOTO_CATEGORIES.values():
            for mk, md in cat["models"].items():
                if mk == model:
                    name = md["name"]
                    break
        await query.edit_message_text(
            f"✅ Photos configured!\n\n📸 Model: {name}\n\nNow type number of photos (e.g., 3)\n⚠️ ONE-TIME USE!",
            parse_mode="HTML"
        )
    
    # User - Reels
    elif data == "user_reels":
        await user_reels_prompt(update, context)

# ======================
# FUNCIONES PARA MANEJAR TEXTO (CREACIÓN)
# ======================

async def handle_text_input(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        return
    if user_id in waiting_for_new_threads_model:
        await handle_new_threads_model_input(update, context)
    elif user_id in waiting_for_new_photo_category:
        await handle_new_photo_category_input(update, context)
    elif user_id in waiting_for_new_photo_model:
        await handle_new_photo_model_input(update, context)
    elif user_id in waiting_for_new_language:
        await handle_new_language_input(update, context)

# ======================
# MAIN
# ======================

def main():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    os.makedirs(PHOTOS_FOLDER, exist_ok=True)
    os.makedirs(REELS_FOLDER, exist_ok=True)
    
    for model in THREADS_MODELS:
        if not os.path.exists(os.path.join(DATA_FOLDER, f"frases_{model}.json")):
            salvare_frasi_per_modello(model, [])
    
    for cat in PHOTO_CATEGORIES.values():
        for model in cat["models"]:
            if model not in fotos_global_state:
                fotos_global_state[model] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    
    inizializzare_stato_fotos()
    inizializzare_stato_reels()
    
    global user_config, user_photo_config
    user_config = caricare_config_utenti()
    user_photo_config = caricare_config_foto_utenti()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Admin
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler("allusers", all_users_status))
    app.add_handler(CommandHandler("userstats", user_stats))
    app.add_handler(CommandHandler("done", done_command))
    
    # User
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reset", reset_command))
    
    # Handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_handle_reel_request))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handle_reels_iguser))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, receive_file))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, receive_media_upload))
    
    print("=" * 60)
    print("✅ BOT COMPLETO - THREADS + PHOTOS + REELS")
    print("=" * 60)
    print(f"🤖 Bot online")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()