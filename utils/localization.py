import json
import os
from private import config
import threading  # For thread-safe file writing
from typing import Union, Dict, Any
from loguru import logger

# 語言文件緩存
_translations: Dict[str, Dict[str, str]] = {}
_user_lang_preferences: Dict[str, str] = {}  # user_id (str): lang_code
USER_PREFS_FILE = "private/user_lang_prefs.json"
_prefs_lock = threading.Lock()  # Lock for writing to the preferences file


def _load_user_preferences():
    """從 JSON 文件加載用戶語言偏好到內存"""
    global _user_lang_preferences
    if not os.path.exists(USER_PREFS_FILE):
        logger.info(
            f"'{USER_PREFS_FILE}' not found. Starting with empty user preferences."
        )
        _user_lang_preferences = {}
        return
    try:
        with (
            _prefs_lock
        ):  # Ensure thread-safe reading, though less critical than writing
            with open(USER_PREFS_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                if not content:  # File is empty
                    _user_lang_preferences = {}
                    logger.info(
                        f"'{USER_PREFS_FILE}' is empty. Starting with empty user preferences."
                    )
                else:
                    _user_lang_preferences = json.loads(content)
                    # Ensure keys are strings if they were stored as ints from interaction.user.id
                    _user_lang_preferences = {
                        str(k): v for k, v in _user_lang_preferences.items()
                    }
                    logger.info(f"已成功從 '{USER_PREFS_FILE}' 加載用戶語言偏好。")
    except json.JSONDecodeError:
        logger.error(f"錯誤：解析 '{USER_PREFS_FILE}' 失敗。將使用空的用戶偏好。")
        _user_lang_preferences = {}
    except Exception as e:
        logger.error(f"加載用戶偏好時發生未知錯誤: {e}")
        _user_lang_preferences = {}


def _save_user_preferences():
    """將內存中的用戶語言偏好保存到 JSON 文件"""
    try:
        with _prefs_lock:  # Thread-safe writing
            # 創建一個要保存的字典副本，確保所有鍵都是字符串
            # 這一步主要是為了調試和確保一致性
            preferences_to_save = {str(k): v for k, v in _user_lang_preferences.items()}

            logger.debug(f"[L10N] Attempting to save: {preferences_to_save}")

            with open(USER_PREFS_FILE, "w", encoding="utf-8") as f:
                json.dump(preferences_to_save, f, ensure_ascii=False, indent=4)

            logger.debug(
                f"[L10N] Successfully saved to '{USER_PREFS_FILE}'. Content: {preferences_to_save}"
            )
    except Exception as e:
        logger.error(f"[L10N] Failed to save to '{USER_PREFS_FILE}': {e}")


def load_language(lang_code: str):
    """加載指定語言的翻譯文件到緩存"""
    if lang_code not in _translations:
        try:
            file_path = os.path.join("locales", f"{lang_code}.json")
            with open(file_path, "r", encoding="utf-8") as f:
                _translations[lang_code] = json.load(f)
                logger.debug(
                    f"[L10N] Successfully loaded language file: {lang_code}.json into _translations['{lang_code}']"
                )
        except FileNotFoundError:
            logger.error(f"[L10N] Language file {lang_code}.json not found.")
            _translations[lang_code] = {}
        except json.JSONDecodeError:
            logger.error(f"[L10N] Failed to parse language file {lang_code}.json.")
            _translations[lang_code] = {}
    else:
        logger.debug(
            f"[L10N] Language {lang_code} already in _translations. Skipping load."
        )

    # DEBUG: Print current state of _translations cache after any load attempt or skip
    logger.debug(f"[L10N] Current _translations keys: {list(_translations.keys())}")
    for lc, trans_dict in _translations.items():
        test_key_val = trans_dict.get("user_profile_game_mode", "<TEST_KEY_MISSING>")
        logger.debug(
            f"[L10N]   _translations['{lc}']['user_profile_game_mode']: '{test_key_val}'"
        )


def get_user_language(user_id: Union[int, str]) -> str:
    """獲取用戶的語言偏好，如果未設置則返回預設語言"""
    # Ensure all keys in the global preferences are strings before attempting to get.
    # This is a safeguard against potential pollution from other parts of the code.
    global _user_lang_preferences  # Explicitly state we are working with the global
    current_prefs_copy = dict(
        _user_lang_preferences
    )  # Work on a copy to iterate and modify safely
    cleaned_prefs = {str(k): v for k, v in current_prefs_copy.items()}
    if len(cleaned_prefs) != len(current_prefs_copy):
        logger.warning(
            f"[L10N] Cleaned _user_lang_preferences due to mixed key types. Original count: {len(current_prefs_copy)}, Cleaned count: {len(cleaned_prefs)}"
        )
        _user_lang_preferences = (
            cleaned_prefs  # Update the global with the cleaned version
        )

    logger.debug(f"[L10N] Called for user_id: '{user_id}'")
    # Now _user_lang_preferences should only have string keys.
    logger.debug(
        f"[L10N] Current (potentially cleaned) _user_lang_preferences: {_user_lang_preferences}"
    )

    lang_to_return = _user_lang_preferences.get(
        str(user_id), config.DEFAULT_LANGUAGE
    )  # Ensure lookup key is also string
    logger.debug(f"[L10N] Returning lang: '{lang_to_return}' for user_id: '{user_id}'")
    return lang_to_return


def set_user_language(user_id: Union[int, str], lang_code: str) -> bool:
    """設置用戶的語言偏好"""
    if lang_code not in config.SUPPORTED_LANGUAGES:
        # 也可以在這裡嘗試加載 lang_code，如果 locales 裡有對應文件但未在 SUPPORTED_LANGUAGES 中聲明
        # 但目前嚴格按照 SUPPORTED_LANGUAGES 列表來
        logger.warning(f"嘗試設置不支持的語言 '{lang_code}' 給用戶 {user_id}")
        return False

    _user_lang_preferences[str(user_id)] = lang_code
    if lang_code not in _translations:
        load_language(lang_code)  # 如果該語言尚未加載，則加載它
    logger.info(f"用戶 {user_id} 的語言已設置為: {lang_code}")
    _save_user_preferences()  # Save after setting
    return True


def get_localized_string(
    user_id_or_lang_code: Union[int, str, None],
    key: str,
    default_fallback: str = "",
    *args,
    **kwargs,
) -> str:
    """根據用戶的語言偏好或預設語言獲取翻譯後的文本。

    如果 user_id 為 None，則直接使用預設語言。
    """
    lang_code = config.DEFAULT_LANGUAGE
    if isinstance(user_id_or_lang_code, (int, str)):
        # Try to treat as user_id first
        potential_lang = get_user_language(user_id_or_lang_code)
        if potential_lang in _translations:  # If it's a valid lang from user prefs
            lang_code = potential_lang
        elif (
            str(user_id_or_lang_code) in _translations
        ):  # Else, if it was a direct lang_code string
            lang_code = str(user_id_or_lang_code)
        # If neither, lang_code remains DEFAULT_LANGUAGE
    elif user_id_or_lang_code is None:
        # lang_code remains DEFAULT_LANGUAGE as initialized
        pass

    # Ensure _translations is populated
    if not _translations:
        logger.critical("[L10N] _translations is empty. Attempting to reload.")
        load_language(
            lang_code
        )  # Attempt to reload if empty, might happen on first call if init order is tricky
        if not _translations:
            logger.critical(
                "[L10N] Reload failed, _translations still empty. Returning raw key or fallback."
            )
            # Cannot format if translations are missing. Return unformatted key or fallback.
            return (
                default_fallback
                if default_fallback
                else f"<missing_translations_for_key: {key}>"
            )

    localized_string = _translations.get(lang_code, {}).get(key)

    if localized_string is None:
        # Try fallback to default language (e.g., English) if not already using it
        if (
            lang_code != config.DEFAULT_LANGUAGE
            and config.DEFAULT_LANGUAGE in _translations
        ):
            localized_string = _translations[config.DEFAULT_LANGUAGE].get(key)

        # If still not found, use the provided default_fallback
        if localized_string is None:
            localized_string = default_fallback
            # If default_fallback was also empty, it means the key is truly missing.
            if (
                not localized_string
            ):  # Checks if default_fallback was also empty or None
                logger.warning(
                    f"[L10N] Key '{key}' not found in lang '{lang_code}' or default '{config.DEFAULT_LANGUAGE}', and no fallback string provided. Returning placeholder."
                )
                return f"<translation_missing: {key}>"

    try:
        # DEBUGGING LOG STATEMENT
        logger.debug(f"[L10N PRE-FORMAT] Key: '{key}', Lang: '{lang_code}'")
        logger.debug(f"[L10N PRE-FORMAT] Raw String: '{localized_string}'")
        logger.debug(f"[L10N PRE-FORMAT] Args: {args} (Type: {type(args)})")
        logger.debug(f"[L10N PRE-FORMAT] Kwargs: {kwargs} (Type: {type(kwargs)})")

        if args or kwargs:  # Only call format if there are args or kwargs
            return localized_string.format(*args, **kwargs)
        return localized_string
    except (
        IndexError,
        KeyError,
        TypeError,
    ) as e:  # Added TypeError for bad keyword args
        # logger.error(f"[L10N] Formatting key='{key}', raw_string='{localized_string}', args={args}, kwargs={kwargs} FAILED: {e}")
        return (
            f"<formatting_error: {key} ({e.__class__.__name__})>"  # Include error type
        )


# 初始加載預設語言 和用戶偏好
_load_user_preferences()  # Load user preferences first

load_language(config.DEFAULT_LANGUAGE)
# 你也可以在這裡加載所有 SUPPORTED_LANGUAGES
for lang in config.SUPPORTED_LANGUAGES:
    if lang not in _translations:
        load_language(lang)

# Alias for convenience
lstr = get_localized_string

# 方便 cogs 或 bot 直接使用的函數 (如果不想處理 user_id)
# 但通常建議在 cog 命令中傳遞 ctx.author.id
# def get_lstr(ctx, key, *args):
#     return get_localized_string(ctx.author.id, key, *args)
