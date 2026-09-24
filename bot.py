async def main():
    await web_server()
    await bot.infinity_polling()

if __name__ == '__main__':
    asyncio.run(main())
