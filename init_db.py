import sqlite3

def init_db():
    conn = sqlite3.connect('stock_db.sqlite')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol VARCHAR(100) UNIQUE,
            shares INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol VARCHAR(100),
            date TEXT,
            price REAL,
            UNIQUE(symbol, date)
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ Tables created successfully.")

if __name__ == '__main__':
    init_db()
