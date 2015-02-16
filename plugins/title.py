import html
import urllib.error
import urllib.parse
import urllib.request


class TitleHandler:
    cmds = ['!title']
    admin = False
    help_topic = 'title'
    help_text = ['Use \x02!title <url>\x02 to look up the title of a URL.']

    def __init__(self, sbot):
        @sbot.ee.on('PRIVMSG')
        def find_titles(message, bot):
            tokens = message.split()
            source = tokens[0].lstrip(':')
            source_nick, _, _ = bot.parse_hostmask(source)
            cmd = tokens[3].lstrip(':').lower()
            builtin_commands = {'!load', '!help'}
            public_commands = set(bot.plug_commands.keys())
            admin_commands = set(bot.plug_commands_admin.keys())
            all_commands = builtin_commands | public_commands | admin_commands
            if cmd in all_commands:
                return

            urls = list()
            for token in tokens:
                try:
                    token = token.lstrip(':')
                    o = urllib.parse.urlparse(token)
                except ValueError:
                    bot.log('** Trouble looking for URLs')
                    continue
                if 'http' in o.scheme and o.netloc:
                    url = o.geturl()
                    bot.log('** Found a URL: {}'.format(url))
                    urls.append(url)

            for url in urls:
                self.handle(source_nick, tokens[2], ['!title', url], bot)

    @staticmethod
    def get_title(url):
        if url.endswith(('.mp3', '.ogg', '.pdf')):
            return None

        try:
            response = urllib.request.urlopen(url, timeout=5)
        except urllib.error.URLError:
            return None

        response_body = response.read()
        try:
            response_html = response_body.decode()
        except UnicodeDecodeError:
            response_html = response_body.decode('iso-8859-1')

        if '<title>' in response_html:
            tail = response_html.partition('<title>')[2]
            title = tail.partition('</title>')[0]
            return html.unescape(' '.join(title.split()))
        else:
            return None

    @classmethod
    def handle(cls, sender, target, tokens, bot):
        if len(tokens) < 2:
            for line in cls.help_text:
                bot.send_privmsg(sender, line)
            return

        title = cls.get_title(tokens[1])
        if title is None:
            return

        title = '[ {} ]'.format(title)
        if bot.is_irc_channel(target):
            bot.send_privmsg(target, '{}: {}'.format(sender, title))
        else:
            bot.send_privmsg(sender, title)
