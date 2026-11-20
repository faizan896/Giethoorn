"""Pure recorded BBO cadence measurements; no trading rules, I/O or clocks."""
from bisect import bisect_left
import json

POLICY = dict(cadence_policy_version=1,clock_discontinuity_ns='1000000000',
    interval_bins_upper_ns=['50000000','100000000','250000000','350000000','500000000','1000000000',None],
    percentiles=[50,90,95,99],percentile_method='nearest_rank',longest_intervals=5,
    series=['bbo_messages','native_opportunities'],cross_connections=False,
    deduplicate_source_recordings=True,orders_generated=False,profit_evaluated=False)


def require(condition,reason):
    if not condition:
        raise ValueError(reason)


def summary(intervals,count):
    values=sorted(int(row['delta_ns']) for row in intervals)
    require(type(count) is int and count>=0 and len(values)<=max(0,count-1) and all(v>=0 for v in values),
            'invalid interval/observation count or negative interval')
    bounds=[int(n) for n in POLICY['interval_bins_upper_ns'] if n is not None]
    histogram=[0]*(len(bounds)+1)
    for value in values:
        histogram[bisect_left(bounds,value)]+=1
    result=dict(observations=count,intervals=len(values),zero_intervals=sum(v==0 for v in values),
        minimum_ns=str(values[0]) if values else None,maximum_ns=str(values[-1]) if values else None,
        percentiles_ns={str(p):str(values[(p*len(values)+99)//100-1]) if values else None for p in POLICY['percentiles']},
        bins=[dict(lower_exclusive_ns=None if i==0 else str(bounds[i-1]),
                   upper_inclusive_ns=str(bounds[i]) if i<len(bounds) else None,count=n)
              for i,n in enumerate(histogram)],
        intervals_crossing_clock_discontinuities=sum(row['clock_discontinuities_crossed']>0 for row in intervals),
        longest_intervals=sorted(intervals,key=lambda r:(-int(r['delta_ns']),r['start']['sequence'],r['end']['sequence']))[:POLICY['longest_intervals']])
    require(sum(histogram)==len(values),'interval histogram differs')
    return result


def message(event):
    if event['channel']!='bbo':
        return None
    raw=json.loads(event['source']['event']['text'])
    data=raw.get('data')
    require(isinstance(data,dict) and type(data.get('time')) is int and data['time']>=0,
            'native-verified BBO message timestamp required')
    return data


def reference(event,exchange,epoch):
    source,frame,link=event['source'],event['frame'],event['link']
    state=(link.get('feeds') or {}).get('bbo') or {}
    return dict(sequence=event['sequence'],connection_id=source['connection_id'],
        monotonic_ns=str(event['time']),local_time_ns=str(source['local_time_ns']),
        exchange_time_ms=None if exchange is None else str(exchange),native_event=frame['event_kind'],
        native_market_status=frame['risk']['market_status'],bbo_status=state.get('status'),
        bbo_acknowledged=state.get('acknowledged'),clock_epoch=epoch)


class Series:
    def __init__(self,kind):
        self.kind=kind
        self.count=0
        self.first=self.last=None
        self.intervals=[]

    def add(self,point):
        if self.last is not None:
            delta=int(point['monotonic_ns'])-int(self.last['monotonic_ns'])
            require(delta>=0 and point['connection_id']==self.last['connection_id'],'cadence series clock/domain differs')
            self.intervals.append(dict(cadence_interval_version=1,series=self.kind,connection_id=point['connection_id'],
                start=self.last,end=point,delta_ns=str(delta),
                clock_discontinuities_crossed=point['clock_epoch']-self.last['clock_epoch']))
        self.first=self.first or point
        self.last=point
        self.count+=1

    def report(self,start,end):
        result=summary(self.intervals,self.count)
        result.update(first=self.first,last=self.last,
            leading_observed_silence_ns=None if self.first is None else str(int(self.first['monotonic_ns'])-start),
            trailing_observed_silence_ns=None if self.last is None else str(end-int(self.last['monotonic_ns'])),
            empty_observed_span_ns=str(end-start) if self.first is None else None,
            edge_silence_is_censored=True)
        return result


def analyze(child,events):
    require(events and len(events)<10000,'bounded native source events required')
    connections={}
    previous=None
    jumps=[]
    backward=0
    epoch=0
    maximum_gap=0
    for index,event in enumerate(events,1):
        source=event['source']
        require(event['sequence']==source['sequence']==index and event['time']==source['monotonic_ns'],
                'cadence source ordering differs')
        now,wall=event['time'],source['local_time_ns']
        require(type(now) is int and type(wall) is int and now>=0 and wall>=0,'exact source timestamps required')
        if previous is not None:
            delta=now-previous['monotonic_ns']
            require(delta>=0,'cadence source monotonic clock regressed')
            maximum_gap=max(maximum_gap,delta)
            clock_delta=wall-previous['local_time_ns']-delta
            backward+=wall<previous['local_time_ns']
            if abs(clock_delta)>=int(POLICY['clock_discontinuity_ns']) or wall<previous['local_time_ns']:
                epoch+=1
                jumps.append(dict(sequence=index,monotonic_ns=str(now),wall_minus_monotonic_step_ns=str(clock_delta),
                                  wall_clock_went_backward=wall<previous['local_time_ns']))
        previous=source
        connection=source['connection_id']
        require(type(connection) is int and connection>=0,'exact connection identity required')
        data=message(event)
        require((data is None and not event['usable']) or connection>0,'BBO data lacks a connection')
        if not connection:
            continue
        if connection not in connections:
            connections[connection]=dict(start=now,end=now,first_sequence=index,last_sequence=index,opened=None,terminal=None,
                bbo_acknowledgements=[],raw_status_counts={},raw_ack_counts={},raw_without_native_opportunity=0,
                raw_repeated_exchange_times=0,raw_regressed_exchange_times=0,native_repeated_exchange_times=0,
                last_raw_exchange=None,last_native_exchange=None,
                series={name:Series(name) for name in POLICY['series']})
        state=connections[connection]
        state.update(end=now,last_sequence=index)
        kind=source['event']['type']
        if kind=='connection_opened':state['opened']=dict(sequence=index,monotonic_ns=str(now))
        if kind in ('connection_closed','connection_error'):
            state['terminal']=dict(sequence=index,monotonic_ns=str(now),event=kind)
        if kind=='text_received' and event['channel']=='subscriptionResponse':
            payload=json.loads(source['event']['text']).get('data') or {}
            if payload.get('method')=='subscribe' and (payload.get('subscription') or {}).get('type')=='bbo':
                state['bbo_acknowledgements'].append(dict(sequence=index,monotonic_ns=str(now)))
        if data is not None:
            exchange=data['time']
            old=state['last_raw_exchange']
            state['raw_repeated_exchange_times']+=old==exchange
            state['raw_regressed_exchange_times']+=old is not None and exchange<old
            state['last_raw_exchange']=exchange
            point=reference(event,exchange,epoch)
            status=point['bbo_status'] or 'unreported'
            ack='acknowledged' if point['bbo_acknowledged'] is True else 'unacknowledged' if point['bbo_acknowledged'] is False else 'unreported'
            state['raw_status_counts'][status]=state['raw_status_counts'].get(status,0)+1
            state['raw_ack_counts'][ack]=state['raw_ack_counts'].get(ack,0)+1
            state['raw_without_native_opportunity']+=not event['usable']
            state['series']['bbo_messages'].add(point)
        if event['usable']:
            require(data is not None and event['link']['quote'] is not None,'native BBO opportunity lacks its original message')
            exchange=event['link']['quote']['exchange_time_ms']
            state['native_repeated_exchange_times']+=state['last_native_exchange']==exchange
            state['last_native_exchange']=exchange
            state['series']['native_opportunities'].add(reference(event,exchange,epoch))
    connection_rows=[]
    intervals=[]
    for identity,state in sorted(connections.items()):
        series={kind:state['series'][kind].report(state['start'],state['end']) for kind in POLICY['series']}
        for value in state['series'].values():
            require(len(value.intervals)==max(0,value.count-1),'per-connection interval identity differs')
            intervals.extend(value.intervals)
        connection_rows.append(dict(connection_id=identity,first_sequence=state['first_sequence'],last_sequence=state['last_sequence'],
            first_source_ns=str(state['start']),last_source_ns=str(state['end']),observed_span_ns=str(state['end']-state['start']),
            connection_opened=state['opened'],terminal_marker=state['terminal'],bbo_acknowledgements=state['bbo_acknowledgements'],
            raw_status_counts=state['raw_status_counts'],raw_ack_counts=state['raw_ack_counts'],
            raw_bbo_without_native_opportunity=state['raw_without_native_opportunity'],
            raw_repeated_exchange_times=state['raw_repeated_exchange_times'],raw_regressed_exchange_times=state['raw_regressed_exchange_times'],
            native_repeated_exchange_times=state['native_repeated_exchange_times'],series=series))
    combined={kind:summary([row for row in intervals if row['series']==kind],
        sum(state['series'][kind].count for state in connections.values())) for kind in POLICY['series']}
    report=dict(cadence_recording_version=1,child=child,source_records=len(events),
        source_first_ns=str(events[0]['time']),source_last_ns=str(events[-1]['time']),
        source_span_ns=str(events[-1]['time']-events[0]['time']),max_source_event_gap_ns=str(maximum_gap),
        source_policy=events[0]['source']['event'].get('policy'),
        source_clock_discontinuities=jumps,wall_clock_backward_events=backward,
        connections=connection_rows,series=combined,
        combined_series_scope='Within-connection interval samples only; no cross-connection interval.',
        measured_order_latency=False,fill_probability_estimated=False,profit_evaluated=False)
    intervals.sort(key=lambda r:(r['end']['sequence'],r['series']))
    return report,intervals
