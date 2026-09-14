# app.py
"""
Dashboard de monitoramento de mercado com Streamlit, yfinance e Plotly.
Execução local:
    streamlit run app.py
Observações:
- Os dados do Yahoo Finance podem apresentar atraso, dependendo do ativo e da bolsa.
- O índice Fear & Greed e o GRP Index não possuem tickers nativos confiáveis no
  Yahoo Finance. O código contém placeholders e instruções para integração futura.
"""
from __future__ import annotations
from typing import Any
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Market Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
# ---------------------------------------------------------------------------
# Configuração dos ativos
# ---------------------------------------------------------------------------
DEFAULT_ASSETS: dict[str, list[dict[str, str]]] = {
    "Macro & Índices": [
        {"ticker": "SPY", "name": "S&P 500 ETF"},
        {"ticker": "^VIX", "name": "Índice VIX"},
        {"ticker": "DX-Y.NYB", "name": "Dólar Index DXY"},
    ],
    "Cripto & Commodities": [
        {"ticker": "BTC-USD", "name": "Bitcoin"},
        {"ticker": "GC=F", "name": "Ouro — Futuros"},
    ],
    "Tech, IA & Semicondutores": [
        {"ticker": "NBIS", "name": "Nebius"},
        {"ticker": "OKLO", "name": "Oklo"},
        {"ticker": "000660.KS", "name": "SK Hynix"},
        {"ticker": "NVDA", "name": "NVIDIA — proxy CoreWeave"},
    ],
    "Segurança Cloud (Cybersecurity)": [
        {"ticker": "NET", "name": "Cloudflare"},
        {"ticker": "CRWD", "name": "CrowdStrike"},
        {"ticker": "PANW", "name": "Palo Alto Networks"},
        {"ticker": "ZS", "name": "Zscaler"},
    ],
}
# ---------------------------------------------------------------------------
# Estado da sessão
# ---------------------------------------------------------------------------
if "custom_tickers" not in st.session_state:
    st.session_state.custom_tickers = []
# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------
def normalize_ticker(ticker: str) -> str:
    """Normaliza um ticker informado pelo usuário."""
    return ticker.strip().upper()
