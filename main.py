import discord
from discord.ext import commands
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import yt_dlp
import asyncio
import os
import sys
import aiohttp
import io
from keep_alive import keep_alive # 引入心跳機

# ==========================================
#  雲端版設定：從 Render 環境變數讀取
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

try:
    MASTER_ID = int(os.getenv("MASTER_ID"))
except:
    MASTER_ID = 0
# ==========================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

genai.configure(api_key=GOOGLE_API_KEY)

system_instruction = """
你現在是 Discord 伺服器裡的「威廉管家」。
請用優雅、恭敬且帶點英式幽默的口吻對話。

【指令規則】
當需要執行動作時，請在回覆的「最後一行」附上指令代碼：
1. 播放音樂 -> CMD:PLAY|關鍵字
2. 建立文字頻道 -> CMD:NEW_TEXT|名稱
3. 建立語音頻道 -> CMD:NEW_VOICE|名稱
4. 刪除本頻道 -> CMD:DELETE_THIS
5. 清除訊息 -> CMD:CLEAN|數量
6. 踢出成員 -> CMD:KICK|成員名
7. 關機 -> CMD:SHUTDOWN
8. 繪圖 -> CMD:IMAGE|畫面描述英文Prompt
9. 提醒/計時 -> CMD:REMIND|秒數|提醒內容

範例：
使用者：「畫一隻貓。」
你回：「遵命，少爺。\nCMD:IMAGE|A cute cat, high quality」
"""

model = genai.GenerativeModel('gemini-flash-latest', system_instruction=system_instruction)

safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

chat_sessions = {}
# 音樂設定 (雖然雲端跑不動，但程式碼留著以免報錯)
yt_dlp_opts = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True}
ffmpeg_opts = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

async def start_reminder(channel, seconds, content):
    await asyncio.sleep(seconds)
    await channel.send(f"⏰ **威廉提醒**：{content}")

@bot.event
async def on_ready():
    print(f'威廉管家 (雲端繪圖版) 已上線')

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if message.content.startswith('!'): await bot.process_commands(message); return

    if bot.user.mentioned_in(message):
        user_identity = "少爺 (Master)" if message.author.id == MASTER_ID else "貴賓 (VIP)"
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not clean_content: clean_content = "你好"

        history_log = []
        async for msg in message.channel.history(limit=10, before=message):
            if msg.author == bot.user: continue
            role = "少爺" if msg.author.id == MASTER_ID else "貴賓"
            history_log.append(f"[{role}]: {msg.content}")
        history_text = "\n".join(history_log[::-1])

        final_prompt = f"""
        [歷史紀錄]
        {history_text}
        [當前發話]
        身分：{user_identity}
        內容：{clean_content}
        (請自然回應，若需執行指令請放在最後一行)
        """

        channel_id = message.channel.id
        if channel_id not in chat_sessions:
            chat_sessions[channel_id] = model.start_chat(history=[])
        chat_session = chat_sessions[channel_id]

        async with message.channel.typing():
            try:
                response = await chat_session.send_message_async(final_prompt, safety_settings=safety_settings)
                reply_text = response.text.strip()

                if "CMD:" in reply_text:
                    parts = reply_text.split("CMD:")
                    chat_content = parts[0].strip()
                    command_content = parts[1].strip().split('\n')[0]

                    if chat_content: await message.channel.send(chat_content)

                    if "|" in command_content: 
                        cmd_parts = command_content.split("|")
                        action = cmd_parts[0]
                        value = cmd_parts[1]
                        extra_value = cmd_parts[2] if len(cmd_parts) > 2 else None
                    else:
                        action, value, extra_value = command_content, None, None

                    if action == "PLAY":
                         await message.channel.send("威廉：抱歉，雲端模式無法支援音樂播放，請少爺改用本機模式。")
                    elif action == "IMAGE":
                        prompt = value.replace(" ", "%20")
                        image_url = f"https://image.pollinations.ai/prompt/{prompt}"
                        async with aiohttp.ClientSession() as session:
                            async with session.get(image_url) as resp:
                                if resp.status == 200:
                                    data = io.BytesIO(await resp.read())
                                    await message.channel.send(file=discord.File(data, 'generated.png'))
                                else:
                                    await message.channel.send("威廉：作畫失敗。")
                    elif action == "REMIND":
                        try:
                            bot.loop.create_task(start_reminder(message.channel, int(value), extra_value if extra_value else "時間到"))
                        except: await message.channel.send("時間格式錯誤")
                    elif action == "NEW_TEXT": await message.guild.create_text_channel(value); await message.channel.send(f"已建立：{value}")
                    elif action == "NEW_VOICE": await message.guild.create_voice_channel(value); await message.channel.send(f"已建立：{value}")
                    elif action == "DELETE_THIS": await message.channel.send("銷毀中..."); await asyncio.sleep(3); await message.channel.delete()
                    elif action == "CLEAN": 
                        try: await message.channel.purge(limit=int(value)+1); await message.channel.send(f"已清理 {value} 則訊息", delete_after=3)
                        except: pass
                    elif action == "KICK":
                        mem = discord.utils.find(lambda m: value in m.name, message.guild.members)
                        if mem: await mem.kick(); await message.channel.send(f"已踢出 {mem.name}")
                        else: await message.channel.send("找不到成員")
                    elif action == "SHUTDOWN":
                         # 雲端版不建議用 shutdown，因為會導致 Render 報錯重啟，所以我們只回話
                         await message.channel.send("威廉：雲端模式下，我必須保持清醒為您服務。")
                    else:
                        await message.channel.send(f"(未知指令：{action})")
                else:
                    await message.channel.send(reply_text)

            except Exception as e:
                print(f"Error: {e}")

@bot.command()
async def join(ctx): pass # 雲端版停用
@bot.command()
async def leave(ctx): pass # 雲端版停用

if __name__ == "__main__":
    keep_alive() # 啟動心跳機
    bot.run(DISCORD_TOKEN)