import config
from discord.ext import bridge, commands
from typing import Union


class Debug(config.RevnobotCog):
    def __init__(self, client):
        self.client: bridge.Bot = client
        self.description = "The Debug Module of the bot"
        self.icon = "\U0001F6E0"
        self.hidden = True

    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type: str):
        print(f"Debug: Received Event: {event_type}")

    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg: str):
        print(f"Debug: Received: {msg}")

    @commands.Cog.listener()
    async def on_socket_raw_send(self, msg: Union[str, bytes]):
        try:
            print(f"Debug: Sent: {msg if isinstance(msg, str) else msg.decode('utf-8')}")
        except UnicodeDecodeError:
            print(f"Debug: Sent: {str(msg)}")


def setup(client):
    client.add_cog(Debug(client))
