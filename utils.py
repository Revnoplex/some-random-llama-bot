import datetime
import errno
import logging
import shutil
import socket
import sys
import asyncio
from cogs import errors
from discord.abc import GuildChannel
import json
import os
import pathlib
import traceback
import discord
import config
from typing import Union, Optional, Any, Literal
from discord.ext import commands, bridge
from discord.commands import ApplicationContext
from discord import TextChannel, Thread, DMChannel, PartialMessageable, CategoryChannel, VoiceChannel, Enum
import re


class UtilsException(config.RevnobotException):
    pass


class ConfigFileException(UtilsException):
    pass


class MissingConfigFile(ConfigFileException):
    """Raises if config file for a server is missing
    Args:
        guild (discord.Guild): The guild the config file is missing for
    Attributes:
        guild (discord.Guild): The guild the config file is missing for
        message (str): The error message to raise
    """
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.message = f"The server configuration file for {guild.name}({guild.id}) is missing. Please run the setup " \
                       f"command to restore or create a new one"
        super().__init__(self.message)


class ConfigFileCorrupted(ConfigFileException):
    """Raises if config file is missing a particular key
    Args:
        guild (discord.Guild): The guild belonging to the corrupted config file
        missing_key (KeyError): The required key that was missing
    Attributes:
        guild (discord.Guild): The guild belonging to the corrupted config file
        missing_key (KeyError): The required key that was missing
        message (str): The error message to raise
    """
    def __init__(self, guild: discord.Guild, missing_key: KeyError = None):
        self.guild = guild
        self.missing_key = missing_key
        if missing_key is None:
            self.message = f"The server configuration file for {guild.name}({guild.id}) Corrupted." \
                           f" Please run the setup command to restore or create a new one"
        else:
            self.message = f"The server configuration file for {guild.name}({guild.id}) is missing the key " \
                           f"{missing_key}. Please run the setup command to restore or create a new one"
        super().__init__(self.message)


class CantEnsureMessage(config.RevnobotException):
    def __init__(self):
        super().__init__("Trying to retrieve some kind of message object associated with the command failed")


class ConvertTime:
    def __init__(self, seconds):
        self.input_seconds = seconds
        self.hours = self.input_seconds // 3600
        self.minutes = self.input_seconds // 60 - self.hours * 60
        self.seconds = self.input_seconds - (self.hours * 3600 + self.minutes * 60)

    def shorter(self):
        hours = f'{self.hours}h ' if self.hours > 0 else ""
        minutes = f'{self.minutes}m ' if self.minutes > 0 else ""
        return f'{hours}{minutes}{self.seconds}s'

    def short(self):
        hours = f'{self.hours}hrs ' if self.hours > 0 else ""
        minutes = f'{self.minutes}min ' if self.minutes > 0 else ""
        return f'{hours}{minutes}{self.seconds}sec'

    def full(self):
        hours = f'{self.hours} hours, ' if self.hours > 0 else ""
        minutes = f'{self.minutes} minutes and ' if self.minutes > 0 else ""
        return f'{hours}{minutes}{self.seconds} seconds'

    def colons(self):
        return f'{self.hours}:{self.minutes}:{self.seconds}'


class DefaultView(discord.ui.View):
    def __init__(self, *args, bot: discord.Bot = None,
                 context: Union[commands.Context, discord.ApplicationContext] = None,
                 user: discord.User = None, cog: config.RevnobotCog = None, message: discord.Message = None,
                 **kwargs):
        self.bot = bot
        self.ctx = context
        self.user = user
        self.cog = cog
        self.original_message = message
        if isinstance(self.original_message, discord.Interaction) and self.ctx is not None:
            self.original_message = self.ctx.interaction.message or self.original_message
        if isinstance(self.original_message,
                      (discord.PartialMessage, discord.WebhookMessage)) and any([self.ctx, self.bot]):
            bot = self.bot or self.ctx.bot
            self.original_message = bot.get_message(self.original_message.id)

        super().__init__(*args, **kwargs)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user and interaction.user.id != self.user.id:
            bot = self.bot or self.ctx.bot
            await interaction.response.send_message(embed=warning_embed(bot, "Action Not Allowed",
                                                                        "Only the user who invoked this command "
                                                                        "can interact with it"),
                                                    ephemeral=True)
            return False
        return True

    async def on_error(self, error: Exception, item: discord.ui.Item, interaction: discord.Interaction):
        bot = self.bot or (
            self.ctx.bot if isinstance(self.ctx, (discord.ApplicationContext, commands.Context)) else None
        )
        ctx = self.ctx or (discord.ApplicationContext(bot, interaction) if bot else None)
        if not isinstance(ctx, discord.ApplicationContext) and bot:
            ctx = discord.ApplicationContext(bot, interaction)
        if bot and ctx:
            invoke_error = discord.ApplicationCommandInvokeError(error)
            await errors.Errors(bot).on_application_command_error(ctx, invoke_error)
        else:
            print(f"Ignoring exception in view {self} for item {item}:", file=sys.stderr)
            traceback.print_exception(error.__class__, error, error.__traceback__, file=sys.stderr)

    async def on_timeout(self):
        if self.original_message:
            try:
                self.disable_all_items()
                await self.original_message.edit(view=self)
            except discord.HTTPException:
                pass
        self.stop()


def repack(*args, **kwargs):
    return args, kwargs


def count_digit_prefix(string: str) -> int:
    digits = 0
    for character in string:
        if character.isdigit():
            digits += 1
        else:
            break
    return digits


def human_readable_to_seconds(human_readable: str) -> int:
    if ":" in human_readable:
        split_timestamp = human_readable.split(":")
        seconds = 0
        for index, part in enumerate(reversed(split_timestamp)):
            if index > 2:
                raise ValueError("Unexpected timestamp format! Expected HH:MM:SS")
            if not part.isdecimal():
                raise ValueError("Invalid timestamp format! Expected HH:MM:SS")
            else:
                seconds += int(part) * 60 ** index
        return seconds
    elif human_readable.isdecimal():
        return int(human_readable)
    else:
        raise ValueError("Unexpected format, expected HH:MM:SS")


def dec_to_bin(decimal: int, digits: int = 64):
    output_str = ""
    if decimal > 2**digits - 1:
        raise OverflowError(f"The decimal number '{decimal}' is too big to be displayed in {digits} binary digits")
    for pow_num in reversed(range(digits)):
        digit = 2**pow_num
        if decimal % digit == decimal:
            output_str += "0"
        else:
            output_str += "1"
            decimal -= digit
    return output_str


