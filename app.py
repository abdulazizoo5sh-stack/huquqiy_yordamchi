"""
Avto-huquq Telegram boti - WEBHOOK versiyasi (bepul hostingda 24/7 ishlash uchun)
------------------------------------------------------------------------------
Bu versiya Flask veb-server sifatida ishlaydi va Telegram'dan xabarlarni
"webhook" orqali qabul qiladi. Render.com kabi bepul veb-hosting xizmatlariga
joylash uchun mo'ljallangan - kompyuteringizda hech narsa ishlab turishi
shart emas.

Hech qanday pullik AI API ishlatilmaydi - faqat kalit so'z qidiruvi.

Muhit o'zgaruvchilari (Render dashboard'da "Environment" bo'limida kiritiladi):
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
    "Iltimos, kalit so'z bilan yozib ko'ring, masalan: tezlik, sug'urta, "
    "svetofor, parkovka, hujjat, mast holda, avariya, shikoyat, chegirma "
    "va h.k."
    + DISCLAIMER
)

START_MESSAGE = (
    "Salom! Men avto-huquq bo'yicha yordamchi botman.\n\n"
    "Menga yo'l harakati bilan bog'liq muammoingizni bitta-ikkita so'z bilan "
    "yozing - masalan:\n"
    "• \"tezlik\"\n"
    "• \"sug'urta yo'q\"\n"
    "• \"svetoforda qizil chiroqda o'tib qoldim\"\n"
    "• \"jarimani qachongacha to'lashim kerak\"\n\n"
    "Men sizga tegishli qoida, modda va taxminiy jarima haqida ma'lumot "
    "beraman.\n\n"
    "⚠️ Eslatma: men rasmiy yurist emasman, javoblarim umumiy yo'nalish "
    "uchun. Muhim holatlarda malakali yuristga murojaat qiling."
)


def send_message(chat_id: int, text: str) -> None:
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


@app.route("/", methods=["GET"])
def health_check():
    # Render/UptimeRobot kabi xizmatlar shu manzilga "tirikmisan" so'rovi
    # yuborib turadi - bu bot uxlab qolmasligiga yordam beradi.
    return "Bot ishlayapti.", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    message = update.get("message") or update.get("edited_message")

    if not message or "text" not in message:
        return "ok", 200

    chat_id = message["chat"]["id"]
    text = message["text"]

    if text.strip() in ("/start", "/help"):
        send_message(chat_id, START_MESSAGE)
        return "ok", 200

    matches = find_matches(text)
    if not matches:
        send_message(chat_id, NOT_FOUND_MESSAGE)
        return "ok", 200

    reply = "\n\n---\n\n".join(format_category(cat) for cat in matches) + DISCLAIMER
    send_message(chat_id, reply)
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
