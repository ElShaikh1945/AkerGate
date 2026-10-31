"""
AkerGate - Internationalization (i18n) Engine
Loads translations from modular JSON files and supports easy addition of new languages.
Zero external dependencies.
Zero emojis.
"""

import json
from pathlib import Path
from akergate.config import load_config, save_config

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

_current_lang = None
_translations_cache = {}

def get_locales_dir() -> Path:
    return LOCALES_DIR

def list_available_languages() -> list[str]:
    """Returns list of available language codes (e.g. ['en', 'ar'])."""
    if not LOCALES_DIR.exists():
        return ["en"]
    return [p.stem for p in LOCALES_DIR.glob("*.json")]

def load_locale(lang: str) -> dict:
    """Loads and caches translation dictionary for a specific language."""
    if lang in _translations_cache:
        return _translations_cache[lang]
        
    locale_file = LOCALES_DIR / f"{lang}.json"
    if not locale_file.exists():
        # Fallback to English
        locale_file = LOCALES_DIR / "en.json"
        
    if locale_file.exists():
        try:
            data = json.loads(locale_file.read_text(encoding="utf-8"))
            _translations_cache[lang] = data
            return data
        except Exception:
            pass
            
    return {}

def get_current_language() -> str:
    """Returns the currently active language code."""
    global _current_lang
    if _current_lang is not None:
        return _current_lang
        
    config = load_config()
    lang = config.get("language", "en")
    _current_lang = lang
    return lang

def set_language(lang: str) -> bool:
    """Sets active language and persists to config."""
    global _current_lang
    available = list_available_languages()
    if lang not in available:
        return False
        
    _current_lang = lang
    config = load_config()
    config["language"] = lang
    save_config(config)
    return True

def t(key: str, **kwargs) -> str:
    """
    Translates a dot-notated key (e.g. 'dashboard.title' or 'services.failsafe_tick').
    Falls back to English if key is missing in active language.
    Applies string formatting with kwargs if provided.
    """
    lang = get_current_language()
    trans = load_locale(lang)
    en_trans = load_locale("en")
    
    parts = key.split(".")
    val = trans
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            val = None
            break
            
    # Fallback to English if not found
    if val is None:
        val = en_trans
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                val = key
                break
                
    if isinstance(val, str) and kwargs:
        try:
            return val.format(**kwargs)
        except Exception:
            return val
            
    return str(val) if val is not None else key
