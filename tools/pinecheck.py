import re, sys
from collections import Counter
path = sys.argv[1] if len(sys.argv) > 1 else 'src/reversal_engine.pine'
raw = open(path).read()
lines = raw.split('\n')

def strip(l):
    o=[];ins=False;i=0
    while i<len(l):
        c=l[i]
        if c=='"': ins=not ins
        if not ins and c=='/' and i+1<len(l) and l[i+1]=='/': break
        o.append(c);i+=1
    return ''.join(o)
code=[strip(l) for l in lines]

print("NON-ASCII:", [i+1 for i,l in enumerate(lines) if any(ord(c)>127 for c in l)] or "none")
print("bare-colon continuation:", [i+1 for i,l in enumerate(lines) if re.match(r'^\s*:',l)] or "none")
tot=0
for l in code:
    t=re.sub(r'"[^"]*"','""',l); tot+=t.count('(')-t.count(')')
print("paren balance:", tot)

# --- NEW: use-before-declare at ANY scope, tracking first assignment line per name
DECL = re.compile(r'^\s*(?:var\s+|varip\s+)?(?:float|int|bool|string|color|table|label|line|box|array<[^>]+>|[a-zA-Z_]\w*\[\])?\s*([A-Za-z_]\w*)\s*(?::=|=)(?!=)')
FN   = re.compile(r'^\s*([A-Za-z_]\w*)\s*\([^)]*\)\s*=>')
TUP  = re.compile(r'^\s*\[([^\]]+)\]\s*=')
first={}
for i,l in enumerate(code):
    m=FN.match(l)
    if m:
        first.setdefault(m.group(1), i+1)
        # register the parameters too -- they are in scope from this line onward
        mp=re.match(r'^\s*[A-Za-z_]\w*\s*\((.*)\)\s*=>', l)
        if mp:
            for prm in mp.group(1).split(','):
                nm=prm.strip().split(' ')[-1].strip()
                if nm: first.setdefault(nm, i+1)
        continue
    m=TUP.match(l)
    if m:
        for n in m.group(1).split(','): first.setdefault(n.strip(), i+1)
        continue
    m=DECL.match(l)
    if m: first.setdefault(m.group(1), i+1)
    # for-loop induction vars
    m2=re.match(r'^\s*for\s+([A-Za-z_]\w*)\s*=', l)
    if m2: first.setdefault(m2.group(1), i+1)
    # function params
    mf=re.match(r'^\s*[A-Za-z_]\w*\s*\(([^)]*)\)\s*=>', l)
    if mf:
        for prm in mf.group(1).split(','):
            nm=prm.strip().split(' ')[-1]
            if nm: first.setdefault(nm, i+1)

KW={'var','varip','float','int','bool','string','color','table','label','line','box','array','matrix','map',
    'if','else','for','to','by','while','switch','and','or','not','true','false','na','import','export','type','method','continue','break'}
bad=[]
for i,l in enumerate(code):
    if not l.strip(): continue
    body=re.sub(r'"[^"]*"','""',l)
    lhs=DECL.match(l)
    lhsname=lhs.group(1) if lhs else None
    for tok in re.findall(r'\b([A-Za-z_]\w*)\b', body):
        if tok in KW or tok not in first: continue
        if tok==lhsname: continue
        if first[tok] > i+1:
            bad.append((i+1, tok, first[tok]))
print("USE-BEFORE-DECLARE (any scope):", bad[:12] if bad else "none")

# --- scope leak: declared inside a function body but referenced outside it.
# Pine functions cannot export locals, and a wrapped block that swallows a global
# declaration compiles as "undeclared identifier" far from the real cause.
fnspans=[]
for i,l in enumerate(code):
    if re.match(r'^[A-Za-z_]\w*\s*\(.*\)\s*=>', l):
        nm=re.match(r'^([A-Za-z_]\w*)',l).group(1)
        j=i+1
        while j<len(code) and (code[j].startswith(' ') or code[j].strip()==''):
            j+=1
        fnspans.append((nm,i,j))
