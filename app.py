from iqoptionapi.stable_api import IQ_Option
import time, datetime, csv, threading, os
import pandas as pd
import numpy as np
import requests

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier
from flask import Flask, render_template_string

# ================== VARIÁVEIS (NUVEM) ==================
EMAIL = os.environ.get("ruberinocarvalho122@gmail.com")
SENHA = os.environ.get("Algoritimo1#")

TELEGRAM_TOKEN = os.environ.get("8599420806:AAF_i6jqAMNEomqiBJdj84Z0zShJCMJW7-")
TELEGRAM_CHAT_ID = os.environ.get("6063654967")

# ================== CONFIG ==================
ATIVOS = ["EURUSD","GBPUSD","USDJPY"]
COOLDOWN = 60

lucro = 0
wins = 0
loss = 0
trades = 0
ultimo_trade = {}

modelo = RandomForestClassifier(n_estimators=100)

# ================== CSV ==================
if not os.path.exists("database_trades.csv"):
    open("database_trades.csv","w").close()

# ================== FUNÇÕES ==================

def enviar(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        )
    except:
        pass

def ema(data,p):
    return pd.Series(data).ewm(span=p).mean().iloc[-1]

def rsi(data,p=7):
    delta = np.diff(data)
    gain = (delta>0)*delta
    loss = (delta<0)*-delta
    ag = np.mean(gain[-p:])
    al = np.mean(loss[-p:])
    if al == 0: return 100
    return 100 - (100/(1+(ag/al)))

# ================== IA ==================

def treinar():
    try:
        df = pd.read_csv("database_trades.csv",
        names=["data","ativo","direcao","resultado","rsi","tendencia"])

        if len(df) < 30:
            return None

        df["t"] = df["tendencia"].map({"alta":1,"baixa":0})

        X = df[["rsi","t"]]
        y = (df["resultado"] > 0).astype(int)

        modelo.fit(X,y)
        return modelo
    except:
        return None

def prever(modelo, rsi_val, tendencia):
    try:
        t = 1 if tendencia=="alta" else 0
        return modelo.predict_proba([[rsi_val,t]])[0][1]
    except:
        return 0

# ================== BOT ==================

def bot():
    global lucro,wins,loss,trades

    api = IQ_Option(EMAIL,SENHA)
    status,_ = api.connect()

    if not status:
        print("Erro login")
        return

    print("🤖 Rodando na nuvem...")

    while True:
        modelo_t = treinar()

        for ativo in ATIVOS:
            try:
                if time.time() - ultimo_trade.get(ativo,0) < COOLDOWN:
                    continue

                velas = api.get_candles(ativo,60,100,time.time())
                closes = np.array([v['close'] for v in velas])

                ema50 = ema(closes,50)
                ema200 = ema(closes,200)
                r = rsi(closes)

                tendencia = "alta" if ema50>ema200 else "baixa"

                if modelo_t:
                    if prever(modelo_t,r,tendencia) < 0.6:
                        continue

                direcao = "call" if tendencia=="alta" else "put"

                valor = api.get_balance()*0.01
                ok,id = api.buy(valor,ativo,direcao,1)

                if ok:
                    win,res = api.check_win_v3(id)

                    lucro += res
                    trades += 1
                    ultimo_trade[ativo] = time.time()

                    if res>0:
                        wins+=1
                        enviar(f"✅ WIN {ativo} +{res:.2f}")
                    else:
                        loss+=1
                        enviar(f"❌ LOSS {ativo} {res:.2f}")

                    with open("database_trades.csv","a",newline="") as f:
                        csv.writer(f).writerow([
                            datetime.datetime.now(),
                            ativo,direcao,res,r,tendencia
                        ])
            except:
                continue

        time.sleep(2)

# ================== WEB ==================

app = Flask(__name__)

HTML = """
<html>
<body style="background:black;color:lime">
<h1>🤖 LUIZA CORP CLOUD</h1>
<p>Lucro: {{lucro}}</p>
<p>Trades: {{trades}}</p>
<p>Winrate: {{winrate}}%</p>
<img src="/plot.png">
<pre>{{tabela}}</pre>
</body>
</html>
"""

@app.route("/")
def home():
    try:
        df = pd.read_csv("database_trades.csv",
        names=["data","ativo","direcao","resultado","rsi","tendencia"])

        lucro = round(df["resultado"].sum(),2)
        trades = len(df)
        winrate = round((len(df[df["resultado"]>0])/trades)*100,1) if trades>0 else 0

        tabela = df.tail(10).to_string()
    except:
        lucro,trades,winrate,tabela = 0,0,0,"Sem dados"

    return render_template_string(HTML,
        lucro=lucro,trades=trades,winrate=winrate,tabela=tabela)

@app.route("/plot.png")
def plot():
    try:
        df = pd.read_csv("database_trades.csv",
        names=["data","ativo","direcao","resultado","rsi","tendencia"])

        if len(df)==0:
            return "",200

        df["eq"]=df["resultado"].cumsum()

        plt.figure(figsize=(8,4))
        plt.plot(df["eq"])
        plt.savefig("plot.png")
        plt.close()

        with open("plot.png","rb") as f:
            return f.read(),200,{'Content-Type':'image/png'}
    except:
        return "",200

# ================== RUN ==================

if __name__ == "__main__":
    threading.Thread(target=bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
