class GeocodeError(Exception):
    """Raised when the Google Geocoding API fails."""


class OneCallError(Exception):
    """Raised when the OWM OneCall API fails."""


class LocationNotFoundError(Exception):
    """Raised when a location cannot be resolved."""