leaks=[]
for nm,a,b in fnspans:
    for l in code[a+1:b]:
        m=re.match(r'^\s{4}(?:var\s+)?(?:float|int|bool|string|table|label|line|array<[^>]+>)?\s*([A-Za-z_]\w*)\s*=(?!=)', l)
        if not m: continue
        v=m.group(1)
        if len(v)<3: continue
        # A reference inside ANOTHER function that declares the same name locally is
        # not a leak -- Pine gives each function its own scope.
        def declared_in(span):
            return any(re.match(r'^\s+(?:var\s+)?(?:float|int|bool|string|table|label|line|array<[^>]+>)?\s*'+re.escape(v)+r'\s*=(?!=)', x) for x in code[span[0]+1:span[1]])
        out=[]
        for k,x in enumerate(code):
            if a<=k<b: continue
            if not re.search(r'\b'+re.escape(v)+r'\b', re.sub(r'"[^"]*"','""',x)): continue
            owner=next(((s2,e2) for n2,s2,e2 in fnspans if s2<=k<e2), None)
            if owner and declared_in(owner): continue
            out.append(k+1)
        if out: leaks.append((nm,v,out[:3]))
print("SCOPE LEAKS (declared in fn, used outside):", leaks[:8] if leaks else "none")

# --- orphaned indentation: an indented line must follow another indented line or
# a block opener. This is what CE10009 ("extraneous input ... expecting end of line
# without line continuation") looks like in the source, and it is exactly the
# artefact a mechanical function-extraction leaves behind.
OPENER = re.compile(r'(=>|^\s*(if|else|else\s+if|for|while|switch|type)\b.*)$')
orphans=[]
prev_indent=0
prev_opener=False
for i,l in enumerate(code):
    if not l.strip():
        continue
    ind=len(l)-len(l.lstrip(' '))
    if ind>prev_indent and not prev_opener:
        orphans.append((i+1, l.strip()[:60]))
    prev_indent=ind
    prev_opener=bool(OPENER.search(l))
print("ORPHANED INDENTATION:", orphans[:8] if orphans else "none")

# --- function return convention: every f_* body ends with a single bare "0"
# Only functions whose last statement is a VOID call need an explicit return; the
# value-returning helpers legitimately end on an expression.
VOIDCALL = re.compile(r'^\s*(table\.(cell|merge_cells|clear)|array\.(push|set|clear|shift)|line\.delete|label\.delete)\s*\(')
badret=[]
for nm,a,b in fnspans:
    if not nm.startswith('f_'): continue
    body=[x for x in code[a+1:b] if x.strip()]
    if not body: continue
    if VOIDCALL.match(body[-1]):
        badret.append((nm, 'ends on a void call, needs a trailing 0'))
    if len(body)>1 and body[-1].strip()=='0' and body[-2].strip()=='0':
        badret.append((nm,'duplicate trailing 0'))
print("FUNCTION RETURN CONVENTION:", badret[:8] if badret else "ok")

# Table names are discovered, not hardcoded: a table added later must not be
# silently skipped. Cells whose column/row are computed (loop counters) cannot be
# bounds-checked here, so they are REPORTED as unverified rather than ignored --
# an instrument that quietly checks nothing is worse than no check.
for tb in sorted(set(re.findall(r'^var table\s+([A-Za-z_]\w*)\s*=', raw, re.M))):
    cs  = re.findall(r'table\.cell\('+tb+r',\s*(\d+),\s*(\d+),', raw)
    dyn = len(re.findall(r'table\.cell\('+tb+r',(?!\s*\d+\s*,\s*\d+\s*,)', raw))
    sz  = re.search(r'table\.new\([^,]+,\s*(\d+),\s*(\d+)', raw[raw.index(tb+' := table.new'):]) if tb+' := table.new' in raw else None
    dec = f" declared={sz.group(1)}x{sz.group(2)}" if sz else " declared=?"
    if not cs and not dyn:
        print(f"{tb}: NO CELLS{dec}")
        continue
    dup = [k for k,v in Counter(cs).items() if v>1] or 'none'
    mr  = max((int(r) for c,r in cs), default=-1)
    mc  = max((int(c) for c,r in cs), default=-1)
    oob = ''
    if sz and cs and (mc >= int(sz.group(1)) or mr >= int(sz.group(2))):
        oob = '  *** OUT OF BOUNDS ***'
    print(f"{tb}: dup={dup} maxrow={mr} maxcol={mc}{dec} dynamic-cells={dyn}{oob}")
