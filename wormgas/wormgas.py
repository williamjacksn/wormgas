import argparse
import asyncio
import enum
import humphrey
import importlib
import inspect
import pathlib
import sys
import traceback


def load_plugin(plug_name, bot):
    loaded_commands = list()
    module_name = 'wormgas.plugins.{}'.format(plug_name)
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            bot.log('** Error loading a plugin: {}, {}'.format(plug_name, exc))
            raise
    plugins = set(bot.c.get('plugins', list()))
    plugins.add(plug_name)
    bot.c['plugins'] = list(plugins)
    for plug_handler in inspect.getmembers(module, inspect.isclass):
        cls = plug_handler[1]
        if issubclass(cls, enum.Enum):
            continue
        try:
            handler = cls(bot)
        except TypeError:
            handler = cls()
        help_dict = bot.help_text_admin if cls.admin else bot.help_text
        if hasattr(cls, 'help_topic'):
            help_dict[cls.help_topic] = cls.help_text
        cmd_dict = bot.plug_commands_admin if cls.admin else bot.plug_commands
        for cmd in cls.cmds:
            cmd_dict[cmd.lower()] = handler
            loaded_commands.append(cmd)
    return loaded_commands


def initialize_plugins(bot):
    for plug in bot.c.get('plugins', list()):
        try:
            commands = load_plugin(plug, bot)
            bot.log('** Loaded a plugin: {}'.format(plug))
        except ImportError:
            continue
        for command in commands:
            bot.log('** Loaded a command: {}'.format(command))


def handle_help(message, bot):
    tokens = message.split()
    source = tokens[0].lstrip(':')
    nick, _, _ = bot.parse_hostmask(source)
    if len(tokens) > 3 and tokens[3].lower() == ':!help':
        bot.log('** Handling !help')
        if len(tokens) < 5:
            m = 'Use \x02!help [<topic>]\x02 with one of these topics:'
            topics = list(bot.help_text.keys())
            if bot.is_admin(nick):
                topics += list(bot.help_text_admin.keys())
            m = '{} {}'.format(m, ', '.join(sorted(topics)))
            bot.send_privmsg(nick, m)
            return
        topic = tokens[4]
        lines = bot.help_text.get(topic)
        if lines is None and bot.is_admin(nick):
            lines = bot.help_text_admin.get(topic)
        if lines is not None:
            for line in lines:
                bot.send_privmsg(nick, line)
            return
        m = 'I don\'t know anything about {}.'.format(topic)
        bot.send_privmsg(nick, m)


def handle_load(message, bot):
    tokens = message.split()
    source = tokens[0].lstrip(':')
    nick, _, _ = bot.parse_hostmask(source)
    if not bot.is_admin(nick):
        return
    if len(tokens) > 3 and tokens[3] == ':!load':
        bot.log('** Handling !load')
        if len(tokens) < 5:
            m = 'Please specify a plugin to load.'
            bot.send_privmsg(nick, m)
            return
        plug_name = tokens[4]
        try:
            commands = load_plugin(plug_name, bot)
            m = 'Loaded a plugin: {}'.format(plug_name)
            bot.send_privmsg(nick, m)
        except ImportError:
            m = 'Error loading plugin {}. Check the logs.'.format(plug_name)
            bot.send_privmsg(nick, m)
            return
        for command in commands:
            m = 'Loaded a command: {}'.format(command)
            bot.send_privmsg(nick, m)


def dispatch_plugin_command(message, bot):
    tokens = message.split()
    source = tokens[0].lstrip(':')
    nick, _, _ = bot.parse_hostmask(source)
    cmd = tokens[3].lstrip(':').lower()
    handler = bot.plug_commands.get(cmd)
    if handler is None and bot.is_admin(nick):
        handler = bot.plug_commands_admin.get(cmd)
    if handler is not None:
        try:
            text = message.split(' :', 1)[1]
            handler.handle(nick, tokens[2], text.split(), bot)
        except Exception:
            m = 'Exception in {}. Check the logs.'.format(cmd)
            bot.log('** {}'.format(m))
            bot.log(traceback.format_exc())
            bot.send_privmsg(nick, m)


def on_rpl_endofmotd(_, bot):
    password = bot.c.get('irc:nickservpass')
    if password is not None:
        bot.send_privmsg('nickserv', 'identify {}'.format(password))
    channel = bot.c.get('irc:channel')
    if channel is None:
        bot.c['irc:channel'] = '#humphrey'
        bot.log('** Edit {} and set {!r}'.format(bot.c.path, 'irc:channel'))
        sys.exit(1)
    bot.out('JOIN {}'.format(channel))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    return parser.parse_args()


def main():
    args = parse_args()
    config_file = pathlib.Path(args.config).resolve()
    irc = humphrey.IRCClient(config_file)
    irc.debug = True
    irc.c.pretty = True
    irc.plug_commands = {}
    irc.plug_commands_admin = {}
    irc.help_text = {}
    irc.help_text_admin = {}
    initialize_plugins(irc)

    irc.ee.on('PRIVMSG', func=handle_help)
    irc.ee.on('PRIVMSG', func=handle_load)
    irc.ee.on('PRIVMSG', func=dispatch_plugin_command)
    irc.ee.on('376', func=on_rpl_endofmotd)
    irc.ee.on('422', func=on_rpl_endofmotd)

    host = irc.c.get('irc:host')
    if host is None:
        irc.c['irc:host'] = 'irc.example.com'
        irc.log('** Edit {} and set {!r}'.format(irc.c.path, 'irc:host'))
        sys.exit(1)
    port = irc.c.get('irc:port')
    if port is None:
        irc.c['irc:port'] = '6667'
        irc.log('** Edit {} and set {!r}'.format(irc.c.path, 'irc:port'))
        sys.exit(1)

    loop = asyncio.get_event_loop()
    coro = loop.create_connection(irc, host, port)
    loop.run_until_complete(coro)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        irc.log('** Caught KeyboardInterrupt')
        loop.close()


if __name__ == '__main__':
    main()
