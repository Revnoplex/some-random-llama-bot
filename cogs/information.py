import datetime
import platform
from collections.abc import Mapping
import discord
from discord.ext import commands, bridge, pages
from discord.commands import Option
from typing import Union, Iterable, Callable, Optional
import sys
import config
import utils
from utils import discord_ts


class BackBtn(discord.ui.Button):
    def __init__(self, back_to: Callable, back_to_args: tuple[tuple, dict], *args, **kwargs):
        self.back_to = back_to
        self.args = back_to_args[0]
        self.kwargs = back_to_args[1]
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.remove_item(self)
        if isinstance(self.view, pages.Paginator):
            self.view.custom_view.remove_item(self)
            await interaction.edit(view=self.view.custom_view)
        try:
            await self.back_to(*self.args, **self.kwargs)
            self.view.stop()
        except RuntimeError:
            self.view.remove_item(self)
            await interaction.edit(view=self.view)


class CommandSelect(discord.ui.Select):
    def __init__(self, cmd_list: list[Union[commands.Command, discord.ApplicationCommand, bridge.BridgeCommand]],
                 help_menu):
        self.help_menu: HelpMenus = help_menu
        self.cmd_list = cmd_list
        options = [discord.SelectOption(label=cmd.qualified_name, emoji="\U0001f579") for cmd in cmd_list]
        super().__init__(placeholder="Select a command", options=options, custom_id=self.__class__.__name__)

    async def callback(self, interaction: discord.Interaction):
        view = self.view.custom_view if isinstance(self.view, pages.Paginator) else self.view
        ctx = discord.ApplicationContext(self.help_menu.context.bot, interaction)
        await ctx.defer()
        if "mainMenuBackBtn" not in [child.custom_id if hasattr(child, "custom_id") else ""
                                     for child in self.view.children]:
            view.add_item(BackBtn(self.help_menu.main_help_menu, utils.repack(utils.map_bot(ctx), view),
                                  label="Main Menu", custom_id="mainMenuBackBtn"))
        if "cogBackBtn" not in [child.custom_id if hasattr(child, "custom_id") else ""
                                for child in self.view.children]:
            if len(self.cmd_list) > 0:
                if self.cmd_list[0].cog is None:
                    mapping = utils.map_bot(self.help_menu.context)
                    parent_cmd, parent_args = self.help_menu.no_cog_menu, utils.repack(mapping[None], view=view)
                else:
                    parent_cmd, parent_args = self.help_menu.cog_help_menu, utils.repack(self.cmd_list[0].cog,
                                                                                         view=view)
                view.add_item(BackBtn(parent_cmd, parent_args, label="Back",
                                      custom_id="cogBackBtn"))
        keys = self.values[0].split()
        cmd = ctx.bot.all_commands.get(keys[0])
        if cmd is None:
            await self.help_menu.command_not_found(keys[0])
            self.view.stop()
            return

        for key in keys[1:]:
            try:
                found = cmd.all_commands.get(key)
            except AttributeError:
                await self.help_menu.subcommand_not_found(cmd, key)
                self.view.stop()
                return
            else:
                if found is None:
                    await self.help_menu.subcommand_not_found(cmd, key)
                    self.view.stop()
                    return
                cmd = found

        if isinstance(cmd, commands.Group):
            await self.help_menu.group_help_menu(cmd, view=view)
            self.view.stop()
            return
        elif cmd is not None:
            await self.help_menu.command_help_menu(cmd, view=view)
            self.view.stop()
            return
        self.view.stop()


class CogSelect(discord.ui.Select):
    def __init__(self, cogs: list[config.RevnobotCog], help_menu):
        self.help_menu: HelpMenus = help_menu
        self.cogs = cogs
        options = [
            discord.SelectOption(
                label=cog.qualified_name if cog.__class__.__base__.__name__ == config.RevnobotCog.__name__ else "NC",
                emoji=cog.icon
            ) for cog in self.cogs
        ]
        super().__init__(placeholder="Select a category", options=options, custom_id=self.__class__.__name__)

    async def callback(self, interaction: discord.Interaction):
        view = self.view.custom_view if isinstance(self.view, pages.Paginator) else self.view
        ctx = discord.ApplicationContext(self.help_menu.context.bot, interaction)
        await ctx.defer()
        if "mainMenuBackBtn" not in [child.custom_id if hasattr(child, "custom_id") else ""
                                     for child in self.view.children]:
            view.add_item(BackBtn(self.help_menu.main_help_menu, utils.repack(utils.map_bot(ctx), view),
                                  label="Main Menu", custom_id="mainMenuBackBtn"))
        if self.values[0] == "NC":
            mapping = utils.map_bot(self.help_menu.context)
            if mapping.get(None):
                await self.help_menu.no_cog_menu(mapping[None], view=view)
                return
            else:
                await self.help_menu.command_not_found("There were no commands without a category")
                return
        try:
            selected_cog = self.cogs[[cog.__cog_name__ for cog in self.cogs].index(self.values[0])]
        except ValueError:
            await self.help_menu.command_not_found(self.values[0])
        else:
            await self.help_menu.cog_help_menu(selected_cog, view=view)
        self.view.stop()


