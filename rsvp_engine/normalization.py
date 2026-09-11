"""Persian text normalization boundary (Phase 2).

Responsible for:
- Unicode NFC normalization
- Character unification (Arabic variants to standard Persian, preserving valid Persian hamzas)
- Eastern Arabic-Indic digits to Persian digits
- ASCII digits to Persian digits where appropriate (preserving identifiers and URLs)
- URL and email preservation (shielding them from punctuation and digit transformations)
- Stripping Arabic diacritics (harakat) and invisible formatting marks (LRM/RLM/ZWSP)
- Persian punctuation standardization (؟ ، ؛ … « »)
- ZWNJ / half-space normalization for Persian verbal, prepositional, nominal affixes and common compounds
- Punctuation attachment and quotation unification
- Kashida and redundant whitespace cleanup
"""

import re
import unicodedata
import uuid

ZWNJ = "\u200c"

# Character & numeral mappings
ARABIC_TO_PERSIAN_MAP = {
    # Letters (preserves valid Persian hamza characters: ئ, ؤ)
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ة": "ه",
    "إ": "ا",
    "أ": "ا",
    "ٱ": "ا",
    "ۀ": "ه",
    # Arabic-Indic digits to Persian digits
    "٠": "۰",
    "١": "۱",
    "٢": "۲",
    "٣": "۳",
    "٤": "۴",
    "٥": "۵",
    "٦": "۶",
    "٧": "۷",
    "٨": "۸",
    "٩": "۹",
}

ASCII_TO_PERSIAN_DIGITS = {str(i): chr(0x06F0 + i) for i in range(10)}

# Arabic diacritics (harakat / tanween / tashdeed / sukun)
DIACRITICS_REGEX = re.compile(r"[\u064B-\u065F\u0670]")

# Invisible directional control marks and zero-width spaces (excluding valid ZWNJ)
INVISIBLE_MARKS_REGEX = re.compile(r"[\u200B\u200E\u200F\u202A-\u202E\uFEFF]")

# Persian affix patterns for half-space correction
# Verb prefix 'می' / 'نمی': note that rare homographs like 'می' (wine) in 'می قرمز'
# will be joined (acceptable trade-off against vast majority of verbal usages).
PREFIX_VERB_REGEX = re.compile(r"\b(می|نمی)\s+([^\s\d.,!؟?،؛:;«»()]+)")
# 'بی' prefix joining: excludes personal pronouns (e.g. "بی تو میمیرم" remains split)
PREFIX_PREP_REGEX = re.compile(r"\b(بی)\s+(?!(?:من|تو|او|ما|شما|آنها|آن‌ها|اینها|این‌ها|هم)\b)([^\s\d.,!؟?،؛:;«»()]+)")

