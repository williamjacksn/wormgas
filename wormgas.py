#!/usr/bin/python

# wormgas -- IRC bot for Rainwave (http://rainwave.cc)
# https://github.com/subtlecoolness/wormgas

import gzip
import json
import os
import psycopg2
import random
import sqlite3
import StringIO
import time
import urllib2
from ircbot import SingleServerIRCBot

class wormgas(SingleServerIRCBot):

    station_names = ("All Stations", "Rainwave",  "OCR Radio", "Mixwave",
        "Bitwave", "Omniwave")

    station_ids = {"rw": 1, "oc": 2, "mw": 3, "bw": 4, "ow": 5}

    def __init__(self):
        self.abspath = os.path.abspath(__file__)
        (self.path, self.file) = os.path.split(self.abspath)

        self.cdbh = sqlite3.connect("%s/config.sqlite" % self.path,
                                    isolation_level=None)
        self.ccur = self.cdbh.cursor()

        self.rdbh = psycopg2.connect("dbname='%s' user='%s' password='%s'" %
            (self.get_config("db:name"), self.get_config("db:user"),
            self.get_config("db:pass")))
        autocommit = psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
        self.rdbh.set_isolation_level(autocommit)
        self.rcur = self.rdbh.cursor()

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

    def handle_election(self, sid, elec_index):
        """Show the candidates in an election

        Returns: a list of sched_id, response strings"""

        rs = []

        url = "http://rainwave.cc/async/%s/get" % sid
        data = self.api_call(url)
        elec_index = int(elec_index)
        if elec_index == 0:
            r = "Current election on %s:" % self.station_names[sid]
        elif elec_index == 1:
            r = "Future election on %s:" % self.station_names[sid]
        else:
            rs.append(0)
            rs.extend(self.handle_help(topic="election"))
            return(rs)

        elec = data["sched_next"][elec_index]
        rs.append(elec["sched_id"])

        for i in (0, 1, 2):
            song = elec["song_data"][i]
            album = song["album_name"]
            title = song["song_title"]
            arts = song["artists"]
            art_list = []
            for art in arts:
                art_name = art["artist_name"]
                art_list.append(art_name)
            art_text = ", ".join(art_list)
            r = "%s \x02[%s]\x0f %s / %s by %s" % (r, i + 1, album, title,
                art_text)
            etype = song["elec_isrequest"]
            if etype in (3, 4):
                requestor = song["song_requestor"]
                r = "%s (requested by %s)" % (r, requestor)
            elif etype in (0, 1):
                r = "%s (conflict)" % r

        rs.append(r)
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
                "8ball, election, flip, id, key")
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
        elif topic == "election":
            rs.append("Use \x02!election <stationcode> [<election index>]\x0f "
                "to see the candidates in an election")
            rs.append("Short version is \x02!el<stationcode> [<election "
                "index>]\x0f")
            rs.append("Election indexes are 0 (current) and 1 (future), "
                "default is 0")
            rs.append("Station codes are \x02rw\x0f, \x02oc\x0f, \x02mw\x0f, "
                "\x02bw\x0f, or \x02ow\x0f")
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
        elif topic == "lookup":
            rs.append("Use \x02!lookup <stationcode> song|album <text>\x0f "
                "to search for songs or albums with <text> in the title")
            rs.append("Short version is \x02!lu<stationcode> song|album "
                "<text>\x0f")
            rs.append("Station codes are \x02rw\x0f, \x02oc\x0f, \x02mw\x0f, "
                "\x02bw\x0f, or \x02ow\x0f")
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

    def handle_lookup(self, sid, mode, text):
        """Look up (search for) a song or album

        Arguments:
            sid: station id of station to search
            mode: "song" or "album"
            text: text to search for"""

        rs = []

        if mode == "song":
            sql = ("select album_name, song_title, song_id from rw_songs join "
                "rw_albums using (album_id) where song_verified is true and "
                "rw_songs.sid = %s and song_title ilike %s order by "
                "album_name, song_title")
            self.rcur.execute(sql, (sid, "%%%s%%" % text))
            rows = self.rcur.fetchall()
            for row in rows:
                r = "%s: %s / %s [%s]" % (self.station_names[sid], row[0],
                    row[1], row[2])
                rs.append(r)
        elif mode == "album":
            sql = ("select album_name, album_id from rw_albums where "
                "album_verified is true and sid = %s and album_name ilike %s "
                "order by album_name")
            self.rcur.execute(sql, (sid, "%%%s%%" % text))
            rows = self.rcur.fetchall()
            for row in rows:
                r = "%s: %s [%s]" % (self.station_names[sid], row[0], row[1])
                rs.append(r)
        else:
            return(self.handle_help(topic="lookup"))

        # I only want 10 results

        unreported_results = 0
        while len(rs) > 10:
            rs.pop()
            unreported_results = unreported_results + 1

        # If I had to trim the results, be honest about it

        if unreported_results > 0:
            r = "%s: %s more result" % (self.station_names[sid],
                unreported_results)
            if unreported_results > 1:
                r = "%ss" % r
            r = ("%s. If you do not see what you are looking for, be more "
                "specific with your search." % r)
            rs.append(r)

        # If I did not find anything with this search, mention that

        if len(rs) < 1:
            r = "%s: No results." % self.station_names[sid]
            rs.append(r)
        elif unreported_results < 1:

            # I got between 1 and 10 results

            r = ("%s: Your search returned %s results." %
                (self.station_names[sid], len(rs)))
            rs.insert(0, r)

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

        # !elbw

        elif cmd == "!elbw":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(4, elec_index)
            rs.pop(0)

        # !election

        elif cmd == "!election":
            try:
                station = cmdtokens[1]
            except IndexError:
                station = "rw"
            try:
                elec_index = cmdtokens[2]
            except IndexError:
                elec_index = 0
            try:
                sid = self.station_ids[station]
            except KeyError:
                sid = 1
            rs = self.handle_election(sid, elec_index)
            rs.pop(0)

        # !elmw

        elif cmd == "!elmw":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(3, elec_index)
            rs.pop(0)

        # !eloc

        elif cmd == "!eloc":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(2, elec_index)
            rs.pop(0)

        # !elow

        elif cmd == "!elow":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(5, elec_index)
            rs.pop(0)

        # !elrw

        elif cmd == "!elrw":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(1, elec_index)
            rs.pop(0)

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

        # !lookup

        elif cmd == "!lookup":
            try:
                station = cmdtokens[1]
                sid = self.station_ids[station]
                mode = cmdtokens[2]
                text = cmdtokens[3]
                rs = self.handle_lookup(sid, mode, text)
            except IndexError, KeyError:
                rs = self.handle_help(topic="lookup")

        # !lubw

        elif cmd == "!lubw":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                rs = self.handle_lookup(4, mode, text)
            except IndexError:
                rs = self.handle_help(topic="lookup")

        # !lumw

        elif cmd == "!lumw":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                rs = self.handle_lookup(3, mode, text)
            except IndexError:
                rs = self.handle_help(topic="lookup")

        # !luoc

        elif cmd == "!luoc":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                rs = self.handle_lookup(2, mode, text)
            except IndexError:
                rs = self.handle_help(topic="lookup")

        # !luow

        elif cmd == "!luow":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                rs = self.handle_lookup(5, mode, text)
            except IndexError:
                rs = self.handle_help(topic="lookup")

        # !lurw

        elif cmd == "!lurw":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                rs = self.handle_lookup(1, mode, text)
            except IndexError:
                rs = self.handle_help(topic="lookup")

        # !stop

        elif priv > 1 and "!stop" in msg:
            self.die()

        # Send responses

        for r in rs:
            c.privmsg(nick, r.encode("utf8"))

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

        # !elbw

        elif cmd == "!elbw":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(4, elec_index)

            sched_id = rs.pop(0)
            if sched_id == 0:
                # There was a problem with the elec_index, send help in privmsg
                privrs.extend(rs)
                rs = []
            elif sched_id == self.get_config("el:4:%s" % elec_index):
                # !election has already been called for this election
                privrs.extend(rs)
                rs = []
                privrs.append("I am cooling down. You can only use !election "
                    "in %s once per election." % chan)
            else:
                self.set_config("el:4:%s" % elec_index, sched_id)

        # !election

        elif cmd == "!election":
            try:
                station = cmdtokens[1]
            except IndexError:
                station = "rw"
            try:
                elec_index = cmdtokens[2]
            except IndexError:
                elec_index = 0
            try:
                sid = self.station_ids[station]
            except KeyError:
                sid = 1
            rs = self.handle_election(sid, elec_index)

            sched_id = rs.pop(0)
            if sched_id == 0:
                # There was a problem with the elec_index, send help in privmsg
                privrs.extend(rs)
                rs = []
            elif sched_id == self.get_config("el:%s:%s" % (sid, elec_index)):
                # !election has already been called for this election
                privrs.extend(rs)
                rs = []
                privrs.append("I am cooling down. You can only use !election "
                    "in %s once per election." % chan)
            else:
                self.set_config("el:%s:%s" % (sid, elec_index), sched_id)

        # !elmw

        elif cmd == "!elmw":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(3, elec_index)

            sched_id = rs.pop(0)
            if sched_id == 0:
                # There was a problem with the elec_index, send help in privmsg
                privrs.extend(rs)
                rs = []
            elif sched_id == self.get_config("el:3:%s" % elec_index):
                # !election has already been called for this election
                privrs.extend(rs)
                rs = []
                privrs.append("I am cooling down. You can only use !election "
                    "in %s once per election." % chan)
            else:
                self.set_config("el:3:%s" % elec_index, sched_id)

        # !eloc

        elif cmd == "!eloc":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(2, elec_index)

            sched_id = rs.pop(0)
            if sched_id == 0:
                # There was a problem with the elec_index, send help in privmsg
                privrs.extend(rs)
                rs = []
            elif sched_id == self.get_config("el:2:%s" % elec_index):
                # !election has already been called for this election
                privrs.extend(rs)
                rs = []
                privrs.append("I am cooling down. You can only use !election "
                    "in %s once per election." % chan)
            else:
                self.set_config("el:2:%s" % elec_index, sched_id)

        # !elow

        elif cmd == "!elow":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(5, elec_index)

            sched_id = rs.pop(0)
            if sched_id == 0:
                # There was a problem with the elec_index, send help in privmsg
                privrs.extend(rs)
                rs = []
            elif sched_id == self.get_config("el:5:%s" % elec_index):
                # !election has already been called for this election
                privrs.extend(rs)
                rs = []
                privrs.append("I am cooling down. You can only use !election "
                    "in %s once per election." % chan)
            else:
                self.set_config("el:5:%s" % elec_index, sched_id)

        # !elrw

        elif cmd == "!elrw":
            try:
                elec_index = cmdtokens[1]
            except IndexError:
                elec_index = 0
            rs = self.handle_election(1, elec_index)

            sched_id = rs.pop(0)
            if sched_id == 0:
                # There was a problem with the elec_index, send help in privmsg
                privrs.extend(rs)
                rs = []
            elif sched_id == self.get_config("el:1:%s" % elec_index):
                # !election has already been called for this election
                privrs.extend(rs)
                rs = []
                privrs.append("I am cooling down. You can only use !election "
                    "in %s once per election." % chan)
            else:
                self.set_config("el:1:%s" % elec_index, sched_id)

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

        # !lookup

        elif cmd == "!lookup":
            try:
                station = cmdtokens[1]
                sid = self.station_ids[station]
                mode = cmdtokens[2]
                text = cmdtokens[3]
                privrs = self.handle_lookup(sid, mode, text)
            except IndexError, KeyError:
                privrs = self.handle_help(topic="lookup")

        # !lubw

        elif cmd == "!lubw":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                privrs = self.handle_lookup(4, mode, text)
            except IndexError:
                privrs = self.handle_help(topic="lookup")

        # !lumw

        elif cmd == "!lumw":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                privrs = self.handle_lookup(3, mode, text)
            except IndexError:
                privrs = self.handle_help(topic="lookup")

        # !luoc

        elif cmd == "!luoc":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                privrs = self.handle_lookup(2, mode, text)
            except IndexError:
                privrs = self.handle_help(topic="lookup")

        # !luow

        elif cmd == "!luow":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                privrs = self.handle_lookup(5, mode, text)
            except IndexError:
                privrs = self.handle_help(topic="lookup")

        # !lurw

        elif cmd == "!lurw":
            try:
                mode = cmdtokens[1]
                text = cmdtokens[2]
                privrs = self.handle_lookup(1, mode, text)
            except IndexError:
                privrs = self.handle_help(topic="lookup")

        # !stop

        elif priv > 1 and "!stop" in msg:
            self.die()

        # Send responses

        for r in rs:
            c.privmsg(chan, "%s: %s" % (nick, r.encode("utf8")))

        for privr in privrs:
            c.privmsg(nick, privr.encode("utf8"))

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

    def api_call(self, url, args=None):
        """Make a call to the Rainwave API

        Returns: the API response object"""

        request = urllib2.Request(url)
        request.add_header("user-agent",
            "wormgas/0.1 +http://github.com/subtlecoolness/wormgas")
        request.add_header("accept-encoding", "gzip")
        opener = urllib2.build_opener()
        gzipdata = opener.open(request).read()
        gzipstream = StringIO.StringIO(gzipdata)
        result = gzip.GzipFile(fileobj=gzipstream).read()
        data = json.loads(result)
        return(data)

def main():
    bot = wormgas()
    bot.start()

if __name__ == "__main__":
    main()