class HelpMenus:
    def __init__(self, context: Union[commands.Context, discord.ApplicationContext]):
        self.context = context
        self.prefix_commands: Union[Iterable[commands.Command], list[discord.ApplicationCommand]] = \
            list(context.bot.commands)
        self.application_commands = context.bot.application_commands
        self.all_commands = self.prefix_commands + self.application_commands
        self.version = "3.3.1"
        if isinstance(self.context, discord.ApplicationContext):
            self.prefix = config.prefix
        else:
            self.prefix = self.context.prefix

    async def subcommand_not_found(self, command: Union[commands.Command, commands.Group], subcommand_name: str):
        if isinstance(command, commands.Group):
            await self.context.respond(
                embed=utils.default_embed(
                    self.context, "Subcommand Not Found",
                    f'The command `{command.name}` has no subcommand or aliases called `{subcommand_name}`'
                )
            )
        else:
            await self.context.respond(
                embed=utils.default_embed(
                    self.context, "No Subcommands", f'The command `{command.name}` has no subcommands'
                )
            )

    async def command_not_found(self, command_name: str):
        await self.context.respond(
            embed=utils.default_embed(
                self.context, "Command or Category not Found",
                f'The bot has no category, command or alias called `{command_name}`'
            )
        )

    async def slash_callback(self, command: Optional[str] = None, subcommand: Optional[str] = None):
        bot = self.context.bot
        if command is None:
            mapping = utils.map_bot(self.context)
            await self.main_help_menu(mapping)
            return
        # Check if it's a cog
        cog = bot.get_cog(str(command).capitalize())
        if cog is None:
            cog = bot.get_cog(str(command).upper())
        if cog is not None:
            await self.cog_help_menu(cog)
            return
        if str(command).lower() == "nc":
            mapping = utils.map_bot(self.context)
            if mapping.get(None):
                return await self.no_cog_menu(mapping[None])

        if subcommand is None:
            keys = [command]
        else:
            keys = [command, subcommand]
        cmd = bot.all_commands.get(keys[0])
        if cmd is None:
            await self.command_not_found(keys[0])
            return

        for key in keys[1:]:
            try:
                found = cmd.all_commands.get(key)
            except AttributeError:
                await self.subcommand_not_found(cmd, key)
                return
            else:
                if found is None:
                    await self.subcommand_not_found(cmd, key)
                    return
                cmd = found

        if isinstance(cmd, commands.Group):
            await self.group_help_menu(cmd)
            return
        elif cmd is not None:
            await self.command_help_menu(cmd)
            return

    async def main_help_menu(self, mapping: Mapping, view: utils.DefaultView = None):
        prefix_command_count = 0
        slash_command_count = 0
        user_command_count = 0
        message_command_count = 0
        user_installable_count = 0
        total_command_count = self.all_commands.__len__()
        owner_commands = []
        for cmd in self.context.bot.get_cog("Owner").get_commands():
            if cmd.qualified_name not in owner_commands:
                owner_commands.append(cmd.qualified_name)
        for cmd in self.all_commands:
            if cmd.qualified_name not in owner_commands:
                if isinstance(cmd, commands.Command):
                    prefix_command_count += 1
                elif isinstance(cmd, discord.SlashCommand) or isinstance(cmd, discord.SlashCommandGroup):
                    slash_command_count += 1
                elif isinstance(cmd, bridge.BridgeExtCommand):
                    prefix_command_count += 1
                    slash_command_count += 1
                elif isinstance(cmd, discord.UserCommand):
                    user_command_count += 1
                elif isinstance(cmd, discord.MessageCommand):
                    message_command_count += 1
                if hasattr(cmd, "integration_types"):
                    user_installable_count += discord.IntegrationType.user_install in cmd.integration_types
            else:
                total_command_count -= 1

        duplicate_commands = slash_command_count + user_command_count + message_command_count
        main_help = utils.default_embed(self.context, f'Help Menu v{self.version}',
                                        f'**{total_command_count}** Total commands '
                                        f'(**{duplicate_commands}** duplicates): **{prefix_command_count}** prefix '
                                        f'commands, **{slash_command_count}** slash commands, '
                                        f'**{user_command_count}** user commands '
                                        f'and **{message_command_count}** message command/s (**{user_installable_count}'
                                        f'** user installable)\n\nType `{self.prefix}help [Category/Command name]` '
                                        f'to bring up information on the command or the commands for that category\n\n'
                                        f'**Categories:**\n\n** **')
        slash_commands = []
        cogs = []
        # Warning, update this to handle pagination if the bot has more than 25 cogs.
        # This is a very unlikely thing to happen, so it has not been implemented
        for cog, cmds in mapping.items():
            for cmd in cmds:
                if isinstance(cmd, discord.SlashCommand) or isinstance(cmd, bridge.BridgeExtCommand):
                    slash_commands.append(cmd)
            if isinstance(cog, config.RevnobotCog):
                if not cog.hidden:
                    main_help.add_field(name=f'{cog.icon} {cog.qualified_name}', value=f'{cog.description}')
                    cogs.append(cog)
            elif len(cmds) > 1:
                main_help.add_field(name=f':question: NC', value='Miscellaneous commands with no category')
                cogs.append(config.RevnobotCog(description="Miscellaneous commands with no category",
                                               icon="\U00002753"))
        if len(main_help.fields) < 1:
            main_help.add_field(name=':warning: Empty', value='There are no visible categories')
        if len(main_help.fields) > 25:
            main_help.clear_fields()
            main_help.add_field(
                name=":x: Too Many Categories",
                value=(
                    "There were too many categories to be displayed."
                    "\nThis is most likely a bug that has caused this and not too many categories, "
                    "So this occurrence should be [reported]"
                    "(https://github.com/Revnoplex/revnobot-public/issues/new/choose) on the "
                    "[public github](https://github.com/revnoplex/revnobot-public)"
                )
            )
        if view is None or view.original_message is None:
            message = await self.context.respond(embed=main_help)
            if isinstance(message, discord.Interaction):
                message = await self.context.interaction.original_response()
        else:
            message = view.original_message
        if view is None or view.original_message is None:
            await message.edit(view=utils.DefaultView(CogSelect(cogs, self),
                                                      message=message, context=self.context))
        else:
            await message.edit(view=utils.DefaultView(CogSelect(cogs, self),
                                                      message=message, context=self.context),
                               embed=main_help)

    async def no_cog_menu(self,
                          command_list: list[Union[discord.ApplicationCommand, commands.Command, bridge.BridgeCommand]],
                          view: utils.DefaultView = None):
        cog_help = utils.default_embed(self.context, f':question: NC', f'Miscellaneous commands with no category',)
        if len(command_list) > 0:
            def cog_menu(page_commands, sub_cog_help, all_slash):
                for command in page_commands:
                    if isinstance(command, commands.Command):
                        slash_version = ""
                        slash_command: Union[discord.SlashCommand, discord.SlashCommandGroup]
                        for slash_command in all_slash:
                            if slash_command.qualified_name == command.qualified_name:
                                slash_version = f"</{slash_command.qualified_name}:{slash_command.qualified_id}>\n"
                        sub_cog_help.add_field(name=f':joystick: {self.prefix}{command.qualified_name}',
                                               value=f'{slash_version}{command.description}')
                    if isinstance(command, (discord.SlashCommand, discord.SlashCommandGroup)):
                        slash_version = f"</{command.qualified_name}:{command.qualified_id}>\n"
                        sub_cog_help.add_field(name=f':joystick: /{command.qualified_name}',
                                               value=f'{slash_version}{command.description}')
                    if isinstance(command, discord.ContextMenuCommand):
                        command_description = "User command" if isinstance(command, discord.UserCommand) \
                            else "Message Command"
                        sub_cog_help.add_field(name=f':joystick: {command.qualified_name}',
                                               value=f'{command_description}')
                return sub_cog_help
            slash_commands = [command for command in command_list
                              if isinstance(command, (discord.SlashCommand, discord.SlashCommandGroup))]
            all_commands: list[Union[commands.Command, discord.ApplicationCommand]] = []
            for command in command_list:
                if isinstance(command, commands.Command):
                    for idx, cmd in enumerate(all_commands):
                        if cmd.qualified_name == command.qualified_name:
                            all_commands.pop(idx)
                    all_commands.append(command)
                if isinstance(command, (discord.SlashCommand, discord.SlashCommandGroup)):
                    if command.qualified_name not in [cmd.qualified_name for cmd in all_commands]:
                        all_commands.append(command)
                if isinstance(command, discord.ContextMenuCommand):
                    if command.qualified_name not in [cmd.qualified_name for cmd in all_commands]:
                        all_commands.append(command)
            if len(all_commands) <= 25:
                ready_embed = cog_menu(all_commands, cog_help, slash_commands)
                if view is None or view.original_message is None:
                    message = await self.context.respond(
                        embed=ready_embed)
                    if isinstance(message, discord.Interaction):
                        message = await self.context.interaction.original_response()
                else:
                    message = view.original_message
                view = utils.DefaultView(message=message, context=self.context)
                view.add_item(BackBtn(self.main_help_menu, utils.repack(utils.map_bot(self.context), view),
                                      label="Main Menu", custom_id="mainMenuBackBtn"))
                view.add_item(CommandSelect(all_commands, self))
                await view.original_message.edit(embed=ready_embed, view=view)
            else:
                s_commands = [all_commands[x:x + 25] for x in range(0, len(all_commands), 25)]
                new_pages = []
                if view is None or view.original_message is None:
                    message = await self.context.respond(
                        embed=utils.default_embed(
                            self.context, f':Question: NC', f'Miscellaneous commands with no category\nLoading...',
                        )
                    )
                    if isinstance(message, discord.Interaction):
                        message = await self.context.interaction.original_response()
                else:
                    message = view.original_message

                for index, s_command in enumerate(s_commands):
                    cog_help = utils.default_embed(self.context, f':Question: NC',
                                                   f'Miscellaneous commands with no category')
                    cog_help = cog_menu(s_command, cog_help, slash_commands)
                    view_instance = utils.DefaultView(message=message, context=self.context, timeout=None)
                    view_instance.add_item(BackBtn(self.main_help_menu, utils.repack(utils.map_bot(self.context),
                                                                                     view_instance),
                                           label="Main Menu", custom_id="mainMenuBackBtn"))
                    view_instance.add_item(CommandSelect(s_command, self))
                    new_pages.append(pages.Page(custom_view=view_instance, embeds=[cog_help]))
                new_view = new_pages[0].custom_view
                paginator = pages.Paginator(pages=new_pages, author_check=False, custom_view=new_view)
                if view is None or view.original_message is None:
                    if isinstance(self.context, discord.ApplicationContext):
                        await paginator.respond(self.context.interaction)
                    else:
                        await paginator.send(self.context)
                else:
                    await paginator.edit((new_view or view).original_message)

        else:
            cog_help.add_field(name=':warning: Empty', value='This cog has no commands')
            if view is None or view.original_message is None:
                message = await self.context.respond(embed=cog_help)
            else:
                message = view.original_message
            view = utils.DefaultView(message=message, context=self.context)
            view.add_item(BackBtn(self.main_help_menu, utils.repack(utils.map_bot(self.context), view),
                                  label="Main Menu", custom_id="mainMenuBackBtn"))
            await view.original_message.edit(embed=cog_help, view=view)

    async def cog_help_menu(self, cog: Union[config.RevnobotCog, commands.Cog], view: utils.DefaultView = None):
        cog_help = utils.default_embed(self.context, f'{cog.icon} {cog.qualified_name}', f'{cog.description}')
        command_list = cog.get_commands()
        if len(command_list) > 0:
            def cog_menu(page_commands, sub_cog_help, all_slash):
                for command in page_commands:
                    if isinstance(command, commands.Command):
                        slash_version = ""
                        slash_command: Union[discord.SlashCommand, discord.SlashCommandGroup]
                        for slash_command in all_slash:
                            if slash_command.qualified_name == command.qualified_name:
                                slash_version = f"</{slash_command.qualified_name}:{slash_command.qualified_id}>\n"
                        sub_cog_help.add_field(name=f':joystick: {self.prefix}{command.qualified_name}',
                                               value=f'{slash_version}{command.description}')
                    if isinstance(command, (discord.SlashCommand, discord.SlashCommandGroup)):
                        slash_version = f"</{command.qualified_name}:{command.qualified_id}>\n"
                        sub_cog_help.add_field(name=f':joystick: /{command.qualified_name}',
                                               value=f'{slash_version}{command.description}')
                    if isinstance(command, discord.ContextMenuCommand):
                        command_description = "User command" if isinstance(command, discord.UserCommand) \
                            else "Message Command"
                        sub_cog_help.add_field(name=f':joystick: {command.qualified_name}',
                                               value=f'{command_description}')
                return sub_cog_help
            slash_commands = [command for command in command_list
                              if isinstance(command, (discord.SlashCommand, discord.SlashCommandGroup))]
            all_commands: list[Union[commands.Command, discord.ApplicationCommand]] = []
            for command in command_list:
                if isinstance(command, commands.Command):
                    for idx, cmd in enumerate(all_commands):
                        if cmd.qualified_name == command.qualified_name:
                            all_commands.pop(idx)
                    all_commands.append(command)
                if isinstance(command, (discord.SlashCommand, discord.SlashCommandGroup)):
                    if command.qualified_name not in [cmd.qualified_name for cmd in all_commands]:
                        all_commands.append(command)
                if isinstance(command, discord.ContextMenuCommand):
                    if command.qualified_name not in [cmd.qualified_name for cmd in all_commands]:
                        all_commands.append(command)
            if len(all_commands) <= 25:
                ready_embed = cog_menu(all_commands, cog_help, slash_commands)
                if view is None or view.original_message is None:
                    message = await self.context.respond(
                        embed=ready_embed)
                    if isinstance(message, discord.Interaction):
                        message = await self.context.interaction.original_response()
                else:
                    message = view.original_message
                view = utils.DefaultView(message=message, context=self.context)
                view.add_item(BackBtn(self.main_help_menu, utils.repack(utils.map_bot(self.context), view),
                                      label="Main Menu", custom_id="mainMenuBackBtn"))
                view.add_item(CommandSelect(all_commands, self))
                await view.original_message.edit(embed=ready_embed, view=view)
            else:
                s_commands = [all_commands[x:x + 25] for x in range(0, len(all_commands), 25)]
                new_pages = []
                if view is None or view.original_message is None:
                    message = await self.context.respond(
                        embed=utils.default_embed(self.context, f'{cog.icon} {cog.qualified_name}',
                                                  f'{cog.description}\nLoading...'))
                    if isinstance(message, discord.Interaction):
                        message = await self.context.interaction.original_response()
                else:
                    message = view.original_message

                for index, s_command in enumerate(s_commands):
                    cog_help = utils.default_embed(self.context, f'{cog.icon} {cog.qualified_name}',
                                                   f'{cog.description}\n**Commands {index + 1}/{len(s_commands)}:**')
                    cog_help = cog_menu(s_command, cog_help, slash_commands)
                    view_instance = utils.DefaultView(message=message, context=self.context, timeout=None)
                    view_instance.add_item(BackBtn(self.main_help_menu, utils.repack(utils.map_bot(self.context),
                                                                                     view_instance),
                                           label="Main Menu", custom_id="mainMenuBackBtn"))
                    view_instance.add_item(CommandSelect(s_command, self))
                    new_pages.append(pages.Page(custom_view=view_instance, embeds=[cog_help]))
                new_view = new_pages[0].custom_view
                paginator = pages.Paginator(pages=new_pages, author_check=False, custom_view=new_view)
                if view is None or view.original_message is None:
                    if isinstance(self.context, discord.ApplicationContext):
                        await paginator.respond(self.context.interaction)
                    else:
                        await paginator.send(self.context)
                else:
                    await paginator.edit((new_view or view).original_message)

        else:
            cog_help.add_field(name=':warning: Empty', value='This cog has no commands')
            if view is None or view.original_message is None:
                message = await self.context.respond(embed=cog_help)
            else:
                message = view.original_message
            view = utils.DefaultView(message=message, context=self.context)
            view.add_item(BackBtn(self.main_help_menu, utils.repack(utils.map_bot(self.context), view),
                                  label="Main Menu", custom_id="mainMenuBackBtn"))
            await view.original_message.edit(embed=cog_help, view=view)

    async def command_help_menu(self, command: commands.Command, view: utils.DefaultView = None):
        if command.description is None:
            desc = ''
        else:
            desc = command.description
        command_help = utils.default_embed(self.context, f':joystick: {command.name}', desc)
        context_menus = []
        types_available = []
        works_in_contexts = set()
        user_installable = False
        user_install_only = False
        is_subcommand = False
        for item in self.all_commands.copy():
            cmd = item
            if item.name in [parent.name for parent in command.parents]:
                if isinstance(item, discord.SlashCommandGroup):
                    for subcommand in item.walk_commands():
                        if subcommand.name == command.name:
                            if not works_in_contexts:
                                works_in_contexts = subcommand.contexts
                            is_subcommand = True
                if isinstance(item, commands.Group):
                    cmd = item.get_command(command.name)
            if cmd.name == command.name:
                if isinstance(cmd, discord.ApplicationCommand):
                    works_in_contexts = cmd.contexts
                    if not user_installable:
                        user_installable = discord.IntegrationType.user_install in cmd.integration_types
                    if not user_install_only:
                        user_install_only = discord.IntegrationType.guild_install not in cmd.integration_types
                if isinstance(cmd, commands.Command):
                    if cmd.name == item.name:
                        types_available.append(f"{self.prefix}{cmd.name}")
                    if not works_in_contexts:
                        works_in_contexts = {
                            discord.InteractionContextType.guild,
                            discord.InteractionContextType.bot_dm,
                            discord.InteractionContextType.private_channel
                        }
                        if cmd.cog:
                            works_in_contexts = await utils.cog_contexts(cmd.cog) or works_in_contexts
                        for check in cmd.checks:
                            if check.__qualname__.split(".")[0] == "guild_only":
                                works_in_contexts = {discord.InteractionContextType.guild}
                            if check.__qualname__.split(".")[0] == "dm_only":
                                works_in_contexts = {discord.InteractionContextType.bot_dm}
                elif isinstance(cmd, discord.SlashCommand):
                    types_available.append(cmd.mention)
                elif isinstance(cmd, discord.SlashCommandGroup):
                    types_available.append(f"</{cmd.name}:{cmd.id}>")
                elif isinstance(cmd, bridge.BridgeExtCommand):
                    types_available.append(f"{self.prefix}{cmd.name}")
                elif isinstance(cmd, discord.UserCommand):
                    context_menus.append(f"User")
                elif isinstance(cmd, discord.MessageCommand):
                    context_menus.append(f"Message")

        if types_available:
            command_help.add_field(name=":control_knobs: Commands Available", value=", ".join(types_available))
        if context_menus:
            command_help.add_field(name=":card_box: Available Context Menus", value=", ".join(context_menus))
        if len(command.aliases) > 0:
            command_help.add_field(name=':chains: Aliases', value=f'`{", ".join(command.aliases)}`',
                                   inline=True)
        works_in = {
            discord.InteractionContextType.guild: "Servers",
            discord.InteractionContextType.bot_dm: "Bot DMs",
            discord.InteractionContextType.private_channel: "Private Channels"
        }
        command_help.add_field(
            name=":white_check_mark: Works in",
            value=", ".join([works_in[ict] for ict in works_in_contexts]) if works_in_contexts else "Unknown"
        )
        if not is_subcommand:
            command_help.add_field(
                name=":briefcase: User Installable", value=utils.yes_no(user_installable)
            )
            command_help.add_field(
                name=":paperclip: User Install Only", value=utils.yes_no(user_install_only)
            )

        if command.usage is not None and command.usage != 'None':
            try:
                command_help.add_field(name=':arrow_right: Usage',
                                       value=(command.usage or "None").format(prefix=self.prefix,
                                                                              name=command.qualified_name))
            except KeyError:
                command_help.add_field(name=':arrow_right: Usage', value=str(command.usage))
        if view is None or view.original_message is None:
            message = await self.context.respond(embed=command_help)
        else:
            message = view.original_message
        view = utils.DefaultView(message=message, context=self.context)
        if command.cog is None:
            mapping = utils.map_bot(self.context)
            parent_cmd, parent_args = self.no_cog_menu, utils.repack(mapping[None], view=view)
        else:
            parent_cmd, parent_args = self.cog_help_menu, utils.repack(command.cog, view=view)
        view.add_item(BackBtn(parent_cmd, parent_args, label="Back",
                              custom_id="cogBackBtn"))
        await message.edit(embed=command_help, view=view)

    async def group_help_menu(self, group: commands.Group, view: utils.DefaultView = None):
        if group.description is None:
            desc = ""
        else:
            desc = group.description
        if len(group.aliases) > 0:
            aliases = f':chains: **Aliases:** `{", ".join(group.aliases)}`'
        else:
            aliases = ""
        if group.usage is not None and group.usage != 'None':
            try:
                usage = (f':arrow_right: **Usage:** '
                         f'{(group.usage or "None").format(prefix=self.prefix, name=group.qualified_name)}')
            except KeyError:
                usage = f':arrow_right: **Usage:** {group.usage}'
        else:
            usage = ""
        context_menus = []
        types_available = []
        works_in_contexts = set()
        user_installable = False
        user_install_only = False
        is_subcommand = False
        for item in self.all_commands.copy():
            cmd = item
            if item.name in [parent.name for parent in group.parents]:
                if isinstance(item, discord.SlashCommandGroup):
                    for subcommand in item.walk_commands():
                        if subcommand.name == group.name:
                            if not works_in_contexts:
                                works_in_contexts = subcommand.contexts
                            is_subcommand = True
                if isinstance(item, commands.Group):
                    cmd = item.get_command(group.name)
            if cmd.name == group.name:
                if isinstance(cmd, discord.ApplicationCommand):
                    works_in_contexts = cmd.contexts
                    if not user_installable:
                        user_installable = discord.IntegrationType.user_install in cmd.integration_types
                    if not user_install_only:
                        user_install_only = discord.IntegrationType.guild_install not in cmd.integration_types
                if isinstance(cmd, commands.Command):
                    if cmd.name == item.name:
                        types_available.append(f"{self.prefix}{cmd.name}")
                    if not works_in_contexts:
                        works_in_contexts = {
                            discord.InteractionContextType.guild,
                            discord.InteractionContextType.bot_dm,
                            discord.InteractionContextType.private_channel
                        }
                        if cmd.cog:
                            works_in_contexts = await utils.cog_contexts(cmd.cog) or works_in_contexts
                        for check in cmd.checks:
                            if check.__qualname__.split(".")[0] == "guild_only":
                                works_in_contexts = {discord.InteractionContextType.guild}
                            if check.__qualname__.split(".")[0] == "dm_only":
                                works_in_contexts = {discord.InteractionContextType.bot_dm}
                elif isinstance(cmd, discord.SlashCommand):
                    types_available.append(cmd.mention)
                elif isinstance(cmd, discord.SlashCommandGroup):
                    types_available.append(f"</{cmd.name}:{cmd.id}>")
                elif isinstance(cmd, bridge.BridgeExtCommand):
                    types_available.append(f"{self.prefix}{cmd.name}")
                elif isinstance(cmd, discord.UserCommand):
                    context_menus.append(f"User")
                elif isinstance(cmd, discord.MessageCommand):
                    context_menus.append(f"Message")
        str_commands = ""
        str_menus = ""
        if types_available:
            str_commands = "\n:control_knobs: **Commands Available:** " + ", ".join(types_available)
        if context_menus:
            str_menus = "\n:card_box: **Available Context Menus:** " + ", ".join(context_menus)
        works_in = {
            discord.InteractionContextType.guild: "Servers",
            discord.InteractionContextType.bot_dm: "Bot DMs",
            discord.InteractionContextType.private_channel: "Private Channels"
        }
        str_works_in = ":white_check_mark: **Works in:** " + (
            ", ".join([works_in[ict] for ict in works_in_contexts]) if works_in_contexts else "Unknown"
        )
        str_user_installable = ""
        str_user_install_only = ""
        if not is_subcommand:
            str_user_installable = ":briefcase: **User Installable:** " + utils.yes_no(user_installable)
            str_user_install_only = ":paperclip: **User Install Only:** " + utils.yes_no(user_install_only)
        group_help = utils.default_embed(
            self.context, f':joystick: {group.name}',
            f'{desc}\n{str_commands}{str_menus}\n{aliases}\n{str_works_in}\n{str_user_installable}\n'
            f'{str_user_install_only}\n{usage}\n:joystick: **Subcommands:**'
        )
        subcommand_list_len = sum(1 for _ in group.walk_commands())
        if view is None or view.original_message is None:
            message = await self.context.respond(embed=group_help)
        else:
            message = view.original_message
        view = utils.DefaultView(message=message, context=self.context)
        if subcommand_list_len > 0:
            slash_subcommands = []
            for command in self.application_commands:
                if (isinstance(command, discord.SlashCommandGroup) and
                        command.qualified_name == group.qualified_name):
                    slash_subcommands = command.subcommands
            all_commands = []
            # this is currently coded to display a limit of 25 commands.
            for subcommand in group.walk_commands():
                slash_alt = ""
                for slash_subcommand in slash_subcommands:
                    if slash_subcommand.qualified_name == subcommand.qualified_name:
                        slash_alt = f"</{slash_subcommand.qualified_name}:{slash_subcommand.qualified_id}>\n"
                group_help.add_field(name=f':joystick: {self.prefix}{group.name} {subcommand.name}',
                                     value=f'** **{slash_alt}{subcommand.description}')
                all_commands.append(subcommand)
            view.add_item(CommandSelect(all_commands, self))
        else:
            group_help.add_field(name=f':warning: Empty',
                                 value=f'This command group has no sub commands')
        if len(group_help.fields) > 25:
            group_help.clear_fields()
            group_help.add_field(
                name=":x: Too Many Subcommands",
                value=(
                    "There were too many subcommands to be displayed."
                    "\nThis is most likely a bug that has caused this and not too many subcommands. "
                    "So this occurrence should be [reported]"
                    "(https://github.com/Revnoplex/revnobot-public/issues/new/choose) on the "
                    "[public github](https://github.com/revnoplex/revnobot-public)"
                )
            )
        if group.cog is None:
            mapping = utils.map_bot(self.context)
            parent_cmd, parent_args = self.no_cog_menu, utils.repack(mapping[None], view=view)
        else:
            parent_cmd, parent_args = self.cog_help_menu, utils.repack(group.cog, view=view)
        view.add_item(BackBtn(parent_cmd, parent_args, label="Back",
                              custom_id="cogBackBtn"))
        await message.edit(embed=group_help, view=view)


