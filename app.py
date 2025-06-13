import sqlite3
from flask import Flask, request, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from datetime import datetime
import threading
import logging
from dateutil import parser as date_parser

app = Flask(__name__)
DATABASE = "rss_monitor.db"
scheduler = BackgroundScheduler(daemon=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Инициализация БД
def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE,
            name TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY,
            keyword TEXT UNIQUE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER,
            title TEXT,
            content TEXT,
            link TEXT UNIQUE,
            published_at DATETIME,
            found_at DATETIME,
            matched_keywords TEXT,
            FOREIGN KEY(feed_id) REFERENCES feeds(id)
        )
    """)
    conn.commit()
    conn.close()

# Парсинг RSS-лент
def parse_feeds():
    logging.info("Начинаю парсинг RSS-лент...")
    with sqlite3.connect(DATABASE) as conn:
        feeds = conn.execute("SELECT id, url FROM feeds").fetchall()
        keywords = [row[0] for row in conn.execute("SELECT keyword FROM keywords").fetchall()]

        logging.info(f"Найдено {len(feeds)} лент и {len(keywords)} ключевых слов.")

        if not feeds:
            logging.warning("Нет активных лент. Пропускаю парсинг.")
            return

        for feed_id, url in feeds:
            logging.info(f"Парсю ленту ID {feed_id}: {url}")
            try:
                feed = feedparser.parse(url)
                if not feed.entries:
                    logging.warning(f"Лента {url} не содержит записей.")
                    continue

                for entry in feed.entries:
                    try:
                        pub_date = None
                        if hasattr(entry, 'published'):
                            pub_date = date_parser.parse(entry.published).isoformat()

                        content = entry.get('description', entry.get('summary', ''))
                        full_text = (entry.title + content).lower()
                        matched_keywords = [k for k in keywords if k.lower() in full_text]

                        conn.execute(
                            "INSERT OR IGNORE INTO news "
                            "(feed_id, title, content, link, published_at, found_at, matched_keywords) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (feed_id, entry.title, content, entry.link, pub_date, datetime.now(), ", ".join(matched_keywords))
                        )
                        conn.commit()
                        logging.info(f"Добавлена новость: {entry.title[:50]}... | Найдено: {matched_keywords}")
                    except Exception as e:
                        logging.error(f"Ошибка при обработке записи: {e}")
            except Exception as e:
                logging.error(f"Ошибка при парсинге ленты {url}: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin/feeds', methods=['GET', 'POST', 'DELETE'])
def manage_feeds():
    if request.method == 'POST':
        data = request.json
        with sqlite3.connect(DATABASE) as conn:
            conn.execute("INSERT OR IGNORE INTO feeds (url, name) VALUES (?, ?)", 
                         (data['url'], data.get('name', '')))
            conn.commit()
        logging.info(f"Добавлена лента: {data['url']}")
        return jsonify({"status": "added"})
    
    elif request.method == 'DELETE':
        feed_id = request.args.get('id')
        with sqlite3.connect(DATABASE) as conn:
            conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
            conn.commit()
        logging.info(f"Удалена лента ID: {feed_id}")
        return jsonify({"status": "deleted"})
    
    else:
        with sqlite3.connect(DATABASE) as conn:
            feeds = conn.execute("SELECT id, url, name FROM feeds").fetchall()
        return jsonify([{"id": row[0], "url": row[1], "name": row[2]} for row in feeds])

@app.route('/admin/keywords', methods=['GET', 'POST', 'DELETE'])
def manage_keywords():
    if request.method == 'POST':
        keyword = request.json.get('keyword')
        with sqlite3.connect(DATABASE) as conn:
            conn.execute("INSERT OR IGNORE INTO keywords (keyword) VALUES (?)", (keyword,))
            conn.commit()
        logging.info(f"Добавлено ключевое слово: {keyword}")
        return jsonify({"status": "added"})
    
    elif request.method == 'DELETE':
        keyword_id = request.args.get('id')
        with sqlite3.connect(DATABASE) as conn:
            conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
            conn.commit()
        logging.info(f"Удалено ключевое слово ID: {keyword_id}")
        return jsonify({"status": "deleted"})
    
    else:
        with sqlite3.connect(DATABASE) as conn:
            keywords = conn.execute("SELECT id, keyword FROM keywords").fetchall()
        return jsonify([{"id": row[0], "keyword": row[1]} for row in keywords])

@app.route('/api/news')
def get_news():
    def dict_factory(cursor, row):
        return {desc[0]: row[i] for i, desc in enumerate(cursor.description)}

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    keyword_filter = request.args.get('keyword', '').strip().lower()
    filter_type = request.args.get('filter_type', 'title')  # title / keywords

    offset = (page - 1) * per_page

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = dict_factory
    cur = conn.cursor()

    base_query = """
        SELECT n.id, n.title, n.content, n.link, n.published_at, f.name as source, n.matched_keywords
        FROM news n JOIN feeds f ON n.feed_id = f.id
    """

    if keyword_filter:
        if filter_type == 'title':
            base_query += f" WHERE INSTR(LOWER(n.title), '{keyword_filter}') > 0"
        elif filter_type == 'keywords':
            base_query += f" WHERE INSTR(LOWER(n.matched_keywords), '{keyword_filter}') > 0"

    base_query += " ORDER BY n.published_at DESC LIMIT ? OFFSET ?"

    cur.execute(base_query, (per_page, offset))
    news = cur.fetchall()

    cur.execute("SELECT COUNT(*) AS total FROM news")
    total = cur.fetchone()['total']

    conn.close()
    return jsonify({"news": news, "total": total})

@app.route('/admin/parse_now')
def manual_parse():
    thread = threading.Thread(target=parse_feeds)
    thread.start()
    logging.info("Запущен ручной парсинг.")
    return jsonify({"status": "Started manual parsing"})

# Запуск парсера
def start_scheduler():
    scheduler.add_job(parse_feeds, 'interval', minutes=1)
    scheduler.start()

if __name__ == '__main__':
    init_db()
    start_scheduler()
    app.run(debug=True, port=5000)