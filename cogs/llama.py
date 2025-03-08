from contextlib import nullcontext
import discord
import httpx
import ollama
from discord.ext import commands, bridge
from discord.ext.bridge import BridgeOption
import config
import utils


class Ollama(config.RevnobotCog):

    def __init__(self, client: bridge.Bot):
        self.client = client
        self.description = "Commands to interact with ollama LLMs"
        self.icon = "\U0001f999"
        self.hidden = False
        self.ollama_client = ollama.AsyncClient(config.ollama_server)

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
                default="3B", choices=["1B", "3B"]
            ) = "3B",
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
        if prompt.split()[0].upper() in ['1B', '3B']:
            model = prompt.split()[0].upper()
        model_id = {"1B": "llama3.2:1b-instruct-fp16", "3B": "llama3.2:3b-instruct-fp16"}[model]
        if model_id not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model ``{model}`` is not available. "
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                response = await self.ollama_client.chat(
                    model=model_id, messages=[
                        {
                            'role': 'user',
                            'content': prompt,
                            'system': 'your response will be sent over discord, so please make sure your entire '
                                      'response is limited to 4096 characters'
                        },
                    ]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama Response", f"{response.message.content}")
            )
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Response Too large",
                    f"Llama sent a response longer that the maximum amount of characters allowed on discord (4096). "
                    f"Please tell llama to limit the response to 4096 characters."
                )
            )

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
                default="11B", choices=["11B", "90B"]
            ) = "11B",
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

        if prompt.split()[0].upper() in ['11B', '90B']:
            model = prompt.split()[0].upper()
        model_id = {"11B": "llama3.2-vision:11b-instruct-fp16", "90B": "llama3.2-vision:90b"}[model]
        if model_id not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model ``{model}`` is not available. "
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                response = await self.ollama_client.chat(
                    model=model_id, messages=[
                        {
                            'role': 'user',
                            'content': prompt,
                            'images': images,
                            'system': 'your response will be sent over discord, so please make sure your entire '
                                      'response is limited to 4096 characters'
                        },
                    ]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama Response", f"{response.message.content}")
            )
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Response Too large",
                    f"Llama sent a response longer that the maximum amount of characters allowed on discord (4096). "
                    f"Please tell llama to limit the response to 4096 characters."
                )
            )

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
                default="3B", choices=["1B", "3B"]
            ) = "3B",
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
        if prompt.split()[0].upper() in ['1B', '3B']:
            model = prompt.split()[0].upper()
        model_id = {"1B": "llama3.2:1b-text-fp16", "3B": "llama3.2:3b-text-fp16"}[model]
        if model_id not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model ``{model}`` is not available. "
            ))
            return
        try:
            async with ctx.typing() if not isinstance(ctx, discord.ApplicationContext) else nullcontext():
                response = await self.ollama_client.chat(
                    model=model_id, messages=[
                        {
                            'role': 'user',
                            'content': prompt,
                            'system': 'your response will be sent over discord, so please make sure your entire '
                                      'response is limited to 4096 characters'
                        },
                    ]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama Response", f"{response.message.content}")
            )
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Response Too large",
                    f"Llama sent a response longer that the maximum amount of characters allowed on discord (4096). "
                    f"Please tell llama to limit the response to 4096 characters."
                )
            )

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
                response = await self.ollama_client.chat(
                    model="llama3.3:70b-instruct-q8_0", messages=[
                        {
                            'role': 'user',
                            'content': prompt,
                            'system': 'your response will be sent over discord, so please make sure your entire '
                                      'response is limited to 4096 characters'
                        },
                    ]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama 3.3 Response", f"{response.message.content}")
            )
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Response Too large",
                    f"Llama sent a response longer that the maximum amount of characters allowed on discord (4096). "
                    f"Please tell llama to limit the response to 4096 characters."
                )
            )

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
                response = await self.ollama_client.chat(
                    model="qwq:32b-fp16", messages=[
                        {
                            'role': 'user',
                            'content': prompt,
                            'system': 'your response will be sent over discord, so please make sure your entire '
                                      'response is limited to 4096 characters'
                        },
                    ]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        if show_thinking:
            response_content = (
                response.message.content.split("\n</think>")[0].replace(
                    "\n", "\n> "
                ).replace(
                    "<think>", "> ### Thinking"
                ) + "\n\n" +
                response.message.content.split("</think>\n\n")[-1]
            )
        else:
            response_content = response.message.content.split("</think>\n\n")[-1]
        if len(response_content) <= 2000:
            await ctx.respond(f"{response_content}")
        elif len(response_content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "QwQ Response", f"{response_content}")
            )
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Response Too large",
                    f"QwQ sent a response longer that the maximum amount of characters allowed on discord (4096). "
                    f"Please tell qwq to limit the response to 4096 characters."
                )
            )

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-deekseek',
        description="Ask the deekseek-r1 llm",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install}
    )
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_deekseek_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to deekseek"),
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
                response = await self.ollama_client.chat(
                    model="deepseek-r1:32b-qwen-distill-fp16", messages=[
                        {
                            'role': 'user',
                            'content': prompt,
                            'system': 'your response will be sent over discord, so please make sure your entire '
                                      'response is limited to 4096 characters'
                        },
                    ]
                )
        except ollama.ResponseError as error:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Error Genrating Response",
                f"{error.error}"
            ))
            return
        if show_thinking:
            response_content = (
                response.message.content.split("\n</think>")[0].replace(
                    "\n", "\n> "
                ).replace(
                    "<think>", "> ### Thinking"
                ) + "\n\n" +
                response.message.content.split("</think>\n\n")[-1]
            )
        else:
            response_content = response.message.content.split("</think>\n\n")[-1]
        if len(response_content) <= 2000:
            await ctx.respond(f"{response_content}")
        elif len(response_content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Deekseek-R1 Response", f"{response_content}")
            )
        else:
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Response Too large",
                    f"Deekseek-R1 sent a response longer that the maximum amount of characters allowed on "
                    f"discord (4096). Please tell deepseek to limit the response to 4096 characters."
                )
            )


def setup(client):
    client.add_cog(Ollama(client))
