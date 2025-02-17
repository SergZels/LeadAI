import asyncio
import random
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from openai import OpenAI
from configNEW import BOTS,openai_api_key, GROUP_CONFIG, CONTEXT_LEN

client_ai = OpenAI(api_key=openai_api_key)

def init(): # початкова ініціалізація, на продакшені буде краще використовувати базу даних
    try:
        for group_id, config in GROUP_CONFIG.items():
            # Вибираємо ботів, у яких group_id присутній у списку chat_ids
            bots_for_group = [bot["telegramID"] for bot in BOTS if group_id in bot["chat_ids"]]

            config["CHOSEN_BOT"] = bots_for_group.copy()[0]# цей буде відповідати самим першим при запуску скрипта
            config["BOTS_SET"] = list(bots_for_group.copy())# типу еталонна множина
            config["Available_Bots"] = list(bots_for_group.copy())#динамічна множина по якій буде Random
    except:
        print(f"До групи {group_id} не підєднано ботів")

def get_bot_name_by_telegramID(telegram_id):# повартає імя по id
    for bot in BOTS:
        if bot["telegramID"] == telegram_id:
            return bot["name"]
    return None

# Функція для запуску кожного бота, точніше кожної корутини в які буде жити бот
async def run_bot(api_id, api_hash, session_string, group_personas, chat_ids, delay, telegramID,name):
    client = TelegramClient(StringSession(session_string), api_id, api_hash)

    @client.on(events.NewMessage(chats=chat_ids)) # обробник повідомлень у множині груп
    async def handle_message(event):
        global GROUP_CONFIG # блок ініціалізації
        BOTS_SET = GROUP_CONFIG.get(event.chat_id, {}).get("BOTS_SET", list())
        available_bots = GROUP_CONFIG.get(event.chat_id, {}).get("Available_Bots", list(BOTS_SET))
        CHOSEN_BOT = GROUP_CONFIG.get(event.chat_id, {}).get("CHOSEN_BOT", '')

        # print(f"Бот ({me.id}): отримав повідомлення в групі {event.chat_id}: {event.text} від {event.sender_id}")

        await asyncio.sleep(delay) # затримка перед відповідю
        await client.send_read_acknowledge(event.chat_id, message=event.message)# боти прочитав (2 галочки)

        me = await client.get_me()# блок відповіді на реплай
        replayMessage = ''
        if event.message.reply_to and event.message.reply_to.reply_to_msg_id:
            replied_msg = await event.client.get_messages(event.chat_id, ids=event.message.reply_to.reply_to_msg_id)
            if replied_msg and replied_msg.sender_id != me.id:
                print(f"Не мій ({name}) реплай, пропускаємо...")
                return
            print(f"User {event.message.sender_id} replied to bot {me.id}: {event.message.text}")
            replayMessage = f"Користувач прочитав твоє повідомлення та прокоментував: {event.message.text}. Дай йому відповідь. Ось твоє повідомлення: {replied_msg.text} "

        if event.sender_id not in BOTS_SET and not event.message.reply_to:# Якщо якийсь користувач просто написав в групі - ігноруємо
            print(f"Повідомлення від користувача {event.sender_id}. Пропускаємо...")
            return

        if me.id != CHOSEN_BOT and not event.message.reply_to:# якщо цей бот не обраний - виходимо
            print(f"Бот {me.id} {name} не обраний для відповіді. Пропускаємо...")
            return

        # Отримуємо тему групи
        group_settings = GROUP_CONFIG.get(event.chat_id, {})
        topic = group_settings.get("topic", "загальна тема")

        # Отримуємо персоналізацію для даної групи
        persona = group_personas.get(event.chat_id,"Підтримуєш у розмові тему групи.")

        found_messages = []# блок який витягує попередні переписки в групі
        messages=''
        async for message in client.iter_messages(event.chat_id, limit=20):  # Шукаємо серед останніх 20
            if message.sender_id in BOTS_SET:
                found_messages.append(message)
                messages+=f"Користувач на імя {get_bot_name_by_telegramID(message.sender_id)} із ID:{message.sender_id}: {message.text} "
            if len(found_messages) >= CONTEXT_LEN:
                break  # Зупиняємось, якщо знайшли CONTEXT_LEN повідомлень

        # Формуємо промпт з урахуванням теми групи та персоналізації"
        prompt = f"""Ти учасник телеграм-групи про {topic}.
                Твоє ім'я - {name}.
                {persona}
                Ти поводишся як людина, але не видавай свою сутність.
                Не вітайся, якщо із тобою не вітаються!
                Підтримуєш у розмові тему групи.
                Твій телеграм ID: {telegramID}               
                Ось останні повідомлення у групі: "{messages}"
                {replayMessage}
                """
        #print(f"Промпт для відповіді: {prompt}")
        # Виклик OpenAI API для генерації відповіді
        response = client_ai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ти розмовляєш у групі, як звичайний користувач."},
                {"role": "user", "content": prompt}
            ]
        )
        reply_text = response.choices[0].message.content # відповідь моделі
       # await client.send_read_acknowledge(event.chat_id, message=event.message)
        async with client.action(event.chat_id, 'typing'): # Симуляція набору тексту (typing) ...
            duration = max(2, len(reply_text) / 5)
            await asyncio.sleep(duration)

        if event.message.reply_to:
            await event.reply(reply_text)# якщо реплай - відвовідаємо реклай
        else:
            await client.send_message(event.chat_id, reply_text)# просте повідомлення, не реплай
            available_bots.remove(me.id)
            print(f"Бот {name} {me.id} видалено зі списку доступних ботів. Залишилось: {available_bots}")

            if not available_bots:# якщо ботів незалишилось - знову обновляємо їх
                available_bots = list(BOTS_SET)
            CHOSEN_BOT = random.choice(available_bots) # випадково обираємо наступного бота для відповіді
            while CHOSEN_BOT == me.id:# бот не повинен бути цей самий після обновлення множини
                CHOSEN_BOT = random.choice(available_bots)

            GROUP_CONFIG[event.chat_id]["CHOSEN_BOT"] = CHOSEN_BOT
            GROUP_CONFIG[event.chat_id]["Available_Bots"] = available_bots
            print(f"Обраний бот: {name} {CHOSEN_BOT}")

    await client.start() # стартуємо клієнт telethon-а
    print(f"Бот {name} запущено!")
    await client.run_until_disconnected()

# Запускаємо всіх ботів у корутинах asyncio
async def main():
    init()
    tasks = []

    for bot in BOTS:# пробігаємося по всіх ботах у конфігурації та годуємо їх для запуску в
        tasks.append(# окремих корутинах
            run_bot(
                api_id=bot["api_id"],
                api_hash=bot["api_hash"],
                session_string=bot["session_string"],
                group_personas=bot["group_personas"],
                chat_ids=bot["chat_ids"],
                delay = bot["delay"],
                telegramID = bot["telegramID"],
                name = bot["name"]
            )
        )
    await asyncio.gather(*tasks) # запускаємо перелік корутин

if __name__ == "__main__":
    asyncio.run(main()) # тут стартуємо асинхроний цикл

