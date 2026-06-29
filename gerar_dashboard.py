#!/usr/bin/env python3
# =====================================================================
#  Gerador do Dashboard de Treinos (Hevy API -> HTML) - Leonardo
#  Uso:  python3 gerar_dashboard.py [saida.html]
#  Busca os treinos DIRETO da API do Hevy (precisa de Hevy Pro + chave).
#  A chave deve estar na variavel de ambiente HEVY_API_KEY ou num
#  arquivo .env (HEVY_API_KEY=sua_chave) na mesma pasta do script.
# =====================================================================
import json, os, re, sys, time, urllib.request, urllib.error
import pandas as pd

# ----------------------- CONFIGURACAO -------------------------------
SAIDA        = sys.argv[1] if len(sys.argv) > 1 else 'dashboard.html'
DATA_INICIO  = '2026-05-14'   # data em que o dashboard abre por padrao (De ... ate hoje)
API_BASE     = 'https://api.hevyapp.com'
PAGE_SIZE    = 10             # maximo permitido pela API para /v1/workouts
FUSO_HORAS   = -3             # Sao Paulo (UTC-3); ajuste se mudar de fuso

# --- Camada de recomendacoes (gancho opcional do Claude) ------------
# A aba "Recomendacoes" e calculada por REGRAS deterministicas no
# proprio navegador (gratis, sempre atualizada, funciona offline).
# Opcionalmente, uma camada "inteligente" pode escrever as justificativas
# em linguagem natural. IMPORTANTE: essa camada roda AQUI (no servidor /
# GitHub Actions), NUNCA no HTML publico -- a chave do Claude jamais vai
# para a pagina. Por padrao fica DESLIGADA (regras puras, custo zero).
# Para ligar: defina a variavel de ambiente CLAUDE_ENABLED=true no passo do
# GitHub Actions (e o secret ANTHROPIC_API_KEY). Local/sem env = desligado.
CLAUDE_ENABLED = os.environ.get('CLAUDE_ENABLED', '').strip().lower() in ('1', 'true', 'yes', 'on')
CLAUDE_MODEL   = 'claude-haiku-4-5-20251001'   # barato; troque se quiser outro

# Renomeacoes de exercicios (chave = nome no Hevy, valor = nome exibido).
# Para adicionar um novo renome, basta incluir uma linha aqui.
RENAME = {
 'Supino Inclinado no Smith (Máquina)':'Supino Inclinado Smith',
 'Supino Sentado (Máquina)':'Supino Máquina (Pegada Pronada)',
 'Crucifixo Sentado (Cabo)':'Crucifixo Inclinado Máquina',
 'Crucifixo na Polia (Máquina)':'Crossover Polia Alta',
 'Extensão de tríceps acima da cabeça (cabo)':'Tríceps Testa na Polia',
 'Extensão de Tríceps (Halter)':'Tríceps Francês com Halteres',
 'Abdominal em bicicleta com pernas levantadas':'Abdominal Bicicleta',
 'Cadeira Abdutora (Máquina)':'Abdução de Quadril Máquina',
 'Levantamento Terra Romeno (Halter)':'Stiff com Halteres',
 'Panturrilha no Leg Press 45º':'Panturrilha no Leg Press Horizontal',
 'Puxada Alta na Polia (Máquina)':'Puxada Aberta Barra Reta',
 'Remada (Corda) Sentado - Pegas Afastadas':'Remada Máquina (Pegada Pronada)',
 'Remo Sentado (Máquina)':'Remada Máquina (Pegada Neutra)',
 'Remada Alta (Corda)':'Remada Alta na Polia Baixa com Barra Reta',
 'Rosca Scott (Halter)':'Rosca Scott Unilateral com Halteres',
 'Abdominal (Corda)':'Abdominal Máquina',
}

# Exercicios ja conhecidos (para sinalizar quando surgir algo novo no CSV).
KNOWN = set(['Abdominal (Corda)', 'Aberturas Invertidas (Corda)', 'Aberturas Invertidas De Ombro Posterior (Na Máquina) ', 'Agachamento no Smith (Máquina)', 'Cadeira Abdutora (Máquina)', 'Cadeira Adutora (Máquina)', 'Cadeira Extensora (Máquina)', 'Cadeira Flexora (Máquina)', 'Caminhada', 'Crucifixo Sentado (Cabo)', 'Crucifixo na Polia (Máquina)', 'Crucifixo no Voador (Máquina)', 'Desenvolvimento Arnold (halteres)', 'Elevação Frontal (Cabo)', 'Elevação Frontal (Halter)', 'Elevação Lateral (Halter)', 'Elevação Lateral (Máquina)', 'Elevação de Panturrilha Sentado (Máquina)', 'Elevação de Panturrilha em Pé (Máquina)', 'Elevação de Quadril (Máquina)', 'Extensão Lombar Maquina', 'Extensão de Panturrilha (Máquina)', 'Extensão de Tríceps (Halter)', 'Extensão de Tríceps (Máquina)', 'Extensão de tríceps acima da cabeça (cabo)', 'Hiperextensão Lombar', 'Hiperextensão Lombar Com Peso', 'Leg Press Horizontal (Máquina)', 'Levantamento Terra Romeno (Halter)', 'Mesa Flexora (Máquina)', 'Máquina De Fundos Sentado', 'Panturrilha no Leg Press 45º', 'Pec Deck', 'Prensa De Ombros (Sentada) (Máquina)', 'Pullover (Halter)', 'Puxada Alta (Máquina)', 'Puxada Alta - Pegada Triângulo', 'Puxada Alta na Polia (Máquina)', 'Puxada Com Braços Esticados (Corda)', 'Remada (Corda) Sentado - Pegas Afastadas', 'Remada Alta (Corda)', 'Remada Sentada com Pegada em V (Cabo)', 'Remo Sentado (Máquina)', 'Rosca Direta (Halter)', 'Rosca Direta (Máquina)', 'Rosca Direta na Polia', 'Rosca Inclinada (Halter)', 'Rosca Martelo com Corda na Polia', 'Rosca Scott (Barra)', 'Rosca Scott (Halter)', 'Rosca Scott (Máquina)', 'Supino Declinado (Máquina)', 'Supino Inclinado (Halter)', 'Supino Inclinado Na Máquina', 'Supino Inclinado no Smith (Máquina)', 'Supino Sentado (Máquina)', 'Tríceps na Polia'])

# ----------------------- CHAVE DE API -------------------------------
def _carrega_env():
    """Le um arquivo .env simples (CHAVE=valor) na pasta do script, se existir."""
    base = os.path.dirname(os.path.abspath(__file__))
    caminho = os.path.join(base, '.env')
    if os.path.exists(caminho):
        with open(caminho, encoding='utf-8') as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith('#') or '=' not in linha:
                    continue
                k, v = linha.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_carrega_env()
API_KEY = os.environ.get('HEVY_API_KEY', '').strip()
if not API_KEY:
    sys.exit('ERRO: defina HEVY_API_KEY (variavel de ambiente ou arquivo .env na pasta do script).\n'
             '      Gere a sua chave em https://hevy.com/settings?developer')

# ----------------------- BUSCA NA API DO HEVY -----------------------
def _get_json(url):
    req = urllib.request.Request(url, headers={'api-key': API_KEY, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))

def busca_workouts():
    todos, page = [], 1
    while True:
        url = '%s/v1/workouts?page=%d&pageSize=%d' % (API_BASE, page, PAGE_SIZE)
        try:
            data = _get_json(url)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                sys.exit('ERRO: chave de API recusada (HTTP %d). Confira a HEVY_API_KEY e se o Hevy Pro esta ativo.' % e.code)
            if e.code == 429:               # rate limit: espera e tenta de novo
                time.sleep(2); continue
            raise
        except urllib.error.URLError as e:
            sys.exit('ERRO de conexao com a API do Hevy: %s' % e.reason)
        lote = data.get('workouts', []) or []
        todos.extend(lote)
        total = data.get('page_count') or data.get('pageCount') or 1
        print('  pagina %d/%s  ->  %d treinos' % (page, total, len(lote)))
        if page >= total or not lote:
            break
        page += 1
        time.sleep(.2)                       # gentileza com a API
    return todos

print('Buscando treinos na API do Hevy...')
workouts = busca_workouts()
print('Total recebido: %d treinos.' % len(workouts))
if not workouts:
    sys.exit('Nenhum treino retornado pela API. Nada a gerar.')

# ----------------------- MONTA OS DADOS (1 linha = 1 serie) ---------
rows = []
for w in workouts:
    t_ini  = w.get('start_time')
    titulo = w.get('title') or ''
    for ex in (w.get('exercises') or []):
        nome = ex.get('title') or ''
        for s in (ex.get('sets') or []):
            rows.append({'start_time': t_ini, 'title': titulo,
                         'exercise_title': nome,
                         'weight_kg': s.get('weight_kg'),
                         'reps': s.get('reps')})

df = pd.DataFrame(rows)
# start_time vem em ISO 8601 (UTC); converte para o fuso local e remove o timezone
df['dt'] = (pd.to_datetime(df['start_time'], utc=True, errors='coerce')
              .dt.tz_localize(None) + pd.Timedelta(hours=FUSO_HORAS))
df = df.dropna(subset=['dt'])

df['weight_kg']=df['weight_kg'].fillna(0); df['reps']=df['reps'].fillna(0)
df['date']=df['dt'].dt.normalize()
def grp(t):
    t=str(t)
    if 'Legs' in t or 'MMII' in t: return 'Pernas'
    if 'Push' in t or 'Peito' in t: return 'Empurrar'
    if 'Pull' in t or 'Costas' in t: return 'Puxar'
    return 'Outros'
