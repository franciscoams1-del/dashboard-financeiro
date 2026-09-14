"""
Dashboard avançado de monitoramento de mercado.

Execute com:
    streamlit run app.py

O aplicativo usa dados do Yahoo Finance. As cotações intraday podem ter atraso
e alguns ativos podem não disponibilizar demonstrações financeiras.
"""

from __future__ import annotations

import hashlib
import html
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from pandas_datareader import data as fred_data
from streamlit_autorefresh import st_autorefresh


# ---------------------------------------------------------------------------
# Configuração e universo inicial
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Market Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


DEFAULT_ASSETS: dict[str, list[dict[str, str]]] = {
    "Macro, Juros e Inflação": [
        {"ticker": "^VIX", "name": "Índice VIX"},
        {"ticker": "DX-Y.NYB", "name": "Dólar Index DXY"},
        {"ticker": "^IRX", "name": "Treasury Yield 3M"},
        {"ticker": "DGS1", "name": "Treasury Yield 1Y — FRED"},
        {"ticker": "^FVX", "name": "Treasury Yield 5Y"},
        {"ticker": "^TNX", "name": "Treasury Yield 10Y"},
        {"ticker": "^TYX", "name": "Treasury Yield 30Y"},
        {"ticker": "T10YIE", "name": "Inflação Implícita 10Y — FRED"},
    ],
    "ETFs Globais e Fatores": [
        {"ticker": "SPY", "name": "S&P 500 ETF"},
        {"ticker": "QQQ", "name": "Nasdaq 100 ETF"},
        {"ticker": "SPHQ", "name": "S&P 500 Quality ETF"},
        {"ticker": "SPQA", "name": "SPDR MSCI Global Quality Mix"},
        {"ticker": "SMOT", "name": "VanEck Morningstar SMID Moat"},
    ],
    "Cripto & Derivados": [
        {"ticker": "BTC-USD", "name": "Bitcoin"},
        {"ticker": "SOL-USD", "name": "Solana"},
        {"ticker": "BITO", "name": "Bitcoin Strategy ETF"},
        {"ticker": "MSTR", "name": "MicroStrategy — proxy BTC"},
    ],
    "Commodities": [
        {"ticker": "GLD", "name": "Ouro — ETF"},
        {"ticker": "SI=F", "name": "Prata — Futuros"},
        {"ticker": "HG=F", "name": "Cobre — Futuros"},
        {"ticker": "ZS=F", "name": "Soja — Futuros"},
        {"ticker": "ZC=F", "name": "Milho — Futuros"},
        {"ticker": "SLX", "name": "Aço/Ferro — ETF"},
    ],
    "Tech, Semi & IA": [
        {"ticker": "NVDA", "name": "NVIDIA"},
        {"ticker": "ANET", "name": "Arista Networks"},
        {"ticker": "NBIS", "name": "Nebius"},
        {"ticker": "OKLO", "name": "Oklo"},
        {"ticker": "000660.KS", "name": "SK Hynix"},
        {"ticker": "APP", "name": "AppLovin"},
    ],
    "Cyber & Cloud": [
        {"ticker": "NET", "name": "Cloudflare"},
        {"ticker": "CRWD", "name": "CrowdStrike"},
        {"ticker": "PANW", "name": "Palo Alto Networks"},
        {"ticker": "ZS", "name": "Zscaler"},
        {"ticker": "GTLB", "name": "GitLab"},
    ],
    "Consumo, Saúde & Diversos": [
        {"ticker": "DLO", "name": "dLocal"},
        {"ticker": "PDD", "name": "PDD Holdings"},
        {"ticker": "EXEL", "name": "Exelixis"},
        {"ticker": "RMV.L", "name": "Rightmove"},
        {"ticker": "GAW.L", "name": "Games Workshop"},
        {"ticker": "DECK", "name": "Deckers Brands"},
        {"ticker": "KPG.AX", "name": "Kelly Partners"},
        {"ticker": "MEDP", "name": "Medpace"},
        {"ticker": "WSO", "name": "Watsco"},
    ],
}


FRED_SERIES: dict[str, str] = {
    "DGS1": "DGS1",
    "T10YIE": "T10YIE",
}


if "custom_tickers" not in st.session_state:
    st.session_state.custom_tickers = []


