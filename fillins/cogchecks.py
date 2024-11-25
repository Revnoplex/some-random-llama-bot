import discord
from typing import Callable


def bridge_contexts(*context_types: discord.InteractionContextType) -> Callable | discord.ApplicationCommand:
    """Intended to work with :class:`.ApplicationCommand` and :class:`BridgeCommand`,
    adds the context type for the command.
    """

    def predicate(func: Callable | discord.ApplicationCommand):
        if isinstance(func, discord.ApplicationCommand):
            func.contexts = set(context_types)
        else:
            func.__contexts__ = set(context_types)
        if list(context_types) == [discord.InteractionContextType.guild]:
            from discord.ext.commands import guild_only

            return guild_only()(func)
        elif discord.InteractionContextType.guild not in context_types:
            from discord.ext.commands import dm_only

            return dm_only()(func)
        else:
            return func

    return predicate
