# main.py
# Word Factory — сюжетный тренажёр словообразования (без state, стабильный вариант)
# Фичи:
# - Атмосфера (рандомные реплики)
# - Редкие детерминированные события (по message_id)
# - Пас как обучающая механика (мини-правила по суффиксам)
# - Микропрогресс без хранения (по message_id)
# - Пасхалки (по ключевым словам)
# - Мини-роли (текстом)
# - Короткий онбординг в начале сессии + мини-онбординг "в начале партии" (перед вопросом)
#
# ВАЖНО:
# - Убрана механика "Правила" (кнопка и показ "текущего вопроса"), чтобы избегать казусов.
# - Если пользователь скажет "правила/помощь", мы отвечаем памяткой и продолжаем.

import csv
import hashlib
import random
import re
from pathlib import Path

CSV_PATH = Path(__file__).with_name("words.csv")

TARGET_COLUMNS = [
    "Verb",
    "Adjective",
    "Opposite Adjective",
    "Adverb",
    "Opposite Adverb",
]

LABELS_RU = {
    "Verb": "глагол",
    "Adjective": "прилагательное",
    "Opposite Adjective": "противоположное прилагательное",
    "Adverb": "наречие",
    "Opposite Adverb": "противоположное наречие",
}

BUTTONS = [
    {"title": "Пас", "hide": True},
    {"title": "Выход", "hide": True},
]


# ---------- helpers ----------
def normalize_en(text: str) -> str:
    if not text:
        return ""
    t = str(text).lower()
    t = re.sub(r"[^a-z'\- ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_ru(text: str) -> str:
    if not text:
        return ""
    t = str(text).strip().lower().replace("ё", "е")
    t = re.sub(r"[^a-zа-я0-9\- ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def split_variants(cell: str) -> list[str]:
    """
    Variants separated by ; , /
    Supports "to invent" -> "invent"
    """
    if not cell:
        return []
    parts = re.split(r"[;,/]+", str(cell))
    out = set()

    for p in parts:
        p = normalize_en(p)
        if not p:
            continue

        if p.startswith("to "):
            p2 = p[3:].strip()
            if p2:
                out.add(p2)

        tokens = p.split()
        if tokens:
            out.add(tokens[-1])

        if len(tokens) == 1:
            out.add(tokens[0])

    out.discard("")
    return list(out)


def load_rows():
    rows = []
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            noun = (r.get("Noun") or "").strip()
            if noun:
                rows.append(r)
    return rows


ROWS = load_rows()


# ---------- deterministic question ----------
def seed64(s: str) -> int:
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:16], 16)  # 64-bit


def msg_seed(session_id: str, user_id: str, message_id: int) -> int:
    return seed64(f"MSG|{session_id}|{user_id}|{message_id}")


def pick_question_by_seed(seed: int, max_tries: int = 80) -> dict:
    rng = random.Random(seed)

    for _ in range(max_tries):
        row = rng.choice(ROWS)
        base = (row.get("Noun") or "").strip()
        if not base:
            continue

        viable = []
        parsed = {}
        for col in TARGET_COLUMNS:
            acc = split_variants(row.get(col, ""))
            if acc:
                viable.append(col)
                parsed[col] = acc

        if not viable:
            continue

        target = rng.choice(viable)
        accepted = parsed[target]

        base_norm = normalize_en(base)
        already_ok = base_norm in set(accepted) if base_norm else False

        return {"base": base, "target": target, "accepted": accepted, "already_ok": already_ok}

    return {"base": "word", "target": "Adjective", "accepted": ["wordy"], "already_ok": False}


def format_question(q: dict) -> str:
    text = f"Сделай {LABELS_RU[q['target']]} от слова {q['base']}."
    if q.get("already_ok"):
        text += " Если слово уже подходит, можно просто повторить его."
    return text


def format_correct(q: dict) -> str:
    accepted = q.get("accepted") or []
    if not accepted:
        return "Правильного варианта в таблице нет."
    if len(accepted) == 1:
        return f"Правильный вариант: {accepted[0]}."
    return "Правильные варианты: " + ", ".join(accepted[:3]) + "."


def alice(text: str, end: bool = False, buttons=None):
    resp = {"response": {"text": text, "tts": text, "end_session": end}, "version": "1.0"}
    if buttons:
        resp["response"]["buttons"] = buttons
    return resp


# ---------- flavour systems (no state) ----------
def stable_rng_for_turn(session_id: str, user_id: str, message_id: int) -> random.Random:
    return random.Random(seed64(f"FLAV|{session_id}|{user_id}|{message_id}"))


