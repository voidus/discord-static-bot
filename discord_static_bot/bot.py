from __future__ import annotations

import re
from asyncio import gather
from typing import TYPE_CHECKING, Iterable, Literal

import discord.utils
from discord import (
    ApplicationCommandError,
    ApplicationContext,
    Bot,
    CategoryChannel,
    CheckFailure,
    Guild,
    Member,
    Message,
    Option,
    TextChannel,
    guild_only,
)

if TYPE_CHECKING:
    from discord.interactions import InteractionChannel

from .config import Config

# TODO
# ----
# - Restrict all calls to server users (if we need that?)
# - Denylist / Allowlist (? does that make sense if we have default-allow? I guess it allows people
#                           from outside the server)
# - Figure out if we can drop the /help or still need it
#
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


class UserVisibleError(Exception):
    pass


# OH THE HORRORS https://github.com/Pycord-Development/pycord/issues/1649
discord.utils._MissingSentinel._get_overridden_method = lambda *args, **kwargs: None  # type: ignore
discord.utils._MissingSentinel.cog_check = lambda *args, **kwargs: True  # type: ignore
discord.utils._MissingSentinel.cog_before_invoke = lambda *args, **kwargs: None  # type: ignore
discord.utils._MissingSentinel.cog_after_invoke = lambda *args, **kwargs: None  # type: ignore
discord.utils._MissingSentinel.cog_command_error = lambda *args, **kwargs: None  # type: ignore


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
            case _:
                await Bot.on_application_command_error(bot, ctx, exception)

    ##########
    # Checks #
    ##########

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

    def in_our_category(ctx: ApplicationContext) -> Literal[True]:
        match ctx.channel:
            case None:
                raise UserVisibleError("Not sent through a channel?!?")
            case object(category_id=config.category_id):
                return True
            case _:
                raise CheckFailure("Only allowed in the private-statics category")

    ###########
    # Helpers #
    ###########

    def our_guild(ctx: ApplicationContext) -> Guild:
        match ctx.guild:
            case Guild(id=config.guild_id):
                return ctx.guild
            case _:
                raise CheckFailure("These commands are only allowed on the server")

    def our_category(ctx: ApplicationContext, guild: Guild) -> CategoryChannel:
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

    def get_guild_member(guild: Guild, name: str) -> Member:
        member = guild.get_member_named(name)
        if member is None:
            raise CheckFailure("That member doesn't exist. Are they on the server?")
        if any(r.id == config.bots_role_id for r in member.roles):
            raise CheckFailure("Not operating on bots")
        return member

    def channel_members(channel: TextChannel) -> Iterable[Member]:
        match channel:
            case TextChannel():
                return (m for m in channel.members if not m.bot)
            case _:
                raise UserVisibleError(f"Cannot get members of {type(channel)}")

    def ensure_text_channel(channel: InteractionChannel | None) -> TextChannel:
        if channel is None:
            raise UserVisibleError("No channel?!?")
        if not isinstance(channel, TextChannel):
            raise CheckFailure("Only works in text channels in the static category")
        return channel

    def get_static_channel(category, name) -> TextChannel | None:
        assert name.startswith("static-")
        try:
            [channel] = [channel.name == name for channel in category.channels]
            return channel
        except ValueError:
            return None

    async def creator(channel: TextChannel) -> Member:
        try:
            [first_message] = await channel.history(
                limit=1, oldest_first=True
            ).flatten()
            [creator, *_] = first_message.mentions
        except ValueError:
            raise CheckFailure(f"Failed to determine creator of {channel.name}")
        if not isinstance(creator, Member):
            raise UserVisibleError(
                f"Expected creator to be a Member, but it's actually a {type(creator)}"
            )
        return creator

    def is_admin(member: Member) -> bool:
        return any(r.id == config.admin_role_id for r in member.roles)

    def has_one_channel_role(member: Member) -> bool:
        return any(role.id == config.one_channel_role_id for role in member.roles)

    ############
    # Commands #
    ############

    @bot.slash_command()
    async def ping(ctx: ApplicationContext):
        """Check if bot connection is working"""
        await ctx.respond("pong", ephemeral=True)

    @bot.slash_command()
    async def check_config(ctx: ApplicationContext):
        raise NotImplementedError()

    ###################
    # Static management

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
        category = our_category(ctx, guild)

        # Permission checks
        one_channel_role = (
            guild.get_role(config.one_channel_role_id)
            if config.one_channel_role_id
            else None
        )
        if (
            one_channel_role
            and not is_admin(ctx.author)
            and has_one_channel_role(ctx.author)
        ):
            raise CheckFailure(
                "You cannot create more than one channel. "
                "Ask a co-member to create it or an @admin to remove the restriction for you"
            )

        # Parameter checks
        name = clean_static_name(name)
        if get_static_channel(category, name) is not None:
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
    @guild_only()
    async def delete(_cog, ctx: ApplicationContext, name: str):
        guild = our_guild(ctx)
        category = our_category(ctx, guild)
        one_channel_role = (
            guild.get_role(config.one_channel_role_id)
            if config.one_channel_role_id
            else None
        )
        if ctx.author is None:
            raise UserVisibleError("author is None for some reason?!?")

        # Parameter checks
        name = clean_static_name(name)
        channel = get_static_channel(category, name)
        if channel is None:
            raise CheckFailure(f"Couldn't find channel {name}")

        if one_channel_role:
            # Find creator and remove one_channel_role
            await (await creator(channel)).remove_roles(one_channel_role)

        await channel.delete(reason=f"{ctx.author.name} asked to remove it")
        await ctx.respond(f"Group {name} deleted.", ephemeral=True)

    @static.command(
        options=[
            Option(
                name="limit",
                input_type=int,
                description="Delete this many recent messages",
            )
        ],
        checks=[admin, in_our_category],
    )
    @guild_only()
    async def clear(_cog, ctx: ApplicationContext, limit: str):
        """Deletes recent messages from the channel"""
        limit_int = int(limit)
        channel = ensure_text_channel(ctx.channel)

        await channel.purge(limit=limit_int)
        await ctx.respond(f"Deleted {limit_int} messages", ephemeral=True)

    @static.command(name="list", checks=[admin])
    @guild_only()
    async def static_list(_cog, ctx: ApplicationContext):
        """List all statics along with the time that the last messag was sent"""

        async def creator_string(channel: TextChannel):
            try:
                return (await creator(channel)).name
            except CheckFailure as e:
                return f"<Error>"

        async def last_message(channel: TextChannel) -> str:
            last_message = await channel.history(limit=1).flatten()
            try:
                return last_message[0].created_at.date().isoformat()
            except ValueError:
                return "???"

        async def channel_data(channel: TextChannel):
            [c, l] = await gather(creator_string(channel), last_message(channel))
            return {
                "name": channel.name,
                "creator": c,
                "last_message": l,
            }

        guild = our_guild(ctx)
        channels = await gather(
            *[
                channel_data(channel)
                for channel in our_category(ctx, guild).channels
                if isinstance(channel, TextChannel)
                and channel.name.startswith("static-")
            ]
        )

        channels = sorted(channels, key=lambda entry: entry["last_message"])

        await ctx.respond(
            "\n".join(
                [
                    "These are the statics on the server",
                    *[
                        " - ".join(
                            [
                                c["name"],
                                f"Last message on {c['last_message']}",
                                f"Creator: {c['creator']}",
                            ]
                        )
                        for c in channels
                    ],
                    "",
                    (
                        "Be aware that creator information might not be accurate if "
                        "the welcome message has been deleted or modified"
                    ),
                ]
            ),
            ephemeral=True,
        )

    ###################
    # Member management

    member = bot.create_group("member", description="Manage members")

    @member.command(
        options=[
            Option(
                input_type=str,
                name="name",
                description="Discord name (NAME#12345) of the server member to add",
            )
        ],
        checks=[in_our_category],
    )
    @guild_only()
    async def add(_cog, ctx: ApplicationContext, name: str):
        guild = our_guild(ctx)
        channel = ensure_text_channel(ctx.channel)

        member = get_guild_member(guild, name)

        await channel.set_permissions(member, view_channel=True)
        await ctx.respond(f"Folks, say welcome to {member.name}!")

    @member.command(
        options=[
            Option(
                input_type=str,
                name="name",
                description="Discord name (NAME#12345) of the static member to add",
            )
        ],
        checks=[in_our_category],
    )
    @guild_only()
    async def remove(_cog, ctx: ApplicationContext, name: str):
        guild = our_guild(ctx)
        channel = ensure_text_channel(ctx.channel)

        member = get_guild_member(guild, name)
        if not channel.permissions_for(member).view_channel:
            raise CheckFailure("That member is not in the channel")

        await channel.set_permissions(member, overwrite=None)
        await ctx.respond(f"Guys, say goodbye to {member.name}")

    @member.command(name="list")
    @guild_only()
    async def member_list(_cog, ctx: ApplicationContext):
        """List channel members"""
        channel = ensure_text_channel(ctx.channel)
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

    ###############
    # Communication

    @bot.slash_command(
        options=[
            Option(
                input_type=str,
                name="message",
                description="Optional message to send everyone",
                required=False,
            )
        ],
        checks=[in_our_category],
    )
    @guild_only()
    async def mention(ctx: ApplicationContext, message: str):
        """Mention everyone in the channel"""
        channel = ensure_text_channel(ctx.channel)
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

    @bot.message_command(checks=[in_our_category])
    @guild_only()
    async def pin(ctx: ApplicationContext, message: Message):
        """Add the message to the channel pins"""
        await message.pin(reason=f"pinned by {message.author.name}")
        await ctx.respond("pinned it :)")

    @bot.message_command(checks=[in_our_category])
    @guild_only()
    async def unpin(ctx: ApplicationContext, message: Message):
        """Remove the message from the channel pins"""
        await message.unpin()
        await ctx.respond("unpinned it :)")

    return bot