# noinspection SpellCheckingInspection
class RevnobotHelp3(commands.HelpCommand):
    def __init__(self, **kwargs):
        self.version = '3.3.1'
        super().__init__(**kwargs)

    async def send_error_message(self, error):
        pass

    async def command_not_found(self, string: str):
        await HelpMenus(self.context).command_not_found(string)

    async def subcommand_not_found(self, command: commands.Command, string: str):
        await HelpMenus(self.context).subcommand_not_found(command, string)

    async def command_callback(self, ctx: commands.Context, *, command=None):
        """|coro|

        The actual implementation of the help command.

        It is not recommended to override this method and instead change
        the behaviour through the methods that actually get dispatched.

        - :meth:`send_bot_help`
        - :meth:`send_cog_help`
        - :meth:`send_group_help`
        - :meth:`send_command_help`
        - :meth:`get_destination`
        - :meth:`command_not_found`
        - :meth:`subcommand_not_found`
        - :meth:`send_error_message`
        - :meth:`on_help_command_error`
        - :meth:`prepare_help_command`
        """
        await self.prepare_help_command(ctx, command)
        bot = ctx.bot

        if command is None:
            mapping = self.get_bot_mapping()
            return await self.send_bot_help(mapping)
        # Check if it's a cog
        cog = bot.get_cog(str(command).capitalize())
        if cog is None:
            cog = bot.get_cog(str(command).upper())
        if cog is not None and isinstance(cog, config.RevnobotCog):
            return await self.send_cog_help(cog)
        if str(command).lower() == "nc":
            mapping = self.get_bot_mapping()
            if mapping.get(None):
                return await self.send_no_cog_help(mapping[None])

        maybe_coro = discord.utils.maybe_coroutine

        # If it's not a cog then it's a command.
        # Since we want to have detailed errors when someone
        # passes an invalid subcommand, we need to walk through
        # the command group chain ourselves.
        keys = command.split(" ")
        cmd = bot.all_commands.get(keys[0])
        if cmd is None:
            string = await maybe_coro(self.command_not_found, self.remove_mentions(keys[0]))
            return await self.send_error_message(string)

        for key in keys[1:]:
            try:
                found = cmd.all_commands.get(key)
            except AttributeError:
                string = await maybe_coro(self.subcommand_not_found, cmd, self.remove_mentions(key))
                return await self.send_error_message(string)
            else:
                if found is None:
                    string = await maybe_coro(self.subcommand_not_found, cmd, self.remove_mentions(key))
                    return await self.send_error_message(string)
                cmd = found

        if isinstance(cmd, commands.Group):
            return await self.send_group_help(cmd)
        else:
            return await self.send_command_help(cmd)

    async def send_bot_help(self, mapping: Mapping):
        await HelpMenus(self.context).main_help_menu(mapping)

    async def send_cog_help(self, cog: config.RevnobotCog):
        await HelpMenus(self.context).cog_help_menu(cog)

    async def send_no_cog_help(self,
                               cmd_list: list[
                                   Union[discord.ApplicationCommand, commands.Command, bridge.BridgeCommand]
                               ]):
        await HelpMenus(self.context).no_cog_menu(cmd_list)

    async def send_command_help(self, command: commands.Command):
        await HelpMenus(self.context).command_help_menu(command)

    async def send_group_help(self, group: commands.Group):
        await HelpMenus(self.context).group_help_menu(group)


