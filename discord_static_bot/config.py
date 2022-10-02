from dataclasses import dataclass, fields
import os
from pathlib import Path
import json
from typing import Optional


@dataclass
class Config:
    token: str
    guild_id: int
    category_id: int
    admin_role_id: int
    bots_role_id: int
    blacklist_role_id: Optional[int]
    whitelist_role_id: Optional[int]
    one_channel_role_id: Optional[int]

    @classmethod
    def load(cls, token_file: Path, config_file: Path):
        with token_file.open() as f:
            token = f.read().replace("\n", "").strip()
        with config_file.open() as f:
            conf = json.load(f)

        return cls(token=token, **{k.lower(): v for k, v in conf.items()})

    @classmethod
    def load_from_environment(cls):
        config = {
            f.name: os.environ.get(f"DISCORD_STATIC_BOT_{f.name.upper()}") for f in fields(cls)
        }
        config = {
            k: int(v) if v and issubclass(int, cls.__dataclass_fields__[k].type) else v
            for k, v in config.items()
        }

        return cls(**config)  # type: ignore
