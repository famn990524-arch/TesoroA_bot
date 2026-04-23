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
PHOTOS_FOLDER = os.path.join(DATA_FOLDER, "fotos")
PHOTOS_DB_FILE = os.path.join(DATA_FOLDER, "fotos_db.json")

# Modelos disponibles
MODELS = ["Mila", "Yuna", "Bella", "Elira", "Aurora", "Milena", "Laura", "Isabella"]

# Idiomas disponibles
LANGUAGES = {
    "italian": {
        "name": "🇮🇹 Italian",
        "context": "Italian men, Italian food (pasta, pizza, gelato), Italian places (Rome, Milan, Venice), Italian culture"
    },
    "german": {
        "name": "🇩🇪 German", 
        "context": "German men, German food (Bratwurst, Sauerkraut, Pretzels), German places (Berlin, Munich, Hamburg), German culture"
    },
    "portuguese": {
        "name": "🇧🇷 Portuguese (Brazil)",
        "context": "Brazilian men, Brazilian food (Feijoada, Pão de Queijo, Brigadeiro), Brazilian places (Rio de Janeiro, São Paulo, Salvador), Brazilian culture"
    },
    "english": {
        "name": "🇺🇸 English (USA)",
        "context": "American men, American food (Burgers, Pizza, BBQ), American places (New York, Los Angeles, Miami), American culture"
    },
    "spanish": {
        "name": "🇪🇸 Spanish",
        "context": "Spanish men, Spanish food (Paella, Tapas, Jamón), Spanish places (Madrid, Barcelona, Seville), Spanish culture"
    }
}

# Estados
waiting_for_file = {}  # {user_id: model_name}
pending_photos = {}    # {user_id: {"iguser": "xxx", "fotos": [paths]}}

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
user_config = {}          # {user_id: {"model": "Mila", "language": "italian"}}
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
            "model": "Mila",
            "language": "italian"
        }
        salvare_config_utenti(user_config)
    return user_config[user_id_str]

def set_user_config(user_id: int, model: str, language: str):
    global user_config
    user_id_str = str(user_id)
    user_config[user_id_str] = {
        "model": model,
        "language": language
    }
    salvare_config_utenti(user_config)

# ======================
# FUNZIONI THREAD (VARIAZIONI)
# ======================

