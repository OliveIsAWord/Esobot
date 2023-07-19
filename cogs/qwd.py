import math
import asyncio
from io import BytesIO
from collections import defaultdict
from tokenize import TokenError

import discord
from PIL import Image
from discord.ext import commands
from pint import UnitRegistry, UndefinedUnitError, DimensionalityError
from typing import Optional, Union

from utils import save_json, load_json, get_pronouns, EmbedPaginator
from constants.paths import QWD_SAVES, QWD_LEADERBOARDS, QWD_LB_ALIASES


ureg = UnitRegistry(autoconvert_offset_to_baseunit=True)
ureg.separate_format_defaults = True
ureg.default_format = "~P"

class ParseError(ValueError):
    pass

class UnitFormatter:
    def __init__(self, unit, prec, compact, radices):
        self.unit = unit
        self.prec = prec
        self.compact = compact
        self.radices = radices

    def format(self, q):
        q = q.to(self.unit)
        s = ""
        for radix in self.radices:
            digit, q = divmod(q, 1*radix)
            s += f"{digit*radix:.0f}"
        if self.compact:
            q = q.to_compact()
        s += f"{q:.{self.prec}f}"
        return s.replace(" ", "")

    def __repr__(self):
        return f"UnitFormatter({self.unit!r}, {self.prec!r}, {self.compact!r}, {self.radices!r})"

    def __str__(self):
        s = "".join([f"{unit:P} + " for unit in self.radices])
        s += f"{'~'*self.compact}{self.unit:P}"
        if self.prec:
            s += f".{self.prec}"
        return s

class Leaderboard:
    def __init__(self, main, others, asc):
        self.main = main
        self.others = others
        self.asc = asc

    def ureq(self, string):
        q = ureg.Quantity(string)
        if q.unitless:
            q = q.m * self.main.unit
        else:
            q.ito(self.main.unit)
        if not math.isfinite(q.m):
            raise commands.BadArgument("What are you doing?")
        return q

    def format(self, string):
        q = self.ureq(string)
        s = self.main.format(q)
        if self.others:
            s += f" ({', '.join([formatter.format(q) for formatter in self.others])})"
        return s

    def __repr__(self):
        return f"Leaderboard({self.main!r}, {self.others!r}, {self.asc!r})"

    def __str__(self):
        return "asc "*self.asc + ", ".join(str(f) for f in [self.main, *self.others])

class LeaderboardParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def peek(self):
        return self.s[self.i:self.i+1]

    def advance(self):
        self.i += 1

    def panic(self, msg):
        pre = "  \033[1;34m|\033[0m "
        s = f"\n\033[1;31merror: \033[0m\033[1m{msg}\n{pre}\n{pre}{self.s}\n{pre}{' '*self.i}\033[1;31m^"
        raise ParseError(s)

    def assert_compatible(self, x, y):
        if not x.is_compatible_with(y):
            self.panic(f"units '{x:P}' and '{y:P}' are incompatible")

    def unit(self):
        n = ""
        while (c := self.peek()) not in ",.~+":
            if c == "-":
                self.panic("unexpected - in unit")
            n += c
            self.advance()
        n = n.strip()
        if not n:
            self.panic("expected unit")
        try:
            u = ureg.Unit(n)
        except (ValueError, UndefinedUnitError):
            self.panic(f"'{n}' is not a unit")
        else:
            return u

    def skip_ws(self):
        while self.peek().isspace():
            self.advance()

    def formatter(self):
        parts = []
        while True:
            self.skip_ws()
            if self.peek() == "~":
                if parts:
                    self.panic("the compacting operator ~ is incompatible with + chaining")
                compact = True
                self.advance()
            else:
                compact = False
            unit = self.unit()
            if parts:
                self.assert_compatible(parts[0], unit)
            parts.append(unit)
            prec = 0
            if self.peek() == ".":
                self.advance()
                try:
                    prec = int(self.peek())
                except ValueError:
                    self.panic("precision must be a digit")
                self.advance()
                self.skip_ws()
                break
            if compact or self.peek() != "+":
                break
            self.advance()
        *radices, unit = parts
        return UnitFormatter(unit, prec, compact, radices)

    def rule(self):
        asc = self.s.startswith("asc ")
        if asc:
            self.i += 4
        main = self.formatter()
        others = []
        while self.peek():
            if self.peek() != ",":
                self.panic("expected comma or end of string")
            self.advance()
            formatter = self.formatter()
            self.assert_compatible(main.unit, formatter.unit)
            others.append(formatter)
        return Leaderboard(main, others, asc)

