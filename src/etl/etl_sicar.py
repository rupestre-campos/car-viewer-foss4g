import os
import zipfile
from pathlib import Path
import json
import psycopg2
from datetime import datetime
from psycopg2.extras import Json, execute_values
from psycopg2 import sql
from uuid_extensions import uuid7str
from SICAR import Sicar, Polygon, State
from osgeo import ogr
import psutil
import hashlib
import random
import time
from random_user_agent.user_agent import UserAgent
from random_user_agent.params import SoftwareName, OperatingSystem
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import Manager

out_root_folder = os.getenv("OUT_ROOT_FOLDER", "/tmp")
max_memory_percent_to_use = float(os.getenv("MAX_MEMORY_PERCENT_TO_USE", 0.01))
max_batch_size = int(os.getenv("MAX_BATCH_SIZE", 100))
timeout = int(os.getenv("TIMEOUT", 25))
chunk_size = int(os.getenv("CHUNK_SIZE", 5 * 1024))
use_proxy = os.getenv("USE_PROXY", "True").lower() in ("true", "1", "yes")
ip_proxy = os.getenv("IP_PROXY", "http://127.0.0.1:3128")
use_http2 = os.getenv("USE_HTTP2", "True").lower() in ("true", "1", "yes")
min_download_rate = int(os.getenv("MIN_DOWNLOAD_RATE", 25))
max_workers = int(os.getenv("MAX_WORKERS", 1))
overwrite = os.getenv("OVERWRITE", "False").lower() in ("true", "1", "yes")

proxy = None
if use_proxy:
    proxy = ip_proxy
print(use_proxy, proxy)

states = list(State)
themes = list(Polygon)

def connect_db():
    conn = psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT")
    )
    return conn

def connect_default_db():
    conn = psycopg2.connect(
        dbname="postgres",
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT")
    )
    return conn

class CycleVariable:
    def __init__(self, values):
        """Initialize with a list of values to randomly choose from."""
        if not values:
            raise ValueError("Values list cannot be empty.")
        self.values = values

    def __call__(self):
        """Return a random value from the list."""
        value = random.choice(self.values)
        print(value)
        return value

software_names = [SoftwareName.CHROME.value, SoftwareName.FIREFOX.value, SoftwareName.EDGE.value, SoftwareName.SAFARI.value]
operating_systems = [OperatingSystem.WINDOWS.value, OperatingSystem.LINUX.value, OperatingSystem.MACOS.value]
user_agent_rotator = UserAgent(software_names=software_names, operating_systems=operating_systems, limit=100)

user_agent = CycleVariable([x.get("user_agent") for x in user_agent_rotator.get_user_agents()])

