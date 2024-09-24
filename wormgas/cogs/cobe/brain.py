# Copyright (C) 2011 Peter Teichman
# Edited 2015-02-11 for simplicity and Python 3 compatibility by William Jackson

import collections
import os
import pprint
import random
import re
import sqlite3
import time

from . import scoring
from . import tokenizers


class CobeError(Exception):
    pass


class Brain:
    """The main interface for Cobe."""

    # use an empty string to denote the start/end of a chain
    END_TOKEN = ""

    # use a magic token id for (single) whitespace, so space is never
    # in the tokens table
    SPACE_TOKEN_ID = -1

    def __init__(self, filename):
        """Construct a brain for the specified filename. If that file
        doesn't exist, it will be initialized with the default brain
        settings."""
        if not os.path.exists(filename):
            Brain.init(filename)

        self.graph = graph = Graph(sqlite3.connect(filename, isolation_level=None))

        version = graph.get_info_text('version')
        if version != '2':
            raise CobeError('cannot read a version {} brain'.format(version))

        self.order = int(graph.get_info_text('order'))

        self.scorer = scoring.ScorerGroup()
        self.scorer.add_scorer(1.0, scoring.CobeScorer())
        self.scorer.add_scorer(-1.0, scoring.IdentityScorer())

        tokenizer_name = graph.get_info_text('tokenizer')
        if tokenizer_name == 'MegaHAL':
            self.tokenizer = tokenizers.MegaHALTokenizer()
        else:
            self.tokenizer = tokenizers.CobeTokenizer()

        self.stemmer = tokenizers.CobeStemmer()

        self._end_token_id = \
            graph.get_token_by_text(self.END_TOKEN, create=True)

        self._end_context = [self._end_token_id] * self.order
        self._end_context_id = graph.get_node_by_tokens(self._end_context)

        self._learning = False

    def start_batch_learning(self):
        """Begin a series of batch learn operations. Data will not be
        committed to the database until stop_batch_learning is
        called. Learn text using the normal learn(text) method."""
        self._learning = True

        self.graph.cursor().execute('PRAGMA journal_mode=memory')
        self.graph.drop_reply_indexes()

    def stop_batch_learning(self):
        """Finish a series of batch learn operations."""
        self._learning = False

        self.graph.commit()
        self.graph.cursor().execute('PRAGMA journal_mode=truncate')
        self.graph.ensure_indexes()

    def del_stemmer(self):
        self.stemmer = None

        self.graph.delete_token_stems()

        self.graph.set_info_text('stemmer', None)
        self.graph.commit()

    def set_stemmer(self, language):
        self.stemmer = tokenizers.CobeStemmer()

        self.graph.delete_token_stems()
        self.graph.update_token_stems(self.stemmer)

        self.graph.set_info_text('stemmer', language)
        self.graph.commit()

    def learn(self, text):
        """Learn a string of text."""
        tokens = self.tokenizer.split(text)

        self._learn_tokens(tokens)

    def _to_edges(self, tokens):
        """This is an iterator that returns the nodes of our graph:
"This is a test" -> "None This" "This is" "is a" "a test" "test None"

Each is annotated with a boolean that tracks whether whitespace was
found between the two tokens."""
        # prepend self.order Nones
        chain = self._end_context + tokens + self._end_context

        has_space = False

        context = []

        for chain_item in chain:
            context.append(chain_item)

            if len(context) == self.order:
                if chain_item == self.SPACE_TOKEN_ID:
                    context.pop()
                    has_space = True
                    continue

                yield tuple(context), has_space

                context.pop(0)
                has_space = False

    @staticmethod
    def _to_graph(contexts):
        """This is an iterator that returns each edge of our graph
with its two nodes"""
        prev = None

        for context in contexts:
            if prev is None:
                prev = context
                continue

            yield prev[0], context[1], context[0]
            prev = context

    def _learn_tokens(self, tokens):
        token_count = len([token for token in tokens if token != " "])
        if token_count < 3:
            return

        # create each of the non-whitespace tokens
        token_ids = []
        for text in tokens:
            if text == ' ':
                token_ids.append(self.SPACE_TOKEN_ID)
                continue

            token_id = self.graph.get_token_by_text(text, create=True,
                                                    stemmer=self.stemmer)
            token_ids.append(token_id)

        edges = list(self._to_edges(token_ids))

        prev_id = None
        for prev, has_space, nxt in self._to_graph(edges):
            if prev_id is None:
                prev_id = self.graph.get_node_by_tokens(prev)
            next_id = self.graph.get_node_by_tokens(nxt)

            self.graph.add_edge(prev_id, next_id, has_space)
            prev_id = next_id

        if not self._learning:
            self.graph.commit()

    def reply(self, text):
        """Reply to a string of text."""

        tokens = self.tokenizer.split(text)
        input_ids = map(self.graph.get_token_by_text, tokens)

        # filter out unknown words and non-words from the potential pivots
        pivot_set = self._filter_pivots(input_ids)

        # Conflate the known ids with the stems of their words
        if self.stemmer is not None:
            self._conflate_stems(pivot_set, tokens)

        # If we didn't recognize any word tokens in the input, pick
        # something random from the database and babble.
        if len(pivot_set) == 0:
            pivot_set = self._babble()

        score_cache = {}

        best_score = -1.0
        best_reply = None

        # loop for half a second
        start = time.time()
        end = start + 0.5
        count = 0

        while time.time() < end:
            candidate = self._generate_reply(pivot_set)

            if candidate is None:
                continue

            count += 1
            edges, pivot_node = candidate
            reply = Reply(self.graph, tokens, input_ids, pivot_node, edges)

            key = self._get_reply_key(reply)
            if key not in score_cache:
                score = self.scorer.score(reply)
                score_cache[key] = score
            else:
                # skip scoring, we've already seen this reply
                score = -1

            if score > best_score:
                best_reply = reply
                best_score = score

        if best_reply is None:
            # we couldn't find any pivot words in _babble(), so we're
            # working with an essentially empty brain. Use the classic
            # MegaHAL reply:
            return 'I don\'t know enough to answer you yet!'

        self.scorer.end()

        # look up the words for these tokens
        text = best_reply.to_text()

        return text

    def _conflate_stems(self, pivot_set, tokens):
        for token in tokens:
            stem_ids = self.graph.get_token_stem_id(self.stemmer.stem(token))
            if len(stem_ids) == 0:
                continue

            # add the tuple of stems to the pivot set, and then
            # remove the individual token_ids
            pivot_set.add(stem_ids)

            for stem_id in stem_ids:
                try:
                    pivot_set.remove(stem_id)
                except KeyError:
                    pass

    @staticmethod
    def _get_reply_key(reply):
        return tuple([edge.edge_id for edge in reply.edges])

    def _babble(self):
        token_ids = []
        for _ in range(5):
            # Generate a few random tokens that can be used as pivots
            token_id = self.graph.get_random_token()

            if token_id is not None:
                token_ids.append(token_id)

        return token_ids

    def _filter_pivots(self, pivots):
        # remove pivots that might not give good results
        tokens = set(filter(None, pivots))

        filtered = self.graph.get_word_tokens(tokens)
        if len(filtered) == 0:
            filtered = self.graph.get_tokens(tokens)

        return set(filtered)

    @staticmethod
    def _choose_pivot(pivot_ids):
        pivot = random.choice(tuple(pivot_ids))

        if isinstance(pivot, tuple):
            # the input word was stemmed to several things
            pivot = random.choice(pivot)

        return pivot

    def _generate_reply(self, pivot_ids):
        if len(pivot_ids) == 0:
            return

        # generate a reply containing one of token_ids
        pivot_id = self._choose_pivot(pivot_ids)
        node = self.graph.get_random_node_with_token(pivot_id)

        if node is None:
            return

        edges = collections.deque()

        self.graph.walk(node, self._end_context_id, 1, edges.append)
        self.graph.walk(node, self._end_context_id, 0, edges.appendleft)

        if len(edges):
            return edges, node

    @staticmethod
    def init(filename, order=3, tokenizer=None):
        """Initialize a brain. This brain's file must not already exist.

Keyword arguments:
order -- Order of the forward/reverse Markov chains (integer)
tokenizer -- One of Cobe, MegaHAL (default Cobe). See documentation
             for cobe.tokenizers for details. (string)"""
        if tokenizer is None:
            tokenizer = 'Cobe'

        if tokenizer not in ('Cobe', 'MegaHAL'):
            tokenizer = 'Cobe'

        graph = Graph(sqlite3.connect(filename))
        graph.init(order, tokenizer)


