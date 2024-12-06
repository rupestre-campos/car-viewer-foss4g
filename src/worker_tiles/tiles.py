import subprocess
import os

skip_geojsonseq_creation = False

# Database connection parameters
dbname = os.getenv("DBNAME")
user = os.getenv("USER")
password = os.getenv("PASSWORD")
host = os.getenv("HOST")

# Output file names
data_folder = "../data/"
final_output_file = os.path.join(data_folder,"area_imovel.geojsonseq")
pmtiles_file = os.path.join(data_folder, "area_imovel.pmtiles")

# Remove the final output file if it exists
if os.path.exists(final_output_file) and skip_geojsonseq_creation==False:
    os.remove(final_output_file)

os.makedirs(data_folder, exist_ok=True)
# Loop through each state and append to the final output file

if not skip_geojsonseq_creation:
    # Assuming schema names are the state abbreviations in lowercase
    table = f'public.area_imovel'

    # Construct the ogr2ogr command
    ogr2ogr_cmd = [
        "ogr2ogr",
        "-f", "GeoJSONSeq",
        #"-t_srs", "EPSG:4326",
        "-quiet",
        "-sql", f"SELECT car_code, geom, properties->>'ind_status' ind_status from {table} where active = 1",
        final_output_file,
        f"PG:dbname={dbname} user={user} password={password} host={host}",
        table,
    ]

    # Execute the ogr2ogr command
    subprocess.run(ogr2ogr_cmd, check=True)

# Construct the tippecanoe command
tippecanoe_cmd = [
    "tippecanoe",
    "-z16",
    "-Z0",
    "-ae",
    "-d12",
    "-D10",
    "-m9",
    "--detect-shared-borders",
    "--grid-low-zooms",
    "--force",
    "--include=car_code",
    "--include=ind_status",
    "--projection=EPSG:4326",
    "--read-parallel",
    "--coalesce-densest-as-needed",
    "--coalesce-smallest-as-needed",
    "-o", pmtiles_file,
    "-l", "area_imovel",
    final_output_file
]

# Execute the tippecanoe command
print(f"Executing: {' '.join(tippecanoe_cmd)}")
subprocess.run(tippecanoe_cmd, check=True)

os.remove(final_output_file)

print("All tasks completed successfully.")