SUCCESS_LINES = [
    "Контроль качества пройден.",
    "Идеально. Партия чистая.",
    "Принято. Деталь по стандарту.",
    "Красиво! Линия идёт ровно.",
    "Окей, это проходит инспекцию.",
]

FAIL_LINES = [
    "Брак обнаружен.",
    "Не по стандарту.",
    "Останавливаем линию — ошибка в детали.",
    "Проверка не пройдена.",
    "Есть несоответствие чертежу.",
]

NEXT_LINES = [
    "Следующая партия.",
    "Новый заказ на линии.",
    "Переходим к следующей детали.",
    "Продолжаем смену.",
    "Дальше по конвейеру.",
]

ROLES = [
    "Я — мастер смены.",
    "Я — старший инспектор.",
    "Я — инженер по качеству.",
    "Я — бригадир линии.",
]

ROLE_SIDEKICKS = [
    "Ты — инспектор на испытательном сроке.",
    "Ты сегодня главный по проверке.",
    "Ты держишь линию в тонусе.",
    "Твоя задача — отбраковывать мусор.",
]

# короткий "онбординг в начале партии" (перед вопросом)
BATCH_INTROS = [
    "Партия поступила на стол.",
    "На ленте новая деталь.",
    "Проверка следующей детали.",
    "Сканируем следующую заготовку.",
    "Следующий контрольный образец.",
]


def micro_progress_line(message_id: int) -> str | None:
    if message_id >= 25 and message_id % 5 == 0:
        return "Чувствуется уверенность. Уже как свой на линии."
    if message_id >= 12 and message_id % 4 == 0:
        return "Неплохо идёшь. Руки набиваются."
    if message_id >= 6 and message_id % 3 == 0:
        return "Втягиваешься. Темп хороший."
    return None


def deterministic_event(message_id: int) -> str | None:
    if message_id > 0 and message_id % 13 == 0:
        return "⚠️ Срочный заказ: проверяем особенно внимательно."
    if message_id > 0 and message_id % 11 == 0:
        return "📦 Большая партия: сегодня много работы."
    if message_id > 0 and message_id % 7 == 0:
        return "🔧 Техосмотр конвейера пройден. Продолжаем."
    if message_id > 0 and message_id % 17 == 0:
        return "🕵️ Аудит качества: на линии проверка без предупреждения."
    return None


def easter_egg(base_word: str) -> str | None:
    w = normalize_en(base_word)
    if any(k in w for k in ["music", "song", "sound", "rhythm", "note"]):
        return "🎛️ Музыкальный цех: тут всё должно звучать чисто."
    if any(k in w for k in ["war", "weapon", "fight", "bomb", "attack"]):
        return "🧯 Опасный отдел: аккуратно с формами."
    if any(k in w for k in ["money", "bank", "finance", "price", "cost", "budget"]):
        return "💸 Финансовый цех: любая ошибка — и бухгалтерия орёт."
    if any(k in w for k in ["death", "blood", "pain", "fear"]):
        return "💀 Мрачный заказ. Но мы профессионалы."
    if any(k in w for k in ["love", "heart", "kiss"]):
        return "💌 Романтический отдел: главное — без лишней лирики."
    if any(k in w for k in ["tech", "computer", "code", "data", "robot"]):
        return "🤖 Тех-цех: слова тоже любят точность."
    return None


def pass_hint(q: dict) -> str | None:
    base = normalize_en(q.get("base", ""))
    target = q.get("target", "")

    if target == "Adverb":
        return "Подсказка: наречие часто делается как adjective + -ly (quick → quickly)."
    if target == "Opposite Adjective":
        return "Подсказка: противоположность часто через un-/in-/im-/ir-/dis- (regular → irregular)."
    if target == "Opposite Adverb":
        return "Подсказка: противоположность наречия часто через un-/in-/dis- или not + adverb."
    if target == "Verb":
        if base.endswith("tion") or base.endswith("sion"):
            return "Подсказка: -tion/-sion иногда превращается в глагол (information → inform)."
        if base.endswith("ment"):
            return "Подсказка: -ment часто указывает на существительное от глагола (develop → development)."
        return "Подсказка: иногда существительное и глагол совпадают (travel → travel)."
    if target == "Adjective":
        if base.endswith("y"):
            return "Подсказка: иногда adjective уже есть (rain → rainy)."
        if base.endswith("tion") or base.endswith("sion"):
            return "Подсказка: -tion часто даёт adjective на -tional/-tive (nation → national)."
        if base.endswith("ence") or base.endswith("ance"):
            return "Подсказка: -ence/-ance иногда → -ent/-ant (difference → different)."
        return "Подсказка: частые суффиксы adjective: -al, -ful, -less, -ic, -ive, -ous."
    return None


