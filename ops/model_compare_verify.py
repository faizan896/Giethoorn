"""Independent Decimal/source checks for a manual arrival-assumption ledger."""
from decimal import Decimal, localcontext
import json


def require(ok,reason):
    if not ok:raise ValueError(reason)


def verify(events,base,scenario,records,links,frames,report,decisions):
    require(len(records)==len(links)==len(frames)==report['records'] and report['complete']
        and report['paper_model_version']==1 and report['config']['source']['kind']=='manual_simulation',
        'unsupported or incomplete manual comparison ledger')
    orders={o['id']:o for o in scenario['orders']}
    require(len(orders)==len(decisions) and {d['order']['id'] for d in decisions}==set(orders),'proxy request membership differs')
    chosen={d['order']['id']:d for d in decisions}
    expected_config=dict(base[0]['event']['config'])
    expected_config['source']=dict(kind='manual_simulation',label='Assumed known book at arrival; offline comparison v1')
    for key in ('starting_collateral','max_abs_position','max_order_notional','max_working_orders','max_loss'):
        expected_config[key]=scenario[key]
    expected_config['fee_rate']=scenario['assumptions']['fee_rate']
    require(report['config']==expected_config,'proxy native risk/account configuration differs')
    requested={};arrivals={};seen_source=0;reference=None;available={};prices={};ambiguous=set()
    fees=spread=slippage=position=Decimal(0);fills=0;expected_fills={};actual_fills=set()
    phases={'source','replay_end','request','arrival_timer','assumed_reference_rejection','assumed_accept',
            'assumed_fill','assumed_ioc_cancel','assumed_ioc_cancel_ack'}
    with localcontext() as context:
        context.prec=100
        for index,(record,link,frame) in enumerate(zip(records,links,frames),1):
            phase=link['phase'];now=record['monotonic_ns'];event=record['event']
            require(phase in phases and record['paper_schema_version']==frame['paper_model_version']==1
                and record['sequence']==frame['sequence']==link['paper_sequence']==index
                and now==frame['monotonic_ns']==int(link['action_monotonic_ns']) and not frame['duplicate']
                and frame['source']==report['config']['source'],'proxy native frame or comparison link differs')
            require(phase=='assumed_fill' or all(key not in link for key in ('fee','spread_cost','slippage_cost','touch_price')),
                'non-fill comparison event includes execution costs')
            if phase=='source':
                seen_source+=1
                source=events[seen_source-1]
                expected=dict(type='session_started',config=expected_config) if seen_source==1 else base[seen_source-1]['event']
                require(event==expected and now==source['time'],'manual source mark differs from native original')
                state=(source['link'].get('feeds') or {}).get('bbo') or {}
                if source['usable']:
                    data=json.loads(source['source']['event']['text'])['data'];bid,ask=data['bbo'];q=source['link']['quote']
                    require(source['channel']=='bbo' and Decimal(bid['px'])==Decimal(q['bid']) and Decimal(ask['px'])==Decimal(q['ask'])
                        and data['time']==q['exchange_time_ms'] and q['connection_id']==source['source']['connection_id'],
                        'proxy original BBO price differs')
                    reference=dict(sequence=seen_source,monotonic_ns=str(now),connection_id=source['source']['connection_id'],
                        exchange_time_ms=str(data['time']),bid=bid['px'],ask=ask['px'],bid_size=bid['sz'],ask_size=ask['sz'])
                    key=(reference['connection_id'],reference['exchange_time_ms'])
                    price=(Decimal(bid['px']),Decimal(ask['px']))
                    if key in prices and prices[key]!=price:ambiguous.add(key)
                    prices[key]=price
                    for side,level in enumerate((bid,ask)):
                        cap=Decimal(level['sz'])*Decimal(scenario['assumptions']['top_size_fraction'])
                        available[key+(side,)]=min(available.get(key+(side,),cap),cap) if key not in ambiguous else Decimal(0)
                if (not state.get('acknowledged') or state.get('status')!='fresh' or reference is not None and
                    (reference['connection_id']!=source['source']['connection_id'] or reference['sequence']!=state.get('latest_sequence'))):
                    if reference is not None:
                        key=(reference['connection_id'],reference['exchange_time_ms'])
                        available[key+(0,)]=available[key+(1,)]=Decimal(0)
                    reference=None
            elif phase=='replay_end':
                require(seen_source==len(events) and index==len(records) and event==base[-1]['event']
                    and now==base[-1]['monotonic_ns'],'proxy generated end differs')
            else:
                require(seen_source>0,'proxy action precedes original source')
                source=events[seen_source-1]
                identity=link['order_id'];order=orders[identity]
                require(now>=source['time'] and (seen_source==len(events) or now<=events[seen_source]['time']),
                    'proxy action uses a future source prefix')
                require(seen_source==len(events) or now!=events[seen_source]['time'] or now==source['time'],
                    'equal-time source must precede an already scheduled arrival')
                if phase=='request':
                    require(identity not in requested and seen_source==order['after_market_sequence'] and now==source['time']
                        and event==dict(type='order_requested',**{k:order[k] for k in ('id','side','quantity','limit_price')}),
                        'manual request differs from frozen plan')
                    requested[identity]=(now,frame['order'])
                else:
                    sent,request_order=requested[identity]
                    arrival=sent+scenario['assumptions']['latency_ms']*1000000
                    require(now==arrival and arrival<=events[-1]['time'],'proxy action is not its declared in-source arrival')
                    d=chosen[identity]
                    require(int(d['request_monotonic_ns'])==sent and int(d['assumed_arrival_ns'])==arrival
                        and d['actual_execution']=='unknown','proxy assumed-time/uncertainty receipt differs')
                    if phase=='arrival_timer':
                        require(event==dict(type='timer') and identity not in arrivals and request_order['status']=='pending_new',
                            'proxy arrival does not resolve a pending request')
                        age=None if reference is None else arrival-int(reference['monotonic_ns'])
                        eligible=reference is not None and age<expected_config['stale_after_ms']*1000000 and frame['account']['mark_fresh']
                        require(d['reference_quote']==reference and d['reference_eligible']==eligible
                            and d['reference_age_ns']==(None if age is None else str(age))
                            and d['known_source_sequence']==seen_source,'proxy arrival reference is not the known original book')
                        arrivals[identity]=(reference,eligible)
                        if not eligible and age is not None and age>=expected_config['stale_after_ms']*1000000:
                            key=(reference['connection_id'],reference['exchange_time_ms'])
                            available[key+(0,)]=available[key+(1,)]=Decimal(0)
                            reference=None
                    elif phase=='assumed_reference_rejection':
                        require(not arrivals[identity][1] and event['type']=='order_rejected' and event['id']==identity,
                            'eligible reference was rejected as unavailable')
                    elif phase=='assumed_accept':
                        q,eligible=arrivals[identity];require(eligible and event==dict(type='order_accepted',id=identity),'proxy acceptance without reference')
                        side=1 if order['side']=='buy' else 0
                        touch=Decimal(q['ask' if side else 'bid'])
                        move=touch*Decimal(scenario['assumptions']['slippage_bps'])/10000
                        price=touch+move if side else touch-move
                        marketable=price<=Decimal(order['limit_price']) if side else price>=Decimal(order['limit_price'])
                        key=(q['connection_id'],q['exchange_time_ms'],side)
                        quantity=min(Decimal(order['quantity']),available[key]) if marketable else Decimal(0)
                        expected_fills[identity]=(quantity,price,touch,abs(touch-(Decimal(q['bid'])+Decimal(q['ask']))/2)*quantity,
                            move*quantity,price*quantity*Decimal(scenario['assumptions']['fee_rate']))
                        require(Decimal(d['assumed_fill_quantity'])==quantity and Decimal(d['assumed_fill_price'])==price
                            and Decimal(d['available_quantity'])==available[key] and d['marketable']==marketable,'proxy price/quantity/limit receipt differs')
                        available[key]-=quantity
                    elif phase=='assumed_fill':
                        quantity,price,touch,sc,sl,fee=expected_fills[identity];q,_=arrivals[identity]
                        require(identity not in actual_fills and quantity>0 and event['type']=='assumed_fill'
                            and event['order_id']==identity and event['fill_id']=='proxy-'+identity
                            and Decimal(event['quantity'])==quantity and Decimal(event['price'])==price
                            and frame['assumed_fill'] is not None and Decimal(frame['assumed_fill']['fee'])==fee
                            and link['reference_quote_sequence']==q['sequence'] and Decimal(link['touch_price'])==touch
                            and Decimal(link['fee'])==fee and Decimal(link['spread_cost'])==sc and Decimal(link['slippage_cost'])==sl,
                            'proxy fill/cost exceeds original reference or declared assumptions')
                        fees+=fee;spread+=sc;slippage+=sl;position+=quantity*(1 if order['side']=='buy' else -1)
                        fills+=1;actual_fills.add(identity)
                    elif phase in ('assumed_ioc_cancel','assumed_ioc_cancel_ack'):
                        require(expected_fills[identity][0]<Decimal(order['quantity'])
                            and event==dict(type='cancel_requested' if phase=='assumed_ioc_cancel' else 'cancel_accepted',id=identity),
                            'proxy IOC cancellation differs')
            require(link['known_source_sequence']==seen_source and int(link['source_monotonic_ns'])==events[seen_source-1]['time']
                and link['assumed_action']==(phase not in ('source','replay_end')),'proxy source reference differs')
            require(Decimal(frame['account']['fees'])==fees and Decimal(frame['account']['position_quantity'])==position,
                'native fee/position differs from assumed fills')
        require(set(requested)==set(orders) and seen_source==len(events) and actual_fills=={k for k,v in expected_fills.items() if v[0]>0}
            and fills==report['assumed_fills'],'proxy source/request/fill membership differs')
        final={o['id']:o for o in report['orders']}
        for identity,d in chosen.items():
            require(d['order']==orders[identity] and d['native_request_order']==requested[identity][1]
                and d['native_final_order']==final[identity],'proxy native lifecycle receipt differs')
            if requested[identity][1]['status']=='rejected':
                require(d['outcome']=='request_rejected' and d['reference_eligible'] is None,'rejected request gained a proxy outcome')
            elif identity not in arrivals:
                require(d['outcome']=='pending_at_source_end' and d['reference_eligible'] is None
                    and final[identity]['status']=='pending_new' and int(d['assumed_arrival_ns'])>events[-1]['time'],
                    'unobserved arrival was resolved')
            elif not arrivals[identity][1]:
                require(d['outcome']=='no_usable_reference' and final[identity]['status']=='rejected','unusable reference outcome differs')
            else:
                quantity,price,touch,sc,sl,fee=expected_fills[identity]
                expected='filled' if quantity==Decimal(orders[identity]['quantity']) else 'partial_fill_cancelled' if quantity>0 else 'not_marketable' if not d['marketable'] else 'no_remaining_capacity'
                require(d['outcome']==expected and Decimal(d['assumed_fee'])==fee and Decimal(d['spread_cost'])==sc
                    and Decimal(d['slippage_cost'])==sl and Decimal(d['touch_price'])==touch,'proxy decision/cost classification differs')
        account=report['account'];starting=Decimal(scenario['starting_collateral'])
        require(Decimal(account['fees'])==fees and Decimal(account['position_quantity'])==position
            and Decimal(account['collateral_balance'])==starting+Decimal(account['realized_pnl'])-fees,
            'proxy conditional ledger balance differs')
        pending=[o['id'] for o in report['orders'] if o['status'] in ('pending_new','open','partially_filled','pending_cancel')]
        closed=position==0 and not pending and fills>0
        result=dict(status='verified',fees=str(fees),spread_cost=str(spread),slippage_cost=str(slippage),
            ending_position_quantity=account['position_quantity'],pending_order_ids=pending,assumed_fills=fills,
            conditional_closed_pnl=str(Decimal(account['collateral_balance'])-starting) if closed else None,
            outcome='closed_under_assumptions' if closed else 'pending_at_source_end' if pending else 'open_exposure' if position else 'no_fills',
            actual_execution='unknown',ledger_kind='manual_simulation')
    return result
