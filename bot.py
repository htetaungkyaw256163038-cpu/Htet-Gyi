@bot.message_handler(commands=['key'])
async def handle_key(message):
    global approve
    key = str(message.chat.id)
    print(f"[KEY] User: {key}, Chat type: {message.chat.type}")
    
    try:
        auth_list, sha = await get_file_content("auth_list.json")
        print(f"[KEY] auth_list keys: {list(auth_list.keys())}")
        print(f"[KEY] Looking for: {key}")
        print(f"[KEY] Found: {key in auth_list}")
        
        if key in auth_list:
            valid = check_key_expiration(auth_list[key])
            print(f"[KEY] Valid: {valid}")
            if valid:
                approve[message.chat.id] = True
                user_data[message.chat.id] = {}
                await bot.reply_to(message, "✅ Key မှန်ကန်ပါသည်။ /input ဖြင့် Session URL ထည့်ပါ။")
            else:
                approve[message.chat.id] = False
                await bot.reply_to(message, "❌ Key Expired ဖြစ်နေပါသည်။")
        else:
            await bot.reply_to(message, "⚠️ သင်၏ key ကို registered မလုပ်ရသေးပါ။")
    except Exception as e:
        print(f"[KEY] ERROR: {e}")
        import traceback
        traceback.print_exc()
        await bot.reply_to(message, f"Error: {e}")
