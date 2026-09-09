# 🛡️ PriceSentry

### Track product prices. Detect drops. Get alerted.

**PriceSentry** is a lightweight Python price-monitoring tool that tracks product prices over time, stores historical observations, detects price drops, and sends alerts when prices reach your configured threshold.

> **Scrape → Persist → Analyse → Alert**

It can run manually for one-time checks or continuously with `watch`, allowing you to monitor products automatically.

---

## ✨ Features

### 🔎 Price Monitoring

* Scrape prices from product pages using CSS selectors 
* Automatic fallback to:

  * `product:price:amount` meta tags
  * JSON-LD `offers`
* Support for multiple products
* International price formats:

  * `$1,299.00`
  * `1.299,00 €`
  * `1 234,50 AMD`
* Automatic retries on network failures

### 📈 Price History

* Timestamped price observations
* Append-only CSV or JSON storage
* View historical prices for individual products or all products
* Automatic statistics:

  * Minimum
  * Maximum
  * Average
  * Overall price change

### 🚨 Smart Alerts

* Threshold-based alerts
* Price-drop detection
* Alerts only when a price **crosses** the configured threshold
* Console notifications
* Desktop notifications with `plyer`
* Email notifications via SMTP

### 📊 Visualisation & Automation

* Generate price-history charts with `matplotlib`
* Built-in scheduler with `watch`
* Run checks automatically at configurable intervals
* Add or remove products through configuration without changing code

---

## 🏗️ Architecture

PriceSentry follows a simple data-collection pipeline:

```text
                         config.json
                products • selectors • thresholds
                         • interval
                              │
                              ▼
                ┌─────────────────────────┐
                │       scraper.py        │
                │                         │
                │  fetch → parse → record │
                │                         │
                │ requests + BeautifulSoup│
                └────────────┬────────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
          ┌─────────────────┐  ┌──────────────────┐
          │    logger.py    │  │    alerts.py     │
          │                 │  │                  │
          │ CSV / JSON      │  │ threshold check  │
          │ price history   │  │ price-drop check │
          └────────┬────────┘  └────────┬─────────┘
                   │                    │
                   ▼                    ▼
          ┌─────────────────┐   ┌─────────────────┐
          │ history / chart │   │ notifications   │
          │                 │   │                 │
          │ price analysis  │   │ console / email │
          │ matplotlib      │   │ / desktop       │
          └─────────────────┘   └─────────────────┘
```

Each check compares the current price with the **previously recorded price**, allowing PriceSentry to distinguish between:

* a product that is simply cheap today
* a product that has **just become cheaper**

---

## ⚙️ How It Works

The application follows four main stages:

| Stage      | Component           | Responsibility                             |
| ---------- | ------------------- | ------------------------------------------ |
| 🔎 Scrape  | `scraper.py`        | Fetch product pages and extract prices     |
| 💾 Persist | `logger.py`         | Store timestamped observations             |
| 📊 Analyse | `history` / `chart` | Calculate statistics and visualise changes |
| 🚨 Alert   | `alerts.py`         | Detect threshold crossings and price drops |

---

## 🧰 Tech Stack

| Technology        | Purpose               |
| ----------------- | --------------------- |
| 🐍 Python 3.10+   | Core application      |
| 🌐 Requests       | HTTP requests         |
| 🍲 BeautifulSoup4 | HTML parsing          |
| 📊 Matplotlib     | Price charts          |
| 🔔 Plyer          | Desktop notifications |
| 🧪 Pytest         | Automated testing     |
| 📄 CSV / JSON     | Price-history storage |
| 📧 SMTP           | Email notifications   |

Only `requests` and `beautifulsoup4` are strictly required.

`matplotlib`, `plyer`, and `lxml` are optional. Missing optional dependencies are handled with clear messages.

---

# 🚀 Installation

## Requirements

