from contextlib import nullcontext
from typing import Union
import discord
import httpx
import ollama
from discord.ext import commands, bridge, pages
from discord.ext.bridge import BridgeOption
import config
import utils

context_bank: dict[int, list] = {}


class Ollama(config.RevnobotCog):

    def __init__(self, client: bridge.Bot):
        self.client = client
        self.description = "Commands to interact with ollama LLMs"
        self.icon = "\U0001f999"
        self.hidden = False
        self.ollama_client = ollama.AsyncClient(config.ollama_server)

    @staticmethod
    async def cog_check(ctx: Union[discord.ApplicationContext, commands.Context]) -> bool:
        if ctx.command.qualified_name in ['clear-context']:
            return True
        check = config.current_profile["commands"][ctx.command.qualified_name]["enabled"]
        if not check:
            raise commands.DisabledCommand('This LLM is disabled in the current configuration')
        return True

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-llama',
        description="Ask the llama llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_llama_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to llama"),
            model: BridgeOption(
                str, "The llama model to use",
                default=config.current_profile['commands']['ask-llama']['default'],
                choices=config.current_profile['commands']['ask-llama']['options'].keys()
            ) = config.current_profile['commands']['ask-llama']['default'],
    ):
        """About the bot?"""
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        available_models = [model.model for model in (await self.ollama_client.list()).models]
        if prompt.split()[0].upper() in config.current_profile['commands'][
            ctx.command.qualified_name
        ]['options'].keys():
            model = prompt.split()[0].upper()
        model_id = config.current_profile['available'][
            config.current_profile['commands'][ctx.command.qualified_name]['options'][model]
        ]
        if model_id not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model ``{model}`` is not available. "
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=model_id, messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama Response", f"{response.message.content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response.message.content[x:x + max_length] for x in range(0, len(response.message.content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Llama Response {index+1}/{len(response_pages)}", f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-llama-vision',
        description="Ask the llama-vision llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_llama_vision_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to llama"),
            model: BridgeOption(
                str, "The llama model to use",
                default=config.current_profile['commands']['ask-llama-vision']['default'],
                choices=config.current_profile['commands']['ask-llama-vision']['options'].keys()
            ) = config.current_profile['commands']['ask-llama-vision']['default'],
            image: BridgeOption(
                discord.Attachment, "The image to show the model", required=False
            ) = None
    ):
        """About the bot?"""
        await ctx.defer()
        images = []
        if (ctx.message and len(ctx.message.attachments) > 0) or image:
            image_bytes = await (
                ctx.message.attachments[0] if ctx.message and len(ctx.message.attachments) > 0
                else image
            ).read()
            images.append(image_bytes)
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        available_models = [model.model for model in (await self.ollama_client.list()).models]

        if prompt.split()[0].upper() in config.current_profile['commands'][
            ctx.command.qualified_name
        ]['options'].keys():
            model = prompt.split()[0].upper()
        print("attempted to use:")
        print(config.current_profile['commands'][ctx.command.qualified_name]['options'][model])
        print("but only these keys existied")
        print(config.current_profile['available'].keys())
        model_id = config.current_profile['available'][
            config.current_profile['commands'][ctx.command.qualified_name]['options'][model]
        ]
        if model_id not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model ``{model}`` is not available. "
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'images': images,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=model_id, messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama Response", f"{response.message.content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response.message.content[x:x + max_length] for x in range(0, len(response.message.content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Llama Response {index + 1}/{len(response_pages)}", f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='llama-text',
        description="Send a sample of text for llama to extend",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def llama_text_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to llama"),
            model: BridgeOption(
                str, "The llama model to use",
                default=config.current_profile['commands']['llama-text']['default'],
                choices=config.current_profile['commands']['llama-text']['options'].keys()
            ) = config.current_profile['commands']['llama-text']['default'],
    ):
        """About the bot?"""
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        available_models = [model.model for model in (await self.ollama_client.list()).models]
        if prompt.split()[0].upper() in config.current_profile['commands'][
            ctx.command.qualified_name
        ]['options'].keys():
            model = prompt.split()[0].upper()
        model_id = config.current_profile['available'][
            config.current_profile['commands'][ctx.command.qualified_name]['options'][model]
        ]
        if model_id not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model ``{model}`` is not available. "
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=model_id, messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama Response", f"{response.message.content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response.message.content[x:x + max_length] for x in range(0, len(response.message.content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Llama Response {index + 1}/{len(response_pages)}", f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-llama-3-3',
        description="Ask the llama 3.3 llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_llama_3_3_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to llama"),
    ):
        """About the bot?"""
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=config.current_profile['available'][
                        next(iter(config.current_profile['commands'][ctx.command.qualified_name]['options'].values()))
                    ],
                    messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama 3.3 Response", f"{response.message.content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response.message.content[x:x + max_length] for x in range(0, len(response.message.content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Llama 3.3 Response {index + 1}/{len(response_pages)}", f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-qwq',
        description="Ask the qwq llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_qwq_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to qwq"),
            show_thinking: BridgeOption(
                bool, "Show <think></think> part of the response", default=True, name="show-thinking"
            ) = True
    ):
        """About the bot?"""
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=config.current_profile['available'][
                        next(iter(config.current_profile['commands'][ctx.command.qualified_name]['options'].values()))
                    ],
                    messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        thinking_part = None
        if show_thinking:
            thinking_part = (
                "-# **Thinking**...\n-# " +
                response.message.content.split("\n</think>")[0].replace("<think>\n\n", "").replace(
                    "<think>\n", ""
                ).replace(
                    "\n", "\n-# "
                ).replace("\n-# \n", "\n-# ** **\n").rsplit("-# ", 1)[0]
            )
            response_content = thinking_part + "\n" + response.message.content.split("</think>\n\n")[-1]
        else:
            response_content = response.message.content.split("</think>\n\n")[-1]
        if len(response_content) <= 2000:
            await ctx.respond(f"{response_content}")
        elif len(response_content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "QwQ Response", f"{response_content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4093 if thinking_part else 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response_content[x:x + max_length] for x in range(0, len(response_content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                part_of_thinking = (
                        thinking_part and index and max_length * index < len(thinking_part)
                )
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"QwQ Response {index + 1}/{len(response_pages)}",
                        f"-# {response_page}" if part_of_thinking else f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-deepseek',
        description="Ask the deepseek-r1 llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_deepseek_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to deepseek"),
            enable_thinking: BridgeOption(
                bool, "Enable the LLM to output thinking", default=True, name="enable-thinking"
            ) = True
    ):
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=config.current_profile['available'][
                        next(iter(config.current_profile['commands'][ctx.command.qualified_name]['options'].values()))
                    ],
                    messages=context_bank[ctx.channel.id],
                    think=enable_thinking
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        thinking_part = None
        if response.message.thinking:
            thinking_part = (
                "-# **Thinking**...\n-# " +
                response.message.thinking.replace(
                    "\n", "\n-# "
                ).replace("\n-# \n", "\n-# ** **\n").rsplit("-# ", 1)[0]
            )
            response_content = thinking_part + "\n" + response.message.content
        elif enable_thinking and not response.message.thinking:
            response_content = (
                    ":warning: **WARNING**: thinking associated with the response is missing\n\n"
                    + response.message.content
            )
        else:
            response_content = response.message.content
        if len(response_content) <= 2000:
            await ctx.respond(f"{response_content}")
        elif len(response_content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Deepseek-R1 Response", f"{response_content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4093 if thinking_part else 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response_content[x:x + max_length] for x in range(0, len(response_content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                part_of_thinking = (
                        thinking_part and index and max_length * index < len(thinking_part)
                )
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Deepseek-R1 Response {index + 1}/{len(response_pages)}",
                        f"-# {response_page}" if part_of_thinking else f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-gemma3',
        description="Ask the gemma 3 llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_gemma3_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to gemma3"),
            image: BridgeOption(
                discord.Attachment, "The image to show the model", required=False
            ) = None
    ):
        """About the bot?"""
        await ctx.defer()
        images = []
        if (ctx.message and len(ctx.message.attachments) > 0) or image:
            image_bytes = await (
                ctx.message.attachments[0] if ctx.message and len(ctx.message.attachments) > 0
                else image
            ).read()
            images.append(image_bytes)
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'images': images,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=config.current_profile['available'][
                        next(iter(config.current_profile['commands'][ctx.command.qualified_name]['options'].values()))
                    ],
                    messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Gemma 3 Response", f"{response.message.content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response.message.content[x:x + max_length] for x in range(0, len(response.message.content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Gemma 3 Response {index + 1}/{len(response_pages)}", f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-llama4',
        description="Ask the llama4 llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_llama4_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to llama4"),
            model: BridgeOption(
                str, "The llama4 model to use",
                default=config.current_profile['commands']['ask-llama4']['default'],
                choices=config.current_profile['commands']['ask-llama4']['options'].keys()
            ) = config.current_profile['commands']['ask-llama4']['default'],
            image: BridgeOption(
                discord.Attachment, "The image to show the model", required=False
            ) = None
    ):
        """About the bot?"""
        await ctx.defer()
        images = []
        if (ctx.message and len(ctx.message.attachments) > 0) or image:
            image_bytes = await (
                ctx.message.attachments[0] if ctx.message and len(ctx.message.attachments) > 0
                else image
            ).read()
            images.append(image_bytes)
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        available_models = [model.model for model in (await self.ollama_client.list()).models]

        if prompt.split()[0].upper() in config.current_profile['commands'][
            ctx.command.qualified_name
        ]['options'].keys():
            model = prompt.split()[0].upper()
        model_id = config.current_profile['available'][
            config.current_profile['commands'][ctx.command.qualified_name]['options'][model]
        ]
        if model_id not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model ``{model}`` is not available. "
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'images': images,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=model_id, messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama 4 Response", f"{response.message.content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response.message.content[x:x + max_length] for x in range(0, len(response.message.content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Llama 4 Response {index + 1}/{len(response_pages)}", f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-qwen3',
        description="Ask the qwen3 llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_qwen3_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to qwen3"),
            model: BridgeOption(
                str, "The qwen3 model to use",
                default=config.current_profile['commands']['ask-qwen3']['default'],
                choices=config.current_profile['commands']['ask-qwen3']['options'].keys()
            ) = config.current_profile['commands']['ask-qwen3']['default'],
            enable_thinking: BridgeOption(
                bool, "Enable the LLM to output thinking", default=True, name="enable-thinking"
            ) = True
    ):
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        available_models = [model.model for model in (await self.ollama_client.list()).models]

        if prompt.split()[0].upper() in config.current_profile['commands'][
            ctx.command.qualified_name
        ]['options'].keys():
            model = prompt.split()[0].upper()
        model_id = config.current_profile['available'][
            config.current_profile['commands'][ctx.command.qualified_name]['options'][model]
        ]
        if model_id not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model ``{model}`` is not available. "
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=model_id,
                    messages=context_bank[ctx.channel.id],
                    think=enable_thinking
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        thinking_part = None
        if response.message.thinking:
            thinking_part = (
                    "-# **Thinking**...\n-# " +
                    response.message.thinking.replace(
                        "\n", "\n-# "
                    ).replace("\n-# \n", "\n-# ** **\n").rsplit("-# ", 1)[0]
            )
            response_content = thinking_part + "\n" + response.message.content
        elif enable_thinking and not response.message.thinking:
            response_content = (
                    ":warning: **WARNING**: thinking associated with the response is missing\n\n"
                    + response.message.content
            )
        else:
            response_content = response.message.content
        if len(response_content) <= 2000:
            await ctx.respond(f"{response_content}")
        elif len(response_content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Qwen 3 Response", f"{response_content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4093 if thinking_part else 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response_content[x:x + max_length] for x in range(0, len(response_content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                part_of_thinking = (
                        thinking_part and index and max_length * index < len(thinking_part)
                )
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Qwen 3 Response {index + 1}/{len(response_pages)}",
                        f"-# {response_page}" if part_of_thinking else f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-magistral',
        description="Ask the magistral llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_magistral_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to magistral"),
            enable_thinking: BridgeOption(
                bool, "Enable the LLM to output thinking", default=True, name="enable-thinking"
            ) = True
    ):
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=config.current_profile['available'][
                        next(iter(
                            config.current_profile['commands'][ctx.command.qualified_name]['options'].values()))
                    ],
                    messages=context_bank[ctx.channel.id],
                    think=enable_thinking
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        thinking_part = None
        if response.message.thinking:
            thinking_part = (
                    "-# **Thinking**...\n-# " +
                    response.message.thinking.replace(
                        "\n", "\n-# "
                    ).replace("\n-# \n", "\n-# ** **\n").rsplit("-# ", 1)[0]
            )
            response_content = thinking_part + "\n" + response.message.content
        elif enable_thinking and not response.message.thinking:
            response_content = (
                    ":warning: **WARNING**: thinking associated with the response is missing\n\n"
                    + response.message.content
            )
        else:
            response_content = response.message.content
        if len(response_content) <= 2000:
            await ctx.respond(f"{response_content}")
        elif len(response_content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Magistral Response", f"{response_content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4093 if thinking_part else 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response_content[x:x + max_length] for x in range(0, len(response_content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                part_of_thinking = (
                        thinking_part and index and max_length * index < len(thinking_part)
                )
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Magistral Response {index + 1}/{len(response_pages)}",
                        f"-# {response_page}" if part_of_thinking else f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-mistral',
        description="Ask the mistral llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_mistral_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to mistral"),
    ):
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=config.current_profile['available'][
                        next(iter(
                            config.current_profile['commands'][ctx.command.qualified_name]['options'].values()))
                    ],
                    messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Mistral Response", f"{response.message.content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response.message.content[x:x + max_length] for x in range(0, len(response.message.content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Mistral Response {index + 1}/{len(response_pages)}", f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-mistral-nemo',
        description="Ask the mistral nemo llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_mistral_nemo_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to mistral nemo"),
    ):
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=config.current_profile['available'][
                        next(iter(
                            config.current_profile['commands'][ctx.command.qualified_name]['options'].values()))
                    ],
                    messages=context_bank[ctx.channel.id]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Mistral NeMo Response", f"{response.message.content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response.message.content[x:x + max_length] for x in range(0, len(response.message.content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"Mistral NeMo Response {index + 1}/{len(response_pages)}", f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-gpt-oss',
        description="Ask the gpt-oss llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_gpt_oss_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to gpt-oss"),
            enable_thinking: BridgeOption(
                bool, "Enable the LLM to output thinking", default=True, name="enable-thinking"
            ) = True
    ):
        await ctx.defer()
        try:
            await self.ollama_client.ps()
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        except httpx.HTTPError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Connecting to Ollama Server.",
                f"There was a problem trying to connect to the ollama server: {error}"
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                message = {
                    'role': 'user',
                    'content': prompt,
                    'system': 'your response will be sent over discord, so please make sure your entire '
                              'response is limited to 4096 characters'
                }
                if ctx.channel.id not in context_bank:
                    context_bank[ctx.channel.id] = []
                context_bank[ctx.channel.id].append(message)
                response = await self.ollama_client.chat(
                    model=config.current_profile['available'][
                        next(iter(
                            config.current_profile['commands'][ctx.command.qualified_name]['options'].values()))
                    ],
                    messages=context_bank[ctx.channel.id],
                    think=enable_thinking
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        context_bank[ctx.channel.id].append({'role': 'assistant', 'content': response.message.content})
        thinking_part = None
        if response.message.thinking:
            thinking_part = (
                    "-# **Thinking**...\n-# " +
                    response.message.thinking.replace(
                        "\n", "\n-# "
                    ).replace("\n-# \n", "\n-# ** **\n").rsplit("-# ", 1)[0]
            )
            response_content = thinking_part + "\n" + response.message.content
        elif enable_thinking and not response.message.thinking:
            response_content = (
                    ":warning: **WARNING**: thinking associated with the response is missing\n\n"
                    + response.message.content
            )
        else:
            response_content = response.message.content
        if len(response_content) <= 2000:
            await ctx.respond(f"{response_content}")
        elif len(response_content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "GPT-OSS Response", f"{response_content}")
            )
        else:
            language_buffer_size = 16
            max_length = 4093 if thinking_part else 4096
            max_length -= language_buffer_size + 8
            embed_pages = []
            response_pages = [
                response_content[x:x + max_length] for x in range(0, len(response_content), max_length)
            ]
            unfinished_codeblock = ""
            unfinished_backtick = False
            for index, response_page in enumerate(response_pages):
                part_of_thinking = (
                        thinking_part and index and max_length * index < len(thinking_part)
                )
                if unfinished_codeblock:
                    response_page = "```" + unfinished_codeblock + '\n' + response_page
                    unfinished_codeblock = ""
                elif unfinished_backtick:
                    response_page = '`' + response_page
                    unfinished_backtick = False
                if response_page.count("```") & 1:
                    unfinished_codeblock = "c"
                    response_page += "```"
                elif response_page.count("`") - 3 * response_page.count("```") & 1:
                    unfinished_backtick = True
                    response_page += "`"
                embed_pages.append(
                    utils.default_embed(
                        ctx, f"GPT-OSS Response {index + 1}/{len(response_pages)}",
                        f"-# {response_page}" if part_of_thinking else f"{response_page}"
                    )
                )
            paginator = pages.Paginator(pages=embed_pages)
            if isinstance(ctx, discord.ApplicationContext):
                await paginator.respond(ctx.interaction)
            else:
                await paginator.send(ctx)

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='clear-context',
        description="Clears the message context from the llms",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def clear_context_cmd(
            self, ctx: bridge.Context,
            scope: BridgeOption(
                str, "The scope of context to clear", default="Current Channel", name="scope",
                choices=["Current Channel", "All"]
            ) = "Current Channel"
    ):
        if scope.lower() == "all":
            owner_check = await ctx.bot.is_owner(ctx.author)
            if not owner_check:
                raise commands.NotOwner()
            await ctx.defer()
            context_bank.clear()
            await ctx.respond("Cleared all session context")
            return
        await ctx.defer()
        if not context_bank.get(ctx.channel.id):
            await ctx.respond("There was no context to clear in this channel")
            return
        context_bank[ctx.channel.id].clear()
        await ctx.respond("Cleared the context for the current channel")


def setup(client):
    client.add_cog(Ollama(client))
