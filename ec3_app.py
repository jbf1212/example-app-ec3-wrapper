import pandas as pd
import streamlit as st
import plotly.express as px
import numpy as np
import pydeck as pdk
from PIL import Image

from streamlit_chart_container import chart_container

from ec3 import EC3Materials

ec3_token = st.secrets["EC3_TOKEN"]

# @st.cache_data
# def remove_outliers(df, n_std, col_names):
#     """
#     Remove extreme outliers that are more than n_std standard deviations away from mean
#     """
#     for col in df[col_names]:
#         mean = df[col].mean()
#         sd = df[col].std()

#         df = df[(df[col] <= mean + (n_std * sd))]

#     return df

def remove_outliers(df, col_names):
    """
    Remove extreme outliers based on IQR method
    """
    q1 = df[col_names].quantile(0.25)
    q3 = df[col_names].quantile(0.75)
    iqr = q3 - q1

    df = df[~((df[col_names] < (q1 - 1.5 * iqr)) |(df[col_names] > (q3 + 1.5 * iqr))).any(axis=1)]

    return df


def is_valid_postal_code(postal_code):
    if len(postal_code) != 5:
        return False
    try:
        int(postal_code)
        return True
    except ValueError:
        return False


######################################
# App title and description
######################################
col1, col2, col3 = st.columns(3)
image = Image.open("./images/ec3_wrapper_logo.png")
col2.image(image, width=250)

st.title("EC3 Concrete Carbon Comparison")
st.markdown(
    "**Compare GWP values of concretes within certain proximity to US postal code**"
)

######################################
# Have user enter data
######################################
with st.form(key="concrete_query"):
    with st.sidebar.form(key="Form1"):
        st.markdown(
            "This app is a demonstration of using the ec3-python-wrapper for querying the EC3 database."
        )

        link = f'<a href="https://github.com/jbf1212/ec3-python-wrapper" style="color:#4A987F;">Link to ec3-python-wrapper repo</a>'
        st.markdown(link, unsafe_allow_html=True)
        st.markdown("***")

        postal_code = st.text_input("Enter a 5-digit postal code")
        miles = st.number_input(
            "Miles from region provided", min_value=0, max_value=500, value=20, step=10
        )
        strength_range = st.slider(
            label="Set range for concrete strength in psi",
            min_value=0,
            max_value=12000,
            value=(2000, 8000),
            step=100,
        )
        weight_type = st.checkbox("Lightweight")
        num_of_materials = st.number_input("Maximum number of concretes", value=500)
        return_all_bool = st.checkbox("Return all matches")
        st.markdown(
            '<span style="color:#094D6C;"> Returning all matches will ignore the maximum set.</span>',
            unsafe_allow_html=True,
        )
        submitted = st.form_submit_button(label="Search Concrete Materials 🔎")
        st.markdown(
            '<span style="color:#094D6C;"> Note! Queries may take several minutes to run depending on the number of materials being returned.</span>',
            unsafe_allow_html=True,
        )