def print_error(*values: object, sep: str | None = "", end="\n", file: Any | None = sys.stderr, flush: bool = False):
    list_values = list(values)
    list_values.insert(0, "\033[0;31m")
    print(*tuple(list_values), sep, end="\033[0m"+end, file=file, flush=flush)


def clean_enum(enum: Enum):
    return enum.name.replace("_", " ").capitalize()


async def ensure_message(ctx: Union[commands.Context, discord.ApplicationContext, bridge.BridgeContext]) \
        -> Union[discord.Message, discord.InteractionMessage]:
    """tries to make sure there will be a message

    This is useful when needing a message object to work with before the main message is sent

    Args:
        ctx: The command context
    Returns:
        discord.Message: a discord message
    Raises:
        CantEnsureMessage: ensuring a message failed
    """
    if isinstance(ctx, discord.ApplicationContext):
        if not ctx.response.is_done():
            await ctx.defer()
        message = await ctx.interaction.original_response()
    else:
        message = ctx.message
    if isinstance(message, (discord.PartialMessage, discord.WebhookMessage)):
        message = ctx.bot.get_message(message.id)
    if message is None:
        raise CantEnsureMessage()
    else:
        return message


def get_url(text: str) -> Optional[list[str]]:
    if "https://" in text or "http://" in text:
        found_urls = []
        for protocol in ["https://", "http://"]:
            for idx, part in enumerate(text.split(protocol)):
                if idx > 0:
                    formatted_url = protocol + part.split(" ")[0].split("\n")[0]
                    for char in [")", "]", ";", ":", "'", '"', ",", ".", "<", "*", "./"]:
                        if formatted_url.endswith(char):
                            construct_url = ""
                            for sub_idx, sub_part in enumerate(formatted_url.rsplit(char)[:-1]):
                                sub_part = char + sub_part if sub_idx > 0 else sub_part
                                construct_url += sub_part
                            formatted_url = construct_url
                    if formatted_url != protocol:
                        found_urls.append(formatted_url)
        return found_urls


