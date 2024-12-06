
import os
import json
from osgeo import ogr, osr, gdal
import matplotlib.colors as mcolors
import simplekml
from datetime import datetime

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


def color_name_to_hex(color_name):
    try:
        return mcolors.to_hex(color_name)
    except Exception:
        return "#000000"

def color_name_to_hex_with_alpha(color_name, alpha=1.0, invert_alpha=False, bgr=False):
    """
    Convert a color name to a hex value with alpha (transparency).
    Alpha should be a float between 0.0 (fully transparent) and 1.0 (fully opaque).
    """
    try:
        # Get the hex color code without the '#' and convert to RGBA
        hex_color = mcolors.to_hex(color_name)[1:]

        # Scale alpha to 255 and convert to hex
        alpha_hex = f"{int(alpha * 255):02X}"
        if bgr:
            hex_color = f"{hex_color[-2:]}{hex_color[2:4]}{hex_color[:2]}"
        if invert_alpha:
            return f"#{alpha_hex}{hex_color}"
        return f"#{hex_color}{alpha_hex}"
    except ValueError:
        return "#000000FF"  # Default to black with full opacity if color name not found


def read_file_as_bytes(file_path):
    with open(file_path, "rb") as file:
        file_bytes = file.read()
    return file_bytes

def create_pdf_from_geojson(geojson_data, cod_imovel):
    output_pdf = f'/tmp/{cod_imovel}.pdf'
    # Create a temporary file to store the GeoJSON data
    temp_geojson_file = '/tmp/temp_geojson.json'
    with open(temp_geojson_file, 'w') as f:
        json.dump(geojson_data, f)

    # Open the GeoJSON file with OGR
    driver = ogr.GetDriverByName('GeoJSON')
    dataSource = driver.Open(temp_geojson_file, 0)  # 0 means read-only

    if dataSource is None:
        print('Could not open file')
        return

    # Create a spatial reference
    spatialRef = osr.SpatialReference()
    spatialRef.ImportFromEPSG(4326)  # Assuming WGS84

    # Create the output PDF driver
    driver_pdf = gdal.GetDriverByName('PDF')
    if driver_pdf is None:
        print('PDF driver is not available.')
        return
    creation_date = datetime.now().strftime("%Y%M%d%H%M%S")+"+00'00'"

    # PDF creation options
    pdf_options = [
        "AUTHOR=Cainã K. Campos https://car.rupestre-campos.org",
        "CREATOR=GDAL",
        f"CREATION_DATE=D:{creation_date}",
        "KEYWORDS=CAR, GDAL, geospatial PDF",
        "PRODUCER=GDAL 3.6.2",
        f"SUBJECT=CAR - {cod_imovel}",
        f"TITLE=CAR - {cod_imovel}"
    ]
    # Create the PDF file
    output_ds = driver_pdf.Create(output_pdf, 0, 0, 0, gdal.GDT_Unknown, options=pdf_options)

    if output_ds is None:
        print('Could not create PDF file')
        return

    # Create a layer for the PDF
    output_layer = output_ds.CreateLayer('layer', srs=spatialRef, geom_type=ogr.wkbUnknown)
    in_lyr = dataSource.GetLayerByIndex(0)
    lyr_def = in_lyr.GetLayerDefn ()
    for i in range(lyr_def.GetFieldCount()):
        output_layer.CreateField ( lyr_def.GetFieldDefn(i) )
    # Iterate through features and style them
    for feature in dataSource.GetLayer():
        geom = feature.GetGeometryRef()
        cod_tema = feature.GetField('cod_tema')

        style = get_style_cod_theme(cod_tema)
        fillOpacity = style.get('fillOpacity', 0.5)
        # Apply the style to the feature
        color = color_name_to_hex_with_alpha(style['color'], style.get("opacity", 0.5))
        fillColor = color_name_to_hex_with_alpha(style.get('fillColor', 'none'), fillOpacity)
        line_width = style.get("weight", 1)
        # Create a new feature with the same geometry
        new_feature = ogr.Feature(output_layer.GetLayerDefn())
        new_feature.SetGeometry(geom.Clone())

        # Set the style of the new feature
        style_string = f"PEN(c:{color},w:{line_width}mm)"
        if fillColor != 'none':
            style_string += f";BRUSH(fc:{fillColor})"
        if cod_tema.lower() == "area_imovel":
            car_code = feature.GetField('cod_imovel')
            area_ha = feature.GetField('num_area')
            status = feature.GetField('ind_status')
            condiction =feature.GetField('des_condic')
            text = f'{car_code}-{status}-{condiction}-{area_ha:4f} ha'
            style_string += f';LABEL(f:"Arial, Helvetica", s:26pt, t:"{text}")'
        if "app_total" in cod_tema.lower():
            area_ha = feature.GetField('num_area')
            text = f'APP Total\n {area_ha:4f} ha'
            style_string += f';LABEL(f:"Arial, Helvetica", c:#FF0000, dx:-10, dy:10, s:220px, t:"{text}")'
        if "arl" in cod_tema.lower():
            area_ha = feature.GetField('num_area')
            text = f'{cod_tema}\n {area_ha:4f} ha'
            style_string += f';LABEL(f:"Arial, Helvetica", c:#00FF00, dx:-10, dy:10, s:220px, t:"{text}")'

        new_feature.SetStyleString(style_string)

        # Add all attributes to the feature
        for i in range(feature.GetFieldCount()):
            field_name = feature.GetFieldDefnRef(i).GetName()
            field_value = feature.GetField(field_name)
            new_feature.SetField(field_name, field_value)

        output_layer.CreateFeature(new_feature)

        # Destroy the feature to free resources
        new_feature = None

    # Close the data sources
    dataSource = None
    output_ds = None
    file_data = read_file_as_bytes(output_pdf)
    os.remove(output_pdf)
    os.remove(temp_geojson_file)
    return file_data

