import eventlet
eventlet.monkey_patch()
from flask import Flask, request, send_from_directory
from flask_socketio import SocketIO, emit
import os, uuid, subprocess, shutil
import random


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'generated'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")

# Track portfolios: {sid: {AAPL: qty, TSLA: qty}}
user_portfolios = {}

@app.route("/")
def serve_html():
    return send_from_directory("static", "client.html")

@socketio.on('generate_exe')
def generate(data):
    code = data.get("code", "")
    if not code:
        emit("error", {"error": "No code provided"})
        return

    file_id = uuid.uuid4().hex[:6]
    filename = f"script_{file_id}.py"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    with open(filepath, "w") as f:
        f.write(code)

    emit("status", {"message": "Saved. Compiling..."})

    try:
        for d in ['build', 'dist']: shutil.rmtree(d, ignore_errors=True)
        spec_file = filename.replace(".py", ".spec")
        if os.path.exists(spec_file): os.remove(spec_file)
        
        # subprocess.run(['pyinstaller', '--onefile', filepath], check=True)

        exe_name = filename.replace('.py', '.exe')
        exe_path = os.path.join('dist', exe_name)
        if os.path.exists(exe_path):
            emit("completed", {"exe": exe_name})
        else:
            emit("error", {"error": "File is saved but can't show exe as this is deployed on linux. Windows video demo: https://drive.google.com/file/d/1FXnUqCu_Jk8TaY4YcqIZZf7ZkPZnxj9S/view?usp=sharing"})
    except Exception as e:
        emit("error", {"error": str(e)})

@socketio.on("add_to_portfolio")
def handle_portfolio_add(data):
    sid = request.sid
    stock = data.get("stock")
    quantity = int(data.get("quantity", 0))

    if not stock or quantity <= 0:
        return

    if sid not in user_portfolios:
        user_portfolios[sid] = {}

    user_portfolios[sid][stock] = quantity

    emit("logs", {
        "stock": stock,
        "message": f"🟢 Bought {stock} -> {quantity}"
    }, to=sid)

    def send_price_loop(symbol):
        while sid in user_portfolios and symbol in user_portfolios[sid]:
            price = round(random.uniform(100, 500), 2)
            quantity = user_portfolios[sid][symbol]
            value = round(price * quantity, 2)

            socketio.emit("portfolio_update", {
                "stock": symbol,
                "price": price,
                "quantity": quantity,
                "value": value
            }, to=sid)

            socketio.sleep(1)

    socketio.start_background_task(send_price_loop, stock)

@socketio.on("del_from_portfolio")
def handle_portfolio_del(data):
    sid = request.sid
    stock = data.get("stock")
    quantity = int(data.get("quantity", 0))

    if sid not in user_portfolios or stock not in user_portfolios[sid]:
        return
    
    if quantity >= user_portfolios[sid][stock]:
        user_portfolios[sid].pop(stock)
        socketio.emit("stock_removed", {"stock": stock}, to=sid)
        # user_portfolios[sid][stock] = 0
    else:
        prev_quan = user_portfolios[sid][stock]
        user_portfolios[sid][stock] = prev_quan - quantity

    emit("logs", {
        "stock": stock,
        "message": f"🔴 Sold {stock} -> {quantity}"
    }, to=sid)


@socketio.on("disconnect")
def on_disconnect():
    user_portfolios.pop(request.sid, None)

@app.route('/download/<exe_name>')
def download(exe_name):
    return send_from_directory("dist", exe_name, as_attachment=True)

if __name__ == "__main__":
    print("Starting Flask-SocketIO server...")
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="localhost", port=port, debug=False)