# Curated whitelist of frequent Persian noun/adjective bases for plural suffix joining (P3-8)
# Prevents open-class false positives on verbs, interjections, and particles (e.g. 'رفت ها!', 'نکن ها!', 'ها ها')
PLURAL_NOUN_BASES = {
    # Pronouns / demonstratives
    "آن", "این", "آنها", "اینها",
    # Core everyday nouns
    "کتاب", "دانشجو", "دانش‌آموز", "دانشگاه", "شهر", "کشور", "خانه", "مرد", "زن",
    "کودک", "سال", "روز", "ماه", "شب", "صبح", "عصر", "کار", "چیز", "راه", "دست",
    "چشم", "پا", "سر", "دل", "آب", "گل", "نام", "پیام", "نکته", "درس", "مشکل",
    "پاسخ", "پرسش", "نامه", "فیلم", "عکس", "داستان", "رنگ", "برگ", "درخت", "گیاه",
    "اتاق", "لباس", "کفش", "قلم", "واژه", "کلمه", "جمله", "روش", "شیوه", "گروه",
    "بخش", "دسته", "بچه", "انسان", "حیوان", "پرنده", "ستاره", "سیاره", "زمین",
    "آسمان", "هدف", "امید", "خاطره", "فرصت", "تغییر", "حرکت", "فعالیت", "ویژگی",
    "ابزار", "قانون", "رویداد", "مکان", "زمان", "پدیده", "تجربه", "احساس", "خطا",
    "تصویر", "مطلب", "مقاله", "خبر", "نوشته", "گفته", "داده", "نظام", "سامانه",
    "برنامه", "پروژه", "هزینه", "سهم", "قیمت", "تومان", "ریال", "درصد", "عدد", "رقم",
    "دولت", "ملت", "جامعه", "نهاد", "سازمان", "شرکت", "موسسه", "مؤسسه", "بانک",
    "بیمارستان", "مدرسه", "خیابان", "کوچه", "ساختمان", "فروشگاه", "بازار", "موزه",
    "صدا", "آهنگ", "ساز", "سخن", "شعر", "شاعر", "نویسنده", "خواننده", "بازیگر",
    "هنرمند", "دانشمند", "پژوهشگر", "محقق", "استاد", "معلم", "پزشک", "کارگر",
    "کارمند", "مدیر", "مسئول", "دوست", "دشمن", "همراه", "یار", "مادر", "پدر",
    "برادر", "خواهر", "فرزند", "پسر", "دختر", "عضو", "فرد", "شخص", "عامل",
    "علت", "دلیل", "اثر", "نتیجه", "مورد", "موضوع", "مسئله", "مشکل", "بیماری",
    "دارو", "غذا", "میوه", "حیات", "جهان", "دنیا", "قرن", "دوره", "عصر",
    "ساعت", "لحظه", "ثانیه", "دقیقه", "جلسه", "کلاس", "آزمون", "امتحان",
    "دیدگاه", "نظر", "عقیده", "فکر", "ایده", "طرح", "مدل", "الگو", "ساختار",
    "بافت", "سطح", "لایه", "حوزه", "رشته", "شاخه", "تکنیک", "مهارت", "ابداع",
    "اختراع", "کشف", "تلاش", "اقدام", "تصمیم", "انتخاب", "ارزش", "معیار",
    # Adjectives frequently nominalized in plural
    "خوب", "بد", "بزرگ", "کوچک", "جدید", "قدیم", "زیبا", "مهم", "سخت", "آسان",
    "سریع", "کند", "پاک", "روشن", "تاریک", "پیر", "جوان", "فقیر", "ثروتمند",
}
PLURAL_BASES_PATTERN = "|".join(re.escape(base) for base in sorted(PLURAL_NOUN_BASES, key=len, reverse=True))
SUFFIX_PLURAL_REGEX = re.compile(
    rf"\b({PLURAL_BASES_PATTERN})\s+(ها|های|هایی|هایم|هایت|هایش|هایمان|هایتان|هایشان)\b"
)
SUFFIX_PAST_PARTICIPLE_REGEX = re.compile(r"([^\s\d.,!؟?،؛:;«»()]+ه)\s+(ام|ات|اش|ای|ایم|اید|اند)\b")

# Comparative/superlative suffix joining is NOT applied blanket-style: without POS
# tagging, "لباس تر" (wet clothes) would wrongly become "لباس‌تر" and "تو تری" (you are)
# would become "تو‌تری". Only a curated whitelist of frequent adjective bases is joined.
COMPARATIVE_BASES = (
    "بزرگ|کوچک|بلند|کوتاه|سریع|آهسته|کند|ساده|سخت|آسان|زیبا|قشنگ|"
    "شیرین|تلخ|گرم|سرد|نزدیک|دور|بالا|پایین|زیاد|خوشحال|غمگین|سبک|"
    "سنگین|قوی|ضعیف|تمیز|کثیف|تازه|قدیمی|جوان|پیر|کم|خوب|بد"
)
SUFFIX_COMPARATIVE_REGEX = re.compile(rf"\b({COMPARATIVE_BASES})\s+(تر|ترین|تری)\b")

