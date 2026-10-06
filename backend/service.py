import hashlib, json, math
from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select, update
from . import db
from .recognition import normalize_code, CODE
from .geometry import validate_geometry, contained
from .measurement import states, summary

class Conflict(ValueError): pass
def effective_today(): return datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()
class Store:
    def __init__(self,engine=db.engine): self.engine=engine
    def state(self,conn,pid):
        p=conn.execute(db.projects.select().where(db.projects.c.id==pid)).mappings().first()
        if not p: raise ValueError('Projeto não encontrado.')
        return {'project':dict(p),**{name:db.rows(conn,name,pid) for name in db.tables if name not in {'projects','snapshots'}}}
    def read(self,pid):
        with self.engine.begin() as c:
            # A write lock (no version increment) gives one coherent state under both databases.
            c.execute(update(db.projects).where(db.projects.c.id==pid).values(version=db.projects.c.version))
            return self.state(c,pid)
    def create_project(self,name,author='local'):
        if not name.strip(): raise ValueError('Informe o nome da obra.')
        with self.engine.begin() as c:
            p={'id':db.uid(),'name':name.strip(),'version':1,'settings':{'units':'unidades / pontos PDF','scope_categories':['structure'],'partial_progress':False,'auto_approval':False},'created_at':db.now()}
            c.execute(db.projects.insert().values(**p))
            for name,token in [('Fabricação','info'),('Recebimento','atencao'),('Montagem','sucesso')]:
                db.insert(c,'stages',p['id'],{'name':name,'token':token,'data':{'dependencies':[],'approved':False}})
            return p
    def mutate(self,pid,expected,key,author,action,payload,callback):
        if not key or len(key)>128: raise ValueError('Chave de idempotência obrigatória.')
        digest=hashlib.sha256(json.dumps({'action':action,'payload':payload},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.engine.begin() as c:
            # Serializes all writes including event allocation and snapshot creation.
            locked=c.execute(update(db.projects).where(db.projects.c.id==pid).values(version=db.projects.c.version)).rowcount
            if not locked: raise ValueError('Projeto não encontrado.')
            previous=c.execute(db.audit.select().where(db.audit.c.project_id==pid,db.audit.c.request_key==key)).mappings().first()
            if previous:
                if previous['data'].get('digest')!=digest: raise Conflict('Chave de idempotência reutilizada para outra ação.')
                response=previous['data']['response']
                if response.get('snapshot_ref'):return {'version':response['version'],'result':db.get(c,'snapshots',response['snapshot_ref'],pid)}
                return response
            changed=c.execute(update(db.projects).where(db.projects.c.id==pid,db.projects.c.version==expected).values(version=expected+1)).rowcount
            if not changed: raise Conflict('O projeto mudou em outra sessão. Atualize antes de salvar.')
            result=callback(c)
            response={'version':expected+1,'result':result}
            saved_response={'version':expected+1,'snapshot_ref':result['id']} if action=='snapshot' else response
            db.insert(c,'audit',pid,{'action':action,'author':author,'request_key':key,
                'data':{'digest':digest,'payload':payload,'response':saved_response,'project_version':expected+1}})
            return response
    def save(self,pid,kind,payload,expected,key,author='local',role='editor'):
        allowed={'piece_types','instances','views','labels','geometries','occurrences','overlays','stages','bom_entries'}
        if kind not in allowed: raise ValueError('Entidade não editável.')
        return self.mutate(pid,expected,key,author,'save:'+kind,payload,lambda c:self._save(c,pid,kind,payload,author,role))
    def _save(self,c,pid,kind,payload,author,role):
        values={k:v for k,v in payload.items() if k not in {'id','version','expected_version','project_id','created_at'}}
        current=db.get(c,kind,payload['id'],pid) if payload.get('id') else None
        if current and payload.get('version')!=current['version']: raise Conflict('Versão da entidade alterada; recarregue.')
        merged={**(current or {}),**values}
        self.validate(c,pid,kind,merged,current,role)
        if kind=='piece_types':values['code']=merged['code']
        if kind=='overlays':values['author']=author
        fields={col.name for col in db.tables[kind].columns}-{'id','version','project_id','created_at'}
        if set(values)-fields: raise ValueError('Campo não reconhecido: '+','.join(set(values)-fields))
        if current:
            c.execute(update(db.tables[kind]).where(db.tables[kind].c.id==current['id']).values(**values,version=current['version']+1))
            result=db.get(c,kind,current['id'],pid)
        else: result=db.insert(c,kind,pid,values)
        if kind=='occurrences' and result['association']=='APROVADA':
            proposal_id=result['data'].get('proposal_id')
            if proposal_id:
                proposal=db.get(c,'proposals',proposal_id,pid)
                if proposal['occurrence_id']!=result['id']:raise ValueError('Proposta pertence a outra ocorrência.')
                c.execute(update(db.proposals).where(db.proposals.c.id==proposal_id).values(state='APROVADA',version=proposal['version']+1,data={**proposal['data'],'decided_by':author,'decided_at':db.now(),'chosen_instance_id':result.get('instance_id')}))
            db.insert(c,'decisions',pid,{'proposal_id':proposal_id,'occurrence_id':result['id'],'author':author,'data':{'reason':result['data']['reason'],'evidence':result['data'].get('evidence'),'source':'manual','protected':True,'before':current}})
        return result
    def validate(self,c,pid,kind,v,current,role):
        data=v.get('data',{})
        if not isinstance(data,dict): raise ValueError('Dados devem ser um objeto.')
        for col in db.tables[kind].columns:
            if col.foreign_keys and col.name!='project_id' and v.get(col.name):
                target=next(iter(col.foreign_keys)).target_fullname.split('.')[0]
                db.get(c,target,v[col.name],pid)
        if kind=='piece_types':
            code=normalize_code(v.get('code',''))
            if not CODE.fullmatch(code): raise ValueError('Código esperado: três dígitos, hífen e letras (ex.: 208-AB).')
            v['code']=code
            if v.get('quantity') is not None and (type(v['quantity']) is not int or v['quantity']<0): raise ValueError('Quantidade inteira não negativa ou desconhecida.')
            if v['validation'] not in {'DRAFT','APPROVED','CONFLICT'}: raise ValueError('Validação inválida.')
            if v['category'] not in {'structure','consumable','bolt'}: raise ValueError('Categoria inválida.')
            if v['validation']=='APPROVED' and (v.get('quantity') is None or not data.get('reason')): raise ValueError('Aprovação requer quantidade e motivo/evidência.')
            if v['validation']=='APPROVED' and role not in {'reviewer','local'}: raise ValueError('Somente revisor aprova o catálogo.')
            if current:
                used=[e for e in db.rows(c,'progress_events',pid) if e['type_id']==current['id']]
                totals={s:sum(x for (t,st,_),x in states(used).items() if st==s) for s in {e['stage_id'] for e in used}}
                if v.get('quantity') is not None and (max(totals.values(),default=0)>v['quantity'] or sum(i['type_id']==current['id'] for i in db.rows(c,'instances',pid))>v['quantity']): raise ValueError('Escopo menor que unidades ou avanço existente; retifique primeiro.')
                if (v.get('quantity')!=current['quantity'] or v['code']!=current['code']) and not data.get('reason'): raise ValueError('Alteração de escopo/código requer motivo.')
            if data.get('weight_validated'):
                from .bom import number_br
                weight=number_br(data.get('weight'))
                if weight is None or weight<0 or not data.get('weight_reason') or data.get('weight_semantics') not in {'line_total','unit'} or role not in {'reviewer','local'}: raise ValueError('Peso exige semântica, valor, motivo e aprovação do revisor.')
                if data.get('weight_semantics')=='line_total' and not data.get('homogeneous'): raise ValueError('Derivação do peso unitário exige unidades homogêneas aprovadas.')
        if kind=='instances':
            piece=db.get(c,'piece_types',v['type_id'],pid)
            if current and current['type_id']!=v['type_id']: raise ValueError('Não mudar o tipo de unidade com identidade estável.')
            if v['state'] not in {'identified','provisional'}: raise ValueError('Estado de unidade inválido.')
            if v['state']=='identified' and not (data.get('location') and data.get('evidence')): raise ValueError('Localização identificada exige descrição e evidência.')
            if v['state']=='provisional' and any(data.get(f) for f in ['location','rack','axes','level','side']): raise ValueError('Unidade provisória não recebe localização presumida.')
            count=sum(i['type_id']==v['type_id'] and i['id']!=(current or {}).get('id') for i in db.rows(c,'instances',pid))
            if piece['quantity'] is None or count+1>piece['quantity']: raise ValueError('Unidades excedem quantidade conhecida do catálogo.')
        if kind=='views':
            page=db.get(c,'pages',v['page_id'],pid)
            validate_geometry({'kind':'polygon','paths':[data.get('polygon',[])]},page['data']['cropbox'])
            if v['kind'] not in {'plan','elevation','section','typical','table','reference','unknown'}: raise ValueError('Tipo de vista inválido.')
            if current and current['page_id']!=v['page_id']: raise ValueError('Crie outra vista para outra página.')
            if current:
                for occurrence in db.rows(c,'occurrences',pid):
                    if occurrence['view_id']==current['id']:contained(db.get(c,'geometries',occurrence['geometry_id'],pid)['data'],data)
        if kind=='labels':
            if v['method'] not in {'manual','native','ocr'}: raise ValueError('Método de leitura inválido.')
        if kind=='geometries':
            page=db.get(c,'pages',v['page_id'],pid)
            validate_geometry(data,page['data']['cropbox'])
            if current and current['page_id']!=v['page_id']: raise ValueError('Geometria não pode mudar de página.')
            for occurrence in db.rows(c,'occurrences',pid):
                if occurrence['geometry_id']==(current or {}).get('id'):
                    view=db.get(c,'views',occurrence['view_id'],pid)
                    contained(data,view['data'])
            if v['origin'] not in {'manual','automatic'}: raise ValueError('Origem de geometria inválida.')
        if kind=='occurrences':
            geometry=db.get(c,'geometries',v['geometry_id'],pid)
            view=db.get(c,'views',v['view_id'],pid)
            if view['page_id']!=geometry['page_id']: raise ValueError('Vista e geometria devem estar na mesma página.')
            contained(geometry['data'],view['data'])
            if v.get('label_id') and db.get(c,'labels',v['label_id'],pid)['page_id']!=view['page_id']: raise ValueError('Observação fora da página da vista.')
            if v['role'] not in {'installation','typical','reference','table'}: raise ValueError('Papel inválido.')
            if view['kind'] in {'typical','table'} and (v['role']=='installation' or v.get('instance_id')):raise ValueError('Vista de detalhe típico/tabela não confirma instalação localizada.')
            if v['role']!='installation' and v.get('instance_id'): raise ValueError('Detalhe, referência ou tabela não gera medição individual.')
            if v['association'] not in {'APROVADA','PROPOSTA FORTE','AMBÍGUA','NÃO ASSOCIADA'}: raise ValueError('Classe de associação inválida.')
            if v.get('instance_id'):
                unit=db.get(c,'instances',v['instance_id'],pid)
                if unit['type_id']!=v['type_id']: raise ValueError('Unidade pertence a outro código.')
                if unit['state']!='identified': raise ValueError('Ocorrência física exige unidade localizada e identificada.')
            if v['association']=='APROVADA' and (role not in {'reviewer','local'} or not data.get('reason')): raise ValueError('Aprovação requer revisor e motivo/evidência.')
            if current and not data.get('reason'): raise ValueError('Correção de vínculo requer motivo.')
        if kind=='overlays':
            geometry=db.get(c,'geometries',v['geometry_id'],pid)
            if geometry['page_id']!=v['page_id']: raise ValueError('Sobreposição fora da página.')
            if v['scope'] not in {'annotation','occurrence','instance','type'}: raise ValueError('Escopo inválido.')
            required={'occurrence':'occurrence_id','instance':'instance_id','type':'type_id'}.get(v['scope'])
            if required and not v.get(required): raise ValueError('Informe o alvo da sobreposição.')
            if v.get('occurrence_id'):
                occ=db.get(c,'occurrences',v['occurrence_id'],pid);view=db.get(c,'views',occ['view_id'],pid)
                if view['page_id']!=v['page_id']: raise ValueError('Ocorrência fora da página.')
            if not v.get('reason'): raise ValueError('Anotação/override requer motivo.')
            if data.get('token','info') not in {'combio','sucesso','atencao','erro','info','serie-1','serie-2','serie-3','serie-4'}: raise ValueError('Cor fora da paleta.')
        if kind=='stages':
            if v.get('token') not in {'sucesso','atencao','erro','info','serie-1','serie-2','serie-3','serie-4'}: raise ValueError('Token inválido.')
            if data.get('approved') and role not in {'reviewer','local'}: raise ValueError('Revisor aprova a configuração de etapa.')
            for dependency in data.get('dependencies',[]):
                db.get(c,'stages',dependency,pid)
                if dependency==v.get('id'): raise ValueError('Etapa não pode depender de si mesma.')
            graph={s['id']:s['data'].get('dependencies',[]) for s in db.rows(c,'stages',pid)}
            if v.get('id'): graph[v['id']]=data.get('dependencies',[])
            def visit(node,path):
                if node in path: raise ValueError('Ciclo nas dependências de etapas.')
                for other in graph.get(node,[]): visit(other,path+[node])
            for node in graph: visit(node,[])
        if kind=='bom_entries':
            if v['approval']=='APPROVED' and (role not in {'reviewer','local'} or not data.get('reason')): raise ValueError('Revisão da BOM exige revisor e motivo.')
    def progress(self,pid,payload,expected,key,author='local'):
        return self.mutate(pid,expected,key,author,'progress',payload,lambda c:self._progress(c,pid,payload,expected,author))
    def _progress(self,c,pid,payload,expected,author):
        piece=db.get(c,'piece_types',payload['type_id'],pid)
        stage=db.get(c,'stages',payload['stage_id'],pid)
        if piece['validation']!='APPROVED' or piece['quantity'] is None: raise ValueError('Revise e aprove a quantidade do código antes de medir.')
        if not stage['data'].get('approved'): raise ValueError('A etapa precisa de configuração aprovada.')
        reason=payload.get('reason','').strip()
        if not reason: raise ValueError('Informe o motivo/evidência da medição.')
        effective=payload.get('effective_at',effective_today())
        date.fromisoformat(effective)
        if effective>effective_today(): raise ValueError('Data efetiva futura não é medição realizada.')
        events=db.rows(c,'progress_events',pid);balances=states(events)
        mode=payload.get('mode');stage_id=stage['id'];type_id=piece['id'];changes=[]
        aggregate=balances.get((type_id,stage_id,None),0)
        units=[i for i in db.rows(c,'instances',pid) if i['type_id']==type_id]
        chosen=payload.get('instance_ids',[])
        if len(chosen)!=len(set(chosen)): raise ValueError('Seleção de unidades duplicada.')
        if mode=='aggregate':
            target=payload.get('quantity')
            if type(target) is not int or target<0: raise ValueError('Saldo agregado deve ser inteiro não negativo.')
            if stage['data'].get('dependencies') and target>0: raise ValueError('Saldo sem localização não permite verificar dependências individuais; aloque unidades primeiro.')
            changes=[(None,target-aggregate)]
        elif mode in {'units','all','allocate'}:
            if mode=='all':
                # Quantity includes currently unlocated balance; never selects geometry arbitrarily.
                if not payload.get('confirm_all') or payload.get('preview_quantity')!=piece['quantity']: raise ValueError('Confirme explicitamente todas as unidades e a quantidade do preview.')
                chosen=[i['id'] for i in units if i['state']=='identified']
                target_aggregate=piece['quantity']-len(chosen)
                changes.append((None,target_aggregate-aggregate))
            for id in chosen:
                instance=db.get(c,'instances',id,pid)
                if instance['type_id']!=type_id or instance['state']!='identified': raise ValueError('Escolha unidades localizadas deste código.')
                old=balances.get((type_id,stage_id,id),0)
                target=payload.get('value',1) if mode=='units' else 1
                if target not in {0,1}: raise ValueError('MVP mede conclusão 0 ou 1 por unidade; parcial ainda não configurado.')
                if mode=='allocate' and old!=0: raise ValueError('Unidade já medida; alocação duplicaria saldo.')
                changes.append((id,target-old))
            if mode=='allocate':
                if not chosen or aggregate<len(chosen): raise ValueError('Saldo agregado insuficiente para alocação.')
                changes.append((None,-len(chosen)))
            elif mode=='units' and not chosen: raise ValueError('Selecione ao menos uma unidade.')
        else: raise ValueError('Escopo inválido.')
        deps=stage['data'].get('dependencies',[])
        for instance,delta in changes:
            if delta>0 and deps:
                if instance is None: raise ValueError('Dependências exigem localização das unidades.')
                if any(balances.get((type_id,dependency,instance),0)<1 for dependency in deps): raise ValueError('Dependência da etapa não concluída nesta unidade.')
        group=db.uid();created=[]
        for instance,delta in changes:
            if abs(delta)<1e-9: continue
            created.append(db.insert(c,'progress_events',pid,{'type_id':type_id,'instance_id':instance,'stage_id':stage_id,
                'delta':delta,'effective_at':effective,'author':author,'reason':reason,'group_id':group,
                'data':{'mode':mode,'evidence':payload.get('evidence'),'source_version':expected}}))
        self.validate_balances(db.rows(c,'progress_events',pid),{p['id']:p for p in db.rows(c,'piece_types',pid)})
        if not created: raise ValueError('Não há mudança de saldo ou de conclusão.')
        return {'events':created,'summary':summary(self.state(c,pid),stage_id)}
    @staticmethod
    def validate_balances(events,pieces):
        # Validate every effective-date prefix, including a backdated correction.
        for cutoff in sorted({e['effective_at'] for e in events}):
            balances=states(events,cutoff)
            totals={}
            for (type_id,stage_id,instance),amount in balances.items():
                if amount<-.0000001 or (instance and amount>1.0000001): raise ValueError('Saldo histórico negativo ou unidade duplicada na data efetiva.')
                totals[(type_id,stage_id)]=totals.get((type_id,stage_id),0)+amount
            for (type_id,_),amount in totals.items():
                if pieces[type_id]['quantity'] is None or amount>pieces[type_id]['quantity']+.0000001: raise ValueError('Avanço excede o escopo previsto. Altere o escopo explicitamente ou aloque o saldo existente.')
    def reverse(self,pid,payload,expected,key,author):
        def operation(c):
            original=db.get(c,'progress_events',payload['event_id'],pid)
            if not payload.get('reason'): raise ValueError('Retificação exige motivo.')
            group=[e for e in db.rows(c,'progress_events',pid) if e['group_id']==original['group_id']]
            if any(e.get('reverted_event_id') for e in group): raise ValueError('Retificação de retificação requer novo registro de avanço.')
            existing={e.get('reverted_event_id') for e in db.rows(c,'progress_events',pid)}
            if any(e['id'] in existing for e in group): raise ValueError('Evento já retificado.')
            effective=payload.get('effective_at',effective_today());date.fromisoformat(effective)
            if effective>effective_today(): raise ValueError('Data futura inválida.')
            new_group=db.uid();created=[]
            for e in group:
                created.append(db.insert(c,'progress_events',pid,{'type_id':e['type_id'],'instance_id':e['instance_id'],
                    'stage_id':e['stage_id'],'delta':-e['delta'],'effective_at':effective,'author':author,
                    'reason':payload['reason'],'group_id':new_group,'reverted_event_id':e['id'],'data':{'reversal':True}}))
            self.validate_balances(db.rows(c,'progress_events',pid),{p['id']:p for p in db.rows(c,'piece_types',pid)})
            return created
        return self.mutate(pid,expected,key,author,'reverse',payload,operation)
    def snapshot(self,pid,payload,expected,key,author):
        def operation(c):
            db.get(c,'stages',payload['stage_id'],pid)
            cutoff=payload['cutoff'];date.fromisoformat(cutoff)
            state=self.state(c,pid)
            return db.insert(c,'snapshots',pid,{'cutoff':cutoff,'stage_id':payload['stage_id'],
                'data':{'schema_version':1,'state':state,'summary':summary(state,payload['stage_id'],cutoff),'generated_at':db.now()}})
        return self.mutate(pid,expected,key,author,'snapshot',payload,operation)
