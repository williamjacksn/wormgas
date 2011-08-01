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
        self.cdbh = sqlite3.connect("%s/config.sqlite" % (self.path,),
                                    isolation_level=None)
        self.ccur = self.cdbh.cursor()
        server = self.get_config("irc:server")
        nick = self.get_config("irc:nick")
        name = self.get_config("irc:name")
        SingleServerIRCBot.__init__(self, [(server, 6667)], nick, name)

    def __del__(self):
        self.cdbh.close()

    def handle_flip(self):

        rs = []
        rs.append(random.choice(("Heads!", "Tails!")))
        return(rs)

    def handle_help(self, priv=0, topic="all"):

        rs = []

        if topic == "all":
            rs.append("Use \x02!help [<topic>]\x0f with one of these topics: "
                "flip")
            if priv > 0:
                rs.append("Level 1 administration topics: (none)")
            if priv > 1:
                rs.append("Level 2 administration topics: stop")
        elif topic == "flip":
            rs.append("Use \x02!flip\x0f to flip a coin")
        elif topic == "stop":
            if priv > 1:
                rs.append("Use \x02!stop\x0f to shut down the bot")
            else:
                rs.append("You are not permitted to use this command")
        else:
            rs.append("I can't help you with '%s'" % topic)

        return(rs)


    def on_privmsg(self, c, e):
        # e.source() == nick!user@host
        # e.arguments()[0] == text of message

        nick = e.source().split("!")[0]
        priv = self.get_config("privlevel:%s" % nick)
        msg = e.arguments()[0].strip()
        cmdtokens = msg.split()

        rs = []

        # !flip

        if cmdtokens[0] == "!flip":
            rs = self.handle_flip()

        # !help

        elif cmdtokens[0] == "!help":
            try:
                topic = cmdtokens[1]
            except IndexError:
                topic = "all"
            rs = self.handle_help(priv, topic)

        # !stop

        elif (priv > 1) and (cmdtokens[0] == "!stop"):
            self.die()

        # Send responses

        for r in rs:
            c.privmsg(nick, r)

    def on_pubmsg(self, c, e):
        nick = e.source().split("!")[0]
        priv = self.get_config("privlevel:%s" % nick)
        chan = e.target()
        msg = e.arguments()[0].strip()
        cmdtokens = msg.split()

        rs = []
        privrs = []

        # !flip

        if cmdtokens[0] == "!flip":
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

        elif cmdtokens[0] == "!help":
            try:
                topic = cmdtokens[1]
            except IndexError:
                topic = "all"
            privrs = self.handle_help(priv, topic)

        # !stop

        elif (priv > 1) and (cmdtokens[0] == "!stop"):
            self.die()

        # Send responses

        for r in rs:
            c.privmsg(chan, r)

        for privr in privrs:
            c.privmsg(nick, privr)

    def on_welcome(self, c, e):
        passwd = self.get_config("irc:nickservpass")
        c.privmsg("nickserv", "identify %s" % passwd)
        c.join(self.get_config("irc:channel"))

    def print_to_log(self, msg):
        """Print to the log file, with UTC timestamp"""

        now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        logfile = open("%s.log" % (self.abspath,), "a")
        logfile.write("%s -- %s\n" % (now, msg))
        logfile.close()

    def get_config(self, id):
        """Read a value from the configuration database
        Returns the value, or -1 if the configuration id does not exist"""

        config_value = "-1"
        sql = "select config_value from botconfig where config_id = ?"
        self.ccur.execute(sql, (id,))
        for r in self.ccur:
            config_value = r[0]
        self.print_to_log("[INFO] get_config(): %s = %s" % (id, config_value))
        return(config_value)

    def set_config(self, id, value):
        cur_config_value = self.get_config(id)
        if value == -1:
            sql = "delete from botconfig where config_id = ?"
            self.ccur.execute(sql, (id,))
        elif cur_config_value == -1:
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
