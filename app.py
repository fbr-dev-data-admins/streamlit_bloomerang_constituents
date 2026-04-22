"""Streamlit application for Bloomerang constituent data export."""

import logging
import os
import sys
from datetime import date

import pandas as pd
import streamlit as st
import yaml
from dotenv import load_dotenv

from api.bloomerang_client import BloomerangClient, BloomerangAPIError
from transformations.individuals import transform_individuals
from transformations.organizations import transform_organizations
from transformations.exceptions import create_exceptions_dataframe
from utils.excel_writer import df_to_excel_bytes

import streamlit as st

# Temporary debug — remove after confirming
try:
    key = st.secrets.get("BLOOMERANG_API_KEY")
    st.write("Key found:", bool(key), "| First 6 chars:", str(key)[:6] if key else "None")
except Exception as e:
    st.write("st.secrets error:", e)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

load_dotenv()


def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), "config", "config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def filter_by_groups(records: list[dict], excluded_groups: list[str]) -> tuple[list[dict], dict[str, int]]:
    """
    Filter out records that belong to excluded groups.

    Args:
        records: List of constituent records
        excluded_groups: List of group names to exclude (case-insensitive)

    Returns:
        Tuple of (filtered records, dict mapping group name to exclusion count)
    """
    if not excluded_groups:
        return records, {}

    excluded_lower = [g.lower() for g in excluded_groups]
    filtered = []
    exclusion_counts = {}

    for record in records:
        groups_details = record.get("GroupsDetails", [])
        excluded = False
        trigger_group = None

        for group in groups_details:
            group_name = group.get("Name", "")
            if group_name.lower() in excluded_lower:
                excluded = True
                trigger_group = group_name
                break

        if excluded:
            exclusion_counts[trigger_group] = exclusion_counts.get(trigger_group, 0) + 1
        else:
            filtered.append(record)

    total_excluded = sum(exclusion_counts.values())
    if total_excluded > 0:
        logger.info(f"Excluded {total_excluded} records by group filter: {exclusion_counts}")

    return filtered, exclusion_counts


def format_date_for_filename(d: date) -> str:
    """Format a date as mm.dd.yy for filename."""
    return d.strftime("%m.%d.%y")


def run_export(start_date: date, end_date: date, config: dict) -> dict:
    """
    Run the full export process.

    Args:
        start_date: Start of date range
        end_date: End of date range
        config: Configuration dict

    Returns:
        Dict with results including DataFrames and statistics
    """
    client = BloomerangClient()

    logger.info(f"Fetching Individual constituents from {start_date} to {end_date}")
    raw_individuals = client.get_constituents(start_date, end_date, "Individual")
    logger.info(f"Retrieved {len(raw_individuals)} Individual records from API")

    logger.info(f"Fetching Organization constituents from {start_date} to {end_date}")
    raw_organizations = client.get_constituents(start_date, end_date, "Organization")
    logger.info(f"Retrieved {len(raw_organizations)} Organization records from API")

    excluded_groups = config.get("excluded_groups", [])

    filtered_individuals, ind_exclusions = filter_by_groups(raw_individuals, excluded_groups)
    filtered_organizations, org_exclusions = filter_by_groups(raw_organizations, excluded_groups)

    all_exclusions = {}
    for group, count in ind_exclusions.items():
        all_exclusions[group] = all_exclusions.get(group, 0) + count
    for group, count in org_exclusions.items():
        all_exclusions[group] = all_exclusions.get(group, 0) + count

    logger.info("Transforming Individual records")
    individuals_df, exception_records = transform_individuals(filtered_individuals, config)

    logger.info("Transforming Organization records")
    organizations_df = transform_organizations(filtered_organizations, config)

    exceptions_df = create_exceptions_dataframe(exception_records)

    date_prefix = f"{format_date_for_filename(start_date)}_to_{format_date_for_filename(end_date)}"

    return {
        "individuals_df": individuals_df,
        "organizations_df": organizations_df,
        "exceptions_df": exceptions_df,
        "stats": {
            "api_individuals": len(raw_individuals),
            "api_organizations": len(raw_organizations),
            "excluded_by_group": all_exclusions,
            "transformed_individuals": len(individuals_df),
            "transformed_organizations": len(organizations_df),
            "exceptions": len(exceptions_df)
        },
        "filenames": {
            "individuals": f"{date_prefix}_individuals.xlsx",
            "organizations": f"{date_prefix}_organizations.xlsx",
            "exceptions": f"{date_prefix}_manual_review.xlsx"
        }
    }