def byte_units(bytes_size: int, iec=False) -> str:
    """Converts large byte numbers to SI units.
    Args:
        bytes_size (int): the number (bytes)
        iec (bool): whether to use iec units (2^10, 2^20, 2^30, etc. bytes) or si units (10^3, 10^6, 10^9, etc. bytes)
    Returns:
        str: the bytes in the appropriate SI Units"""
    units_in = 2**10 if iec else 10**3
    unit_names = ['bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB'] if iec else \
        ['bytes', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    exponent = abs(bytes_size.bit_length() - 1) // 10 if iec else (len(str(bytes_size)) - 1) // 3
    if exponent < len(unit_names):
        unit_name = unit_names[exponent]
    else:
        unit_name = unit_names[8]
    if unit_name == 'bytes':
        unit_name = 'byte' if bytes_size == 1 else unit_name
        rounded = f"{bytes_size} {unit_name}"
    else:
        rounded = f"%s {unit_name}" % float('%.4g' % round(bytes_size/units_in**exponent, 1))
    return rounded


async def format_http_error(error: discord.HTTPException) -> dict:
    """Auto-formats information on a discord http error
    Args:
        error(HTTPException): The http exception to format the information on
    Returns:
        dict: The formatted http exception
    """
    red_header = dict(error.response.headers)
    http_info = {"request url": error.response.url,
                 "response status": error.status,
                 "response reason": error.response.reason,
                 "response message": error.text,
                 "request method": error.response.method,
                 "original url": error.response.real_url,
                 "response type": error.response.content_type,
                 "encoding": error.response.get_encoding(),
                 "headers": red_header}
    if error.response.content_type == "application/json":
        red_data = await discord.utils.maybe_coroutine(error.response.json)
        http_info["response content"] = red_data
    return http_info


async def print_http_error(error: discord.HTTPException, stderr=True, formatting_size=4):
    """Auto-prints information on a discord http error
        Args:
            error(HTTPException): The http exception to print the information on
            stderr(bool): Whether to print to stderr or stdout
            formatting_size(int): The minimum space size between the names and values
    """
    to_print = ["HTTP Response Error Information"]
    http_info = await format_http_error(error)
    space_size = 0
    for name, _ in http_info.items():
        if len(name) > space_size:
            space_size = len(name)
    for name, value in http_info.items():
        to_print.append(f'{str(name).title()}:'
                        f'{"".join([" " for _ in range(space_size + formatting_size - len(name))])}{value}')
    print("\n".join(to_print), file=sys.stderr if stderr else None)


def all_files(directory: Union[pathlib.Path, str], symlink_exclusions: list[str] = None,
              first_iteration=True) -> list[pathlib.Path]:
    sym_exc = symlink_exclusions or []
    if isinstance(directory, str):
        directory = pathlib.Path(directory)
    if directory.exists():
        items = []
        for item in directory.iterdir():
            if item.is_dir():
                if not first_iteration and directory.is_symlink() and directory.name not in sym_exc:
                    continue
                else:
                    sub_items = all_files(item, sym_exc, first_iteration=False)
                    items.extend(sub_items)
            else:
                items.append(item)
        return items
    else:
        raise FileNotFoundError("path not found")


def progress_bar(part_amount: int, total_amount: int, size: int, highlighted_spaces=False):
    """Creates a progress bar out of blocks and spaces
    Args:
        part_amount(int): The value out of the total amount
        total_amount(int): The total value of the progress bar
        size(int): The size of the progress bar in characters
        highlighted_spaces(bool) Whether to use highlighted spaces as progress bar blocks for cli output
    """
    percent = round(part_amount / total_amount * size)
    block_character = "\033[7m " if highlighted_spaces else "█"
    block_line = ""
    if percent > 0:
        for _ in range(percent):
            block_line += block_character
    if highlighted_spaces:
        block_line += "\033[0m"
    space_line = ""
    if percent < size:
        for _ in range(size - percent):
            space_line += " "
    return block_line + space_line


def linux_current_pid():
    """Fetches the current process id for this process
    Returns:
        int: The ID of the current process
    Raises:
        OSError: Could not read the file requested
        UnicodeDecodeError: Could not get the PID from the file requested (unexpected output)
        ValueError: Could not get the PID from the file requested (unexpected output)
    """
    with open("/proc/self/stat", 'r') as stat_handle:
        stat_m = stat_handle.read()
        stat_handle.close()
    return int(stat_m.split(" ")[0])


def linux_proc_mem_info():
    """Fetches memory information on the current process .
        This only works on linux and will raise a FileNotFoundError if otherwise or the directory is missing
        Returns:
            dict: The process memory information
        Raises:
            FileNotFoundError: OS is not linux or the /proc/self/statm (link to /proc/$PID/statm) directory is missing
            OSError: Fetching the process memory information failed
    """

    with open('/proc/self/statm', 'r', encoding="utf-8") as proc_handle:
        proc_mem_info = proc_handle.read().split(" ")
        proc_handle.close()
    return {"Resident": int(proc_mem_info[1]) * 4096, "Shared": int(proc_mem_info[2]) * 4096,
            "Individual": int(proc_mem_info[1]) * 4096 - int(proc_mem_info[2]) * 4096}


def linux_mount_source(mount_point="/", parent_device=False, resolve=True) -> Optional[pathlib.Path]:
    """Fetches the device of a mount point. Returns None if not found
    Args:
        mount_point(str): The mount point of the device to search for
        parent_device(bool): Whether to return the parent device if the mount source is a sub device
        resolve(bool): Whether to return the physical path to the device. This will fail if the source is not physical,
            so set this to false if you want to get the source of e.g. /proc or a network mount
    Returns:
        Optional[Path]: The device linked to the mounted point. Returns None if not found
    """
    # noinspection SpellCheckingInspection
    with open('/etc/mtab', 'r', encoding="utf-8") as mounts_handle:
        mounts = mounts_handle.readlines()
    for raw_mount in mounts:
        mount = raw_mount.split(" ")
        if mount[1] == mount_point:
            if resolve:
                mount_dev = pathlib.Path(mount[0]).resolve()
            else:
                mount_dev = pathlib.Path(mount[0])
            if parent_device and mount_dev.exists() and mount_dev.name not in os.listdir('/sys/block/'):
                for item in os.listdir('/sys/block/'):
                    if mount_dev.name.startswith(item) and mount_dev.name != item:
                        mount_dev = pathlib.Path('/dev/{}'.format(item)).resolve()
            return mount_dev


def linux_resolve_uid(user_id: int) -> Optional[str]:
    """Finds the username of a given ID
    Args:
        user_id(str): The id of the user
    Returns:
        Optional[str]: The username of the found user. Returns None if not found
    """
    with open('/etc/passwd', 'r', encoding="utf-8") as passwd_handle:
        passwd = passwd_handle.readlines()
    for entries in passwd:
        entry = entries.split(":")
        if entry[2] == str(user_id):
            return entry[0]


def linux_resolve_gid(group_id: int) -> Optional[str]:
    """Finds the group-name of a given ID
    Args:
        group_id(str): The id of the group
    Returns:
        Optional[str]: The group-name of the found group. Returns None if not found
    """
    with open('/etc/group', 'r', encoding="utf-8") as group_handle:
        group = group_handle.readlines()
    for entries in group:
        entry = entries.split(":")
        if entry[2] == str(group_id):
            return entry[0]


def user_in_group(username: str, group_id: Union[str, int]) -> bool:
    """Finds checks if a user is in a group
    Args:
        username(str): The username of the user,
        group_id(Union[str, int]): The group to check
    Returns:
        bool: If the user was found in the group
    """
    if isinstance(group_id, int):
        group_name = str(group_id)
        search_index = 2
    else:
        group_name = group_id
        search_index = 0
    with open('/etc/group', 'r', encoding="utf-8") as group_handle:
        group = group_handle.readlines()
    user_found = False
    for entries in group:
        entry = entries.replace("\n", "").split(":")
        if group_name == entry[search_index]:
            if len(entry) >= 4:
                group_users = entry[3].split(",")
                user_found = username in group_users
            else:
                user_found = False
    return user_found


def can_read(path: pathlib.Path) -> bool:
    path_stat = path.stat(follow_symlinks=False)
    owner = path_stat.st_uid
    user_id = int(os.getuid())
    username = linux_resolve_uid(user_id)
    st_mode_bin = bin(path_stat.st_mode)[2:]
    if owner == user_id and int(st_mode_bin[-9]):
        return True
    elif user_in_group(username, path_stat.st_gid) and int(st_mode_bin[-6]):
        return True
    elif int(st_mode_bin[-3]):
        return True
    else:
        return False


async def walk_dir(directory: pathlib.Path) -> tuple[int, int, int]:
    size_count = 0
    file_count = 0
    directory_count = 0
    for file_dir in directory.iterdir():
        if file_dir.is_file():
            size_count += file_dir.stat(follow_symlinks=False).st_size
            file_count += 1
        elif file_dir.is_dir() and not file_dir.is_symlink():
            directory_count += 1
            if can_read(file_dir):
                try:
                    sub_size_count, sub_file_count, sub_directory_count = await walk_dir(file_dir)
                    size_count += sub_size_count
                    file_count += sub_file_count
                    directory_count += sub_directory_count
                except PermissionError:
                    pass
    return size_count, file_count, directory_count


def linux_block_dev_info(device_id: str, sub_block=False) -> dict:
    """Fetches information on a block device
    Args:
        device_id(str): The id of the block device to get the information of
        sub_block(bool): value used by this function. it is recommended not to touch it
    Returns:
        dict: The metadata of the block device
    Raises:
        FileNotFoundError: The device could not be found
    """
    block_info = {"device id": device_id}
    device_found = False
    if device_id not in os.listdir('/sys/block/'):
        for item in os.listdir('/sys/block/'):
            if device_id.startswith(item) and device_id != item:
                device_found = True
                block_info['parent device'] = linux_block_dev_info(item, True)
                block_info['parent device']['device id'] = item
    if not device_found:
        if os.path.exists(f"/sys/class/block/{device_id}/slaves/"):
            physical_volume = 0
            for item in os.listdir(f"/sys/class/block/{device_id}/slaves/"):
                physical_volume += 1
                block_info[f"physical volume {physical_volume}"] = linux_block_dev_info(item)

    for file in all_files("/sys/class/block/{}".format(device_id), ["bdi"]):
        try:
            with open(file, 'r', encoding="utf-8") as info_handle:
                info_file = info_handle.read()
                info_handle.close()
        except OSError:
            continue
        except UnicodeDecodeError:
            continue
        else:
            if file.parent.name.startswith(device_id) and file.parent.name != device_id and not sub_block:
                # noinspection PyTypeChecker
                sub_device_num = int("".join(filter(str.isdecimal, file.parent.name)))
                if block_info.get(f"sub device {sub_device_num}") is None:
                    block_info[f'sub device {sub_device_num}'] = {}
                block_info[f'sub device {sub_device_num}'][file.name] = info_file.replace("\n", "")
                block_info[f'sub device {sub_device_num}']["device id"] = file.parent.name
            elif block_info.get(file.name) is not None and file.parent.name != device_id:
                pass
            else:
                block_info[file.name] = info_file.replace("\n", "")

    return block_info


def linux_cpu_info():
    # noinspection SpellCheckingInspection
    """Fetches cpu information provided by the kernel in /proc/cpuinfo and returns it as a list of cpus.
    This only works on linux and will raise a FileNotFoundError if otherwise or the file is missing
    Returns:
        list[dict]: The CPU information
    Raises:
        FileNotFoundError: OS is not linux or /proc/cpuinfo is missing
        PermissionError: Unable to read /proc/cpuinfo
        OSError: Fetching the cpu information failed
    """
    # noinspection SpellCheckingInspection
    with open("/proc/cpuinfo", 'r', encoding='utf-8') as cpu_info_handle:
        raw_cpu_info = cpu_info_handle.readlines()
        cpu_info_handle.close()
    core_number = 0
    cpus = []
    sub_cpu = {}
    for line in raw_cpu_info:
        if line == '\n':
            cpus.append(sub_cpu)
            sub_cpu = {}
            core_number += 1
        else:
            clean_line = line.replace("\t", "").replace("\n", "")
            parts = clean_line.split(':')
            sub_cpu[parts[0]] = parts[1][1:]
    return cpus


def linux_cpu_stat() -> list[list[str]]:
    """Gets stat information provided by the kernel
    Returns:
        list[list[str]]: A 2D array of stat information
    Raises:
        FileNotFoundError: The stat file is missing because the os is not linux or the root directory is wrong
    """
    with open("/proc/stat") as processes:
        return [line.split() for line in processes.read().splitlines()]


def linux_proc_stat(pid: int) -> list[str]:
    with open(f"/proc/{pid}/stat") as stat_file:
        return stat_file.read().split()


async def linux_cpu_utilization(thread: int = -1) -> float:
    """Calculates the utilization of a cpu thread or the total across all threads

    This process takes approximately 0.5 seconds to execute
    Args:
        thread (int): The thread number starting from 0. Defaults to -1 which gets the total utilization across all
                      threads
    Returns:
        float: The utilization of the cpu or thread out of 1
    Raises:
        IndexError:
            An invalid thread number was specified
        FileNotFoundError:
            Inherited from :method:`linux_cpu_info` and :method:`linux_cpu_stat`
    """
    cpu_last_sum = 0
    idle_last = 0
    usages = []
    num_threads = int(linux_cpu_info()[0]['siblings'])
    if not -1 <= thread <= num_threads-1:
        raise IndexError(f"Invalid thread number! Please enter -1 for total or a number between 0 and {num_threads-1}")
    for _ in range(10):
        stats = linux_cpu_stat()
        cpu_total = stats[thread+1]
        cpu_sum = sum([int(column) for column in cpu_total[1:]])
        cpu_delta = cpu_sum - cpu_last_sum
        cpu_idle = int(cpu_total[4]) - idle_last
        cpu_used = cpu_delta - cpu_idle
        cpu_usage = cpu_used / cpu_delta
        usages.append(cpu_usage)
        cpu_last_sum = cpu_sum
        idle_last = int(cpu_total[4])
        await asyncio.sleep(0.05)
    return sum(usages) / len(usages)


async def linux_proc_cpu_utilization(pid: int = None):
    pid = pid or linux_current_pid()

    def timer():
        return datetime.datetime.now().timestamp() * os.cpu_count()

    def get_stat():
        stats = linux_proc_stat(pid)
        return [int(stat) / os.sysconf("SC_CLK_TCK") for stat in stats[13:17] + [stats[41]]]

    avg_util = []

    for _ in range(10):
        st1 = timer()
        pt1 = get_stat()
        await asyncio.sleep(0.05)
        st2 = timer()
        pt2 = get_stat()

        delta_proc = (pt2[0] - pt1[0]) + (pt2[1] - pt1[1])
        delta_time = st2 - st1

        try:
            # This is the utilization split evenly between all CPUs.
            # E.g. a busy loop process on a 2-CPU-cores system at this
            # point is reported as 50% instead of 100%.
            overall_cpus = delta_proc / delta_time
        except ZeroDivisionError:
            # interval was too low
            avg_util.append(0.0)
        else:
            # Note 1:
            # in order to emulate "top" we multiply the value for the num
            # of CPU cores. This way the busy process will be reported as
            # having 100% (or more) usage.
            #
            # Note 2:
            # taskmgr.exe on Windows differs in that it will show 50%
            # instead.
            #
            # Note 3:
            # a percentage > 100 is legitimate as it can result from a
            # process with multiple threads running on different CPU
            # cores (top does the same), see:
            # http://stackoverflow.com/questions/1032357
            # https://github.com/giampaolo/psutil/issues/474
            # single_cpu_percent = overall_cpus_percent * num_cpus
            avg_util.append(overall_cpus)
    return sum(avg_util) / len(avg_util)


def linux_board_info():
    """Fetches system board information from /sys/devices/virtual/dmi/id/ and returns it as a dict.
        This only works on linux and will raise a FileNotFoundError if otherwise or the directory is missing
        Returns:
            dict: The system board information
        Raises:
            FileNotFoundError: OS is not linux or the /sys/devices/virtual/dmi/id/ directory is missing
            OSError: Fetching the system board information failed
        """
    sys_dir = pathlib.Path("/sys/devices/virtual/dmi/id/")
    sys_info = {}
    for file in sys_dir.iterdir():
        if file.is_file():
            try:
                with open(file, 'r', encoding="utf-8") as info_file:
                    sys_info[file.name] = info_file.read().replace("\n", "")
                    info_file.close()
            except PermissionError:
                continue
    return sys_info


def linux_mem_info():
    """Fetches RAM information from /proc/meminfo and returns it as a dict.
    This only works on linux and will raise a FileNotFoundError if otherwise or the file is missing
    Returns:
        dict: The RAM information
    Raises:
        FileNotFoundError: OS is not linux or /proc/meminfo is missing
        PermissionError: Unable to read /proc/meminfo
        OSError: Fetching the RAM information failed
    """
    with open("/proc/meminfo", 'r', encoding='utf-8') as mem_info_handle:
        raw_mem_info = mem_info_handle.readlines()
        mem_info_handle.close()
    output = {}
    mem_total = 0
    for line in raw_mem_info:
        clean_line = line.replace("\t", "").replace("\n", "")
        parts = clean_line.split(':')
        value_bytes = int(parts[1].replace(" kB", '')) * 1000
        if parts[0] == "MemTotal":
            mem_total = value_bytes
        if parts[0] == "MemAvailable":
            output["MemUsed"] = mem_total - value_bytes
        output[parts[0]] = value_bytes
    return output


def get_guild_config(guild: discord.Guild, *, key: str = None) -> \
        Optional[Union[discord.TextChannel, discord.Role, str, int, dict]]:
    """Fetches the log channel for a server if any
    Args:
        key (str): The key to look for in the configuration. Defaults to sending the entire configuration
        guild (discord.Guild): The guild to find a logging channel for
    Returns:
        Optional[Union[discord.TextChannel, discord.Role, str, int, dict]]:
            The requested property in the configuration if any
    Raises:
        MissingConfigFile: The configuration file for the guild is missing
        ConfigFileCorrupted: The configuration file for the guild is corrupted
    """
    if not pathlib.Path(f'./json/guilds/{guild.id}.json').exists():
        raise MissingConfigFile(guild)
    else:
        with open(f'./json/guild-template.json', 'r', encoding='utf-8') as key_checker_file:
            key_checker: dict = json.load(key_checker_file)
            key_checker_file.close()
        with open(f'./json/guilds/{guild.id}.json', 'r', encoding='utf-8') as r_guild_info:
            try:
                guild_info = json.load(r_guild_info)
            except json.JSONDecodeError:
                raise ConfigFileCorrupted(guild)
            r_guild_info.close()
        if key is None:
            return guild_info
        elif key in key_checker:
            try:
                if guild_info[key] is not None:
                    valid_channels = [key for key in key_checker if key.endswith("channel")]
                    valid_roles = [key for key in key_checker if key.endswith("role")]
                    if key in valid_channels:
                        requested_channel = guild.get_channel(guild_info[key])
                        return requested_channel
                    elif key in valid_roles:
                        requested_role = guild.get_role(guild_info[key])
                        return requested_role
                    else:
                        return guild_info[key]
            except KeyError as key_err:
                raise ConfigFileCorrupted(guild, key_err)


def dt_readable(date_time: datetime.datetime) -> str:
    return date_time.strftime(config.dt_string)


def discord_ts(date_time: Union[datetime.datetime, int], style: str = "F") -> str:
    return f'<t:{round(date_time.timestamp()) if isinstance(date_time, datetime.datetime) else date_time}:{style}>'


def is_dm_channel(channel: Union[TextChannel, Thread, DMChannel, PartialMessageable, GuildChannel,
                                 CategoryChannel, VoiceChannel]):
    return True if isinstance(channel, (DMChannel, PartialMessageable)) else False


def has_permissions(perms: discord.Permissions, *, as_list=False, separator: str = ', ', capitalise=True,
                    use_spaces=True, upper_case=False, developer_terms=False, embed_field=False):
    perm_list = []
    for perm in perms.__iter__():
        if perm[1]:
            perm_to_append = perm[0]
            if not developer_terms:
                perm_to_append = perm_to_append.replace('guild', 'server')
                perm_to_append = perm_to_append.replace('create_instant_invite', 'create_invites')
                perm_to_append = perm_to_append.replace('external_emojis', 'use_external_emojis')
                perm_to_append = perm_to_append.replace('external_stickers', 'use_external_stickers')
            perm_to_append = perm_to_append.replace('_', ' ') if use_spaces else perm_to_append
            perm_to_append = perm_to_append.title() if capitalise else perm_to_append
            perm_to_append = perm_to_append.upper() if upper_case else perm_to_append
            perm_list.append(perm_to_append)
    if not as_list:
        str_perms = separator.join(perm_list)
        return perms.value if embed_field and len(str_perms) > 1024 else str_perms
    else:
        return perm_list


def clean_list(input_list, *, separator: str = ', ', capitalise=True, use_spaces=True,
               upper_case=False, lower_case=False, developer_terms=False, empty_message: str = "empty"):
    formatted_list = []
    if len(input_list) < 1:
        input_list.append(empty_message)
    for item in input_list:
        if not developer_terms:
            item = item.replace('guild', 'server')
        item = item.replace('_', ' ') if use_spaces else item
        item = item.lower() if lower_case else item
        item = item.title() if capitalise else item
        item = item.upper() if upper_case else item
        formatted_list.append(item)
    return separator.join(formatted_list)


def has_system_channel_flags(flags: discord.SystemChannelFlags, *, as_list=False, separator: str = ', ',
                             capitalise=True, use_spaces=True, upper_case=False, developer_terms=False):
    flag_list = []
    for flag in flags.__iter__():
        if flag[1]:
            flag_to_append = flag[0]
            if not developer_terms:
                flag_to_append = flag_to_append.replace('guild_reminder_notifications', 'server_tips')
                flag_to_append = flag_to_append.replace('join_notifications', 'welcome_messages')
                flag_to_append = flag_to_append.replace('join_notification_replies', 'welcome_message_stickers')
                flag_to_append = flag_to_append.replace('premium_subscriptions', 'boost_notifications')
            flag_to_append = flag_to_append.replace('_', ' ') if use_spaces else flag_to_append
            flag_to_append = flag_to_append.title() if capitalise else flag_to_append
            flag_to_append = flag_to_append.upper() if upper_case else flag_to_append
            flag_list.append(flag_to_append)
    return separator.join(flag_list) if not as_list else flag_list


def is_empty(text: str):
    if len(text) < 1:
        return True
    for char in list(text):
        if char != ' ':
            return False
    return True


def map_bot(context: Union[commands.Context, discord.ApplicationContext]):
    """maps all bot cogs and commands outside the HelpCommand.send_bot_help.
    Particularly useful for using in an application help command
    Args:
        context (Union[commands.Context, discord.ApplicationContext]): the command/application command context
    Returns:
        collections.abc.Mapping: the bytes in the appropriate SI Units"""
    bot = context.bot
    mapping = {cog: cog.get_commands() for cog in bot.cogs.values()}
    # noinspection PyTypeChecker
    mapping[None] = [c for c in bot.commands if c.cog is None]
    return mapping


def keep_file(file_path: Union[str, os.PathLike]):
    """Creates a secondary file with the same name but with a number.
    Args:
        file_path (Union[str, os.Pathlike]): The file path of the existing file
    Returns:
        str: The new filename with a higher number in brackets
    Raises:
        FileNotFoundError: not already a file to number"""
    if isinstance(file_path, str):
        file_path = pathlib.Path(file_path)
    if file_path.exists():
        highest_number = 0
        for file in file_path.parent.iterdir():
            if file.name.startswith(f'{file_path.stem}(') and file.name.endswith(f'){file_path.suffix}'):
                split_1 = file.name.rsplit(')')
                raw_number = split_1[0].rsplit('(')[-1]
                if raw_number.isdecimal():
                    if int(raw_number) > highest_number:
                        highest_number = int(raw_number)
        return f'{file_path.stem}({highest_number+1}){file_path.suffix}'
    else:
        raise FileNotFoundError(f'there isn\'t already a file called "{file_path.name}" in '
                                f'"{file_path.parent}"')


def remove_ansi_colours(text: str):
    """Removes ansi escape characters.
        Args:
            text (str): The string (example: a command output) to remove the ansi colour characters from
        Returns:
            str: The string with the characters removed"""
    return re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\\/]*[@-~]').sub('', text)