class Reply:
    """Provide useful support for scoring functions"""
    def __init__(self, graph, tokens, token_ids, pivot_node, edges):
        self.graph = graph
        self.tokens = tokens
        self.token_ids = token_ids
        self.pivot_node = pivot_node
        self.edges = edges

    def to_graph(self):
        text = []
        for edge in self.edges:
            text.append(edge.pretty())

        return pprint.pformat(text)

    def to_text(self):
        text = []
        for edge in self.edges:
            text.append(edge.get_prev_word())
            if edge.has_space:
                text.append(' ')
        return ''.join(text)


class Edge:
    def __init__(self, graph, edge_id, prev, nxt, has_space, count):
        self.graph = graph

        self.edge_id = edge_id
        self.prev = prev
        self.next = nxt
        self.has_space = has_space
        self.count = count

    def get_prev_word(self):
        # get the last word in the prev context
        return self.graph.get_word_by_node(self.prev)

    def get_prev_token(self):
        # get the last token in the prev context
        return self.graph.get_token_by_node(self.prev)

    def pretty(self):
        prev = '|'.join(self.graph.get_node_text(self.prev))
        nxt = '|'.join(self.graph.get_node_text(self.next))

        return '{} -> {} ({} -> {})'.format(prev, nxt, self.prev, self.next)


