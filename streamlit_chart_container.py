from contextlib import contextmanager
from typing import Generator, Sequence

import pandas as pd
import streamlit as st


@st.cache
def _to_csv(data: pd.DataFrame):
    return data.to_csv().encode("utf-8")

_SUPPORTED_EXPORTS = {
    "CSV": {
        "function": _to_csv,
        "extension": ".csv",
        "mime": "text/csv",
    }
}

_SUPPORTED_EXPORT_KEYS = list(_SUPPORTED_EXPORTS.keys())


@contextmanager
def chart_container(
    data: pd.DataFrame,
    tabs: Sequence[str] = (
        "Chart 📈",
        "Dataframe 📄",
        "Export 📁",
    ),
    export_formats: Sequence[str] = _SUPPORTED_EXPORT_KEYS,
    ) -> Generator:
    """Embed chart in a (chart, data, export, explore) tabs container to let the viewer explore and export its underlying data.

    Args:
        data (pd.DataFrame): Dataframe used in the dataframe tab.
        tabs (Sequence, optional): Tab labels. Defaults to ("Chart 📈", "Dataframe 📄", "Export 📁").
        export_formats (Sequence, optional): Export file formats. Defaults to ("CSV", "Parquet")
    """

    assert all(
        export_format in _SUPPORTED_EXPORTS for export_format in export_formats
    ), f"Input format is not supported, please use one within {_SUPPORTED_EXPORTS.keys()}"

    if "chart_container_widget_key" not in st.session_state:
        st.session_state["chart_container_widget_key"] = 0

    def _get_random_widget_key() -> str:
        st.session_state.chart_container_widget_key += 1
        return st.session_state.chart_container_widget_key

    tab_1, tab_2, tab_3 = st.tabs(tabs)

    with tab_1:
        yield

    with tab_2:
        st.dataframe(data, use_container_width=True)

    with tab_3:
        export_data = data.head(1_000_000)
        for chosen_export_format in export_formats:
            export_utils = _SUPPORTED_EXPORTS[chosen_export_format]
            exporter = export_utils["function"]
            extension = export_utils["extension"]
            st.download_button(
                f"Download data as {extension}",
                data=exporter(export_data),
                file_name="data" + extension,
                mime=export_utils.get("mime"),
                key=_get_random_widget_key(),
            )