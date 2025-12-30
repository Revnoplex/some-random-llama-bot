import sys
import datetime
import discord
from discord import Enum
from discord.ext import commands, bridge
import config
import traceback
import utils
import logging
from typing import Union

error_logging = logging.getLogger('errors')
bot_logger = logging.getLogger('bot-logger')
command_logging = logging.getLogger('commands')


class Errors(config.RevnobotCog):
    def __init__(self, client: bridge.Bot):
        self.client = client
        self.description = "The main error handler of the bot"
        self.icon = "\U000026A0"
        self.hidden = True

    async def command_error_manage(
            self, ctx: Union[commands.Context, discord.ApplicationContext], error: discord.DiscordException
    ):
        app = await self.client.application_info()

        # noinspection SpellCheckingInspection
        async def log_error():
            now = int(round(datetime.datetime.now().timestamp()))
            resp_message = None
            resp_message_id = 0
            if isinstance(ctx, discord.ApplicationContext):
                if not ctx.interaction.response.is_done():
                    try:
                        resp_interaction = await ctx.respond("** **", ephemeral=True)
                    except discord.HTTPException:
                        resp_message = await ctx.channel.send("** **")
                        resp_message_id = resp_message.id
                    else:
                        try:
                            resp_message = await resp_interaction.original_response()
                        except discord.DiscordException:
                            pass
                        else:
                            resp_message_id = resp_message.id
                else:
                    try:
                        resp_message = await ctx.interaction.original_response()
                    except discord.DiscordException:
                        pass
                    else:
                        resp_message_id = resp_message.id
                    resp_message = None
            # Binary layout of error IDs:
            # VINT (2-bit), CT (1-bit), PID (22-bit), BMID (1-bit), TS (64-bit)
            # 00-0-0000000000000000000000-0-0000000000000000000000000000000000000000000000000000000000000000
            # VINT: Version integer: 0 is full, 1 is beta and 2 is dev
            # CT: Command type: 0 means prefix command, 1 means application command
            # PID: Process ID: The current process ID of the bot on the system
            # BMID: Is Message ID: This bit indicates if the TS value is a message id (1) or just a timestamp (0)
            # TS: Timestamp or Message ID: The message involved with the command
            # or the timestamp in seconds from 1970 of when the error occurred.
            # A timestamp can be calculated from the message id using the following:
            # (int(message_id) >> 22) + 1420070400000) / 1000
            if isinstance(ctx, discord.ApplicationContext):
                error_id_dec = (
                        config.version_int << 88 | 1 << 87 | utils.linux_current_pid() << 65 |
                        bool(resp_message_id) << 64 | (resp_message_id or now)
                )
            else:
                error_id_dec = (
                        config.version_int << 88 | 0 << 87 | utils.linux_current_pid() << 65 |
                        bool(ctx.message.id) << 64 | (ctx.message.id or now)
                )
            error_id = hex(error_id_dec)[2:]
            full_error_string = type(error).__name__ + ": " + str(error)
            traceback_string = "\n".join(traceback.format_tb(error.__traceback__))
            oneline_tb = "\\n".join([line.replace('\n', '') for line in traceback.format_tb(error.__traceback__)])
            if isinstance(error, (commands.CommandInvokeError, discord.ApplicationCommandInvokeError,
                                  commands.ConversionError)):
                full_error_string = type(error.original).__name__ + ": " + str(error.original)
                traceback_string = "\n".join(traceback.format_tb(error.original.__traceback__))
                oneline_tb = "\\n".join([line.replace('\n', '') for line in
                                         traceback.format_tb(error.original.__traceback__)])
            if isinstance(error.original, discord.HTTPException):
                if error.original.code == 40060:
                    http_embed = utils.warning_embed(
                        ctx.bot, "Response Clash", "I couldn't not respond to the interation because it was already "
                                                   "responded to. This is most likely because there is a duplicate "
                                                   "process of the bot running by accident")
                    await ctx.send(embed=http_embed)
                    return
                if error.original.code == 50006:
                    http_embed = utils.warning_embed(
                        ctx.bot, "Empty Message", "Oops, it looks like a message containing a NoneType object was "
                                                  "attempted to be sent")
                    if isinstance(ctx, discord.ApplicationContext):
                        if not ctx.interaction.response.is_done() or resp_message is None:
                            try:
                                await ctx.respond(embed=http_embed, ephemeral=True)
                            except discord.NotFound:
                                await ctx.channel.send(embed=http_embed)
                        else:
                            await resp_message.edit(embed=http_embed)
                    else:
                        await ctx.send(embed=http_embed)
                    return
                if error.original.code == 10062:
                    http_embed = utils.warning_embed(
                        ctx.bot, "Bot Response Failed",
                        "Sorry, but it appears I took too long to respond to your request. Please try again"
                    )
                    if isinstance(ctx, discord.ApplicationContext):
                        if not ctx.interaction.response.is_done() or resp_message is None:
                            try:
                                await ctx.respond(embed=http_embed, ephemeral=True)
                            except discord.NotFound:
                                await ctx.channel.send(embed=http_embed)
                        else:
                            await resp_message.edit(embed=http_embed)
                    else:
                        await ctx.send(embed=http_embed)
                    return
                await utils.print_http_error(error.original)
            utils.print_error(
                f'Oops, an unexpected error occurred in a command! Error ID: {error_id}. {full_error_string}.'
                f'\nTraceback:\n{traceback_string}', file=sys.stderr)

            full = ""
            if ctx.command is None:
                command_name = "No command was invoked"
            else:
                if hasattr(ctx.command, "full_parent_name"):
                    if ctx.command.full_parent_name == "":
                        full = ""
                    else:
                        full = f'{ctx.command.full_parent_name}: '
                else:
                    full = ''
                command_name = ctx.command.name

            if hasattr(ctx, "cog"):
                if ctx.cog is None:
                    cog_name = None
                else:
                    cog_name = ctx.cog.qualified_name
            else:
                cog_name = None
            if utils.is_dm_channel(ctx.channel):
                channel_name = 'DM Channel'
                guild_name = 'No Guild'
            else:
                channel_name = f'#{ctx.channel.name}'
                guild_name = ctx.guild.name
            if isinstance(ctx, discord.ApplicationContext):
                if resp_message is None:
                    message_content = None
                    jump_url = None
                else:
                    message_content = resp_message.content
                    jump_url = resp_message.jump_url
            else:
                jump_url = ctx.message.jump_url
                message_content = ctx.message.content
            if hasattr(ctx, "invoked_with"):
                invoked_with = ctx.invoked_with
            else:
                invoked_with = command_name
            http_field = ""
            if hasattr(error, "original") and isinstance(error.original, discord.HTTPException):
                http_info = await utils.format_http_error(error.original)
                http_value = ""
                for name, value in http_info.items():
                    http_value += f'{str(name.title())}: {value}, '
                http_field = f', HTTP Response Error Information: ({http_value})'
            error_logging.error(
                f'Command Failed Invoking ({error}). Details: Error ID: {error_id}, '
                f'{guild_name}, '
                f'{channel_name}, '
                f'{ctx.author}({ctx.author.id}): '
                f'{message_content} ({cog_name}: {full}'
                f'{invoked_with}({command_name}): '
                f'({jump_url}), Traceback: ({oneline_tb}){http_field}')
            command_logging.error(
                f'Command Failed Invoking ({error}). Details: '
                f'{guild_name}, '
                f'{channel_name}, '
                f'{ctx.author}({ctx.author.id}): '
                f'{message_content} ({cog_name}: {full}'
                f'{invoked_with}({command_name}): '
                f'({jump_url}), Traceback: ({oneline_tb}){http_field}')
            bot_logger.error(
                f'Command Failed Invoking ({error}). Details: Error ID: {error_id}, '
                f'Guild: {guild_name}, '
                f'Channel: {channel_name}, '
                f'{ctx.author}({ctx.author.id}): '
                f'{message_content} ({cog_name}: {full}'
                f'{invoked_with}({command_name}): '
                f'({jump_url}) , Traceback: ({oneline_tb}){http_field}')
            owner_name = f"{app.owner.name}#{app.owner.discriminator}" if int(app.owner.discriminator) \
                else app.owner.name
            msg_embed = utils.default_embed(
                ctx, f'Something went wrong!',
                f'Sorry, but {ctx.bot.user.mention} has encountered an unexpected error.\n'
                f'A report has been sent to the developer **@{owner_name}**. Please '
                f'[report this error]('
                f'https://github.com/Revnoplex/some-random-llama-bot/issues/new'
                f'?assignees=&labels=bug+tagged+with+error+id'
                f') on [the github repository](https://github.com/Revnoplex/some-random-llama-bot), and make sure to '
                f'specify the following error ID: `{error_id}` and specify any extra information regarding the error.',
                discord.Colour.red(),
                "Unexpected Error"
            )
            if isinstance(ctx, discord.ApplicationContext):
                if not ctx.interaction.response.is_done() or resp_message is None:
                    try:
                        await ctx.respond(embed=msg_embed, ephemeral=True)
                    except discord.HTTPException:
                        await ctx.channel.send(embed=msg_embed)
                else:
                    await resp_message.edit(embed=msg_embed)
            else:
                await ctx.send(embed=msg_embed)

            t_full = ""
            if ctx.command is None:
                t_command_name = "No command was invoked"
            else:
                if hasattr(ctx.command, "full_parent_name"):
                    if ctx.command.full_parent_name == "":
                        t_full = ""
                    else:
                        t_full = f'{ctx.command.full_parent_name}: '
                else:
                    t_full = ''
                t_command_name = ctx.command.name
            if hasattr(ctx, "cog"):
                if ctx.cog is None:
                    t_cog_name = None
                else:
                    t_cog_name = ctx.cog.qualified_name
            else:
                t_cog_name = None
            if utils.is_dm_channel(ctx.channel):
                t_channel_name = 'DM Channel'
                t_channel_id = 'DM Channel'
                t_guild_name = 'No Guild'
                t_guild_id = "No Guild"
            else:
                t_channel_name = f'#{ctx.channel.name}'
                t_channel_id = ctx.channel.id
                t_guild_name = ctx.guild.name
                t_guild_id = ctx.guild.id
            pre_description = "An Unexpected Error Occurred With the bot. details are below:\n```python\n{}```"
            if len(traceback_string) <= 4096 - len(pre_description) + 2:
                description = pre_description.format(traceback_string)
            else:
                description = pre_description.format(
                    "Traceback was too large to be displayed. See tty output for traceback"
                )
            report_embed = utils.default_embed(
                ctx, f'Unexpected Error Report', description, discord.Colour.red(), "Unexpected Error"
            )
            report_embed.add_field(name=":1234: Error ID", value=f'`{error_id}`')
            report_embed.add_field(name=":file_folder: Exception Class", value=f'`{type(error.original).__name__}`')
            report_embed.add_field(name=":x: Error Raised", value=f'`{error.original.__str__()[:1022]}`')
            report_embed.add_field(name=":house: Guild", value=f'{t_guild_name}\n`{t_guild_id}`')
            report_embed.add_field(name=":hash: Channel", value=f'{t_channel_name}\n`{t_channel_id}`')
            report_user = f"{ctx.author.name}#{ctx.author.discriminator}" if int(ctx.author.discriminator) else \
                ctx.author
            report_embed.add_field(name=":bust_in_silhouette: User",
                                   value=f'{report_user}\n`{ctx.author.id}`')
            if isinstance(ctx, discord.ApplicationContext) and ctx.interaction.response.is_done():
                try:
                    resp_message = await ctx.interaction.original_response()
                except discord.NotFound:
                    resp_message = None
            else:
                resp_message = ctx.message
            if resp_message is not None:
                if resp_message.content:
                    report_embed.add_field(
                        name=":speech_balloon: Command Invoked With Message",
                        value="Too large to be displayed" if len(resp_message.content) > 1024 else resp_message.content,
                        inline=False
                    )
                report_embed.add_field(name=":1234: Message ID",
                                       value=f' [{resp_message.id}]({resp_message.jump_url})')
                report_embed.add_field(name=":link: Jump URL",
                                       value=f' {resp_message.jump_url}')
            if hasattr(ctx, "invoked_with"):
                invoked_with = ctx.invoked_with
            else:
                invoked_with = t_command_name
            report_embed.add_field(name=":joystick: Command Name", value=f'{invoked_with} ({t_command_name})')
            report_embed.add_field(name=":gear: Command Cog/Full Name", value=f'{t_cog_name}, {t_full}')
            if isinstance(error.original, discord.HTTPException):
                http_info = await utils.format_http_error(error.original)
                http_items = http_info.items()
                if len(http_items) > 25 - len(report_embed.fields):
                    http_items = list(http_items)[:25 - len(report_embed.fields)]

                def big_content_check(key) -> bool:
                    return (
                        str(key).lower().endswith("url") or str(key).lower().endswith("message") or
                        str(key).lower().endswith("content") or str(key).lower() == "headers"
                    )
                inlines = [(name, value) for name, value in http_items if not big_content_check(name)]
                big_fields = [(name, value) for name, value in http_items if big_content_check(name)]
                for name, value in inlines:
                    if len(str(value)) <= 1024:
                        report_embed.add_field(name=str(name).title(), value=str(value))
                    else:
                        report_embed.add_field(
                            name=str(name).title(),
                            value="Value was too large to be displayed. See console for full output"
                        )
                for name, value in big_fields:
                    if len(str(value)) <= 1024:
                        report_embed.add_field(name=str(name).title(), value=str(value), inline=False)
                    else:
                        report_embed.add_field(
                            name=str(name).title(),
                            value="Value was too large to be displayed. See console for full output"
                        )
            report_message = await app.owner.send(embed=report_embed)
            if resp_message is not None:
                if len(resp_message.attachments) > 0:
                    files = []
                    for attachment in resp_message.attachments:
                        the_file = await attachment.to_file()
                        files.append(the_file)
                    await report_message.reply('**Attachments:**', files=files)
                if len(resp_message.embeds) > 0:
                    for message_embed in resp_message.embeds:
                        await report_message.reply('**Embed:**', embed=message_embed)
        if isinstance(error, (commands.CommandInvokeError, discord.ApplicationCommandInvokeError,
                              commands.ConversionError)):
            if isinstance(error.original, (commands.CheckFailure,  commands.UserInputError, commands.CommandNotFound,
                                           commands.CommandOnCooldown)):
                error = error.original
            else:
                await log_error()

        if isinstance(error, commands.MissingRequiredArgument):
            if isinstance(ctx.command.parent, commands.Group):
                usage = ("{prefix}" + ctx.command.usage) if ctx.command.usage else None
            else:
                usage = ctx.command.usage if hasattr(ctx.command, "usage") else None
            if usage is None:
                usage_message = 'The correct usage for this command was not specified'
            else:
                try:
                    usage_message = (f'The correct usage for this command is '
                                     f'`{(usage or "None").format(prefix=ctx.prefix, name=ctx.command.qualified_name)}'
                                     f'`')
                except KeyError:
                    usage_message = f'The correct usage for this command is `{usage}`'
            await ctx.reply(embed=utils.warning_embed(
                ctx.bot, "Not Enough Arguments",
                f'Not enough arguments Provided!\n{usage_message}. See `{ctx.bot.command_prefix}help '
                f'{ctx.command.qualified_name}` for more info'
            ))

        elif isinstance(error, commands.TooManyArguments):
            if isinstance(ctx.command.parent, commands.Group):
                usage = ("{prefix}" + ctx.command.usage) if ctx.command.usage else None
            else:
                usage = ctx.command.usage
            if usage is None:
                usage_message = 'The correct usage for this command was not specified'
            else:
                try:
                    usage_message = (f'The correct usage for this command is '
                                     f'`{(usage or "None").format(prefix=ctx.prefix, name=ctx.command.qualified_name)}'
                                     f'`')
                except KeyError:
                    usage_message = (f'The correct usage for this command is '
                                     f'`{usage}`')
            await ctx.reply(embed=utils.warning_embed(ctx.bot,
                                                      "Too Many Arguments",
                                                      f'Too many arguments Provided!\n{usage_message}. See '
                                                      f'`{ctx.prefix}help {ctx.command.qualified_name}` for more info'))

        elif isinstance(error, (commands.BadArgument, commands.BadUnionArgument)):
            if isinstance(ctx, commands.Context):
                if isinstance(ctx.command.parent, commands.Group):
                    usage = ("{prefix}" + ctx.command.usage) if ctx.command.usage else None
                else:
                    usage = ctx.command.usage
                if usage is None or usage == "None":
                    usage_message = 'The correct usage for this command was not specified'
                else:
                    try:
                        usage_message = (
                            f'The correct usage for this command is `'
                            f'{(usage or "None").format(prefix=ctx.prefix, name=ctx.command.qualified_name)}`'
                        )
                    except KeyError:
                        usage_message = f'The correct usage for this command is `{usage}`'
            else:
                usage_message = "The correct usage for this command is in the help menu"
            if isinstance(error, commands.BadUnionArgument):
                error_message = ", ".join([str(e) for e in error.errors])
            else:
                error_message = str(error)
            error_message_quotes = f"{error_message}{'' if error_message.endswith('.') else '.'}\n\n" \
                if error_message else ""
            prefix = '/' if isinstance(ctx, discord.ApplicationContext) else ctx.prefix
            embed = utils.warning_embed(
                ctx.bot,
                "Bad Command Argument",
                f'{error_message_quotes}{usage_message}. See `{prefix}help {ctx.command.qualified_name}` for more info'
            )
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)

        elif isinstance(error, commands.NoPrivateMessage):
            embed = utils.warning_embed(ctx.bot, "Server Only", f'This command can only be executed in a server')
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)

        elif isinstance(error, commands.NSFWChannelRequired):
            embed = utils.warning_embed(ctx.bot, "Not Nsfw Channel", f'This command contains explict material and can '
                                                                     f'only be run in channels marked as nsfw')
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)

        elif isinstance(error, commands.PrivateMessageOnly):
            embed = utils.warning_embed(ctx.bot, "DMs Only", f'This command can only be executed in DMs')
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)
        elif isinstance(error, commands.NotOwner):
            embed = utils.warning_embed(
                ctx.bot, f'Not Owner',
                f'{ctx.author.mention}, {error.__str__()} Only {app.owner.mention} can do this'
            )
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.response.send_message(embed=embed, ephemeral=True)
                except discord.DiscordException:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRole):
            role = ctx.guild.get_role(error.missing_role)
            if role is not None:
                if role.mentionable:
                    role_mention = role.mention
                else:
                    role_mention = f'@{role.name}'
            else:
                role_mention = '@unknown role'
            embed = utils.warning_embed(ctx.bot, f'Required Role Missing',
                                        f'{ctx.author.mention}, you need {role_mention} to be able to do this')
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingPermissions):
            if len(error.missing_permissions) == 1:
                perm_to_write = error.missing_permissions[0]
                perm_to_write = perm_to_write.replace('guild', 'server')
                perm_to_write = perm_to_write.replace('create_instant_invite', 'create_invites')
                perm_to_write = perm_to_write.replace('external_emojis', 'use_external_emojis')
                perm_to_write = perm_to_write.replace('external_stickers', 'use_external_stickers')
                perm_to_write = perm_to_write.replace("_", " ")
                perm_to_write = perm_to_write.title()
                perms = perm_to_write
                p = "permission"
            else:
                p = "permissions"
                perms = ""
                for x in error.missing_permissions:
                    perm_to_write = x
                    perm_to_write = perm_to_write.replace('guild', 'server')
                    perm_to_write = perm_to_write.replace('create_instant_invite', 'create_invites')
                    perm_to_write = perm_to_write.replace('external_emojis', 'use_external_emojis')
                    perm_to_write = perm_to_write.replace('external_stickers', 'use_external_stickers')
                    perm_to_write = perm_to_write.replace("_", " ")
                    perm_to_write = perm_to_write.title()
                    perms += f'{perm_to_write}, '
            embed = utils.warning_embed(ctx.bot, f'Required {p.capitalize()} Missing',
                                        f'{ctx.author.mention}, you need the {p} **{perms}** to be able to do this')
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)
        elif isinstance(error, commands.BotMissingPermissions):
            if len(error.missing_permissions) == 1:
                perm_to_write = error.missing_permissions[0]
                perm_to_write = perm_to_write.replace('guild', 'server')
                perm_to_write = perm_to_write.replace('create_instant_invite', 'create_invites')
                perm_to_write = perm_to_write.replace('external_emojis', 'use_external_emojis')
                perm_to_write = perm_to_write.replace('external_stickers', 'use_external_stickers')
                perm_to_write = perm_to_write.replace("_", " ")
                perm_to_write = perm_to_write.title()
                perms = perm_to_write
                p = "permission"
            else:
                p = "permissions"
                perms = ""
                for x in error.missing_permissions:
                    perm_to_write = x
                    perm_to_write = perm_to_write.replace('guild', 'server')
                    perm_to_write = perm_to_write.replace('create_instant_invite', 'create_invites')
                    perm_to_write = perm_to_write.replace('external_emojis', 'use_external_emojis')
                    perm_to_write = perm_to_write.replace('external_stickers', 'use_external_stickers')
                    perm_to_write = perm_to_write.replace("_", " ")
                    perm_to_write = perm_to_write.title()
                    perms += f'{perm_to_write}, '
            try:
                embed = utils.warning_embed(ctx.bot, f'Bot Missing {p.capitalize()}',
                                            f'{ctx.author.mention}, I need the {p} **{perms}** to be able to do this')
                if isinstance(ctx, discord.ApplicationContext):
                    try:
                        await ctx.respond(embed=embed, ephemeral=True)
                    except discord.NotFound:
                        await ctx.channel.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
            except discord.Forbidden:
                try:
                    await ctx.message.add_reaction('❗')
                except (discord.Forbidden, AttributeError):
                    try:
                        await ctx.author.send(f'>>> Bot Missing {p.capitalize()}\n {ctx.author.mention}, '
                                              f'I need the {p} **{perms}** to be able to do this')
                    except discord.Forbidden:
                        pass
        elif isinstance(error, commands.CommandNotFound):
            command_ = error
            command_st = str(command_)
            command_list = command_st.split()
            command_short = [s.replace('"', '') for s in command_list]
            command_str = command_short[1]
            help_cmd = self.client.get_application_command("help")
            help_cmd_mention = "" if help_cmd is None else f'</help:{help_cmd.id}> or '
            await ctx.send(embed=utils.warning_embed(ctx.bot, f'Command Not Found',
                                                     f'The Command **{ctx.prefix}{command_str} ** Was Not Found!\n'
                                                     f'Try {help_cmd_mention}**{self.client.command_prefix}'
                                                     f'help** for a list of commands'))
        elif isinstance(error, commands.CommandOnCooldown):
            retry_after_str = utils.discord_ts(
                datetime.datetime.now() + datetime.timedelta(seconds=error.retry_after), "R"
            )
            cooldown_prefix = [
                "I am", "You are", "This Server is", "This Channel is", "You are",
                "This Category is", "Your Role is"
            ]
            channel_mention, channel_category = "this channel", "this category"
            if isinstance(ctx.channel, discord.abc.GuildChannel):
                channel_mention = ctx.channel.mention
                channel_category = ctx.channel.category
            guild_mention = ctx.guild.name if ctx.guild else "this server"
            role_mention = ctx.author.top_role.mention if isinstance(
                ctx.author, discord.Member
            ) else "a role in this server"
            cooldown_suffix = [
                "", f"as {ctx.author.mention}", f"in {guild_mention}", f"in {channel_mention}",
                f"as {ctx.author.mention} in {guild_mention}", f"in {channel_category}",
                f"as a member of {role_mention}"
            ]
            bucket_type: Enum = error.type
            suffix_string = ""
            type_string = ""
            if isinstance(bucket_type.value, int):
                suffix_string = cooldown_suffix[bucket_type.value]
                type_string = cooldown_prefix[bucket_type.value] + " on "
            if isinstance(ctx.channel, discord.abc.PrivateChannel):
                suffix_string, type_string = (
                     f"as {ctx.author.mention}", "You are on "
                ) if bucket_type.value in [4, 6] else ("in this channel", "This Channel is on ")
            cooldown_embed = utils.default_embed(
                ctx,
                f"{type_string.split(';')[0]}Cooldown" + (type_string.split(';')[-1] if ";" in type_string else ""),
                f'{retry_after_str}, you can execute another command {suffix_string}',
                discord.Colour.blue()
            )
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=cooldown_embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=cooldown_embed)
            else:
                await ctx.send(embed=cooldown_embed)
        elif isinstance(error, commands.DisabledCommand):
            embed = utils.warning_embed(ctx.bot, "Command Disabled", f'{error}')
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)
        elif not isinstance(error, (commands.CommandInvokeError, discord.ApplicationCommandInvokeError,
                                    commands.ConversionError)):
            embed = utils.warning_embed(ctx.bot, f'Unknown Error',
                                        f'Description: `{type(error)}`, `{repr(error)}`, `{str(error)}`')
            if isinstance(ctx, discord.ApplicationContext):
                try:
                    await ctx.respond(embed=embed, ephemeral=True)
                except discord.NotFound:
                    await ctx.channel.send(embed=embed)
            else:
                await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        await self.command_error_manage(ctx, error)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await self.command_error_manage(ctx, error)

    async def event_error(self, event_name: str, exception: BaseException, data: tuple, other_data: dict):
        app = await self.client.application_info()
        if isinstance(exception, utils.ConfigFileException):
            bot_logger.warning(str(exception))
            utils.print_error(str(exception), file=sys.stderr)
            term = "corrupted" if isinstance(exception, utils.ConfigFileCorrupted) else "missing"
            embed = utils.warning_embed(self.client, f"A Server Config File is {term.capitalize()}",
                                                     f"The server configuration file for **{exception.guild.name}** "
                                                     f"is {term}! Please tell the server owner "
                                                     f"to run the setup command to restore or create a new one.")
            embed.add_field(name="Guild ID", value=f'{exception.guild.id}')
            embed.add_field(name="Event", value=f'{event_name}')
            if isinstance(exception, utils.ConfigFileCorrupted):
                embed.add_field(name="Missing Key", value=f"`{exception.missing_key}`")
            if event_name != 'on_message' or data[0].author.id != self.client.user.id:
                await app.owner.send(embed=embed)
            return
        full_error_string = type(exception).__name__ + ": " + str(exception)
        formatted_tb = traceback.format_tb(exception.__traceback__)
        tb_string = "\n".join(formatted_tb)
        oneline_tb = "\\n".join([line.replace('\n', '') for line in formatted_tb])
        error_logging.error(
            f'Event Failed Executing ({full_error_string}). Details: '
            f'Event: {event_name}, Exception Class: {type(exception).__name__}, Error Message: {exception}, '
            f'Traceback: {oneline_tb}')
        bot_logger.error(
            f'Event Failed Executing. Details: '
            f'Event: {event_name}, Exception Class: {type(exception).__name__}, Error Message: {exception}, '
            f'Data: {data}, Extra Data: {other_data}, '
            f'Traceback: {oneline_tb}')
        if isinstance(exception, discord.HTTPException) and exception.status == 405:
            pass
        else:
            embed = utils.default_embed(
                self.client, f'Unexpected Error Report',
                f'An Unexpected Error Occurred With the bot. Data associated with the event has been logged. '
                f'Details are below:\n```python\n{tb_string}```',
                colour=discord.Colour.red(), typename="Unexpected Error"
            )
            embed.add_field(name=":file_folder: Exception Class", value=f'`{type(exception).__name__}`')
            embed.add_field(name=":x: Error Raised", value=f'`{exception}`')
            embed.add_field(name=":clipboard: Event", value=f'`{event_name}`')
            if event_name != 'on_message' or data[0].author.id != self.client.user.id:
                await app.owner.send(embed=embed)
            utils.print_error(f'Oops, an unexpected error occurred in an event! {full_error_string}.\nTraceback:'
                              f'\n{tb_string}',
                              file=sys.stderr)


def setup(client):
    client.add_cog(Errors(client))