* Python **3.10+**
* Internet connection for live product pages

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/PriceSentry.git
cd PriceSentry
```

### 2. Create a virtual environment

#### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

# ⚙️ Configuration

PriceSentry is configured through `config.json`.

The repository includes two offline demo products so you can test the application immediately.

Example:

```json
{
  "storage": {
    "path": "data/price_history.csv"
  },
  "schedule": {
    "interval_minutes": 360
  },
  "alerts": {
    "notify_on_drop": true,
    "desktop": false,
    "email": {
      "enabled": false
    }
  },
  "products": [
    {
      "name": "Aurora X200 Headphones",
      "url": "https://demoshop.example/p/aurora-x200",
      "selector": ".price-now",
      "threshold": 160.0
    }
  ]
}
```

---

## 📝 Configuration Fields

| Field       | Required | Description                                              |
| ----------- | :------: | -------------------------------------------------------- |
| `name`      |     ✅    | Product name used in logs, alerts and `--product`        |
| `url`       |     ✅    | Product page URL. Local `.html` files are also supported |
| `selector`  |     ❌    | CSS selector for the price element                       |
| `threshold` |     ❌    | Alert when the price reaches or falls below this value   |
| `currency`  |     ❌    | Force a specific currency code                           |

### Finding a CSS Selector

1. Open the product page
2. Right-click the displayed price
3. Select **Inspect**
4. Right-click the highlighted element
5. Choose **Copy → Copy selector**
6. Simplify it to a stable selector when possible

For example:

```css
.price-now
```

or:

```css
#priceblock_ourprice
```

If you omit `selector`, PriceSentry automatically tries to detect the price using page metadata and JSON-LD.

---

## 💾 Storage

CSV is the default format:

```json
{
  "storage": {
    "path": "data/price_history.csv"
  }
}
```

To use JSON instead:

```json
{
  "storage": {
    "path": "data/price_history.json"
  }
}
```

The storage format is determined by the file extension.

---

# 🖥️ Usage 

## Check prices

Check every configured product:

```bash
python -m src.main check
```

Check a specific product:

```bash
python -m src.main check -p "Headphones"
```

---

## 📜 View Price History

Show the complete history:

```bash
python -m src.main history
```

Show the latest 10 records for a product:

```bash
python -m src.main history -p "Headphones" -n 10
```

Get machine-readable JSON:

```bash
python -m src.main history --json
```

---

## 📊 Generate Charts

Generate a price chart:

```bash
python -m src.main chart
```

Output:

```text
data/price_chart.png
```

Generate a chart for a specific product:

```bash
python -m src.main chart -p "Headphones" -o mychart.png
```

---

## 🛒 View Tracked Products 

```bash
python -m src.main products
```

This shows the products being monitored and their latest recorded prices.

---

## ⏰ Continuous Monitoring

Check every 60 minutes:

```bash
python -m src.main watch -i 60
```

You can also use a different configuration file:

```bash
python -m src.main -c other.json check
```

### Windows

If `python` is not available on your PATH:

```bash
py -m src.main check
```

---

# 🔔 Notifications

## 🖥️ Desktop Notifications

Install `plyer`:

```bash
pip install plyer
```

Then enable desktop notifications:

```json
{
  "alerts": {
    "desktop": true
  }
}
```

---

## 📧 Email Notifications

Email notifications use SMTP.

Example configuration:

```json
{
  "email": {
    "enabled": true,
    "host": "smtp.gmail.com",
    "port": 587,
    "sender": "you@gmail.com",
    "recipients": [
      "you@gmail.com"
    ],
    "password_env": "PRICESENTRY_SMTP_PASSWORD"
  }
}
```

The password is **never stored inside `config.json`**.

### Windows

```powershell
$env:PRICESENTRY_SMTP_PASSWORD = "your-app-password"
```

### macOS / Linux

```bash
export PRICESENTRY_SMTP_PASSWORD="your-app-password"
```

For Gmail, use an **App Password** rather than your normal account password.

---

# 💡 Example

Running:

```bash
python -m src.main check
```

might produce:

```text
Checking 2 product(s) at 2026-01-07 09:00:03

  Aurora X200 Headphones:
      149.99 USD
      threshold 160.00
      price <= threshold

      down 24.51 since 2026-01-06 09:00

  [!] Price alert: Aurora X200 Headphones

      Aurora X200 Headphones is now 149.99 USD,
      below your threshold of 160.00 USD.

      https://demoshop.example/p/aurora-x200

  Nimbus 68 Keyboard:
      89.50 USD
      threshold 75.00
      price > threshold

Logged 2 price(s) to data/price_history.csv
```

---

# 📉 Sample Price History

The repository includes:

```text
data/price_history.sample.csv
```

This contains a week of sample observations, allowing you to test the application without waiting for real historical data.

Example:

```csv
timestamp,product,url,price,currency
2026-01-06 09:00:04,Aurora X200 Headphones,https://demoshop.example/p/aurora-x200,174.50,USD
2026-01-07 09:00:03,Aurora X200 Headphones,https://demoshop.example/p/aurora-x200,149.99,USD
2026-01-08 09:00:02,Aurora X200 Headphones,https://demoshop.example/p/aurora-x200,149.99,USD
```

Example history output:

```text
TIMESTAMP            PRODUCT                 PRICE
-------------------  ----------------------  ----------
2026-01-04 09:00:05  Aurora X200 Headphones  189.99 USD
2026-01-05 09:00:02  Aurora X200 Headphones  189.99 USD
2026-01-06 09:00:04  Aurora X200 Headphones  174.50 USD
2026-01-07 09:00:03  Aurora X200 Headphones  149.99 USD
2026-01-08 09:00:02  Aurora X200 Headphones  149.99 USD

