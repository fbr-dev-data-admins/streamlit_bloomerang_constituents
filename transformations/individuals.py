"""Transformation logic for Individual constituent records."""

import logging
import re

import pandas as pd

from utils.name_parser import parse_individual_name
from transformations.exceptions import create_exception_record

logger = logging.getLogger(__name__)

INDIVIDUAL_OUTPUT_COLUMNS = [
    "Account Number",
    "First Name",
    "Last Name",
    "Title",
    "Suffix",
    "Nickname",
    "Spouse First Name",
    "Spouse Last Name",
    "Spouse Nickname",
    "Home Address",
    "Home City",
    "Home State",
    "Home ZIP",
    "Country",
    "Email Type",
    "Home Email",
    "Phone Type",
    "Home Phone",
    "Addressee",
    "Spouse Addressee",
    "Salutation",
    "Spouse Salutation",
    "Data Source",
    # Raw name fields for reference
    "Raw Full Name",
    "Raw Formal Name",
    "Raw Informal Name",
    "Raw Envelope Name",
]


def flatten_constituent(raw: dict, config: dict) -> dict:
    """
    Flatten a raw constituent record into a normalized dict.

    Args:
        raw: Raw API response dict for a constituent
        config: Configuration dict with supporter_type_mapping

    Returns:
        Flattened dict with standardized field names
    """
    flat = {}

    flat["Id"] = raw.get("Id", "")
    flat["AccountNumber"] = str(raw.get("AccountNumber", ""))
    flat["Type"] = raw.get("Type", "")
    flat["FormalName"] = raw.get("FormalName", "")
    flat["FullName"] = raw.get("FullName", "")
    flat["InformalName"] = raw.get("InformalName", "")
    flat["EnvelopeName"] = raw.get("EnvelopeName", "")
    flat["FirstName"] = raw.get("FirstName", "")
    flat["LastName"] = raw.get("LastName", "")
    flat["Prefix"] = raw.get("Prefix", "")

    address = raw.get("PrimaryAddress")
    if not address:
        addresses = raw.get("Addresses", [])
        if addresses:
            primary_addr = next(
                (a for a in addresses if a.get("IsPrimary")),
                addresses[0]
            )
            address = primary_addr

    if address:
        flat["Home Address"] = address.get("Street", "") or ""
        flat["Home City"] = address.get("City", "") or ""
        flat["Home State"] = address.get("State", "") or ""
        flat["Home ZIP"] = str(address.get("PostalCode", "") or "")
    else:
        flat["Home Address"] = ""
        flat["Home City"] = ""
        flat["Home State"] = ""
        flat["Home ZIP"] = ""

    flat["Country"] = "United States"

    email = ""
    primary_email = raw.get("PrimaryEmail")
    if primary_email and primary_email.get("Value"):
        email = primary_email.get("Value", "")
    else:
        emails = raw.get("Emails", [])
        if emails:
            primary = next((e for e in emails if e.get("IsPrimary")), None)
            if primary:
                email = primary.get("Value", "")

    flat["Home Email"] = email or ""

    phone = ""
    primary_phone = raw.get("PrimaryPhone")
    if primary_phone and primary_phone.get("Number"):
        phone = primary_phone.get("Number", "")
    else:
        phones = raw.get("Phones", [])
        if phones:
            primary = next((p for p in phones if p.get("IsPrimary")), None)
            if primary:
                phone = primary.get("Number", "")

    phone = format_phone(phone, flat.get("Id", "unknown"))
    flat["Home Phone"] = phone

    custom_fields = raw.get("CustomFields", {})
    supporter_type_values = custom_fields.get("Supporter Type", [])
    if supporter_type_values:
        raw_type = supporter_type_values[0]
        mapping = config.get("supporter_type_mapping", {})
        flat["Supporter Type"] = mapping.get(raw_type, raw_type)
    else:
        flat["Supporter Type"] = ""

    return flat


def format_phone(raw_phone: str, constituent_id) -> str:
    """
    Format a phone number to (XXX) XXX-XXXX format.

    Args:
        raw_phone: Raw phone string
        constituent_id: ID for logging purposes

    Returns:
        Formatted phone or empty string
    """
    if not raw_phone:
        return ""

    digits = re.sub(r'\D', '', raw_phone)

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    else:
        if digits:
            logger.warning(
                f"Invalid phone format for constituent {constituent_id}: '{raw_phone}' "
                f"({len(digits)} digits after cleanup)"
            )
        return ""


