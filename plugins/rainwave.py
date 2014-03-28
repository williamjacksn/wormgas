import requests

chan_code_to_id = {
    u'rw': 1,
    u'game': 1,
    u'oc': 2,
    u'ocr': 2,
    u'vw': 3,
    u'mw': 3,
    u'cover': 3,
    u'covers': 3,
    u'bw': 4,
    u'chip': 4,
    u'ch': 4,
    u'ow': 5,
    u'omni': 5,
    u'all': 5
}

chan_id_to_name = [
    u'Rainwave network',
    u'Game channel',
    u'OCR channel',
    u'Covers channel',
    u'Chiptune channel',
    u'All channel'
]

def get_current_channel_for_id(listener_id, config):
    user_id = config.get(u'rw:user_id')
    key = config.get(u'rw:key')
    for chan_id in range(1, 6):
        d = rw_current_listeners(user_id, key, chan_id)
        for user in d.get(u'current_listeners').get(u'users'):
            if int(user.get(u'id')) == int(listener_id):
                return chan_id
    return None

def get_current_channel_for_nick(nick, config):
    user_id = config.get(u'rw:user_id')
    key = config.get(u'rw:key')
    d = rw_user_search(user_id, key, nick)
    return d.get(u'user').get(u'sid')

def get_id_for_nick(nick, config):
    listener_id = config.get_id_for_nick(nick)
    if listener_id is None:
        user_id = config.get(u'rw:user_id')
        key = config.get(u'rw:key')
        d = rw_user_search(user_id, key, nick)
        listener_id = d.get(u'user').get(u'user_id')
    return listener_id

def _call(path, params=dict()):
    base_url = u'http://rainwave.cc/api4/'
    url = u'{}{}'.format(base_url, path.lstrip(u'/'))
    d = requests.post(url, params=params)
    if d.ok:
        return d.json()
    d.raise_for_status()

def rw_current_listeners(user_id, key, sid):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid
    }
    return _call(u'current_listeners', params=params)

def rw_info(sid):
    params = {u'sid': sid}
    return _call(u'info', params=params)

def rw_listener(user_id, key, listener_id):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'id': listener_id
    }
    return _call(u'listener', params=params)

def rw_user_search(user_id, key, username):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'username': username
    }
    return _call(u'admin/user_search', params=params)

def is_irc_channel(s):
    return s and s[0] == u'#'


class NowPlayingHandler(object):
    cmds = [u'!nowplaying', u'!np', u'!npall', u'!npbw', u'!npch', u'!npchip',
        u'!npcover', u'!npcovers', u'!npgame', u'!npmw', u'!npoc', u'!npocr',
        u'!npomni', u'!npow', u'!nprw', u'!npvw']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        cmd = tokens[0].lower()

        chan_id = None

        if cmd in [u'!npgame', u'!nprw']:
            chan_id = 1

        if cmd in [u'!npoc', u'!npocr']:
            chan_id = 2

        if cmd in [u'!npcover', u'!npcovers', u'!npmw', u'!npvw']:
            chan_id = 3

        if cmd in [u'!npbw', u'!npch', u'!npchip']:
            chan_id = 4

        if cmd in [u'!npall', u'!npomni', u'!npow']:
            chan_id = 5

        if cmd in [u'!nowplaying', u'!np']:
            if len(tokens) > 1:
                chan_id = chan_code_to_id.get(tokens[1].lower())
            if chan_id is None:
                listener_id = get_id_for_nick(sender, config)
                chan_id = get_current_channel_for_id(listener_id, config)
            if chan_id is None:
                m = u'You are not tuned in and you did not specify a valid'
                m = u'{} channel code.'.format(m)
                private.append(m)
                return public, private

        m = u'Now playing on the {}:'.format(chan_id_to_name[int(chan_id)])
        d = rw_info(chan_id)
        song = d.get(u'sched_current').get(u'songs')[0]
        m = u'{} {} //'.format(m, song.get(u'albums')[0].get(u'name'))
        m = u'{} {} //'.format(m, song.get(u'title'))
        m = u'{} {}'.format(m, song.get(u'artist_tag'))

        if is_irc_channel(target):
            public.append(m)
        else:
            private.append(m)

        return public, private
