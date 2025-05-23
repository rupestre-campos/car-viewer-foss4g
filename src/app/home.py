
import folium.plugins
import streamlit as st
import requests
import folium
import json
from streamlit_folium import st_folium
from streamlit_navigation_bar import st_navbar
from datetime import datetime

from unidecode import unidecode
import os

API_KEY = os.getenv("API_KEY_FRONTEND", "1234")
BASE_URL = os.getenv("API_URL", "http://localhost:8000")

cache_ttl = int(os.getenv("CACHE_TTL", "300"))
cache_ttl_get_layers  = int(os.getenv("CACHE_TTL_GET_LAYERS", "3600"))

default_car_code = os.getenv("DEFAULT_CAR_CODE", "ABCD")

st.set_page_config(page_title="Car Viewer", page_icon=":world_map:", layout="wide")
option_nav_bar = st_navbar(
    pages=["CAR Viewer", "Search on map", ],
    selected="CAR Viewer",
    options={"use_padding": True}
)

# Function to validate car code
def validate_car_code(car_code):
    return len(car_code) == 43

def get_layers_api():
    url = f"{BASE_URL}/list-layers?API_KEY={API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Failed to fetch data: {response.status_code}")
        return {}

@st.cache_data(ttl=cache_ttl_get_layers)
def get_layers():
    layers_data = get_layers_api()
    return layers_data

# Function to get GeoJSON data
@st.cache_data(ttl=cache_ttl, max_entries=5)
def get_geojson(car_code):
    url = f"{BASE_URL}/layers/{car_code}.geojson?API_KEY={API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Failed to fetch data: {response.status_code}")
        return {}

