"""Integration and Unit tests for Persian RSVP API, Authentication, and RSVP Engine."""

import asyncio
import os
import re
import tempfile
from pathlib import Path

# CRITICAL FIX: Isolate test database so development db.sqlite3 is never touched or deleted
TEST_DB_FILE = Path(tempfile.gettempdir()) / "persian_rsvp_isolated_test.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite://{TEST_DB_FILE}"

try:
    import pytest
except ImportError:
    pytest = None

from httpx import AsyncClient, ASGITransport
from tortoise import Tortoise

from app import app
from database import TORTOISE_ORM
from models import SavedText, User
from rsvp_engine import (
    EngineInput,
    RSVPChunkResponse,
    RSVPEngine,
    RSVPToken,
)
from rsvp_engine.chunking import create_chunks
from rsvp_engine.difficulty import calculate_word_metrics
from rsvp_engine.frequency import get_word_frequency
from rsvp_engine.models import ENGINE_VERSION
from rsvp_engine.normalization import normalize_text
from rsvp_engine.orp import calculate_orp
from rsvp_engine.pacing import calculate_duration_weight
from rsvp_engine.semantics import analyze_token_boundaries, is_clause_boundary, is_sentence_boundary
from rsvp_engine.tokenizer import tokenize


def maybe_async_test(fn):
    if pytest is not None:
        return pytest.mark.asyncio(fn)
    return fn


def test_rsvp_engine_modular_units():
    """Unit tests for independent rsvp_engine modules."""
    # 1. Normalization: Arabic letters, digits, diacritics, invisible marks
    raw = "كِتَابٌ‌خانه‌يِ   ما   ـ  \u200f١٢٣٤٥\u200e  تندخوانی"
    normalized = normalize_text(raw)
    assert "ک" in normalized
    assert "ی" in normalized
    assert "ـ" not in normalized       # Kashida removed
    assert "ِ" not in normalized       # Kasra removed
    assert "ٌ" not in normalized       # Tanween removed
    assert "\u200f" not in normalized  # RLM mark removed
    assert "\u200e" not in normalized  # LRM mark removed
    assert "۱۲۳۴۵" in normalized       # Arabic-Indic to Persian digits

    # 2. Tokenizer module
    tokens = tokenize("می‌خواهم کتاب‌خانه را ببینم.")
    assert len(tokens) == 4
    assert tokens[0] == "می‌خواهم"
    assert tokens[1] == "کتاب‌خانه"

    # 3. ORP calculation module & trailing punctuation stability
    assert calculate_orp("او") == 0
    # Crucial: ORP must be computed on core word, so trailing punctuation does not shift focal point!
    assert calculate_orp("تندخوانی") == calculate_orp("تندخوانی.")
    assert calculate_orp("«کتاب»") == 2  # skips « and points to 'ت'

    # 4. Pacing calculation module
    base_weight = calculate_duration_weight("کتاب")
    sentence_end_weight = calculate_duration_weight("کتاب.")
    long_compound_weight = calculate_duration_weight("بین‌المللی‌سازی")
    assert base_weight == 100
    assert sentence_end_weight >= 185
    assert long_compound_weight > base_weight

    # 5. Chunking module & engine_version
    dummy_tokens = [RSVPToken(w=f"word_{i}", orp=1, d=100) for i in range(10)]
    chunk_0 = create_chunks(dummy_tokens, chunk_index=0, chunk_size=3)
    assert chunk_0.engine_version == ENGINE_VERSION
    assert chunk_0.chunk_index == 0
    assert chunk_0.total_chunks == 4
    assert chunk_0.total_tokens == 10
    assert chunk_0.has_more is True
    assert len(chunk_0.tokens) == 3

    # 6. RSVPEngine facade with EngineInput contract
    inp = EngineInput(text="تندخوانی سریع و آسان", chunk_index=0, chunk_size=2)
    resp = RSVPEngine.process_input(inp)
    assert isinstance(resp, RSVPChunkResponse)
    assert resp.engine_version == ENGINE_VERSION
    assert resp.total_tokens == 4
    assert resp.total_chunks == 2
    assert resp.has_more is True


