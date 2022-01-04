import ast
import bisect
import copy
import json
import operator
import random
import time

basestring = str

BEGIN = "___BEGIN__"
END = "___END__"


def accumulate(iterable, func=operator.add):
    """Cumulative calculations.

    (Summation, by default.)
    Via: https://docs.python.org/3/library/itertools.html#itertools.accumulate
    """
    it = iter(iterable)
    total = next(it)
    yield total
    for element in it:
        total = func(total, element)
        yield total


def compile_next(next_dict):
    words = list(next_dict.keys())
    cff = list(accumulate(next_dict.values()))
    return [words, cff]


class Chain(object):
    """A Markov chain representing processes that have both beginnings and
    ends.

    For example: Sentences.
    """
    def __init__(self, corpus, state_size, model=None, model_reversed=None):
        """
        `corpus`: A list of lists, where each outer list is a "run"
        of the process (e.g., a single sentence), and each inner list
        contains the steps (e.g., words) in the run. If you want to simulate
        an infinite process, you can come very close by passing just one, very
        long run.

        `state_size`: An integer indicating the number of items the model
        uses to represent its state. For text generation, 2 or 3 are typical.
        """
        self.state_size = state_size

        corpus_clone = copy.deepcopy(corpus)

        self.model = model or self.build(corpus, self.state_size)
        self.model_reversed = model_reversed or self.build_reverse(corpus_clone, self.state_size)

        self.compiled = (
            (len(self.model) > 0) and
            (len(self.model_reversed) > 0)) and (isinstance(self.model[tuple([BEGIN] * state_size)], list) and
                                                 (isinstance(self.model_reversed[tuple([BEGIN] * state_size)], list)))

        if not self.compiled:
            self.precompute_begin_state()

    def compile(self, inplace=False):
        if self.compiled:
            if inplace:
                return self
            return Chain(None,
                         self.state_size,
                         model=copy.deepcopy(self.model),
                         model_reversed=copy.deepcopy(self.model_reversed))

        mdict = {state: compile_next(next_dict) for (state, next_dict) in self.model.items()}

        mdict_reversed = {state: compile_next(next_dict) for (state, next_dict) in self.model_reversed.items()}

        if not inplace:
            return Chain(None, self.state_size, model=mdict, model_reversed=mdict_reversed)
        self.model = mdict
        self.model_reversed = mdict_reversed
        self.compiled = True
        return self

    def build(self, corpus, state_size, overwrite=False):
        """Build a Python representation of the Markov model.

        Returns a dict of dicts where the keys of the outer dict
        represent all possible states, and point to the inner dicts. The
        inner dicts represent all possibilities for the "next" item in
        the chain, along with the count of times it appears. When
        overwrite is True, this method will update the self.model dict
        instead of starting from scratch with an empty dict.
        """

        # Using a DefaultDict here would be a lot more convenient, however the memory
        # usage is far higher.
        model = self.model if overwrite else {}

        for run in corpus:
            items = ([BEGIN] * state_size) + run + [END]
            for i in range(len(run) + 1):
                state = tuple(items[i:i + state_size])
                follow = items[i + state_size]
                if state not in model:
                    model[state] = {}

                if follow not in model[state]:
                    model[state][follow] = 0

                model[state][follow] += 1
        return model

    def build_reverse(self, corpus, state_size):
        """Build a Python representation of the Markov model.

        Returns a dict of dicts where the keys of the outer dict
        represent all possible states, and point to the inner dicts. The
        inner dicts represent all possibilities for the "next" item in
        the chain, along with the count of times it appears.
        """

        # Using a DefaultDict here would be a lot more convenient, however the memory
        # usage is far higher.
        model = {}
        for run in corpus:
            run.reverse()
            items = ([BEGIN] * state_size) + run + [END]
            for i in range(len(run) + 1):
                state = tuple(items[i:i + state_size])
                follow = items[i + state_size]
                if state not in model:
                    model[state] = {}

                if follow not in model[state]:
                    model[state][follow] = 0

                model[state][follow] += 1
        return model

    def precompute_begin_state(self):
        """
        Caches the summation calculation and available choices for BEGIN * state_size.
        Significantly speeds up chain generation on large corpora. Thanks, @schollz!
        """
        begin_state = tuple([BEGIN] * self.state_size)
        choices, cumdist = compile_next(self.model[begin_state])
        self.begin_cumdist = cumdist
        self.begin_choices = choices

    def move(self, state):
        """Given a state, choose the next item at random."""
        if self.compiled:
            choices, cumdist = self.model[state]
        elif state == tuple([BEGIN] * self.state_size):
            choices = self.begin_choices
            cumdist = self.begin_cumdist
        else:
            choices, weights = zip(*self.model[state].items())
            cumdist = list(accumulate(weights))
        r = random.random() * cumdist[-1]
        selection = choices[bisect.bisect(cumdist, r)]
        return selection

    def move_back(self, state):
        """Given a state, choose the next item at random."""
        if self.compiled:
            choices, cumdist = self.model_reversed[state]
        elif state == tuple([BEGIN] * self.state_size):
            choices = self.begin_choices
            cumdist = self.begin_cumdist
        else:
            choices, weights = zip(*self.model_reversed[state].items())
            cumdist = list(accumulate(weights))
        r = random.random() * cumdist[-1]
        selection = choices[bisect.bisect(cumdist, r)]
        return selection

    def gen(self, init_state=None):
        """Starting either with a naive BEGIN state, or the provided
        `init_state` (as a tuple), return a generator that will yield
        successive items until the chain reaches the END state."""
        state = init_state or (BEGIN, ) * self.state_size
        while True:
            next_word = self.move(state)
            if next_word == END:
                break
            yield next_word
            state = tuple(state[1:]) + (next_word, )

    def gen_back(self, init_state=None):
        """Starting either with a naive BEGIN state, or the provided
        `init_state` (as a tuple), return a generator that will yield
        successive items until the chain reaches the END state."""
        state = init_state or (BEGIN, ) * self.state_size
        while True:
            next_word = self.move_back(state)
            if next_word == END:
                break
            yield next_word
            state = tuple(state[1:]) + (next_word, )

    def walk_back(self, init_state=None):
        """Return a list representing a single run of the Markov model, either
        starting with a naive BEGIN state, or the provided `init_state` (as a
        tuple)."""
        return list(self.gen_back(init_state))

    def walk(self, init_state=None):
        """Return a list representing a single run of the Markov model, either
        starting with a naive BEGIN state, or the provided `init_state` (as a
        tuple)."""
        return list(self.gen(init_state))

    def update(self, corpus):
        """Update the internal Markov model with words from `corpus`.

        This instance of Chain will be mutated (this function returns
        None).
        """
        self.model = self.build(corpus, self.state_size, overwrite=True)
        self.precompute_begin_state()

    def to_json(self):
        """Dump the model as a JSON object, for loading later."""
        return json.dumps(list(self.model.items())), json.dumps(list(self.model_reversed.items()))

    @classmethod
    def from_json(cls, json_thing):
        """Given a JSON object or JSON string that was created by
        `self.to_json`, return the corresponding markovify.Chain."""

        if isinstance(json_thing, str):
            obj = json.loads(json_thing)
        else:
            obj = json_thing

        if isinstance(obj, tuple) and not isinstance(obj[0], dict):
            obj1 = ast.literal_eval(obj[0])
            obj2 = ast.literal_eval(obj[1])
            rehydrated = dict((tuple(item[0]), item[1]) for item in obj1)
            rehydrated_reversed = dict((tuple(item[0]), item[1]) for item in obj2)
        elif isinstance(obj, list) and not isinstance(obj[0], dict):
            obj1 = ast.literal_eval(obj[0])
            obj2 = ast.literal_eval(obj[1])
            rehydrated = dict((tuple(item[0]), item[1]) for item in obj1)
            rehydrated_reversed = dict((tuple(item[0]), item[1]) for item in obj2)
        elif isinstance(obj[0], dict):
            obj1 = obj[0]
            obj2 = obj[1]
            rehydrated = obj1
            rehydrated_reversed = obj2
        else:
            raise ValueError("Object should be tuple")

        state_size = len(list(rehydrated.keys())[0])

        inst = cls(None, state_size, rehydrated, rehydrated_reversed)
        return inst
