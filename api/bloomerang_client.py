"""Bloomerang API client for constituent data retrieval."""

import logging
import os
import time
from datetime import date, datetime

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bloomerang.co/v2"


class BloomerangAPIError(Exception):
    """Raised when an unrecoverable API error occurs."""
    pass


class BloomerangClient:
    """Client for interacting with the Bloomerang API v2."""

    def __init__(self):
        """
        Initialize the Bloomerang client.

        Raises:
            EnvironmentError: If BLOOMERANG_API_KEY is not set
        """
        api_key = os.environ.get("BLOOMERANG_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "BLOOMERANG_API_KEY environment variable is not set. "
                "Please set it to your Bloomerang v2 private API key."
            )

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Basic {api_key}:",
            "Content-Type": "application/json"
        })

    def _request_with_retry(
        self, method: str, url: str, params: dict | None = None, max_retries: int = 3
    ) -> requests.Response:
        """
        Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            params: Query parameters
            max_retries: Maximum number of retry attempts

        Returns:
            Response object

        Raises:
            BloomerangAPIError: If all retries fail
        """
        backoff_times = [1, 2, 4]

        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, params=params)

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after else backoff_times[attempt]
                    logger.warning(
                        f"Rate limited (429). Waiting {wait_time}s before retry {attempt + 1}/{max_retries}"
                    )
                    time.sleep(wait_time)
                    continue

                if response.status_code >= 500:
                    wait_time = backoff_times[attempt]
                    logger.warning(
                        f"Server error ({response.status_code}). Waiting {wait_time}s before retry {attempt + 1}/{max_retries}"
                    )
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = backoff_times[attempt]
                    logger.warning(f"Request failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise BloomerangAPIError(
                        f"Failed to complete request to {url} after {max_retries} attempts: {e}"
                    )

        raise BloomerangAPIError(
            f"Failed to complete request to {url} after {max_retries} attempts"
        )

    def get_constituents(
        self,
        start_date: date,
        end_date: date,
        constituent_type: str | None = None
    ) -> list[dict]:
        """
        Retrieve constituents created within the specified date range.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            constituent_type: Filter by type ("Individual" or "Organization")

        Returns:
            List of constituent records as dicts
        """
        url = f"{BASE_URL}/constituents"
        collected = []
        skip = 0
        take = 50
        page_num = 0

        while True:
            params = {
                "skip": skip,
                "take": take,
                "orderBy": "CreatedDate",
                "orderDirection": "Asc"
            }
            if constituent_type:
                params["type"] = constituent_type

            response = self._request_with_retry("GET", url, params=params)
            data = response.json()

            total_filtered = data.get("TotalFiltered", 0)
            results = data.get("Results", [])
            start_idx = data.get("Start", skip)
            result_count = data.get("ResultCount", len(results))

            page_num += 1
            if page_num % 5 == 0:
                logger.info(
                    f"Pagination progress: page {page_num}, processed {skip + result_count}/{total_filtered} "
                    f"({constituent_type or 'all types'})"
                )

            should_stop = False
            for record in results:
                audit_trail = record.get("AuditTrail", {})
                created_date_str = audit_trail.get("CreatedDate")

                if not created_date_str:
                    logger.warning(
                        f"Constituent {record.get('Id')} missing CreatedDate, skipping"
                    )
                    continue

                try:
                    created_dt = datetime.fromisoformat(created_date_str.replace("Z", "+00:00"))
                    created_date_only = created_dt.date()
                except ValueError as e:
                    logger.warning(
                        f"Could not parse CreatedDate '{created_date_str}' for constituent {record.get('Id')}: {e}"
                    )
                    continue

                if created_date_only < start_date:
                    continue
                elif start_date <= created_date_only <= end_date:
                    collected.append(record)
                else:
                    should_stop = True
                    break

            if should_stop:
                logger.info(
                    f"Early termination: reached records after {end_date} "
                    f"({constituent_type or 'all types'})"
                )
                break

            if start_idx + result_count >= total_filtered:
                break

            skip += take

        logger.info(
            f"Retrieved {len(collected)} {constituent_type or 'all'} constituents "
            f"created between {start_date} and {end_date}"
        )
        return collected
