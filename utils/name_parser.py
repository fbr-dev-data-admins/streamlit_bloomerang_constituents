"""Name parser for individual constituent records."""

import re
import logging

logger = logging.getLogger(__name__)


def parse_individual_name(formal_name: str, informal_name: str, config: dict) -> dict:
    """
    Parse an individual's formal name into structured fields.

    Args:
        formal_name: The formal name string to parse (e.g., "John and Jane Doe")
        informal_name: The informal/nickname string (e.g., "Johnny and Janie")
        config: Dict containing name_prefixes, name_suffixes, name_exception_keywords

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

    # Step 1: Reject immediately if empty
    if not working:
        result["parse_exception"] = True
        result["parse_exception_reason"] = "Unparseable Name"
        return result

    # Step 1: Reject if contains exception keywords (whole word, case-insensitive)
    for keyword in exception_keywords:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, working, re.IGNORECASE):
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

    # Step 1: Reject if entirely uppercase or entirely lowercase
    alpha_chars = [c for c in working if c.isalpha()]
    if alpha_chars:
        if all(c.isupper() for c in alpha_chars) or all(c.islower() for c in alpha_chars):
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

    # Step 2: Strip prefixes/titles from beginning
    title_found = ""
    for prefix in prefixes:
        pattern = r'^' + re.escape(prefix) + r'\s+'
        match = re.match(pattern, working, re.IGNORECASE)
        if match:
            title_found = prefix
            working = working[match.end():].strip()
            break
    result["title"] = title_found

    # Step 3: Strip suffixes from end
    suffix_found = ""
    for suffix in suffixes:
        pattern = r'\s+' + re.escape(suffix) + r'\.?$'
        match = re.search(pattern, working, re.IGNORECASE)
        if match:
            suffix_found = suffix
            working = working[:match.start()].strip()
            break
    result["suffix"] = suffix_found

    # Step 4: Detect couple pattern
    couple_match = re.search(r'\s+(?:and|&)\s+', working, re.IGNORECASE)

    if couple_match:
        # Parse as couple
        left_part = working[:couple_match.start()].strip()
        right_part = working[couple_match.end():].strip()

        left_tokens = left_part.split()
        right_tokens = right_part.split()

        if len(left_tokens) >= 2 and len(right_tokens) >= 1:
            # Case A: Two full names (e.g., "John Doe and Jane Smith")
            result["first_name"] = left_tokens[0]
            result["last_name"] = left_tokens[-1]
            result["spouse_first_name"] = right_tokens[0]
            result["spouse_last_name"] = right_tokens[-1] if len(right_tokens) >= 2 else left_tokens[-1]
        elif len(left_tokens) == 1 and len(right_tokens) >= 2:
            # Case B: Shared last name (e.g., "John and Jane Doe")
            result["first_name"] = left_tokens[0]
            result["last_name"] = right_tokens[-1]
            result["spouse_first_name"] = right_tokens[0]
            result["spouse_last_name"] = right_tokens[-1]
        elif len(left_tokens) == 1 and len(right_tokens) == 1:
            # Case C: Cannot determine (e.g., "John and Jane" with no last name)
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result
        else:
            # Case C: Cannot determine
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result
    else:
        # Parse as single person
        tokens = working.split()
        if len(tokens) >= 2:
            result["first_name"] = tokens[0]
            result["last_name"] = tokens[-1]
        elif len(tokens) == 1:
            # Only one name - cannot determine first vs last
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result
        else:
            result["parse_exception"] = True
            result["parse_exception_reason"] = "Unparseable Name"
            return result

    # Final check: must have first and last name
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
    
    # If informal revealed a spouse but formal was parsed as solo, derive spouse fields
    if result["spouse_nickname"] and not result["spouse_first_name"]:
        result["spouse_first_name"] = result["spouse_nickname"]
        result["spouse_last_name"] = result["last_name"]  # assume shared last name


if __name__ == "__main__":
    # Test configuration
    test_config = {
        "name_prefixes": ["Dr.", "Mr.", "Mrs.", "Ms.", "Miss", "Rev.", "Prof."],
        "name_suffixes": ["Jr.", "Sr.", "II", "III", "IV", "V", "Esq.", "Ph.D."],
        "name_exception_keywords": [
            "Family", "Foundation", "Fund", "Trust", "Estate", "Group",
            "Committee", "Association", "Society", "Organization"
        ]
    }

    test_cases = [
        # (formal_name, informal_name, expected_checks)
        ("John Doe", "", {
            "first_name": "John", "last_name": "Doe",
            "spouse_first_name": "", "parse_exception": False
        }),
        ("John and Jane Doe", "", {
            "first_name": "John", "last_name": "Doe",
            "spouse_first_name": "Jane", "spouse_last_name": "Doe", "parse_exception": False
        }),
        ("John Doe and Jane-Ann Smith", "", {
            "first_name": "John", "last_name": "Doe",
            "spouse_first_name": "Jane-Ann", "spouse_last_name": "Smith", "parse_exception": False
        }),
        ("John Doe & Jane-Ann Doe", "", {
            "first_name": "John", "last_name": "Doe",
            "spouse_first_name": "Jane-Ann", "spouse_last_name": "Doe", "parse_exception": False
        }),
        ("Dr. John Doe", "", {
            "title": "Dr.", "first_name": "John", "last_name": "Doe", "parse_exception": False
        }),
        ("John Doe Jr.", "", {
            "first_name": "John", "last_name": "Doe", "suffix": "Jr.", "parse_exception": False
        }),
        ("The Smith Family", "", {
            "parse_exception": True, "parse_exception_reason": "Unparseable Name"
        }),
        ("JOHN DOE", "", {
            "parse_exception": True, "parse_exception_reason": "Unparseable Name"
        }),
        ("Jane-Ann O'Brien", "", {
            "first_name": "Jane-Ann", "last_name": "O'Brien", "parse_exception": False
        }),
        ("Rev. John and Jane Doe", "", {
            "title": "Rev.", "first_name": "John", "last_name": "Doe",
            "spouse_first_name": "Jane", "spouse_last_name": "Doe", "parse_exception": False
        }),
    ]

    print("Running name parser tests...\n")
    all_passed = True

    for i, (formal, informal, expected) in enumerate(test_cases, 1):
        result = parse_individual_name(formal, informal, test_config)

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
