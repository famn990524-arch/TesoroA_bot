import asyncio
import logging
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp
import json
from typing import List, Dict
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

# Detecta el entorno y usa la ruta correcta
if os.path.exists('/app'):
    DATA_FOLDER = "/app/data"
else:
    DATA_FOLDER = "."

# Archivos
MAIN_SENTENCES_FILE = os.path.join(DATA_FOLDER, "frases_principali.json")
USER_STATE_FILE = os.path.join(DATA_FOLDER, "user_state.json")
PHOTOS_FOLDER = os.path.join(DATA_FOLDER, "fotos")
PHOTOS_DB_FILE = os.path.join(DATA_FOLDER, "fotos_db.json")

# Estados
waiting_for_file = {}  # {user_id: "frase" or "fotos"}
pending_photos = {}    # {user_id: {"iguser": "xxx", "fotos": [paths]}}

# Constantes
MAX_VARIATIONS = 50
THRESHOLD_FOTOS = 5  # Avisar al admin cuando queden menos de X fotos

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# STRUTTURE DATI
# ======================

user_threads_state = {}  # Para threads (variaciones)
fotos_global_state = {}  # Para fotos: {"iguser": {"total": X, "disponibili": [ids], "usate": [ids], "metadata": {id: {"path": xxx, "used": False}}}

# ======================
# FUNZIONI THREAD (VARIAZIONI) - INVARIATE
# ======================

def estrarre_frasi_dal_testo(testo: str) -> List[Dict]:
    frasi = []
    linee = testo.strip().split('\n')
    frase_attuale = None
    numero_attuale = None
    
    i = 0
    while i < len(linee):
        linea = linee[i].strip()
        if not linea:
            i += 1
            continue
        
        match = re.match(r'^(\d{1,2})\.\s+(.*)', linea)
        
        if match:
            if frase_attuale is not None and numero_attuale is not None:
                frasi.append({
                    "numero": numero_attuale,
                    "testo": frase_attuale.strip()
                })
            
            numero_attuale = int(match.group(1))
            frase_attuale = match.group(2)
        else:
            if frase_attuale is not None:
                frase_attuale += "\n" + linea
        
        i += 1
    
    if frase_attuale is not None and numero_attuale is not None:
        frasi.append({
            "numero": numero_attuale,
            "testo": frase_attuale.strip()
        })
    
    return frasi

def pulisci_numero_dal_testo(testo: str) -> str:
    return re.sub(r'^\d+\.\s*', '', testo)