def send_type(context: Union[commands.Context, ApplicationContext], reply=True):
    """Removes ansi escape characters.
            Args:
                context (Union[commands.Context, ApplicationContext]): The context object to use
                reply (bool): to either reply or send the message if it's not a slash command
            Returns:
                callable: the correct function to send the message"""
    return context.respond if isinstance(context, discord.ApplicationContext) else context.reply if reply \
        else context.send


def yes_no(boolean: bool, capitalise: str = True):
    return_bool = "yes" if boolean else "no"
    return return_bool.capitalize() if capitalise else return_bool


def format_typename(typename: str) -> str:
    whitespace_typename = typename
    if typename not in config.dont_replace:
        whitespace_typename = typename.replace("-", " ").replace("_", " ")
    formatted_typename = ""
    for word in (
            whitespace_typename.strip().title() if whitespace_typename not in config.dont_replace
            else whitespace_typename.strip()
    ).split():
        if word.lower() in config.uppercase_phrases:
            word = word.upper()
        formatted_typename += f" {word}"
    return formatted_typename.strip()


def minimal_embed(message: str, *, colour=config.embed_colour_default, url: str = None,
                  use_title=True):
    if str(url).startswith('https://') or str(url).startswith('http://'):
        set_url = url
    else:
        set_url = None
    warn_msg = None
    warn_message = f'Warning: Invalid Embed Colour Specified. ' \
                   f'\nEmbed Colour Was Set To Default: #{str(hex(config.embed_colour_default)).replace("0x", "")}'
    int_colour = config.embed_colour_default
    if isinstance(colour, int):
        if colour <= 16777215:
            int_colour = colour
        else:
            warn_msg = warn_message
    elif isinstance(colour, str):
        olo = str(colour).replace('0x', '')
        olo = olo.replace('#', '')
        if len(olo) == 6:
            try:
                int_colour = int("0x" + olo, 16)
            except ValueError:
                warn_msg = warn_message
        else:
            warn_msg = warn_message
    elif isinstance(colour, discord.colour.Colour):
        int_colour = colour
    else:
        warn_msg = warn_message
    if use_title:
        embed = discord.Embed(
            title=message,
            colour=int_colour,
            url=set_url
        )
    else:
        embed = discord.Embed(
            description=message,
            colour=int_colour,
            url=set_url
        )
    if warn_msg is not None:
        embed.set_footer(text=warn_msg)
    return embed


