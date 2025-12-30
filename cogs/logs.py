import asyncio
import gzip
import json
import os
import pathlib
import shutil
import sys
from typing import Union
import aiohttp
import discord
import config
import logging
from logging.handlers import RotatingFileHandler
from discord.ext import commands, bridge
import utils

typename = "logs"


def namer(name):
    return name + ".gz"


def rotator(source, destination):
    with open(source, 'rb') as f_in:
        with gzip.open(destination, 'wb') as f_out:
            # noinspection PyTypeChecker
            shutil.copyfileobj(f_in, f_out)
    os.remove(source)


bot_logger = logging.getLogger('bot-logger')
bot_logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(filename='./logs/bot-logger.log', encoding='utf-8', mode='w',
                              maxBytes=config.max_log_size, backupCount=config.max_log_backups)
handler.rotator = rotator
handler.namer = namer
# noinspection SpellCheckingInspection
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
if not bot_logger.handlers:
    bot_logger.addHandler(handler)
bot_logger.info("bot startup")
handler.close()
command_logging = logging.getLogger('commands')
command_logging.setLevel(logging.DEBUG)
handler = RotatingFileHandler(filename='./logs/commands.log', encoding='utf-8', mode='a', maxBytes=config.max_log_size,
                              backupCount=config.max_log_backups)
handler.rotator = rotator
handler.namer = namer
# noinspection SpellCheckingInspection
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
if not command_logging.handlers:
    command_logging.addHandler(handler)
handler.close()
dm_logging = logging.getLogger('dms')
dm_logging.setLevel(logging.DEBUG)
handler = RotatingFileHandler(filename='./logs/dms.log', encoding='utf-8', mode='a', maxBytes=config.max_log_size,
                              backupCount=config.max_log_backups)
handler.rotator = rotator
handler.namer = namer
# noinspection SpellCheckingInspection
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
if not dm_logging.handlers:
    dm_logging.addHandler(handler)
handler.close()
message_logging = logging.getLogger('messages')
message_logging.setLevel(logging.DEBUG)
handler = RotatingFileHandler(filename='./logs/messages.log', encoding='utf-8', mode='a', maxBytes=config.max_log_size,
                              backupCount=config.max_log_backups)
handler.rotator = rotator
handler.namer = namer
# noinspection SpellCheckingInspection
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
if not message_logging.handlers:
    message_logging.addHandler(handler)
handler.close()
error_logging = logging.getLogger('errors')
error_logging.setLevel(logging.DEBUG)
handler = RotatingFileHandler(filename='./logs/errors.log', encoding='utf-8', mode='a', maxBytes=config.max_log_size,
                              backupCount=config.max_log_backups)
handler.rotator = rotator
handler.namer = namer
# noinspection SpellCheckingInspection
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
if not error_logging.handlers:
    error_logging.addHandler(handler)
handler.close()
guild_logging = logging.getLogger('guilds')
guild_logging.setLevel(logging.DEBUG)
handler = RotatingFileHandler(filename='./logs/guilds.log', encoding='utf-8', mode='a', maxBytes=config.max_log_size,
                              backupCount=config.max_log_backups)
handler.rotator = rotator
handler.namer = namer
# noinspection SpellCheckingInspection
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
if not guild_logging.handlers:
    guild_logging.addHandler(handler)


