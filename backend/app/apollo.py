import httpx

from app.config import settings

BASE_URL = "https://api.apollo.io/api/v1"


def request_apollo(path: str, params: list[tuple[str, str]]):
    if not settings.apollo_api_key:
        raise RuntimeError("APOLLO_API_KEY is not configured.")
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(
                BASE_URL + path, params=params,
                headers={"x-api-key": settings.apollo_api_key, "Cache-Control": "no-cache"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Apollo returned HTTP {exc.response.status_code}. Check account access and limits.") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise RuntimeError("Could not retrieve a valid response from Apollo.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Apollo returned an unexpected response.")
    return data


def search_people(domain: str):
    params = [("q_organization_domains_list[]", domain), ("page", "1"), ("per_page", "25")]
    params.extend(("person_seniorities[]", value) for value in
                  ("owner", "founder", "c_suite", "vp", "head", "director"))
    return request_apollo("/mixed_people/api_search", params).get("people", [])


def enrich_person(apollo_id: str):
    return request_apollo("/people/match", [("id", apollo_id)]).get("person")
