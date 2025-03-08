import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import plotly.express as px
import os

# Configuración de la página
st.set_page_config(page_title="Visualización de Pedidos", layout="wide")

# Cargar datos
def cargar_datos():
    try:
        puntos_venta = pd.read_excel("puntos_venta.xlsx")
        pedidos_servidos = pd.read_excel("pedidos_servidos.xlsx")
        
        # Convertir fechas
        pedidos_servidos["fecha_servicio"] = pd.to_datetime(
            pedidos_servidos["fecha_servicio"], 
            errors='coerce'
        )
        
        return puntos_venta, pedidos_servidos, None
    except Exception as e:
        return None, None, f"Error al cargar datos: {str(e)}"

# Filtrar pedidos
def filtrar_pedidos(pedidos, fecha=None, repartidor=None, viaje=None):
    if pedidos is None:
        return None
    
    datos_filtrados = pedidos.copy()
    
    if fecha:
        # Convertir la fecha seleccionada a datetime si no lo es ya
        if not isinstance(fecha, pd.Timestamp):
            fecha = pd.Timestamp(fecha)
        
        # Comparar solo las fechas sin las horas
        datos_filtrados = datos_filtrados[
            datos_filtrados["fecha_servicio"].dt.date == fecha.date()
        ]
    
    if repartidor and repartidor != "Todos":
        datos_filtrados = datos_filtrados[datos_filtrados["repartidor"] == repartidor]
    
    if viaje and viaje != "Todos":
        # Verificar el tipo de datos de la columna viaje
        if datos_filtrados["viaje"].dtype == 'object':
            # Si es texto, comparar directamente
            datos_filtrados = datos_filtrados[datos_filtrados["viaje"] == viaje]
        else:
            try:
                # Intentar convertir a número si la columna es numérica
                viaje_num = float(viaje) if '.' in viaje else int(viaje)
                datos_filtrados = datos_filtrados[datos_filtrados["viaje"] == viaje_num]
            except (ValueError, TypeError):
                # Si falla la conversión, comparar como texto
                datos_filtrados = datos_filtrados[datos_filtrados["viaje"].astype(str) == viaje]
    
    return datos_filtrados

# Unir datos
def unir_datos(pedidos, puntos_venta):
    if pedidos is None or puntos_venta is None:
        return None
    
    # Determinar la columna de unión
    if "punto_venta" in pedidos.columns and "punto_venta" in puntos_venta.columns:
        # Unir por punto_venta
        datos_unidos = pedidos.merge(puntos_venta, on="punto_venta", how="left")
    elif "punto_venta" in pedidos.columns and "codigo_punto_venta" in puntos_venta.columns:
        # Unir por punto_venta = codigo_punto_venta
        datos_unidos = pedidos.merge(
            puntos_venta, 
            left_on="punto_venta", 
            right_on="codigo_punto_venta", 
            how="left"
        )
    else:
        st.error("No se encontraron columnas compatibles para unir los datos")
        return None
    
    # Verificar columnas de coordenadas
    if "latitud" in datos_unidos.columns and "longitud" in datos_unidos.columns:
        return datos_unidos
    elif "Latitud" in datos_unidos.columns and "Longitud" in datos_unidos.columns:
        # Renombrar columnas
        datos_unidos = datos_unidos.rename(columns={
            "Latitud": "latitud",
            "Longitud": "longitud"
        })
        return datos_unidos
    else:
        st.error("No se encontraron columnas de coordenadas en los datos unidos")
        return None