df['grupo']=df['title'].map(grp)

# avisa sobre exercicios novos (nao renomeados e nao conhecidos)
novos=sorted(set(df['exercise_title'].dropna().unique()) - KNOWN - set(RENAME))
if novos:
    print('AVISO - exercicios novos neste CSV (verifique se algum precisa de renome em RENAME):')
    for n in novos: print('   -', n)

df['exercise_title']=df['exercise_title'].apply(lambda s:RENAME.get(s,s))
dias={0:'Seg',1:'Ter',2:'Qua',3:'Qui',4:'Sex',5:'Sáb',6:'Dom'}
sessions=[]
for d,day in df.groupby('date'):
    ex=[]
    for name,eg in day.groupby('exercise_title',sort=False):
        sets=[[round(float(w),1),int(r)] for w,r in zip(eg['weight_kg'],eg['reps'])]
        ex.append({'n':name,'s':sets})
    sessions.append({'dateISO':d.strftime('%Y-%m-%d'),'dia':dias[d.weekday()],
                     'treino':day['title'].iloc[0],'grupo':day['grupo'].iloc[0],'ex':ex})
sessions.sort(key=lambda s:s['dateISO'])
raw_meta={'minISO':sessions[0]['dateISO'],'maxISO':sessions[-1]['dateISO']}

# ---- GANCHO: camada de justificativa "inteligente" (opcional) ------
def enriquecer_com_claude(sessions):
    """Roda no GitHub Actions (chave em Secrets, NUNCA no HTML publico).
    Recalcula as MESMAS decisoes do dashboard (para o texto bater com o
    selo na tela) e pede ao Claude apenas para REESCREVER a justificativa
    de cada exercicio num tom mais humano. Devolve {nome: paragrafo}.
    Se qualquer coisa falhar, devolve {} e a aba usa as regras locais.
    """
    import urllib.request, datetime as _dt
    from collections import Counter

    # 1) peso de trabalho (modal) + ultimas 3 sessoes por exercicio -----
    def _ws(ex):
        pesos = [s[0] for s in ex['s']]
        if not pesos:
            return None
        best = max(Counter(pesos).items(), key=lambda kv: (kv[1], kv[0]))[0]
        reps = [r for w, r in ex['s'] if w == best]
        return {'weight': best, 'reps': reps}

    # 2) MESMAS regras do navegador (status + motivo curto) -------------
    def _classify(last, total):
        n = len(last); recent = last[-1]; bw = recent['weight'] == 0
        if total < 2 or n < 2:
            return 'manter', 'poucos dados'
        hits = sum(1 for s in last if s['firstReps'] >= 11)
        w = [s['weight'] for s in last]; fr = [s['firstReps'] for s in last]
        weight_up = w[-1] > w[-2]
        wdrop = n >= 3 and w[-1] < w[-2] and w[-2] <= w[-3] and w[-1] < w[-3]
        rdecl = n >= 3 and fr[0] > fr[1] > fr[2]
        same = all(s['weight'] == recent['weight'] for s in last)
        collapse = (not bw) and recent['firstReps'] <= 6 and recent['drop'] >= 4
        if (not weight_up) and (wdrop or (rdecl and same) or collapse):
            return 'reduzir', 'queda consistente'
        if hits >= 2 and recent['firstReps'] >= 10 and recent['drop'] <= 4 and not rdecl and not wdrop:
            return 'aumentar', 'pronto para subir'
        if weight_up:
            return 'manter', 'ajuste de carga recente'
        if hits >= 2:
            return 'manter', 'quase la - recuou na ultima'
        if hits == 1:
            return 'manter', 'quase la - pico isolado'
        if recent['drop'] >= 4 and recent['firstReps'] >= 9:
            return 'manter', 'quase la - oscilacao alta'
        return 'manter', 'construindo reps'

    por = {}
    for s in sessions:
        for ex in s['ex']:
            ws = _ws(ex)
            if not ws or not ws['reps']:
                continue
            d = por.setdefault(ex['n'], {'grupos': {}, 'sess': []})
            d['grupos'][s['grupo']] = d['grupos'].get(s['grupo'], 0) + 1
            d['sess'].append({'dateISO': s['dateISO'], 'weight': ws['weight'],
                              'reps': ws['reps'], 'firstReps': ws['reps'][0],
                              'drop': ws['reps'][0] - ws['reps'][-1]})

    maxISO = max(s['dateISO'] for s in sessions)
    maxd = _dt.date.fromisoformat(maxISO)
    cand = []
    for nome, d in por.items():
        d['sess'].sort(key=lambda x: x['dateISO'])
        last = d['sess'][-3:]
        if (maxd - _dt.date.fromisoformat(last[-1]['dateISO'])).days > 35:
            continue                                   # fora da rotina atual
        if max(last[-1]['reps']) == 0:
            continue                                   # cardio
        grupo = max(d['grupos'].items(), key=lambda kv: kv[1])[0]
        status, motivo = _classify(last, len(d['sess']))
        hist = '; '.join('%skg %s' % (s['weight'], '-'.join(map(str, s['reps']))) for s in last)
        cand.append((nome, grupo, status, motivo, hist))

    if not cand:
        return {}

    # 3) UMA chamada com todos os exercicios ----------------------------
    linhas = '\n'.join('- %s [%s] | decisao=%s (%s) | ultimas 3 sessoes: %s'
                       % (n, g, st, mo, h) for (n, g, st, mo, h) in cand)
    prompt = (
        "Voce e um personal trainer experiente, direto e acolhedor, falando em "
        "portugues brasileiro com Leonardo sobre o treino dele. Faixa-alvo: 10 a 12 "
        "reps, sempre avaliando a PRIMEIRA serie (a mais descansada).\n\n"
        "Para CADA exercicio abaixo a decisao (aumentar / manter / reduzir) JA esta "
        "tomada por regras objetivas -- NAO mude a decisao. Escreva 1 a 2 frases curtas "
        "explicando o porque de um jeito humano e especifico, citando os numeros reais "
        "das ultimas sessoes. Sem jargao, sem repetir o nome do exercicio no inicio.\n\n"
        "Exercicios:\n" + linhas + "\n\n"
        "Responda APENAS com um objeto JSON valido, sem markdown e sem comentarios, no "
        "formato {\"Nome exato do exercicio\": \"explicacao\", ...} usando os nomes exatos acima."
    )
    corpo = json.dumps({'model': CLAUDE_MODEL, 'max_tokens': 3000,
                        'messages': [{'role': 'user', 'content': prompt}]}).encode('utf-8')
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=corpo,
        headers={'x-api-key': os.environ.get('ANTHROPIC_API_KEY', ''),
                 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))
        texto = ''.join(b.get('text', '') for b in resp.get('content', [])).strip()
        if texto.startswith('```'):
            texto = texto.split('```')[1]
            if texto.startswith('json'):
                texto = texto[4:]
        dados = json.loads(texto.strip())
        print('  Claude enriqueceu %d exercicios.' % len(dados))
        return dados if isinstance(dados, dict) else {}
    except Exception as e:
        print('  (enriquecimento Claude falhou, seguindo so com as regras):', e)
        return {}

RECS_AI = enriquecer_com_claude(sessions) if CLAUDE_ENABLED else {}
raw=json.dumps({'meta':raw_meta,'sessions':sessions,'recsAI':RECS_AI},ensure_ascii=False,separators=(',',':'))

