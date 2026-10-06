from datetime import datetime
from collections import defaultdict

def states(events,cutoff=None):
    balances=defaultdict(float)
    for event in events:
        if cutoff and event['effective_at'][:10]>cutoff[:10]: continue
        balances[(event['type_id'],event['stage_id'],event.get('instance_id'))]+=event['delta']
    return dict(balances)
def summary(state,stage_id,cutoff=None,categories=None):
    categories=categories or state['project']['settings'].get('scope_categories',['structure'])
    balances=states(state['progress_events'],cutoff)
    current={d['id'] for d in state['drawings'] if not d['data'].get('superseded')}
    page_drawing={p['id']:p['drawing_id'] for p in state['pages']}
    view_drawing={v['id']:page_drawing[v['page_id']] for v in state['views']}
    mapped={o['instance_id'] for o in state['occurrences'] if o['association']=='APROVADA' and o['instance_id'] and view_drawing[o['view_id']] in current and o['role']=='installation'}
    result=[];denominator=0;completed=0;approved_mapped=0;unvalidated=0
    for piece in state['piece_types']:
        total=sum(v for (t,s,_),v in balances.items() if t==piece['id'] and s==stage_id)
        aggregate=balances.get((piece['id'],stage_id,None),0)
        mapped_count=len({i['id'] for i in state['instances'] if i['type_id']==piece['id'] and i['id'] in mapped})
        valid=piece['validation']=='APPROVED' and piece['quantity'] is not None
        included=piece['category'] in categories
        if included and valid:
            denominator+=piece['quantity'];completed+=total;approved_mapped+=mapped_count
        elif included: unvalidated+=1
        result.append({**piece,'completed':round(total,8),'aggregate':round(aggregate,8),'mapped':mapped_count,
                       'percent':100*total/piece['quantity'] if valid and piece['quantity'] else None,
                       'included':included,'validated':valid})
    pending=sum(p['validation']!='APPROVED' for p in state['piece_types'])
    pending+=sum(o['association']!='APROVADA' for o in state['occurrences'])
    pending+=sum(b['approval']!='APPROVED' for b in state['bom_entries'])
    pending+=sum(p['state']!='APROVADA' for p in state.get('proposals',[]))
    return {'rows':result,'denominator':denominator,'completed':round(completed,8),
        'percent':100*completed/denominator if denominator else None,
        'mapped':approved_mapped,'mapping_percent':100*approved_mapped/denominator if denominator else None,
        'pending':pending,'unvalidated_types':unvalidated,'scope_categories':categories,
        'weight':'Pendente de validação','cutoff':cutoff,'stage_id':stage_id}
