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
# 2. MOTOR DE DATOS (ETL EN MEMORIA)
# ==========================================
@st.cache_data
def cargar_tasas_historicas():
    df = pd.read_csv('Data_Dashboard_S1_2020_2026.csv', sep=';', dtype=str)
    
    df['monto_total'] = df['monto_total'].str.replace(',', '.', regex=False).astype(float)
    df['tasa_activa_efectiva'] = df['tasa_activa_efectiva'].str.replace(',', '.', regex=False).astype(float)
    if 'tasa_nominal' in df.columns:
        df['tasa_nominal'] = df['tasa_nominal'].str.replace(',', '.', regex=False).astype(float)
    else:
        df['tasa_nominal'] = df['tasa_activa_efectiva'] # Respaldo si no existe la columna
        
    df['numero_operaciones'] = pd.to_numeric(df['numero_operaciones'], errors='coerce').fillna(0).astype(int)
    
    df['monto_x_tasa_efectiva'] = df['monto_total'] * df['tasa_activa_efectiva']
    df['monto_x_tasa_nominal'] = df['monto_total'] * df['tasa_nominal']
    
    df['fecha_dt'] = pd.to_datetime(df['fecha'] + '-01')
    
    df['segmento_agrupado'] = df['segmento_credito'].apply(
        lambda x: 'Consumo' if 'CONSUMO' in str(x).upper() 
        else ('Microcrédito' if 'MICRO' in str(x).upper() 
        else ('Inmobiliario' if any(palabra in str(x).upper() for palabra in ['VIVIENDA', 'INMOBILIARIO']) 
        else 'Comercial'))
    )
    return df

@st.cache_data
def cargar_techos_bce():
    try:
        df_bce = pd.read_csv('Tasas_Activas_Maximas_BCE_2023_2026.xlsx - 📊 Tasas Máximas.csv')
        df_bce_actual = df_bce.iloc[-1] 
        return {
            'Consumo': float(df_bce_actual['Consumo']),
            'Microcrédito': float(df_bce_actual['Microcrédito Minorista']),
            'Inmobiliario': float(df_bce_actual['Inmobiliario'] if 'Inmobiliario' in df_bce.columns else 10.58)
        }
    except:
        return {'Consumo': 16.77, 'Microcrédito': 28.23, 'Inmobiliario': 10.58}

@st.cache_data
def cargar_boletines_financieros():
    # Se unifica la lectura de SEPS para saldos. (Los bancos se pueden integrar aquí en el futuro)
    try:
        df_seps = pd.read_excel('Boletin Financiero Segmento 1_abr_2026.xlsm', sheet_name='2. ESTADO FINANCIERO', header=15) 
        df_seps.columns = df_seps.columns.astype(str).str.strip()
        if 'COD CONTABLE' not in df_seps.columns:
            col_codigo = next((c for c in df_seps.columns if 'COD' in c.upper() and 'CONTABLE' in c.upper()), None)
            if col_codigo: df_seps = df_seps.rename(columns={col_codigo: 'COD CONTABLE'})
        if 'COD CONTABLE' in df_seps.columns:
            df_seps['COD CONTABLE'] = df_seps['COD CONTABLE'].astype(str).str.replace('.0', '', regex=False).str.strip()
        return df_seps
    except:
        return pd.DataFrame()

df_crudo = cargar_tasas_historicas()
techos_bce = cargar_techos_bce()
df_seps = cargar_boletines_financieros()

# ==========================================
# 3. LISTA DE AGENCIAS - PLAZA PASTAZA
# ==========================================
# Palabras clave para filtrar las entidades que operan físicamente en la provincia
keywords_pastaza = [
    'PICHINCHA', 'GUAYAQUIL', 'INTERNACIONAL', 'BANECUADOR', 'PRODUBANCO',
    'PASTAZA', 'SAN FRANCISCO', '29 DE OCTUBRE', 'JEP', 'MUSHUC RUNA',
    'OSCUS', 'EDUCADORES', 'MERCED', 'POLICIA NACIONAL', 'CAMARA DE COMERCIO DE AMBATO'
]

# ==========================================
# 4. BARRA LATERAL (FILTROS)
# ==========================================
st.sidebar.header("⚙️ Parámetros de Análisis")

# NUEVO: Selector de Alcance Geográfico (La "Hoja" de Pastaza)
alcance = st.sidebar.radio("📍 Alcance del Mercado", ["Nacional (Todo el S1 + Bancos)", "Plaza Local (Pastaza)"])

