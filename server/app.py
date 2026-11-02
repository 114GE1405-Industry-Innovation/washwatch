# app.py：我們的 API server
#
# 跑起來：python app.py
# 然後打開：
#   http://localhost:3000/status          -> 全部機台
#   http://localhost:3000/status/<mac>    -> 單台
#   http://localhost:3000/docs            -> 自動產生的 API 文件

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import wipepay

app = FastAPI(title='washwatch')

# 讓直接用檔案打開的 HTML（v2）也能呼叫這個 server
app.add_middleware(CORSMiddleware, allow_origins=['*'])


@app.exception_handler(ConnectionError)
def wipepay_down(request, exc):
    return JSONResponse({'error': str(exc)}, status_code=502)


@app.get('/status')
def all_status():
    return wipepay.get_status()


@app.get('/status/{mac}')
def one_status(mac: str):
    return wipepay.get_status([mac.lower()])


if __name__ == '__main__':
    uvicorn.run(app, port=3000)