def caricare_frasi_per_modello(model: str) -> List[Dict]:
    """Carica le frasi per uno specifico modello"""
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
    """Genera una variazione adattata al modello e alla lingua"""
    
    language_config = LANGUAGES[language]
    
    system_prompt = f"""You are an Italian copywriter. Create ONE variation of the given phrase.

CRITICAL RULES:
1. The model's name is {model}. ALWAYS use this name when referring to herself.
2. Keep Chinese origin ONLY if mentioned in original phrase
3. Adapt ALL cultural references to {language_config['context']}
4. Keep censorship (use * or emojis as in original)
5. Change words, not the meaning
6. This is variation number {variazione_num}
7. Keep teen tone (18 years old)
8. ALWAYS speak in feminine (herself)
9. DO NOT include the original phrase number
10. Reply ONLY with the variation text, nothing else

IMPORTANT: 
- The character is CHINESE (if mentioned), living in the target country
- She is attracted to {language_config['context'].split(',')[0]}
- Use cultural references from {language_config['context']}

Original phrase (number {frase_numero}):
{frase_originale}

Generate variation number {variazione_num} in {language.upper()}:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Generate ONE variation in {language.upper()} for {model}:"}
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
# FUNZIONI FOTO (USA E GETTA) - IDENTICO A PRIMA
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

def reset_fotos_per_iguser(iguser: str):
    global fotos_global_state
    
    if iguser in fotos_global_state:
        for fid, meta in fotos_global_state[iguser].get("metadata", {}).items():
            path = meta.get("path")
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass
    
    fotos_global_state[iguser] = {
        "total": 0,
        "disponibili": [],
        "usate": [],
        "metadata": {}
    }
    salvare_stato_fotos_globale()

def aggiungere_foto_per_iguser(iguser: str, foto_path: str):
    global fotos_global_state
    
    if iguser not in fotos_global_state:
        fotos_global_state[iguser] = {
            "total": 0,
            "disponibili": [],
            "usate": [],
            "metadata": {}
        }
    
    nuovo_id = fotos_global_state[iguser]["total"] + 1
    
    ext = os.path.splitext(foto_path)[1]
    nuovo_nome = f"{iguser}_foto_{nuovo_id}{ext}"
    nuovo_path = os.path.join(PHOTOS_FOLDER, nuovo_nome)
    
    shutil.copy2(foto_path, nuovo_path)
    
    fotos_global_state[iguser]["metadata"][nuovo_id] = {
        "path": nuovo_path,
        "original_name": os.path.basename(foto_path),
        "used": False
    }
    
    fotos_global_state[iguser]["total"] += 1
    fotos_global_state[iguser]["disponibili"].append(nuovo_id)
    
    salvare_stato_fotos_globale()
    
    return nuovo_id

def ottenere_foto_disponibili_per_iguser(iguser: str, quantita: int) -> List[int]:
    if iguser not in fotos_global_state:
        return []
    
    disponibili = [fid for fid, meta in fotos_global_state[iguser]["metadata"].items() 
                   if not meta.get("used", False)]
    
    random.shuffle(disponibili)
    return disponibili[:quantita]

def marcare_foto_come_usate_per_iguser(iguser: str, foto_ids: List[int]):
    if iguser not in fotos_global_state:
        return
    
    for fid in foto_ids:
        if fid in fotos_global_state[iguser]["metadata"]:
            fotos_global_state[iguser]["metadata"][fid]["used"] = True
            if fid in fotos_global_state[iguser]["disponibili"]:
                fotos_global_state[iguser]["disponibili"].remove(fid)
            fotos_global_state[iguser]["usate"].append(fid)
    
    salvare_stato_fotos_globale()

def get_stato_fotos_per_iguser(iguser: str) -> tuple:
    if iguser not in fotos_global_state:
        return 0, 0, 0
    
    usate = len(fotos_global_state[iguser]["usate"])
    disponibili = len([f for f in fotos_global_state[iguser]["metadata"].values() if not f.get("used", False)])
    total = fotos_global_state[iguser]["total"]
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
# MENU INTERATTIVI
# ======================

async def menu_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il menu per selezionare la modello"""
    keyboard = []
    row = []
    for i, model in enumerate(MODELS):
        row.append(InlineKeyboardButton(model, callback_data=f"model_{model}"))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🌸 <b>Choose your model:</b>\n\nSelect the girl you want to generate threads for:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def menu_lingua(update: Update, context: ContextTypes.DEFAULT_TYPE, model: str):
    """Mostra il menu per selezionare la lingua"""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    for lang_key, lang_info in LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(lang_info["name"], callback_data=f"lang_{model}_{lang_key}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"🌸 <b>Model: {model}</b>\n\n"
        f"🌍 <b>Choose language:</b>\n\n"
        f"Select the language for your threads:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i callback dei menu"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("model_"):
        model = data.replace("model_", "")
        context.user_data["selected_model"] = model
        await menu_lingua(update, context, model)
    
    elif data.startswith("lang_"):
        parts = data.split("_")
        model = parts[1]
        language = parts[2]
        
        # Salva la configurazione dell'utente
        set_user_config(user_id, model, language)
        
        await query.edit_message_text(
            f"✅ <b>Configuration saved!</b>\n\n"
            f"🌸 Model: {model}\n"
            f"🌍 Language: {LANGUAGES[language]['name']}\n\n"
            f"Now use <code>/threads</code> to generate threads.\n"
            f"Example: <code>/5threads</code>",
            parse_mode="HTML"
        )

# ======================
# COMANDI ADMIN - FRASI PER MODELLO
# ======================

async def upload_frases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /upload model_name - Upload text file for a specific model"""
    user = update.effective_user
    
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ **Usage:** <code>/upload model_name</code>\n\n"
            f"Available models: {', '.join(MODELS)}\n\n"
            "Example: <code>/upload Mila</code>\n\n"
            "Then send a .txt file with numbered phrases.",
            parse_mode="HTML"
        )
        return
    
    model_name = context.args[0].capitalize()
    if model_name not in MODELS:
        await update.message.reply_text(
            f"❌ Invalid model. Available: {', '.join(MODELS)}"
        )
        return
    
    waiting_for_file[user.id] = model_name
    await update.message.reply_text(
        f"📁 **Ready to receive file for {model_name}!**\n\n"
        "Send a .txt file with numbered phrases.\n\n"
        "📌 **Expected format:**\n"
        "<code>43. Ti amo... Non è vero bugiardo...</code>\n"
        "<code>44. Sono molto sola 😍...</code>\n\n"
        "⏳ Waiting for file...",
        parse_mode="HTML"
    )

async def receive_phrases_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the .txt file with phrases for a model"""
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
    
    status_msg = await update.message.reply_text(f"📥 Processing file for {model_name}...")
    
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
        
        # Extract numbered phrases
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
            f"✅ <b>Phrases for {model_name} loaded successfully!</b>\n\n"
            f"📊 <b>Total phrases:</b> {len(frases)}\n\n"
            + "\n".join(preview) +
            (f"\n... and {len(frases) - 5} more" if len(frases) > 5 else ""),
            parse_mode="HTML"
        )
        
        await notificare_admin(context, f"📝 You loaded {len(frases)} phrases for {model_name}", is_admin_action=True)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def view_phrases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /view model_name - View loaded phrases for a model"""
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ Usage: <code>/view model_name</code>\n\n"
            f"Available models: {', '.join(MODELS)}",
            parse_mode="HTML"
        )
        return
    
    model_name = context.args[0].capitalize()
    if model_name not in MODELS:
        await update.message.reply_text(f"❌ Invalid model. Available: {', '.join(MODELS)}")
        return
    
    frases = caricare_frasi_per_modello(model_name)
    
    if not frases:
        await update.message.reply_text(f"❌ No phrases loaded for {model_name}.")
        return
    
    msg = f"📊 <b>PHRASES FOR {model_name.upper()}: {len(frases)}</b>\n\n"
    for f in frases[:10]:
        msg += f"• <b>{f['numero']}:</b> {f['testo'][:80]}...\n"
    
    if len(frases) > 10:
        msg += f"\n... and {len(frases) - 10} more"
    
    await update.message.reply_text(msg, parse_mode="HTML")

# ======================
# COMANDI ADMIN - FOTO USA E GETTA
# ======================

async def upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /uploadphoto iguser - Upload photos for an Instagram user"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ **Usage:** <code>/uploadphoto iguser</code>\n"
            "Example: <code>/uploadphoto bellamoreno</code>\n\n"
            "Then send photos (one or more at a time).\n"
            "When done, use <code>/done</code>",
            parse_mode="HTML"
        )
        return
    
    iguser = context.args[0].lower()
    
    waiting_for_file[user_id] = "fotos"
    if user_id not in pending_photos:
        pending_photos[user_id] = {}
    pending_photos[user_id] = {
        "iguser": iguser,
        "fotos": []
    }
    
    await update.message.reply_text(
        f"📸 **Uploading photos for @{iguser}**\n\n"
        "Send photos (one or more at a time).\n"
        "You'll receive a confirmation every 10 photos.\n"
        "When done, type <code>/done</code>\n\n"
        f"⏳ Photos received so far: 0",
        parse_mode="HTML"
    )

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives photos during upload session - confirms every 10 photos"""
    user = update.effective_user
    user_id = user.id
    
    if user_id not in waiting_for_file or waiting_for_file[user_id] != "fotos":
        return
    
    if user_id not in pending_photos:
        return
    
    iguser = pending_photos[user_id]["iguser"]
    photos_added = 0
    
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        temp_path = f"temp_photo_{int(time.time())}_{random.randint(1000,9999)}.jpg"
        await file.download_to_drive(temp_path)
        pending_photos[user_id]["fotos"].append(temp_path)
        photos_added += 1
    
    if update.message.document:
        doc = update.message.document
        if doc.mime_type and doc.mime_type.startswith('image/'):
            file = await context.bot.get_file(doc.file_id)
            ext = os.path.splitext(doc.file_name)[1]
            temp_path = f"temp_photo_{int(time.time())}_{random.randint(1000,9999)}{ext}"
            await file.download_to_drive(temp_path)
            pending_photos[user_id]["fotos"].append(temp_path)
            photos_added += 1
    
    if photos_added > 0:
        total = len(pending_photos[user_id]["fotos"])
        
        if total % 10 == 0:
            await update.message.reply_text(
                f"📸 Loaded {total} photos for @{iguser}...",
                parse_mode="HTML"
            )

