# Copyright (C) 2011 Peter Teichman
# Edited 2015-02-11 for simplicity and Python 3 compatibility by William Jackson

import math

from itertools import islice


class Scorer:
    def __init__(self):
        self.cache = {}

    def end(self):
        self.cache = {}

    @staticmethod
    def normalize(score):
        # map high-valued scores into 0..1
        if score < 0:
            return score

        return 1.0 - 1.0 / (1.0 + score)

    def score(self, reply):
        return NotImplementedError


class ScorerGroup:
    def __init__(self):
        self.scorers = []
        self.total_weight = 0.0

    def add_scorer(self, weight, scorer):
        # add a scorer with a negative weight if you want to reverse
        # its impact
        self.scorers.append((weight, scorer))

        total = 0.0
        for weight, _ in self.scorers:
            total += abs(weight)
        self.total_weight = total

    def end(self):
        for scorer in self.scorers:
            scorer[1].end()

    def score(self, reply):
        # normalize to 0..1
        score = 0.0
        for weight, scorer in self.scorers:
            s = scorer.score(reply)

            # make sure score is in our accepted range
            assert 0.0 <= score <= 1.0

            if weight < 0.0:
                s = 1.0 - s

            score += abs(weight) * s

        return score / self.total_weight


class CobeScorer(Scorer):
    """Classic Cobe scorer"""

    def score(self, reply):
        info = 0.0

        cache = self.cache
        nodes = set()

        for edge in reply.edges:
            node_id = edge.prev

            if node_id not in cache:
                nodes.add(node_id)

        counts = reply.graph.get_node_counts(nodes)

        for node_id, count in counts:
            cache[node_id] = count

        for edge in reply.edges:
            node_count = cache[edge.prev]
            info += -math.log(float(edge.count) / node_count, 2)

        # Approximate the number of cobe 1.2 contexts in this reply, so the
        # scorer will have similar results.

        # First, we have (graph.order - 1) extra edges on either end of the
        # reply, since cobe 2.0 learns from (_END_TOKEN, _END_TOKEN, ...).
        n_words = len(reply.edges) - (reply.graph.order - 1) * 2

        # Add back one word for each space between edges, since cobe 1.2
        # treated those as separate parts of a context.
        for edge in reply.edges:
            if edge.has_space:
                n_words += 1

        # Double the score, since Cobe 1.x scored both forward and backward
        info *= 2.0

        # Comparing to Cobe 1.x scoring:
        # At this point we have an extra count for every space token
        # that adjoins punctuation. I'm tweaking the two checks below
        # for replies longer than 16 and 32 tokens (rather than our
        # original 8 and 16) as an adjustment. Scoring is an ongoing
        # project.

        if n_words > 16:
            info /= math.sqrt(n_words - 1)
        elif n_words >= 32:
            info /= n_words

        return self.normalize(info)


class IdentityScorer(Scorer):
    """Parrot the input exactly. Best used with a negative weight."""

    def token_iter(self, reply):
        cache = self.cache

        for edge in islice(reply.edges, 1, None):
            node_id = edge.prev

            if node_id in cache:
                token = cache[node_id]
            else:
                token = edge.get_prev_token()
                cache[node_id] = token

            yield edge.get_prev_token()
            if edge.has_space:
                yield None

    def score(self, reply):
        len_token_ids = 0
        for _ in reply.token_ids:
            len_token_ids += 1
        if len_token_ids != len(reply.edges) - 1:
            return 0.0

        for a, b in zip(reply.token_ids, self.token_iter(reply)):
            if a != b:
                return 0.0

        return 1.0


class InformationScorer(Scorer):
    """Score based on the information of each edge in the graph"""

    def score(self, reply):
        info = 0.0

        get_node_count = reply.graph.get_node_count

        cache = self.cache
        for edge in reply.edges:
            node_id = edge.prev

            if node_id in cache:
                node_count = cache[node_id]
            else:
                node_count = get_node_count(node_id)
                cache[node_id] = node_count

            info += -math.log(float(edge.count) / node_count, 2)

        return self.normalize(info)


class LengthScorer(Scorer):
    def score(self, reply):
        return self.normalize(len(reply.edges))