class Graph:
    """A special-purpose graph class, stored in a sqlite3 database"""
    def __init__(self, conn, run_migrations=True):
        self._conn = conn
        conn.row_factory = sqlite3.Row

        if self.is_initted():
            if run_migrations:
                self._run_migrations()

            self.order = int(self.get_info_text('order'))

            self._all_tokens = ','.join(['token%d_id' % i
                                         for i in range(self.order)])
            self._all_tokens_args = ' AND '.join(
                ['token%d_id = ?' % i for i in range(self.order)])
            self._all_tokens_q = ','.join(['?' for _ in range(self.order)])
            self._last_token = 'token%d_id' % (self.order - 1)

            # Use a 10M cache by default. This speeds replies quite a bit.
            c = self.cursor()
            c.execute('PRAGMA cache_size=10000')

            # Each of these speed-for-reliability trade-offs is useful for
            # bulk learning.
            c.execute('PRAGMA journal_mode=truncate')
            c.execute('PRAGMA temp_store=memory')
            c.execute('PRAGMA synchronous=OFF')

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def close(self):
        return self._conn.close()

    def is_initted(self):
        try:
            self.get_info_text('order')
            return True
        except sqlite3.OperationalError:
            return False

    def set_info_text(self, attribute, text):
        c = self.cursor()

        if text is None:
            q = 'DELETE FROM info WHERE attribute = ?'
            c.execute(q, (attribute,))
        else:
            q = 'UPDATE info SET text = ? WHERE attribute = ?'
            c.execute(q, (text, attribute))

            if c.rowcount == 0:
                q = 'INSERT INTO info (attribute, text) VALUES (?, ?)'
                c.execute(q, (attribute, text))

    def get_info_text(self, attribute, default=None, text_factory=None):
        c = self.cursor()

        old_text_factory = self._conn.text_factory
        if text_factory is not None:
            self._conn.text_factory = text_factory

        q = 'SELECT text FROM info WHERE attribute = ?'
        row = c.execute(q, (attribute,)).fetchone()

        if text_factory is not None:
            self._conn.text_factory = old_text_factory

        if row:
            return row[0]

        return default

    @staticmethod
    def get_seq_expr(seq):
        # Format the sequence seq as (item1, item2, item2) as appropriate
        # for an IN () clause in SQL
        if len(seq) == 1:
            # Grab the first item from seq. Use an iterator so this works
            # with sets as well as lists.
            for item in seq:
                return '({})'.format(item)

        return str(tuple(seq))

    def get_token_by_text(self, text, create=False, stemmer=None):
        c = self.cursor()

        q = 'SELECT id FROM tokens WHERE text = ?'

        row = c.execute(q, (text,)).fetchone()
        if row:
            return row[0]
        elif create:
            q = 'INSERT INTO tokens (text, is_word) VALUES (?, ?)'

            is_word = bool(re.search(r'\w', text, re.UNICODE))
            c.execute(q, (text, is_word))

            token_id = c.lastrowid
            if is_word and stemmer is not None:
                self.insert_stem(token_id, stemmer.stem(text))

            return token_id

    def insert_stem(self, token_id, stem):
        q = 'INSERT INTO token_stems (token_id, stem) VALUES (?, ?)'
        self._conn.execute(q, (token_id, stem))

    def get_token_by_id(self, token_id):
        q = 'SELECT text FROM tokens WHERE id = ?'
        row = self._conn.execute(q, (token_id,)).fetchone()
        if row:
            return row[0]

    def get_token_stem_id(self, stem):
        q = 'SELECT token_id FROM token_stems WHERE token_stems.stem = ?'
        rows = self._conn.execute(q, (stem,))
        if rows:
            return tuple(val[0] for val in rows)

    def get_word_by_node(self, node_id):
        # return the last word in the node
        q = 'SELECT tokens.text FROM nodes, tokens WHERE nodes.id = ? AND %s = tokens.id' % self._last_token

        row = self._conn.execute(q, (node_id,)).fetchone()
        if row:
            return row[0]

    def get_token_by_node(self, node_id):
        # return the last token in the node
        q = 'SELECT tokens.id FROM nodes, tokens WHERE nodes.id = ? AND %s = tokens.id' % self._last_token

        row = self._conn.execute(q, (node_id,)).fetchone()
        if row:
            return row[0]

    def get_word_tokens(self, token_ids):
        q = 'SELECT id FROM tokens WHERE id IN %s AND is_word = 1' % self.get_seq_expr(token_ids)

        rows = self._conn.execute(q)
        if rows:
            return [row['id'] for row in rows]

        return []

    def get_tokens(self, token_ids):
        q = 'SELECT id FROM tokens WHERE id IN %s' % self.get_seq_expr(token_ids)

        rows = self._conn.execute(q)
        if rows:
            return [row['id'] for row in rows]

        return []

    def get_node_by_tokens(self, tokens):
        c = self.cursor()

        q = 'SELECT id FROM nodes WHERE %s' % self._all_tokens_args

        row = c.execute(q, tokens).fetchone()
        if row:
            return int(row[0])

        # if not found, create the node
        q = 'INSERT INTO nodes (count, %s) VALUES (0, %s)' % (self._all_tokens, self._all_tokens_q)
        c.execute(q, tokens)
        return c.lastrowid

    def get_node_tokens(self, node_id):
        q = 'SELECT %s FROM nodes WHERE id = ?' % self._all_tokens

        row = self._conn.execute(q, (node_id,)).fetchone()
        assert row is not None

        return tuple(row)

    def get_node_text(self, node_id):
        tokens = self.get_node_tokens(node_id)
        return [self.get_token_by_id(token_id) for token_id in tokens]

    def get_random_token(self):
        # token 1 is the end_token_id, so we want to generate a random token
        # id from 2..max(id) inclusive.
        q = 'SELECT (abs(random()) % (MAX(id)-1)) + 2 FROM tokens'
        row = self._conn.execute(q).fetchone()
        if row:
            return row[0]

    def get_random_node_with_token(self, token_id):
        c = self.cursor()

        q = '''
            SELECT id FROM nodes WHERE token0_id = ? LIMIT 1
            OFFSET abs(random())%(SELECT count(*) FROM nodes WHERE token0_id = ?)
        '''

        row = c.execute(q, (token_id, token_id)).fetchone()
        if row:
            return int(row[0])

    def add_edge(self, prev_node, next_node, has_space):
        c = self.cursor()

        assert isinstance(has_space, bool)

        update_q = 'UPDATE edges SET count = count + 1 WHERE prev_node = ? AND next_node = ? AND has_space = ?'

        q = 'INSERT INTO edges (prev_node, next_node, has_space, count) VALUES (?, ?, ?, 1)'

        args = (prev_node, next_node, has_space)

        c.execute(update_q, args)
        if c.rowcount == 0:
            c.execute(q, args)

        # The count on the next_node in the nodes table must be
        # incremented here, to register that the node has been seen an
        # additional time. This is now handled by database triggers.

    def get_node_count(self, node_id):
        q = 'SELECT count FROM nodes WHERE nodes.id = ?'

        row = self._conn.execute(q, (node_id,)).fetchone()
        assert row

        return row[0]

    def get_node_counts(self, node_ids):
        q = 'SELECT id, count FROM nodes WHERE id IN %s' % self.get_seq_expr(node_ids)

        return self._conn.execute(q)

    def walk(self, node, end_id, direction, append):
        """Perform a random walk on the graph starting at node"""
        if direction:
            q = 'SELECT id, next_node, prev_node, has_space, count ' \
                'FROM edges WHERE prev_node = :last ' \
                'LIMIT 1 OFFSET abs(random())%(SELECT count(*) from edges ' \
                '                              WHERE prev_node = :last)'
        else:
            q = 'SELECT id, prev_node, next_node, has_space, count ' \
                'FROM edges WHERE next_node = :last ' \
                'LIMIT 1 OFFSET abs(random())%(SELECT count(*) from edges ' \
                '                              WHERE next_node = :last)'

        c = self.cursor()
        last_node = node

        while last_node != end_id:
            row = c.execute(q, {'last': last_node}).fetchone()

            append(Edge(self, row['id'], row['prev_node'], row['next_node'],
                        row['has_space'], row['count']))

            last_node = row[1]

    def init(self, order, tokenizer, run_migrations=True):
        c = self.cursor()

        c.execute('CREATE TABLE info (attribute TEXT NOT NULL PRIMARY KEY, '
                  'text TEXT NOT NULL)')

        c.execute('CREATE TABLE tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                  'text TEXT UNIQUE NOT NULL, is_word INTEGER NOT NULL)')

        tokens = []
        for i in range(order):
            tokens.append('token%d_id INTEGER REFERENCES token(id)' % i)

        c.execute('CREATE TABLE token_stems (token_id INTEGER, stem TEXT NOT '
                  'NULL)')

        sql = ('CREATE TABLE nodes (id INTEGER PRIMARY KEY AUTOINCREMENT, '
               'count INTEGER NOT NULL, {})')
        c.execute(sql.format(', '.join(tokens)))

        c.execute('CREATE TABLE edges (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                  'prev_node INTEGER NOT NULL REFERENCES nodes(id), next_node '
                  'INTEGER NOT NULL REFERENCES nodes(id), count INTEGER NOT '
                  'NULL, has_space INTEGER NOT NULL)')

        if run_migrations:
            self._run_migrations()

        # save the order of this brain
        self.set_info_text('order', str(order))
        self.order = order

        # save the tokenizer
        self.set_info_text('tokenizer', tokenizer)

        # save the brain/schema version
        self.set_info_text('version', '2')

        self.commit()
        self.ensure_indexes()

        self.close()

    def drop_reply_indexes(self):
        self._conn.execute('DROP INDEX IF EXISTS edges_all_next')
        self._conn.execute('DROP INDEX IF EXISTS edges_all_prev')

        self._conn.execute('CREATE INDEX IF NOT EXISTS learn_index ON edges '
                           '(prev_node, next_node)')

    def ensure_indexes(self):
        c = self.cursor()

        # remove the temporary learning index if it exists
        c.execute('DROP INDEX IF EXISTS learn_index')

        token_ids = ','.join(['token%d_id' % i for i in range(self.order)])
        sql = 'CREATE UNIQUE INDEX IF NOT EXISTS nodes_token_ids on nodes ({})'
        c.execute(sql.format(token_ids))

        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS edges_all_next ON edges '
                  '(next_node, prev_node, has_space, count)')

        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS edges_all_prev ON edges '
                  '(prev_node, next_node, has_space, count)')

    def delete_token_stems(self):
        c = self.cursor()

        # drop the two stem indexes
        c.execute('DROP INDEX IF EXISTS token_stems_stem')
        c.execute('DROP INDEX IF EXISTS token_stems_id')

        # delete all the existing stems from the table
        c.execute('DELETE FROM token_stems')

        self.commit()

    def update_token_stems(self, stemmer):
        # stemmer is a CobeStemmer
        c = self.cursor()
        insert_c = self.cursor()
        insert_q = 'INSERT INTO token_stems (token_id, stem) VALUES (?, ?)'
        q = c.execute('SELECT id, text FROM tokens WHERE is_word = 1')
        for row in q:
            insert_c.execute(insert_q, (row[0], stemmer.stem(row[1])))
        self.commit()

        c.execute('CREATE INDEX token_stems_id on token_stems (token_id)')
        c.execute("CREATE INDEX token_stems_stem on token_stems (stem)")

    def _run_migrations(self):
        self._maybe_drop_tokens_text_index()
        self._maybe_create_node_count_triggers()

    def _maybe_drop_tokens_text_index(self):
        # tokens_text was an index on tokens.text, deemed redundant since
        # tokens.text is declared UNIQUE, and sqlite automatically creates
        # indexes for UNIQUE columns
        self._conn.execute('DROP INDEX IF EXISTS tokens_text')

    def _maybe_create_node_count_triggers(self):
        # Create triggers on the edges table to update nodes counts.
        # In previous versions, the node counts were updated with a
        # separate query. Moving them into triggers improves
        # performance.
        c = self.cursor()

        c.execute('CREATE TRIGGER IF NOT EXISTS edges_insert_trigger AFTER '
                  'INSERT ON edges BEGIN UPDATE nodes SET count = count + '
                  'NEW.count WHERE nodes.id = NEW.next_node; END;')

        c.execute('CREATE TRIGGER IF NOT EXISTS edges_update_trigger AFTER '
                  'UPDATE ON edges BEGIN UPDATE nodes SET count = count + '
                  '(NEW.count - OLD.count) WHERE nodes.id = NEW.next_node; '
                  'END;')

        c.execute('CREATE TRIGGER IF NOT EXISTS edges_delete_trigger AFTER '
                  'DELETE ON edges BEGIN UPDATE nodes SET count = count - '
                  'old.count WHERE nodes.id = OLD.next_node; END;')