def format_price(value: float) -> str:
    """Formata preços sem assumir uma moeda específica."""
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return f"{value:,.4f}"
@st.cache_data(ttl=300, show_spinner=False)
def fetch_ticker_data(ticker: str) -> tuple[pd.DataFrame | None, float | None, float | None, str | None]:
    """
    Busca aproximadamente três meses de dados históricos.
    Retorna:
        histórico normalizado, preço mais recente, variação percentual e erro.
    """
    try:
        history = yf.Ticker(ticker).history(
            period="3mo",
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
        if history is None or history.empty:
            return None, None, None, (
                f"O Yahoo Finance não retornou dados para o ticker {ticker}."
            )
        close_column: Any = "Close"
        if isinstance(history.columns, pd.MultiIndex):
            close_candidates = [
                column
                for column in history.columns
                if str(column[0]).lower() == "close"
            ]
            if not close_candidates:
                return None, None, None, (
                    f"Não foi possível encontrar preços de fechamento para {ticker}."
                )
            close_column = close_candidates[0]
        close = pd.to_numeric(history[close_column], errors="coerce").dropna()
        if close.empty:
            return None, None, None, (
                f"Não existem preços válidos disponíveis para {ticker}."
            )
        dates = pd.to_datetime(close.index, errors="coerce")
        if getattr(dates, "tz", None) is not None:
            dates = dates.tz_localize(None)
        chart_data = pd.DataFrame(
            {
                "Data": dates,
                "Preço": close.to_numpy(),
            }
        ).dropna()
        if chart_data.empty:
            return None, None, None, (
                f"Não foi possível preparar o histórico de {ticker}."
            )
        latest_price = float(chart_data["Preço"].iloc[-1])
        if len(chart_data) >= 2:
            previous_price = float(chart_data["Preço"].iloc[-2])
            if previous_price != 0:
                change_percent = ((latest_price / previous_price) - 1) * 100
            else:
                change_percent = None
        else:
            change_percent = None
        return chart_data, latest_price, change_percent, None
    except Exception as error:
        return None, None, None, (
            f"Não foi possível carregar {ticker}. "
            f"O ativo pode estar indisponível ou o ticker pode ser inválido."
        )
def render_asset_metrics(
    assets: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Renderiza métricas dos ativos e retorna dados válidos e avisos."""
    valid_assets: list[dict[str, Any]] = []
    warnings: list[str] = []
    columns_per_row = 4
    for row_start in range(0, len(assets), columns_per_row):
        row_assets = assets[row_start : row_start + columns_per_row]
        columns = st.columns(len(row_assets))
        for column, asset in zip(columns, row_assets):
            ticker = asset["ticker"]
            name = asset["name"]
            chart_data, latest_price, change_percent, error = fetch_ticker_data(ticker)
            with column:
                if error or chart_data is None or latest_price is None:
                    warnings.append(error or f"Dados indisponíveis para {ticker}.")
                    st.metric(
                        label=f"{name} ({ticker})",
                        value="N/D",
                        delta="Sem dados",
                    )
                    continue
                formatted_change = (
                    f"{change_percent:+.2f}%"
                    if change_percent is not None
                    else "N/D"
                )
                st.metric(
                    label=f"{name} ({ticker})",
                    value=format_price(latest_price),
                    delta=formatted_change,
                )
                valid_assets.append(
                    {
                        "ticker": ticker,
                        "name": name,
                        "data": chart_data,
                    }
                )
    return valid_assets, warnings
def render_price_chart(
    assets: list[dict[str, Any]],
    title: str,
) -> None:
    """Cria um gráfico interativo com o histórico dos ativos válidos."""
    if not assets:
        st.info("Nenhum ativo válido disponível para exibição no gráfico.")
        return
    figure = go.Figure()
    for asset in assets:
        chart_data = asset["data"]
        figure.add_trace(
            go.Scatter(
                x=chart_data["Data"],
                y=chart_data["Preço"],
                mode="lines",
                name=f'{asset["name"]} ({asset["ticker"]})',
                hovertemplate=(
                    f'{asset["name"]}<br>'
                    "Data: %{x|%d/%m/%Y}<br>"
                    "Preço: %{y:,.4f}"
                    "<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        title=title,
        template="plotly_dark",
        height=500,
        hovermode="x unified",
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        xaxis_title="Data",
        yaxis_title="Preço de fechamento",
    )
    st.plotly_chart(
        figure,
        use_container_width=True,
        config={
            "displaylogo": False,
            "responsive": True,
        },
    )
def render_category(
    category_name: str,
    assets: list[dict[str, str]],
) -> None:
    """Renderiza métricas e gráfico de uma categoria."""
    st.subheader(category_name)
    valid_assets, warnings = render_asset_metrics(assets)
    if warnings:
        for warning in sorted(set(warnings)):
            st.warning(warning)
    st.divider()
    render_price_chart(
        valid_assets,
        title=f"Histórico de preços — {category_name} — últimos 3 meses",
    )
def create_custom_assets() -> list[dict[str, str]]:
    """Converte os tickers personalizados em ativos exibíveis."""
    return [
        {
            "ticker": ticker,
            "name": f"Ativo personalizado",
        }
        for ticker in st.session_state.custom_tickers
    ]
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
        "Informe tickers separados por vírgula",
        placeholder="Ex.: AAPL, MSFT, PETR4.SA",
        help=(
            "Use os símbolos aceitos pelo Yahoo Finance. "
            "Exemplos: AAPL, TSLA, PETR4.SA, ETH-USD."
        ),
    )
    if st.button("Adicionar ativos", use_container_width=True):
        new_tickers = [
            normalize_ticker(ticker)
            for ticker in ticker_input.split(",")
            if normalize_ticker(ticker)
        ]
        all_default_tickers = {
            asset["ticker"]
            for assets in DEFAULT_ASSETS.values()
            for asset in assets
        }
        for ticker in new_tickers:
            if ticker not in all_default_tickers and ticker not in st.session_state.custom_tickers:
                st.session_state.custom_tickers.append(ticker)
        if new_tickers:
            st.success("Ticker(s) adicionado(s).")
            st.rerun()
    if st.session_state.custom_tickers:
        st.caption("Ativos personalizados adicionados:")
        for ticker in st.session_state.custom_tickers:
            st.write(f"• {ticker}")
        if st.button("Limpar ativos personalizados", use_container_width=True):
            st.session_state.custom_tickers = []
            st.rerun()
    st.divider()
    auto_refresh = st.checkbox(
        "Atualização automática",
        value=True,
        help="Atualiza os dados periodicamente.",
    )
    if auto_refresh:
        st_autorefresh(
            interval=60_000,
            limit=None,
            key="market_dashboard_refresh",
        )
    if st.button("🔄 Atualizar agora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(
        "Dados fornecidos pelo Yahoo Finance. "
        "Cotações podem apresentar atraso."
    )
# ---------------------------------------------------------------------------
# Cabeçalho principal
# ---------------------------------------------------------------------------
st.title("📊 Market Monitor")
st.caption(
    "Monitoramento de índices, criptoativos, commodities, tecnologia e segurança cloud."
)
st.info(
    "Os dados são atualizados automaticamente a cada minuto quando essa opção "
    "está habilitada. A disponibilidade e o atraso das cotações dependem do Yahoo Finance."
)
# ---------------------------------------------------------------------------
# Abas
# ---------------------------------------------------------------------------
tab_macro, tab_crypto, tab_tech, tab_cyber, tab_custom = st.tabs(
    [
        "Macro & Índices",
        "Cripto & Commodities",
        "Tech, IA & Semicondutores",
        "Segurança Cloud",
        "Meus Tickers",
    ]
)
with tab_macro:
    render_category(
        "Macro & Índices",
        DEFAULT_ASSETS["Macro & Índices"],
    )
    st.divider()
    st.subheader("Indicadores complementares")
    fear_greed_column, grp_column = st.columns(2)
    with fear_greed_column:
        st.info(
            """
            **Fear & Greed Index**
            Placeholder visual.
            O índice pode ser integrado via:
            - API pública da Alternative.me;
            - endpoint de um provedor de dados financeiros;
            - web scraping autorizado de uma página pública.
            Exemplo de endpoint:
            `https://api.alternative.me/fng/`
            """
        )
    with grp_column:
        st.info(
            """
            **GRP Index**
            Placeholder visual.
            Como não existe um ticker nativo confiável no Yahoo Finance,
            a integração deve ser feita por:
            - API oficial do provedor do índice;
            - API de terceiros;
            - web scraping autorizado, respeitando robots.txt e os termos de uso.
            Recomenda-se implementar essa fonte em uma função separada,
            com cache e tratamento de indisponibilidade.
            """
        )
with tab_crypto:
    render_category(
        "Cripto & Commodities",
        DEFAULT_ASSETS["Cripto & Commodities"],
    )
    st.caption(
        "O ouro está representado pelo contrato futuro GC=F. "
        "Como alternativa, é possível usar o ETF GLD."
    )
with tab_tech:
    st.warning(
        """
        **CoreWeave:** a empresa não possui ticker público negociado em bolsa
        disponível no Yahoo Finance. Por isso, ela é representada aqui por um
        placeholder e a NVIDIA (NVDA) é exibida como proxy do setor de GPUs,
        infraestrutura de IA e data centers.
        """
    )
    st.info(
        "Quando a CoreWeave possuir um ticker público ou uma fonte de dados "
        "confiável, substitua o placeholder no dicionário DEFAULT_ASSETS."
    )
    render_category(
        "Tech, IA & Semicondutores",
        DEFAULT_ASSETS["Tech, IA & Semicondutores"],
    )
with tab_cyber:
    render_category(
        "Segurança Cloud (Cybersecurity)",
        DEFAULT_ASSETS["Segurança Cloud (Cybersecurity)"],
    )
with tab_custom:
    custom_assets = create_custom_assets()
    if not custom_assets:
        st.info(
            "Nenhum ticker personalizado foi adicionado. "
            "Use a barra lateral para adicionar ativos separados por vírgula."
        )
    else:
        render_category("Meus Tickers", custom_assets)
# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "Dashboard educacional. Não constitui recomendação de investimento. "
    "Valide os dados diretamente com fontes oficiais antes de tomar decisões financeiras."
)
# requirements.txt
streamlit>=1.35.0
streamlit-autorefresh>=1.0.1
yfinance>=0.2.40
plotly>=5.20.0
pandas>=2.0.0
