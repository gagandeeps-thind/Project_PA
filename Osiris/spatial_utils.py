import math
from datetime import datetime

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates distance between two GPS points in kilometers."""
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_polygon_area_sqkm(coords: list) -> float:
    """
    Approximate area of a polygon using the Shoelace formula.
    Note: This is a flat-earth approximation for the MVP.
    Production will use PostGIS ST_Area.
    """
    if len(coords) < 3:
        return 0.0

    # Convert coordinates to approximate km on a Cartesian plane
    R = 6371.0
    avg_lat = math.radians(sum(c.lat for c in coords) / len(coords))
    
    points = []
    for c in coords:
        x = R * math.radians(c.lng) * math.cos(avg_lat)
        y = R * math.radians(c.lat)
        points.append((x, y))
        
    area = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
        
    return abs(area) / 2.0

def check_velocity_violation(coords: list, max_speed_kmh: float = 25.0) -> bool:
    """Anti-Cheat: Returns True if the user exceeded the max speed limit between points."""
    for i in range(1, len(coords)):
        dist = haversine_distance(coords[i-1].lat, coords[i-1].lng, coords[i].lat, coords[i].lng)
        time_diff_hours = (coords[i].timestamp - coords[i-1].timestamp).total_seconds() / 3600.0
        if time_diff_hours > 0:
            speed = dist / time_diff_hours
            if speed > max_speed_kmh:
                return True # Violation detected!
    return False