def caricare_frasi_principali() -> List[Dict]:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(MAIN_SENTENCES_FILE):
        return []
    with open(MAIN_SENTENCES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvare_frasi_principali(frasi: List[Dict]):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(MAIN_SENTENCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(frasi, f, ensure_ascii=False, indent=2)

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

def resettare_tutti_gli_utenti_threads():
    global user_threads_state
    user_threads_state = {}
    salvare_stato_utenti_threads({})

async def generare_variazione(frase_testo: str, frase_numero: int, variazione_num: int) -> str:
    system_prompt = f"""Sei una copywriter italiana. Devi creare UNA SOLA variazione della frase che ti viene data.

REGOLE:
1. Mantieni ESATTAMENTE la stessa struttura
2. Mantieni la CENSURA originale (usa * o emoji come nell'originale)
3. Cambia le parole, non il senso
4. Questa è la variazione numero {variazione_num}
5. Mantieni il tono giovane (18 anni) e il contesto italiano
6. La modella è CINESE fittizia che vive in ITALIA
7. Parla sempre in femminile, mai riferimento maschile
8. NON includere il numero della frase originale
9. Rispondi SOLO con il testo della variazione, nient'altro"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Frase originale (numero {frase_numero}):\n{frase_testo}\n\nGenera la variazione numero {variazione_num} in ITALIANO:"}
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
                    return f"❌ Errore API: {response.status}"
    except Exception as e:
        return f"❌ Errore: {str(e)}"

# ======================
# FUNZIONI FOTO (USA E GETTA PER IGUSER)
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
                text=f"👑 <b>NOTIFICA ADMIN:</b>\n{messaggio}",
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=messaggio,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Errore nell'invio della notifica all'admin: {e}")

# ======================
# COMANDI ADMIN - FRASI (Threads)
# ======================

async def caricare_frase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Solo @famn25 può usare questo comando.")
        return
    
    waiting_for_file[user_id] = "frase"
    await update.message.reply_text(
        "📁 **Pronto a ricevere il file!**\n\n"
        "Ora invia il file .txt con le frasi numerate.\n\n"
        "📌 **Formato atteso:**\n"
        "<code>43. Ti amo... Non è vero bugiardo...</code>\n"
        "<code>44. Sono molto sola 😍...</code>\n\n"
        "⏳ In attesa del file...",
        parse_mode="HTML"
    )

async def ricevere_file_frase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id not in waiting_for_file or waiting_for_file[user_id] != "frase":
        return
    
    if not update.message.document:
        await update.message.reply_text("❌ Per favore, invia un file .txt")
        return
    
    document = update.message.document
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Il file deve essere .txt")
        return
    
    status_msg = await update.message.reply_text("📥 Elaborazione del file...")
    
    try:
        file = await context.bot.get_file(document.file_id)
        
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', encoding='utf-8', delete=False) as tmp_file:
            await file.download_to_drive(tmp_file.name)
            with open(tmp_file.name, 'r', encoding='utf-8') as f:
                contenuto = f.read()
        
        os.unlink(tmp_file.name)
        
        if not contenuto or not contenuto.strip():
            await status_msg.edit_text("❌ Il file è vuoto")
            return
        
        frasi = estrarre_frasi_dal_testo(contenuto)
        
        if not frasi:
            await status_msg.edit_text("❌ Nessuna frase numerata rilevata nel file.")
            return
        
        salvare_frasi_principali(frasi)
        resettare_tutti_gli_utenti_threads()
        
        del waiting_for_file[user_id]
        
        anteprima = []
        for f in frasi[:10]:
            anteprima.append(f"📌 <b>Frase {f['numero']}:</b> {f['testo'][:60]}...")
        
        await status_msg.edit_text(
            f"✅ <b>Frasi caricate correttamente!</b>\n\n"
            f"📊 <b>Totale frasi:</b> {len(frasi)}\n\n"
            + "\n".join(anteprima) +
            (f"\n... e altre {len(frasi) - 10} frasi" if len(frasi) > 10 else ""),
            parse_mode="HTML"
        )
        
        await notificare_admin(context, f"📝 Hai caricato {len(frasi)} nuove frasi.", is_admin_action=True)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Errore: {str(e)}")

async def verificare_frase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Solo @famn25 può usare questo comando.")
        return
    
    frasi = caricare_frasi_principali()
    
    if not frasi:
        await update.message.reply_text("❌ Nessuna frase caricata.")
        return
    
    msg = f"📊 <b>FRASI CARICATE: {len(frasi)}</b>\n\n"
    for f in frasi[:20]:
        msg += f"• <b>{f['numero']}:</b> {f['testo'][:80]}...\n"
    
    if len(frasi) > 20:
        msg += f"\n... e altre {len(frasi) - 20} frasi"
    
    await update.message.reply_text(msg, parse_mode="HTML")
    await notificare_admin(context, f"📋 Hai verificato le frasi caricate. Totale: {len(frasi)}", is_admin_action=True)

# ======================
# COMANDI ADMIN - FOTO USA E GETTA (con argumento)
# ======================

async def caricare_foto_iguser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /caricarefoto iguser - Prepara per caricare foto per un iguser specifico"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Solo @famn25 può usare questo comando.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ **Formato errato!**\n\n"
            "Usa: <code>/caricarefoto iguser</code>\n"
            "es. <code>/caricarefoto bellamoreno</code>\n\n"
            "Poi invia le foto (una o più alla volta).\n"
            "Quando hai finito, usa <code>/done</code>",
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
        f"📸 **Caricamento foto per @{iguser}**\n\n"
        "Invia le foto (una o più alla volta).\n"
        "Quando hai finito, scrivi <code>/done</code>\n\n"
        f"⏳ Foto ricevute finora: 0",
        parse_mode="HTML"
    )

async def ricevere_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve le foto durante la sessione di caricamento"""
    user = update.effective_user
    user_id = user.id
    
    if user_id not in waiting_for_file or waiting_for_file[user_id] != "fotos":
        return
    
    if user_id not in pending_photos:
        return
    
    iguser = pending_photos[user_id]["iguser"]
    fotos_recibidas = 0
    
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        temp_path = f"temp_foto_{int(time.time())}_{random.randint(1000,9999)}.jpg"
        await file.download_to_drive(temp_path)
        pending_photos[user_id]["fotos"].append(temp_path)
        fotos_recibidas += 1
    
    if update.message.document:
        doc = update.message.document
        if doc.mime_type and doc.mime_type.startswith('image/'):
            file = await context.bot.get_file(doc.file_id)
            ext = os.path.splitext(doc.file_name)[1]
            temp_path = f"temp_foto_{int(time.time())}_{random.randint(1000,9999)}{ext}"
            await file.download_to_drive(temp_path)
            pending_photos[user_id]["fotos"].append(temp_path)
            fotos_recibidas += 1
    
    if fotos_recibidas > 0:
        total_actual = len(pending_photos[user_id]["fotos"])
        await update.message.reply_text(
            f"✅ Ricevute {fotos_recibidas} foto per @{iguser}.\n"
            f"📸 Totale accumulato: {total_actual}\n\n"
            f"Quando hai finito, scrivi <code>/done</code>",
            parse_mode="HTML"
        )

async def done_fotos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /done - Finalizza il caricamento delle foto per un iguser"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Solo @famn25 può usare questo comando.")
        return
    
    if user_id not in waiting_for_file or waiting_for_file[user_id] != "fotos":
        await update.message.reply_text(
            "❌ Non c'è una sessione di caricamento attiva.\n"
            "Usa prima /caricarefoto iguser"
        )
        return
    
    if user_id not in pending_photos or not pending_photos[user_id]["fotos"]:
        await update.message.reply_text("❌ Nessuna foto pendente da processare.")
        del waiting_for_file[user_id]
        if user_id in pending_photos:
            del pending_photos[user_id]
        return
    
    iguser = pending_photos[user_id]["iguser"]
    fotos_pendenti = pending_photos[user_id]["fotos"]
    
    status_msg = await update.message.reply_text(f"📥 Elaborazione di {len(fotos_pendenti)} foto per @{iguser}...")
    
    for path in fotos_pendenti:
        aggiungere_foto_per_iguser(iguser, path)
    
    for path in fotos_pendenti:
        if os.path.exists(path):
            try:
                os.unlink(path)
            except:
                pass
    
    del waiting_for_file[user_id]
    del pending_photos[user_id]
    
    usate, disponibili, total = get_stato_fotos_per_iguser(iguser)
    
    await status_msg.edit_text(
        f"✅ <b>Foto caricate correttamente per @{iguser}!</b>\n\n"
        f"📸 Foto aggiunte: {len(fotos_pendenti)}\n"
        f"📊 Totale nel pool: {total}\n"
        f"⏳ Disponibili: {disponibili}\n"
        f"✅ Usate: {usate}",
        parse_mode="HTML"
    )
    
    await notificare_admin(context, f"📸 Hai caricato {len(fotos_pendenti)} foto per @{iguser}", is_admin_action=True)
    logger.info(f"Admin ha caricato {len(fotos_pendenti)} foto per iguser: {iguser}")

async def stato_foto_iguser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stato_foto iguser - Mostra stato pool foto per un iguser"""
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Solo @famn25 può vedere questo.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Usa: <code>/stato_foto iguser</code>", parse_mode="HTML")
        return
    
    iguser = context.args[0].lower()
    usate, disponibili, total = get_stato_fotos_per_iguser(iguser)
    
    await update.message.reply_text(
        f"📸 <b>STATO POOL FOTO - @{iguser}</b>\n\n"
        f"• Totale foto caricate: {total}\n"
        f"• Foto usate: {usate}\n"
        f"• Foto disponibili: {disponibili}\n\n"
        f"📌 Usa /caricarefoto {iguser} per aggiungere altre foto.",
        parse_mode="HTML"
    )

async def reset_foto_iguser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /reset_foto iguser - Resetta tutte le foto per un iguser"""
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Solo @famn25 può usare questo comando.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Usa: <code>/reset_foto iguser</code>", parse_mode="HTML")
        return
    
    iguser = context.args[0].lower()
    reset_fotos_per_iguser(iguser)
    
    await update.message.reply_text(f"✅ Pool di foto per @{iguser} resettato completamente.", parse_mode="HTML")
    await notificare_admin(context, f"🔄 Hai resettato il pool foto per @{iguser}", is_admin_action=True)

# ======================
# COMANDI UTENTI - THREADS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"👤 Nuovo utente: @{username} (ID: {user_id})")
    
    frasi = caricare_frasi_principali()
    inizializzare_stato_utente_threads(user_id)
    totale_ricevute = user_threads_state[user_id]["total_sent"]
    
    await update.message.reply_text(
        f"Ciao @{username}! 👋\n\n"
        f"📝 <b>Come funziona:</b>\n"
        f"• <code>/Nthreads</code> - Ricevi N variazioni CASUALI\n"
        f"• <code>/Nfoto iguser</code> - Ricevi N foto usa e getta\n\n"
        f"📌 <b>Esempi:</b>\n"
        f"• <code>/12threads</code> → 12 variazioni\n"
        f"• <code>/3foto bellamoreno</code> → 3 foto usa e getta\n\n"
        f"📊 <b>Il tuo progresso:</b>\n"
        f"• Variazioni ricevute: {totale_ricevute}\n\n"
        f"💡 <b>Comandi:</b>\n"
        f"• <code>/stato</code> - Il tuo progresso\n"
        f"• <code>/reset_utente</code> - Resetta progresso\n"
        f"• <code>/aiuto</code> - Tutti i comandi",
        parse_mode="HTML"
    )

async def thread_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    text = update.message.text
    
    match = re.match(r'^/(\d+)threads$', text.lower())
    if not match:
        return
    
    quantita = int(match.group(1))
    if quantita < 1 or quantita > MAX_VARIATIONS:
        await update.message.reply_text(f"❌ Usa /1threads fino a /{MAX_VARIATIONS}threads")
        return
    
    frasi = caricare_frasi_principali()
    if not frasi:
        await update.message.reply_text("❌ Nessuna frase caricata.")
        return
    
    numeri_disponibili = ottenere_numeri_disponibili_threads(user_id, quantita)
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"🔄 @{username} ha richiesto {len(numeri_disponibili)} variazioni")
    else:
        await notificare_admin(context, f"👑 Hai richiesto {len(numeri_disponibili)} variazioni", is_admin_action=True)
    
    await update.message.reply_text(
        f"🎲 Generazione di {len(numeri_disponibili)} variazioni ...",
        parse_mode="HTML"
    )
    
    inviate = []
    frasi_mischiate = frasi.copy()
    random.shuffle(frasi_mischiate)
    
    for i, num in enumerate(numeri_disponibili):
        frase_attuale = frasi_mischiate[i % len(frasi_mischiate)]
        
        variazione = await generare_variazione(frase_attuale["testo"], frase_attuale["numero"], num)
        
        if variazione and not variazione.startswith("❌"):
            variazione_pulita = pulisci_numero_dal_testo(variazione)
            await update.message.reply_text(variazione_pulita, parse_mode="HTML")
            inviate.append(num)
            await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(f"❌ Errore nella generazione della variazione {num}")
    
    marcare_come_inviate_threads(user_id, inviate)
    totale_ricevute = user_threads_state[user_id]["total_sent"]
    
    await update.message.reply_text(
        f"✅ <b>Variazioni inviate!</b>\n\n"
        f"📨 Inviate in questa sessione: {len(inviate)}\n"
        f"📊 Totale variazioni ricevute: {totale_ricevute}",
        parse_mode="HTML"
    )
    
    logger.info(f"Utente {username} ha ricevuto {len(inviate)} variazioni. Totale: {totale_ricevute}")

