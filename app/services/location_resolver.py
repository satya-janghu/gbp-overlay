"""Location inference and disambiguation."""
import logging
import re
from collections import Counter
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# US states for quick lookup
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

# Unambiguous major cities (no Gemini call needed)
UNAMBIGUOUS_CITIES = {
    "chicago": "Chicago, IL",
    "houston": "Houston, TX",
    "phoenix": "Phoenix, AZ",
    "philadelphia": "Philadelphia, PA",
    "san antonio": "San Antonio, TX",
    "san diego": "San Diego, CA",
    "dallas": "Dallas, TX",
    "austin": "Austin, TX",
    "san jose": "San Jose, CA",
    "los angeles": "Los Angeles, CA",
    "new york": "New York, NY",
    "miami": "Miami, FL",
    "atlanta": "Atlanta, GA",
    "boston": "Boston, MA",
    "seattle": "Seattle, WA",
    "denver": "Denver, CO",
    "detroit": "Detroit, MI",
    "minneapolis": "Minneapolis, MN",
    "tampa": "Tampa, FL",
    "orlando": "Orlando, FL",
    "pittsburgh": "Pittsburgh, PA",
    "baltimore": "Baltimore, MD",
    "las vegas": "Las Vegas, NV",
    "milwaukee": "Milwaukee, WI",
    "albuquerque": "Albuquerque, NM",
    "tucson": "Tucson, AZ",
    "sacramento": "Sacramento, CA",
    "kansas city": "Kansas City, MO",
    "nashville": "Nashville, TN",
    "new orleans": "New Orleans, LA",
    "salt lake city": "Salt Lake City, UT",
    "san francisco": "San Francisco, CA",
}


# Full state name -> abbreviation mapping
STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}

# Regex for "City, ST" (two-letter state abbreviation)
_RE_CITY_STATE_ABBR = re.compile(
    r'\b([A-Z][a-zA-Z .]+?),\s*([A-Z]{2})\b'
)

# Regex for "City, StateName" (full state name)
_RE_CITY_STATE_FULL = re.compile(
    r'\b([A-Z][a-zA-Z .]+?),\s*(' + '|'.join(
        re.escape(s.title()) for s in STATE_NAMES
    ) + r')\b'
)


def extract_location_from_text(text: str) -> str | None:
    """Extract a 'City, ST' location from free text (titles, meta descriptions).

    Tries two patterns:
    1. "City, ST" — e.g. "Springfield, IL"
    2. "City, StateName" — e.g. "Springfield, Illinois"

    Cross-references against UNAMBIGUOUS_CITIES and STATE_NAMES for validation.
    Returns "City, ST" format or None.
    """
    if not text:
        return None

    # Try "City, ST" pattern first
    match = _RE_CITY_STATE_ABBR.search(text)
    if match:
        city, state = match.group(1).strip(), match.group(2).upper()
        if state in US_STATES:
            return f"{city}, {state}"

    # Try "City, StateName" pattern
    match = _RE_CITY_STATE_FULL.search(text)
    if match:
        city = match.group(1).strip()
        state_name = match.group(2).lower()
        state_abbr = STATE_NAMES.get(state_name)
        if state_abbr:
            return f"{city}, {state_abbr}"

    # Check if text contains an unambiguous city name
    text_lower = text.lower()
    for city_name, resolved in UNAMBIGUOUS_CITIES.items():
        if city_name in text_lower:
            # Verify it's a word boundary (not part of a larger word)
            idx = text_lower.index(city_name)
            before_ok = idx == 0 or not text_lower[idx - 1].isalpha()
            after_idx = idx + len(city_name)
            after_ok = after_idx >= len(text_lower) or not text_lower[after_idx].isalpha()
            if before_ok and after_ok:
                return resolved

    return None


def extract_location_from_url(url: str) -> str | None:
    """Extract a location name from URL path segments."""
    path = urlparse(url).path.strip("/")
    segments = path.split("/")

    # Look for location-indicating segments
    location_indicators = {"locations", "location", "service-area", "service-areas",
                          "areas-we-serve", "cities", "city"}

    for i, segment in enumerate(segments):
        if segment.lower() in location_indicators and i + 1 < len(segments):
            # The next segment is likely the location
            slug = segments[i + 1]
            return slug.replace("-", " ").replace("_", " ").title()

    # If no indicator found, try the last segment
    if len(segments) >= 2:
        last = segments[-1]
        if len(last) > 2 and not last.startswith(("page", "index", "about", "contact")):
            return last.replace("-", " ").replace("_", " ").title()

    return None


def build_context_profile(locations: list[str]) -> dict:
    """Build a location context profile to help with disambiguation.

    Analyzes all locations to find common state patterns.
    """
    state_counts = Counter()
    resolved = {}

    for loc in locations:
        if not loc:
            continue
        loc_lower = loc.lower().strip()

        # Check if already in City, State format
        if ", " in loc:
            parts = loc.split(", ")
            if len(parts) == 2 and parts[1].upper() in US_STATES:
                state_counts[parts[1].upper()] += 1
                resolved[loc_lower] = loc
                continue

        # Check unambiguous cities
        if loc_lower in UNAMBIGUOUS_CITIES:
            full = UNAMBIGUOUS_CITIES[loc_lower]
            state = full.split(", ")[1]
            state_counts[state] += 1
            resolved[loc_lower] = full

    # Find dominant state
    dominant_state = state_counts.most_common(1)[0][0] if state_counts else None

    return {
        "state_counts": dict(state_counts),
        "dominant_state": dominant_state,
        "resolved": resolved,
    }


def resolve_location(location: str, context: dict | None = None,
                     known_locations: list[str] | None = None) -> str:
    """Resolve a location string to "City, State" format.

    Tries in order:
    1. Already in City, State format -> return as-is
    2. Unambiguous city -> resolve directly
    3. Context profile has dominant state -> assume that state
    4. Fall back to Gemini API call
    """
    if not location:
        return ""

    location = location.strip()

    # Already resolved
    if ", " in location:
        parts = location.split(", ")
        if len(parts) == 2 and len(parts[1]) <= 3:
            return location

    loc_lower = location.lower()

    # Unambiguous
    if loc_lower in UNAMBIGUOUS_CITIES:
        return UNAMBIGUOUS_CITIES[loc_lower]

    # Use context profile
    if context and context.get("dominant_state"):
        return f"{location.title()}, {context['dominant_state']}"

    # Gemini fallback
    try:
        from app.services.gemini_client import resolve_location as gemini_resolve
        return gemini_resolve(location, known_locations or [])
    except Exception as e:
        logger.warning("Gemini location resolution failed for '%s': %s", location, e)
        return location