Aurora X200 Headphones:
5 checks | now 149.99 USD | min 149.99 | max 189.99
avg 170.89 | down 40.00 overall
```

---

# ⏱️ Scheduling

The built-in `watch` command is the simplest option:

```bash
python -m src.main watch -i 360
```

For checks that should survive application restarts and system reboots, use the operating system's scheduler.

### Windows

Use:

**Task Scheduler → Create Basic Task → Daily → Start a program**

Program:

```text
py
```

Arguments:

```text
-m src.main check
```

Start in:

```text
/path/to/PriceSentry
```

### macOS / Linux

Use:

```bash
crontab -e
```

Example:

```cron
0 9 * * * cd /path/to/PriceSentry && .venv/bin/python -m src.main check
```

---

# 📁 Project Structure

```text
PriceSentry/
│
├── src/
│   ├── main.py         # CLI: check / history / chart / watch / products
│   ├── scraper.py      # Fetch pages and extract prices
│   ├── logger.py       # Append-only CSV/JSON history
│   ├── alerts.py       # Threshold & drop detection
│   ├── chart.py        # Optional matplotlib charts
│   └── config.py       # Configuration loading & validation
│
├── data/
│   └── price history   # Gitignored runtime data
│
├── samples/
│   └── offline demo product pages
│
├── tests/
│   └── pytest test suite
│
├── config.json
├── config.example.json
├── requirements.txt
└── README.md
```

---

# 🧪 Testing

Run the complete test suite:

```bash
pytest
```

PriceSentry includes **96 tests** covering:

* Price parsing
* HTML extraction
* Storage
* Alert logic
* Configuration validation
* CLI behaviour
* End-to-end workflows

All tests use local fixture pages.

> The test suite never touches the network, making it fast and deterministic.

---

# 🛡️ Scraping Notes

PriceSentry is designed to monitor prices responsibly.

### Be polite

Avoid checking a website every few seconds.

A few checks per day are generally much more reasonable than aggressive polling.

### Respect website policies

Always check the website's terms of service before scraping.

Some retailers prohibit automated scraping and may use:

* CAPTCHA
* rate limiting
* bot detection
* request blocking

PriceSentry sends a normal browser User-Agent but **does not attempt to bypass bot protection**.

### Selectors can break

Websites change their HTML structure.

If a product suddenly stops working:

1. Inspect the product page again
2. Copy the new selector
3. Update `config.json`

If possible, try removing `selector` first and let PriceSentry use the metadata fallback.

### Price parsing

Price parsing is heuristic.

The following formats are supported:

```text
1.299,00  → 1299.00
1,299.00  → 1299.00
```

A single separator followed by exactly three digits is treated as a thousands separator:

```text
1,234 → 1234
1,23  → 1.23
```

### Append-only history

Price history is append-only.

Existing records are never rewritten, and corrupted lines are skipped instead of causing the entire history file to be discarded.

---

# 🔄 Data Pipeline

```text
┌──────────────┐
│ Product Page │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Scrape    │
│ requests +   │
│ BeautifulSoup│
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Parse Price  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ PriceRecord  │
│ + timestamp  │
└──────┬───────┘
       │
       ├───────────────┐
       ▼               ▼
┌──────────────┐ ┌──────────────┐
│ Price History│ │ Alert Engine │
│ CSV / JSON   │ │ threshold /  │
│              │ │ price drop   │
└──────┬───────┘ └──────┬───────┘
       │                 │
       ▼                 ▼
┌──────────────┐ ┌──────────────┐
│   Charts     │ │ Notifications│
│  matplotlib  │ │ console/email│
└──────────────┘ │   / desktop  │
                 └──────────────┘
```

---

# 🎯 Design Goals

PriceSentry was designed around a few principles:

* **Simple** — configuration instead of code changes
* **Reliable** — one failed product should not stop the entire run
* **Offline-testable** — tests never depend on external websites
* **Extensible** — CSV/JSON storage and multiple notification methods
* **Transparent** — historical data remains available for later analysis
* **Responsible** — no attempts to bypass bot protection

---

# 📄 License

This project is licensed under the **MIT License**.

---

<div align="center">

### 🛡️ PriceSentry

**Monitor prices. Catch drops. Buy smarter.**

Built with Python 🐍

</div>
