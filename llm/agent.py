# agent.py：一個最小的 agent
#
# LLM 只會生文字，它自己不會上網、不會 call API。
# 這支程式就是 harness（馬具），幫 LLM 做到它做不到的事：
#   1. 告訴 LLM 有哪些工具可以用（寫在 SYSTEM_PROMPT 裡）
#   2. LLM 回「我要用某個工具」，harness 就真的去執行，再把結果貼回去
#   3. 一直重複，直到 LLM 說出最後的答案
#   4. 會改東西的工具，先問人可不可以
#   5. LLM 亂回、API 出錯，都不能讓整支程式掛掉
#
# 跑起來（server 要先開著，而且要有 GET /free、POST /reports）：
#   cd llm
#   python agent.py

import inspect
import json
from typing import Literal

import requests
from dotenv import dotenv_values
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

config = dotenv_values('.env')
GEMINI_API_KEY = config.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise SystemExit('找不到 GEMINI_API_KEY：.env 設定好了嗎？是在 llm/ 資料夾裡執行的嗎？')
# Gemini 常常回 503（太忙）或 429（太多次），讓 SDK 自動重試：最多 5 次，間隔越來越長，最多等 10 秒
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=5, max_delay=10)),
)
MODEL = 'gemini-3.5-flash-lite'

API_URL = 'http://localhost:3000'
MAX_STEPS = 10  # 最多讓 LLM 用幾次工具，避免它無限繞圈


# ===== 工具：其實就是普通的 Python 函式，裡面 call 我們自己的 API =====
# raise_for_status()：server 回 404、500 這類錯誤時丟出例外，不要當成正常結果

def get_status():
    response = requests.get(f'{API_URL}/status', timeout=10)
    response.raise_for_status()
    return response.json()


def get_free(type=None):
    response = requests.get(f'{API_URL}/free', params={'type': type}, timeout=10)
    response.raise_for_status()
    return response.json()


def add_report(mac, note):
    response = requests.post(f'{API_URL}/reports', json={'mac': mac, 'note': note}, timeout=10)
    response.raise_for_status()
    return response.json()


TOOLS = {
    'get_status': get_status,
    'get_free': get_free,
    'add_report': add_report,
}
NEED_APPROVAL = {'add_report'}  # 會改到東西的工具，執行前要先問人


# ===== 跟 LLM 的約定：它每次都要照這個格式回答 =====
# 這個 class 會變成 JSON schema 交給 Gemini，Gemini 只能生出符合格式的 JSON。
# 欄位名稱跟工具函式的參數名稱一樣，harness 才知道要把哪個欄位傳給哪個參數。

class Reply(BaseModel):
    action: Literal['get_status', 'get_free', 'add_report', 'answer']
    type: Literal['washer', 'dryer'] | None = None  # get_free 用
    mac: str | None = None                          # add_report 用
    note: str | None = None                         # add_report 用
    answer: str | None = None                       # action 是 answer 時，給使用者的回答


SYSTEM_PROMPT = """
你是宿舍洗衣機小幫手，用繁體中文回答。

你可以使用這些工具（action 填工具名稱，需要的參數填在同名欄位）：
- get_status：全部機台的狀態。每台有 mac、name、type（washer/dryer）、
  state（free/busy/almost/offline）、timeLeft（剩幾秒）
- get_free：可用的機台。可以填 type（washer 或 dryer），不填就是全部
- add_report：回報某台機器故障。要填 mac 和 note。要用 mac，不是名稱

可以回答使用者了，就把 action 設成 answer，回答寫在 answer 欄位。

用了工具之後，你會收到工具的結果，看完再決定下一步。
工具回傳 error 時，照實告訴使用者錯誤內容，不要自己編原因。
不知道的事情就去查，不要猜。
"""


def message(role, text):
    # role 是 'user'（我們這邊）或 'model'（LLM 那邊）
    return {'role': role, 'parts': [{'text': text}]}


def ask_llm(history):
    response = client.models.generate_content(
        model=MODEL,
        contents=history,  # 每次都把「整段對話」重新送過去，LLM 自己不會記得
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type='application/json',
            response_schema=Reply,  # 只能照 Reply 的格式回答
        ),
    )
    return response.text or ''


def run_tool(reply):
    name = reply.action
    func = TOOLS[name]
    # 這個函式要哪些參數，就從 reply 拿同名的欄位
    args = {param: getattr(reply, param) for param in inspect.signature(func).parameters}

    if name in NEED_APPROVAL:
        ok = input(f'  [harness] 允許執行 {name}({args}) 嗎？(y/n) ')
        if ok != 'y':
            return {'error': '使用者不允許'}
    try:
        return func(**args)
    except Exception as e:
        return {'error': str(e)}  # 出錯也告訴 LLM，讓它自己想辦法


def run(question, history):
    history.append(message('user', question))

    for step in range(MAX_STEPS):
        try:
            text = ask_llm(history)
        except Exception as e:
            return f'（呼叫 Gemini 失敗：{e}）'  # 重試 5 次還是失敗，例如今天的額度用完了

        history.append(message('model', text))

        # 有 schema 還是可能出錯（例如回應被截斷），檢查不過就請它重回，不要讓程式掛掉
        try:
            reply = Reply.model_validate_json(text)
        except ValidationError as e:
            print(f'  [harness] 第 {step + 1} 步，LLM 回的格式不對，請它重回')
            history.append(message('user', f'你的回答格式不對：{e}。請照格式重新回答。'))
            continue

        if reply.action == 'answer':
            return reply.answer or '（LLM 沒有給回答）'

        # LLM 想用工具：harness 幫它執行，再把結果貼回對話裡
        print(f'  [harness] 第 {step + 1} 步，LLM 想用 {reply.action}')
        result = run_tool(reply)
        result_text = json.dumps({'tool_result': result}, ensure_ascii=False, default=str)
        print(f'  [harness] 結果：{result_text[:80]}...')
        history.append(message('user', result_text))

    return f'（用了 {MAX_STEPS} 次工具還沒想出答案，先停下來）'


if __name__ == '__main__':
    history = []  # 整段對話，harness 幫 LLM 記著
    while True:
        question = input('User: ')
        if question == '':
            break
        print('Agent: ', run(question, history))
        print()
