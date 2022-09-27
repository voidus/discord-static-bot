import json
from pathlib import Path

from discord_static_bot.config import Config


def test_load(tmp_path: Path):
    token_file = tmp_path / "token"
    token = "tttttoken"
    token_file.write_text(token)

    config_file = tmp_path / "config"
    config = {
        "guild_id": 1,
        "category_id": 2,
        "admin_role_id": 3,
        "bots_role_id": 4,
        "blacklist_role_id": "foo",
        "whitelist_role_id": "bar",
        "one_channel_role_id": "baz",
    }
    config_file.write_text(json.dumps(config))

    actual = Config.load
