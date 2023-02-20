import pandas as pd
import streamlit as st
import plotly.express as px
import numpy as np
from PIL import Image

from ec3 import EC3Materials

ec3_token = st.secrets["EC3_TOKEN"]

# NOTE Not caching since I want data to refresh when user resubmits query
# @st.cache
def load_mat_data(mat_obj, param_dict, postal_code, plant_dist, return_all_bool):
    mat_records = mat_obj.get_materials_within_region(
        postal_code,
        plant_distance=plant_dist,
        return_all=return_all_bool,
        params=param_dict,
    )
    return mat_records


# @st.cache
def remove_outliers(df, n_std, col_names):
    """
    Remove extreme outliers that are more than n_std standard deviations away from mean
    """
    for col in df[col_names]:
        mean = df[col].mean()
        sd = df[col].std()

        df = df[(df[col] <= mean + (n_std * sd))]

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
            "Miles from region provided", min_value=0, max_value=200, value=10, step=1
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
            '<span style="color:#094D6C;"> Returning all matches will ignore the maximum set. *</span>',
            unsafe_allow_html=True,
        )
        submitted = st.form_submit_button(label="Search Concrete Materials 🔎")
        st.markdown(
            '<span style="color:#094D6C;"> Note! Queries may take several minutes to run depending on the number of materials being returned. *</span>',
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

    # Conduct a search of normal weights concrete mixes between 2000 psi and 9000 psi from plants in NY state
    mat_param_dict = {
        "product_classes": {"EC3": "Concrete >> ReadyMix"},
        "lightweight": weight_type,
        "concrete_compressive_strength_at_28d__gt": strength_min,
        "concrete_compressive_strength_at_28d__lt": strength_max,
    }

    ec3_materials.return_fields = [
        "id",
        "concrete_compressive_strength_28d",
        "gwp",
        "plant_or_group",
    ]
    if not return_all_bool:
        ec3_materials.max_records = num_of_materials
    ec3_materials.only_valid = True

    # NOTE The following query may take a couple minutes to return all responses

    mat_records = load_mat_data(
        ec3_materials, mat_param_dict, postal_int, miles_str, return_all_bool
    )

    ######################################
    # Clean and convert the data
    ######################################
    # The following code will convert all the compressive strengths to the same units and round to the nearest 500 psi
    mpa_to_psi = 145.03773773  # conversion for megapascal

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

        plant_name = rec["plant_or_group"]["owned_by"]["name"]
        if not plant_name:
            plant_name = "Unknown"
        elif not isinstance(plant_name, str):
            plant_name = "Unknown"

        new_dict["Compressive Strength [psi]"] = rounded_strength
        new_dict["GWP [kgCO2e]"] = float(rec["gwp"].split()[0])
        new_dict["Plant"] = plant_name
        converted_records.append(new_dict)

    df = pd.DataFrame(converted_records)
    df = remove_outliers(df, 3, ["GWP [kgCO2e]"])

    st.markdown("***")
    st.markdown(
        "_The following chart includes data from **{}** concrete materials. Extreme outliers may be removed from dataset_".format(
            len(df.index)
        )
    )

    ## Create simple plotly plot ###
    fig = px.box(
        df,
        x="Compressive Strength [psi]",
        y="GWP [kgCO2e]",
        color_discrete_sequence=["steelblue"],
    )
    st.plotly_chart(fig, theme="streamlit")

    st.markdown("***")
    ## Create Treemap ###
    grouped_df = df.groupby(["Plant"]).size().reset_index(name="count")
    fig2 = px.treemap(
        grouped_df,
        path=["Plant"],
        values="count",
        color="Plant",
        color_continuous_scale="tempo",
        title="Material Count by Plant",
    )
    st.plotly_chart(fig2, theme="streamlit")
    st.markdown(
        "_Proportions above will not be representative of availability uness 'Return all macthes' is selected._"
    )
