import asyncio
import datetime
import json
import pathlib
import io
import signal
from inspect import Parameter
import discord
import sys
import os
from typing import Union, Optional
import subprocess

from discord.ext.bridge import BridgeOption

import config
import aiohttp
from discord import MISSING
from discord.ext import commands, bridge, pages
import utils
from fillins import cogchecks

supported_encodings = ['ascii', 'utf-8', 'utf-16', 'utf-32', 'binary', 'hexadecimal', 'decimal bytes', 'byte string']


class TestException(config.RevnobotException):
    def __init__(self, custom_message=None):
        message = custom_message if custom_message else "This exception was raised for testing purposes"
        super().__init__(message)


class TextChannelSelection(discord.ui.Select):
    def __init__(self, ctx: commands.Context, channel_purpose: str):
        self.ctx = ctx
        self.purpose = channel_purpose

        super().__init__(
            select_type=discord.ComponentType.channel_select,
            placeholder=f"Choose a channel to send {channel_purpose} messages to",
            min_values=0,
            max_values=1,
            channel_types=[discord.ChannelType.text]
        )

    async def callback(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        app_ctx = discord.ApplicationContext(self.ctx.bot, interaction)
        raw_selection: Optional[int] = None
        if len(self.values) < 1:
            selection: str = "None"
        else:
            # noinspection PyTypeChecker
            channel: discord.abc.GuildChannel = self.values[0]
            if channel is None:
                message = f"There was an issue validating the channel selected! Try selecting another channel"
                embed.description = message + self.view.embed_suffix
                await interaction.response.edit_message(embed=embed, view=self.view)
                await app_ctx.respond(embed=utils.default_embed(self.ctx,
                                                                f"Couldn't Set {self.purpose.capitalize()} Channel",
                                                                message), ephemeral=True)
                return
            elif not channel.permissions_for(interaction.guild.me).send_messages:
                message = f'I cannot send messages in {channel.mention}!'
                embed.description = message + self.view.embed_suffix
                await interaction.response.edit_message(embed=embed, view=self.view)
                await app_ctx.respond(embed=utils.default_embed(self.ctx,
                                                                f"Couldn't Set {self.purpose.capitalize()} Channel",
                                                                message), ephemeral=True)
                return
            else:
                selection = channel.mention
                raw_selection = channel.id

        message = f"You selected the channel: {selection} for {self.purpose} messages" \
            if raw_selection is not None else f"You didn't set a {self.purpose} channel"
        embed.description = message + self.view.embed_suffix
        field_exists = False
        for idx, field in enumerate(embed.fields):
            if field.name == f'{self.purpose.capitalize()} Channel':
                embed.set_field_at(idx, name=field.name, value=selection)
                field_exists = True
                break
        if not field_exists:
            embed.add_field(name=f'{self.purpose.capitalize()} Channel', value=selection)
        with open(f'./json/guilds/{interaction.guild.id}.json', 'r', encoding='utf-8') as guild_info_handle:
            guild_info = json.load(guild_info_handle)
            guild_info_handle.close()
        guild_info[f"{self.purpose} channel"] = raw_selection
        with open(f'./json/guilds/{interaction.guild.id}.json', 'w', encoding='utf-8') as write_guild_info:
            json.dump(guild_info, write_guild_info, indent=4)
            write_guild_info.close()
        await interaction.response.edit_message(embed=embed, view=self.view)
        await app_ctx.respond(embed=utils.default_embed(self.ctx, "Value Set", "You have set the following value:",
                                                        fields=[discord.EmbedField(
                                                            name=f'{self.purpose.capitalize()} Channel',
                                                            value=selection)]),
                              ephemeral=True)


class TextChannelClearBtn(discord.ui.Button):
    def __init__(self, ctx: commands.Context, channel_purpose: str, row: int):
        self.ctx = ctx
        self.purpose = channel_purpose

        super().__init__(style=discord.ButtonStyle.red, label="Clear", row=row)

    async def callback(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        app_ctx = discord.ApplicationContext(self.ctx.bot, interaction)
        raw_selection: Optional[int] = None
        selection: str = "None"
        message = f"You selected the channel: {selection} for {self.purpose} messages" \
            if raw_selection is not None else f"You didn't set a {self.purpose} channel"
        embed.description = message + self.view.embed_suffix
        field_exists = False
        for idx, field in enumerate(embed.fields):
            if field.name == f'{self.purpose.capitalize()} Channel':
                embed.set_field_at(idx, name=field.name, value=selection)
                field_exists = True
                break
        if not field_exists:
            embed.add_field(name=f'{self.purpose.capitalize()} Channel', value=selection)
        with open(f'./json/guilds/{interaction.guild.id}.json', 'r', encoding='utf-8') as guild_info_handle:
            guild_info = json.load(guild_info_handle)
            guild_info_handle.close()
        guild_info[f"{self.purpose} channel"] = raw_selection
        with open(f'./json/guilds/{interaction.guild.id}.json', 'w', encoding='utf-8') as write_guild_info:
            json.dump(guild_info, write_guild_info, indent=4)
            write_guild_info.close()

        await interaction.response.edit_message(embed=embed, view=self.view)
        await app_ctx.respond(embed=utils.default_embed(self.ctx, "Value Set", "You have set the following value:",
                                                        fields=[discord.EmbedField(
                                                            name=f'{self.purpose.capitalize()} Channel',
                                                            value=selection)]),
                              ephemeral=True)


class EventMessageInput(discord.ui.InputText):
    def __init__(self, ctx: commands.Context, message_purpose: str):
        self.ctx = ctx
        self.purpose = message_purpose
        with open(f'./json/guilds/{ctx.guild.id}.json', 'r', encoding='utf-8') as guild_info_handle:
            self.guild_info: dict = json.load(guild_info_handle)
            guild_info_handle.close()
        join_leave: dict = self.guild_info["join leave"]
        self.field: str = join_leave[f'{self.purpose} message']
        self.field = self.field.replace("\n", "\\n")
        super().__init__(label=f"Please edit the current {self.purpose} message", value=f"{self.field}", min_length=1,
                         max_length=2000)


class EventMessageModal(discord.ui.Modal):
    def __init__(self, ctx: commands.Context, view, button: discord.ui.Button):
        self.ctx = ctx
        self.view = view
        self.item = button
        super().__init__(EventMessageInput(self.ctx, "welcome"), EventMessageInput(self.ctx, "leave"),
                         title="Set welcome and leave messages")

    async def on_error(self, error: Exception, interaction: discord.Interaction):
        await self.view.on_error(error, self.item, interaction)

    async def callback(self, interaction: discord.Interaction):
        app_ctx = discord.ApplicationContext(self.ctx.bot, interaction)
        welcome_message = self.children[0].value.replace("\\n", "\n")
        leave_message = self.children[1].value.replace("\\n", "\n")
        embed = interaction.message.embeds[0]
        welcome_args = {"user_mention": "placeholder", "server_member_count": "placeholder",
                        "server_name": "placeholder"}
        leave_args = {"username": "placeholder"}
        for field, field_args, field_name in [(welcome_message, welcome_args, "welcome"),
                                              (leave_message, leave_args, "leave")]:
            fixed_args = list(field_args.keys()).copy()
            for key in fixed_args:
                if "{" + key + "}" not in field:
                    field_args.pop(key)
            try:
                field.format(**field_args)
            except KeyError as out_key:
                message = (f"Invalid variable in {field_name} message: **{out_key}** is not a valid variable.\n"
                           f"Valid variable names are: **{', '.join(fixed_args)}**")
                embed.description = message + self.view.embed_suffix
                await interaction.response.edit_message(embed=embed, view=self.view)
                await app_ctx.respond(embed=utils.default_embed(self.ctx,
                                                                f"Couldn't Set {field_name.capitalize()} Message",
                                                                message), ephemeral=True)
                return
            except ValueError:
                message = f"Invalid Syntax: {field_name} message can't contain unmatched curly braces " + \
                          "(\"{\" or \"}\" on their own) and only \"{\" and \"}\" when specifying a variable."
                embed.description = message + self.view.embed_suffix
                await interaction.response.edit_message(embed=embed, view=self.view)
                await app_ctx.respond(embed=utils.default_embed(self.ctx,
                                                                f"Couldn't Set {field_name.capitalize()} Message",
                                                                message), ephemeral=True)
                return
        for field_text, field_name in [(welcome_message, "welcome"), (leave_message, "leave")]:
            if utils.is_empty(field_text):
                message = f"The {field_name} message can't be empty or just spaces"
                embed.description = message + self.view.embed_suffix
                await interaction.response.edit_message(embed=embed, view=self.view)
                await app_ctx.respond(embed=utils.default_embed(self.ctx,
                                                                f"Couldn't Set {field_name.capitalize()} Message",
                                                                message), ephemeral=True)
                return
        embed.description = f'You have set the welcome message as "{welcome_message}" and the leave message as ' \
                            f'"{leave_message}".' + self.view.embed_suffix
        for idx, field in enumerate(embed.fields):
            if field.name == "Welcome Message":
                embed.set_field_at(idx, name=field.name, value=welcome_message)
            if field.name == "Leave Message":
                embed.set_field_at(idx, name=field.name, value=leave_message)

        with open(f'./json/guilds/{interaction.guild.id}.json', 'r', encoding='utf-8') as guild_info_handle:
            guild_info: dict = json.load(guild_info_handle)
        join_leave: dict = guild_info["join leave"]
        join_leave["welcome message"] = welcome_message
        join_leave["leave message"] = leave_message
        guild_info["join leave"] = join_leave
        with open(f'./json/guilds/{interaction.guild.id}.json', 'w', encoding='utf-8') as write_guild_info:
            json.dump(guild_info, write_guild_info, indent=4)
            write_guild_info.close()
        await interaction.response.edit_message(embed=embed, view=self.view)
        await app_ctx.respond(embed=utils.default_embed(self.ctx, "Values Set",
                                                        "You have set the following values:",
                                                        fields=[discord.EmbedField(name="Welcome Message",
                                                                                   value=welcome_message),
                                                                discord.EmbedField(name="Leave Message",
                                                                                   value=leave_message)]),
                              ephemeral=True)


class RoleSelection(discord.ui.Select):
    def __init__(self, ctx: commands.Context, role_purpose: str):
        self.ctx = ctx
        self.purpose = role_purpose
        super().__init__(
            placeholder=f"Choose a {role_purpose} role",
            min_values=0,
            max_values=1,
            select_type=discord.ComponentType.role_select
        )

    async def callback(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        app_ctx = discord.ApplicationContext(self.ctx.bot, interaction)
        raw_selection: Optional[int] = None
        if len(self.values) < 1:
            selection: str = "None"
        else:
            # noinspection PyTypeChecker
            role: discord.Role = self.values[0]
            if role is None:
                message = f"There was an issue validating the role selected! Try selecting another role"
                embed.description = message + self.view.embed_suffix
                await interaction.response.edit_message(embed=embed, view=self.view)
                await app_ctx.respond(embed=utils.default_embed(self.ctx,
                                                                f"Couldn't Set {self.purpose.capitalize()} Role",
                                                                message), ephemeral=True)
                return
            elif not role.is_assignable():
                message = (
                    f'I do not have permission to give or remove {role.mention}!\nMake sure the role is below '
                    f'{self.ctx.guild.self_role.mention if self.ctx.guild.self_role else "my highest role (if any)"} '
                    f'and I have permission to add and remove roles.'
                )
                embed.description = message + self.view.embed_suffix
                await interaction.response.edit_message(embed=embed, view=self.view)
                await app_ctx.respond(embed=utils.default_embed(self.ctx,
                                                                f"Couldn't Set {self.purpose.capitalize()} Role",
                                                                message), ephemeral=True)
                return
            else:
                selection = role.mention
                raw_selection = role.id

        message = f"You selected the role: {selection} as the {self.purpose} role" \
            if raw_selection is not None else f"You didn't set a {self.purpose} role"
        embed.description = message + self.view.embed_suffix
        field_exists = False
        for idx, field in enumerate(embed.fields):
            if field.name == f'{self.purpose.capitalize()} Role':
                embed.set_field_at(idx, name=field.name, value=selection)
                field_exists = True
                break
        if not field_exists:
            embed.add_field(name=f'{self.purpose.capitalize()} Role', value=selection)
        with open(f'./json/guilds/{interaction.guild.id}.json', 'r', encoding='utf-8') as guild_info_handle:
            guild_info = json.load(guild_info_handle)
            guild_info_handle.close()
        guild_info[f"{self.purpose} role"] = raw_selection
        with open(f'./json/guilds/{interaction.guild.id}.json', 'w', encoding='utf-8') as write_guild_info:
            json.dump(guild_info, write_guild_info, indent=4)
            write_guild_info.close()
        await interaction.response.edit_message(embed=embed, view=self.view)
        await app_ctx.respond(embed=utils.default_embed(self.ctx, "Value Set", "You have set the following value:",
                                                        fields=[discord.EmbedField(
                                                            name=f'{self.purpose.capitalize()} Role',
                                                            value=selection)]),
                              ephemeral=True)


class RoleClearBtn(discord.ui.Button):
    def __init__(self, ctx: commands.Context, role_purpose: str, row: int):
        self.ctx = ctx
        self.purpose = role_purpose
        super().__init__(style=discord.ButtonStyle.red, label="Clear", row=row)

    async def callback(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        app_ctx = discord.ApplicationContext(self.ctx.bot, interaction)
        raw_selection: Optional[int] = None
        selection: str = "None"
        message = f"You selected the role: {selection} as the {self.purpose} role" \
            if raw_selection is not None else f"You didn't set a {self.purpose} role"
        embed.description = message + self.view.embed_suffix
        field_exists = False
        for idx, field in enumerate(embed.fields):
            if field.name == f'{self.purpose.capitalize()} Role':
                embed.set_field_at(idx, name=field.name, value=selection)
                field_exists = True
                break
        if not field_exists:
            embed.add_field(name=f'{self.purpose.capitalize()} Role', value=selection)
        with open(f'./json/guilds/{interaction.guild.id}.json', 'r', encoding='utf-8') as guild_info_handle:
            guild_info = json.load(guild_info_handle)
            guild_info_handle.close()
        guild_info[f"{self.purpose} role"] = raw_selection
        with open(f'./json/guilds/{interaction.guild.id}.json', 'w', encoding='utf-8') as write_guild_info:
            json.dump(guild_info, write_guild_info, indent=4)
            write_guild_info.close()
        await interaction.response.edit_message(embed=embed, view=self.view)
        await app_ctx.respond(embed=utils.default_embed(self.ctx, "Value Set", "You have set the following value:",
                                                        fields=[discord.EmbedField(
                                                            name=f'{self.purpose.capitalize()} Role',
                                                            value=selection)]),
                              ephemeral=True)


class SetupView(utils.DefaultView):
    def __init__(self, ctx: commands.Context, timeout: float = 500):
        self.current_page = 0
        self.embed_suffix = "\n\n**Values Set:**"
        super().__init__(timeout=timeout, context=ctx)
        selector_types = {
            "channel": [TextChannelSelection, TextChannelClearBtn],
            "role": [RoleSelection, RoleClearBtn]
        }
        exclusions = ["auto admin"]
        with open("json/guild-template.json") as guild_template_file:
            guild_template = json.load(guild_template_file)
        menu_selectors = {}
        for key in guild_template.keys():
            prefix, suffix = " ".join(key.split(" ")[:-1]), key.split(" ")[-1]
            if suffix in selector_types.keys() and prefix not in exclusions:
                menu_selectors[prefix] = suffix
        self.pages = []
        for purpose, selector_type in menu_selectors.items():
            method = self.pages.append
            row = 1
            if len(self.pages) > 0 and len(self.pages[-1]) < 3:
                method = self.pages[-1].extend
                row = len(self.pages[-1]) + 1
            method([
                selector_types[selector_type][0](self.ctx, purpose),
                selector_types[selector_type][1](self.ctx, purpose, row)
            ])
        for item in self.pages[0]:
            self.add_item(item)

    @discord.ui.button(label='Prev', style=discord.ButtonStyle.blurple, disabled=True, row=4)
    async def prev_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.current_page -= 1
        if self.current_page == 0:
            button.disabled = True
        if isinstance(self.pages[0], list):
            for item in self.pages[self.current_page + 1]:
                self.remove_item(item)
            for item in self.pages[self.current_page]:
                self.add_item(item)
        if self.current_page + 1 < len(self.pages):
            row_4 = [child for child in self.children if child.row == 4]
            next_btn = row_4[1]
            if isinstance(next_btn, discord.ui.Button):
                next_btn.disabled = False
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.blurple, disabled=False, row=4)
    async def next_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.current_page += 1
        if self.current_page + 1 == len(self.pages):
            button.disabled = True

        if isinstance(self.pages[0], list):
            for item in self.pages[self.current_page - 1]:
                self.remove_item(item)
            for item in self.pages[self.current_page]:
                self.add_item(item)
        if self.current_page > 0:
            row_4 = [child for child in self.children if child.row == 4]
            prev_btn = row_4[0]
            if isinstance(prev_btn, discord.ui.Button):
                prev_btn.disabled = False
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Set welcome and leave messages", style=discord.ButtonStyle.primary, row=4)
    async def event_message(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(EventMessageModal(self.ctx, self, button))

    @discord.ui.button(label="Finish Setup", style=discord.ButtonStyle.green, row=4)
    async def done_button(self, _: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await self.message.edit(view=self)


class InvalidConfiguration(config.RevnobotException):
    pass


class FileExistsView(utils.DefaultView):
    def __init__(self, input_filedir: Union[str, os.PathLike], message: discord.Message, bot: discord.Bot,
                 timeout: int = 60):
        super().__init__(timeout=timeout, bot=bot, message=message)
        if isinstance(input_filedir, str):
            input_filedir = pathlib.Path(input_filedir)
        self.input_filedir = input_filedir
        self.filename_to_write = None
        self.selected_button = None

    async def button_press(self, button: discord.ui.Button, interaction: discord.Interaction,
                           button_pressed: str = None):
        self.selected_button = button_pressed
        for child in button.view.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label='Replace File', style=discord.ButtonStyle.green)
    async def replace_file(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.filename_to_write = self.input_filedir.name
        await self.button_press(button, interaction, 'replace')

    @discord.ui.button(label='Keep Both', style=discord.ButtonStyle.blurple)
    async def keep_both(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.filename_to_write = utils.keep_file(self.input_filedir)
        await self.button_press(button, interaction, 'keep')

    @discord.ui.button(label='Skip', style=discord.ButtonStyle.red)
    async def skip(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.button_press(button, interaction, None)


class SystemExecuteView(utils.DefaultView):
    def __init__(
            self, process: Union[subprocess.Popen[bytes], subprocess.Popen],
            message: discord.Message, bot: discord.Bot, timeout: int = 60
    ):
        super().__init__(timeout=timeout, bot=bot, message=message)
        self.selected_button = None
        self.process = process

    @discord.ui.button(label='Kill', style=discord.ButtonStyle.grey)
    async def kill(self, _: discord.ui.Button, interaction: discord.Interaction):
        self.process.kill()
        await interaction.response.defer()
        self.process.wait()

    @discord.ui.button(label='Terminate', style=discord.ButtonStyle.grey)
    async def terminate(self, _: discord.ui.Button, interaction: discord.Interaction):
        self.process.terminate()
        await interaction.response.defer()
        self.process.wait()

    @discord.ui.button(label='Ctrl-C', style=discord.ButtonStyle.grey)
    async def sigint(self, _: discord.ui.Button, interaction: discord.Interaction):
        self.process.send_signal(signal.SIGINT)
        await interaction.response.defer()
        self.process.wait()


class Owner(config.RevnobotCog):
    """owner only commands"""
    def __init__(self, client: bridge.Bot):
        self.client = client
        self.description = "owner only commands"
        self.icon = "\U0001F451"
        self.hidden = True

    async def cog_check(self, ctx: Union[discord.ApplicationContext, commands.Context]) -> bool:
        check = await self.client.is_owner(ctx.author)
        if not check:
            raise commands.NotOwner('You do not own this bot.')
        return True

    @bridge.bridge_command(
        name='test', description="Hello World",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def test_cmd(self, ctx: bridge.Context):
        embed = utils.minimal_embed("Hello World")
        message = await ctx.respond(embed=embed)
        if isinstance(message, discord.Interaction):
            message = await message.original_response()
        await message.edit("This is an \u202b message")

    # noinspection PyTypeHints
    @bridge.bridge_command(name='echo', description="echo your message back", usage="{prefix}{name} [message]")
    @commands.cooldown(**config.default_cooldown_options)
    @commands.bot_has_permissions(send_messages=True)
    async def echo_cmd(self, ctx: bridge.Context, *, message: BridgeOption(str, "The message to echo back")):
        await ctx.respond(embed=utils.minimal_embed(f'{message}', use_title=False))

    @bridge.bridge_command(name='raise-test', description="Raise an exception on purpose",
                           usage="{prefix}{name} [custom exception message](optional)")
    @commands.cooldown(**config.default_cooldown_options)
    @commands.bot_has_permissions(send_messages=True)
    async def raise_test_cmd(self, ctx: bridge.Context, *, custom: str = None):
        await ctx.respond(embed=utils.minimal_embed("Raising TestException...."))
        raise_message = custom or 'This exception was raised on purpose by the raise-test command'
        raise TestException(raise_message)

    @commands.command(name='reply', description="@Hello World")
    @commands.cooldown(**config.default_cooldown_options)
    async def reply_cmd(self, ctx: commands.Context):
        await ctx.reply(embed=utils.minimal_embed('Hello World'))

    # noinspection SpellCheckingInspection
    @bridge.bridge_command(name="dm", description="DM: Hello World", aliases=['dmtest', 'dm-test'])
    @commands.cooldown(**config.default_cooldown_options)
    async def dm_cmd(self, ctx: bridge.Context):
        await ctx.defer()
        try:
            await ctx.author.send(embed=utils.minimal_embed('Hello World'))
        except discord.HTTPException:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Couldn't DM you", "Make sure you have server DMs on or Im not blocked and try again"
            ))
        else:
            await ctx.respond(embed=utils.default_embed(ctx, 'Check Your DMs', ""))

    # noinspection SpellCheckingInspection,PyTypeChecker
    @bridge.bridge_command(name='setup', description='Configure Revnobot in your server')
    @bridge.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(send_messages=True)
    @commands.cooldown(**config.default_cooldown_options)
    @cogchecks.bridge_contexts(discord.InteractionContextType.guild)
    async def setup_cmd(self, ctx: bridge.Context):
        config_path = pathlib.Path(f"./json/guilds/{ctx.guild.id}.json")
        if not config_path.exists():
            with open(f'./json/guild-template.json', 'r', encoding='utf-8') as r_guilds_template:
                guilds_template: dict = json.load(r_guilds_template)
                r_guilds_template.close()
            guilds_template["name"] = ctx.guild.name
            guilds_template["server id"] = ctx.guild.id
            json_bytes = json.dumps(guilds_template, ensure_ascii=False).encode("utf-8")
            with open(f'./json/guilds/{ctx.guild.id}.json', 'wb') as w_guild_config:
                w_guild_config.write(json_bytes)
                w_guild_config.close()
            server_config = guilds_template
        else:
            with open(f'./json/guilds/{ctx.guild.id}.json', 'r', encoding='utf-8') as config_handle:
                server_config: dict = json.load(config_handle)
        # noinspection SpellCheckingInspection
        embed = utils.default_embed(
            ctx, "Setup Configuration",
            "To properly configure Revnobot, you need fill out or change the values below\n\n"
            "**Note:** Due to discord limitations, already set options cannot initially be displayed in the select "
            "menus. Please use the clear button below each of the select menus to unset the already set values. "
            "\n\n**Values Set:**",
        )
        for name, value in server_config.items():
            if name == "join leave":
                embed.add_field(name="Welcome Message", value=value["welcome message"])
                embed.add_field(name="Leave Message", value=value["leave message"])
            else:
                if name.endswith('channel'):
                    channel = ctx.guild.get_channel(value)
                    if channel is not None:
                        value = channel.mention
                if name.endswith('role'):
                    channel = ctx.guild.get_role(value)
                    if channel is not None:
                        value = channel.mention
                if name != "auto admin role" and name != "raid protection mode":
                    embed.add_field(name=name.title(), value=f'{value}')
        if len(embed.fields) > 25:
            embed.clear_fields()
            embed.add_field(
                name=":x: Too Many Fields",
                value=(
                    "There were too many fields to be displayed."
                    "\nThis is most likely a bug that has caused this and not too many fields. "
                    "So this occurrence should be [reported]"
                    "(https://github.com/Revnoplex/revnobot-public/issues/new/choose) on the "
                    "[public github](https://github.com/revnoplex/revnobot-public)"
                )
            )
        await ctx.respond(embed=embed, view=SetupView(ctx, 500))

    # noinspection SpellCheckingInspection
    @bridge.bridge_command(
        name='guild-ls',
        aliases=[
            'guild_ls', 'guildls', 'server-ls', 'serverls', 'connected_guilds', 'connected-guilds', 'connectedguilds',
            'connected_servers', 'connected-servers', 'connectedservers', 'guild-count', 'guild_count'
        ],
        description="lists all the guilds the bot is in"
    )
    @commands.bot_has_permissions(send_messages=True)
    async def guild_ls(self, ctx: bridge.Context):
        """lists all the guilds the bot is in"""
        if len(self.client.guilds) <= 25:
            embed = utils.default_embed(ctx, f'Connected to {len(self.client.guilds)} Guilds', '')
            for x in self.client.guilds:
                embed.add_field(name=f'<:DiscordLogo:882561395982495754> {x.name}', value=f'{x.id}\n'
                                                                                          f'{x.member_count} Members')
            await ctx.respond(embed=embed)
        else:
            embed_pages = []
            data_pages = [self.client.guilds[x:x + 25] for x in range(0, len(self.client.guilds), 25)]
            for index, data_page in enumerate(data_pages):
                embed = utils.default_embed(
                    ctx, f'Connected to {len(self.client.guilds)} Guilds',
                    f'{index + 1}/{len(data_pages)}'
                )
                for x in data_page:
                    embed.add_field(name=f'<:DiscordLogo:882561395982495754> {x.name}', value=f'{x.id}')
                embed_pages.append(embed)
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    @bridge.bridge_command(
        name="vc-ls", description="list how many voice channels the bot is currently in",
        aliases=["vc_ls", "list-vcs", "list_vcs"]
    )
    @commands.bot_has_permissions(send_messages=True)
    async def vc_ls_cmd(self, ctx: bridge.Context):
        voice_clients = self.client.voice_clients
        if len(voice_clients) <= 25:
            vc_embed = utils.default_embed(ctx, f"Connected to {len(voice_clients)} Voice Channels", "")
            for voice_client in self.client.voice_clients:
                status = ""
                if isinstance(voice_client, discord.VoiceClient):
                    guild = "Private Channel" if voice_client.guild is None else \
                        f'<:DiscordLogo:882561395982495754> {voice_client.guild.name} ({voice_client.guild.id})'
                    status = ":pause_button:" if voice_client.is_paused() else ":arrow_forward:" \
                        if voice_client.is_playing() else ""
                else:
                    guild = "Unknown"
                if isinstance(voice_client.channel, (discord.VoiceChannel, discord.StageChannel)):
                    vc_embed.add_field(name=f'{guild}', value=f'{status}{voice_client.channel.mention} '
                                                              f'({voice_client.channel.id})', inline=True)
            await ctx.respond(embed=vc_embed)
        else:
            embed_pages = []
            data_pages = [voice_clients[x:x + 25] for x in range(0, len(voice_clients), 25)]
            for index, data_page in enumerate(data_pages):
                vc_embed = utils.default_embed(ctx, f"Connected to {len(voice_clients)} Voice Channels",
                                               f'{index + 1}/{len(data_pages)}', )
                for voice_client in data_page:
                    status = ""
                    if isinstance(voice_client, discord.VoiceClient):
                        guild = "Private Channel" if voice_client.guild is None else \
                            f'<:DiscordLogo:882561395982495754> {voice_client.guild.name} ({voice_client.guild.id})'
                        status = ":pause_button:" if voice_client.is_paused() else ":arrow_forward:" \
                            if voice_client.is_playing() else ""
                    else:
                        guild = "Unknown"
                    if isinstance(voice_client.channel, (discord.VoiceChannel, discord.StageChannel)):
                        vc_embed.add_field(name=f'{guild}', value=f'{status}{voice_client.channel.mention} '
                                                                  f'({voice_client.channel.id})', inline=True)
                embed_pages.append(vc_embed)
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    @bridge.bridge_group(
        name='update-status', usage='{prefix}{name} [subcommand]', description="Update the status of the bot",
        aliases=['update_status'])
    @commands.bot_has_permissions(send_messages=True)
    @commands.cooldown(**config.default_cooldown_options)
    async def update_status_group(self, ctx: bridge.Context):
        pass

    # noinspection PyTypeHints
    @update_status_group.command(
        name="custom", usage='{name} [custom status]', description="Change bot status completely", aliases=["new"]
    )
    async def update_status_custom_cmd(
            self, ctx: bridge.Context, *, status: BridgeOption(str, "The custom status to set")
    ):
        """change bot status completely"""
        await self.client.change_presence(activity=discord.Game(status))
        await ctx.respond(
            embed=utils.default_embed(
                ctx, "Updated Status",
                f'Successfully changed the bot status to **{status}**'
            )
        )

    # noinspection PyTypeHints
    @update_status_group.command(
        name="append", aliases=['update'], usage='{name} [custom status]',
        description="Change bot status while keeping prefix"
    )
    async def update_status_append_cmd(
            self, ctx: bridge.Context, *, status: BridgeOption(str, "The custom status to append")
    ):
        full_status_str = config.prefix_status_with + status
        await self.client.change_presence(activity=discord.Game(full_status_str))
        await ctx.respond(
            embed=utils.default_embed(
                ctx, "Updated Status", f'Successfully changed the bot status to **{full_status_str}**'
            )
        )

    @update_status_group.command(
        name="reset", aliases=["default"], description='Reset the bots status back to the default'
    )
    async def update_status_reset_cmd(self, ctx: bridge.Context):
        default_status = config.default_status.format(guild_count=len(self.client.guilds))
        await self.client.change_presence(activity=discord.Game(default_status))
        await ctx.respond(
            embed=utils.default_embed(
                ctx, "Updated Status", f'Successfully changed the bot status to **{default_status}**'
            )
        )

    @bridge.bridge_command(name="shutdown", description="Shuts down the bot")
    @commands.bot_has_permissions(send_messages=True)
    async def shutdown(self, ctx: bridge.Context):
        await ctx.respond(embed=utils.default_embed(ctx, "Shutdown", "The bot is shutting down....", ))
        if config.systemd_service:
            utils.sd_notify(b'STOPPING=1')
        print("Bot exited via shutdown command")
        await self.client.close()
        sys.exit('The bot has exited via the shutdown command')

    # noinspection PyTypeHints
    @bridge.bridge_command(name="restart", description="Restarts the bot", aliases=['reboot'])
    @commands.bot_has_permissions(send_messages=True)
    async def restart(self, ctx: bridge.Context):
        await ctx.respond(embed=utils.default_embed(ctx, "Restart", "The bot is restarting....", ))
        print('System will restart because of the restart command....')
        if sys.argv:
            os.execl(sys.argv[0], sys.argv[0], " ".join(sys.argv[1:]))
        os.execl(sys.executable, sys.executable)

    @bridge.bridge_group(
        name="guild-tools", aliases=["guild_tools", "server-tools", "server_tools"],
        description="Create and delete servers", usage="{prefix}{name} [subcommand]"
    )
    @commands.bot_has_permissions(send_messages=True)
    async def guild_tools_group(self, ctx: bridge.Context):
        pass

    # noinspection PyTypeHints
    @guild_tools_group.command(
        name='leave', usage='{name} server(id)',
        description="The bot will leave the current server or the server specified"
    )
    @commands.bot_has_permissions(send_messages=True)
    async def guild_tools_leave_cmd(
            self, ctx: bridge.Context, *,
            guild_arg: BridgeOption(str, "A discord server name or ID", name="server", required=False) = None):
        to_leave = None
        if guild_arg is not None:
            if guild_arg.isdecimal():
                to_leave = self.client.get_guild(int(guild_arg))
            else:
                to_leave = discord.utils.find(lambda n: n.name == guild_arg, self.client.guilds)
            if to_leave is None:
                raise commands.BadArgument(f'Guild "{guild_arg}" not found.')
        to_leave = to_leave or ctx.guild
        if to_leave is None:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Guild Not Found",
                    f"The Guild {guild_arg} doesn't exist or I'm not in it."
                )
            )
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Leaving Guild....", f'Leaving **{to_leave.name}** `{to_leave.id}`'
                )
            )
            await to_leave.leave()

    # noinspection SpellCheckingInspection
    @bridge.bridge_group(
        name='g-send', usage='{prefix}{name} [subcommand]', description="g-send",
        aliases=['gsend'], contexts={discord.InteractionContextType.bot_dm}
    )
    @commands.bot_has_permissions(send_messages=True)
    @commands.dm_only()
    @commands.cooldown(**config.default_cooldown_options)
    async def g_send_group(self, ctx: bridge.Context):
        pass

    # noinspection PyTypeHints
    @g_send_group.command(name="message", description="g-send", usage='{name} [channel id] [message content]')
    @commands.dm_only()
    async def g_send_message_cmd(
            self, ctx: bridge.Context, channel_id: BridgeOption(str, "A channel or user ID", name="channel"), *,
            content: BridgeOption(str, "The content of the message to send"),
            reply_to: BridgeOption(str, "The ID of a message to reply to", name="reply-to", required=False) = None,
            mention_author: BridgeOption(
                bool, "whether to mention the original author of the message specified in reply-to",
                name="mention-author", required=False
            ) = None,
            attachment: BridgeOption(
                discord.Attachment, "The image that will be the server icon", required=False
            ) = None
    ):
        """Command info: (classified)"""
        conversion_err = commands.BadUnionArgument(Parameter("channel", Parameter.POSITIONAL_ONLY,
                                                             annotation=Union[discord.abc.GuildChannel, discord.User]),
                                                   (discord.abc.GuildChannel, discord.User),
                                                   [commands.ChannelNotFound(channel_id),
                                                    commands.UserNotFound(channel_id)])
        message = await ctx.respond(embed=utils.default_embed(
            ctx, "Preparing to send message", f"Preparing to send message to `{channel_id}`", ),
        )
        if isinstance(message, discord.Interaction):
            message = await message.original_response()
        if not channel_id.isdecimal():
            raise conversion_err
        channel = self.client.get_channel(int(channel_id))
        if channel is None:
            channel = self.client.get_user(int(channel_id))
        if channel is None:
            raise conversion_err
        ref_message = None
        if reply_to:
            try:
                ref_message = await channel.fetch_message(reply_to)
            except discord.HTTPException:
                pass
        attachment_file = None
        if (ctx.message and len(ctx.message.attachments) > 0) or attachment:
            message_attachment = (
                ctx.message.attachments[0] if ctx.message and len(ctx.message.attachments) > 0
                else attachment
            )
            if message_attachment.size > 10 * 1024 ** 2:
                await message.edit(embed=utils.default_embed(
                    ctx, "Attachment Too Large",
                    f"The attachment provided of size **{utils.byte_units(message_attachment.size, iec=True)}** is"
                    f" too big and must be less than or equal to **10 MiB**",
                ))
                return
            attachment_file = await message_attachment.to_file()
        await message.edit(embed=utils.default_embed(
            ctx, "Sending Message", f"Sending message to {channel.mention}", ),
        )
        try:
            await channel.send(content, reference=ref_message, mention_author=mention_author, file=attachment_file)
        except discord.HTTPException as http_error:
            await message.edit(embed=utils.default_embed(
                ctx, "Couldn't Send message", f"`{http_error.text}`")
            )
        else:
            if isinstance(channel, discord.User):
                user_name = f"{channel.name}#{channel.discriminator}" if int(channel.discriminator) \
                    else channel.name
                await message.edit(
                    embed=utils.default_embed(ctx, "Message Sent",
                                              f'Sent message to **{user_name} '
                                              f'(`{channel.id}`)', ))
            else:
                await message.edit(
                    embed=utils.default_embed(ctx, "Message Sent",
                                              f'Sent message to #{channel.name} (`{channel.id}`) in '
                                              f'**{channel.guild.name}** (`{channel.guild.id}`)', ))

    # noinspection PyTypeHints
    @g_send_group.command(name="embed", description="g-send", usage='{name} [channel id] [embed title]')
    @commands.dm_only()
    async def g_send_embed_cmd(
            self, ctx: bridge.Context, channel_id: BridgeOption(str, "A channel or user ID", name="channel"), *,
            title: BridgeOption(str, "The title of the embed"),
            colour: BridgeOption(
                str, "The hexadecimal value of a colour", default=config.embed_colour_default
            ) = config.embed_colour_default,
            description: BridgeOption(str, "The description of the embed", default="") = "",
            typename: BridgeOption(str, "The text where the author of the embed is", required=False) = None,
            url: BridgeOption(str, "The URL for the title of the embed", default=None) = None,
            image: BridgeOption(str, "An image URL to set in the embed", required=False) = None,
            reply_to: BridgeOption(str, "The ID of a message to reply to", name="reply-to", required=False) = None,
            mention_author: BridgeOption(
                bool, "whether to mention the original author of the message specified in reply-to",
                name="mention-author", required=False
            ) = None,
            attachment: BridgeOption(
                discord.Attachment, "The image that will be the server icon", required=False
            ) = None
    ):
        """Command info: (classified)"""
        conversion_err = commands.BadUnionArgument(Parameter("channel", Parameter.POSITIONAL_ONLY,
                                                             annotation=Union[discord.abc.GuildChannel, discord.User]),
                                                   (discord.abc.GuildChannel, discord.User),
                                                   [commands.ChannelNotFound(channel_id),
                                                    commands.UserNotFound(channel_id)])
        message = await ctx.respond(embed=utils.default_embed(
            ctx, "Preparing to send message", f"Preparing to send message to `{channel_id}`", ),
        )
        if isinstance(message, discord.Interaction):
            message = await message.original_response()
        if not channel_id.isdecimal():
            raise conversion_err
        channel = self.client.get_channel(int(channel_id))
        if channel is None:
            channel = self.client.get_user(int(channel_id))
        if channel is None:
            raise conversion_err
        embed = utils.default_embed(ctx, f'{title}', f'{description}', colour, typename, url)
        if image:
            embed.set_image(url=image)
        ref_message = None
        if reply_to:
            try:
                ref_message = await channel.fetch_message(reply_to)
            except discord.HTTPException:
                pass
        if (ctx.message and len(ctx.message.attachments) > 0) or attachment:
            message_attachment = (
                ctx.message.attachments[0] if ctx.message and len(ctx.message.attachments) > 0
                else attachment
            )
            if message_attachment.size > 10 * 1024 ** 2:
                await message.edit(embed=utils.default_embed(
                    ctx, "Attachment Too Large",
                    f"The attachment provided of size **{utils.byte_units(message_attachment.size, iec=True)}** is"
                    f" too big and must be less than or equal to **10 MiB**",
                ))
                return
            embed.set_image(url=message_attachment.url)
        await message.edit(embed=utils.default_embed(
            ctx, "Sending Message", f"Sending message to {channel.mention}", ),
        )
        try:
            await channel.send(embed=embed, reference=ref_message, mention_author=mention_author)
        except discord.HTTPException as http_error:
            await message.edit(embed=utils.default_embed(
                ctx, "Couldn't Send message", f"`{http_error.text}`", )
            )
        else:
            if isinstance(channel, discord.User):
                user_name = f"{channel.name}#{channel.discriminator}" if int(channel.discriminator) \
                    else channel.name
                await message.edit(
                    embed=utils.default_embed(ctx, "Message Sent",
                                              f'Sent message to **{user_name} '
                                              f'(`{channel.id}`)', ))
            else:
                await message.edit(
                    embed=utils.default_embed(ctx, "Message Sent",
                                              f'Sent message to #{channel.name} (`{channel.id}`) in '
                                              f'**{channel.guild.name}** (`{channel.guild.id}`)', ))

    # noinspection PyTypeHints
    @g_send_group.command(name="typing", description="g-send", usage='{name} [channel id] [message content]',
                          aliases=["trigger-typing", "trigger_typing"])
    @commands.dm_only()
    async def g_send_typing_cmd(
            self, ctx: bridge.Context, channel_id: BridgeOption(str, "A channel or user ID", name="channel")
    ):
        """Command info: (classified)"""
        conversion_err = commands.BadUnionArgument(Parameter("channel", Parameter.POSITIONAL_ONLY,
                                                             annotation=Union[discord.abc.GuildChannel, discord.User]),
                                                   (discord.abc.GuildChannel, discord.User),
                                                   [commands.ChannelNotFound(channel_id),
                                                    commands.UserNotFound(channel_id)])
        if not channel_id.isdecimal():
            raise conversion_err
        channel = self.client.get_channel(int(channel_id))
        if channel is None:
            channel = self.client.get_user(int(channel_id))
        if channel is None:
            raise conversion_err
        try:
            await channel.trigger_typing()
        except discord.HTTPException as http_error:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Couldn't Trigger Typing", f"`{http_error.text}`")
            )
        else:
            if isinstance(channel, discord.User):
                user_name = f"{channel.name}#{channel.discriminator}" if int(channel.discriminator) \
                    else channel.name
                await ctx.respond(
                    embed=utils.default_embed(ctx, "Triggered Typing",
                                              f'Triggered typing in **{user_name} '
                                              f"(`{channel.id}`)'s DMs", ))
            else:
                await ctx.respond(
                    embed=utils.default_embed(ctx, "Triggered Typing",
                                              f'Triggered Typing in #{channel.name} (`{channel.id}`) in '
                                              f'**{channel.guild.name}** (`{channel.guild.id}`)', ))

    @bridge.bridge_group(name="extension", aliases=["module"], usage="{prefix}{name} [subcommand]",
                         description="Load, unload or reload a module")
    @commands.bot_has_permissions(send_messages=True)
    async def extension_group(self, ctx: bridge.Context):
        pass

    # noinspection PyTypeHints
    @extension_group.command(name='load', usage='{name} [extension name]', description="load a module")
    @commands.bot_has_permissions(send_messages=True)
    async def extension_load_cmd(
            self, ctx: bridge.Context, extension: BridgeOption(str, "The name of the module", name="module-name")
    ):
        """load a module"""
        try:
            cog_status = self.client.load_extension(f'cogs.{extension}')
        except discord.ExtensionError as cog_err:
            cog_error = cog_err
        else:
            if isinstance(cog_status, dict):
                cog_error = cog_status.get(f'cogs.{extension}')
            else:
                cog_error = None
        if isinstance(cog_error, Exception):
            await ctx.respond(embed=utils.default_embed(ctx, "Could Not Load Module", f'{cog_error}', ))
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Loaded Module",
                    f'Successfully loaded the module {extension.capitalize()}'
                )
            )

    # noinspection PyTypeHints
    @extension_group.command(name="reload", usage='{name} [extension name]', description="reload a module")
    @commands.bot_has_permissions(send_messages=True)
    async def extension_reload_cmd(
            self, ctx: bridge.Context, extension: BridgeOption(str, "The name of the module", name="module-name")
    ):
        """unload a module"""
        try:
            self.client.reload_extension(f'cogs.{extension}')
        except discord.ExtensionError as e:
            await ctx.respond(embed=utils.default_embed(ctx, "Could Not Reload Module", f'{e}', ))
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Reloaded Module",
                    f'Successfully reloaded the module {extension}'
                ))

    # noinspection PyTypeHints
    @extension_group.command(name="unload", usage='{name} [extension name]', description="unload a module")
    @commands.bot_has_permissions(send_messages=True)
    async def extension_unload_cmd(
            self, ctx: bridge.Context, extension: BridgeOption(str, "The name of the module", name="module-name")
    ):
        """unload a module"""
        if extension == "owner":
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Can't Unload Owner Module",
                    f"This module can't be unloaded as it would brick the ability to load cogs again"
                )
            )
            return
        try:
            self.client.unload_extension(f'cogs.{extension}')
        except discord.ExtensionError as e:
            await ctx.respond(embed=utils.default_embed(ctx, "Could Not Unload Module", f'{e}', ))
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Unloaded Module",
                    f'Successfully unloaded the module {extension.capitalize()}'
                )
            )

    # noinspection PyTypeHints
    @bridge.bridge_command(
        name='view-log', description="View a log file in ./logs",
        aliases=['view_log'], usage='{prefix}{name} [log filename]',
        contexts={discord.InteractionContextType.bot_dm}
    )
    @commands.dm_only()
    @commands.bot_has_permissions(send_messages=True, attach_files=True)
    async def view_log_cmd(
            self, ctx: bridge.Context, filename: BridgeOption(str, description="The log file to upload")
    ):
        if "." in filename:
            log = filename
        else:
            log = f'{filename}.log'
        message = await ctx.respond(embed=utils.default_embed(
            ctx, f'Uploading `{log}`....',
            'Please wait. The bot will not be able to send any other messages in this channel during this process'
        ))
        if isinstance(message, discord.Interaction):
            message = await message.original_response()
        path_to_fetch = pathlib.Path(f'./logs/{log}')
        if not path_to_fetch.exists():
            await message.edit(embed=utils.default_embed(ctx, f'Upload Failed',
                                                         f'The log `{log}` could not be found. Make '
                                                         f"sure you didn't type the log name "
                                                         f'incorrectly', ))
            return

        if path_to_fetch.resolve().parent != pathlib.Path("./logs/").resolve():
            await message.edit(embed=utils.default_embed(ctx, f'Action Not Allowed',
                                                         f'Breaking out of the logs directory is forbidden', ))
            return
        try:
            await message.edit(embed=utils.default_embed(ctx, f'Uploaded `{log}`', f'', ),
                               file=discord.File(path_to_fetch))
        except (FileNotFoundError, IsADirectoryError):
            await message.edit(embed=utils.default_embed(ctx, f'Upload Failed',
                                                         f'The log `{log}` could not be found. Make '
                                                         f"sure you didn't type the log name "
                                                         f'incorrectly', ))
        except discord.HTTPException as err:
            if err.code == 40005:
                await message.edit(embed=utils.default_embed(ctx, f'Upload Failed',
                                                             f'The log `{log}` is too big to be uploaded due to '
                                                             f'discord\'s 10 MiB upload limit', ))
            else:
                raise

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name="create-invite", aliases=['crinv', 'create_invite'], description="Create An Invite",
        usage='{prefix}{name} #channel(optional) [expiry time](optional) [maximum uses](optional) [reason](optional)'
    )
    @cogchecks.bridge_contexts(discord.InteractionContextType.guild)
    @commands.bot_has_permissions(create_instant_invite=True, send_messages=True)
    async def create_invite(
            self, ctx: bridge.Context,
            channel: BridgeOption(
                discord.TextChannel, "The channel the invite leads to. Defaults to the current channel",
                required=False
            ) = None,
            age: BridgeOption(
                int, "The time before the invite expires in seconds", default=0, name="expires-in"
            ) = None,
            uses: BridgeOption(int, "The maximum number of times the invite can be used", default=0) = 0,
            *,
            reason: BridgeOption(str, "The reason the invite was created", required=False) = None
    ):
        inv_channel: discord.TextChannel = channel or ctx.channel
        try:
            generated_invite = await inv_channel.create_invite(reason=reason, max_age=age, max_uses=uses)
        except discord.HTTPException as invite_error:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Could Not Create Invite", f'{invite_error.text}')
            )
        else:
            embed = utils.default_embed(ctx, "Successfully Created Invite", "", )
            embed.add_field(name=":1234: Invite ID", value=f'{generated_invite.id}')
            embed.add_field(name=":hash: Invite Channel", value=f'{inv_channel.mention}')
            embed.add_field(name=":clock3: Expires", value=utils.discord_ts(generated_invite.expires_at, "R"))
            embed.add_field(name=":timer: Max Age Set", value=f'{datetime.timedelta(seconds=generated_invite.max_age)}')
            uses_set = generated_invite.max_uses
            if uses_set == 0:
                uses_set = "∞"
            embed.add_field(name=":door: Uses set", value=f'{uses_set}')
            if reason:
                embed.add_field(name=":hammer: With Reason", value=f'{reason}')
            embed.add_field(name=":link: Link", value=f'[Invite Link]({generated_invite.url})')
            await ctx.respond(embed=embed)

    # noinspection PyTypeHints
    @guild_tools_group.command(
        name="create", description='Create a server using the bot',
        usage='{name} [server name] attachment:icon(optional)'
    )
    @commands.bot_has_permissions(send_messages=True)
    async def guild_tools_create_cmd(
            self, ctx: bridge.Context, *, name: BridgeOption(str, "What the name of the guild will be"),
            icon: BridgeOption(discord.Attachment, "The image that will be the server icon", required=False) = None
    ):
        message = await ctx.respond(
            embed=utils.default_embed(ctx, "Creating Guild", f'Please wait. Creating {name}')
        )
        if isinstance(message, discord.Interaction):
            message = await message.original_response()
        attachment = MISSING
        if (ctx.message and len(ctx.message.attachments) > 0) or icon:
            attachment = await (
                ctx.message.attachments[0] if ctx.message and len(ctx.message.attachments) > 0
                else icon
            ).read()
        try:
            created_guild = await self.client.create_guild(name=name, icon=attachment)
        except (discord.HTTPException, discord.InvalidArgument) as guild_error:
            await message.edit(embed=utils.default_embed(ctx, "Could Not Create Server", f'{guild_error}', ))
        else:
            created_guild = self.client.get_guild(int(created_guild.id))
            guild_invite = await created_guild.text_channels[0].create_invite(max_age=0, max_uses=0)
            embed = utils.default_embed(ctx, f'{created_guild.name}', "Successfully created server", )
            if created_guild.icon is not None:
                embed.set_thumbnail(url=created_guild.icon.url)
            embed.add_field(name=":link: Invite", value=f'[Click to join server]({guild_invite.url})')
            embed.add_field(name=":1234: Guild ID", value=f'{created_guild.id}')
            embed.add_field(name=":crown: Owner", value=created_guild.owner.mention)
            embed.add_field(name=":calendar: Creation Date", value=utils.discord_ts(created_guild.created_at))
            embed.add_field(name=':hash: Text Channel Count', value=f'{len(created_guild.text_channels)}')
            embed.add_field(name=':loud_sound: VC Count', value=f'{len(created_guild.voice_channels)}')
            embed.add_field(name=':file_folder: Category Count', value=f'{len(created_guild.categories)}')
            embed.add_field(name=':hash::loud_sound: Total Channel Count', value=f'{len(created_guild.channels)}')
            embed.add_field(name=':military_medal: Role Count', value=f'{len(created_guild.roles)}')
            if created_guild.system_channel is not None:
                embed.add_field(name=f':inbox_tray: System Message Channel',
                                value=f'<#{created_guild.system_channel.id}>')
            embed.add_field(name=":closed_lock_with_key: Verification Level",
                            value=f'{created_guild.verification_level}')
            embed.add_field(name=":no_entry: Content Filter", value=f'{created_guild.explicit_content_filter}')
            embed.add_field(name=":speech_balloon: Notification Settings",
                            value=f'{created_guild.default_notifications}')
            embed.add_field(name=":key: Authentication", value=f'{created_guild.mfa_level}')
            embed.add_field(name=":zzz: AFK Channel", value=f'{created_guild.afk_channel}')
            embed.add_field(name=":first_quarter_moon_with_face: AFK Timeout", value=f'{created_guild.afk_timeout}s')
            embed.add_field(name=":busts_in_silhouette: Total Member Count", value=f'{created_guild.member_count}')
            await message.edit(f'{guild_invite.url}', embed=embed)

    # noinspection PyTypeHints
    @guild_tools_group.command(
        name='delete', aliases=['del'], usage="{name} [guild id](optional)",
        description='delete a server if the bot owns it'
    )
    @commands.bot_has_permissions(send_messages=True)
    async def guild_tools_delete_cmd(
            self, ctx: bridge.Context,
            gid: BridgeOption(str, "The id of the server to delete", required=False, name="server-id") = None
    ):
        async def del_server(guild: discord.Guild):
            if guild.owner.id != guild.me.id:
                await ctx.respond(
                    embed=utils.default_embed(ctx, "Could Not Delete Server", f'I do not own **{guild.name}**')
                )
            else:
                message = await ctx.respond(
                    embed=utils.default_embed(ctx, "Deleting Server", f'Deleting **{guild.name}**....')
                )
                if isinstance(message, discord.Interaction):
                    message = await message.original_response()
                try:
                    await guild.delete()
                except discord.HTTPException as error:
                    await message.edit(embed=utils.default_embed(ctx, "Could Not Delete Server", f'{error.text}',
                                                                 ))
                else:
                    if guild.id != ctx.guild.id:
                        await message.edit(embed=utils.default_embed(ctx, "Deleted Server",
                                                                     f'Successfully deleted **{guild.name}**', ))

        if gid is None:
            await del_server(ctx.guild)
        else:
            c_guild = self.client.get_guild(int(gid))
            if c_guild is None:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "Could Not Delete Server",
                        f"The guild `{gid}` does not exist or i'm not in it"
                    )
                )
            else:
                await del_server(c_guild)

    @bridge.bridge_group(
        name="role-tools", aliases=["role_tools"], description="Create, Delete, Add and Remove roles",
        usage="{prefix}{name} [subcommand]", contexts={discord.InteractionContextType.guild}
    )
    @cogchecks.bridge_contexts(discord.InteractionContextType.guild)
    @commands.bot_has_permissions(manage_roles=True, send_messages=True)
    async def role_tools_group(self, ctx: bridge.Context):
        pass

    # noinspection SpellCheckingInspection,PyTypeHints
    @role_tools_group.command(
        name='create', description="Create a role using the bot",
        usage="{name} [role permisisons](int)(optional) [role name](optional) [colour](int)(optional)"
    )
    @commands.bot_has_permissions(manage_roles=True, send_messages=True)
    async def role_tools_create_cmd(
            self, ctx: bridge.Context,
            per: BridgeOption(
                int, "The permissions of the role as an integer",
                max=discord.Permissions.all().value, default=0, name="permissions"
            ) = None,
            *,
            name: BridgeOption(str, 'The name of the role. Defaults to "new role".', default="new role") = "new role",
            colour: BridgeOption(
                str, "The colour of the role as a hex value", default=discord.Colour.default()
            ) = discord.Colour.default(),
            hoist: BridgeOption(bool, "If the role will be hoisted.", default=False) = False,
            mention: BridgeOption(bool, "If people can ping this role.", default=False, name="mentionable") = False,
            reason: BridgeOption(
                str, "The reason for creating this role to appear in the audit log", required=False
            ) = None
    ):
        if isinstance(colour, discord.Colour):
            int_colour = colour
        else:
            raw_colour = str(colour).strip('#').replace("0x", "")
            if len(raw_colour) == 6:
                try:
                    int_colour = int("0x" + raw_colour, 16)
                except ValueError:
                    int_colour = discord.Colour.default()
            elif raw_colour.isdecimal():
                int_colour = int(raw_colour)
            else:
                int_colour = discord.Colour.default()
        try:
            role = await ctx.guild.create_role(name=name, colour=int_colour,
                                               permissions=discord.Permissions(permissions=(int(per))), hoist=hoist,
                                               mentionable=mention, reason=reason)
        except discord.DiscordException as error:
            await ctx.respond(embed=utils.default_embed(ctx, "Could not create role", f'{error}', ))
        else:
            embed = utils.default_embed(ctx, f'Role Created', f'The role {role.mention} was created',
                                        role.colour)
            embed.add_field(name=":1234: Role ID", value=f'{str(role.id)}', inline=True)
            embed.add_field(name=":art: Colour", value=f'[{str(role.colour)}]'
                                                       f'(https://testthisdevice.com/color/color.php?c='
                                                       f'{str(role.colour).replace("#", "")})', inline=True)
            embed.add_field(name=":key: Permissions", value=f'{utils.has_permissions(role.permissions)}')
            if role.hoist:
                embed.add_field(name=":star2: Hoisted", value="Yes")
            if role.mentionable:
                embed.add_field(name=":mega: Mentionable", value="Yes")
            if reason is not None:
                embed.add_field(name=":hammer: Reason", value=f'{reason}')
            await ctx.respond(embed=embed)

    # noinspection SpellCheckingInspection,PyTypeHints
    @role_tools_group.command(
        name='delete', aliases=['del'], description=f'Delete roles using the bot',
        usage="{name} @role [reason](optional)"
    )
    @commands.bot_has_permissions(manage_roles=True, send_messages=True)
    async def role_tools_delete_cmd(
            self, ctx: bridge.Context, role: BridgeOption(discord.Role, "The role in the serevr to delete"),
            reason: BridgeOption(str, "The reason for deleting the role", required=False) = None
    ):
        try:
            await role.delete(reason=reason)
        except discord.HTTPException as why:
            await ctx.respond(embed=utils.default_embed(ctx, "Could Not Delete Role", f'{why.text}', ))
        else:
            embed = utils.default_embed(ctx, f'Role Deleted', f'The role **@{role.name}** was deleted',
                                        role.colour.value)
            embed.add_field(name=":1234: Role ID", value=f'{role.id}')
            embed.add_field(name=":art: Colour", value=f'[{role.colour}]'
                                                       f'(https://testthisdevice.com/color/color.php?c='
                                                       f'{str(role.colour).replace("#", "")})')
            embed.add_field(name=":arrows_clockwise: Position", value=f'{role.position}')
            embed.add_field(name=":calendar: Creation Date", value=utils.discord_ts(role.created_at))
            if role.hoist:
                embed.add_field(name=":star2: Was Hoisted?", value=f'Yes')
            embed.add_field(name=":busts_in_silhouette: Role Members", value=f'{len(role.members)}')
            if role.mentionable:
                embed.add_field(name=":mega: Was Mentionable?", value=f'Yes')
            embed.add_field(name=":key: Permissions", value=f'{utils.has_permissions(role.permissions)}')
            if reason is not None:
                embed.add_field(name=":hammer: Reason", value=f'{reason}')
            await ctx.respond(embed=embed)

    # noinspection SpellCheckingInspection,PyTypeHints
    @role_tools_group.command(
        name='give', aliases=['assign'], description="Add roles to members using the bot",
        usage="{name} @role @user(optional)"
    )
    @commands.bot_has_permissions(manage_roles=True, send_messages=True)
    async def role_tools_give_cmd(
            self, ctx: bridge.Context, role: BridgeOption(discord.Role, "The role to assign"),
            member: BridgeOption(discord.Member, "The member to give the role to", required=False) = None
    ):
        if member is None:
            selected_member = ctx.author
        else:
            selected_member = member
        if selected_member.get_role(role.id) is not None:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Already Has Role",
                f'{selected_member.mention} already has the role {role.mention}'
            ))
        else:
            try:
                await selected_member.add_roles(role)
            except discord.HTTPException as role_error:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "Could Not Add Role To Member", f'{role_error.text}'
                    )
                )
            else:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "Added Role To Member",
                        f'Successfully gave the role {role.mention} to {selected_member.mention}'
                    )
                )

    # noinspection PyTypeHints,SpellCheckingInspection
    @role_tools_group.command(
        name='remove',
        aliases=['rm', 'unassign', 'un-assign', 'un_assign', 'uassign'],
        description="Remove roles from members using the bot",
        usage="{name} @role @user(optional)"
    )
    @commands.bot_has_permissions(manage_roles=True, send_messages=True)
    async def role_tools_remove_cmd(
            self, ctx: bridge.Context, role: BridgeOption(discord.Role, "The role to remove"),
            member: BridgeOption(discord.Member, "The member to remove the role from", required=False) = None
    ):
        if member is None:
            selected_member = ctx.author
        else:
            selected_member = member
        if selected_member.get_role(role.id) is None:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Doesn't Have Role",
                f"{selected_member.mention} doesn't have the role {role.mention}"
            ))
        else:
            try:
                await selected_member.remove_roles(role)
            except discord.HTTPException as role_error:
                await ctx.respond(embed=utils.default_embed(
                    ctx, "Could Not Remove Role From Member", f'{role_error.text}'
                ))
            else:
                await ctx.respond(embed=utils.default_embed(
                    ctx, "Removed Role From Member",
                    f'Successfully removed the role {role.mention} from {selected_member.mention}'
                ))

    # noinspection PyTypeHints
    @bridge.bridge_command(
        name='wget', aliases=['web_grab', 'web-grab'], description="Download files from a URL",
        usage="{prefix}{name} [url] [bypass ssl errors](boolean)(optional)"
    )
    @commands.bot_has_permissions(send_messages=True)
    async def wget_cmd(
            self, ctx: bridge.Context,
            url: BridgeOption(str, "The url to extract the file from"),
            cert_bypass: BridgeOption(
                bool,
                "Whether or not to ignore ssl certificate errors. Defaults to false.",
                default=False, name="bypass-ssl"
            ) = False
    ):
        message = await ctx.respond(
            embed=utils.default_embed(
                ctx, f'Downloading `{url.rsplit("/")[-1]}`....', f"Connecting to **{url}**...."
            )
        )
        if isinstance(message, discord.Interaction):
            message = await message.original_response()
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=not bool(cert_bypass)),
                                         timeout=timeout) as session:
            try:
                async with session.get(url) as file:
                    await message.edit(embed=utils.default_embed(
                        ctx, f'Downloading `{url.rsplit("/")[-1]}`....',
                        f'**{url.split("/")[2]}** status: [{file.status}]'
                        f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{file.status})'
                    ))

                    if not file.ok:
                        await message.edit(embed=utils.default_embed(
                            ctx, f'Download Failed: {file.status}',
                            f'The server **{url.split("/")[2]}** Returned a [{file.status}]'
                            f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{file.status}) error'
                        ))
                    else:
                        file_info = await file.content.read()
                        filename_to_write = f'{url.rsplit("/")[-1]}'
                        if os.path.exists(f'./media/downloads/{url.rsplit("/")[-1]}'):
                            view = FileExistsView(timeout=60, input_filedir=f'./media/downloads/{url.rsplit("/")[-1]}',
                                                  message=message, bot=self.client)
                            await message.edit(embed=utils.default_embed(
                                ctx, f'A File Called `{url.rsplit("/")[-1]}` already exists',
                                f'What do you want to do?\n\nDownload will be canceled automatically in '
                                f'{view.timeout} seconds if nothing is selected.\n\n **{url.split("/")[2]}** status:'
                                f' [{file.status}]'
                                f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{file.status})'
                            ), view=view)
                            await view.wait()
                            filename_to_write = view.filename_to_write
                        if filename_to_write is None:
                            await message.edit(embed=utils.default_embed(
                                ctx, "Download Canceled",
                                f'Download was canceled because filename already existed\n\n '
                                f'**{url.split("/")[2]}** status: [{file.status}]'
                                f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{file.status})'
                            ))
                        else:
                            with open(f'./media/downloads/{filename_to_write}', 'wb') as file_write:
                                file_write.write(file_info)
                                file_write.close()
                            await message.edit(embed=utils.default_embed(
                                ctx, "Download Successful",
                                f'Successfully downloaded file as **{filename_to_write}** in '
                                f'`./media/downloads/{filename_to_write}` '
                                f'from {url}\n\n **{url.split("/")[2]}** status: [{file.status}]'
                                f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{file.status})'
                            ))
            except aiohttp.ClientError as aio_error:
                if isinstance(aio_error, aiohttp.InvalidURL):
                    await message.edit(embed=utils.default_embed(ctx, "Download Failed: Invalid URL",
                                                                 f"`{aio_error}` is not a URL", ))
                elif 'timeout' in str(aio_error):
                    await message.edit(embed=utils.default_embed(ctx, "Download Failed: Connection timed out",
                                                                 f'The server **{url.split("/")[2]}** '
                                                                 f'is not responding', ))
                else:
                    await message.edit(embed=utils.default_embed(ctx, "Download Failed", f'```{aio_error}```', ))

    @bridge.bridge_group(
        name='system', description="Run commands that can view and manipulate the host system", aliases=["file"]
    )
    @commands.bot_has_permissions(send_messages=True, attach_files=True)
    @commands.is_owner()
    async def system_group(self, ctx: bridge.Context):
        pass

    # noinspection PyTypeHints
    @system_group.command(name='give', description='Upload files to the filesystem', aliases=['send'],
                          usage="{name} attachment:file [directory](optional)")
    @commands.is_owner()
    async def system_give_cmd(
            self, ctx: bridge.Context, *,
            directory: BridgeOption(
                str, "The directory to upload the file to", default='./media/downloads'
            ) = './media/downloads',
            file: BridgeOption(discord.Attachment, "The file to upload") = None
    ):
        fp = pathlib.Path(directory)
        try:
            directory_path = fp.expanduser()
        except RuntimeError:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Could Not Give File", f'Invalid syntax: `{fp}`'
            ))
            return
        message = await ctx.respond(embed=utils.default_embed(ctx, f'Getting Attachment....', "", ))
        if isinstance(message, discord.Interaction):
            message = await message.original_response()

        if file is not None:
            attachment = file
        elif isinstance(ctx, commands.Context) and len(ctx.message.attachments) > 0:
            attachment = ctx.message.attachments[0]
        else:
            attachment = None
        if attachment is None:
            await message.edit(embed=utils.default_embed(ctx, "No Attachment", "You didn't provide any attachments",
                                                         ))
        elif not directory_path.is_dir():
            await message.edit(embed=utils.default_embed(ctx, "Invalid Directory",
                                                         f"The directory `{directory_path.name}` doesn't exist", ))
        else:
            await message.edit(embed=utils.default_embed(ctx, f'Sending File',
                                                         f'Sending `{attachment.filename}` to '
                                                         f'`{directory_path.absolute()}`', ))
            filename_to_write = attachment.filename
            path_to_write = pathlib.Path(f'{directory_path.absolute().__str__()}/{filename_to_write}')
            if path_to_write.exists():
                view = FileExistsView(timeout=60, input_filedir=path_to_write, message=message, bot=self.client)
                await message.edit(embed=utils.default_embed(ctx,
                                                             f"A File Already Called `{attachment.filename}` Already "
                                                             f"Exists at `{directory_path.absolute().__str__()}`",
                                                             f'What do you want to do?\n\n'
                                                             f'This operation will be canceled automatically in '
                                                             f'{view.timeout} seconds if nothing is selected.', ),
                                   view=view)
                await view.wait()
                filename_to_write = view.filename_to_write
                path_to_write = pathlib.Path(f'{directory_path.absolute().__str__()}/{filename_to_write}')
            if filename_to_write is None:
                await message.edit(embed=utils.default_embed(
                    ctx, f'Operation Canceled', f'Operation was canceled because filename already existed'
                ))
            else:
                await message.edit(embed=utils.default_embed(ctx, f'Writing File',
                                                             f'Writing `{filename_to_write}` to '
                                                             f'`{directory_path.absolute()}`', ))
                try:
                    await attachment.save(path_to_write, seek_begin=True, use_cached=False)
                except discord.HTTPException as error:
                    error_string = f'`{error.text}`'
                    if isinstance(error, discord.NotFound):
                        error_string = "The attachment is could not be found! was it deleted?"
                    await message.edit(embed=utils.default_embed(ctx, "Operation Failed", error_string, ))
                except PermissionError:
                    await message.edit(embed=utils.default_embed(ctx, "Operation Failed",
                                                                 f"Cannot write `{filename_to_write}`: Missing "
                                                                 f"permissions to write in `{directory_path.absolute()}"
                                                                 f"`", ))
                else:
                    await message.edit(
                        embed=utils.default_embed(ctx, f'Operation Complete',
                                                  f'Successfully wrote `{filename_to_write}` to '
                                                  f'`{directory_path.absolute().__str__()}`', ))

    # noinspection PyTypeHints
    @system_group.command(
        name="grab", description='Download files from the filesystem', aliases=['get'], usage="{name} [file path]"
    )
    @commands.is_owner()
    async def system_grab_cmd(
            self, ctx: bridge.Context, *, path: BridgeOption(str, "The path of the file to download")
    ):
        fp = pathlib.Path(path)
        try:
            fp = fp.expanduser()
        except RuntimeError:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Could Not Grab File", f'Invalid syntax: `{fp}`'
                )
            )
            return
        stat_args = {"follow_symlinks": False}
        if not fp.exists():
            error_message = f"The file `{fp}` does not exist. Make sure there isn't any typos. "
            await ctx.respond(embed=utils.default_embed(ctx, "Could not Fetch File", error_message, ))
        elif not fp.is_file():
            if fp.is_dir():
                error_message = "Cannot fetch a directory. must be a file"
            else:
                error_message = f"The file `{fp.absolute()}` does not exist. Make sure there isn't any typos. "
            await ctx.respond(embed=utils.default_embed(ctx, "Could not Fetch File", error_message, ))
        elif not fp.stat(**stat_args).st_size <= 10 * 1024 ** 2:
            await ctx.respond(embed=utils.default_embed(
                ctx, "File Not Upload-able",
                f'The file `{fp.name}` is too big: `{utils.byte_units(fp.stat(**stat_args).st_size, iec=True)}`. The '
                f'file must meet discord\'s upload limit: `10 MiB`', ))
        else:
            directory = fp.absolute().parent
            if directory == "":
                directory = f'./{directory}'
            elif not directory == '/':
                directory = f'{directory}/'
            message = await ctx.respond(
                embed=utils.default_embed(ctx, "Fetching File",
                                          f'Fetching `{fp.name}` in 'f'`{directory}`', ))
            if isinstance(message, discord.Interaction):
                message = await message.original_response()
            try:
                file_to_upload = discord.File(fp=fp)
            except PermissionError:
                await message.edit(embed=utils.default_embed(ctx, "Could not fetch file",
                                                             f'Missing permission to read '
                                                             f'`{fp.name}` in '
                                                             f'`{directory}`', ))
            else:
                try:
                    await message.edit(embed=utils.default_embed(ctx, "File Fetched Successfully",
                                                                 f'Fetched file `{fp.name}` in '
                                                                 f'`{directory}`', ), file=file_to_upload)
                except discord.HTTPException as discord_error:
                    discord_error_message = str(discord_error.text)
                    if discord_error.code == 40005:
                        discord_error_message = "File too big to upload! (8MiB Discord Limit)"
                    await message.edit(embed=utils.default_embed(ctx, "Could Not Upload File",
                                                                 f'{discord_error_message}', ))

    # noinspection PyTypeHints
    @system_group.command(
        name="ls", description='List files in a directory', aliases=['list'], usage="{name} [directory]"
    )
    @commands.is_owner()
    async def system_ls_cmd(
            self, ctx: bridge.Context, *, directory: BridgeOption(str, 'The directory to list', default='./') = './',
            units_in: BridgeOption(
                str, 'Display file sizes in SI (1kB = 1000B, etc.) or IEC units (1KiB = 1024B, etc.). Defaults to SI',
                choices=["SI", "IEC"], default="SI", name="units-in"
            ) = "SI"
    ):
        """list all the files in a directory"""
        iec = units_in == "IEC"
        try:
            directory_path = pathlib.Path(directory).expanduser()
        except RuntimeError:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Could Not List Directory", f'Invalid syntax: `{directory}`'
                )
            )
            return
        dir_name = directory_path.absolute().__str__()
        if not directory_path.exists():
            await ctx.respond(embed=utils.default_embed(
                ctx, "Could Not List Directory",
                f'The Directory `{directory}` could not be found. Make sure there are no typos in the directory '
                f'name and try again'
            ))
        elif not directory_path.is_dir():
            await ctx.respond(embed=utils.default_embed(
                ctx, "Could Not List Directory", f'`{directory_path.name}` is not a directory'
            ))
        else:
            directory_list = []
            for file_folder in directory_path.iterdir():
                if not file_folder.exists():
                    directory_list.append("{:<10}".format(f'Unknown:') + f' {file_folder.name}')
                    continue
                is_link = ''
                stat_args = {"follow_symlinks": False}
                item_status = file_folder.stat(**stat_args)
                if file_folder.is_symlink():
                    is_link = "Sym "
                if file_folder.is_file():
                    directory_list.append("{:<10}".format(f'{is_link}File:') + f' {file_folder.name} - '
                                                                               f'{utils.byte_units(item_status.st_size, iec=iec)}')
                elif file_folder.is_dir():
                    dir_type = 'Dir'
                    if file_folder.is_mount():
                        dir_type = "Mnt Dir"
                    directory_list.append("{:<10}".format(f'{is_link}{dir_type}:') + f' {file_folder.name}')
                elif file_folder.is_block_device():
                    directory_list.append("{:<10}".format(f'{is_link}Block:') + f' {file_folder.name}')
                elif file_folder.is_char_device():
                    directory_list.append("{:<10}".format(f'{is_link}Char:') + f' {file_folder.name}')
                elif file_folder.is_socket():
                    directory_list.append("{:<10}".format(f'{is_link}Socket:') + f' {file_folder.name}')
                elif file_folder.is_fifo():
                    directory_list.append("{:<10}".format(f'{is_link}Pipe:') + f' {file_folder.name}')
                else:
                    directory_list.append("{:<10}".format(f'{is_link}Unknown:') + f' {file_folder.name}')
            list_to_send = '```' + '\n'.join(directory_list) + '```'
            if len(list_to_send) <= 4096:
                await ctx.respond(embed=utils.default_embed(ctx, f'Contents of `{dir_name}`', list_to_send))
            else:
                dir_str = '\n'.join(directory_list)
                dir_bytes = dir_str.encode('utf-8')
                if len(dir_bytes) > 10 * 1024 ** 2:
                    await ctx.respond(
                        embed=utils.default_embed(ctx, "Could Not List Directory",
                                                  f'The directory `{directory_path.name}` '
                                                  f'is too large to be displayed', ))
                else:
                    await ctx.respond(
                        embed=utils.default_embed(ctx, f'Contents of `{dir_name}`', 'See attached file', ),
                        file=discord.File(io.BytesIO(dir_str.encode()), filename='directory.txt')
                    )

    # noinspection PyTypeHints
    @system_group.command(
        name='path', description='Get information on a file or directory', usage="{name} [path]",
        aliases=["size", "file-info", "file_info", "file", "directory"]
    )
    @commands.is_owner()
    async def system_file_cmd(
            self, ctx: bridge.Context, *,
            raw_path: BridgeOption(str, 'The path to the file to get the size of', name="path")
    ):
        try:
            path = pathlib.Path(raw_path).expanduser()
        except RuntimeError:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Could Not Get Path Info", f'Invalid syntax: `{raw_path}`'
                ))
            return
        stat_args = {"follow_symlinks": False}
        if not path.exists():
            await ctx.respond(embed=utils.default_embed(
                ctx, 'Could Not Get Path Info',
                f'The path `{raw_path}` could not be found. Make sure there are no typos in the path name and try again'
            ))
        else:
            path_info = path.stat(**stat_args)
            if path.is_dir():
                path_name = path.absolute().name
                raw_size, calculated_files, calculated_directories = "calculating...", "calculating...", \
                    "calculating..."
            else:
                path_name = path.name
                raw_size = path_info.st_size
                calculated_files, calculated_directories = None, None
            if isinstance(raw_size, str):
                si_size = raw_size
                iec_size = raw_size
            else:
                si_size = utils.byte_units(raw_size)
                iec_size = utils.byte_units(raw_size, iec=True)
            path_type = "directory" if path.is_dir() else "file"
            embed = utils.default_embed(ctx, f'Information of {path_type} `{path_name}`',
                                        f'{si_size} (SI Units)', )

            def format_path_perms(st_mode: int):
                path_octal = format(st_mode, "06o")
                path_perms = path_octal[-3:]
                special_perms = path_octal[-4]
                special_perms_bin = [int(bit) for bit in str(bin(int(special_perms)))[2:].zfill(3)]
                str_perms = ""
                for index, val in enumerate(path_perms):
                    str_perm = ""
                    for idx, perm in enumerate(["r", "w", "x"]):
                        str_perm += perm if bool(int(str(bin(int(val)))[2:].zfill(3)[idx])) else ""
                    str_perm += ("s" if index + 1 < len(path_perms) else "t") if special_perms_bin[index] else ""
                    if len(str_perm) < 1:
                        str_perms += "n"
                    str_perms += str_perm + "," if index + 1 < len(path_perms) else str_perm
                return str_perms

            str_path_perms = format_path_perms(path_info.st_mode)
            path_bin = format(path_info.st_mode, "016b")
            path_type_hex = hex(int(path_bin[:4], 2))[2:]
            path_types = {"0": "Unknown (Zero)", "1": "Pipe (FIFO)", "2": "Character Device",
                          "4": "Directory", "6": "Block Device", "8": "File", "a": "Symlink", "c": "Socket",
                          "e": "Whiteout", "f": "All (File Mask)"}
            str_type = path_types.get(path_type_hex)
            if str_type is None:
                str_type = "Unknown (Type Not Recognised)"
            embed.add_field(name="Type", value=f'{str_type}')
            if path_type_hex == "a":
                res_path = path.resolve()
                res_path_info = res_path.stat(**stat_args)
                res_path_bin = format(res_path_info.st_mode, "016b")
                res_str_type = path_types.get(hex(int(res_path_bin[:4], 2))[2:])
                res_str_perms = format_path_perms(res_path_info.st_mode)
                embed.add_field(name="Source Type", value=f'{res_str_type}')
                embed.add_field(name="Source Path", value=f'{res_path.absolute().__str__()}')
                if res_path.is_mount():
                    mnt_source = utils.linux_mount_source(res_path.absolute().__str__(), resolve=False)
                    if mnt_source is not None:
                        embed.add_field(name="Source Mount Source", value=f'{mnt_source.__str__()}')
                embed.add_field(name="Source Permissions (u,g,o)", value=f'{res_str_perms}')
                embed.add_field(name="Source Owner",
                                value=f'{utils.linux_resolve_uid(res_path_info.st_uid)} ({res_path_info.st_uid})')
                embed.add_field(name="Source Group",
                                value=f'{utils.linux_resolve_gid(res_path_info.st_gid)} ({res_path_info.st_gid})')
                embed.add_field(name="Source Last Accessed At",
                                value=utils.discord_ts(datetime.datetime.fromtimestamp(res_path_info.st_atime)))
                embed.add_field(name="Source Last Modified At",
                                value=utils.discord_ts(datetime.datetime.fromtimestamp(res_path_info.st_mtime)))
                embed.add_field(name="Source Last Stat Change At",
                                value=utils.discord_ts(datetime.datetime.fromtimestamp(res_path_info.st_ctime)))
            if path.is_mount():
                mnt_source = utils.linux_mount_source(path.absolute().__str__(), resolve=False)
                if mnt_source is not None:
                    embed.add_field(name="Mount Source", value=f'{mnt_source.__str__()}')
            embed.add_field(name="Permissions (u,g,o)", value=f'{str_path_perms}')
            embed.add_field(name="Owner",
                            value=f'{utils.linux_resolve_uid(path_info.st_uid)} ({path_info.st_uid})')
            embed.add_field(name="Group",
                            value=f'{utils.linux_resolve_gid(path_info.st_gid)} ({path_info.st_gid})')
            embed.add_field(name="Last Accessed At",
                            value=utils.discord_ts(datetime.datetime.fromtimestamp(path_info.st_atime)))
            embed.add_field(name="Last Modified At",
                            value=utils.discord_ts(datetime.datetime.fromtimestamp(path_info.st_mtime)))
            embed.add_field(name="Last Stat Change At",
                            value=utils.discord_ts(datetime.datetime.fromtimestamp(path_info.st_ctime)))
            embed.add_field(name="Size in SI Units", value=si_size)
            embed.add_field(name="Size in IEC Units", value=iec_size)
            if isinstance(raw_size, str):
                embed.add_field(name="Exact Size", value=raw_size)
            else:
                embed.add_field(name="Exact Size", value=f'{"{:,}".format(raw_size)} '
                                                         f'{"byte" if raw_size == 1 else "bytes"}')
            if calculated_files is not None:
                embed.add_field(name="Files", value=calculated_files)
            if calculated_directories is not None:
                embed.add_field(name="Directories", value=calculated_directories)
            if not path.is_dir():
                embed.add_field(name="Upload-able to Discord",
                                value=utils.yes_no(path.stat(**stat_args).st_size <= 10 * 1024 ** 2))

            if not path.is_dir():
                await ctx.respond(embed=embed)
            else:
                message = await ctx.respond(embed=embed)
                if isinstance(message, discord.Interaction):
                    message = await message.original_response()
                embed_len = len(embed.fields)
                raw_size, calculated_files, calculated_directories = await utils.walk_dir(path)
                si_size = utils.byte_units(raw_size)
                iec_size = utils.byte_units(raw_size, iec=True)
                embed.description = f'{si_size} (SI Units)'
                embed.set_field_at(embed_len - 5, name="Size in SI Units", value=si_size)
                embed.set_field_at(embed_len - 4, name="Size in IEC Units", value=iec_size)
                embed.set_field_at(embed_len - 3, name="Exact Size", value=f'{"{:,}".format(raw_size)} '
                                                                           f'{"byte" if raw_size == 1 else "bytes"}')
                embed.set_field_at(embed_len - 2, name="Files", value=f'{"{:,}".format(calculated_files)}')
                embed.set_field_at(embed_len - 1, name="Directories", value=f'{"{:,}".format(calculated_directories)}')
                await message.edit(embed=embed)

    # noinspection PyTypeHints
    @system_group.command(
        name='execute', aliases=['system-command', 'bash', 'os', 'operating-system', 'system', 'exec'],
        description="executes operations on the host system", usage="{name} [command]"
    )
    @commands.is_owner()
    async def system_execute_cmd(
            self, ctx: bridge.Context, *, command: BridgeOption(str, "The the command to run on the operating system"),
            shell: BridgeOption(
                str, "The Shell to use to interpret the commands. Defaults to bash", default="bash",
                choices=["bash", "dash", "python3", "csh", "zsh"]
            ) = "bash",
            replace_new_lines: BridgeOption(
                bool, "Replace each line of an output for carriage returns. Defaults to False.", default=False,
                name="replace-new-lines"
            ) = False,
            ansi_colour: BridgeOption(
                bool, "whether to display ansi colours or remove all ansi characters completely", default=True,
                name="ansi-colour"
            ) = True
    ):
        execution_embed = utils.default_embed(ctx, "Executing...", f'Running `{command}`', )
        message = await ctx.respond(embed=execution_embed)
        if isinstance(message, discord.Interaction):
            message = await message.original_response()
        shell_path_cmd = subprocess.Popen(["which", shell], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await self.client.loop.run_in_executor(None, lambda: shell_path_cmd.wait())
        shell_path = await self.client.loop.run_in_executor(
            None,
            lambda: shell_path_cmd.stdout.read().decode("utf-8").replace("\n", "")
        )
        if len(shell_path) < 1:
            execution_embed.title = "Execution Failed"
            execution_embed.description = f'Shell **{command.split()[0]}** not found'
            await message.edit(embed=execution_embed)
            return
        if command.startswith("sudo"):
            execution_embed.title = "Execution Failed"
            execution_embed.description = f'Running commands as root are not permitted'
            await message.edit(embed=execution_embed)
            return
        try:
            process = await self.client.loop.run_in_executor(
                None, lambda: subprocess.Popen(
                    command,
                    shell=True,
                    executable=f'{shell_path}',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    universal_newlines=False,
                    env={
                        "LINES": "35",
                        "COLUMNS": "169",
                        "TERM": "xterm-256color"
                    },
                )
            )
            execution_embed.add_field(name="PID", value=f'{process.pid}')
            view = SystemExecuteView(process, timeout=60, message=message, bot=self.client)
            await message.edit(embed=execution_embed, view=view)
        except FileNotFoundError as file_not_found:
            execution_embed.title = "Execution Failed"
            execution_embed.description = f'Could not execute `{command}`: `{file_not_found}`'
            await message.edit(embed=execution_embed)
        else:
            async def print_output(raw_output: bytes):
                decoded_output = raw_output.decode("utf-8").replace("```", "`​`​`")

                def fit_output(the_output: str, output_list: list):
                    if len(the_output) < 1994:
                        output_list.append(the_output)
                    else:
                        cut_len = len(the_output) - 1988
                        formatted_output = the_output[:-cut_len]
                        rem_output = the_output[1988:]
                        output_list.append(formatted_output)
                        if len(rem_output) > 0:
                            fit_output(rem_output, output_list)

                if len(raw_output) > 4084:
                    outputs: list[str] = []
                    fit_output(decoded_output, outputs)
                    for inx, big_line in enumerate(outputs):
                        if len(big_line) < 1 or all(char == "\n" for char in big_line):
                            big_line = 'no output'
                        if inx < 1:
                            operation = message.edit
                        else:
                            operation = ctx.respond
                        execution_embed.title = f"Output of `{command}` {inx + 1}/{len(outputs)}"
                        execution_embed.description = "```" + ("ansi\n" + big_line if ansi_colour else
                                                               utils.remove_ansi_colours(big_line)) + "```"
                        await operation(embed=execution_embed)
                        return execution_embed
                else:
                    if len(decoded_output) < 1 or all(char == "\n" for char in decoded_output):
                        decoded_output = 'no output'
                    # ansi = re.finditer(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]', decoded_output)
                    # ansi = re.finditer(r'\x1b\[[0-9;]*m', decoded_output)
                    execution_embed.title = f"Output of `{command}`"
                    execution_embed.description = "```" + ("ansi\n" + decoded_output if ansi_colour else
                                                           utils.remove_ansi_colours(decoded_output)) + "```"
                    await message.edit(embed=execution_embed)
                    return execution_embed

            exec_embed: Optional[discord.Embed] = None
            if replace_new_lines:
                nice_stdout = open(os.dup(process.stdout.fileno()), newline='')
                for line in nice_stdout:
                    exec_embed = await print_output(line.encode('utf-8'))
            else:
                output = await self.client.loop.run_in_executor(None, lambda: process.stdout.read())
                exec_embed = await print_output(output)
            return_code = await self.client.loop.run_in_executor(None, lambda: process.wait())
            str_exit_code = str(return_code)
            if return_code < 0:
                str_exit_code = f"{return_code} ({128 | return_code * -1})"
            if exec_embed:
                exec_embed.add_field(name="Exit Code", value=str_exit_code)
                view.disable_all_items()
                view.stop()
                await message.edit(embed=exec_embed, view=view)

    # noinspection PyTypeHints
    @system_group.command(
        name="view", description="Attempt to view the contents of a file", aliases=['quick-view', 'quickview'],
        usage="{name} [file]"
    )
    @commands.is_owner()
    async def system_view_cmd(
            self, ctx: bridge.Context, *, fp: BridgeOption(str, "The path to the file to read"),
            view_as: BridgeOption(
                str, "How to view the file as. Defaults to utf-8 and a byte string if encoding fails",
                choices=supported_encodings, default='utf-8', name="view-as"
            ) = 'utf-8'
    ):
        fp = pathlib.Path(fp)
        try:
            fp = fp.expanduser()
        except RuntimeError:
            await ctx.respond(f"Invalid syntax: `{fp}`")
            return
        if not fp.exists():
            await ctx.respond(embed=utils.default_embed(
                ctx, 'Could Not View File',
                f'The file `{fp}` could not be found. Make sure there are no typos in the path name and try again'
            ))
        elif not fp.is_file():
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, 'Could Not View File', f'`{fp.name}` is not a readable file'
                )
            )
        else:
            try:
                with open(fp, 'rb') as file_handle:
                    file_contents = file_handle.read()
                    file_handle.close()
            except PermissionError:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "Could Not View File", f'Missing permission to read `{fp.name}`'
                    )
                )
                return
            text_encoded = False
            failed_encoding = False
            if view_as == "decimal bytes":
                file_contents_bin = ""
                for byte in list(file_contents):
                    file_contents_bin += f'{byte} '.zfill(4)
                file_contents = file_contents_bin
            elif view_as == "binary":
                file_contents_bin = ""
                for byte in list(file_contents):
                    file_contents_bin += f'{bin(byte)} '.replace("0b", "").zfill(9)
                file_contents = file_contents_bin
            elif view_as == "hexadecimal":
                file_contents_bin = ""
                for byte in list(file_contents):
                    file_contents_bin += f'{hex(byte)} '.replace("0x", "").zfill(3)
                file_contents = file_contents_bin
            elif view_as == "byte string":
                pass
            else:
                try:
                    file_contents = file_contents.decode(view_as)
                    text_encoded = True
                except UnicodeDecodeError:
                    failed_encoding = True
            lang = ""
            if text_encoded:
                lang = fp.suffix.replace('.', '')
                file_lines = file_contents.splitlines()
                if file_contents.startswith("#!"):
                    shebang = file_lines[0]
                    shebang_cmd = shebang.replace("#!", "")
                    lang = shebang_cmd.rsplit("/", 1)[-1]
                    first_arg = lang.split(" ", 1)[0]
                    if first_arg == "env":
                        try:
                            lang = lang.split(" ")[1]
                        except IndexError:
                            pass
                    else:
                        lang = first_arg
                    if lang.startswith("python"):
                        lang = "python"
                    if lang == "node":
                        lang = "js"
                check_line = file_lines[0]
                if file_contents.startswith("<?"):
                    dec_line = file_lines[0]
                    lang = dec_line[2:].split()[0]
                    if len(file_lines) > 1:
                        check_line = file_lines[1]
                if check_line.startswith("<!DOCTYPE"):
                    if len(check_line.split()) > 1:
                        lang = check_line.split()[1].strip(">")
                file_contents = f"{lang}\n{file_contents}"
            if isinstance(file_contents, bytes):
                file_contents = str(file_contents)[2:-1]
            if len(file_contents) < 1:
                file_contents = "This file is empty"
            else:
                file_contents = "```" + file_contents + "```"
            stat_size = fp.stat(follow_symlinks=False).st_size
            if len(file_contents) > 4096:
                embed = utils.default_embed(ctx, f'Could Not View File',
                                            f'The file `{fp.name}` is too large to '
                                            f'be displayed as {view_as} on discord', )
                embed.add_field(name="Max Size", value="4090 characters")
                embed.add_field(name="Representation size", value=f"{len(file_contents) - (6 + len(lang))} characters")
                embed.add_field(name="Representation selected", value=view_as)
                embed.add_field(name="File Size", value=f"{'{:,}'.format(stat_size)} bytes "
                                                        f"({utils.byte_units(stat_size)}, "
                                                        f"{utils.byte_units(stat_size, iec=True)})")
                await ctx.respond(embed=embed)

            else:
                sizes = f'{utils.byte_units(stat_size)} / {utils.byte_units(stat_size, iec=True)} / ' \
                        f'{"{:,}".format(stat_size)} ASCII characters' if stat_size >= 1024 else \
                    (f'{utils.byte_units(stat_size)} / {"{:,}".format(stat_size)} bytes / ASCII characters'
                     if stat_size >= 1000 else f'{"{:,}".format(stat_size)} bytes / ASCII characters')
                await ctx.respond(embed=utils.default_embed(
                    ctx,
                    f'Contents of `{fp.name}`\n{sizes}' +
                    (
                        f'\n:warning: Could not display the file in the format {view_as}! Defaulting to a byte string'
                        if failed_encoding else ""
                    ),
                    f'{file_contents}'
                ))

    # noinspection PyTypeHints
    @bridge.bridge_command(name='con-spam', usage="{prefix}{name} [amount](int) [times](int) [message]")
    @commands.is_owner()
    @commands.bot_has_permissions(send_messages=True)
    async def con_spam_cmd(
            self, ctx: bridge.Context, amount: BridgeOption(int, "The amount of lines per message"),
            times: BridgeOption(int, "The amount of messages to send"), *,
            message: BridgeOption(str, "The contents of the message to send")
    ):
        message_send = ""
        for x in range(amount):
            message_send += f'{message}\n'

        for x in range(times):
            if x == 0:
                await ctx.respond(message_send)
            await ctx.channel.send(message_send)

    # noinspection PyTypeHints
    @guild_tools_group.command(
        name="fix-missing", aliases=["fix-config"], description="fixes all missing configuration files for servers",
        usage="{name} server(id)"
    )
    @commands.is_owner()
    @commands.bot_has_permissions(send_messages=True)
    async def guild_tools_fix_missing(
            self, ctx: bridge.Context,
            guild_id: BridgeOption(str, "The ID of the guild to check", required=False, name="guild-id") = None
    ):
        guilds_fixed = 0
        guild = None
        if guild_id and guild_id.isdecimal():
            guild = self.client.get_guild(guild_id)
            if guild is None:
                raise commands.BadArgument(f'Guild "{guild_id}" not found.')

        def fix_config(bot_guild: discord.Guild):
            server_config = pathlib.Path(f"./json/guilds/{bot_guild.id}.json")
            if not server_config.exists():
                with open(f'./json/guild-template.json', 'r', encoding='utf-8') as r_guilds_template:
                    guilds_template = json.load(r_guilds_template)
                    r_guilds_template.close()
                guilds_template["name"] = bot_guild.name
                guilds_template["server id"] = bot_guild.id
                with open(f'./json/guilds/{bot_guild.id}.json', 'w', encoding='utf-8') as w_guild_config:
                    json.dump(guilds_template, w_guild_config, ensure_ascii=False, indent=4)
                    w_guild_config.close()
                return 1
            return 0
        if guild is None:
            async for client_guild in self.client.fetch_guilds():
                fix_func = fix_config(client_guild)
                guilds_fixed += fix_func
            if guilds_fixed:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "Fixed Configuration",
                        f'Repaired server configuration files for **{guilds_fixed}** servers'
                    )
                )
            else:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "None Missing", f'No server configuration files were missing'
                    )
                )
        else:
            fix_func = fix_config(guild)
            if fix_func:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "Fixed Configuration", f'Repaired server configuration file for **{guild.name}**'
                    )
                )
            else:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "Not Missing",
                        f'The server configuration file for **{guild.name}** already exists. To repair a '
                        f'broken configuration file, delete the config file for the server and run this command again'
                    )
                )

    @bridge.bridge_group(
        name="psa", aliases=["public_service", "public-service"],
        description="Write and cancel public service announcements", usage="{prefix}{name} [subcommand]"
    )
    @commands.bot_has_permissions(send_messages=True)
    async def psa_group(self, ctx: bridge.Context):
        pass

    # noinspection PyTypeHints
    @psa_group.command(
        name="write", description="Write a psa that will appear when someone executes a command",
        usage="{name} [content]"
    )
    @commands.is_owner()
    @commands.bot_has_permissions(send_messages=True)
    async def psa_write_cmd(
            self, ctx: bridge.Context, *, content: BridgeOption(str, "The contents of the psa message to broadcast"),
            embed: BridgeOption(bool, "Whether the psa message should be a plain text message or an embed") = True
    ):
        if isinstance(ctx, bridge.BridgeApplicationContext):
            content = content.replace("\\n", "\n")
        if embed:
            # noinspection SpellCheckingInspection
            await ctx.respond(
                "**PSA Preview:**",
                embed=utils.default_embed(ctx, "Revnobot Public Service Announcement", content, )
            )
        else:
            await ctx.respond("**PSA Preview:**")
            await ctx.respond(content)
        with open("json/psa-messages-template.json") as psa_template_file:
            psa_messages_template = json.load(psa_template_file)
        psa_messages_template["active"] = True
        psa_messages_template["content"] = content
        psa_messages_template["embed"] = embed
        with open(f'json/psa-messages.json', 'w', encoding='utf-8') as empty_json:
            json.dump(psa_messages_template, empty_json, ensure_ascii=False, indent=2)
            empty_json.close()

    @psa_group.command(name="cancel", description="Cancel the psa set if any")
    @commands.is_owner()
    @commands.bot_has_permissions(send_messages=True)
    async def psa_cancel_cmd(self, ctx: bridge.Context):
        with open("json/psa-messages-template.json") as psa_template_file:
            psa_messages_template = json.load(psa_template_file)
        psa_messages_template["active"] = False
        with open(f'json/psa-messages.json', 'w', encoding='utf-8') as empty_json:
            json.dump(psa_messages_template, empty_json, ensure_ascii=False, indent=2)
            empty_json.close()
        if isinstance(ctx, bridge.BridgeExtContext):
            await ctx.message.add_reaction("\U00002705")
        else:
            await ctx.respond("\U00002705", ephemeral=True)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='web-status', aliases=['web_status', 'webstatus'], usage='{prefix}{name} [website url]',
        description="check the status of a website to see if its up"
    )
    @commands.bot_has_permissions(send_messages=True)
    @commands.is_owner()
    @commands.cooldown(**config.default_cooldown_options)
    async def web_status_cmd(
            self, ctx: bridge.Context, url: BridgeOption(str, "The webpage to get the status of"),
            cert_bypass: BridgeOption(
                bool,
                "Whether or not to ignore ssl certificate errors. Defaults to false.",
                default=False, name="bypass-ssl"
            ) = False
    ):
        """check the status of a website to see if its up"""
        url = f"https://{url}" if not any(x in url for x in ["https://", "http://"]) else url
        timeout = aiohttp.ClientTimeout(total=30)
        try:
            url.split("/")[2]
        except IndexError:
            split_url = url
        else:
            split_url = url.split("/")[2]

        message = await ctx.respond(embed=utils.default_embed(
            ctx, f'Connecting to {split_url}....',
            "Connection will timeout after 30 seconds and website will be considered down"
        ))
        if hasattr(ctx, 'interaction'):
            message = await ctx.interaction.original_response()
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=not cert_bypass),
                                             timeout=timeout) as session:
                async with session.get(url) as site:
                    if str(site.status).startswith(("1", "3")):
                        await message.edit(embed=utils.default_embed(
                            ctx, f'Website Accessible',
                            f'The website **{url.split("/")[2]}** is accessible but returned a status of '
                            f'[{site.status}](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{site.status})'
                        ))
                    if str(site.status).startswith("4"):
                        await message.edit(embed=utils.default_embed(
                            ctx, f'Website Possibly Down',
                            f'The website **{url.split("/")[2]}** returned an error [{site.status}]'
                            f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{site.status})'
                        ))
                    if str(site.status).startswith("5"):
                        await message.edit(embed=utils.default_embed(
                            ctx, f'Website is down',
                            f'The website **{url.split("/")[2]}** is down with an error code: [{site.status}]'
                            f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{site.status})'
                        ))
                    if str(site.status).startswith("2"):
                        if site.status == 200:
                            await message.edit(embed=utils.default_embed(
                                ctx, f'Website is up',
                                f'The website **{url.split("/")[2]}** is up and running with a status of '
                                f'[{site.status}]'
                                f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{site.status})'
                            ))
                        else:
                            await message.edit(embed=utils.default_embed(
                                ctx, f'Website is up',
                                f'The website **{url.split("/")[2]}** is up and gave a status of [{site.status}]'
                                f'(https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{site.status})'
                            ))

        except (aiohttp.InvalidURL, IndexError, AttributeError):
            await message.edit(
                embed=utils.default_embed(ctx, "Invalid Url", "this is not a url")
            )
        except asyncio.exceptions.TimeoutError:
            await message.edit(embed=utils.default_embed(
                ctx, "Website Down: Connection timed out",
                f'**{url.split("/")[2]}**\'s server is not responding',
            ))
        except aiohttp.TooManyRedirects:
            await message.edit(
                embed=utils.default_embed(
                    ctx, "Website Down: Broken Response",
                    f'**{url.split("/")[2]}** caused a redirect loop'
                ))
        except aiohttp.ClientConnectorCertificateError:
            await message.edit(embed=utils.default_embed(
                ctx, "Website Inaccessible: SSL Verification Failed",
                f'The ssl certificate for **{url.split("/")[2]}** was rejected. Try running this command again with '
                f'the `ignore_ssl` parameter set to `Yes`. But this could mean something is wrong with the website',
            ))
        except aiohttp.ClientSSLError:
            await message.edit(embed=utils.default_embed(
                ctx, "Website Inaccessible: SSL Verification Failed",
                f'The ssl verification failed for **{url.split("/")[2]}**. Try running this command again with the '
                f'`ignore_ssl` parameter set to `Yes`. But this could mean something is wrong with the website'
            ))
        except aiohttp.ClientOSError as error:
            await message.edit(embed=utils.default_embed(
                ctx, "Website Inaccessible: ",
                f'An error occurred while trying to connect to **{url.split("/")[2]}**: ```{error}```'
            ))

    # noinspection PyTypeHints
    @guild_tools_group.command(
        name="ban", aliases=["blacklist"], usage="{name} server(id)", description="Ban servers from adding the bot"
    )
    @commands.is_owner()
    async def guild_tools_ban_cmd(
            self, ctx: bridge.Context, guild_str: BridgeOption(str, "The ID of the guild to ban", name="guild-id")
    ):
        if not guild_str.isdecimal():
            raise commands.BadArgument('Converting to "int" failed for parameter "guild_str".')
        guild_id = int(guild_str)
        if not os.path.isfile(f'./json/banned-guilds.json'):
            with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                json.dump([], empty_json, indent=2)
                empty_json.close()
        with open(f'./json/banned-guilds.json', 'r', encoding='utf-8') as ban_file:
            try:
                ban_list: list = json.load(ban_file)
            except json.JSONDecodeError:
                with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                    json.dump([], empty_json, indent=2)
                    empty_json.close()
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, "Ban List Corrupted", "Created new list. Run this command again to ban server"
                    )
                )
            else:
                if not isinstance(ban_list, list):
                    with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                        json.dump([], empty_json, indent=2)
                        empty_json.close()
                    await ctx.respond(
                        embed=utils.default_embed(
                            ctx, "Ban List Corrupted",
                            "Created new list. Run this command again to ban server"
                        )
                    )
                elif guild_id in ban_list:
                    await ctx.respond(
                        embed=utils.default_embed(
                            ctx, "Already Banned", "Server already in ban list"
                        )
                    )
                else:
                    ban_list.append(guild_id)
                    with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as w_ban_file:
                        json.dump(ban_list, w_ban_file, indent=2)
                        w_ban_file.close()
                    try:
                        guild = await self.client.fetch_guild(guild_id)
                    except discord.HTTPException:
                        guild = None
                    if guild_id in [client_guild.id for client_guild in self.client.guilds]:
                        if guild:
                            await guild.leave()
                    text = f"{guild.name} ({guild_id})" if guild else f"{guild_id}"
                    await ctx.respond(
                        embed=utils.default_embed(
                            ctx, "Banned Server", f"Successfully banned {text}"
                        )
                    )

    # noinspection PyTypeHints
    @guild_tools_group.command(
        name="unban", usage="{name} server(id)", description="Unban servers from adding the bot"
    )
    @commands.is_owner()
    async def guild_tools_unban_cmd(
            self, ctx: bridge.Context, guild_str: BridgeOption(str, "The ID of the guild to unban", name="guild-id")
    ):
        if not guild_str.isdecimal():
            raise commands.BadArgument('Converting to "int" failed for parameter "guild_str".')
        guild_id = int(guild_str)
        if not os.path.isfile(f'./json/banned-guilds.json'):
            with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                json.dump([], empty_json, indent=2)
                empty_json.close()
        with open(f'./json/banned-guilds.json', 'r', encoding='utf-8') as ban_file:
            try:
                ban_list: list = json.load(ban_file)
            except json.JSONDecodeError:
                with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                    json.dump([], empty_json, indent=2)
                    empty_json.close()
                await ctx.respond(embed=utils.default_embed(
                    ctx, "Ban List Corrupted", "Created new list. Run this command again to unban server"
                ))
            else:
                if not isinstance(ban_list, list):
                    with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                        json.dump([], empty_json, indent=2)
                        empty_json.close()
                    await ctx.respond(embed=utils.default_embed(
                        ctx, "Ban List Corrupted", "Created new list. Run this command again to unban server"
                    ))
                elif guild_id not in ban_list:
                    await ctx.respond(embed=utils.default_embed(
                        ctx, "Not Banned", "Server is not in ban list"
                    ))
                else:
                    ban_list.remove(guild_id)
                    with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as w_ban_file:
                        json.dump(ban_list, w_ban_file, indent=2)
                        w_ban_file.close()
                    try:
                        guild = await self.client.fetch_guild(guild_id)
                    except discord.HTTPException:
                        guild = None
                    text = f"{guild.name} ({guild_id})" if guild else f"{guild_id}"
                    await ctx.respond(embed=utils.default_embed(
                        ctx, "Unbanned Server", f"Successfully unbanned {text}"
                    ))

    @guild_tools_group.command(name="list", aliases=["ls"], description="List banned server IDs")
    @commands.is_owner()
    async def guild_tools_list_cmd(self, ctx: bridge.Context):
        if not os.path.isfile(f'./json/banned-guilds.json'):
            with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                json.dump([], empty_json, indent=2)
                empty_json.close()
        with open(f'./json/banned-guilds.json', 'r', encoding='utf-8') as ban_file:
            try:
                ban_list: list = json.load(ban_file)
            except json.JSONDecodeError:
                with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                    json.dump([], empty_json, indent=2)
                    empty_json.close()
                await ctx.respond(embed=utils.default_embed(
                    ctx, "Ban List Corrupted", "Created new list. Run this command again to unban server"
                ))
            else:
                if not isinstance(ban_list, list):
                    with open(f'./json/banned-guilds.json', 'w', encoding='utf-8') as empty_json:
                        json.dump([], empty_json, indent=2)
                        empty_json.close()
                    await ctx.respond(embed=utils.default_embed(
                        ctx, "Ban List Corrupted", "Created new list. Run this command again to unban server"
                    ))
                else:
                    str_ban_list = '\n'.join([str(entry) for entry in ban_list])
                    await ctx.respond(embed=utils.default_embed(
                        ctx, "List of Banned Server IDs", f"{str_ban_list}"
                    ))

    @bridge.bridge_command(
        name="ups-status", description="Get the status of the ups the bots host machine is powered from"
    )
    @commands.is_owner()
    async def ups_status_cmd(self, ctx: bridge.Context):
        try:
            apcaccess_cmd = subprocess.Popen(["apcaccess", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as missing:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, f"Error", f"`{missing.filename}` command not found"
                )
            )
            return
        apcaccess_failed = await self.client.loop.run_in_executor(None, lambda: apcaccess_cmd.wait())
        try:
            apcaccess_output = await self.client.loop.run_in_executor(
                None,
                lambda: apcaccess_cmd.stdout.read().decode("utf-8")
            )
        except UnicodeDecodeError:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, f"Error", f"`apcaccess status` returned unreadable result"
                )
            )
            return
        if apcaccess_failed:
            try:
                error_message = await self.client.loop.run_in_executor(
                    None,
                    lambda: apcaccess_cmd.stderr.read().decode("utf-8")
                )
            except UnicodeDecodeError:
                error_message = "Unreadable"
            if len(error_message) < 1:
                error_message = apcaccess_output or "No Output"
            await ctx.respond(
                embed=utils.default_embed(
                    ctx,
                    f"Error",
                    f"`apcaccess status` returned exit code **{apcaccess_failed}**"
                    f"\n**Output:**\n```ansi\n{error_message}\n```"
                )
            )
        else:
            status_embed = utils.default_embed(ctx, "UPS Status", "")
            # noinspection SpellCheckingInspection
            name_lookup = {
                "LINEV": "Mains Voltage",
                "LOADPCT": "Load",
                "BCHARGE": "Battery Charge",
                "TIMELEFT": "Estimated Battery Time",
                "MBATTCHG": "Minimum Percent Threshold",
                "MINTIMEL": "Minimum Time Threshold",
                "MAXTIME": "Max Time",
                "LOTRANS": "Low Transfer Threshold",
                "HITRANS": "High Transfer Threshold",
                "ALARMDEL": "Alarm Delay",
                "BATTV": "Battery Voltage",
                "LASTXFER": "Last Transfer Reason",
                "NUMXFERS": "Number Of Transfers",
                "XONBATT": "Last On Battery",
                "TONBATT": "Time On Battery",
                "CUMONBATT": "Total Time On Battery",
                "XOFFBATT": "Last Off Battery",
                "BATTDATE": "Battery Last Replaced",
                "NOMINV": "Typical Mains Voltage",
                "NOMBATTV": "Normal Battery Voltage",
                "LASTSTEST": "Last Test"
            }
            items = {}
            output_split = apcaccess_output.splitlines()
            # noinspection SpellCheckingInspection
            datetime_fields = ["XOFFBATT", "XONBATT", "BATTDATE", "LASTSTEST"]
            # noinspection SpellCheckingInspection
            excluded_fields = ["STATFLAG", "SERIALNO", "END APC"]
            load_dec = 0.0
            rating = 0
            voltage = 0.0
            for line in output_split[9:][:25+len(excluded_fields)]:
                name, value = line.split(": ", 1)
                items[name.strip()] = value.strip()
                # noinspection SpellCheckingInspection
                if name.strip() == "LOADPCT":
                    load_dec = float(value.strip().split()[0]) / 100
                if name.strip() == "MODEL":
                    rating = int(value.strip().split()[-1][:-1])
                # noinspection SpellCheckingInspection
                if name.strip() == "LINEV":
                    voltage = float(value.strip().split()[0])
            for name, value in items.items():
                if name in datetime_fields:
                    try:
                        value = utils.discord_ts(datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z"))
                    except ValueError:
                        try:
                            value = utils.discord_ts(datetime.datetime.strptime(value, "%Y-%m-%d"), "d")
                        except ValueError:
                            pass
                value = value.replace(" Volts", "V").replace(" Percent", "%")
                # noinspection SpellCheckingInspection
                if name == "LOADPCT":
                    load_va = load_dec * rating
                    current = load_va / voltage
                    value = f"{value}, {load_va} VA, {round(current*1000, 1)} mA"
                if name not in excluded_fields:
                    status_embed.add_field(name=name_lookup.get(name) or name.lower().title(), value=value)
            # just in case it goes over
            status_embed.fields = status_embed.fields[:25]
            await ctx.respond(embed=status_embed)

    # noinspection SpellCheckingInspection,PyTypeHints
    @commands.command(
        name='manual-setup', description='Manually configure Revnobot in your server',
        usage="{prefix}{name} attachment:config_file(optional)",
        aliases=["manual_setup", "old-setup", "old_setup", "json-setup", "json_setup"]
    )
    @commands.bot_has_permissions(send_messages=True)
    @commands.cooldown(**config.default_cooldown_options)
    @commands.guild_only()
    async def manual_setup_cmd(self, ctx: commands.Context, config_file: discord.Attachment = None):
        attachment = None
        if isinstance(ctx, commands.Context):
            if len(ctx.message.attachments) > 0:
                attachment = ctx.message.attachments[0]
        elif config_file is not None:
            attachment = config_file
        if attachment is None:
            server_config = pathlib.Path(f"./json/guilds/{ctx.guild.id}.json")
            if not server_config.exists():
                with open(f'./json/guild-template.json', 'r', encoding='utf-8') as r_guilds_template:
                    guilds_template = json.load(r_guilds_template)
                    r_guilds_template.close()
                guilds_template["name"] = ctx.guild.name
                guilds_template["server id"] = ctx.guild.id
                json_bytes = json.dumps(guilds_template, ensure_ascii=False).encode("utf-8")
                with open(f'./json/guilds/{ctx.guild.id}.json', 'wb') as w_guild_config:
                    w_guild_config.write(json_bytes)
                    w_guild_config.close()
                config_to_send = discord.File(io.BytesIO(json_bytes), filename=f'{ctx.guild.id}.json')
            else:
                config_to_send = discord.File(server_config)
            # noinspection SpellCheckingInspection
            await ctx.reply(
                embed=utils.default_embed(
                    ctx,
                    "Setup",
                    "To properly configure Revnobot, you need to download the file above, fill out or change the "
                    "values and run this command again with the file attached"
                ),
                files=[config_to_send])
        else:
            try:
                attachment_bytes = await attachment.read()
            except discord.HTTPException as attachment_error:
                await ctx.reply(
                    embed=utils.default_embed(
                        ctx,
                        "Unable To Download Attachment",
                        f'{attachment_error.text}',
                    )
                )
            else:
                try:
                    config_json: dict = json.load(io.BytesIO(attachment_bytes))
                except json.JSONDecodeError as decode_error:
                    await ctx.reply(
                        embed=utils.default_embed(
                            ctx,
                            "Format Error",
                            f'this is not a json file or it is corrupted: {decode_error}',
                        )
                    )
                else:
                    try:
                        if config_json['name'] != ctx.guild.name:
                            config_json["name"] = ctx.guild.name
                        if not isinstance(config_json['server id'], int) or \
                                config_json['server id'] != ctx.guild.id:
                            config_json["server id"] = ctx.guild.id
                        if config_json['log channel'] is not None:
                            if not isinstance(config_json['log channel'], int):
                                raise InvalidConfiguration(f'Invalid log channel id specified')
                            log_channel = ctx.guild.get_channel(config_json['log channel'])
                            if log_channel is None:
                                raise InvalidConfiguration(f'Invalid log channel id specified '
                                                           f'or I cannot see the channel')

                            if not log_channel.permissions_for(ctx.guild.me).send_messages:
                                raise InvalidConfiguration(f'I cannot send messages in the channel '
                                                           f'specified')
                        if config_json['welcome channel'] is not None:
                            if not isinstance(config_json['welcome channel'], int):
                                raise InvalidConfiguration(f'Invalid welcome channel id specified')
                            welcome_channel = ctx.guild.get_channel(config_json['welcome channel'])
                            if welcome_channel is None:
                                raise InvalidConfiguration(f'Invalid welcome channel id specified '
                                                           f'or i cannot see the channel')

                            if not welcome_channel.permissions_for(ctx.guild.me).send_messages:
                                raise InvalidConfiguration(f'I cannot send messages in the channel '
                                                           f'specified')
                        if config_json['spam channel'] is not None:
                            if not isinstance(config_json['spam channel'], int):
                                raise InvalidConfiguration(f'Invalid spam channel id specified')
                            welcome_channel = ctx.guild.get_channel(config_json['spam channel'])
                            if welcome_channel is None:
                                raise InvalidConfiguration(f'Invalid spam channel id specified '
                                                           f'or i cannot see the channel')

                            if not welcome_channel.permissions_for(ctx.guild.me).send_messages:
                                raise InvalidConfiguration(f'I cannot send messages in the channel '
                                                           f'specified')
                        if config_json["join leave"] is None or not isinstance(config_json["join leave"], dict):
                            config_json["join leave"] = {"welcome message": "Hello {user_mention}!\nYou are member "
                                                                            "**#{server_member_count}** of "
                                                                            "**{server_name}**",
                                                         "leave message": "**{username}** left"}
                        else:
                            for field_name in ["welcome", "leave"]:
                                if config_json["join leave"][f"{field_name} message"] is not None:
                                    if not isinstance(config_json["join leave"][f"{field_name} message"], str) or \
                                            utils.is_empty(config_json["join leave"][f"{field_name} message"]):
                                        raise InvalidConfiguration(
                                            f"The {field_name} message can't be empty or just "
                                            f"spaces")
                                    else:
                                        field = config_json["join leave"][f"{field_name} message"]
                                        try:
                                            field.format()
                                        except ValueError:
                                            raise InvalidConfiguration(
                                                f"Invalid Syntax: {field_name} message can't "
                                                "contain **{** or **}** on their own and only "
                                                "**{** and **}** when specifying a variable.")
                                        except KeyError:
                                            pass
                                        welcome_args = {"user_mention": "placeholder",
                                                        "server_member_count": "placeholder",
                                                        "server_name": "placeholder"}
                                        leave_args = {"username": "placeholder"}
                                        field_args = welcome_args if field_name == "welcome" else leave_args
                                        fixed_args = field_args.keys()
                                        for key in list(fixed_args):
                                            if "{" + key + "}" not in field:
                                                field_args.pop(key)
                                        try:
                                            field.format(**field_args)
                                        except KeyError as out_key:
                                            raise InvalidConfiguration(f"Invalid variable in {field_name} message: "
                                                                       f"**{out_key}** is not a valid variable")
                        if config_json['member role'] is not None:
                            if not isinstance(config_json['member role'], int):
                                raise InvalidConfiguration(f'Invalid member role id specified')
                            member_role = ctx.guild.get_role(config_json['member role'])
                            if member_role is None:
                                raise InvalidConfiguration(
                                    f'the member role id specified for the member role did not '
                                    f'match any roles in this server')

                            if not member_role.is_assignable():
                                raise InvalidConfiguration(f'I do not have permissions to add this role')
                        if config_json['mute role'] is not None:
                            if not isinstance(config_json['mute role'], int):
                                raise InvalidConfiguration(f'Invalid mute role id specified')
                            member_role = ctx.guild.get_role(config_json['mute role'])
                            if member_role is None:
                                raise InvalidConfiguration(
                                    f'the mute role id specified for the member role did not '
                                    f'match any roles in this server')

                            if not member_role.is_assignable():
                                raise InvalidConfiguration(f'I do not have permissions to add this role')
                        if config_json["auto admin role"] is not None:
                            if not isinstance(config_json["auto admin role"], int) or \
                                    ctx.guild.owner.id != ctx.guild.me.id:
                                config_json["auto admin role"] = None
                    except KeyError as missing_key:
                        await ctx.reply(
                            embed=utils.default_embed(
                                ctx,
                                "Invalid Configuration",
                                f"The key `{missing_key}` is missing from the configuration file"
                            )
                        )
                    except InvalidConfiguration as invalid_configuration:
                        await ctx.reply(
                            embed=utils.default_embed(
                                ctx,
                                "Invalid Configuration",
                                f"{invalid_configuration}"
                            )
                        )
                    else:
                        with open(f'./json/guilds/{ctx.guild.id}.json', 'w', encoding='utf-8') as w_guild_config:
                            json.dump(config_json, w_guild_config, ensure_ascii=False, indent=4)
                        await ctx.reply(
                            embed=utils.default_embed(
                                ctx,
                                "Configuration Saved",
                                f"The configuration for this server has been updated successfully"
                            )
                        )


def setup(client):
    client.add_cog(Owner(client))
