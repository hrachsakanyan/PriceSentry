# PriceSentry

**Track product prices over time and get alerted when they drop.**

PriceSentry scrapes the price of the products you care about, appends every
observation to a timestamped log, and alerts you when a price crosses below the
threshold you set. Run it by hand, or leave `watch` running and forget about it.

It is a small, complete data-collection pipeline: **scrape → persist → analyse →
alert**. The log it builds up is plain CSV (or JSON), so anything you learn later
about data analysis can be pointed straight at it.

---

## How it works

```
                    config.json
                 (products, selectors,
                  thresholds, interval)
                          │
                          ▼
   ┌──────────────────────────────────────────────┐
   │  scraper.py                                  │
   │  fetch page ──► parse price ──► PriceRecord  │
   │  (requests)     (BeautifulSoup) (timestamped)│
   └──────────────────────────────────────────────┘
                          │
              ┌───────────┴────────────┐
              ▼                        ▼
   ┌──────────────────┐     ┌────────────────────────┐
   │  logger.py       │     │  alerts.py             │
   │  append to       │     │  compare to threshold  │
   │  price_history   │     │  and to last price     │
   │  .csv / .json    │     └────────────────────────┘
   └──────────────────┘                 │
              │              ┌──────────┼──────────┐
              ▼              ▼          ▼          ▼
     history / chart     console     desktop     email
```

Each check reads the *previous* recorded price for the product, so PriceSentry
knows the difference between "cheap today" and "just got cheaper".

---

## Features

**Core**

- **Scrape a price** from any product page — CSS selector, or automatic fallback
  to the `product:price:amount` meta tags and JSON-LD `offers` that most shops embed
- **Timestamped history log** — append-only CSV (or JSON), one row per observation
- **Threshold alerts** — fires when the price *crosses* below your threshold, not
  every single run while it sits there
- **View price history** — table or JSON, per product or all, with min / max /
  average / overall change

**Also included**

- **Multiple products** in one config file
- **Price-drop alerts** independent of the threshold ("cheaper than last time")
- **Price chart** — PNG line chart of price over time (`matplotlib`)
- **Scheduler** — `watch` keeps checking on an interval
- **Desktop notifications** (`plyer`) and **email notifications** (SMTP)
- **Config file** — add a product without touching a line of code
- Handles international price formats: `$1,299.00`, `1.299,00 €`, `1 234,50 AMD`
- Retries on network failure; one broken product never stops the others

