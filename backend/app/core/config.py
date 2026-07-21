from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pydantic

# Pydantic v2 moved BaseSettings to pydantic-settings
if pydantic.__version__.startswith("2"):
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field
else:
    from pydantic import BaseSettings, Field
    SettingsConfigDict = None  # not needed for v1


class ParserSettings(BaseSettings):
    encoding: str = "utf-8"
    errors: str = "ignore"
    hash_algorithm: str = "sha256"

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(env_prefix="EDITH_PARSER_", case_sensitive=False)
    else:
        class Config:
            env_prefix = "EDITH_PARSER_"
            case_sensitive = False


class AISettings(BaseSettings):
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 1024
    api_key: Optional[str] = None
    api_base: Optional[str] = None

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(env_prefix="EDITH_AI__", case_sensitive=False)
    else:
        class Config:
            env_prefix = "EDITH_AI__"
            case_sensitive = False


class AppConfig(BaseSettings):
    db_directory: Path = Path("data")
    db_filename: str = "edith.db"

    logging_level: str = "INFO"
    logging_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging_file: Optional[Path] = None

    cache_directory: Path = Path(".cache")

    parser: ParserSettings = ParserSettings()
    ai: AISettings = AISettings()

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(env_prefix="EDITH_", case_sensitive=False)
    else:
        class Config:
            env_prefix = "EDITH_"
            case_sensitive = False

    @property
    def db_path(self) -> Path:
        return self.db_directory / self.db_filename


config = AppConfig()

logger = logging.getLogger("edith")
logger.setLevel(config.logging_level)

if not logger.handlers:
    formatter = logging.Formatter(config.logging_format)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(config.logging_level)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if config.logging_file is not None:
        file_handler = logging.FileHandler(config.logging_file)
        file_handler.setLevel(config.logging_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