# High-frequency Persian compounds needing consistent half-spaces
COMMON_COMPOUND_WORDS = {
    r"\bکتاب\s+خانه\b": f"کتاب{ZWNJ}خانه",
    r"\bدارو\s+خانه\b": f"داروخانه",
    r"\bدانش\s+گاه\b": f"دانشگاه",
    r"\bدانش\s+نامه\b": f"دانش{ZWNJ}نامه",
    r"\bروز\s+نامه\b": f"روزنامه",
    r"\bبه\s+ویژه\b": f"به{ZWNJ}ویژه",
    r"\bگفت\s+و\s+گو\b": f"گفت{ZWNJ}و{ZWNJ}گو",
    r"\bرو\s+به\s+رو\b": f"رو{ZWNJ}به{ZWNJ}رو",
    r"\bدست\s+کم\b": f"دست{ZWNJ}کم",
    r"\bآن\s+ها\b": f"آن{ZWNJ}ها",
    r"\bاین\s+ها\b": f"این{ZWNJ}ها",
}

# Floating punctuation: attach horizontal whitespace before punctuation to preceding token (P3-3, P3-9)
FLOATING_PUNCTUATION_REGEX = re.compile(r"[ \t]+([.!؟،؛:;,…»]+)")

# URLs, emails, and punctuation shield
URL_REGEX = re.compile(r"(https?://[^\s]+|www\.[^\s]+)")
EMAIL_REGEX = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
SENTENCE_TRAILING_PUNCT = ".!؟,;،؛»)]}"


