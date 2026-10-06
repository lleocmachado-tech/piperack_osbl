"""One manual field mark, committed together with its identity and measurement."""
from . import db
from .geometry import validate_geometry, contained
from .measurement import states
from .service import effective_today
from datetime import date


def mark(store, pid, payload, expected, key, author, role):
    def operation(c):
        reason = payload.get('reason', '').strip()
        if not reason:
            raise ValueError('Descreva a verificação feita em campo.')
        effective = payload.get('effective_at', '')
        date.fromisoformat(effective)
        if effective > effective_today():
            raise ValueError('A verificação em campo não pode ter data futura.')
        if not payload.get('confirm_installation'):
            raise ValueError('Confirme que a área representa uma peça localizada na montagem.')
        piece = db.get(c, 'piece_types', payload['type_id'], pid)
        stage = db.get(c, 'stages', payload['stage_id'], pid)
        page = db.get(c, 'pages', payload['page_id'], pid)
        drawing = db.get(c, 'drawings', page['drawing_id'], pid)
        if drawing['data'].get('superseded'):
            raise ValueError('Escolha a revisão atual para marcar a montagem.')
        if piece['category'] != 'structure':
            raise ValueError('Selecione um código de estrutura para a montagem.')
        if piece['validation'] != 'APPROVED':
            if not payload.get('approve_quantity'):
                raise ValueError('Confirme a quantidade prevista deste código.')
            piece = store._save(c, pid, 'piece_types', {
                **piece, 'quantity': payload.get('quantity'), 'validation': 'APPROVED',
                'data': {**piece['data'], 'reason': reason},
            }, author, role)
        if not stage['data'].get('approved'):
            if not payload.get('approve_stage'):
                raise ValueError('Confirme a etapa antes de registrar a montagem.')
            stage = store._save(c, pid, 'stages', {
                **stage, 'data': {**stage['data'], 'approved': True, 'reason': reason},
            }, author, role)
        if payload.get('instance_id'):
            unit = db.get(c, 'instances', payload['instance_id'], pid)
            if unit['type_id'] != piece['id'] or unit['state'] != 'identified':
                raise ValueError('Escolha uma posição identificada deste código.')
        else:
            location = payload.get('location', '').strip()
            if not location:
                raise ValueError('Informe onde esta peça está na obra.')
            if any(i['type_id'] == piece['id'] and i['data'].get('location', '').strip().casefold() == location.casefold()
                   for i in db.rows(c, 'instances', pid)):
                raise ValueError('Esta posição já existe. Selecione a peça cadastrada para evitar duplicidade.')
            unit = store._save(c, pid, 'instances', {
                'type_id': piece['id'], 'state': 'identified',
                'data': {'location': location, 'evidence': reason},
            }, author, role)
        geometry = payload['geometry']
        validate_geometry(geometry, page['data']['cropbox'])
        if payload.get('view_id'):
            view = db.get(c, 'views', payload['view_id'], pid)
            if view['page_id'] != page['id'] or view['kind'] in {'typical', 'table', 'reference'}:
                raise ValueError('Use uma vista de montagem desta página.')
            contained(geometry, view['data'])
        else:
            # A manually confirmed local installation region, never a whole-sheet assumption.
            from shapely.geometry import Polygon, LineString
            for existing in db.rows(c, 'views', pid):
                if existing['page_id'] == page['id'] and existing['kind'] in {'typical', 'table', 'reference'}:
                    boundary = Polygon(existing['data']['polygon'])
                    if any(boundary.intersects(Polygon(p) if geometry['kind'] in {'polygon', 'multipolygon'} else LineString(p))
                           for p in geometry['paths']):
                        raise ValueError('A marca cruza um detalhe, tabela ou referência. Revise a vista em Gestão e revisão.')
            points = [p for path in geometry['paths'] for p in path]
            pad = geometry.get('width', 2) / 2 + 1
            crop = page['data']['cropbox']
            x0 = max(crop[0], min(p[0] for p in points) - pad)
            y0 = max(crop[1], min(p[1] for p in points) - pad)
            x1 = min(crop[2], max(p[0] for p in points) + pad)
            y1 = min(crop[3], max(p[1] for p in points) + pad)
            view = store._save(c, pid, 'views', {
                'page_id': page['id'], 'name': unit['data']['location'], 'kind': 'unknown',
                'data': {'polygon': [[x0,y0],[x1,y0],[x1,y1],[x0,y1]],
                         'title_evidence': reason, 'quality': 'manual', 'field_region': True},
            }, author, role)
        area = store._save(c, pid, 'geometries', {
            'page_id': page['id'], 'origin': 'manual', 'data': geometry,
        }, author, role)
        occurrence = store._save(c, pid, 'occurrences', {
            'view_id': view['id'], 'geometry_id': area['id'], 'type_id': piece['id'],
            'instance_id': unit['id'], 'role': 'installation', 'association': 'APROVADA',
            'data': {'reason': reason, 'evidence': reason, 'source': 'manual-field'},
        }, author, role)
        value = payload.get('value')
        if type(value) is not int or value not in {0, 1}:
            raise ValueError('Informe se a montagem desta peça foi concluída.')
        balances = states(db.rows(c, 'progress_events', pid))
        previous = balances.get((piece['id'], stage['id'], unit['id']), 0)
        if previous != value:
            allocation = payload.get('allocate') is True
            if allocation and (previous != 0 or value != 1):
                raise ValueError('Alocação exige uma peça ainda sem montagem registrada.')
            store._progress(c, pid, {
                'type_id': piece['id'], 'stage_id': stage['id'],
                'mode': 'allocate' if allocation else 'units',
                'instance_ids': [unit['id']], 'value': value,
                'reason': reason, 'evidence': reason, 'effective_at': payload['effective_at'],
            }, expected, author)
        return {'geometry_id': area['id'], 'occurrence_id': occurrence['id'], 'instance_id': unit['id']}
    return store.mutate(pid, expected, key, author, 'field:mark', payload, operation)
