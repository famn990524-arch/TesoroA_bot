async def caricare_foto_iguser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /caricarefoto iguser - Prepara per caricare foto per un iguser specifico"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Solo @famn25 può usare questo comando.")
        return
    
    # Estraiamo l'iguser dagli argomenti
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
    
    # Inizializzare sessione per questo iguser
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


async def foto_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i comandi /Nfoto iguser (con espacio)"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    text = update.message.text
    
    # Formato: /3foto bellamoreno
    match = re.match(r'^/(\d+)foto\s+(\w+)$', text.lower())
    if not match:
        return
    
    quantita = int(match.group(1))
    iguser = match.group(2).lower()
    
    if quantita < 1:
        await update.message.reply_text("❌ Usa /1foto iguser o più")
        return
    
    # Verificare che l'iguser esista nel database
    if iguser not in fotos_global_state or fotos_global_state[iguser]["total"] == 0:
        await update.message.reply_text(
            f"❌ Nessuna foto disponibile per @{iguser}.\n"
            f"L'admin deve caricare foto con /caricarefoto {iguser}"
        )
        return
    
    usate, disponibili, total = get_stato_fotos_per_iguser(iguser)
    
    # Avisar al admin si quedan pocas fotos
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