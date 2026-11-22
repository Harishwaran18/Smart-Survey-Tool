"""Design tokens and global CSS for the Streamlit front-end."""

from __future__ import annotations

import streamlit as st

PALETTE = {
    "primary": "#4F46E5",
    "primary_dark": "#3730A3",
    "accent": "#06B6D4",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "neutral": "#64748B",
    "surface": "#FFFFFF",
    "muted": "#F1F5F9",
    "text": "#0F172A",
}

SENTIMENT_COLORS = {
    "POSITIVE": PALETTE["success"],
    "NEUTRAL": PALETTE["neutral"],
    "NEGATIVE": PALETTE["danger"],
}

SEVERITY_COLORS = {
    "critical": PALETTE["danger"],
    "warning": PALETTE["warning"],
    "positive": PALETTE["success"],
    "info": PALETTE["accent"],
}

_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

  html, body, [class*="css"] { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
  .stApp { background: #F8FAFC; }
  .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }

  .hero {
    background: linear-gradient(120deg, #4F46E5 0%, #6366F1 45%, #06B6D4 100%);
    border-radius: 18px; padding: 26px 30px; color: #fff; margin-bottom: 22px;
    box-shadow: 0 18px 40px -18px rgba(79,70,229,.65);
  }
  .hero h1 { margin: 0; font-size: 1.9rem; font-weight: 800; letter-spacing: -.02em; }
  .hero p { margin: 6px 0 0; opacity: .9; font-size: .95rem; }
  .hero .pill {
    display: inline-block; margin-top: 12px; padding: 4px 12px; border-radius: 999px;
    background: rgba(255,255,255,.18); font-size: .75rem; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase;
  }

  .kpi {
    background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 18px 20px;
    box-shadow: 0 1px 2px rgba(15,23,42,.04); height: 100%;
  }
  .kpi .label { font-size: .74rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: #64748B; }
  .kpi .value { font-size: 1.85rem; font-weight: 800; color: #0F172A; line-height: 1.15; margin-top: 6px; }
  .kpi .delta { font-size: .8rem; font-weight: 600; margin-top: 4px; }
  .kpi .delta.up { color: #10B981; }
  .kpi .delta.down { color: #EF4444; }
  .kpi .hint { font-size: .78rem; color: #94A3B8; margin-top: 4px; }

  .card {
    background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 20px 22px;
    box-shadow: 0 1px 2px rgba(15,23,42,.04); margin-bottom: 16px;
  }
  .card h3 { margin: 0 0 6px; font-size: 1.02rem; font-weight: 700; color: #0F172A; }
  .card p { color: #475569; font-size: .9rem; }

  .insight { border-radius: 14px; padding: 16px 18px; margin-bottom: 12px; border-left: 4px solid #94A3B8;
             background: #fff; box-shadow: 0 1px 2px rgba(15,23,42,.05); }
  .insight .tag { font-size: .68rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
  .insight .title { font-weight: 700; font-size: .98rem; margin: 4px 0 4px; color: #0F172A; }
  .insight .desc { font-size: .87rem; color: #475569; }
  .insight .rec { font-size: .84rem; color: #334155; margin-top: 8px; }
  .insight .rec b { color: #0F172A; }

  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: .72rem; font-weight: 700; }
  .badge.published { background: #DCFCE7; color: #166534; }
  .badge.draft { background: #E2E8F0; color: #334155; }
  .badge.closed { background: #FEE2E2; color: #991B1B; }

  .summary-box { background: #EEF2FF; border: 1px solid #C7D2FE; border-radius: 14px; padding: 16px 18px; }
  .summary-box .label { font-size: .7rem; letter-spacing: .07em; text-transform: uppercase; font-weight: 700; color: #4338CA; }
  .summary-box p { margin: 8px 0 0; color: #1E293B; font-size: .93rem; line-height: 1.55; }

  section[data-testid="stSidebar"] { background: #0F172A; }
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] span,
  section[data-testid="stSidebar"] .stMarkdown * { color: #E2E8F0 !important; }
  section[data-testid="stSidebar"] .stRadio label { font-size: .92rem; padding: 4px 0; }
  section[data-testid="stSidebar"] .stRadio label p { font-weight: 500; }
  section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
    background: #1E293B !important; border-color: #334155 !important;
  }
  section[data-testid="stSidebar"] div[data-baseweb="select"] input,
  section[data-testid="stSidebar"] div[data-baseweb="select"] svg { color: #E2E8F0 !important; fill: #94A3B8; }
  section[data-testid="stSidebar"] [data-baseweb="popover"] * { color: #0F172A !important; }
  section[data-testid="stSidebar"] hr { border-color: #1E293B; }

  .brand { display: flex; align-items: center; gap: 10px; padding: 4px 0 20px; }
  .brand .mark {
    width: 34px; height: 34px; border-radius: 10px; flex: none;
    background: linear-gradient(135deg, #4F46E5, #06B6D4);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: .95rem; color: #fff;
  }
  .brand .name { font-size: 1.2rem; font-weight: 800; letter-spacing: -.02em; line-height: 1.1; }
  .brand .tag { font-size: .72rem; opacity: .6; letter-spacing: .04em; text-transform: uppercase; }

  .stButton > button {
    border-radius: 10px; font-weight: 600; border: 1px solid #E2E8F0; transition: all .15s ease;
  }
  .stButton > button:hover { border-color: #4F46E5; color: #4F46E5; }
  .stButton > button[kind="primary"] {
    background: linear-gradient(120deg, #4F46E5, #6366F1); border: none; color: #fff;
  }
  div[data-testid="stMetricValue"] { font-weight: 800; }
  .stTabs [data-baseweb="tab-list"] { gap: 6px; }
  .stTabs [data-baseweb="tab"] { border-radius: 10px; padding: 6px 14px; }
  #MainMenu, footer { visibility: hidden; }
</style>
"""


def inject_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
