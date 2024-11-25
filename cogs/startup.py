import datetime
import platform
import signal
import traceback
import discord
import asyncio
import aioconsole
import os
import sys
from discord.ext import commands, bridge
import main
import utils
from cogs.logs import bot_logger, error_logging
import config


async def stop(signum, client):
    print(f"Received {signal.Signals(signum).name} from systemd, shutting down....")
    utils.sd_notify(b'STOPPING=1')
    await client.close()
    sys.exit('The bot has exited as requested from systemd')


class InputConsoleException(config.RevnobotException):
    pass


class BadArguments(InputConsoleException):
    def __init__(self, req_arguments: list):
        self.arguments = req_arguments
        super().__init__(f'bad arguments were provided: you need to give {len(req_arguments)} arguments')


class Startup(config.RevnobotCog):
    def __init__(self, client: bridge.Bot):
        self.client = client
        self.servers = 0
        self.description = "The module containing boot operations"
        self.icon = "\U0001F504"
        self.hidden = True

    @commands.Cog.listener()
    async def on_connect(self):
        if config.systemd_service:
            for sig in [signal.SIGINT, signal.SIGTERM]:
                self.client.loop.add_signal_handler(
                    sig, lambda: asyncio.ensure_future(stop(sig, self.client))
                )
        print(f"Logged on as\033[1;92m {self.client.user}\033[0m")
        bot_logger.info("Connected....")
        if self.client.auto_sync_commands:
            print("\033[1;94mLoading application commands....\033[0m")
            try:
                await self.client.sync_commands()
            except discord.DiscordException as error:
                if isinstance(error, discord.HTTPException) and error.status == 405:
                    print(
                        "\r\033[1;93mApplication commands registered, but guild command permissions won't work\033[0m"
                    )
                    bot_logger.warning("Application commands registered, but guild command permissions won't work")
                else:
                    tb = "\n".join(traceback.format_tb(error.__traceback__))
                    oneline_tb = (
                        "\\n".join(
                            [line.replace('\n', '') for line in traceback.format_tb(error.__traceback__)]
                        )
                    )
                    print(
                        f'\rCould not load application commands!: {type(error).__name__}: {error} \n Full Traceback:'
                        f'{tb}', file=sys.stderr)
                    error_logging.info(f'Could not load application commands!: {type(error).__name__}: {error}. '
                                       f'Full Traceback: {oneline_tb}')
                    bot_logger.error(f'Could not load application commands!: {type(error).__name__}: {error}. Full '
                                     f'traceback in errors.log')

            else:
                bot_logger.info("Application commands registered successfully")
                print("\033[1;92mApplication commands registered successfully\033[0m")

    @commands.Cog.listener()
    async def on_ready(self):
        if config.systemd_service:
            utils.sd_notify(
                b"READY=1\nSTATUS=Logged on as " + self.client.user.__str__().encode("utf-8") + b". Connected to "
                + str(len(self.client.guilds)).encode("utf-8") + b" guilds and " +
                str(len(self.client.users)).encode("utf-8") + b" users"
            )
        bot_logger.info("Ready....")
        utils.check_guilds(self.client, log=bot_logger)
        print('\033[0mConnected to' + f"\033[1;94m {len(self.client.guilds)}" + f'\033[0m guilds and '
                                                                                f'\033[1;92m{len(self.client.users)}'
                                                                                f'\033[0m users:')
        guild_names = []
        async for g in self.client.fetch_guilds(limit=None):
            if g.name is None:
                guild_names.append("\033[1;31mCould not get guild name\033[1;94m")
            else:
                guild_names.append(g.name)
        print(f'\033[1;94m{", ".join(guild_names)}\033[0m')
        await self.client.change_presence(
            activity=discord.Game(config.default_status.format(guild_count=len(self.client.guilds)))
        )

        async def debug_loop():
            client = self.client

            class CliCommands:
                def __init__(self):
                    # noinspection SpellCheckingInspection
                    self.aliases = {
                                    "q": ["exit", "quit", "stop"],
                                    "restart": ["reboot", "relaunch", "re-launch"],
                                    "g_send": ["send", "message", "dm", "g-send", "gsend"],
                                    "about": ["botinfo", "bot-info", 'bot_info', "uname"],
                                    "_eval": ["eval"],
                                    "eval_async": ["eval-async", "async_eval", "async-eval"]
                                    }

                async def help(self, _):
                    """displays this message"""
                    # arguments = args[1]
                    raw_class = dir(self)
                    cmds = [obj for obj in raw_class if not obj.startswith('__')]
                    print("here is a list of executable commands:")
                    for cmd in cmds:
                        cmd_attr = getattr(self, cmd)
                        if callable(cmd_attr):
                            doc = cmd_attr.__doc__
                            print(f'{cmd.strip("_")} - {doc}')

                @staticmethod
                async def g_send(arguments):
                    """send a message to a channel"""
                    if len(arguments) < 2:
                        raise BadArguments(['channel', 'content'])
                    send_channel = arguments[0]
                    if not str(send_channel).isdecimal():
                        print("This is not a discord ID!")
                        return
                    else:
                        send_channel = int(send_channel)
                    send_content = " ".join(arguments[1:])
                    the_get_channel = client.get_channel(int(send_channel))
                    user = None
                    if the_get_channel is None:
                        try:
                            await client.fetch_user(send_channel)
                        except discord.NotFound:
                            print("User not found! Note, the bot cannot dm users who do not share any server with "
                                  "this bot")
                        user = client.get_user(send_channel)
                        if user is None:
                            print("Channel not found!")
                            return
                        else:
                            the_get_channel = user.dm_channel
                            if the_get_channel is None:
                                try:
                                    the_get_channel = await user.create_dm()
                                except discord.HTTPException as dm_err:
                                    print(f"Could not send message (discord error code: {dm_err.code}): {dm_err.text}")
                                    return
                    if len(send_content) > 2000:
                        print('Message is too long. must be 2000 characters or less')
                    else:
                        try:
                            await the_get_channel.send(send_content)
                        except discord.HTTPException as channel_err:
                            print(f"Could not send message (discord error code: {channel_err.code}): "
                                  f"{channel_err.text}")
                            return
                        if user is not None:
                            user_name = f"{user.name}#{user.discriminator}" if int(user.discriminator) \
                                else user.name
                            print(f'successfully sent message to {user_name}')
                        else:
                            print(f'successfully sent message to #{the_get_channel.name}')

                @staticmethod
                async def q(_):
                    """shut down the bot"""
                    print("shutting down....")
                    await client.close()
                    sys.exit('The bot has exited via the q command')

                @staticmethod
                async def restart(args):
                    """restart the bot"""
                    print('restarting....')
                    if args:
                        os.execl(args[0], args[0], " ".join(args[1:]))
                    if sys.argv:
                        os.execl(sys.argv[0], sys.argv[0], " ".join(sys.argv[1:]))
                    os.execl(sys.executable, sys.executable)

                # noinspection PyMethodMayBeStatic
                async def _eval(self, args):
                    """Evaluate expressions in the current environment"""
                    # noinspection PyUnusedLocal
                    def eval_env(bot, cls, cmds):
                        return eval(" ".join(cmds))
                    print("Warning: if you open a shell, every second command you type will be executed in the debug "
                          "shell all at once")
                    print("Tip: just press enter every second time, and if you want to exit type exit on the first "
                          "command and press enter twice")
                    result = await client.loop.run_in_executor(None, lambda: eval_env(client, self, args))
                    print(result)

                @staticmethod
                async def about(_):
                    # noinspection SpellCheckingInspection
                    """information about revnobot"""
                    app = await client.application_info()
                    ascii_art = [ascii_line.replace("starting up....",
                                                    'Bot Information') for ascii_line in main.ascii_startup]
                    print("\n".join(ascii_art))
                    print(f'\033[1;97m{client.user.name}\033[0m is a multi purpose bot for testing api '
                          f'functions by \033[1;97m{app.owner}\033[0m')
                    info_list = {"Version": f'{config.version}', "Bot User ID": f'{client.user.id}',
                                 "Developer": f'{app.owner}',
                                 "API Account Created At": f'{utils.dt_readable(client.user.created_at)}',
                                 "Latency": f'{round(client.latency*10**3)}ms',
                                 "Python Version": f'{"{}.{}.{}-{}".format(*tuple(sys.version_info))}',
                                 "Pycord Version": f'{discord.__version__}',
                                 "Guild Count": f'{len(client.guilds)}',
                                 "Up Since": f'{config.up_since.strftime("%A, %B %d %Y, %H:%M:%S")}',
                                 "Uptime": f'{datetime.datetime.now() - config.up_since}'}
                    sysinfo = platform.uname()
                    info_list['OS Type'] = f'{sysinfo.system}'
                    info_list["OS Kernel"] = f'{sysinfo.release}'
                    info_list["System Type"] = f'{sysinfo.machine}'
                    info_list["Platform"] = f'{platform.platform()}'
                    info_list["Architecture"] = f'{", ".join(platform.architecture())}'
                    if sysinfo.system == "Linux":
                        board_info = utils.linux_board_info()
                        info_list["Hardware Model"] = f'{board_info["product_name"]}'
                        info_list["Hardware Vendor"] = f'{board_info["sys_vendor"]}'
                        cpu_info = utils.linux_cpu_info()[0]
                        info_list['CPU Model'] = f'{cpu_info["model name"]}'
                        info_list['Process ID'] = f'{utils.linux_current_pid()}'
                        mem_info = utils.linux_mem_info()
                        util_total_perc = round(mem_info["MemUsed"] / mem_info["MemTotal"] * 100, 2)
                        ram_progress = utils.progress_bar(mem_info["MemUsed"], mem_info["MemTotal"], 20, True)
                        info_list['Utilised/Total RAM'] = f'{utils.byte_units(mem_info["MemUsed"], iec=True)} ' \
                                                          f'({util_total_perc}%) [{ram_progress}]' \
                                                          f' {utils.byte_units(mem_info["MemTotal"], iec=True)} '
                        proc_mem_info = utils.linux_proc_mem_info()
                        bot_total_perc = round(proc_mem_info["Individual"] / mem_info["MemTotal"] * 100, 2)
                        info_list["Bot/Total RAM"] = f'{utils.byte_units(proc_mem_info["Individual"], iec=True)}'\
                            f' ({bot_total_perc}%) ' \
                            f'[{utils.progress_bar(proc_mem_info["Individual"], mem_info["MemTotal"], 20, True)}] ' \
                            f'{utils.byte_units(mem_info["MemTotal"], iec=True)}'
                        bot_util_perc = round(proc_mem_info["Individual"] / mem_info["MemUsed"] * 100, 2)
                        info_list["Bot/Utilised Usage"] = \
                            f'{utils.byte_units(proc_mem_info["Individual"], iec=True)}'\
                            f' ({bot_util_perc}%) ' \
                            f'[{utils.progress_bar(proc_mem_info["Individual"], mem_info["MemUsed"], 20, True)}] ' \
                            f'{utils.byte_units(mem_info["MemUsed"], iec=True)}'
                        try:
                            distro_info = platform.freedesktop_os_release()
                        except OSError:
                            pass
                        else:
                            if distro_info.get("PRETTY_NAME") is not None:
                                info_list["Linux Distro"] = f'{distro_info.get("PRETTY_NAME")}'
                        storage_info: dict = utils.linux_block_dev_info(utils.linux_mount_source('/').name)
                        if storage_info.get("physical volume 1") is not None:
                            volume_block_size = int(storage_info.get("hw_sector_size"))
                            info_list["Volume ID"] = f"{storage_info.get('device id')}"
                            info_list["Volume Name"] = f"{storage_info.get('name')}"
                            info_list["Volume Size"] = \
                                f"{utils.byte_units(int(storage_info.get('size')) * volume_block_size)}"
                            physical_partition: dict = storage_info['physical volume 1']
                            info_list["Physical Partition ID"] = f"{physical_partition.get('device id')}"
                            parent_device: dict = physical_partition.get("parent device")
                            block_size = int(parent_device.get("hw_sector_size"))
                            physical_block_size = int(parent_device.get("hw_sector_size"))
                            info_list["Physical Partition Size"] = \
                                f"{utils.byte_units(int(physical_partition.get('size')) * physical_block_size)}"
                        else:
                            parent_device: dict = storage_info.get("parent device")
                            block_size = int(parent_device.get("hw_sector_size"))
                            info_list['Partition ID'] = f"{storage_info.get('device id')}"
                            info_list["Partition Size"] = \
                                f"{utils.byte_units(int(storage_info.get('size')) * block_size)}"
                        info_list["Main Disk ID"] = f'{parent_device.get("device id")}'
                        info_list["Disk Model"] = f'{parent_device.get("model")}'
                        disk_type = "HDD" if bool(int(parent_device.get("rotational"))) else "SSD"
                        info_list["Disk Type"] = disk_type
                        info_list["Total Disk Size"] = \
                            f"{utils.byte_units(int(parent_device.get('size')) * block_size)}"
                    space_size = 0
                    for name, _ in info_list.items():
                        if len(name) > space_size:
                            space_size = len(name)
                    for name, value in info_list.items():
                        print(f'{name}:{"".join([" " for _ in range(space_size + 4 - len(name))])}{value}')
            cli_commands = CliCommands()
            while True:
                try:
                    input2 = await aioconsole.ainput(f'\033[1;92m{self.client.user}({self.client.user.id})'
                                                     f':\033[1;94m{os.getcwd()}\033[0m> ')
                    if len(input2) > 0:
                        cmd_name = str(input2).split()[0]
                        try:
                            for command in cli_commands.aliases.items():
                                if cmd_name in command[1]:
                                    cmd_name = command[0]
                            if hasattr(cli_commands, cmd_name):
                                try:
                                    to_run = getattr(cli_commands, cmd_name)
                                    await to_run(str(input2).split()[1:])
                                except BadArguments:
                                    print('you did not provide the correct arguments for this command')
                            else:
                                # noinspection SpellCheckingInspection
                                print(f'revnobot cli menu: command "{cmd_name}" not found')
                        except BaseException as err:
                            if isinstance(err, SystemExit):
                                raise
                            if isinstance(err, asyncio.exceptions.CancelledError):
                                raise
                            print(err)
                            print(traceback.format_exc())
                except EOFError:
                    try:
                        input()
                    except EOFError:
                        print("There appears to be no stdin, so the input console will not run")
                        break
                    print("shutting down....")
                    await client.close()
                    sys.exit()
                except RuntimeError:
                    break
                except SystemExit:
                    raise
                except asyncio.exceptions.CancelledError:
                    raise
                except BaseException as fatal_error:
                    print(f'Fatal: {fatal_error}'
                          f'\nInput console was terminated to prevent an infinite loop of getting this error!\n'
                          f'Exception class: {type(fatal_error)}')
                    break
        if not config.systemd_service:
            loop = asyncio.get_running_loop()
            await loop.create_task(debug_loop())


def setup(client):
    client.add_cog(Startup(client))
