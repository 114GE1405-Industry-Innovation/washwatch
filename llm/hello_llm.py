# hello_llm.py：第一次 call LLM
#
# LLM 就是一個 API：送一段文字過去，它回一段文字。
#
# 跑起來：
#   cd llm
#   python hello_llm.py

from dotenv import dotenv_values
from google import genai
from google.genai import types

config = dotenv_values('.env')  # 讀取 .env（要在 llm/ 資料夾裡執行）
GEMINI_API_KEY = config.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise SystemExit('找不到 GEMINI_API_KEY：.env 設定好了嗎？是在 llm/ 資料夾裡執行的嗎？')
# Gemini 常常回 503（太忙）或 429（太多次），讓 SDK 自動重試：最多 5 次，間隔越來越長，最多等 10 秒
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=5, max_delay=10)),
)

# 模型名稱會隨時間下架或改名，遇到 404 就到 Google AI Studio 看現在可用的模型
MODEL = 'gemini-3.5-flash-lite'

if __name__ == '__main__':
    while True:
        question = input('User: ')
        if question == '':
            break  # 直接按 Enter 結束

        # 每一次都是一個獨立的 request: 只送這一句話過去
        try:
            response = client.models.generate_content(model=MODEL, contents=question)
            print('LLM: ', response.text)
        except Exception as e:
            print('（呼叫 Gemini 失敗：', e, '）')  # 重試完還是失敗，印出原因，不要讓程式掛掉
        print()
