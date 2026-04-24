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
REELS_FOLDER = os.path.join(DATA_FOLDER, "reels")
REELS_DB_FILE = os.path.join(DATA_FOLDER, "reels_db.json")

# Modelos para THREADS
THREADS_MODELS = {
    "mila": {"name": "🇨🇳 Mila", "origin": "Chinese", "origin_text": "I'm Chinese", "full_name": "Mila"},
    "yuna": {"name": "🇯🇵 Yuna", "origin": "Japanese", "origin_text": "I'm Japanese", "full_name": "Yuna"},
    "ita": {"name": "🇮🇹 ITA Models", "origin": "Italian", "origin_text": "I'm Italian", "full_name": "ITA Models"}
}

# Modelos para FOTOS
PHOTO_MODELS = {
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
    "elira": {"name": "🇮🇹 Elira", "category": "italian", "display": "Elira"},
    "bella": {"name": "🇮🇹 Bella", "category": "italian", "display": "Bella"},
    "milena": {"name": "🇮🇹 Milena", "category": "italian", "display": "Milena"},
    "isabella": {"name": "🇮🇹 Isabella", "category": "italian", "display": "Isabella"},
    "laura": {"name": "🇮🇹 Laura", "category": "italian", "display": "Laura"},
    "aurora": {"name": "🇮🇹 Aurora", "category": "italian", "display": "Aurora"}
}

# Idiomas para THREADS
LANGUAGES = {
    "italian": {"name": "🇮🇹 Italiano", "code": "it", "context": "Italian men, Italian food (pasta, pizza, gelato), Italian places (Rome, Milan, Venice)"},
    "german": {"name": "🇩🇪 Deutsch", "code": "de", "context": "German men, German food (Bratwurst, Sauerkraut, Pretzels), German places (Berlin, Munich, Hamburg)"},
    "portuguese": {"name": "🇧🇷 Português", "code": "pt", "context": "Brazilian men, Brazilian food (Feijoada, Pão de Queijo), Brazilian places (Rio de Janeiro, São Paulo)"},
    "english": {"name": "🇺🇸 English", "code": "en", "context": "American men, American food (Burgers, BBQ, Pizza), American places (New York, Los Angeles, Miami)"},
    "spanish": {"name": "🇪🇸 Español", "code": "es", "context": "Spanish men, Spanish food (Paella, Tapas, Jamón), Spanish places (Madrid, Barcelona, Seville)"}
}

# Constantes
MAX_VARIATIONS = 50
THRESHOLD_FOTOS = 40
THRESHOLD_REELS = 3

# Estados
waiting_for_file = {}
waiting_for_photo_upload = {}
waiting_for_reel_upload = {}
pending_uploads = {}
waiting_for_reels_iguser = {}
waiting_for_reset_confirmation = {}  # {user_id: {"type": "photos" or "reels", "target": xxx}}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================
# STRUTTURE DATI
# ======================

user_threads_state = {}
user_config = {}
user_photo_config = {}
fotos_global_state = {}
reels_global_state = {}

# ======================
# FUNZIONI CONFIGURAZIONE
# ======================

