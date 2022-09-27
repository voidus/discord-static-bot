from discord import ApplicationContext, ChannelType, PartialMessageable

from .config import Config

class Checks:
    def __init__(self, config: Config):
        self._config = config

    def match_server(self, ctx: ApplicationContext) -> bool:
        return ctx.guild_id == self._config.guild_id

    def match_channel_category(self, ctx: ApplicationContext) -> bool:
        return (
            ctx.channel is not None
            and (category_id := getattr(ctx.channel, "category_id"))
            and category_id == self._config.category_id
        )

    def direct_message(self, ctx: ApplicationContext) -> bool:
        return (
            ctx.channel is not None
            and (is_private := getattr(ctx.channel, "is_private"))
            and is_private()
        )
