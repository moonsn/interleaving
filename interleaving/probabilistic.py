from .ranking import Ranking
from .interleaving_method import InterleavingMethod
import numpy as np


class DictDependingOnTau(dict):
    '''is a dict which depends on a value of tau (or t)'''

    def __new__(cls, tau):
        if not hasattr(cls, '_tau_to_dict'):
            cls._tau_to_dict = {}
        if tau not in cls._tau_to_dict:
            cls._tau_to_dict[tau] = dict.__new__(cls, tau)
        return cls._tau_to_dict[tau]

    def __init__(self, tau):
        raise NotImplementedError()

    def __missing__(self, n):
        raise NotImplementedError()


class CumulationCache(DictDependingOnTau):
    '''is a dict where n -> List l where...

    the item at an index i is selected in probability of
    l[i] - l[i - 1] (or just l[i] if i == 0).
    '''

    class SumCache(DictDependingOnTau):
        '''is a dict where n -> Sum of 1 / r^t where r is in [1, n] .'''

        class MemberCache(DictDependingOnTau):
            '''is a dict where r -> 1 / r^t .'''

            def __init__(self, tau):
                self.tau = tau

            def __missing__(self, r):
                self[r] = 1.0 / r ** self.tau
                return self[r]

        def __init__(self, tau):
            self.member_cache = self.MemberCache(tau)

        def __missing__(self, n):
            self[n] = sum([self.member_cache[r] for r in range(1, n + 1)])
            return self[n]

    def __init__(self, tau):
        self.sum_cache = self.SumCache(tau)
        self.member_cache = self.SumCache.MemberCache(tau)

    def __missing__(self, l):
        result = []
        numerator = 0.0
        denominator = self.sum_cache[l]
        for r in range(1, l):
            numerator += self.member_cache[r]
            result.append(numerator / denominator)
        result.append(1)
        self[l] = result
        return result

    def choice_one_of(self, r_l):
        n = r_l.get_length()
        f = np.random.random()
        cumulation = self[n]
        node = r_l
        for i in range(0, n):
            if f < cumulation[i]:
                return node.next_value
            node = node.next


class RemovalNode(object):
    __slots__ = ['next_value', 'next']
    _pool = []

    @classmethod
    def take_one(cls):
        if 0 < len(cls._pool):
            return cls._pool.pop()
        else:
            return object.__new__(cls)

    def follow(self, prev, value):
        prev.next_value = value
        prev.next = self
        self.next = None
        self.next_value = None

    def remove_next(self):
        self._pool.append(self.next)
        self.next_value = self.next.next_value
        self.next = self.next.next
        return self.next_value


class RemovalList(RemovalNode):
    __slots__ = ['next_value', 'next', 'dict', 'last']

    def __init__(self, l=[]):
        self.next_value = None
        self.next = None
        self.dict = {}
        self.last = self
        for v in l:
            self.append(v)

    def append(self, value):
        node = RemovalNode.take_one()
        node.follow(self.last, value)
        self.dict[value] = self.last
        self.last = node

    def get_length(self):
        return len(self.dict)

    def remove(self, value):
        if value in self.dict:
            prev = self.dict.pop(value)
            new_next_value = prev.remove_next()
            if new_next_value is not None:
                self.dict[new_next_value] = prev

    def truncate(self):
        for value in list(self.dict.keys()):
            self.remove(value)


class Probabilistic(InterleavingMethod):
    '''Probabilistic Interleaving'''
    np.random.seed()

    def __init__(self, tau=3.0):
        self._cumulation_cache = CumulationCache(tau)

    def _advance(self, input_rankings, ranker_index, output_ranking):
        '''choices a document in input_rankings[ranker_index].'''

        ranking = input_rankings[ranker_index]
        document = self._cumulation_cache.choice_one_of(ranking)
        output_ranking.append(document)
        output_ranking.rank_to_ranker_index.append(ranker_index)
        for r_l in input_rankings:
            r_l.remove(document)

    def interleave(self, k, a, b):
        '''performs interleaving...

        k: the maximum length of resultant interleaving
        a: a list of document IDs
        b: a list of document IDs

        Returns an instance of Ranking
        '''

        result = Ranking()
        result.number_of_rankers = 2
        result.rank_to_ranker_index = []
        rankings = [RemovalList(a), RemovalList(b)]
        for i in range(k):
            ranker_index = np.random.randint(0, 2)
            self._advance(rankings, ranker_index, result)
            if k <= len(result):
                for ranking in rankings:
                    ranking.truncate()
                return result

    def multileave(self, k, *lists):
        '''performs multileaving...

        k: the maximum length of resultant multileaving
        *lists: lists of document IDs

        Returns an instance of Ranking
        '''

        result = Ranking()
        result.number_of_rankers = len(lists)
        result.rank_to_ranker_index = []
        rankings = []
        for original_list in lists:
            r_l = RemovalList(original_list)
            rankings.append(r_l)
        while True:
            ranker_indexes = [i for i in range(0, len(rankings))]
            np.random.shuffle(ranker_indexes)
            while(0 < len(ranker_indexes)):
                ranker_index = ranker_indexes.pop()
                self._advance(rankings, ranker_index, result)
                if k <= len(result):
                    for ranking in rankings:
                        ranking.truncate()
                    return result

    def evaluate(self, ranking, clicks):
        '''evaluates rankers based on clicks

        ranking: an instance of Ranking generated by
                 Probabilistic::interleave or Probabilistic::multileave
        clicks:  a list of indices clicked by a user

        Return a list of pairs of ranker indices
        in which element (i, j) indicates i won j.
        '''
        counts = [0] * ranking.number_of_rankers
        rank_to_ranker_index = ranking.rank_to_ranker_index
        for d in clicks:
            counts[rank_to_ranker_index[d]] += 1

        result = []
        for i in range(ranking.number_of_rankers):
            for j in range(i+1, ranking.number_of_rankers):
                if counts[i] > counts[j]:
                    result.append((i, j))
                elif counts[i] < counts[j]:
                    result.append((j, i))
                else: # scores[i] == scores[j]
                    pass
        return result