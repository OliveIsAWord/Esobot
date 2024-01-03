import discord
import requests
from discord.ext import commands
from ahocorasick import Automaton

import re
from constants import colors, channels
from utils import make_embed, show_error


d = requests.get("https://gist.githubusercontent.com/Vexs/629488c4bb4126ad2a9909309ed6bd71/raw/edd5473221f42ea0f8b9de16545b4b853bf11140/emoji_map.json").json()
unicode = Automaton()
for emoji in d.values():
    unicode.add_word(emoji, emoji)
unicode.make_automaton()

custom = re.compile("<a?:[a-zA-Z0-9_]{2,32}:[0-9]{18,22}>")
role = re.compile(r'<@&([0-9]{18,22})>|`(.*?)`|"(.*?)"|\((.*?)\)|\*(.*?)\*|-\s*(.*?)$')

def get_emoji(s):
    emoji = []
    emoji.extend(unicode.iter(s))
    emoji.extend((m.end(), m.group(0)) for m in custom.finditer(s))
    emoji.sort(key=lambda x: x[0])

    out = []
    for end_pos, text in emoji:
        if m := role.search(s, end_pos):
            if m.group(1):
                r = int(m.group(1))
            else:
                for r in m.group(2, 3, 4, 5, 6):
                    if r:
                        break
            out.append((text, r))

    return out


class ReactionRoles(commands.Cog, name="Reaction roles"):
    """A cog for managing Esobot's reaction-based role system."""

    def __init__(self, bot):
        self.bot = bot

    async def scan(self, msg, *, content=None, channel_id=None):
        msg_id = msg.id
        content = content or msg.content
        guild = msg.guild

        pairs = {}
        errors = []
        m = {}

        for emoji, role in get_emoji(content):
            if role_obj := discord.utils.get(guild.roles, name=role) or (isinstance(role, int) and guild.get_role(role)):
                pairs[emoji] = role_obj.id
                if role_obj >= guild.me.top_role:
                    errors.append(f"The '{role_obj.name}' role is too high for me to control.")
                if k := m.get(role_obj):
                    errors.append(f"{emoji} and {k} map to the same role. Maybe your formatting is wrong?")
                else:
                    m[role_obj] = emoji
            else:
                errors.append(f"Role '{role}' not found.")

        if not guild.me.guild_permissions.manage_roles:
            errors.append("I don't have the Manage Roles permission.")

        async with self.bot.db.execute("SELECT emoji, role_id FROM ReactionRolePairs WHERE message_id = ?", (msg_id,)) as cur:
            old_pairs = dict(await cur.fetchall())
        if pairs != old_pairs:
            current_emoji = list(old_pairs) if old_pairs else []
            target_emoji = list(pairs)

            for emoji in current_emoji:
                try:
                    target_emoji.remove(emoji)
                except ValueError:
                    pass
            for emoji in target_emoji:
                await msg.add_reaction(emoji)

            if channel_id:
                await self.bot.db.execute("INSERT INTO ReactionRoleMessages (message_id, origin_channel) VALUES (?, ?)", (msg_id, channel_id))
            await self.bot.db.execute("DELETE FROM ReactionRolePairs WHERE message_id = ?", (msg_id,))
            for x, y in pairs.items():
                await self.bot.db.execute("INSERT INTO ReactionRolePairs (message_id, emoji, role_id) VALUES (?, ?, ?)", (msg_id, x, y))
            await self.bot.db.commit()
            lines = [f"- {emoji}: <@&{role}>" for emoji, role in pairs.items()] if pairs else ["No reactions configured."]
            if errors:
                lines.append("")
                lines.append("Issues were found.")
                lines.extend("- " + e for e in errors)
            return "\n".join(lines)
        else:
            return None

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def rolewatch(self, ctx, *, msg: discord.Message):
        """Register a message for reaction role management."""
        m = await self.scan(msg, channel_id=ctx.channel.id)

        if m:
            await ctx.send(f"Data parsed and committed. I'm watching this message for reactions.\n\n{m}", allowed_mentions=discord.AllowedMentions.none())
        else:
            await ctx.send("Nothing has changed.")

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload):
        msg_id = payload.message_id
        async with self.bot.db.execute("SELECT origin_channel FROM ReactionRoleMessages WHERE message_id = ?", (msg_id,)) as cur:
            origin = await cur.fetchone()
        if not origin:
            return
        guild = self.bot.get_guild(payload.guild_id)
        p = discord.PartialMessage(id=msg_id, channel=guild.get_channel(payload.channel_id))
        msg = await self.scan(p, content=payload.data["content"])
        if msg:
            channel = guild.get_channel(origin[0])
            await channel.send(f"Detected changes to <https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{msg_id}>.\n\n{msg}", allowed_mentions=discord.AllowedMentions.none())

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        await self.bot.db.execute("DELETE FROM ReactionRoleMessages WHERE message_id = ?", (payload.message_id,))
        await self.bot.db.commit()

    async def dry(self, method, payload):
        msg_id = payload.message_id
        async with self.bot.db.execute("SELECT role_id FROM ReactionRolePairs WHERE message_id = ? AND emoji = ?", (msg_id, str(payload.emoji))) as cur:
            role_id = await cur.fetchone()
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(role_id[0])
        try:
            await method(guild.get_member(payload.user_id), role)
        except discord.Forbidden:
            async with self.bot.db.execute("SELECT origin_channel FROM ReactionRoleMessages WHERE message_id = ?", (msg_id,)) as cur:
                origin, = await cur.fetchone()
            channel = guild.get_channel(origin)
            await channel.send(f"I tried to change the role '{role.name}' on {payload.member}, but I don't have permission.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.dry(discord.Member.add_roles, payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.dry(discord.Member.remove_roles, payload)


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
