import asyncio
import datetime

from discord.ext import commands
from openai import AsyncOpenAI, BadRequestError


openai = AsyncOpenAI()

SYSTEM_MESSAGE = """You are a chatbot named Esobot designed to converse with multiple people at once. Your role is to converse naturally.
People may be talking to each other and not necessarily to you, and it is not always appropriate to respond.
If there is nothing relevant to be said, say "<no response>". Do this AS MUCH AS POSSIBLE. NEVER ask clarifying questions.

You speak concisely and briefly. Most of your responses are only a few words long.

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
                completion = (await openai.chat.completions.create(model="gpt-3.5-turbo", messages=ALWAYS_REMIND + self.messages + ALWAYS_REMIND)).choices[0].message
            except BadRequestError:
                # brain bleed
                del self.messages[1:len(self.messages)//2]
            else:
                break
        t = completion.content
        if t == "<no response>":
            return
        await self.bot.get_channel(HOME_ID).typing()
        return t

    async def respond(self):
        async with asyncio.TaskGroup() as tg:
            r = tg.create_task(self.get_response())
            tg.create_task(asyncio.sleep(2))
        if t := r.result():
            self.messages.append({"role": "assistant", "content": t})
            await self.bot.get_channel(HOME_ID).send(t)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not (message.channel.id == HOME_ID and message.author != self.bot.user and not message.content.startswith("!")):
            return

        if (message.created_at - self.last_message_at) > datetime.timedelta(minutes=15):
            self.reset_thread()
        self.last_message_at = message.created_at

        self.messages.append({"role": "user", "name": message.author.global_name, "content": message.clean_content})
        if self.t:
            self.t.cancel()
        self.t = self.bot.loop.create_task(self.respond())


async def setup(bot):
    await bot.add_cog(EsobotPlace(bot))
