# app.py — 78枚フルタロット + D9(ナヴァムシャ) + ヴィムショッタリ・ダシャ 本格実装
import os
import math
import random
from datetime import datetime, date, time, timedelta

import streamlit as st
from fpdf import FPDF

# ==== Optional astrology libs (fallback if missing) ====
HAS_ASTRO = True
try:
    import swisseph as swe
    from geopy.geocoders import Nominatim
    from timezonefinder import TimezoneFinder
    import pytz
except Exception:
    HAS_ASTRO = False

# =============== ページ設定 ===============
st.set_page_config(page_title="🔮 AI統合占い(78枚+D9+ダシャ)", page_icon="🔮", layout="wide")

# セッション初期化
if "history" not in st.session_state:
    st.session_state.history = []

# --- Secrets 読み込み（無ければ空文字） ---
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
PAID_CHECKOUT_URL = st.secrets.get("PAID_CHECKOUT_URL", "")  # Stripe/BASE の購入ページ
PREMIUM_ACCESS_CODES = set(st.secrets.get("PREMIUM_ACCESS_CODES", []))
BRAND_NAME = st.secrets.get("BRAND_NAME", "AI統合占い")
AD_LINK = st.secrets.get("AD_LINK", "https://example.com")

# =============== 78枚タロット定義 ===============
MAJOR = ["愚者","魔術師","女教皇","女帝","皇帝","法王","恋人","戦車","力","隠者","運命の輪","正義","吊るされた男","死神","節制","悪魔","塔","星","月","太陽","審判","世界"]
SUITS = {
    "Wands": [f"ワンド{n}" for n in ["エース","2","3","4","5","6","7","8","9","10","ペイジ","ナイト","クイーン","キング"]],
    "Cups": [f"カップ{n}" for n in ["エース","2","3","4","5","6","7","8","9","10","ペイジ","ナイト","クイーン","キング"]],
    "Swords": [f"ソード{n}" for n in ["エース","2","3","4","5","6","7","8","9","10","ペイジ","ナイト","クイーン","キング"]],
    "Pentacles": [f"ペンタクル{n}" for n in ["エース","2","3","4","5","6","7","8","9","10","ペイジ","ナイト","クイーン","キング"]],
}
ALL_78 = MAJOR + sum(SUITS.values(), [])

SPREADS = {
    "一枚引き": 1,
    "過去-現在-未来": 3,
    "ヘキサグラム(簡易)": 6,
    "ケルト十字(簡易10)": 10
}

CARD_MEANINGS = {
    # 主要カードのみ簡易メモ（必要に応じて拡張）
    "愚者": "自由/新しい旅立ち。逆位置: 無計画/衝動",
    "女教皇": "直感/静観。逆位置: 閉鎖/鈍化",
    "恋人": "選択/調和。逆位置: 優柔不断/不一致",
    "星": "希望/インスピレーション。逆位置: 期待過多",
    "月": "曖昧/不安。逆位置: 霧が晴れる",
    "太陽": "成功/活力。逆位置: 焦り/一時停滞",
    "世界": "完成/統合。逆位置: 未完/仕上げ不足",
}

# =============== タロット関数 ===============

def draw_cards(n: int):
    cards = random.sample(ALL_78, k=min(n, len(ALL_78)))
    result = []
    for c in cards:
        pos = random.choice(["正位置","逆位置"])
        result.append((c, pos))
    return result


def render_cards(cards):
    items = []
    for name, pos in cards:
        tip = CARD_MEANINGS.get(name.split("(")[0], "")
        items.append(f"{name}（{pos}）" + (f" — {tip}" if tip else ""))
    return "\n".join(["・" + it for it in items])

# =============== 占断生成（OpenAI or ダミー） ===============

def compose_prompt(name, birth, question, cards, mode="free"):
    base = f"""
あなたはインド占星術(D1/D9)とヴィムショッタリ・ダシャ、タロット78枚、エンジェルカードを統合する占い師です。
出力は日本語で、ニュートラルかつ具体的に。過度な断定/医療・法律助言は避けます。

依頼者: {name}
出生情報: {birth}
相談内容: {question}
引いたカード: {', '.join([f"{n}({p})" for n,p in cards])}
出力要件:
- 見出し『総合鑑定結果』
- 全体像 200字
- 恋愛/仕事/金運/対人/今月の鍵 各150〜220字
- 具体的アクション: 箇条書き3〜5
- 最後に前向きな一言
- 文字量: {"約400字(無料)" if mode=="free" else "合計900字以上(有料)"}
""".strip()
    return base


