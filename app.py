from flask import Flask, request, render_template, redirect, url_for, jsonify, session
from flask_socketio import join_room, leave_room, send, emit, SocketIO
import sqlite3
import os
import random
from string import ascii_uppercase

app = Flask(__name__)
app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app)

# Configurações do banco de dados
DATABASE = "messages.db"

# Variáveis globais
listaUsuarios = ["user1"]
listaSenhas = ["1234"]
rooms = {}

@app.route("/port")
def port():
    return render_template('port.html') 

# Inicializa o banco de dados
def init_db():
    if not os.path.exists(DATABASE):
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                receiver TEXT NOT NULL,
                content TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()

# Função para gerar códigos únicos
def generate_unique_code(length):
    while True:
        code = ''.join(random.choice(ascii_uppercase) for _ in range(length))
        if code not in rooms:
            return code

# Rota inicial
@app.route("/")
def home():
    return render_template("index.html")

# Rota para cadastro de usuários
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        if username not in listaUsuarios:
            listaUsuarios.append(username)
            listaSenhas.append(password)
            return redirect(url_for("selecionarChat"))
        else:
            return render_template("cadastro.html", usuario_valido=False)

    return render_template("cadastro.html", usuario_valido=True)

# Verificar se o nome de usuário já existe
@app.route('/verificar_usuario', methods=["POST"])
def verificar_usuario():
    nome_usuario = request.form.get('username')
    return jsonify({'disponivel': nome_usuario not in listaUsuarios})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        if username in listaUsuarios and listaSenhas[listaUsuarios.index(username)] == password:
            session["username"] = username  # Salva o nome na sessão
            return redirect(url_for("selecionarChat"))
        else:
            return render_template("login.html", usuario_valido=False)

    return render_template("login.html", usuario_valido=True)


@app.route('/validar_login', methods=["POST"])
def validar_login():
    username = request.form.get('username')
    password = request.form.get('password')

    if username in listaUsuarios:
        index = listaUsuarios.index(username)
        if listaSenhas[index] == password:
            return jsonify({'valido': True})
        return jsonify({'valido': False, 'erro': 'Senha inválida'})
    return jsonify({'valido': False, 'erro': 'Usuário não encontrado'})



@app.route("/selecionarChat", methods=["GET", "POST"])
def selecionarChat():
    return render_template("selecionarChat.html")


@app.route("/oldMessages", methods=["GET", "POST"])
def oldMessages():
    return render_template("oldMessages.html")

@app.route("/homeChat", methods=["GET", "POST"])
def homeChat():
    # Verifica se o nome já está salvo na sessão
    if "username" not in session:
        session["username"] = "Visitante"  # Nome padrão, se não houver login

    if request.method == "POST":
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        name = session["username"]  # Nome vem da sessão

        if join and not code:
            return render_template("home.html", error="Por favor, insira o código da sala.", code=code)

        if create:
            code = generate_unique_code(4)
            rooms[code] = {"members": 0, "messages": []}
        elif code not in rooms:
            return render_template("home.html", error="A sala não existe.", code=code)

        session["room"] = code
        session["name"] = name
        return redirect(url_for("roomChat"))

    return render_template("home.html", name=session["username"])

@app.route("/room")
def roomChat():
    room = session.get("room")
    if not room or session.get("name") is None or room not in rooms:
        return redirect(url_for("homeChat"))
    return render_template("room.html", code=room, messages=rooms[room]["messages"])

# Rota para envio de mensagens ao banco de dados
@app.route('/send_message', methods=['POST'])
def send_message():
    sender = request.form.get('sender')
    receiver = request.form.get('receiver')
    content = request.form.get('content')

    if sender and receiver and content:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (sender, receiver, content)
            VALUES (?, ?, ?)
        ''', (sender, receiver, content))
        conn.commit()
        conn.close()
        return redirect(url_for('search_messages', user=sender))  # Redireciona para busca de mensagens do remetente
    return "Erro: Todos os campos são obrigatórios."

# Rota para busca de mensagens
@app.route('/search_messages', methods=['GET'])
def search_messages():
    user = request.args.get('user')  # Obtém o nome do usuário do formulário de busca
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM messages
        WHERE sender = ? OR receiver = ?
        ORDER BY id DESC
    ''', (user, user))
    messages = cursor.fetchall()
    conn.close()
    return render_template('secondIndex.html', messages=messages, user=user)

# Eventos SocketIO para chat
@socketio.on("message")
def message(data):
    room = session.get("room")
    if room in rooms:
        content = {"name": session.get("name"), "message": data["data"]}
        rooms[room]["messages"].append(content)
        send(content, to=room)

@socketio.on("connect")
def connect():
    room = session.get("room")
    name = session.get("name")
    if room and name and room in rooms:
        join_room(room)
        rooms[room]["members"] += 1
        send({"name": name, "message": "has entered the room"}, to=room)

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    if room and name and room in rooms:
        leave_room(room)
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]
        send({"name": name, "message": "has left the room"}, to=room)

# Função para obter todas as mensagens
def get_all_messages():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM messages
        ORDER BY id DESC
    ''')
    messages = cursor.fetchall()
    conn.close()
    return messages

@app.context_processor
def inject_messages():
    return dict(all_messages=get_all_messages())

if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
