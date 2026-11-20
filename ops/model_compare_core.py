"""Pure hypothetical arrival compiler; native prefix feedback owns risk/accounting."""
import copy
from decimal import Decimal, localcontext
import heapq
import json

POLICY = dict(comparison_policy_version=1,proxy_model_version=1,
    proxy_model='assumed_known_book_at_arrival_v1', ledger_schema_version=1,
    ledger_kind='manual_simulation', max_orders=64,max_records=10000,
    source_event_before_equal_arrivals=True,zero_latency_after_own_request=True,
    fixed_original_requests=True,alternative_strategy_evaluated=False,
    actual_execution_known=False,full_window_verified=False)


def require(condition,reason):
    if not condition:raise ValueError(reason)


def amount(value):
    require(isinstance(value,str),'exact decimal string required')
    result=Decimal(value)
    require(result.is_finite(),'finite decimal required')
    return result


def text(value):
    raw=format(value,'f')
    return '0' if value==0 else raw.rstrip('0').rstrip('.') if '.' in raw else raw


def top(event):
    if not event['usable']:return None
    require(event['channel']=='bbo','comparison requires native BBO marks')
    data=json.loads(event['source']['event']['text'])['data']
    bid,ask=data['bbo']
    quote=event['link']['quote']
    require(bid and ask and amount(bid['px'])==amount(quote['bid']) and amount(ask['px'])==amount(quote['ask'])
        and amount(bid['sz'])>0 and amount(ask['sz'])>0 and data['time']==quote['exchange_time_ms']
        and quote['connection_id']==event['source']['connection_id'],'native reference differs from original BBO')
    return dict(sequence=event['sequence'],monotonic_ns=str(event['time']),connection_id=event['source']['connection_id'],
        exchange_time_ms=str(data['time']),bid=bid['px'],ask=ask['px'],bid_size=bid['sz'],ask_size=ask['sz'])


class Liquidity:
    def __init__(self,fraction):
        self.fraction=amount(fraction);self.identity=None;self.prices=None;self.left=[Decimal(0),Decimal(0)]

    def observe(self,quote):
        key=(quote['connection_id'],quote['exchange_time_ms'])
        prices=(amount(quote['bid']),amount(quote['ask']))
        with localcontext() as context:
            context.prec=100
            sizes=[amount(quote[k])*self.fraction for k in ('bid_size','ask_size')]
            if self.identity==key:
                self.left=[min(a,b) for a,b in zip(self.left,sizes)] if self.prices==prices else [Decimal(0),Decimal(0)]
            else:self.left=sizes
        self.identity,self.prices=key,prices

    def invalidate(self):
        self.left=[Decimal(0),Decimal(0)]


