import json
import urllib.request


class SlackHandler:
    cmds = []
    admin = False

    def __init__(self, sbot):
        @sbot.ee.on('PRIVMSG')
        def handle_privmsg(message, bot):
            tokens = message.split()
            source = tokens[0].lstrip(':')
            source_nick, _, _ = bot.parse_hostmask(source)
            target = tokens[2]
            text = message.split(' :', maxsplit=1)[1]
            if bot.is_irc_channel(target):
                url = bot.c.get('slack:url')
                if url is None:
                    bot.log('** Set slack:url to use the slack plugin')
                    return
                data_obj = {'text': text, 'username': '<{}>'.format(source_nick)}
                data = json.dumps(data_obj).encode()
                urllib.request.urlopen(url, data=data)