# CSS (embutido)
style = '<style>\n:root{\n  --paper:#EEF0F4; --card:#FFFFFF; --ink:#191A21; --ink2:#474A54; --muted:#878C97;\n  --line:#E3E5EB; --line2:#EDEEF2;\n  --violet:#6D49E0; --violet-d:#5634C9; --violet-soft:#ECE7FB; --violet-ghost:#F5F2FD;\n  --green:#13A368; --green-soft:#E0F3EA;\n  --amber:#E2603B; --amber-soft:#FBE9E2;\n  --display:\'Space Grotesk\',system-ui,sans-serif;\n  --body:\'Inter\',system-ui,sans-serif;\n  --mono:\'JetBrains Mono\',ui-monospace,monospace;\n  --shadow:0 1px 2px rgba(20,22,30,.04),0 6px 20px rgba(20,22,30,.06);\n  --r:16px;\n}\n*{box-sizing:border-box;margin:0;padding:0}\nhtml{scroll-behavior:smooth}\nbody{background:var(--paper);color:var(--ink);font-family:var(--body);\n  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;\n  background-image:radial-gradient(circle at 1px 1px,rgba(25,26,33,.035) 1px,transparent 0);\n  background-size:22px 22px}\n.wrap{max-width:1180px;margin:0 auto;padding:0 20px 80px}\n\n/* header */\nheader{padding:30px 0 18px}\n.brandrow{display:flex;align-items:center;gap:14px;flex-wrap:wrap}\n.mark{width:42px;height:42px;border-radius:12px;background:var(--ink);\n  display:grid;place-items:center;flex-shrink:0}\n.mark svg{width:24px;height:24px}\n.htitle{font-family:var(--display);font-weight:700;font-size:26px;letter-spacing:-.02em;line-height:1.05}\n.hsub{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:3px;letter-spacing:.01em}\n.hsub b{color:var(--violet-d);font-weight:600}\n\n/* tabs */\n.tabs{display:flex;gap:6px;margin:22px 0 8px;background:var(--card);padding:5px;\n  border-radius:13px;border:1px solid var(--line);width:fit-content;box-shadow:var(--shadow)}\n.tab{font-family:var(--display);font-weight:600;font-size:14px;color:var(--ink2);\n  padding:9px 18px;border-radius:9px;cursor:pointer;border:none;background:none;\n  transition:all .18s;white-space:nowrap}\n.tab:hover{color:var(--ink);background:var(--violet-ghost)}\n.tab.on{background:var(--ink);color:#fff}\n.panel{display:none;animation:fade .35s ease}\n.panel.on{display:block}\n@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}\n\n/* cards / layout */\n.grid{display:grid;gap:16px}\n.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow)}\n.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;\n  color:var(--muted);font-weight:600}\n.ctitle{font-family:var(--display);font-weight:600;font-size:16px;letter-spacing:-.01em}\n\n/* KPI */\n.kpis{grid-template-columns:repeat(4,1fr);margin-top:16px}\n.kpi{padding:18px 18px 16px;position:relative;overflow:hidden}\n.kpi .lab{font-family:var(--mono);font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);font-weight:600}\n.kpi .val{font-family:var(--display);font-weight:700;font-size:34px;letter-spacing:-.03em;line-height:1;margin-top:12px}\n.kpi .unit{font-size:14px;color:var(--muted);font-weight:500;margin-left:3px}\n.kpi .foot{font-size:12px;color:var(--ink2);margin-top:6px}\n.kpi::after{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--violet)}\n.kpi.k2::after{background:var(--green)}\n.kpi.k3::after{background:var(--ink)}\n.kpi.k4::after{background:var(--amber)}\n\n/* overview rows */\n.two{grid-template-columns:1.35fr 1fr;margin-top:16px;align-items:stretch}\n.pad{padding:20px}\n.chead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px;gap:10px}\n.note{font-size:12px;color:var(--muted)}\n\n/* heatmap */\n.hm{display:flex;gap:5px;margin-top:16px;overflow-x:auto;padding-bottom:4px}\n.hmweek{display:flex;flex-direction:column;gap:5px}\n.hmcell{width:26px;height:26px;border-radius:7px;background:var(--line2);position:relative;cursor:default}\n.hmcell.has{cursor:pointer}\n.hmcell .tip,.dot .tip,.bar .tip{position:absolute;bottom:130%;left:50%;transform:translateX(-50%);\n  background:var(--ink);color:#fff;font-family:var(--mono);font-size:11px;padding:6px 9px;border-radius:7px;\n  white-space:nowrap;opacity:0;pointer-events:none;transition:.15s;z-index:5;box-shadow:var(--shadow)}\n.hmcell.has:hover .tip{opacity:1}\n.hmlegend{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:14px}\n.hmlegend i{width:16px;height:16px;border-radius:5px;display:inline-block}\n.hmrows{display:flex;flex-direction:column;gap:5px;margin-right:3px}\n.hmrows span{height:26px;display:flex;align-items:center;font-family:var(--mono);font-size:10px;color:var(--muted)}\n\n/* highlights */\n.hl{padding:16px 20px;border-bottom:1px solid var(--line2);display:flex;align-items:center;gap:14px}\n.hl:last-child{border-bottom:none}\n.hl .rk{font-family:var(--display);font-weight:700;font-size:13px;color:var(--muted);width:18px}\n.hl .nm{flex:1;font-weight:500;font-size:14px}\n.hl .gp{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}\n.delta{font-family:var(--display);font-weight:700;font-size:15px;font-variant-numeric:tabular-nums}\n.delta.up{color:var(--green)} .delta.dn{color:var(--amber)} .delta.flat{color:var(--muted)}\n.pill{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:11px;\n  padding:3px 8px;border-radius:20px;font-weight:600}\n.pill.up{background:var(--green-soft);color:var(--green)}\n.pill.dn{background:var(--amber-soft);color:var(--amber)}\n.pill.flat{background:var(--line2);color:var(--muted)}\n\n/* evolution explorer */\n.exp{grid-template-columns:300px 1fr;margin-top:16px;align-items:start}\n.exlist{padding:8px;max-height:560px;overflow-y:auto}\n.grphead{font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.06em;\n  text-transform:uppercase;color:var(--violet-d);padding:14px 12px 7px}\n.exitem{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:10px;cursor:pointer;transition:.14s}\n.exitem:hover{background:var(--violet-ghost)}\n.exitem.on{background:var(--ink)}\n.exitem.on .exn{color:#fff} .exitem.on .exg{color:#b9bdc9}\n.exn{flex:1;font-size:13.5px;font-weight:500;line-height:1.25}\n.exg{font-family:var(--mono);font-size:10px;color:var(--muted)}\n.minidelta{font-family:var(--display);font-weight:700;font-size:12px;font-variant-numeric:tabular-nums;flex-shrink:0}\n\n.detail{padding:24px}\n.dhead{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}\n.dname{font-family:var(--display);font-weight:700;font-size:22px;letter-spacing:-.02em}\n.dgrp{font-family:var(--mono);font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:3px}\n.statrow{display:flex;gap:26px;margin:20px 0 6px;flex-wrap:wrap}\n.stat .sl{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}\n.stat .sv{font-family:var(--display);font-weight:700;font-size:20px;margin-top:3px;font-variant-numeric:tabular-nums}\n.chartbox{margin-top:8px}\n.svgchart{width:100%;height:auto;display:block;overflow:visible}\n.dot{cursor:pointer}\n.empty{padding:60px 20px;text-align:center;color:var(--muted)}\n\n/* sessions */\n.filters{display:flex;gap:8px;margin:16px 0;flex-wrap:wrap}\n.chip{font-family:var(--mono);font-size:12px;font-weight:600;padding:7px 14px;border-radius:20px;\n  border:1px solid var(--line);background:var(--card);color:var(--ink2);cursor:pointer;transition:.15s}\n.chip:hover{border-color:var(--violet)}\n.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}\n.sess{margin-bottom:10px;overflow:hidden}\n.sesshead{display:grid;grid-template-columns:auto 1fr auto auto;gap:16px;align-items:center;\n  padding:16px 20px;cursor:pointer}\n.sdate{font-family:var(--display);font-weight:700;font-size:15px;min-width:96px}\n.sdate small{display:block;font-family:var(--mono);font-size:10px;color:var(--muted);font-weight:500;text-transform:uppercase}\n.streino{font-weight:600;font-size:14.5px}\n.streino .tag{display:inline-block;font-family:var(--mono);font-size:10px;font-weight:600;\n  padding:2px 8px;border-radius:6px;background:var(--violet-soft);color:var(--violet-d);margin-left:8px;\n  text-transform:uppercase;letter-spacing:.03em;vertical-align:middle}\n.smeta{font-family:var(--mono);font-size:12px;color:var(--muted);text-align:right}\n.smeta b{color:var(--ink);font-weight:600}\n.chev{transition:.2s;color:var(--muted)}\n.sess.open .chev{transform:rotate(180deg)}\n.sbody{display:none;border-top:1px solid var(--line2);padding:6px 20px 14px}\n.sess.open .sbody{display:block}\n.exrow{padding:11px 0;border-bottom:1px solid var(--line2)}\n.exrow:last-child{border-bottom:none}\n.exrow .ex-top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}\n.exrow .ex-nm{font-weight:500;font-size:14px}\n.exrow .ex-tw{font-family:var(--mono);font-size:12px;color:var(--violet-d);font-weight:600}\n.setline{font-family:var(--mono);font-size:12px;color:var(--ink2);margin-top:6px;display:flex;flex-wrap:wrap;gap:6px}\n.setbadge{background:var(--paper);border:1px solid var(--line);padding:2px 8px;border-radius:6px}\n\nfooter{margin-top:30px;text-align:center;font-family:var(--mono);font-size:11px;color:var(--muted)}\n\n@media(max-width:880px){\n  .kpis{grid-template-columns:repeat(2,1fr)}\n  .two,.exp{grid-template-columns:1fr}\n  .exlist{max-height:none}\n  .sesshead{grid-template-columns:auto 1fr auto}\n  .smeta{display:none}\n}\n</style>'

EXTRA_CSS = """
<style>
.rangebar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:16px}
.presets{display:flex;gap:6px;flex-wrap:wrap}
.preset{font-family:var(--mono);font-size:12px;font-weight:600;padding:7px 13px;border-radius:9px;
  border:1px solid var(--line);background:var(--card);color:var(--ink2);cursor:pointer;transition:.15s;box-shadow:var(--shadow)}
.preset:hover{border-color:var(--violet);color:var(--ink)}
.preset.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.daterow{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:12px;color:var(--muted);
  background:var(--card);border:1px solid var(--line);border-radius:9px;padding:5px 11px;box-shadow:var(--shadow)}
.daterow input[type=date]{font-family:var(--mono);font-size:12.5px;border:none;background:none;color:var(--ink);
  padding:3px 2px;border-radius:6px;color-scheme:light}
.daterow input[type=date]:focus{outline:2px solid var(--violet-soft)}
.two>.card,.exp>.card{min-width:0}
.hm{max-width:100%}
.empty-lg{padding:54px 20px;text-align:center;color:var(--muted);font-size:14px;font-family:var(--body)}
.msel{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0 4px}
.mbtn{font-family:var(--mono);font-size:11.5px;font-weight:600;padding:6px 12px;border-radius:8px;
  border:1px solid var(--line);background:var(--card);color:var(--ink2);cursor:pointer;transition:.15s}
.mbtn:hover{border-color:var(--violet);color:var(--ink)}
.mbtn.on{background:var(--violet);color:#fff;border-color:var(--violet)}
.charthint{font-family:var(--mono);font-size:10.5px;color:var(--muted);margin:10px 0 -4px;letter-spacing:.02em}
.dot{cursor:pointer}
#csvg .ptdot{transition:r .12s}
.exlhint{font-family:var(--mono);font-size:10px;letter-spacing:.04em;text-transform:uppercase;
  color:var(--muted);padding:11px 12px 3px}
.exlhint b{color:var(--violet-d);font-weight:600}
.empty-lg b{display:block;font-family:var(--display);font-size:16px;color:var(--ink2);margin-bottom:4px}
</style>
"""

