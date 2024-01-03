import socket
import urllib.parse

from discord.ext import commands
from constants import colors, info
from utils import make_embed


class Esolangs(commands.Cog):
    """Commands related to esoteric programming languages."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["ew", "w", "wiki"])
    async def esowiki(self, ctx, *, esolang_name):
        """Link to the Esolang Wiki page for an esoteric programming language."""
        async with self.bot.session.get(
            "https://esolangs.org/w/index.php",
            params = {
                "search": esolang_name,
            },
            allow_redirects=False,
        ) as resp:
            if resp.status != 302:
                return await ctx.send(
                    embed=make_embed(
                        color=colors.EMBED_ERROR,
                        title="Error",
                        description=f"Page not found.",
                    )
                )
            f, l = resp.headers["Location"].rsplit("/", 1)
            await ctx.send(f + "/" + l.replace(".", "%2E"))


async def setup(bot):
    await bot.add_cog(Esolangs(bot))
