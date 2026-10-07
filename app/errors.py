class InvalidFileError(Exception):
    """The uploaded file can't be read as a valid Shapefile ZIP / KML / KMZ.

    The message is safe to show to the client.
    """