REC_CSS = """
<style>
:root{--red:#D23B3B;--red-soft:#FBE4E4}
.recnote{font-size:12.5px;color:var(--ink2);background:var(--violet-ghost);border:1px solid var(--violet-soft);
  border-radius:11px;padding:12px 14px;margin:16px 0 4px;line-height:1.55}
.recnote b{color:var(--violet-d)}
.recsum{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 2px}
.recsum .pillc{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:12px;font-weight:600;
  padding:7px 12px;border-radius:11px;border:1px solid var(--line);background:var(--card);box-shadow:var(--shadow)}
.recsum .dotc{width:9px;height:9px;border-radius:50%}
.recgrp{font-family:var(--display);font-weight:700;font-size:13px;letter-spacing:.04em;text-transform:uppercase;
  margin:24px 4px 10px;display:flex;align-items:center;gap:10px}
.recgrp .gln{flex:1;height:1px;background:var(--line)}
.rec{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);
  margin-bottom:9px;overflow:hidden;border-left:4px solid var(--muted)}
.rec.s-aumentar{border-left-color:var(--green)}
.rec.s-manter{border-left-color:var(--violet)}
.rec.s-reduzir{border-left-color:var(--red)}
.rechead{display:grid;grid-template-columns:104px 1fr auto;gap:14px;align-items:center;padding:14px 16px}
.recbadge{font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.02em;text-transform:uppercase;
  padding:7px 8px;border-radius:8px;text-align:center;display:flex;align-items:center;justify-content:center;gap:5px}
.b-aumentar{background:var(--green-soft);color:var(--green)}
.b-manter{background:var(--violet-soft);color:var(--violet-d)}
.b-reduzir{background:var(--red-soft);color:var(--red)}
.recnm{font-weight:600;font-size:14.5px;line-height:1.25;min-width:0}
.recnm .recwhytag{font-family:var(--mono);font-size:11px;color:var(--muted);font-weight:500;margin-top:3px;display:block}
.recmove{font-family:var(--mono);font-size:12px;color:var(--ink2);text-align:right;white-space:nowrap;font-weight:600}
.recmove b{color:var(--ink);font-size:14px}
.recmove .ai{color:var(--violet);font-size:11px;margin-left:3px}
details.recwhy{border-top:1px solid var(--line2)}
details.recwhy summary{list-style:none;cursor:pointer;font-family:var(--mono);font-size:11.5px;font-weight:600;
  color:var(--violet-d);padding:10px 16px;display:flex;align-items:center;gap:7px;user-select:none}
details.recwhy summary::-webkit-details-marker{display:none}
details.recwhy summary .chv{transition:.2s;display:inline-flex}
details.recwhy[open] summary .chv{transform:rotate(180deg)}
details.recwhy summary:hover{background:var(--violet-ghost)}
.recbody{padding:2px 16px 16px;font-size:13.5px;line-height:1.6;color:var(--ink2)}
.recbody .sug{margin-top:10px;padding:11px 13px;background:var(--paper);border:1px solid var(--line);border-radius:10px;font-size:13px}
.recbody .sug b{color:var(--ink);font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;display:block;margin-bottom:4px}
.recbody .hist{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.recbody .hist b{color:var(--ink2);font-weight:600;text-transform:none;letter-spacing:0}
.recbody .hist span{background:var(--paper);border:1px solid var(--line);padding:2px 8px;border-radius:6px}
@media(max-width:880px){.rechead{grid-template-columns:96px 1fr;grid-row-gap:9px}
  .recmove{grid-column:1 / -1;text-align:left}}
</style>
"""

BODY = """
<div class="wrap">
<header>
  <div class="brandrow">
    <div class="mark"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><path d="M2 12h2M20 12h2M5 8v8M19 8v8M8 6v12M16 6v12"/></svg></div>
    <div>
      <div class="htitle">Evolu&ccedil;&atilde;o de Treinos</div>
      <div class="hsub">LEONARDO &middot; <span id="periodo"></span></div>
    </div>
  </div>
  <div class="rangebar">
    <div class="presets" id="presets">
      <button class="preset" data-days="30">30 dias</button>
      <button class="preset" data-days="60">2 meses</button>
      <button class="preset" data-days="90">3 meses</button>
      <button class="preset" data-days="180">6 meses</button>
      <button class="preset" data-all>Tudo</button>
    </div>
    <div class="daterow">
      <span>De</span><input type="date" id="dStart">
      <span>at&eacute;</span><input type="date" id="dEnd">
    </div>
  </div>
  <div class="tabs" role="tablist">
    <button class="tab on" data-tab="overview">Vis&atilde;o</button>
    <button class="tab" data-tab="evolucao">Evolu&ccedil;&atilde;o</button>
    <button class="tab" data-tab="sessoes">Sess&otilde;es</button>
    <button class="tab" data-tab="recs">Insights</button>
  </div>
</header>

<section class="panel on" id="overview">
  <div class="grid kpis" id="kpis"></div>
  <div class="grid two">
    <div class="card pad">
      <div class="chead"><div><div class="eyebrow">Const&acirc;ncia</div><div class="ctitle">Mapa de treinos</div></div></div>
      <div class="note">Cada coluna &eacute; uma semana. Cor mais forte = mais volume no dia.</div>
      <div id="heatmap"></div>
      <div class="hmlegend">menos
        <i style="background:var(--line2)"></i><i style="background:#cdbef4"></i><i style="background:#9b7fe8"></i><i style="background:#6D49E0"></i><i style="background:#4a2da8"></i>
        mais volume</div>
    </div>
    <div class="card pad">
      <div class="chead"><div><div class="eyebrow">Carga semanal</div><div class="ctitle">Volume por semana</div></div></div>
      <div class="note">Soma de peso &times; reps de todas as s&eacute;ries (mil kg = t).</div>
      <div id="weekly" class="chartbox"></div>
    </div>
  </div>
  <div class="grid two">
    <div class="card">
      <div class="pad" style="padding-bottom:6px"><div class="eyebrow">Destaques</div><div class="ctitle">Maiores ganhos de carga</div></div>
      <div id="gains"></div>
    </div>
    <div class="card">
      <div class="pad" style="padding-bottom:6px"><div class="eyebrow">Revisar</div><div class="ctitle">Pontos de aten&ccedil;&atilde;o</div></div>
      <div id="drops"></div>
    </div>
  </div>
</section>

<section class="panel" id="evolucao">
  <div class="filters" id="exfilters"></div>
  <div class="grid exp">
    <div class="card exlist" id="exlist"></div>
    <div class="card detail" id="detail"></div>
  </div>
</section>

<section class="panel" id="sessoes">
  <div class="filters" id="filters"></div>
  <div id="sesslist"></div>
</section>

<section class="panel" id="recs">
  <div class="recnote" id="recnote"></div>
  <div class="filters" id="recfilters"></div>
  <div id="reclist"></div>
</section>

<footer>Gerado a partir da API do Hevy &middot; ajuste o intervalo no topo &middot; clique nos exerc&iacute;cios e nas sess&otilde;es</footer>
</div>
"""

