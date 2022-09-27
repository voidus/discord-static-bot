from __future__ import annotations
import re

from typing import Iterable, Literal, Union
from discord.abc import Messageable
from discord import (
    ApplicationCommandError,
    ApplicationContext,
    Bot,
    CategoryChannel,
    CheckFailure,
    ForumChannel,
    Member,
    Message,
    Option,
    PartialMessageable,
    StageChannel,
    TextChannel,
    Thread,
    VoiceChannel,
    guild_only,
)

from .config import Config

# TODO
# ----
# - Restrict all calls to server users (if we need that?)
# - Denylist / Allowlist (? does that make sense if we have default-allow? I guess it allows people
#                           from outside the server)
# - Figure out if we can drop the /help or still need it
#
# --
#
# Commands:
# - /create (in DM)
# - /delete (DM + admin)
# - /last_message (DM + admin)
# - /add (in category)
# - /remove (in category)
# - /clear (In category)
#
# Open questions
# --------------
# - Is one_channel_role_id used? seems like it prevents channel creation completely.


class UserVisibleError(Exception):
    pass


def make_bot(config: Config) -> Bot:
    bot = Bot()

    @bot.event
    async def on_application_command_error(ctx: ApplicationContext, exception):
        match exception:
            case CheckFailure(args=[message]):
                await ctx.respond(f"Sorry: {message}", ephemeral=True)
            case ApplicationCommandError(original=UserVisibleError(args=[message])):
                await ctx.respond(f"Error: {message}", ephemeral=True)
            case _:
                await Bot.on_application_command_error(bot, ctx, exception)

    ########
    # Checks

    def in_static_category(ctx: ApplicationContext) -> Literal[True]:
        match ctx.channel:
            case None:
                raise UserVisibleError("Not sent through a channel?!?")
            case object(category=config.category_id):
                return True
            case _:
                raise CheckFailure("Only allowed in the private-statics category")

    #########
    # Helpers

    ##########
    # Commands

    static = bot.slash_group("static", description="Manage channels for statics")

    static_name_re = re.compile("[a-z][a-z0-9-]*")
    static_name_re_description = "It must only contain lowercase letters, numbers and the character '-' and start with a letter."

    @static.slash_command(
        options=[
            Option(
                input_type=str,
                name="name",
                description='Name of the static (do not include "static-" at the start)',
            )
        ]
    )
    @guild_only()
    async def create(ctx: ApplicationContext, name: str):
        """Create a new channel for a private static"""
        if not ctx.guild:
            raise CheckFailure(f"Can only create channels in a guild")
        if not static_name_re.fullmatch(name):
            raise CheckFailure(
                f"Cannot accept that static name. {static_name_re_description}"
            )
        if name.startswith("static"):
            raise CheckFailure(
                'Static names should not start with "static", that will be added automatically'
            )

        name = f"static-{name}"

        if any(channel for channel in ctx.guild.channels):
            pass

    @bot.slash_command()
    async def ping(ctx: ApplicationContext):
        """Check if bot connection is working"""
        await ctx.respond("pong", ephemeral=True)

    @bot.slash_command()
    @guild_only()
    async def members(ctx: ApplicationContext):
        """List channel members"""
        channel = ctx.channel
        if channel is None:
            raise UserVisibleError("No channel ?!?")

        if not isinstance(channel, Messageable):
            raise UserVisibleError(
                f"Cannot send message to channel type {type(channel)}"
            )

        members = channel_members(channel)

        await ctx.respond(
            "\n".join(
                (
                    "The members of this channel are:",
                    *sorted(f"- {member.nick or member.name}" for member in members),
                )
            ),
            ephemeral=True,
        )

    @bot.slash_command(
        options=[
            Option(
                input_type=str,
                name="message",
                description="Optional message to send everyone",
                required=False,
            )
        ],
        checks=[in_static_category],
        guild_ids=[1023747544637001800],
    )
    @guild_only()
    async def mention(ctx: ApplicationContext, message: str):
        """Mention everyone in the channel"""
        channel = ctx.channel
        if channel is None:
            raise UserVisibleError("No channel?!?")

        if not isinstance(channel, Messageable):
            raise UserVisibleError(
                f"Cannot send message to channel type {type(channel)}"
            )

        members = channel_members(channel)
        await ctx.respond(
            "\n".join(
                (
                    message or "Hey guys!",
                    " ".join(member.mention for member in members),
                )
            )
        )

    ######
    # Pins

    @bot.message_command()
    @guild_only()
    async def pin(ctx: ApplicationContext, message: Message):
        """Add the message to the channel pins"""
        await message.pin(reason=f"pinned by {message.author.name}")
        await ctx.respond("pinned it :)")

    @bot.message_command()
    @guild_only()
    async def unpin(ctx: ApplicationContext, message: Message):
        """Remove the message from the channel pins"""
        await message.unpin()
        await ctx.respond("unpinned it :)")

    return bot


def channel_members(
    channel: Union[
        VoiceChannel,
        StageChannel,
        TextChannel,
        ForumChannel,
        CategoryChannel,
        Thread,
        PartialMessageable,
    ]
) -> Iterable[Member]:
    match channel:
        case PartialMessageable() | CategoryChannel():
            raise UserVisibleError(f"Cannot get members of {type(channel)}")
        case Thread():
            parent = channel.parent
            if parent is None:
                raise UserVisibleError("thread without parent?!?")
            return (m for m in parent.members if not m.bot)
        case _:
            return (m for m in channel.members if not m.bot)
