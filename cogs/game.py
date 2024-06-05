import asyncio
import random
import os
import re

import discord
from discord.ext import commands


def is_idea_message(content):
    return bool(re.match(r".*\bidea\s*:", content))

class Games(commands.Cog):
    """Games! Fun and games! Have fun!"""

    def __init__(self, bot):
        self.bot = bot
        self.words = None

    @commands.Cog.listener("on_message")
    async def on_message_idea(self, message):
        if not message.author.bot and message.guild and is_idea_message(message.content):
            await self.bot.db.execute("INSERT INTO Ideas (guild_id, channel_id, message_id) VALUES (?, ?, ?)", (message.guild.id, message.channel.id, message.id))
            await self.bot.db.commit()

    @commands.command()
    async def idea(self, ctx):
        """Get a random idea."""
        while True:
            async with self.bot.db.execute("SELECT rowid FROM Ideas") as cur:
                rowid, = random.choice(await cur.fetchall())
            async with self.bot.db.execute("SELECT * FROM Ideas WHERE rowid = ?", (rowid,)) as cur:
                m = await cur.fetchone()
            try:
                msg = await self.bot.get_guild(m["guild_id"]).get_channel(m["channel_id"]).fetch_message(m["message_id"])
            except discord.HTTPException:
                msg = None
            if not msg or not is_idea_message(idea := msg.content):
                await self.bot.db.execute("DELETE FROM Ideas WHERE rowid = ?", (rowid,))
                continue
            if idea.endswith("idea:"):
                idea_extra = None
                async for m in msg.channel.history(after=msg, limit=5):
                    if m.author == msg.author:
                        idea_extra = m.content
                        break
                if idea_extra is not None:
                    idea += "\n"
                    idea += idea_extra
            await ctx.send(f"{msg.jump_url}\n{msg.content}", allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False))
            break

    async def run_race(self, ctx, prompt, is_valid):
        await ctx.send(f"Race begins in 5 seconds. Get ready!")
        await asyncio.sleep(5)

        zwsp = "\u2060"
        start = await ctx.send(zwsp.join(prompt.translate(str.maketrans({
            "a": "а",
            "c": "с",
            "e": "е",
            "s": "ѕ",
            "i": "і",
            "j": "ј",
            "o": "о",
            "p": "р",
            "y": "у",
            "x": "х"
        }))))

        winners = {}
        is_ended = asyncio.Event()

        async def on_message(message):
            if message.channel == ctx.channel and is_valid(message.content) and not message.author.bot and message.author not in winners:
                first_winner = not winners
                winners[message.author] = (message.created_at - start.created_at).total_seconds()
                if first_winner:
                    async def ender():
                        await asyncio.sleep(10)
                        is_ended.set()
                    await ctx.send(f"{message.author.name.replace('@', '@' + zwsp)} wins. Other participants have 10 seconds to finish.")
                    self.bot.loop.create_task(ender())
                await message.delete()

        self.bot.add_listener(on_message)
        try:
            await asyncio.wait_for(is_ended.wait(), 120)
        except asyncio.TimeoutError:
            pass
        else:
            await ctx.send("\n".join(f"{i + 1}. {u.name.replace('@', '@' + zwsp)} - {t:.4f} seconds ({len(prompt) / t * 12:.2f}WPM)" for i, (u, t) in enumerate(winners.items())))
        finally:
            self.bot.remove_listener(on_message)

    @commands.command(aliases=["tr", "type", "race"])
    @commands.guild_only()
    async def typerace(self, ctx, words: int = 10):
        """A simple typing race."""
        if not 5 <= words <= 75:
            return await ctx.send("Use between 5 and 75 words.")
        if not self.words:
            async with self.bot.session.get("https://raw.githubusercontent.com/monkeytypegame/monkeytype/master/frontend/static/languages/english_1k.json") as resp:
                self.words = (await resp.json(content_type="text/plain"))["words"]
        prompt = " ".join(random.choices(self.words, k=words))
        await self.run_race(ctx, prompt, lambda s: s.lower() == prompt)

    @commands.command()
    @commands.guild_only()
    async def kanarace(self, ctx, kana_count: int = 10, use_katakana: bool = False):
        """A typing race with hiragana (or katakana)"""
        if not 1 <= kana_count <= 50:
            return await ctx.send("Use between 1 and 50 kana.")
        hiragana = "あいうえおかきくけこがぎぐげごさしすせそざじずぜぞたちつてとだぢづでどなにぬねのはひふへほばびぶべぼぱぴぷぺぽまみむめもやゆよらりるれろわを"
        katakana = "アイウエオカキクケコガギグゲゴサシスセソザジズゼゾタチツテトダヂヅデドナニヌネノハヒフヘホバビブベボポピプペポマミムメモヤユヨラリルレロワヲ"
        table = str.maketrans(katakana, hiragana)
        prompt = "".join(random.choices(katakana if use_katakana else hiragana, k=kana_count))
        await self.run_race(ctx, prompt, lambda s: s.translate(table) == prompt.translate(table))

    @commands.command()
    @commands.guild_only()
    async def sortrace(self, ctx, count: int = 10, max_value: int = 100):
        """Why would you play this?"""
        prompt = [random.randint(0, max_value) for _ in range(count)]
        sorted_prompt = sorted(prompt)
        await self.run_race(ctx, str(prompt), lambda s: [(m := x.strip("[],")).isdigit() and int(m) for x in s.split()] == sorted_prompt)


async def setup(bot):
    await bot.add_cog(Games(bot))
