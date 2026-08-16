"""
Avto-huquq Telegram boti - WEBHOOK + TUGMALI MENYU versiyasi
--------------------------------------------------------------
Bepul hostingda (Render.com) 24/7 ishlaydi. Hech qanday pullik AI API
ishlatilmaydi - faqat kalit so'z qidiruvi + Telegram inline tugmalari.

Muhit o'zgaruvchilari (Render dashboard'da "Environment" bo'limida):
    BOT_TOKEN - BotFather'dan olingan token
"""

import json
import os
import re

import requests
from flask import Flask, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")

BOT_TOKEN = os.environ["BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

with open(KB_PATH, "r", encoding="utf-8") as f:
    KB = json.load(f)

CATEGORIES = KB["kategoriyalar"]
APOSTROPHE_PATTERN = re.compile(r"[ʻʼ`´']")

# Tez tugmalar uchun: (kategoriya_indeksi, tugma_matni)
QUICK_TOPICS = [
    (8, "🚓 Tezlik"),
    (3, "🚦 Svetofor"),
    (2, "📄 Sug'urta"),
    (1, "🪪 Hujjat"),
    (4, "🅿️ Parkovka"),
    (5, "📱 Telefon"),
    (11, "🍺 Mast holda"),
    (18, "⏳ To'lash muddati"),
    (19, "💸 Chegirma"),
    (20, "⚖️ Shikoyat"),
]


def normalize(text: str) -> str:
    text = text.lower()
    text = APOSTROPHE_PATTERN.sub("'", text)
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return text


def find_matches(user_text: str, top_n: int = 3):
    norm_text = normalize(user_text)
    scored = []
    for cat in CATEGORIES:
        score = sum(1 for kw in cat["kalit_sozlar"] if normalize(kw) in norm_text)
        if score > 0:
            scored.append((score, cat))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [cat for _, cat in scored[:top_n]]


def format_category(cat: dict) -> str:
    lines = [f"📌 {cat['mavzu']}"]
    if cat.get("modda") and cat["modda"] != "-":
        lines.append(f"Modda: {cat['modda']}")
    if cat.get("tavsif"):
        lines.append(f"Tavsif: {cat['tavsif']}")
    if cat.get("jarima") and cat["jarima"] != "-":
        lines.append(f"Jarima: {cat['jarima']}")
    if cat.get("izoh"):
        lines.append(f"Izoh: {cat['izoh']}")
    return "\n".join(lines)


DISCLAIMER = (
    "\n\n⚠️ Bu ma'lumot umumiy yo'nalish uchun, rasmiy yuridik maslahat emas. "
    "Aniq holatlar uchun lex.uz yoki malakali yuristga murojaat qiling."
)

NOT_FOUND_MESSAGE = (
    "Kechirasiz, muammoingizga mos qoidani topa olmadim. 🤔\n\n"
    "Iltimos, kalit so'z bilan yozib ko'ring yoki pastdagi tugmalardan "
    "birini tanlang."
    + DISCLAIMER
)

START_MESSAGE = (
    "Salom! Men avto-huquq bo'yicha yordamchi botman. 🚗\n\n"
    "Pastdagi tugmalardan birini tanlang yoki muammoingizni o'z so'zlaringiz "
    "bilan yozing - masalan:\n"
    "• \"tezlikni oshirib qoldim\"\n"
    "• \"sug'urta yo'q\"\n"
    "• \"svetoforda qizil chiroqda o'tib qoldim\"\n\n"
    "⚠️ Eslatma: men rasmiy yurist emasman, javoblarim umumiy yo'nalish "
    "uchun. Muhim holatlarda malakali yuristga murojaat qiling."
)


def main_menu_keyboard() -> dict:
    """Tez-tez so'raladigan mavzular uchun 2 ustunli tugmalar paneli."""
    rows = []
    for i in range(0, len(QUICK_TOPICS), 2):
        row = []
        for idx, label in QUICK_TOPICS[i:i + 2]:
            row.append({"text": label, "callback_data": f"topic_{idx}"})
        rows.append(row)
    return {"inline_keyboard": rows}


def back_to_menu_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": "🔙 Bosh menyu", "callback_data": "menu_main"}]]}


def send_message(chat_id: int, text: str, reply_markup: dict = None) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)


def answer_callback_query(callback_query_id: str) -> None:
    requests.post(
        f"{TELEGRAM_API}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id},
        timeout=10,
    )


@app.route("/", methods=["GET"])
def health_check():
    # Render/UptimeRobot kabi xizmatlar shu manzilga so'rov yuborib turishi
    # mumkin - bu bot uxlab qolishini kamaytiradi.
    return "Bot ishlayapti.", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}

    # --- Tugma bosilganda ---
    callback_query = update.get("callback_query")
    if callback_query:
        answer_callback_query(callback_query["id"])
        chat_id = callback_query["message"]["chat"]["id"]
        data = callback_query.get("data", "")

        if data == "menu_main":
            send_message(chat_id, START_MESSAGE, reply_markup=main_menu_keyboard())
        elif data.startswith("topic_"):
            try:
                idx = int(data.split("_", 1)[1])
                cat = CATEGORIES[idx]
                reply = format_category(cat) + DISCLAIMER
                send_message(chat_id, reply, reply_markup=back_to_menu_keyboard())
            except (ValueError, IndexError):
                send_message(chat_id, NOT_FOUND_MESSAGE, reply_markup=main_menu_keyboard())
        return "ok", 200

    # --- Oddiy matnli xabar ---
    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return "ok", 200

    chat_id = message["chat"]["id"]
    text = message["text"]

    if text.strip() in ("/start", "/help", "/menu"):
        send_message(chat_id, START_MESSAGE, reply_markup=main_menu_keyboard())
        return "ok", 200

    matches = find_matches(text)
    if not matches:
        send_message(chat_id, NOT_FOUND_MESSAGE, reply_markup=main_menu_keyboard())
        return "ok", 200

    reply = "\n\n---\n\n".join(format_category(cat) for cat in matches) + DISCLAIMER
    send_message(chat_id, reply, reply_markup=back_to_menu_keyboard())
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
