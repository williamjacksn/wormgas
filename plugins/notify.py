import time
import urllib.parse
import urllib.request


class NotifyHandler:
    cmds = ['!notify']
    admin = False
    help_topic = 'notify'
    help_text = [('Use \x02!notify <secret_key>\x02 to get notified via IFTTT '
                  'when someone says your nick in the channel.'),
                 ('<secret_key> is the secret key from your IFTTT Maker '
                  'Channel.'),
                 ('I will send the Maker Channel event \'irc_mention\'. You '
                  'must set up an IFTTT recipe to act on that event.'),
                 ('In the Maker Channel event, value1 is the person who '
                  'mentioned your nick, value2 is the channel name, and value3 '
                  'is the full text of the message.'),
                 ('Use \x02!notify show\x02 to see the secret key I currently '
                  'have saved for you.'),
                 ('Use \x02!notify stop\x02 to delete your secret key and stop '
                  'receiving notifications.')]

    def __init__(self, bot):
        bot.ee.on('PRIVMSG', func=NotifyHandler.notify_on_match)
        bot.ee.on('ACTION', func=NotifyHandler.notify_on_match)

    @staticmethod
    def get_config(bot):
        config_path = bot.c.path.with_name('_notify.json')
        return bot.c.__class__(config_path)

    def handle(self, sender, _, tokens, bot):
        config = self.get_config(bot)
        if len(tokens) < 2:
            self.send_help(sender, bot)
            return
        nick = sender.lower()
        action = tokens[1]
        if action == 'show':
            return self.handle_show(nick, bot)
        elif action == 'stop':
            config.remove(nick)
            m = ('I will no longer notify you when someone says your nick in '
                 'the channel.')
        else:
            config[nick] = {'key': action, 'seen': int(time.time())}
            m = ('I will use the secret key {} to notify you when someone says '
                 'your nick in the channel.'.format(action))
        bot.send_privmsg(sender, m)

    def handle_show(self, nick, bot):
        config = self.get_config(bot)
        try:
            rec = config[nick]
        except IndexError:
            m = 'I do not have a secret key saved for you.'
            return bot.send_privmsg(nick, m)
        try:
            key = rec['key']
        except IndexError:
            m = 'I do not have a secret key saved for you.'
            return bot.send_privmsg(nick, m)
        m = 'Your secret key is ' + key
        return bot.send_privmsg(nick, m)

    @staticmethod
    def notify(key, sender, target, text):
        url = 'https://maker.ifttt.com/trigger/irc_mention/with/key/' + key
        params = {'value1': sender, 'value2': target, 'value3': text}
        data = urllib.parse.urlencode(params).encode()
        urllib.request.urlopen(url, data=data)

    @staticmethod
    def notify_on_match(message, bot):
        config = NotifyHandler.get_config(bot)
        source = message.split()[0].lstrip(':')
        sender, _, _ = bot.parse_hostmask(source)
        sender_low = sender.lower()
        if sender_low in config:
            bot.log('** Updating last seen time for ' + sender_low)
            rec = config[sender_low]
            rec['seen'] = int(time.time())
            config[sender_low] = rec
        text = message.split(' :', maxsplit=1)[1]
        for nick in config.keys():
            if nick in text.lower():
                seen = int(config[nick]['seen'])
                now = int(time.time())
                m = '** {} last seen at {}, it is currently {}'
                bot.log(m.format(nick, seen, now))
                if now > seen + 300:
                    target = message.split()[2]
                    if bot.is_irc_channel(target):
                        bot.log('** Sending notification to ' + nick)
                        key = config[nick]['key']
                        NotifyHandler.notify(key, sender, target, text)

    def send_help(self, target, bot):
        for line in self.help_text:
            bot.send_privmsg(target, line)
