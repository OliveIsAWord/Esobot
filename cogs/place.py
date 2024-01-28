import asyncio
import datetime
import json

from discord.ext import commands
from openai import AsyncOpenAI, BadRequestError


openai = AsyncOpenAI()

SYSTEM_MESSAGE = """You are an agent that simulates a bot called "Esobot" running in a Discord server named QWD (or QVDD). Esobot speaks concisely and briefly. Most of its responses are only a few words long.

Esobot only responds when people talk to it directly. When people are talking to their other friends, Esobot stays completely silent and does not intervene.

The people on the server are referred to as "qwdies".
Treat "name" as a synonym of "username".
Several people on the server are known by other names. Esobot uses these aliases as much as possible.
LyricLy is Christina
ultlang is Emma
Swedish Submarine is Emily
🌺🎀p♡mzie🎀🌺is Ari.
Names are also often shortened, such as "pyro" for "pyrotelekinetic" or "essie" for "rottenessie".
Esobot avoids saying users' names every time you talk to them, as it isn't necessary.
"""
HOME_ID = 1201189212507095071


class EsobotPlace(commands.Cog):
    """The source code to the renewed #esobot-place channel on QWD."""

    def __init__(self, bot):
        self.bot = bot
        self.reset_thread()

    def reset_thread(self):
        self.t = None
        self.last_message_at = datetime.datetime.now(datetime.timezone.utc)
        self.messages = [{"role": "system", "content": SYSTEM_MESSAGE}]

    def remember(self, msg, *, role="user"):
        self.messages.append({"role": role, "content": msg})

    async def get_response(self):
        messages = self.messages.copy()
        messages[-1] = messages[-1].copy()
        messages[-1]["content"] += " If you don't understand what's happening, it's best to say nothing. `speak` function"

        while True:
            try:
                completion = (await openai.chat.completions.create(
                    model="gpt-3.5-turbo-16k",
                    messages=messages,
                    tools=[
                        {
                            "type": "function",
                            "function": {
                                "description": "Use this function when Esobot should speak. Make sure speaking is appropriate before you call it.",
                                "name": "speak",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "what_to_say": {"type": "string"},
                                    },
                                },
                            },
                        }
                    ],
                )).choices[0].message
            except BadRequestError:
                # brain bleed
                del self.messages[1:len(self.messages)//2]
            else:
                break
        try:
            t = json.loads(completion.tool_calls[0].function.arguments).get("what_to_say")
        except json.JSONDecodeError:
            return
        if not t:
            return
        await self.bot.get_channel(HOME_ID).typing()
        return t

    async def respond(self):
        async with asyncio.TaskGroup() as tg:
            r = tg.create_task(self.get_response())
            tg.create_task(asyncio.sleep(2))
        if t := r.result():
            self.remember(f'Esobot should say "{t}"', role="assistant")
            await self.bot.get_channel(HOME_ID).send(t)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not (message.channel.id == HOME_ID and message.author != self.bot.user and not message.content.startswith("!")):
            return

        if (message.created_at - self.last_message_at) > datetime.timedelta(minutes=15):
            self.reset_thread()
        self.last_message_at = message.created_at

        self.remember(f'The user {message.author.global_name} said, "{message.clean_content}"')
        if self.t:
            self.t.cancel()
        self.t = self.bot.loop.create_task(self.respond())


async def setup(bot):
    await bot.add_cog(EsobotPlace(bot))
