import os
from pathlib import Path

from .bot import make_bot
from .config import Config
import sys

def main():
    if 'DISCORD_STATIC_BOT_TOKEN' in os.environ:
        config = Config.load_from_environment()
    else:
        config = Config.load(Path('token.txt'), Path(sys.argv[1]))
    make_bot(config).run(config.token)