# Crear mapa
def crear_mapa(datos, mostrar_heatmap=False, color_dict=None):
    if datos is None or datos.empty:
        return None
    
    # Asegurar que las coordenadas sean numéricas
    datos["latitud"] = pd.to_numeric(datos["latitud"], errors='coerce')
    datos["longitud"] = pd.to_numeric(datos["longitud"], errors='coerce')
    datos["peso_teorico"] = pd.to_numeric(datos["peso_teorico"], errors='coerce')
    
    # Filtrar datos válidos
    datos_validos = datos.dropna(subset=["latitud", "longitud"])
    
    if datos_validos.empty:
        st.error("No hay datos con coordenadas válidas para mostrar en el mapa")
        return None
    
    # Crear mapa
    centro = [datos_validos["latitud"].mean(), datos_validos["longitud"].mean()]
    mapa = folium.Map(location=centro, zoom_start=12)
    
    # Crear diccionario de colores si no se proporciona
    if color_dict is None:
        colores = ["red", "blue", "green", "purple", "orange", "darkred", "lightred", 
                  "beige", "darkblue", "darkgreen", "cadetblue", "pink", "gray"]
        repartidores = datos["repartidor"].unique()
        color_dict = {repartidor: colores[i % len(colores)] for i, repartidor in enumerate(repartidores)}
    
    # Añadir leyenda de colores al mapa
    legend_html = """
    <div style="position: fixed; bottom: 50px; left: 50px; z-index: 1000; background-color: white; 
    padding: 10px; border: 1px solid grey; border-radius: 5px;">
    <h4>Repartidores</h4>
    """
    for repartidor, color in color_dict.items():
        legend_html += f'<div><i style="background:{color};width:10px;height:10px;display:inline-block;"></i> {repartidor}</div>'
    legend_html += '</div>'
    mapa.get_root().html.add_child(folium.Element(legend_html))
    
    # Añadir marcadores
    for _, row in datos_validos.iterrows():
        # Determinar el nombre del punto de venta
        if "nombre" in row:
            nombre = row["nombre"]
        elif "nombre_comercial" in row:
            nombre = row["nombre_comercial"]
        elif "Nombre Comercial" in row:
            nombre = row["Nombre Comercial"]
        else:
            nombre = f"Punto {row.get('punto_venta', 'desconocido')}"
        
        popup_text = f"""
        <b>{nombre}</b><br>
        Pedido: {row.get('Pedido', 'N/A')}<br>
        Peso: {row.get('peso_teorico', 0):.2f} kg<br>
        Repartidor: {row['repartidor']}<br>
        Viaje: {row.get('viaje', 'N/A')}<br>
        """
        
        folium.Marker(
            location=[row["latitud"], row["longitud"]],
            popup=folium.Popup(popup_text, max_width=300),
            icon=folium.Icon(color=color_dict[row["repartidor"]])
        ).add_to(mapa)
    
    # Añadir heatmap si se solicita
    if mostrar_heatmap and not datos_validos.empty:
        # Filtrar solo datos válidos para el heatmap
        heat_data = []
        for _, row in datos_validos.iterrows():
            try:
                lat = float(row["latitud"])
                lon = float(row["longitud"])
                peso = float(row["peso_teorico"])
                if not (pd.isna(lat) or pd.isna(lon) or pd.isna(peso)):
                    heat_data.append([lat, lon, peso])
            except (ValueError, TypeError):
                continue
        
        if heat_data:  # Solo añadir si hay datos válidos
            HeatMap(heat_data).add_to(mapa)
    
    return mapa

# Crear gráficos
def crear_graficos(datos):
    if datos is None or datos.empty:
        return None, None
        
    # Gráfico de barras: Peso por repartidor
    fig_peso = px.bar(
        datos.groupby("repartidor")["peso_teorico"].sum().reset_index(),
        x="repartidor", 
        y="peso_teorico",
        title="Peso Total por Repartidor (kg)",
        labels={"repartidor": "Repartidor", "peso_teorico": "Peso Total (kg)"},
        color="repartidor"
    )
    
    # Gráfico de pastel: Número de pedidos por repartidor
    fig_pedidos = px.pie(
        datos.groupby("repartidor").size().reset_index(name="num_pedidos"),
        values="num_pedidos",
        names="repartidor",
        title="Distribución de Pedidos por Repartidor"
    )
    
    return fig_peso, fig_pedidos