def test_persian_phase2_normalization_and_tokenization():
    """Phase 2 comprehensive tests: Persian normalization, ZWNJ, numbers, URLs, and tokenization."""
    # 1. Four core examples from Phase 2 spec: می‌خواهم, کتاب‌خانه, آن‌ها, رفته‌ام.
    # A) Pre-composed ZWNJ text
    spec_text = "می‌خواهم کتاب‌خانه آن‌ها رفته‌ام."
    norm_spec = normalize_text(spec_text)
    assert "می‌خواهم" in norm_spec
    assert "کتاب‌خانه" in norm_spec
    assert "آن‌ها" in norm_spec
    assert "رفته‌ام." in norm_spec
    tokens_spec = tokenize(norm_spec)
    assert tokens_spec == ["می‌خواهم", "کتاب‌خانه", "آن‌ها", "رفته‌ام."]

    # B) Un-normalized space-separated input automatically corrected to proper ZWNJ
    dirty_affixes = "من می خواهم کتاب خانه آن ها را ببینم و دیروز رفته ام ."
    norm_dirty = normalize_text(dirty_affixes)
    tokens_dirty = tokenize(norm_dirty)
    assert "می‌خواهم" in tokens_dirty
    assert "کتاب‌خانه" in tokens_dirty
    assert "آن‌ها" in tokens_dirty
    assert "رفته‌ام." in tokens_dirty

    # C) Stray spaces around ZWNJ (e.g. keyboard typing accidents: Space + ZWNJ)
    stray_zwnj = "کتاب \u200c خانه و می\u200c خواهم و بی\u200c فایده"
    norm_stray = normalize_text(stray_zwnj)
    tokens_stray = tokenize(norm_stray)
    assert tokens_stray == ["کتاب‌خانه", "و", "می‌خواهم", "و", "بی‌فایده"]

    # 2. Persian numerals and formatted numbers: ۱۲,۵۰۰, ۳٫۱۴, ۲۵٪
    num_text = "قیمت ۱۲,۵۰۰ تومان و عدد ۳.۱۴ و تخفیف ٪ ۲۵ است."
    norm_num = normalize_text(num_text)
    assert "۱۲,۵۰۰" in norm_num
    assert "۳٫۱۴" in norm_num
    assert "۲۵٪" in norm_num
    tokens_num = tokenize(norm_num)
    assert "۱۲,۵۰۰" in tokens_num
    assert "۳٫۱۴" in tokens_num
    assert "۲۵٪" in tokens_num

    # Percent canonicalization (P2-2): all percent inputs must produce identical canonical NUMBER + ٪
    for p_variant in ["٪ ۲۵", "٪۲۵", "25%", "۲۵%", "۲۵ ٪"]:
        assert "۲۵٪" in normalize_text(p_variant)
        assert tokenize(normalize_text(p_variant)) == ["۲۵٪"]

    # Conversion of unformatted Latin digits in Persian text, preserving identifiers like COVID-19
    latin_nums = "سال 1402 و قیمت 12,500 و درصد 25% با شیوع COVID-19."
    norm_latin = normalize_text(latin_nums)
    tokens_latin = tokenize(norm_latin)
    assert "۱۴۰۲" in tokens_latin
    assert "۱۲,۵۰۰" in tokens_latin
    assert "۲۵٪" in tokens_latin
    assert "COVID-19." in tokens_latin  # Latin identifier preserved!

    # 3. URLs and emails preservation
    web_text = "به https://taaghche.com/book/123 مراجعه کنید یا به info@fidibo.com ایمیل بزنید."
    norm_web = normalize_text(web_text)
    tokens_web = tokenize(norm_web)
    assert "https://taaghche.com/book/123" in tokens_web
    assert "info@fidibo.com" in tokens_web

    # URL/email with sentence-ending punctuation attached
    web_end_text = "لینک خرید: https://taaghche.com/book/123. ایمیل پشتیبانی: support@example.ir!"
    norm_web_end = normalize_text(web_end_text)
    tokens_web_end = tokenize(norm_web_end)
    assert "https://taaghche.com/book/123." in tokens_web_end
    assert "support@example.ir!" in tokens_web_end

    # Balanced parenthesized URLs (P3-4)
    paren_url_text = "(https://taaghche.com/book/123)"
    norm_paren = normalize_text(paren_url_text)
    assert tokenize(norm_paren) == ["(https://taaghche.com/book/123)"]

    # 4. Deterministic tokenization across messy formatting
    clean_p = "او گفت: «کتاب خوانده شد.»"
    messy_p = "او  گفت :  «  کتاب  خوانده  شد  .  »"
    tokens_clean = tokenize(normalize_text(clean_p))
    tokens_messy = tokenize(normalize_text(messy_p))
    assert tokens_clean == tokens_messy
    assert tokens_clean == ["او", "گفت:", "«کتاب", "خوانده", "شد.»"]

    # 5. Elimination of isolated floating punctuation (no orphan punctuation frames)
    for t in tokens_messy:
        assert t not in {".", "!", "؟", "،", "؛", ":", "«", "»", "(", ")"}

    # 6. Character normalization & Hamza preservation
    persian_ortho = "مسئله‌ی رئیس و اعضای هیئت و فرد مطمئن و تأثیر مؤثر."
    norm_ortho = normalize_text(persian_ortho)
    assert "مسئله" in norm_ortho
    assert "رئیس" in norm_ortho
    assert "مطمئن" in norm_ortho
    assert "مؤثر" in norm_ortho

    # 7. End-to-end plan generation through RSVPEngine
    plan = RSVPEngine.generate_token_plan("او گفت: «کتاب‌خانه باز است.» قیمت آن ۱۲,۵۰۰ تومان است.")
    words = [token.w for token in plan]
    assert words == ["او", "گفت:", "«کتاب‌خانه", "باز", "است.»", "قیمت", "آن", "۱۲,۵۰۰", "تومان", "است."]
    quote_token = [t for t in plan if t.w == "است.»"][0]
    assert quote_token.d >= 185
    compound_token = [t for t in plan if t.w == "«کتاب‌خانه"][0]
    assert compound_token.orp > 0

    # 8. Regression test for P1-1: Comparative suffix whitelist (negative & positive cases)
    # Negative cases: must NOT join non-adjectives or homographs
    neg_comp_1 = normalize_text("لباس تر بود.")
    assert "لباس تر" in neg_comp_1
    assert "لباس‌تر" not in neg_comp_1
    assert "لباستر" not in neg_comp_1

    neg_comp_2 = normalize_text("تو تری که میدانی.")
    assert "تو تری" in neg_comp_2
    assert "توتری" not in neg_comp_2
    assert "تو‌تری" not in neg_comp_2

    # Positive cases: whitelisted adjectives MUST join with ZWNJ
    pos_comp = normalize_text("این راه بزرگ تر و خوب ترین و آسان تر است.")
    assert "بزرگ‌تر" in pos_comp
    assert "خوب‌ترین" in pos_comp
    assert "آسان‌تر" in pos_comp

    # 9. Regression test for P1-2: Multi-character punctuation runs must not become orphan frames
    punct_run_text = "کتاب !!! ... ؟؟؟ خوانده شد."
    tokens_punct_run = tokenize(normalize_text(punct_run_text))
    # No standalone punctuation frame permitted
    for t in tokens_punct_run:
        assert not re.match(r"^[.!؟?،؛:;,…»()\[\]{}٪%-]+$", t), f"Orphan punctuation frame found: {t}"
    assert tokens_punct_run == ["کتاب!…؟؟؟", "خوانده", "شد."]

    # Document-leading punctuation run must be dropped, not emitted as an isolated frame
    leading_punct_run = "!!! ... ؟؟؟ شروع متن."
    tokens_leading_run = tokenize(normalize_text(leading_punct_run))
    for t in tokens_leading_run:
        assert not re.match(r"^[.!؟?،؛:;,…»()\[\]{}٪%-]+$", t)
    assert tokens_leading_run == ["شروع", "متن."]

    # 10. Regression test for P3-1: 'بی' prefix pronoun protection
    pronoun_text = normalize_text("بی تو میمیرم و بی من کجایی و بی فایده بودن.")
    assert "بی تو" in pronoun_text
    assert "بی من" in pronoun_text
    assert "بی‌فایده" in pronoun_text


