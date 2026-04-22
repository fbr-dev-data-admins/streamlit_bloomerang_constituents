"""Name parser for individual constituent records."""

import re
import logging

logger = logging.getLogger(__name__)


def _has_joining_term(value: str) -> bool:
    """Returns True if the string contains a couple-joining term (and, &)."""
    return bool(re.search(r'\b(?:and|&)\b', value, re.IGNORECASE))


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
    envelope_name: str = "",
    raw_first: str = "",
    raw_last: str = "",
    raw_prefix: str = ""
) -> dict:
    """
    Parse an individual's formal name into structured fields.

    Priority order:
      1. Raw FirstName/LastName if clean (no joining terms) — for primary person fields
      2. Envelope name — for spouse fields and first name resolution on last-name-only formals
      3. Formal name parsing — fallback for everything else

    Args:
        formal_name: The formal name string to parse (e.g., "John and Jane Doe")
        informal_name: The informal/nickname string (e.g., "Johnny and Janie")
        config: Dict containing name_prefixes, name_suffixes, name_exception_keywords
        envelope_name: The envelope name string (e.g., "Rebecca & Noble Fowler")
        raw_first: Raw FirstName field from API
        raw_last: Raw LastName field from API
        raw_prefix: Raw Prefix field from API

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

    # Determine if raw API fields are reliable for primary person
    raw_fields_clean = (
        raw_first and raw_last
        and not _has_joining_term(raw_first)
        and not _has_joining_term(raw_last)
    )

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
    result["title"] = raw_prefix if raw_prefix else title_found

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
        # Last-name-only formal — use raw fields + envelope to resolve
        envelope = _parse_envelope(envelope_name)
        informal = informal_name.strip() if informal_name else ""

        if raw_fields_clean:
            result["first_name"] = raw_first
            result["last_name"] = raw_last
        elif envelope:
            result["first_name"] = envelope["primary_first"]
            result["last_name"] = tokens_after_strip[0]
        elif informal:
            result["first_name"] = informal.split()[0]
            result["last_name"] = tokens_after_strip[0]
        else:
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

        # Spouse from envelope
        if envelope:
            result["spouse_first_name"] = envelope["spouse_first"]
            result["spouse_last_name"] = envelope["spouse_last"]

        # Nicknames from informal
        if informal:
            informal_match = re.search(r'\s+(?:and|&)\s+', informal, re.IGNORECASE)
            if informal_match:
                result["nickname"] = informal[:informal_match.start()].strip()
                result["spouse_nickname"] = informal[informal_match.end():].strip()
            else:
                result["nickname"] = informal

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
            # Case A: "John Doe and Jane Smith" or "John Doe and Jane"
            result["first_name"] = left_tokens[0]
            result["last_name"] = left_tokens[-1]
            result["spouse_first_name"] = right_tokens[0]
            result["spouse_last_name"] = right_tokens[-1] if len(right_tokens) >= 2 else left_tokens[-1]
        elif len(left_tokens) == 1 and len(right_tokens) >= 2:
            # Case B: "John and Jane Doe"
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

        # If raw fields are clean, override primary person fields
        if raw_fields_clean:
            result["first_name"] = raw_first
            result["last_name"] = raw_last

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

        # If raw fields are clean, override primary person fields
        if raw_fields_clean:
            result["first_name"] = raw_first
            result["last_name"] = raw_last

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


if __name__ == "__main__":
    test_config = {
        "name_prefixes": ["Dr.", "Mr.", "Mrs.", "Ms.", "Miss", "Rev.", "Prof."],
        "name_suffixes": ["Jr.", "Sr.", "II", "III", "IV", "V", "Esq.", "Ph.D."],
        "name_exception_keywords": [
            "Family", "Foundation", "Fund", "Trust", "Estate", "Group",
            "Committee", "Association", "Society", "Organization"
        ]
    }

    test_cases = [
        # (formal, informal, envelope, raw_first, raw_last, raw_prefix, expected)
        ("John Doe", "", "", "", "", "", {
            "first_name": "John", "last_name": "Doe",
            "spouse_first_name": "", "parse_exception": False
        }),
        ("John and Jane Doe", "", "", "", "", "", {
            "first_name": "John", "last_name": "Doe",
            "spouse_first_name": "Jane", "spouse_last_name": "Doe", "parse_exception": False
        }),
        ("John Doe and Jane-Ann Smith", "", "", "", "", "", {
            "first_name": "John", "last_name": "Doe",
            "spouse_first_name": "Jane-Ann", "spouse_last_name": "Smith", "parse_exception": False
        }),
        ("Dr. John Doe", "", "", "", "", "", {
            "title": "Dr.", "first_name": "John", "last_name": "Doe", "parse_exception": False
        }),
        ("John Doe Jr.", "", "", "", "", "", {
            "first_name": "John", "last_name": "Doe", "suffix": "Jr.", "parse_exception": False
        }),
        ("The Smith Family", "", "", "", "", "", {
            "parse_exception": True
        }),
        ("JOHN DOE", "", "", "", "", "", {
            "parse_exception": True
        }),
        # Raw fields override formal parsing for primary person
        ("David Osborn", "David & Jessica", "", "David", "Osborn", "", {
            "first_name": "David", "last_name": "Osborn",
            "spouse_first_name": "Jessica", "spouse_last_name": "Osborn", "parse_exception": False
        }),
        # Last-name-only formal, raw fields clean
        ("Mrs. Aaron-Fowler", "Rebecca", "Rebecca & Noble Fowler", "Rebecca", "Aaron-Fowler", "Mrs.", {
            "first_name": "Rebecca", "last_name": "Aaron-Fowler",
            "spouse_first_name": "Noble", "spouse_last_name": "Fowler",
            "title": "Mrs.", "nickname": "Rebecca", "parse_exception": False
        }),
        # Solo formal, informal reveals spouse, envelope corrects spouse last name
        ("Rebecca Smith", "Rebecca and Noble", "Rebecca Smith & Noble Fowler", "Rebecca", "Smith", "", {
            "first_name": "Rebecca", "last_name": "Smith",
            "spouse_first_name": "Noble", "spouse_last_name": "Fowler", "parse_exception": False
        }),
        # Last-name-only formal, no raw first name
        ("Mrs. Smith", "Rebecca", "Rebecca & Noble Fowler", "", "", "Mrs.", {
            "first_name": "Rebecca", "last_name": "Smith",
            "spouse_first_name": "Noble", "spouse_last_name": "Fowler",
            "title": "Mrs.", "parse_exception": False
        }),
    ]

    print("Running name parser tests...\n")
    all_passed = True

    for i, (formal, informal, envelope, raw_first, raw_last, raw_prefix, expected) in enumerate(test_cases, 1):
        result = parse_individual_name(
            formal, informal, test_config,
            envelope_name=envelope,
            raw_first=raw_first,
            raw_last=raw_last,
            raw_prefix=raw_prefix
        )

        passed = True
        failures = []
        for key, expected_val in expected.items():
            actual_val = result.get(key)
            if actual_val != expected_val:
                passed = False
                failures.append(f"  {key}: expected '{expected_val}', got '{actual_val}'")

        status = "PASS" if passed else "FAIL"
        print(f"Test {i}: \"{formal}\" -> {status}")
        if not passed:
            all_passed = False
            for f in failures:
                print(f)
        print()

    print(f"\n{'All tests passed!' if all_passed else 'Some tests failed.'}")
