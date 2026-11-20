"""Pure close compilation from the proxy control's causal native position."""
import copy
from decimal import Decimal,localcontext

if __package__:
    from . import cost_core as FROZEN,model_compare_core as PROXY
else:
    import cost_core as FROZEN
    import model_compare_core as PROXY

POLICY=dict(causal_proxy_policy_version=1,policy_id='r001-known-book-causal-001',
    original_cost_policy_id=FROZEN.POLICY['policy_id'],proxy_model=PROXY.POLICY['proxy_model'],
    max_cases=24,max_requests_per_case=2,own_position_close=True,one_cycle_per_child_profile=True,
    exploratory=True,actual_execution_known=False,live_orders_enabled=False,
    portfolio_profit_evaluated=False,full_window_verified=False)
require=FROZEN.require


def prefix_rows(records,links,frames,decision,final=False):
    require(decision is not None and len(records)==len(links)==len(frames),'bounded native decision prefix required')
    sequence,now=decision['sequence'],decision['monotonic_ns']
    require(type(sequence) is int and sequence>0 and type(now) is int and now>=0,'exact source decision required')
    result=[]
    for record,link,frame in zip(records,links,frames):
        if link['phase']=='replay_end' or link['known_source_sequence']>sequence or record['monotonic_ns']>now:
            break
        if link['phase']=='request' and record['event']['id']=='close':
            require(final,'entry-only control contains a close');break
        result.append([record,link,frame])
    require(result and result[-1][1]['known_source_sequence']==sequence
        and sum(row[1]['phase']=='source' for row in result)==sequence,
        'native decision source boundary is missing')
    return result


def position_at(rows,entry):
    require(len(entry['orders'])==1 and entry['orders'][0]['id']=='entry','one fixed entry request required')
    state=rows[-1][2]
    with localcontext() as context:
        context.prec=100
        position=Decimal(state['account']['position_quantity'])
        fills=sum((Decimal(frame['assumed_fill']['quantity'])*(1 if frame['assumed_fill']['side']=='buy' else -1)
            for _,_,frame in rows if frame['assumed_fill'] is not None),Decimal(0))
        require(position==fills and abs(position)<=min(Decimal(FROZEN.POLICY['target_quantity']),Decimal(entry['orders'][0]['quantity'])),
            'native entry-prefix quantity differs or exceeds the frozen target')
        require(position==0 or (position>0)==(entry['orders'][0]['side']=='buy'),'entry-prefix position reversed')
    return position,state


def compile_close(entry,decision,records,links,frames):
    plan=copy.deepcopy(entry)
    require(len(plan['orders'])==1 and plan['orders'][0]['id']=='entry','fixed entry-only control required')
    receipt=dict(close_compilation_version=1,status='missing_decision',decision=copy.deepcopy(decision),
        known_position=None,working_orders=None,risk_at_decision=None,prefix_records=None,prefix_sha256=None)
    if decision is None:return plan,receipt
    rows=prefix_rows(records,links,frames,decision)
    position,state=position_at(rows,entry)
    working=state['risk']['working_orders']
    receipt.update(status='unresolved_entry' if working else 'flat_no_close' if position==0 else 'close_compiled',
        known_position=FROZEN.text(position),working_orders=working,risk_at_decision=copy.deepcopy(state['risk']),
        prefix_records=len(rows),prefix_sha256=FROZEN.fingerprint(rows))
    if not working and position!=0:
        side='sell' if position>0 else 'buy';quote=decision['quote']
        plan['orders'].append(dict(id='close',after_market_sequence=decision['sequence'],side=side,
            quantity=FROZEN.text(abs(position)),limit_price=FROZEN.limit_price(side,quote['bid'],quote['ask'])))
    return plan,receipt


def verify_close(entry,plan,decision,receipt,control,final):
    require(receipt['close_compilation_version']==1 and receipt['decision']==decision,
        'close compiler version or source decision differs')
    require({k:v for k,v in plan.items() if k!='orders'}=={k:v for k,v in entry.items() if k!='orders'}
        and plan['orders'][0]==entry['orders'][0] and 1<=len(plan['orders'])<=2,'compiled plan changed entry or assumptions')
    if decision is None:
        require(plan==entry and receipt['status']=='missing_decision' and receipt['known_position'] is None
            and all(receipt[key] is None for key in ('prefix_sha256','prefix_records','risk_at_decision','working_orders')),
            'missing decision gained a closing order or known position')
        return dict(status='verified',decision_available=False,prefix_records=None,prefix_sha256=None)
    a=prefix_rows(*control,decision)
    b=prefix_rows(*final,decision,final=True)
    require(a==b,'compiled close changed the complete control prefix')
    position,state=position_at(a,entry)
    require(receipt['prefix_records']==len(a) and receipt['prefix_sha256']==FROZEN.fingerprint(a)
        and Decimal(receipt['known_position'])==position and receipt['working_orders']==state['risk']['working_orders']
        and receipt['risk_at_decision']==state['risk'],'close receipt differs from native prefix state')
    expected='unresolved_entry' if state['risk']['working_orders'] else 'flat_no_close' if position==0 else 'close_compiled'
    require(receipt['status']==expected,'close decision classification differs')
    if expected!='close_compiled':require(plan==entry,'flat or pending entry gained a close')
    else:
        close=plan['orders'][-1];quote=decision['quote']
        require(len(plan['orders'])==2 and close['id']=='close' and close['after_market_sequence']==decision['sequence']
            and Decimal(close['quantity'])==abs(position) and close['side']==('sell' if position>0 else 'buy'),
            'close quantity, side or anchor differs from own native position')
        with localcontext() as context:
            context.prec=100
            rate=Decimal(FROZEN.POLICY['limit_envelope_bps'])/10000
            expected_limit=Decimal(quote['bid' if position>0 else 'ask'])*(1-rate if position>0 else 1+rate)
            require(Decimal(close['limit_price'])==expected_limit,'close limit differs from known decision quote')
    return dict(status='verified',decision_available=True,prefix_records=len(a),prefix_sha256=FROZEN.fingerprint(a))