def test_phase3_orp_and_device_aware_rendering():
    """Phase 3 acceptance tests: Logical ORP centering, ZWNJ safety, and architectural boundaries."""
    # 1. Word length classes (1-3 chars: 0; 4-6 chars: ~1/3; 7+ chars: 1/3 to midpoint)
    assert calculate_orp("من") == 0
    assert calculate_orp("او") == 0
    assert calculate_orp("یک") == 0
    assert calculate_orp("کتاب") == 1
    assert calculate_orp("سرعت") == 1
    assert calculate_orp("تندخو") == 1

    # 2. Long Persian words remain centered around the intended focus point (Plan §6)
    long_words = [
        "تندخوانی",
        "بین‌المللی",
        "بین‌المللی‌سازی",
        "میکروالکترونیک",
        "عکس‌العمل‌هایشان",
        "شخصی‌سازی",
    ]
    for w in long_words:
        orp = calculate_orp(w)
        # Focal character must never be the invisible ZWNJ character
        assert w[orp] != "\u200c", f"ORP landed on ZWNJ in {w}"
        # Centering invariant: ORP position must fall within the core reading zone (between 25% and 55% of word)
        ratio = orp / len(w)
        assert 0.20 <= ratio <= 0.55, f"ORP {orp} in word '{w}' (len {len(w)}, ratio {ratio:.2f}) is off-center"

    # 3. ZWNJ collision avoidance: if computed index lands on ZWNJ, shifts to adjacent readable letter
    # 'می‌خواهم': len 8, chars: ['م', 'ی', '\u200c', 'خ', 'و', 'ا', 'ه', 'م']
    # 8/3 ~ 3 -> 'خ' (index 3), avoids index 2 (ZWNJ)
    orp_verb = calculate_orp("می‌خواهم")
    assert orp_verb != 2
    assert "می‌خواهم"[orp_verb] in {"ی", "خ"}

    # 4. Focal stability across trailing and leading punctuation (attached punctuation must NOT shift ORP)
    base_orp = calculate_orp("تندخوانی")
    assert calculate_orp("تندخوانی.") == base_orp
    assert calculate_orp("تندخوانی؟") == base_orp
    assert calculate_orp("تندخوانی!") == base_orp
    assert calculate_orp("«تندخوانی»") == base_orp + 1  # Offset by 1 for opening quote, landing on same core letter

    # 5. Public contract opacity: tokens contain only {w, orp, d}, no physical pixel predictions
    plan = RSVPEngine.generate_token_plan("بین‌المللی‌سازی متون فارسی.")
    for token in plan:
        assert isinstance(token.w, str)
        assert isinstance(token.orp, int)
        assert isinstance(token.d, int)
        assert 0 <= token.orp < len(token.w)
        # Strictly verify no physical layout leak (backend never predicts pixel dimensions)
        dump = token.model_dump()
        assert set(dump.keys()) == {"w", "orp", "d"}