class Information(config.RevnobotCog):

    def __init__(self, client: bridge.Bot):
        self.client = client
        self.description = "get information about the bot, a user or a server"
        self.icon = "\U0001F4E1"
        self.hidden = False

    @commands.slash_command(
        name="help", description="Displays The Help Command",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def slash_help(
            self, ctx: discord.ApplicationContext, name: Option(str, "Category or Command", required=False),
            sub: Option(str, "Subcommand", required=False, name="subcommand")
    ):
        await HelpMenus(ctx).slash_callback(name, sub)

    # noinspection SpellCheckingInspection
    @bridge.bridge_command(
        name='about',
        description="About the bot?",
        aliases=['botinfo', 'bot-info', 'bot_info', 'bio', 'ping', 'latency', 'info', 'uptime', 'version']
    )
    @commands.bot_has_permissions(send_messages=True)
    @commands.cooldown(**config.default_cooldown_options)
    async def about_cmd(self, ctx: bridge.Context):
        """About the bot?"""
        app = await self.client.application_info()

        embed = utils.default_embed(ctx, f'{self.client.user.display_name}',
                                    f'Some random bot that interacts with the llama LLM')
        embed.set_thumbnail(url=self.client.user.display_avatar.url)
        embed.add_field(name=':tools: Version', value=f'{config.version_string}')
        embed.add_field(name=":1234: Discord ID", value=f'{str(self.client.user.id)}')
        embed.add_field(name=":mechanic: Developer", value=f'{app.owner.mention}')
        embed.add_field(name=":calendar: API account created at",
                        value=discord_ts(self.client.user.created_at))
        if not utils.is_dm_channel(ctx.channel):
            embed.add_field(name=":inbox_tray: Joined Current Server At",
                            value=discord_ts(ctx.guild.me.joined_at))
        embed.add_field(name=":signal_strength: Latency", value=f'{round(self.client.latency * 10**3)}ms')
        embed.add_field(name=":globe_with_meridians: Server Count", value=f"{len(self.client.guilds)}")
        embed.add_field(name=":alien: Total Users Visible", value=f"{len(self.client.users)}")
        users = []
        bots = []
        for user in self.client.users:
            bots.append(user) if user.bot else users.append(user)
        embed.add_field(name=f':busts_in_silhouette: Users', value=f'{len(users)}')
        embed.add_field(name=f':robot: Bots', value=f'{len(bots)}')
        sysinfo = platform.uname()
        if sysinfo.system != "Linux":
            import os
            embed.add_field(name="Process ID", value=f'{os.getpid()}')
        else:
            embed.add_field(name="Process ID", value=f'{utils.linux_current_pid()}')
        embed.add_field(name="OS Kernel", value=f'{sysinfo.system} {sysinfo.release} ')
        embed.add_field(name="CPU Architecture", value=f'{sysinfo.machine}')
        embed.add_field(name="Python Executable", value=f'{", ".join(platform.architecture())}')
        mem_info = utils.linux_mem_info()
        util_total_perc = round(mem_info["MemUsed"] / mem_info["MemTotal"] * 100, 2)
        ram_progress = utils.progress_bar(mem_info["MemUsed"], mem_info["MemTotal"], 50)
        # 10
        embed.add_field(name='Utilised/Total RAM',
                        value=f'{utils.byte_units(mem_info["MemUsed"], iec=True)} / '
                              f'{utils.byte_units(mem_info["MemTotal"], iec=True)} ({util_total_perc}%)\n'
                              f'`{ram_progress}`', inline=False)
        proc_mem_info = utils.linux_proc_mem_info()
        bot_total_perc = round(proc_mem_info["Individual"] / mem_info["MemTotal"] * 100, 2)
        # 11
        embed.add_field(name='Bot/Total RAM',
                        value=f'{utils.byte_units(proc_mem_info["Individual"], iec=True)} / '
                              f'{utils.byte_units(mem_info["MemTotal"], iec=True)} ({bot_total_perc}%)\n'
                              f'`{utils.progress_bar(proc_mem_info["Individual"], mem_info["MemTotal"], 50)}`',
                        inline=False)
        bot_util_perc = round(proc_mem_info["Individual"] / mem_info["MemUsed"] * 100, 2)
        # 12
        embed.add_field(name='Bot/Utilised RAM',
                        value=f'{utils.byte_units(proc_mem_info["Individual"], iec=True)} / '
                              f'{utils.byte_units(mem_info["MemUsed"], iec=True)} ({bot_util_perc}%)\n'
                              f'`{utils.progress_bar(proc_mem_info["Individual"], mem_info["MemUsed"], 50)}`',
                        inline=False)
        cpu_util = await utils.linux_cpu_utilization()
        cpu_total_perc = round(cpu_util * 100, 2)
        # 13
        embed.add_field(name='Utilised/Total CPU (Inaccurate due to interference)',
                        value=f'{cpu_total_perc}%\n'
                              f'`{utils.progress_bar(*cpu_util.as_integer_ratio(), 50)}`',
                        inline=False)
        proc_util = await utils.linux_proc_cpu_utilization()
        proc_cpu_total_perc = round(proc_util * 100, 2)
        # 14
        embed.add_field(name='Bot/Total CPU',
                        value=f'{proc_cpu_total_perc}%\n'
                              f'`{utils.progress_bar(*proc_util.as_integer_ratio(), 50)}`',
                        inline=False)
        system_command = self.client.get_application_command("system-info")
        if system_command is None:
            class DummyApplicationCMD:
                def __init__(self):
                    self.id = 0
            system_command = DummyApplicationCMD()
        embed.add_field(name="More System Information",
                        value=f"See **{self.client.command_prefix}system-info** or "
                              f"</system-info:{system_command.id}>")
        embed.add_field(name="<:pysnake:955767348202192936> Python version",
                        value=f'[{"{}.{}.{}-{}".format(*tuple(sys.version_info))}](https://www.python.org/downloads'
                              f'/release/python-{"{}{}{}".format(*tuple(sys.version_info))}/)')
        if ctx.guild is not None and ctx.guild.id == 336642139381301249:
            embed.add_field(name="<:dpy:596577034537402378> "
                                 "Discord.py version",
                            value=f'[2.0.0a](https://pypi.org/project/discord.py/'
                                  f'2.0.0a)')
        else:
            embed.add_field(name="<:PycordLogo:955768689528033290> "
                                 "Pycord version",
                            value=f'[{discord.__version__}](https://pypi.org/project/py-cord/'
                                  f'{discord.__version__})')
        embed.add_field(name=":stopwatch: Up Since", value=utils.discord_ts(config.up_since, "R"))
        embed.add_field(name=":stopwatch: Uptime", value=f'{datetime.datetime.now() - config.up_since}')
        await ctx.respond(embed=embed)

    @bridge.bridge_command(
        name="invite", description="Invite the bot to your server",
        aliases=["add-bot", "add_bot", "add-app", "add_app"]
    )
    @commands.cooldown(**config.default_cooldown_options)
    @commands.bot_has_permissions(send_messages=True)
    async def invite_cmd(self, ctx: bridge.Context):
        """Invite the bot to your server"""
        view = utils.DefaultView(discord.ui.Button(style=discord.ButtonStyle.blurple, label="Add Bot",
                                                   url=f'https://revnoplex.xyz/revnobot'))

        if hasattr(ctx, 'respond'):
            await ctx.respond(ephemeral=True, view=view)
        else:
            try:
                await ctx.author.send(view=view)
                await ctx.message.add_reaction('✉')
            except discord.Forbidden:
                await ctx.respond(
                    embed=utils.default_embed(
                        ctx, f'Could not dm you a bot invite',
                        f'Make sure you have server dms on or im not blocked and try again'
                    )
                )


def setup(client):
    client.add_cog(Information(client))
