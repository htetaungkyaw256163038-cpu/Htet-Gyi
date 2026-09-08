@bot.message_handler(commands=['result'])
async def handle_result(message):
    auth_list, _ = await get_file_content("auth_list.json")
    if str(message.chat.id) in auth_list:
        try:
            results, _ = await get_file_content("result.json")
            chat_id_str = str(message.chat.id)
            if chat_id_str in results and results[chat_id_str]:
                codes = "\n".join(results[chat_id_str])
                await bot.reply_to(message, f"📋 ရလဒ်များ -\n\n{codes}")
            else:
                await bot.reply_to(message, "ပြသရန် ရလဒ်မရှိသေးပါ။")
        except Exception as e:
            print(f"Error at handle_result: {e}")
            await bot.reply_to(message, "ရလဒ်ဆွဲယူရာတွင် အမှားအယွင်းရှိခဲ့ပါသည်။")
    else:
        await bot.reply_to(message, "သင်သည် ဤ command ကိုသုံးရန် ခွင့်ပြုချက်မရှိပါ။")