def test_phase4_basic_cognitive_pacing():
    """Phase 4 acceptance tests: Basic Cognitive Pacing, 4 reading tiers, context & WPM adaptation."""
    # 1. Class 1: Normal words and high-frequency function words (range: [75, 110])
    # High-frequency function words (و, به, در, از, با, تا, که) receive reduced duration (d = 80)
    assert calculate_duration_weight("به", prev_word="کتاب", next_word="دوست") == 80
    assert calculate_duration_weight("و", prev_word="علی", next_word="رضا") == 80
    assert calculate_duration_weight("از", prev_word="من", next_word="او") == 80
    assert calculate_duration_weight("در", prev_word="او", next_word="خانه") == 80

    # Normal mid-sentence content words: base delay (d = 100)
    assert calculate_duration_weight("کتاب", prev_word="یک", next_word="خواندم") == 100
    assert calculate_duration_weight("خواندم", prev_word="کتاب", next_word="و") == 100

    # Standalone word (neutral context without preceding punctuation): base delay (d = 100)
    assert calculate_duration_weight("کتاب") == 100

    # Sentence-initial orienting delay: d = 110
    assert calculate_duration_weight("کتاب", prev_word="^") == 110  # Explicit document start
    assert calculate_duration_weight("کتاب", prev_word="شد.") == 110  # After period
    assert calculate_duration_weight("کتاب", prev_word="آمد؟") == 110  # After question mark
    assert calculate_duration_weight("کتاب", prev_word="دید!»") == 110  # After quote-closed sentence

    # 2. Class 2: Naturally longer reading units, compounds, numerals (range: [115, 145])
    # Shorter compounds with ZWNJ (not triggering long-word threshold)
    d_compound_short = calculate_duration_weight("دل‌تنگ", prev_word="یک", next_word="دیدم")
    assert 115 <= d_compound_short <= 145
    assert d_compound_short == 125  # 115 base + 10 compound

    # Compound + length compound: "کتاب‌خانه" (8 chars >= 7 threshold)
    d_compound_long = calculate_duration_weight("کتاب‌خانه", prev_word="یک", next_word="دیدم")
    assert 115 <= d_compound_long <= 145
    assert d_compound_long == 131  # 115 base + 10 compound + (8-6)*3

    # Formatted numerals
    d_num = calculate_duration_weight("۱۲,۵۰۰", prev_word="قیمت", next_word="تومان")
    assert 115 <= d_num <= 145
    assert d_num == 125  # 115 base + 10 digits

    # Words with character length >= 7 chars
    d_long = calculate_duration_weight("دانشگاه", prev_word="به", next_word="رفت")  # len 7
    assert 115 <= d_long <= 145
    assert d_long == 118  # 115 + (7-6)*3 = 118

    d_very_long = calculate_duration_weight("بین‌المللی‌سازی", prev_word="برای", next_word="متون")
    assert 115 <= d_very_long <= 145

    # 3. Class 3: Clause boundaries and weak punctuation (range: [145, 180])
    d_comma = calculate_duration_weight("آمد،", prev_word="او", next_word="بعد")
    assert 145 <= d_comma <= 180
    assert d_comma == 155

    d_semicolon = calculate_duration_weight("رفت؛", prev_word="او", next_word="سپس")
    assert 145 <= d_semicolon <= 180
    assert d_semicolon == 155

    d_colon = calculate_duration_weight("گفت:", prev_word="او", next_word="ساکت")
    assert 145 <= d_colon <= 180
    assert d_colon == 160

    # Dialogue quotation introducer (colon followed by opening quote)
    d_dialogue = calculate_duration_weight("گفت:", prev_word="او", next_word="«سلام»")
    assert d_dialogue in (165, 170)
    assert d_dialogue > d_colon

    # 4. Class 4: Sentence endings and terminal propositions (range: [185, 260])
    d_period = calculate_duration_weight("شد.", prev_word="تمام", next_word="کتاب", wpm=300)
    assert 185 <= d_period <= 260
    assert d_period == 200

    d_question = calculate_duration_weight("کجا؟", prev_word="او", next_word="رفت", wpm=300)
    assert 185 <= d_question <= 260
    assert d_question == 200

    d_exclamation = calculate_duration_weight("ایست!", prev_word="گفت", next_word="او", wpm=300)
    assert 185 <= d_exclamation <= 260
    assert d_exclamation == 200

    d_ellipsis = calculate_duration_weight("شاید…", prev_word="او", next_word="رفت", wpm=300)
    assert 185 <= d_ellipsis <= 260
    assert d_ellipsis == 220

    # Quote-closed terminal boundary: e.g. "شد.»"
    d_quote_end = calculate_duration_weight("شد.»", prev_word="تمام", next_word=None, wpm=300)
    assert 185 <= d_quote_end <= 260
    assert d_quote_end == 200

    # Priority / Disjoint tier rule: terminal sentence boundary overrides compounding / word length
    # e.g. "کتاب‌خانه." must be Class 4 (>= 185), not Class 2 ([115, 145])
    d_compound_sentence = calculate_duration_weight("کتاب‌خانه.", prev_word="این", next_word="بزرگ", wpm=300)
    assert d_compound_sentence >= 185

    # 5. WPM-derived cognitive adaptation
    # At high WPM (>= 600), human proposition consolidation requires higher relative pause
    wpm_normal = 300
    wpm_high = 900
    d_end_normal = calculate_duration_weight("شد.", wpm=wpm_normal)
    d_end_high = calculate_duration_weight("شد.", wpm=wpm_high)
    assert d_end_normal == 200
    assert d_end_high == 230  # 200 + (900-600)/10 = 230
    assert d_end_high > d_end_normal
    # Non-sentence words (Class 1-3) should remain predictable across WPM changes
    assert calculate_duration_weight("کتاب", prev_word="یک", wpm=wpm_normal) == calculate_duration_weight("کتاب", prev_word="یک", wpm=wpm_high)

    # 6. End-to-end RSVPEngine plan generation and determinism
    text = "او گفت: «تندخوانی روشی مفید است.» کتاب‌خانه ۱۲,۵۰۰ کتاب دارد."
    plan1 = RSVPEngine.generate_token_plan(text, wpm=300)
    plan2 = RSVPEngine.generate_token_plan(text, wpm=300)
    assert len(plan1) == len(plan2)
    for t1, t2 in zip(plan1, plan2):
        assert t1.w == t2.w
        assert t1.orp == t2.orp
        assert t1.d == t2.d

    # Strict public contract opacity: no internal weights or metrics exposed
    for token in plan1:
        dump = token.model_dump()
        assert set(dump.keys()) == {"w", "orp", "d"}
        assert isinstance(token.d, int)
        assert 75 <= token.d <= 260

    # 7. Backend contract for refetch on WPM change:
    # Same text + same chunk_index + new WPM returns tokens reflecting the new cognitive pacing.
    text_refetch = "تندخوانی با روش RSVP حرکات ساکادیک چشم را کاهش می‌دهد. این یک آزمون است."
    chunk_300 = RSVPEngine.get_chunk(text=text_refetch, chunk_index=0, chunk_size=150, wpm=300)
    chunk_900 = RSVPEngine.get_chunk(text=text_refetch, chunk_index=0, chunk_size=150, wpm=900)

    # Word sequence and ORP focal points must be 100% identical
    assert len(chunk_300.tokens) == len(chunk_900.tokens)
    for t300, t900 in zip(chunk_300.tokens, chunk_900.tokens):
        assert t300.w == t900.w
        assert t300.orp == t900.orp

    # Terminal punctuation token duration multiplier must scale up at 900 WPM
    term_token_300 = [t for t in chunk_300.tokens if t.w.endswith(".")][0]
    term_token_900 = [t for t in chunk_900.tokens if t.w.endswith(".")][0]
    assert term_token_300.d == 200
    assert term_token_900.d == 230
    assert term_token_900.d > term_token_300.d


