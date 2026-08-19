"""
Huquqiy yordamchi Telegram boti - AVTO + NIKOH + KONSTITUTSIYA
------------------------------------------------------------------------
Bepul hostingda (Render.com) 24/7 ishlaydi. Hech qanday pullik AI API
ishlatilmaydi - kalit so'z qidiruvi (avto/nikoh) + to'liq matn qidiruvi
(konstitutsiya) + Telegram inline tugmalari.

Muhit o'zgaruvchilari (Render dashboard'da "Environment" bo'limida):
    BOT_TOKEN - BotFather'dan olingan token
"""

import html
import json
import os
import re

import requests
from flask import Flask, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.environ["BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)


def get_bot_username() -> str:
    """Botning @username'ini Telegram API orqali avtomatik aniqlaydi (ulashish havolasi uchun)."""
    try:
        resp = requests.get(f"{TELEGRAM_API}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            return data["result"]["username"]
    except requests.RequestException:
        pass
    return None


BOT_USERNAME = get_bot_username()
SHARE_URL = (
    f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}"
    "&text=O'zbekiston%20qonunchiligi%20bo'yicha%20bepul%20yordamchi%20bot!"
    if BOT_USERNAME else None
)


def load_json(filename: str) -> dict:
    path = os.path.join(BASE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def esc(text: str) -> str:
    """Telegram HTML formatlash uchun maxsus belgilarni xavfsizlashtiradi."""
    return html.escape(str(text))


# ---------------------------------------------------------------------
# ODDIY SOHALAR (avto, nikoh) - kalit so'z asosida qidiriladi
# ---------------------------------------------------------------------
DOMAINS = {
    "avto": {
        "label": "🚗 Avto huquqi",
        "categories": load_json("knowledge_base.json")["kategoriyalar"],
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
        "categories": load_json("knowledge_base_nikoh.json")["kategoriyalar"],
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

# ---------------------------------------------------------------------
# KONSTITUTSIYA - bo'lim -> bob -> modda tuzilishi, to'liq matn qidiruvi
# ---------------------------------------------------------------------
KONST = load_json("knowledge_base_konstitutsiya.json")
KONST_BOLIMLAR = KONST["bolimlar"]

KONST_BOLIM_QISQA = [
    "1-bo'lim: Asosiy prinsiplar",
    "2-bo'lim: Inson huquqlari",
    "3-bo'lim: Jamiyat va shaxs",
    "4-bo'lim: Hududiy tuzilish",
    "5-bo'lim: Davlat hokimiyati",
    "6-bo'lim: O'zgartirish tartibi",
]

APOSTROPHE_PATTERN = re.compile(r"[ʻʼ`´']")

# ---------------------------------------------------------------------
# KIRILL -> LOTIN transliteratsiya (o'zbekcha kirill klaviaturasidan
# yozganlar uchun ham qidiruv ishlashi uchun)
# ---------------------------------------------------------------------
CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "x", "ц": "s", "ч": "ch", "ш": "sh", "щ": "sh",
    "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}


def translit_cyrillic(text: str) -> str:
    return "".join(CYRILLIC_TO_LATIN.get(ch, ch) for ch in text)


def normalize(text: str) -> str:
    text = text.lower()
    text = translit_cyrillic(text)
    text = APOSTROPHE_PATTERN.sub("'", text)
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return text


# ---------------------------------------------------------------------
# IMLO XATOLARIGA CHIDAMLI (FUZZY) SO'Z SOLISHTIRISH
# ---------------------------------------------------------------------
def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def words_match(w1: str, w2: str) -> bool:
    if w1 == w2:
        return True
    if abs(len(w1) - len(w2)) > 2:
        return False
    threshold = 1 if len(w1) <= 6 else 2
    return levenshtein(w1, w2) <= threshold


def fuzzy_keyword_in_text(keyword_norm: str, text_words: list) -> bool:
    """Kalit so'zning har bir bo'lagi matnda borligini tekshiradi:
    - qo'shimchali shakllar uchun (masalan "tezlikni") - substring sifatida,
    - imlo xatolari uchun (masalan "tezlk") - fuzzy masofa orqali."""
    for kw_word in keyword_norm.split():
        found = any(
            kw_word in tw or words_match(kw_word, tw)
            for tw in text_words
        )
        if not found:
            return False
    return True


def find_matches(user_text: str, top_n: int = 3):
    """Avto/nikoh (kalit so'z) + konstitutsiya (to'liq matn) bo'yicha qidiradi.
    Kirill matnni avtomatik lotinga o'tkazadi va kichik imlo xatolariga chidamli."""
    norm_text = normalize(user_text)
    text_words = norm_text.split()
    query_words = [w for w in text_words if len(w) >= 4]
    scored = []

    for domain_key, domain in DOMAINS.items():
        for cat in domain["categories"]:
            score = sum(
                1 for kw in cat["kalit_sozlar"]
                if fuzzy_keyword_in_text(normalize(kw), text_words)
            )
            if score > 0:
                scored.append((score, "kat", domain_key, cat))

    if query_words:
        for b_idx, bolim in enumerate(KONST_BOLIMLAR):
            for bob_idx, bob in enumerate(bolim["boblar"]):
                for m_idx, modda in enumerate(bob["moddalar"]):
                    norm_matn_words = modda.get("_norm_words")
                    if norm_matn_words is None:
                        norm_matn_words = normalize(modda["matn"]).split()
                        modda["_norm_words"] = norm_matn_words
                    score = sum(
                        1 for qw in query_words
                        if any(words_match(qw, tw) for tw in norm_matn_words)
                    )
                    if score > 0:
                        scored.append((score, "konst", (b_idx, bob_idx, m_idx), modda))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


def format_category(domain_key: str, cat: dict) -> str:
    domain_label = DOMAINS[domain_key]["label"]
    lines = [f"<b>{esc(domain_label)}</b>", f"📌 <b>{esc(cat['mavzu'])}</b>", ""]
    if cat.get("modda") and cat["modda"] != "-":
        lines.append(f"📖 <b>Modda:</b> {esc(cat['modda'])}")
    if cat.get("tavsif"):
        lines.append(f"📝 <b>Tavsif:</b> {esc(cat['tavsif'])}")
    if cat.get("jarima") and cat["jarima"] != "-":
        lines.append(f"💰 <b>Jarima/Miqdor:</b> {esc(cat['jarima'])}")
    if cat.get("izoh"):
        lines.append(f"\nℹ️ <b>Izoh:</b> {esc(cat['izoh'])}")
    return "\n".join(lines)


def format_modda(b_idx: int, bob_idx: int, m_idx: int) -> str:
    bolim = KONST_BOLIMLAR[b_idx]
    bob = bolim["boblar"][bob_idx]
    modda = bob["moddalar"][m_idx]
    lines = [
        "⚖️ <b>O'zbekiston Respublikasi Konstitutsiyasi</b>",
        f"<i>{esc(bob['nomi'])}</i>",
        "",
        f"📜 <b>{esc(modda['raqam'])}-modda</b>",
        "",
        esc(modda["matn"]),
    ]
    return "\n".join(lines)


DISCLAIMER = (
    "\n\n<i>⚠️ Bu ma'lumot umumiy yo'nalish uchun, rasmiy yuridik maslahat emas. "
    "Aniq holatlar uchun lex.uz yoki malakali yuristga murojaat qiling.</i>"
)

NOT_FOUND_MESSAGE = (
    "Kechirasiz, muammoingizga mos qoidani topa olmadim. 🤔\n\n"
    "Iltimos, kalit so'z bilan yozib ko'ring yoki pastdagi menyudan soha "
    "tanlab, tugmalardan birini bosing."
    + DISCLAIMER
)

START_MESSAGE = (
    "Salom! 👋 Men <b>huquqiy yordamchi</b> botman. ⚖️\n\n"
    "Quyidagi sohalardan birini tanlang yoki muammoingizni to'g'ridan-to'g'ri "
    "o'z so'zlaringiz bilan yozing, masalan:\n"
    "• <i>\"tezlikni oshirib qoldim\"</i>\n"
    "• <i>\"aliment qancha to'lanadi\"</i>\n"
    "• <i>\"so'z erkinligi\"</i>\n\n"
    "<i>⚠️ Eslatma: men rasmiy yurist emasman, javoblarim umumiy yo'nalish "
    "uchun. Muhim holatlarda malakali yuristga murojaat qiling.</i>"
)


def domain_selection_keyboard() -> dict:
    rows = [[{"text": d["label"], "callback_data": f"dom_{key}"}] for key, d in DOMAINS.items()]
    rows.append([{"text": "⚖️ Konstitutsiya", "callback_data": "dom_konst"}])
    if SHARE_URL:
        rows.append([{"text": "📤 Do'stlarga ulashish", "url": SHARE_URL}])
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


def konst_bolim_keyboard() -> dict:
    rows = []
    for i, _ in enumerate(KONST_BOLIMLAR):
        label = KONST_BOLIM_QISQA[i] if i < len(KONST_BOLIM_QISQA) else f"{i+1}-bo'lim"
        rows.append([{"text": label, "callback_data": f"kb_{i}"}])
    rows.append([{"text": "🏠 Sohalar menyusi", "callback_data": "menu_main"}])
    return {"inline_keyboard": rows}


def konst_bob_keyboard(b_idx: int) -> dict:
    bolim = KONST_BOLIMLAR[b_idx]
    rows = []
    for j, bob in enumerate(bolim["boblar"]):
        # Bob nomini qisqartirish (tugma matni uzun bo'lmasligi uchun)
        label = bob["nomi"]
        if len(label) > 40:
            label = label[:37] + "..."
        rows.append([{"text": label, "callback_data": f"kbob_{b_idx}_{j}"}])
    rows.append([{"text": "🔙 Bo'limlar", "callback_data": "dom_konst"}])
    rows.append([{"text": "🏠 Sohalar menyusi", "callback_data": "menu_main"}])
    return {"inline_keyboard": rows}


def konst_modda_keyboard(b_idx: int, bob_idx: int) -> dict:
    bob = KONST_BOLIMLAR[b_idx]["boblar"][bob_idx]
    rows = []
    moddalar = bob["moddalar"]
    for i in range(0, len(moddalar), 4):
        row = []
        for k in range(i, min(i + 4, len(moddalar))):
            raqam = moddalar[k]["raqam"]
            row.append({"text": f"{raqam}-modda", "callback_data": f"km_{b_idx}_{bob_idx}_{k}"})
        rows.append(row)
    rows.append([{"text": "🔙 Boblar", "callback_data": f"kb_{b_idx}"}])
    rows.append([{"text": "🏠 Sohalar menyusi", "callback_data": "menu_main"}])
    return {"inline_keyboard": rows}


def konst_modda_answer_keyboard(b_idx: int, bob_idx: int) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔙 Modda ro'yxati", "callback_data": f"kbob_{b_idx}_{bob_idx}"}],
            [{"text": "🏠 Sohalar menyusi", "callback_data": "menu_main"}],
        ]
    }


def send_message(chat_id: int, text: str, reply_markup: dict = None) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)


def send_typing(chat_id: int) -> None:
    """Foydalanuvchiga bot javob tayyorlayotganini bildiruvchi 'yozyapti...' indikatori."""
    try:
        requests.post(
            f"{TELEGRAM_API}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except requests.RequestException:
        pass


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

        try:
            if data == "menu_main":
                send_message(chat_id, START_MESSAGE, reply_markup=domain_selection_keyboard())

            elif data == "dom_konst":
                send_message(
                    chat_id,
                    "⚖️ <b>Konstitutsiya</b>\n\nBo'lim tanlang:",
                    reply_markup=konst_bolim_keyboard(),
                )

            elif data.startswith("dom_"):
                domain_key = data.split("_", 1)[1]
                if domain_key in DOMAINS:
                    label = DOMAINS[domain_key]["label"]
                    send_message(
                        chat_id,
                        f"<b>{esc(label)}</b>\n\nMavzu tanlang yoki muammoingizni yozing:",
                        reply_markup=topics_keyboard(domain_key),
                    )

            elif data.startswith("topic_"):
                _, domain_key, idx_str = data.split("_", 2)
                idx = int(idx_str)
                cat = DOMAINS[domain_key]["categories"][idx]
                reply = format_category(domain_key, cat) + DISCLAIMER
                send_message(chat_id, reply, reply_markup=answer_keyboard(domain_key))

            elif data.startswith("kbob_"):
                _, b_idx_str, bob_idx_str = data.split("_", 2)
                b_idx, bob_idx = int(b_idx_str), int(bob_idx_str)
                bob = KONST_BOLIMLAR[b_idx]["boblar"][bob_idx]
                send_message(
                    chat_id,
                    f"⚖️ <b>{esc(bob['nomi'])}</b>\n\nModda tanlang:",
                    reply_markup=konst_modda_keyboard(b_idx, bob_idx),
                )

            elif data.startswith("kb_"):
                b_idx = int(data.split("_", 1)[1])
                bolim = KONST_BOLIMLAR[b_idx]
                send_message(
                    chat_id,
                    f"⚖️ <b>{esc(bolim['nomi'])}</b>\n\nBob tanlang:",
                    reply_markup=konst_bob_keyboard(b_idx),
                )

            elif data.startswith("km_"):
                _, b_idx_str, bob_idx_str, m_idx_str = data.split("_", 3)
                b_idx, bob_idx, m_idx = int(b_idx_str), int(bob_idx_str), int(m_idx_str)
                reply = format_modda(b_idx, bob_idx, m_idx) + DISCLAIMER
                send_message(chat_id, reply, reply_markup=konst_modda_answer_keyboard(b_idx, bob_idx))

        except (ValueError, IndexError, KeyError):
            send_message(chat_id, NOT_FOUND_MESSAGE, reply_markup=domain_selection_keyboard())

        return "ok", 200

    # --- Oddiy matnli xabar ---
    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return "ok", 200

    chat_id = message["chat"]["id"]
    text = message["text"]
    send_typing(chat_id)

    if text.strip() in ("/start", "/help", "/menu"):
        send_message(chat_id, START_MESSAGE, reply_markup=domain_selection_keyboard())
        return "ok", 200

    matches = find_matches(text)
    if not matches:
        send_message(chat_id, NOT_FOUND_MESSAGE, reply_markup=domain_selection_keyboard())
        return "ok", 200

    parts = []
    for item in matches:
        if item[1] == "kat":
            _, _, domain_key, cat = item
            parts.append(format_category(domain_key, cat))
        else:
            _, _, (b_idx, bob_idx, m_idx), _modda = item
            parts.append(format_modda(b_idx, bob_idx, m_idx))

    reply = "\n\n➖➖➖➖➖➖➖➖➖➖\n\n".join(parts) + DISCLAIMER
    send_message(chat_id, reply, reply_markup=domain_selection_keyboard())
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
