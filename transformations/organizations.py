"""Transformation logic for Organization constituent records."""

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

ORGANIZATION_OUTPUT_COLUMNS = [
    "Account Number",
    "Organization Name",
    "Home Address",
    "Home City",
    "Home State",
    "Home ZIP",
    "Country",
    "Email Type",
    "Home Email",
    "Phone Type",
    "Home Phone",
    "Primary Contact First Name",
    "Primary Contact Last Name",
    "Supporter Type",
    "Contact Type",
    "Is Primary?",
    "Contact Addressee",
    "Contact Salutation",
    "Relationship",
    "Reciprocal",
    "Data Source"
]


def flatten_organization(raw: dict, config: dict) -> dict:
    """
    Flatten a raw organization record into a normalized dict.

    Args:
        raw: Raw API response dict for an organization
        config: Configuration dict with supporter_type_mapping

    Returns:
        Flattened dict with standardized field names
    """
    flat = {}

    flat["Id"] = raw.get("Id", "")
    flat["AccountNumber"] = str(raw.get("AccountNumber", ""))
    flat["FullName"] = raw.get("FullName", "")
    flat["FirstName"] = raw.get("FirstName", "")
    flat["LastName"] = raw.get("LastName", "")

    address = raw.get("Address")
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
                f"Invalid phone format for organization {constituent_id}: '{raw_phone}' "
                f"({len(digits)} digits after cleanup)"
            )
        return ""


def transform_organizations(raw_records: list[dict], config: dict) -> pd.DataFrame:
    """
    Transform raw organization records into the output format.

    Args:
        raw_records: List of raw API response dicts
        config: Configuration dict

    Returns:
        Transformed DataFrame
    """
    transformed_rows = []

    for raw in raw_records:
        try:
            flat = flatten_organization(raw, config)

            row = {}
            row["Account Number"] = flat["AccountNumber"]
            row["Organization Name"] = flat["FullName"]
            row["Home Address"] = flat["Home Address"]
            row["Home City"] = flat["Home City"]
            row["Home State"] = flat["Home State"]
            row["Home ZIP"] = flat["Home ZIP"]
            row["Country"] = flat["Country"]

            row["Email Type"] = "E-mail" if flat["Home Email"] else ""
            row["Home Email"] = flat["Home Email"]

            row["Phone Type"] = "Primary Phone" if flat["Home Phone"] else ""
            row["Home Phone"] = flat["Home Phone"]

            row["Primary Contact First Name"] = flat["FirstName"] or ""
            row["Primary Contact Last Name"] = flat["LastName"] or ""
            row["Supporter Type"] = flat["Supporter Type"]

            has_contact = bool(flat["FirstName"])
            row["Contact Type"] = "Primary Contact" if has_contact else ""
            row["Is Primary?"] = "TRUE" if has_contact else ""
            row["Contact Addressee"] = "46" if has_contact else ""
            row["Contact Salutation"] = "35" if has_contact else ""
            row["Relationship"] = "MANUAL UPDATE" if has_contact else ""
            row["Reciprocal"] = "MANUAL UPDATE" if has_contact else ""

            row["Data Source"] = "Bloomerang"

            transformed_rows.append(row)

        except Exception as e:
            logger.warning(
                f"Unexpected error transforming organization {raw.get('Id', 'unknown')}: {e}"
            )

    if transformed_rows:
        df = pd.DataFrame(transformed_rows)
        df = df[ORGANIZATION_OUTPUT_COLUMNS]
    else:
        df = pd.DataFrame(columns=ORGANIZATION_OUTPUT_COLUMNS)

    logger.info(f"Organization transformation complete: {len(transformed_rows)} transformed")

    return df
