import math

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

def point_in_polygon(x: float, y: float, polygon: list) -> bool:
    """Ray casting algorithm to determine if a point (x=lng, y=lat) is inside a polygon."""
    n = len(polygon)
    inside = False
    
    def get_coords(pt):
        if isinstance(pt, dict):
            return pt['lng'], pt['lat']
        return pt.lng, pt.lat

    p1x, p1y = get_coords(polygon[0])
    for i in range(1, n + 1):
        p2x, p2y = get_coords(polygon[i % n])
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def is_polygon_swallowed(target_coords: list, challenger_coords: list) -> bool:
    """
    Checks if a target polygon is completely swallowed by a challenger polygon.
    Returns True if ALL points of the target_coords are inside the challenger_coords.
    """
    for pt in target_coords:
        x = pt['lng'] if isinstance(pt, dict) else pt.lng
        y = pt['lat'] if isinstance(pt, dict) else pt.lat
        if not point_in_polygon(x, y, challenger_coords):
            return False
    return True