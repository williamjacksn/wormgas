import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree


class WolframAlphaHandler:
    cmds = ['!wa']
    admin = False
    help_topic = 'wa'
    help_text = ['Use \x02!wa <query>\x02 to send a query to Wolfram Alpha.']

    @classmethod
    def handle(cls, sender, target, tokens, bot):
        if len(tokens) > 1:
            query = ' '.join(tokens[1:])
        else:
            for line in cls.help_text:
                bot.send_privmsg(sender, line)
            return

        result = cls._aux_wa(query, bot)

        if not bot.is_irc_channel(target):
            for line in result:
                bot.send_privmsg(sender, line)
            return

        now = int(time.time())
        last = int(bot.c.get('wolframalpha:last', 0))
        wait = int(bot.c.get('wolframalpha:wait', 0))
        if last < now - wait:
            for line in result[:5]:
                bot.send_privmsg(target, line)
            bot.c.set('wolframalpha:last', now)
        else:
            for line in result:
                bot.send_privmsg(sender, line)
            remaining = last + wait - now
            m = 'I am cooling down. You cannot use {}'.format(tokens[0])
            m = '{} in {} for another {} seconds.'.format(m, target, remaining)
            bot.send_privmsg(sender, m)

    @classmethod
    def _aux_wa(cls, query, bot):
        api_key = bot.c.get('wolframalpha:key')
        if api_key is None:
            return ['Wolfram Alpha API key not configured, cannot use !wa.']
        try:
            url = 'http://api.wolframalpha.com/v2/query'
            params = {
                'appid': api_key,
                'input': query,
                'format': 'plaintext'
            }
            data = urllib.parse.urlencode(params).encode()
            response = urllib.request.urlopen(url, data=data)
            if response.status == 200:
                body = response.read().decode()
            else:
                raise RuntimeError
            root = xml.etree.ElementTree.fromstring(body)
            if root.get('success') != 'true':
                return ['Wolfram Alpha found no answer.']
            plaintext = root.find('./pod[@primary="true"]/subpod/plaintext')
            if plaintext is None:
                for pod in root.findall('./pod'):
                    if pod.get('title') != 'Input interpretation':
                        plaintext = pod.find('./subpod/plaintext')
                        if plaintext is not None:
                            break
            if plaintext is None:
                return ['Error: could not find response.']
            if plaintext.text is None:
                return ['Error: empty response.']
            return plaintext.text.splitlines()
        except xml.etree.ElementTree.ParseError:
            return ['Error: could not parse response.']
