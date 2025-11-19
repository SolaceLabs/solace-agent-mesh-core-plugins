"""Tool for converting city names to timezone information."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
import yaml
from google.adk.tools import ToolContext

from .services import MapsCoGeocodingService

log = logging.getLogger(__name__)
def _find_timezone_from_coordinates(lat: float, lng: float) -> Optional[str]:
    """
    Find timezone from coordinates using a simple mapping approach.
    
    This is a simplified implementation that maps coordinates to timezones
    based on longitude ranges. For more accurate results, consider using
    an external service or a comprehensive timezone boundary database.
    
    Args:
        lat: Latitude
        lng: Longitude
        
    Returns:
        Timezone string (e.g., 'America/New_York') or None if not found
    """
    # Get all available timezones
    timezones = available_timezones()
    
    # Simple heuristic: use longitude to estimate timezone
    # This is approximate and works best for major cities
    # Longitude ranges roughly correspond to UTC offsets (15 degrees per hour)
    
    # Common timezone mappings based on regions and estimated offset
    # This is a simplified approach - for production use, consider a more comprehensive solution
    timezone_candidates = []
    
    # North America
    if 25 <= lat <= 50 and -130 <= lng <= -60:
        if lng < -120:
            timezone_candidates.extend(['America/Los_Angeles', 'America/Vancouver'])
        elif lng < -105:
            timezone_candidates.extend(['America/Denver', 'America/Phoenix'])
        elif lng < -90:
            timezone_candidates.extend(['America/Chicago', 'America/Mexico_City'])
        else:
            timezone_candidates.extend(['America/New_York', 'America/Toronto'])
    
    # Europe
    elif 35 <= lat <= 70 and -10 <= lng <= 40:
        if lng < 5:
            timezone_candidates.extend(['Europe/London', 'Europe/Dublin'])
        elif lng < 15:
            timezone_candidates.extend(['Europe/Paris', 'Europe/Berlin', 'Europe/Rome'])
        else:
            timezone_candidates.extend(['Europe/Athens', 'Europe/Helsinki', 'Europe/Moscow'])
    
    # Asia
    elif -10 <= lat <= 50 and 60 <= lng <= 150:
        if lng < 80:
            timezone_candidates.extend(['Asia/Kolkata', 'Asia/Dubai'])
        elif lng < 110:
            timezone_candidates.extend(['Asia/Bangkok', 'Asia/Singapore'])
        elif lng < 130:
            timezone_candidates.extend(['Asia/Shanghai', 'Asia/Hong_Kong'])
        else:
            timezone_candidates.extend(['Asia/Tokyo', 'Asia/Seoul'])
    
    # Australia
    elif -45 <= lat <= -10 and 110 <= lng <= 155:
        if lng < 130:
            timezone_candidates.extend(['Australia/Perth'])
        elif lng < 145:
            timezone_candidates.extend(['Australia/Adelaide', 'Australia/Darwin'])
        else:
            timezone_candidates.extend(['Australia/Sydney', 'Australia/Melbourne'])
    
    # South America
    elif -55 <= lat <= 15 and -80 <= lng <= -35:
        if lng < -70:
            timezone_candidates.extend(['America/Lima', 'America/Bogota'])
        elif lng < -55:
            timezone_candidates.extend(['America/Santiago', 'America/La_Paz'])
        else:
            timezone_candidates.extend(['America/Sao_Paulo', 'America/Buenos_Aires'])
    
    # Africa
    elif -35 <= lat <= 35 and -20 <= lng <= 50:
        if lng < 10:
            timezone_candidates.extend(['Africa/Lagos', 'Africa/Accra'])
        elif lng < 30:
            timezone_candidates.extend(['Africa/Cairo', 'Africa/Johannesburg'])
        else:
            timezone_candidates.extend(['Africa/Nairobi', 'Africa/Addis_Ababa'])
    
    # Return first valid candidate that exists in available timezones
    for tz in timezone_candidates:
        if tz in timezones:
            return tz
    
    # Fallback: if no specific timezone found, return a reasonable default based on longitude
    if -180 <= lng < -120:
        return 'America/Los_Angeles'
    elif -120 <= lng < -90:
        return 'America/Denver'
    elif -90 <= lng < -60:
        return 'America/Chicago'
    elif -60 <= lng < -30:
        return 'America/New_York'
    elif -30 <= lng < 0:
        return 'Atlantic/Azores'
    elif 0 <= lng < 30:
        return 'Europe/London'
    elif 30 <= lng < 60:
        return 'Europe/Moscow'
    elif 60 <= lng < 90:
        return 'Asia/Kolkata'
    elif 90 <= lng < 120:
        return 'Asia/Shanghai'
    elif 120 <= lng < 150:
        return 'Asia/Tokyo'
    elif 150 <= lng <= 180:
        return 'Pacific/Auckland'
    
    return None


async def city_to_timezone(
    city: str,
    tool_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Converts a city name to its timezone information, including current UTC offset and DST status.

    Args:
        city (str): The name of the city to look up.
    """
    plugin_name = "sam-geo-information"
    log_identifier = f"[{plugin_name}:city_to_timezone]"
    log.info("%s Received city: '%s'", log_identifier, city)

    if not tool_config:
        return {"status": "error", "message": "Tool configuration is missing."}

    try:
        geocoding_api_key = tool_config.get("geocoding_api_key")
        geocoding_service = MapsCoGeocodingService(api_key=geocoding_api_key)

        locations = await geocoding_service.geocode(city)
        if not locations:
            raise ValueError(f"No locations found for city: {city}")

        results = []
        for loc in locations:
            timezone_str = _find_timezone_from_coordinates(
                lat=loc.latitude, lng=loc.longitude
            )
            if not timezone_str:
                continue

            try:
                timezone = ZoneInfo(timezone_str)
                now = datetime.now(timezone)

                result = {
                    "location": loc.display_name,
                    "timezone": timezone_str,
                    "utc_offset": now.strftime("%z"),
                    "dst_active": bool(now.dst()),
                    "current_time": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
                }
                results.append(result)
            except Exception as tz_error:
                log.warning("%s Could not process timezone %s: %s", log_identifier, timezone_str, tz_error)
                continue

        if not results:
            raise ValueError(
                f"Could not determine timezone for any matching location: {city}"
            )

        message = f"Found timezone information for {len(results)} possible match(es) for {city}:\n\n{yaml.dump(results)}"

        return {"status": "success", "message": message, "results": results}

    except Exception as e:
        log.exception("%s Error looking up timezone: %s", log_identifier, e)
        return {"status": "error", "message": f"Error looking up timezone: {str(e)}"}