async def stato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    inizializzare_stato_utente_threads(user_id)
    totale = user_threads_state[user_id]["total_sent"]
    rimanenti_nel_ciclo = MAX_VARIATIONS - (totale % MAX_VARIATIONS)
    
    await update.message.reply_text(
        f"📊 <b>Il tuo stato</b>\n\n"
        f"• Variazioni ricevute: {totale}\n"
        f"• Prossime variazioni disponibili: {rimanenti_nel_ciclo}\n\n"
        f"💡 Usa /reset_utente per resettare il progresso",
        parse_mode="HTML"
    )

async def reset_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    user_threads_state[user_id] = {"sent_numbers": set(), "total_sent": 0}
    salvare_stato_utente_threads(user_id)
    
    await update.message.reply_text("🔄 Il tuo progresso è stato resettato. Ora puoi ricominciare da capo!")
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"🔄 Utente @{username} ha resettato il suo progresso")
    else:
        await notificare_admin(context, f"👑 Hai resettato il tuo progresso", is_admin_action=True)

# ======================
# COMANDI UTENTI - FOTO USA E GETTA
# ======================

async def foto_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i comandi /Nfoto iguser (es. /3foto bellamoreno)"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    text = update.message.text
    
    match = re.match(r'^/(\d+)foto\s+(\w+)$', text.lower())
    if not match:
        return
    
    quantita = int(match.group(1))
    iguser = match.group(2).lower()
    
    if quantita < 1:
        await update.message.reply_text("❌ Usa /1foto iguser o più")
        return
    
    if iguser not in fotos_global_state or fotos_global_state[iguser]["total"] == 0:
        await update.message.reply_text(
            f"❌ Nessuna foto disponibile per @{iguser}.\n"
            f"L'admin deve caricare foto con /caricarefoto {iguser}"
        )
        return
    
    usate, disponibili, total = get_stato_fotos_per_iguser(iguser)
    
    if disponibili <= THRESHOLD_FOTOS and disponibili > 0:
        await notificare_admin(
            context,
            f"⚠️ <b>ATTENZIONE - POCHE FOTO PER @{iguser}!</b>\n"
            f"📸 Foto disponibili: {disponibili}\n"
            f"📌 Usa /caricarefoto {iguser} per caricare altre foto.",
            is_admin_action=True
        )
    
    if disponibili == 0:
        await update.message.reply_text(f"❌ Nessuna foto disponibile per @{iguser}. L'admin deve caricare nuove foto.")
        return
    
    if disponibili < quantita:
        await update.message.reply_text(
            f"⚠️ Solo {disponibili} foto disponibili per @{iguser}.\n"
            f"Te ne invio {disponibili}."
        )
        quantita = disponibili
    
    await notificare_admin(context, f"📸 @{username} ha richiesto {quantita} foto per @{iguser}")
    
    foto_ids = ottenere_foto_disponibili_per_iguser(iguser, quantita)
    
    await update.message.reply_text(f"📸 Invio di {len(foto_ids)} foto per @{iguser}...")
    
    inviate = []
    for i, fid in enumerate(foto_ids, 1):
        metadata = fotos_global_state[iguser]["metadata"].get(fid, {})
        foto_path = metadata.get("path")
        
        if foto_path and os.path.exists(foto_path):
            try:
                with open(foto_path, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=f"📸 Foto {i}/{len(foto_ids)}"
                    )
                inviate.append(fid)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Errore invio foto {fid} per {iguser}: {e}")
    
    if inviate:
        marcare_foto_come_usate_per_iguser(iguser, inviate)
    
    await update.message.reply_text(
        f"✅ <b>Foto inviate!</b>\n\n"
        f"📨 Inviate: {len(inviate)}",
        parse_mode="HTML"
    )
    
    logger.info(f"Utente {username} ha ricevuto {len(inviate)} foto per {iguser}")

