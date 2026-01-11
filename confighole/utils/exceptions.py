"""Custom exceptions for ConfigHole.

This module defines all custom exceptions used throughout the application.
"""


class ConfigurationError(Exception):
    """Raised when there are configuration validation errors.

    This exception is raised when:
    - Required configuration fields are missing
    - Configuration values are invalid
    - Password resolution fails
    """
