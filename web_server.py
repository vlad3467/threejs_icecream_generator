from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
import os
import sqlite3
from datetime import datetime
import hashlib

app = Flask(__name__)
CORS(app)

# ===== БАЗА ДАННЫХ =====
def initDb():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT
            );''')
    c.execute('''CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            slot_number INTEGER NOT NULL,
            ball INTEGER DEFAULT 0,
            strawberry INTEGER DEFAULT 0,
            lemon INTEGER DEFAULT 0
            );''')
    conn.commit()
    conn.close()

def hashPassword(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ===== МАРШРУТЫ =====

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def staticFiles(filename):
    return send_from_directory('static', filename)

@app.route('/models/<path:filename>')
def serveModel(filename):
    return send_from_directory('models', filename)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Заполните все поля'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        c.execute("""
            INSERT INTO users (username, password_hash) 
            VALUES (?, ?)
        """, (username, hashPassword(password)))
        
        userId = c.lastrowid
        
        for slotNum in range(1, 7):
            c.execute("""
                INSERT INTO slots (user_id, slot_number, ball, strawberry, lemon)
                VALUES (?, ?, 0, 0, 0)
            """, (userId, slotNum))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': 'Регистрация успешна!',
            'user_id': userId,
            'username': username
        })
        
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Пользователь уже существует'}), 400

@app.route('/api/save', methods=['PUT'])
def save():
    data = request.get_json()
    username = data.get('username')
    slotNumber = data.get('slotNumber')
    ball = data.get('ball')
    strawberry = data.get('strawberry')
    lemon = data.get('lemon')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    userId = result[0]
    
    c.execute("UPDATE slots SET ball = ?, strawberry = ?, lemon = ? WHERE user_id = ? AND slot_number = ?", (ball, strawberry, lemon, userId, slotNumber))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': f'Слот {slotNumber} сохранен', 
        'data': {
            'username': username,
            'slot_number': slotNumber,
            'ball': ball,
            'strawberry': strawberry,
            'lemon': lemon
        }
    })

@app.route('/api/remind', methods=['POST'])
def remind():
    data = request.get_json()
    userId = data.get('userId')
    slotNumber = data.get('slotNumber')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM slots WHERE user_id = ? AND slot_number = ?", (userId, slotNumber))
    slot = c.fetchone()
    conn.close()

    if slot:
        return jsonify({
            'success': True,
            'slot': {
                'user_id': slot[1],
                'slot_number': slot[2],
                'ball': slot[3],
                'strawberry': slot[4],
                'lemon': slot[5]
            }
        })
    else:
        return jsonify({'error': 'Слот не найден'}), 404

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Заполните все поля'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE username = ? AND password_hash = ?",
              (username, hashPassword(password)))
    user = c.fetchone()
    conn.close()
    
    if user:
        return jsonify({
            'success': True, 
            'user_id': user[0],
            'username': user[1]
        })
    else:
        return jsonify({'error': 'Неверное имя пользователя или пароль'}), 401

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'ok',
        'message': 'Сервер работает!',
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# ===== ЗАПУСК =====
if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    os.makedirs('models', exist_ok=True)
    initDb()
    
    app.run(host='0.0.0.0', port=5000, debug=True)