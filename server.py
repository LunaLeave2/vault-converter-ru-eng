from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from fastapi import FastAPI, Request, Form, Query
from fastapi.templating import Jinja2Templates
from converter.core import ConverterCore, parse_pair

app = FastAPI()
templates = Jinja2Templates(directory="templates")
core = ConverterCore(db_path="rates.sqlite3")

def style_vars(font_px:int, bg:str, text:str, accent:str, border:str, radius_px:int) -> str:
    return (
        f"--cc-font:{font_px}px; "
        f"--cc-bg:{bg}; --cc-text:{text}; --cc-accent:{accent}; "
        f"--cc-border:{border}; --cc-radius:{radius_px}px;"
    )

@app.get("/")
async def index(
    request: Request,
    lang: str = Query("ru"),
    font: int = Query(16, ge=10, le=24),
    bg: str = Query("#ffffff"),
    text: str = Query("#111827"),
    accent: str = Query("#0ea5e9"),
    border: str = Query("#e5e7eb"),
    radius: int = Query(16, ge=0, le=32),
):
    def style_vars(font_px, bg, text, accent, border, radius_px):
        return (
            f"--cc-font:{font_px}px; --cc-bg:{bg}; --cc-text:{text}; "
            f"--cc-accent:{accent}; --cc-border:{border}; --cc-radius:{radius_px}px;"
        )
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "lang": "ru" if lang not in ("ru", "en") else lang,
            "style_inline": style_vars(font, bg, text, accent, border, radius),
            "result": None,
            "error": None,
            "form": {"base": "", "quote": "", "amount": "", "pair": ""},
        },
    )

@app.post("/convert")
async def convert(
    request: Request,
    lang: str = Form("ru"),
    base: str = Form(""),
    quote: str = Form(""),
    amount: str = Form(""),
    pair: str = Form(""),
    font: int = Form(16),
    bg: str = Form("#ffffff"),
    text: str = Form("#111827"),
    accent: str = Form("#0ea5e9"),
    border: str = Form("#e5e7eb"),
    radius: int = Form(16),
):
    def style_vars(font_px, bg, text, accent, border, radius_px):
        return (
            f"--cc-font:{font_px}px; --cc-bg:{bg}; --cc-text:{text}; "
            f"--cc-accent:{accent}; --cc-border:{border}; --cc-radius:{radius_px}px;"
        )

    lang = "ru" if lang not in ("ru","en") else lang
    ctx = {
        "request": request,
        "lang": lang,
        "style_inline": style_vars(font, bg, text, accent, border, radius),
        "result": None,
        "error": None,
        "form": {"base": base, "quote": quote, "amount": amount, "pair": pair},
    }

    try:
        #приоритет
        if pair.strip():
            a, b = parse_pair(pair.strip())
        else:
            a, b = base.strip(), quote.strip()
            if len(a) < 3 or len(b) < 3:
                raise ValueError("Укажите обе валюты" if lang=="ru" else "Provide both currencies")

        cleaned = (amount.replace(" ", "").replace("\u00a0","").replace("_","").replace(",", "."))
        if not cleaned:
            raise InvalidOperation
        amt = Decimal(cleaned)
        if amt <= 0:
            raise InvalidOperation

        res = core.convert(a, b, amt)
        q3 = lambda x: x.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        q6 = lambda x: x.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

        def fmt(num, loc):
            s = f"{num:,.3f}"
            return s.replace(",", " ").replace(".", ",") if loc=="ru" else s

        ctx["result"] = {
            "amount_fmt": fmt(q3(res.amount), lang),
            "result_fmt": fmt(q3(res.result), lang),
            "rate_fmt": (str(q6(res.rate)) if lang=="en"
                         else str(q6(res.rate)).replace(".", ",")),
            "base": res.base, "quote": res.quote,
            "updated": res.fetched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "source": res.source,
        }
    except InvalidOperation:
        ctx["error"] = "Некорректная сумма" if lang=="ru" else "Invalid amount"
    except Exception as e:
        ctx["error"] = str(e)

    return templates.TemplateResponse("index.html", ctx)
