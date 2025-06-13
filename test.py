import feedparser


#url='https://tass.ru/rss/v2.xml'
url='https://lenta.ru/rss'

feed = feedparser.parse(url)

print(feed)


#for entry in feed.entries:
    #print(entry.get('summary'))
    # content = entry.get('description', entry.get('summary', ''))
    # if any(keyword.lower() in (entry.title + content).lower() for keyword in keywords):
        # try:
            # conn.execute(
                # "INSERT OR IGNORE INTO news (feed_id, title, content, link, published_at, found_at) "
                # "VALUES (?, ?, ?, ?, ?, ?)",
                # (feed_id, entry.title, content, entry.link, 
                 # entry.get('published', ''), datetime.now())
            # )
            # conn.commit()
        # except sqlite3.IntegrityError:
            # pass