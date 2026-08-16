from enum import StrEnum


class Layout(StrEnum):
    DAILY = "daily"
    SINGLE = "single"


# folder-key stand-in for `threads dump` filenames under the single layout
SINGLE_SLICE = "all"
