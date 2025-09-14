# app.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from converter.core import ConverterCore, parse_pair


def choose_language() -> str:
    while True:
        lang = input("Choose language: русский/english (ru/eng): ").strip().lower()
        if lang in {"ru", "eng"}:
            return lang
        print("Please type 'ru' or 'eng' / Пожалуйста, введите 'ru' или 'eng'.")


def ask_pair(lang: str) -> str:
    if lang == "ru":
        return input('Введите валюты в формате, например: "RUB - USD": ').strip()
    return input('Enter currencies like: "RUB - USD": ').strip()


def ask_amount(lang: str) -> Decimal:
    while True:
        prompt = "Введите сумму: " if lang == "ru" else "Enter amount: "
        raw = input(prompt).strip()
        try:
            cleaned = (
                raw.replace(" ", "")
                   .replace("\u00a0", "")
                   .replace("_", "")
                   .replace(",", ".")
            )
            amount = Decimal(cleaned)
            if amount <= 0:
                raise InvalidOperation
            return amount
        except InvalidOperation:
            if lang == "ru":
                print("Некорректная сумма, попробуйте ещё раз.")
            else:
                print("Invalid amount, try again.")


def q3(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def main() -> None:
    lang = choose_language()
    pair = ask_pair(lang)
    amount = ask_amount(lang)

    core = ConverterCore(db_path="rates.sqlite3", auto_update_age_hours=12)
    try:
        a, b = parse_pair(pair)
        res = core.convert(a, b, amount=amount)

        result_3 = q3(res.result)
        rate_6 = res.rate.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        fetched_local = res.fetched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")

        if lang == "ru":
            print(f"{q3(amount)} {res.base} = {result_3} {res.quote}")
            print(f"Курс: {rate_6} | Обновлено: {fetched_local} | Источник: {res.source}")
        else:
            print(f"{q3(amount)} {res.base} = {result_3} {res.quote}")
            print(f"Rate: {rate_6} | Updated: {fetched_local} | Source: {res.source}")

    except Exception as e:
        print(("Ошибка: " if lang == "ru" else "Error: ") + str(e))
    finally:
        core.close()


if __name__ == "__main__":
    main()
