import time
import logging
from pprint import pprint

class Vertex:
    @property
    def id(self): raise NotImplementedError
    @property
    def active(self): raise NotImplementedError
    
class Message:
    @property
    def target_id(self):
        raise NotImplementedError

class Edge: pass

class Combiner:
    def createCombiner(self, msg): raise NotImplementedError
    def mergeMsg(self, combiner, msg): raise NotImplementedError
    def mergeCombiners(self, a, b): raise NotImplementedError

class Aggregator:
    def createAggregator(self, vert): raise NotImplementedError
    def mergeAggregator(self, a, b): raise NotImplementedError

class DefaultCombiner(Combiner):
    def createCombiner(self, msg):
        return [msg]
    def mergeMsg(self, combiner, msg):
        return combiner+[msg]
    def mergeCombiners(self, a, b):
        return a + b

class NullAggregator(Aggregator):
    def createAggregator(self, vert):
        pass
    def mergeAggregator(self, a, b):
        pass

class Bagel:
    @classmethod
    def run(cls, ctx, verts, msgs, compute,
            combiner=DefaultCombiner(), aggregator=NullAggregator(),
            superstep=0, numSplits=None):

        while True:
            logging.info("Starting superstep %d", superstep)
            start = time.time()
            aggregated = cls.agg(verts, aggregator)
            combinedMsgs = msgs.combineByKey(combiner.createCombiner,
                combiner.mergeMsg, combiner.mergeCombiners, numSplits)
            grouped = verts.groupWith(combinedMsgs)
            processed, numMsgs, numActiveVerts = cls.comp(ctx, grouped, 
                lambda v, ms: compute(v, ms, aggregated, superstep))
            logging.info("superstep %d took %s s", superstep, time.time()-start)

            noActivity = numMsgs == 0 and numActiveVerts == 0
            if noActivity:
                return processed.map(lambda (id, (vert, msgs)): vert)
            
            verts = processed.mapValue(lambda (vert, msgs): vert)
            msgs = processed.flatMap(lambda (id, (vert, msgs)):
                    [(m.target_id, m) for m in msgs])
            superstep += 1
        
    @classmethod
    def agg(cls, verts, aggregator):
        if isinstance(aggregator, NullAggregator):
            return 
        r = verts.map(lambda (id, vert): aggregator.createAggregator(vert))
        return r.reduce(aggregator.mergeAggregators)

    @classmethod
    def comp(cls, ctx, grouped, compute):
        numMsgs = ctx.accumulator(0)
        numActiveVerts = ctx.accumulator(0)
        def proc((vs, cs)):
            if not vs:
                return []
            newVert, newMsgs = compute(vs[0], cs)
            numMsgs.add(len(newMsgs))
            if newVert.active:
                numActiveVerts += 1
            return [(newVert, newMsgs)]
        processed = grouped.flatMapValue(proc).cache()
        # force evaluation of processed RDD for accurate performance measurements
        processed.count()
        return processed, numMsgs.value, numActiveVerts.value

    @classmethod
    def addAggregatorArg(cls, compute):
        def _(vert, messages, aggregator, superstep):
            return compute(vert, messages)
        return _
