import json
from html import escape
from urllib.request import Request, urlopen
from urllib.parse import urlencode


def format_signal(s) -> str:
    def price(x):
        if x is None: return "—"
        return f"{x:.6f}" if abs(x) < 10 else f"{x:,.2f}"
    def number(x):
        if x is None: return "—"
        return f"{x:.2f}"
    def ratio(x): return "—" if x is None else f"{x:.2f}x"
    def spread(x): return "—" if x is None else f"{x:.3f}%"
    refinement = s.indicators.get("entry_refinement", {})
    def indicator_block(name, values):
        if name == "4h":
            return f"🕓 <b>4H</b>  EMA50 <code>{number(values.get('ema50'))}</code>  EMA200 <code>{number(values.get('ema200'))}</code>  {escape(str(values.get('structure', 'neutral')).upper())}"
        if name == "1h":
            return f"🕐 <b>1H</b>  EMA20 <code>{number(values.get('ema20'))}</code>  EMA50 <code>{number(values.get('ema50'))}</code>  RSI <code>{number(values.get('rsi'))}</code>  MACD <code>{number(values.get('macd'))}</code>  Hist <code>{number(values.get('macd_hist'))}</code>  Vol <code>{ratio(values.get('volume_ratio'))}</code>"
        return f"⏱ <b>15M</b>  ATR <code>{number(values.get('atr'))}</code>  Vol <code>{ratio(values.get('volume_ratio'))}</code>  TR z <code>{number(values.get('tr_zscore'))}</code>"
    styles = {"LONG": "🟢", "SHORT": "🔴", "NO TRADE": "⚪"}
    indicator_text = "\n".join(indicator_block(k, v) for k, v in s.indicators.items())
    reasons = "\n".join(f"• {escape(reason)}" for reason in s.rejection_reasons) or "• All conditions aligned"
    timestamp = s.timestamp_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    return (f"{styles.get(s.signal.value, 'ℹ️')} <b>{escape(s.symbol)}  |  {escape(s.signal.value)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Price</b>  <code>{price(s.price)}</code>\n"
            f"🎯 <b>Entry</b>  <code>{price(s.entry_low)} — {price(s.entry_high)}</code>\n"
            f"🛑 <b>Stop</b>  <code>{price(s.stop_loss)}</code>    ✅ <b>Target</b>  <code>{price(s.take_profit)}</code>\n"
            f"📐 <b>Risk / reward</b>  <code>{number(s.risk_reward)}</code>\n"
            f"📋 <b>Profile</b>  <code>{escape(s.profile)}</code>\n"
            f"🧮 <b>Conditions</b>  <code>{s.condition_score}/10</code>\n"
            f"↔️ <b>Spread</b>  <code>{spread(s.spread_percent)}</code>\n"
            f"🔍 <b>5M refinement</b>  <code>{escape(str(refinement.get('status', 'not_configured')))}</code>\n"
            f"🧭 <b>Aligned</b>  {escape(' · '.join(s.aligned_timeframes) or '—')}\n\n"
            f"📊 <b>Indicators</b>\n{indicator_text}\n\n"
            f"📝 <b>Why</b>\n{reasons}\n\n"
            f"🕒 <i>{timestamp}</i>")


class TelegramNotifier:
    def __init__(self, settings): self.settings = settings
    def send(self, signal):
        return self.send_text(format_signal(signal))

    def send_text(self, message: str):
        data = urlencode({"chat_id": self.settings.telegram_chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
        request = Request(f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage", data=data, method="POST")
        with urlopen(request, timeout=self.settings.request_timeout_ms / 1000) as response:
            body = json.loads(response.read())
        if not body.get("ok"): raise RuntimeError(body)
        return str(body["result"]["message_id"])