def caricare_config_utenti() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(USER_CONFIG_FILE): return {}
    with open(USER_CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def salvare_config_utenti(config: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(USER_CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config, f, ensure_ascii=False, indent=2)

def get_user_config(user_id: int) -> Dict:
    global user_config
    user_id_str = str(user_id)
    if user_id_str not in user_config:
        user_config[user_id_str] = {"threads_model": "mila", "threads_language": "italian"}
        salvare_config_utenti(user_config)
    return user_config[user_id_str]

def set_user_config(user_id: int, threads_model: str = None, threads_language: str = None):
    global user_config
    user_id_str = str(user_id)
    if user_id_str not in user_config:
        user_config[user_id_str] = {"threads_model": "mila", "threads_language": "italian"}
    if threads_model: user_config[user_id_str]["threads_model"] = threads_model
    if threads_language: user_config[user_id_str]["threads_language"] = threads_language
    salvare_config_utenti(user_config)

def caricare_config_foto_utenti() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(USER_PHOTO_CONFIG_FILE): return {}
    with open(USER_PHOTO_CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def salvare_config_foto_utenti(config: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(USER_PHOTO_CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config, f, ensure_ascii=False, indent=2)

def get_user_photo_config(user_id: int) -> Dict:
    global user_photo_config
    user_id_str = str(user_id)
    if user_id_str not in user_photo_config:
        user_photo_config[user_id_str] = {"photo_model": None, "waiting_for_number": False}
        salvare_config_foto_utenti(user_photo_config)
    return user_photo_config[user_id_str]

def set_user_photo_model(user_id: int, photo_model: str):
    global user_photo_config
    user_id_str = str(user_id)
    if user_id_str not in user_photo_config:
        user_photo_config[user_id_str] = {"photo_model": None, "waiting_for_number": False}
    user_photo_config[user_id_str]["photo_model"] = photo_model
    user_photo_config[user_id_str]["waiting_for_number"] = True
    salvare_config_foto_utenti(user_photo_config)

def set_photo_waiting_for_number(user_id: int, waiting: bool):
    global user_photo_config
    user_id_str = str(user_id)
    if user_id_str not in user_photo_config:
        user_photo_config[user_id_str] = {"photo_model": None, "waiting_for_number": False}
    user_photo_config[user_id_str]["waiting_for_number"] = waiting
    if not waiting: user_photo_config[user_id_str]["photo_model"] = None
    salvare_config_foto_utenti(user_photo_config)

def is_photo_waiting_for_number(user_id: int) -> bool:
    user_id_str = str(user_id)
    if user_id_str in user_photo_config: return user_photo_config[user_id_str].get("waiting_for_number", False)
    return False

def get_photo_model_for_user(user_id: int) -> str:
    user_id_str = str(user_id)
    if user_id_str in user_photo_config: return user_photo_config[user_id_str].get("photo_model")
    return None

# ======================
# FUNZIONI THREADS
# ======================

def caricare_frasi_per_modello(model: str) -> List[Dict]:
    file_path = os.path.join(DATA_FOLDER, f"frases_{model}.json")
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(file_path): return []
    with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)

def salvare_frasi_per_modello(model: str, frasi: List[Dict]):
    file_path = os.path.join(DATA_FOLDER, f"frases_{model}.json")
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f: json.dump(frasi, f, ensure_ascii=False, indent=2)

def caricare_stato_utenti_threads() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(USER_STATE_FILE): return {}
    with open(USER_STATE_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def salvare_stato_utenti_threads(stato: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(USER_STATE_FILE, 'w', encoding='utf-8') as f: json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_utente_threads(user_id: int):
    stato = caricare_stato_utenti_threads()
    user_id_str = str(user_id)
    if user_id_str not in stato:
        stato[user_id_str] = {"sent_numbers": [], "total_sent": 0}
        salvare_stato_utenti_threads(stato)
    if user_id not in user_threads_state:
        user_threads_state[user_id] = {"sent_numbers": set(stato[user_id_str]["sent_numbers"]), "total_sent": stato[user_id_str]["total_sent"]}

def salvare_stato_utente_threads(user_id: int):
    if user_id in user_threads_state:
        stato = caricare_stato_utenti_threads()
        user_id_str = str(user_id)
        stato[user_id_str] = {"sent_numbers": list(user_threads_state[user_id]["sent_numbers"]), "total_sent": user_threads_state[user_id]["total_sent"]}
        salvare_stato_utenti_threads(stato)

def ottenere_numeri_disponibili_threads(user_id: int, quantita: int) -> List[int]:
    inizializzare_stato_utente_threads(user_id)
    inviati = user_threads_state[user_id]["sent_numbers"]
    disponibili = [n for n in range(1, MAX_VARIATIONS + 1) if n not in inviati]
    if not disponibili:
        user_threads_state[user_id] = {"sent_numbers": set(), "total_sent": 0}
        salvare_stato_utente_threads(user_id)
        disponibili = list(range(1, MAX_VARIATIONS + 1))
    random.shuffle(disponibili)
    return disponibili[:quantita]

def marcare_come_inviate_threads(user_id: int, numeri: List[int]):
    inizializzare_stato_utente_threads(user_id)
    for num in numeri:
        user_threads_state[user_id]["sent_numbers"].add(num)
        user_threads_state[user_id]["total_sent"] += 1
    salvare_stato_utente_threads(user_id)

async def generare_variazione(model: str, language: str, frase_originale: str, frase_numero: int, variazione_num: int) -> str:
    model_info = THREADS_MODELS[model]
    lang_info = LANGUAGES[language]
    
    # Detectar si la frase original menciona nombre u origen
    menciona_nombre = model_info['full_name'].lower() in frase_originale.lower()
    menciona_origen = model_info['origin'].lower() in frase_originale.lower() or model_info['origin_text'].lower() in frase_originale.lower()
    
    reglas_adicionales = ""
    if menciona_nombre and menciona_origen:
        reglas_adicionales = f"""
6. The girl's name is {model_info['full_name']}. Use it ONLY when the original phrase mentions a name.
7. Her origin is {model_info['origin']}. Use it ONLY when the original phrase mentions origin."""
    elif menciona_nombre:
        reglas_adicionales = f"""
6. The girl's name is {model_info['full_name']}. Use it ONLY when the original phrase mentions a name."""
    elif menciona_origen:
        reglas_adicionales = f"""
6. Her origin is {model_info['origin']}. Use it ONLY when the original phrase mentions origin."""
    
    system_prompt = f"""You are a copywriter. Create ONE variation of the given phrase in {lang_info['name']}.

CRITICAL RULES:
1. Maintain EXACTLY the same structure and meaning as the original phrase.
2. Keep censorship exactly as in the original (use * or emojis).
3. Change words, change the way of expressing things, but NOT the meaning.
4. This is variation number {variazione_num}.
5. PRESERVE the exact same format: if the original has line breaks, emojis, numbers, or lists, keep them.
{reglas_adicionales}
8. Keep teen tone (18 years old), FIRST PERSON.
9. Adapt cultural references to: {lang_info['context']} (if the original mentions men, food, places, etc.)
10. DO NOT add any extra information that wasn't in the original phrase.
11. Reply ONLY with the variation text in {lang_info['name']}, nothing else.

Original phrase (number {frase_numero}):
{frase_originale}

Generate variation number {variazione_num} in {lang_info['name']}, keeping the exact same format (line breaks, lists, etc.):"""
    
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Generate variation {variazione_num} keeping the same format:"}]
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
# FUNZIONI FOTOS (USA E GETTA)
# ======================

def init_fotos_db():
    os.makedirs(PHOTOS_FOLDER, exist_ok=True)

def caricare_stato_fotos() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(PHOTOS_DB_FILE): return {}
    with open(PHOTOS_DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def salvare_stato_fotos(stato: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(PHOTOS_DB_FILE, 'w', encoding='utf-8') as f: json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_fotos():
    global fotos_global_state
    fotos_global_state = caricare_stato_fotos()

def salvare_stato_fotos_globale():
    salvare_stato_fotos(fotos_global_state)

def aggiungere_foto_per_modello(photo_model: str, foto_path: str):
    global fotos_global_state
    if photo_model not in fotos_global_state:
        fotos_global_state[photo_model] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    nuovo_id = fotos_global_state[photo_model]["total"] + 1
    ext = os.path.splitext(foto_path)[1]
    nuovo_nome = f"{photo_model}_foto_{nuovo_id}{ext}"
    nuovo_path = os.path.join(PHOTOS_FOLDER, nuovo_nome)
    shutil.copy2(foto_path, nuovo_path)
    fotos_global_state[photo_model]["metadata"][nuovo_id] = {"path": nuovo_path, "original_name": os.path.basename(foto_path), "used": False}
    fotos_global_state[photo_model]["total"] += 1
    fotos_global_state[photo_model]["disponibili"].append(nuovo_id)
    salvare_stato_fotos_globale()

def ottenere_foto_disponibili_per_modello(photo_model: str, quantita: int) -> List[int]:
    if photo_model not in fotos_global_state: return []
    disponibili = [fid for fid, meta in fotos_global_state[photo_model]["metadata"].items() if not meta.get("used", False)]
    random.shuffle(disponibili)
    return disponibili[:quantita]

def marcare_foto_come_usate_per_modello(photo_model: str, foto_ids: List[int]):
    if photo_model not in fotos_global_state: return
    for fid in foto_ids:
        if fid in fotos_global_state[photo_model]["metadata"]:
            fotos_global_state[photo_model]["metadata"][fid]["used"] = True
            if fid in fotos_global_state[photo_model]["disponibili"]: fotos_global_state[photo_model]["disponibili"].remove(fid)
            fotos_global_state[photo_model]["usate"].append(fid)
    salvare_stato_fotos_globale()

def get_stato_fotos_per_modello(photo_model: str) -> tuple:
    if photo_model not in fotos_global_state: return 0, 0, 0
    usate = len(fotos_global_state[photo_model]["usate"])
    disponibili = len([f for f in fotos_global_state[photo_model]["metadata"].values() if not f.get("used", False)])
    total = fotos_global_state[photo_model]["total"]
    return usate, disponibili, total

def reset_fotos_per_modello(photo_model: str):
    global fotos_global_state
    if photo_model in fotos_global_state:
        for fid, meta in fotos_global_state[photo_model].get("metadata", {}).items():
            path = meta.get("path")
            if path and os.path.exists(path):
                try: os.unlink(path)
                except: pass
    fotos_global_state[photo_model] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    salvare_stato_fotos_globale()

# ======================
# FUNZIONI REELS (USA E GETTA PER IGUSER)
# ======================

def init_reels_db():
    os.makedirs(REELS_FOLDER, exist_ok=True)

def caricare_stato_reels() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(REELS_DB_FILE): return {}
    with open(REELS_DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def salvare_stato_reels(stato: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(REELS_DB_FILE, 'w', encoding='utf-8') as f: json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_reels():
    global reels_global_state
    reels_global_state = caricare_stato_reels()

def salvare_stato_reels_globale():
    salvare_stato_reels(reels_global_state)

def aggiungere_reel_per_iguser(iguser: str, reel_path: str):
    global reels_global_state
    if iguser not in reels_global_state:
        reels_global_state[iguser] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    nuovo_id = reels_global_state[iguser]["total"] + 1
    ext = os.path.splitext(reel_path)[1]
    nuovo_nome = f"{iguser}_reel_{nuovo_id}{ext}"
    nuovo_path = os.path.join(REELS_FOLDER, nuovo_nome)
    shutil.copy2(reel_path, nuovo_path)
    reels_global_state[iguser]["metadata"][nuovo_id] = {"path": nuovo_path, "original_name": os.path.basename(reel_path), "used": False}
    reels_global_state[iguser]["total"] += 1
    reels_global_state[iguser]["disponibili"].append(nuovo_id)
    salvare_stato_reels_globale()

def ottenere_reel_disponibile_per_iguser(iguser: str) -> Optional[int]:
    if iguser not in reels_global_state: return None
    disponibili = [fid for fid, meta in reels_global_state[iguser]["metadata"].items() if not meta.get("used", False)]
    if not disponibili: return None
    random.shuffle(disponibili)
    return disponibili[0]

def marcare_reel_come_usato_per_iguser(iguser: str, reel_id: int):
    if iguser not in reels_global_state: return
    if reel_id in reels_global_state[iguser]["metadata"]:
        reels_global_state[iguser]["metadata"][reel_id]["used"] = True
        if reel_id in reels_global_state[iguser]["disponibili"]: reels_global_state[iguser]["disponibili"].remove(reel_id)
        reels_global_state[iguser]["usate"].append(reel_id)
    salvare_stato_reels_globale()

def get_stato_reels_per_iguser(iguser: str) -> tuple:
    if iguser not in reels_global_state: return 0, 0, 0
    usate = len(reels_global_state[iguser]["usate"])
    disponibili = len([f for f in reels_global_state[iguser]["metadata"].values() if not f.get("used", False)])
    total = reels_global_state[iguser]["total"]
    return usate, disponibili, total

def reset_reels_per_iguser(iguser: str):
    global reels_global_state
    if iguser in reels_global_state:
        for fid, meta in reels_global_state[iguser].get("metadata", {}).items():
            path = meta.get("path")
            if path and os.path.exists(path):
                try: os.unlink(path)
                except: pass
    reels_global_state[iguser] = {"total": 0, "disponibili": [], "usate": [], "metadata": {}}
    salvare_stato_reels_globale()

def get_all_igusers_with_reels() -> List[str]:
    """Retorna lista de todos los igusers que tienen reels"""
    return list(reels_global_state.keys())

# ======================
# NOTIFICHE ADMIN
# ======================

async def notificare_admin(context: ContextTypes.DEFAULT_TYPE, messaggio: str, is_admin_action: bool = False):
    try:
        if is_admin_action:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"👑 <b>ADMIN:</b>\n{messaggio}", parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=messaggio, parse_mode="HTML")
    except Exception as e: logger.error(f"Error sending admin notification: {e}")

# ======================
# FUNCIONES DE RESET CON CONFIRMACIÓN
# ======================

async def reset_photos_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los modelos de fotos para resetear"""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    # Agrupar por categoría
    asian_models = []
    italian_models = []
    
    for key, model in PHOTO_MODELS.items():
        if model["category"] == "asian":
            asian_models.append([InlineKeyboardButton(f"🇦🇸 {model['name']}", callback_data=f"reset_photo_{key}")])
        else:
            italian_models.append([InlineKeyboardButton(f"🇮🇹 {model['name']}", callback_data=f"reset_photo_{key}")])
    
    keyboard.extend(asian_models)
    keyboard.extend(italian_models)
    keyboard.append([InlineKeyboardButton("◀️ Back to Admin Menu", callback_data="admin_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🔄 <b>RESET PHOTOS</b>\n\n"
        "Select which model's photos you want to reset.\n"
        "⚠️ This will delete ALL photos for that model!",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def reset_reels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los igusers con reels para resetear"""
    query = update.callback_query
    await query.answer()
    
    igusers = get_all_igusers_with_reels()
    
    if not igusers:
        await query.edit_message_text(
            "❌ No reels found in the database.\n\n"
            "Use /admin → Reels to upload reels first.",
            parse_mode="HTML"
        )
        return
    
    keyboard = []
    for iguser in igusers:
        used, available, total = get_stato_reels_per_iguser(iguser)
        status_icon = "🟢" if available > 0 else "🔴"
        keyboard.append([InlineKeyboardButton(f"{status_icon} @{iguser} ({available}/{total})", callback_data=f"reset_reel_{iguser}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Back to Admin Menu", callback_data="admin_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🔄 <b>RESET REELS</b>\n\n"
        "Select which Instagram user's reels you want to reset.\n"
        "⚠️ This will delete ALL reels for that user!",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE, reset_type: str, target: str):
    """Pide confirmación antes de resetear"""
    query = update.callback_query
    await query.answer()
    
    if reset_type == "photo":
        model_name = PHOTO_MODELS.get(target, {}).get("name", target)
        message = f"⚠️ <b>CONFIRM RESET</b>\n\n"
        message += f"You are about to reset ALL photos for:\n"
        message += f"📸 <b>{model_name}</b>\n\n"
        message += f"This action is <b>IRREVERSIBLE</b> and will delete all photos for this model.\n\n"
        message += f"Are you sure?"
        
        keyboard = [
            [InlineKeyboardButton("✅ YES, RESET", callback_data=f"confirm_reset_photo_{target}")],
            [InlineKeyboardButton("❌ NO, CANCEL", callback_data="admin_reset")]
        ]
    else:
        message = f"⚠️ <b>CONFIRM RESET</b>\n\n"
        message += f"You are about to reset ALL reels for:\n"
        message += f"🎬 <b>@{target}</b>\n\n"
        message += f"This action is <b>IRREVERSIBLE</b> and will delete all reels for this user.\n\n"
        message += f"Are you sure?"
        
        keyboard = [
            [InlineKeyboardButton("✅ YES, RESET", callback_data=f"confirm_reset_reel_{target}")],
            [InlineKeyboardButton("❌ NO, CANCEL", callback_data="admin_reset")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")

async def execute_reset(update: Update, context: ContextTypes.DEFAULT_TYPE, reset_type: str, target: str):
    """Ejecuta el reset después de la confirmación"""
    query = update.callback_query
    await query.answer()
    
    if reset_type == "photo":
        reset_fotos_per_modello(target)
        model_name = PHOTO_MODELS.get(target, {}).get("name", target)
        message = f"✅ <b>Photos reset successfully!</b>\n\n"
        message += f"📸 Model: {model_name}\n"
        message += f"All photos for this model have been deleted."
    else:
        reset_reels_per_iguser(target)
        message = f"✅ <b>Reels reset successfully!</b>\n\n"
        message += f"🎬 User: @{target}\n"
        message += f"All reels for this user have been deleted."
    
    keyboard = [[InlineKeyboardButton("◀️ Back to Admin Menu", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")
    
    await notificare_admin(context, f"🔄 Reset completed: {reset_type} - {target}", is_admin_action=True)

# ======================
# MENU ADMIN (principal)
# ======================

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    keyboard = [
        [InlineKeyboardButton("📝 Upload Threads", callback_data="admin_threads")],
        [InlineKeyboardButton("📸 Upload Photos", callback_data="admin_photos")],
        [InlineKeyboardButton("🎬 Upload Reels", callback_data="admin_reels")],
        [InlineKeyboardButton("🔄 Reset Photos", callback_data="admin_reset_photos")],
        [InlineKeyboardButton("🔄 Reset Reels", callback_data="admin_reset_reels")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👑 <b>Admin Menu</b>\n\nSelect an option:", reply_markup=reply_markup, parse_mode="HTML")

async def admin_threads_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(THREADS_MODELS["mila"]["name"], callback_data="admin_threads_mila")],
        [InlineKeyboardButton(THREADS_MODELS["yuna"]["name"], callback_data="admin_threads_yuna")],
        [InlineKeyboardButton(THREADS_MODELS["ita"]["name"], callback_data="admin_threads_ita")],
        [InlineKeyboardButton("◀️ Back", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📝 <b>Select model to upload THREADS:</b>", reply_markup=reply_markup, parse_mode="HTML")

async def admin_photos_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🇦🇸 Asian Models", callback_data="admin_photos_asian")],
        [InlineKeyboardButton("🇮🇹 Italian Models", callback_data="admin_photos_italian")],
        [InlineKeyboardButton("◀️ Back", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📸 <b>Select category for PHOTOS:</b>", reply_markup=reply_markup, parse_mode="HTML")

async def admin_photos_models(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, model in PHOTO_MODELS.items():
        if model["category"] == category:
            keyboard.append([InlineKeyboardButton(model["name"], callback_data=f"admin_photos_model_{key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_photos")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    category_name = "Asian" if category == "asian" else "Italian"
    await query.edit_message_text(f"📸 <b>Select model ({category_name}) to upload PHOTOS:</b>", reply_markup=reply_markup, parse_mode="HTML")

async def admin_reels_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎬 <b>Upload REELS</b>\n\n"
        "Please type the Instagram username for these reels.\n"
        "Example: <code>bellamoreno</code>\n\n"
        "Then send the video files (one or more at a time).\n"
        "When done, use <code>/done</code>",
        parse_mode="HTML"
    )
    waiting_for_reels_iguser[ADMIN_USER_ID] = True

async def admin_handle_reels_iguser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID: return
    if not waiting_for_reels_iguser.get(user_id): return
    iguser = update.message.text.strip().lower()
    if not iguser:
        await update.message.reply_text("❌ Please type a valid username.")
        return
    del waiting_for_reels_iguser[user_id]
    waiting_for_reel_upload[user_id] = iguser
    if user_id not in pending_uploads:
        pending_uploads[user_id] = {"type": "reels", "target": iguser, "files": []}
    await update.message.reply_text(
        f"🎬 **Uploading reels for @{iguser}**\n\n"
        "Send videos (one or more at a time).\n"
        "When done, type <code>/done</code>\n\n"
        f"⏳ Files received so far: 0",
        parse_mode="HTML"
    )

# ======================
# MENU USUARIO
# ======================

async def user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 Threads", callback_data="user_threads")],
        [InlineKeyboardButton("📸 Photos", callback_data="user_photos")],
        [InlineKeyboardButton("🎬 Reels", callback_data="user_reels")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📱 <b>Main Menu</b>\n\nWhat would you like to get?", reply_markup=reply_markup, parse_mode="HTML")

async def user_threads_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, model in THREADS_MODELS.items():
        keyboard.append([InlineKeyboardButton(model["name"], callback_data=f"user_threads_model_{key}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🌸 <b>Choose your model for THREADS:</b>", reply_markup=reply_markup, parse_mode="HTML")

async def user_threads_language(update: Update, context: ContextTypes.DEFAULT_TYPE, model: str):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for lang_key, lang_info in LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(lang_info["name"], callback_data=f"user_threads_lang_{model}_{lang_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_threads")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"🌸 <b>Model: {THREADS_MODELS[model]['name']}</b>\n\n🌍 <b>Choose language:</b>", reply_markup=reply_markup, parse_mode="HTML")

async def user_photos_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🇦🇸 Asian Models", callback_data="user_photos_asian")],
        [InlineKeyboardButton("🇮🇹 Italian Models", callback_data="user_photos_italian")],
        [InlineKeyboardButton("◀️ Back", callback_data="user_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📸 <b>Select category for PHOTOS:</b>", reply_markup=reply_markup, parse_mode="HTML")

async def user_photos_models(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, model in PHOTO_MODELS.items():
        if model["category"] == category:
            keyboard.append([InlineKeyboardButton(model["name"], callback_data=f"user_photos_model_{key}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="user_photos")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    category_name = "Asian" if category == "asian" else "Italian"
    await query.edit_message_text(f"📸 <b>Select model ({category_name}) for PHOTOS:</b>", reply_markup=reply_markup, parse_mode="HTML")

async def user_reels_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎬 <b>Get a REEL</b>\n\n"
        "Please type the Instagram username you want reels from.\n"
        "Example: <code>bellamoreno</code>\n\n"
        "⚠️ You will receive <b>ONE reel</b> (one-time use, never repeated).",
        parse_mode="HTML"
    )
    context.user_data["waiting_for_reel_iguser"] = True

async def user_handle_reel_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    if not context.user_data.get("waiting_for_reel_iguser"):
        return
    iguser = update.message.text.strip().lower()
    context.user_data["waiting_for_reel_iguser"] = False
    if not iguser:
        await update.message.reply_text("❌ Please type a valid username.")
        return
    if iguser not in reels_global_state or reels_global_state[iguser]["total"] == 0:
        await update.message.reply_text(f"❌ No reels available for @{iguser}.")
        return
    used, available, total = get_stato_reels_per_iguser(iguser)
    if available <= THRESHOLD_REELS and available > 0:
        await notificare_admin(context, f"⚠️ <b>LOW REELS WARNING - @{iguser}!</b>\n📸 Reels available: {available}", is_admin_action=True)
    if available == 0:
        await update.message.reply_text(f"❌ No reels available for @{iguser}. All reels have been used!")
        return
    reel_id = ottenere_reel_disponibile_per_iguser(iguser)
    if not reel_id:
        await update.message.reply_text(f"❌ No reels available for @{iguser}. Please try again later.")
        return
    metadata = reels_global_state[iguser]["metadata"].get(reel_id, {})
    reel_path = metadata.get("path")
    if reel_path and os.path.exists(reel_path):
        try:
            with open(reel_path, 'rb') as f:
                await update.message.reply_video(video=f, caption=f"🎬 Reel from @{iguser}")
            marcare_reel_come_usato_per_iguser(iguser, reel_id)
            await notificare_admin(context, f"🎬 @{username} received a reel from @{iguser}")
            _, remaining, _ = get_stato_reels_per_iguser(iguser)
            await update.message.reply_text(f"✅ <b>Reel sent!</b>\n\n📨 Sent: 1 reel from @{iguser}", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending reel for {iguser}: {e}")
            await update.message.reply_text("❌ Error sending the reel. Please try again.")
    else:
        await update.message.reply_text("❌ Reel file not found. Please try again.")

# ======================
# MANEJADOR PRINCIPAL DE CALLBACKS
# ======================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # ADMIN CALLBACKS
    if data == "admin_back":
        await admin_menu(update, context)
    
    elif data == "admin_threads":
        await admin_threads_menu(update, context)
    
    elif data.startswith("admin_threads_"):
        model = data.replace("admin_threads_", "")
        waiting_for_file[user_id] = model
        await query.edit_message_text(
            f"📁 **Ready to receive file for {THREADS_MODELS[model]['name']}**\n\n"
            "Send a .txt file with numbered phrases.\n"
            "📌 Format: <code>43. Your phrase here...</code>\n\n"
            "⏳ Waiting for file...",
            parse_mode="HTML"
        )
    
    elif data == "admin_photos":
        await admin_photos_category(update, context)
    
    elif data == "admin_photos_asian":
        await admin_photos_models(update, context, "asian")
    
    elif data == "admin_photos_italian":
        await admin_photos_models(update, context, "italian")
    
    elif data.startswith("admin_photos_model_"):
        photo_model = data.replace("admin_photos_model_", "")
        waiting_for_photo_upload[user_id] = photo_model
        if user_id not in pending_uploads:
            pending_uploads[user_id] = {"type": "photos", "target": photo_model, "files": []}
        await query.edit_message_text(
            f"📸 **Uploading photos for {PHOTO_MODELS[photo_model]['name']}**\n\n"
            "Send photos (one or more at a time).\n"
            "When done, type <code>/done</code>\n\n"
            f"⏳ Photos received: 0",
            parse_mode="HTML"
        )
    
    elif data == "admin_reels":
        await admin_reels_prompt(update, context)
    
    # ADMIN RESET CALLBACKS
    elif data == "admin_reset_photos":
        await reset_photos_menu(update, context)
    
    elif data == "admin_reset_reels":
        await reset_reels_menu(update, context)
    
    elif data == "admin_reset":
        await admin_menu(update, context)
    
    elif data.startswith("reset_photo_"):
        photo_model = data.replace("reset_photo_", "")
        await confirm_reset(update, context, "photo", photo_model)
    
    elif data.startswith("reset_reel_"):
        iguser = data.replace("reset_reel_", "")
        await confirm_reset(update, context, "reel", iguser)
    
    elif data.startswith("confirm_reset_photo_"):
        photo_model = data.replace("confirm_reset_photo_", "")
        await execute_reset(update, context, "photo", photo_model)
    
    elif data.startswith("confirm_reset_reel_"):
        iguser = data.replace("confirm_reset_reel_", "")
        await execute_reset(update, context, "reel", iguser)
    
    # USER CALLBACKS
    elif data == "user_back":
        await user_menu(update, context)
    
    elif data == "user_threads":
        await user_threads_menu(update, context)
    
    elif data.startswith("user_threads_model_"):
        model = data.replace("user_threads_model_", "")
        await user_threads_language(update, context, model)
    
    elif data.startswith("user_threads_lang_"):
        parts = data.split("_")
        model = parts[3]
        language = parts[4]
        set_user_config(user_id, threads_model=model, threads_language=language)
        await query.edit_message_text(
            f"✅ <b>Threads configured!</b>\n\n"
            f"🌸 Model: {THREADS_MODELS[model]['name']}\n"
            f"🌍 Language: {LANGUAGES[language]['name']}\n\n"
            f"📝 Now type the number of threads you want!\n"
            f"Example: <code>5</code>",
            parse_mode="HTML"
        )
    
    elif data == "user_photos":
        await user_photos_category(update, context)
    
    elif data == "user_photos_asian":
        await user_photos_models(update, context, "asian")
    
    elif data == "user_photos_italian":
        await user_photos_models(update, context, "italian")
    
    elif data.startswith("user_photos_model_"):
        photo_model = data.replace("user_photos_model_", "")
        set_user_photo_model(user_id, photo_model)
        await query.edit_message_text(
            f"✅ <b>Photos configured!</b>\n\n"
            f"📸 Model: {PHOTO_MODELS[photo_model]['name']}\n\n"
            f"📝 Now type the number of photos you want!\n"
            f"Example: <code>3</code>\n\n"
            f"⚠️ Photos are ONE-TIME USE!",
            parse_mode="HTML"
        )
    
    elif data == "user_reels":
        await user_reels_prompt(update, context)

# ======================
# HANDLERS DE ARCHIVOS (Admin)
# ======================

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id not in waiting_for_file: return
    model_name = waiting_for_file[user_id]
    if not update.message.document: return
    if not update.message.document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ File must be .txt")
        return
    status_msg = await update.message.reply_text(f"📥 Processing file...")
    try:
        file = await context.bot.get_file(update.message.document.file_id)
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', encoding='utf-8', delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            with open(tmp.name, 'r', encoding='utf-8') as f:
                content = f.read()
        os.unlink(tmp.name)
        
        # Parsear frases numeradas respetando listas internas
        frases = []
        lines = content.strip().split('\n')
        current_number = None
        current_text = []
        
        i = 0
        while i < len(lines):
            line = lines[i].rstrip('\n\r')
            
            # Buscar patrón de número al inicio: "43. Texto..."
            # Solo considerar como NUEVA frase si el número está al inicio de línea
            # y NO es parte de una lista (ej: "1.", "2." dentro de una frase)
            match_principal = re.match(r'^(\d{1,2})\.\s+(.*)', line)
            
            # Si encontramos un número al inicio de línea, es UNA NUEVA FRASE
            if match_principal:
                # Guardar la frase anterior si existe
                if current_number is not None and current_text:
                    texto_completo = "\n".join(current_text).strip()
                    frases.append({
                        "numero": current_number,
                        "testo": texto_completo
                    })
                
                # Iniciar nueva frase con este número
                current_number = int(match_principal.group(1))
                current_text = [match_principal.group(2)]
            else:
                # Es continuación de la frase actual (puede tener listas internas con números)
                if current_text is not None:
                    current_text.append(line)
            
            i += 1
        
        # Guardar la última frase
        if current_number is not None and current_text:
            texto_completo = "\n".join(current_text).strip()
            frases.append({
                "numero": current_number,
                "testo": texto_completo
            })
        
        if not frases:
            await status_msg.edit_text("❌ No numbered phrases found.")
            return
        
        salvare_frasi_per_modello(model_name, frases)
        del waiting_for_file[user_id]
        
        # Mostrar preview
        preview_lines = []
        for f in frases[:5]:
            preview_text = f['testo'][:80] + "..." if len(f['testo']) > 80 else f['testo']
            # Mostrar primeras líneas del preview
            preview_lines.append(f"📌 <b>{f['numero']}:</b> {preview_text}")
        
        preview = "\n".join(preview_lines)
        await status_msg.edit_text(
            f"✅ <b>Loaded for {THREADS_MODELS[model_name]['name']}</b>\n\n"
            f"📊 Total phrases: {len(frases)}\n\n"
            f"{preview}\n\n"
            f"✅ Format preserved (multiline phrases with internal lists are kept intact!)",
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def receive_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id not in pending_uploads: return
    upload_type = pending_uploads[user_id]["type"]
    target = pending_uploads[user_id]["target"]
    added = 0
    if update.message.video:
        file = await context.bot.get_file(update.message.video.file_id)
        ext = ".mp4"
        temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}{ext}"
        await file.download_to_drive(temp_path)
        pending_uploads[user_id]["files"].append(temp_path)
        added += 1
    elif update.message.video_note:
        file = await context.bot.get_file(update.message.video_note.file_id)
        temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}.mp4"
        await file.download_to_drive(temp_path)
        pending_uploads[user_id]["files"].append(temp_path)
        added += 1
    elif update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}.jpg"
        await file.download_to_drive(temp_path)
        pending_uploads[user_id]["files"].append(temp_path)
        added += 1
    elif update.message.document:
        doc = update.message.document
        if doc.mime_type and (doc.mime_type.startswith('image/') or doc.mime_type.startswith('video/')):
            file = await context.bot.get_file(doc.file_id)
            ext = os.path.splitext(doc.file_name)[1]
            temp_path = f"temp_{int(time.time())}_{random.randint(1000,9999)}{ext}"
            await file.download_to_drive(temp_path)
            pending_uploads[user_id]["files"].append(temp_path)
            added += 1
    if added > 0:
        total = len(pending_uploads[user_id]["files"])
        if total % 10 == 0:
            type_name = "photos" if upload_type == "photos" else "reels"
            await update.message.reply_text(f"📦 Loaded {total} {type_name} for {target}...")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only admin can use /done")
        return
    if user_id not in pending_uploads or not pending_uploads[user_id]["files"]:
        await update.message.reply_text("❌ No files to process.")
        return
    upload_type = pending_uploads[user_id]["type"]
    target = pending_uploads[user_id]["target"]
    files = pending_uploads[user_id]["files"]
    total_files = len(files)
    status_msg = await update.message.reply_text(f"📥 Processing {total_files} files...")
    for path in files:
        if upload_type == "photos":
            aggiungere_foto_per_modello(target, path)
        else:
            aggiungere_reel_per_iguser(target, path)
    for path in files:
        if os.path.exists(path):
            try: os.unlink(path)
            except: pass
    del pending_uploads[user_id]
    if upload_type == "photos":
        used, available, total = get_stato_fotos_per_modello(target)
        await status_msg.edit_text(f"✅ <b>Photos for {PHOTO_MODELS[target]['name']} loaded!</b>\n\n📸 Added: {total_files}\n📊 Total: {total}\n⏳ Available: {available}", parse_mode="HTML")
    else:
        used, available, total = get_stato_reels_per_iguser(target)
        await status_msg.edit_text(f"✅ <b>Reels for @{target} loaded!</b>\n\n🎬 Added: {total_files}\n📊 Total: {total}\n⏳ Available: {available}", parse_mode="HTML")

# ======================
# HANDLER NUMEROS (para threads y fotos)
# ======================

async def handle_number_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()
    if not text.isdigit(): return
    quantity = int(text)
    if quantity < 1 or quantity > MAX_VARIATIONS:
        await update.message.reply_text(f"❌ Number between 1 and {MAX_VARIATIONS}")
        return
    if is_photo_waiting_for_number(user_id):
        photo_model = get_photo_model_for_user(user_id)
        if photo_model:
            await send_photos_to_user(update, context, user_id, photo_model, quantity)
            set_photo_waiting_for_number(user_id, False)
            return
    await generate_threads_for_user(update, context, user_id, quantity)

async def generate_threads_for_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, quantity: int):
    user = update.effective_user
    username = user.username or user.first_name
    config = get_user_config(user_id)
    model = config["threads_model"]
    language = config["threads_language"]
    frases = caricare_frasi_per_modello(model)
    if not frases:
        await update.message.reply_text(f"❌ No phrases for {THREADS_MODELS[model]['name']}.")
        return
    numbers = ottenere_numeri_disponibili_threads(user_id, quantity)
    await notificare_admin(context, f"🔄 @{username} requested {len(numbers)} threads | {THREADS_MODELS[model]['name']} | {LANGUAGES[language]['name']}")
    await update.message.reply_text(f"🎲 Generating {len(numbers)} threads...", parse_mode="HTML")
    sent = []
    mixed = frases.copy()
    random.shuffle(mixed)
    for i, num in enumerate(numbers):
        phrase = mixed[i % len(mixed)]
        variation = await generare_variazione(model, language, phrase["testo"], phrase["numero"], num)
        if variation and not variation.startswith("❌"):
            await update.message.reply_text(variation, parse_mode="HTML")
            sent.append(num)
            await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(f"❌ Error generating variation {num}")
    marcare_come_inviate_threads(user_id, sent)
    total_received = user_threads_state[user_id]["total_sent"]
    await update.message.reply_text(f"✅ <b>Threads sent!</b>\n\n📨 Sent: {len(sent)}\n📊 Total received: {total_received}", parse_mode="HTML")

async def send_photos_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, photo_model: str, quantity: int):
    user = update.effective_user
    username = user.username or user.first_name
    used, available, total = get_stato_fotos_per_modello(photo_model)
    if available <= THRESHOLD_FOTOS and available > 0:
        await notificare_admin(context, f"⚠️ <b>LOW PHOTOS - {PHOTO_MODELS[photo_model]['name']}!</b>\n📸 Available: {available}", is_admin_action=True)
    if total == 0 or available == 0:
        await update.message.reply_text(f"❌ No photos for {PHOTO_MODELS[photo_model]['name']}.")
        return
    if available < quantity:
        await update.message.reply_text(f"⚠️ Only {available} photos available.\nSending {available} instead.")
        quantity = available
    photo_ids = ottenere_foto_disponibili_per_modello(photo_model, quantity)
    await update.message.reply_text(f"📸 Sending {len(photo_ids)} photos...")
    sent = []
    for i, fid in enumerate(photo_ids, 1):
        path = fotos_global_state[photo_model]["metadata"][fid]["path"]
        if path and os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    await update.message.reply_photo(photo=f, caption=f"📸 Photo {i}/{len(photo_ids)}")
                sent.append(fid)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Error sending photo: {e}")
    if sent:
        marcare_foto_come_usate_per_modello(photo_model, sent)
    await update.message.reply_text(f"✅ <b>Photos sent!</b>\n\n📨 Sent: {len(sent)}", parse_mode="HTML")

# ======================
# COMANDOS ADMIN - ESTADOS DE USUARIOS
# ======================

async def all_users_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    stato_threads = caricare_stato_utenti_threads()
    config_utenti = caricare_config_utenti()
    stato_fotos = caricare_stato_fotos()
    stato_reels = caricare_stato_reels()
    
    all_user_ids = set()
    all_user_ids.update(stato_threads.keys())
    all_user_ids.update(config_utenti.keys())
    
    if not all_user_ids:
        await update.message.reply_text("📊 No users found in the database.")
        return
    
    message = "📊 <b>ALL USERS STATUS</b>\n\n"
    
    for user_id_str in sorted(all_user_ids, key=lambda x: int(x) if x.isdigit() else 0):
        user_id = int(user_id_str)
        
        threads_info = stato_threads.get(user_id_str, {})
        threads_total = threads_info.get("total_sent", 0)
        threads_remaining = MAX_VARIATIONS - (threads_total % MAX_VARIATIONS)
        
        user_config_data = config_utenti.get(user_id_str, {})
        threads_model = user_config_data.get("threads_model", "mila")
        threads_language = user_config_data.get("threads_language", "italian")
        model_name = THREADS_MODELS.get(threads_model, {}).get("name", threads_model)
        language_name = LANGUAGES.get(threads_language, {}).get("name", threads_language)
        
        username = "Unknown"
        try:
            chat = await context.bot.get_chat(user_id)
            username = chat.username or chat.first_name or str(user_id)
        except:
            username = str(user_id)
        
        message += f"👤 <b>@{username}</b> (ID: {user_id})\n"
        message += f"   📝 Threads: {threads_total} received | {threads_remaining} to cycle\n"
        message += f"   🌸 Model: {model_name} | 🌍 Lang: {language_name}\n"
        message += "\n"
        
        if len(message) > 3500:
            await update.message.reply_text(message, parse_mode="HTML")
            message = "📊 <b>ALL USERS STATUS (continued)</b>\n\n"
    
    if message.strip():
        await update.message.reply_text(message, parse_mode="HTML")

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ Usage: <code>/userstats user_id</code>\n\n"
            "Example: <code>/userstats 7097140504</code>\n\n"
            "You can also use <code>/allusers</code> to see all users.",
            parse_mode="HTML"
        )
        return
    
    target_user_id_str = context.args[0]
    if not target_user_id_str.isdigit():
        await update.message.reply_text("❌ User ID must be a number.")
        return
    
    target_user_id = int(target_user_id_str)
    
    stato_threads = caricare_stato_utenti_threads()
    config_utenti = caricare_config_utenti()
    
    user_id_str = str(target_user_id)
    
    threads_info = stato_threads.get(user_id_str, {})
    threads_total = threads_info.get("total_sent", 0)
    threads_numbers = threads_info.get("sent_numbers", [])
    threads_remaining = MAX_VARIATIONS - (threads_total % MAX_VARIATIONS)
    
    user_config_data = config_utenti.get(user_id_str, {})
    threads_model = user_config_data.get("threads_model", "mila")
    threads_language = user_config_data.get("threads_language", "italian")
    model_name = THREADS_MODELS.get(threads_model, {}).get("name", threads_model)
    language_name = LANGUAGES.get(threads_language, {}).get("name", threads_language)
    
    username = "Unknown"
    try:
        chat = await context.bot.get_chat(target_user_id)
        username = chat.username or chat.first_name or str(target_user_id)
    except:
        username = str(target_user_id)
    
    message = f"📊 <b>USER STATUS - @{username}</b>\n\n"
    message += f"🆔 User ID: {target_user_id}\n\n"
    
    message += f"<b>📝 THREADS:</b>\n"
    message += f"   • Model: {model_name}\n"
    message += f"   • Language: {language_name}\n"
    message += f"   • Total received: {threads_total}\n"
    message += f"   • Remaining in cycle: {threads_remaining}\n"
    if threads_numbers:
        message += f"   • Numbers used: {', '.join(map(str, sorted(threads_numbers)[:10]))}"
        if len(threads_numbers) > 10:
            message += f" +{len(threads_numbers)-10} more"
        message += "\n"
    
    await update.message.reply_text(message, parse_mode="HTML")

# ======================
# COMANDOS BASE
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"👤 New user: @{username} (ID: {user_id})")
    config = get_user_config(user_id)
    threads_model_name = THREADS_MODELS[config["threads_model"]]["name"]
    language_name = LANGUAGES[config["threads_language"]]["name"]
    await update.message.reply_text(
        f"Hello @{username}! 👋\n\n"
        f"📱 <b>Use /menu to open the main menu</b>\n\n"
        f"📊 <b>Your current THREADS settings:</b>\n"
        f"🌸 Model: {threads_model_name}\n"
        f"🌍 Language: {language_name}\n\n"
        f"💡 Commands:\n"
        f"• <code>/menu</code> - Open main menu\n"
        f"• <code>/status</code> - Your progress\n"
        f"• <code>/reset</code> - Reset thread progress",
        parse_mode="HTML"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    inizializzare_stato_utente_threads(user_id)
    total = user_threads_state[user_id]["total_sent"]
    remaining = MAX_VARIATIONS - (total % MAX_VARIATIONS)
    config = get_user_config(user_id)
    await update.message.reply_text(
        f"📊 <b>Your Status</b>\n\n"
        f"🌸 Threads model: {THREADS_MODELS[config['threads_model']]['name']}\n"
        f"🌍 Language: {LANGUAGES[config['threads_language']]['name']}\n\n"
        f"📝 Threads received: {total}\n"
        f"🔄 Remaining in cycle: {remaining}",
        parse_mode="HTML"
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_threads_state[user_id] = {"sent_numbers": set(), "total_sent": 0}
    salvare_stato_utente_threads(user_id)
    await update.message.reply_text("🔄 Your thread progress has been reset!")

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await user_menu(update, context)

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
    
    inizializzare_stato_fotos()
    inizializzare_stato_reels()
    
    global user_config
    user_config = caricare_config_utenti()
    global user_photo_config
    user_photo_config = caricare_config_foto_utenti()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Admin commands
    application.add_handler(CommandHandler("admin", admin_menu))
    application.add_handler(CommandHandler("allusers", all_users_status))
    application.add_handler(CommandHandler("userstats", user_stats))
    application.add_handler(CommandHandler("done", done_command))
    
    # User base commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    
    # User handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_handle_reel_request))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handle_reels_iguser))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.Document.ALL, receive_file))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, receive_media_upload))
    
    print("=" * 60)
    print("✅ BOT COMPLETO - THREADS + PHOTOS + REELS (USA E GETTA)")
    print("=" * 60)
    print(f"🤖 Bot: @TesoroA_bot")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("=" * 60)
    print("👑 ADMIN COMMANDS:")
    print("  • /admin - Open admin menu")
    print("  • /allusers - Show all users status")
    print("  • /userstats <id> - Show specific user status")
    print("  • /done - Finalize upload")
    print("=" * 60)
    print("📱 USER COMMANDS:")
    print("  • /menu - Open main menu")
    print("  • /status - Check progress")
    print("  • /reset - Reset threads")
    print("=" * 60)
    
    application.run_polling()

if __name__ == "__main__":
    main()