def test_phase5_persian_difficulty_and_frequency():
    """Phase 5 acceptance tests: Difficulty & Frequency Intelligence, P3-6, P3-8, and opaque contract."""
    # 1. P3-6: Persian decimal separator (٫) and decimal-comma normalization
    # Decimal point between digits normalized to canonical Persian decimal separator (٫ / \u066b)
    dec_dot_text = "عدد ۳.۱۴ و نسبت ۲.۷۱۸ و نسخه 3.14 است."
    norm_dot = normalize_text(dec_dot_text)
    assert "۳٫۱۴" in norm_dot
    assert "۲٫۷۱۸" in norm_dot
    tokens_dot = tokenize(norm_dot)
    assert "۳٫۱۴" in tokens_dot

    # Decimal comma between digits (comma followed by 1 or 2 digits) normalized to ٫
    dec_comma_text = "نرخ تورم ۱۲,۵ درصد و احتمال ۰,۲۵ و خطا 12.5 است."
    norm_comma = normalize_text(dec_comma_text)
    assert "۱۲٫۵" in norm_comma
    assert "۰٫۲۵" in norm_comma
    tokens_comma = tokenize(norm_comma)
    assert "۱۲٫۵" in tokens_comma
    assert "۰٫۲۵" in tokens_comma

    # Standard thousands separator (comma followed by 3 digits) and Arabic thousands separator (٬ / \u066c) preserved as ,
    thousands_text = "مبلغ ۱۲,۵۰۰ تومان و بودجه ۱۲٬۵۰۰ ریال است."
    norm_thousands = normalize_text(thousands_text)
    assert "۱۲,۵۰۰" in norm_thousands
    assert "۱۲٬۵۰۰" not in norm_thousands
    tokens_thousands = tokenize(norm_thousands)
    assert "۱۲,۵۰۰" in tokens_thousands

    # Attached punctuation and percent signs on decimals
    dec_punct_text = "عدد ۳٫۱۴. نرخ ۴۲٫۵٪!"
    norm_dec_punct = normalize_text(dec_punct_text)
    tokens_dec_punct = tokenize(norm_dec_punct)
    assert "۳٫۱۴." in tokens_dec_punct
    assert "۴۲٫۵٪!" in tokens_dec_punct

    # 2. P3-8: Whitelist-backed plural 'ها' suffix join vs negative non-plural tests
    # Positive cases: whitelisted nouns/pronouns MUST join with ZWNJ
    pos_plural_text = "کتاب ها و روز ها و کشور های جهان و آن ها و این ها."
    norm_pos = normalize_text(pos_plural_text)
    assert "کتاب‌ها" in norm_pos
    assert "روز‌ها" in norm_pos
    assert "کشور‌های" in norm_pos
    assert "آن‌ها" in norm_pos
    assert "این‌ها" in norm_pos
    assert "کتاب ها" not in norm_pos

    # Negative cases: verbs, interjections, and particles MUST NOT join
    neg_plural_1 = normalize_text("او رفت ها! حواست باشد.")
    assert "رفت ها" in neg_plural_1
    assert "رفت‌ها" not in neg_plural_1

    neg_plural_2 = normalize_text("این کار را نکن ها!")
    assert "نکن ها" in neg_plural_2
    assert "نکن‌ها" not in neg_plural_2

    neg_plural_3 = normalize_text("او آمد ها ولی دیر شد.")
    assert "آمد ها" in neg_plural_3
    assert "آمد‌ها" not in neg_plural_3

    neg_plural_4 = normalize_text("ها ها ها! خیلی خندیدیم.")
    assert "ها ها ها" in neg_plural_4

    neg_plural_5 = normalize_text("ها! چه گفتی؟")
    assert "ها!" in neg_plural_5

    # 3. Lexical difficulty and frequency scoring unit metrics
    # Common words: high frequency, low difficulty
    diff_book, freq_book, comp_book = calculate_word_metrics("کتاب", "کتاب")
    assert freq_book >= 0.75
    assert diff_book <= 0.20

    # Rare words: low frequency, elevated difficulty
    diff_impeach, freq_impeach, comp_impeach = calculate_word_metrics("استیضاح", "استیضاح")
    assert freq_impeach <= 0.15
    assert diff_impeach >= 0.50
    assert diff_impeach > diff_book

    # Highly complex compound: high complexity and difficulty
    diff_intl, freq_intl, comp_intl = calculate_word_metrics("بین‌المللی‌سازی", "بین‌المللی‌سازی")
    assert comp_intl >= 0.60
    assert diff_intl >= 0.70

    # Technical esoteric word
    diff_micro, freq_micro, comp_micro = calculate_word_metrics("میکروالکترونیک", "میکروالکترونیک")
    assert diff_micro >= 0.75

    # 4. Cognitive pacing duration differentials based on difficulty and frequency
    # Class 1: common vs rare word duration
    d_common = calculate_duration_weight("کتاب", prev_word="یک", next_word="خواندم")
    d_rare = calculate_duration_weight("محاق", prev_word="یک", next_word="خواندم")
    assert d_rare > d_common
    assert 75 <= d_common <= 110
    assert 75 <= d_rare <= 110

    # Class 2: common compound vs rare/complex compound
    d_comp_common = calculate_duration_weight("کتاب‌خانه", prev_word="یک", next_word="دیدم")
    d_comp_rare = calculate_duration_weight("بین‌المللی‌سازی", prev_word="برای", next_word="متون")
    assert d_comp_rare > d_comp_common
    assert 115 <= d_comp_common <= 145
    assert 115 <= d_comp_rare <= 145

    # Class 2: common 7-char word vs rare 7-char word
    d_long_common = calculate_duration_weight("دانشگاه", prev_word="به", next_word="رفت")
    d_long_rare = calculate_duration_weight("استیضاح", prev_word="به", next_word="رفت")
    assert d_long_rare > d_long_common
    assert 115 <= d_long_common <= 145
    assert 115 <= d_long_rare <= 145

    # Class 4: rare word + terminal punctuation combination cases
    d_term_common = calculate_duration_weight("شد.", wpm=300)
    d_term_rare = calculate_duration_weight("استیضاح.", wpm=300)
    assert d_term_rare > d_term_common
    assert 185 <= d_term_common <= 260
    assert 185 <= d_term_rare <= 260

    # Class 3: rare word + clause boundary punctuation
    d_clause_common = calculate_duration_weight("شد،")
    d_clause_rare = calculate_duration_weight("استیضاح،")
    assert d_clause_rare > d_clause_common
    assert 145 <= d_clause_common <= 180
    assert 145 <= d_clause_rare <= 180

    # 5. InternalToken rich metadata vs strict public contract opacity (Rule 5)
    internal_tokens = RSVPEngine.generate_internal_tokens("استیضاح وزیر انجام شد.")
    assert len(internal_tokens) == 4
    rare_token = internal_tokens[0]
    assert rare_token.clean_word == "استیضاح"
    assert rare_token.difficulty_score > 0.50
    assert rare_token.frequency_score < 0.20

    # Public token plan must NEVER leak difficulty_score or frequency_score
    public_tokens = RSVPEngine.generate_token_plan("استیضاح وزیر انجام شد.")
    for token in public_tokens:
        dump = token.model_dump()
        assert set(dump.keys()) == {"w", "orp", "d"}
        assert not hasattr(token, "difficulty_score")
        assert not hasattr(token, "frequency_score")

    # 6. Determinism: identical input + engine version + wpm yields bit-for-bit identical outputs
    plan_a = RSVPEngine.generate_token_plan("استیضاح در مجلس انجام شد.", wpm=350)
    plan_b = RSVPEngine.generate_token_plan("استیضاح در مجلس انجام شد.", wpm=350)
    assert len(plan_a) == len(plan_b)
    for ta, tb in zip(plan_a, plan_b):
        assert ta.w == tb.w
        assert ta.orp == tb.orp
        assert ta.d == tb.d

    # 7. Version bump verification
    assert ENGINE_VERSION >= "2026.05.1"

    # 8. Regression tests for P2-1: Conjugated verb frequency inheritance & Class 2 demotion
    # a. Inheritance: get_word_frequency for common inflected forms >= 0.60
    assert get_word_frequency("میخواهم") >= 0.60
    assert get_word_frequency("می‌خواهم") >= 0.60
    assert get_word_frequency("میخوانم") >= 0.60
    assert get_word_frequency("می‌خوانم") >= 0.60
    assert get_word_frequency("گفتهام") >= 0.60
    assert get_word_frequency("گفته‌ام") >= 0.60
    assert get_word_frequency("کتابها") >= 0.60
    assert get_word_frequency("کتاب‌ها") >= 0.60
    assert get_word_frequency("میدهم") >= 0.60
    assert get_word_frequency("می‌دهم") >= 0.60
    assert get_word_frequency("میروند") >= 0.60
    assert get_word_frequency("می‌روند") >= 0.60
    assert get_word_frequency("خانوادهام") >= 0.60
    assert get_word_frequency("خانواده‌ام") >= 0.60
    assert get_word_frequency("گوش") >= 0.60
    assert get_word_frequency("سینما") >= 0.60
    assert get_word_frequency("موسیقی") >= 0.60
    assert get_word_frequency("شنبه") >= 0.60
    assert get_word_frequency("رستوران") >= 0.60

    # b. Ceiling test: in natural prose with common inflected verbs, every common-inflected token's d <= rare fixture token's d
    d_rare_fixture = calculate_duration_weight("استیضاح")  # 125
    d_rare_term = calculate_duration_weight("استیضاح.", wpm=300)  # 213
    probe_sentence = "من هر روز کتاب می‌خوانم و به موسیقی گوش می‌دهم."
    plan_probe = RSVPEngine.generate_token_plan(probe_sentence, wpm=300)
    for token in plan_probe:
        if token.w.endswith("."):
            assert token.d <= d_rare_term, f"Terminal token '{token.w}' ({token.d}) exceeded rare term 'استیضاح.' ({d_rare_term})"
        else:
            assert token.d <= d_rare_fixture, f"Token '{token.w}' ({token.d}) exceeded rare fixture 'استیضاح' ({d_rare_fixture})"

    # Also verify natural prose with both common inflected verbs and rare fixture word
    probe_with_rare = "من هر روز کتاب می‌خوانم و موضوع استیضاح را می‌دانم."
    plan_with_rare = RSVPEngine.generate_token_plan(probe_with_rare, wpm=300)
    rare_token = [t for t in plan_with_rare if "استیضاح" in t.w][0]
    verb_token = [t for t in plan_with_rare if "می‌خوانم" in t.w][0]
    assert verb_token.d <= rare_token.d
    assert verb_token.d < rare_token.d  # 100 < 125

    # c. Class demotion: calculate_duration_weight('میخوانم', prev_word='کتاب', next_word='و') lands in Class 1 range [75, 110]
    d_demoted_ascii = calculate_duration_weight("میخوانم", prev_word="کتاب", next_word="و")
    assert 75 <= d_demoted_ascii <= 110
    d_demoted_zwnj = calculate_duration_weight("می‌خوانم", prev_word="کتاب", next_word="و")
    assert 75 <= d_demoted_zwnj <= 110
    # Also verify other common inflected forms demote to Class 1
    assert 75 <= calculate_duration_weight("کتاب‌ها", prev_word="این", next_word="را") <= 110
    assert 75 <= calculate_duration_weight("گفته‌ام", prev_word="من", next_word="این") <= 110
    assert 75 <= calculate_duration_weight("می‌روند", prev_word="آن‌ها", next_word="به") <= 110
    assert 75 <= calculate_duration_weight("گوش", prev_word="به", next_word="می‌دهم") <= 110
    assert 75 <= calculate_duration_weight("موسیقی", prev_word="به", next_word="گوش") <= 110