def default_embed(bot_ctx: Union[discord.Bot, commands.Context, ApplicationContext, bridge.BridgeContext],
                  title: str, desc: str, colour: Union[int, str, discord.Colour] = config.embed_colour_default,
                  typename: str = None,
                  url: str = None, *, timestamp: datetime.datetime = None, fields: list[discord.EmbedField] = None,
                  thumbnail: str = None):
    bot = bot_ctx if isinstance(bot_ctx, discord.Bot) else bot_ctx.bot
    if str(url).startswith('https://') or str(url).startswith('http://'):
        set_url = url
    else:
        set_url = None
    warn_msg = ''
    warn_message = f'\n**Warning**: Invalid Embed Colour Specified. ' \
                   f'\nEmbed Colour Was Set To Default: [#{str(hex(config.embed_colour_default)).replace("0x", "")}]' \
                   f'(https://testthisdevice.com/color/color.php?c=' \
                   f'{str(hex(config.embed_colour_default)).replace("0x", "")})'
    int_colour = config.embed_colour_default
    if isinstance(colour, int):
        if colour <= 16777215:
            int_colour = colour
        else:
            warn_msg = warn_message
    elif isinstance(colour, str):
        olo = str(colour).replace('0x', '')
        olo = olo.replace('#', '')
        if len(olo) == 6:
            try:
                int_colour = int("0x" + olo, 16)
            except ValueError:
                warn_msg = warn_message
        else:
            warn_msg = warn_message
    elif isinstance(colour, discord.colour.Colour):
        int_colour = colour
    else:
        warn_msg = warn_message
    if timestamp is None:
        timestamp = datetime.datetime.now()
    embed = discord.Embed(
        title=title,
        description=desc+warn_msg,
        colour=int_colour,
        url=set_url,
        timestamp=timestamp,
        fields=fields,
        thumbnail=discord.EmbedMedia(url=thumbnail)
    )
    if typename is None:
        if isinstance(bot_ctx, commands.Context):
            author_ext = f' - {format_typename(bot_ctx.command.name)}'
        elif isinstance(bot_ctx, discord.commands.ApplicationContext) and bot_ctx.interaction.data.get("name"):
            author_ext = f' - {format_typename(bot_ctx.interaction.data.get("name"))}'
        else:
            author_ext = f''
    else:
        author_ext = f' - {format_typename(typename)}'
    embed.set_author(
        name=f'{bot.user.name}{author_ext}',
        icon_url=bot.user.display_avatar.url)
    embed.set_footer(text=config.default_footer)
    return embed


