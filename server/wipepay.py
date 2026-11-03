# wipepay.py：助教給的程式，當黑盒子用就好
#
# 你只需要知道一件事：
#   get_status()          -> 全部機台的狀態
#   get_status([mac, ...]) -> 指定機台的狀態
#
# 背景：洗衣機是 Queen Laundry 的，IoT 由捷奏數科（Beat Digital Solutions）負責，
# wipepay.com.tw 是他們的付款網站兼 MQTT server。
#
# 內部做的事（有興趣再看）：
# 第一次呼叫時，在背景跟 wipepay 的 MQTT broker 開一條長連線，訂閱下面 MACHINES 的 status topic，
# 之後每收到一筆就更新記憶體裡的最新狀態，供 get_status() 使用。
# 這樣不管多少人在問我們的 server，對 wipepay 來說都只是一個人開著官方頁面而已。
# 斷線時 paho 會自己重連；topic 是 retained 的，重新訂閱就會馬上補到最新一筆。

import json
import threading
import time

import paho.mqtt.client as mqtt

BROKER_HOST = 'wipepay.com.tw'
BROKER_PORT = 443
BROKER_PATH = '/mqtt/'

CONNECT_TIMEOUT_S = 5
# 連上後最多等多久的 retained 訊息（官方頁面設 2 秒）；從沒上線過的機器根本不會有 retained 訊息，只能等逾時
RETAINED_TIMEOUT_S = 2
# 官方 heartbeat.timeout：運轉中超過這麼久沒心跳就當作離線
HEARTBEAT_TIMEOUT_S = 15
ALMOST_DONE_S = 300

# mac -> (名稱, 種類)
MACHINES = {
    '94c96001b3e3': ('仁齋男洗1', 'washer'),
    '94c96001b3f4': ('仁齋男洗2', 'washer'),
    '94c96001b3f6': ('仁齋男洗3', 'washer'),
    '94c96001b3f5': ('仁齋男洗4', 'washer'),
    '94c96001b3ce': ('實齋男洗1', 'washer'),
    '94c96001b3c9': ('實齋男洗2', 'washer'),
    '94c96001b3c2': ('實齋男洗3', 'washer'),
    '94c96001b3cc': ('實齋男洗4', 'washer'),
    '94c96001b39f': ('實齋男烘1', 'dryer'),
    '94c96001b396': ('實齋男烘2', 'dryer'),
    '94c96001b38b': ('實齋男烘3', 'dryer'),
}

# 主狀態碼（status 的高位元組），對照官方頁面的 machine.statuses
STATUS_KEYS = {
    -1: 'timeout',
    0: 'none',
    1: 'free',
    2: 'waitingForPayment',
    4: 'waitingForOperation',
    5: 'waitingForOperationPf',
    8: 'running',
    9: 'doorLocking',
    10: 'doorUnlocking',
    11: 'paused',
    12: 'done',
    128: 'error',
}
FREE_CODES = {0, 1, 2, 12}
BUSY_CODES = {4, 5, 8, 9, 10, 11}


def get_status(macs=None):
    """抓機台狀態。macs 不給就抓全部。

    回傳：
    {
      "queriedAt": 1791889679.3,
      "free": 3, "total": 11,
      "machines": [
        {"mac": "...", "name": "仁齋男洗1", "type": "washer",
         "state": "free" | "busy" | "almost" | "offline",
         "timeLeft": 秒, ...},
        ...
      ]
    }
    連不上 wipepay 會丟 ConnectionError。
    """
    macs = list(MACHINES) if macs is None else macs
    heartbeats = _latest_heartbeats()
    now = time.time()
    machines = [_describe(mac, heartbeats.get(mac), now) for mac in macs]
    return {
        'queriedAt': now,
        'free': sum(m['state'] == 'free' for m in machines),
        'total': len(machines),
        'machines': machines,
    }