JS = r"""
<script id="rawdata" type="application/json">__RAWJSON__</script>
<script>
const RAW=JSON.parse(document.getElementById('rawdata').textContent);
const grpColor={Pernas:'#6D49E0',Empurrar:'#13A368',Puxar:'#E2603B',Outros:'#878C97'};
const grpOrder={Pernas:0,Empurrar:1,Puxar:2,Outros:3};
const fmt=n=>Math.round(n).toLocaleString('pt-BR');
const pdate=iso=>{const a=iso.split('-');return a[2]+'/'+a[1]+'/'+a[0];};
const sdate=iso=>{const a=iso.split('-');return a[2]+'/'+a[1];};
function parseISO(iso){const a=iso.split('-');return new Date(+a[0],+a[1]-1,+a[2]);}
function ymd(d){const m=String(d.getMonth()+1).padStart(2,'0'),da=String(d.getDate()).padStart(2,'0');return d.getFullYear()+'-'+m+'-'+da;}
function weekStartISO(iso){const d=parseISO(iso);const dow=(d.getDay()+6)%7;d.setDate(d.getDate()-dow);return ymd(d);}
function addDays(iso,n){const d=parseISO(iso);d.setDate(d.getDate()+n);return ymd(d);}
function clamp(iso){return iso<RAW.meta.minISO?RAW.meta.minISO:(iso>HI?HI:iso);}

const TODAY=ymd(new Date());
const HI=(TODAY>RAW.meta.maxISO)?TODAY:RAW.meta.maxISO;
const STATE={start:RAW.meta.minISO,end:HI,grupo:'Todos',exGrupo:'Todos',ex:null,metric:'peso',point:null};

/* tabs */
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(x=>x.classList.remove('on'));
  t.classList.add('on');document.getElementById(t.dataset.tab).classList.add('on');
});

function aggregate(){
  const sess=RAW.sessions.filter(s=>s.dateISO>=STATE.start&&s.dateISO<=STATE.end);
  let totalVol=0,totalSets=0;const exMap={},dayVol={},exNames=new Set();
  sess.forEach(s=>{let svol=0;
    s.ex.forEach(e=>{exNames.add(e.n);
      let topW=-Infinity,topRep=0,bestE=0,evol=0,treps=0;
      e.s.forEach(p=>{const w=p[0],r=p[1],v=w*r;svol+=v;evol+=v;totalVol+=v;totalSets++;treps+=r;
        if(w>topW){topW=w;topRep=r;}const e1=w*(1+r/30);if(e1>bestE)bestE=e1;});
      const m=(exMap[e.n]=exMap[e.n]||{grupo:{},pts:[]});
      m.grupo[s.grupo]=(m.grupo[s.grupo]||0)+1;
      m.pts.push({dataISO:s.dateISO,data:sdate(s.dateISO),peso:topW===-Infinity?0:topW,
        reps:topRep,totReps:treps,e1rm:Math.round(bestE*10)/10,volume:Math.round(evol),series:e.s.length});});
    dayVol[s.dateISO]={volume:Math.round(svol),grupo:s.grupo,dia:s.dia,data:sdate(s.dateISO)};});

  const exercises=Object.keys(exMap).map(name=>{const o=exMap[name];
    o.pts.sort((a,b)=>a.dataISO<b.dataISO?-1:1);
    const grupo=Object.keys(o.grupo).sort((a,b)=>o.grupo[b]-o.grupo[a])[0];
    const maxw=Math.max.apply(null,o.pts.map(p=>p.peso));
    const metric=maxw===0?'reps':'peso';
    const serie=o.pts.map(p=>metric==='peso'?p.peso:p.reps);
    const first=serie[0],last=serie[serie.length-1];
    return {nome:name,grupo,gordem:grpOrder[grupo]!=null?grpOrder[grupo]:9,metric,pontos:o.pts,
      primeira:first,ultima:last,dAbs:Math.round((last-first)*10)/10,
      dPct:first?((last-first)/first):0,
      bestE1rm:Math.round(Math.max.apply(null,o.pts.map(p=>p.e1rm))*10)/10,nSess:o.pts.length};
  }).sort((a,b)=>a.gordem-b.gordem||a.nome.localeCompare(b.nome));

  const isos=sess.map(s=>s.dateISO).sort();let weeks=1;
  if(isos.length>=2){weeks=Math.max(1,(parseISO(isos[isos.length-1])-parseISO(isos[0]))/(7*864e5));}
  const kpis={sessoes:sess.length,series:totalSets,volume:Math.round(totalVol),
    exercicios:exNames.size,freq:sess.length?Math.round(sess.length/weeks*10)/10:0};

  const daymap=Object.keys(dayVol).sort().map(iso=>Object.assign({dataISO:iso},dayVol[iso]));
  const wk={};daymap.forEach(d=>{const ws=weekStartISO(d.dataISO);
    (wk[ws]=wk[ws]||{volume:0,sessoes:0});wk[ws].volume+=d.volume;wk[ws].sessoes++;});
  const weekly=Object.keys(wk).sort().map(ws=>({iso:ws,label:sdate(ws),volume:wk[ws].volume,sessoes:wk[ws].sessoes}));

  const sv=sess.slice().sort((a,b)=>a.dateISO<b.dateISO?1:-1).map(s=>{
    let vol=0,sets=0;const lista=s.ex.map(e=>{let tw=-Infinity;
      e.s.forEach(p=>{vol+=p[0]*p[1];sets++;if(p[0]>tw)tw=p[0];});
      return {nome:e.n,topPeso:tw===-Infinity?0:tw,series:e.s.map(p=>({w:p[0],reps:p[1]}))};});
    return {dataISO:s.dateISO,data:pdate(s.dateISO),dia:s.dia,treino:s.treino,grupo:s.grupo,
      exercicios:s.ex.length,series:sets,volume:Math.round(vol),lista};});

  return {kpis,daymap,weekly,exercises,sessions:sv};
}

/* ---------- renderers ---------- */
function renderKPIs(k){
  const def=[
    {c:'',lab:'Sess&otilde;es',val:k.sessoes,unit:'',foot:k.series+' s&eacute;ries no total'},
    {c:'k2',lab:'Frequ&ecirc;ncia',val:k.freq,unit:'/sem',foot:'treinos por semana'},
    {c:'k3',lab:'Volume movido',val:(k.volume/1000).toFixed(1),unit:'t',foot:fmt(k.volume)+' kg somados'},
    {c:'k4',lab:'Exerc&iacute;cios',val:k.exercicios,unit:'',foot:'diferentes no per&iacute;odo'}];
  document.getElementById('kpis').innerHTML=def.map(d=>`
    <div class="card kpi ${d.c}"><div class="lab">${d.lab}</div>
    <div class="val">${d.val}<span class="unit">${d.unit}</span></div>
    <div class="foot">${d.foot}</div></div>`).join('');
}

function renderHeatmap(daymap){
  const box=document.getElementById('heatmap');
  if(!daymap.length){box.innerHTML='<div class="empty-lg">Sem treinos neste intervalo.</div>';return;}
  const days=['Seg','Ter','Qua','Qui','Sex','S&aacute;b','Dom'];
  const map={};daymap.forEach(d=>map[d.dataISO]=d);
  const maxv=Math.max.apply(null,daymap.map(d=>d.volume))||1;
  const shade=v=>{if(!v)return'var(--line2)';const t=v/maxv;
    if(t>.8)return'#4a2da8';if(t>.55)return'#6D49E0';if(t>.3)return'#9b7fe8';return'#cdbef4';};
  let start=weekStartISO(daymap[0].dataISO),end=daymap[daymap.length-1].dataISO;
  let weeks=[],cur=start;
  while(cur<=end){let col=[];for(let i=0;i<7;i++){col.push({iso:cur,d:map[cur]});cur=addDays(cur,1);}weeks.push(col);}
  let html='<div class="hmrows">'+days.map(d=>`<span>${d}</span>`).join('')+'</div>';
  html+=weeks.map(col=>'<div class="hmweek">'+col.map(c=>{
    if(c.d)return`<div class="hmcell has" style="background:${shade(c.d.volume)}">
      <span class="tip">${c.d.dia} ${c.d.data} &middot; ${c.d.grupo}<br>${fmt(c.d.volume)} kg</span></div>`;
    return`<div class="hmcell"></div>`;}).join('')+'</div>').join('');
  box.innerHTML='<div class="hm">'+html+'</div>';
}

function renderWeekly(w){
  const box=document.getElementById('weekly');
  if(!w.length){box.innerHTML='<div class="empty-lg">Sem dados.</div>';return;}
  const W=520,H=190,pad={l:8,r:8,t:16,b:30},n=w.length;
  const max=Math.max.apply(null,w.map(d=>d.volume))||1,bw=(W-pad.l-pad.r)/n;
  const showVal=n<=14,step=Math.ceil(n/13);
  let bars=w.map((d,i)=>{const bh=(d.volume/max)*(H-pad.t-pad.b),x=pad.l+i*bw,y=H-pad.b-bh;
    const lbl=(i%step===0)?`<text x="${x+bw/2}" y="${H-pad.b+16}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="10" fill="var(--muted)">${d.label}</text>`:'';
    const val=showVal?`<text x="${x+bw/2}" y="${y-5}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="9.5" font-weight="600" fill="var(--ink2)">${(d.volume/1000).toFixed(1)}t</text>`:'';
    return`<g class="bar"><rect x="${x+bw*.16}" y="${y}" width="${bw*.68}" height="${bh}" rx="4" fill="var(--violet)" opacity="${.45+.55*d.volume/max}">
      <title>Semana ${d.label} &middot; ${fmt(d.volume)} kg &middot; ${d.sessoes} treino(s)</title></rect>${lbl}${val}</g>`;}).join('');
  box.innerHTML=`<svg class="svgchart" viewBox="0 0 ${W} ${H}">${bars}</svg>`;
}

function pillFor(p){const cls=p>0.001?'up':(p<-0.001?'dn':'flat');
  return`<span class="pill ${cls}">${(p>0?'+':'')+(p*100).toFixed(0)}%</span>`;}
function renderHighlights(exs){
  const real=exs.filter(e=>e.nSess>=2&&e.metric==='peso');
  const gains=real.slice().sort((a,b)=>b.dPct-a.dPct).slice(0,5);
  const drops=real.slice().sort((a,b)=>a.dPct-b.dPct).slice(0,5);
  const row=(e,i)=>`<div class="hl"><div class="rk">${i+1}</div>
    <div class="nm">${e.nome}<div class="gp">${e.grupo}</div></div>
    <div style="text-align:right">${pillFor(e.dPct)}
    <div style="font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:3px">${e.primeira}&rarr;${e.ultima} kg</div></div></div>`;
  const empty='<div class="empty-lg">Precisa de pelo menos 2 sess&otilde;es de um exerc&iacute;cio no intervalo.</div>';
  document.getElementById('gains').innerHTML=gains.length?gains.map(row).join(''):empty;
  document.getElementById('drops').innerHTML=drops.length?drops.map(row).join(''):empty;
}

let CURex=[];
function exDelta(e){
  const f=METRICS[STATE.metric].key,s=e.pontos.map(p=>p[f]);
  let txt='&middot;',cls='flat';
  if(e.nSess>=2){const a=s[0],b=s[s.length-1];
    if(a!==0){const pct=(b-a)/a;txt=(pct>0?'+':'')+(pct*100).toFixed(0)+'%';cls=pct>0.001?'up':(pct<-0.001?'dn':'flat');}
    else if(b===0){txt='0%';}}
  return {txt,cls};
}
function exItem(e){const d=exDelta(e);
  return `<div class="exitem" data-ex="${encodeURIComponent(e.nome)}"><div style="flex:1">
    <div class="exn">${e.nome}</div><div class="exg">${e.nSess} sess&otilde;es</div></div>
    <div class="minidelta delta ${d.cls}">${d.txt}</div></div>`;}
function renderExplorer(exs){
  CURex=exs;STATE.point=null;
  const present=[...new Set(exs.map(e=>e.grupo))];
  const chips=['Todos'].concat(['Empurrar','Puxar','Pernas','Outros'].filter(g=>present.includes(g)));
  if(chips.indexOf(STATE.exGrupo)<0) STATE.exGrupo='Todos';
  document.getElementById('exfilters').innerHTML=chips.map(g=>
    `<button class="chip ${g===STATE.exGrupo?'on':''}" data-g="${g}">${g}</button>`).join('');
  document.querySelectorAll('#exfilters .chip').forEach(c=>c.onclick=()=>{STATE.exGrupo=c.dataset.g;renderExplorer(CURex);});

  const view=exs.filter(e=>STATE.exGrupo==='Todos'||e.grupo===STATE.exGrupo);
  const box=document.getElementById('exlist');
  if(!view.length){box.innerHTML='<div class="empty-lg">Sem exerc&iacute;cios neste grupo/intervalo.</div>';
    document.getElementById('detail').innerHTML='<div class="empty-lg"><b>Nada para mostrar</b>Ajuste o filtro ou o intervalo.</div>';return;}
  let html='<div class="exlhint">% por <b>'+METRICS[STATE.metric].label+'</b></div>';
  if(STATE.exGrupo==='Todos'){
    const groups={};view.forEach(e=>{(groups[e.grupo]=groups[e.grupo]||[]).push(e)});
    ['Pernas','Empurrar','Puxar','Outros'].filter(g=>groups[g]).forEach(g=>{
      html+=`<div class="grphead" style="color:${grpColor[g]}">${g}</div>`;
      groups[g].forEach(e=>{html+=exItem(e);});});
  } else { view.forEach(e=>{html+=exItem(e);}); }
  box.innerHTML=html;
  box.querySelectorAll('.exitem').forEach(it=>it.onclick=()=>selectEx(decodeURIComponent(it.dataset.ex)));
  let keep=STATE.ex&&view.find(e=>e.nome===STATE.ex);
  let target=keep?STATE.ex:(view.find(e=>e.metric==='peso'&&e.nSess>=2)||view[0]).nome;
  selectEx(target);
}

const METRICS={
  peso:{key:'peso',label:'Carga m&aacute;x',unit:'kg',sub:p=>p.reps+' reps'},
  e1rm:{key:'e1rm',label:'e1RM',unit:'kg',sub:p=>p.peso+'kg &times; '+p.reps},
  volume:{key:'volume',label:'Volume',unit:'kg',sub:p=>p.series+' s&eacute;ries'},
  reps:{key:'totReps',label:'Reps totais',unit:'reps',sub:p=>p.series+' s&eacute;ries'}
};
const METRIC_ORDER=['peso','e1rm','volume','reps'];

function setMetric(m){STATE.metric=m;STATE.point=null;renderExplorer(CURex);}

function selectEx(name){
  const e=CURex.find(x=>x.nome===name);if(!e)return;
  if(name!==STATE.ex)STATE.point=null;
  STATE.ex=name;
  document.querySelectorAll('.exitem').forEach(i=>i.classList.toggle('on',decodeURIComponent(i.dataset.ex)===name));
  const md=METRICS[STATE.metric],field=md.key,u=md.unit?(' '+md.unit):'';
  const series=e.pontos.map(p=>p[field]);
  const first=series[0],last=series[series.length-1];
  const dAbs=Math.round((last-first)*10)/10,dPct=first?((last-first)/first):0;
  const best=Math.max.apply(null,series),cls=dPct>0.001?'up':(dPct<-0.001?'dn':'flat');
  const dtxt=(dAbs>0?'+':'')+dAbs+u+'  ('+(dPct>0?'+':'')+(dPct*100).toFixed(1)+'%)';
  const sel=METRIC_ORDER.map(k=>`<button class="mbtn ${k===STATE.metric?'on':''}" data-m="${k}">${METRICS[k].label}</button>`).join('');
  document.getElementById('detail').innerHTML=`<div class="dhead"><div><div class="dname">${e.nome}</div>
    <div class="dgrp">${e.grupo} &middot; ${md.label} por sess&atilde;o</div></div>
    <div class="delta ${cls}" style="font-size:22px">${dtxt}</div></div>
    <div class="msel">${sel}</div>
    <div class="statrow">
      <div class="stat"><div class="sl">1&ordf; sess&atilde;o</div><div class="sv">${first}${u}</div></div>
      <div class="stat"><div class="sl">&Uacute;ltima</div><div class="sv">${last}${u}</div></div>
      <div class="stat"><div class="sl">Sess&otilde;es</div><div class="sv">${e.nSess}</div></div>
      <div class="stat"><div class="sl">Melhor</div><div class="sv">${best}${u}</div></div>
    </div>
    <div class="charthint">Toque nos pontos para ver o valor de cada sess&atilde;o</div>
    <div class="chartbox" id="lc"></div>`;
  document.querySelectorAll('.mbtn').forEach(b=>b.onclick=()=>setMetric(b.dataset.m));
  drawLine(e,series,md);
}

let CHART=null;
function drawLine(e,vals,md){
  const W=640,H=270,pad={l:44,r:18,t:26,b:34},n=vals.length;
  const max=Math.max.apply(null,vals),min=Math.min.apply(null,vals);
  const span=(max-min)||1,lo=min-span*.25,hi=max+span*.25,rng=(hi-lo)||1;
  const X=i=>pad.l+(n===1?(W-pad.l-pad.r)/2:i*(W-pad.l-pad.r)/(n-1));
  const Y=v=>H-pad.b-((v-lo)/rng)*(H-pad.t-pad.b);
  const col=grpColor[e.grupo],step=Math.ceil(n/12);
  const coords=e.pontos.map((p,i)=>({x:X(i),y:Y(vals[i]),v:vals[i],p:p}));
  CHART={coords,col,md,W,H,pad};
  let grid='';for(let g=0;g<=3;g++){const v=lo+rng*g/3,y=Y(v);
    grid+=`<line x1="${pad.l}" y1="${y}" x2="${W-pad.r}" y2="${y}" stroke="var(--line2)"/>
    <text x="${pad.l-8}" y="${y+3.5}" text-anchor="end" font-family="ui-monospace,monospace" font-size="10" fill="var(--muted)">${v.toFixed(v<10?1:0)}</text>`;}
  let path='';coords.forEach((c,i)=>{path+=(i?'L':'M')+c.x+' '+c.y+' ';});
  let area=`M${coords[0].x} ${H-pad.b} `+coords.map(c=>'L'+c.x+' '+c.y).join(' ')+` L${coords[n-1].x} ${H-pad.b} Z`;
  let dots=coords.map((c,i)=>{
    const lbl=(i%step===0||i===n-1)?`<text x="${c.x}" y="${H-pad.b+18}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="9.5" fill="var(--muted)">${c.p.data}</text>`:'';
    return`<g class="dot" data-i="${i}"><circle cx="${c.x}" cy="${c.y}" r="16" fill="transparent"/>
      <circle class="ptdot" cx="${c.x}" cy="${c.y}" r="5" fill="#fff" stroke="${col}" stroke-width="2.5"/>${lbl}</g>`;}).join('');
  const len=1500;
  document.getElementById('lc').innerHTML=`<svg id="csvg" class="svgchart" viewBox="0 0 ${W} ${H}">
    <defs><linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${col}" stop-opacity=".18"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    ${grid}<path d="${area}" fill="url(#grad)"/>
    <path d="${path}" fill="none" stroke="${col}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"
      stroke-dasharray="${len}" stroke-dashoffset="${len}">
      <animate attributeName="stroke-dashoffset" from="${len}" to="0" dur=".7s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/></path>
    ${dots}<g id="ptip"></g></svg>`;
  const svg=document.getElementById('csvg');svg.style.cursor='pointer';
  svg.addEventListener('click',ev=>{const m=svg.getScreenCTM();if(!m)return;
    const pt=svg.createSVGPoint();pt.x=ev.clientX;pt.y=ev.clientY;
    const sp=pt.matrixTransform(m.inverse());
    let bi=0,bd=1e9;CHART.coords.forEach((c,i)=>{const d=Math.abs(c.x-sp.x);if(d<bd){bd=d;bi=i;}});
    showPoint(bi);});
  if(STATE.point!=null&&STATE.point<n)showPoint(STATE.point);
}

function showPoint(i){
  if(!CHART)return;STATE.point=i;const c=CHART.coords[i],md=CHART.md;
  document.querySelectorAll('#csvg .ptdot').forEach((d,j)=>{
    d.setAttribute('r',j===i?'7':'5');d.setAttribute('fill',j===i?CHART.col:'#fff');});
  const u=md.unit?(' '+md.unit):'';
  const line1=c.p.data,line2=c.v+u,line3=md.sub(c.p);
  const approx=Math.max(line1.length,(''+line2).length,line3.replace(/&[a-z]+;/g,'x').length);
  const bw=Math.min(Math.max(approx*7+18,92),190),bh=50;
  let bx=Math.max(4,Math.min(c.x-bw/2,CHART.W-bw-4));
  let above=c.y-bh-14>=2,by=above?c.y-bh-14:c.y+16;
  const arrow=above?`<polygon points="${c.x-6},${by+bh} ${c.x+6},${by+bh} ${c.x},${by+bh+7}" fill="#191A21"/>`:'';
  document.getElementById('ptip').innerHTML=`<g pointer-events="none">
    <rect x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="9" fill="#191A21"/>${arrow}
    <text x="${bx+bw/2}" y="${by+16}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="9.5" fill="#9aa0ad">${line1}</text>
    <text x="${bx+bw/2}" y="${by+32}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="14" font-weight="700" fill="#fff">${line2}</text>
    <text x="${bx+bw/2}" y="${by+45}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="9.5" fill="#cdbef4">${line3}</text></g>`;
}

function renderSessions(sv){
  const box=document.getElementById('sesslist');
  const grupos=['Todos'].concat([...new Set(sv.map(s=>s.grupo))]);
  document.getElementById('filters').innerHTML=grupos.map(g=>
    `<button class="chip ${g===STATE.grupo?'on':''}" data-g="${g}">${g}</button>`).join('');
  document.querySelectorAll('#filters .chip').forEach(c=>c.onclick=()=>{STATE.grupo=c.dataset.g;renderSessions(sv);});
  const list=sv.filter(s=>STATE.grupo==='Todos'||s.grupo===STATE.grupo);
  if(!list.length){box.innerHTML='<div class="card"><div class="empty-lg"><b>Nenhuma sess&atilde;o</b>Sem treinos para este filtro/intervalo.</div></div>';return;}
  box.innerHTML=list.map(s=>{
    const exs=s.lista.map(ex=>`<div class="exrow"><div class="ex-top">
      <span class="ex-nm">${ex.nome}</span><span class="ex-tw">top ${ex.topPeso} kg</span></div>
      <div class="setline">${ex.series.map(st=>`<span class="setbadge">${st.w>0?st.w+'kg':'corporal'} &times; ${st.reps}</span>`).join('')}</div></div>`).join('');
    return`<div class="card sess"><div class="sesshead">
      <div class="sdate">${s.data}<small>${s.dia}</small></div>
      <div class="streino">${s.treino}<span class="tag">${s.grupo}</span></div>
      <div class="smeta"><b>${s.exercicios}</b> exerc&iacute;cios &middot; <b>${s.series}</b> s&eacute;ries<br>${fmt(s.volume)} kg de volume</div>
      <svg class="chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>
      </div><div class="sbody">${exs}</div></div>`;}).join('');
  box.querySelectorAll('.sess .sesshead').forEach(h=>h.onclick=()=>h.parentElement.classList.toggle('open'));
}

/* ---------- recomendacoes ---------- */
const kgfmt=v=>(Math.round(v*10)/10).toString().replace('.',',');
const recStatusOrder={aumentar:0,reduzir:1,manter:2};
const recReasonRank={'Pronto para subir':0,'Queda consistente':0,'Ajuste de carga recente':1,
  'Quase l&aacute; &mdash; recuou na &uacute;ltima':2,'Quase l&aacute; &mdash; pico isolado':2,
  'Quase l&aacute; &mdash; oscila&ccedil;&atilde;o alta':2};

/* peso de trabalho = peso mais frequente da sessao (ignora aquecimento/teste) */
function workingSet(e){
  const order={};e.s.forEach(p=>{const w=p[0];(order[w]=order[w]||[]).push(p[1]);});
  let bestW=null,bestC=-1;
  Object.keys(order).forEach(wk=>{const w=+wk,c=order[wk].length;
    if(c>bestC||(c===bestC&&w>bestW)){bestC=c;bestW=w;}});
  const reps=e.s.filter(p=>p[0]===bestW).map(p=>p[1]);
  return {weight:bestW,reps};
}

function classifyRec(last,all){
  const n=last.length,recent=last[n-1],TOP=11,bw=recent.bodyweight;
  const w=last.map(s=>s.weight),fr=last.map(s=>s.firstReps);
  const tgt=(()=>{let t=Math.round((recent.weight*0.95)/2.5)*2.5;if(t>=recent.weight)t=recent.weight-2.5;return t;})();
  if(all.length<2||n<2)
    return {status:'manter',reason:'Poucos dados',
      detail:'S&oacute; '+all.length+' sess&atilde;o(&otilde;es) desse exerc&iacute;cio na rotina recente. Preciso de pelo menos 2 para avaliar a tend&ecirc;ncia com seguran&ccedil;a.',
      sug:'Mantenha a carga e registre mais algumas sess&otilde;es.',
      move: bw?'manter':'manter '+kgfmt(recent.weight)+' kg'};

  const hits=last.filter(s=>s.firstReps>=TOP).length;
  const weightUp=w[n-1]>w[n-2];
  const weightDropPersistent=(n>=3)&&(w[n-1]<w[n-2]&&w[n-2]<=w[n-3]&&w[n-1]<w[n-3]);
  const repsDeclinePersistent=(n>=3)&&(fr[0]>fr[1]&&fr[1]>fr[2]);
  const sameWeight=last.every(s=>s.weight===recent.weight);
  const formCollapse=(!bw)&&recent.firstReps<=6&&recent.drop>=4;
  const avg=(fr.reduce((a,b)=>a+b,0)/n).toFixed(1).replace('.',',');

  /* REDUZIR */
  if(!weightUp&&(weightDropPersistent||(repsDeclinePersistent&&sameWeight)||formCollapse)){
    let why;
    if(weightDropPersistent) why='A carga vem caindo em sess&otilde;es seguidas ('+w.map(kgfmt).join('&rarr;')+' kg) &mdash; isso &eacute; uma tend&ecirc;ncia consistente, n&atilde;o um dia ruim isolado.';
    else if(repsDeclinePersistent) why='As reps da 1&ordf; s&eacute;rie ca&iacute;ram sess&atilde;o ap&oacute;s sess&atilde;o no mesmo peso ('+fr.join('&rarr;')+'). Sinal de fadiga acumulada, n&atilde;o de progresso.';
    else why='A 1&ordf; s&eacute;rie j&aacute; sai baixa ('+recent.firstReps+' reps) e despenca dentro da sess&atilde;o. A execu&ccedil;&atilde;o est&aacute; colapsando cedo.';
    return {status:'reduzir',reason:'Queda consistente',
      detail:why+' Recuar um pouco por 1&ndash;2 semanas costuma destravar e te devolver &agrave; faixa de 10&ndash;12.',
      sug: bw?'Reduza o volume (menos reps-alvo) ou aumente o descanso entre s&eacute;ries.'
            :'Reduza para ~'+kgfmt(tgt)+' kg e reconstrua at&eacute; voltar a 11+ na 1&ordf; s&eacute;rie.',
      move: bw?'reduzir':kgfmt(recent.weight)+' &rarr; <b>'+kgfmt(tgt)+'</b> kg'};
  }

  /* AUMENTAR -- com trava de recencia: a ultima sessao tem que continuar forte (>=10) */
  const controlledDrop=recent.drop<=4,noDecline=!repsDeclinePersistent&&!weightDropPersistent;
  if(hits>=2&&recent.firstReps>=10&&controlledDrop&&noDecline)
    return {status:'aumentar',reason:'Pronto para subir',
      detail:'Sua 1&ordf; s&eacute;rie bateu 11+ reps em '+hits+' das &uacute;ltimas '+n+' sess&otilde;es ('+fr.join(', ')+') e a &uacute;ltima continua firme, com a queda dentro da sess&atilde;o sob controle. Voc&ecirc; domou esse peso de forma consistente &mdash; n&atilde;o foi sorte de um dia.',
      sug: bw?'Aumente a dificuldade (mais reps-alvo ou progress&atilde;o do movimento).'
            :'Suba para '+kgfmt(recent.weight+2.5)+' kg no pr&oacute;ximo treino. &Eacute; normal a 1&ordf; s&eacute;rie cair para ~9&ndash;10 reps no peso novo; em 2&ndash;3 sess&otilde;es voc&ecirc; recupera.',
      move: bw?'subir dificuldade':kgfmt(recent.weight)+' &rarr; <b>'+kgfmt(recent.weight+2.5)+'</b> kg'};

  const moveManter = bw?'manter':'manter '+kgfmt(recent.weight)+' kg';

  /* ajuste de carga recente */
  if(weightUp)
    return {status:'manter',reason:'Ajuste de carga recente',
      detail:'Voc&ecirc; subiu a carga h&aacute; pouco ('+w.map(kgfmt).join('&rarr;')+' kg), ent&atilde;o &eacute; esperado as reps recuarem agora. N&atilde;o &eacute; problema &mdash; &eacute; o come&ccedil;o do novo ciclo.',
      sug:'Fique em '+kgfmt(recent.weight)+' kg e foque em recuperar as repeti&ccedil;&otilde;es at&eacute; 11+ na 1&ordf; s&eacute;rie.',move:moveManter};
  /* bateu o topo 2x mas a ultima recuou */
  if(hits>=2)
    return {status:'manter',reason:'Quase l&aacute; &mdash; recuou na &uacute;ltima',
      detail:'Voc&ecirc; bateu 11+ na 1&ordf; s&eacute;rie em sess&otilde;es recentes, mas a &uacute;ltima recuou ('+fr.join(', ')+'). Quero ver a 1&ordf; s&eacute;rie forte de novo antes de subir &mdash; assim a progress&atilde;o n&atilde;o vira recuo na semana seguinte.',
      sug:'Mantenha '+kgfmt(recent.weight)+' kg e repita um bom desempenho na 1&ordf; s&eacute;rie mais uma vez.',move:moveManter};
  /* pico isolado */
  if(hits===1)
    return {status:'manter',reason:'Quase l&aacute; &mdash; pico isolado',
      detail:'Voc&ecirc; chegou a 11+ na 1&ordf; s&eacute;rie em s&oacute; 1 das &uacute;ltimas '+n+' sess&otilde;es ('+fr.join(', ')+') &mdash; foi um pico isolado. Para subir com seguran&ccedil;a, o ideal &eacute; repetir isso em 2 de 3 sess&otilde;es.',
      sug:'Mantenha '+kgfmt(recent.weight)+' kg e busque repetir o bom desempenho.',move:moveManter};
  /* oscilacao alta dentro da sessao */
  if(recent.drop>=4&&recent.firstReps>=9)
    return {status:'manter',reason:'Quase l&aacute; &mdash; oscila&ccedil;&atilde;o alta',
      detail:'A 1&ordf; s&eacute;rie vai bem ('+recent.firstReps+'), mas dentro da mesma sess&atilde;o cai bastante ('+recent.reps.join('&rarr;')+'). Essa oscila&ccedil;&atilde;o mostra que o peso ainda n&atilde;o est&aacute; domado.',
      sug:'Mantenha '+kgfmt(recent.weight)+' kg at&eacute; a queda dentro da sess&atilde;o diminuir; a&iacute; sobe.',move:moveManter};
  /* construindo reps */
  return {status:'manter',reason:'Construindo repeti&ccedil;&otilde;es',
    detail:'A m&eacute;dia da 1&ordf; s&eacute;rie est&aacute; em ~'+avg+' reps, ainda abaixo da faixa de subida (11+ na 1&ordf; s&eacute;rie). Sem queda preocupante &mdash; &eacute; s&oacute; seguir ganhando repeti&ccedil;&atilde;o.',
    sug: bw?'Continue e foque em ganhar repeti&ccedil;&otilde;es.':'Mantenha '+kgfmt(recent.weight)+' kg e mire chegar a 11 reps na 1&ordf; s&eacute;rie.',move:moveManter};
}

function computeRecs(){
  const map={};
  RAW.sessions.forEach(s=>s.ex.forEach(e=>{
    const ws=workingSet(e);if(!ws.reps.length)return;
    const fr=ws.reps[0],lr=ws.reps[ws.reps.length-1];
    (map[e.n]=map[e.n]||{nome:e.n,grupos:{},sess:[]});
    map[e.n].grupos[s.grupo]=(map[e.n].grupos[s.grupo]||0)+1;
    map[e.n].sess.push({dateISO:s.dateISO,weight:ws.weight,reps:ws.reps,
      firstReps:fr,lastReps:lr,drop:fr-lr,bodyweight:ws.weight===0});
  }));
  const maxISO=RAW.meta.maxISO;
  return Object.values(map).map(m=>{
    m.sess.sort((a,b)=>a.dateISO<b.dateISO?-1:1);
    const grupo=Object.keys(m.grupos).sort((a,b)=>m.grupos[b]-m.grupos[a])[0];
    const last=m.sess.slice(-3);
    const r=classifyRec(last,m.sess);
    return {nome:m.nome,grupo,gordem:(grpOrder[grupo]!=null?grpOrder[grupo]:9),
      last,nSess:m.sess.length,...r};
  }).filter(r=>{
    const lISO=r.last[r.last.length-1].dateISO;
    if((parseISO(maxISO)-parseISO(lISO))/864e5>35) return false;      // fora da rotina atual
    if(Math.max.apply(null,r.last[r.last.length-1].reps)===0) return false; // cardio
    return true;
  }).sort((a,b)=>a.gordem-b.gordem
    ||recStatusOrder[a.status]-recStatusOrder[b.status]
    ||(recReasonRank[a.reason]!=null?recReasonRank[a.reason]:3)-(recReasonRank[b.reason]!=null?recReasonRank[b.reason]:3)
    ||a.nome.localeCompare(b.nome));
}

function renderRecsTab(){
  if(!STATE.recGrupo)STATE.recGrupo='Todos';
  const all=computeRecs();
  const AI=RAW.recsAI||{};
  const cnt={aumentar:0,manter:0,reduzir:0};all.forEach(r=>cnt[r.status]++);
  document.getElementById('recnote').innerHTML=
    'Baseado nas <b>3 sess&otilde;es mais recentes</b> de cada exerc&iacute;cio da sua rotina atual (n&atilde;o muda com o filtro de datas do topo). '+
    'Faixa-alvo <b>10&ndash;12 reps</b>: o crit&eacute;rio olha a <b>1&ordf; s&eacute;rie</b> (a mais descansada). Toque em "Por qu&ecirc;?" para ver o racioc&iacute;nio.';

  const present=[...new Set(all.map(r=>r.grupo))];
  const chips=['Todos'].concat(['Pernas','Empurrar','Puxar','Outros'].filter(g=>present.includes(g)));
  if(chips.indexOf(STATE.recGrupo)<0)STATE.recGrupo='Todos';
  document.getElementById('recfilters').innerHTML=chips.map(g=>
    `<button class="chip ${g===STATE.recGrupo?'on':''}" data-g="${g}">${g}</button>`).join('');
  document.querySelectorAll('#recfilters .chip').forEach(c=>c.onclick=()=>{STATE.recGrupo=c.dataset.g;renderRecsTab();});

  const view=all.filter(r=>STATE.recGrupo==='Todos'||r.grupo===STATE.recGrupo);
  const box=document.getElementById('reclist');
  if(!view.length){box.innerHTML='<div class="card"><div class="empty-lg"><b>Sem recomenda&ccedil;&otilde;es</b>Nenhum exerc&iacute;cio deste grupo na rotina recente.</div></div>';return;}

  const label={aumentar:'&#9650; Aumentar',manter:'&#9644; Manter',reduzir:'&#9660; Reduzir'};
  const groups={};view.forEach(r=>{(groups[r.grupo]=groups[r.grupo]||[]).push(r);});
  let html='';
  ['Pernas','Empurrar','Puxar','Outros'].filter(g=>groups[g]).forEach(g=>{
    html+=`<div class="recgrp" style="color:${grpColor[g]}">${g}<span class="gln" style="background:${grpColor[g]};opacity:.18"></span></div>`;
    groups[g].forEach(r=>{
      const ai=AI[r.nome];
      const hist=r.last.map(s=>`<span>${s.weight>0?kgfmt(s.weight)+'kg ':''}${s.reps.join('-')}</span>`).join('');
      const detailHTML=ai
        ?`<p>${ai} <span style="color:var(--violet)">&#10024;</span></p>`
        :`<p>${r.detail}</p>`;
      html+=`<div class="rec s-${r.status}">
        <div class="rechead">
          <span class="recbadge b-${r.status}">${label[r.status]}</span>
          <div class="recnm">${r.nome}<span class="recwhytag">${r.reason}</span></div>
          <div class="recmove">${r.move}${ai?'<span class="ai">&#10024;</span>':''}</div>
        </div>
        <details class="recwhy"><summary>Por qu&ecirc;?
          <svg class="chv" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg></summary>
          <div class="recbody">${detailHTML}
            <div class="sug"><b>Sugest&atilde;o</b>${r.sug}</div>
            <div class="hist"><b>&Uacute;ltimas:</b>${hist}</div>
          </div></details>
      </div>`;
    });
  });
  box.innerHTML=html;
}

/* ---------- range control ---------- */
function setActivePreset(){
  document.querySelectorAll('.preset').forEach(b=>{
    let on=false;
    if(b.hasAttribute('data-all')) on=(STATE.start===RAW.meta.minISO&&STATE.end===HI);
    else on=(STATE.end===HI&&STATE.start===clamp(addDays(HI,-(+b.dataset.days))));
    b.classList.toggle('on',on);});
}
function render(){
  const agg=aggregate();
  renderKPIs(agg.kpis);renderHeatmap(agg.daymap);renderWeekly(agg.weekly);
  renderHighlights(agg.exercises);renderExplorer(agg.exercises);renderSessions(agg.sessions);
  document.getElementById('periodo').innerHTML=
    pdate(STATE.start)+' &ndash; '+pdate(STATE.end)+' &middot; '+agg.kpis.sessoes+' sess&otilde;es';
  document.getElementById('dStart').value=STATE.start;
  document.getElementById('dEnd').value=STATE.end;
  setActivePreset();
}
document.querySelectorAll('.preset').forEach(b=>b.onclick=()=>{
  if(b.hasAttribute('data-all')){STATE.start=RAW.meta.minISO;STATE.end=HI;}
  else{STATE.end=HI;STATE.start=clamp(addDays(HI,-(+b.dataset.days)));}
  render();
});
function onDateChange(){
  let s=document.getElementById('dStart').value||RAW.meta.minISO;
  let e=document.getElementById('dEnd').value||HI;
  s=clamp(s);e=clamp(e);if(s>e){const t=s;s=e;e=t;}
  STATE.start=s;STATE.end=e;render();
}
['dStart','dEnd'].forEach(id=>{const el=document.getElementById(id);
  el.min=RAW.meta.minISO;el.max=HI;el.onchange=onDateChange;});

/* init: abre de 14/05 ate o dia atual */
STATE.start=clamp('2026-05-14');STATE.end=HI;
render();
renderRecsTab();
</script>
"""

head = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Evolu&ccedil;&atilde;o de Treinos &mdash; Leonardo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
"""

JS = JS.replace('__RAWJSON__', raw).replace('2026-05-14', DATA_INICIO)
html = head + style + EXTRA_CSS + REC_CSS + "</head>\n<body>\n" + BODY + JS + "\n</body>\n</html>"
open(SAIDA,'w',encoding='utf-8').write(html)
print('OK ->', SAIDA, '|', round(len(html)/1024,1),'KB |', len(sessions),'sessoes |', raw_meta['minISO'],'a',raw_meta['maxISO'])