async def done_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /done - Finalizes photo upload for an iguser"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if user_id not in waiting_for_file or waiting_for_file[user_id] != "fotos":
        await update.message.reply_text(
            "❌ No active upload session.\n"
            "Use /uploadphoto iguser first"
        )
        return
    
    if user_id not in pending_photos or not pending_photos[user_id]["fotos"]:
        await update.message.reply_text("❌ No pending photos to process.")
        del waiting_for_file[user_id]
        if user_id in pending_photos:
            del pending_photos[user_id]
        return
    
    iguser = pending_photos[user_id]["iguser"]
    pending = pending_photos[user_id]["fotos"]
    total_photos = len(pending)
    
    status_msg = await update.message.reply_text(f"📥 Processing {total_photos} photos for @{iguser}...")
    
    for path in pending:
        aggiungere_foto_per_iguser(iguser, path)
    
    for path in pending:
        if os.path.exists(path):
            try:
                os.unlink(path)
            except:
                pass
    
    del waiting_for_file[user_id]
    del pending_photos[user_id]
    
    used, available, total = get_stato_fotos_per_iguser(iguser)
    
    await status_msg.edit_text(
        f"✅ <b>Photos loaded successfully for @{iguser}!</b>\n\n"
        f"📸 Photos added: {total_photos}\n"
        f"📊 Total in pool: {total}\n"
        f"⏳ Available: {available}\n"
        f"✅ Used: {used}",
        parse_mode="HTML"
    )
    
    await notificare_admin(context, f"📸 You loaded {total_photos} photos for @{iguser}", is_admin_action=True)
    logger.info(f"Admin loaded {total_photos} photos for iguser: {iguser}")