def is_meta_request(ru: str) -> bool:
    return ru in {"правила", "помощь", "как играть", "что делать", "инструкция"}


def batch_prompt(frng: random.Random, q: dict) -> str:
    """
    Мини-онбординг "в начале партии": одна короткая строка перед вопросом.
    """
    lines = [frng.choice(BATCH_INTROS)]
    ev = deterministic_event  # alias
    egg = easter_egg(q["base"])
    if egg:
        lines.append(egg)
    lines.append(format_question(q))
    return "\n".join(lines)


# ---------- handler ----------
def handler(event, context):
    req = event.get("request", {}) or {}
    sess = event.get("session", {}) or {}

    original = req.get("original_utterance", "") or req.get("command", "")
    ru = normalize_ru(original)
    en = normalize_en(original)

    session_id = sess.get("session_id", "")
    user_id = (sess.get("user", {}) or {}).get("user_id", "") or sess.get("user_id", "")
    message_id = int(sess.get("message_id", 0) or 0)

    frng = stable_rng_for_turn(session_id, user_id, message_id)

    # Exit
    if ru in {"хватит", "выход", "стоп"} or en in {"exit", "stop"}:
        return alice("Смена окончена. Хорошая работа в Word Factory. Возвращайся ещё!", end=True)

    # New session: onboarding + first batch
    if bool(sess.get("new", False)):
        q = pick_question_by_seed(msg_seed(session_id, user_id, message_id))

        role_line = frng.choice(ROLES) + " " + frng.choice(ROLE_SIDEKICKS)

        lines = [
            "Добро пожаловать в Word Factory!",
            role_line,
            "Правило простое: отвечай одним английским словом.",
            "Команды: «пас» — пропуск с подсказкой; «выход» — закончить смену.",
        ]

        ev = deterministic_event(message_id)
        if ev:
            lines.append(ev)

        # first batch prompt (short onboarding per batch)
        lines.append(batch_prompt(frng, q))

        return alice("\n".join(lines), end=False, buttons=BUTTONS)

    # asked / next questions
    asked_q = pick_question_by_seed(msg_seed(session_id, user_id, max(message_id - 1, 0)))
    next_q = pick_question_by_seed(msg_seed(session_id, user_id, message_id))

    # Meta requests: short reminder + continue (no "current question" display)
    if is_meta_request(ru):
        lines = [
            "Памятка: отвечай одним английским словом.",
            "«пас» — показать правильный ответ и подсказку.",
            "«выход» — закончить смену.",
            frng.choice(NEXT_LINES),
            batch_prompt(frng, next_q),
        ]
        return alice("\n".join(lines), end=False, buttons=BUTTONS)

    # PASS
    if ru in {"пас", "не знаю", "пропуск"}:
        hint = pass_hint(asked_q)

        lines = [
            "Окей, пас.",
            format_correct(asked_q),
        ]
        if hint:
            lines.append(hint)

        ev = deterministic_event(message_id)
        if ev:
            lines.append(ev)

        mp = micro_progress_line(message_id)
        if mp:
            lines.append(mp)

        lines.append(frng.choice(NEXT_LINES))
        lines.append(batch_prompt(frng, next_q))

        return alice("\n".join(lines), end=False, buttons=BUTTONS)

    # Evaluate answer
    accepted = set(asked_q.get("accepted") or [])
    correct = bool(en) and (en in accepted)

    lines = []

    # Mini-role flavour sometimes
    if message_id % 9 == 0:
        lines.append(frng.choice(ROLES))
    if message_id % 10 == 0:
        lines.append(frng.choice(ROLE_SIDEKICKS))

    if correct:
        lines.append(frng.choice(SUCCESS_LINES))
        if asked_q.get("already_ok") and en == normalize_en(asked_q.get("base", "")):
            lines.append("Да, иногда слово уже в нужной форме — так тоже правильно.")
    else:
        lines.append(frng.choice(FAIL_LINES))
        lines.append(format_correct(asked_q))

    ev = deterministic_event(message_id)
    if ev:
        lines.append(ev)

    mp = micro_progress_line(message_id)
    if mp:
        lines.append(mp)

    lines.append(frng.choice(NEXT_LINES))
    lines.append(batch_prompt(frng, next_q))

    return alice("\n".join(lines), end=False, buttons=BUTTONS)
