import math
import xml.etree.ElementTree as ET
from datetime import date as date_cls
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from crewai.tools import tool


GEOCODE_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
POI_TAGS = [
    ("leisure", "stadium", "Stadium"),
    ("leisure", "pitch", "Sports Pitch"),
    ("leisure", "sports_centre", "Sports Centre"),
    ("amenity", "cinema", "Cinema"),
    ("amenity", "theatre", "Theatre"),
    ("shop", "mall", "Mall"),
    ("leisure", "park", "Park"),
    ("tourism", "attraction", "Attraction"),
    ("amenity", "restaurant", "Restaurant"),
]


def _parse_iso_date(value: str | None) -> date_cls | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _today_utc() -> date_cls:
    return datetime.now(timezone.utc).date()


def _lookup_coordinates(location: str) -> tuple[float, float, str] | None:
    """Resolve a human-readable location string to coordinates via Open-Meteo."""
    if not location:
        return None

    response = requests.get(
        GEOCODE_ENDPOINT,
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("results"):
        return None

    match = data["results"][0]
    label = ", ".join(
        filter(
            None,
            [
                match.get("name"),
                match.get("admin1"),
                match.get("country"),
            ],
        )
    )
    return match["latitude"], match["longitude"], label


def _km_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _fetch_forecast(lat: float, lon: float, start_date: str | None = None, end_date: str | None = None) -> dict:
    """Pull hourly and daily forecast data from Open-Meteo."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "auto",
        "hourly": [
            "temperature_2m",
            "precipitation_probability",
            "relative_humidity_2m",
        ],
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "sunrise",
            "sunset",
        ],
    }

    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date
    else:
        params["forecast_days"] = 1

    response = requests.get(
        FORECAST_ENDPOINT,
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _format_news_age(pub_date: str) -> str:
    try:
        published = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError):
        return "recent"
    delta = datetime.now(timezone.utc) - published.astimezone(timezone.utc)
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "just now"
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _tag_label(tags: dict) -> str:
    for key, value, label in POI_TAGS:
        if tags.get(key) == value:
            return label
    return tags.get("amenity") or tags.get("leisure") or tags.get("tourism") or "Point of interest"


def _overpass_query(lat: float, lon: float, radius_m: int = 8000) -> str:
    selectors = "\n".join(
        f'  node(around:{radius_m},{lat},{lon})["{key}"="{value}"];' for key, value, _ in POI_TAGS
    )
    return f"""
[out:json][timeout:25];
(
{selectors}
);
out center;
"""


@tool("GetWeatherOutlook")
def get_weather_outlook(location: str, target_date: str | None = None) -> str:
    """Return a concise weather outlook for a location and date."""
    coordinates = _lookup_coordinates(location)
    if coordinates is None:
        return f"Unable to locate coordinates for '{location}'. Ask the user for a clearer location."

    target_day = _parse_iso_date(target_date) or _today_utc()
    lat, lon, pretty_label = coordinates
    day_str = target_day.isoformat()
    forecast = _fetch_forecast(lat, lon, start_date=day_str, end_date=day_str)
    daily = forecast.get("daily", {})

    def _pick(series: list, default: str = "N/A") -> str:
        return series[0] if series else default

    max_temp = _pick(daily.get("temperature_2m_max", []))
    min_temp = _pick(daily.get("temperature_2m_min", []))
    sunrise = _pick(daily.get("sunrise", []))
    sunset = _pick(daily.get("sunset", []))
    max_precip = _pick(daily.get("precipitation_probability_max", []))

    hourly = forecast.get("hourly", {})
    hourly_precip = hourly.get("precipitation_probability", [])
    humidity = hourly.get("relative_humidity_2m", [])
    temperature = hourly.get("temperature_2m", [])

    precip_risk = f"{max(hourly_precip)}%" if hourly_precip else "No precipitation data"
    humidity_snapshot = f"{humidity[len(humidity) // 2]}%" if humidity else "N/A"
    midday_temp = f"{temperature[len(temperature) // 2]}°C" if temperature else "N/A"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return (
        f"Weather outlook for {pretty_label} on {day_str} (generated {timestamp}):\n"
        f"- Daily range: {min_temp}°C – {max_temp}°C (midday ~ {midday_temp})\n"
        f"- Humidity snapshot: {humidity_snapshot}\n"
        f"- Peak precipitation probability: {max_precip}% (hourly max {precip_risk})\n"
        f"- Sunrise at {sunrise}, sunset at {sunset}\n"
        f"- Tip: favor indoor plans if precipitation exceeds 40% or humidity stays above 80%."
    )


@tool("GetCityNews")
def get_city_news(location: str, target_date: str | None = None, interests: str | None = None) -> str:
    """Fetch city-specific headlines filtered by date and interests."""
    if not location:
        return "Location not provided for news lookup."

    target_day = _parse_iso_date(target_date) or _today_utc()
    keywords = [
        token.strip().lower()
        for token in (interests or "").split(",")
        if token.strip()
    ]

    response = requests.get(
        GOOGLE_NEWS_RSS,
        params={
            "q": f"{location} events OR festival OR sports OR concert",
            "hl": "en",
            "gl": "US",
            "ceid": "US:en",
        },
        timeout=10,
    )
    response.raise_for_status()

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return f"Unable to parse news feed for {location}."

    items = root.findall(".//item")
    filtered = []
    for item in items:
        pub_date = item.findtext("pubDate", default="")
        if pub_date:
            try:
                published = parsedate_to_datetime(pub_date).astimezone(timezone.utc).date()
                if published != target_day:
                    continue
            except (TypeError, ValueError):
                pass

        title = item.findtext("title", default="Untitled")
        description = item.findtext("description", default="")
        link = item.findtext("link", default="")
        source = item.find("./source")
        source_name = source.text if source is not None else "Local outlet"
        age = _format_news_age(pub_date)
        title_lower = title.lower()
        desc_lower = description.lower()

        if keywords and not any(
            keyword in title_lower or keyword in desc_lower for keyword in keywords
        ):
            continue

        filtered.append(f"- {title} ({source_name}, {age})\n  {link}")

        if len(filtered) == 5:
            break

    if not filtered:
        fallback = [
            item.findtext("title", default="Untitled")
            for item in items[:3]
        ]
        return (
            f"No date-matching headlines found for {location} on {target_day.isoformat()}.\n"
            f"Sample current stories: {', '.join(fallback) if fallback else 'N/A'}."
        )

    return f"City news for {location} on {target_day.isoformat()}:\n" + "\n".join(filtered)


@tool("GetLocalSpots")
def get_local_spots(location: str, interest: str | None = None) -> str:
    """Recommend nearby venues (stadiums, cinemas, malls, parks) within ~8km."""
    coordinates = _lookup_coordinates(location)
    if coordinates is None:
        return f"Unable to locate coordinates for '{location}'."

    lat, lon, pretty_label = coordinates
    query = _overpass_query(lat, lon)
    response = requests.post(
        OVERPASS_ENDPOINT,
        data=query,
        headers={"Content-Type": "text/plain"},
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    spots = []
    seen = set()

    interest_lower = (interest or "").lower()

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name or name in seen:
            continue

        elem_lat = element.get("lat") or element.get("center", {}).get("lat")
        elem_lon = element.get("lon") or element.get("center", {}).get("lon")
        if elem_lat is None or elem_lon is None:
            continue

        distance = _km_distance(lat, lon, elem_lat, elem_lon)
        label = _tag_label(tags)

        score = distance
        if interest_lower:
            if "cricket" in interest_lower and "stadium" in label.lower():
                score -= 2
            if "movie" in interest_lower and "cinema" in label.lower():
                score -= 1.5
            if any(word in interest_lower for word in ("game", "gaming", "mall")) and label == "Mall":
                score -= 1

        spots.append(
            {
                "name": name,
                "label": label,
                "distance": distance,
                "score": max(score, 0),
            }
        )
        seen.add(name)

    if not spots:
        return f"No notable venues were detected within 8km of {pretty_label}."

    spots.sort(key=lambda s: s["score"])
    lines = [
        f"Highlighted venues near {pretty_label} (within ~8 km):",
    ]
    for spot in spots[:7]:
        lines.append(
            f"- {spot['name']} ({spot['label']}) · {spot['distance']:.1f} km away"
        )

    if interest_lower:
        lines.append(f"Interest bias applied for: {interest_lower}.")

    return "\n".join(lines)

