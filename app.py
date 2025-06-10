from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
import mysql.connector
import requests
import datetime
import time
from bs4 import BeautifulSoup
import csv
from io import StringIO

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return 'Backend is live! Use /api/... endpoints.'

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="localhost",
        database="stock_db"
    )

# GET all stocks
@app.route('/api/stocks')
def get_stocks():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM stocks")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print("[Get Stocks Error]", e)
        return jsonify({"error": str(e)}), 500

# ADD a new stock
@app.route('/api/stocks', methods=['POST'])
def add_stock():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        symbol = request.json.get('symbol')
        cursor.execute("INSERT IGNORE INTO stocks (symbol) VALUES (%s)", (symbol,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Stock added"}), 201
    except Exception as e:
        print("[Add Stock Error]", e)
        return jsonify({"error": str(e)}), 500

# DELETE a stock
@app.route('/api/stocks/<symbol>', methods=['DELETE'])
def delete_stock(symbol):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stocks WHERE symbol = %s", (symbol,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Stock deleted"})
    except Exception as e:
        print("[Delete Stock Error]", e)
        return jsonify({"error": str(e)}), 500

# BUY or SELL shares
@app.route('/api/stocks/<symbol>/shares', methods=['PUT'])
def update_shares(symbol):
    try:
        data = request.get_json()
        action = data.get('action')
        amount = int(data.get('amount'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT shares FROM stocks WHERE symbol = %s", (symbol,))
        stock = cursor.fetchone()

        if not stock:
            return jsonify({"error": "Stock not found"}), 404

        current_shares = stock['shares']
        new_shares = current_shares + amount if action == "buy" else current_shares - amount

        if new_shares < 0:
            return jsonify({"error": "Not enough shares to sell"}), 400

        cursor.execute("UPDATE stocks SET shares = %s WHERE symbol = %s", (new_shares, symbol))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"{action.capitalize()} successful", "shares": new_shares})
    except Exception as e:
        print("[Update Shares Error]", e)
        return jsonify({"error": str(e)}), 500

# GET stock chart data
@app.route('/api/stocks/<symbol>/chart', methods=['GET'])
def get_stock_chart(symbol):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT date, price FROM stock_prices
            WHERE symbol = %s ORDER BY date
        """, (symbol,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        chart_data = {
            "dates": [str(row["date"]) for row in rows],
            "prices": [float(row["price"]) for row in rows]
        }
        return jsonify(chart_data)
    except Exception as e:
        print("[Chart Data Error]", e)
        return jsonify({"error": str(e)}), 500

# Convert date to UNIX
def convert_to_unix(date_str):
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return int(time.mktime(dt.timetuple()))

# Scrape Yahoo Finance for date range
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
        cursor = conn.cursor()
        count = 0

        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 6:
                try:
                    date_text = cols[0].text.strip()
                    close_price = cols[4].text.strip().replace(',', '')
                    date_obj = datetime.datetime.strptime(date_text, "%b %d, %Y").date()
                    price = float(close_price)

                    cursor.execute("""
                        INSERT INTO stock_prices (symbol, date, price)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE price = VALUES(price)
                    """, (symbol.upper(), date_obj, price))
                    count += 1
                except:
                    continue

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Scraped {count} records for {symbol.upper()}."})

    except Exception as e:
        print("[Scraping Error]", e)
        return jsonify({"error": "Scraping failed"}), 500

# Export CSV
@app.route('/api/stocks/<symbol>/export', methods=['GET'])
def export_csv(symbol):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT date, price FROM stock_prices
            WHERE symbol = %s ORDER BY date ASC
        """, (symbol,))
        rows = cursor.fetchall()
        cursor.close()
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

# Portfolio Summary
@app.route('/api/report/summary', methods=['GET'])
def get_portfolio_summary():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT SUM(shares) AS total_shares FROM stocks")
        shares = cursor.fetchone()['total_shares'] or 0

        cursor.execute("SELECT COUNT(*) AS total_stocks FROM stocks")
        stock_count = cursor.fetchone()['total_stocks']

        cursor.execute("SELECT MAX(date) AS latest_date FROM stock_prices")
        latest_date = cursor.fetchone()['latest_date']

        cursor.close()
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
    app.run(debug=True)