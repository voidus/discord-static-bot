# discord-static-bot
 Discord bot to create private static channels

# Description

This is the code for running a Discord bot using Python and the discord.py library.

You can use this in two contexts for different reasons:

* In a DM: by writing a private message to the bot, you can ask it to $create a new private group for you. 
    This will create a channel in the Private Channels Category.
* Inside a private channel, the bot has other utilities:
    * $add/$remove: add/remove members to/from your group.
    * Check current $members of the group.
    * $mention (@) all members of the group.
    * $pin/$unpin: pin/unpin a selected message.

You can get the list of commands anytime by typing $help either in a DM to the bot 
or in a private channel (**both contexts have different messages and different commands available**).

# Disclaimer

This bot was a one-sunday thing, its goals was for it to be 1) simple to code, 2) simple to use. 
It was created to be stateless and save no data of any kind. 
As such, I prioritized simplicity over functionality, covering all cases and security. 

What I mean about security is that it is possible for a user to:

* Create as many channels as they want. This is mitigated with the "one-channel-only" role, 
that you get every time you create a channel, and doesn't allow you to create more 
unless and admin removes the role from you.
* Spam commands trying to overwhelm the bot. No limit rate of any kind is performed,
as this will require the bot to save "sessions", knowing the command rate of each user.
* Add/remove/pin/unpin as much as they want once they're inside a group. 
They could even kick the leader of a static from its own group. 

Obviously, these are clear weaknesses of the system, 
but the amount of damage such a malicious user could do is minimal, 
as 1) admins can blacklist that user at any time, 
2) everything can be restored back to normal with a few commands.

If you feel like you need more security in place, 
feel free to edit the code and add as much as you need.

# Building a docker image

```
docker run --rm -v $PWD:/work nixos/nix --extra-experimental-features nix-command\ flakes build /work#docker-latest
# you could also copy the result file to a server and import it there. Note that result is a symlink
# and you need to copy the actual file, not the link. Show the filename with `readlink result`
docker import <result
```

This is horribly inefficient, especially in regards to network bandwidth. Sorry about that.

# Setup

Create your own bot in https://discord.com/developers/applications
For that, you need an application, create a bot in the Bot section,
uncheck the "PUBLIC BOT" option and check the "SERVER MEMBERS INTENT" option.
Finally, click the "Copy" button up on the Token section (next to the avatar). 
Save that token verbatim in a file called token.txt right on the bot folder.

You also need to invite your bot to your server. For that, go to the OAuth2 tab, 
enable the Bot scope, and select all permissions you require for your bot.
For the default functionality shown in this repository, add:
* Manage Roles
* Manage Channels
* View Channels
* Send Messages
* Manage Messages (for pins)
* Read Message History
After enabling everything, copy the url at the end of the scopes box
and paste it into your browser to invite the Bot to your server.

Create a Channel Category with "View Channels" permission set to False by default.
Inside, only channels called "static-X" will be located.

You'll also need some special roles in your server:
* ADMIN (required): administrator role, to allow its members to perform some extra commands with the bot (delete group, clear, etc.)
* BOTS (required): bots role. Create a new role for all your bots, so that this bot doesn't count them as members of your channel.
* BLACKLIST (required): blacklist some users to avoid them using the bot. This role can be empty,
    but create it to quickly add any problematic members as soon as they abuse the bot.
* WHITELIST (optional): if it exists, only members inside this role can use the bot.
* ONE_CHANNEL_ROLE_ID (optional): if it exists, it allows you to prevent users from creating infinite channels.
    The downside is that they won't be able to create more than one channel, 
    unless and admin removes the role from them every time. 
    Really recommended to have this role unless you fully trust your members.

You'll need to access Discord ids for the next step. To do that, open your Discord application,
go to Settings->Advanced and toggle on Developer Mode. Now, you can right-click on any 
server/channel/message/role/user and get their ids (a long number).

Set the conf.json file with:
* "GUILD_ID": the id of the server.
* "CATEGORY_ID": the id of the static channels category. 
* "ADMIN_ROLE_ID": the id of the "admin" role in the server.
* "BOTS_ROLE_ID": the id of the "bots" role in the server.
* "BLACKLIST_ROLE_ID": the id of the blacklist role in the server.
* "WHITELIST_ROLE_ID": the id of the whitelist role in the server.
    If null, all members can use the bot.
* "ONE_CHANNEL_ROLE_ID": the id of the static-leader role. 
    This is used to block members to create more than 1 channel.
    To circumvent this restriction, admins can remove the role 
    from members who requested to create more. 
    If null, all members can create as many channels as they want.

If you don't want to put any id there, fill the value with "null" (without "). 

After all this is done, you can execute the bot by running `python3 bot.py conf.json` in a command-line.
Note that you need to keep the bot running for it to work. For simple setups, using `tmux` 
to run the command and detaching from the session might be enough.
