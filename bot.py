import os
import sys
import json

import discord

# These strings are used by the $help command
DM_HELP = """
Send me a DM with the following command:
`$create` - create a new static group and role (with you inside).
    Example: 
        `$create fridays`

    This will create a new group called static-fridays
    where you will be added. **Don't use whitespaces in the name.**

Remember that there are other commands you can use inside your static groups. 
Use $help there to see an explanation of them.
""".strip()

DM_ADMIN_HELP = """
Send me a DM with the following command:
`$create` - create a new static group and role (with you inside).
    Example: 
        `$create fridays`

    This will create a new group called static-fridays
    where you will be added. **Don't use whitespaces in the name.**

`$delete` - deletes a static group and role.
    Example: 
        `$delete fridays`

    This will delete the group/role static-fridays if it exists.

`$last_message` - lists all static channels in order of the last message date.
    If no message is present in the channel, its date is the date of creation of the channel.

Remember that there are other commands you can use inside your static groups. 
Use $help there to see an explanation of them.
""".strip()

CHANNEL_HELP = """
Send a message with any of these commands inside your static private group.

For commands that ask you for usernames, 
use the discord username (i.e. DiscordLord#9999), 
make sure that every character and number is correct
and that you respect uppercase/lowercase.

`$add` - add members to this group. You can pass multiple people separating them by spaces.
    Example:
        `$add DiscordLord#9999`
        or
        `$add DiscordLord#9999 DiscordLady#1234`

`$remove` - remove members from this group. You can pass multiple people separating them by spaces.
    Example:
        `$remove DiscordLord#9999`
        or
        `$remove DiscordLord#9999 DiscordLady#1234`

`$members` - list all members of this static.

`$mention` - mention (@ ping) all members of this static.

`$pin` - pin the last message or the replied message.

    If you reply to the message you want to pin with $pin, it will pin that message.
    If you don't reply to any message but still use $pin, it will pin the previous message.

`$unpin` - unpin the replied message.

    **You must reply to the message you want to unpin** with $unpin for it to work.
""".strip()

# Get bot token
with open("token.txt") as f:
    TOKEN = f.read().replace("\n", "").strip()

# Get configuration variables
conf = sys.argv[1]
with open(conf) as f:
    conf = json.load(f)

for k, v in conf.items():
    globals()[k] = v

# Check that required roles are configured
assert not any(
    idx is None for idx in (GUILD_ID, CATEGORY_ID, ADMIN_ROLE_ID, BLACKLIST_ROLE_ID)
)

# Create client
# The members intent is required for some functionalities
intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    await client.change_presence()
    print("We have logged in as {0.user}".format(client))
    # The bot will receive messages after printing this