def warning_embed(bot: discord.Bot, title: str, desc: str, *,
                  timestamp: datetime.datetime = None):
    if timestamp is None:
        timestamp = datetime.datetime.now()
    embed = discord.Embed(
        title=title,
        description=desc,
        colour=discord.Colour.orange(),
        timestamp=timestamp
    )
    embed.set_author(
        name=f'{bot.user.name} - Warnings',
        icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url='https://cdn-0.emojis.wiki/emoji-pics/twitter/warning-twitter.png')
    embed.set_footer(text=config.default_footer)
    return embed


def user_profile(bot: discord.Bot, user: discord.User, member: discord.Member = None, embed: discord.Embed = None,
                 ctx: Union[commands.Context, discord.ApplicationContext] = None):
    """Creates a user profile card as an embed or adds it to an existing embed

        Args:
            bot (discord.Bot): The bot instance to use
            user (discord.User): The user to create the card for. Preferably should be fetched using fetch_user()
            member (discord.Member): The member instance of the user to use alongside
            embed (Optional[discord.Embed]): The embed to use
            ctx (Union[commands.Context, discord.ApplicationContext]): Context instance to use with embed if specified
        Returns:
            discord.Embed: The embed with the user profiled added
        Raises:
            AssertionError: The member instance does not belong to this user
    """
    # WARNING: there cannot be more than 25 non-conditional embed.add_field lines or discord will return an error
    # The uses of embed.add_field are counted below and should be updated as necessary
    assert not (member and user.id != member.id)
    in_guild = bool(member)
    # try to fetch a guild member version
    if member is None:
        for guild in bot.guilds:
            member = guild.get_member(user.id)
            if member:
                break
    user_name = f"{user.name}#{user.discriminator}" if int(user.discriminator) \
        else user.name
    name_order = [user_name]
    if user.global_name is not None:
        name_order.insert(0, user.global_name)

    def valid_colour(colour: discord.Colour):
        return colour if colour and colour.value else None
    embed_colour = valid_colour(user.accent_colour) or valid_colour(user.colour) or config.embed_colour_default
    if member is not None:
        embed_colour = (valid_colour(member.colour) if in_guild else None) or valid_colour(member.accent_colour) \
                       or config.embed_colour_default
        status = ''
        if len(member.activities) > 0:
            secondary = f'{member.activities[0].name}'
            if isinstance(member.activities[0], discord.Activity):
                secondary = f'**{member.activities[0].name}:**\n{member.activities[0].details}'
            if isinstance(member.activities[0], discord.Game):
                secondary = f'{member.activities[0].name}'
            if isinstance(member.activities[0], discord.Streaming):
                secondary = f'{member.activities[0].name} ({member.activities[0].game}) on ' \
                            f'{member.activities[0].platform}'
            status = f'**{str(member.activities[0].type).rsplit(".")[-1].capitalize()}** {secondary}'
            if str(member.activities[0].type).rsplit(".")[-1] == "custom":
                status = secondary
        member_status = member.raw_status
        status_check = [member.raw_status, str(member.web_status), str(member.desktop_status)]
        if member.is_on_mobile() and status_check == ["online", "offline", "offline"]:
            member_status = "online_mobile"
        # noinspection SpellCheckingInspection
        status_emoji = f'<:revnobot_status_{member_status}:{config.user_status_emojis.get(member_status)}>'
        if in_guild and member.nick:
            name_order.insert(0, member.nick)
        desc = "\n".join(name_order[1:]) + "\n\n" + status if len(name_order) > 1 else status
        if embed is None:
            embed = default_embed(ctx or bot, f'{status_emoji}{name_order[0]}', desc, embed_colour)
    else:
        if embed is None:
            embed = default_embed(
                ctx or bot, f'{name_order[0]}', f"{name_order[1] if len(name_order) > 1 else ''}", colour=embed_colour
            )
    embed.set_thumbnail(url=user.display_avatar.url)
    # 8 uses of embed.add_field. Total: 8
    embed.add_field(name=":name_badge: Display Name", value=user.global_name or user.name)
    embed.add_field(name=":identification_card: Username", value=user_name)
    embed.add_field(name=":1234: ID", value=f'{user.id}')
    embed.add_field(name=":robot: Bot", value=yes_no(user.bot))
    embed.add_field(name=":calendar: Account Creation Date", value=discord_ts(user.created_at))
    embed.add_field(name=":clipboard: Copyable Timestamp", value=f"{round(((user.id >> 22) + 1420070400000) / 1000)}")
    embed.add_field(name=':mega: Mention', value=user.mention)
    embed.add_field(name='<:DiscordLogo:882561395982495754> System User', value=yes_no(user.system))
    # 2 uses of embed.add_field. Total: 10
    if valid_colour(user.colour):
        embed.add_field(name=':art: Primary Colour',
                        value=f'[{user.colour}](https://testthisdevice.com/color/color.php?c='
                              f'{str(user.colour).replace("#", "")})')
    if valid_colour(user.accent_colour):
        embed.add_field(name=':art: Accent Colour',
                        value=f'[{user.accent_colour}](https://testthisdevice.com/color/color.php?c='
                              f'{str(user.accent_colour).replace("#", "")})')
    badge: Enum
    badges = [f'<:{badge.name}:{config.user_badge_emojis.get(badge.name)}>'
              if config.user_badge_emojis.get(badge.name) is not None else badge.name
              for badge in user.public_flags.all()]
    # 1 use of embed.add_field. Total: 11
    if len(badges) > 0:
        embed.add_field(name=':military_medal: Badges', value=f'{" ".join(badges)}')
    if member is not None:
        if len(member.activities) > 0:
            secondary = f'{member.activities[0].name}'
            if isinstance(member.activities[0], discord.Activity):
                secondary = f':video_game: **{member.activities[0].name}:**\n{member.activities[0].details}'
            if isinstance(member.activities[0], discord.Game):
                secondary = f':video_game: {member.activities[0].name}'
            if isinstance(member.activities[0], discord.Streaming):
                secondary = f':tv: {member.activities[0].name} ({member.activities[0].game}) on ' \
                            f'{member.activities[0].platform}'
            # 1 use of embed.add_field. Total: 12
            if str(member.activities[0].type).rsplit(".")[-1] == "custom":
                embed.add_field(name=f':keyboard: Custom Status', value=secondary)
            else:
                embed.add_field(name=f':keyboard: {str(member.activities[0].type).rsplit(".")[-1].capitalize()}',
                                value=secondary)
        member_status = member.raw_status
        status_check = [member_status, str(member.web_status), str(member.desktop_status)]
        if member.is_on_mobile() and status_check == ["online", "offline", "offline"]:
            member_status = "online_mobile"
        # noinspection SpellCheckingInspection
        status_emoji = f'<:revnobot_status_{member_status}:{config.user_status_emojis.get(member_status)}>'
        # 1 use of embed.add_field. Total: 13
        embed.add_field(name='Status', value=f'{status_emoji} {member_status.replace("_", " ").title()}')
        if member.raw_status != 'offline':
            on = ':question: Error or Unknown'
            if member.is_on_mobile():
                on = ':mobile_phone: Mobile'
            if str(member.web_status) != 'offline':
                on = ':globe_with_meridians: Browser'
            if str(member.desktop_status) != 'offline':
                on = ':desktop: Desktop'
            if member.bot:
                on = ':robot: API'
            # 1 use of embed.add_field. Total: 14
            embed.add_field(name='On', value=on)
        mutual_guilds = 0
        for guild in ctx.bot.guilds if ctx else bot.guilds:
            if guild.get_member(member.id):
                mutual_guilds += 1
        # 8 use of embed.add_field. Total: 22
        embed.add_field(name="<:DiscordLogo:882561395982495754> Mutual Servers (Bot)", value=f'{mutual_guilds}')
        if in_guild:
            if valid_colour(member.colour) and member.colour.value != user.colour.value:
                embed.add_field(name=':art: Server Primary Colour',
                                value=f'[{member.colour}](https://testthisdevice.com/color/color.php?c='
                                      f'{str(member.colour).replace("#", "")})')
            if valid_colour(member.accent_colour) and member.accent_colour.value != user.accent_colour.value:
                embed.add_field(name=':art: Server Accent Colour',
                                value=f'[{member.accent_colour}](https://testthisdevice.com/color/color.php?c='
                                      f'{str(member.accent_colour).replace("#", "")})')
            embed.add_field(name=':inbox_tray: Joined Current Server At',
                            value=discord_ts(member.joined_at))
            if member.nick is not None:
                embed.add_field(name=':speech_balloon: Nickname', value=member.nick)
            embed.add_field(name=':warning: Pending Verification', value=yes_no(member.pending))
            if member.premium_since is not None:
                embed.add_field(name=':gem: Last Boosted Server At',
                                value=discord_ts(member.premium_since))
            if member.voice is not None:
                embed.add_field(name=":inbox_tray: Connected to", value=member.voice.channel.mention)
            vle_roles = f'{", ".join(role.mention for role in member.roles)}'
            role_name = f'@{member.top_role.name}'
            if member.top_role.mentionable:
                role_name = member.top_role.mention
            # 3 uses of embed.add_field. Total: 25 WARNING: MAX
            embed.add_field(name=":crown: Highest Role", value=f'{role_name}')
            if len(vle_roles) <= 1024 and len(member.roles) <= 25:
                embed.add_field(name=f':military_medal: Roles ({len(member.roles)})',
                                value=vle_roles, inline=False)
            else:
                embed.add_field(name=f':military_medal: Roles', value=f'{len(member.roles)}')
            embed.add_field(name=':key: Server Permissions',
                            value=f'{has_permissions(member.guild_permissions, embed_field=True)}', inline=False)

    return embed