async def photo_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /photostatus iguser - Show photo pool status"""
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can see this.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Usage: <code>/photostatus iguser</code>", parse_mode="HTML")
        return
    
    iguser = context.args[0].lower()
    used, available, total = get_stato_fotos_per_iguser(iguser)
    
    await update.message.reply_text(
        f"📸 <b>PHOTO POOL STATUS - @{iguser}</b>\n\n"
        f"• Total photos loaded: {total}\n"
        f"• Photos used: {used}\n"
        f"• Photos available: {available}\n\n"
        f"📌 Use /uploadphoto {iguser} to add more photos.",
        parse_mode="HTML"
    )

async def reset_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /resetphotos iguser - Reset all photos for an iguser"""
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Only @famn25 can use this command.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Usage: <code>/resetphotos iguser</code>", parse_mode="HTML")
        return
    
    iguser = context.args[0].lower()
    reset_fotos_per_iguser(iguser)
    
    await update.message.reply_text(f"✅ Photo pool for @{iguser} completely reset.", parse_mode="HTML")
    await notificare_admin(context, f"🔄 You reset the photo pool for @{iguser}", is_admin_action=True)

# ======================
# COMANDI UTENTI - THREADS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"👤 New user: @{username} (ID: {user_id})")
    
    # Get user config
    config = get_user_config(user_id)
    model = config["model"]
    language = config["language"]
    
    await update.message.reply_text(
        f"Hello @{username}! 👋\n\n"
        f"📝 <b>How to use:</b>\n"
        f"• <code>/threads</code> - Open menu to choose model and language\n"
        f"• <code>/Nthreads</code> - Generate N threads (using your saved settings)\n"
        f"• <code>/Nphoto iguser</code> - Receive N one-time photos\n\n"
        f"📌 <b>Examples:</b>\n"
        f"• <code>/threads</code> - Change model/language\n"
        f"• <code>/5threads</code> → 5 threads\n"
        f"• <code>/3photo bellamoreno</code> → 3 one-time photos\n\n"
        f"📊 <b>Your current settings:</b>\n"
        f"• Model: {model}\n"
        f"• Language: {LANGUAGES[language]['name']}\n\n"
        f"💡 <b>Commands:</b>\n"
        f"• <code>/status</code> - Your progress\n"
        f"• <code>/reset</code> - Reset progress\n"
        f"• <code>/help</code> - All commands",
        parse_mode="HTML"
    )