def test_phase6_semantic_chunking_and_intelligent_pauses():
    """Phase 6: Semantic Chunking & Intelligent Pauses acceptance tests."""
    # 1. P3-3 Hard Gate: Floating punctuation preserves newlines, and \n is a real sentence boundary
    # 1a. normalize_text does not swallow newlines following punctuation
    norm_nl = normalize_text("گفت.\nاو آمد.")
    assert norm_nl == "گفت.\nاو آمد."
    assert "\n" in norm_nl

    # 1b. tokenize preserves newline as sentence-boundary carrier on previous token
    tokens_nl = tokenize(norm_nl)
    assert tokens_nl[0] == "گفت.\n"
    assert tokens_nl[1] == "او"
    assert tokens_nl[2] == "آمد."

    # 1c. RSVPEngine processes unpunctuated newline boundaries (او رفت\nعلی آمد)
    plan_nl = RSVPEngine.generate_token_plan("او رفت\nعلی آمد")
    assert len(plan_nl) == 4
    # Token 0: 'او' (sentence initial orienting delay)
    assert plan_nl[0].w == "او"
    assert plan_nl[0].d == 110
    # Token 1: 'رفت' (precedes newline -> sentence boundary pause)
    assert plan_nl[1].w == "رفت"
    assert plan_nl[1].d >= 185
    assert plan_nl[1].d == 200
    # Token 2: 'علی' (follows newline -> sentence initial orienting delay)
    assert plan_nl[2].w == "علی"
    assert plan_nl[2].d == 110
    # Token 3: 'آمد'
    assert plan_nl[3].w == "آمد"
    assert "\n" not in plan_nl[1].w  # Public contract strips \n

    # 1d. Multi-paragraph text with \n\n preserved
    norm_para = normalize_text("پاراگراف اول.\n\n\nپاراگراف دوم.")
    assert norm_para == "پاراگراف اول.\n\nپاراگراف دوم."
    plan_para = RSVPEngine.generate_token_plan(norm_para)
    tok_p1_end = [t for t in plan_para if "اول" in t.w][0]
    tok_p2_start = [t for t in plan_para if "دوم" in t.w][0]
    assert tok_p1_end.d >= 185

    # 2. P3-9 Ride-Along: Eliminate cosmetic intermediate space in normalized string
    assert normalize_text("کتاب . خوانده شد") == "کتاب. خوانده شد"
    assert normalize_text("کتاب ، خوانده شد") == "کتاب، خوانده شد"
    assert normalize_text("آیا آمد ؟ بله") == "آیا آمد؟ بله"
    assert normalize_text("رفت ! بسیار عالی") == "رفت! بسیار عالی"

    # 3. Sentence Boundary Detection across edge cases
    # 3a. Quoted sentences with internal terminals
    quote_text = "«او گفت: من می‌روم. اما برمی‌گردم.»"
    plan_quote = RSVPEngine.generate_token_plan(quote_text)
    # Token 'می‌روم.' is terminal inside quotes
    tok_quote_mid = [t for t in plan_quote if "می‌روم." in t.w][0]
    assert tok_quote_mid.d >= 185
    # Token 'برمی‌گردم.»' ends the outer quotation
    tok_quote_end = [t for t in plan_quote if "برمی‌گردم.»" in t.w][0]
    assert tok_quote_end.d >= 185
    # Token 'اما' immediately following period receives sentence-initial orienting delay
    tok_ama_after_period = [t for t in plan_quote if t.w == "اما"][0]
    assert tok_ama_after_period.d == 110

    # 3b. Various terminal punctuation marks (. ? ! …)
    term_marks = ["کتاب.", "کتاب؟", "کتاب!", "کتاب…"]
    for tm in term_marks:
        assert is_sentence_boundary(tm) is True

    # 4. Phrase & Semantic Clause Boundary Detection
    # 4a. Subordinating conjunction (که, اگر, چون, زیرا, اگرچه, etc.)
    # Word preceding 'که' receives unpunctuated clause boundary pause (d >= 140)
    plan_sub = RSVPEngine.generate_token_plan("او می‌دانست که فردا باران می‌بارد.")
    tok_midanest = [t for t in plan_sub if "می‌دانست" in t.w][0]
    assert tok_midanest.d >= 140
    assert tok_midanest.d == 145

    # 4b. Adversative/consequential conjunction without punctuation (بود اما)
    plan_adv_unpunct = RSVPEngine.generate_token_plan("اگرچه هوا بسیار سرد بود اما او رفت.")
    tok_bood_unpunct = [t for t in plan_adv_unpunct if t.w == "بود"][0]
    assert tok_bood_unpunct.d >= 140
    assert tok_bood_unpunct.d == 145
    # Regression guard: unpunctuated semantic branch still works (بود اما -> 145)
    assert calculate_duration_weight("بود", next_word="اما", wpm=300) == 145

    # 4c. Adversative conjunction with punctuation (بود، اما) — punctuation + semantic combination bonus
    plan_adv_punct = RSVPEngine.generate_token_plan("اگرچه هوا بسیار سرد بود، اما او رفت.")
    tok_bood_punct = [t for t in plan_adv_punct if t.w == "بود،"][0]
    assert tok_bood_punct.d == 160
    assert 155 <= tok_bood_punct.d <= 180
    assert calculate_duration_weight("بود،", next_word="اما", wpm=300) > calculate_duration_weight("بود،", next_word="بعد", wpm=300)
    assert 155 <= calculate_duration_weight("بود،", next_word="اما", wpm=300) <= 180

    # 4d. Speech verb before quotation (گفت:)
    tok_goft = [t for t in plan_quote if "گفت:" in t.w][0]
    assert tok_goft.d >= 155

    # 5. Long sentence rhythm variance test (avoiding flat-stream reading fatigue)
    long_sentence = (
        "اگرچه بسیاری از پژوهشگران بر این باورند که تندخوانی مهارت مهمی است، "
        "اما تمرین مداوم و درک مطلب دقیق همچنان نیازمند توجه و تمرکز عمیق خواننده خواهد بود."
    )
    plan_long = RSVPEngine.generate_token_plan(long_sentence)
    assert len(plan_long) >= 20
    durations = [t.d for t in plan_long]
    mean_d = sum(durations) / len(durations)
    variance_d = sum((d - mean_d) ** 2 for d in durations) / len(durations)
    # Variance must meaningfully exceed flat-stream baseline (sigma^2 > 400)
    assert variance_d > 400
    # Range between quickest word and longest boundary pause must be at least 90ms
    assert (max(durations) - min(durations)) >= 90

    # 6. Public Token Contract Opacity (Rule 5: No engine-internals leakage)
    for tok in plan_long:
        d_dict = tok.model_dump()
        assert set(d_dict.keys()) == {"w", "orp", "d"}
        assert not hasattr(tok, "is_sentence_end")
        assert not hasattr(tok, "is_clause_end")
        assert not hasattr(tok, "difficulty_score")
        assert not hasattr(tok, "frequency_score")
        assert "\n" not in tok.w

    # 7. Determinism: identical input + engine version + wpm yields bit-for-bit identical outputs
    plan_a = RSVPEngine.generate_token_plan(long_sentence, wpm=350)
    plan_b = RSVPEngine.generate_token_plan(long_sentence, wpm=350)
    assert len(plan_a) == len(plan_b)
    for ta, tb in zip(plan_a, plan_b):
        assert ta.w == tb.w
        assert ta.orp == tb.orp
        assert ta.d == tb.d

    # 8. Version verification
    assert ENGINE_VERSION == "2026.06.1"


