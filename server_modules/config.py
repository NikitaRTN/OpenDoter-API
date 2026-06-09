import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "matches"
PLAYERS_DIR = ROOT / "data" / "players"
JAR_PATH = ROOT / "target" / "stats-0.1.0.jar"
PARSER_PORT = 5600
WEB_PORT = int(os.environ.get("PORT", "8080"))

CONSTANTS = {
    "heroes": ROOT / "constants_heroes.json",
    "items": ROOT / "constants_items.json",
    "abilities": ROOT / "constants_abilities.json",
    "ability_ids": ROOT / "constants_ability_ids.json",
}
CONSTANT_URLS = {
    "heroes": "https://raw.githubusercontent.com/odota/dotaconstants/master/build/heroes.json",
    "items": "https://raw.githubusercontent.com/odota/dotaconstants/master/build/items.json",
    "abilities": "https://raw.githubusercontent.com/odota/dotaconstants/master/build/abilities.json",
    "ability_ids": "https://raw.githubusercontent.com/odota/dotaconstants/master/build/ability_ids.json",
}