# ======================
# COMANDO AIUTO
# ======================

async def aiuto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    messaggio_base = (
        f"📖 <b>Guida del Bot</b>\n\n"
        f"<b>Comandi utente:</b>\n"
        f"• <code>/Nthreads</code> - Ricevi N variazioni CASUALI (es. /5threads)\n"
        f"• <code>/Nfoto iguser</code> - Ricevi N foto usa e getta (es. /3foto bellamoreno)\n"
        f"• <code>/stato</code> - Visualizza il tuo progresso delle variazioni\n"
        f"• <code>/reset_utente</code> - Resetta il progresso delle variazioni\n"
        f"• <code>/aiuto</code> - Mostra questa guida\n\n"
        f"🎲 <b>CARATTERISTICHE:</b>\n"
        f"• Le variazioni sono CASUALI e NON si ripetono fino a 50\n"
        f"• Le foto sono USA E GETTA, non si ripetono mai\n\n"
        f"📌 <b>Esempi:</b>\n"
        f"• <code>/12threads</code> → 12 variazioni casuali\n"
        f"• <code>/3foto bellamoreno</code> → 3 foto usa e getta"
    )
    
    if user_id == ADMIN_USER_ID:
        messaggio_admin = (
            f"\n\n👑 <b>Comandi admin (@{ADMIN_USERNAME}):</b>\n"
            f"├─ <b>FRASI:</b>\n"
            f"│  • <code>/caricare_frase</code> - Carica file .txt con frasi\n"
            f"│  • <code>/verificare_frase</code> - Mostra frasi caricate\n"
            f"├─ <b>FOTO USA E GETTA:</b>\n"
            f"│  • <code>/caricarefoto iguser</code> - Carica foto per un utente Instagram\n"
            f"│  • <code>/stato_foto iguser</code> - Mostra stato pool foto\n"
            f"│  • <code>/reset_foto iguser</code> - Resetta pool foto\n"
            f"└─ <b>COMANDI GENERALI:</b>\n"
            f"   • <code>/done</code> - Finalizza il caricamento delle foto"
        )
        await update.message.reply_text(messaggio_base + messaggio_admin, parse_mode="HTML")
    else:
        await update.message.reply_text(messaggio_base, parse_mode="HTML")