async def threads_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /threads - Shows model selection menu"""
    await menu_modelo(update, context)

async def generate_threads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /Nthreads commands"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    text = update.message.text
    
    match = re.match(r'^/(\d+)threads$', text.lower())
    if not match:
        return
    
    quantity = int(match.group(1))
    if quantity < 1 or quantity > MAX_VARIATIONS:
        await update.message.reply_text(f"❌ Use /1threads to /{MAX_VARIATIONS}threads")
        return
    
    # Get user config
    config = get_user_config(user_id)
    model = config["model"]
    language = config["language"]
    
    # Load phrases for model
    frases = caricare_frasi_per_modello(model)
    if not frases:
        await update.message.reply_text(
            f"❌ No phrases loaded for {model}.\n"
            f"Admin @{ADMIN_USERNAME} needs to upload phrases with /upload {model}"
        )
        return
    
    available_numbers = ottenere_numeri_disponibili_threads(user_id, quantity)
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"🔄 @{username} requested {len(available_numbers)} threads | Model: {model} | Language: {language}")
    else:
        await notificare_admin(context, f"👑 You requested {len(available_numbers)} threads | Model: {model} | Language: {language}", is_admin_action=True)
    
    # Send initial message with language info
    await update.message.reply_text(
        f"🎲 Generating {len(available_numbers)} threads for {model} in {LANGUAGES[language]['name']}...",
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

async def user_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /status - Shows user progress and current config"""
    user = update.effective_user
    user_id = user.id
    
    inizializzare_stato_utente_threads(user_id)
    total = user_threads_state[user_id]["total_sent"]
    remaining_in_cycle = MAX_VARIATIONS - (total % MAX_VARIATIONS)
    
    config = get_user_config(user_id)
    model = config["model"]
    language = config["language"]
    
    await update.message.reply_text(
        f"📊 <b>Your Status</b>\n\n"
        f"<b>Current settings:</b>\n"
        f"🌸 Model: {model}\n"
        f"🌍 Language: {LANGUAGES[language]['name']}\n\n"
        f"<b>Threads progress:</b>\n"
        f"• Threads received: {total}\n"
        f"• Remaining in cycle: {remaining_in_cycle}\n\n"
        f"💡 Use <code>/threads</code> to change model/language\n"
        f"💡 Use <code>/reset</code> to reset thread progress",
        parse_mode="HTML"
    )

async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /reset - Resets user's thread progress"""
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

# ======================
# COMANDI UTENTI - FOTO USA E GETTA
# ======================

async def photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /Nphoto iguser commands"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    text = update.message.text
    
    match = re.match(r'^/(\d+)photo\s+(\w+)$', text.lower())
    if not match:
        return
    
    quantity = int(match.group(1))
    iguser = match.group(2).lower()
    
    if quantity < 1:
        await update.message.reply_text("❌ Use /1photo iguser or more")
        return
    
    if iguser not in fotos_global_state or fotos_global_state[iguser]["total"] == 0:
        await update.message.reply_text(
            f"❌ No photos available for @{iguser}.\n"
            f"Admin must upload photos with /uploadphoto {iguser}"
        )
        return
    
    used, available, total = get_stato_fotos_per_iguser(iguser)
    
    if available <= THRESHOLD_FOTOS and available > 0:
        await notificare_admin(
            context,
            f"⚠️ <b>LOW PHOTOS WARNING - @{iguser}!</b>\n"
            f"📸 Photos available: {available}\n"
            f"📌 Use /uploadphoto {iguser} to add more.",
            is_admin_action=True
        )
    
    if available == 0:
        await update.message.reply_text(f"❌ No photos available for @{iguser}. Admin needs to upload new photos.")
        return
    
    if available < quantity:
        await update.message.reply_text(
            f"⚠️ Only {available} photos available for @{iguser}.\n"
            f"Sending {available} instead."
        )
        quantity = available
    
    await notificare_admin(context, f"📸 @{username} requested {quantity} photos for @{iguser}")
    
    photo_ids = ottenere_foto_disponibili_per_iguser(iguser, quantity)
    
    await update.message.reply_text(f"📸 Sending {len(photo_ids)} photos for @{iguser}...")
    
    sent = []
    for i, fid in enumerate(photo_ids, 1):
        metadata = fotos_global_state[iguser]["metadata"].get(fid, {})
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
                logger.error(f"Error sending photo {fid} for {iguser}: {e}")
    
    if sent:
        marcare_foto_come_usate_per_iguser(iguser, sent)
    
    await update.message.reply_text(
        f"✅ <b>Photos sent!</b>\n\n"
        f"📨 Sent: {len(sent)}",
        parse_mode="HTML"
    )
    
    logger.info(f"User {username} received {len(sent)} photos for {iguser}")