def _status_main(code):
    # 16-bit 混合碼：高位元組＝主狀態、低位元組＝子狀態；watchdog 發的 -1 不做位移
    return code if code < 0 else (code >> 8) & 0xFF


# ---- 背景長連線 ----
# 只訂閱 MACHINES 裡的機台：外面傳進來的 mac 不會讓我們去訂閱任意 topic

_heartbeats = {}                 # mac -> 最新一筆 status payload
_lock = threading.Lock()
_connected = threading.Event()   # 目前有連著
_ready = threading.Event()       # 第一批 retained 收齊（或等過 RETAINED_TIMEOUT_S）
_client = None
_start_lock = threading.Lock()


def _on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        return
    client.subscribe([(f'machine/{mac}/status/#', 0) for mac in MACHINES])
    _connected.set()
    # 從沒上線過的機器不會有 retained 訊息，所以最多等這麼久就當作收齊
    timer = threading.Timer(RETAINED_TIMEOUT_S, _ready.set)
    timer.daemon = True
    timer.start()


def _on_disconnect(client, userdata, flags, reason_code, properties):
    _connected.clear()


def _on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode('utf-8'))
    except ValueError:
        return
    if data.get('type') != 'status' or data.get('mac') not in MACHINES:
        return
    with _lock:
        prev = _heartbeats.get(data['mac'])
        if prev is None or data.get('ts', 0) >= prev.get('ts', 0):
            _heartbeats[data['mac']] = data
        if len(_heartbeats) == len(MACHINES):
            _ready.set()


def _start():
    """整個程式只開一次連線；之後重連交給 paho。"""
    global _client
    with _start_lock:
        if _client is not None:
            return
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport='websockets')
        client.ws_set_options(path=BROKER_PATH)
        client.tls_set()
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect
        client.on_message = _on_message
        client.connect_async(BROKER_HOST, BROKER_PORT)
        client.loop_start()
        _client = client


def _latest_heartbeats():
    """回傳記憶體裡的最新狀態 {mac: payload}；第一次呼叫會等連線和第一批資料。"""
    _start()
    if not _connected.wait(CONNECT_TIMEOUT_S):
        raise ConnectionError('連不上 wipepay MQTT broker')
    _ready.wait(RETAINED_TIMEOUT_S)
    with _lock:
        return dict(_heartbeats)


def _describe(mac, hb, now):
    """把原始心跳轉成好用的格式。state: free | busy | almost | offline"""
    name, kind = MACHINES.get(mac, (mac, None))
    result = {
        'mac': mac,
        'name': name,
        'type': kind,
        'url': f'https://wipepay.com.tw/v2/machine/{mac}/',
        'state': 'offline',
        'key': None,
        'code': None,
        'timeLeft': 0,
        'totalTime': None,
        'lastHeartbeat': None,
    }
    if hb is None:
        return result

    code = int(hb.get('status', 0))
    main = _status_main(code)
    ts = hb.get('ts', 0)
    time_left = hb.get('timeLeft') or 0
    result.update({
        'key': STATUS_KEYS.get(main, 'unknown'),
        'code': code,
        'totalTime': hb.get('totalTime'),
        'lastHeartbeat': ts,
    })

    if main == 8:
        if now - ts > HEARTBEAT_TIMEOUT_S:
            return result  # 運轉中卻斷了心跳 -> offline
        # 只有運轉中才扣掉從心跳到現在過了多久
        time_left = max(0, time_left - (now - ts))
        if time_left < 1:
            result.update(state='free', key='done')  # 官方邏輯：倒數到 0 就視為完成
            return result
    elif main not in BUSY_CODES:
        time_left = 0

    if main in BUSY_CODES:
        state = 'almost' if 0 < time_left <= ALMOST_DONE_S else 'busy'
    elif main in FREE_CODES:
        state = 'free'
    else:
        state = 'offline'  # timeout、error、unknown

    result.update(state=state, timeLeft=int(time_left))
    return result
