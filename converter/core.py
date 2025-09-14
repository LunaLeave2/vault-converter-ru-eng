from __future__ import annotations
from dataclasses import dataclass
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
import sqlite3
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from urllib.request import urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s %(name)s: %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


NAME_ALIASES: Dict[str, str] = {
    #Фиат
    "usd": "USD", "dollar": "USD", "us dollar": "USD", "$": "USD",
    "eur": "EUR", "euro": "EUR", "€": "EUR",
    "gbp": "GBP", "pound": "GBP", "sterling": "GBP",
    "jpy": "JPY", "yen": "JPY",
    "cny": "CNY", "yuan": "CNY", "rmb": "CNY",
    "rub": "RUB", "ruble": "RUB", "rouble": "RUB",
    "kzt": "KZT", "tenge": "KZT",
    "try": "TRY", "lira": "TRY",
    "chf": "CHF", "franc": "CHF",
    "uah": "UAH", "hryvnia": "UAH",
    "kgs": "KGS", "krs": "KGS", "som": "KGS",
    "inr": "INR", "rupee": "INR",
    "aed": "AED", "dirham": "AED",
    "cad": "CAD", "canadian dollar": "CAD",
    "aud": "AUD", "australian dollar": "AUD",
    "nok": "NOK", "sek": "SEK", "dkk": "DKK",
    "pln": "PLN", "zloty": "PLN",
    "huf": "HUF", "forint": "HUF",
    "brl": "BRL", "real": "BRL",
    "mxn": "MXN", "peso": "MXN",
    "zar": "ZAR", "rand": "ZAR",
    "krw": "KRW", "won": "KRW",
    "tjs": "TJS", "mdl": "MDL", "amd": "AMD",
    "thb": "THB", "myr": "MYR", "ringgit": "MYR",
    "gel": "GEL", "ils": "ILS", "shekel": "ILS",
    "доллар": "USD", "американский доллар": "USD",
    "евро": "EUR",
    "фунт": "GBP", "фунт стерлингов": "GBP",
    "йена": "JPY", "иена": "JPY",
    "юань": "CNY",
    "рубль": "RUB", "руб": "RUB", "₽": "RUB",
    "тенге": "KZT",
    "лира": "TRY",
    "франк": "CHF",
    "гривна": "UAH", "ривна": "UAH",
    "сом": "KGS",
    "рупия": "INR",
    "дирхам": "AED",
    "злотый": "PLN", "форинт": "HUF",
    "реал": "BRL",
    "песо": "MXN",
    "ранд": "ZAR",
    "вона": "KRW", "вон": "KRW",
    "сомони": "TJS", "лей": "MDL", "драм": "AMD",
    "бат": "THB", "ринггит": "MYR",
    "лари": "GEL", "шекель": "ILS",
    "крона": "SEK", "кроны": "SEK", "норвежская крона": "NOK",
    "датская крона": "DKK",
    "австралийский доллар": "AUD",
    "канадский доллар": "CAD",
    # Крипта — коды (верхний регистр) и синонимы
    "btc": "BTC", "bitcoin": "BTC", "биткоин": "BTC", "биток": "BTC",
    "eth": "ETH", "ethereum": "ETH", "эфир": "ETH",
    "usdt": "USDT", "tether": "USDT", "тезер": "USDT", "тетер": "USDT",
    "usdc": "USDC", "usd coin": "USDC",
    "bnb": "BNB",
    "xrp": "XRP",
    "ada": "ADA", "cardano": "ADA",
    "sol": "SOL", "solana": "SOL",
    "trx": "TRX", "tron": "TRX",
    "doge": "DOGE", "dogecoin": "DOGE", "додж": "DOGE",
    "ton": "TON", "тон": "TON", "toncoin": "TON", "the open network": "TON",
    "dot": "DOT", "polkadot": "DOT",
    "link": "LINK", "chainlink": "LINK",
    "ltc": "LTC", "litecoin": "LTC",
    "bch": "BCH", "bitcoin cash": "BCH",
    "avax": "AVAX", "avalanche": "AVAX",
    "xmr": "XMR", "monero": "XMR",
    "etc": "ETC", "ethereum classic": "ETC",
    "atom": "ATOM", "cosmos": "ATOM",
    "near": "NEAR",
    "matic": "MATIC", "polygon": "MATIC",
    "dai": "DAI",
}