def main():
    st.set_page_config(
        page_title="Bloomerang Constituent Export",
        page_icon="📊",
        layout="wide"
    )

    st.title("Bloomerang Constituent Export")

    try:
        config = load_config()
    except Exception as e:
        st.error(f"Failed to load configuration: {e}")
        return

    with st.sidebar:
        st.header("Export Settings")

        today = date.today()
        first_of_month = today.replace(day=1)

        start_date = st.date_input(
            "Start Date",
            value=first_of_month,
            max_value=today
        )

        end_date = st.date_input(
            "End Date",
            value=today,
            min_value=start_date,
            max_value=today
        )

        run_button = st.button("Run Export", type="primary")

    if run_button:
        st.session_state.pop("export_results", None)

        with st.spinner("Fetching and transforming records..."):
            try:
                results = run_export(start_date, end_date, config)
                st.session_state["export_results"] = results
            except EnvironmentError as e:
                st.error(str(e))
                logger.exception("Environment configuration error")
                return
            except BloomerangAPIError as e:
                st.error(f"API Error: {e}")
                logger.exception("Bloomerang API error")
                return
            except Exception as e:
                st.error(f"An unexpected error occurred. Please check the logs for details.")
                logger.exception(f"Unexpected error during export: {e}")
                return

    if "export_results" in st.session_state:
        results = st.session_state["export_results"]
        stats = results["stats"]

        st.header("Summary")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Individuals from API", stats["api_individuals"])
            st.metric("Individuals Transformed", stats["transformed_individuals"])
        with col2:
            st.metric("Organizations from API", stats["api_organizations"])
            st.metric("Organizations Transformed", stats["transformed_organizations"])
        with col3:
            excluded_total = sum(stats["excluded_by_group"].values())
            st.metric("Excluded by Group Filter", excluded_total)
            st.metric("Exceptions (Manual Review)", stats["exceptions"])

        if stats["excluded_by_group"]:
            st.subheader("Exclusions by Group")
            for group, count in stats["excluded_by_group"].items():
                st.write(f"- **{group}**: {count} records")

        st.header("Preview")

        individuals_df = results["individuals_df"]
        organizations_df = results["organizations_df"]
        exceptions_df = results["exceptions_df"]

        with st.expander("Individuals Preview (first 20 rows)", expanded=True):
            if len(individuals_df) > 0:
                st.dataframe(individuals_df.head(20), use_container_width=True)
            else:
                st.info("No Individual records to display.")

        with st.expander("Organizations Preview (first 20 rows)"):
            if len(organizations_df) > 0:
                st.dataframe(organizations_df.head(20), use_container_width=True)
            else:
                st.info("No Organization records to display.")

        if len(exceptions_df) > 0:
            with st.expander("Manual Review Preview (first 20 rows)"):
                st.dataframe(exceptions_df.head(20), use_container_width=True)

        st.header("Downloads")

        filenames = results["filenames"]

        col1, col2, col3 = st.columns(3)

        with col1:
            if len(individuals_df) > 0:
                individuals_bytes = df_to_excel_bytes(individuals_df)
                st.download_button(
                    label="Download Individuals",
                    data=individuals_bytes,
                    file_name=filenames["individuals"],
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("No Individuals to download.")

        with col2:
            if len(organizations_df) > 0:
                organizations_bytes = df_to_excel_bytes(organizations_df)
                st.download_button(
                    label="Download Organizations",
                    data=organizations_bytes,
                    file_name=filenames["organizations"],
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("No Organizations to download.")

        with col3:
            if len(exceptions_df) > 0:
                exceptions_bytes = df_to_excel_bytes(exceptions_df)
                st.download_button(
                    label="Download Manual Review",
                    data=exceptions_bytes,
                    file_name=filenames["exceptions"],
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )


if __name__ == "__main__":
    main()
