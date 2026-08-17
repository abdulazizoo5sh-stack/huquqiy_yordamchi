
"""
Huquqiy yordamchi Telegram boti - KO'P SOHALI, WEBHOOK + TUGMALI MENYU
------------------------------------------------------------------------
Bepul hostingda (Render.com) 24/7 ishlaydi. Hech qanday pullik AI API
ishlatilmaydi - faqat kalit so'z qidiruvi + Telegram inline tugmalari.

Hozircha 2 ta soha bor: Avto huquqi va Nikoh/oila huquqi.
Yangi soha qo'shish uchun: yangi knowledge_base_<soha>.json fayl yarating
va DOMAINS lug'atiga qo'shing (pastda tushuntirilgan).

Muhit o'zgaruvchilari (Render dashboard'da "Environment" bo'limida):
    BOT_TOKEN - BotFather'dan olingan token
"""

import json
import os
import re

import requests
from flask import Flask, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.environ["BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)


def load_kb(filename: str) -> list:
    path = os.path.join(BASE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["kategoriyalar"]


# ---------------------------------------------------------------------
# SOHALAR RO'YXATI - yangi soha qo'shish uchun shu yerga qo'shing:
#   "domain_kaliti": {
#       "label": "🆕 Soha nomi",
#       "file": "knowledge_base_<soha>.json",
#       "quick_topics": [(kategoriya_indeksi, "Tugma matni"), ...]
#   }
# ---------------------------------------------------------------------
DOMAINS = {
    "avto": {
        "label": "🚗 Avto huquqi",
        "categories": load_kb("knowledge_base.json"),
        "quick_topics": [
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
        ],
    },
    "nikoh": {
        "label": "💍 Nikoh / oila huquqi",
        "categories": load_kb("knowledge_base_nikoh.json"),
        "quick_topics": [
            (0, "📝 Ajratish (FHDYo)"),
            (1, "⚖️ Ajratish (sud)"),
            (2, "👶 Aliment miqdori"),
            (5, "🚫 Aliment to'lamaslik"),
            (6, "🏠 Mol-mulk bo'lish"),
            (8, "👨‍👩‍👧 Bola kim bilan qoladi"),
            (10, "❌ Fiktiv nikoh"),
            (11, "💰 Ajralish narxi"),
        ],
    },
}

APOSTROPHE_PATTERN = re.compile(r"[ʻʼ`´']")


def normalize(text: str) -> str:
    text = text.lower()
    text = APOSTROPHE_PATTERN.sub("'", text)
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return text


def find_matches(user_text: str, top_n: int = 3):
    """Barcha sohalar bo'yicha qidiradi, natijada (domain_key, kategoriya) qaytadi."""
    norm_text = normalize(user_text)
    scored = []
    for domain_key, domain in DOMAINS.items():
        for cat in domain["categories"]:
            score = sum(1 for kw in cat["kalit_sozlar"] if normalize(kw) in norm_text)
            if score > 0:
                scored.append((score, domain_key, cat))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(dk, cat) for _, dk, cat in scored[:top_n]]


def format_category(domain_key: str, cat: dict) -> str:
    domain_label = DOMAINS[domain_key]["label"]
    lines = [f"{domain_label}", f"📌 {cat['mavzu']}"]
    if cat.get("modda") and cat["modda"] != "-":
        lines.append(f"Modda: {cat['modda']}")
    if cat.get("tavsif"):
        lines.append(f"Tavsif: {cat['tavsif']}")
    if cat.get("jarima") and cat["jarima"] != "-":
        lines.append(f"Jarima/Miqdor: {cat['jarima']}")
    if cat.get("izoh"):
        lines.append(f"Izoh: {cat['izoh']}")
    return "\n".join(lines)


DISCLAIMER = (
    "\n\n⚠️ Bu ma'lumot umumiy yo'nalish uchun, rasmiy yuridik maslahat emas. "
    "Aniq holatlar uchun lex.uz yoki malakali yuristga murojaat qiling."
)

NOT_FOUND_MESSAGE = (
    "Kechirasiz, muammoingizga mos qoidani topa olmadim. 🤔\n\n"
    "Iltimos, kalit so'z bilan yozib ko'ring yoki pastdagi menyudan soha "
    "tanlab, tugmalardan birini bosing."
    + DISCLAIMER
)

START_MESSAGE = (
    "Salom! Men huquqiy yordamchi botman. ⚖️\n\n"
    "Quyidagi sohalardan birini tanlang yoki muammoingizni to'g'ridan-to'g'ri "
    "o'z so'zlaringiz bilan yozing - masalan:\n"
    "• \"tezlikni oshirib qoldim\"\n"
    "• \"aliment qancha to'lanadi\"\n\n"
    "⚠️ Eslatma: men rasmiy yurist emasman, javoblarim umumiy yo'nalish "
    "uchun. Muhim holatlarda malakali yuristga murojaat qiling."
)


def domain_selection_keyboard() -> dict:
    rows = [[{"text": d["label"], "callback_data": f"dom_{key}"}] for key, d in DOMAINS.items()]
    return {"inline_keyboard": rows}


def topics_keyboard(domain_key: str) -> dict:
    topics = DOMAINS[domain_key]["quick_topics"]
    rows = []
    for i in range(0, len(topics), 2):
        row = []
        for idx, label in topics[i:i + 2]:
            row.append({"text": label, "callback_data": f"topic_{domain_key}_{idx}"})
        rows.append(row)
    rows.append([{"text": "🏠 Sohalar menyusi", "callback_data": "menu_main"}])
    return {"inline_keyboard": rows}


def answer_keyboard(domain_key: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔙 Mavzular", "callback_data": f"dom_{domain_key}"}],
            [{"text": "🏠 Sohalar menyusi", "callback_data": "menu_main"}],
        ]
    }


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
            send_message(chat_id, START_MESSAGE, reply_markup=domain_selection_keyboard())
        elif data.startswith("dom_"):
            domain_key = data.split("_", 1)[1]
            if domain_key in DOMAINS:
                label = DOMAINS[domain_key]["label"]
                send_message(
                    chat_id,
                    f"{label}\n\nMavzu tanlang yoki muammoingizni yozing:",
                    reply_markup=topics_keyboard(domain_key),
                )
        elif data.startswith("topic_"):
            try:
                _, domain_key, idx_str = data.split("_", 2)
                idx = int(idx_str)
                cat = DOMAINS[domain_key]["categories"][idx]
                reply = format_category(domain_key, cat) + DISCLAIMER
                send_message(chat_id, reply, reply_markup=answer_keyboard(domain_key))
            except (ValueError, IndexError, KeyError):
                send_message(chat_id, NOT_FOUND_MESSAGE, reply_markup=domain_selection_keyboard())
        return "ok", 200

    # --- Oddiy matnli xabar ---
    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return "ok", 200

    chat_id = message["chat"]["id"]
    text = message["text"]

    if text.strip() in ("/start", "/help", "/menu"):
        send_message(chat_id, START_MESSAGE, reply_markup=domain_selection_keyboard())
        return "ok", 200

    matches = find_matches(text)
    if not matches:
        send_message(chat_id, NOT_FOUND_MESSAGE, reply_markup=domain_selection_keyboard())
        return "ok", 200

    reply = "\n\n---\n\n".join(
        format_category(dk, cat) for dk, cat in matches
    ) + DISCLAIMER
    send_message(chat_id, reply, reply_markup=domain_selection_keyboard())
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
