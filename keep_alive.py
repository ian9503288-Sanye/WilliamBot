from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "I'm alive! 威廉管家正在工作中。"

def run():
    # 設定 port 為 8080 或 Render 指定的 port
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()