# ---------------------------------------------------------------------------
# CSS dos cards
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    .market-card {
        min-height: 218px;
        padding: 18px 18px 14px 18px;
        border-radius: 16px;
        color: #ffffff;
        margin-bottom: 8px;
        border: 1px solid rgba(255,255,255,.10);
        box-shadow: 0 8px 24px rgba(0,0,0,.18);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .market-card-positive {
        background: linear-gradient(145deg, #155b3a 0%, #0b3426 100%);
    }

    .market-card-negative {
        background: linear-gradient(145deg, #702e36 0%, #3f1b23 100%);
    }

    .market-card-neutral {
        background: linear-gradient(145deg, #34445b 0%, #202b3d 100%);
    }

    .market-card .asset-name {
        color: rgba(255,255,255,.82);
        font-size: .88rem;
        font-weight: 600;
        min-height: 22px;
    }

    .market-card .ticker {
        color: rgba(255,255,255,.60);
        font-size: .75rem;
        letter-spacing: .06em;
        text-transform: uppercase;
    }

    .market-card .price {
        font-size: 1.75rem;
        font-weight: 750;
        line-height: 1.15;
        margin-top: 14px;
    }

    .market-card .change {
        font-size: 1rem;
        font-weight: 700;
        margin-top: 4px;
    }

    .market-card .moving-averages {
        border-top: 1px solid rgba(255,255,255,.16);
        color: rgba(255,255,255,.75);
        font-size: .72rem;
        line-height: 1.55;
        margin-top: 15px;
        padding-top: 10px;
    }

    .market-card .year-ago {
        color: rgba(255,255,255,.72);
        font-size: .72rem;
        margin-top: 7px;
    }

    div[data-testid="stHorizontalBlock"] {
        gap: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Utilitários gerais
# ---------------------------------------------------------------------------

def normalize_ticker(ticker: str) -> str:
    """Normaliza um ticker informado na sidebar."""
    return ticker.strip().upper()


def ticker_key(ticker: str) -> str:
    """Cria uma chave estável e segura para widgets do Streamlit."""
    return hashlib.md5(ticker.encode("utf-8")).hexdigest()[:10]


def safe_float(value: Any) -> float | None:
    """Converte números vindos de yfinance sem propagar exceções."""
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def format_price(value: float | None) -> str:
    """Formata preço sem assumir que todos os ativos estão em USD."""
    if value is None:
        return "N/A"
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return f"{value:,.4f}"


def format_percent(value: float | None) -> str:
    """Formata uma taxa percentual."""
    return "N/A" if value is None else f"{value:+.2f}%"


def format_compact_number(value: float | None) -> str:
    """Formata valores financeiros grandes de forma compacta."""
    if value is None:
        return "N/A"

    absolute = abs(value)
    sign = "-" if value < 0 else ""

    if absolute >= 1_000_000_000_000:
        return f"{sign}{absolute / 1_000_000_000_000:.2f}T"
    if absolute >= 1_000_000_000:
        return f"{sign}{absolute / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}{absolute / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{sign}{absolute / 1_000:.2f}K"
    return f"{value:,.2f}"


def normalize_close_history(history: pd.DataFrame) -> pd.DataFrame:
    """Extrai e normaliza a série Close, inclusive em respostas MultiIndex."""
    if history.empty:
        return pd.DataFrame(columns=["Data", "Preço"])

    close_column: Any = "Close"

    if isinstance(history.columns, pd.MultiIndex):
        candidates = [
            column
            for column in history.columns
            if str(column[0]).lower() == "close"
        ]
        if not candidates:
            return pd.DataFrame(columns=["Data", "Preço"])
        close_column = candidates[0]

    close = pd.to_numeric(history[close_column], errors="coerce").dropna()

    if close.empty:
        return pd.DataFrame(columns=["Data", "Preço"])

    dates = pd.to_datetime(close.index, errors="coerce")
    if getattr(dates, "tz", None) is not None:
        dates = dates.tz_localize(None)

    return pd.DataFrame(
        {
            "Data": dates,
            "Preço": close.to_numpy(),
        }
    ).dropna()


def statement_series(
    statement: pd.DataFrame | None,
    labels: list[str],
) -> pd.Series | None:
    """
    Localiza uma linha de demonstração financeira por vários nomes possíveis.
    O Yahoo Finance altera alguns nomes entre ativos e períodos.
    """
    if statement is None or statement.empty:
        return None

    normalized_labels = {
        label.lower().replace(" ", "").replace("_", "")
        for label in labels
    }

    for index_label in statement.index:
        normalized_index = (
            str(index_label).lower().replace(" ", "").replace("_", "")
        )
        if normalized_index in normalized_labels:
            series = pd.to_numeric(statement.loc[index_label], errors="coerce")
            return series.dropna()

    return None


def latest_statement_value(
    statement: pd.DataFrame | None,
    labels: list[str],
    position: int = 0,
) -> float | None:
    """Retorna o valor mais recente, ou o valor na posição solicitada."""
    series = statement_series(statement, labels)
    if series is None or len(series) <= position:
        return None
    return safe_float(series.iloc[position])


def sum_statement_values(
    statement: pd.DataFrame | None,
    labels: list[str],
    start: int = 0,
    count: int = 4,
) -> float | None:
    """Soma períodos de uma demonstração para aproximar um LTM."""
    series = statement_series(statement, labels)
    if series is None or len(series) <= start:
        return None

    values = pd.to_numeric(
        series.iloc[start : start + count],
        errors="coerce",
    ).dropna()

    if values.empty:
        return None

    return safe_float(values.sum())


# ---------------------------------------------------------------------------
# Dados de mercado
# ---------------------------------------------------------------------------

def build_market_snapshot(
    ticker: str,
    data: pd.DataFrame,
) -> dict[str, Any]:
    """Calcula preço, variação diária, médias e distância das médias."""
    if data.empty:
        return {
            "ticker": ticker,
            "error": f"O Yahoo Finance/FRED não retornou histórico para {ticker}.",
        }

    data = data.copy()
    data["MM7"] = data["Preço"].rolling(7, min_periods=1).mean()
    data["MM30"] = data["Preço"].rolling(30, min_periods=1).mean()
    data["MM180"] = data["Preço"].rolling(180, min_periods=1).mean()

    latest_price = safe_float(data["Preço"].iloc[-1])
    previous_price = (
        safe_float(data["Preço"].iloc[-2])
        if len(data) >= 2
        else None
    )

    daily_change = None
    if latest_price is not None and previous_price not in (None, 0):
        daily_change = ((latest_price / previous_price) - 1) * 100

    moving_average_distances: dict[str, float | None] = {}
    for average_name in ("MM7", "MM30", "MM180"):
        average = safe_float(data[average_name].iloc[-1])
        moving_average_distances[average_name] = (
            ((latest_price / average) - 1) * 100
            if latest_price is not None and average not in (None, 0)
            else None
        )

    return {
        "ticker": ticker,
        "history": data,
        "price": latest_price,
        "daily_change": daily_change,
        "mm7": safe_float(data["MM7"].iloc[-1]),
        "mm30": safe_float(data["MM30"].iloc[-1]),
        "mm180": safe_float(data["MM180"].iloc[-1]),
        "distance_mm7": moving_average_distances["MM7"],
        "distance_mm30": moving_average_distances["MM30"],
        "distance_mm180": moving_average_distances["MM180"],
        "one_year_ago": safe_float(data["Preço"].iloc[0]),
        "error": None,
    }


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fred_market_data(ticker: str) -> dict[str, Any]:
    """Busca séries macroeconômicas diretamente no banco de dados FRED."""
    try:
        series_id = FRED_SERIES[ticker]
        start = datetime.utcnow() - timedelta(days=420)
        end = datetime.utcnow()
        history = fred_data.DataReader(series_id, "fred", start, end)

        if history.empty or series_id not in history.columns:
            return {
                "ticker": ticker,
                "error": f"O FRED não retornou dados para {ticker}.",
            }

        values = pd.to_numeric(history[series_id], errors="coerce").dropna()
        dates = pd.to_datetime(values.index, errors="coerce")

        data = pd.DataFrame(
            {
                "Data": dates,
                "Preço": values.to_numpy(),
            }
        ).dropna()

        return build_market_snapshot(ticker, data)
    except Exception:
        return {
            "ticker": ticker,
            "error": (
                f"Não foi possível carregar {ticker} via FRED. "
                "O indicador pode estar temporariamente indisponível."
            ),
        }


@st.cache_data(ttl=300, show_spinner=False)
def fetch_market_data(ticker: str) -> dict[str, Any]:
    """Baixa um ano de histórico e calcula preço, variação e médias móveis."""
    if ticker in FRED_SERIES:
        return fetch_fred_market_data(ticker)

    try:
        history = yf.Ticker(ticker).history(
            period="1y",
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
        data = normalize_close_history(history)

        if data.empty:
            return {
                "ticker": ticker,
                "error": (
                    f"O Yahoo Finance não retornou histórico para {ticker}."
                ),
            }

        return build_market_snapshot(ticker, data)
    except Exception:
        return {
            "ticker": ticker,
            "error": (
                f"Não foi possível carregar {ticker}. "
                "Verifique se o ticker é válido no Yahoo Finance."
            ),
        }


@st.cache_data(ttl=120, show_spinner=False)
def fetch_intraday_data(ticker: str, last_five_days: bool) -> pd.DataFrame:
    """Busca dados intraday para o gráfico do modal."""
    try:
        if last_five_days:
            period, interval = "5d", "15m"
        else:
            period, interval = "1d", "5m"

        history = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            auto_adjust=False,
            actions=False,
        )

        if history.empty:
            return pd.DataFrame(columns=["Data", "Preço"])

        return normalize_close_history(history)
    except Exception:
        return pd.DataFrame(columns=["Data", "Preço"])


# ---------------------------------------------------------------------------
# Fundamentos e métricas LTM
# ---------------------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def fetch_fundamentals(ticker: str, current_price: float | None) -> dict[str, Any]:
    """
    Extrai métricas fundamentalistas com fallback e tratamento de exceções.

    Para ETFs, índices, futuros e criptoativos, as métricas corporativas são
    explicitamente marcadas como não aplicáveis.
    """
    empty = {
        "enterprise_value": None,
        "market_cap": None,
        "net_debt": None,
        "net_debt_ebitda": None,
        "net_income_ltm": None,
        "pe_ltm": None,
        "forward_pe": None,
        "pe_realtime": None,
        "roic": None,
        "roiic": None,
        "not_applicable": False,
        "note": None,
    }

    try:
        security = yf.Ticker(ticker)

        try:
            info = security.info or {}
        except Exception:
            info = {}

        quote_type = str(info.get("quoteType", "")).upper()
        known_non_corporate = (
            ticker.startswith("^")
            or ticker.endswith("-USD")
            or ticker.endswith("=F")
            or ticker in FRED_SERIES
            or ticker in {
                "SPY",
                "QQQ",
                "SPHQ",
                "SPQA",
                "SMOT",
                "BITO",
                "GLD",
                "SLX",
                "DX-Y.NYB",
            }
        )

        if quote_type in {
            "ETF",
            "INDEX",
            "CRYPTOCURRENCY",
            "FUTURE",
            "CURRENCY",
        } or known_non_corporate:
            empty["not_applicable"] = True
            empty["note"] = (
                "Não aplicável: o ativo não possui demonstrações financeiras "
                "corporativas comparáveis."
            )
            return empty

        try:
            financials = security.financials
        except Exception:
            financials = pd.DataFrame()

        try:
            quarterly_financials = security.quarterly_financials
        except Exception:
            quarterly_financials = pd.DataFrame()

        try:
            cashflow = security.cashflow
        except Exception:
            cashflow = pd.DataFrame()

        try:
            quarterly_cashflow = security.quarterly_cashflow
        except Exception:
            quarterly_cashflow = pd.DataFrame()

        try:
            balance_sheet = security.balance_sheet
        except Exception:
            balance_sheet = pd.DataFrame()

        try:
            quarterly_balance_sheet = security.quarterly_balance_sheet
        except Exception:
            quarterly_balance_sheet = pd.DataFrame()

        enterprise_value = safe_float(info.get("enterpriseValue"))
        market_cap = safe_float(info.get("marketCap"))

        total_debt = (
            latest_statement_value(
                quarterly_balance_sheet,
                [
                    "Total Debt",
                    "TotalDebt",
                    "Long Term Debt And Capital Lease Obligation",
                ],
            )
            or latest_statement_value(
                balance_sheet,
                [
                    "Total Debt",
                    "TotalDebt",
                    "Long Term Debt And Capital Lease Obligation",
                ],
            )
            or safe_float(info.get("totalDebt"))
        )

        cash = (
            latest_statement_value(
                quarterly_balance_sheet,
                [
                    "Cash Cash Equivalents And Short Term Investments",
                    "Cash And Cash Equivalents",
                    "CashAndCashEquivalents",
                ],
            )
            or latest_statement_value(
                balance_sheet,
                [
                    "Cash Cash Equivalents And Short Term Investments",
                    "Cash And Cash Equivalents",
                    "CashAndCashEquivalents",
                ],
            )
            or safe_float(info.get("totalCash"))
        )

        net_debt = (
            total_debt - cash
            if total_debt is not None and cash is not None
            else None
        )

        ebitda = (
            safe_float(info.get("ebitda"))
            or sum_statement_values(
                quarterly_financials,
                ["EBITDA", "Normalized EBITDA"],
            )
            or latest_statement_value(
                financials,
                ["EBITDA", "Normalized EBITDA"],
            )
        )

        net_income_ltm = (
            safe_float(info.get("netIncomeToCommon"))
            or sum_statement_values(
                quarterly_financials,
                ["Net Income", "NetIncome", "Net Income Common Stockholders"],
            )
            or latest_statement_value(
                financials,
                ["Net Income", "NetIncome", "Net Income Common Stockholders"],
            )
        )

        pe_ltm = safe_float(info.get("trailingPE"))
        forward_pe = safe_float(info.get("forwardPE"))
        eps_ltm = safe_float(info.get("trailingEps"))
        pe_realtime = (
            current_price / eps_ltm
            if current_price is not None and eps_ltm not in (None, 0)
            else None
        )

        operating_income_ltm = (
            sum_statement_values(
                quarterly_financials,
                ["Operating Income", "OperatingIncome"],
            )
            or latest_statement_value(
                financials,
                ["Operating Income", "OperatingIncome"],
            )
        )

        # Alguns emissores não publicam EBITDA diretamente. Nessa situação,
        # aproximamos EBITDA como EBIT + depreciação/amortização usando
        # financials/cashflow e seus equivalentes trimestrais.
        if ebitda is None:
            depreciation_ltm = (
                sum_statement_values(
                    quarterly_cashflow,
                    [
                        "Depreciation And Amortization",
                        "Depreciation",
                        "Depreciation And Amortization In Cash Flow",
                    ],
                )
                or latest_statement_value(
                    cashflow,
                    [
                        "Depreciation And Amortization",
                        "Depreciation",
                        "Depreciation And Amortization In Cash Flow",
                    ],
                )
            )

            if operating_income_ltm is not None and depreciation_ltm is not None:
                ebitda = operating_income_ltm + depreciation_ltm

        net_debt_ebitda = (
            net_debt / ebitda
            if net_debt is not None and ebitda not in (None, 0)
            else safe_float(info.get("debtToEbitda"))
        )

        pretax_income_ltm = (
            sum_statement_values(
                quarterly_financials,
                ["Pretax Income", "PretaxIncome"],
            )
            or latest_statement_value(
                financials,
                ["Pretax Income", "PretaxIncome"],
            )
        )

        tax_provision_ltm = (
            sum_statement_values(
                quarterly_financials,
                ["Tax Provision", "TaxProvision"],
            )
            or latest_statement_value(
                financials,
                ["Tax Provision", "TaxProvision"],
            )
        )

        tax_rate = safe_float(info.get("taxRate"))
        if tax_rate is None and pretax_income_ltm not in (None, 0):
            if tax_provision_ltm is not None:
                tax_rate = tax_provision_ltm / pretax_income_ltm

        if tax_rate is None or tax_rate < 0 or tax_rate > 1:
            tax_rate = 0.21

        nopat = (
            operating_income_ltm * (1 - tax_rate)
            if operating_income_ltm is not None
            else None
        )

        equity = (
            latest_statement_value(
                quarterly_balance_sheet,
                [
                    "Stockholders Equity",
                    "StockholdersEquity",
                    "Total Equity Gross Minority Interest",
                    "Total Equity",
                ],
            )
            or latest_statement_value(
                balance_sheet,
                [
                    "Stockholders Equity",
                    "StockholdersEquity",
                    "Total Equity Gross Minority Interest",
                    "Total Equity",
                ],
            )
        )

        invested_capital = (
            equity + total_debt - cash
            if equity is not None and total_debt is not None and cash is not None
            else None
        )

        roic = (
            nopat / invested_capital
            if nopat is not None and invested_capital not in (None, 0)
            else None
        )

        # ROIIC aproximado: variação do NOPAT LTM dividida pela variação
        # do capital investido entre o período atual e aproximadamente um ano
        # antes. Quando não existem oito trimestres, o resultado fica N/A.
        prior_operating_income = sum_statement_values(
            quarterly_financials,
            ["Operating Income", "OperatingIncome"],
            start=4,
            count=4,
        )
        prior_equity = latest_statement_value(
            quarterly_balance_sheet,
            [
                "Stockholders Equity",
                "StockholdersEquity",
                "Total Equity Gross Minority Interest",
                "Total Equity",
            ],
            position=4,
        )
        prior_debt = latest_statement_value(
            quarterly_balance_sheet,
            [
                "Total Debt",
                "TotalDebt",
                "Long Term Debt And Capital Lease Obligation",
            ],
            position=4,
        )
        prior_cash = latest_statement_value(
            quarterly_balance_sheet,
            [
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Cash Equivalents",
                "CashAndCashEquivalents",
            ],
            position=4,
        )

        prior_invested_capital = (
            prior_equity + prior_debt - prior_cash
            if (
                prior_equity is not None
                and prior_debt is not None
                and prior_cash is not None
            )
            else None
        )

        prior_nopat = (
            prior_operating_income * (1 - tax_rate)
            if prior_operating_income is not None
            else None
        )

        invested_capital_delta = (
            invested_capital - prior_invested_capital
            if invested_capital is not None and prior_invested_capital is not None
            else None
        )

        roiic = (
            (nopat - prior_nopat) / invested_capital_delta
            if (
                nopat is not None
                and prior_nopat is not None
                and invested_capital_delta not in (None, 0)
            )
            else None
        )

        return {
            **empty,
            "enterprise_value": enterprise_value,
            "market_cap": market_cap,
            "net_debt": net_debt,
            "net_debt_ebitda": net_debt_ebitda,
            "net_income_ltm": net_income_ltm,
            "pe_ltm": pe_ltm,
            "forward_pe": forward_pe,
            "pe_realtime": pe_realtime,
            "roic": roic,
            "roiic": roiic,
            "note": (
                "ROIC e ROIIC são aproximações calculadas a partir das "
                "demonstrações disponíveis no Yahoo Finance."
            ),
        }

    except Exception:
        return {
            **empty,
            "note": (
                "Fundamentos indisponíveis para este ativo. "
                "Os dados de mercado continuam sendo exibidos."
            ),
        }


# ---------------------------------------------------------------------------
# Componentes de interface
# ---------------------------------------------------------------------------

def card_class(daily_change: float | None) -> str:
    """Seleciona a cor do card com base na variação diária."""
    if daily_change is None:
        return "market-card-neutral"
    return "market-card-positive" if daily_change >= 0 else "market-card-negative"


def render_market_card(asset: dict[str, str], data: dict[str, Any]) -> bool:
    """Renderiza um card e retorna True quando o usuário abre os detalhes."""
    ticker = asset["ticker"]
    name = asset["name"]
    price = data.get("price")
    change = data.get("daily_change")

    if data.get("error"):
        st.markdown(
            f"""
            <div class="market-card market-card-neutral">
                <div class="asset-name">{html.escape(name)}</div>
                <div class="ticker">{html.escape(ticker)}</div>
                <div class="price">N/A</div>
                <div class="change">Dados indisponíveis</div>
                <div class="moving-averages">
                    O Yahoo Finance não retornou um histórico válido.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.warning(data["error"])
        return False

    card_html = f"""
        <div class="market-card {card_class(change)}">
            <div class="asset-name">{html.escape(name)}</div>
            <div class="ticker">{html.escape(ticker)}</div>
            <div class="price">{format_price(price)}</div>
            <div class="change">{format_percent(change)}</div>
            <div class="moving-averages">
                Vs MM7: {format_percent(data.get("distance_mm7"))}<br>
                Vs MM30: {format_percent(data.get("distance_mm30"))}<br>
                Vs MM180: {format_percent(data.get("distance_mm180"))}
            </div>
            <div class="year-ago">
                Preço há 1 ano: {format_price(data.get("one_year_ago"))}
            </div>
        </div>
    """

    st.markdown(card_html, unsafe_allow_html=True)

    return st.button(
        "Ver Detalhes",
        key=f"details_{ticker_key(ticker)}",
        use_container_width=True,
    )


def render_intraday_chart(
    ticker: str,
    history: pd.DataFrame,
    last_five_days: bool,
) -> None:
    """Renderiza o gráfico intraday com eixo Y ajustado ao intervalo observado."""
    if history.empty:
        st.warning(
            f"Não há dados intraday disponíveis para {ticker} "
            "neste momento."
        )
        return

    minimum = float(history["Preço"].min())
    maximum = float(history["Preço"].max())
    observed_range = maximum - minimum
    padding = observed_range * 0.12 if observed_range else max(abs(minimum) * 0.002, 0.01)

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=history["Data"],
            y=history["Preço"],
            mode="lines",
            line=dict(color="#55d68a", width=2),
            name=ticker,
            hovertemplate=(
                "Data: %{x|%d/%m %H:%M}<br>"
                "Preço: %{y:,.4f}<extra></extra>"
            ),
        )
    )

    figure.update_layout(
        template="plotly_dark",
        height=410,
        margin=dict(l=15, r=15, t=25, b=15),
        showlegend=False,
        hovermode="x unified",
        xaxis_title="Horário",
        yaxis_title="Preço",
        yaxis=dict(range=[minimum - padding, maximum + padding]),
    )

    st.plotly_chart(
        figure,
        use_container_width=True,
        config={"displaylogo": False, "responsive": True},
    )


def render_fundamental_metrics(
    ticker: str,
    current_price: float | None,
) -> None:
    """Renderiza as métricas fundamentalistas dentro do modal."""
    metrics = fetch_fundamentals(ticker, current_price)

    if metrics.get("not_applicable"):
        st.info(
            metrics.get("note")
            or "Métricas fundamentalistas não aplicáveis a este ativo."
        )
        return

    values = [
        ("Enterprise Value LTM", format_compact_number(metrics["enterprise_value"])),
        ("Equity Value / Market Cap", format_compact_number(metrics["market_cap"])),
        ("Dívida Líquida LTM", format_compact_number(metrics["net_debt"])),
        ("Dívida Líquida / EBITDA", format_compact_number(metrics["net_debt_ebitda"])),
        ("Lucro Líquido LTM", format_compact_number(metrics["net_income_ltm"])),
        ("P/E LTM", format_compact_number(metrics["pe_ltm"])),
        ("Fwd P/E", format_compact_number(metrics["forward_pe"])),
        ("ROIC LTM", format_percent(
            metrics["roic"] * 100 if metrics["roic"] is not None else None
        )),
        ("ROIIC LTM", format_percent(
            metrics["roiic"] * 100 if metrics["roiic"] is not None else None
        )),
    ]

    for row_start in range(0, len(values), 3):
        row = values[row_start : row_start + 3]
        columns = st.columns(len(row))
        for column, (label, value) in zip(columns, row):
            with column:
                st.metric(label, value)

    if metrics.get("note"):
        st.caption(metrics["note"])


@st.dialog("Detalhes do ativo")
def show_asset_details(
    asset: dict[str, str],
    market_data: dict[str, Any],
) -> None:
    """Modal com gráfico intraday e fundamentos."""
    ticker = asset["ticker"]
    name = asset["name"]
    current_price = market_data.get("price")

    st.subheader(f"{name} ({ticker})")
    st.caption(
        f"Preço atual: {format_price(current_price)} · "
        f"Variação do dia: {format_percent(market_data.get('daily_change'))}"
    )

    last_five_days = st.toggle(
        "Ver Últimos 5 Dias",
        value=False,
        key=f"range_{ticker_key(ticker)}",
    )

    intraday = fetch_intraday_data(ticker, last_five_days)
    render_intraday_chart(ticker, intraday, last_five_days)

    st.divider()
    st.subheader("Métricas fundamentalistas")
    render_fundamental_metrics(ticker, current_price)


def render_asset_grid(assets: list[dict[str, str]]) -> None:
    """Renderiza quatro cards por linha."""
    for start in range(0, len(assets), 4):
        row = assets[start : start + 4]
        columns = st.columns(len(row))

        for column, asset in zip(columns, row):
            with column:
                data = fetch_market_data(asset["ticker"])
                open_details = render_market_card(asset, data)
                if open_details and not data.get("error"):
                    show_asset_details(asset, data)


def render_category(category: str, assets: list[dict[str, str]]) -> None:
    """Renderiza uma categoria completa."""
    st.subheader(category)
    render_asset_grid(assets)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Configurações")

    st.subheader("Tickers padrão")
    for category, assets in DEFAULT_ASSETS.items():
        with st.expander(category, expanded=False):
            for asset in assets:
                st.write(f"**{asset['ticker']}** — {asset['name']}")

    st.divider()
    st.subheader("Adicionar tickers")

    ticker_input = st.text_input(
        "Tickers separados por vírgula",
        placeholder="Ex.: AAPL, MSFT, PETR4.SA",
    )

    if st.button("Adicionar ativos", use_container_width=True):
        candidates = [
            normalize_ticker(item)
            for item in ticker_input.split(",")
            if normalize_ticker(item)
        ]

        default_tickers = {
            asset["ticker"]
            for assets in DEFAULT_ASSETS.values()
            for asset in assets
        }

        for ticker in candidates:
            if (
                ticker not in default_tickers
                and ticker not in st.session_state.custom_tickers
            ):
                st.session_state.custom_tickers.append(ticker)

        if candidates:
            st.success("Ticker(s) adicionado(s).")
            st.rerun()

    if st.session_state.custom_tickers:
        st.caption("Meus tickers:")
        for ticker in st.session_state.custom_tickers:
            st.write(f"• {ticker}")

        if st.button("Limpar meus tickers", use_container_width=True):
            st.session_state.custom_tickers = []
            st.rerun()

    st.divider()
    auto_refresh = st.checkbox("Atualização automática", value=True)

    if auto_refresh:
        st_autorefresh(
            interval=60_000,
            limit=None,
            key="market_monitor_refresh",
        )

    if st.button("🔄 Atualizar agora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption(
        "Cotações fornecidas pelo Yahoo Finance. "
        "O atraso varia por ativo e bolsa."
    )


# ---------------------------------------------------------------------------
# Conteúdo principal
# ---------------------------------------------------------------------------

st.title("📈 Market Monitor")
st.caption(
    "Painel único para monitorar mercado, juros, inflação, commodities, "
    "cripto, tecnologia e análise fundamentalista."
)

st.warning(
    """
    **CoreWeave:** não possui ticker público disponível no Yahoo Finance.
    O ativo é representado por um alerta e a NVIDIA (NVDA) aparece como proxy
    do setor de GPUs, infraestrutura de IA e data centers.
    """
)

for category_name, category_assets in DEFAULT_ASSETS.items():
    render_category(category_name, category_assets)

    if category_name == "Macro, Juros e Inflação":
        st.caption(
            "DGS1 e T10YIE são buscados no FRED via pandas-datareader. "
            "Os demais indicadores usam o Yahoo Finance."
        )

    if category_name == "Commodities":
        st.caption(
            "Commodities são representadas por contratos futuros e ETFs "
            "disponíveis no Yahoo Finance."
        )

    st.divider()

st.subheader("Outros")
custom_assets = [
    {"ticker": ticker, "name": "Ativo personalizado"}
    for ticker in st.session_state.custom_tickers
]

if not custom_assets:
    st.info(
        "Adicione tickers pela barra lateral. Eles aparecerão automaticamente "
        "nesta seção quando não pertencerem às categorias padrão."
    )
else:
    render_asset_grid(custom_assets)

st.divider()
st.caption(
    "Os cálculos de ROIC e ROIIC são aproximações baseadas na disponibilidade "
    "das demonstrações financeiras no Yahoo Finance. Este dashboard não é "
    "recomendação de investimento."
)
