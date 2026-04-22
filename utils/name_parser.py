"""Name parser for individual constituent records."""

import re
import logging

logger = logging.getLogger(__name__)


def _parse_envelope(envelope_name: str) -> dict | None:
    """
    Parse envelope name to extract primary and spouse name components.
    Handles patterns like:
      "Rebecca & Noble Fowler"
      "Rebecca Smith & Noble Fowler"
      "Rebecca & Noble Smith"

    Returns dict with keys: primary_first, primary_last, spouse_first, spouse_last
    or None if unparseable.
    """
    if not envelope_name:
        return None

    couple_match = re.search(r'\s*(?:and|&)\s*', envelope_name, re.IGNORECASE)
    if not couple_match:
        return None

    left = envelope_name[:couple_match.start()].strip()
    right = envelope_name[couple_match.end():].strip()

    left_tokens = left.split()
    right_tokens = right.split()

    if not left_tokens or not right_tokens:
        return None

    if len(left_tokens) == 1 and len(right_tokens) >= 2:
        # "Rebecca & Noble Fowler" — primary first only, spouse has full name
        return {
            "primary_first": left_tokens[0],
            "primary_last": right_tokens[-1],   # assume shared last
            "spouse_first": right_tokens[0],
            "spouse_last": right_tokens[-1]
        }
    elif len(left_tokens) >= 2 and len(right_tokens) >= 2:
        # "Rebecca Smith & Noble Fowler" — both have full names
        return {
            "primary_first": left_tokens[0],
            "primary_last": left_tokens[-1],
            "spouse_first": right_tokens[0],
            "spouse_last": right_tokens[-1]
        }
    elif len(left_tokens) >= 2 and len(right_tokens) == 1:
        # "Rebecca Smith & Noble" — primary full, spouse first only, shared last
        return {
            "primary_first": left_tokens[0],
            "primary_last": left_tokens[-1],
            "spouse_first": right_tokens[0],
            "spouse_last": left_tokens[-1]
        }

    return None


