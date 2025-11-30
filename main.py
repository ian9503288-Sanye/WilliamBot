import discord
from discord.ext import commands
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import yt_dlp
import asyncio
import os # 務必確認有這一行
import sys
from keep_alive import keep_alive

# ==========================================
#  雲端版設定：改用 os.getenv 讀取密碼
# ==========================================
# 這樣做，我們就不會把密碼直接暴露在程式碼裡
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 讀取 ID，如果讀不到預設為 0 (避免報錯)
try:
    MASTER_ID = int(os.getenv("MASTER_ID"))
except:
    MASTER_ID = 0
# ==========================================

# ... (下面的程式碼完全不用動) ...

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
7. 關機/休息 -> CMD:SHUTDOWN

範例：
使用者：「威廉，你可以去休息了。」
你回：「遵命，少爺。祝您有個美好的夜晚，威廉先行告退。\nCMD:SHUTDOWN」
"""

model = genai.GenerativeModel('gemini-flash-latest', system_instruction=system_instruction)

safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

chat_sessions = {}
yt_dlp_opts = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True}
ffmpeg_opts = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

@bot.event
async def on_ready():
    print(f'威廉管家 (含關機功能) 已上線')

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if message.content.startswith('!'): await bot.process_commands(message); return

    # ==========================================
    # ★★★ 只認 Tag (無視空格版) ★★★
    # ==========================================
    # 只要訊息裡有藍色的 @威廉管家，就會觸發
    if bot.user.mentioned_in(message):
        
        # 1. 判斷身分
        user_identity = "少爺 (Master)" if message.author.id == MASTER_ID else "貴賓 (VIP)"
        
        # 2. 【關鍵處理】把 Tag 變成的亂碼拿掉
        # Discord 的 Tag 其實是一串像 <@123456789> 的字串
        # 我們把它刪掉，剩下的就是你打的內容
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        # 如果因為黏太緊，導致還有殘留的符號 (針對手機版或特殊狀況的防呆)
        if clean_content.startswith('>'): 
             clean_content = clean_content[1:].strip()

        # 如果只 Tag 沒講話
        if not clean_content: clean_content = "你好"

        # 3. 讀取歷史
        history_log = []
        async for msg in message.channel.history(limit=10, before=message):
            if msg.author == bot.user: continue
            role = "少爺" if msg.author.id == MASTER_ID else "貴賓"
            history_log.append(f"[{role}]: {msg.content}")
        history_text = "\n".join(history_log[::-1])

        # 4. 組合提示詞
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

                    if "|" in command_content: action, value = command_content.split("|", 1)
                    else: action, value = command_content, None

                    # --- 執行動作 ---
                    if action == "PLAY":
                        if not message.author.voice:
                            await message.channel.send("威廉：請先加入語音頻道。")
                        else:
                            vc = message.guild.voice_client
                            if not vc: 
                                await message.author.voice.channel.connect()
                                vc = message.guild.voice_client
                            vc.stop()
                            if not chat_content: await message.channel.send(f"搜尋中：{value}")
                            try:
                                with yt_dlp.YoutubeDL(yt_dlp_opts) as ydl:
                                    info = ydl.extract_info(f"ytsearch:{value}", download=False)['entries'][0]
                                    source = discord.FFmpegPCMAudio(info['url'], executable='ffmpeg.exe', **ffmpeg_opts)
                                    vc.play(source)
                                    await message.channel.send(f"🎵 播放：**{info['title']}**")
                            except Exception as e: await message.channel.send(f"播放失敗：{e}")

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
                        if message.author.id == MASTER_ID:
                            await bot.close()
                            sys.exit()
                        else:
                            await message.channel.send("威廉：權限不足。")
                    else:
                        await message.channel.send(f"(未知指令：{action})")
                else:
                    await message.channel.send(reply_text)

            except Exception as e:
                print(f"Error: {e}")

# 傳統指令區
@bot.command()
async def join(ctx):
    if ctx.author.voice: await ctx.author.voice.channel.connect()
@bot.command()
async def leave(ctx):
    if ctx.voice_client: await ctx.voice_client.disconnect()

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)