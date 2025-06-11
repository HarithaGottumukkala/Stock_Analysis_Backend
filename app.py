from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import sqlite3
import requests
import datetime
import time
from bs4 import BeautifulSoup
import csv
from io import StringIO
import os

app = Flask(__name__)
CORS(app)

DB_PATH = 'stock_db.sqlite'  # Change if needed

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # For dict-like access
    return conn

@app.route('/')
def home():
    return 'Backend is live! Use /api/... endpoints.'

@app.route('/api/stocks')
def get_stocks():
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT * FROM stocks")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print("[Get Stocks Error]", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks', methods=['POST'])
def add_stock():
    try:
        conn = get_db_connection()
        symbol = request.json.get('symbol')
        conn.execute("INSERT OR IGNORE INTO stocks (symbol) VALUES (?)", (symbol,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Stock added"}), 201
    except Exception as e:
        print("[Add Stock Error]", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks/<symbol>', methods=['DELETE'])
def delete_stock(symbol):
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM stocks WHERE symbol = ?", (symbol,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Stock deleted"})
    except Exception as e:
        print("[Delete Stock Error]", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks/<symbol>/shares', methods=['PUT'])
def update_shares(symbol):
    try:
        data = request.get_json()
        action = data.get('action')
        amount = int(data.get('amount'))

        conn = get_db_connection()
        cursor = conn.execute("SELECT shares FROM stocks WHERE symbol = ?", (symbol,))
        stock = cursor.fetchone()

        if not stock:
            return jsonify({"error": "Stock not found"}), 404

        current_shares = stock['shares']
        new_shares = current_shares + amount if action == "buy" else current_shares - amount

        if new_shares < 0:
            return jsonify({"error": "Not enough shares to sell"}), 400

        conn.execute("UPDATE stocks SET shares = ? WHERE symbol = ?", (new_shares, symbol))
        conn.commit()
        conn.close()
        return jsonify({"message": f"{action.capitalize()} successful", "shares": new_shares})
    except Exception as e:
        print("[Update Shares Error]", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks/<symbol>/chart', methods=['GET'])
def get_stock_chart(symbol):
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT date, price FROM stock_prices WHERE symbol = ? ORDER BY date", (symbol,))
        rows = cursor.fetchall()
        conn.close()

        chart_data = {
            "dates": [str(row["date"]) for row in rows],
            "prices": [float(row["price"]) for row in rows]
        }
        return jsonify(chart_data)
    except Exception as e:
        print("[Chart Data Error]", e)
        return jsonify({"error": str(e)}), 500

def convert_to_unix(date_str):
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return int(time.mktime(dt.timetuple()))

@app.route('/api/stocks/<symbol>/scrape-range', methods=['POST'])
def scrape_from_yahoo(symbol):
    try:
        data = request.get_json()
        start_date = data.get('start')
        end_date = data.get('end')

        if not (start_date and end_date):
            return jsonify({"error": "Missing start or end date"}), 400

        period1 = convert_to_unix(start_date)
        period2 = convert_to_unix(end_date)
        url = f"https://finance.yahoo.com/quote/{symbol}/history?period1={period1}&period2={period2}&interval=1d&filter=history&frequency=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        print(f"[INFO] Scraping: {url}")

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'lxml')
        rows = soup.select('table tbody tr')

        conn = get_db_connection()
        count = 0

        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 6:
                try:
                    date_text = cols[0].text.strip()
                    close_price = cols[4].text.strip().replace(',', '')
                    date_obj = datetime.datetime.strptime(date_text, "%b %d, %Y").date()
                    price = float(close_price)

                    conn.execute("""
                        INSERT INTO stock_prices (symbol, date, price)
                        VALUES (?, ?, ?)
                        ON CONFLICT(symbol, date) DO UPDATE SET price = excluded.price
                    """, (symbol.upper(), str(date_obj), price))
                    count += 1
                except:
                    continue

        conn.commit()
        conn.close()
        return jsonify({"message": f"Scraped {count} records for {symbol.upper()}."})
    except Exception as e:
        print("[Scraping Error]", e)
        return jsonify({"error": "Scraping failed"}), 500

@app.route('/api/stocks/<symbol>/export', methods=['GET'])
def export_csv(symbol):
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT date, price FROM stock_prices WHERE symbol = ? ORDER BY date ASC", (symbol,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return jsonify({'error': 'No data to export'}), 404

        csv_buffer = StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(['Date', 'Price'])
        for row in rows:
            writer.writerow([row['date'], row['price']])

        return Response(
            csv_buffer.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment;filename={symbol}_prices.csv"}
        )
    except Exception as e:
        print("[Export CSV Error]", e)
        return jsonify({'error': 'Failed to export CSV'}), 500

@app.route('/api/report/summary', methods=['GET'])
def get_portfolio_summary():
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT SUM(shares) AS total_shares FROM stocks")
        shares = cursor.fetchone()['total_shares'] or 0

        cursor = conn.execute("SELECT COUNT(*) AS total_stocks FROM stocks")
        stock_count = cursor.fetchone()['total_stocks']

        cursor = conn.execute("SELECT MAX(date) AS latest_date FROM stock_prices")
        latest_date = cursor.fetchone()['latest_date']

        conn.close()

        return jsonify({
            "total_shares": shares,
            "total_stocks": stock_count,
            "latest_price_date": str(latest_date) if latest_date else "N/A"
        })
    except Exception as e:
        print("[Summary Error]", e)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print("[INFO] SQLite database file not found. Please create it with required schema.")
    app.run(debug=True)
