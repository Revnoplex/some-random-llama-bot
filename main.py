#!./venv/bin/python3.13
import asyncio
import signal
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler
import aiohttp
import discord
import logging
import os
import config
from discord.ext import bridge
import utils
from cogs import information, errors, logs


# function for reloading with systemd
def reload(signum, _):
    print(f"Received {signal.Signals(signum).name} from systemd, reloading....")
    # noinspection SpellCheckingInspection
    utils.sd_notify(b'RELOADING=1\nMONOTONIC_USEC='+str(time.monotonic_ns() // 1000).encode("utf-8"))
    if sys.argv:
        os.execl(sys.argv[0], sys.argv[0], " ".join(sys.argv[1:]))
    os.execl(sys.executable, sys.executable)


# function for stopping or restarting with systemd
def stop(signum, _):
    print(f"Received {signal.Signals(signum).name} from systemd, shutting down....")
    utils.sd_notify(b'STOPPING=1')
    sys.exit('The bot has exited as requested from systemd')


if __name__ == "__main__":
    # Add signal handlers if running as systemd service
    if config.systemd_service:
        # noinspection PyTypeChecker
        signal.signal(signal.SIGHUP, reload)
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, stop)
    # print startup text
    print(f"SomeRandomLlamaBot {config.version}")
    print(config.copyright_line)
    print("starting up....")

# specify the client and intents
# noinspection SpellCheckingInspection
intents = discord.Intents.default() + discord.Intents.message_content
client: bridge.Bot = bridge.Bot(command_prefix=config.prefix, intents=intents,
                                help_command=information.RevnobotHelp3(), debug_guilds=config.slash_guilds,
                                max_messages=10**3, enable_debug_events=config.debug_mode)
# noinspection SpellCheckingInspection
client.u_stoopid_counter = 0
client.stay_in = []
client.active_voice_text_channels = {}
# setup logging for the pycord library
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(filename='./logs/discord.log', encoding='utf-8', mode='w', maxBytes=config.max_log_size,
                              backupCount=config.max_log_backups)
handler.rotator = logs.rotator
handler.namer = logs.namer
# noinspection SpellCheckingInspection
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# load in every cog in ./cogs directory
if __name__ == "__main__":
    cogs_folder = list(os.listdir('./cogs'))
    for filename in cogs_folder:
        if filename.endswith('.py'):
            # disable the debug cog if the bot is not executed with the "debug mode" parameter set to true in the
            # config json file
            if filename == "debug.py" and not config.debug_mode:
                continue
            # 2 methods are used to handle cog errors because the pycord devs keep changing how they work
            try:
                cog_status = client.load_extension(f'cogs.{filename[:-3]}')
            except discord.ExtensionFailed as cog_err:
                cog_error = cog_err
            else:
                if isinstance(cog_status, dict):
                    cog_error = cog_status.get(f'cogs.{filename[:-3]}')
                else:
                    cog_error = None
            if isinstance(cog_error, Exception):
                if isinstance(cog_error, discord.ExtensionFailed):
                    if isinstance(cog_error.original, SyntaxError):
                        print(f"\aSyntax Error! Please check line {cog_error.original.lineno} from column "
                              f"{cog_error.original.offset} in "
                              f"{cog_error.original.filename}\nHint: {cog_error.original.msg}", file=sys.stderr)
                        if (cog_error.original.filename and cog_error.original.lineno is not None and
                                cog_error.original.offset is not None and cog_error.original.end_offset is not None):
                            with open(cog_error.original.filename) as error_file:
                                error_line = error_file.readlines()[cog_error.original.lineno-1]
                                print(f'{error_line}{" "*(cog_error.original.offset-1)}'
                                      f'{"^"*(cog_error.original.end_offset-1-cog_error.original.offset-1)}',
                                      file=sys.stderr)
                        exit(1)
                    else:
                        traceback_string = "\n".join(traceback.format_tb(cog_error.__traceback__))
                        if isinstance(cog_error, discord.ExtensionFailed):
                            traceback_string = "\n".join(traceback.format_tb(cog_error.original.__traceback__))
                        print(f'Oops, a cog raised an error:\n{type(cog_error.original).__name__}: '
                              f'{cog_error.original}\nTraceback:\n'
                              f'{traceback_string}', file=sys.stderr)
                else:
                    traceback_string = "\n".join(traceback.format_tb(cog_error.__traceback__))
                    if isinstance(cog_error, discord.ExtensionFailed):
                        traceback_string = "\n".join(traceback.format_tb(cog_error.original.__traceback__))
                    print(f'Oops, a cog raised an error:\n{type(cog_error).__name__}: {cog_error}\nTraceback:\n'
                          f'{traceback_string}', file=sys.stderr)


#   send event errors to a special handler in cogs.error (error cog)
@client.event
async def on_error(event_name: str, *args, **kwargs):
    await errors.Errors(client).event_error(event_name, sys.exc_info()[1], args, kwargs)


# Attempt to connect and start the client.
# The client will not start and will be halted for one of the following reasons:

#   - The program is running as root: this will display a warning message and sound the terminal bell. The client can
#     still be started by typing the specified phrase.

#   - A connection to discord cannot be established: most likely to happen if the bot starts without an internet
#     connection. The program will restart and reattempt to connect every 30 seconds
if __name__ == "__main__":
    if os.geteuid() == 0:
        try:
            security_message = ["@@@@@@@@@@@@@@@@@@",
                                "@                @",
                                "@   Attention!   @",
                                "@                @",
                                "@@@@@@@@@@@@@@@@@@"]
            print("\a\033[1;31;5m"+"\n".join(security_message)+"\033[0m")
            print("\033[1;94mWarning! you are trying to run this program as root! Which can pose a "
                  "\033[1;91;5mDANGEROUS\033[0m\033[1;94m risk for "
                  "an attacker to gain full access to this system. \n\033[1;95mIf the token provided belongs to an "
                  "application that is "
                  
                  "owned by a discord account that is not yours, \nthen that account could have access to "
                  "your entire system!\033[0m")
            security_input = input("\033[1;93mTo Continue (\033[1;91;5mDISCOURAGED\033[0m\033[1;93m), "
                                   "Please exactly "
                                   "type the following phrase: \"Yes, I understand this is VeRy unsAFe....\": "
                                   "\033[1;91m")
            print("\033[0m")
            if security_input != "Yes, I understand this is VeRy unsAFe....":
                print("aborting....")
                exit(0)
        except KeyboardInterrupt:
            # noinspection SpellCheckingInspection
            print("\033[0maborting....")
            exit(0)
    try:
        client.run(config.token)
    except aiohttp.ClientConnectionError:
        if config.systemd_service:
            utils.sd_notify(b"STATUS=Offline: Unable to connect to discord")
        try:
            for seconds in reversed(range(30)):
                utils.print_error(f"\rCould not connect to discord! Restarting bot in {seconds} seconds....", end='')
                time.sleep(1)
            print("\033[0m")
            os.execl(sys.executable, sys.executable, sys.argv[0])
        except KeyboardInterrupt:
            pass
    except (aiohttp.ServerTimeoutError, asyncio.TimeoutError, TimeoutError):
        if config.systemd_service:
            utils.sd_notify(b"STATUS=Offline: Unable to connect to discord")
        try:
            for seconds in reversed(range(30)):
                utils.print_error(f"\rCould not connect to discord! The connection timed out. "
                                  f"Restarting bot in {seconds} seconds....", end='')
                time.sleep(1)
            print("\033[0m")
            os.execl(sys.executable, sys.executable, sys.argv[0])
        except KeyboardInterrupt:
            pass
    except discord.HTTPException as error:
        utils.print_error(f"Something went wrong! There was an issue logging into discord: {error}")
        asyncio.run(utils.print_http_error(error))
        raise
    except BaseException as error:
        utils.print_error(f"Something went wrong! There was an issue while initialising: {error}")
        raise