def transform_individuals(
    raw_records: list[dict],
    config: dict
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Transform raw individual records into the output format.

    Args:
        raw_records: List of raw API response dicts
        config: Configuration dict with name parsing settings

    Returns:
        Tuple of (transformed DataFrame, list of exception records)
    """
    transformed_rows = []
    exception_records = []

    for raw in raw_records:
        try:
            flat = flatten_constituent(raw, config)

            name_source = flat.get("FormalName", "").strip()
            if not name_source:
                name_source = flat.get("FullName", "").strip()

            if not name_source:
                exception_records.append(
                    create_exception_record(raw, flat, "Unparseable Name")
                )
                continue

            parse_result = parse_individual_name(
                name_source,
                flat.get("InformalName", ""),
                config,
                envelope_name=flat.get("EnvelopeName", ""),
                raw_first=flat.get("FirstName", ""),
                raw_last=flat.get("LastName", ""),
                raw_prefix=flat.get("Prefix", "")
            )

            if parse_result["parse_exception"]:
                exception_records.append(
                    create_exception_record(raw, flat, parse_result["parse_exception_reason"])
                )
                continue

            row = {}
            row["Account Number"] = flat["AccountNumber"]
            row["First Name"] = parse_result["first_name"]
            row["Last Name"] = parse_result["last_name"]
            row["Title"] = parse_result["title"]
            row["Suffix"] = parse_result["suffix"]
            row["Nickname"] = parse_result["nickname"]
            row["Spouse First Name"] = parse_result["spouse_first_name"]
            row["Spouse Last Name"] = parse_result["spouse_last_name"]
            row["Spouse Nickname"] = parse_result["spouse_nickname"]

            row["Home Address"] = flat["Home Address"]
            row["Home City"] = flat["Home City"]
            row["Home State"] = flat["Home State"]
            row["Home ZIP"] = flat["Home ZIP"]
            row["Country"] = flat["Country"]

            row["Email Type"] = "E-mail" if flat["Home Email"] else ""
            row["Home Email"] = flat["Home Email"]

            row["Phone Type"] = "Primary Phone" if flat["Home Phone"] else ""
            row["Home Phone"] = flat["Home Phone"]

            spouse_first = parse_result["spouse_first_name"]
            last_name = parse_result["last_name"]
            spouse_last = parse_result["spouse_last_name"]

            if spouse_first:
                if last_name.lower() == spouse_last.lower():
                    row["Addressee"] = "49"
                    row["Spouse Addressee"] = "49"
                else:
                    row["Addressee"] = "48"
                    row["Spouse Addressee"] = "48"
                row["Salutation"] = "46"
                row["Spouse Salutation"] = "46"
            else:
                row["Addressee"] = "48"
                row["Spouse Addressee"] = ""
                row["Salutation"] = "35"
                row["Spouse Salutation"] = ""

            row["Data Source"] = "Bloomerang"

            # Raw name fields appended for reference/QC
            row["Raw Full Name"] = flat.get("FullName", "")
            row["Raw Formal Name"] = flat.get("FormalName", "")
            row["Raw Informal Name"] = flat.get("InformalName", "")
            row["Raw Envelope Name"] = flat.get("EnvelopeName", "")
            

            transformed_rows.append(row)

        except Exception as e:
            logger.warning(
                f"Unexpected error transforming individual {raw.get('Id', 'unknown')}: {e}"
            )
            flat = flatten_constituent(raw, config)
            exception_records.append(
                create_exception_record(raw, flat, "Unparseable Name")
            )

    if transformed_rows:
        df = pd.DataFrame(transformed_rows)
        df = df[INDIVIDUAL_OUTPUT_COLUMNS]
    else:
        df = pd.DataFrame(columns=INDIVIDUAL_OUTPUT_COLUMNS)

    logger.info(
        f"Individual transformation complete: {len(transformed_rows)} transformed, "
        f"{len(exception_records)} exceptions"
    )

    return df, exception_records
