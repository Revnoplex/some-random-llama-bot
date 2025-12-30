import config
from discord.ext import bridge


class Processes(config.RevnobotCog):
    def __init__(self, client: bridge.Bot):
        self.client = client
        self.servers = 0
        self.description = "The module containing processes that run in the background"
        self.icon = "\U0001F5A5"
        self.hidden = True


def setup(client):
    client.add_cog(Processes(client))