@st.cache_data(ttl=cache_ttl, max_entries=5)
def get_pdf(car_code, param):
    url = f"{BASE_URL}/layers/{car_code}.pdf?API_KEY={API_KEY}{param}"
    headers = {"API_KEY": API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.content
    else:
        st.error(f"Failed to fetch data: {response.status_code}")
        return {}

@st.cache_data(ttl=cache_ttl, max_entries=5)
def get_kml(car_code, param):
    url = f"{BASE_URL}/layers/{car_code}.kmz?API_KEY={API_KEY}{param}"
    headers = {"API_KEY": API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.content
    else:
        st.error(f"Failed to fetch data: {response.status_code}")
        return {}

def get_style_rules():
    return {
        "hidrografia": {"color": "blue", "fillColor": "blue", "fillOpacity": 0.6, "opacity":0.5, "weight":0},
        "area_imovel": {"color": "yellow", "fillColor": "white", "fillOpacity":0.1, "weight":3, "opacity":1},
        "apps": {"color": "red", "fillColor": "red", "fillOpacity": 0.3, "opacity":0.5, "weight":0.8},
        "reserva_legal": {"color": "green", "fillColor": "green", "fillOpacity": 0.4, "opacity":0.8, "weight":3},
        "area_consolidada": {"color": "lightyellow", "fillColor": "lightyellow", "fillOpacity": 0.3, "opacity":0.5, "weight":0},
        "uso_restrito": {"color": "orange", "fillColor": "orange", "fillOpacity": 0.5, "opacity":0.5, "weight":0},
        "servidao_administrativa": {"color": "black", "fillColor": "black", "fillOpacity": 0.5, "opacity":0.5, "weight":1},
        "area_pousio": {"color": "lightorange", "fillColor": "lightorange", "fillOpacity": 0.5, "opacity":0.5, "weight":0},
        "vegetacao_nativa": {"color": "lightgreen", "fillColor": "lightgreen", "fillOpacity": 0.4, "opacity":0.3, "weight":3},
        #"arl_proposta": {"color": "green", "fillColor": "green", "fillOpacity": 0.5, "opacity":0.5, "weight":0},
    }

def get_style(feature):
    cod_tema = feature['properties'].get('cod_tema', '').lower()
    return get_style_cod_theme(cod_tema)

def get_style_cod_theme(cod_tema):
    style_rules = get_style_rules()
    cod_tema = str(cod_tema).lower()
    if cod_tema in style_rules:
        return style_rules[cod_tema]
    if "app" in cod_tema.lower():
        return style_rules["apps"]
    if "arl" in cod_tema.lower():
        return style_rules["reserva_legal"]
    if "reservatorio" in cod_tema.lower():
        return style_rules["hidrografia"]
    if "rio" in cod_tema.lower():
        return style_rules["hidrografia"]
    if "servidao" in cod_tema.lower():
        return style_rules["servidao_administrativa"]
    if "publica" in cod_tema.lower():
        return style_rules["servidao_administrativa"]
    if "uso_restrito" in cod_tema.lower():
        return style_rules["uso_restrito"]
    return {"color": "purple", "fillColor": "purple", "opacity":0.5, "fillOpacity": 0.5,}

def add_geojson_to_map(m, geojson):
    feature_groups = {}
    area_imovel = {}
    for feature in geojson['features']:
        cod_tema = feature['properties'].get('cod_tema', '').lower()
        if not cod_tema in feature_groups:
            feature_groups[cod_tema] = folium.FeatureGroup(name=cod_tema.replace("_"," ").capitalize())
        if cod_tema.lower() == "area_imovel":
            area_imovel = feature
        # Style popup content
        popup_html = "<div style='font-size: 16px;'>"
        for key, value in feature['properties'].items():
            popup_html += f"<b>{key}:</b> {value}<br>"
        popup_html += "</div>"
        popup_content = folium.Popup(html=popup_html, max_width=300)

        # Style tooltip content
        tooltip_text = feature['properties'].get('nom_tema', 'No Name')
        tooltip_html = f"<div style='font-size: 14px;'>{tooltip_text}</div>"
        tooltip_content = folium.Tooltip(tooltip_html)
        folium.GeoJson(
            feature,
            name=cod_tema,
            style_function=get_style,
            highlight_function=lambda x: {"color": "red", "fillColor": "red", "weight":5, "opacity":0.8, "fillOpacity":0.1, "dashArray": "3, 6"},
            popup=popup_content,
            tooltip=tooltip_content,
            popup_keep_highlighted=True,
        ).add_to(feature_groups[cod_tema])

    # Add all feature groups to the map
    if "area_imovel" in feature_groups:
        feature_groups["area_imovel"].add_to(m)
    for layer, fg in feature_groups.items():
        if layer == "area_imovel":
            continue
        fg.add_to(m)


    m.fit_bounds(m.get_bounds())
    return m, area_imovel

def fetch_intersecting_perimeters(latitude, longitude):
    url = f"{BASE_URL}/intersecting-perimeters"
    payload = {"latitude": latitude, "longitude": longitude}
    headers = {"Content-Type": "application/json", "API_KEY": API_KEY}
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch intersecting perimeters: {response.status_code}")
        print(response.content)
        return {}


def parse_feature_status(status):
    if not status:
        return "Not found"
    if status == "AT":
        return "Active"
    if status == "PE":
        return "Pending"
    if status == "SU":
        return "Suspended"
    if status == "CA":
        return "Canceled"
    return status

def parse_feature_type(type_feature):
    if not type_feature:
        return "Not found"
    if type_feature == "IRU":
        return "Rural Property"
    if type_feature == "PCT":
        return "Traditional Peoples and Comunities"
    if type_feature == "AST":
        return "Rural Settlement"
    return type_feature

def parse_feature_condiction(condiction):
    condiction = unidecode(condiction)
    if not condiction:
        return "Not found"
    if condiction == "Aguardando analise":
        return "Waiting verification"
    if condiction == "Em analise":
        return "Verification in progress"
    if condiction == "Analisado":
        return "Verified"
    if condiction == "Analisado, aguardando atendimento a notificacao":
        return "Verified but waiting notification response"
    if "pendencia" in condiction:
        return "Pendencies in register"
    return condiction

def add_map_options(m):
    #folium.plugins.Geocoder(position="bottomright", add_marker=False).add_to(m)
    #folium.plugins.LocateControl(
    #    strings={"title": "See you current location"}).add_to(m)
    #folium.plugins.MeasureControl(primary_area_unit="hectares",position="topleft").add_to(m)
    #folium.plugins.MousePosition(position="bottomright").add_to(m)
    openstreetmap = folium.TileLayer(
        tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attr='OpenStreetMap',
        name='OpenStreetMap',
        overlay=False,
        control=True,
        show=False
    )
    openstreetmap.add_to(m)

    # Add Google Satellite layer
    google_satellite = folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        attr='Google Satellite',
        name='Google Satellite',
        overlay=False,
        control=True,
        max_native_zoom=18,
        max_zoom=22,
        min_zoom=0,
        show=False
    )
    google_satellite.add_to(m)
    # Add OpenStreetMap layer

    # Add Google Satellite Hybrid layer
    google_hybrid = folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr='Google Hybrid',
        name='Google Hybrid',
        overlay=False,
        control=True,
        max_native_zoom=18,
        max_zoom=22,
        min_zoom=0,
        show=True
    )
    google_hybrid.add_to(m)

    return m