@maybe_async_test
async def test_full_auth_and_text_flow():
    # Setup isolated test database schema
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()
    await SavedText.all().delete()
    await User.all().delete()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Register test user
            reg_resp = await client.post(
                "/api/auth/register",
                json={
                    "username": "speed_reader",
                    "password": "strongpassword123",
                    "email": "reader@example.com",
                },
            )
            assert reg_resp.status_code == 201
            data = reg_resp.json()
            assert "access_token" in data
            assert data["user"]["username"] == "speed_reader"
            token = data["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # 2. Duplicate registration check
            dup_resp = await client.post(
                "/api/auth/register",
                json={"username": "speed_reader", "password": "strongpassword123"},
            )
            assert dup_resp.status_code == 400

            # 3. Bad login
            bad_login = await client.post(
                "/api/auth/login",
                json={"username": "speed_reader", "password": "wrong_password"},
            )
            assert bad_login.status_code == 401

            # 4. Successful login
            login_resp = await client.post(
                "/api/auth/login",
                json={"username": "speed_reader", "password": "strongpassword123"},
            )
            assert login_resp.status_code == 200

            # 5. Fetch profile
            me_resp = await client.get("/api/auth/me", headers=headers)
            assert me_resp.status_code == 200
            assert me_resp.json()["username"] == "speed_reader"

            # 6. Update preferred WPM
            patch_resp = await client.patch("/api/auth/me", headers=headers, json={"preferred_wpm": 400})
            assert patch_resp.status_code == 200
            assert patch_resp.json()["preferred_wpm"] == 400

            # 7. Create saved text
            text_resp = await client.post(
                "/api/texts",
                headers=headers,
                json={
                    "title": "مقدمه‌ای بر تندخوانی",
                    "content": "تندخوانی با روش RSVP حرکات سا کادیک چشم را کاهش می‌دهد.",
                    "wpm": 400,
                },
            )
            assert text_resp.status_code == 201
            text_id = text_resp.json()["id"]

            # 8. List saved texts
            list_resp = await client.get("/api/texts", headers=headers)
            assert list_resp.status_code == 200
            assert len(list_resp.json()) == 1

            # 9. RSVP Plan API: raw text plan with chunking and engine_version
            rsvp_raw = await client.post(
                "/api/rsvp/plan",
                json={
                    "text": "تندخوانی روشی سریع برای مطالعه متون فارسی است.",
                    "chunk_size": 3,
                    "chunk_index": 0,
                },
            )
            assert rsvp_raw.status_code == 200
            raw_data = rsvp_raw.json()
            assert raw_data["engine_version"] == ENGINE_VERSION
            assert raw_data["total_tokens"] == 8
            assert raw_data["total_chunks"] == 3
            assert raw_data["has_more"] is True
            assert len(raw_data["tokens"]) == 3
            assert "w" in raw_data["tokens"][0]
            assert "orp" in raw_data["tokens"][0]
            assert "d" in raw_data["tokens"][0]

            # 10. RSVP Plan API: saved text plan by text_id
            rsvp_saved = await client.post(
                "/api/rsvp/plan",
                headers=headers,
                json={"text_id": text_id, "chunk_size": 10, "chunk_index": 0},
            )
            assert rsvp_saved.status_code == 200
            saved_plan = rsvp_saved.json()
            assert saved_plan["total_tokens"] > 0
            assert saved_plan["engine_version"] == ENGINE_VERSION

            # 11. RSVP Plan API: explicit WPM support and refetch pacing derivation
            rsvp_wpm_300 = await client.post(
                "/api/rsvp/plan",
                json={
                    "text": "خواندن این کتاب تمام شد.",
                    "wpm": 300,
                },
            )
            assert rsvp_wpm_300.status_code == 200
            tokens_300 = rsvp_wpm_300.json()["tokens"]
            term_tok_300 = [t for t in tokens_300 if t["w"] == "شد."][0]
            assert term_tok_300["d"] == 200

            rsvp_wpm_900 = await client.post(
                "/api/rsvp/plan",
                json={
                    "text": "خواندن این کتاب تمام شد.",
                    "wpm": 900,
                },
            )
            assert rsvp_wpm_900.status_code == 200
            tokens_900 = rsvp_wpm_900.json()["tokens"]
            term_tok_900 = [t for t in tokens_900 if t["w"] == "شد."][0]
            assert term_tok_900["d"] == 230  # High-speed WPM cognitive pause boost
            assert term_tok_900["d"] > term_tok_300["d"]

            # 12. Unbounded text rejection (> 100,000 chars)
            giant_text = "تندخوانی " * 15000  # > 120,000 chars
            unbounded_resp = await client.post(
                "/api/rsvp/plan",
                json={"text": giant_text},
            )
            assert unbounded_resp.status_code == 422

            # 13. Delete saved text
            del_resp = await client.delete(f"/api/texts/{text_id}", headers=headers)
            assert del_resp.status_code == 204

    finally:
        await Tortoise.close_connections()
        if TEST_DB_FILE.exists():
            try:
                TEST_DB_FILE.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    test_rsvp_engine_modular_units()
    test_persian_phase2_normalization_and_tokenization()
    test_phase3_orp_and_device_aware_rendering()
    test_phase4_basic_cognitive_pacing()
    test_phase5_persian_difficulty_and_frequency()
    test_phase6_semantic_chunking_and_intelligent_pauses()
    asyncio.run(test_full_auth_and_text_flow())
    print("All tests passed successfully!")
