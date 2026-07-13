import logging
import sys


class _CleanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.levelno == logging.DEBUG:
            return f"DEBUG: {msg}"
        if record.levelno == logging.WARNING:
            return f"WARNING: {msg}"
        if record.levelno >= logging.ERROR:
            return f"ERROR: {msg}"
        return msg


def setup_logging(verbose: bool) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_CleanFormatter())
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, handlers=[handler])
    if not verbose:
        logging.getLogger("telethon").setLevel(logging.WARNING)
