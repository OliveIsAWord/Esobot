import aiohttp
import asyncio
import pykakasi
import discord
import asyncio
import random
import openai
import io

from utils import show_error
from discord.ext import commands, menus


def format_jp_entry(entry):
    try:
        return f"{entry['word']}【{entry['reading']}】"
    except KeyError:
        try:
            return entry["reading"]
        except KeyError:
            try:
                return entry["word"]
            except KeyError:
                return "???"

class DictSource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, menu, entry):
        e = discord.Embed(
            title = f"Result #{menu.current_page + 1}",
            description = format_jp_entry(entry['japanese'][0])
        )
        if tags := [
            *["common"]*entry.get("is_common", False),
            *sorted(f"JLPT {x.partition('-')[2]}" for x in entry.get("jlpt", []))[-1:],
        ]:
            e.title += f" ({', '.join(tags)})"
        for i, sense in enumerate(entry["senses"], start=1):
            e.add_field(
                name = ", ".join(sense["parts_of_speech"]) if sense["parts_of_speech"] else "\u200b",
                value = " | ".join([
                    f"{i}. " + "; ".join(sense["english_definitions"]),
                    *filter(None, [", ".join(f"*{x}*" for x in sense["tags"] + sense["info"])]),
                ]),
                inline=False
            )
        if len(entry["japanese"]) > 1:
            e.add_field(name = "Other forms", value = "\n".join(format_jp_entry(x) for x in entry["japanese"][1:]), inline=False)
        return e

class Japanese(commands.Cog):
    """Weeb stuff."""

    def __init__(self, bot):
        self.bot = bot
        kakasi = pykakasi.kakasi()
        kakasi.setMode("H", "a")
        kakasi.setMode("K", "a")
        kakasi.setMode("J", "a")
        kakasi.setMode("s", True)
        self.conv = kakasi.getConverter()

    @commands.command(aliases=["ro", "roman", "romanize", "romanise"])
    async def romaji(self, ctx, *, text: commands.clean_content = None):
        """Romanize Japanese text."""
        await ctx.send(self.conv.do(text or self.last_lyric_msg))

    @commands.command(aliases=["jp", "jsh", "dictionary", "dict"])
    async def jisho(self, ctx, *, query):
        """Look things up in the Jisho dictionary."""
        async with self.bot.session.get("https://jisho.org/api/v1/search/words", params={"keyword": query}) as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                data = None
        if not data["data"]:
            return await show_error(ctx, "That query returned no results.")
        pages = menus.MenuPages(source=DictSource(data["data"]), clear_reactions_after=True)
        await pages.start(ctx)

    GENERAL_PROMPT = " ".join("""
        Your role is to explain recent references to Japan in a Discord chat log.
        You look at the context for references to Japanese culture and media, giving brief but comprehensive descriptions in English as necessary.
        If the meaning of something would be obvious to an English speaker, it should not be explained.
        When text is written in Japanese, give a literal translation of it and *do not* say anything else. It is not necessary to say "The Japanese text translates to".
        There is no single user that you can address. Do not use second-person pronouns. Do not refer to the input as "the text".
        Talk about the channel as a whole with terms like "that I can see", "here", or "in the chat" instead.
        Only when there is absolutely nothing to be explained, meaning that there is nothing Japanese in the input
        or that everything Japanese is obvious or has already been explained, indicate as such in your own words and say nothing else.
        If there is something to be explained, there is no need to say anything along the lines of "there are no other references to Japan in the chat".
        When you are done explaining, simply stop talking and say nothing more.
        Try to keep your responses natural and avoid repeating the words in this prompt verbatim.
        Do not acknowledge non-Japanese messages unless you're certain they're relevant.
    """.split())

    SPECIFIC_PROMPT = " ".join("""
        Your role is to explain references to Japanese culture and media, providing short but comprehensive descriptions in English.
        When you see text written in Japanese, you give a literal translation of the text without any further commentary.
        Careful not to let responses get too long. Aim for a handful of sentences.
    """.split())

    @commands.command(aliases=["what", "unlyric", "undweeb", ";)", "otherlanguagesscareme",
                               "機械翻訳", "ifyouhaveajapaneseimewhyareyouusingashittygpt4command"])
    async def unweeb(self, ctx, *, lyric_quote: commands.clean_content = None):
        """Translate Japanese."""
        if not lyric_quote and (r := ctx.message.reference):
            if not isinstance(r.resolved, discord.Message):
                return await ctx.send("Reply unavailable :(")
            lyric_quote = r.resolved.content

        if not lyric_quote:
            prompt = self.GENERAL_PROMPT
            text = "\n".join([m.content async for m in ctx.history(limit=12)][:0:-1])
        else:
            prompt = self.SPECIFIC_PROMPT
            text = lyric_quote

        completion = await openai.ChatCompletion.acreate(
            model="gpt-4-1106-preview",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        result = completion["choices"][0]["message"]["content"]

        if len(result) > 2000:
            await ctx.reply(file=discord.File(io.StringIO(result), "resp.txt"))
        else:
            await ctx.reply(result)


async def setup(bot):
    await bot.add_cog(Japanese(bot))