def parse_leaderboard(text):
    return LeaderboardParser(text).rule()

async def accept_leaderboard(ctx, definition, *, compat=None):
    try:
        lb = parse_leaderboard(definition)
    except ParseError as e:
        raise commands.BadArgument(f"```ansi{e}```")
    lb_unit = lb.main.unit
    compat_unit = compat.main.unit
    if compat and not lb_unit.is_compatible_with(compat_unit):
        raise commands.BadArgument(f"unit '{lb_unit:P}' is incompatible with unit '{compat_unit:P}'")
    return lb

def rank_enumerate(xs, *, key, reverse):
    cur_idx = None
    cur_key = None
    for idx, x in enumerate(sorted(xs, key=key, reverse=reverse), start=1):
        if cur_key is None or key(x) != cur_key:
            cur_idx = idx
            cur_key = key(x)
        yield (cur_idx, x)

def render_graph(member_values):
    # Dimensions: len*120 + 120 x 720
    # Margins: 60 x 40
    member_values.sort(key=lambda x: -x[0])
    base = Image.new('RGBA', (len(member_values * 120), 720), (200, 200, 200, 0))
    max_value, min_value = member_values[0][0], member_values[-1][0]
    diff = max_value - min_value

    for i, (value, member, avatar) in enumerate(member_values):
        bar_value = math.ceil((value - min_value) * 680 / diff) + 40
        avatar = Image.open(BytesIO(avatar)).resize((120, bar_value)).convert('RGBA')
        base.alpha_composite(avatar, (120 * i, 720 - bar_value))

    rendered = BytesIO()
    base.save(rendered, format='png')
    rendered.seek(0)
    return rendered

# evil
class LeaderboardConv(commands.Converter):
    async def convert(self, ctx, argument):
        x = ctx.bot.get_cog("QWD").leaderboards.get(argument)
        if not x:
            raise commands.BadArgument("leaderboard doesn't exist :(")
        x.name = argument
        return x


