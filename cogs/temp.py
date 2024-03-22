import datetime
import os
import random
import uuid
import re
import unicodedata

import discord
from discord.ext import commands, tasks


class Temporary(commands.Cog):
    """Temporary, seasonal, random and miscellaneous poorly-written functionality. Things in here should probably be developed further or removed at some point."""

    def __init__(self, bot):
        self.bot = bot
        self.last_10 = None
        self.pride_loop.start()

    def cog_unload(self):
        self.pride_loop.cancel()

    # 12PM UTC
    @tasks.loop(
        time=datetime.time(12),
    )
    async def pride_loop(self):
        PATH = "./assets/limes/"
        l = sorted(os.listdir(PATH))
        if "index" in l:
            with open(PATH + "index") as f:
                i = int(f.read())
        else:
            random.shuffle(l)
            for i, f in enumerate(l):
                name = f"{i:0>{len(str(len(l)))}}-{uuid.uuid4()}"
                os.replace(PATH + f, PATH + name)
                l[i] = name
            i = 0
        next_lime = l[i]
        i += 1
        if i >= len(l)-1:
            os.remove(PATH + "index")
        else:
            with open(PATH + "index", "w") as f:
                f.write(str(i))
        with open(PATH + next_lime, "rb") as f:
            d = f.read()
        await self.bot.get_guild(346530916832903169).edit(icon=d)

    @pride_loop.before_loop
    async def before_pride_loop(self):
        await self.bot.wait_until_ready()

    @commands.group(hidden=True, invoke_without_command=True)
    async def olivia(self, ctx):
        pass

    @olivia.command(name="time", hidden=True)
    async def _time(self, ctx):
        if member := ctx.guild.get_member(156021301654454272):
            await self.bot.get_command("time")(ctx, user=member)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user and len(message.content.split(" ")) == 10:
            self.last_10 = message.created_at
        if self.last_10 and message.author.id == 509849474647064576 and len(message.content.split(" ")) == 10 and (message.created_at - self.last_10).total_seconds() < 1.0:
            await message.delete()

        if (parts := message.content.split(" ", 1))[0] == "?chairinfo":
            lines = []
            for c in parts[1]:
                name = unicodedata.name(c, "")
                if m := re.fullmatch(r"(.*)LATIN SMALL LETTER (.*)\bH\b(.*)", name):
                    title = f"{m[1]}{m[2]}CHAIR{m[3]}"
                elif m := re.fullmatch(r"CYRILLIC (.*)LETTER (.*)\bCHE\b(.*)", name):
                    title = f"TURNED {m[1].replace('CAPITAL', 'BIG')}{m[2]}CHAIR{m[3]}"
                else:
                    title = {
                        "🪑": "CHAIR", "💺": "CHAIR", "🛋": "DOUBLE CHAIR", "⑁": "OPTICAL CHARACTER RECOGNIZABLE CHAIR",
                        "♿": "SYMBOLIC WHEELED CHAIR", "🦽": "MANUAL WHEELED CHAIR", "🦼": "AUTOMATIC WHEELED CHAIR",
                        "µ": "VERTICALLY-FLIPPED CHAIR", "ɥ": "TURNED CHAIR", "ɰ": "DOUBLE TURNED CHAIR",
                        "ꜧ": "UNEVEN CHAIR", "ћ": "SLAVIC CHAIR WITH STROKE", "ђ": "UNEVEN CHAIR WITH STROKE",
                        "Һ": "SLAVIC BIG CHAIR", "һ": "SLAVIC SMALL CHAIR",
                        "Ꚕ": "SLAVIC BIG CHAIR WITH HOOK", "ꚕ": "SLAVIC SMALL CHAIR WITH HOOK",
                        "Ԧ": "SLAVIC BIG CHAIR WITH DESCENDER", "ԧ": "SLAVIC SMALL CHAIR WITH DESCENDER",
                        "Ի": "BIG CHAIR WITH SHORT LEG", "ի": "SMALL CHAIR WITH LONG LEG",
                        "Կ": "TURNED BIG CHAIR WITH SHORT LEG", "կ": "TURNED SMALL CHAIR WITH LONG LEG",
                        "Ϧ": "FANCY CHAIR", "փ": "ABOMINATION",
                        "Ⴗ": "GEORGIAN TURNED CHAIR",
                        "۲": "NUMERIC VERTICALLY-FLIPPED CHAIR", "ށ": "CURSIVE VERTICALLY-FLIPPED CHAIR",
                        "Ꮒ": "BIG CHAIR", "Ꮵ": "FANCY CHAIR",
                        "ᖹ": "HORIZONTALLY-FLIPPED SYLLABIC CHAIR", "ᖺ": "SYLLABIC CHAIR", "ᖻ": "TURNED SYLLABIC CHAIR",
                        "ᚴ": "VERTICALLY-FLIPPED NORDIC CHAIR",
                        "ℎ": "ITALIC CHAIR", "ℏ": "ITALIC CHAIR WITH STROKE",
                        "ₕ": "SUBSCRIPT CHAIR", "ʰ": "SUPERSCRIPT CHAIR",
                    }.get(c, "NOT A CHAIR")
                lines.append(f"`\\U{ord(c):>08x}`: {title} **\N{EM DASH}** {c}")
            await message.channel.send("\n".join(lines))

async def setup(bot):
    await bot.add_cog(Temporary(bot))
