"""Configuration management for cairn-mail."""

from .loader import ConfigLoader
from .tags import (
    DEFAULT_TAGS,
    CATEGORY_COLORS,
    merge_tags,
    get_tag_color,
    get_tag_names,
    get_tags_for_prompt,
)

__all__ = [
    "ConfigLoader",
    "DEFAULT_TAGS",
    "CATEGORY_COLORS",
    "merge_tags",
    "get_tag_color",
    "get_tag_names",
    "get_tags_for_prompt",
]