# Карта тикер -> id в CoinGecko
COINGECKO_IDS: Dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "SOL": "solana",
    "TRX": "tron",
    "DOGE": "dogecoin",
    "TON": "the-open-network",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "AVAX": "avalanche-2",
    "XMR": "monero",
    "ETC": "ethereum-classic",
    "ATOM": "cosmos",
    "NEAR": "near",
    "MATIC": "matic-network",
    "DAI": "dai",
}

# ------------------------- Модель результата -------------------------

@dataclass
class ConversionResult:
    base: str
    quote: str
    amount: Decimal
    rate: Decimal
    result: Decimal
    fetched_at: datetime
    source: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _as_epoch(dt: datetime) -> int:
    return int(dt.timestamp())

def _from_epoch(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)

def normalize_code(name_or_code: str) -> str:
    s = (name_or_code or "").strip().lower()
    if not s:
        raise ValueError("Пустое название валюты")
    if len(s) == 3 and s.isalpha():
        return s.upper()
    return NAME_ALIASES.get(s) or (s.upper() if len(s) == 3 else NAME_ALIASES.get(s, ""))

def parse_pair(pair: str) -> Tuple[str, str]:
    if not pair or not pair.strip():
        raise ValueError("Строка с валютами пуста")

    s = pair.strip()
    s = re.sub(r"[–—]+", "-", s)
    s = re.sub(r"\s+", " ", s)

    parts = re.split(r"\s*[-/\\→]+\s*|\s+(?:to|в)\s+", s, maxsplit=1, flags=re.I)

    if len(parts) != 2:
        toks = s.split(" ")
        if len(toks) == 2:
            parts = toks
        else:
            raise ValueError("Укажите две валюты, например: 'RUB - USD' или 'RUB USD'")

    a, b = parts[0].strip(), parts[1].strip()
    code_a = normalize_code(a)
    code_b = normalize_code(b)
    if not code_a or not code_b:
        raise ValueError(f"Не удалось распознать валюты из строки: '{pair}'")
    return code_a, code_b


def _fetch_json(url: str, timeout: float = 10.0) -> dict:
    with urlopen(url, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))

def fetch_fiat_usd_from_ecb() -> Dict[str, Decimal]:
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
    with urlopen(url, timeout=10.0) as resp:
        content = resp.read()
    root = ET.fromstring(content)
    #элементы <Cube currency="XXX" rate="N.NNNN">
    eur_to: Dict[str, Decimal] = {}
    for cube in root.iter():
        c = cube.attrib.get("currency")
        r = cube.attrib.get("rate")
        if c and r:
            eur_to[c.upper()] = Decimal(str(r))
    eur_to["EUR"] = Decimal("1")
    if "USD" not in eur_to:
        raise RuntimeError("В ответе ЕЦБ нет USD")
    #USD->X = (EUR->X) / (EUR->USD)
    eur_to_usd = eur_to["USD"]
    usd_to: Dict[str, Decimal] = {sym: (rate / eur_to_usd) for sym, rate in eur_to.items()}
    usd_to["USD"] = Decimal("1")
    return usd_to

def fetch_crypto_usd_from_coingecko(symbols: List[str]) -> Dict[str, Decimal]:
    ids = [COINGECKO_IDS[sym] for sym in symbols if sym in COINGECKO_IDS]
    if not ids:
        return {}
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies=usd"
    data = _fetch_json(url)
    result: Dict[str, Decimal] = {}
    for sym, cid in COINGECKO_IDS.items():
        obj = data.get(cid)
        if not obj:
            continue
        price = obj.get("usd")
        if price is None:
            continue
        # USD->COIN = 1 / (USD per COIN)
        try:
            result[sym] = (Decimal("1") / Decimal(str(price)))
        except Exception:
            continue
    return result

