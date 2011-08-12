#!/usr/bin/python

# wormgas -- IRC bot for Rainwave (http://rainwave.cc)
# https://github.com/subtlecoolness/wormgas

import os
import random
import sqlite3
import time
from ircbot import SingleServerIRCBot

class wormgas(SingleServerIRCBot):

    def __init__(self):
        self.abspath = os.path.abspath(__file__)
        (self.path, self.file) = os.path.split(self.abspath)
        self.cdbh = sqlite3.connect("%s/config.sqlite" % self.path,
                                    isolation_level=None)
        self.ccur = self.cdbh.cursor()
        server = self.get_config("irc:server")
        nick = self.get_config("irc:nick")
        name = self.get_config("irc:name")
        SingleServerIRCBot.__init__(self, [(server, 6667)], nick, name)

    def __del__(self):
        self.cdbh.close()

    def handle_8ball(self):
        """Ask a question of the magic 8ball

        Returns: a list of strings"""

        rs = []
        answers = ("As I see it, yes.",
                   "Ask again later.",
                   "Better not tell you now.",
                   "Cannot predict now.",
                   "Concentrate and ask again.",
                   "Don't count on it.",
                   "It is certain.",
                   "It is decidedly so.",
                   "Most likely.",
                   "My reply is no.",
                   "My sources say no.",
                   "Outlook good.",
                   "Outlook not so good.",
                   "Reply hazy, try again.",
                   "Signs point to yes.",
                   "Very doubtful.",
                   "Without a doubt.",
                   "Yes.",
                   "Yes - definitely.",
                   "You may rely on it.")
        rs.append(random.choice(answers))
        return(rs)

    def handle_config(self, id=None, value=None):
        """View or change config values

        Arguments:
            id: the config_id you want to view or change (leave empty to show
                all available config_ids)
            value: the value to change config_id to (leave empty to view current
                value)

        Returns: a list of strings"""

        rs = []

        if id and value:
            self.set_config(id, value)
            rs.append("%s = %s" % (id, value))
        elif id:
            rs.append("%s = %s" % (id, self.get_config(id)))
        else:
            cids = []
            sql = "select distinct config_id from botconfig"
            self.ccur.execute(sql)
            for r in self.ccur:
                cids.append(r[0])
            mlcl = int(self.get_config("maxlength:configlist"))
            while len(cids) > mlcl:
                clist = cids[:mlcl]
                cids[0:mlcl] = []
                rs.append(", ".join(clist))
            rs.append(", ".join(cids))

        return(rs)

    def handle_flip(self):
        """Simulate a coin flip

        Returns: a list of strings"""

        rs = []
        answers = ("Heads!", "Tails!")
        rs.append(random.choice(answers))
        return(rs)

    def handle_help(self, priv=0, topic="all"):
        """Look up help about a topic

        Arguments:
            priv: integer, the privilege level of the person asking for help
            topic: string, the topic the person wants help about

        Returns: a list of strings"""

        rs = []

        if topic == "all":
            rs.append("Use \x02!help [<topic>]\x0f with one of these topics: "
                "8ball, flip, id, key")
            if priv > 0:
                rs.append("Level 1 administration topics: (none)")
            if priv > 1:
                rs.append("Level 2 administration topics: config, stop")
        elif topic == "8ball":
            rs.append("Use \x02!8ball\x0f to ask a question of the magic 8ball")
        elif topic == "config":
            if priv > 1:
                rs.append("Use \x02!config [<id>] [<value>]\x0f to display or "
                    "change configuration settings")
                rs.append("Leave off <value> to see the current setting, or "
                    "use a <value> of -1 to remove a setting")
                rs.append("Leave off <id> and <value> to see a list of all "
                    "available config ids")
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "flip":
            rs.append("Use \x02!flip\x0f to flip a coin")
        elif topic == "id":
            rs.append("Look up your Rainwave user id at "
                "http://rainwave.cc/auth/ and use \x02!id add <id>\x0f to tell "
                "me about it")
            rs.append("Use \x02!id drop\x0f to delete your user id and \x02!id "
                "show\x0f to see it")
        elif topic == "key":
            rs.append("Get an API key from http://rainwave.cc/auth/ and use "
                "\x02!key add <key>\x0f to tell me about it")
            rs.append("Use \x02!key drop\x0f to delete your key and \x02!key "
                "show\x0f to see it")
        elif topic == "stop":
            if priv > 1:
                rs.append("Use \x02!stop\x0f to shut down the bot")
            else:
                rs.append("You are not permitted to use this command")
        else:
            rs.append("I cannot help you with '%s'" % topic)

        return(rs)

    def handle_id(self, nick, mode, id):
        """Manage correlation between an IRC nick and Rainwave User ID

        Arguments:
            nick: string, IRC nick of person to manage id for
            mode: string, one of "help", "add", "drop", "show"
            id: numeric, the person's Rainwave User ID

        Returns: a list of strings"""

        rs = []

        # Make sure this nick is in the user_keys table

        stored_nick = None
        sql = "select distinct user_nick from user_keys where user_nick = ?"
        self.ccur.execute(sql, (nick,))
        for r in self.ccur:
            stored_nick = r[0]
        if not stored_nick:
            sql = "insert into user_keys (user_nick) values (?)"
            self.ccur.execute(sql, (nick,))

        if mode == "help":
            priv = self.get_config("privlevel:%s" % nick)
            rs = self.handle_help(priv, "id")
        elif mode == "add":
            sql = "update user_keys set user_id = ? where user_nick = ?"
            self.ccur.execute(sql, (id, nick))
            rs.append("I assigned the user id %s to nick '%s'" % (id, nick))
        elif mode == "drop":
            sql = "update user_keys set user_id = null where user_nick = ?"
            self.ccur.execute(sql, (nick,))
            rs.append("I dropped the user id for nick '%s'" % nick)
        elif mode == "show":
            stored_id = None
            sql = "select user_id from user_keys where user_nick = ?"
            self.ccur.execute(sql, (nick,))
            for r in self.ccur:
                stored_id = r[0]
            if stored_id:
                rs.append("The user id for nick '%s' is %s" % (nick, stored_id))
            else:
                rs.append("I do not have a user id for nick '%s'" % nick)

        return(rs)

    def handle_key(self, nick, mode="help", key=None):
        """Manage API keys
        
        Arguments:
            nick: string, IRC nick of person to manage key for
            mode: string, one of "help", "add", "drop", "show"
            key: string, the API key to add

        Returns: a list of strings"""

        rs = []

        # Make sure this nick is in the user_keys table

        stored_nick = None
        sql = "select distinct user_nick from user_keys where user_nick = ?"
        self.ccur.execute(sql, (nick,))
        for r in self.ccur:
            stored_nick = r[0]
        if not stored_nick:
            sql = "insert into user_keys (user_nick) values (?)"
            self.ccur.execute(sql, (nick,))

        if mode == "help":
            priv = self.get_config("privlevel:%s" % nick)
            rs = self.handle_help(priv, "key")
        elif mode == "add":
            sql = "update user_keys set user_key = ? where user_nick = ?"
            self.ccur.execute(sql, (key, nick))
            rs.append("I assigned the API key '%s' to nick '%s'" % (key, nick))
        elif mode == "drop":
            sql = "update user_keys set user_key = null where user_nick = ?"
            self.ccur.execute(sql, (nick,))
            rs.append("I dropped the API key for nick '%s'" % nick)
        elif mode == "show":
            stored_id = None
            sql = "select user_key from user_keys where user_nick = ?"
            self.ccur.execute(sql, (nick,))
            for r in self.ccur:
                stored_id = r[0]
            if stored_id:
                rs.append("The API key for nick '%s' is '%s'" %
                    (nick, stored_id))
            else:
                rs.append("I do not have an API key for nick '%s'" % nick)

        return(rs)

    def on_privmsg(self, c, e):
        """This method is called when a message is sent directly to the bot

        Arguments:
            c: the Connection object associated with this event
            e: the Event object"""

        nick = e.source().split("!")[0]
        priv = self.get_config("privlevel:%s" % nick)
        msg = e.arguments()[0].strip()
        cmdtokens = msg.split()
        try:
            cmd = cmdtokens[0]
        except IndexError:
            cmd = None

        rs = []

        # !8ball

        if "!8ball" in msg:
            rs = self.handle_8ball()

        # !config

        elif priv > 1 and cmd == "!config":
            try:
                id = cmdtokens[1]
            except IndexError:
                id = None
            try:
                value = cmdtokens[2]
            except IndexError:
                value = None
            rs = self.handle_config(id, value)

        # !flip

        elif "!flip" in msg:
            rs = self.handle_flip()

        # !help

        elif cmd == "!help":
            try:
                topic = cmdtokens[1]
            except IndexError:
                topic = "all"
            rs = self.handle_help(priv, topic)

        # !id

        elif cmd == "!id":
            try:
                mode = cmdtokens[1]
            except IndexError:
                mode = "help"
            try:
                id = cmdtokens[2]
            except IndexError:
                id = None
            rs = self.handle_id(nick, mode, id)

        # !key

        elif cmd == "!key":
            try:
                mode = cmdtokens[1]
            except IndexError:
                mode = "help"
            try:
                key = cmdtokens[2]
            except IndexError:
                key = None
            rs = self.handle_key(nick, mode, key)

        # !stop

        elif priv > 1 and "!stop" in msg:
            self.die()

        # Send responses

        for r in rs:
            c.privmsg(nick, r)

    def on_pubmsg(self, c, e):
        """This method is called when a message is sent to the channel the bot
        is on

        Arguments:
            c: the Connection object associated with this event
            e: the Event object"""

        nick = e.source().split("!")[0]
        priv = self.get_config("privlevel:%s" % nick)
        chan = e.target()
        msg = e.arguments()[0].strip()
        cmdtokens = msg.split()
        try:
            cmd = cmdtokens[0]
        except IndexError:
            cmd = None

        rs = []
        privrs = []

        # !8ball

        if "!8ball" in msg:
            ltb = int(self.get_config("lasttime:8ball"))
            wb = int(self.get_config("wait:8ball"))
            if ltb < time.time() - wb:
                rs = self.handle_8ball()
                if "again" not in rs[0]:
                    self.set_config("lasttime:8ball", time.time())
            else:
                privrs = self.handle_8ball()
                wait = ltb + wb - int(time.time())
                privrs.append("I am cooling down. You cannot use !8ball in %s "
                    "for another %s seconds." % (chan, wait))

        # !config

        elif priv > 1 and cmd == "!config":
            try:
                id = cmdtokens[1]
            except IndexError:
                id = None
            try:
                value = cmdtokens[2]
            except IndexError:
                value = None
            privrs = self.handle_config(id, value)

        # !flip

        elif "!flip" in msg:
            ltf = int(self.get_config("lasttime:flip"))
            wf = int(self.get_config("wait:flip"))
            if ltf < time.time() - wf:
                self.set_config("lasttime:flip", time.time())
                rs = self.handle_flip()
            else:
                privrs = self.handle_flip()
                wait = ltf + wf - int(time.time())
                privrs.append("I am cooling down. You cannot use !flip in %s "
                    "for another %s seconds." % (chan, wait))

        # !help

        elif cmd == "!help":
            try:
                topic = cmdtokens[1]
            except IndexError:
                topic = "all"
            privrs = self.handle_help(priv, topic)

        # !id

        elif cmd == "!id":
            try:
                mode = cmdtokens[1]
            except IndexError:
                mode = "help"
            try:
                id = cmdtokens[2]
            except IndexError:
                id = None
            privrs = self.handle_id(nick, mode, id)

        # !key

        elif cmd == "!key":
            try:
                mode = cmdtokens[1]
            except IndexError:
                mode = "help"
            try:
                key = cmdtokens[2]
            except IndexError:
                key = None
            privrs = self.handle_key(nick, mode, key)

        # !stop

        elif priv > 1 and "!stop" in msg:
            self.die()

        # Send responses

        for r in rs:
            c.privmsg(chan, "%s: %s" % (nick, r))

        for privr in privrs:
            c.privmsg(nick, privr)

    def on_welcome(self, c, e):
        """This method is called when the bot first connects to the server

        Arguments:
            c: the Connection object associated with this event
            e: the Event object"""

        passwd = self.get_config("irc:nickservpass")
        c.privmsg("nickserv", "identify %s" % passwd)
        c.join(self.get_config("irc:channel"))

    def print_to_log(self, msg):
        """Print to the log file

        Arguments:
            msg: string, the message to print to the log file (timestamp and
                 newline are not required)"""

        now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        logfile = open("%s.log" % (self.abspath,), "a")
        logfile.write("%s -- %s\n" % (now, msg))
        logfile.close()

    def get_config(self, id):
        """Read a value from the configuration database

        Arguments:
            id: the config_id that you want to read

        Returns: the config_value, or -1 if the config_id does not exist"""

        config_value = -1
        sql = "select config_value from botconfig where config_id = ?"
        self.ccur.execute(sql, (id,))
        for r in self.ccur:
            config_value = r[0]
        self.print_to_log("[INFO] get_config(): %s = %s" % (id, config_value))
        return(config_value)

    def set_config(self, id, value):
        """Set a configuration value in the database

        Arguments:
            id: the config_id to set
            value: the value to set it to"""

        cur_config_value = self.get_config(id)
        if value in (-1, "-1"):
            sql = "delete from botconfig where config_id = ?"
            self.ccur.execute(sql, (id,))
        elif cur_config_value in (-1, "-1"):
            sql = ("insert into botconfig (config_id, config_value) values "
                "(?, ?)")
            self.ccur.execute(sql, (id, value))
        else:
            sql = "update botconfig set config_value = ? where config_id = ?"
            self.ccur.execute(sql, (value, id))
        self.print_to_log("[INFO] set_config: %s = %s" % (id, value))

def main():
    bot = wormgas()
    bot.start()

if __name__ == "__main__":
    main()
