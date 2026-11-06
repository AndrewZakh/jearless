"""The base error: reaches the user as a single line, without a traceback."""


class JearlessError(RuntimeError):
    """Parent of all jearless errors — the CLI catches it and prints it briefly."""
