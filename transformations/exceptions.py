"""Exception record handling for manual review."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

EXCEPTION_OUTPUT_COLUMNS = [
    "Id",
    "AccountNumber",
    "Type",
    "Status",
    "FirstName",
    "LastName",
    "MiddleName",
    "Prefix",
    "Suffix",
    "InformalName",
    "FormalName",
    "FullName",
    "EnvelopeName",
    "RecognitionName",
    "PrimaryEmail",
    "PrimaryPhone",
    "Home Address",
    "Home City",
    "Home State",
    "Home ZIP",
    "Country",
    "Exception Reason"
]


def create_exception_record(raw_record: dict, flattened: dict, reason: str) -> dict:
    """
    Create an exception record for manual review.

    Args:
        raw_record: Original API response dict
        flattened: Flattened record dict
        reason: Reason for the exception

    Returns:
        Dict ready for the exceptions DataFrame
    """
    exception = {}

    exception["Id"] = str(raw_record.get("Id", ""))
    exception["AccountNumber"] = str(raw_record.get("AccountNumber", ""))
    exception["Type"] = raw_record.get("Type", "")
    exception["Status"] = raw_record.get("Status", "")
    exception["FirstName"] = raw_record.get("FirstName", "")
    exception["LastName"] = raw_record.get("LastName", "")
    exception["MiddleName"] = raw_record.get("MiddleName", "")
    exception["Prefix"] = raw_record.get("Prefix", "")
    exception["Suffix"] = raw_record.get("Suffix", "")
    exception["InformalName"] = raw_record.get("InformalName", "")
    exception["FormalName"] = raw_record.get("FormalName", "")
    exception["FullName"] = raw_record.get("FullName", "")
    exception["EnvelopeName"] = raw_record.get("EnvelopeName", "")
    exception["RecognitionName"] = raw_record.get("RecognitionName", "")

    primary_email = raw_record.get("PrimaryEmail", {})
    exception["PrimaryEmail"] = primary_email.get("Value", "") if primary_email else ""

    primary_phone = raw_record.get("PrimaryPhone", {})
    exception["PrimaryPhone"] = primary_phone.get("Number", "") if primary_phone else ""

    exception["Home Address"] = flattened.get("Home Address", "")
    exception["Home City"] = flattened.get("Home City", "")
    exception["Home State"] = flattened.get("Home State", "")
    exception["Home ZIP"] = flattened.get("Home ZIP", "")
    exception["Country"] = flattened.get("Country", "")
    exception["Exception Reason"] = reason

    for col in EXCEPTION_OUTPUT_COLUMNS:
        if col not in exception:
            exception[col] = ""

    return exception


def create_exceptions_dataframe(exception_records: list[dict]) -> pd.DataFrame:
    """
    Create a DataFrame from exception records.

    Args:
        exception_records: List of exception record dicts

    Returns:
        DataFrame with proper column ordering
    """
    if not exception_records:
        return pd.DataFrame(columns=EXCEPTION_OUTPUT_COLUMNS)

    df = pd.DataFrame(exception_records)
    df = df[EXCEPTION_OUTPUT_COLUMNS]

    return df
