#!/usr/bin/env python3

import asyncio
import humphrey
import importlib
import inspect
import pathlib
import sys
import traceback

config_file = pathlib.Path(__file__).resolve().with_name('_config.json')
gbot = humphrey.IRCClient(config_file)
gbot.debug = True
gbot.c.pretty = True
gbot.plug_commands = dict()
gbot.plug_commands_admin = dict()
gbot.help_text = dict()
gbot.help_text_admin = dict()


def load_plugin(plug_name, bot):
    loaded_commands = list()
    module_name = 'plugins.{}'.format(plug_name)
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            bot.log('** Error loading a plugin: {}'.format(exc))
            raise
    plugins = set(bot.c.get('plugins', list()))
    plugins.add(plug_name)
    bot.c['plugins'] = list(plugins)
    for plug_handler in inspect.getmembers(module, inspect.isclass):
        cls = plug_handler[1]
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

initialize_plugins(gbot)


@gbot.ee.on('PRIVMSG')
def handle_help(message, bot):
    tokens = message.split()
    source = tokens[0].lstrip(':')
    source_nick, _, _ = bot.parse_hostmask(source)
    if len(tokens) > 3 and tokens[3].lower() == ':!help':
        bot.log('** Handling !help')
        if len(tokens) < 5:
            m = 'Use \x02!help [<topic>]\x02 with one of these topics:'
            topics = list(bot.help_text.keys())
            if source_nick in bot.admins:
                topics += list(bot.help_text_admin.keys())
            m = '{} {}'.format(m, ', '.join(sorted(topics)))
            bot.send_privmsg(source_nick, m)
            return
        topic = tokens[4]
        lines = bot.help_text.get(topic)
        if lines is None and source_nick in bot.admins:
            lines = bot.help_text_admin.get(topic)
        if lines is not None:
            for line in lines:
                bot.send_privmsg(source_nick, line)
            return
        m = 'I don\'t know anything about {}.'.format(topic)
        bot.send_privmsg(source_nick, m)


@gbot.ee.on('PRIVMSG')
def handle_load(message, bot):
    tokens = message.split()
    source = tokens[0].lstrip(':')
    source_nick, _, _ = bot.parse_hostmask(source)
    if source_nick not in bot.admins:
        return
    if len(tokens) > 3 and tokens[3] == ':!load':
        bot.log('** Handling !load')
        if len(tokens) < 5:
            m = 'Please specify a plugin to load.'
            bot.send_privmsg(source_nick, m)
            return
        plug_name = tokens[4]
        try:
            commands = load_plugin(plug_name, bot)
            m = 'Loaded a plugin: {}'.format(plug_name)
            bot.send_privmsg(source_nick, m)
        except ImportError:
            m = 'Error loading plugin {}. Check the logs.'.format(plug_name)
            bot.send_privmsg(source_nick, m)
            return
        for command in commands:
            m = 'Loaded a command: {}'.format(command)
            bot.send_privmsg(source_nick, m)


@gbot.ee.on('PRIVMSG')
def dispatch_plugin_command(message, bot):
    tokens = message.split()
    source = tokens[0].lstrip(':')
    source_nick, _, _ = bot.parse_hostmask(source)
    cmd = tokens[3].lstrip(':').lower()
    handler = bot.plug_commands.get(cmd)
    if handler is None and source_nick in bot.admins:
        handler = bot.plug_commands_admin.get(cmd)
    if handler is not None:
        try:
            text = message.split(' :', 1)[1]
            handler.handle(source_nick, tokens[2], text.split(), bot)
        except Exception:
            m = 'Exception in {}. Check the logs.'.format(cmd)
            bot.log('** {}'.format(m))
            bot.log(traceback.format_exc())
            bot.send_privmsg(source_nick, m)


@gbot.ee.on('376')
def on_rpl_endofmotd(message, bot):
    password = bot.c.get('irc:nickservpass')
    if password is not None:
        bot.send_privmsg('nickserv', 'identify {}'.format(password))
    bot.out('JOIN {}'.format(bot.c['irc:channel']))


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    host = gbot.c.get('irc:host')
    port = gbot.c.get('irc:port')
    coro = loop.create_connection(gbot, host, port)
    loop.run_until_complete(coro)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        gbot.log('** Caught KeyboardInterrupt')
        loop.close()
