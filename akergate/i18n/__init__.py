"""
AkerGate i18n package.
"""

from akergate.i18n.manager import (
    t,
    get_current_language,
    set_language,
    list_available_languages,
    get_locales_dir
)

__all__ = [
    "t",
    "get_current_language",
    "set_language",
    "list_available_languages",
    "get_locales_dir"
]