def ensure_asset_format(
        asset: discord.Asset,
        static_format: Literal["webp", "jpeg", "jpg", "png"] = "png",
        target_size=1024, gif_if_animated=True
) -> discord.Asset:
    return (
        asset.with_format("gif") if asset.is_animated() and gif_if_animated else asset.with_format(static_format)
    ).with_size(target_size)


async def cog_contexts(cog: discord.Cog) -> set[discord.InteractionContextType] | None:
    class DummyContext:
        def __init__(self):
            self.guild = None
    supported_contexts = None
    dummy_context = DummyContext()
    try:
        await discord.utils.maybe_coroutine(cog.cog_check, dummy_context)
    except BaseException as e:
        if isinstance(e, commands.NoPrivateMessage):
            supported_contexts = {discord.InteractionContextType.guild}
    dummy_context.guild = 1
    try:
        await discord.utils.maybe_coroutine(cog.cog_check, dummy_context)
    except BaseException as e:
        if isinstance(e, commands.PrivateMessageOnly):
            supported_contexts = {discord.InteractionContextType.bot_dm}

    return supported_contexts


def sd_notify(message: bytes):
    """From https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html#Standalone%20Implementations"""

    if not message:
        raise ValueError("notify() requires a message")

    socket_path = os.environ.get("NOTIFY_SOCKET")
    if not socket_path:
        return

    if socket_path[0] not in ("/", "@"):
        raise OSError(errno.EAFNOSUPPORT, "Unsupported socket type")

    # Handle abstract socket.
    if socket_path[0] == "@":
        socket_path = "\0" + socket_path[1:]

    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC) as sock:
        sock.connect(socket_path)
        sock.sendall(message)


