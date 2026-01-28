from __future__ import annotations

from pathlib import Path
from typing import List
import os
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    # Telegram
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    bot_username: str = Field(default="", alias="BOT_USERNAME")  # without @
    admin_tg_ids: List[int] = Field(default_factory=list, alias="ADMIN_TG_IDS")  # comma-separated
    ceo_tg_ids: List[int] = Field(default_factory=list, alias="CEO_TG_IDS")      # comma-separated

    # Subscription gate
    required_channel: str = Field(default="", alias="REQUIRED_CHANNEL")  # @username or https://t.me/...
    required_group: str = Field(default="", alias="REQUIRED_GROUP")
    required_channel_url: str = Field(default="", alias="REQUIRED_CHANNEL_URL")
    required_group_url: str = Field(default="", alias="REQUIRED_GROUP_URL")

    # Database
    # Database
    database_url: str = Field(default="", alias="DATABASE_URL")
    sqlite_path: str = Field(default="data/bot.db", alias="SQLITE_PATH")


    # Admin panel (aiohttp, optional)
    admin_panel_host: str = Field(default="127.0.0.1", alias="ADMIN_PANEL_HOST")
    admin_panel_port: int = Field(default=8080, alias="ADMIN_PANEL_PORT")
    admin_panel_public_url: str = Field(default="", alias="ADMIN_PANEL_PUBLIC_URL")
    admin_panel_token: str = Field(default="", alias="ADMIN_PANEL_TOKEN")

    # MiniApp (aiohttp)
    # MiniApp (aiohttp)
    # MiniApp (aiohttp)
    miniapp_host: str = Field(default="0.0.0.0", alias="MINIAPP_HOST")
    miniapp_port: int = Field(default_factory=lambda: int(os.getenv("PORT", os.getenv("MINIAPP_PORT", "8000"))), alias="MINIAPP_PORT")
    miniapp_public_url: str = Field(default="", alias="MINIAPP_PUBLIC_URL")
    miniapp_dev_bypass: bool = Field(default=False, alias="MINIAPP_DEV_BYPASS")



    # UX
    emoji_mode_default: bool = Field(default=True, alias="EMOJI_MODE_DEFAULT")


    @field_validator("admin_tg_ids", "ceo_tg_ids", mode="before")
    @classmethod
    def _parse_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return [int(x) for x in v]
        s = str(v).strip()
        if not s:
            return []
        out: list[int] = []
        for part in s.split(","):
            part = part.strip()
            if part and part.lstrip("-").isdigit():
                out.append(int(part))
        return out

    @staticmethod
    def _normalize_url(value: str) -> str:
        v = (value or "").strip()
        if not v:
            return ""
        for prefix in ("ADMIN_PANEL_PUBLIC_URL=", "MINIAPP_PUBLIC_URL="):
            if v.startswith(prefix):
                v = v[len(prefix):].strip()
        return v

    @property
    def sqlite_url(self) -> str:
        p = Path(self.sqlite_path)
        if not p.is_absolute():
            p = Path.cwd() / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{p.as_posix()}"

    @property
    def effective_admin_panel_url(self) -> str:
        pub = self._normalize_url(self.admin_panel_public_url)
        if pub:
            return pub.rstrip("/")
        return f"http://{self.admin_panel_host}:{self.admin_panel_port}".rstrip("/")

    @property
    def effective_miniapp_url(self) -> str:
        pub = self._normalize_url(self.miniapp_public_url)
        if pub:
            return pub.rstrip("/")
        return f"http://{self.miniapp_host}:{self.miniapp_port}".rstrip("/")


settings = Settings()