# Interfaz principal
def main():
    st.title("📦 Visualización de Pedidos Servidos")
    
    # Cargar datos
    puntos_venta, pedidos_servidos, error = cargar_datos()
    
    if error:
        st.error(error)
        st.stop()
    
    # Crear sidebar para filtros
    with st.sidebar:
        st.header("Filtros")
        
        # Selección de fecha
        fechas_disponibles = sorted(pedidos_servidos["fecha_servicio"].dt.date.unique())
        if fechas_disponibles:
            fecha_seleccionada = st.date_input("Selecciona una fecha", fechas_disponibles[-1])
        else:
            st.error("No hay fechas disponibles en los datos")
            st.stop()
        
        # Filtrar pedidos por fecha para obtener repartidores y viajes disponibles
        pedidos_fecha = filtrar_pedidos(pedidos_servidos, fecha_seleccionada)
        
        # Selección de repartidor
        repartidores = ["Todos"] + sorted(pedidos_fecha["repartidor"].unique().tolist())
        repartidor_seleccionado = st.selectbox("Selecciona un repartidor", repartidores)
        
        # Filtrar por repartidor para obtener viajes disponibles
        if repartidor_seleccionado != "Todos":
            pedidos_repartidor = pedidos_fecha[pedidos_fecha["repartidor"] == repartidor_seleccionado]
            viajes_disponibles = pedidos_repartidor["viaje"].astype(str).unique().tolist()
        else:
            viajes_disponibles = pedidos_fecha["viaje"].astype(str).unique().tolist()
        
        # Ordenar los viajes numéricamente si es posible
        try:
            viajes_disponibles = sorted(viajes_disponibles, key=lambda x: float(x) if '.' in x else int(x))
        except (ValueError, TypeError):
            viajes_disponibles = sorted(viajes_disponibles)
        
        # Selección de viaje
        viajes = ["Todos"] + viajes_disponibles
        viaje_seleccionado = st.selectbox("Selecciona un viaje", viajes)
        
        # Opciones visuales
        st.header("Opciones del mapa")
        mostrar_heatmap = st.checkbox("Mostrar mapa de calor", False)
    
    # Filtrar datos
    pedidos_filtrados = filtrar_pedidos(
        pedidos_servidos, 
        fecha_seleccionada, 
        repartidor_seleccionado, 
        viaje_seleccionado if viaje_seleccionado != "Todos" else None
    )
    
    if pedidos_filtrados.empty:
        st.warning(f"No hay pedidos para los filtros seleccionados: Fecha: {fecha_seleccionada}, Repartidor: {repartidor_seleccionado}, Viaje: {viaje_seleccionado}")
        st.stop()
    
    # Unir datos
    datos_unidos = unir_datos(pedidos_filtrados, puntos_venta)
    
    if datos_unidos is None:
        st.error("No se pudieron unir los datos")
        st.stop()
    
    # Crear diccionario de colores para repartidores
    colores = ["red", "blue", "green", "purple", "orange", "darkred", "lightred", 
              "beige", "darkblue", "darkgreen", "cadetblue", "pink", "gray"]
    repartidores = datos_unidos["repartidor"].unique()
    color_dict = {repartidor: colores[i % len(colores)] for i, repartidor in enumerate(repartidores)}
    
    # Layout de columnas
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Mostrar mapa
        st.subheader("Mapa de Entregas")
        mapa = crear_mapa(datos_unidos, mostrar_heatmap, color_dict)
        if mapa:
            st_folium(mapa, width=800, height=600)
        else:
            st.error("No se pudo crear el mapa")
    
    with col2:
        # Mostrar estadísticas con colores
        st.subheader("Resumen por Repartidor")
        
        # Convertir peso_teorico a numérico
        datos_unidos["peso_teorico"] = pd.to_numeric(datos_unidos["peso_teorico"], errors='coerce')
        
        # Crear resumen
        resumen = datos_unidos.groupby("repartidor")["peso_teorico"].agg(['sum', 'count']).reset_index()
        resumen.columns = ["Repartidor", "Peso Total (kg)", "Número de Pedidos"]
        
        # Añadir columna de color
        resumen["Color"] = resumen["Repartidor"].map(lambda x: f'<span style="color:{color_dict[x]}">■■■</span>')
        
        # Ordenar por peso total
        resumen = resumen.sort_values(by="Peso Total (kg)", ascending=False)
        
        # Mostrar tabla
        st.markdown(resumen.to_html(escape=False, index=False), unsafe_allow_html=True)
        
        # Mostrar número total de pedidos
        total_pedidos = len(pedidos_filtrados)
        total_peso = datos_unidos["peso_teorico"].sum()
        
        st.metric("Total de pedidos", total_pedidos)
        st.metric("Peso total (kg)", f"{total_peso:.2f}")
    
    # Gráficos
    st.subheader("Análisis Gráfico")
    fig_peso, fig_pedidos = crear_graficos(datos_unidos)
    
    if fig_peso and fig_pedidos:
        grafico1, grafico2 = st.columns(2)
        
        with grafico1:
            st.plotly_chart(fig_peso, use_container_width=True)
            
        with grafico2:
            st.plotly_chart(fig_pedidos, use_container_width=True)
    else:
        st.warning("No se pudieron crear los gráficos con los datos disponibles.")

if __name__ == "__main__":
    main()