# Filtrar el DataFrame base según el alcance
if alcance == "Plaza Local (Pastaza)":
    # Filtra dinámicamente cualquier entidad que contenga una de las palabras clave de Pastaza
    df = df_crudo[df_crudo['razon_social'].apply(lambda x: any(kw in str(x).upper() for kw in keywords_pastaza))]
else:
    df = df_crudo.copy()

entidades_disponibles = sorted(df['razon_social'].unique())
entidad_base_default = next((e for e in entidades_disponibles if 'PASTAZA' in e.upper() and 'CACPE' in e.upper()), entidades_disponibles[0])

st.sidebar.subheader("1. Tu Institución")
entidad_principal = st.sidebar.selectbox("Entidad a Analizar (Base)", options=entidades_disponibles, index=entidades_disponibles.index(entidad_base_default))

st.sidebar.subheader("2. El Mercado (Competidores)")
filtro_competidores = st.sidebar.multiselect(
    "Seleccionar Competidores",
    options=[e for e in entidades_disponibles if e != entidad_principal],
    default=[e for e in entidades_disponibles if e != entidad_principal][:8] # Carga más competidores por defecto para la plaza local
)

entidades_grafico = [entidad_principal] + filtro_competidores

filtro_segmentos = st.sidebar.multiselect(
    "Segmento de Crédito",
    options=sorted(df['segmento_agrupado'].unique()),
    default=["Consumo", "Microcrédito", "Inmobiliario"]
)

fecha_min = df['fecha_dt'].min().date()
fecha_max = df['fecha_dt'].max().date()
rango_fechas = st.sidebar.slider("Rango Histórico", min_value=fecha_min, max_value=fecha_max, value=(fecha_min, fecha_max), format="YYYY-MM")

st.sidebar.markdown("---")
tipo_tasa_grafico = st.sidebar.radio("Métrica para el Gráfico Histórico", ["Tasa Efectiva", "Tasa Nominal"])

mask = (
    df['razon_social'].isin(entidades_grafico) &
    df['segmento_agrupado'].isin(filtro_segmentos) &
    (df['fecha_dt'].dt.date >= rango_fechas[0]) &
    (df['fecha_dt'].dt.date <= rango_fechas[1])
)
df_filtrado = df[mask]

# ==========================================
# 5. COMPORTAMIENTO HISTÓRICO
# ==========================================
# Título dinámico
st.header(f"📉 1. Evolución Histórica del Mercado: {alcance.split('(')[0].strip()}")

if not df_filtrado.empty:
    volumen_total = df_filtrado['monto_total'].sum()
    operaciones_total = df_filtrado['numero_operaciones'].sum()
    
    if volumen_total > 0:
        tasa_efectiva_global = df_filtrado['monto_x_tasa_efectiva'].sum() / volumen_total
        tasa_nominal_global = df_filtrado['monto_x_tasa_nominal'].sum() / volumen_total
    else:
        tasa_efectiva_global = tasa_nominal_global = 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Volumen Analizado", f"${volumen_total:,.0f}")
    col2.metric("📋 Total Operaciones", f"{operaciones_total:,.0f}")
    col3.metric("🎯 Tasa Efectiva Global", f"{tasa_efectiva_global:.2f}%")
    col4.metric("📄 Tasa Nominal Global", f"{tasa_nominal_global:.2f}%")
    
    st.markdown("---")

    col_izq, col_der = st.columns(2)
    
    with col_izq:
        st.subheader(f"Evolución de la {tipo_tasa_grafico}")
        tendencia = df_filtrado.groupby(['fecha_dt', 'razon_social']).agg(
            monto_sum=('monto_total', 'sum'),
            monto_tasa_efectiva_sum=('monto_x_tasa_efectiva', 'sum'),
            monto_tasa_nominal_sum=('monto_x_tasa_nominal', 'sum')
        ).reset_index()
        
        if tipo_tasa_grafico == "Tasa Efectiva":
            tendencia['Tasa Plot'] = tendencia['monto_tasa_efectiva_sum'] / tendencia['monto_sum']
        else:
            tendencia['Tasa Plot'] = tendencia['monto_tasa_nominal_sum'] / tendencia['monto_sum']
        
        color_map = {entidad: 'red' if entidad == entidad_principal else '#1f77b4' for entidad in entidades_grafico}
        
        fig_tasas = px.line(
            tendencia, x='fecha_dt', y='Tasa Plot', color='razon_social',
            markers=True, color_discrete_map=color_map,
            labels={'Tasa Plot': f'{tipo_tasa_grafico} (%)', 'fecha_dt': 'Fecha', 'razon_social': 'Entidad'}
        )
        fig_tasas.update_layout(legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_tasas, use_container_width=True)

    with col_der:
        st.subheader("Estructura de Colocación")
        volumen_seg = df_filtrado.groupby(['razon_social', 'segmento_agrupado'])['monto_total'].sum().reset_index()
        fig_vol = px.bar(
            volumen_seg, x='segmento_agrupado', y='monto_total', color='razon_social',
            barmode='group', color_discrete_map=color_map
        )
        fig_vol.update_layout(legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_vol, use_container_width=True)

