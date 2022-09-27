@client.event
async def on_message(message):
    try:

        splits = list(filter(bool, message.content.split(" ")))
        command, args = (splits[0], splits[1:]) if splits else ("", tuple())
        command = command.lower()
        args = [arg.strip() for arg in args if arg.strip()]

        author_id = f"{message.author.name} ({message.author.id})"

        # If private message
        if message.channel.type == discord.ChannelType.private:
            if command == "$create":

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
                    guild.get_role(config.one_channel_role_id)
                    if config.one_channel_role_id is not None
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
                        elif channel.category.id != config.category_id:
                            await message.channel.send(
                                f"Group {name} is not a private static."
                            )
                        else:
                            one_channel_role = (
                                guild.get_role(config.one_channel_role_id)
                                if config.one_channel_role_id is not None
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
        # If group message (in config.category_id)
        elif (
            message.guild.id == config.guild_id
            and message.channel.category.id == config.category_id
        ):

            if command == "$add":
                try:
                    guild = client.get_guild(config.guild_id)
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
                    guild = client.get_guild(config.guild_id)
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

            elif command == "$clear" and is_admin(member):
                limit = args[0] if args else "100"

                try:
                    limit = int(limit) + 1  # + 1 to include the $clear message
                except ValueError:
                    await error_message(message.channel, "Unrecognized limit number.")

                await message.channel.purge(limit=limit)

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
    return any(role.id == config.admin_role_id for role in member.roles)


async def get_previous_message(message):
    l = await message.channel.history(limit=1, before=message).flatten()

    if l:
        return l[0]
    else:
        return None


async def get_channel_named(name):
    guild = client.get_guild(config.guild_id)
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
    guild = client.get_guild(config.guild_id)
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
    assert channel.category_id == config.category_id

    return [
        member
        for member in channel.members
        if not has_role(member, config.bots_role_id)
        and channel.overwrites_for(member).view_channel
    ]
