import math
from shapely.geometry import Polygon, LineString, Point

def matrix(box,rotation=0,scale=1):
    """Raw PDF bottom-left -> rotated CropBox raster top-left (PDF.js convention)."""
    x0,y0,x1,y1=map(float,box)
    if rotation==0: return [scale,0,0,-scale,-x0*scale,y1*scale]
    if rotation==90: return [0,scale,scale,0,-y0*scale,-x0*scale]
    if rotation==180: return [-scale,0,0,scale,x1*scale,-y0*scale]
    if rotation==270: return [0,-scale,-scale,0,y1*scale,x1*scale]
    raise ValueError('Rotação deve ser 0, 90, 180 ou 270.')
def transform(point,m):
    x,y=point;a,b,c,d,e,f=m
    return [a*x+c*y+e,b*x+d*y+f]
def inverse(m):
    a,b,c,d,e,f=m;det=a*d-b*c
    if abs(det)<1e-12: raise ValueError('Matriz singular.')
    return [d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det]
def validate_geometry(data,box):
    shape=data.get('kind'); paths=data.get('paths')
    if shape not in {'polygon','multipolygon','line','freehand'} or not isinstance(paths,list) or not paths:
        raise ValueError('Geometria requer tipo e caminhos em pontos PDF.')
    if sum(len(p) for p in paths)>10000: raise ValueError('Limite de 10.000 vértices.')
    x0,y0,x1,y1=box
    for path in paths:
        if len(path)<(3 if shape in {'polygon','multipolygon'} else 2): raise ValueError('Caminho incompleto.')
        for pair in path:
            if len(pair)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in pair): raise ValueError('Coordenada inválida.')
            if not (x0<=pair[0]<=x1 and y0<=pair[1]<=y1): raise ValueError('Geometria fora do CropBox.')
        geometry=Polygon(path) if shape in {'polygon','multipolygon'} else LineString(path)
        if geometry.is_empty or not geometry.is_valid: raise ValueError('Geometria inválida ou com auto-interseção; corrija os vértices.')
    width=data.get('width',2)
    if not isinstance(width,(int,float)) or not math.isfinite(width) or not 0<width<=100: raise ValueError('Largura deve ser de 0 a 100 pontos PDF.')
    return data

def contained(geometry,view):
    boundary=Polygon(view['polygon'])
    for path in geometry['paths']:
        shape=Polygon(path) if geometry['kind'] in {'polygon','multipolygon'} else LineString(path).buffer(geometry.get('width',2)/2)
        if not boundary.buffer(.1).covers(shape): raise ValueError('Geometria ultrapassa a vista. Revise o limite ou a pintura.')