def check_guilds(bot: discord.Bot, *, guild: discord.Guild = None, log: logging.Logger = None):
    with open("json/guild-template.json") as guild_template_file:
        guild_template: dict = json.load(guild_template_file)
    missing_configs = 0
    outdated_configs = 0
    unarchived_configs = 0
    guilds = [guild] if guild else bot.guilds
    for bot_guild in guilds:
        if not pathlib.Path(f'json/guilds/{bot_guild.id}.json').exists():
            archive_if_exists = pathlib.Path(f'./json/guilds/archived guilds/{bot_guild.id}.json')
            if not archive_if_exists.exists():
                new_config = guild_template.copy()
                new_config["name"] = bot_guild.name
                new_config["server id"] = bot_guild.id
                with open(f'./json/guilds/{bot_guild.id}.json', 'w', encoding='utf-8') as w_guilds_json:
                    json.dump(new_config, w_guilds_json, indent=4)
                    w_guilds_json.close()
                missing_configs += 1
                continue

            try:
                shutil.move(archive_if_exists, pathlib.Path('./json/guilds/'))
            except (shutil.Error, OSError) as archive_error:
                if log:
                    log.warning(
                        f'Could not un-archive the data file for the server {bot_guild.name}({bot_guild.id}): '
                        f'{archive_error}'
                    )
                print(
                    f'Could not un-archive the data file for the server {bot_guild.name}({bot_guild.id}): '
                    f'{archive_error}'
                )
                continue
            else:
                unarchived_configs += 1

        with open(f"json/guilds/{bot_guild.id}.json", "r") as current_config_file:
            current_config = json.load(current_config_file)
        key_diff = set(guild_template.keys()).difference(set(current_config.keys()))
        if key_diff:
            for missing_key in key_diff:
                current_config[missing_key] = None
            with open(f"json/guilds/{bot_guild.id}.json", "w") as new_config_file:
                json.dump(current_config, new_config_file, indent=4)
            outdated_configs += 1
    if any([missing_configs, outdated_configs, unarchived_configs]):
        message = (
            f"Added {missing_configs} missing configs, Updated {outdated_configs} outdated configs, "
            f"Unarchived {unarchived_configs} configs"
        )
        print(message)
        if log:
            log.info(message)


async def check_appropriate_channel(
        ctx: commands.Context | discord.ApplicationContext, channel_topic: str, log: logging.Logger = None
) -> bool:
    try:
        topic_channel = get_guild_config(ctx.guild, key=f"{channel_topic} channel")
    except ConfigFileException:
        check_guilds(ctx.bot, guild=ctx.guild, log=log)
        return False
    else:
        if not topic_channel:
            setup_cmd = ctx.bot.get_application_command("setup", type=discord.SlashCommand)
            setup_cmd_string = f" or </setup:{setup_cmd.id}>" if setup_cmd else ""
            await (ctx.send if isinstance(ctx, commands.Context) else ctx.respond)(embed=default_embed(
                ctx, f"No {channel_topic.title()} Channel",
                f"Server admins please set up {channel_topic} channel in the {ctx.bot.command_prefix}setup"
                f"{setup_cmd_string} command."
            ))
            return False
        if ctx.channel.id != topic_channel.id:
            await (ctx.send if isinstance(ctx, commands.Context) else ctx.respond)(embed=default_embed(
                ctx, f"Not A {channel_topic.title()} Channel",
                f"Please run this command in {topic_channel.mention}."
            ))
            return False
        return True
