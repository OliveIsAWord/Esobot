import asyncio
import datetime
import re

from discord.ext import commands
from openai import AsyncOpenAI, BadRequestError


openai = AsyncOpenAI()

SYSTEM_MESSAGE = """You are a chatbot named Esobot designed to converse naturally with multiple people at once.

You are on a Discord server named "QWD", sometimes also referred to as "QVDD". The people on this server are referred to as "qwdies".
Treat "name" as a synonym of "username".
Several people on the server are known by other names. You should use these aliases as much as possible.
LyricLy is Christina
ultlang is Emma
Swedish Submarine is Emily
🌺🎀p♡mzie🎀🌺is Ari.
Names are also often shortened, such as "pyro" for "pyrotelekinetic" or "essie" for "rottenessie".
Avoid saying users' names every time you talk to them. It's usually not necessary.
"""
HOME_ID = 1201189212507095071

ALWAYS_REMIND = [{"role": "system", "content": SYSTEM_MESSAGE}]


class EsobotPlace(commands.Cog):
    """The source code to the renewed #esobot-place channel on QWD."""

    def __init__(self, bot):
        self.bot = bot
        self.reset_thread()

    def reset_thread(self):
        self.t = None
        self.last_message_at = datetime.datetime.now(datetime.timezone.utc)
        self.messages = []

    def remember(self, msg):
        self.messages.append({"role": "user", "content": msg})

    async def get_response(self):
        while True:
            try:
                completion = (await openai.chat.completions.create(model="gpt-3.5-turbo", messages=ALWAYS_REMIND + self.messages)).choices[0].message
            except BadRequestError as e:
                if e.code == "context_length_exceeded":
                    # brain bleed
                    del self.messages[1:len(self.messages)//2]
                else:
                    raise
            else:
                break
        await self.bot.get_channel(HOME_ID).typing()
        return completion.content

    async def respond(self):
        async with asyncio.TaskGroup() as tg:
            r = tg.create_task(self.get_response())
            tg.create_task(asyncio.sleep(2))
        t = r.result()
        self.messages.append({"role": "assistant", "content": t})
        await self.bot.get_channel(HOME_ID).send(t)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not (message.channel.id == HOME_ID and message.author != self.bot.user and not message.content.startswith("!")):
            return

        if (message.created_at - self.last_message_at) > datetime.timedelta(minutes=15):
            self.reset_thread()
        self.last_message_at = message.created_at

        self.messages.append({"role": "user", "name": re.sub(r"[^a-zA-Z0-9_-]+", "", message.author.global_name), "content": message.clean_content})
        if self.t:
            self.t.cancel()
        self.t = self.bot.loop.create_task(self.respond())
        await self.t


async def setup(bot):
    await bot.add_cog(EsobotPlace(bot))