# ======================
# HELP COMMAND
# ======================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    base_message = (
        f"📖 <b>Bot Help</b>\n\n"
        f"<b>User Commands:</b>\n"
        f"• <code>/threads</code> - Choose model and language\n"
        f"• <code>/Nthreads</code> - Generate N random threads (ex: /5threads)\n"
        f"• <code>/Nphoto iguser</code> - Receive N one-time photos (ex: /3photo bellamoreno)\n"
        f"• <code>/status</code> - Your current settings and progress\n"
        f"• <code>/reset</code> - Reset your thread progress\n"
        f"• <code>/help</code> - Show this help\n\n"
        f"🎲 <b>FEATURES:</b>\n"
        f"• Threads adapt to selected model and language\n"
        f"• Languages: Italian, German, Portuguese, English (USA), Spanish (Spain)\n"
        f"• Photos are ONE-TIME USE, never repeat\n\n"
        f"📌 <b>Examples:</b>\n"
        f"• <code>/12threads</code>\n"
        f"• <code>/3photo bellamoreno</code>"
    )
    
    if user_id == ADMIN_USER_ID:
        admin_message = (
            f"\n\n👑 <b>Admin Commands (@{ADMIN_USERNAME}):</b>\n"
            f"├─ <b>THREADS (per model):</b>\n"
            f"│  • <code>/upload model_name</code> - Upload .txt file for a model\n"
            f"│  • <code>/view model_name</code> - View loaded phrases\n"
            f"├─ <b>ONE-TIME PHOTOS:</b>\n"
            f"│  • <code>/uploadphoto iguser</code> - Upload photos for Instagram user\n"
            f"│  • <code>/photostatus iguser</code> - Show photo pool status\n"
            f"│  • <code>/resetphotos iguser</code> - Reset photo pool\n"
            f"└─ <b>GENERAL:</b>\n"
            f"   • <code>/done</code> - Finalize photo upload\n\n"
            f"📁 <b>Models available:</b> {', '.join(MODELS)}\n"
            f"🌍 <b>Languages:</b> Italian, German, Portuguese, English, Spanish"
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
    
    # Initialize empty phrase files for models if they don't exist
    for model in MODELS:
        if not os.path.exists(os.path.join(DATA_FOLDER, f"frases_{model}.json")):
            salvare_frasi_per_modello(model, [])
    
    inizializzare_stato_fotos()
    
    # Load user configs
    global user_config
    user_config = caricare_config_utenti()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Admin commands - Threads
    application.add_handler(CommandHandler("upload", upload_frases))
    application.add_handler(CommandHandler("view", view_phrases))
    
    # Admin commands - Photos
    application.add_handler(CommandHandler("uploadphoto", upload_photo))
    application.add_handler(CommandHandler("photostatus", photo_status))
    application.add_handler(CommandHandler("resetphotos", reset_photos))
    application.add_handler(CommandHandler("done", done_photos))
    
    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("threads", threads_menu))
    application.add_handler(CommandHandler("status", user_status))
    application.add_handler(CommandHandler("reset", reset_user))
    application.add_handler(CommandHandler("help", help_command))
    
    # Dynamic commands
    application.add_handler(MessageHandler(filters.Regex(r'^/\d+threads$'), generate_threads))
    application.add_handler(MessageHandler(filters.Regex(r'^/\d+photo\s+\w+$'), photo_command))
    
    # File and photo handlers
    application.add_handler(MessageHandler(filters.Document.ALL, receive_phrases_file))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_photo))
    
    # Callback handler for inline menus
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    print("=" * 60)
    print("✅ BOT COMPLETO - THREADS CON MODELLI E LINGUE + FOTO USA E GETTA")
    print("=" * 60)
    print(f"🤖 Bot: @TesoroA_bot")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("=" * 60)
    print("📌 ADMIN COMMANDS:")
    print("  • /upload Mila - upload .txt file for model Mila")
    print("  • /view Mila - view loaded phrases")
    print("  • /uploadphoto bellamoreno - upload photos")
    print("  • /photostatus bellamoreno - check status")
    print("  • /resetphotos bellamoreno - reset photos")
    print("  • /done - finalize photo upload")
    print("=" * 60)
    print("📌 USER COMMANDS:")
    print("  • /threads - choose model and language")
    print("  • /5threads - generate 5 threads")
    print("  • /3photo bellamoreno - get 3 one-time photos")
    print("  • /status, /reset, /help")
    print("=" * 60)
    print(f"🌍 MODELS: {', '.join(MODELS)}")
    print(f"🌍 LANGUAGES: Italian, German, Portuguese, English, Spanish")
    print("=" * 60)
    
    application.run_polling()

if __name__ == "__main__":
    main()