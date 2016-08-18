import humphrey
import pendulum
import time


class SeenHandler:
    cmds = ['!seen']
    admin = False
    help_topic = 'seen'
    help_text = ['Use \x02!seen <nick>\x02 to see the last time <nick> was active in the channel.',
                 'I track messages, actions, joins, parts, quits, and nick changes.']

    def __init__(self, bot: humphrey.IRCClient):
        bot.ee.on('ACTION', func=SeenHandler.watch_action)
        bot.ee.on('JOIN', func=SeenHandler.watch_join)
        bot.ee.on('NICK', func=SeenHandler.watch_nick)
        bot.ee.on('PART', func=SeenHandler.watch_part)
        bot.ee.on('PRIVMSG', func=SeenHandler.watch_privmsg)
        bot.ee.on('QUIT', func=SeenHandler.watch_quit)

    @staticmethod
    def get_config(bot):
        config_path = bot.c.path.with_name('_seen.json')
        return bot.c.__class__(config_path)

    def handle(self, sender, target, tokens, bot):
        if len(tokens) < 2:
            self.send_help(sender, bot)
            return
        nick = tokens[1]
        config = self.get_config(bot)
        nick_record = config.get(nick.lower())
        msgs = []
        if nick_record is None:
            msgs.append('I have not seen {} in {}'.format(nick, bot.c.get('irc:channel')))
        else:
            diff = pendulum.from_timestamp(nick_record['time']).diff_for_humans()
            msgs.append('I saw {} in {} {}'.format(nick, bot.c.get('irc:channel'), diff))
            msgs.append(nick_record['text'])
        if bot.is_irc_channel(target):
            response_target = target
        else:
            response_target = sender
        for msg in msgs:
            bot.send_privmsg(response_target, msg)

    @staticmethod
    def record_sighting(nick, text, bot):
        config = SeenHandler.get_config(bot)
        sighting = {'time': time.time(), 'text': text}
        config[nick.lower()] = sighting

    @staticmethod
    def watch_action(message: str, bot: humphrey.IRCClient):
        tokens = message.split(maxsplit=3)
        target = tokens[2]
        if not bot.is_irc_channel(target):
            return
        source = tokens[0].lstrip(':')
        nick, user, host = bot.parse_hostmask(source)
        text = tokens[3].split(maxsplit=1)[1].rstrip('\x01')
        SeenHandler.record_sighting(nick, '* {} {}'.format(nick, text), bot)

    @staticmethod
    def watch_join(message: str, bot: humphrey.IRCClient):
        tokens = message.split()
        source = tokens[0].lstrip(':')
        nick, user, host = bot.parse_hostmask(source)
        SeenHandler.record_sighting(nick, '- {} [{}] has joined {}'.format(nick, source, bot.c.get('irc:channel')), bot)

    @staticmethod
    def watch_nick(message: str, bot: humphrey.IRCClient):
        tokens = message.split()
        source = tokens[0].lstrip(':')
        nick, user, host = bot.parse_hostmask(source)
        SeenHandler.record_sighting(nick, '- {} is now known as {}'.format(nick, tokens[2].lstrip(':')), bot)

    @staticmethod
    def watch_part(message: str, bot: humphrey.IRCClient):
        tokens = message.split(maxsplit=3)
        source = tokens[0].lstrip(':')
        nick, user, host = bot.parse_hostmask(source)
        text = '- {} [{}] has left {}'.format(nick, source, bot.c.get('irc:channel'))
        if len(tokens) > 3:
            text = '{} [{}]'.format(text, tokens[3].lstrip(':'))
        SeenHandler.record_sighting(nick, text, bot)

    @staticmethod
    def watch_privmsg(message, bot):
        tokens = message.split(maxsplit=3)
        target = tokens[2]
        if not bot.is_irc_channel(target):
            return
        source = tokens[0].lstrip(':')
        nick, user, host = bot.parse_hostmask(source)
        text = tokens[3].lstrip(':')
        SeenHandler.record_sighting(nick, '<{}> {}'.format(nick, text), bot)

    @staticmethod
    def watch_quit(message: str, bot: humphrey.IRCClient):
        tokens = message.split(maxsplit=2)
        source = tokens[0].lstrip(':')
        nick, user, host = bot.parse_hostmask(source)
        SeenHandler.record_sighting(nick, '- {} [{}] has quit [{}]'.format(nick, source, tokens[2].lstrip(':')), bot)

    def send_help(self, target, bot):
        for line in self.help_text:
            bot.send_privmsg(target, line)