def main():

    # Streamlit app
    m = folium.Map(
        location=[-15.0, -55.0],
        zoom_start=4,
        min_zoom=3,
        max_zoom=22,
        control_scale=True,
        tiles=None,
        prefer_canvas=True
    )


    if option_nav_bar == "CAR Viewer":
        st.write("Search CAR by code")
    if option_nav_bar == "Search on map":
        st.write("Search with a click on map")

    car_code = st.query_params.get("car_code")

    if not car_code:
        car_code = default_car_code

    if "intersect_results" not in st.session_state:
        st.session_state["intersect_results"] = []
    if "last_clicked" not in st.session_state:
        st.session_state["last_clicked"] = {}
    if "geojson" not in st.session_state:
        st.session_state["geojson"] = {}

    click_on_map_search = False
    if "search on map" in option_nav_bar.lower():
        click_on_map_search = True
    else:
        car_code = st.text_input("Input CAR Code", max_chars=55, value=car_code, placeholder="AC-1200435-7F0D43D35743470E89A58271AE84AE46")

    message_box = st.empty()

    with st.sidebar:
        if st.session_state["intersect_results"]:
            car_code_index = st.session_state["intersect_results"].index(car_code) if car_code in st.session_state["intersect_results"] else None
            if car_code_index:
                car_code = st.selectbox(
                    "Select from CAR found list",
                    options=st.session_state["intersect_results"],
                    index=car_code_index)
                reset_button = st.button("Reset results")
                if reset_button:
                    st.session_state["intersect_results"] = []

        if car_code is None:
            car_code =  ""

        car_code = car_code.strip().upper().replace(".","").replace(" ","")
        st.query_params["car_code"] = car_code


        if validate_car_code(car_code):
            message_box.write("Getting data...")
            car_data = get_geojson(car_code)
            if car_data:
                message_box.write("Done!")
                st.session_state["geojson"] = car_data
            else:
                message_box.write("Could not get CAR at this moment")
        else:
            message_box.write("Invalid CAR Code. Please enter a code with 43 characters.")

        if st.session_state["geojson"]:
            message_box.write("loading map")
            m, area_imovel_feature = add_geojson_to_map(m, st.session_state["geojson"])

            message_box.write("Creating download options...")
            st.write("Download options")
            download_choice = st.radio("Content", options=["Perimeter", "All layers"], index=0)
            if download_choice == "Perimeter":
                param = "&layer=area_imovel"
                file_ending = ""
            if download_choice == "All layers":
                param = ""
                file_ending = "-all-layers"

            if st.button("Create .GeoPDF"):
                pdf_map = get_pdf(car_code, param)

                st.download_button(
                    label="Download",
                    data=pdf_map,
                    file_name=f'{car_code}_{datetime.now().strftime("%Y-%M-%dT%H-%m-%S")}{file_ending}.pdf',
                    mime="application/pdf"
                )
            if st.button("Create .KML"):
                kmz_file_bytes = get_kml(car_code, param)

                st.download_button(
                    label="Download",
                    data=kmz_file_bytes,
                    file_name=f'{car_code}_{datetime.now().strftime("%Y-%M-%dT%H-%m-%S")}{file_ending}.kmz',
                    mime="application/vnd.google-earth.kmz"
                )
            if st.button("Create .GeoJSON"):
                if download_choice == "All layers":
                    st.download_button(
                        "Download",
                        data=json.dumps(st.session_state["geojson"]),
                        file_name=f'{car_code}_{datetime.now().strftime("%Y-%M-%dT%H-%m-%S")}{file_ending}.geojson'
                    )
                else:
                    st.download_button(
                        "Download",
                        data=json.dumps({
                            "type": "FeatureCollection",
                            "features": [area_imovel_feature]
                        }),
                        file_name=f'{car_code}_{datetime.now().strftime("%Y-%M-%dT%H-%m-%S")}{file_ending}.geojson'
                    )
            message_box.write("refreshing available layers...")
            layers = get_layers()
            with st.expander("Available data per state:"):
                st.json(layers, expanded=True)


    if click_on_map_search and st.session_state["last_clicked"]:
        st.write(f"Clicked at Lat: {st.session_state['last_clicked']['lat']:6f} Long: {st.session_state['last_clicked']['lng']:6f}")
    message_box.write("loading map...")
    if st.session_state["geojson"]:
        st.markdown(f"### {car_code}")
        feature_area_ha = area_imovel_feature.get("properties", {}).get("num_area")
        feature_status = parse_feature_status(area_imovel_feature.get("properties", {}).get("ind_status"))
        feature_condiction = parse_feature_condiction(area_imovel_feature.get("properties", {}).get("des_condic"))
        feature_type = parse_feature_type(area_imovel_feature.get("properties", {}).get("ind_tipo"))
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"**Total Area:** {feature_area_ha} ha ")
        with col2:
            st.markdown(f"**Status:** {feature_status}")
        with col3:
            st.markdown(f"**Type:** {feature_type}")
        with col4:
            st.markdown(f"**Analysis status:** {feature_condiction}")

    search_point_at_box = st.empty()
    search_result_box = st.empty()
    #vector_layer_area_imovel_pendency._template = custom_template

    m = add_map_options(m)

    layer_control = folium.LayerControl()
    drawings = st_folium(
        m,
        use_container_width=True,
        returned_objects=["last_clicked"],
        layer_control=layer_control
    )
    message_box.write(" ")

    if drawings.get("last_clicked") and click_on_map_search:
        search = ""
        drawing = drawings.get("last_clicked")
        if drawing != st.session_state["last_clicked"]:

            search_point_at_box.write(f"Searching point Lat: {drawing['lat']:6f} Long: {drawing['lng']:6f}...")

            search = fetch_intersecting_perimeters(latitude=drawing["lat"], longitude=drawing["lng"])
            if len(search.get("features", [])) > 0:
                result_codes = []
                for feature in search["features"]:
                    cod_imovel = feature.get("properties",{}).get("cod_imovel")
                    result_codes.append(cod_imovel)

                st.query_params["car_code"] = cod_imovel
                st.session_state["intersect_results"] = result_codes
                st.session_state["last_clicked"] = drawing
                st.rerun()
            else:
                search_result_box.write(":red[None CAR register found on click, try again!]")

    if drawings.get("last_clicked") and not click_on_map_search:
        last_clicked_point = drawings.get("last_clicked")
        st.session_state["last_clicked"] = last_clicked_point

if __name__=="__main__":
    main()