def normalize_text(text: str) -> str:
    """Applies comprehensive Persian text normalization.

    Ensures consistent, deterministic text representation for speed reading.
    """
    if not text:
        return ""

    # 1. Shield URLs and Email addresses from Persian character & digit transformations
    placeholders = {}
    shield_salt = uuid.uuid4().hex[:8]

    def shield_url(match):
        val = match.group(0)
        trail = ""
        while val and val[-1] in SENTENCE_TRAILING_PUNCT:
            # Respect balanced parentheses and brackets within URLs (e.g. Wikipedia links)
            if val[-1] == ")" and val.count("(") >= val.count(")"):
                break
            if val[-1] == "]" and val.count("[") >= val.count("]"):
                break
            trail = val[-1] + trail
            val = val[:-1]
        key = f"__RSVPURL_{shield_salt}_{len(placeholders)}__"
        placeholders[key] = val
        return key + trail

    def shield_email(match):
        val = match.group(0)
        trail = ""
        while val and val[-1] in SENTENCE_TRAILING_PUNCT:
            trail = val[-1] + trail
            val = val[:-1]
        key = f"__RSVPEMAIL_{shield_salt}_{len(placeholders)}__"
        placeholders[key] = val
        return key + trail

    text = URL_REGEX.sub(shield_url, text)
    text = EMAIL_REGEX.sub(shield_email, text)

    # 2. Unicode NFC Canonical Normalization
    text = unicodedata.normalize("NFC", text)

    # 3. Map Arabic characters and digits to Persian
    for ar, fa in ARABIC_TO_PERSIAN_MAP.items():
        text = text.replace(ar, fa)

    # 4. Remove tatweel (kashida)
    text = text.replace("ـ", "")

    # 5. Strip Arabic diacritics (harakat)
    text = DIACRITICS_REGEX.sub("", text)

    # 6. Strip invisible directional formatting characters
    text = INVISIBLE_MARKS_REGEX.sub("", text)

    # 7. Standardize quotes & dashes
    text = re.sub(r'"([^"\n]+)"', r"«\1»", text)
    text = text.replace("“", "«").replace("”", "»")
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("–", "-").replace("—", "-")

    # 8. Normalize Persian punctuation
    text = re.sub(r"\.{3,}", "…", text)
    text = re.sub(r"\?{2,}", "؟", text)
    text = re.sub(r"!{2,}", "!", text)
    # Convert trailing Latin/Arabic question mark/comma to Persian if preceded by Persian characters/digits
    text = re.sub(r"([آ-ی۰-۹])\?", r"\1؟", text)
    text = re.sub(r"([آ-ی]),", r"\1،", text)
    text = re.sub(r"([۰-۹]),\s", r"\1، ", text)
    text = re.sub(r"([آ-ی]);", r"\1؛", text)
    text = re.sub(r"([۰-۹]);\s", r"\1؛ ", text)

    # 9. Persian number & numeral handling (P3-6: Persian decimal separator ٫ and decimal comma)
    def to_persian_digits(m):
        return "".join(ASCII_TO_PERSIAN_DIGITS.get(c, c) for c in m.group(0))

    # Convert ASCII digits not embedded in Latin words/identifiers
    text = re.sub(r"(?<![a-zA-Z0-9_\-])([0-9]+)(?![a-zA-Z0-9_\-])", to_persian_digits, text)

    # Normalize Arabic thousands separator (٬ / \u066c) between digits to standard thousands comma (,)
    text = re.sub(r"(?<=[۰-۹0-9])\u066c(?=[۰-۹0-9])", ",", text)

    # Normalize decimal comma between digits:
    # If comma is followed by 1 or 2 digits (e.g. ۱۲,۵ or ۰,۲۵ or ۳,۱۴), convert to official Persian decimal separator ٫ (\u066b).
    # Thousands separator groups (e.g. ۱۲,۵۰۰) remain intact.
    text = re.sub(r"(?<=[۰-۹0-9]),(?=[۰-۹0-9]{1,2}(?:[^\d۰-۹]|$))", "\u066b", text)

    # Normalize decimal point between digits (e.g. ۳.۱۴) to Persian decimal separator ٫ (\u066b)
    text = re.sub(r"(?<=[۰-۹0-9])\.(?=[۰-۹0-9])", "\u066b", text)

    # Normalize percent signs to canonical form (Number + ٪, e.g. ۲۵٪)
    text = re.sub(r"٪\s*([۰-۹0-9]+)", r"\1٪", text)
    text = re.sub(r"%\s*([۰-۹0-9]+)", r"\1٪", text)
    text = re.sub(r"([۰-۹0-9]+)\s*%", r"\1٪", text)
    text = re.sub(r"([۰-۹0-9]+)\s*٪", r"\1٪", text)

    # 10. Persian affix and half-space (ZWNJ) normalization
    # Collapse any stray spaces surrounding ZWNJ characters into clean single ZWNJ
    text = re.sub(r"(?<=\S)\s*\u200c+\s*(?=\S)", ZWNJ, text)
    text = re.sub(r"^\u200c+|\u200c+$", "", text)
    text = re.sub(r"(?<=\s)\u200c+(?=\s)", "", text)

    # Common Persian compounds
    for pattern, repl in COMMON_COMPOUND_WORDS.items():
        text = re.sub(pattern, repl, text)

    # Prefixes (می‌ / نمی‌ / بی‌)
    text = PREFIX_VERB_REGEX.sub(rf"\1{ZWNJ}\2", text)
    text = PREFIX_PREP_REGEX.sub(rf"\1{ZWNJ}\2", text)

    # Suffixes (-ها, -تر, -ترین, -ام)
    text = SUFFIX_PLURAL_REGEX.sub(rf"\1{ZWNJ}\2", text)
    text = SUFFIX_COMPARATIVE_REGEX.sub(rf"\1{ZWNJ}\2", text)
    text = SUFFIX_PAST_PARTICIPLE_REGEX.sub(rf"\1{ZWNJ}\2", text)

    # Clean redundant and stray ZWNJs
    text = re.sub(rf"{ZWNJ}+", ZWNJ, text)

    # 11. Attach floating punctuation to preceding token (P3-3, P3-9)
    text = FLOATING_PUNCTUATION_REGEX.sub(r"\1", text)

    # 12. Clean redundant whitespace and preserve sentence-bounding newlines (P3-3, P3-9)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 13. Restore shielded URLs and Emails
    for k, v in placeholders.items():
        text = text.replace(k, v)

    return text.strip()
