import asyncio
import discord
import logging
import requests

log = logging.getLogger(__name__)


class DiscordSyncHandler:
    cmds = ['!discord']
    admin = False
    help_topic = 'discord'
    help_text = [
        'Use \x02!discord users\x02 to see a list of users in the Discord channel.'
    ]

    def __init__(self, bot):
        self.bot = bot

        log.info('Attaching the Discord client to the bot')
        bot.discord = discord.Client()
        bot.discord_channel = None
        bot.discord.event(self.on_ready)
        bot.discord.event(self.on_message)
        asyncio.ensure_future(self._connect())

        bot.ee.on('PRIVMSG', func=self.watch_privmsg)

    @staticmethod
    def color(text, color, background=None):
        colors = {
            'white':     '00', 'yellow':      '08',
            'black':     '01', 'light_green': '09',
            'blue':      '02', 'cyan':        '10',
            'green':     '03', 'light_cyan':  '11',
            'light_red': '04', 'light_blue':  '12',
            'brown':     '05', 'pink':        '13',
            'purple':    '06', 'grey':        '14',
            'orange':    '07', 'light_grey':  '15'
        }
        if background is None:
            code = colors[color]
        else:
            code = '{},{}'.format(colors[color], colors[background])
        return '\x03{}{}\x03'.format(code, text)

    def status_dot(self, status):
        dot = '\u2022'
        dots = {
            discord.Status.online: self.color(dot, 'green'),
            discord.Status.idle: self.color(dot, 'yellow'),
            discord.Status.dnd: self.color(dot, 'light_red')
        }
        return dots[status]

    def handle(self, sender, _, tokens, bot):
        log.debug('Handling !discord')
        if len(tokens) < 2:
            self.send_help(sender, bot)
            return
        if tokens[1] == 'users':
            users = []
            for user in bot.discord_channel.server.members:
                if user.status is not discord.Status.offline:
                    nick = user.nick or user.name
                    users.append('{}{}'.format(self.status_dot(user.status), nick))
            while len(users) > 10:
                user_list = users[:10]
                users[0:10] = []
                bot.send_privmsg(sender, ' '.join(user_list))
            bot.send_privmsg(sender, ' '.join(users))

    def send_help(self, target, bot):
        for line in self.help_text:
            bot.send_privmsg(target, line)

    async def _connect(self):
        log.info('Attempting to connect to Discord')
        token = self.bot.c.get('discord:token')
        if token is None:
            log.warning('Set discord:token to use the discord_sync plugin')
            return
        await self.bot.discord.start(token)

    def _to_discord(self, message):
        log.debug('Sending to Discord: {!r}'.format(message))
        asyncio.ensure_future(self.bot.discord.send_message(self.bot.discord_channel, message))

    async def on_ready(self):
        log.info('Discord is ready')

        discord_server = None
        config_server = self.bot.c.get('discord:server')
        if config_server is None:
            log.warning('Set discord:server to the name of your Discord server')
            return
        for server in self.bot.discord.servers:
            if server.name == config_server:
                log.info('I am using the Discord server {!r}'.format(config_server))
                discord_server = server
        if discord_server is None:
            log.warning('I could not find a Discord server named {!r}'.format(config_server))
            return

        config_channel = self.bot.c.get('discord:channel')
        if config_channel is None:
            log.warning('Set discord:channel to the name of a public text channel')
            return
        config_channel = config_channel.lstrip('#')
        for channel in discord_server.channels:
            if channel.type is discord.ChannelType.text and channel.name == config_channel:
                log.info('I am using the Discord channel #{}'.format(channel.name))
                self.bot.discord_channel = channel
        if self.bot.discord_channel is None:
            log.warning('I could not find a public text channel named #{}'.format(config_channel))

    async def on_message(self, message):
        if self.bot.c.get('discord:sync_messages') is None:
            log.debug('Not syncing Discord messages')
            return
        if message.author == self.bot.discord.user:
            log.debug('Ignoring a Discord message from myself')
            return
        if message.author.bot:
            log.debug('Ignoring a Discord message from a bot')
            return
        if message.channel == self.bot.discord_channel:
            sender = message.author.nick or message.author.name
            m = '<{}> {}'.format(sender, message.clean_content)
            self.bot.send_privmsg(self.bot.c.get('irc:channel'), m)
        elif message.channel.is_private:
            log.info('I received a private Discord message from {!r}'.format(message.author))

    def watch_privmsg(self, message, bot):
        if bot.c.get('discord:sync_messages') is None:
            log.debug('Not syncing Discord messages')
            return
        tokens = message.split(maxsplit=3)
        target = tokens[2]
        if not bot.is_irc_channel(target):
            return
        source = tokens[0].lstrip(':')
        nick, user, host = bot.parse_hostmask(source)
        text = tokens[3].lstrip(':')
        webhook = bot.c.get('discord:webhook')
        if webhook is None:
            self._to_discord('<{}> {}'.format(nick, text))
        else:
            log.debug('Sending to webhook')
            requests.post(webhook, json={'content': text, 'username': '<{}>'.format(nick)})
