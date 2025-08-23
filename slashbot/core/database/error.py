class WikiFeetModelNotFoundError(Exception):
    """Raised when a model is not found on WikiFeet during scraping."""


class WikiFeetModelNotInDatabaseError(Exception):
    """Raised when a model is not found in the local database."""


class WikiFeetDataParseError(Exception):
    """Raised when there is an error parsing model data from WikiFeet."""


class WikiFeetDuplicateCommentError(Exception):
    """Raised when attempting to add a duplicate comment to the database."""


class WikiFeetDuplicateImageError(Exception):
    """Raised when attempting to add a duplicate image to the database."""


class WikiFeetDuplicateModelError(Exception):
    """Raised when attempting to add a duplicate model to the database."""
