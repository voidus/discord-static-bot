from __future__ import annotations
from asyncio import gather
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
    Guild,
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
# - /last_message (DM + admin)
# - /add (in category)
# - /remove (in category)
# - /clear (In category)
#
# Open questions
# --------------
# - Can we restrict permissions so that commands don't show up where not allowed? discord api
# supports that but the python library is confusing me a bit.
#
# Future work
# -----------
# - Remove the hack below once https://github.com/Pycord-Development/pycord/issues/1649 is fixed
# - Autocomplete once https://github.com/Pycord-Development/pycord/issues/1630 is released

# OH THE HORRORS https://github.com/Pycord-Development/pycord/issues/1649
import discord.utils

discord.utils._MissingSentinel._get_overridden_method = lambda *args, **kwargs: None  # type: ignore
discord.utils._MissingSentinel.cog_check = lambda *args, **kwargs: True  # type: ignore
discord.utils._MissingSentinel.cog_before_invoke = lambda *args, **kwargs: None  # type: ignore
discord.utils._MissingSentinel.cog_after_invoke = lambda *args, **kwargs: None  # type: ignore
discord.utils._MissingSentinel.cog_command_error = lambda *args, **kwargs: None  # type: ignore


class UserVisibleError(Exception):
    pass


static_name_re = re.compile("[a-z][a-z0-9-]*")
static_name_re_description = "It must only contain lowercase letters, numbers and the character '-' and start with a letter."


def clean_static_name(name: str) -> str:
    if not static_name_re.fullmatch(name):
        raise CheckFailure(
            f"Cannot accept that static name. {static_name_re_description}"
        )
    if name.startswith("static"):
        raise CheckFailure(
            'Static names should not start with "static", that will be added automatically'
        )
    return f"static-{name}"


def make_bot(config: Config) -> Bot:
    bot = Bot()

    @bot.event
    async def on_application_command_error(ctx: ApplicationContext, exception):
        match exception:
            case CheckFailure(args=[message]):
                await ctx.respond(f"Sorry: {message}", ephemeral=True)
            case ApplicationCommandError(original=original):
                match original:
                    case UserVisibleError(args=[message]):
                        await ctx.respond(f"Error: {message}", ephemeral=True)
                    case NotImplementedError():
                        await ctx.respond(
                            f"Sorry, that feature isn't implemented yet. We're working on it!"
                        )
            case _:
                await Bot.on_application_command_error(bot, ctx, exception)

    ########
    # Checks

    def admin(ctx: ApplicationContext) -> Literal[True]:
        match ctx.author:
            case Member(roles=roles):
                if any(role.id == config.admin_role_id for role in roles):
                    return True
                else:
                    raise CheckFailure("That command is for admins only.")
            case _:
                raise CheckFailure(
                    "Couldn't determine roles. Maybe you're using the command in a dm? It only works on the server."
                )

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

    def our_guild(ctx: ApplicationContext) -> Guild:
        match ctx.guild:
            case Guild(id=config.guild_id):
                return ctx.guild
            case _:
                raise CheckFailure("These commands are only allowed on the server")

    def our_category(ctx: ApplicationContext) -> CategoryChannel:
        guild = our_guild(ctx)
        try:
            [category] = [
                c for c in our_guild(ctx).categories if c.id == config.category_id
            ]
        except ValueError:
            raise UserVisibleError("Couldn't find the category for statics")

        if not category.permissions_for(guild.me).view_channel:
            raise UserVisibleError(
                "The bot needs explicit view_channel permissions on the statics category"
            )
        return category

    ##########
    # Commands

    static = bot.create_group("static", description="Manage channels for statics")

    @static.command(
        options=[
            Option(
                input_type=str,
                name="name",
                description='Name of the static to create (do not include "static-" at the start)',
            )
        ],
    )
    @guild_only()
    async def create(_cog, ctx: ApplicationContext, name: str):
        """Create a new channel for a private static"""
        # Consistency checks
        guild = our_guild(ctx)
        if not isinstance(ctx.author, Member):
            raise UserVisibleError(
                f"Expected author to be a Member but got {type(ctx.author)}"
            )
        category = our_category(ctx)

        # Permission checks
        admin_role = guild.get_role(config.admin_role_id)
        if admin_role is None:
            raise UserVisibleError("admin role not found")

        one_channel_role = (
            guild.get_role(config.one_channel_role_id)
            if config.one_channel_role_id
            else None
        )
        if (
            one_channel_role
            and not any(r.id == config.admin_role_id for r in ctx.author.roles)
            and any(role.id == config.one_channel_role_id for role in ctx.author.roles)
        ):
            raise CheckFailure(
                "You cannot create more than one channel. "
                "Ask a co-member to create it or an @admin to remove the restriction for you"
            )

        # Parameter checks
        name = clean_static_name(name)

        # Collision checks
        if any(channel.name == name for channel in guild.channels):
            raise CheckFailure(
                "Static with that name already exists, please pick another one"
            )

        # Let's do it
        if one_channel_role:
            await ctx.author.add_roles(one_channel_role)

        channel = await guild.create_text_channel(
            name=name,
            reason=f"{ctx.author.name} requested the channel",
            category=category,
        )
        await channel.set_permissions(
            ctx.author, view_channel=True, reason="created the static"
        )

        gather(
            ctx.respond("Group created, take a look in the server!", ephemeral=True),
            channel.send(f"Welcome to your new group {ctx.author.mention}"),
        )

    @static.command(
        options=[
            Option(
                input_type=str,
                name="name",
                description='Name of the static to delete (do not include "static-" at the start)',
            )
        ],
        checks=[admin],
    )
    async def delete(_cog, ctx: ApplicationContext, name: str):
        guild = our_guild(ctx)
        category = our_category(ctx)
        one_channel_role = (
            guild.get_role(config.one_channel_role_id)
            if config.one_channel_role_id
            else None
        )
        if ctx.author is None:
            raise UserVisibleError("author is None for some reason?!?")

        # Parameter checks
        name = clean_static_name(name)
        try:
            [channel] = [c for c in category.channels if c.name == name]
        except ValueError:
            raise CheckFailure(f"Couldn't find channel {name}")
        if not isinstance(channel, TextChannel):
            raise CheckFailure(f"{name} is not a text channel")

        if one_channel_role:
            # Find creator and remove one_channel_role
            try:
                [first_message] = await channel.history(
                    limit=1, oldest_first=True
                ).flatten()
                [creator, *_] = first_message.mentions
            except ValueError:
                raise CheckFailure(f"Failed to determine owner of {name}")
            if not isinstance(creator, Member):
                raise UserVisibleError(
                    f"Expected creator to be a Member, but it's actually a {type(creator)}"
                )
            await creator.remove_roles(one_channel_role)

        await channel.delete(reason=f"{ctx.author.name} asked to remove it")
        await ctx.respond(f"Group {name} deleted.", ephemeral=True)

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