def fetch_usd_rates() -> Tuple[Dict[str, Decimal], str]:
    source_parts: List[str] = []
    rates: Dict[str, Decimal] = {}

    #Фиат
    try:
        fiat = fetch_fiat_usd_from_ecb()
        rates.update(fiat)
        source_parts.append("ECB")
    except Exception as e:
        logger.warning("ЕЦБ недоступен: %s", e)
        try:
            data = _fetch_json("https://api.frankfurter.app/latest?from=USD")
            if "rates" in data:
                for k, v in data["rates"].items():
                    rates[k.upper()] = Decimal(str(v))
                rates["USD"] = Decimal("1")
                source_parts.append("Frankfurter(ECB)")
        except Exception as e2:
            logger.warning("Резервный провайдер недоступен: %s", e2)

    try:
        crypto_list = list(COINGECKO_IDS.keys())
        crypto = fetch_crypto_usd_from_coingecko(crypto_list)
        if crypto:
            rates.update(crypto)
            source_parts.append("CoinGecko")
    except Exception as e:
        logger.warning("CoinGecko недоступен: %s", e)

    if not rates:
        raise RuntimeError("Не удалось получить курсы ни от одного провайдера")

    rates["USD"] = Decimal("1")
    return rates, "+".join(source_parts) if source_parts else "unknown"


DDL = """
CREATE TABLE IF NOT EXISTS rates (
    base       TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    rate       TEXT NOT NULL,
    fetched_at INTEGER NOT NULL,
    source     TEXT NOT NULL,
    PRIMARY KEY (base, symbol)
);
CREATE INDEX IF NOT EXISTS idx_rates_fetched ON rates(base, fetched_at);
"""

def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()

def _last_fetch_meta(conn: sqlite3.Connection, base: str) -> Optional[Tuple[int, str]]:
    cur = conn.execute(
        "SELECT fetched_at, source FROM rates WHERE base=? ORDER BY fetched_at DESC LIMIT 1",
        (base,)
    )
    row = cur.fetchone()
    return (row[0], row[1]) if row else None

def _upsert_rates(conn: sqlite3.Connection, base: str, rates: Dict[str, Decimal], source: str, fetched_at: datetime) -> None:
    ts = _as_epoch(fetched_at)
    rows = [(base, sym, str(val), ts, source) for sym, val in rates.items()]
    conn.executemany(
        "INSERT OR REPLACE INTO rates(base, symbol, rate, fetched_at, source) VALUES(?,?,?,?,?)",
        rows
    )
    conn.commit()

def _get_two_rates(conn: sqlite3.Connection, base: str, a: str, b: str) -> Dict[str, Decimal]:
    cur = conn.execute(
        "SELECT symbol, rate FROM rates WHERE base=? AND symbol IN (?, ?)",
        (base, a, b),
    )
    res = {row[0]: Decimal(row[1]) for row in cur.fetchall()}
    if a == base and base not in res:
        res[base] = Decimal("1")
    if b == base and base not in res:
        res[base] = Decimal("1")
    return res


