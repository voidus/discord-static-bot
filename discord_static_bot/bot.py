from __future__ import annotations
import dataclasses

import re
from asyncio import gather
import sys
import traceback
from typing import TYPE_CHECKING, Iterable, Literal
from discord.errors import NotFound

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
    User,
    guild_only,
)

if TYPE_CHECKING:
    from discord.interactions import InteractionChannel

from .config import Config

# TODO
# ----
# - Restrict all calls to server users (if we need that?)
# - Figure out if we can drop the /help or still need it
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
# - Audit log


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
                # copied from Bot.on_application_command_error since that has special logic which
                # makes it do nothing if we also want to handle our specific errors

                command = ctx.command
                if command and command.has_error_handler():
                    return

                cog = ctx.cog
                if cog and cog.has_error_handler():
                    return

                print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
                traceback.print_exception(
                    type(exception), exception, exception.__traceback__, file=sys.stderr
                )

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
            [channel] = [
                channel for channel in category.channels if channel.name == name
            ]
            return channel
        except ValueError:
            return None

    async def creator(channel: TextChannel) -> User | Member:
        try:
            [first_message] = await channel.history(
                limit=1, oldest_first=True
            ).flatten()
            [creator, *_] = first_message.mentions
        except ValueError:
            raise CheckFailure(f"Failed to determine creator of {channel.name}")

        if isinstance(creator, User):
            return await channel.guild.fetch_member(42)
        else:
            return creator

    def is_admin(member: Member) -> bool:
        return any(r.id == config.admin_role_id for r in member.roles)

    def has_one_channel_role(member: Member) -> bool:
        return any(role.id == config.one_channel_role_id for role in member.roles)

    def as_member(member: User | Member | None) -> Member:
        if not isinstance(member, Member):
            raise CheckFailure("The bot only works on a server")
        return member

    ########################
    # Common functionality #
    ########################

    if config.blacklist_role_id is not None:

        @bot.check
        def denylist(ctx: ApplicationContext) -> Literal[True]:
            assert config.blacklist_role_id is not None
            if as_member(ctx.author).get_role(config.blacklist_role_id):
                raise CheckFailure("You are forbidden from using this bot.")
            return True

    if config.whitelist_role_id is not None:

        @bot.check
        def allowlist(ctx: ApplicationContext) -> Literal[True]:
            assert config.whitelist_role_id is not None
            if as_member(ctx.author).get_role(config.whitelist_role_id):
                raise CheckFailure("You are not allowed to using this bot.")
            return True

    ############
    # Commands #
    ############

    @bot.slash_command()
    async def ping(ctx: ApplicationContext):
        """Check if bot connection is working"""
        await ctx.respond("pong", ephemeral=True)

    @bot.slash_command(checks=[admin])
    async def check_config(ctx: ApplicationContext):
        """Admin only: Verify that the bot is configured correctly"""
        good, bad, unkn = ":white_check_mark:", ":exclamation:", ":grey_question:"
        checked = {"token"}  # We wouldn't be here if that doesn't work

        lines: list[str] = []
        mk_line = lambda icon, key, msg: " ".join(
            [icon, *([key] if key else []), *([f": {msg}"] if msg else [])]
        )
        add_line = lambda *a: lines.append(mk_line(*a))

        if not isinstance(ctx.me, Member):
            raise UserVisibleError(
                "The bot is not a member. Are you using the command on the server?"
            )

        if not config.guild_id:
            add_line(bad, "GUILD_ID", "Missing")
        else:
            checked.add("guild_id")
            ctx.guild
            if ctx.guild is None or ctx.guild.id != config.guild_id:
                add_line(unkn, "GUILD_ID", "Configured, but we're not on the server")
            else:
                if not config.category_id:
                    add_line(bad, "CATEGORY_ID", "Not configured")
                elif not (category := our_category(ctx, ctx.guild)):
                    add_line(bad, "CATEGORY_ID", "Static category not found")
                else:
                    for perm in ["view_channel", "manage_channels"]:
                        if not getattr(category.permissions_for(ctx.me), perm):
                            add_line(
                                bad,
                                "CATEGORY_ID",
                                f'Bot needs "{perm}" permissions on the category',
                            )
                checked.add("category_id")

                for key in ["ADMIN_ROLE_ID", "BOTS_ROLE_ID"]:
                    id = getattr(config, key.lower())
                    if not id:
                        add_line(bad, key, "Not configured")
                    elif not ctx.guild.get_role(id):
                        add_line(bad, key, "Role not found")
                    checked.add(key.lower())

                for key in [
                    "BLACKLIST_ROLE_ID",
                    "WHITELIST_ROLE_ID",
                    "ONE_CHANNEL_ROLE_ID",
                ]:
                    id = getattr(config, key.lower())
                    if id and not ctx.guild.get_role(id):
                        add_line(bad, key, "Role not found")
                    checked.add(key.lower())

                for perm in ["manage_channels", "manage_roles", "manage_messages"]:
                    if not getattr(ctx.me.guild_permissions, perm):
                        add_line(bad, None, f'Bot needs "{perm}" permission')

        unchecked = set(dataclasses.asdict(config).keys()) - checked

        await ctx.respond(
            "\n".join(
                [
                    "Checking bot config:",
                    *(lines if lines else [":smiling_face_with_3_hearts: All good"]),
                    *(
                        ["\nUnchecked values: {', '.join(unchecked)}"]
                        if unchecked
                        else []
                    ),
                ]
            ),
            ephemeral=True,
        )

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
        """Admin only: Delete a static channel"""
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
            the_creator = await creator(channel)
            try:
                if isinstance(the_creator, User):
                    the_creator = await guild.fetch_member(the_creator.id)
                await the_creator.remove_roles(one_channel_role)
            except NotFound:
                await ctx.respond(
                    f"({the_creator.name} doesn't seem to be on the server anymore)"
                )

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
        """Admin only: Delete recent messages from the channel"""
        limit_int = int(limit)
        channel = ensure_text_channel(ctx.channel)

        await channel.purge(limit=limit_int)
        await ctx.respond(f"Deleted {limit_int} messages", ephemeral=True)

    @static.command(name="list", checks=[admin])
    @guild_only()
    async def static_list(_cog, ctx: ApplicationContext):
        """Admin only: List all statics along with the time that the last messag was sent"""

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
        """Add a new member to this static"""
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
        """Remove a member from this static"""
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
        """List static members"""
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
