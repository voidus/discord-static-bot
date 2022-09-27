from pathlib import Path

from .bot import make_bot
from .config import Config
import sys

def main():
    config = Config.load(Path('token.txt'), Path(sys.argv[1]))
    make_bot(config).run(config.token)
