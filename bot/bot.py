# bot.py：washwatch 的 Discord bot
#
# 它是另一種「前端」：跟 v2 網頁一樣，只負責 call 我們的 API server，把結果給人看。
#
# 跑起來（server 要先開著）：
#   cd bot
#   python bot.py

from typing import Literal

import discord
import requests
from discord.ext import commands
from dotenv import dotenv_values

config = dotenv_values('.env')  # 讀取 .env（要在 bot/ 資料夾裡執行）
BOT_TOKEN = config.get('BOT_TOKEN')
TEST_GUILD_ID = config.get('TEST_GUILD_ID')

API_URL = 'http://localhost:3000'

""" Parameters """
# True：區域註冊，指令只註冊到 TEST_GUILD_ID 這個伺服器，馬上生效（開發測試用）
# False：全域註冊，bot 加入的每個伺服器都能用，但可能要等一段時間才會出現
use_local = True

bot = commands.Bot(command_prefix='!', intents=discord.Intents.default())


@bot.event
async def on_ready():
    # 註冊指令：告訴 Discord 這個 bot 有哪些指令
    if use_local:
        local_guild = discord.Object(id=int(TEST_GUILD_ID))
        bot.tree.copy_global_to(guild=local_guild)  # 把所有指令複製一份到測試伺服器
        synced = await bot.tree.sync(guild=local_guild)
    else:
        synced = await bot.tree.sync()
    print(f'Logged in as {bot.user}, synced {len(synced)} commands {"locally" if use_local else "globally"}')


@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error):
    # 指令出錯時（例如 server 沒開），在 Discord 裡告訴使用者
    error = getattr(error, 'original', error)
    if isinstance(error, requests.ConnectionError):
        print(f"Can't reach {API_URL}. Is the server running?")
        msg = f'連不上 {API_URL}，server 有開嗎？'
    else:
        print(f'Command error: {error!r}')
        msg = f'Error: {error}'
    if interaction.response.is_done():
        await interaction.followup.send(msg)
    else:
        await interaction.response.send_message(msg)


# ===== 指令寫在這下面 =====


@bot.tree.command(name='ping')
async def ping(interaction: discord.Interaction):
    """To test if the bot is alive"""
    await interaction.response.send_message('pong!')


# 在這裡加上 /laundry、/report


if __name__ == '__main__':
    if not BOT_TOKEN or (use_local and not TEST_GUILD_ID):
        raise SystemExit('找不到 BOT_TOKEN 或 TEST_GUILD_ID：.env 設定好了嗎？是在 bot/ 資料夾裡執行的嗎？')
    bot.run(BOT_TOKEN)