def generate_reading(prompt: str, mode="free") -> str:
    if not OPENAI_API_KEY:
        # ダミー
        body = (
            "【総合鑑定結果】
"
            "変化は穏やかに進行。既存の強みを磨くほど成果が出やすい流れです。

"
            "● 恋愛: 小さな誤解は早期解消が鍵。共通の体験作りを。
"
            "● 仕事: 既存顧客の深堀りが売上に直結。提案書を簡潔に。
"
            "● 金運: 小さな固定費の見直しで可処分が増える。
"
            "● 対人: 主張<傾聴。相手の意図を言い換えて確認。
"
            "● 今月の鍵: 朝の散歩とメモ習慣。

"
            "■ 行動
・週3で作品発信
・既存案件の再編集提案
・小口メニューを用意し受注口を増やす

前向きな一言: 丁寧な積み重ねが最短の近道です。"
        )
        return body if mode=="free" else body + "

【詳細補足】コラボ提案は今期の追い風…"

    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        completion = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"あなたは優秀な占い師です。"},
                {"role":"user","content": prompt}
            ],
            temperature=0.8,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"（AI生成エラー: {e}）
フォールバックメッセージ: 調整と整えがテーマです…"

# =============== PDF出力 ===============

def build_pdf(title: str, body: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font('Arial', size=12)
    pdf.cell(0, 10, txt=title, ln=True)
    for line in body.split('
'):
        pdf.multi_cell(0, 8, line)
    return pdf.output(dest='S').encode('latin-1', errors='ignore')

# =============== インド占星術ユーティリティ ===============

PLANETS = [
    ("Sun", swe.SUN), ("Moon", swe.MOON), ("Mars", swe.MARS), ("Mercury", swe.MERCURY),
    ("Jupiter", swe.JUPITER), ("Venus", swe.VENUS), ("Saturn", swe.SATURN),
    ("Rahu", swe.MEAN_NODE), ("Ketu", -1)  # Ketu はRahu反対点
] if HAS_ASTRO else []

NAKSHATRA_NAMES = [
    "アシュウィニ","バラニ","クリティカ","ロヒニ","ムリガシラー","アルドラ","プナルヴァス","プシャ","アーシュレーシャ",
    "マガ","プールヴァ・パルグニ","ウッタラ・パルグニ","ハスタ","チトラー","スワーティ","ヴィシャーカー","アヌラーダ","ジェーシュタ",
    "ムーラ","プールヴァ・アシャーダ","ウッタラ・アシャーダ","シュラヴァナ","ダニシュタ","シャタビシャ","プールヴァ・バドラパダ","ウッタラ・バドラパダ","レーヴァティ"
] if HAS_ASTRO else []

VIM_MAHA_ORDER = ["Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury"]
VIM_MAHA_YEARS = {"Ketu":7,"Venus":20,"Sun":6,"Moon":10,"Mars":7,"Rahu":18,"Jupiter":16,"Saturn":19,"Mercury":17}


def geo_time(birth_date: date, birth_time: time, place: str):
    if not HAS_ASTRO:
        return None
    geolocator = Nominatim(user_agent="ai_fortune_app")
    loc = geolocator.geocode(place, timeout=10)
    if not loc:
        raise ValueError("場所が見つかりませんでした")
    tz = TimezoneFinder().timezone_at(lng=loc.longitude, lat=loc.latitude)
    if not tz:
        tz = "UTC"
    tzobj = pytz.timezone(tz)
    local_dt = tzobj.localize(datetime.combine(birth_date, birth_time))
    utc_dt = local_dt.astimezone(pytz.utc)
    return {
        "lat": loc.latitude,
        "lon": loc.longitude,
        "tz": tz,
        "utc": utc_dt
    }


def julday_from_utc(utc_dt: datetime):
    if not HAS_ASTRO:
        return None
    return swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute/60 + utc_dt.second/3600)


def normalize_deg(d):
    d = d % 360.0
    return d


def rasi_sign_index(longitude):
    # 0: Aries… 11: Pisces
    return int(math.floor(normalize_deg(longitude) / 30))


def navamsa_sign_index(longitude):
    # 各ラシ30度、ナヴァムシャは3°20' = 3.333... 度
    rasi = rasi_sign_index(longitude)
    deg_in_sign = normalize_deg(longitude) - rasi*30
    pada = int(deg_in_sign // (3
