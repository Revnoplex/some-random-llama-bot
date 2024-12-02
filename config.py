import datetime
import os
import sys
from typing import Optional, Literal, NamedTuple
from discord.ext import commands
from dotenv import load_dotenv
import json

with open("./json/config-template.json") as sysinfo_check_file:
    sysinfo_check: dict = json.load(sysinfo_check_file)

if not os.path.isfile('./json/config.json'):
    with open('./json/config.json', "w") as w_sysinfo:
        json.dump(sysinfo_check, w_sysinfo, indent=2)
    print("Warning: json/config.json file not found. Created config.json using default template")

with open('./json/config.json') as sysinfo_file:
    sysinfo: dict = json.load(sysinfo_file)

for key in sysinfo_check.keys():
    if key not in sysinfo.keys():
        print("New config field not present in old config.json!\n"
              "Attempting to fix the issue by copying the field from the template...")
        sysinfo[key] = sysinfo_check[key]
        with open('./json/config.json', "w") as w_sysinfo:
            json.dump(sysinfo, w_sysinfo, ensure_ascii=False, indent=2)
with open('./json/version-info.json') as version_info_handle:
    raw_version_info: dict = json.load(version_info_handle)
with open('./json/emoji-database.json') as emoji_db_handle:
    emoji_db: dict = json.load(emoji_db_handle)


#   root exception for all the bot code
# noinspection SpellCheckingInspection
class RevnobotException(Exception):
    pass


class NoToken(RevnobotException):
    def __init__(self):
        # noinspection SpellCheckingInspection
        super().__init__('No discord login token was provided. Please specify it under the environmental variable: '
                         f'"BOT_TOKEN"')


#   all cogs will inherit from this class
# noinspection SpellCheckingInspection
class RevnobotCog(commands.Cog):
    def __init__(self, description: str = "No description provided", icon: str = "\U00002699"):
        self.description = description
        self.icon = icon
        self.hidden = False


class VersionInfo(NamedTuple):
    major: int
    minor: int
    micro: int
    version_code: Literal["alpha", "beta", "full"]


version_info = VersionInfo(**raw_version_info)

#   tests
load_dotenv("./.env")
# noinspection SpellCheckingInspection
token: Optional[str] = os.getenv(f"BOT_TOKEN")
prefix: str = sysinfo["prefix"]
# noinspection SpellCheckingInspection
version_string: str = f'{version_info.major}.{version_info.minor}.{version_info.micro}'
github_version: str = f'v{version_string}'
version: str = f'{version_string} {version_info.version_code}'
version_code: str = version_info.version_code
user_status_emojis = emoji_db["user status"]
user_badge_emojis = emoji_db["user badges"]
debug_mode: bool = sysinfo["debug mode"]
log_messages: bool = sysinfo["log messages"]
logging_excluded: list = sysinfo["logging excluded"]
ollama_server: str = sysinfo["ollama_server"]
ascii_colour = "\033[0m"
version_int = 0
if version_code == "alpha":
    ascii_colour = "\033[34;1m"
    version_int = 2
elif version_code == "beta":
    ascii_colour = "\033[31;1m"
    version_int = 1
elif version_code == "full":
    ascii_colour = "\033[0m"
    version_int = 0

if token is None or len(token) < 1:
    raise NoToken()

up_since = None

if os.path.isfile("./json/up-since.json"):
    with open("./json/up-since.json") as up_since_file:
        up_since_data: dict = json.load(up_since_file)
    if up_since_data.get('pid') == str(os.getpid()):
        up_since = datetime.datetime.fromtimestamp(up_since_data["up_since"])
        print("Restoring saved uptime....")
if up_since is None:
    up_since = datetime.datetime.now()
    with open("./json/up-since.json", "w") as w_up_since_file:
        json.dump({"pid": str(os.getpid()), "up_since": int(up_since.timestamp())}, w_up_since_file, indent=2)


#   set default embed colour
embed_colour_default = int("0x" + (sysinfo['def_embed_colour']).replace('#', ''), 16)

#   set cooldown defaults from json
default_cooldown_rate = int(sysinfo["default_cooldown_rate"])
default_cooldown_time = float(sysinfo["default_cooldown_time"])
default_cooldown_options = {'rate': default_cooldown_rate, 'per': default_cooldown_time,
                            'type': commands.BucketType.channel}

systemd_service = "--systemd" in sys.argv

#   set copyright year
copyright_year = datetime.datetime.now().year

# set copyright text
copyright_line: str = sysinfo["copyright line"].format(copyright_year=copyright_year)

#   sync a default footer to all embeds
# noinspection SpellCheckingInspection
default_footer = f'SomeRandomLlamaBot {github_version} - {copyright_line}'

#   status for when bot starts up
prefix_status = f"{prefix}help"
prefix_status_with = prefix_status + " | "
default_status = prefix_status_with + "in {guild_count} servers"
alt_status = prefix_status_with + " Version {version_string}"

dt_string = "%A, %B %d %Y, %H:%M:%S UTC"

timezone = datetime.timezone(datetime.timedelta(hours=10))

uppercase_phrases = ["pfp", "pp", "tnt", "id"]
dont_replace = ["g-send-embed", "g-send", "un-mute"]

max_log_size = 512*1024
max_log_backups = 16

slash_guilds: Optional[list] = sysinfo["slash guilds"]
if slash_guilds is None or len(slash_guilds) < 1:
    slash_guilds = None