---

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/<your-username>/PriceSentry.git
cd PriceSentry

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
```

Only `requests` and `beautifulsoup4` are strictly required. `matplotlib` (charts),
`plyer` (desktop notifications) and `lxml` (faster parsing) are optional — the
matching feature degrades with a clear message if they are missing.

### Configure your products

`config.json` ships with two offline demo products so you can try it immediately.
Replace them with your own:

```json
{
  "storage": { "path": "data/price_history.csv" },
  "schedule": { "interval_minutes": 360 },
  "alerts": {
    "notify_on_drop": true,
    "desktop": false,
    "email": { "enabled": false }
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

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Label used in the log, alerts and `--product` |
| `url` | yes | Product page URL (a local `.html` path also works) |
| `selector` | no | CSS selector for the price element. Omit it to let PriceSentry try the page's price metadata |
| `threshold` | no | Alert when the price drops to or below this |
| `currency` | no | Force a currency code instead of detecting it |

**Finding a selector:** open the product page, right-click the price →
*Inspect* → right-click the highlighted element → *Copy → Copy selector*.
Trim it down to something stable like `.price-now` or `#priceblock_ourprice`.

Set `"storage": {"path": "data/price_history.json"}` to log JSON instead of CSV —
the format follows the file extension.

---

## Usage

```bash
python -m src.main check                    # scrape every product now, log, alert
python -m src.main check -p "Headphones"    # just one product
python -m src.main history                  # full history + summary stats
python -m src.main history -p "Headphones" -n 10
python -m src.main history --json           # machine-readable output
python -m src.main chart                    # data/price_chart.png
python -m src.main chart -p "Headphones" -o mychart.png
python -m src.main products                 # what is tracked + last seen price
python -m src.main watch -i 60              # check every 60 minutes
python -m src.main -c other.json check      # use a different config file
```

On Windows, use `py -m src.main ...` if `python` is not on your PATH.

Example run:

```
$ python -m src.main check
Checking 2 product(s) at 2026-01-07 09:00:03
  Aurora X200 Headphones: 149.99 USD  (threshold 160.00, price <= threshold)
      down 24.51 since 2026-01-06 09:00

  [!] Price alert: Aurora X200 Headphones
      Aurora X200 Headphones is now 149.99 USD, below your threshold of 160.00 USD.
      https://demoshop.example/p/aurora-x200
  Nimbus 68 Keyboard: 89.50 USD  (threshold 75.00, price > threshold)

Logged 2 price(s) to data/price_history.csv
```

### Scheduling

`watch` is the simplest option and needs nothing extra. For a check that survives
reboots, hand a single `check` run to your OS scheduler instead:

- **Windows** — Task Scheduler → Create Basic Task → daily → *Start a program*:
  program `py`, arguments `-m src.main check`, start-in your project folder.
- **macOS / Linux** — `crontab -e`, then:
  `0 9 * * * cd /path/to/PriceSentry && .venv/bin/python -m src.main check`

### Notifications

Desktop toasts: `pip install plyer`, then set `"desktop": true` under `alerts`.

Email: fill in `alerts.email` and put the password in the environment — it is
never stored in the config file.

```json
"email": {
  "enabled": true,
  "host": "smtp.gmail.com",
  "port": 587,
  "sender": "you@gmail.com",
  "recipients": ["you@gmail.com"],
  "password_env": "PRICESENTRY_SMTP_PASSWORD"
}
```

```powershell
$env:PRICESENTRY_SMTP_PASSWORD = "your-app-password"   # Windows
export PRICESENTRY_SMTP_PASSWORD="your-app-password"   # macOS / Linux
```

Gmail requires an [app password](https://support.google.com/accounts/answer/185833),
not your normal account password.

---

## Sample data

[`data/price_history.sample.csv`](data/price_history.sample.csv) contains a week
of recorded prices so you can see the output format without waiting a week:

```csv
timestamp,product,url,price,currency
2026-01-06 09:00:04,Aurora X200 Headphones,https://demoshop.example/p/aurora-x200,174.50,USD
2026-01-07 09:00:03,Aurora X200 Headphones,https://demoshop.example/p/aurora-x200,149.99,USD
2026-01-08 09:00:02,Aurora X200 Headphones,https://demoshop.example/p/aurora-x200,149.99,USD
```

```
$ python -m src.main history -p "Aurora X200 Headphones" -n 5
TIMESTAMP            PRODUCT                 PRICE
-------------------  ----------------------  ----------
2026-01-04 09:00:05  Aurora X200 Headphones  189.99 USD
2026-01-05 09:00:02  Aurora X200 Headphones  189.99 USD
2026-01-06 09:00:04  Aurora X200 Headphones  174.50 USD
2026-01-07 09:00:03  Aurora X200 Headphones  149.99 USD
2026-01-08 09:00:02  Aurora X200 Headphones  149.99 USD

Aurora X200 Headphones: 5 checks | now 149.99 USD | min 149.99 | max 189.99 | avg 170.89 | down 40.00 overall
```

---

## Project structure

```
PriceSentry/
├── src/
│   ├── main.py         CLI: check / history / chart / watch / products
│   ├── scraper.py      fetching pages and parsing prices out of HTML
│   ├── logger.py       append-only CSV/JSON price history
│   ├── alerts.py       threshold & drop detection, console/desktop/email
│   ├── chart.py        optional matplotlib chart
│   └── config.py       config loading and validation
├── data/               your price log lives here (gitignored)
├── samples/            offline demo product pages
├── tests/              pytest suite, fully offline
├── config.json         your tracked products
├── config.example.json annotated template
└── requirements.txt
```

## Tests

```bash
pytest
```

96 tests covering price parsing, HTML extraction, storage, alert logic, config
validation and the CLI end to end. Every test runs against local fixture pages —
the suite never touches the network, so it is fast and deterministic.

---

## Notes

- **Be polite.** Check a product a few times a day, not every minute. Scraping
  aggressively gets your IP blocked and is rude to the shop's servers.
- **Read the site's terms.** Some sites prohibit scraping; many large retailers
  (Amazon in particular) actively block automated requests and serve CAPTCHAs.
  PriceSentry sends a normal browser User-Agent but does not attempt to defeat
  bot protection.
- **Selectors break.** Shops redesign their pages. If a product starts failing,
  re-copy the selector. The metadata fallback is often more durable than a class
  name — try omitting `selector` first.
- **Prices are parsed heuristically.** Both `1.299,00` and `1,299.00` are read as
  1299.00. A single separator followed by exactly three digits is treated as a
  thousands separator, so `1,234` is 1234 and `1,23` is 1.23.
- The history log is append-only: nothing is ever rewritten, and corrupt lines are
  skipped rather than discarding the whole file.

## License

MIT
