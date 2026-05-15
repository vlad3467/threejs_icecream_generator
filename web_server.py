from flask import Flask, send_from_directory, jsonify, request, render_template_string
from flask_cors import CORS
import os
import sqlite3
from datetime import datetime
import hashlib
import hmac
import json
import base64

app = Flask(__name__)
CORS(app)
app.secret_key = os.urandom(24).hex()

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
            lemon INTEGER DEFAULT 0,
            ice_cream_link TEXT DEFAULT NULL
            );''')
    c.execute('''CREATE TABLE IF NOT EXISTS ice_cream_links (
            id INTEGER PRIMARY KEY,
            token TEXT UNIQUE,
            ingredients_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );''')
    conn.commit()
    conn.close()

def hashPassword(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_signed_token(ingredients_data):
    """Генерирует защищенный токен с HMAC-подписью"""
    data_json = json.dumps(ingredients_data, sort_keys=True)
    
    signature = hmac.new(
        app.secret_key.encode(),
        data_json.encode(),
        hashlib.sha256
    ).hexdigest()
    
    token_data = json.dumps({
        'data': ingredients_data,
        'signature': signature
    })
    
    token = base64.urlsafe_b64encode(token_data.encode()).decode()
    return token

def verify_token(token):
    """Проверяет подлинность токена"""
    try:
        token_data = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
        
        data = token_data['data']
        signature = token_data['signature']
        
        data_json = json.dumps(data, sort_keys=True)
        expected_signature = hmac.new(
            app.secret_key.encode(),
            data_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if hmac.compare_digest(signature, expected_signature):
            return data
        return None
    except:
        return None

def get_ingredients_from_db(token):
    """Получает данные ингредиентов из базы данных"""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT ingredients_data FROM ice_cream_links WHERE token = ?", (token,))
    result = c.fetchone()
    conn.close()
    
    if result:
        try:
            return json.loads(result[0])
        except:
            return None
    return None

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
    ingredients = data.get('ingredients')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    if not result:
        conn.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    
    userId = result[0]
    
    # Генерируем защищенную ссылку если есть ингредиенты
    ice_cream_link = None
    if ingredients and len(ingredients) > 0:
        token = generate_signed_token(ingredients)
        
        # Сохраняем в базу данных
        c.execute("""
            INSERT INTO ice_cream_links (token, ingredients_data) 
            VALUES (?, ?)
        """, (token, json.dumps(ingredients)))
        
        ice_cream_link = f"/view/{token}"
    
    # Обновляем слот
    c.execute("""
        UPDATE slots 
        SET ball = ?, strawberry = ?, lemon = ?, ice_cream_link = ? 
        WHERE user_id = ? AND slot_number = ?
    """, (ball, strawberry, lemon, ice_cream_link, userId, slotNumber))
    
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
            'lemon': lemon,
            'ice_cream_link': ice_cream_link
        }
    })

@app.route('/view/<token>')
def view_ice_cream(token):
    """Отображает страницу с собранным мороженым"""
    # Проверяем токен
    ingredients_data = verify_token(token)
    
    if not ingredients_data:
        # Пробуем найти в базе данных
        ingredients_data = get_ingredients_from_db(token)
        
        if not ingredients_data:
            return "Недействительная или устаревшая ссылка", 404
    
    # Передаем данные в шаблон через data-атрибут
    return send_from_directory('static', 'show.html')

@app.route('/api/get-ingredients/<token>')
def get_ingredients(token):
    """API endpoint для получения данных ингредиентов"""
    ingredients_data = verify_token(token)
    
    if not ingredients_data:
        ingredients_data = get_ingredients_from_db(token)
        
        if not ingredients_data:
            return jsonify({'error': 'Недействительный токен'}), 404
    
    return jsonify({
        'success': True,
        'ingredients': ingredients_data
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
                'lemon': slot[5],
                'ice_cream_link': slot[6]
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