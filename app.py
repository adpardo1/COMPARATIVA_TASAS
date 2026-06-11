import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# ==========================================
# 1. CONFIGURACIÓN DEL TABLERO
# ==========================================
st.set_page_config(page_title="Tablero ALM Integral", page_icon="🏦", layout="wide")
st.title("🏦 Modelo Integral de Pricing y Brechas")
st.markdown("Comparativa histórica de colocación combinada con análisis de brechas legales y competitivas.")

# ==========================================
# 2. CARGA DE DATOS
# ==========================================
@st.cache_data
def cargar_tasas_historicas():
    df = pd.read_csv("Data_Dashboard_S1_2020_2026.csv", sep=";", dtype=str)

    df["monto_total"] = df["monto_total"].str.replace(",", ".", regex=False).astype(float)
    df["tasa_activa_efectiva"] = df["tasa_activa_efectiva"].str.replace(",", ".", regex=False).astype(float)

    df["tasa_nominal"] = (
        df["tasa_nominal"].str.replace(",", ".", regex=False).astype(float)
        if "tasa_nominal" in df.columns
        else df["tasa_activa_efectiva"]
    )

    df["numero_operaciones"] = pd.to_numeric(df["numero_operaciones"], errors="coerce").fillna(0).astype(int)

    df["monto_x_tasa_efectiva"] = df["monto_total"] * df["tasa_activa_efectiva"]
    df["monto_x_tasa_nominal"] = df["monto_total"] * df["tasa_nominal"]

    df["fecha_dt"] = pd.to_datetime(df["fecha"].astype(str) + "-01", errors="coerce")

    df["segmento_agrupado"] = df["segmento_credito"].astype(str).apply(
        lambda x: (
            "Consumo" if "CONSUMO" in x.upper()
            else "Microcrédito" if "MICRO" in x.upper()
            else "Inmobiliario" if any(p in x.upper() for p in ["VIVIENDA", "INMOBILIARIO"])
            else "Comercial"
        )
    )

    return df


@st.cache_data
def cargar_techos_bce():
    try:
        df_bce = pd.read_csv("tasas_bce.csv")  # 🔥 renombrado limpio
        last = df_bce.iloc[-1]

        return {
            "Consumo": float(last["Consumo"]),
            "Microcrédito": float(last["Microcrédito Minorista"]),
            "Inmobiliario": float(last.get("Inmobiliario", 10.58))
        }
    except:
        return {"Consumo": 16.77, "Microcrédito": 28.23, "Inmobiliario": 10.58}


@st.cache_data
def cargar_boletines_financieros():
    try:
        df_seps = pd.read_excel(
            "boletin_financiero.xlsm",
            sheet_name="2. ESTADO FINANCIERO",
            header=15
        )
        df_seps.columns = df_seps.columns.astype(str).str.strip()
        return df_seps
    except:
        return pd.DataFrame()


df_crudo = cargar_tasas_historicas()
techos_bce = cargar_techos_bce()
df_seps = cargar_boletines_financieros()

# ==========================================
# 3. FILTRO GEOGRÁFICO
# ==========================================
keywords_pastaza = [
    "PICHINCHA", "GUAYAQUIL", "INTERNACIONAL", "BANECUADOR",
    "PASTAZA", "JEP", "MUSHUC RUNA"
]

st.sidebar.header("⚙️ Parámetros")

alcance = st.sidebar.radio(
    "📍 Alcance",
    ["Nacional", "Plaza Local (Pastaza)"]
)

if alcance == "Plaza Local (Pastaza)":
    df = df_crudo[df_crudo["razon_social"].astype(str).apply(
        lambda x: any(k in x.upper() for k in keywords_pastaza)
    )]
else:
    df = df_crudo.copy()

entidades = sorted(df["razon_social"].unique())

entidad_principal = st.sidebar.selectbox("Entidad base", entidades)

competidores = st.sidebar.multiselect(
    "Competidores",
    [e for e in entidades if e != entidad_principal],
    default=[e for e in entidades if e != entidad_principal][:5]
)

segmentos = st.sidebar.multiselect(
    "Segmentos",
    sorted(df["segmento_agrupado"].unique()),
    default=["Consumo", "Microcrédito", "Inmobiliario"]
)

fecha_min = df["fecha_dt"].min()
fecha_max = df["fecha_dt"].max()

rango = st.sidebar.slider(
    "Rango",
    min_value=fecha_min.to_pydatetime(),
    max_value=fecha_max.to_pydatetime(),
    value=(fecha_min.to_pydatetime(), fecha_max.to_pydatetime())
)

tipo_tasa = st.sidebar.radio("Tasa", ["Tasa Efectiva", "Tasa Nominal"])

# ==========================================
# 4. FILTRADO
# ==========================================
mask = (
    df["razon_social"].isin([entidad_principal] + competidores)
    & df["segmento_agrupado"].isin(segmentos)
    & (df["fecha_dt"] >= pd.to_datetime(rango[0]))
    & (df["fecha_dt"] <= pd.to_datetime(rango[1]))
)

df_f = df[mask]

# ==========================================
# 5. KPIs
# ==========================================
st.header("📉 Evolución")

if not df_f.empty:
    vol = df_f["monto_total"].sum()
    ops = df_f["numero_operaciones"].sum()

    col1, col2 = st.columns(2)
    col1.metric("Volumen", f"${vol:,.0f}")
    col2.metric("Operaciones", f"{ops:,.0f}")

# ==========================================
# 6. GRÁFICO
# ==========================================
if not df_f.empty:
    tendencia = df_f.groupby(["fecha_dt", "razon_social"]).agg(
        monto=("monto_total", "sum"),
        eff=("monto_x_tasa_efectiva", "sum"),
        nom=("monto_x_tasa_nominal", "sum")
    ).reset_index()

    tendencia["tasa"] = (
        tendencia["eff"] / tendencia["monto"]
        if tipo_tasa == "Tasa Efectiva"
        else tendencia["nom"] / tendencia["monto"]
    )

    fig = px.line(
        tendencia,
        x="fecha_dt",
        y="tasa",
        color="razon_social",
        markers=True
    )

    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 7. MATRIZ
# ==========================================
st.header("🎯 Matriz")

df_final = pd.DataFrame({
    "Segmento": segmentos,
    "Techo BCE": [techos_bce.get(s, 0) for s in segmentos]
})

st.dataframe(df_final)