class Compiler:
    """Yield persisted batches; receive authoritative native PaperReport feedback."""
    def __init__(self,events,base_inputs,scenario):
        require(0<len(events)<10000 and len(base_inputs)==len(events)+1,'bounded complete native market required')
        require(scenario['scenario_version']==1 and 0<len(scenario['orders'])<=POLICY['max_orders'],'bounded frozen scenario required')
        require(len({o['id'] for o in scenario['orders']})==len(scenario['orders']),'unique request identifiers required')
        anchors=[o['after_market_sequence'] for o in scenario['orders']]
        require(anchors==sorted(anchors) and all(type(n) is int and 1<=n<=len(events) for n in anchors),'ordered original source anchors required')
        self.events,self.base,self.scenario=events,base_inputs,scenario
        self.batch=[];self.count=0;self.now=0;self.source=None;self.reference=None
        self.freshness_ns=base_inputs[0]['event']['config']['stale_after_ms']*1000000
        self.liquidity=Liquidity(scenario['assumptions']['top_size_fraction'])
        self.pending=[];self.decisions=[];self.feedback=None

    def emit(self,event,now,phase,**extra):
        require(type(now) is int and self.now<=now<=18446744073709551615,'proxy action clock regressed or overflowed')
        self.now=now;self.count+=1
        require(self.count<=POLICY['max_records'],'proxy paper record bound exceeded')
        source=self.source
        link=dict(comparison_link_version=1,paper_sequence=self.count,phase=phase,
            known_source_sequence=source['sequence'],source_monotonic_ns=str(source['time']),
            action_monotonic_ns=str(now),assumed_action=phase not in ('source','replay_end'),**extra)
        record=dict(paper_schema_version=1,sequence=self.count,monotonic_ns=now,event=event)
        self.batch.append(dict(record=record,link=link))

    def checkpoint(self):
        batch,self.batch=self.batch,[]
        report=yield batch
        require(type(report) is dict and report['records']==self.count and report['paper_model_version']==1
            and report['config']['source']['kind']=='manual_simulation','native prefix feedback differs')
        self.feedback=report

    def native_order(self,identity):
        result=next((o for o in self.feedback['orders'] if o['id']==identity),None)
        require(result is not None,'native request missing from feedback')
        return result

    def observe(self,event):
        quote=top(event)
        state=(event['link'].get('feeds') or {}).get('bbo') or {}
        if quote is not None:
            self.reference=quote;self.liquidity.observe(quote)
        if not state.get('acknowledged') or state.get('status')!='fresh' or (self.reference is not None and
            (event['source']['connection_id']!=self.reference['connection_id'] or state.get('latest_sequence')!=self.reference['sequence'])):
            self.reference=None;self.liquidity.invalidate()

    def settle(self,order,index,now,decision):
        identity=order['id']
        self.emit(dict(type='timer'),now,'arrival_timer',order_id=identity)
        yield from self.checkpoint()
        require(self.native_order(identity)['status']=='pending_new','arrival does not refer to a pending request')
        quote=copy.deepcopy(self.reference)
        age=None if quote is None else now-int(quote['monotonic_ns'])
        usable=quote is not None and 0<=age<self.freshness_ns and self.feedback['account']['mark_fresh'] is True
        decision.update(reference_quote=quote,reference_age_ns=None if age is None else str(age),reference_eligible=usable,
                        known_source_sequence=self.source['sequence'],actual_execution='unknown')
        if not usable:
            self.emit(dict(type='order_rejected',id=identity,reason='Assumed proxy: no usable known BBO at arrival'),now,
                'assumed_reference_rejection',order_id=identity)
            decision['outcome']='no_usable_reference'
            if age is not None and age>=self.freshness_ns:
                self.reference=None;self.liquidity.invalidate()
        else:
            side=1 if order['side']=='buy' else 0
            touch=amount(quote['ask' if side else 'bid'])
            assumptions=self.scenario['assumptions']
            with localcontext() as context:
                context.prec=100
                adjustment=touch*amount(assumptions['slippage_bps'])/10000
                price=touch+adjustment if side else touch-adjustment
                marketable=price<=amount(order['limit_price']) if side else price>=amount(order['limit_price'])
                capacity=self.liquidity.left[side]
                quantity=min(amount(order['quantity']),capacity) if marketable else Decimal(0)
                mid=(amount(quote['bid'])+amount(quote['ask']))/2
                fee=price*quantity*amount(assumptions['fee_rate'])
                spread=abs(touch-mid)*quantity;slippage=adjustment*quantity
                self.liquidity.left[side]-=quantity
            decision.update(assumed_fill_price=text(price),touch_price=text(touch),available_quantity=text(capacity),
                assumed_fill_quantity=text(quantity),assumed_fee=text(fee),spread_cost=text(spread),slippage_cost=text(slippage),
                marketable=marketable)
            self.emit(dict(type='order_accepted',id=identity),now,'assumed_accept',order_id=identity)
            if quantity>0:
                self.emit(dict(type='assumed_fill',fill_id='proxy-'+identity,order_id=identity,price=text(price),quantity=text(quantity)),
                    now,'assumed_fill',order_id=identity,reference_quote_sequence=quote['sequence'],
                    touch_price=text(touch),fee=text(fee),spread_cost=text(spread),slippage_cost=text(slippage))
            if quantity<amount(order['quantity']):
                self.emit(dict(type='cancel_requested',id=identity),now,'assumed_ioc_cancel',order_id=identity)
                self.emit(dict(type='cancel_accepted',id=identity),now,'assumed_ioc_cancel_ack',order_id=identity)
            decision['outcome']=('filled' if quantity==amount(order['quantity']) else 'partial_fill_cancelled' if quantity>0
                else 'not_marketable' if not marketable else 'no_remaining_capacity')
        yield from self.checkpoint()
        decision['native_final_order']=copy.deepcopy(self.native_order(identity))

    def run(self):
        orders=self.scenario['orders']
        by_anchor={}
        for index,order in enumerate(orders):by_anchor.setdefault(order['after_market_sequence'],[]).append((index,order))
        config=copy.deepcopy(self.base[0]['event']['config'])
        config['source']=dict(kind='manual_simulation',label='Assumed known book at arrival; offline comparison v1')
        for key in ('starting_collateral','max_abs_position','max_order_notional','max_working_orders','max_loss'):
            config[key]=self.scenario[key]
        config['fee_rate']=self.scenario['assumptions']['fee_rate']
        latency=self.scenario['assumptions']['latency_ms']*1000000
        require(type(latency) is int and 0<=latency<=60000000000,'bounded exact assumed latency required')
        for event,base in zip(self.events,self.base):
            require(base['sequence']==event['sequence'] and base['monotonic_ns']==event['time'],'native source ordering differs')
            while self.pending and self.pending[0][0]<event['time']:
                arrival,index,order,decision=heapq.heappop(self.pending)
                yield from self.settle(order,index,arrival,decision)
            self.source=event
            paper_event=dict(type='session_started',config=config) if event['sequence']==1 else copy.deepcopy(base['event'])
            self.emit(paper_event,event['time'],'source')
            self.observe(event)
            while self.pending and self.pending[0][0]==event['time']:
                arrival,index,order,decision=heapq.heappop(self.pending)
                yield from self.settle(order,index,arrival,decision)
            for index,order in by_anchor.get(event['sequence'],[]):
                require(event['source']['event']['type']!='session_ended','source end cannot be a request anchor')
                arrival=event['time']+latency
                require(arrival<=18446744073709551615,'assumed arrival overflow')
                decision=dict(order=copy.deepcopy(order),request_monotonic_ns=str(event['time']),assumed_arrival_ns=str(arrival),
                    actual_execution='unknown',outcome='pending_at_source_end',reference_quote=None,reference_eligible=None,
                    assumed_fill_quantity=None,assumed_fee=None)
                self.decisions.append(decision)
                self.emit(dict(type='order_requested',**{k:order[k] for k in ('id','side','quantity','limit_price')}),
                    event['time'],'request',order_id=order['id'])
                yield from self.checkpoint()
                state=self.native_order(order['id'])
                decision['native_request_order']=copy.deepcopy(state)
                if state['status']=='rejected':
                    decision.update(outcome='request_rejected',native_final_order=copy.deepcopy(state))
                elif arrival==event['time']:
                    yield from self.settle(order,index,arrival,decision)
                else:heapq.heappush(self.pending,(arrival,index,order,decision))
        ending=self.base[-1]
        require(ending['event']['type']=='session_ended' and ending['monotonic_ns']>=self.now,'native generated end required')
        self.emit(copy.deepcopy(ending['event']),ending['monotonic_ns'],'replay_end')
        yield from self.checkpoint()
        require(self.feedback['complete'] is True,'manual ledger did not finalize')
        for _,_,order,decision in self.pending:
            decision['native_final_order']=copy.deepcopy(self.native_order(order['id']))
        return self.decisions
