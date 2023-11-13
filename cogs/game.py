import asyncio
import datetime
import random
import os
import re

import discord
from discord.ext import commands

from utils import make_embed, load_json, save_json
from constants.paths import IDEA_SAVES


def is_idea_message(content):
    return bool(re.match(r".*\bidea\s*:", content))

class Games(commands.Cog):
    """Games! Fun and games! Have fun!"""

    def __init__(self, bot):
        self.bot = bot
        self.words = None
        self.ideas = load_json(IDEA_SAVES)

    @commands.Cog.listener("on_message")
    async def on_message_idea(self, message):
        if not message.author.bot and message.guild and is_idea_message(message.content):
            self.ideas.append({"guild_id": message.guild.id, "channel_id": message.channel.id, "message_id": message.id})
            save_json(IDEA_SAVES, self.ideas)

    @commands.command()
    async def idea(self, ctx):
        """Get a random idea."""
        while True:
            i = random.randrange(len(self.ideas))
            m = self.ideas[i]
            try:
                msg = await self.bot.get_guild(m["guild_id"]).get_channel(m["channel_id"]).fetch_message(m["message_id"])
            except discord.HTTPException:
                self.ideas.pop(i)
                continue
            idea = msg.content
            if not is_idea_message(idea):
                self.ideas.pop(i)
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


    @commands.group(invoke_without_command=True)
    async def hwdyk(self, ctx):
        """How well do you know your friends?"""
        pass

    @commands.guild_only()
    @hwdyk.command(aliases=["msg"])
    async def message(self, ctx):
        """Pick a random message. If you can guess who sent it, you win!"""

        if ctx.guild.name == "QVDD":
            base = datetime.datetime(year=2023, month=7, day=25)
            year = 2023
            channel = ctx.guild.get_channel(1133026989637382149 if random.random() < .909 else 1133027144512049223)
        else:
            base = datetime.datetime(year=2020, month=1, day=1)
            # hardcoded list of "discussion" channels: esolang*, mathematics, off-topic, programming, *-games
            channel = self.bot.get_channel(random.choice([
                348671457808613388,
                348702485994668033,
                348702065062838273,
                351171126594109455,
                348702212110680064,
                412764872816852994,
                415981720286789634,
                445375649511768074,
                348697452712427522,
            ]))

        # this doesn't uniformly pick a random message: it strongly prefers messages sent after longer pauses
        # however this is a trade-off for making it incredibly cheap to grab a message because we don't have to spam history calls or store any data
        t = base + datetime.timedelta(milliseconds=random.randint(0, int((datetime.datetime.utcnow() - base).total_seconds() * 1000)))
        async for message in channel.history(before=t):
            if message.content and len(message.content) >= 20 and message.author in ctx.guild.members:
                break

        embed = make_embed(
            description=message.content,
            footer_text="#??? • ??/??/????",
        )
        embed.set_author(name="❓  ???")
        if message.attachments:
            filename = message.attachments[0].filename
            if filename.endswith(".png") or filename.endswith(".jpg") or filename.endswith(".jpeg"):
                embed.set_image(url=message.attachments[0].url)

        bot_msg = await ctx.reply("Who sent this message?", embed=embed)

        while True:
            r = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            try:
                member = await commands.MemberConverter().convert(ctx, r.content)
            except commands.BadArgument:
                pass
            else:
                break

        # reveal info
        embed.set_footer(text="#" + message.channel.name)
        embed.timestamp = message.edited_at or message.created_at
        embed.set_author(name=message.author.global_name or message.author.name, icon_url=message.author.display_avatar)
        await bot_msg.edit(embed=embed)

        if member == message.author:
            await r.reply("You were correct!")
        else:
            await r.reply("Too bad. Good luck with the next time!")

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
                if not winners:
                    async def ender():
                        await asyncio.sleep(10)
                        is_ended.set()
                    await ctx.send(f"{message.author.name.replace('@', '@' + zwsp)} wins. Other participants have 10 seconds to finish.")
                    self.bot.loop.create_task(ender())
                winners[message.author] = (message.created_at - start.created_at).total_seconds()
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