def get_headers():
    return {
        "User-Agent": user_agent(),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Accept": "*/*",
        "Referer": "https://consultapublica.car.gov.br/publico/estados/downloads",
        "Host": "consultapublica.car.gov.br",
        "Priority": "u=0",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

def extract_zip_to_folder(zip_path, extract_to_folder):
    zip_path = Path(zip_path)
    extract_to_folder = Path(extract_to_folder)
    extract_to_folder.mkdir(parents=True, exist_ok=True)
    zip_extracted = False
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_to_folder)
        zip_extracted = True
    except Exception as e:
        print(e)
    finally:
        try:
            os.remove(zip_path)
        except Exception as e:
            print(e)
    return zip_extracted

def create_statistics_table():
    conn = connect_db()
    cursor = conn.cursor()

    table_query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS car_statistics (
            id UUID PRIMARY KEY,
            state_code VARCHAR(2),
            layer TEXT,
            release_date DATE,
            created_at DATE DEFAULT CURRENT_DATE,
            count_active_features INT,
            count_new_features INT,
            count_updated_features INT,
            count_parsed_features INT
        );
    """
    )
    cursor.execute(table_query)
    create_state_code_index_query = sql.SQL("""
        CREATE INDEX IF NOT EXISTS car_statistics_state
        ON car_statistics (state_code);
    """)
    cursor.execute(create_state_code_index_query)

    conn.commit()
    cursor.close()
    conn.close()


def create_database():
    conn = connect_default_db()
    conn.autocommit = True
    cursor = conn.cursor()

    db_name = os.getenv("POSTGRES_DB")
    try:
        cursor.execute(f"CREATE DATABASE {db_name};")
        print(f"Database '{db_name}' created successfully.")
    except Exception as e:
        print(e)
    finally:
        cursor.close()
        conn.close()

    try:
        conn = connect_db()
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(f"CREATE EXTENSION postgis;")
    except Exception as e:
        print(e)
    finally:
        cursor.close()
        conn.close()

def main_table_structure(table_name):
    return sql.SQL("""
        CREATE TABLE IF NOT EXISTS {table} (
            id UUID,
            car_code TEXT,
            state_code VARCHAR(2),
            release_date DATE,
            created_at DATE DEFAULT CURRENT_DATE,
            feature_hash UUID,
            geom_hash UUID,
            properties_hash UUID,
            geom geometry(geometry, 4326),
            properties JSONB,
            PRIMARY KEY (id, state_code)
        ) PARTITION BY LIST (state_code);
    """).format(
        table=sql.Identifier(table_name)
    )

def partition_table_structure(table_name, value_partition):
    return sql.SQL("""
        CREATE TABLE IF NOT EXISTS {partition} PARTITION OF {table} FOR VALUES IN (%s) ;
    """).format(
        partition=sql.Identifier(f"{table_name}_{value_partition}"),
        table=sql.Identifier(table_name),
    )

def create_partition_and_table( state, theme):
    conn = connect_db()
    cursor = conn.cursor()
    table_query = main_table_structure(theme.lower())
    cursor.execute(table_query)
    partition_query = partition_table_structure(theme.lower(), state.lower())
    cursor.execute(partition_query, [state.upper()])

    conn.commit()
    cursor.close()
    conn.close()

def create_indices(state, theme):
    conn = connect_db()
    cursor = conn.cursor()
    create_spatial_index_query = sql.SQL("""
        CREATE INDEX IF NOT EXISTS {index_geom}
        ON {table}
        USING GIST (geom);
    """).format(
        index_geom=sql.Identifier(f"{theme.lower()}_{state.lower()}_geom_idx"),
        table=sql.Identifier(f"{theme.lower()}_{state.lower()}")
    )
    cursor.execute(create_spatial_index_query)

    create_cod_imovel_index_query = sql.SQL("""
        CREATE INDEX IF NOT EXISTS {index_cod_imovel}
        ON {table} (car_code);
    """).format(
        index_cod_imovel=sql.Identifier(f"{theme.lower()}_{state.lower()}_cod_imovel_idx"),
        table=sql.Identifier(f"{theme.lower()}_{state.lower()}")
    )
    cursor.execute(create_cod_imovel_index_query)

    # Index on release_date column
    create_release_date_index_query = sql.SQL("""
        CREATE INDEX IF NOT EXISTS {index_release_date}
        ON {table} (release_date);
    """).format(
        index_release_date=sql.Identifier(f"{theme.lower()}_{state.lower()}_release_date_idx"),
        table=sql.Identifier(f"{theme.lower()}_{state.lower()}")
    )
    cursor.execute(create_release_date_index_query)
    conn.commit()
    cursor.close()
    conn.close()

def vacuum(theme, state):
    conn = connect_db()
    conn.autocommit = True
    cursor = conn.cursor()
    vacuum_query = sql.SQL("""
        VACUUM ANALYSE {table};""").format(
        table=sql.Identifier(f"{theme.lower()}_{state.lower()}")

    )
    cursor.execute(vacuum_query)
    cursor.close()
    conn.close()

def insert_statistics_data(feature_count, release_date, layer, state_code):
    conn = connect_db()
    cursor = conn.cursor()

    # Query to calculate active, new, and updated features
    count_query = sql.SQL("""
        SELECT COUNT(1) FROM {table} WHERE state_code = %s AND active = 1
    """).format(table=sql.Identifier(layer.lower()))

    # Execute the query with parameters supplied separately to avoid formatting issues
    cursor.execute(count_query, (state_code.upper(), ))

    counts = cursor.fetchone()

    # Prepare the data for insertion
    insert_query = sql.SQL("""
        INSERT INTO car_statistics (
            id,
            state_code,
            layer,
            release_date,
            count_active_features,
            count_new_features,
            count_updated_features,
            count_parsed_features
        )
        VALUES %s
    """)

    values = [
        (
            uuid7str(),
            state_code.upper(),
            layer,
            release_date,
            counts[0],  # count active features
            0, # todo count new features
            0, # todo count updated features
            feature_count
        )
    ]

    # Insert statistics data
    execute_values(cursor, insert_query.as_string(conn), values)

    conn.commit()
    cursor.close()
    conn.close()

def insert_data_batch(state, theme, batch, release_date):
    conn = connect_db()
    cursor = conn.cursor()
    # Collect all car codes from the batch
    table_name = f"{theme.lower()}_temp"
    # Filter batch to include only new records
    new_records = [
        (
            uuid7str(),
            feature["properties"]["cod_imovel"],
            state.upper(),
            release_date,
            feature["hash"],
            feature["geom_hash"],
            feature["properties_hash"],
            feature["geometry"],
            Json(feature["properties"])
        )
        for feature in batch
    ]

    # Insert new records
    if new_records:
        insert_query = sql.SQL("""
            INSERT INTO {table} (
                id,
                car_code,
                state_code,
                release_date,
                feature_hash,
                geom_hash,
                properties_hash,
                geom,
                properties)
            VALUES %s
        """).format(
            table=sql.Identifier(table_name)
        )
        execute_values(cursor, insert_query.as_string(conn), new_records)
        conn.commit()

    cursor.close()
    conn.close()
def switch_active_version(state, theme, release_date):
    conn = connect_db()
    cursor = conn.cursor()

    table_name = f"{theme.lower()}_{state.lower()}"
    temp_table_name = f"{theme.lower()}_temp_{state.lower()}"
    parent_table_name = theme.lower()  # Assuming all partitions belong to this table
    temp_parent_table_name = f"{theme.lower()}_temp"

    done = False
    try:
        cursor.execute(sql.SQL("BEGIN;"))

        # Detach the temp table from its parent (if it is already attached)
        cursor.execute(sql.SQL("ALTER TABLE {temp_parent} DETACH PARTITION {temp_table};").format(
            temp_parent=sql.Identifier(parent_table_name),
            temp_table=sql.Identifier(table_name)
        ))
        # Detach the temp table from its parent (if it is already attached)
        cursor.execute(sql.SQL("ALTER TABLE {temp_parent} DETACH PARTITION {temp_table};").format(
            temp_parent=sql.Identifier(temp_parent_table_name),
            temp_table=sql.Identifier(temp_table_name)
        ))
        # Drop the existing old partition table (you can truncate instead if you want to preserve structure)
        cursor.execute(sql.SQL("DROP TABLE IF EXISTS {table} CASCADE;").format(
            table=sql.Identifier(table_name)
        ))

        # Rename the temp table to become the active one
        cursor.execute(sql.SQL("ALTER TABLE {temp_table} RENAME TO {table};").format(
            temp_table=sql.Identifier(temp_table_name),
            table=sql.Identifier(table_name)
        ))

        # Attach the newly renamed table back as a partition
        # You MUST know the partition range or list constraint here:
        cursor.execute(sql.SQL("""
            ALTER TABLE {parent} ATTACH PARTITION {table}
            FOR VALUES IN (%s);
        """).format(
            parent=sql.Identifier(parent_table_name),
            table=sql.Identifier(table_name)
        ), (state.upper(),))  # assuming partitioning is LIST(state)

        cursor.execute(sql.SQL("COMMIT;"))
        done = True

    except Exception as e:
        conn.rollback()
        print(f"An error occurred on switch versions: {e}")

    finally:
        cursor.close()
        conn.close()
    return done


def read_shapefile(shapefile_path):
    # Open the shapefile using OGR
    driver = ogr.GetDriverByName("ESRI Shapefile")
    datasource = driver.Open(shapefile_path, 0)  # 0 means read-only

    # Check if the datasource was opened successfully
    if datasource is None:
        raise FileNotFoundError(f"Could not open {shapefile_path}")

    # Get the first (and usually only) layer
    layer = datasource.GetLayer()

    # Iterate over each feature in the layer
    for feature in layer:
        try:
            # Convert the feature's geometry to GeoJSON
            geom = feature.GetGeometryRef()

            if geom is None:
                continue

            yield from process_geometry(feature, geom)

        except Exception as e:
            print(f"Error processing feature: {e}")
            continue


def process_geometry(feature, geom):
    # Export geometry to WKB
    wkb = geom.ExportToWkb()
    object_size = len(wkb)
    geom_hash = hashlib.md5(wkb).hexdigest()

    # Create a GeoJSON-like dictionary for the feature
    properties = {}

    # Add properties to the dictionary
    for field_name in feature.keys():
        properties[field_name] = feature.GetField(field_name)
    properties_str = json.dumps(properties, sort_keys=True)
    properties_str_encode = properties_str.encode("utf-8")
    object_size += len(properties_str_encode)

    properties_hash = hashlib.md5(properties_str_encode).hexdigest()
    feature_hash = hashlib.md5(f"{geom_hash}-{properties_hash}".encode("utf-8")).hexdigest()

    yield {
        "geometry": wkb,
        "properties": properties,
        "size": object_size,
        "hash": feature_hash,
        "geom_hash": geom_hash,
        "properties_hash": properties_hash
    }

def delete_temp_table(state, theme):
    conn = connect_db()
    cursor = conn.cursor()
    table_name = f"{theme.lower()}_temp_{state.lower()}"
    # Use a single query with a transaction block to update the active status
    drop_temp_table = sql.SQL("""
        DROP TABLE IF EXISTS {table};
    """).format(
        table=sql.Identifier(table_name)
    )

    try:
        # Execute the transaction
        cursor.execute(drop_temp_table, (table_name,))

        # Commit the transaction
        conn.commit()
    except Exception as e:
        # If an error occurs, rollback the transaction
        conn.rollback()
        print(f"An error occurred: {e}")
    finally:
        # Always close the cursor
        cursor.close()
        conn.close()


def create_temp_table(state, theme):
    conn = connect_db()
    cursor = conn.cursor()
    table_name = f"{theme.lower()}_temp"
    table_query = main_table_structure(table_name)

    partition_query = partition_table_structure(table_name, state.lower())
    try:
        # Execute the transaction
        cursor.execute(table_query)
        conn.commit()
        cursor.execute(partition_query, (state.upper(),))

        # Commit the transaction
        conn.commit()
        print(f"temp table {table_name} created")
    except Exception as e:
        # If an error occurs, rollback the transaction
        conn.rollback()
        print(f"An error occurred: {e}")
    finally:
        # Always close the cursor
        cursor.close()
        conn.close()

def process_shapefiles_and_save_to_db(extracted_folder, state, theme, release_date):

    # Get total available RAM in bytes and divide by 10 for batch size
    max_batch_size_bytes = psutil.virtual_memory().available * max_memory_percent_to_use

    extracted_folder = Path(extracted_folder)
    try:
        shapefiles = list(extracted_folder.glob("**/*.shp"))
        feature_count = 0
        print("deleting temp table")
        delete_temp_table(state, theme)
        print("creating temp table")
        create_temp_table(state, theme)

        for shapefile in shapefiles:
            print("inserting into database...")
            batch_size_bytes = 0
            batch = []

            for feature in read_shapefile(shapefile.as_posix()):
                batch.append(feature)
                batch_size_bytes += feature["size"]
                feature_count += 1

                if batch_size_bytes >= max_batch_size_bytes or len(batch)>=max_batch_size:
                    # Submit a batch for insertion
                    insert_data_batch(state, theme, batch, release_date)
                    batch = []
                    batch_size_bytes = 0

            # Insert any remaining features in the batch
            if batch:
                insert_data_batch(state, theme, batch, release_date)

            # Clean up the shapefile and its associated files
            for ext in [".shp", ".prj", ".shx", ".dbf", ".fix"]:
                try:
                    os.remove(shapefile.with_suffix(ext))
                except Exception as e:
                    print(f"Error removing file {shapefile.with_suffix(ext)}: {e}")


        # Create indices
        print("Creating indexes")
        create_indices(state, theme)
        # insert statistics
        print("Inserting from temp to real table")
        done = switch_active_version(state, theme, release_date)
        if done:
            insert_statistics_data(feature_count, release_date, theme, state)
            print("Vacuuming")
            vacuum(theme, state)
    except Exception as e:
        print(f"Error inserting shapefile: {e}")
    finally:
        for file in list(extracted_folder.glob("**/*")):
            try:
                os.remove(file)
            except Exception as e:
                print(f"Could not remove file: {e}")


def get_car( state, theme, out_folder):
    result = False
    car = Sicar(
        use_http2=use_http2,
        proxy=proxy,
        read_timeout=timeout,
        connect_timeout=timeout,
        headers=get_headers(),
    )
    while result == False:
        try:
            result = car.download_state(
                state=state,
                polygon=theme,
                folder=out_folder,
                tries=1,
                debug=True,
                chunk_size=chunk_size,
                overwrite=overwrite,
                min_download_rate=min_download_rate
            )

        except Exception as e:
            print(f"Error in download {state} {theme}: {e}")
            time.sleep(random.random() + random.random())
            car = Sicar(
                use_http2=use_http2,
                proxy=proxy,
                read_timeout=timeout,
                connect_timeout=timeout,
                headers=get_headers(),
            )

    return result

def check_data_exists( state, layer, release_date):
    conn = connect_db()
    cursor = conn.cursor()
    query = """
        SELECT COUNT(1)
        FROM car_statistics
        WHERE state_code = %s AND layer = %s AND release_date = %s;
    """

    cursor.execute(query, (state.upper(), layer, release_date))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    return count > 0

def clean_orphan_rows(state, theme, release_date):
    conn = connect_db()
    cursor = conn.cursor()

    # Format the table name dynamically based on the theme and state
    table_name = theme.lower()
    # Prepare the SQL query to check if the table exists and has data for the given release_date
    check_query = sql.SQL("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_tables
            WHERE schemaname = 'public' AND tablename = %s
        )
    """)

    try:
        # Execute the check query
        cursor.execute(check_query, (table_name,))
        table_exists = cursor.fetchone()

        if table_exists[0]:
            # Table exists and there is data for the specified release_date, proceed with deletion
            delete_query = sql.SQL("""
                DELETE FROM {table}
                WHERE release_date = %s AND state_code = %s
            """).format(table=sql.Identifier(table_name))

            cursor.execute(delete_query, (release_date, state,))
            conn.commit()
            print(f"Deleted rows from {table_name} where release_date is {release_date}")
        else:
            print("No deletion performed: either table does not exist or no data for the specified release_date.")

    except Exception as e:
        conn.rollback()  # Rollback the transaction in case of an error
        print(f"Failed to execute deletion: {e}")

    finally:
        cursor.close()
        conn.close()

def process_state_theme_pair(state, theme, release_dates, done_list):
    try:
        if not state in release_dates:
            done_list["undone"].append((state, theme))
            return

        release_date = datetime.strptime(release_dates[state], "%d/%m/%Y").strftime("%Y-%m-%d")
        check_data_already = check_data_exists(state, theme, release_date)

        #if not check_data_already:
        #clean_orphan_rows(state, theme, release_date)
        if check_data_already:
            done_list["done"].append((state, theme))
            print(f"Data already exists for {state}, {theme}")
            return

        state_folder = os.path.join(out_root_folder, state)
        out_folder = os.path.join(state_folder, theme)

        os.makedirs(out_folder, exist_ok=True)

        result = get_car(state, theme, out_folder)
        if not result:
            done_list["undone"].append((state, theme))
            return

        result_path = result.as_posix()

        print("Extracting zip")
        extracted_zip = extract_zip_to_folder(result_path, out_folder)
        if not extracted_zip:
            raise Exception("zip not extractable")

        print("Creating schema and table")
        create_partition_and_table(state, theme)
        print("Processing shapefile")
        process_shapefiles_and_save_to_db(out_folder, state, theme, release_date)
        print(f"Done processing {state}, {theme}")
        done_list["done"].append((state, theme))
    except Exception as e:
        print(f"Error processing {state}, {theme}: {e}")
        done_list["undone"].append((state, theme))

def main():
    car = Sicar(
        use_http2=use_http2,
        proxy=proxy,
        read_timeout=timeout,
        connect_timeout=timeout,
        headers=get_headers())

    create_database()
    create_statistics_table()
    release_dates = car.get_release_dates()

    # Use a Manager to create a shared done_list dictionary
    with Manager() as manager:
        done_list = manager.dict()
        done_list["undone"] = manager.list()
        done_list["done"] = manager.list()

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for state in states:
                for theme in themes:
                    print(f"Submitting task for {state}, {theme}")
                    futures.append(executor.submit(process_state_theme_pair, state, theme, release_dates, done_list))

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error during processing: {e}")

        if len(done_list["undone"]) == 0:
            time.sleep(3600)
            return True
        time.sleep(60)
        return False

if __name__=="__main__":
    main()