class Logging(config.RevnobotCog):
    def __init__(self, client):
        self.client: bridge.Bot = client
        self.description = "The Logging Module of the bot"
        self.icon = "\U0001F5A8"
        self.hidden = True

    @commands.Cog.listener()
    async def on_disconnect(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://one.one.one.one"):
                    pass
            except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
                if config.systemd_service:
                    utils.sd_notify(b"STATUS=Offline: Internet connection lost")
                bot_logger.warning("Lost connection to websocket: Internet connection was lost!")
                print("Lost connection to websocket: Internet connection was lost!", file=sys.stderr)
            else:
                try:
                    async with session.get("https://discord.com/api/v10/applications") as discord_response:
                        if discord_response.status >= 500:
                            if config.systemd_service:
                                utils.sd_notify(b"STATUS=Offline: Discord Down")
                            bot_logger.warning("Lost connection to websocket! Discord is down!")
                            print("Lost connection to websocket: Discord is down!", file=sys.stderr)
                except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
                    if config.systemd_service:
                        utils.sd_notify(b"STATUS=Offline: Discord Probably Down")
                    bot_logger.warning("Lost connection to websocket: Discord appears to be down!")
                    print("Lost connection to websocket: Discord appears to be down!", file=sys.stderr)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if not pathlib.Path(f'./json/guilds/{guild.id}.json').exists():
            archive_if_exists = pathlib.Path(f'./json/guilds/archived guilds/{guild.id}.json')
            if archive_if_exists.exists():
                try:
                    shutil.move(archive_if_exists, pathlib.Path('./json/guilds/'))
                except (shutil.Error, OSError) as archive_error:
                    bot_logger.warning(f'Could not un-archive the data file for the server {guild.name}({guild.id}): '
                                       f'{archive_error}')
                    print(f'Could not un-archive the data file for the server {guild.name}({guild.id}): {archive_error}'
                          )
            else:
                with open(f'./json/guild-template.json', 'r', encoding='utf-8') as r_guilds_template:
                    guilds_template = json.load(r_guilds_template)
                guilds_template["name"] = guild.name
                guilds_template["server id"] = guild.id
                with open(f'./json/guilds/{guild.id}.json', 'w', encoding='utf-8') as w_guilds_json:
                    json.dump(guilds_template, w_guilds_json, ensure_ascii=False, indent=4)
                    w_guilds_json.close()
                if guild.owner.id == guild.me.id:
                    admin_role = await guild.create_role(name="admin", permissions=discord.Permissions(permissions=8),
                                                         colour=discord.Colour.orange(), hoist=True, mentionable=True)
                    await guild.me.add_roles(admin_role)
                    guilds_template["auto admin role"] = admin_role.id
                    admin_category = await guild.create_category(name='admin',
                                                                 reason='auto setup of category for admin channels')
                    log_channel = await guild.create_text_channel(
                        name="auto-logging", reason='auto setup of logging channel', category=admin_category,
                        overwrites={guild.default_role: discord.PermissionOverwrite(read_messages=False),
                                    admin_role: discord.PermissionOverwrite(read_messages=True)})
                    guilds_template["log channel"] = log_channel.id
                with open(f'./json/guilds/{guild.id}.json', 'w', encoding='utf-8') as w_admin_role_json:
                    json.dump(guilds_template, w_admin_role_json, ensure_ascii=False, indent=4)
                    w_admin_role_json.close()
        await self.client.change_presence(
            activity=discord.Game(f'{self.client.command_prefix}help | in {str(len(self.client.guilds))} servers'))
        try:
            invite = await guild.text_channels[0].create_invite(max_age=0, max_uses=0)
        except discord.HTTPException:
            invite = None

        if invite is None:
            log_invite = "(Did not have permission to create invite)"
        else:
            log_invite = invite
        owner_name = f"{guild.owner.name}#{guild.owner.discriminator}" if int(guild.owner.discriminator) else \
            guild.owner.name
        guild_logging.info(f'joined "{guild.name}" Guild ID:{guild.id} Invite:{log_invite}'
                           f' Owner:{owner_name} Owner ID:{guild.owner.id}')

        app = await self.client.application_info()
        bot_logger.info(f'joined "{guild.name}" Guild ID:{guild.id} Invite:{log_invite}'
                        f' Owner:{owner_name} Owner ID:{guild.owner.id}')
        embed = utils.default_embed(self.client, f'Joined {guild.name}', f'check `./logs/guilds.log` for details',
                                    typename=typename)
        embed.set_author(name=f'{self.client.user.name}', icon_url=self.client.user.display_avatar.url)
        embed.set_footer(text=config.default_footer)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name=':1234:Server ID', value=f'{guild.id}')
        if invite is None:
            content = None
        else:
            content = invite.url
            embed.add_field(name=':inbox_tray: Invite', value=f'[{invite.code}]({invite.url})')
        embed.add_field(name=':crown:Owner', value=f'{owner_name}')
        embed.add_field(name=':1234: Owner ID', value=f'{guild.owner.id}')
        embed.add_field(
            name=":key: Permissions", value=utils.has_permissions(guild.me.guild_permissions), inline=False)
        await app.owner.send(content, embed=embed, file=discord.File('./logs/guilds.log'))
        if not os.path.isfile(f'./json/banned-guilds.json'):
            with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                json.dump([], empty_json, ensure_ascii=False, indent=2)
                empty_json.close()
        with open(f'./json/banned-guilds.json', 'r', encoding='utf-8') as ban_file:
            ban_list: list = json.load(ban_file)
        if guild.id in ban_list:
            try:
                await guild.leave()
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        server_data = pathlib.Path(f'./json/guilds/{guild.id}.json')
        if not server_data.exists():
            bot_logger.warning(f'Could not archive the data file for the server {guild.name}({guild.id}) because its '
                               f'missing')
            print(f'Could not archive the data file for the server {guild.name}({guild.id}) because its missing')
        else:
            if guild.owner.id == self.client.user.id:
                server_data.unlink()
            else:
                try:
                    shutil.move(server_data, pathlib.Path('./json/guilds/archived guilds/'))
                except (shutil.Error, OSError) as archive_error:
                    bot_logger.warning(f'Could not archive the data file for the server {guild.name}({guild.id}): '
                                       f'{archive_error}')
                    print(f'Could not archive the data file for the server {guild.name}({guild.id}): {archive_error}')
        await self.client.change_presence(
            activity=discord.Game(f'{self.client.command_prefix}help | in {str(len(self.client.guilds))} servers'))
        owner_name = f"{guild.owner.name}#{guild.owner.discriminator}" if int(guild.owner.discriminator) else \
            guild.owner.name
        guild_logging.info(f'left "{guild.name}" Guild ID:{guild.id}'
                           f' Owner:{owner_name} Owner ID:{guild.owner.id}')

        app = await self.client.application_info()
        bot_logger.info(f'left "{guild.name}" Guild ID:{guild.id}'
                        f' Owner:{owner_name} Owner ID:{guild.owner.id}')
        embed = utils.default_embed(self.client, f'Left {guild.name}', f'check `./logs/guilds.log` for details',
                                    typename=typename)
        embed.set_author(name=f'{self.client.user.name}', icon_url=self.client.user.display_avatar.url)
        embed.set_footer(text=config.default_footer)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name=':1234: Server ID', value=f'{guild.id}')
        embed.add_field(name=':crown: Owner', value=f'{owner_name}')
        embed.add_field(name=':1234: Owner ID', value=f'{guild.owner.id}')
        await app.owner.send(embed=embed, file=discord.File('./logs/guilds.log'))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.owner.id == member.guild.me.id:
            app = await self.client.application_info()
            if member.id == app.owner.id and pathlib.Path(f"./json/guilds/{member.guild.id}.json").exists():
                with open(f"./json/guilds/{member.guild.id}.json", 'r', encoding="utf-8") as r_guild:
                    try:
                        guild_json = json.load(r_guild)
                    except (json.JSONDecodeError, ValueError):
                        bot_logger.warning(f"{member.guild.id}.json lost its format")
                        print(f"{member.guild.id}.json lost its format")
                    else:
                        if guild_json.get("auto admin role") is not None and \
                                member.get_role(guild_json.get("auto admin role")) is None:
                            role = member.guild.get_role(guild_json.get("auto admin role"))
                            await member.add_roles(role)

    async def psa_message(self, ctx: Union[discord.ApplicationContext, commands.Context]):
        if not os.path.isfile(f'json/psa-messages.json'):
            with open("json/psa-messages-template.json") as psa_template_file:
                psa_messages_template = json.load(psa_template_file)
            with open(f'json/psa-messages.json', 'w', encoding='utf-8') as empty_json:
                json.dump(psa_messages_template, empty_json, ensure_ascii=False, indent=2)
                empty_json.close()
        with open("json/psa-messages.json", "r") as message_file:
            psa_data = json.load(message_file)
        if (
                psa_data["active"] and ctx.guild and ctx.guild.me and ctx.guild.id not in psa_data["posted to"]
                and psa_data["content"] and ctx.command.name != "write-psa"
        ):
            if psa_data["embed"]:
                await utils.send_type(ctx)(
                    embed=utils.default_embed(
                        ctx, f"{ctx.bot.user.display_name} Public Service Announcement", psa_data["content"]
                    )
                )
            else:
                await utils.send_type(ctx)(psa_data["content"])
            psa_data["posted to"].append(ctx.guild.id)
            if set(psa_data["posted to"]) == set([guild.id for guild in self.client.guilds]):
                psa_data["active"] = False
            with open("json/psa-messages.json", "w") as message_file:
                json.dump(psa_data, message_file, indent=2)

    @commands.Cog.listener()
    async def on_application_command_completion(self, ctx: discord.ApplicationContext):
        await self.psa_message(ctx)
        if self.client.is_closed():
            return
        if ctx.cog is None:
            cog_name = None
        else:
            cog_name = ctx.cog.qualified_name
        try:
            message = await ctx.interaction.original_response()
        except discord.HTTPException:
            message_content = "Unknown"
            message_jump_url = f"https://discord.com/channels/{ctx.guild}/{ctx.channel}/"
        else:
            message_content = message.content
            message_jump_url = message.jump_url
        if utils.is_dm_channel(ctx.channel):
            channel_name = 'DM Channel'
            guild_name = 'No Guild'
        else:
            channel_name = f'#{ctx.channel.name}'
            guild_name = ctx.guild.name
        if ctx.command.full_parent_name == "":
            full = ""
        else:
            full = f'{ctx.command.full_parent_name}: '
        command_logging.info(f'Command Finished Invoking. Details: '
                             f'{guild_name}, '
                             f'{channel_name}, '
                             f'{ctx}({ctx.user.id}): '
                             f'{message_content} ({cog_name}: {full}'
                             f'{ctx.command.qualified_name}({ctx.command.qualified_name}): '
                             f'({message_jump_url})')
        bot_logger.debug(f'Command Finished Invoking. Details: '
                         f'{guild_name}, '
                         f'{channel_name}, '
                         f'{ctx.user}({ctx.user.id}): '
                         f'{message_content} ({cog_name}: {full}'
                         f'{ctx.command.qualified_name}({ctx.command.qualified_name}): '
                         f'({message_jump_url})')

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        await self.psa_message(ctx)
        if self.client.is_closed():
            return
        if ctx.cog is None:
            cog_name = None
        else:
            cog_name = ctx.cog.qualified_name
        if utils.is_dm_channel(ctx.channel):
            channel_name = 'DM Channel'
            guild_name = 'No Guild'
        else:
            channel_name = f'#{ctx.channel.name}'
            guild_name = ctx.guild.name
        if ctx.command.full_parent_name == "":
            full = ""
        else:
            full = f'{ctx.command.full_parent_name}: '
        command_logging.info(f'Command Finished Invoking. Details: '
                             f'{guild_name}, '
                             f'{channel_name}, '
                             f'{ctx.message.author}({ctx.message.author.id}): '
                             f'{ctx.message.content} ({cog_name}: {full}'
                             f'{ctx.invoked_with}({ctx.command.name}): '
                             f'({ctx.message.jump_url})')
        bot_logger.debug(f'Command Finished Invoking. Details: '
                         f'{guild_name}, '
                         f'{channel_name}, '
                         f'{ctx.message.author}({ctx.message.author.id}): '
                         f'{ctx.message.content} ({cog_name}: {full}'
                         f'{ctx.invoked_with}({ctx.command.name}): '
                         f'({ctx.message.jump_url})')

        if isinstance(ctx.command, (commands.Group, discord.SlashCommandGroup, bridge.BridgeCommandGroup)):
            if ctx.invoked_subcommand is None:
                has_base_function = bool(ctx.command.brief)
                if not has_base_function:
                    await ctx.send(embed=utils.warning_embed(ctx.bot, f'No subcommand was executed',
                                                             f'type `{self.client.command_prefix}help '
                                                             f'{ctx.command}` for a list of subcommands'))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        app = await self.client.application_info()

        if message.author.id == self.client.user.id:
            if utils.is_dm_channel(message.channel):
                location = "a DM Channel "
            else:
                location = f'{message.guild}, in  # {message.channel} '
            if len(message.embeds) > 0:
                embeds = f' ({len(message.embeds)} embeds)'
            else:
                embeds = ""
            command_logging.info(
                f'{self.client.user} ({self.client.user.id}) sent a message: '
                f'{message.content}{embeds} (in {location})({message.jump_url})')
            bot_logger.info(
                f'{self.client.user} ({self.client.user.id}) sent a message: '
                f'{message.content}{embeds} (in {location})({message.jump_url})')

        if utils.is_dm_channel(message.channel):
            if message.author.id != self.client.user.id and message.author.id != app.owner.id:
                embed = utils.default_embed(self.client, f'{message.author} ({message.author.id}) sent a dm',
                                                         f'{message.content}')
                embed.set_author(name=f'{message.author.name} - {message.created_at.strftime(config.dt_string)}',
                                 icon_url=message.author.display_avatar.url)
                user = message.author
                fetched_user = await self.client.fetch_user(user.id)
                embed = utils.user_profile(self.client, fetched_user,
                                           user if isinstance(user, discord.Member) else None, embed)
                bot_message = await app.owner.send(embed=embed)
                if len(message.attachments) > 0:
                    files = []
                    for x in message.attachments:
                        the_file = await x.to_file()
                        files.append(the_file)
                    await bot_message.reply('**Attachments:**', files=files)
                if len(message.embeds) > 0:
                    for x in message.embeds:
                        await bot_message.reply('**Embed:**', embed=x)

            if len(message.embeds) > 0:
                embeds = f' ({len(message.embeds)} embeds)'
            else:
                embeds = ""
            dm_logging.info(
                f'{message.author} ({message.author.id}) sent a dm: '
                f'{message.content}{embeds} (in a DM Channel) ({message.jump_url})')

            bot_logger.info(
                f'{message.author} ({message.author.id}) sent a dm: '
                f'{message.content}{embeds} (in a DM Channel) ({message.jump_url})')
        else:
            if not os.path.isfile(f'./json/banned-guilds.json'):
                with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                    json.dump([], empty_json, ensure_ascii=False, indent=2)
                    empty_json.close()
            with open(f'./json/banned-guilds.json', 'r', encoding='utf-8') as ban_file:
                ban_list: list = json.load(ban_file)
            if message.guild.id in ban_list:
                try:
                    await message.guild.leave()
                except discord.HTTPException:
                    pass


def setup(client):
    client.add_cog(Logging(client))
