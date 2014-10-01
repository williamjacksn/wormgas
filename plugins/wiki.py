import time
import wikipedia


def is_irc_channel(s):
    return s and s[0] == u'#'


class WikipediaHandler(object):
    cmds = [u'!wiki']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        title = u' '.join(tokens[1:])
        try:
            summ = wikipedia.summary(title)
            summ = u' '.join(summ.splitlines())
        except wikipedia.exceptions.DisambiguationError as e:
            m = u'Disambiguation: [{}]'.format(u'], ['.join(e.options))
        except wikipedia.exceptions.PageError as e:
            m = str(e)
        else:
            m = summ

        if len(m) > 400:
            m = u'{}...'.format(m[:400])

        if not is_irc_channel(target):
            private.append(m)
            return public, private

        now = int(time.time())
        last = int(config.get(u'wiki:last', 0))
        wait = int(config.get(u'wiki:wait', 0))
        if last < now - wait:
            public.append(m)
            config.set(u'wiki:last', now)
        else:
            private.append(m)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            private.append(m)

        return public, private
