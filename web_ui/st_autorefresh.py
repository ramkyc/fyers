# Vendored from streamlit-autorefresh==1.0.1
# Original source: https://github.com/kmcgrady/streamlit-autorefresh
# This code is copied directly into the project to bypass environment issues.

import streamlit as st
from streamlit.components.v1 import html
from streamlit.runtime import get_instance
from streamlit.runtime.scriptrunner import get_script_run_ctx

def st_autorefresh(interval: int, limit: int = 100, key: str = None):
    """
    A component that automatically re-runs the script on a timer.

    Args:
        interval (int): The interval in milliseconds.
        limit (int, optional): The number of times to rerun the script. Defaults to 100.
        key (str, optional): The key for the component. Defaults to None.
    """
    # Get the session ID
    session_id = get_script_run_ctx().session_id
    runtime = get_instance()
    session_info = runtime._session_mgr.get_session_info(session_id)

    # Initialize the session state
    if key not in st.session_state:
        st.session_state[key] = 0

    # Check if the script has been rerun too many times
    if st.session_state[key] >= limit:
        return

    # Increment the rerun count
    st.session_state[key] += 1

    # Create the HTML to rerun the script
    html(
        f"""
        <script>
            const streamlitDoc = window.parent.document;
            const rerunButton = Array.from(
                streamlitDoc.querySelectorAll('.stButton > button')
            ).find(el => el.innerText === 'Rerun');

            setTimeout(() => {{
                rerunButton.click();
            }}, {interval});
        </script>
        """,
        height=0,
        width=0,
    )