def create_kmz_from_geojson(geojson_data, car_code):
    output_kmz = f'/tmp/{car_code}.kmz'
    # Create a KML object
    kml = simplekml.Kml()

    # Iterate through features and style them
    for feature in geojson_data['features']:
        cod_tema = feature['properties'].get('cod_tema')
        style = get_style_cod_theme(cod_tema)

        # Extract geometry and properties
        geom = feature['geometry']
        properties = feature['properties']

        # Create a KML placemark for the feature
        placemark = kml.newmultigeometry(name=cod_tema)
        for coords in geom['coordinates']:
            if geom['type'] == 'Polygon':
                placemark.newpolygon(outerboundaryis=coords)
            elif geom['type'] == 'MultiPolygon':
                for polygon_coords in coords:
                    placemark.newpolygon(outerboundaryis=polygon_coords)

        # Apply style to the placemark
        color = color_name_to_hex_with_alpha(
            style['color'],
            style.get("opacity",0.5),
            invert_alpha=True,
            bgr=True
        ).upper()

        fillColor = style.get('fillColor', 'none')
        if fillColor != 'none':
            fillColor = color_name_to_hex_with_alpha(
                fillColor,
                style.get("fillOpacity",0.5),
                invert_alpha=True,
                bgr=True
            ).upper()

        placemark.style.linestyle.color = color.replace("#","")
        placemark.style.linestyle.width = style.get('weight', 1)
        if fillColor != 'none':
            placemark.style.polystyle.color = fillColor.replace("#","")

        # Add attributes as description
        description = "<br>".join(f"<b>{key}</b>: {value}" for key, value in properties.items())
        placemark.description = description

    # Save KML to a KMZ file
    kml.savekmz(output_kmz)
    file_data = read_file_as_bytes(output_kmz)
    os.remove(output_kmz)
    return file_data