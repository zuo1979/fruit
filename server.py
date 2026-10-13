# -*- coding: utf-8 -*-
"""水果王國後端伺服器"""
import sqlite3
import hashlib
import random
import secrets
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.')
CORS(app)

DB_PATH = 'lucky.db'
DEFAULT_PASSWORD = 'xg8888'

# 登录失败限制
_login_failures = {}
MAX_FAILS = 5
LOCK_SECONDS = 600

# 混淆后的 API 路径
API_PREFIX = '/api/x7k2m'
LOGIN_PATH = API_PREFIX + '/auth'
SET_NEXT_PATH = API_PREFIX + '/s1'
CLEAR_NEXT_PATH = API_PREFIX + '/s2'
REDRAW_PATH = API_PREFIX + '/s3'
CHANGE_PW_PATH = API_PREFIX + '/s4'
SLOTS_PATH = API_PREFIX + '/s5'
HISTORY_PATH = API_PREFIX + '/s6'
NEXT_INFO_PATH = API_PREFIX + '/s7'
LUCKY_PATH = API_PREFIX + '/p1'

FRUITS = [
    {'id':1,'name':'荔枝','jp':'ライチ'},{'id':2,'name':'青蘋果','jp':'青リンゴ'},
    {'id':3,'name':'山竹','jp':'マンゴスチン'},{'id':4,'name':'雪梨','jp':'白ナシ'},
    {'id':5,'name':'楊梅','jp':'ヨウバイ'},{'id':6,'name':'石榴','jp':'ザクロ'},
    {'id':7,'name':'枇杷','jp':'ビワ'},{'id':8,'name':'檸檬','jp':'レモン'},
    {'id':9,'name':'柚子','jp':'ユズ'},{'id':10,'name':'蜜桔','jp':'みかん'},
    {'id':11,'name':'葡萄','jp':'ブドウ'},{'id':12,'name':'無花果','jp':'イチジク'},
    {'id':13,'name':'柿子','jp':'カキ'},{'id':14,'name':'草莓','jp':'イチゴ'},
    {'id':15,'name':'藍莓','jp':'ブルーベリー'},{'id':16,'name':'聖女果','jp':'ミニトマト'},
    {'id':17,'name':'西瓜','jp':'スイカ'},{'id':18,'name':'哈密瓜','jp':'ハミウリ'},
    {'id':19,'name':'番石榴','jp':'グァバ'},{'id':20,'name':'水蜜桃','jp':'モモ'},
    {'id':21,'name':'楊桃','jp':'スターフルーツ'},{'id':22,'name':'龍眼','jp':'リュウガン'},
    {'id':23,'name':'香蕉','jp':'バナナ'},{'id':24,'name':'芒果','jp':'マンゴー'},
    {'id':25,'name':'鳳梨','jp':'パイナップル'},{'id':26,'name':'椰子','jp':'ココナッツ'},
    {'id':27,'name':'火龍果','jp':'ドラゴンフルーツ'},{'id':28,'name':'百香果','jp':'パッションフルーツ'},
    {'id':29,'name':'釋迦果','jp':'釈迦頭'},{'id':30,'name':'甘蔗','jp':'サトウキビ'},
    {'id':31,'name':'奇異果','jp':'キウイ'},{'id':32,'name':'李子','jp':'スモモ'},
    {'id':33,'name':'榴槤','jp':'ドリアン'},{'id':34,'name':'車厘子','jp':'チェリー'},
    {'id':35,'name':'牛油果','jp':'アボカド'},
]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS lucky_results (
        date_str TEXT, session INTEGER, fruit_ids TEXT,
        PRIMARY KEY(date_str, session)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT, ua TEXT, device TEXT, os TEXT, browser TEXT,
        visit_count INTEGER, referer TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    # 舊表加referer字段
    try:
        c.execute("ALTER TABLE visits ADD COLUMN referer TEXT")
    except:
        pass
    c.execute("SELECT value FROM settings WHERE key='password_hash'")
    if not c.fetchone():
        h = hashlib.sha256(DEFAULT_PASSWORD.encode()).hexdigest()
        c.execute("INSERT INTO settings (key, value) VALUES ('password_hash', ?)", (h,))
    conn.commit()
    conn.close()

def get_password_hash():
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key='password_hash'").fetchone()
    conn.close()
    return row['value'] if row else hashlib.sha256(DEFAULT_PASSWORD.encode()).hexdigest()

def verify_token():
    """驗證請求頭裡的 token 是否有效"""
    token = request.headers.get('X-Auth-Token', '')
    if not token:
        return False
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key='auth_token'").fetchone()
    conn.close()
    return row and row['value'] == token

def issue_token():
    """生成新 token 存數據庫"""
    token = secrets.token_hex(16)
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auth_token', ?)", (token,))
    conn.commit()
    conn.close()
    return token

def get_slots():
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key='slots'").fetchone()
    conn.close()
    if row:
        try:
            return [int(x) for x in row['value'].split(',')]
        except:
            pass
    return [14*60+30, 21*60+30]

def fmt_time(minutes):
    return str(int(minutes//60)) + ':' + str(int(minutes%60)).zfill(2)

def get_display_info():
    """返回當前應該顯示的場次 + 下一場信息"""
    now = datetime.now()
    cur_min = now.hour * 60 + now.minute
    slots = get_slots()

    # 找當前顯示哪場，下一場是哪場
    if cur_min < slots[0]:
        # 還沒到第一場：顯示昨天第二場，下一場是今天第一場
        yd = now - timedelta(days=1)
        display = {'date_str': yd.strftime('%Y%m%d'), 'session': 1, 'label': fmt_time(slots[1])}
        next_draw = {'date_str': now.strftime('%Y%m%d'), 'session': 0, 'label': fmt_time(slots[0]), 'min_left': slots[0] - cur_min}
    elif cur_min < slots[1]:
        # 第一場已開，第二場未開：顯示今天第一場，下一場是今天第二場
        display = {'date_str': now.strftime('%Y%m%d'), 'session': 0, 'label': fmt_time(slots[0])}
        next_draw = {'date_str': now.strftime('%Y%m%d'), 'session': 1, 'label': fmt_time(slots[1]), 'min_left': slots[1] - cur_min}
    else:
        # 兩場都開完了：顯示今天第二場，下一場是明天第一場
        tm = now + timedelta(days=1)
        display = {'date_str': now.strftime('%Y%m%d'), 'session': 1, 'label': fmt_time(slots[1])}
        next_draw = {'date_str': tm.strftime('%Y%m%d'), 'session': 0, 'label': fmt_time(slots[0]), 'min_left': (24*60 - cur_min) + slots[0]}

    return display, next_draw, now

def get_or_draw(date_str, session):
    """讀結果，沒有就自動抽"""
    conn = get_db()
    row = conn.execute('SELECT fruit_ids FROM lucky_results WHERE date_str=? AND session=?', (date_str, session)).fetchone()
    if row:
        ids = [int(x) for x in row['fruit_ids'].split(',')]
    else:
        ids = [random.randint(1, 35) for _ in range(3)]
        conn.execute('INSERT OR REPLACE INTO lucky_results (date_str, session, fruit_ids) VALUES (?,?,?)',
                     (date_str, session, ','.join(map(str, ids))))
        conn.commit()
    conn.close()
    return [next(f for f in FRUITS if f['id'] == i) for i in ids]

@app.route(LUCKY_PATH)
def api_lucky():
    display, next_draw, now = get_display_info()
    fruits = get_or_draw(display['date_str'], display['session'])
    return jsonify({
        'display_label': display['label'],
        'display_date': display['date_str'],
        'fruits': fruits,
        'next_label': next_draw['label'],
        'next_min': next_draw['min_left']
    })

@app.route(NEXT_INFO_PATH)
def api_next_info():
    """返回下一場信息"""
    display, next_draw, now = get_display_info()
    result = {
        'next_label': next_draw['label'],
        'next_date': next_draw['date_str'],
        'next_min': next_draw['min_left']
    }
    # 只有带token的后台请求才返回current_ids
    if verify_token():
        conn = get_db()
        row = conn.execute('SELECT fruit_ids FROM lucky_results WHERE date_str=? AND session=?',
                           (next_draw['date_str'], next_draw['session'])).fetchone()
        conn.close()
        result['current_ids'] = [int(x) for x in row['fruit_ids'].split(',')] if row else None
    return jsonify(result)

@app.route(LOGIN_PATH, methods=['POST'])
def api_login():
    ip = request.remote_addr
    now = time.time()
    # 检查是否被锁
    if ip in _login_failures:
        fails, lock_until = _login_failures[ip]
        if lock_until and now < lock_until:
            remain = int((lock_until - now) / 60) + 1
            return jsonify({'ok': False, 'error': f'失敗過多、{remain}分待機 / 错误过多，请等{remain}分钟'}), 429
    data = request.get_json()
    if hashlib.sha256(data.get('password', '').encode()).hexdigest() == get_password_hash():
        _login_failures.pop(ip, None)
        return jsonify({'ok': True, 'token': issue_token()})
    # 登录失败记录
    fails = _login_failures.get(ip, (0, 0))[0] + 1
    lock_until = now + LOCK_SECONDS if fails >= MAX_FAILS else 0
    _login_failures[ip] = (fails, lock_until)
    left = MAX_FAILS - fails
    return jsonify({'ok': False, 'error': f'パスワード違い、残り{left}回 / 密码错误，剩{left}次'}), 401

@app.route(CHANGE_PW_PATH, methods=['POST'])
def api_change_password():
    if not verify_token():
        return jsonify({'ok': False, 'error': '未授權'}), 401
    data = request.get_json()
    if hashlib.sha256(data.get('old_password','').encode()).hexdigest() != get_password_hash():
        return jsonify({'ok': False, 'error': '舊密碼錯誤'})
    if len(data.get('new_password','')) < 6:
        return jsonify({'ok': False, 'error': '新密碼至少6位'})
    conn = get_db()
    conn.execute("UPDATE settings SET value=? WHERE key='password_hash'",
                 (hashlib.sha256(data['new_password'].encode()).hexdigest(),))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route(SET_NEXT_PATH, methods=['POST'])
def api_set_next():
    """設置下一場的水果"""
    if not verify_token():
        return jsonify({'ok': False, 'error': '未授權'}), 401
    data = request.get_json()
    ids = data.get('fruit_ids')
    if not ids or len(ids) != 3:
        return jsonify({'ok': False, 'error': '請選擇3個水果'})
    _, next_draw, _ = get_display_info()
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO lucky_results (date_str, session, fruit_ids) VALUES (?,?,?)',
                 (next_draw['date_str'], next_draw['session'], ','.join(map(str, ids))))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route(CLEAR_NEXT_PATH, methods=['POST'])
def api_clear_next():
    """清除下一場設置，恢復自動隨機"""
    if not verify_token():
        return jsonify({'ok': False, 'error': '未授權'}), 401
    _, next_draw, _ = get_display_info()
    conn = get_db()
    conn.execute('DELETE FROM lucky_results WHERE date_str=? AND session=?',
                 (next_draw['date_str'], next_draw['session']))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route(REDRAW_PATH, methods=['POST'])
def api_redraw_next():
    """重新隨機抽取下一場"""
    if not verify_token():
        return jsonify({'ok': False, 'error': '未授權'}), 401
    _, next_draw, _ = get_display_info()
    ids = [random.randint(1, 35) for _ in range(3)]
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO lucky_results (date_str, session, fruit_ids) VALUES (?,?,?)',
                 (next_draw['date_str'], next_draw['session'], ','.join(map(str, ids))))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route(HISTORY_PATH)
def api_history():
    conn = get_db()
    rows = conn.execute('SELECT date_str, session, fruit_ids FROM lucky_results ORDER BY date_str DESC, session DESC').fetchall()
    conn.close()
    result = []
    for r in rows:
        ids = [int(x) for x in r['fruit_ids'].split(',')]
        fruits = [next(f for f in FRUITS if f['id'] == i) for i in ids]
        result.append({'date_str': r['date_str'], 'session': r['session'], 'fruits': fruits})
    return jsonify({'history': result})

@app.route(API_PREFIX + '/d1', methods=['POST'])
def api_delete_history():
    """删除历史记录：传 ids=[date_str,session] 列表，或 all=true 全部删除"""
    if not verify_token():
        return jsonify({'ok': False, 'error': '未授權'}), 401
    data = request.get_json()
    conn = get_db()
    if data.get('all'):
        conn.execute('DELETE FROM lucky_results')
    else:
        for item in data.get('ids', []):
            conn.execute('DELETE FROM lucky_results WHERE date_str=? AND session=?', (item[0], item[1]))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route(API_PREFIX + '/a1', methods=['POST'])
def api_add_history():
    """添加历史记录：传 date_str, session, fruit_ids"""
    if not verify_token():
        return jsonify({'ok': False, 'error': '未授權'}), 401
    data = request.get_json()
    conn = get_db()
    for item in data.get('items', []):
        conn.execute('INSERT OR REPLACE INTO lucky_results (date_str, session, fruit_ids) VALUES (?,?,?)',
                     (item['date_str'], item['session'], ','.join(map(str, item['fruit_ids']))))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route(SLOTS_PATH)
def api_get_slots():
    s = get_slots()
    return jsonify({'slots': {'slot1': s[0], 'slot2': s[1]}})

@app.route(SLOTS_PATH, methods=['POST'])
def api_set_slots():
    if not verify_token():
        return jsonify({'ok': False, 'error': '未授權'}), 401
    data = request.get_json()
    s1, s2 = data.get('slot1'), data.get('slot2')
    if s1 is None or s2 is None or s1 >= s2:
        return jsonify({'ok': False, 'error': '時間設定錯誤'})
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('slots', ?)", (str(s1)+','+str(s2),))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/')
def index():
    # 記錄訪客
    try:
        ip = request.remote_addr
        ua = request.headers.get('User-Agent', '')
        # 簡單解析UA
        device = '手機' if 'Mobile' in ua else '電腦'
        if 'Android' in ua: os = 'Android'
        elif 'iPhone' in ua or 'iPad' in ua: os = 'iOS'
        elif 'Windows' in ua: os = 'Windows'
        elif 'Macintosh' in ua: os = 'MacOS'
        elif 'Linux' in ua: os = 'Linux'
        else: os = '其他'
        if 'Chrome' in ua: browser = 'Chrome'
        elif 'Safari' in ua: browser = 'Safari'
        elif 'Firefox' in ua: browser = 'Firefox'
        elif 'Edge' in ua: browser = 'Edge'
        else: browser = '其他'
        conn = get_db()
        # 查這個IP訪問過幾次
        row = conn.execute('SELECT visit_count FROM visits WHERE ip=? ORDER BY id DESC LIMIT 1', (ip,)).fetchone()
        count = (row['visit_count'] + 1) if row else 1
        # 訪問來源
        referer = request.headers.get('Referer', '直接訪問')
        if referer:
            # 只取域名部分
            try:
                from urllib.parse import urlparse
                referer = urlparse(referer).netloc or '直接訪問'
            except:
                pass
        # 用北京時間
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('INSERT INTO visits (ip, ua, device, os, browser, visit_count, referer, created_at) VALUES (?,?,?,?,?,?,?,?)',
                     (ip, ua, device, os, browser, count, referer, now_str))
        conn.commit()
        conn.close()
    except:
        pass
    html = open('鲜果优选水果店.html', 'r', encoding='utf-8').read()
    # 檢查秘密參數，正確才注入後台標記
    if request.args.get('a') == 'k7x9m2':
        html = html.replace('</head>', '<script>window.__admin=true</script></head>')
    return html

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

# 訪客統計 API
VISITS_STATS_PATH = API_PREFIX + '/v1'
@app.route(VISITS_STATS_PATH)
def api_visits_stats():
    if not verify_token():
        return jsonify({'ok': False, 'error': '未授權'}), 401
    conn = get_db()
    # 今日訪問量
    today = datetime.now().strftime('%Y-%m-%d')
    today_count = conn.execute("SELECT COUNT(*) as c FROM visits WHERE date(created_at)=?", (today,)).fetchone()['c']
    # 總訪問量
    total_count = conn.execute("SELECT COUNT(*) as c FROM visits").fetchone()['c']
    # 獨立IP數
    unique_ip = conn.execute("SELECT COUNT(DISTINCT ip) as c FROM visits").fetchone()['c']
    # 設備分布
    device_stats = conn.execute("SELECT device, COUNT(*) as c FROM visits GROUP BY device").fetchall()
    # 操作系統分布
    os_stats = conn.execute("SELECT os, COUNT(*) as c FROM visits GROUP BY os").fetchall()
    # 最近10條訪問
    recent = conn.execute("SELECT ip, device, os, browser, visit_count, referer, created_at FROM visits ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return jsonify({
        'today': today_count,
        'total': total_count,
        'unique_ip': unique_ip,
        'device': [dict(r) for r in device_stats],
        'os': [dict(r) for r in os_stats],
        'recent': [dict(r) for r in recent]
    })

if __name__ == '__main__':
    init_db()
    print('伺服器啟動: http://127.0.0.1:5000')

    # 後台定時任務：到了開獎時間自動生成結果
    import threading
    def auto_draw_loop():
        while True:
            try:
                display, next_draw, now = get_display_info()
                # 觸發當前顯示場次生成
                get_or_draw(display['date_str'], display['session'])
                print(f"[自動開獎] {display['date_str']} {display['label']} 場次已確認")
            except Exception as e:
                print(f"[自動開獎] 錯誤: {e}")
            time.sleep(60)  # 每分鐘檢查一次
    threading.Thread(target=auto_draw_loop, daemon=True).start()

import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