strength_min = str(strength_range[0]) + " psi"
strength_max = str(strength_range[1]) + " psi"
######################################
# Make request for material data
######################################
if submitted:
    if not is_valid_postal_code(postal_code):
        st.warning(
            "Invalid postal code. Please enter a 5-digit code with integers only."
        )
        st.stop()
    else:
        postal_int = int(postal_code)

    miles_str = str(miles) + " mi"

    ec3_materials = EC3Materials(bearer_token=ec3_token, ssl_verify=False)

    # Conduct a search of normal weights concrete mixes between min and max strengths
    mat_filters = [
        {
        "field": "concrete_compressive_strength_at_28d",
        "op": "gt",
        "arg": strength_min
        },
        {
        "field": "concrete_compressive_strength_at_28d",
        "op": "lt",
        "arg": strength_max
        },
        {
        "field": "lightweight",
        "op": "exact",
        "arg": weight_type
        }
    ]

    # ec3_materials.return_fields = [
    #     "id",
    #     "open_xpd_uuid",
    #     "concrete_compressive_strength_28d",
    #     "gwp",
    #     "name",
    #     "plant_or_group",
    #     # "plant_or_group__owned_by__name"
    # ]

    if not return_all_bool:
        ec3_materials.max_records = num_of_materials
    ec3_materials.only_valid = True

    # NOTE The following query may take a couple minutes to return all responses
    with st.spinner("Searching for materials..."):
        mat_records = ec3_materials.get_materials_within_region_mf("ReadyMix", mat_filters, postal_int, plant_distance=miles_str, return_all=return_all_bool)

    # Warn user if no records found within radius
    if len(mat_records) == 0:
        st.warning('No material records found within region. Try adjusting distance or other parameters.', icon="⚠️")
        st.stop()

    ######################################
    # Clean and convert the data
    ######################################
    # The following code will convert all the compressive strengths to the same units and round to the nearest 500 psi
    mpa_to_psi = 145.03773773  # conversion for megapascal

    missing_location_data = []

    converted_records = []

    for rec in mat_records:
        new_dict = {}
        split_strength = rec["concrete_compressive_strength_28d"].split()
        if split_strength[1] == "MPa":
            conc_strength = float(split_strength[0]) * mpa_to_psi
        elif split_strength[1] == "psi":
            conc_strength = float(split_strength[0])
        elif split_strength[1] == "ksi":
            conc_strength = float(split_strength[0]) * 1000
        else:
            continue  # unknown unit

        rounded_strength = int(round(conc_strength / 500.0) * 500.0)

        plant_owner_name = rec["plant_or_group"]["owned_by"]["name"]
        plant_local_name = rec["plant_or_group"]["name"]

        if not plant_owner_name:
            plant_owner_name = "Unknown"
        elif not isinstance(plant_owner_name, str):
            plant_owner_name = "Unknown"

        if not plant_local_name:
            plant_local_name = "Unknown"
        elif not isinstance(plant_local_name, str):
            plant_local_name = "Unknown"

        try:
            plant_lat = rec["plant_or_group"]["latitude"]
            plant_long = rec["plant_or_group"]["longitude"]
        except KeyError:
            if plant_local_name not in missing_location_data:
                st.warning("WARNING: No location data provided for the following plant : " + plant_local_name)
                missing_location_data.append(plant_local_name)
            continue

        new_dict["Compressive Strength [psi]"] = rounded_strength
        new_dict["GWP [kgCO2e/m³]"] = float(rec["gwp"].split()[0])
        new_dict["Plant_Owner"] = plant_owner_name
        new_dict["Plant_Name"] = plant_local_name
        new_dict["Product Name"] = rec["name"]
        new_dict["Latitude"] = plant_lat
        new_dict["Longitude"] = plant_long
        converted_records.append(new_dict)

    df = pd.DataFrame(converted_records)
    data_length_prior = len(df.index)
    df = remove_outliers(df, ["GWP [kgCO2e/m³]"])
    data_length_post = len(df.index)

    st.markdown("***")
    st.markdown(
        "_The following chart includes data from **{}** concrete materials._".format(
            data_length_post
        )
    )
    st.markdown(
        "_**{}** material records were deemed to be outliers and not included in data below. Material records are considered outliers based on the Interquartile Range (IQR) method._".format(
            data_length_prior - data_length_post
        )
    )

    ######################################
    ## Create simple box plot
    ######################################
    fig = px.box(
        df,
        x="Compressive Strength [psi]",
        y="GWP [kgCO2e/m³]",
        color_discrete_sequence=["steelblue"],
        hover_data=["Product Name", "Plant_Owner", "Plant_Name"],
    )

    with chart_container(df):
        st.write("**GWP by Compressive Strength**")
        st.plotly_chart(fig, theme="streamlit")

    st.markdown("***")

    ######################################
    ## Create map plot
    ######################################
    map_df = (
        df.groupby(["Plant_Owner", "Plant_Name", "Latitude", "Longitude"])["Plant_Name"]
        .count()
        .reset_index(name="EPD_Count")
    )

    # Define a layer to display on a map
    mix_layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        pickable=True,
        opacity=0.3,
        stroked=True,
        filled=True,
        radius_scale=10,
        radius_min_pixels=5,
        radius_max_pixels=60,
        line_width_min_pixels=1,
        get_position=["Longitude", "Latitude"],
        get_radius="EPD_Count",
        get_fill_color=[74, 152, 127],
        get_line_color=[9, 77, 108],
    )

    # Set view state
    # view_state = pdk.data_utils.compute_view(points=map_df[["Latitude", "Longitude"]], view_proportion=0.9) #This should work, but is not
    mean_lat = map_df.loc[:, "Latitude"].mean()
    mean_long = map_df.loc[:, "Longitude"].mean()
    view_state = pdk.ViewState(latitude=mean_lat, longitude=mean_long, zoom=8)

    # Render map
    r = pdk.Deck(
        layers=[mix_layer],
        initial_view_state=view_state,
        tooltip={"text": "{Plant_Owner}\n{Plant_Name}\nEPD Count: {EPD_Count}"},
        map_style="mapbox://styles/mapbox/light-v10",
    )

    mix_map = st.pydeck_chart(r)

    ######################################
    ## Plot counts
    ######################################
    # Hide index column in dataframe
    hide_table_row_index = """
            <style>
            thead tr th:first-child {display:none}
            tbody th {display:none}
            </style>
            """
    st.markdown(hide_table_row_index, unsafe_allow_html=True)
    st.table(map_df[["Plant_Owner", "Plant_Name", "EPD_Count"]].sort_values("EPD_Count", ascending=False))

    # st.markdown("***")

    # ######################################
    # ## Create Treemap
    # ######################################
    # grouped_df = df.groupby(["Plant"]).size().reset_index(name="count")
    # fig2 = px.treemap(
    #     grouped_df,
    #     path=["Plant"],
    #     values="count",
    #     color="Plant",
    #     color_continuous_scale="tempo",
    #     title="Material Count by Plant",
    # )
    # st.plotly_chart(fig2, theme="streamlit")
    # st.markdown(
    #     "_Proportions above will not be representative of availability unless 'Return all macthes' is selected._"
    # )
