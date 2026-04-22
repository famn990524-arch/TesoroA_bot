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

MAIN_SENTENCES_FILE = os.path.join(DATA_FOLDER, "frases_principali.json")
USER_STATE_FILE = os.path.join(DATA_FOLDER, "user_state.json")

waiting_for_file = {}
MAX_VARIATIONS = 50

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_threads_state = {}

# ======================
# PERSISTENZA STATO UTENTI
# ======================

def caricare_stato_utenti() -> Dict:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    if not os.path.exists(USER_STATE_FILE):
        return {}
    with open(USER_STATE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvare_stato_utenti(stato: Dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(USER_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)

def inizializzare_stato_utente(user_id: int):
    stato = caricare_stato_utenti()
    user_id_str = str(user_id)
    
    if user_id_str not in stato:
        stato[user_id_str] = {
            "sent_numbers": [],
            "total_sent": 0
        }
        salvare_stato_utenti(stato)
    
    if user_id not in user_threads_state:
        user_threads_state[user_id] = {
            "sent_numbers": set(stato[user_id_str]["sent_numbers"]),
            "total_sent": stato[user_id_str]["total_sent"]
        }

def salvare_stato_utente_specifico(user_id: int):
    if user_id in user_threads_state:
        stato = caricare_stato_utenti()
        user_id_str = str(user_id)
        stato[user_id_str] = {
            "sent_numbers": list(user_threads_state[user_id]["sent_numbers"]),
            "total_sent": user_threads_state[user_id]["total_sent"]
        }
        salvare_stato_utenti(stato)

def resettare_tutti_gli_utenti():
    global user_threads_state
    user_threads_state = {}
    salvare_stato_utenti({})

# ======================
# FUNZIONI FRASI
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

# ======================
# FUNZIONE ALEATORIA CORRETTA
# ======================

def ottenere_numeri_disponibili_threads(user_id: int, quantita_desiderata: int) -> List[int]:
    """Ottiene numeri CASUALI di variazioni non ancora inviate all'utente"""
    inizializzare_stato_utente(user_id)
    
    inviati = user_threads_state[user_id]["sent_numbers"]
    
    # Numeri totali disponibili (1-50)
    tutti_i_numeri = list(range(1, MAX_VARIATIONS + 1))
    
    # Filtrar los no enviados
    disponibili = [n for n in tutti_i_numeri if n not in inviati]
    
    # Si no hay disponibles, reseta el ciclo
    if not disponibili:
        user_threads_state[user_id] = {
            "sent_numbers": set(),
            "total_sent": 0
        }
        salvare_stato_utente_specifico(user_id)
        disponibili = list(range(1, MAX_VARIATIONS + 1))
    
    # IMPORTANTE: Mezclar ALEATORIAMENTE
    random.shuffle(disponibili)
    
    # Devolver la cantidad deseada
    return disponibili[:quantita_desiderata]

def marcare_come_inviate_threads(user_id: int, numeri: List[int]):
    inizializzare_stato_utente(user_id)
    
    for num in numeri:
        user_threads_state[user_id]["sent_numbers"].add(num)
        user_threads_state[user_id]["total_sent"] += 1
    
    salvare_stato_utente_specifico(user_id)

# ======================
# API DEEPSEEK
# ======================

async def generare_variazione(frase_testo: str, frase_numero: int, variazione_num: int) -> str:
    system_prompt = f"""Sei una copywriter italiana. Devi creare UNA SOLA variazione della frase che ti viene data.

REGOLE:
1. Mantieni ESATTAMENTE la stessa struttura
2. Mantieni la CENSURA originale (usa * o emoji come nell'originale)
3. Cambia le parole, non il senso
4. Questa è la variazione numero {variazione_num}
5. Mantieni il tono giovane (18 anni) e il contesto italiano
6. La modella è CINESE fittizia che vive in ITALIA, si chiama MILA, usa sempre il nome MILA, non cambiare mai il nome
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
# COMANDI ADMIN
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
        resettare_tutti_gli_utenti()
        
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
# COMANDI UTENTI
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"👤 Nuovo utente: @{username} (ID: {user_id})")
    
    frasi = caricare_frasi_principali()
    inizializzare_stato_utente(user_id)
    totale_ricevute = user_threads_state[user_id]["total_sent"]
    
    await update.message.reply_text(
        f"Ciao @{username}! 👋\n\n"
        f"📝 <b>Come funziona:</b>\n"
        f"usa il comando /Nthreads (es. /5threads)\n\n"
        f"🎲 <b>CARATTERISTICHE:</b>\n"
        f"• Le variazioni sono CASUALI\n"
        f"• NON si ripetono fino ad esaurimento delle 50\n\n"
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
        await update.message.reply_text("❌ Nessuna frase caricata. L'admin deve prima caricare le frasi con /caricare_frase")
        return
    
    numeri_disponibili = ottenere_numeri_disponibili_threads(user_id, quantita)
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"🔄 @{username} ha richiesto {len(numeri_disponibili)} variazioni")
    else:
        await notificare_admin(context, f"👑 Hai richiesto {len(numeri_disponibili)} variazioni", is_admin_action=True)
    
    # Mensaje de inicio
    await update.message.reply_text(
        f"🎲 Generazione di {len(numeri_disponibili)} variazioni ...",
        parse_mode="HTML"
    )
    
    inviate = []
    
    # Mezclar las frases ALEATORIAMENTE también
    frasi_mischiate = frasi.copy()
    random.shuffle(frasi_mischiate)
    
    for i, num in enumerate(numeri_disponibili):
        # Seleccionar frase aleatoria
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
    
    # Mensaje de confirmación simplificado
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
    
    inizializzare_stato_utente(user_id)
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
    salvare_stato_utente_specifico(user_id)
    
    await update.message.reply_text("🔄 Il tuo progresso è stato resettato. Ora puoi ricominciare da capo!")
    
    if user_id != ADMIN_USER_ID:
        await notificare_admin(context, f"🔄 Utente @{username} ha resettato il suo progresso")
    else:
        await notificare_admin(context, f"👑 Hai resettato il tuo progresso", is_admin_action=True)

async def aiuto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    messaggio_base = (
        f"📖 <b>Guida del Bot</b>\n\n"
        f"<b>Comandi utente:</b>\n"
        f"• <code>/Nthreads</code> - Ricevi N variazioni CASUALI (es. /5threads)\n"
        f"• <code>/stato</code> - Visualizza il tuo progresso\n"
        f"• <code>/reset_utente</code> - Resetta il tuo progresso\n"
        f"• <code>/aiuto</code> - Mostra questa guida\n\n"
        f"🎲 <b>CARATTERISTICHE:</b>\n"
        f"• Le variazioni sono CASUALI\n"
        f"• NON si ripetono fino ad esaurimento delle 50\n\n"
        f"📌 <b>Esempi:</b>\n"
        f"• <code>/3threads</code> → 3 variazioni casuali\n"
        f"• <code>/12threads</code> → 12 variazioni casuali"
    )
    
    if user_id == ADMIN_USER_ID:
        messaggio_admin = (
            f"\n\n👑 <b>Comandi admin (@{ADMIN_USERNAME}):</b>\n"
            f"• <code>/caricare_frase</code> - Carica file .txt con frasi\n"
            f"• <code>/verificare_frase</code> - Mostra le frasi caricate"
        )
        await update.message.reply_text(messaggio_base + messaggio_admin, parse_mode="HTML")
    else:
        await update.message.reply_text(messaggio_base, parse_mode="HTML")

# ======================
# MAIN
# ======================

def main():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    
    if not os.path.exists(MAIN_SENTENCES_FILE):
        salvare_frasi_principali([])
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("caricare_frase", caricare_frase))
    application.add_handler(CommandHandler("verificare_frase", verificare_frase))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stato", stato))
    application.add_handler(CommandHandler("reset_utente", reset_utente))
    application.add_handler(CommandHandler("aiuto", aiuto))
    application.add_handler(MessageHandler(filters.Regex(r'^/\d+threads$'), thread_comando))
    application.add_handler(MessageHandler(filters.Document.ALL, ricevere_file_frase))
    
    print("=" * 50)
    print("✅ BOT VARIAZIONI CASUALI")
    print(f"🤖 Bot: @TesoroA_bot")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("=" * 50)
    print("🎲 Le variazioni sono CASUALI")
    print("✅ Non si ripetono fino a 50")
    print("=" * 50)
    
    application.run_polling()

if __name__ == "__main__":
    main()