def parse_individual_name(
    formal_name: str,
    informal_name: str,
    config: dict,
    envelope_name: str = ""
) -> dict:
    """
    Parse an individual's formal name into structured fields.

    Args:
        formal_name: The formal name string to parse (e.g., "John and Jane Doe")
        informal_name: The informal/nickname string (e.g., "Johnny and Janie")
        config: Dict containing name_prefixes, name_suffixes, name_exception_keywords
        envelope_name: The envelope name string (e.g., "Rebecca & Noble Fowler")

    Returns:
        Dict with parsed name fields and parse_exception status
    """
    result = {
        "first_name": "",
        "last_name": "",
        "title": "",
        "suffix": "",
        "nickname": "",
        "spouse_first_name": "",
        "spouse_last_name": "",
        "spouse_nickname": "",
        "parse_exception": False,
        "parse_exception_reason": ""
    }

    prefixes = config.get("name_prefixes", [])
    suffixes = config.get("name_suffixes", [])
    exception_keywords = config.get("name_exception_keywords", [])

    working = formal_name.strip() if formal_name else ""

    if not working:
        result["parse_exception"] = True
        result["parse_exception_reason"] = "Unparseable Name"
        return result

    for keyword in exception_keywords:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, working, re.IGNORECASE):
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

    alpha_chars = [c for c in working if c.isalpha()]
    if alpha_chars:
        if all(c.isupper() for c in alpha_chars) or all(c.islower() for c in alpha_chars):
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

    # Strip prefix/title
    title_found = ""
    for prefix in prefixes:
        pattern = r'^' + re.escape(prefix) + r'\s+'
        match = re.match(pattern, working, re.IGNORECASE)
        if match:
            title_found = prefix
            working = working[match.end():].strip()
            break
    result["title"] = title_found

    # Strip suffix
    suffix_found = ""
    for suffix in suffixes:
        pattern = r'\s+' + re.escape(suffix) + r'\.?$'
        match = re.search(pattern, working, re.IGNORECASE)
        if match:
            suffix_found = suffix
            working = working[:match.start()].strip()
            break
    result["suffix"] = suffix_found

    # Check if only one token remains after prefix/suffix strip (last-name-only formal)
    # e.g. "Mrs. Aaron-Fowler" -> working = "Aaron-Fowler"
    tokens_after_strip = working.split()
    if len(tokens_after_strip) == 1 and title_found:
        # Last-name-only formal name — use envelope to resolve
        envelope = _parse_envelope(envelope_name)
        informal = informal_name.strip() if informal_name else ""
        if envelope:
            result["first_name"] = envelope["primary_first"]
            result["last_name"] = tokens_after_strip[0]  # trust formal for primary last
            result["spouse_first_name"] = envelope["spouse_first"]
            result["spouse_last_name"] = envelope["spouse_last"]
            # nickname from informal
            if informal:
                informal_match = re.search(r'\s+(?:and|&)\s+', informal, re.IGNORECASE)
                if informal_match:
                    result["nickname"] = informal[:informal_match.start()].strip()
                    result["spouse_nickname"] = informal[informal_match.end():].strip()
                else:
                    result["nickname"] = informal
        elif informal:
            # No envelope, try informal for first name at minimum
            result["first_name"] = informal.split()[0]
            result["last_name"] = tokens_after_strip[0]
            result["nickname"] = informal.split()[0]
        else:
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

        if not result["first_name"] or not result["last_name"]:
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

        return result

    # Detect couple pattern in formal name
    couple_match = re.search(r'\s+(?:and|&)\s+', working, re.IGNORECASE)

    if couple_match:
        left_part = working[:couple_match.start()].strip()
        right_part = working[couple_match.end():].strip()

        left_tokens = left_part.split()
        right_tokens = right_part.split()

        if len(left_tokens) >= 2 and len(right_tokens) >= 1:
            result["first_name"] = left_tokens[0]
            result["last_name"] = left_tokens[-1]
            result["spouse_first_name"] = right_tokens[0]
            result["spouse_last_name"] = right_tokens[-1] if len(right_tokens) >= 2 else left_tokens[-1]
        elif len(left_tokens) == 1 and len(right_tokens) >= 2:
            result["first_name"] = left_tokens[0]
            result["last_name"] = right_tokens[-1]
            result["spouse_first_name"] = right_tokens[0]
            result["spouse_last_name"] = right_tokens[-1]
        elif len(left_tokens) == 1 and len(right_tokens) == 1:
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result
        else:
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result
    else:
        # Single person formal name
        tokens = working.split()
        if len(tokens) >= 2:
            result["first_name"] = tokens[0]
            result["last_name"] = tokens[-1]
        elif len(tokens) == 1:
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result
        else:
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

    if not result["first_name"] or not result["last_name"]:
        result["parse_exception"] = True
        result["parse_exception_reason"] = "Unparseable Name"
        return result

    # Parse informal name for nicknames
    informal = informal_name.strip() if informal_name else ""
    if informal:
        informal_match = re.search(r'\s+(?:and|&)\s+', informal, re.IGNORECASE)
        if informal_match:
            result["nickname"] = informal[:informal_match.start()].strip()
            result["spouse_nickname"] = informal[informal_match.end():].strip()
        else:
            result["nickname"] = informal
            result["spouse_nickname"] = ""

    # If informal revealed a spouse but formal was solo, derive spouse fields
    if result["spouse_nickname"] and not result["spouse_first_name"]:
        result["spouse_first_name"] = result["spouse_nickname"]
        # Use envelope to get correct spouse last name if available
        envelope = _parse_envelope(envelope_name)
        if envelope and envelope["spouse_last"]:
            result["spouse_last_name"] = envelope["spouse_last"]
        else:
            result["spouse_last_name"] = result["last_name"]  # fallback: assume shared

    return result