class Qwd(commands.Cog, name="QWD"):
    """Commands for QWD."""

    def __init__(self, bot):
        self.bot = bot
        self.qwdies = defaultdict(dict, load_json(QWD_SAVES))
        self.leaderboards = {k: parse_leaderboard(v) for k, v in load_json(QWD_LEADERBOARDS).items()}
        self.aliases = load_json(QWD_LB_ALIASES)
        self.qwd = None

    def save_leaderboards(self):
        save_json(QWD_LEADERBOARDS, {k: str(v) for k, v in self.leaderboards.items()})
        save_json(QWD_LB_ALIASES, self.aliases)

    def cog_check(self, ctx):
        if not self.qwd:
            self.qwd = self.bot.get_guild(1047299292492206101)
        return not ctx.guild and self.qwd.get_member(ctx.author.id) or ctx.guild == self.qwd

    @commands.group(invoke_without_command=True, aliases=["doxx"])
    @commands.guild_only()
    async def dox(self, ctx, *, target: discord.Member):
        """Reveal someone's address if they have set it through the bot. Must be used in a guild; the answer will be DMed to you."""
        p = get_pronouns(target)
        if not (addr := self.qwdies[str(target.id)].get("address")):
            return await ctx.send(f'{p.Subj()} {p.plrnt("do", "es")} have an address set.')
        await ctx.author.send(addr)
        await ctx.send(f"Alright, I've DMed you {p.pos_det} address.")

    @dox.command(name="set")
    @commands.dm_only()
    async def set_dox(self, ctx, *, address=""):
        """Set your address to be doxxed by others. Must be used in a DM with the bot. You can clear your address by using `set` without an argument."""
        self.qwdies[str(ctx.author.id)]["address"] = address
        save_json(QWD_SAVES, self.qwdies)
        if not address:
            await ctx.send("Successfully cleared your address.")
        else:
            await ctx.send("Successfully set your address.")     

    def true_key(self, key):
        return self.aliases.get(key, key)

    def data(self, member):
        return self.qwdies[str(member.id)].setdefault("lb", {})

    def data_of(self, member, key):
        return self.data(member).get(self.true_key(key))

    def lb_of(self, key):
        people = []
        for user in self.qwd.members:
            value = self.data_of(user, key)
            if not value or key == "height" and "razetime" in (user.global_name, user.name):
                continue
            people.append((value, user))
        return people

    @commands.group(invoke_without_command=True, aliases=["lb"])
    async def leaderboard(self, ctx, lb: LeaderboardConv):
        """Show a leaderboard, given its name."""
        entries = []
        for i, (value, user) in rank_enumerate(self.lb_of(lb.name), key=lambda x: lb.ureq(x[0]), reverse=not lb.asc):
            entries.append(rf"{i}\. {user.global_name or user.name} - {lb.format(value)}")
        embed = discord.Embed(title=f"The `{lb.name}` leaderboard", colour=discord.Colour(0x75ffe3), description="\n".join(entries))
        if not entries:
            embed.set_footer(text="Seems to be empty")
        await ctx.send(embed=embed)

    @leaderboard.command()
    async def get(self, ctx, lb: LeaderboardConv, *, member: discord.Member):
        """Get a specific person's number on a leaderboard."""
        value = self.data_of(member or ctx.author, lb.name)
        p = get_pronouns(member)
        if not value:
            return await ctx.send(f'{p.Subj()} {p.plrnt("do", "es")} have a `{lb.name}` value set.')
        await ctx.send(embed=discord.Embed(title=f"{member.global_name or member.name}'s `{lb.name}`", description=lb.format(value), colour=discord.Colour(0x75ffe3)))

    @leaderboard.command()
    async def set(self, ctx, lb: LeaderboardConv, *, value=None):
        """Play nice. Don't you fucking test me."""
        data = self.data(ctx.author)
        name = self.true_key(lb.name)
        if not value:
            if data.pop(name, None):
                return await ctx.send("Done.")
            else:
                return await ctx.send("Nothing to do.")
        try:
            nice = lb.format(value)
        except (TokenError, UndefinedUnitError):
            return await ctx.send("I couldn't parse that as a sensible value.")
        except DimensionalityError:
            return await ctx.send(f"Unit mismatch: your unit is incompatible with the leaderboard's unit '{lb.main.unit:P}'.")
        data[name] = value
        save_json(QWD_SAVES, self.qwdies)
        await ctx.send(f"Okay, your value will display as {nice}.")

    @leaderboard.command(aliases=["new", "add", "make"])
    async def create(self, ctx, name="", *, definition=""):
        """Create a leaderboard. WARNING: The syntax for this command is complex and you cannot remove or edit leaderboards. Use `!help lb new` for more info.

        To make a leaderboard, you pass to this command the name of the command (in quotes if necessary) and its definition. The simplest leaderboards consist of a single unit, and look like this:
        `!lb create height cm`

        However, this leaderboard will only display values in centimetres. The `create` command has various formatting options to make output nicer. For starters, you can offer multiple choices of unit, like so:
        `!lb create height cm, in`

        This will show both centimeters and inches. However, people's heights are usually shown in feet *and* inches, so we can chain those units together with `+`.
        `!lb create height cm, ft+in`

        We probably want to show the shortest people first (I like them better), so we can also flip the sorting order.
        `!lb create height asc cm, ft+in`

        This is now a good height leaderboard, so let's explore the rest of the options by making a leaderboard for people's remaining disk space. The base unit should be gigabytes.
        `!lb create disk gigabytes`

        But some people have almost filled up their drives, while others have empty 2TB hard drives. We don't want to display 2TB values as "2000GB" or small values as "0GB". We could try to alleviate this by using `TB + GB + MB`, but the resulting strings are fairly ugly. Instead, we can use the `~` option to automatically scale the unit.
        `!lb create disk ~bytes`

        Now, no matter the number of bytes entered, the displayed value will scale correspondingly. The final option is the `.` operator, which allows us to specify more significant digits to show.
        `!lb create disk ~bytes.2`

        That's it! Now you know about all of `create`'s formatting features and how they can be used to make convenient leaderboards. Remember once again to be VERY careful with this command.
        """
        if not name or not definition:
            return await ctx.send("No definition provided. **Please** read the text of `!help lb create` in full to learn how to use this command. Do not use it lightly; created leaderboards cannot be removed or edited again without LyricLy. And she will *not* like helping you, no matter how much you think she will.")
        if name in self.leaderboards:
            return await ctx.send("Look at you. You're so cute, trying to do that. This leaderboard already exists.")
        lb = await accept_leaderboard(ctx, definition)
        self.leaderboards[name] = lb
        self.save_leaderboards()
        await ctx.send(f"Successfully created a new ``{name}`` leaderboard: ``{lb}``. You'd better not regret this. You can edit this leaderboard at any time.")

    @leaderboard.command(aliases=["link", "point", "ln"])
    async def alias(self, ctx, to_lb: LeaderboardConv, fro: str, *, definition=None):
        """Create a new alias to another leaderboard. You may specify a new way to format the values; the default is to use the formatting of the source leaderboard."""
        if fro in self.leaderboards:
            return await ctx.send("Very funny. That name is taken.")
        from_lb = await accept_leaderboard(ctx, definition, compat=to_lb)
        self.leaderboards[fro] = from_lb
        self.aliases[fro] = to_lb.name
        self.save_leaderboards()
        await ctx.send("Successfully created a new alias ``{fro}`` -> ``{to_lb.name}``: ``{from_lb}``. You can edit or delete this alias at any time.")

    @leaderboard.command(aliases=["delete"])
    async def remove(self, ctx, lb: LeaderboardConv):
        """Remove a leaderboard alias."""
        if not self.aliases.pop(lb.name, None):
            if ctx.author.id != 319753218592866315:
                return await ctx.send("You can't remove a leaderboard that isn't an alias.")
            else:
                for v in self.qwdies.values():
                    v.get("lb", {}).pop(lb.name, None)
        self.leaderboards.pop(lb.name)
        self.save_leaderboards()
        await ctx.send("Done.")

    @leaderboard.command(aliases=["modify", "update", "replace"])
    async def edit(self, ctx, old: LeaderboardConv, *, definition):
        """Edit a leaderboard's formatting definition."""
        new = await accept_leaderboard(ctx, definition, compat=old)
        self.leaderboards[old.name] = new
        self.save_leaderboards()
        await ctx.send("Done.")

    @leaderboard.command(aliases=["list"])
    async def all(self, ctx):
        paginator = EmbedPaginator()
        for name, lb in self.leaderboards.items():
            paginator.add_line(f"`{name}`: `{lb}`")
        paginator.embeds[0].title = "All leaderboards"
        for embed in paginator.embeds:
            await ctx.send(embed=embed)

    @leaderboard.command()
    async def graph(self, ctx, lb: LeaderboardConv):
        """Graph a (somewhat humorous) ranking of people's values in a leaderboard such as `height`."""
        people = [(lb.ureq(value).m, user, await user.avatar.read()) for value, user in self.lb_of(lb.name)]
        if len(people) < 2:
            return await ctx.send("There must be at least 2 people on a leaderboard to use `graph`.")
        image = await asyncio.to_thread(render_graph, people)
        await ctx.send(file=discord.File(image, filename='height_graph.png'))


async def setup(bot):
    await bot.add_cog(Qwd(bot))
