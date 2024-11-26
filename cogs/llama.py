import httpx
from ollama import Client
from discord.ext import commands, bridge
from discord.ext.bridge import BridgeOption
import config
import utils


class Llama(config.RevnobotCog):

    def __init__(self, client: bridge.Bot):
        self.client = client
        self.description = "Commands to interact with the llama llm"
        self.icon = "\U0001f999"
        self.hidden = False
        self.ollama_client = Client(
            host='http://192.168.100.41:11434',
        )

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='ask-llama',
        description="Ask the llama llm",
    )
    @commands.bot_has_permissions(send_messages=True)
    @commands.cooldown(**config.default_cooldown_options)
    async def ask_llama_cmd(
            self, ctx: bridge.Context, *, prompt: BridgeOption(str, "Prompt to send to llama"),
            model: BridgeOption(
                str, "The llama model to use. See /ollama-list for available models",
                default="llama3.2:latest"
            ) = "llama3.2"
    ):
        """About the bot?"""
        await ctx.defer()
        try:
            self.ollama_client.ps()
        except httpx.ConnectError:
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        available_models = [model.model for model in self.ollama_client.list().models]
        if prompt.split()[0] in available_models:
            model = prompt.split()[0]
        if model not in available_models:
            await ctx.respond(embed=utils.default_embed(
                ctx, "Model Not Found",
                f"The model {model} is not available. See {ctx.bot.get_command('list-models').id} for available models."
            ))
            return
        response = await ctx.bot.loop.run_in_executor(None, lambda: self.ollama_client.chat(model=model, messages=[
            {
                'role': 'user',
                'content': prompt,
            },
        ]))
        if len(response.message.content) <= 2000:
            await ctx.respond(f"{response.message.content}")
        elif len(response.message.content) <= 4096:
            await ctx.respond(
                embed=utils.default_embed(ctx, "Llama Response", f"{response.message.content}")
            )
        else:
            print(response.message.content)
            await ctx.respond(
                embed=utils.default_embed(
                    ctx, "Response Too large",
                    f"Llama sent a response longer that the maximum amount of characters allowed on discord (4096)"
                )
            )
            await ctx.respond(f"Response too large")

    # noinspection SpellCheckingInspection,PyTypeHints
    @bridge.bridge_command(
        name='list-models',
        description="List available llama models",
    )
    @commands.bot_has_permissions(send_messages=True)
    @commands.cooldown(**config.default_cooldown_options)
    async def list_models_cmd(self, ctx: bridge.Context,):
        try:
            self.ollama_client.ps()
        except httpx.ConnectError:
            app = await ctx.bot.application_info()
            await ctx.respond(embed=utils.default_embed(
                ctx, "Cannot Connect to Ollama Server.",
                "Unable to connect to ollama server as it is probably not running. "
                f"Please ask {app.owner.mention} to start the ollama server."
            ))
            return
        await ctx.respond("\n".join([model.model for model in self.ollama_client.list().models]))


def setup(client):
    client.add_cog(Llama(client))