# ======================
# MAIN
# ======================

def main():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    os.makedirs(PHOTOS_FOLDER, exist_ok=True)
    
    if not os.path.exists(MAIN_SENTENCES_FILE):
        salvare_frasi_principali([])
    
    inizializzare_stato_fotos()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Comandi admin - Frasi
    application.add_handler(CommandHandler("caricare_frase", caricare_frase))
    application.add_handler(CommandHandler("verificare_frase", verificare_frase))
    
    # Comandi admin - Foto (con argumento)
    application.add_handler(CommandHandler("caricarefoto", caricare_foto_iguser))
    application.add_handler(CommandHandler("stato_foto", stato_foto_iguser))
    application.add_handler(CommandHandler("reset_foto", reset_foto_iguser))
    application.add_handler(CommandHandler("done", done_fotos))
    
    # Comandi utente
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stato", stato))
    application.add_handler(CommandHandler("reset_utente", reset_utente))
    application.add_handler(CommandHandler("aiuto", aiuto))
    
    # Comandi dinamici
    application.add_handler(MessageHandler(filters.Regex(r'^/\d+threads$'), thread_comando))
    application.add_handler(MessageHandler(filters.Regex(r'^/\d+foto\s+\w+$'), foto_comando))
    
    # Handler per ricevere file e foto
    application.add_handler(MessageHandler(filters.Document.ALL, ricevere_file_frase))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, ricevere_foto))
    
    print("=" * 60)
    print("✅ BOT COMPLETO - THREADS + FOTO USA E GETTA")
    print("=" * 60)
    print(f"🤖 Bot: @TesoroA_bot")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("=" * 60)
    print("📌 COMANDI ADMIN - FRASI:")
    print("  • /caricare_frase")
    print("  • /verificare_frase")
    print("=" * 60)
    print("📌 COMANDI ADMIN - FOTO USA E GETTA:")
    print("  • /caricarefoto bellamoreno")
    print("  • /stato_foto bellamoreno")
    print("  • /reset_foto bellamoreno")
    print("  • /done")
    print("=" * 60)
    print("📌 COMANDI UTENTI:")
    print("  • /12threads -> variazioni casuali")
    print("  • /3foto bellamoreno -> foto usa e getta")
    print("  • /stato, /reset_utente, /aiuto")
    print("=" * 60)
    
    application.run_polling()

if __name__ == "__main__":
    main()