@client.event
async def on_message(message):
    try:
        # Ignore non-command messages
        if not message.content.startswith("$"):
            return
        elif "\n" in message.content:
            await error_message(
                message.channel, "Can't use multiline messages when using commands."
            )
            return

        # Ignore own messages
        if message.author == client.user:
            return

        try:
            # Get these variables for later
            guild = client.get_guild(GUILD_ID)
            if guild is None:
                raise ValueError()
            category = guild.get_channel(CATEGORY_ID)
            if category is None:
                raise ValueError()
        except ValueError:
            await error_message(
                message.channel, "Guild/category was not found. Contact an admin."
            )

        member = guild.get_member(message.author.id)
        if member is None:
            await message.channel.send(
                "Discord tells me you're not in the server. If this is not the case, contact an @admin."
            )
            return
        elif has_role(member, BLACKLIST_ROLE_ID):
            await error_message(
                message.channel, "You are blacklisted from using this bot."
            )
            return
        elif WHITELIST_ROLE_ID is not None and not has_role(member, WHITELIST_ROLE_ID):
            await error_message(
                message.channel, "You are not whitelisted to use this bot."
            )
            return

        splits = list(filter(bool, message.content.split(" ")))
        command, args = (splits[0], splits[1:]) if splits else ("", tuple())
        command = command.lower()
        args = [arg.strip() for arg in args if arg.strip()]

        author_id = f"{message.author.name} ({message.author.id})"

        # If private message
        if message.channel.type == discord.ChannelType.private:
            if command == "$hello":
                await message.channel.send("BEEP BOOP")

            elif command == "$create":
                if not args:
                    await error_message(
                        message.channel,
                        "Error: Add the group name after the $create command.",
                    )
                    return
                elif len(args) > 1:
                    await error_message(
                        message.channel,
                        "Error: static name must not contain whitespaces.",
                    )
                    return
                elif not channel_name_legal(args[0]):
                    await error_message(
                        message.channel,
                        "Channel name can only contain lowercase English letters, numbers and dashes.",
                    )
                    return

                if (
                    ONE_CHANNEL_ROLE_ID is not None
                    and not is_admin(member)
                    and has_role(member, ONE_CHANNEL_ROLE_ID)
                ):
                    await error_message(
                        message.channel,
                        "Error: you cannot create more than one channel. "
                        "Ask a co-member to create it or an @admin to remove the restriction for you.",
                    )
                    return

                name = args[0].strip().lower()
                if name.startswith("static"):
                    await error_message(
                        message.channel,
                        (
                            "Your group name should not start with static, as it will be automatically added by the bot.\n"
                            "Example: 'fridays' will become 'static-fridays'."
                        ),
                    )
                    return
                else:
                    name = name.replace("_", "-")
                    name = "static-" + name

                # Check that the group doesn't exist already
                channels = await guild.fetch_channels()
                if any(item.name.lower().strip() == name for item in channels):
                    await error_message(message.channel, "Group name already exists.")
                    return

                channel = await guild.create_text_channel(
                    name=name,
                    category=category,
                    reason=f"{author_id} requested the channel.",
                )

                # After creation, set the view_channel permission.
                # Don't do it in create_channel because it will override the category permissions.
                await channel.set_permissions(member, view_channel=True)

                # Finally, also add the one_channel role to the member
                one_channel_role = (
                    guild.get_role(ONE_CHANNEL_ROLE_ID)
                    if ONE_CHANNEL_ROLE_ID is not None
                    else None
                )
                if one_channel_role is not None:
                    await member.add_roles(one_channel_role)

                await message.channel.send("Group created, take a look in the server!")
                await channel.send(f"Welcome to your new group {member.mention}!")

            elif is_admin(member):
                if command == "$delete":
                    if not args:
                        await error_message(
                            message.channel,
                            "Add the group name after the $delete command.",
                        )
                        return
                    elif len(args) > 1:
                        await error_message(
                            message.channel,
                            "Error: static name must not contain whitespaces.",
                        )
                        return

                    name = args[0].strip().lower()
                    if name.startswith("static"):
                        await error_message(
                            message.channel,
                            (
                                "Your group name should not start with static, as it will be automatically added by the bot.\n"
                                "Example: 'fridays' will become 'static-fridays'."
                            ),
                        )
                        return
                    else:
                        name = name.replace("_", "-")
                        name = "static-" + name

                        if category is None:
                            raise ValueError()
                        channel = await get_channel_named(name)
                        if channel is None:
                            await message.channel.send(f"Group {name} doesn't exist.")
                        elif channel.category.id != CATEGORY_ID:
                            await message.channel.send(
                                f"Group {name} is not a private static."
                            )
                        else:
                            one_channel_role = (
                                guild.get_role(ONE_CHANNEL_ROLE_ID)
                                if ONE_CHANNEL_ROLE_ID is not None
                                else None
                            )
                            if one_channel_role:
                                # Get the first message, where the creator is mentioned
                                messages = await channel.history(
                                    limit=1, oldest_first=True
                                ).flatten()
                                if not messages:
                                    await message.channel.send(
                                        "Error: Channel creator not defined."
                                    )
                                    return
                                else:
                                    (m,) = messages
                                    if not m.mentions:
                                        await message.channel.send(
                                            "Error: Channel creator not defined."
                                        )
                                    else:
                                        creator = m.mentions[0]
                                        await creator.remove_roles(one_channel_role)

                            await channel.delete(
                                reason=f"{author_id} asked to delete it."
                            )
                            await message.channel.send(f"Group {name} deleted.")

                elif command == "$last_message":
                    l = []
                    for channel in category.channels:
                        if isinstance(channel, discord.TextChannel):
                            messages = await channel.history(limit=1).flatten()
                            created_at = (
                                messages[0].created_at
                                if messages
                                else channel.created_at
                            )

                            l.append((channel.name, created_at))

                    l = sorted(l, key=lambda pair: pair[1])
                    await message.channel.send(
                        "\n".join(" - ".join(map(str, pair)) for pair in l)
                    )

                elif command == "$help":
                    await message.channel.send(DM_ADMIN_HELP)

            elif command == "$help":
                await message.channel.send(DM_HELP)

        # If group message (in CATEGORY_ID)
        elif (
            message.guild.id == GUILD_ID and message.channel.category.id == CATEGORY_ID
        ):

            if not message.content.startswith("$"):
                return  # ignore

            assert command.startswith("$")
            if command == "$hello":
                message.channel.send("BEEP BOOP")

            elif command == "$members":
                await message.channel.send(
                    "The members of this channel are: \n"
                    + "\n".join(
                        member.nick if member.nick else member.name
                        for member in get_static_members(message.channel)
                    )
                )

            elif command == "$mention":
                await message.channel.send(
                    "Hey guys! "
                    + " ".join(
                        member.mention for member in get_static_members(message.channel)
                    )
                )

            elif command == "$add":
                try:
                    guild = client.get_guild(GUILD_ID)
                    if guild is None:
                        raise ValueError()

                    members = get_static_members(message.channel)

                    # args are all members to add
                    added_members = []
                    members_set = set()
                    errors = []
                    for member_name in args:
                        member = guild.get_member_named(member_name)

                        if member is None:
                            errors.append(member_name)
                        elif member.id not in members_set and member not in members:
                            await message.channel.set_permissions(
                                member, view_channel=True
                            )

                            added_members.append(member.mention)
                            members_set.add(member.id)

                    errors = set(errors)
                    if errors:
                        await error_message(
                            message.channel,
                            f"User{'s' if len(errors) > 1 else ''} {', '.join(errors)} "
                            "could not be found. Make sure to use the NAME#XXXX format (i.e., DiscordLord#9999).",
                        )

                    if added_members:
                        s = "Guys, say welcome to "
                        if len(added_members) == 1:
                            s += added_members[0]
                        else:
                            s += (
                                ", ".join(added_members[:-1])
                                + " and "
                                + added_members[-1]
                            )
                        s += "!"
                        await message.channel.send(s)
                    else:
                        await message.channel.send("ERROR: No members to add!")

                except ValueError:
                    await error_message(
                        message.channel, "Add member failed. Contact an admin."
                    )
                    return

            elif command == "$remove":
                try:
                    guild = client.get_guild(GUILD_ID)
                    if guild is None:
                        raise ValueError()

                    members = get_static_members(message.channel)

                    # args are all members to add
                    removed_members = []
                    members_set = set()
                    errors = []
                    for member_name in args:
                        member = guild.get_member_named(member_name)

                        if member is None:
                            errors.append(member_name)
                        elif member.id not in members_set and member in members:
                            await message.channel.set_permissions(
                                member, overwrite=None
                            )
                            removed_members.append(member.mention)
                            members_set.add(member.id)

                    errors = set(errors)
                    if errors:
                        await error_message(
                            message.channel,
                            f"User{'s' if len(errors) > 1 else ''} {', '.join(errors)} "
                            "could not be found. Make sure to use the NAME#XXXX format (i.e., DiscordLord#9999).",
                        )

                    if removed_members:
                        s = "Guys, say goodbye to "
                        if len(removed_members) == 1:
                            s += removed_members[0]
                        else:
                            s += (
                                ", ".join(removed_members[:-1])
                                + " and "
                                + removed_members[-1]
                            )
                        s += "!"
                        await message.channel.send(s)
                    else:
                        await message.channel.send("ERROR: No members to remove!")

                except ValueError:
                    await error_message(
                        message.channel, "Add member failed. Contact an admin."
                    )
                    return

            elif command == "$pin":
                if message.reference is None:
                    prev_message = await get_previous_message(message)
                    if prev_message is None:
                        reference_id = None
                    else:
                        reference_id = prev_message.id
                else:
                    reference_id = message.reference.message_id

                if reference_id is None:
                    await error_message(message.channel, "No messages to pin yet.")
                else:
                    try:
                        reference = await message.channel.fetch_message(reference_id)
                        if not reference.pinned:
                            await reference.pin(
                                reason=f"{author_id} requested the pin."
                            )
                        else:
                            await error_message(
                                message.channel,
                                "The specified message is already pinned.",
                            )
                    except discord.NotFound:
                        await error_message(
                            message.channel, "The specified message was not found."
                        )

            elif command == "$unpin":
                if message.reference is None:
                    await error_message(
                        message.channel,
                        "You need to reply to the message you want to $unpin.",
                    )
                else:
                    try:
                        reference = await message.channel.fetch_message(
                            message.reference.message_id
                        )
                        if reference.pinned:
                            await reference.unpin(
                                reason=f"{author_id} requested the unpin."
                            )
                            await message.channel.send(
                                "Unpinned message.", reference=reference
                            )
                        else:
                            await error_message(
                                message.channel, "The specified message is not pinned."
                            )
                    except discord.NotFound:
                        await error_message(
                            message.channel, "The specified message was not found."
                        )

            elif command == "$clear" and is_admin(member):
                limit = args[0] if args else "100"

                try:
                    limit = int(limit) + 1  # + 1 to include the $clear message
                except ValueError:
                    await error_message(message.channel, "Unrecognized limit number.")

                await message.channel.purge(limit=limit)

            elif command == "$help":
                await message.channel.send(CHANNEL_HELP)

        else:
            # Talking in public channel, ignore
            pass

    except discord.Forbidden:
        await error_message(
            message.channel,
            "Bot doesn't have the permissions required for this action (@admin).",
        )
    except discord.HTTPException:
        await error_message(
            message.channel,
            "Something unexpected happened. Please try again in a few minutes.",
        )


async def error_message(channel, message):
    await channel.send(message)


def is_admin(member):
    return any(role.id == ADMIN_ROLE_ID for role in member.roles)


async def get_previous_message(message):
    l = await message.channel.history(limit=1, before=message).flatten()

    if l:
        return l[0]
    else:
        return None


async def get_channel_named(name):
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        await error_message(
            message.channel, "Guild/category was not found. Contact an admin."
        )
        return
    channels = await guild.fetch_channels()

    for channel in channels:
        if channel.name == name:
            return channel


async def get_role_named(name):
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        await error_message(
            message.channel, "Guild/category was not found. Contact an admin."
        )
        return
    roles = await guild.fetch_roles()

    for role in roles:
        if role.name == name:
            return role


def channel_name_legal(name):
    import string

    return set(name) <= set(string.ascii_letters.lower()).union(set("-0123456789"))


def has_role(member, role_id):
    return any(role.id == role_id for role in member.roles)


def get_static_members(channel):
    assert channel.category_id == CATEGORY_ID

    return [
        member
        for member in channel.members
        if not has_role(member, BOTS_ROLE_ID)
        and channel.overwrites_for(member).view_channel
    ]


# Start the bot
client.run(TOKEN)
