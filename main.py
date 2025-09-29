import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from skel_telegram_bot.bot import main


if __name__ == "__main__":
    main()