class ConverterCore:
    def __init__(self, db_path: str | Path = "rates.sqlite3", ref_base: str = "USD", auto_update_age_hours: int = 12) -> None:
        self.db_path = Path(db_path)
        self.ref_base = ref_base.upper()
        self.auto_update_age = timedelta(hours=auto_update_age_hours)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        _init_db(self.conn)

        meta = _last_fetch_meta(self.conn, self.ref_base)
        if meta is None:
            logger.info("Первая инициализация БД — загружаем курсы %s", self.ref_base)
            self.update_rates(force=True)

    def update_rates(self, force: bool = False) -> None:
        with self.lock:
            meta = _last_fetch_meta(self.conn, self.ref_base)
            need = True
            if meta and not force:
                last_dt = _from_epoch(meta[0])
                age = _utcnow() - last_dt
                need = age >= self.auto_update_age

        if need:
            rates, source = fetch_usd_rates() if self.ref_base == "USD" else fetch_usd_like_base(self.ref_base)
            now = _utcnow()
            with self.lock:
                _upsert_rates(self.conn, self.ref_base, rates, source=source, fetched_at=now)
            logger.info("Курсы обновлены (%s), записей: %d", source, len(rates))
        else:
            logger.info("Курсы актуальны, обновление не требуется")

    def convert(self, from_code: str, to_code: str, amount: Decimal = Decimal("1")) -> ConversionResult:
        a = normalize_code(from_code)
        b = normalize_code(to_code)
        if not a or not b:
            raise ValueError("Не удалось распознать коды валют")

        self.update_rates(force=False)

        with self.lock:
            rates = _get_two_rates(self.conn, self.ref_base, a, b)
            meta = _last_fetch_meta(self.conn, self.ref_base)

        missing = [sym for sym in (a, b) if sym != self.ref_base and sym not in rates]
        if missing:
            logger.info("В БД нет курсов для %s — выполняю принудительное обновление…", ", ".join(missing))
            self.update_rates(force=True)
            with self.lock:
                rates = _get_two_rates(self.conn, self.ref_base, a, b)
                meta = _last_fetch_meta(self.conn, self.ref_base)
            missing = [sym for sym in (a, b) if sym != self.ref_base and sym not in rates]
            if missing:
                raise ValueError(f"Курс(ы) {', '.join(missing)!r} недоступен(ы) у провайдера")

        if a == b:
            rate = Decimal("1")
        elif a == self.ref_base:
            rate = rates[b]
        elif b == self.ref_base:
            rate = (Decimal("1") / rates[a])
        else:
            rate = (rates[b] / rates[a])

        result_amount = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        fetched_at = _from_epoch(meta[0]) if meta else _utcnow()
        source = meta[1] if meta else "unknown"

        return ConversionResult(base=a, quote=b, amount=amount, rate=rate, result=result_amount, fetched_at=fetched_at,
                                source=source)

    def convert_pair_string(self, pair: str, amount: Decimal = Decimal("1")) -> Dict[str, object]:
        a, b = parse_pair(pair)
        res = self.convert(a, b, amount=amount)
        return {
            "base": res.base,
            "quote": res.quote,
            "amount": str(res.amount),
            "rate": str(res.rate),
            "result": str(res.result),
            "fetched_at": res.fetched_at.isoformat(),
            "source": res.source,
        }

    def close(self) -> None:
        with self.lock:
            try:
                self.conn.close()
            except Exception:
                pass


def fetch_usd_like_base(base: str) -> Tuple[Dict[str, Decimal], str]:
    base = base.upper()
    try:
        data = _fetch_json(f"https://api.frankfurter.app/latest?from={base}")
        if "rates" in data and isinstance(data["rates"], dict):
            rates = {k.upper(): Decimal(str(v)) for k, v in data["rates"].items()}
            rates[base] = Decimal("1")
            return rates, "Frankfurter(ECB)"
    except Exception as e:
        logger.warning("Не удалось получить курсы для базы %s: %s", base, e)

    # fallback
    usd_rates, src = fetch_usd_rates()
    if base not in usd_rates:
        raise RuntimeError(f"Невозможно построить базу {base}: нет курса к USD")
    converted: Dict[str, Decimal] = {sym: (val / usd_rates[base]) for sym, val in usd_rates.items()}
    converted[base] = Decimal("1")
    return converted, f"{src} (via USD)"

if __name__ == "__main__":
    core = ConverterCore()
    print(core.convert_pair_string("usd-eur"))
    print(core.convert_pair_string("usd-btc"))
    print(core.convert_pair_string("btc-eth", amount=Decimal("0.5")))
    core.close()