# ==========================================
# 6. MATRIZ DE ALM & PRICING
# ==========================================
st.markdown("---")
st.header(f"🎯 2. Matriz de Competitividad e Impacto ({alcance.split('(')[0].strip()})")

saldos_entidad = {'Consumo': 0, 'Microcrédito': 0, 'Inmobiliario': 0}

# Cruce con la SEPS (Solo aplica si la entidad base está en el boletín de cooperativas)
if not df_seps.empty:
    col_seps = next((c for c in df_seps.columns if str(c).upper().replace('LIMITADA', '').replace('LTDA', '').strip() in entidad_principal.upper()), None)
    if col_seps:
        try:
            saldos_entidad['Consumo'] = float(df_seps[df_seps['COD CONTABLE'] == '1402'][col_seps].values[0])
            saldos_entidad['Inmobiliario'] = float(df_seps[df_seps['COD CONTABLE'] == '1403'][col_seps].values[0])
            saldos_entidad['Microcrédito'] = float(df_seps[df_seps['COD CONTABLE'] == '1404'][col_seps].values[0])
        except: pass

mes_actual = df['fecha'].max()
df_mes = df[df['fecha'] == mes_actual]

resultados = []
for segmento in ['Consumo', 'Microcrédito', 'Inmobiliario']:
    datos_seg = df_mes[df_mes['segmento_agrupado'] == segmento]
    
    # Base
    base = datos_seg[datos_seg['razon_social'] == entidad_principal]
    tasa_efec_base = base['monto_x_tasa_efectiva'].sum() / base['monto_total'].sum() if base['monto_total'].sum() > 0 else 0
    tasa_nom_base = base['monto_x_tasa_nominal'].sum() / base['monto_total'].sum() if base['monto_total'].sum() > 0 else 0
    
    # Mercado
    mercado = datos_seg[datos_seg['razon_social'].isin(filtro_competidores)]
    tasa_efec_mercado = mercado['monto_x_tasa_efectiva'].sum() / mercado['monto_total'].sum() if mercado['monto_total'].sum() > 0 else 0
    
    resultados.append({
        'Segmento': segmento,
        'Saldo Cartera ($)': saldos_entidad.get(segmento, 0),
        'Tu Tasa Nominal (%)': round(tasa_nom_base, 2),
        'Tu Tasa Efectiva (%)': round(tasa_efec_base, 2),
        'Prom. Mercado Efectiva (%)': round(tasa_efec_mercado, 2),
        'Techo Legal BCE (%)': techos_bce.get(segmento, 0)
    })

df_estrategia = pd.DataFrame(resultados)
df_estrategia['Brecha Competitiva (p.p)'] = df_estrategia['Prom. Mercado Efectiva (%)'] - df_estrategia['Tu Tasa Efectiva (%)']

df_estrategia['Incremento Sugerido (%)'] = df_estrategia.apply(
    lambda row: min(row['Brecha Competitiva (p.p)'], row['Techo Legal BCE (%)'] - row['Tu Tasa Efectiva (%)']) if row['Brecha Competitiva (p.p)'] > 0 else 0, 
    axis=1
)
df_estrategia['Impacto Anual Proyectado ($)'] = df_estrategia['Saldo Cartera ($)'] * (df_estrategia['Incremento Sugerido (%)'] / 100)

df_vista = df_estrategia.copy()
df_vista['Saldo Cartera ($)'] = df_vista['Saldo Cartera ($)'].apply(lambda x: f"${x:,.0f}")
df_vista['Impacto Anual Proyectado ($)'] = df_vista['Impacto Anual Proyectado ($)'].apply(lambda x: f"${x:,.0f}")

st.dataframe(df_vista.style.applymap(
    lambda x: 'background-color: #d4edda; color: #155724' if float(x.replace('$', '').replace(',', '')) > 0 else '', 
    subset=['Impacto Anual Proyectado ($)']
), use_container_width=True)